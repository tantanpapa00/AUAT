# patch_poll_worker_changes_v1.py
# Usage:
#   cd C:\autobot
#   python .\patch_poll_worker_changes_v1.py

from __future__ import annotations
import re
import sys
from pathlib import Path
from datetime import datetime

ROOT = Path.cwd()
MAIN = ROOT / "app" / "main.py"

def die(msg: str) -> None:
    print(f"[patch-worker-changes-v1] ERROR: {msg}", file=sys.stderr)
    sys.exit(1)

def backup(path: Path) -> Path:
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    bak = path.with_suffix(path.suffix + f".bak.{ts}")
    bak.write_bytes(path.read_bytes())
    return bak

def main():
    if not MAIN.exists():
        die(f"not found: {MAIN}")

    txt = MAIN.read_text(encoding="utf-8-sig")

    # Idempotency markers
    if "# [POLL_CHANGES_WRAPPER_V1]" in txt and "# [ORDER_POLL_WORKER_V1]" in txt:
        print("[patch-worker-changes-v1] OK (already applied)")
        return

    # 1) Rename existing poll_orders_once -> _poll_orders_once_impl (only if not already renamed)
    if "def poll_orders_once(*, limit: int = 20) -> dict:" in txt and "def _poll_orders_once_impl(*, limit: int = 20) -> dict:" not in txt:
        txt = txt.replace(
            "def poll_orders_once(*, limit: int = 20) -> dict:",
            "def _poll_orders_once_impl(*, limit: int = 20) -> dict:",
            1
        )

    # Find the impl function block (renamed) so we can insert wrapper right after it
    impl_sig = r"def _poll_orders_once_impl\(\*, limit: int = 20\) -> dict:"
    m_sig = re.search(impl_sig, txt)
    if not m_sig:
        die("cannot find: def _poll_orders_once_impl(*, limit: int = 20) -> dict: (rename may have failed)")

    # Find end of function block: until next top-level def/@app
    start = m_sig.start()
    m_end = re.search(r"\n(?=@app\.|def\s+)", txt[m_sig.end():])
    if not m_end:
        die("cannot locate end of _poll_orders_once_impl block")
    end = m_sig.end() + m_end.start()

    # 2) Insert wrapper (changes-only return) if missing
    if "# [POLL_CHANGES_WRAPPER_V1]" not in txt:
        wrapper = r'''

# [POLL_CHANGES_WRAPPER_V1]
def poll_orders_once(*, limit: int = 20) -> dict:
    """
    poll_orders_once 래퍼:
    - 기존 구현(_poll_orders_once_impl)을 그대로 사용하되,
    - 호출 전/후 스냅샷 비교로 "실제 변경분(changes)"만 items로 반환합니다.
    """
    # 1) BEFORE snapshot (candidates only)
    before = {}
    candidate_ids = []

    try:
        db_gen = get_db()
        db = next(db_gen)
        try:
            rows = db.execute(text("""
                select id, asset_id, symbol, market, side, qty, order_type,
                       status, okx_order_id, okx_state, filled_qty, avg_px, last_checked_at
                  from orders
                 where okx_order_id is not null
                   and status in ('sent','partial')
                 order by coalesce(last_checked_at, to_timestamp(0)) asc, id asc
                 limit :lim
            """), {"lim": limit}).mappings().all()

            for r in rows:
                oid = int(r["id"])
                candidate_ids.append(oid)
                before[oid] = {
                    "status": r.get("status"),
                    "okx_state": r.get("okx_state"),
                    "filled_qty": r.get("filled_qty"),
                    "avg_px": r.get("avg_px"),
                    "last_checked_at": r.get("last_checked_at"),
                }
        finally:
            try:
                db_gen.close()
            except Exception:
                pass
    except Exception as e:
        # snapshot 실패해도 impl은 돌 수 있으니 계속 진행
        candidate_ids = []
        before = {}

    # 2) Run existing implementation
    impl_res = {}
    try:
        impl_res = _poll_orders_once_impl(limit=limit) or {}
    except Exception as e:
        # impl 자체가 죽어도 /tv는 영향 없도록 여기서 삼킴
        return {"ok": False, "count": 0, "items": [], "note": f"impl_failed: {e}"}

    # 3) AFTER snapshot for candidate ids
    changes = []
    if candidate_ids:
        try:
            db_gen2 = get_db()
            db2 = next(db_gen2)
            try:
                after_rows = db2.execute(text("""
                    select id, asset_id, symbol, market, side, qty, order_type,
                           status, okx_order_id, okx_state, filled_qty, avg_px, last_checked_at, reason
                      from orders
                     where id = any(:ids)
                     order by id asc
                """), {"ids": candidate_ids}).mappings().all()

                for r in after_rows:
                    oid = int(r["id"])
                    b = before.get(oid, {})
                    a_status = r.get("status")
                    a_state  = r.get("okx_state")
                    a_fq     = r.get("filled_qty")
                    a_apx    = r.get("avg_px")

                    changed = (
                        a_status != b.get("status")
                        or (a_state or None) != (b.get("okx_state") or None)
                        or (a_fq or None) != (b.get("filled_qty") or None)
                        or (a_apx or None) != (b.get("avg_px") or None)
                    )

                    if changed:
                        changes.append({
                            "order_id": oid,
                            "asset_id": r.get("asset_id"),
                            "symbol": r.get("symbol"),
                            "market": r.get("market"),
                            "side": r.get("side"),
                            "qty": r.get("qty"),
                            "order_type": r.get("order_type"),
                            "from_status": b.get("status"),
                            "to_status": a_status,
                            "from_okx_state": b.get("okx_state"),
                            "to_okx_state": a_state,
                            "filled_qty": a_fq,
                            "avg_px": a_apx,
                            "okx_order_id": r.get("okx_order_id"),
                            "last_checked_at": r.get("last_checked_at"),
                            "reason": r.get("reason"),
                        })
            finally:
                try:
                    db_gen2.close()
                except Exception:
                    pass
        except Exception:
            # after 조회 실패 시 changes 없이 반환
            pass

    note = "changes_only"
    impl_note = impl_res.get("note") if isinstance(impl_res, dict) else None
    if impl_note:
        note = f"{note} | impl:{impl_note}"

    return {
        "ok": True,
        "count": len(changes),
        "items": changes,
        "scanned": len(candidate_ids),
        "note": note,
    }
'''
        txt = txt[:end] + wrapper + txt[end:]

    # 3) Insert background worker startup/shutdown if missing
    if "# [ORDER_POLL_WORKER_V1]" not in txt:
        # Place after "app = FastAPI" line
        m_app = re.search(r"^app\s*=\s*FastAPI\(.*\)\s*$", txt, flags=re.MULTILINE)
        if not m_app:
            die("cannot find: app = FastAPI(...) line for worker insertion")

        insert_pos = m_app.end()

        worker = r'''

# [ORDER_POLL_WORKER_V1]
# ORDER_POLL_ENABLE=1 이면 서버 기동 시 주문상태 폴링 워커를 백그라운드로 실행합니다.
# - ORDER_POLL_INTERVAL: 초 (default 5)
# - ORDER_POLL_BATCH: 한번에 처리할 주문 수 (default 20)
import os as _os
import threading as _threading

try:
    _poll_logger = logger  # type: ignore[name-defined]
except Exception:
    import logging as _logging
    _poll_logger = _logging.getLogger("autobot.poll")

_POLL_STOP = _threading.Event()
_POLL_THREAD = None

def _poll_worker_loop():
    interval = float(_os.getenv("ORDER_POLL_INTERVAL", "5") or "5")
    batch = int(_os.getenv("ORDER_POLL_BATCH", "20") or "20")
    _poll_logger.info("order-poll-worker started interval=%s batch=%s", interval, batch)

    # loop
    while not _POLL_STOP.is_set():
        try:
            poll_orders_once(limit=batch)  # changes-only wrapper
        except Exception as e:
            try:
                _poll_logger.exception("order-poll-worker error: %s", e)
            except Exception:
                pass
        _POLL_STOP.wait(interval)

@app.on_event("startup")
def _start_order_poll_worker():
    enable = (_os.getenv("ORDER_POLL_ENABLE", "0") or "0").strip().lower()
    if enable not in ("1", "true", "yes", "y", "on"):
        return

    global _POLL_THREAD
    if _POLL_THREAD and getattr(_POLL_THREAD, "is_alive", lambda: False)():
        return

    _POLL_STOP.clear()
    _POLL_THREAD = _threading.Thread(target=_poll_worker_loop, daemon=True, name="order-poll-worker")
    _POLL_THREAD.start()

@app.on_event("shutdown")
def _stop_order_poll_worker():
    _POLL_STOP.set()
'''
        txt = txt[:insert_pos] + worker + txt[insert_pos:]

    bak = backup(MAIN)
    MAIN.write_text(txt, encoding="utf-8")
    print("[patch-worker-changes-v1] OK")
    print(f"[patch-worker-changes-v1] main.py -> {MAIN} (backup: {bak.name})")

if __name__ == "__main__":
    main()

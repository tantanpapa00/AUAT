# patch_changes_hangfix_v1.py
# Usage:
#   cd C:\autobot
#   python .\patch_changes_hangfix_v1.py

from __future__ import annotations
import sys, re
from pathlib import Path
from datetime import datetime

MAIN = Path(r"C:\autobot\app\main.py")

def die(msg: str):
    print(f"[patch-changes-hangfix-v1] ERROR: {msg}", file=sys.stderr)
    sys.exit(1)

def backup(path: Path) -> Path:
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    bak = path.with_suffix(path.suffix + f".bak.{ts}")
    bak.write_bytes(path.read_bytes())
    return bak

def replace_between(txt: str, start_marker: str, end_marker: str, new_block: str) -> str:
    s = txt.find(start_marker)
    if s < 0:
        die(f"marker not found: {start_marker}")
    e = txt.find(end_marker, s)
    if e < 0:
        # fallback: until next @app or EOF
        e2 = txt.find("\n@app.", s)
        e = e2 if e2 >= 0 else len(txt)
    return txt[:s] + new_block + txt[e:]

def main():
    if not MAIN.exists():
        die(f"not found: {MAIN}")

    txt = MAIN.read_text(encoding="utf-8-sig")

    # (A) poll_orders_once wrapper를 v4로 강제 교체 (후보 0이면 즉시 반환)
    new_wrapper = r'''
# [POLL_CHANGES_WRAPPER_V1]
def poll_orders_once(*, limit: int = 20) -> dict:
    """
    poll_orders_once 래퍼 (v4):
    - okx_order_id 있는 'sent/partial'만 대상.
    - 대상이 0건이면 OKX 호출 없이 즉시 반환 (changes 모드 타임아웃 방지).
    - 대상이 있으면 기존 구현(_poll_orders_once_impl)을 1회 실행 후 전/후 비교로 변경분만 반환.
    """
    candidate_ids: list[int] = []
    before: dict[int, dict] = {}

    # 1) BEFORE snapshot
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
    except Exception:
        return {"ok": True, "count": 0, "items": [], "scanned": 0, "note": "changes_only | snapshot_failed"}

    # ✅ 핵심: 후보 0건이면 OKX 호출 없이 즉시 반환
    if not candidate_ids:
        return {"ok": True, "count": 0, "items": [], "scanned": 0, "note": "changes_only | no_candidates"}

    # 2) Run impl (may call OKX)
    try:
        _poll_orders_once_impl(limit=limit)
    except Exception as e:
        return {"ok": False, "count": 0, "items": [], "scanned": len(candidate_ids), "note": f"impl_failed: {e}"}

    # 3) AFTER snapshot + diff
    changes: list[dict] = []
    try:
        db_gen2 = get_db()
        db2 = next(db_gen2)
        try:
            params = {}
            ph = []
            for i, oid in enumerate(candidate_ids):
                k = f"id{i}"
                params[k] = int(oid)
                ph.append(f":{k}")

            sql = f"""
                select id, asset_id, symbol, market, side, qty, order_type,
                       status, okx_order_id, okx_state, filled_qty, avg_px, last_checked_at, reason
                  from orders
                 where id in ({", ".join(ph)})
                 order by id asc
            """
            after_rows = db2.execute(text(sql), params).mappings().all()

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
        return {"ok": True, "count": 0, "items": [], "scanned": len(candidate_ids), "note": "changes_only | diff_failed"}

    return {"ok": True, "count": len(changes), "items": changes, "scanned": len(candidate_ids), "note": "changes_only"}
'''.lstrip("\n")

    txt = replace_between(txt, "# [POLL_CHANGES_WRAPPER_V1]", "# [ORDER_POLL_WORKER_V1]", new_wrapper + "\n# [ORDER_POLL_WORKER_V1]\n")

    # (B) /api/diag/poll-now changes 경로에 "스레드 타임아웃(3초)" 강제
    #     res = poll_orders_once(...) 호출을 찾아서 안전 래퍼로 교체
    pattern = r"res\s*=\s*poll_orders_once\(limit\s*=\s*limit\)\s*#\s*changes-only wrapper"
    if not re.search(pattern, txt):
        # 어떤 버전은 주석이 다를 수 있어 대체 패턴도 시도
        pattern = r"res\s*=\s*poll_orders_once\(limit\s*=\s*limit\)"
        if not re.search(pattern, txt):
            die("cannot find call to poll_orders_once(limit=limit) in api_poll_now")

    repl = r'''# changes-only wrapper (thread timeout guard)
        import threading as _th
        import queue as _q

        _qq = _q.Queue()

        def _run_changes():
            try:
                _qq.put(poll_orders_once(limit=limit))
            except Exception as _e:
                _qq.put({"ok": False, "count": 0, "items": [], "note": f"changes_exception: {_e}"})

        _t = _th.Thread(target=_run_changes, daemon=True)
        _t.start()
        _t.join(3.0)

        if _t.is_alive():
            return {"ok": False, "count": 0, "items": [], "note": "changes_timeout"}

        res = _qq.get() if not _qq.empty() else {"ok": True, "count": 0, "items": [], "note": "changes_empty"}'''

    txt = re.sub(pattern, repl, txt, count=1)

    bak = backup(MAIN)
    MAIN.write_text(txt, encoding="utf-8")
    print("[patch-changes-hangfix-v1] OK")
    print(f"[patch-changes-hangfix-v1] main.py -> {MAIN} (backup: {bak.name})")

if __name__ == "__main__":
    main()

# patch_poll_lock_v1.py
# Usage:
#   cd C:\autobot
#   python .\patch_poll_lock_v1.py

from __future__ import annotations
import re, sys
from pathlib import Path
from datetime import datetime

ROOT = Path.cwd()
MAIN = ROOT / "app" / "main.py"

def die(msg: str):
    print(f"[patch-poll-lock-v1] ERROR: {msg}", file=sys.stderr)
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

    # 1) Insert global lock near worker marker
    if "_POLL_LOCK" not in txt:
        m = re.search(r"# \[ORDER_POLL_WORKER_V1\][\s\S]*?\nimport os as _os\nimport threading as _threading\n", txt)
        if not m:
            die("cannot find ORDER_POLL_WORKER_V1 import section")
        insert_pos = m.end()
        lock_code = "\n_POLL_LOCK = _threading.Lock()\n"
        txt = txt[:insert_pos] + lock_code + txt[insert_pos:]

    # 2) Replace poll-now endpoint block to fast-fail if busy
    pattern = r'@app\.post\("/api/diag/poll-now"\)[\s\S]*?(?=\n@app\.|\Z)'
    m = re.search(pattern, txt)
    if not m:
        die('cannot find endpoint block: @app.post("/api/diag/poll-now")')

    new_block = r'''@app.post("/api/diag/poll-now")
def api_poll_now(
    limit: int = Query(20, ge=1, le=200),
    mode: str = Query("changes", pattern="^(changes|recent)$"),
    db: Session = Depends(get_db),
):
    """
    수동 폴링(디버깅용). ORDER_POLL_ENABLE과 무관하게 1회 실행합니다.
    - 워커와 동시 실행 시 DB 대기/락으로 멈추는 현상 방지: busy면 즉시 반환
    """
    # ✅ 절대 대기 금지: 0.3초 내 락 못 잡으면 즉시 반환
    try:
        acquired = _POLL_LOCK.acquire(timeout=0.3)
    except Exception:
        acquired = False

    if not acquired:
        return {"ok": False, "count": 0, "items": [], "note": "poll_busy"}

    try:
        _ensure_orders_table(db)
        _ensure_order_tracking_cols(db)

        if mode == "recent":
            rows = db.execute(text("""
                select
                    id as order_id,
                    asset_id, symbol, market, side, qty, order_type,
                    status, okx_order_id, okx_state, filled_qty, avg_px, last_checked_at, reason
                from orders
                where last_checked_at is not null
                order by last_checked_at desc, id desc
                limit :lim
            """), {"lim": limit}).mappings().all()

            return {"ok": True, "count": len(rows), "items": [dict(r) for r in rows], "note": "recent_checked"}

        # mode == changes
        res = poll_orders_once(limit=limit)  # changes-only wrapper
        if isinstance(res, dict):
            res.setdefault("note", "changes_only")
            return res
        return {"ok": True, "count": 0, "items": [], "note": "changes_only_empty"}

    except Exception as e:
        try:
            db.rollback()
        except Exception:
            pass
        return {"ok": False, "count": 0, "items": [], "note": f"error: {e}"}
    finally:
        try:
            _POLL_LOCK.release()
        except Exception:
            pass
'''
    txt = re.sub(pattern, new_block, txt, count=1)

    # 3) Make worker skip if lock is held (no pile-up)
    # Replace the core call line inside _poll_worker_loop
    if "poll_orders_once(limit=batch)" in txt and "if not _POLL_LOCK.acquire" not in txt:
        txt = txt.replace(
            "            poll_orders_once(limit=batch)  # changes-only wrapper",
            "            if _POLL_LOCK.acquire(timeout=0.1):\n"
            "                try:\n"
            "                    poll_orders_once(limit=batch)  # changes-only wrapper\n"
            "                finally:\n"
            "                    _POLL_LOCK.release()\n"
            "            else:\n"
            "                pass\n",
            1
        )

    bak = backup(MAIN)
    MAIN.write_text(txt, encoding="utf-8")
    print("[patch-poll-lock-v1] OK")
    print(f"[patch-poll-lock-v1] main.py -> {MAIN} (backup: {bak.name})")

if __name__ == "__main__":
    main()

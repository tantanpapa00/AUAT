# patch_pollnow_mode_v2.py
# Usage:
#   cd C:\autobot
#   python .\patch_pollnow_mode_v2.py

from __future__ import annotations
import re
import sys
from pathlib import Path
from datetime import datetime

ROOT = Path.cwd()
MAIN = ROOT / "app" / "main.py"

def die(msg: str) -> None:
    print(f"[patch-pollnow-mode-v2] ERROR: {msg}", file=sys.stderr)
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

    mode:
      - changes (default): 이번 폴링에서 "실제 변경된 주문"만 반환 (count=변경건수)
      - recent: 최근 last_checked_at 기준 목록 반환 (관측성/히스토리 확인용)
    """
    try:
        _ensure_orders_table(db)
        _ensure_order_tracking_cols(db)

        if mode == "recent":
            rows = db.execute(text("""
                select
                    id as order_id,
                    asset_id, symbol, market, side, qty, order_type,
                    status,
                    okx_order_id,
                    okx_state,
                    filled_qty,
                    avg_px,
                    last_checked_at,
                    reason
                from orders
                where last_checked_at is not null
                order by last_checked_at desc, id desc
                limit :lim
            """), {"lim": limit}).mappings().all()

            return {
                "ok": True,
                "count": len(rows),
                "items": [dict(r) for r in rows],
                "note": "recent_checked",
            }

        # mode == "changes"
        res = poll_orders_once(limit=limit)  # changes-only wrapper in v1
        if isinstance(res, dict):
            # poll_orders_once 자체가 changes-only를 반환하므로 그대로 리턴
            res.setdefault("note", "changes_only")
            return res

        return {"ok": True, "count": 0, "items": [], "note": "changes_only_empty"}

    except Exception as e:
        try:
            db.rollback()
        except Exception:
            pass
        # poll-now는 절대 죽지 않게
        return {"ok": False, "count": 0, "items": [], "note": f"error: {e}"}
'''
    new_txt = re.sub(pattern, new_block, txt, count=1)
    if new_txt == txt:
        die("replace no-op (unexpected)")

    bak = backup(MAIN)
    MAIN.write_text(new_txt, encoding="utf-8")
    print("[patch-pollnow-mode-v2] OK")
    print(f"[patch-pollnow-mode-v2] main.py -> {MAIN} (backup: {bak.name})")

if __name__ == "__main__":
    main()

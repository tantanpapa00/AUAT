# patch_pollnow_response_v1.py
# Usage:
#   cd C:\autobot
#   python .\patch_pollnow_response_v1.py

from __future__ import annotations
import sys
import re
from pathlib import Path
from datetime import datetime

ROOT = Path.cwd()
MAIN = ROOT / "app" / "main.py"

def die(msg: str) -> None:
    print(f"[patch-pollnow-v1] ERROR: {msg}", file=sys.stderr)
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

    # Replace whole endpoint block: @app.post("/api/diag/poll-now") ... until next @app. decorator
    pattern = r'@app\.post\("/api/diag/poll-now"\)[\s\S]*?(?=\n@app\.|\Z)'
    m = re.search(pattern, txt)
    if not m:
        die('cannot find endpoint block: @app.post("/api/diag/poll-now")')

    new_block = r'''@app.post("/api/diag/poll-now")
def api_poll_now(limit: int = Query(20, ge=1, le=200), db: Session = Depends(get_db)):
    """
    수동 폴링(디버깅용). ORDER_POLL_ENABLE과 무관하게 1회 실행합니다.

    ✅ 개선점:
    - poll_orders_once()가 items를 비워 반환하는 케이스가 있어도,
      "최근 last_checked_at 갱신된 주문 목록"을 fallback으로 반환하여 관측성을 확보합니다.
    """
    # 1) 기존 로직 실행
    res = poll_orders_once(limit=limit)

    # 2) 기존 결과가 items를 주면 그대로 반환
    try:
        if isinstance(res, dict) and res.get("items"):
            res["note"] = res.get("note") or "poll_orders_once"
            return res
    except Exception:
        pass

    # 3) fallback: 최근 체크된 주문을 보여줘서 "count=0 혼선" 제거
    try:
        _ensure_orders_table(db)
        _ensure_order_tracking_cols(db)

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
            "note": "recent_checked_fallback"
        }
    except Exception as e:
        return {"ok": True, "count": 0, "items": [], "note": f"fallback_failed: {e}"}
'''
    new_txt = re.sub(pattern, new_block, txt, count=1)
    if new_txt == txt:
        die("replace no-op (unexpected)")

    bak = backup(MAIN)
    MAIN.write_text(new_txt, encoding="utf-8")
    print("[patch-pollnow-v1] OK")
    print(f"[patch-pollnow-v1] main.py -> {MAIN} (backup: {bak.name})")

if __name__ == "__main__":
    main()

# patch_okx_order_tracking_v2.py
# Usage:
#   cd C:\autobot
#   python .\patch_okx_order_tracking_v2.py

from __future__ import annotations
import sys
import re
from pathlib import Path
from datetime import datetime

ROOT = Path.cwd()
MAIN = ROOT / "app" / "main.py"

def die(msg: str) -> None:
    print(f"[patch-v2] ERROR: {msg}", file=sys.stderr)
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

    # 1) Fix: do NOT mark sent when okx_order_id(ordId) is missing
    old = '_set_order_status(db, int(order_id), "sent", okx_order_id=okx_order_id, okx_response=okx_result)\n        db.commit()\n        return okx_result'
    if old not in txt:
        die("anchor not found for sent-without-ordId block")

    new = (
        'if not okx_order_id:\n'
        '            _set_order_status(db, int(order_id), "failed", reason="okx_no_ordId (check OKX env/key)", okx_response=okx_result)\n'
        '            db.commit()\n'
        '            return okx_result\n'
        '\n'
        '        _set_order_status(db, int(order_id), "sent", okx_order_id=okx_order_id, okx_response=okx_result)\n'
        '        db.commit()\n'
        '        return okx_result'
    )
    txt = txt.replace(old, new, 1)

    # 2) Add diag endpoint: fix bad rows (sent but okx_order_id is null)
    if '@app.post("/api/diag/fix-bad-sent")' not in txt:
        m = re.search(r'@app\.post\("/api/diag/poll-now"\)[\s\S]+?return poll_orders_once\(limit=limit\)\n', txt)
        if not m:
            die("cannot find /api/diag/poll-now block to insert fix endpoint")
        insert_pos = m.end()
        endpoint = r'''
@app.post("/api/diag/fix-bad-sent")
def api_fix_bad_sent(db: Session = Depends(get_db)):
    """
    정리용: okx_order_id 없이 sent로 남아있는 주문을 failed로 정리합니다.
    (이런 row는 정상 상태추적이 불가능)
    """
    try:
        _ensure_orders_table(db)
        _ensure_order_tracking_cols(db)
        r = db.execute(text("""
            update orders
               set status='failed',
                   reason=coalesce(reason,'') || ' | fixed: sent_without_ordId',
                   updated_at=now()
             where status='sent' and okx_order_id is null
        """))
        db.commit()
        return {"ok": True, "updated": int(getattr(r, "rowcount", 0) or 0)}
    except Exception as e:
        try:
            db.rollback()
        except Exception:
            pass
        return {"ok": False, "error": str(e)}
'''
        txt = txt[:insert_pos] + endpoint + "\n" + txt[insert_pos:]

    bak = backup(MAIN)
    MAIN.write_text(txt, encoding="utf-8")
    print("[patch-v2] OK")
    print(f"[patch-v2] main.py -> {MAIN} (backup: {bak.name})")

if __name__ == "__main__":
    main()

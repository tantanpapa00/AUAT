# patch_okx_dashboard_resync_v1.py
# Usage:
#   cd C:\autobot
#   python .\patch_okx_dashboard_resync_v1.py
#
# What it does:
# - Updates /api/diag/fix-bad-sent to also sync assets.last_* from orders
# - Adds /api/diag/resync-assets-last endpoint to recompute assets last_* from latest order per asset
# - Backup main.py before writing

from __future__ import annotations
import re
import sys
from pathlib import Path
from datetime import datetime

ROOT = Path.cwd()
MAIN = ROOT / "app" / "main.py"

def die(msg: str) -> None:
    print(f"[patch-v3] ERROR: {msg}", file=sys.stderr)
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

    # 1) Patch api_fix_bad_sent body to sync assets too
    # Find the function block and replace within it (simple anchor-based)
    anchor = '@app.post("/api/diag/fix-bad-sent")'
    pos = txt.find(anchor)
    if pos < 0:
        die("anchor not found: /api/diag/fix-bad-sent")

    # Grab function block roughly: from anchor to next @app. (or EOF)
    next_app = txt.find("\n@app.", pos + 1)
    if next_app < 0:
        block = txt[pos:]
        rest = ""
    else:
        block = txt[pos:next_app]
        rest = txt[next_app:]

    # Replace the entire function with a safer, richer version
    if "def api_fix_bad_sent" not in block:
        die("cannot locate def api_fix_bad_sent in block")

    new_fix = r'''@app.post("/api/diag/fix-bad-sent")
def api_fix_bad_sent(db: Session = Depends(get_db)):
    """
    정리용:
    1) okx_order_id 없이 sent로 남아있는 주문을 failed로 정리
    2) 해당 주문이 연결된 assets.last_* (전광판 컬럼)도 orders 기준으로 동기화
    """
    try:
        _ensure_orders_table(db)
        _ensure_order_tracking_cols(db)

        # 1) fix bad orders
        r = db.execute(text("""
            with fixed as (
                update orders
                   set status='failed',
                       reason=coalesce(reason,'') || ' | fixed: sent_without_ordId',
                       updated_at=now()
                 where status='sent' and okx_order_id is null
                 returning id
            )
            select count(*)::int as cnt from fixed
        """)).mappings().first()
        fixed_cnt = int((r or {}).get("cnt", 0))

        # 2) sync assets based on their last_order_id -> orders row
        # (전광판은 assets 컬럼을 보여주므로 반드시 맞춰야 함)
        db.execute(text("""
            update assets a
               set last_order_status = o.status,
                   last_order_reason = o.reason,
                   last_okx_order_id = o.okx_order_id,
                   last_filled_qty   = o.filled_qty,
                   last_order_avg_px = o.avg_px,
                   last_checked_at   = o.last_checked_at,
                   updated_at        = now()
              from orders o
             where a.last_order_id = o.id
        """))

        db.commit()
        return {"ok": True, "updated": fixed_cnt}
    except Exception as e:
        try:
            db.rollback()
        except Exception:
            pass
        return {"ok": False, "error": str(e)}
'''
    # Remove existing fix function by regex (from @app.post("/api/diag/fix-bad-sent") up to next decorator)
    replaced_block = re.sub(
        r'@app\.post\("/api/diag/fix-bad-sent"\)[\s\S]*?(?=\n@app\.|\Z)',
        new_fix + "\n",
        txt,
        count=1
    )
    if replaced_block == txt:
        die("failed to replace /api/diag/fix-bad-sent (regex no-op)")

    txt = replaced_block

    # 2) Add resync endpoint if missing
    if '@app.post("/api/diag/resync-assets-last")' not in txt:
        # Insert after fix-bad-sent function block
        insert_after = txt.find('@app.post("/api/diag/fix-bad-sent")')
        if insert_after < 0:
            die("cannot re-find fix-bad-sent after replacement")

        # find end of that function (next @app. after it)
        npos = txt.find("\n@app.", insert_after + 10)
        if npos < 0:
            npos = len(txt)

        resync = r'''
@app.post("/api/diag/resync-assets-last")
def api_resync_assets_last(db: Session = Depends(get_db)):
    """
    전광판 재동기화:
    assets별로 가장 최근 orders를 찾아 assets.last_*를 재계산합니다.
    (과거 패치/테스트로 assets와 orders가 어긋났을 때 한방에 정리)
    """
    try:
        _ensure_orders_table(db)
        _ensure_order_tracking_cols(db)

        # asset별 최신 order를 찾아서 assets 컬럼을 재기입
        db.execute(text("""
            with latest as (
                select distinct on (asset_id)
                       id as order_id,
                       asset_id,
                       status,
                       reason,
                       okx_order_id,
                       filled_qty,
                       avg_px,
                       last_checked_at,
                       created_at
                  from orders
                 where asset_id is not null
                 order by asset_id, created_at desc, id desc
            )
            update assets a
               set last_order_at     = now(),
                   last_order_id     = l.order_id,
                   last_order_status = l.status,
                   last_order_reason = l.reason,
                   last_okx_order_id = l.okx_order_id,
                   last_filled_qty   = l.filled_qty,
                   last_order_avg_px = l.avg_px,
                   last_checked_at   = l.last_checked_at,
                   updated_at        = now()
              from latest l
             where a.id = l.asset_id
        """))

        db.commit()
        return {"ok": True}
    except Exception as e:
        try:
            db.rollback()
        except Exception:
            pass
        return {"ok": False, "error": str(e)}
'''
        txt = txt[:npos] + resync + "\n" + txt[npos:]

    bak = backup(MAIN)
    MAIN.write_text(txt, encoding="utf-8")
    print("[patch-v3] OK")
    print(f"[patch-v3] main.py -> {MAIN} (backup: {bak.name})")

if __name__ == "__main__":
    main()

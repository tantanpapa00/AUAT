import re
import shutil
from datetime import datetime
from pathlib import Path

MAIN = Path(r"C:\autobot\app\main.py")

def backup(p: Path):
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    b = p.with_suffix(p.suffix + f".bak_{ts}")
    shutil.copy2(p, b)
    return b

HOME_BLOCK = r'''
# ---- Home API (Dashboard) ----
@app.get("/api/home")
def api_home(db: Session = Depends(get_db)):
    """
    UI 전광판용: assets + account/strategy 이름 join
    - 절대 500 내지 않도록: 실패 시에도 ok:true, items:[] 반환
    """
    q = text("""
        select
          a.id,
          acc.name as account_name,
          s.name   as strategy_name,
          a.symbol,
          a.market,
          a.is_active,
          a.last_signal_at,
          a.last_signal_id,
          a.last_order_at,
          a.last_order_status,
          a.last_order_reason
        from assets a
        join accounts acc on acc.id = a.account_id
        join strategies s on s.id = a.strategy_id
        order by a.id asc
    """)
    try:
        rows = db.execute(q).mappings().all()
        return {"ok": True, "items": [dict(r) for r in rows]}
    except Exception as e:
        # UI가 죽지 않게 200으로 빈 리스트 반환
        return {"ok": True, "items": [], "warn": str(e)}
'''

def upsert_import(src: str, needle: str, line_to_add: str) -> str:
    if needle in src:
        return src
    # sqlalchemy import/text 근처 위에 넣기
    m = re.search(r'^(from sqlalchemy .*|import sqlalchemy.*)$', src, flags=re.M)
    if m:
        pos = m.start()
        return src[:pos] + line_to_add + "\n" + src[pos:]
    return line_to_add + "\n" + src

def main():
    if not MAIN.exists():
        raise SystemExit(f"main.py not found: {MAIN}")

    src = MAIN.read_text(encoding="utf-8", errors="replace")
    b = backup(MAIN)
    print("Backup:", b)

    # 필요한 import 보장(이미 있으면 스킵)
    src = upsert_import(src, "from fastapi import Depends", "from fastapi import Depends")
    src = upsert_import(src, "from sqlalchemy.orm import Session", "from sqlalchemy.orm import Session")

    # /api/home 블록 찾아서 교체 (가장 안전한 패턴)
    pat = r'(?s)# ---- Home API \(Dashboard\) ----\n@app\.get\("/api/home"\)\n.*?\n(?=\n# ----|\n@app\.|\Z)'
    if re.search(pat, src):
        src = re.sub(pat, HOME_BLOCK.strip() + "\n", src)
        print("Replaced existing /api/home block")
    else:
        # 없으면 Accounts API 앞에 삽입
        anchor = "# ---- Accounts API ----"
        if anchor in src:
            src = src.replace(anchor, HOME_BLOCK + "\n" + anchor, 1)
            print("Inserted /api/home before Accounts API")
        else:
            src = src + "\n\n" + HOME_BLOCK + "\n"
            print("Appended /api/home at EOF")

    MAIN.write_text(src, encoding="utf-8")
    print("Patched:", MAIN)

if __name__ == "__main__":
    main()

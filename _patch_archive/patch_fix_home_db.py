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
    Minimal dashboard list for UI.
    - assets + account/strategy name join
    - last_* 컬럼은 있을 수도/없을 수도 있어서 2단 쿼리로 안전 처리
    """
    q_full = text("""
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
        order by a.id desc
    """)

    q_min = text("""
        select
          a.id,
          acc.name as account_name,
          s.name   as strategy_name,
          a.symbol,
          a.market,
          a.is_active,

          null::timestamp as last_signal_at,
          null::text      as last_signal_id,

          null::timestamp as last_order_at,
          null::text      as last_order_status,
          null::text      as last_order_reason

        from assets a
        join accounts acc on acc.id = a.account_id
        join strategies s on s.id = a.strategy_id
        order by a.id desc
    """)

    try:
        rows = db.execute(q_full).mappings().all()
    except Exception:
        rows = db.execute(q_min).mappings().all()

    return {"ok": True, "items": [dict(r) for r in rows]}
'''

def remove_engine_injection(src: str) -> str:
    # 1) 우리가 넣었던 engine 블록(마커 기준) 제거
    src = re.sub(
        r'\n# ---- DB Engine \(for simple query endpoints like /api/home\) ----.*?\n\n',
        '\n',
        src,
        flags=re.S
    )

    # 2) "try: engine except NameError: engine = create_engine(...)" 형태로 들어간 블록도 제거(마커가 없을 때 대비)
    src = re.sub(
        r'\ntry:\n\s*engine\s*# type: ignore\nexcept NameError:\n.*?engine\s*=\s*create_engine\(.*?\)\n',
        '\n',
        src,
        flags=re.S
    )

    # 3) from sqlalchemy import text, create_engine -> text만 남기기
    src = re.sub(r'from sqlalchemy import\s+text\s*,\s*create_engine\s*', 'from sqlalchemy import text', src)

    return src

def upsert_home_api(src: str) -> str:
    # 기존 /api/home 정의가 있으면 그 함수 블록을 교체
    pat = r'(?s)# ---- Home API \(Dashboard\) ----\n@app\.get\("/api/home"\)\n.*?\n(?=\n# ----|\n@app\.|\Z)'
    if re.search(pat, src):
        src = re.sub(pat, HOME_BLOCK.strip() + "\n", src)
        return src

    # 없으면 Accounts API 앞에 삽입
    anchor = "# ---- Accounts API ----"
    if anchor in src:
        return src.replace(anchor, HOME_BLOCK + "\n" + anchor, 1)

    # 최후: 파일 끝에 추가
    return src + "\n" + HOME_BLOCK + "\n"

def main():
    if not MAIN.exists():
        raise SystemExit(f"main.py not found: {MAIN}")

    src = MAIN.read_text(encoding="utf-8", errors="replace")
    b = backup(MAIN)
    print("Backup:", b)

    src = remove_engine_injection(src)
    src = upsert_home_api(src)

    MAIN.write_text(src, encoding="utf-8")
    print("Patched:", MAIN)

if __name__ == "__main__":
    main()

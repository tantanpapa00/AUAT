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

HOME_ROUTE = r'''

# ---- Home API (Dashboard) ----
@app.get("/api/home")
def api_home():
    """
    Minimal dashboard list for UI.
    Returns assets joined with account/strategy names and some last_* columns if present.
    """
    # Try to include last_signal/last_order if columns exist (older schema may not have them).
    q1 = """
    SELECT
      a.id,
      acc.name AS account_name,
      s.name   AS strategy_name,
      a.symbol,
      a.market,
      a.is_active,
      COALESCE(a.last_signal, '') AS last_signal,
      COALESCE(a.last_order,  '') AS last_order
    FROM assets a
    JOIN accounts acc ON acc.id = a.account_id
    JOIN strategies s ON s.id = a.strategy_id
    ORDER BY a.id DESC
    """
    q0 = """
    SELECT
      a.id,
      acc.name AS account_name,
      s.name   AS strategy_name,
      a.symbol,
      a.market,
      a.is_active,
      '' AS last_signal,
      '' AS last_order
    FROM assets a
    JOIN accounts acc ON acc.id = a.account_id
    JOIN strategies s ON s.id = a.strategy_id
    ORDER BY a.id DESC
    """
    with engine.begin() as conn:
        try:
            rows = conn.execute(text(q1)).mappings().all()
        except Exception:
            rows = conn.execute(text(q0)).mappings().all()

    return {"ok": True, "items": [dict(r) for r in rows]}
'''

def main():
    if not MAIN.exists():
        raise SystemExit(f"main.py not found: {MAIN}")

    src = MAIN.read_text(encoding="utf-8", errors="replace")

    # Already exists?
    if re.search(r'@app\.get\("/api/home"\)', src):
        print("Skip: /api/home already exists")
        return

    b = backup(MAIN)
    print("Backup:", b)

    # Insert before Accounts API section if possible, else append.
    anchor = "# ---- Accounts API ----"
    if anchor in src:
        src2 = src.replace(anchor, HOME_ROUTE + "\n" + anchor, 1)
    else:
        src2 = src + "\n" + HOME_ROUTE

    MAIN.write_text(src2, encoding="utf-8")
    print("Patched:", MAIN)

if __name__ == "__main__":
    main()

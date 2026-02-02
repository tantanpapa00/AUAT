import re
from pathlib import Path
from datetime import datetime

p = Path(r"C:\autobot\app\templates\index.html")
src = p.read_text(encoding="utf-8")

bak = p.with_suffix(p.suffix + f".bak_{datetime.now().strftime('%Y%m%d_%H%M%S')}")
bak.write_text(src, encoding="utf-8")

def repl(m):
    # m.group(1) is the state field name: accounts/strategies/assets
    fld = m.group(1)
    return f"state.{fld} = (Array.isArray(rows) ? rows : (rows.items || []));"

# 3군데: state.accounts / state.strategies / state.assets
dst, n = re.subn(r"state\.(accounts|strategies|assets)\s*=\s*rows\.items\s*\|\|\s*\[\]\s*;", repl, src)

p.write_text(dst, encoding="utf-8")
print("Backup:", bak)
print("Patched:", p)
print("Replaced:", n)

import re
from pathlib import Path
from datetime import datetime

p = Path(r"C:\autobot\app\templates\index.html")
src = p.read_text(encoding="utf-8")

bak = p.with_suffix(p.suffix + f".bak_{datetime.now().strftime('%Y%m%d_%H%M%S')}")
bak.write_text(src, encoding="utf-8")

pat = r"(window\.openStrategyConfig\s*=\s*async function\(strategyId\)\{\s*\n)"
m = re.search(pat, src)
if not m:
    raise SystemExit("Cannot find override: window.openStrategyConfig = async function(strategyId){")

inject = (
    m.group(1) +
    "      // [PATCH] ensure modal is visible even in override\n"
    "      const mb = document.getElementById('modal-backdrop');\n"
    "      if(mb) mb.style.display = 'flex';\n"
    "      const mt = document.getElementById('modal-title');\n"
    "      if(mt) mt.textContent = `Strategy 설정 (ID ${strategyId})`;\n"
)

dst = re.sub(pat, inject, src, count=1)
p.write_text(dst, encoding="utf-8")

print('Backup:', bak)
print('Patched:', p)

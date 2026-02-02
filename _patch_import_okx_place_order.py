import re
from pathlib import Path

p = Path(r"C:\autobot\app\main.py")
s = p.read_text(encoding="utf-8", errors="replace")

# 이미 import 되어있으면 스킵
if re.search(r"from\s+\.okx_api\s+import\s+okx_place_order", s):
    print("SKIP: okx_place_order already imported")
    raise SystemExit(0)

# import 블록(상단) 근처에 삽입: from .pine_parser import parse_pine_inputs 다음 줄에 넣기
anchor = r"from\s+\.pine_parser\s+import\s+parse_pine_inputs\s*\n"
m = re.search(anchor, s)
if not m:
    raise SystemExit("ERR: cannot find pine_parser import anchor")

ins = "from .okx_api import okx_place_order\n"
s2 = s[:m.end()] + ins + s[m.end():]

tmp = p.with_suffix(".py.tmp")
tmp.write_text(s2, encoding="utf-8")
if tmp.stat().st_size < 20000:
    raise SystemExit("ERR: patched file too small")

tmp.replace(p)
print("OK: imported okx_place_order from .okx_api")

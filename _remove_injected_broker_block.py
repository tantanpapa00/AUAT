import re
from pathlib import Path

p = Path(r"C:\autobot\app\main.py")
s = p.read_text(encoding="utf-8", errors="replace")

# 우리가 주입했던 블록(정확히 이 주석부터 payload=... 까지) 삭제
pat = r"\n\s*# ✅ broker send \(guarded\)\n\s*if created and order_id is not None:\n[\s\S]*?\n\s*\)\n"
s2, n = re.subn(pat, "\n", s, count=1)

if n == 0:
    raise SystemExit("ERR: injected broker block not found (nothing removed)")
p.write_text(s2, encoding="utf-8")
print("OK: removed injected broker block")

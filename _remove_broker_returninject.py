import re
from pathlib import Path

p = Path(r"C:\autobot\app\main.py")
s = p.read_text(encoding="utf-8", errors="replace")

# 우리가 넣었던 "post-return-inject safe spot" 블록 제거
pat = r"\n[ \t]*# ✅ broker send \(post-return-inject safe spot\)[\s\S]*?\n[ \t]*\)\n"
s2, n = re.subn(pat, "\n", s, count=1)

print("REMOVED:", n)
p.write_text(s2, encoding="utf-8")

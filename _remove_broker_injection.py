import re
from pathlib import Path

p = Path(r"C:\autobot\app\main.py")
s = p.read_text(encoding="utf-8", errors="replace")

# /tv 내부에 잘못 삽입된 broker send 블록 제거
# "# ✅ broker send" 부터 "except HTTPException as he:" 직전까지 삭제
pat = r"(?ms)^\s*#\s*✅\s*broker send.*?\n(?=^\s*except\s+HTTPException\s+as\s+he\s*:)"
s2, n = re.subn(pat, "", s)

print("REMOVED_BLOCKS =", n)
p.write_text(s2, encoding="utf-8")

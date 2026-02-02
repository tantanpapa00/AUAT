from pathlib import Path
p = Path(r"C:\autobot\app\main.py")
s = p.read_text(encoding="utf-8", errors="replace")
p.write_text(s.expandtabs(4), encoding="utf-8")
print("OK: expandtabs(4)")

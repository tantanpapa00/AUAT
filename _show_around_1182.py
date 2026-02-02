from pathlib import Path
p = Path(r"C:\autobot\app\main.py")
lines = p.read_text(encoding="utf-8", errors="replace").splitlines()
line_no = 1182
start = max(0, line_no-40-1)
end = min(len(lines), line_no+40)
for i in range(start, end):
    print(f"{i+1:04d}: {lines[i]}")

import re
from pathlib import Path

path = Path(r"C:\autobot\app\main.py")
src = path.read_text(encoding="utf-8", errors="replace")

# params = {...} 블록 직후에 setdefault 2줄을 주입
pat = r"(\n\s*params\s*=\s*\{[\s\S]*?\n\s*\}\s*\n)"
m = re.search(pat, src)
if not m:
    raise SystemExit("ERR: cannot find params = {...} block")

# 이미 들어갔으면 스킵
if "params.setdefault('dedup_key'" in src or 'params.setdefault("dedup_key"' in src:
    print("SKIP: setdefault already present")
    raise SystemExit(0)

inject = "\n        params.setdefault('dedup_key', idem_key)\n        params.setdefault('status', 'received')\n"
src2 = src[:m.end()] + inject + src[m.end():]

tmp = path.with_suffix(".py.tmp")
tmp.write_text(src2, encoding="utf-8")

if tmp.stat().st_size < 20000:
    raise SystemExit(f"ERR: patched file too small: {tmp.stat().st_size}")

tmp.replace(path)
print("OK: injected params.setdefault(dedup_key/status)")

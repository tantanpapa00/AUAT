import re
from pathlib import Path

path = Path(r"C:\autobot\app\main.py")
src = path.read_text(encoding="utf-8", errors="replace")

# def _mk_idem_key(...) 함수 블록 교체
pat = r"def _mk_idem_key\([^)]*\):\n(?:[ \t].*\n)+"
m = re.search(pat, src)
if not m:
    raise SystemExit("ERR: cannot find _mk_idem_key()")

new = """def _mk_idem_key(config_hash: str, alert_id: str, symbol: str, side: str, bucket: str) -> str:
    # NOTE: alert_id는 의도적으로 키에 포함하지 않는다(재전송/복붙/변경 가능)
    base = f"{config_hash}|{symbol}|{side}|{bucket}"
    return hashlib.sha256(base.encode("utf-8")).hexdigest()
"""

src2 = src[:m.start()] + new + src[m.end():]
tmp = path.with_suffix(".py.tmp")
tmp.write_text(src2, encoding="utf-8")

if tmp.stat().st_size < 20000:
    raise SystemExit(f"ERR: patched file too small: {tmp.stat().st_size}")

tmp.replace(path)
print("OK: patched _mk_idem_key (bucket-based, ignore alert_id)")

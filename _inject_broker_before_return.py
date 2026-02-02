import re
from pathlib import Path

p = Path(r"C:\autobot\app\main.py")
s = p.read_text(encoding="utf-8", errors="replace")

if "_maybe_send_to_broker(" not in s:
    raise SystemExit("ERR: helper _maybe_send_to_broker not found (v5 not applied?)")

# /tv 응답에서 accepted 리턴 블록을 찾고, 그 직전에 주입
# 패턴: return { "ok": True, "code": "accepted", ... }
pat = r"(\n\s*return\s*\{\s*\n(?:[ \t]*.*\n){1,40}?\s*['\"]code['\"]\s*:\s*['\"]accepted['\"].*\n(?:[ \t]*.*\n){1,60}?\s*\}\s*)"
m = re.search(pat, s)
if not m:
    raise SystemExit("ERR: cannot find accepted return block to inject before")

block = m.group(1)

inject = """
        # ✅ broker send (post-return-inject safe spot)
        if created and order_id is not None:
            _maybe_send_to_broker(
                db,
                order_id=int(order_id),
                symbol=str(symbol) if symbol is not None else "",
                side=str(side) if side is not None else "",
                qty=qty,
                order_type=payload.get("type") if isinstance(payload, dict) else None,
                payload=payload if isinstance(payload, dict) else None,
            )
"""

# accepted return 블록 맨 앞(리턴 직전)에 inject 삽입
block2 = inject + block
s2 = s[:m.start(1)] + block2 + s[m.end(1):]

p.write_text(s2, encoding="utf-8")
print("OK: injected safe broker-call before accepted return")

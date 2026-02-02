import re
from pathlib import Path

p = Path(r"C:\autobot\app\main.py")
s = p.read_text(encoding="utf-8", errors="replace")

# v6 주입 블록을 찾는다
pat = r"""
(?P<indent>^[ \t]*)#\s*✅\s*broker\s*send\s*\(v6:\s*right\s*after\s*create_order_if_new\)\s*\n
(?P=indent)if\s+created\s+and\s+order_id\s+is\s+not\s+None:\s*\n
(?P=indent)[ \t]+_maybe_send_to_broker\([\s\S]*?\n(?P=indent)[ \t]+\)\s*\n
"""
m = re.search(pat, s, flags=re.M|re.X)
if not m:
    raise SystemExit("ERR: cannot find v6 injected broker block")

indent = m.group("indent")

replacement = f"""{indent}# ✅ broker send (v7: guarded; never raise 500 from /tv)
{indent}if created and order_id is not None:
{indent}    try:
{indent}        _maybe_send_to_broker(
{indent}            db,
{indent}            order_id=int(order_id),
{indent}            symbol=str(symbol) if symbol is not None else "",
{indent}            side=str(side) if side is not None else "",
{indent}            qty=qty,
{indent}            order_type=payload.get("type") if isinstance(payload, dict) else None,
{indent}            payload=payload if isinstance(payload, dict) else None,
{indent}        )
{indent}    except Exception as e:
{indent}        # broker 실패는 주문 row에 기록만 하고, /tv 응답은 accepted 유지(재전송 폭탄 방지)
{indent}        try:
{indent}            _set_order_status(db, int(order_id), "failed", reason=str(e))
{indent}            db.commit()
{indent}        except Exception:
{indent}            try: db.rollback()
{indent}            except Exception: pass
"""

s2 = s[:m.start()] + replacement + s[m.end():]
p.write_text(s2, encoding="utf-8")
print("OK: v7 patched (guard broker call; never 500)")

import re
from pathlib import Path

p = Path(r"C:\autobot\app\main.py")
s = p.read_text(encoding="utf-8", errors="replace")

# /tv 라우트 찾기
m_tv = re.search(r"^\s*@app\.post\(\s*['\"]\/tv['\"]\s*\)", s, flags=re.M)
if not m_tv:
    raise SystemExit("ERR: cannot find @app.post('/tv')")

# tv 핸들러 def 시작
m_def = re.search(r"^\s*(async\s+def|def)\s+\w+\s*\(", s[m_tv.end():], flags=re.M)
if not m_def:
    raise SystemExit("ERR: cannot find handler def after @app.post('/tv')")

fn_start = m_tv.end() + m_def.start()

# 함수 끝(다음 @app. 또는 EOF)
m_next = re.search(r"^\s*@app\.\w+\(", s[fn_start:], flags=re.M)
fn_end = fn_start + (m_next.start() if m_next else len(s) - fn_start)

fn = s[fn_start:fn_end]

if "_maybe_send_to_broker(" in fn:
    print("SKIP: already injected inside /tv")
    raise SystemExit(0)

# _create_order_if_new 할당 찾기(블록 포함)
pat_call = r"(^[ \t]*created\s*,\s*order_id\s*,\s*idem_key\s*=\s*_create_order_if_new\([\s\S]*?\)\s*\n)"
m_call = re.search(pat_call, fn, flags=re.M)
if not m_call:
    raise SystemExit("ERR: cannot find create_order_if_new assignment inside /tv")

call_block = m_call.group(1)
# indent는 call_block 첫 줄에서 가져옴
indent = re.match(r"^([ \t]*)", call_block).group(1)

inject = f"""{indent}# ✅ broker send (v6: right after create_order_if_new)\n{indent}if created and order_id is not None:\n{indent}    _maybe_send_to_broker(\n{indent}        db,\n{indent}        order_id=int(order_id),\n{indent}        symbol=str(symbol) if symbol is not None else \"\",\n{indent}        side=str(side) if side is not None else \"\",\n{indent}        qty=qty,\n{indent}        order_type=payload.get(\"type\") if isinstance(payload, dict) else None,\n{indent}        payload=payload if isinstance(payload, dict) else None,\n{indent}    )\n"""

fn2 = fn[:m_call.end()] + inject + fn[m_call.end():]

s2 = s[:fn_start] + fn2 + s[fn_end:]
p.write_text(s2, encoding="utf-8")

print("OK: injected v6 inside /tv after _create_order_if_new (indent-safe)")

import re
from pathlib import Path

p = Path(r"C:\autobot\app\main.py")
s = p.read_text(encoding="utf-8", errors="replace")

# 후보: status update 함수들
cands = []
for name in ["_set_order_status", "set_order_status", "_update_order_status", "update_order_status"]:
    m = re.search(rf"^\s*def\s+{re.escape(name)}\b", s, flags=re.M)
    if m:
        cands.append((name, m.start()))
print("STATUS_FN_CANDIDATES:", cands)

# tv endpoint 위치
m_tv = re.search(r'^\s*@app\.post\("/tv"\)\s*$', s, flags=re.M)
print("TV_DECORATOR_AT:", m_tv.start() if m_tv else None)

# /tv handler def 위치(대개 tv_webhook)
m_tvdef = re.search(r'^\s*def\s+\w+\s*\(.*\)\s*:\s*$',
                    s[m_tv.start():] if m_tv else s, flags=re.M)
if m_tv and m_tvdef:
    print("TV_DEF_LINE_SNIP:", s[m_tv.start()+m_tvdef.start(): m_tv.start()+m_tvdef.start()+120].replace("\n","\\n"))

# create_order 호출 위치
m_co = re.search(r"_create_order_if_new\s*\(", s)
print("CREATE_ORDER_CALL_AT:", m_co.start() if m_co else None)

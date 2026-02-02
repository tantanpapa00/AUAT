import re
from pathlib import Path

path = Path(r"C:\autobot\app\main.py")
src = path.read_text(encoding="utf-8", errors="replace")

# 1) orders insert SQL에 dedup_key/status가 없으면 추가 (idem_key 주변에 삽입)
#    - column list: ... idem_key, ...
#    - values list: ... :idem_key, ...
sql_pat = r"(insert\s+into\s+orders\s*\(\s*[^)]*idem_key[^)]*\)\s*values\s*\(\s*[^)]*:idem_key[^)]*\))"
m = re.search(sql_pat, src, flags=re.I|re.S)
if not m:
    raise SystemExit("ERR: cannot find orders INSERT containing idem_key")

sql = m.group(1)

# column list 추출
col_list_pat = r"insert\s+into\s+orders\s*\(\s*([^)]*)\)\s*values\s*\(\s*([^)]*)\)"
mm = re.search(col_list_pat, sql, flags=re.I|re.S)
cols = mm.group(1)
vals = mm.group(2)

def has_token(s, tok):
    return re.search(rf"\b{re.escape(tok)}\b", s) is not None

new_cols = cols
new_vals = vals

# dedup_key 없으면 idem_key 다음에 넣기
if not has_token(cols, "dedup_key"):
    new_cols = re.sub(r"\bidem_key\b", "idem_key, dedup_key", new_cols, count=1)
    new_vals = re.sub(r":idem_key\b", ":idem_key, :dedup_key", new_vals, count=1)

# status 없으면 values/cols 끝쪽에 넣기 (혹시 default가 없을 수도 있어서)
if not has_token(cols, "status"):
    new_cols = new_cols.strip() + ", status"
    new_vals = new_vals.strip() + ", :status"

new_sql = re.sub(col_list_pat,
                 lambda _ : f"insert into orders ({new_cols}) values ({new_vals})",
                 sql, flags=re.I|re.S)

src2 = src[:m.start()] + new_sql + src[m.end():]

# 2) params dict에 dedup_key/status 주입 (idem_key 설정 근처에 넣기)
#    'idem_key': idem_key 가 있는 dict 블록을 찾아 dedup_key/status 추가
param_pat = r"(\{[^{}]*['\"]idem_key['\"]\s*:\s*idem_key[^{}]*\})"
pm = re.search(param_pat, src2, flags=re.S)
if not pm:
    raise SystemExit("ERR: cannot find params dict containing idem_key")

block = pm.group(1)
if "dedup_key" not in block:
    block = re.sub(r"(['\"]idem_key['\"]\s*:\s*idem_key\s*,?)",
                   r"\1\n            'dedup_key': idem_key,",
                   block, count=1)

if "status" not in block:
    # status는 received로 고정(Week3에서는 state machine 유지)
    block = block.rstrip("} \n\t") + ",\n            'status': 'received'\n        }"

src3 = src2[:pm.start()] + block + src2[pm.end():]

tmp = path.with_suffix(".py.tmp")
tmp.write_text(src3, encoding="utf-8")

if tmp.stat().st_size < 20000:
    raise SystemExit(f"ERR: patched file too small: {tmp.stat().st_size}")

tmp.replace(path)
print("OK: patched orders INSERT to include dedup_key/status")
print("SIZE:", path.stat().st_size)

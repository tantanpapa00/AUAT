import re
from datetime import datetime

MAIN = r"C:\autobot\app\main.py"

with open(MAIN, "r", encoding="utf-8") as f:
    src = f.read()

# 백업
ts = datetime.now().strftime("%Y%m%d_%H%M%S")
bak = MAIN + f".bak_fix_integrity_{ts}"
with open(bak, "w", encoding="utf-8") as f:
    f.write(src)
print("Backup:", bak)

# _create_order_if_new() 내부의 except IntegrityError 블록만 교체 (except Exception 전까지)
pat = re.compile(
    r"(?ms)"
    r"(def _create_order_if_new\([^\)]*\):.*?\n)"                 # func header ~ somewhere
    r"(?P<ind>^[ \t]*)except IntegrityError as ie:\n"             # except IntegrityError line (captures indent)
    r".*?(?=^(?P=ind)except Exception as e:)",                    # consume until next except Exception (same indent)
)

m = pat.search(src)
if not m:
    raise SystemExit("ERROR: cannot find 'except IntegrityError as ie:' block inside _create_order_if_new().")

ind = m.group("ind")

new_block = "\n".join([
    f"{ind}except IntegrityError as ie:",
    f"{ind}    db.rollback()",
    f"{ind}    # ✅ IntegrityError 원인 식별 (PostgreSQL: constraint_name / pgcode)",
    f"{ind}    orig = getattr(ie, 'orig', None)",
    f"{ind}    cname = None",
    f"{ind}    pgcode = None",
    f"{ind}    try:",
    f"{ind}        cname = getattr(getattr(orig, 'diag', None), 'constraint_name', None) or getattr(orig, 'constraint_name', None)",
    f"{ind}        pgcode = getattr(orig, 'pgcode', None) or getattr(orig, 'sqlstate', None)",
    f"{ind}    except Exception:",
    f"{ind}        pass",
    f"{ind}    msg = str(orig) if orig is not None else str(ie)",
    "",
    f"{ind}    # ✅ 'idem_key 유니크(ux_orders_idem_key)'만 duplicate로 인정",
    f"{ind}    is_dup = False",
    f"{ind}    if cname == 'ux_orders_idem_key':",
    f"{ind}        is_dup = True",
    f"{ind}    elif pgcode == '23505' and ('ux_orders_idem_key' in msg or 'idem_key' in msg):",
    f"{ind}        is_dup = True",
    "",
    f"{ind}    if is_dup:",
    f"{ind}        # 중복이면 정상적으로 duplicate 처리",
    f"{ind}        return False, None, idem_key",
    "",
    f"{ind}    # 그 외 IntegrityError는 숨기지 말고 그대로 노출",
    f"{ind}    raise HTTPException(status_code=400, detail=f\"orders_integrity_error[{{cname or pgcode}}]: {{msg}}\")",
    "",
])

dst = pat.sub(lambda mm: mm.group(1) + new_block + "\n", src, count=1)

with open(MAIN, "w", encoding="utf-8") as f:
    f.write(dst)

print("PATCH OK:", MAIN)

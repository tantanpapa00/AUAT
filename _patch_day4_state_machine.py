import re
from pathlib import Path

path = Path(r"C:\autobot\app\main.py")
src = path.read_text(encoding="utf-8", errors="replace")

if "import os" not in src:
    src = re.sub(r"(^import .*?$)", r"\1\nimport os", src, flags=re.M, count=1)

if "def _is_dry_run" not in src:
    inject = """
def _is_dry_run() -> bool:
    v = os.getenv("DRY_RUN", "1").strip().lower()
    return v in ("1","true","yes","y","on")
"""
    src = src.replace("def _mk_idem_key", inject + "\n\ndef _mk_idem_key", 1)

if "def _set_order_status" not in src:
    helper = """
def _set_order_status(db: Session, order_id: int, status: str, *, okx_order_id=None, okx_response=None, reason=None):
    params = {"id": int(order_id), "status": status}
    sql = "update orders set status=:status, updated_at=now()"
    if okx_order_id is not None:
        sql += ", okx_order_id=:okx_order_id"
        params["okx_order_id"] = okx_order_id
    if okx_response is not None:
        sql += ", okx_response=CAST(:okx_response as jsonb)"
        params["okx_response"] = json.dumps(okx_response, ensure_ascii=False)
    if reason is not None:
        sql += ", reason=:reason"
        params["reason"] = reason
    sql += " where id=:id"
    db.execute(text(sql), params)
"""
    src = src.replace("def _create_order_if_new", helper + "\n\ndef _create_order_if_new", 1)

hook_pat = r"(\n\s*# 5\) accepted[^\n]*\n)"
m = re.search(hook_pat, src)
if not m:
    raise SystemExit("ERR: cannot find '# 5) accepted' anchor")

hook = """
        # 4.5) (Day4) optional broker send
        if created and order_id is not None:
            if _is_dry_run():
                pass
            else:
                try:
                    _set_order_status(db, int(order_id), "sending")
                    okx_result = None
                    try:
                        okx_result = okx_place_order(
                            symbol=symbol,
                            side=side,
                            qty=qty,
                            order_type=payload.get("type") if isinstance(payload, dict) else "market",
                        )
                    except NameError:
                        okx_result = {"note": "okx_place_order not wired yet (Week4 Day1)"}

                    okx_order_id = None
                    if isinstance(okx_result, dict):
                        okx_order_id = okx_result.get("ordId") or okx_result.get("order_id") or okx_result.get("okx_order_id")

                    _set_order_status(db, int(order_id), "sent", okx_order_id=okx_order_id, okx_response=okx_result)
                    db.commit()
                except Exception as e:
                    db.rollback()
                    try:
                        _set_order_status(db, int(order_id), "failed", reason=str(e))
                        db.commit()
                    except Exception:
                        db.rollback()
"""
src2 = src[:m.start()] + hook + src[m.start():]
path.write_text(src2, encoding="utf-8")
print("OK: inserted Day4 broker send hook + helpers")

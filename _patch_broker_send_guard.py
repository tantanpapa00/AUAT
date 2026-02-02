import re
from pathlib import Path

path = Path(r"C:\autobot\app\main.py")
src = path.read_text(encoding="utf-8", errors="replace")

# 1) _set_order_status 다음(다음 def 직전)에 _maybe_send_to_broker 삽입
pat = r"(def _set_order_status\([^\n]*\):\n(?:[ \t].*\n)+)(\n\ndef _mk_idem_key)"
m = re.search(pat, src)
if not m:
    raise SystemExit("ERR: cannot locate _set_order_status block to inject helper")

helper = r"""
def _maybe_send_to_broker(db: Session, *, order_id: int, symbol: str, side: str, qty, order_type: str | None):
    # 중복 블록/재호출 방지: DB status가 received일 때만 1회 실행
    cur = db.execute(text("select status from orders where id=:id"), {"id": int(order_id)}).scalar()
    if cur and str(cur) != "received":
        return

    # dry-run이면 눈에 보이게 status만 바꿈
    if _is_dry_run():
        try:
            _set_order_status(db, int(order_id), "dry_run", reason="DRY_RUN=1")
            db.commit()
        except Exception:
            db.rollback()
        return

    try:
        _set_order_status(db, int(order_id), "sending")
        db.commit()

        okx_result = None
        try:
            okx_result = okx_place_order(
                symbol=symbol,
                side=side,
                qty=float(qty) if qty is not None else 0.0,
                order_type=order_type or "market",
            )
        except NameError:
            raise RuntimeError("okx_place_order not wired yet (Week4 Day1)")

        # ordId 추출(형태가 달라도 최대한 잡음)
        okx_order_id = None
        if isinstance(okx_result, dict):
            okx_order_id = okx_result.get("ordId") or okx_result.get("order_id")
            if not okx_order_id and isinstance(okx_result.get("data"), list) and okx_result["data"]:
                okx_order_id = okx_result["data"][0].get("ordId") or okx_result["data"][0].get("order_id")

        _set_order_status(db, int(order_id), "sent", okx_order_id=okx_order_id, okx_response=okx_result)
        db.commit()
    except Exception as e:
        try:
            db.rollback()
            _set_order_status(db, int(order_id), "failed", reason=str(e))
            db.commit()
        except Exception:
            db.rollback()
"""

src2 = src[:m.start(2)] + helper + src[m.start(2):]

# 2) tv_webhook에서 _create_order_if_new(...) 호출 직후에 _maybe_send_to_broker 호출 주입
#    (중복 블록이 나중에 있어도 status 가드로 1회만 실행됨)
pat2 = r"(created,\s*order_id,\s*idem_key\s*=\s*_create_order_if_new\([\s\S]*?\)\s*\n)"
m2 = re.search(pat2, src2)
if not m2:
    raise SystemExit("ERR: cannot locate _create_order_if_new(...) call to inject broker send")

inject = """
        if created and order_id is not None:
            _maybe_send_to_broker(
                db,
                order_id=int(order_id),
                symbol=str(symbol) if symbol is not None else "",
                side=str(side) if side is not None else "",
                qty=qty,
                order_type=payload.get("type") if isinstance(payload, dict) else None,
            )
"""
src3 = src2[:m2.end()] + inject + src2[m2.end():]

tmp = path.with_suffix(".py.tmp")
tmp.write_text(src3, encoding="utf-8")
if tmp.stat().st_size < 20000:
    raise SystemExit(f"ERR: patched file too small: {tmp.stat().st_size}")

tmp.replace(path)
print("OK: injected _maybe_send_to_broker + call after _create_order_if_new")
print("SIZE:", path.stat().st_size)

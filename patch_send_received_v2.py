import re
from pathlib import Path
from datetime import datetime

MAIN = Path(r"C:\autobot\app\main.py")
PATCH_TAG = "[SEND_RECEIVED_V2]"

# NOTE:
# - We use outer triple SINGLE quotes for the endpoint code so we can safely use """ inside SQL.
SEND_ENDPOINT = '''
# {PATCH_TAG}
# - Adds /api/diag/send-now : process orders with status=received and okx_order_id is null
# - Never raises 500; always returns JSON

@app.post("/api/diag/send-now")
def api_send_now(
    limit: int = Query(20, ge=1, le=200),
    db: Session = Depends(get_db),
):
    import time as _time

    t0 = _time.time()
    out_items = []
    scanned = 0

    # if okx_place_order doesn't exist, don't crash
    if "okx_place_order" not in globals():
        return {
            "ok": False,
            "count": 0,
            "items": [],
            "scanned": 0,
            "note": "send_impl_missing",
            "elapsed_ms": int((_time.time() - t0) * 1000),
        }

    try:
        rows = db.execute(text("""
            select id, asset_id, symbol, market, side, qty, order_type
              from orders
             where status = 'received'
               and okx_order_id is null
             order by id asc
             limit :lim
        """), {"lim": limit}).mappings().all()

        for r in rows:
            scanned += 1
            oid = int(r["id"])
            symbol = r["symbol"]
            side = r["side"]
            qty = float(r["qty"])
            order_type = (r.get("order_type") or "market")

            # mark sending (best effort)
            try:
                db.execute(text("""
                    update orders
                       set status='sending',
                           reason=null
                     where id=:id
                """), {"id": oid})
                db.commit()
            except Exception:
                db.rollback()

            try:
                okx_res = okx_place_order(
                    symbol=symbol,
                    side=side,
                    qty=qty,
                    order_type=order_type,
                    payload={"source": "api_send_now"},
                )

                # extract ordId
                ord_id = None
                if isinstance(okx_res, dict):
                    data = okx_res.get("data") or []
                    if isinstance(data, list) and len(data) > 0 and isinstance(data[0], dict):
                        ord_id = data[0].get("ordId")

                if not ord_id:
                    raise RuntimeError(f"okx_no_ordId: {okx_res}")

                db.execute(text("""
                    update orders
                       set status='sent',
                           okx_order_id=:ord,
                           okx_state='sent',
                           last_checked_at=now(),
                           reason=null
                     where id=:id
                """), {"id": oid, "ord": str(ord_id)})
                db.commit()

                out_items.append({"id": oid, "status": "sent", "okx_order_id": str(ord_id)})

            except Exception as e:
                db.rollback()
                msg = str(e)
                db.execute(text("""
                    update orders
                       set status='failed',
                           reason=:r,
                           last_checked_at=now()
                     where id=:id
                """), {"id": oid, "r": f"send_failed: {msg}"})
                db.commit()
                out_items.append({"id": oid, "status": "failed", "reason": f"send_failed: {msg}"})

        return {
            "ok": True,
            "count": len(out_items),
            "items": out_items,
            "scanned": scanned,
            "note": "send_checked",
            "elapsed_ms": int((_time.time() - t0) * 1000),
        }

    except Exception as e:
        db.rollback()
        return {
            "ok": False,
            "count": 0,
            "items": [],
            "scanned": scanned,
            "note": "send_exception",
            "error": str(e),
            "elapsed_ms": int((_time.time() - t0) * 1000),
        }
'''.lstrip("\n")

def main():
    src = MAIN.read_text(encoding="utf-8", errors="replace")

    if PATCH_TAG in src:
        print("[patch_send_received_v2] already patched")
        return 0

    block = "\n\n" + SEND_ENDPOINT.replace("{PATCH_TAG}", PATCH_TAG) + "\n"

    # Insert after api_poll_now if we can find it, otherwise append.
    m = re.search(r"\ndef\s+api_poll_now\s*\(", src)
    if m:
        rest = src[m.end():]
        nxt = re.search(r"\n@app\.", rest)
        ins_at = (m.end() + nxt.start()) if nxt else len(src)
    else:
        ins_at = len(src)

    out = src[:ins_at] + block + src[ins_at:]

    bak = MAIN.with_name(f"main.py.bak.{datetime.now().strftime('%Y%m%d_%H%M%S')}")
    bak.write_text(src, encoding="utf-8")
    MAIN.write_text(out, encoding="utf-8")

    print("[patch_send_received_v2] OK")
    print(f"[patch_send_received_v2] backup -> {bak}")
    print(f"[patch_send_received_v2] wrote  -> {MAIN}")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())

from __future__ import annotations
from pathlib import Path
from datetime import datetime
import re

TARGET = Path(r"C:\autobot\app\main.py")

def backup(p: Path) -> Path:
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    bak = p.with_name(p.name + f".bak_okxbroker_{ts}")
    bak.write_text(p.read_text(encoding="utf-8", errors="replace"), encoding="utf-8")
    return bak

def find_func_block_end(lines, start_idx):
    # start_idx: 0-based, line with "def ..."
    def_line = lines[start_idx]
    base_indent = len(def_line) - len(def_line.lstrip(" "))
    i = start_idx + 1
    while i < len(lines):
        ln = lines[i]
        # stop when we hit next top-level def with same/lower indent (and not blank/comment)
        if ln.strip() and not ln.lstrip().startswith("#"):
            indent = len(ln) - len(ln.lstrip(" "))
            if indent <= base_indent and ln.lstrip().startswith("def "):
                return i
        i += 1
    return len(lines)

def insert_after_mk_idem_key(src: str) -> str:
    if "def okx_place_order(" in src and "def _maybe_send_to_broker(" in src:
        return src  # already patched

    lines = src.splitlines()
    mk_idx = None
    for i, ln in enumerate(lines):
        if "def _mk_idem_key" in ln:
            mk_idx = i
            break
    if mk_idx is None:
        raise SystemExit("ERR: cannot find 'def _mk_idem_key' insertion point")

    end_idx = find_func_block_end(lines, mk_idx)

    broker_block = r'''
# -------------------------------------------------------------------
# OKX broker send (Spot) + order status transition
# - DRY_RUN=1: do nothing (keep status=received)
# - DRY_RUN=0: sending -> sent/failed
# - never raise 500 from /tv (caller must guard)
# -------------------------------------------------------------------

import base64
import hmac
import requests
from datetime import datetime as _dt

def _is_dry_run() -> bool:
    v = os.getenv("DRY_RUN", "1").strip().lower()
    return v not in ("0", "false", "no", "off")

def _okx_env():
    base = os.getenv("OKX_BASE_URL", "https://www.okx.com").rstrip("/")
    key = os.getenv("OKX_API_KEY", "").strip()
    sec = os.getenv("OKX_API_SECRET", "").strip()
    pas = os.getenv("OKX_API_PASSPHRASE", "").strip()
    sim = os.getenv("OKX_SIMULATED", "0").strip()
    to  = os.getenv("OKX_TIMEOUT", "10").strip()
    if not key or not sec or not pas:
        raise RuntimeError("missing OKX_API_KEY/OKX_API_SECRET/OKX_API_PASSPHRASE")
    return base, key, sec, pas, sim, float(to)

def _okx_ts() -> str:
    # 2020-12-08T09:08:57.715Z
    return _dt.utcnow().isoformat(timespec="milliseconds") + "Z"

def _okx_sign(secret: str, prehash: str) -> str:
    mac = hmac.new(secret.encode("utf-8"), prehash.encode("utf-8"), digestmod="sha256").digest()
    return base64.b64encode(mac).decode("utf-8")

def okx_place_order(*, symbol: str, side: str, qty: float, order_type: str = "market", payload: dict | None = None) -> dict:
    base, key, sec, pas, sim, timeout = _okx_env()

    path = "/api/v5/trade/order"
    url = base + path

    ord_type = (order_type or "market").lower()
    if ord_type not in ("market", "limit"):
        ord_type = "market"

    body = {
        "instId": symbol,
        "tdMode": "cash",
        "side": side,
        "ordType": ord_type,
    }

    # qty is treated as "base" amount (e.g. 0.0001 BTC)
    # OKX spot market BUY defaults sz=quote unless tgtCcy is specified.
    # We want base size for both buy/sell to match TradingView qty.
    body["sz"] = str(qty)
    if side.lower() == "buy" and ord_type == "market":
        body["tgtCcy"] = "base_ccy"

    if ord_type == "limit":
        px = None
        if isinstance(payload, dict):
            px = payload.get("price") or payload.get("px")
        if px is None:
            raise RuntimeError("limit order requires payload.price (or px)")
        body["px"] = str(px)

    body_json = json.dumps(body, separators=(",", ":"), ensure_ascii=False)

    ts = _okx_ts()
    prehash = f"{ts}POST{path}{body_json}"
    sign = _okx_sign(sec, prehash)

    headers = {
        "Content-Type": "application/json",
        "OK-ACCESS-KEY": key,
        "OK-ACCESS-SIGN": sign,
        "OK-ACCESS-TIMESTAMP": ts,
        "OK-ACCESS-PASSPHRASE": pas,
    }
    if sim == "1":
        headers["x-simulated-trading"] = "1"

    resp = requests.post(url, headers=headers, data=body_json.encode("utf-8"), timeout=timeout)
    text_body = resp.text
    if resp.status_code != 200:
        raise RuntimeError(f"okx_http_error status={resp.status_code} body={text_body}")

    data = resp.json()
    if str(data.get("code")) != "0":
        raise RuntimeError(f"okx_error code={data.get('code')} msg={data.get('msg')} data={data.get('data')}")

    return data

def _set_order_status(db: Session, order_id: int, status: str, *, okx_order_id=None, okx_response=None, reason=None):
    # okx_response stored as jsonb if available
    okx_resp_json = None
    if okx_response is not None:
        try:
            okx_resp_json = json.dumps(okx_response, ensure_ascii=False)
        except Exception:
            okx_resp_json = None

    db.execute(
        text(
            """
            update orders
               set status      = :status,
                   reason      = :reason,
                   okx_order_id = :okx_order_id,
                   okx_response = case
                                    when :okx_response is null then okx_response
                                    else (:okx_response)::jsonb
                                  end,
                   updated_at   = now()
             where id = :id
            """
        ),
        {
            "id": int(order_id),
            "status": status,
            "reason": reason,
            "okx_order_id": okx_order_id,
            "okx_response": okx_resp_json,
        },
    )

def _maybe_send_to_broker(
    db: Session,
    *,
    order_id: int,
    symbol: str,
    side: str,
    qty: float,
    order_type: str | None,
    payload: dict | None,
):
    if _is_dry_run():
        return {"note": "dry_run=1 (skip broker send)"}

    # status: sending
    try:
        _set_order_status(db, int(order_id), "sending")
        db.commit()
    except Exception:
        try:
            db.rollback()
        except Exception:
            pass

    try:
        okx_result = okx_place_order(
            symbol=symbol,
            side=side,
            qty=qty,
            order_type=order_type or "market",
            payload=payload if isinstance(payload, dict) else None,
        )
        okx_order_id = None
        try:
            okx_order_id = okx_result.get("data", [{}])[0].get("ordId")
        except Exception:
            okx_order_id = None

        _set_order_status(db, int(order_id), "sent", okx_order_id=okx_order_id, okx_response=okx_result)
        db.commit()
        return okx_result
    except Exception as e:
        try:
            _set_order_status(db, int(order_id), "failed", reason=str(e))
            db.commit()
        except Exception:
            try:
                db.rollback()
            except Exception:
                pass
        raise
'''.strip("\n")

    # insert broker_block after _mk_idem_key block end
    new_lines = lines[:end_idx] + ["", broker_block, ""] + lines[end_idx:]
    return "\n".join(new_lines) + "\n"

def patch_tv_call(src: str) -> str:
    if "def _maybe_send_to_broker(" not in src:
        raise SystemExit("ERR: broker helper not inserted")

    # Find the place after _create_order_if_new(...) call inside /tv handler
    # We inject:
    #   if created and order_id is not None:
    #       try: _maybe_send_to_broker(...)
    #       except Exception: pass
    marker = "created, order_id, idem_key = _create_order_if_new("
    idx = src.find(marker)
    if idx < 0:
        raise SystemExit("ERR: cannot find create_order_if_new call in /tv")

    # find end of that call (the closing parenthesis line) by scanning forward from idx
    before = src[:idx]
    after = src[idx:]
    lines = after.splitlines(True)

    call_end_pos = None
    depth = 0
    started = False
    pos = 0
    for ln in lines:
        pos += len(ln)
        if marker in ln:
            started = True
        if started:
            depth += ln.count("(")
            depth -= ln.count(")")
            if depth <= 0:
                call_end_pos = pos
                break
    if call_end_pos is None:
        raise SystemExit("ERR: cannot locate end of _create_order_if_new(...) call")

    after_call = after[call_end_pos:]

    # Determine indentation of the line that contains marker (should be inside try)
    # We'll use 12 spaces typical: try->4, call->8, inside args->? but our inject should align with call line indent.
    # We'll detect indent from the marker line in original src.
    m = re.search(r"(?m)^(?P<ind>\s*)created,\s*order_id,\s*idem_key\s*=\s*_create_order_if_new\(", src)
    if not m:
        raise SystemExit("ERR: cannot detect indentation for injection")
    ind = m.group("ind")  # e.g. 12 spaces
    inject = (
        f"{ind}# broker send (guarded: never break /tv)\n"
        f"{ind}if created and order_id is not None:\n"
        f"{ind}    try:\n"
        f"{ind}        _maybe_send_to_broker(\n"
        f"{ind}            db,\n"
        f"{ind}            order_id=int(order_id),\n"
        f"{ind}            symbol=str(symbol) if symbol is not None else \"\",\n"
        f"{ind}            side=str(side) if side is not None else \"\",\n"
        f"{ind}            qty=float(qty) if qty is not None else 0.0,\n"
        f"{ind}            order_type=payload.get(\"type\") if isinstance(payload, dict) else None,\n"
        f"{ind}            payload=payload if isinstance(payload, dict) else None,\n"
        f"{ind}        )\n"
        f"{ind}    except Exception:\n"
        f"{ind}        pass\n"
    )

    # inject right after the create_order_if_new call block
    new_src = before + after[:call_end_pos] + "\n" + inject + after_call
    return new_src

def main():
    if not TARGET.exists():
        raise SystemExit(f"ERR: not found: {TARGET}")

    bak = backup(TARGET)
    src = TARGET.read_text(encoding="utf-8", errors="replace")

    src2 = insert_after_mk_idem_key(src)
    src3 = patch_tv_call(src2)

    # normalize tabs (avoid indentation hell)
    src3 = src3.expandtabs(4)

    TARGET.write_text(src3, encoding="utf-8")
    print("OK: patched OKX broker send")
    print("BACKUP:", bak)

if __name__ == "__main__":
    main()

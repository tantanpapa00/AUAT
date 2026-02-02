# patch_okx_order_tracking_v1.py
# Usage (PowerShell):
#   cd C:\autobot
#   python .\patch_okx_order_tracking_v1.py
#
# What it does:
# - app\main.py: adds OKX order status tracking (polling) + DB cols + /api/diag/poll-now + home/orders fields
# - app\templates\index.html: dashboard shows last_order_status / filled_qty / okx_order_id
#
# Safety:
# - Creates timestamped .bak files next to originals before writing.
# - Fails fast if expected anchors are not found (to avoid corrupting your file).

from __future__ import annotations
import re
import sys
from pathlib import Path
from datetime import datetime

ROOT = Path.cwd()
MAIN = ROOT / "app" / "main.py"
HTML = ROOT / "app" / "templates" / "index.html"

def backup(path: Path) -> Path:
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    bak = path.with_suffix(path.suffix + f".bak.{ts}")
    bak.write_bytes(path.read_bytes())
    return bak

def die(msg: str) -> None:
    print(f"[patch] ERROR: {msg}", file=sys.stderr)
    sys.exit(1)

def replace_once(text: str, old: str, new: str, *, label: str) -> str:
    if old not in text:
        die(f"anchor not found for {label}")
    return text.replace(old, new, 1)

def main():
    if not MAIN.exists():
        die(f"not found: {MAIN}")
    if not HTML.exists():
        die(f"not found: {HTML}")

    main_txt = MAIN.read_text(encoding="utf-8-sig")
    html_txt = HTML.read_text(encoding="utf-8")

    # -------------------------------
    # 1) Replace OKX broker block
    # -------------------------------
    start_anchor = "# -------------------------------------------------------------------\n# OKX broker send"
    start = main_txt.find(start_anchor)
    if start < 0:
        die("OKX block start anchor not found")
    end_anchor = "def _create_order_if_new"
    end = main_txt.find(end_anchor, start)
    if end < 0:
        die("OKX block end anchor not found (def _create_order_if_new)")

    okx_block = OKX_BLOCK.rstrip() + "\n\n"
    main_txt = main_txt[:start] + okx_block + main_txt[end:]

    # -------------------------------
    # 2) orders table: add new cols for fresh install + migrate existing
    # -------------------------------
    main_txt = main_txt.replace(
        "                okx_order_id    text,\n                okx_response    jsonb,\n\n                payload         jsonb",
        "                okx_order_id    text,\n                okx_response    jsonb,\n                filled_qty      numeric,\n                avg_px          numeric,\n                okx_state       text,\n                last_checked_at timestamptz,\n                broker_raw      jsonb,\n\n                payload         jsonb",
    )

    needle = '        db.execute(text("alter table orders add column if not exists dedup_key text;"))'
    if needle not in main_txt:
        die("orders migrate anchor not found (dedup_key)")
    main_txt = main_txt.replace(
        needle,
        needle + "\n"
        '        db.execute(text("alter table orders add column if not exists filled_qty numeric;"))\n'
        '        db.execute(text("alter table orders add column if not exists avg_px numeric;"))\n'
        '        db.execute(text("alter table orders add column if not exists okx_state text;"))\n'
        '        db.execute(text("alter table orders add column if not exists last_checked_at timestamptz;"))\n'
        '        db.execute(text("alter table orders add column if not exists broker_raw jsonb;"))',
        1
    )

    needle2 = '        db.execute(text("create index if not exists ix_orders_alert_id on orders(alert_id);"))'
    if needle2 not in main_txt:
        die("orders index anchor not found (ix_orders_alert_id)")
    main_txt = main_txt.replace(
        needle2,
        needle2 + "\n"
        '        db.execute(text("create index if not exists ix_orders_okx_order_id on orders(okx_order_id);"))\n'
        '        db.execute(text("create index if not exists ix_orders_status on orders(status);"))\n'
        '        db.execute(text("create index if not exists ix_orders_last_checked_at on orders(last_checked_at);"))',
        1
    )

    # -------------------------------
    # 3) /api/home: select new cols + auto-migrate + add last_signal/last_order strings
    # -------------------------------
    main_txt = replace_once(
        main_txt,
        '@app.get("/api/home")\ndef api_home(db: Session = Depends(get_db)):\n',
        '@app.get("/api/home")\ndef api_home(db: Session = Depends(get_db)):\n'
        "    # dashboard columns might be missing on older DBs\n"
        "    try:\n"
        "        _ensure_orders_table(db)\n"
        "        _ensure_order_tracking_cols(db)\n"
        "        db.commit()\n"
        "    except Exception:\n"
        "        try:\n"
        "            db.rollback()\n"
        "        except Exception:\n"
        "            pass\n",
        label="/api/home signature"
    )

    main_txt = main_txt.replace(
        "          a.last_order_reason",
        "          a.last_order_reason,\n"
        "          a.last_order_id,\n"
        "          a.last_okx_order_id,\n"
        "          a.last_filled_qty,\n"
        "          a.last_order_avg_px,\n"
        "          a.last_checked_at",
        1
    )

    home_return_old = '        rows = db.execute(q).mappings().all()\n        return {"ok": True, "items": [dict(r) for r in rows]}\n'
    if home_return_old not in main_txt:
        die("home return anchor not found")
    main_txt = main_txt.replace(home_return_old, HOME_RETURN_NEW, 1)

    # -------------------------------
    # 4) /api/orders: include new cols
    # -------------------------------
    main_txt = main_txt.replace(
        "            idem_key, status, reason, okx_order_id",
        "            idem_key, status, reason, okx_order_id,\n"
        "            filled_qty, avg_px, okx_state, last_checked_at",
        1
    )

    # -------------------------------
    # 5) add /api/diag/poll-now endpoint (debug)
    # -------------------------------
    if '@app.post("/api/diag/poll-now")' not in main_txt:
        m = re.search(
            r'@app\.get\("/api/orders"\)\ndef api_list_orders[\s\S]+?return \{"ok": True, "count": len\(rows\), "items": \[dict\(r\) for r in rows\]\}\n',
            main_txt
        )
        if not m:
            die("cannot find api_list_orders block to insert diag endpoint")
        insert_pos = m.end()
        main_txt = main_txt[:insert_pos] + "\n\n" + DIAG_ENDPOINT + "\n" + main_txt[insert_pos:]

    # -------------------------------
    # 6) index.html: show last_order_status / filled_qty / okx_order_id
    # -------------------------------
    html_txt = html_txt.replace(
        "              <th>last_signal</th>\n              <th>last_order</th>",
        "              <th>last_signal</th>\n"
        "              <th>last_order_status</th>\n"
        "              <th>filled_qty</th>\n"
        "              <th>okx_order_id</th>\n"
        "              <th>last_order</th>",
        1
    )
    html_txt = html_txt.replace(
        '          <td class="mono">${escapeHtml(r.last_signal||"-")}</td>\n          <td class="mono">${escapeHtml(r.last_order||"-")}</td>',
        '          <td class="mono">${escapeHtml(r.last_signal||"-")}</td>\n'
        '          <td class="mono">${escapeHtml(r.last_order_status||"-")}</td>\n'
        '          <td class="mono">${escapeHtml(r.last_filled||"-")}</td>\n'
        '          <td class="mono">${escapeHtml(r.last_okx_order_id||"-")}</td>\n'
        '          <td class="mono">${escapeHtml(r.last_order||"-")}</td>',
        1
    )

    bak_main = backup(MAIN)
    bak_html = backup(HTML)

    MAIN.write_text(main_txt, encoding="utf-8")
    HTML.write_text(html_txt, encoding="utf-8")

    print("[patch] OK")
    print(f"[patch] main.py     -> {MAIN} (backup: {bak_main.name})")
    print(f"[patch] index.html  -> {HTML} (backup: {bak_html.name})")
    print("[patch] Next: restart uvicorn with ORDER_POLL_ENABLE=1")

OKX_BLOCK = r'''# -------------------------------------------------------------------
# OKX broker send (Spot) + Order status tracking
# - DRY_RUN=1: do nothing (keep status=received)
# - DRY_RUN=0: sending -> sent/failed
# - status polling: sent/partial -> filled/canceled (by OKX GET /trade/order)
# - never raise 500 from /tv (caller must guard)
# -------------------------------------------------------------------

import base64
import hmac
import requests
import threading
import time
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

def _okx_headers(ts: str, sign: str, *, key: str, pas: str, sim: str):
    headers = {
        "Content-Type": "application/json",
        "OK-ACCESS-KEY": key,
        "OK-ACCESS-SIGN": sign,
        "OK-ACCESS-TIMESTAMP": ts,
        "OK-ACCESS-PASSPHRASE": pas,
    }
    if sim == "1":
        headers["x-simulated-trading"] = "1"
    return headers

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

    headers = _okx_headers(ts, sign, key=key, pas=pas, sim=sim)

    resp = requests.post(url, headers=headers, data=body_json.encode("utf-8"), timeout=timeout)
    text_body = resp.text
    if resp.status_code != 200:
        raise RuntimeError(f"okx_http_error status={resp.status_code} body={text_body}")

    data = resp.json()
    if str(data.get("code")) != "0":
        raise RuntimeError(f"okx_error code={data.get('code')} msg={data.get('msg')} data={data.get('data')}")
    return data

def okx_get_order(*, symbol: str, okx_order_id: str) -> dict:
    """OKX 주문 상세 조회 (Spot): GET /api/v5/trade/order?instId=...&ordId=..."""
    base, key, sec, pas, sim, timeout = _okx_env()

    path = "/api/v5/trade/order"
    query = f"instId={symbol}&ordId={okx_order_id}"
    url = base + path + "?" + query

    ts = _okx_ts()
    prehash = f"{ts}GET{path}?{query}"
    sign = _okx_sign(sec, prehash)

    headers = _okx_headers(ts, sign, key=key, pas=pas, sim=sim)

    resp = requests.get(url, headers=headers, timeout=timeout)
    text_body = resp.text
    if resp.status_code != 200:
        raise RuntimeError(f"okx_http_error status={resp.status_code} body={text_body}")

    data = resp.json()
    if str(data.get("code")) != "0":
        raise RuntimeError(f"okx_error code={data.get('code')} msg={data.get('msg')} data={data.get('data')}")
    return data

def _to_float(x, default=0.0) -> float:
    try:
        if x is None or x == "":
            return float(default)
        return float(x)
    except Exception:
        return float(default)

def _map_okx_state_to_status(state: str | None, *, filled: float, total: float) -> str:
    s = (state or "").lower().strip()
    if s == "filled":
        return "filled"
    if s == "canceled":
        return "canceled"
    if s in ("partially_filled", "partially-filled"):
        return "partial"
    if s == "live":
        # live인데 accFillSz>0이면 partial
        if filled > 0 and (total <= 0 or filled < total):
            return "partial"
        return "sent"
    # fallback
    if filled > 0 and (total <= 0 or filled < total):
        return "partial"
    return "sent"

def _safe_json(x):
    if x is None:
        return None
    try:
        return json.dumps(x, ensure_ascii=False)
    except Exception:
        return None

def _ensure_order_tracking_cols(db: Session):
    """orders/asset에 '상태추적' 컬럼이 없으면 안전하게 추가."""
    # orders
    db.execute(text("alter table orders add column if not exists filled_qty numeric;"))
    db.execute(text("alter table orders add column if not exists avg_px numeric;"))
    db.execute(text("alter table orders add column if not exists okx_state text;"))
    db.execute(text("alter table orders add column if not exists last_checked_at timestamptz;"))
    db.execute(text("alter table orders add column if not exists broker_raw jsonb;"))
    db.execute(text("create index if not exists ix_orders_okx_order_id on orders(okx_order_id);"))
    db.execute(text("create index if not exists ix_orders_status on orders(status);"))
    db.execute(text("create index if not exists ix_orders_last_checked_at on orders(last_checked_at);"))

    # assets (dashboard fields)
    db.execute(text("alter table assets add column if not exists last_order_id bigint;"))
    db.execute(text("alter table assets add column if not exists last_okx_order_id text;"))
    db.execute(text("alter table assets add column if not exists last_filled_qty numeric;"))
    db.execute(text("alter table assets add column if not exists last_order_avg_px numeric;"))
    db.execute(text("alter table assets add column if not exists last_checked_at timestamptz;"))

def _set_order_status(
    db: Session,
    order_id: int,
    status: str,
    *,
    okx_order_id=None,
    okx_response=None,
    broker_raw=None,
    reason=None,
    filled_qty=None,
    avg_px=None,
    okx_state=None,
    last_checked_at=None,
):
    """orders 업데이트 + 전광판용 assets(last_*)를 같이 갱신."""
    _ensure_order_tracking_cols(db)

    db.execute(
        text(
            """
            update orders
               set status        = :status,
                   reason        = :reason,
                   okx_order_id   = :okx_order_id,
                   filled_qty    = coalesce(:filled_qty, filled_qty),
                   avg_px        = coalesce(:avg_px, avg_px),
                   okx_state     = coalesce(:okx_state, okx_state),
                   last_checked_at = coalesce(:last_checked_at, last_checked_at),
                   okx_response  = case
                                    when :okx_response is null then okx_response
                                    else (:okx_response)::jsonb
                                  end,
                   broker_raw    = case
                                    when :broker_raw is null then broker_raw
                                    else (:broker_raw)::jsonb
                                  end,
                   updated_at    = now()
             where id = :id
            """
        ),
        {
            "id": int(order_id),
            "status": status,
            "reason": reason,
            "okx_order_id": okx_order_id,
            "filled_qty": filled_qty,
            "avg_px": avg_px,
            "okx_state": okx_state,
            "last_checked_at": last_checked_at,
            "okx_response": _safe_json(okx_response),
            "broker_raw": _safe_json(broker_raw),
        },
    )

    # Dashboard update (best-effort)
    try:
        db.execute(text(
            """
            update assets
               set last_order_at     = now(),
                   last_order_status = :status,
                   last_order_reason = :reason,
                   last_order_id     = :oid,
                   last_okx_order_id = coalesce(:okx_order_id, last_okx_order_id),
                   last_filled_qty   = coalesce(:filled_qty, last_filled_qty),
                   last_order_avg_px = coalesce(:avg_px, last_order_avg_px),
                   last_checked_at   = coalesce(:last_checked_at, last_checked_at),
                   updated_at        = now()
             where id = (select asset_id from orders where id = :oid)
            """
        ), {
            "oid": int(order_id),
            "status": status,
            "reason": reason,
            "okx_order_id": okx_order_id,
            "filled_qty": filled_qty,
            "avg_px": avg_px,
            "last_checked_at": last_checked_at,
        })
    except Exception:
        pass

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
    except Exception as e:
        try:
            db.rollback()
        except Exception:
            pass
        # sending 상태 갱신 실패는 여기서 끝(그래도 /tv는 accepted 유지)
        try:
            _set_order_status(db, int(order_id), "failed", reason=f"status_update_failed: {e}")
            db.commit()
        except Exception:
            try:
                db.rollback()
            except Exception:
                pass
        return {"note": "status_update_failed"}

    # place order
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
        # raise: caller(/tv)에서 잡아먹고 accepted 유지
        raise

def _poll_one_order(db: Session, row: dict) -> dict:
    """단일 주문 상태 조회 + DB 반영 (best-effort)."""
    oid = int(row["id"])
    symbol = row.get("symbol") or ""
    okx_order_id = row.get("okx_order_id") or ""
    now_ts = _dt.utcnow().replace(tzinfo=timezone.utc)

    data = okx_get_order(symbol=symbol, okx_order_id=okx_order_id)
    od = None
    try:
        od = (data.get("data") or [None])[0] or None
    except Exception:
        od = None

    if not isinstance(od, dict):
        raise RuntimeError(f"okx_get_order_bad_shape: {data}")

    state = od.get("state")
    total = _to_float(od.get("sz"), 0.0)
    filled = _to_float(od.get("accFillSz") or od.get("fillSz"), 0.0)
    avg_px = _to_float(od.get("avgPx"), 0.0)

    new_status = _map_okx_state_to_status(state, filled=filled, total=total)

    _set_order_status(
        db,
        oid,
        new_status,
        okx_order_id=okx_order_id,
        broker_raw=data,
        filled_qty=filled,
        avg_px=avg_px,
        okx_state=str(state) if state is not None else None,
        last_checked_at=now_ts,
    )
    return {"id": oid, "status": new_status, "filled_qty": filled, "avg_px": avg_px, "okx_state": state}

def poll_orders_once(*, limit: int = 20) -> dict:
    """DB에서 추적 대상 주문(sent/partial)을 뽑아서 한번 갱신."""
    # get_db 의존성(제너레이터)을 워커에서도 재사용
    db = next(get_db())
    try:
        _ensure_orders_table(db)
        _ensure_order_tracking_cols(db)

        rows = db.execute(text("""
            select id, symbol, okx_order_id, status, last_checked_at
              from orders
             where okx_order_id is not null
               and okx_order_id <> ''
               and status in ('sent','partial','sending')
             order by coalesce(last_checked_at, created_at) asc
             limit :lim
        """), {"lim": int(limit)}).mappings().all()

        updated = []
        for r in rows:
            try:
                updated.append(_poll_one_order(db, dict(r)))
                db.commit()
            except Exception as e:
                # poll 실패는 status를 망가뜨리지 않고 reason/last_checked_at만 갱신
                try:
                    _set_order_status(
                        db,
                        int(r["id"]),
                        str(r.get("status") or "sent"),
                        reason=f"poll_failed: {e}",
                        last_checked_at=_dt.utcnow().replace(tzinfo=timezone.utc),
                    )
                    db.commit()
                except Exception:
                    try:
                        db.rollback()
                    except Exception:
                        pass

        return {"ok": True, "count": len(updated), "items": updated}
    finally:
        try:
            db.close()
        except Exception:
            pass

def _poller_loop():
    enable = os.getenv("ORDER_POLL_ENABLE", "0").strip().lower() in ("1","true","yes","on")
    if not enable:
        return
    interval = float(os.getenv("ORDER_POLL_INTERVAL", "5").strip() or "5")
    batch = int(os.getenv("ORDER_POLL_BATCH", "20").strip() or "20")
    while True:
        try:
            poll_orders_once(limit=batch)
        except Exception:
            pass
        time.sleep(max(1.0, interval))

@app.on_event("startup")
def _startup_order_poller():
    """ORDER_POLL_ENABLE=1 이면 OKX 주문 상태 폴링 워커를 시작합니다."""
    enable = os.getenv("ORDER_POLL_ENABLE", "0").strip().lower() in ("1","true","yes","on")
    if not enable:
        return
    t = threading.Thread(target=_poller_loop, name="okx-order-poller", daemon=True)
    t.start()
'''

HOME_RETURN_NEW = r'''        rows = db.execute(q).mappings().all()
        items = []
        for r in rows:
            d = dict(r)

            ls_at = d.get("last_signal_at")
            ls_id = d.get("last_signal_id")
            lo_at = d.get("last_order_at")
            lo_st = d.get("last_order_status")
            lo_fill = d.get("last_filled_qty")
            lo_okx = d.get("last_okx_order_id")
            lo_chk = d.get("last_checked_at")

            d["last_signal"] = (f"{ls_at.isoformat()} ({ls_id})" if ls_at and ls_id else (ls_at.isoformat() if ls_at else "-"))
            # last_order string: time + status + filled + okx_id
            lo_parts = []
            if lo_at:
                lo_parts.append(lo_at.isoformat())
            if lo_st:
                lo_parts.append(str(lo_st))
            if lo_fill is not None:
                lo_parts.append(f"filled={lo_fill}")
            if lo_okx:
                lo_parts.append(f"ordId={lo_okx}")
            if lo_chk:
                lo_parts.append(f"checked={lo_chk.isoformat()}")
            d["last_order"] = " | ".join(lo_parts) if lo_parts else "-"

            # convenience UI fields (strings)
            d["last_filled"] = (str(lo_fill) if lo_fill is not None else "-")

            items.append(d)

        return {"ok": True, "items": items}
'''

DIAG_ENDPOINT = r'''@app.post("/api/diag/poll-now")
def api_poll_now(limit: int = Query(20, ge=1, le=200)):
    """수동 폴링(디버깅용). ORDER_POLL_ENABLE과 무관하게 1회 실행합니다."""
    return poll_orders_once(limit=limit)
'''

if __name__ == "__main__":
    main()

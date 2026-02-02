# patch_fix_missing_poll_orders_once_v2.py
# - poll_orders_once()가 없는 상태에서 /api/diag/poll-now(changes)가 NameError 나는 문제를 "확실히" 해결
# - 1) poll_orders_once()를 api_poll_now 바로 위에 삽입(없을 때만)
# - 2) api_poll_now 내부에서 globals()로 함수 존재 확인 + 없으면 안전 응답(절대 NameError로 죽지 않게)
# - C:\autobot\app\main.py 직접 패치 + 백업 생성

from __future__ import annotations
import re
from pathlib import Path
from datetime import datetime

MAIN = Path(r"C:\autobot\app\main.py")

MARKER = "# [PATCH_FIX_MISSING_POLL_ORDERS_ONCE_V2]"

POLL_ORDERS_ONCE_BLOCK = r'''
# [PATCH_FIX_MISSING_POLL_ORDERS_ONCE_V2]
def poll_orders_once(*, limit: int = 20) -> dict:
    """
    DB에서 추적 대상 주문(sent/partial + okx_order_id not null)을 뽑아서
    OKX 주문 조회로 상태를 1회 갱신합니다.
    - diag/worker 전용 ( /tv 절대 영향 X )
    """
    import os, json, base64, hmac, hashlib
    from datetime import datetime, timezone

    def _utc_ts() -> str:
        return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")

    def _sign(secret: str, ts: str, method: str, path_qs: str, body: str) -> str:
        msg = f"{ts}{method}{path_qs}{body}".encode("utf-8")
        mac = hmac.new(secret.encode("utf-8"), msg, hashlib.sha256).digest()
        return base64.b64encode(mac).decode("utf-8")

    def _http_get(url: str, headers: dict, timeout: float) -> tuple[int, str]:
        try:
            import requests  # type: ignore
            r = requests.get(url, headers=headers, timeout=timeout)
            return r.status_code, r.text
        except Exception:
            import urllib.request
            req = urllib.request.Request(url, headers=headers, method="GET")
            try:
                with urllib.request.urlopen(req, timeout=timeout) as resp:
                    return int(resp.status), resp.read().decode("utf-8", errors="replace")
            except Exception as e:
                return 599, str(e)

    def okx_get_order(inst_id: str, ord_id: str) -> dict:
        base = os.getenv("OKX_BASE_URL", "https://www.okx.com").rstrip("/")
        key = os.getenv("OKX_API_KEY", "")
        sec = os.getenv("OKX_API_SECRET", "")
        pas = os.getenv("OKX_API_PASSPHRASE", "")
        sim = os.getenv("OKX_SIMULATED", "0")
        timeout = float(os.getenv("OKX_TIMEOUT", "10"))

        if not (key and sec and pas):
            raise RuntimeError("missing OKX_API_KEY/OKX_API_SECRET/OKX_API_PASSPHRASE")

        path_qs = f"/api/v5/trade/order?instId={inst_id}&ordId={ord_id}"
        ts = _utc_ts()
        sign = _sign(sec, ts, "GET", path_qs, "")

        headers = {
            "OK-ACCESS-KEY": key,
            "OK-ACCESS-SIGN": sign,
            "OK-ACCESS-TIMESTAMP": ts,
            "OK-ACCESS-PASSPHRASE": pas,
        }
        if str(sim).strip() == "1":
            headers["x-simulated-trading"] = "1"

        status, text = _http_get(base + path_qs, headers=headers, timeout=timeout)

        try:
            j = json.loads(text) if isinstance(text, str) else {}
        except Exception:
            j = {"raw": text}

        if status != 200:
            raise RuntimeError(f"okx_http_error status={status} body={text}")
        if str(j.get("code")) != "0":
            raise RuntimeError(f"okx_api_error code={j.get('code')} msg={j.get('msg')} raw={text}")

        data = (j.get("data") or [])
        if not data:
            raise RuntimeError(f"okx_empty_data raw={text}")
        return {"raw": j, "item": data[0]}

    # DB session (main.py에 있는 get_db/text를 사용)
    g = get_db()
    db = next(g)

    scanned = 0
    items = []

    try:
        q = text("""
            select id, asset_id, symbol, market, side, qty, order_type,
                   status, okx_order_id, okx_state, filled_qty, avg_px, last_checked_at
              from orders
             where okx_order_id is not null
               and status in ('sent','partial')
             order by last_checked_at asc nulls first, id asc
             limit :lim
        """)
        rows = db.execute(q, {"lim": int(limit)}).mappings().all()
        scanned = len(rows)

        for r in rows:
            oid = int(r["id"])
            inst = r["symbol"]
            ord_id = str(r["okx_order_id"])

            try:
                resp = okx_get_order(inst, ord_id)
                it = resp["item"]
                st = str(it.get("state") or "").lower()

                filled = it.get("accFillSz", None) or it.get("fillSz", None)
                avgpx = it.get("avgPx", None) or None

                new_status = r["status"]
                if st == "filled":
                    new_status = "filled"
                elif st in ("partially_filled", "partial_filled", "partially-filled", "partial-filled"):
                    new_status = "partial"
                elif st in ("canceled", "cancelled"):
                    new_status = "canceled"
                elif st in ("live", "new", "open"):
                    new_status = "sent"

                u = text("""
                    update orders
                       set status = :status,
                           okx_state = :okx_state,
                           filled_qty = coalesce(:filled_qty, filled_qty),
                           avg_px = coalesce(:avg_px, avg_px),
                           last_checked_at = now()
                     where id = :id
                """)
                db.execute(u, {
                    "id": oid,
                    "status": new_status,
                    "okx_state": st if st else None,
                    "filled_qty": filled,
                    "avg_px": avgpx,
                })
                db.commit()

                items.append({
                    "order_id": oid,
                    "asset_id": r["asset_id"],
                    "symbol": r["symbol"],
                    "market": r["market"],
                    "side": r["side"],
                    "qty": float(r["qty"]) if r["qty"] is not None else None,
                    "order_type": r["order_type"],
                    "status": new_status,
                    "okx_order_id": r["okx_order_id"],
                    "okx_state": st if st else None,
                    "filled_qty": float(filled) if filled not in (None, "") else None,
                    "avg_px": float(avgpx) if avgpx not in (None, "") else None,
                    "reason": None,
                })

            except Exception as e:
                msg = str(e)
                u = text("""
                    update orders
                       set last_checked_at = now(),
                           reason = :reason
                     where id = :id
                """)
                db.execute(u, {"id": oid, "reason": f"poll_failed: {msg}"})
                db.commit()

                items.append({
                    "order_id": oid,
                    "asset_id": r["asset_id"],
                    "symbol": r["symbol"],
                    "market": r["market"],
                    "side": r["side"],
                    "qty": float(r["qty"]) if r["qty"] is not None else None,
                    "order_type": r["order_type"],
                    "status": r["status"],
                    "okx_order_id": r["okx_order_id"],
                    "okx_state": r["okx_state"],
                    "filled_qty": r["filled_qty"],
                    "avg_px": r["avg_px"],
                    "reason": f"poll_failed: {msg}",
                })

        note = "changes_only | no_candidates" if scanned == 0 else None
        return {"ok": True, "count": len(items), "items": items, "scanned": scanned, "note": note}

    finally:
        try:
            next(g)
        except StopIteration:
            pass
'''

def backup(path: Path) -> Path:
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    bak = path.with_name(path.name + f".bak.{ts}")
    bak.write_text(path.read_text(encoding="utf-8"), encoding="utf-8")
    return bak

def main():
    if not MAIN.exists():
        raise SystemExit(f"main.py not found: {MAIN}")

    src = MAIN.read_text(encoding="utf-8", errors="replace")
    if MARKER in src:
        print("[patch-v2] marker already present (skip)")
        return

    # 1) poll_orders_once가 "진짜로" 존재하는지 체크 (주석/문자열 오탐 방지)
    has_def = re.search(r"(?m)^\s*def\s+poll_orders_once\s*\(", src) is not None

    # 2) api_poll_now 위치 찾기
    m = re.search(r'(?m)^\s*@app\.post\("/api/diag/poll-now"\)', src)
    if not m:
        raise SystemExit("api_poll_now decorator not found")

    # 3) 삽입/수정 준비
    out = src
    if not has_def:
        out = out[:m.start()] + "\n" + POLL_ORDERS_ONCE_BLOCK + "\n" + out[m.start():]

    # 4) api_poll_now 내부에 방어코드 삽입 (globals에 없으면 안전 응답)
    #    - "def api_poll_now" 바로 다음 줄에 삽입
    out = re.sub(
        r'(?m)^(\s*def\s+api_poll_now\s*\(.*\)\s*:\s*)$',
        r'\1\n'
        r'    # [PATCH_FIX_MISSING_POLL_ORDERS_ONCE_V2] safety: avoid NameError\n'
        r'    _fn = globals().get("poll_orders_once")\n'
        r'    if _fn is None:\n'
        r'        return {"ok": False, "count": 0, "items": [], "note": "poll_orders_once_missing"}\n',
        out,
        count=1
    )

    bak = backup(MAIN)
    MAIN.write_text(out, encoding="utf-8")
    print("[patch-fix-missing-poll-orders-once-v2] OK")
    print("[patch-fix-missing-poll-orders-once-v2] main.py ->", str(MAIN))
    print("[patch-fix-missing-poll-orders-once-v2] backup ->", str(bak))

if __name__ == "__main__":
    main()

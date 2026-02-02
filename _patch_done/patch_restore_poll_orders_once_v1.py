# patch_restore_poll_orders_once_v1.py
# 목적:
# - main.py 에 poll_orders_once() 가 없어서 /api/diag/poll-now(changes)가 죽는 문제 복구
# - poll_orders_once()를 "없으면" api_poll_now 바로 위에 삽입
# - 구현은: DB에서 (sent/partial & okx_order_id not null) 후보를 뽑아 OKX 주문조회로 status/filled/avg_px 갱신
#
# 실행:
#   python .\patch_restore_poll_orders_once_v1.py

from __future__ import annotations
import re
from pathlib import Path
from datetime import datetime

MAIN = Path(r"C:\autobot\app\main.py")

INSERT_BLOCK = r'''
# [PATCH_RESTORE_POLL_ORDERS_ONCE_V1]
def poll_orders_once(*, limit: int = 20) -> dict:
    """
    DB에서 추적 대상 주문(sent/partial + okx_order_id not null)을 뽑아서
    OKX 주문 조회로 상태를 1회 갱신합니다.
    - /tv는 절대 죽이지 않음(여기는 diag/worker만 사용)
    - 외부 DDL/ensure 호출 금지(완전 읽기/업데이트만)
    """
    import os, json, base64, hmac, hashlib, time
    from datetime import datetime, timezone

    # --- tiny helpers ---
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
            # fallback: urllib
            import urllib.request
            req = urllib.request.Request(url, headers=headers, method="GET")
            try:
                with urllib.request.urlopen(req, timeout=timeout) as resp:
                    return int(resp.status), resp.read().decode("utf-8", errors="replace")
            except Exception as e:
                return 599, str(e)

    def _okx_env():
        base = os.getenv("OKX_BASE_URL", "https://www.okx.com").rstrip("/")
        key = os.getenv("OKX_API_KEY", "")
        sec = os.getenv("OKX_API_SECRET", "")
        pas = os.getenv("OKX_API_PASSPHRASE", "")
        sim = os.getenv("OKX_SIMULATED", "0")
        timeout = float(os.getenv("OKX_TIMEOUT", "10"))
        return base, key, sec, pas, sim, timeout

    def okx_get_order(inst_id: str, ord_id: str) -> dict:
        base, key, sec, pas, sim, timeout = _okx_env()
        if not (key and sec and pas):
            raise RuntimeError("missing OKX_API_KEY/OKX_API_SECRET/OKX_API_PASSPHRASE")

        # OKX: GET /api/v5/trade/order?instId=...&ordId=...
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

        url = base + path_qs
        status, text = _http_get(url, headers=headers, timeout=timeout)
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

    # --- DB session (FastAPI dependency generator 재사용) ---
    # get_db / text / timezone now() 등은 main.py에 이미 있다고 가정
    g = get_db()
    db = next(g)

    scanned = 0
    items = []
    note = None

    try:
        # 후보: okx_order_id 있고 sent/partial
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

                # OKX 필드: avgPx, accFillSz 등 (없으면 fillSz)
                filled = it.get("accFillSz", None)
                if filled is None:
                    filled = it.get("fillSz", None)
                avgpx = it.get("avgPx", None)
                if avgpx in ("", None):
                    avgpx = None

                # 상태 매핑
                new_status = r["status"]
                if st == "filled":
                    new_status = "filled"
                elif st in ("partially_filled", "partial_filled", "partially-filled", "partial-filled"):
                    new_status = "partial"
                elif st in ("canceled", "cancelled"):
                    new_status = "canceled"
                elif st in ("live", "new", "open"):
                    new_status = "sent"
                else:
                    # 알 수 없는 상태는 okx_state만 갱신
                    new_status = r["status"]

                # 업데이트
                u = text("""
                    update orders
                       set status = :status,
                           okx_state = :okx_state,
                           filled_qty = coalesce(:filled_qty, filled_qty),
                           avg_px = coalesce(:avg_px, avg_px),
                           last_checked_at = now(),
                           reason = null
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
                })

            except Exception as e:
                # 조회 실패는 주문을 failed로 만들지 않고 reason만 남김(단, ordId가 있는데 조회 실패는 poll_failed)
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

        if scanned == 0:
            note = "changes_only | no_candidates"

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
    if re.search(r"def\s+poll_orders_once\s*\(", src):
        print("[patch-restore-poll-orders-once-v1] poll_orders_once already exists (skip)")
        return

    # api_poll_now 앞에 삽입
    m = re.search(r"\n@app\.post\(\"/api/diag/poll-now\"", src)
    if not m:
        raise SystemExit("api_poll_now decorator not found")

    bak = backup(MAIN)
    out = src[:m.start()] + "\n" + INSERT_BLOCK + "\n" + src[m.start():]
    MAIN.write_text(out, encoding="utf-8")

    print("[patch-restore-poll-orders-once-v1] OK")
    print("[patch-restore-poll-orders-once-v1] main.py ->", str(MAIN))
    print("[patch-restore-poll-orders-once-v1] backup ->", str(bak))

if __name__ == "__main__":
    main()

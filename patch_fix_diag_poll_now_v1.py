import re
from pathlib import Path
from datetime import datetime

MAIN = r"C:\autobot\app\main.py"

REPL = r'''@app.post("/api/diag/poll-now")
def api_poll_now(
    limit: int = Query(20, ge=1, le=200),
    mode: str = Query("changes", pattern=r"^(changes|recent|poll)$"),
    db: Session = Depends(get_db),
):
    """
    diag poll-now (stable)
    - recent : DB 최근 주문 조회(항상 즉시)
    - poll   : poll_orders_once* 1회 호출(없으면 poll_impl_missing)
    - changes: poll 1회 호출을 3초 타임박스로 감싸 hang/500 방지
    """
    import time as _time
    import threading as _threading
    import queue as _queue
    from sqlalchemy import text as _sql_text

    t0 = _time.time()
    stage = {"stage": "start", "ts": t0}

    def _elapsed_ms():
        return int((_time.time() - t0) * 1000)

    def _as_items(x):
        if isinstance(x, dict):
            items = x.get("items", [])
            if items is None:
                items = []
            cnt = x.get("count", len(items))
            return x, items, cnt
        if x is None:
            return {"ok": True}, [], 0
        if isinstance(x, list):
            return {"ok": True}, x, len(x)
        return {"ok": True, "raw": str(x)}, [], 0

    def _resolve_poll_fn():
        g = globals()
        # 1) 정확한 이름
        fn = g.get("poll_orders_once")
        if callable(fn):
            return fn
        # 2) 접두어로 찾기 (poll_orders_once_v1, poll_orders_once_impl 등)
        for k, v in g.items():
            if k.startswith("poll_orders_once") and callable(v):
                return v
        # 3) 기타 후보
        for k in ("_poll_orders_once", "poll_orders_once_raw", "poll_orders_once_impl"):
            v = g.get(k)
            if callable(v):
                return v
        return None

    def _recent():
        q = _sql_text("""
            select id, asset_id, symbol, market, side, qty, order_type,
                   status, okx_order_id, okx_state, filled_qty, avg_px, last_checked_at, reason
              from orders
             order by id desc
             limit :lim
        """)
        rows = db.execute(q, {"lim": int(limit)}).mappings().all()
        return [dict(r) for r in rows]

    # ---- recent ----
    if mode == "recent":
        try:
            items = _recent()
            return {"ok": True, "items": items, "count": len(items), "note": "recent_checked", "stage": stage, "elapsed_ms": _elapsed_ms()}
        except Exception as e:
            return {"ok": False, "items": [], "count": 0, "note": "recent_failed", "error": str(e), "stage": stage, "elapsed_ms": _elapsed_ms()}

    # ---- poll / changes 공통: poll fn 준비 ----
    fn = _resolve_poll_fn()
    if not callable(fn):
        # 500 금지: 구현이 없으면 명시적으로 알려주기
        return {"ok": True, "items": [], "count": 0, "note": "poll_impl_missing", "stage": stage, "elapsed_ms": _elapsed_ms()}

    def _call_poll():
        # stage 같은 키워드 절대 넘기지 않음
        return fn(limit=int(limit))

    # ---- poll ----
    if mode == "poll":
        try:
            res = _call_poll()
            base, items, cnt = _as_items(res)
            ok = bool(base.get("ok", True))
            note = "poll_checked" if ok else "poll_failed"
            out = {"ok": ok, "items": items, "count": cnt, "note": note, "stage": stage, "elapsed_ms": _elapsed_ms()}
            # poll_orders_once가 추가 필드를 주면 유지
            for k in ("scanned", "changed", "updated"):
                if isinstance(res, dict) and k in res:
                    out[k] = res[k]
            if isinstance(res, dict) and "error" in res:
                out["error"] = res["error"]
            return out
        except Exception as e:
            stage2 = {"stage": "poll_exception", "error": str(e)}
            return {"ok": False, "items": [], "count": 0, "note": "poll_failed", "error": str(e), "stage": stage2, "elapsed_ms": _elapsed_ms()}

    # ---- changes (3초 타임박스) ----
    # mode == "changes"
    q = _queue.Queue()

    def _worker():
        try:
            q.put(("ok", _call_poll()))
        except Exception as e:
            q.put(("err", str(e)))

    th = _threading.Thread(target=_worker, daemon=True)
    th.start()
    th.join(timeout=3.0)

    if th.is_alive():
        stage2 = {"stage": "changes_timeout"}
        return {"ok": False, "items": [], "count": 0, "note": "changes_timeout", "stage": stage2, "elapsed_ms": _elapsed_ms()}

    try:
        tag, payload = q.get_nowait()
    except Exception:
        tag, payload = ("err", "no_result")

    if tag != "ok":
        stage2 = {"stage": "changes_worker_exception", "error": str(payload)}
        return {"ok": False, "items": [], "count": 0, "note": "changes_checked", "error": str(payload), "stage": stage2, "elapsed_ms": _elapsed_ms()}

    base, items, cnt = _as_items(payload)
    ok = bool(base.get("ok", True))
    note = "changes_checked" if ok else "changes_failed"
    out = {"ok": ok, "items": items, "count": cnt, "note": note, "stage": stage, "elapsed_ms": _elapsed_ms()}
    for k in ("scanned", "changed", "updated"):
        if isinstance(payload, dict) and k in payload:
            out[k] = payload[k]
    if isinstance(payload, dict) and "error" in payload:
        out["error"] = payload["error"]
    return out
'''

def patch():
    p = Path(MAIN)
    src = p.read_text(encoding="utf-8", errors="replace")

    # decorator부터 다음 @app.* 전까지 통째로 교체
    pat = re.compile(r'(?ms)^@app\.post\("/api/diag/poll-now"\)\s*\n^def\s+api_poll_now\([\s\S]*?\n\):\n(?:^[ \t].*\n)*?(?=^@app\.|\Z)')
    m = pat.search(src)
    if not m:
        raise SystemExit("[patch_fix_diag_poll_now_v1] FAIL: target block not found: @app.post(\"/api/diag/poll-now\") + def api_poll_now")

    backup = p.with_name(f"main.py.bak.{datetime.now().strftime('%Y%m%d_%H%M%S')}")
    backup.write_text(src, encoding="utf-8")
    out = src[:m.start()] + REPL + "\n\n" + src[m.end():]
    p.write_text(out, encoding="utf-8")
    print(f"[patch_fix_diag_poll_now_v1] OK")
    print(f"[patch_fix_diag_poll_now_v1] backup -> {backup}")
    print(f"[patch_fix_diag_poll_now_v1] wrote  -> {p}")

if __name__ == "__main__":
    patch()

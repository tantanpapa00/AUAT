# patch_changes_stage_debug_v1.py
# Usage:
#   cd C:\autobot
#   python .\patch_changes_stage_debug_v1.py

from __future__ import annotations
import sys, re
from pathlib import Path
from datetime import datetime

MAIN = Path(r"C:\autobot\app\main.py")

def die(msg: str) -> None:
    print(f"[patch-stage-debug-v1] ERROR: {msg}", file=sys.stderr)
    sys.exit(1)

def backup(path: Path) -> Path:
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    bak = path.with_suffix(path.suffix + f".bak.{ts}")
    bak.write_bytes(path.read_bytes())
    return bak

def main():
    if not MAIN.exists():
        die(f"not found: {MAIN}")

    txt = MAIN.read_text(encoding="utf-8-sig")
    before = txt

    # --- A) poll_orders_once wrapper 교체 (stage + timing + statement_timeout)
    start = txt.find("# [POLL_CHANGES_WRAPPER_V1]")
    if start < 0:
        die("marker not found: # [POLL_CHANGES_WRAPPER_V1]")

    end = txt.find("# [ORDER_POLL_WORKER_V1]", start)
    if end < 0:
        end2 = txt.find("\n@app.", start)
        end = end2 if end2 >= 0 else len(txt)

    head = txt[:start]
    tail = txt[end:]  # includes marker line

    new_wrapper = '''
# [POLL_CHANGES_WRAPPER_V1]
def poll_orders_once(*, limit: int = 20, stage: dict | None = None) -> dict:
    """
    poll_orders_once (stage-debug v1)
    - okx_order_id 있는 'sent/partial'만 대상
    - 후보 0건이면 즉시 반환 (OKX 호출 없음)
    - stage dict에 진행상태 기록 (changes_timeout 원인 추적용)
    """
    import time as _time

    def _set(stage_name: str, **kw):
        if stage is None:
            return
        stage["stage"] = stage_name
        stage["ts"] = _time.time()
        for k, v in kw.items():
            stage[k] = v

    t0 = _time.perf_counter()
    _set("enter")

    candidate_ids: list[int] = []
    before: dict[int, dict] = {}

    # 1) BEFORE snapshot
    try:
        _set("get_db_before")
        db_gen = get_db()
        db = next(db_gen)
        _set("get_db_before_ok", ms=int((_time.perf_counter() - t0) * 1000))

        try:
            # 쿼리/세션이 비정상적으로 늘어지는 경우를 막기 위해 statement_timeout을 걸어둠
            # (session 단위. 실패해도 무시)
            try:
                db.execute(text("SET statement_timeout = 2500"))
            except Exception:
                pass

            _set("sql_before_start")
            rows = db.execute(text("""
                select id, asset_id, symbol, market, side, qty, order_type,
                       status, okx_order_id, okx_state, filled_qty, avg_px, last_checked_at
                  from orders
                 where okx_order_id is not null
                   and status in ('sent','partial')
                 order by coalesce(last_checked_at, to_timestamp(0)) asc, id asc
                 limit :lim
            """), {"lim": limit}).mappings().all()
            _set("sql_before_done", ms=int((_time.perf_counter() - t0) * 1000), rows=len(rows))

            for r in rows:
                oid = int(r["id"])
                candidate_ids.append(oid)
                before[oid] = {
                    "status": r.get("status"),
                    "okx_state": r.get("okx_state"),
                    "filled_qty": r.get("filled_qty"),
                    "avg_px": r.get("avg_px"),
                    "last_checked_at": r.get("last_checked_at"),
                }

        finally:
            try:
                db_gen.close()
            except Exception:
                pass

    except Exception as e:
        _set("before_failed", err=str(e), ms=int((_time.perf_counter() - t0) * 1000))
        return {"ok": True, "count": 0, "items": [], "scanned": 0, "note": "changes_only | snapshot_failed", "stage": stage}

    # ✅ 후보 0이면 즉시 반환
    if not candidate_ids:
        _set("no_candidates", ms=int((_time.perf_counter() - t0) * 1000))
        return {"ok": True, "count": 0, "items": [], "scanned": 0, "note": "changes_only | no_candidates", "stage": stage}

    # 2) Run impl (OKX call)
    try:
        _set("impl_start", n=len(candidate_ids))
        _poll_orders_once_impl(limit=limit)
        _set("impl_done", ms=int((_time.perf_counter() - t0) * 1000))
    except Exception as e:
        _set("impl_failed", err=str(e), ms=int((_time.perf_counter() - t0) * 1000))
        return {"ok": False, "count": 0, "items": [], "scanned": len(candidate_ids), "note": f"impl_failed: {e}", "stage": stage}

    # 3) AFTER snapshot + diff
    changes: list[dict] = []
    try:
        _set("get_db_after")
        db_gen2 = get_db()
        db2 = next(db_gen2)
        _set("get_db_after_ok", ms=int((_time.perf_counter() - t0) * 1000))

        try:
            try:
                db2.execute(text("SET statement_timeout = 2500"))
            except Exception:
                pass

            params = {}
            ph = []
            for i, oid in enumerate(candidate_ids):
                k = f"id{i}"
                params[k] = int(oid)
                ph.append(f":{k}")

            _set("sql_after_start")
            sql = f"""
                select id, asset_id, symbol, market, side, qty, order_type,
                       status, okx_order_id, okx_state, filled_qty, avg_px, last_checked_at, reason
                  from orders
                 where id in ({", ".join(ph)})
                 order by id asc
            """
            after_rows = db2.execute(text(sql), params).mappings().all()
            _set("sql_after_done", ms=int((_time.perf_counter() - t0) * 1000), rows=len(after_rows))

            for r in after_rows:
                oid = int(r["id"])
                b = before.get(oid, {})
                a_status = r.get("status")
                a_state  = r.get("okx_state")
                a_fq     = r.get("filled_qty")
                a_apx    = r.get("avg_px")

                changed = (
                    a_status != b.get("status")
                    or (a_state or None) != (b.get("okx_state") or None)
                    or (a_fq or None) != (b.get("filled_qty") or None)
                    or (a_apx or None) != (b.get("avg_px") or None)
                )

                if changed:
                    changes.append({
                        "order_id": oid,
                        "asset_id": r.get("asset_id"),
                        "symbol": r.get("symbol"),
                        "market": r.get("market"),
                        "side": r.get("side"),
                        "qty": r.get("qty"),
                        "order_type": r.get("order_type"),
                        "from_status": b.get("status"),
                        "to_status": a_status,
                        "from_okx_state": b.get("okx_state"),
                        "to_okx_state": a_state,
                        "filled_qty": a_fq,
                        "avg_px": a_apx,
                        "okx_order_id": r.get("okx_order_id"),
                        "last_checked_at": r.get("last_checked_at"),
                        "reason": r.get("reason"),
                    })

        finally:
            try:
                db_gen2.close()
            except Exception:
                pass

    except Exception as e:
        _set("after_failed", err=str(e), ms=int((_time.perf_counter() - t0) * 1000))
        return {"ok": True, "count": 0, "items": [], "scanned": len(candidate_ids), "note": "changes_only | diff_failed", "stage": stage}

    _set("done", ms=int((_time.perf_counter() - t0) * 1000), changed=len(changes))
    return {"ok": True, "count": len(changes), "items": changes, "scanned": len(candidate_ids), "note": "changes_only", "stage": stage}
'''.lstrip("\n")

    txt = head + new_wrapper + "\n# [ORDER_POLL_WORKER_V1]\n" + tail.split("# [ORDER_POLL_WORKER_V1]", 1)[1]

    # --- B) /api/diag/poll-now의 changes 경로를 stage 포함 버전으로 교체
    # 기존 "changes-only wrapper (thread timeout guard)" 블록을 찾아 통째로 교체
    pat = r"(# changes-only wrapper \(thread timeout guard\)[\s\S]*?res\s*=\s*_qq\.get\(\)[\s\S]*?else[\s\S]*?\})"
    if not re.search(pat, txt):
        # 버전에 따라 패턴이 다를 수 있으니, 최소한 changes_timeout 반환 라인을 기준으로 교체
        if "changes_timeout" not in txt:
            die("cannot find poll-now changes wrapper block (no changes_timeout found)")
        # changes_timeout 구간을 좀 더 넓게 잡아서 교체 시도
        pat2 = r"(import threading as _th[\s\S]{0,800}?return \{\"ok\": False,[\s\S]{0,300}?\"changes_timeout\"[\s\S]{0,200}?\})"
        if not re.search(pat2, txt):
            die("cannot locate changes timeout wrapper region")
        # pat2 영역을 아래 block으로 교체
        repl_block = r'''# changes-only wrapper (thread timeout guard + stage)
        import threading as _th
        import queue as _q
        import time as _time

        _qq = _q.Queue()
        _stage = {"stage": "init", "ts": _time.time()}

        def _run_changes():
            try:
                _stage["stage"] = "call_poll_orders_once"
                _stage["ts"] = _time.time()
                _qq.put(poll_orders_once(limit=limit, stage=_stage))
            except Exception as _e:
                _qq.put({"ok": False, "count": 0, "items": [], "note": f"changes_exception: {_e}", "stage": _stage})

        _t = _th.Thread(target=_run_changes, daemon=True)
        _t.start()
        _t.join(3.0)

        if _t.is_alive():
            age_ms = int((_time.time() - _stage.get("ts", _time.time())) * 1000)
            return {"ok": False, "count": 0, "items": [], "note": "changes_timeout", "stage": _stage, "age_ms": age_ms}

        res = _qq.get() if not _qq.empty() else {"ok": True, "count": 0, "items": [], "note": "changes_empty", "stage": _stage}'''
        txt = re.sub(pat2, repl_block, txt, count=1)
    else:
        repl_block = r'''# changes-only wrapper (thread timeout guard + stage)
        import threading as _th
        import queue as _q
        import time as _time

        _qq = _q.Queue()
        _stage = {"stage": "init", "ts": _time.time()}

        def _run_changes():
            try:
                _stage["stage"] = "call_poll_orders_once"
                _stage["ts"] = _time.time()
                _qq.put(poll_orders_once(limit=limit, stage=_stage))
            except Exception as _e:
                _qq.put({"ok": False, "count": 0, "items": [], "note": f"changes_exception: {_e}", "stage": _stage})

        _t = _th.Thread(target=_run_changes, daemon=True)
        _t.start()
        _t.join(3.0)

        if _t.is_alive():
            age_ms = int((_time.time() - _stage.get("ts", _time.time())) * 1000)
            return {"ok": False, "count": 0, "items": [], "note": "changes_timeout", "stage": _stage, "age_ms": age_ms}

        res = _qq.get() if not _qq.empty() else {"ok": True, "count": 0, "items": [], "note": "changes_empty", "stage": _stage}'''
        txt = re.sub(pat, repl_block, txt, count=1)

    if txt == before:
        print("[patch-stage-debug-v1] OK (no changes needed)")
        return

    bak = backup(MAIN)
    MAIN.write_text(txt, encoding="utf-8")
    print("[patch-stage-debug-v1] OK")
    print(f"[patch-stage-debug-v1] main.py -> {MAIN} (backup: {bak.name})")

if __name__ == "__main__":
    main()

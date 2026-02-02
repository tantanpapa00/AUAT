# -*- coding: utf-8 -*-
"""
patch_fix_poll_impl_missing_v1.py

목표:
- app\main.py에 poll_orders_once가 없으면, app\main.py.bak.* 중 가장 최근 것에서 poll_orders_once 블록을 복원
- /api/diag/poll-now 의 api_poll_now를 안정 버전으로 교체:
  - mode=recent : 최근 주문 조회(빠르게)
  - mode=poll   : poll_orders_once 실행(500 금지, JSON 반환)
  - mode=changes: poll_orders_once를 3초 타임아웃 래퍼로 실행(행 걸려도 JSON 반환)
"""

from __future__ import annotations
import os, re, sys, glob
from pathlib import Path
from datetime import datetime

MAIN = Path(r"C:\autobot\app\main.py")
APP_DIR = MAIN.parent

def read_text(p: Path) -> str:
    return p.read_text(encoding="utf-8", errors="replace")

def write_text(p: Path, s: str):
    p.write_text(s, encoding="utf-8", newline="\n")

def backup_file(path: Path) -> Path:
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    bk = path.with_name(path.name + f".bak.{ts}")
    bk.write_bytes(path.read_bytes())
    return bk

def find_poll_orders_once_block(src: str) -> str | None:
    # top-level def poll_orders_once(...) 블록 추출
    m = re.search(r"(?m)^def\s+poll_orders_once\s*\(.*?\)\s*:\s*\n", src)
    if not m:
        return None
    start = m.start()
    rest = src[m.end():]
    # 다음 top-level def 또는 decorator(@app...) 직전까지
    m2 = re.search(r"(?m)^(def\s+\w+\s*\(|@app\.)", rest)
    end = (m.end() + (m2.start() if m2 else len(rest)))
    block = src[start:end].rstrip() + "\n\n"
    return block

def ensure_poll_orders_once(main_src: str) -> str:
    if re.search(r"(?m)^def\s+poll_orders_once\s*\(", main_src):
        return main_src

    # 백업에서 복원
    backups = sorted(APP_DIR.glob("main.py.bak.*"), key=lambda p: p.stat().st_mtime, reverse=True)
    chosen = None
    block = None
    for bk in backups:
        s = read_text(bk)
        b = find_poll_orders_once_block(s)
        if b:
            chosen = bk
            block = b
            break

    if not block:
        raise RuntimeError("poll_orders_once block not found in current main.py and no backup contains it.")

    # /api/diag/poll-now 데코레이터 앞에 삽입(가장 안전)
    ins = re.search(r'(?m)^@app\.post\(\s*["\']/api/diag/poll-now["\']\s*\)', main_src)
    if ins:
        i = ins.start()
        main_src = main_src[:i] + block + main_src[i:]
    else:
        # 못 찾으면 파일 맨 끝에 추가
        main_src = main_src.rstrip() + "\n\n" + block

    print(f"[patch] restored poll_orders_once from backup: {chosen}")
    return main_src

def replace_api_poll_now(main_src: str) -> str:
    # @app.post("/api/diag/poll-now") ~ def api_poll_now(...) 블록 전체 교체
    pat = re.compile(
        r'(?ms)^@app\.post\(\s*["\']/api/diag/poll-now["\']\s*\)\s*\n'
        r'^def\s+api_poll_now\s*\(.*?\)\s*:\s*\n'
        r'(?:^[^\n]*\n)*?'
        r'(?=^@app\.|^def\s|\Z)'
    )

    m = pat.search(main_src)
    if not m:
        # decorator는 있는데 패턴이 안 맞는 경우를 대비해 느슨하게 탐색
        anchor = re.search(r'(?m)^@app\.post\(\s*["\']/api/diag/poll-now["\']\s*\)\s*$', main_src)
        if not anchor:
            raise RuntimeError('"/api/diag/poll-now" endpoint not found')
        # anchor부터 다음 decorator/def까지 잘라내기
        start = anchor.start()
        rest = main_src[anchor.end():]
        nxt = re.search(r"(?m)^(?:@app\.|def\s)", rest)
        end = anchor.end() + (nxt.start() if nxt else len(rest))
        m = type("M", (), {"start": lambda: start, "end": lambda: end})()

    new_block = r'''@app.post("/api/diag/poll-now")
def api_poll_now(
    limit: int = Query(20, ge=1, le=200),
    mode: str = Query("changes", pattern=r"^(changes|recent|poll)$"),
):
    """
    mode=recent : 최근 주문 N개 즉시 반환(디버그)
    mode=poll   : poll_orders_once 1회 실행(OKX 조회)
    mode=changes: poll_orders_once를 3초 타임아웃 래퍼로 실행(행 걸려도 200 JSON)
    """
    import time
    import threading
    import queue

    stage = {"stage": "start", "ts": time.time()}
    t0 = time.time()

    # ---- helper: get db session from generator ----
    def _with_db(fn):
        db_gen = get_db()
        db = next(db_gen)
        try:
            return fn(db)
        finally:
            try:
                db.close()
            except Exception:
                pass
            try:
                next(db_gen)
            except StopIteration:
                pass
            except Exception:
                pass

    # ---- mode: recent ----
    if mode == "recent":
        def _q(db):
            q = text("""
                select id, asset_id, symbol, market, side, qty, order_type,
                       status, okx_order_id, okx_state, filled_qty, avg_px, last_checked_at, reason
                  from orders
                 order by id desc
                 limit :lim
            """)
            rows = db.execute(q, {"lim": int(limit)}).mappings().all()
            return {"ok": True, "items": [dict(r) for r in rows], "count": len(rows),
                    "note": "recent_checked", "stage": stage, "elapsed_ms": int((time.time()-t0)*1000)}
        try:
            return _with_db(_q)
        except Exception as e:
            return {"ok": False, "items": [], "count": 0, "note": "recent_failed", "error": str(e),
                    "stage": {"stage": "recent_exception", "error": str(e)}, "elapsed_ms": int((time.time()-t0)*1000)}

    # ---- poll implementation must exist ----
    poll_fn = globals().get("poll_orders_once")
    if not callable(poll_fn):
        return {"ok": False, "items": [], "count": 0, "note": "poll_impl_missing",
                "stage": {"stage": "poll_impl_missing"}, "elapsed_ms": int((time.time()-t0)*1000)}

    # ---- mode: poll (direct) ----
    if mode == "poll":
        try:
            res = poll_fn(limit=int(limit))
            if not isinstance(res, dict):
                res = {"ok": True, "items": [], "count": 0, "note": "poll_ran_non_dict"}
            res.setdefault("stage", stage)
            res.setdefault("elapsed_ms", int((time.time()-t0)*1000))
            return res
        except Exception as e:
            return {"ok": False, "items": [], "count": 0, "note": "poll_failed", "error": str(e),
                    "stage": {"stage": "poll_exception", "error": str(e)}, "elapsed_ms": int((time.time()-t0)*1000)}

    # ---- mode: changes (timeout wrapper) ----
    # 3초 안에 끝나면 결과, 아니면 timeout JSON
    qout: "queue.Queue[dict]" = queue.Queue()

    def _run():
        try:
            r = poll_fn(limit=int(limit))
            if not isinstance(r, dict):
                r = {"ok": True, "items": [], "count": 0, "note": "changes_ran_non_dict"}
            qout.put(r)
        except Exception as e:
            qout.put({"ok": False, "items": [], "count": 0, "note": "changes_failed", "error": str(e),
                      "stage": {"stage": "changes_worker_exception", "error": str(e)}})

    th = threading.Thread(target=_run, daemon=True)
    th.start()
    th.join(timeout=3.0)

    if th.is_alive():
        return {"ok": False, "items": [], "count": 0, "note": "changes_timeout",
                "stage": {"stage": "changes_timeout"}, "elapsed_ms": int((time.time()-t0)*1000)}

    try:
        r = qout.get_nowait()
    except Exception:
        r = {"ok": False, "items": [], "count": 0, "note": "changes_no_result",
             "stage": {"stage": "changes_no_result"}}

    r.setdefault("stage", stage)
    r.setdefault("elapsed_ms", int((time.time()-t0)*1000))
    return r
'''
    start = m.start()
    end = m.end()
    return main_src[:start] + new_block + main_src[end:]

def main():
    if not MAIN.exists():
        print("[patch] FAIL: main.py not found:", MAIN)
        return 2

    src = read_text(MAIN)
    src2 = ensure_poll_orders_once(src)
    src3 = replace_api_poll_now(src2)

    bk = backup_file(MAIN)
    write_text(MAIN, src3)

    print("[patch] backup ->", bk)
    print("[patch] wrote  ->", MAIN)
    return 0

if __name__ == "__main__":
    raise SystemExit(main())

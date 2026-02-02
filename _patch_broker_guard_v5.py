import re
from pathlib import Path

path = Path(r"C:\autobot\app\main.py")
src = path.read_text(encoding="utf-8", errors="replace")

if "_maybe_send_to_broker(" in src:
    print("SKIP: already patched (_maybe_send_to_broker exists)")
    raise SystemExit(0)

# --- helper 삽입 위치: def _create_order_if_new 바로 위 (없으면 _mk_idem_key 위) ---
m_ins = re.search(r"^\s*def\s+_create_order_if_new\b", src, flags=re.M)
if not m_ins:
    m_ins = re.search(r"^\s*def\s+_mk_idem_key\b", src, flags=re.M)
if not m_ins:
    raise SystemExit("ERR: cannot find insertion point (no _create_order_if_new / _mk_idem_key)")

insert_at = m_ins.start()

helper = """
def _maybe_send_to_broker(db: Session, *, order_id: int, symbol: str, side: str, qty, order_type: str | None, payload: dict | None = None):
    # ✅ 중복 호출 방지: received일 때만 1회 실행
    cur = db.execute(text("select status from orders where id=:id"), {"id": int(order_id)}).scalar()
    if cur and str(cur) != "received":
        return

    # ✅ DRY_RUN이면 status=dry_run으로 바꿔서 실행 여부 확인
    if _is_dry_run():
        try:
            db.execute(
                text("update orders set status='dry_run', reason=:r, updated_at=now() where id=:id"),
                {"id": int(order_id), "r": "DRY_RUN=1"}
            )
            db.commit()
        except Exception:
            db.rollback()
        return

    # ✅ 실전: sending -> (okx) -> sent/failed
    try:
        db.execute(text("update orders set status='sending', updated_at=now() where id=:id"), {"id": int(order_id)})
        db.commit()

        try:
            okx_result = okx_place_order(
                symbol=symbol,
                side=side,
                qty=float(qty) if qty is not None else 0.0,
                order_type=order_type or "market",
            )
        except NameError:
            raise RuntimeError("okx_place_order not wired yet (Week4 Day1)")

        okx_order_id = None
        if isinstance(okx_result, dict):
            okx_order_id = okx_result.get("ordId") or okx_result.get("order_id")
            if not okx_order_id and isinstance(okx_result.get("data"), list) and okx_result["data"]:
                okx_order_id = okx_result["data"][0].get("ordId") or okx_result["data"][0].get("order_id")

        db.execute(
            text("update orders set status='sent', okx_order_id=:oid, okx_response=cast(:resp as jsonb), updated_at=now() where id=:id"),
            {"id": int(order_id), "oid": okx_order_id, "resp": json.dumps(okx_result, ensure_ascii=False)}
        )
        db.commit()
    except Exception as e:
        try:
            db.rollback()
            db.execute(
                text("update orders set status='failed', reason=:r, updated_at=now() where id=:id"),
                {"id": int(order_id), "r": str(e)}
            )
            db.commit()
        except Exception:
            db.rollback()
"""

src2 = src[:insert_at] + helper + "\n" + src[insert_at:]

# --- /tv 핸들러 블록 안에서만 주입(데코레이터가 싱글/더블쿼트 상관없게) ---
m_tv = re.search(r"^\s*@app\.post\(\s*['\"]\/tv['\"]\s*\)", src2, flags=re.M)
if m_tv:
    # 데코레이터 뒤 첫 def 찾기
    m_def = re.search(r"^\s*(async\s+def|def)\s+\w+\s*\(", src2[m_tv.end():], flags=re.M)
    if not m_def:
        raise SystemExit("ERR: found @app.post('/tv') but cannot find handler def")

    fn_start = m_tv.end() + m_def.start()
    # 함수 끝: 다음 데코레이터(@app.) 또는 EOF 전까지를 대충 함수 블록으로 본다
    m_next_route = re.search(r"^\s*@app\.\w+\(", src2[fn_start:], flags=re.M)
    fn_end = fn_start + (m_next_route.start() if m_next_route else len(src2) - fn_start)
    fn_block = src2[fn_start:fn_end]

    pat_assign = r"(created\s*,\s*order_id\s*,\s*idem_key\s*=\s*_create_order_if_new\([\s\S]*?\)\s*\n)"
    m_assign = re.search(pat_assign, fn_block)
    if not m_assign:
        raise SystemExit("ERR: cannot find _create_order_if_new assignment inside /tv handler")

    inject = """
        # ✅ broker send (guarded)
        if created and order_id is not None:
            _maybe_send_to_broker(
                db,
                order_id=int(order_id),
                symbol=str(symbol) if symbol is not None else "",
                side=str(side) if side is not None else "",
                qty=qty,
                order_type=payload.get("type") if isinstance(payload, dict) else None,
                payload=payload if isinstance(payload, dict) else None,
            )
"""
    fn_block2 = fn_block[:m_assign.end()] + inject + fn_block[m_assign.end():]
    src3 = src2[:fn_start] + fn_block2 + src2[fn_end:]
else:
    # /tv 라우트 못 찾으면(특이 케이스): 전체에서 첫 assignment 뒤에 주입
    pat_assign = r"(created\s*,\s*order_id\s*,\s*idem_key\s*=\s*_create_order_if_new\([\s\S]*?\)\s*\n)"
    m_assign = re.search(pat_assign, src2)
    if not m_assign:
        raise SystemExit("ERR: cannot find any _create_order_if_new assignment to inject")
    inject = """
        # ✅ broker send (guarded)
        if created and order_id is not None:
            _maybe_send_to_broker(
                db,
                order_id=int(order_id),
                symbol=str(symbol) if symbol is not None else "",
                side=str(side) if side is not None else "",
                qty=qty,
                order_type=payload.get("type") if isinstance(payload, dict) else None,
                payload=payload if isinstance(payload, dict) else None,
            )
"""
    src3 = src2[:m_assign.end()] + inject + src2[m_assign.end():]

tmp = path.with_suffix(".py.tmp")
tmp.write_text(src3, encoding="utf-8")
if tmp.stat().st_size < 20000:
    raise SystemExit(f"ERR: patched file too small: {tmp.stat().st_size}")
tmp.replace(path)

print("OK: v5 patched (_maybe_send_to_broker + inject after _create_order_if_new in /tv)")
print("SIZE:", path.stat().st_size)

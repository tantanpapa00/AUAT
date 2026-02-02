import re
from pathlib import Path

path = Path(r"C:\autobot\app\main.py")
src = path.read_text(encoding="utf-8", errors="replace")

marker = r"# 4\.5\) \(Day4\) optional broker send"
accepted_anchor = r"# 5\) accepted"

# 훅이 몇 개 있는지 체크
cnt = len(re.findall(marker, src))
print("HOOK_COUNT_BEFORE =", cnt)
if cnt == 0:
    raise SystemExit("ERR: no Day4 hook marker found")

# 훅 블록(들)을 통째로 걷어낼 구간:
# 첫 marker부터 '# 5) accepted' 직전까지를 모두 제거 후, canonical 훅 1개만 삽입
m_first = re.search(marker, src)
m_acc = re.search(accepted_anchor, src)
if not m_first or not m_acc or m_first.start() > m_acc.start():
    raise SystemExit("ERR: cannot locate hook region before '# 5) accepted'")

pre = src[:m_first.start()]
post = src[m_acc.start():]  # '# 5) accepted'부터 끝까지

canonical = """
        # 4.5) (Day4) optional broker send
        # - DRY_RUN=1: no broker call, keep status=received
        # - DRY_RUN=0: sending -> sent on success, failed on error
        if created and order_id is not None:
            if _is_dry_run():
                pass
            else:
                try:
                    _set_order_status(db, int(order_id), "sending")
                    db.commit()

                    try:
                        okx_result = okx_place_order(
                            symbol=symbol,
                            side=side,
                            qty=qty,
                            order_type=payload.get("type") if isinstance(payload, dict) else "market",
                        )
                    except NameError:
                        raise RuntimeError("okx_place_order not wired yet (Week4 Day1)")

                    okx_order_id = None
                    if isinstance(okx_result, dict):
                        okx_order_id = okx_result.get("ordId") or okx_result.get("order_id") or okx_result.get("okx_order_id")

                    _set_order_status(db, int(order_id), "sent", okx_order_id=okx_order_id, okx_response=okx_result)
                    db.commit()

                except Exception as e:
                    db.rollback()
                    try:
                        _set_order_status(db, int(order_id), "failed", reason=str(e))
                        db.commit()
                    except Exception:
                        db.rollback()
"""

# 들여쓰기 안정화: pre의 마지막 줄에서 indent 추정(보통 8칸)
# 이미 canonical은 8칸 기준으로 작성됨.

src2 = pre + canonical + post

cnt_after = len(re.findall(marker, src2))
print("HOOK_COUNT_AFTER =", cnt_after)
if cnt_after != 1:
    raise SystemExit(f"ERR: expected 1 hook after patch, got {cnt_after}")

# 안전 체크
tmp = path.with_suffix(".py.tmp")
tmp.write_text(src2, encoding="utf-8")
if tmp.stat().st_size < 20000:
    raise SystemExit(f"ERR: patched file too small: {tmp.stat().st_size}")

tmp.replace(path)
print("OK: deduped Day4 hook to 1 copy + NameError=>failed")
print("SIZE:", path.stat().st_size)

# patch_poll_candidates_orderby_v2.py
# Usage:
#   cd C:\autobot
#   python .\patch_poll_candidates_orderby_v2.py

from __future__ import annotations
import sys, re
from pathlib import Path
from datetime import datetime

MAIN = Path(r"C:\autobot\app\main.py")

def die(msg: str) -> None:
    print(f"[patch-orderby-v2] ERROR: {msg}", file=sys.stderr)
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

    # 1) 가장 정확한 문자열 치환
    old1 = "order by coalesce(last_checked_at, to_timestamp(0)) asc, id asc"
    new1 = "order by last_checked_at asc nulls first, id asc"
    if old1 in txt:
        txt = txt.replace(old1, new1)

    # 2) 혹시 공백/개행이 다른 변형 대응(정규식)
    #    order by coalesce(last_checked_at, to_timestamp(0)) asc, id asc
    rx = re.compile(
        r"order\s+by\s+coalesce\s*\(\s*last_checked_at\s*,\s*to_timestamp\s*\(\s*0\s*\)\s*\)\s*asc\s*,\s*id\s*asc",
        re.IGNORECASE
    )
    txt, n2 = rx.subn(new1, txt)

    # 3) 안전장치: 바뀐 게 하나도 없으면 실패로 처리
    if txt == before:
        # 힌트용으로 coalesce(last_checked_at) 존재 여부만 체크
        if "coalesce(last_checked_at" in txt:
            die("coalesce(last_checked_at...) found but ORDER BY pattern mismatch. Send me the exact snippet around the query.")
        die("target ORDER BY not found")

    bak = backup(MAIN)
    MAIN.write_text(txt, encoding="utf-8")

    # 치환 개수 출력
    changed = 0
    if old1 in before:
        changed += before.count(old1)
    changed += n2

    print("[patch-orderby-v2] OK")
    print(f"[patch-orderby-v2] replaced={changed}")
    print(f"[patch-orderby-v2] main.py -> {MAIN} (backup: {bak.name})")

if __name__ == "__main__":
    main()

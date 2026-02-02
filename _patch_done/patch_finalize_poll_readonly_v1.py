# patch_finalize_poll_readonly_v1.py
# 목적:
# - /api/diag/poll-now (changes 모드)를 "완전 읽기 전용"으로 안정화
# - 런타임에서 _ensure_* (DDL) 호출 제거
# - startup 중복 워커 이름 꼬임 방지: _startup_order_poller 블록 비활성화(있으면)
#
# 실행:
#   python .\patch_finalize_poll_readonly_v1.py

from __future__ import annotations
import re
from pathlib import Path
from datetime import datetime

ROOT = Path(r"C:\autobot")
MAIN = ROOT / "app" / "main.py"

def backup(path: Path) -> Path:
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    bak = path.with_name(path.name + f".bak.{ts}")
    bak.write_text(path.read_text(encoding="utf-8"), encoding="utf-8")
    return bak

def main():
    if not MAIN.exists():
        raise SystemExit(f"main.py not found: {MAIN}")

    src = MAIN.read_text(encoding="utf-8")
    bak = backup(MAIN)

    changed = 0

    # 1) api_poll_now 내부에서 _ensure_* 호출 제거(DDL 금지)
    #    - api_poll_now 함수 블록만 대상으로 함.
    m = re.search(r"@app\.post\(\"/api/diag/poll-now\"[\s\S]*?\ndef api_poll_now\([\s\S]*?\):\n", src)
    if not m:
        raise SystemExit("api_poll_now not found")

    # api_poll_now 함수 전체 블록 잘라내기 (다음 데코레이터 혹은 EOF 전까지)
    start = m.start()
    # 다음 @app. 데코레이터 위치를 찾되, api_poll_now 이후의 첫 번째 @app.* 를 엔드로 잡음
    m2 = re.search(r"\n@app\.(get|post|put|delete)\(", src[m.end():])
    end = (m.end() + m2.start()) if m2 else len(src)
    block = src[start:end]

    # ensure 호출 제거
    block2 = re.sub(r"^\s*_ensure_orders_table\(db\)\s*\n", "", block, flags=re.M)
    block2 = re.sub(r"^\s*_ensure_order_tracking_cols\(db\)\s*\n", "", block2, flags=re.M)

    if block2 != block:
        src = src[:start] + block2 + src[end:]
        changed += 1

    # 2) changes 모드에서 lock_timeout/statement_timeout을 과격하게 건드리는 부분이 있으면 완화
    #    - SET lock_timeout=... / SET statement_timeout=... 를 api_poll_now 블록 안에서만 제거
    #    (이미 wrapper에서 stage 캡처/timeout 관리가 있으니, 여기서 SET은 불필요)
    # 다시 블록 재추출
    m = re.search(r"@app\.post\(\"/api/diag/poll-now\"[\s\S]*?\ndef api_poll_now\([\s\S]*?\):\n", src)
    start = m.start()
    m2 = re.search(r"\n@app\.(get|post|put|delete)\(", src[m.end():])
    end = (m.end() + m2.start()) if m2 else len(src)
    block = src[start:end]

    block2 = re.sub(r"^\s*db\.execute\(text\(\"SET\s+lock_timeout\s*=\s*[^\"']+\"\)\)\s*\n", "", block, flags=re.M)
    block2 = re.sub(r"^\s*db\.execute\(text\(\"SET\s+statement_timeout\s*=\s*[^\"']+\"\)\)\s*\n", "", block2, flags=re.M)

    if block2 != block:
        src = src[:start] + block2 + src[end:]
        changed += 1

    # 3) _startup_order_poller 중복/NameError 유발 블록을 주석 처리(있으면)
    #    - "def _startup_order_poller" 정의가 있으면 통째로 주석 처리 (안전빵)
    pat = r"\n@app\.on_event\(\"startup\"\)\n(?:@?[^\n]*\n)*def _startup_order_poller\([\s\S]*?\n(?=@app\.on_event\(\"startup\"\)|\n@app\.(get|post|put|delete)\(|\Z)"
    mm = re.search(pat, src)
    if mm:
        chunk = src[mm.start():mm.end()]
        if "ORDER_POLL_WORKER_V1" in src or "_start_order_poll_worker" in src:
            # 중복 가능성 높으니 주석 처리
            commented = "\n".join("# " + line if line.strip() else line for line in chunk.splitlines())
            src = src[:mm.start()] + "\n\n# [PATCH_FINALIZE_POLL_READONLY_V1] disabled duplicate startup poller\n" + commented + "\n\n" + src[mm.end():]
            changed += 1

    if changed == 0:
        print("[patch-finalize-poll-readonly-v1] nothing changed (already applied?)")
        print("[patch-finalize-poll-readonly-v1] backup:", bak)
        return

    MAIN.write_text(src, encoding="utf-8")
    print("[patch-finalize-poll-readonly-v1] OK")
    print("[patch-finalize-poll-readonly-v1] main.py ->", MAIN)
    print("[patch-finalize-poll-readonly-v1] backup ->", bak)

if __name__ == "__main__":
    main()

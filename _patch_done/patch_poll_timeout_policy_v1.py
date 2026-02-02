# patch_poll_timeout_policy_v1.py
# Usage:
#   cd C:\autobot
#   python .\patch_poll_timeout_policy_v1.py

from __future__ import annotations
import sys
from pathlib import Path
from datetime import datetime

MAIN = Path(r"C:\autobot\app\main.py")

def die(msg: str) -> None:
    print(f"[patch-timeout-policy-v1] ERROR: {msg}", file=sys.stderr)
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

    # poll_orders_once(stage-debug wrapper)에서 걸어둔 statement_timeout=2500 제거
    old = 'db.execute(text("SET statement_timeout = 2500"))'
    old2 = 'db2.execute(text("SET statement_timeout = 2500"))'
    # (혹시 공백 변형)
    old3 = 'db.execute(text("SET statement_timeout=2500"))'
    old4 = 'db2.execute(text("SET statement_timeout=2500"))'

    repl = '\n            # 후보 조회는 statement_timeout으로 끊지 말고, lock_timeout만 짧게 둡니다.\n            try:\n                db.execute(text("SET lock_timeout = 800"))\n                db.execute(text("SET statement_timeout = 0"))\n            except Exception:\n                pass\n'
    repl2 = '\n            try:\n                db2.execute(text("SET lock_timeout = 800"))\n                db2.execute(text("SET statement_timeout = 0"))\n            except Exception:\n                pass\n'

    # db 구간 치환
    if old in txt:
        txt = txt.replace(old, repl)
    if old3 in txt:
        txt = txt.replace(old3, repl)

    # db2 구간 치환
    if old2 in txt:
        txt = txt.replace(old2, repl2)
    if old4 in txt:
        txt = txt.replace(old4, repl2)

    if txt == before:
        # statement_timeout 라인이 아예 없으면 이미 제거된 상태
        if "statement_timeout = 2500" in before or "statement_timeout=2500" in before:
            die("found statement_timeout=2500 but pattern mismatch. (Send 20 lines around it.)")
        print("[patch-timeout-policy-v1] OK (already applied or not found)")
        return

    bak = backup(MAIN)
    MAIN.write_text(txt, encoding="utf-8")
    print("[patch-timeout-policy-v1] OK")
    print(f"[patch-timeout-policy-v1] main.py -> {MAIN} (backup: {bak.name})")

if __name__ == "__main__":
    main()

# patch_stabilize_polling_v1.py
# 목적:
# - poll_orders_once 내부의 "SET statement_timeout = 2500"를 제거하고
#   lock_timeout=800 + statement_timeout=0으로 안정화
# - 워커 startup에서 _poller_loop 잘못 참조 시 _poll_worker_loop로 치환
# - 컴파일 체크 후 실패하면 자동 롤백
#
# Usage:
#   cd C:\autobot
#   python .\patch_stabilize_polling_v1.py

from __future__ import annotations
import sys
from pathlib import Path
from datetime import datetime

MAIN = Path(r"C:\autobot\app\main.py")

def backup(path: Path) -> Path:
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    bak = path.with_suffix(path.suffix + f".bak.{ts}")
    bak.write_bytes(path.read_bytes())
    return bak

def compile_check(text: str) -> None:
    compile(text, str(MAIN), "exec")

def main():
    if not MAIN.exists():
        print(f"[patch-stabilize-v1] ERROR: not found {MAIN}", file=sys.stderr)
        sys.exit(1)

    before = MAIN.read_text(encoding="utf-8-sig")
    txt = before

    # 1) 워커 NameError 방지: target=_poller_loop -> target=_poll_worker_loop
    txt = txt.replace("target=_poller_loop", "target=_poll_worker_loop")

    # 2) statement_timeout=2500 제거/대체
    #   (라인 단위로 안전하게: 동일 indent 유지)
    def replace_timeout_line(s: str) -> str:
        import re
        patterns = [
            r'^(?P<ind>\s*)db\.execute\(text\("SET statement_timeout\s*=\s*2500"\)\)\s*$',
            r'^(?P<ind>\s*)db2\.execute\(text\("SET statement_timeout\s*=\s*2500"\)\)\s*$',
            r'^(?P<ind>\s*)db\.execute\(text\("SET statement_timeout\s*=\s*2500;"\)\)\s*$',
            r'^(?P<ind>\s*)db2\.execute\(text\("SET statement_timeout\s*=\s*2500;"\)\)\s*$',
        ]
        for p in patterns:
            s = re.sub(
                p,
                lambda m: (
                    f'{m.group("ind")}' +
                    ('db2' if 'db2.' in m.group(0) else 'db') +
                    '.execute(text("SET lock_timeout = 800"))\n' +
                    f'{m.group("ind")}' +
                    ('db2' if 'db2.' in m.group(0) else 'db') +
                    '.execute(text("SET statement_timeout = 0"))'
                ),
                s,
                flags=re.MULTILINE
            )
        # 혹시 inline으로 들어간 케이스도 보수적으로 치환
        s = s.replace('text("SET statement_timeout = 2500")', 'text("SET statement_timeout = 0")')
        s = s.replace('text("SET statement_timeout=2500")', 'text("SET statement_timeout = 0")')
        return s

    txt = replace_timeout_line(txt)

    # 3) 컴파일 체크 (실패하면 롤백)
    bak = backup(MAIN)
    try:
        compile_check(txt)
    except Exception as e:
        # 롤백
        MAIN.write_bytes(bak.read_bytes())
        print("[patch-stabilize-v1] ERROR: compile failed, rolled back to backup", file=sys.stderr)
        print(f"[patch-stabilize-v1] backup used: {bak.name}", file=sys.stderr)
        print(f"[patch-stabilize-v1] err: {e}", file=sys.stderr)
        sys.exit(1)

    # 4) 적용
    MAIN.write_text(txt, encoding="utf-8")
    print("[patch-stabilize-v1] OK")
    print(f"[patch-stabilize-v1] main.py -> {MAIN} (backup: {bak.name})")

if __name__ == "__main__":
    main()

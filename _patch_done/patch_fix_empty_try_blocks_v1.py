# patch_fix_empty_try_blocks_v1.py
# 목적: main.py에서 "try:" 다음에 들여쓴 블록이 없는(빈) 케이스를 자동으로 찾아 pass를 삽입해 IndentationError를 복구
# Usage:
#   cd C:\autobot
#   python .\patch_fix_empty_try_blocks_v1.py

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

def leading_spaces(s: str) -> int:
    return len(s) - len(s.lstrip(" "))

def main():
    if not MAIN.exists():
        print(f"[patch-fix-empty-try-v1] ERROR: not found {MAIN}", file=sys.stderr)
        sys.exit(1)

    txt = MAIN.read_text(encoding="utf-8-sig")
    lines = txt.splitlines(True)

    out = []
    fixed = 0
    n = len(lines)

    i = 0
    while i < n:
        line = lines[i]
        out.append(line)

        if line.strip() == "try:":
            base = leading_spaces(line)

            # 다음 "비어있지 않은" 라인을 찾는다
            j = i + 1
            while j < n and lines[j].strip() == "":
                j += 1

            if j < n:
                nxt = lines[j]
                nxt_indent = leading_spaces(nxt)

                # 정상이라면 nxt_indent > base 여야 함
                # 그렇지 않으면 빈 try 블록이므로 pass 삽입
                if nxt_indent <= base:
                    out.append(" " * (base + 4) + "pass  # autofix empty try block\n")
                    fixed += 1

        i += 1

    if fixed == 0:
        print("[patch-fix-empty-try-v1] OK (no empty try blocks found)")
        return

    bak = backup(MAIN)
    MAIN.write_text("".join(out), encoding="utf-8")
    print("[patch-fix-empty-try-v1] OK")
    print(f"[patch-fix-empty-try-v1] fixed={fixed}")
    print(f"[patch-fix-empty-try-v1] main.py -> {MAIN} (backup: {bak.name})")

if __name__ == "__main__":
    main()

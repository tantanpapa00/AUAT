# patch_fix_backslash_quotes_v1.py
# Usage:
#   cd C:\autobot
#   python .\patch_fix_backslash_quotes_v1.py

from __future__ import annotations
import sys
from pathlib import Path
from datetime import datetime

MAIN = Path(r"C:\autobot\app\main.py")

def die(msg: str) -> None:
    print(f"[fix-quotes-v1] ERROR: {msg}", file=sys.stderr)
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

    start = txt.find("# [POLL_CHANGES_WRAPPER_V1]")
    if start < 0:
        die("marker not found: [POLL_CHANGES_WRAPPER_V1]")

    end = txt.find("# [ORDER_POLL_WORKER_V1]", start)
    if end < 0:
        # 그래도 안전하게: 다음 @app 또는 EOF까지
        end2 = txt.find("\n@app.", start)
        end = end2 if end2 >= 0 else len(txt)

    head = txt[:start]
    mid  = txt[start:end]
    tail = txt[end:]

    # 핵심: wrapper 구간에 남아있는 \" 를 모두 " 로 복구
    fixed_mid = mid.replace('\\"', '"')

    if fixed_mid == mid:
        print("[fix-quotes-v1] OK (no changes needed)")
        return

    bak = backup(MAIN)
    MAIN.write_text(head + fixed_mid + tail, encoding="utf-8")
    print("[fix-quotes-v1] OK")
    print(f"[fix-quotes-v1] main.py -> {MAIN} (backup: {bak.name})")

if __name__ == "__main__":
    main()

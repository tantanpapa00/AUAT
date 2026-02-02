import re
import shutil
from datetime import datetime
from pathlib import Path

MAIN = Path(r"C:\autobot\app\main.py")

def backup(p: Path):
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    b = p.with_suffix(p.suffix + f".bak_{ts}")
    shutil.copy2(p, b)
    return b

def main():
    src = MAIN.read_text(encoding="utf-8", errors="replace")
    b = backup(MAIN)
    print("Backup:", b)

    # 1) 가장 흔한 케이스: textfrom sqlalchemy.exc ...
    src2 = src.replace(
        "from sqlalchemy import textfrom sqlalchemy.exc import IntegrityError",
        "from sqlalchemy import text\nfrom sqlalchemy.exc import IntegrityError"
    )

    # 2) 혹시 다른 형태로도 붙었을 수 있어 안전망(regex)
    src2 = re.sub(
        r"(from sqlalchemy import\s+text)\s*from\s+sqlalchemy\.exc\s+import",
        r"\1\nfrom sqlalchemy.exc import",
        src2
    )

    # 3) 혹시 'textfrom ' 자체가 남아있으면 강제 분리(최후 안전망)
    src2 = src2.replace("from sqlalchemy import textfrom ", "from sqlalchemy import text\nfrom ")

    if src2 == src:
        print("WARN: No change detected (import line may be different). 그래도 파일은 그대로 둡니다.")
    else:
        MAIN.write_text(src2, encoding="utf-8")
        print("Fixed imports:", MAIN)

if __name__ == "__main__":
    main()

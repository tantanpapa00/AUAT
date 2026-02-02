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

    # 이미 engine이 있으면 스킵
    if re.search(r'^\s*engine\s*=\s*create_engine\(', src, flags=re.M):
        print("Skip: engine already exists")
        return

    # create_engine import가 없으면 추가
    if "from sqlalchemy import create_engine" not in src and "create_engine" not in src:
        # 대부분 text()를 쓰고 있으니 sqlalchemy import 블록 근처에 삽입
        src = src.replace("from sqlalchemy import text", "from sqlalchemy import text, create_engine")

    # DATABASE_URL이 main.py에 로딩되는지 확인
    # - 이미 os.getenv / dotenv 사용하고 있을 가능성 높음
    if "DATABASE_URL" not in src:
        print("WARN: DATABASE_URL string not found in main.py. 그래도 engine은 env에서 가져오도록 넣습니다.")

    # app = FastAPI(...) 뒤에 engine 생성 블록 삽입
    m = re.search(r'^\s*app\s*=\s*FastAPI\([^\)]*\)\s*$', src, flags=re.M)
    if not m:
        raise SystemExit("ERROR: app = FastAPI(...) 라인을 찾지 못했습니다. 수동 패치가 필요합니다.")

    insert = """
# ---- DB Engine (for simple query endpoints like /api/home) ----
try:
    engine  # type: ignore
except NameError:
    # DATABASE_URL is expected to be loaded from .env (same as existing code)
    engine = create_engine(DATABASE_URL, pool_pre_ping=True)
"""

    pos = m.end()
    src2 = src[:pos] + "\n" + insert + src[pos:]

    b = backup(MAIN)
    MAIN.write_text(src2, encoding="utf-8")
    print("Backup:", b)
    print("Patched engine into:", MAIN)

if __name__ == "__main__":
    main()

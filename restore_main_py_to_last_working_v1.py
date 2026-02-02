# restore_main_py_to_last_working_v1.py
# 목적: C:\autobot\app\main.py.bak.* 중 "컴파일 가능한" 최신 백업을 찾아 main.py로 복구
# Usage:
#   cd C:\autobot
#   python .\restore_main_py_to_last_working_v1.py

from __future__ import annotations
import sys
from pathlib import Path
from datetime import datetime

APP_DIR = Path(r"C:\autobot\app")
MAIN = APP_DIR / "main.py"

def compile_ok(text: str, fname: str) -> bool:
    try:
        compile(text, fname, "exec")
        return True
    except SyntaxError:
        return False
    except Exception:
        # 다른 예외는 일단 통과(컴파일만 확인)
        return True

def main():
    if not MAIN.exists():
        print(f"[restore] ERROR: not found {MAIN}", file=sys.stderr)
        sys.exit(1)

    backups = sorted(APP_DIR.glob("main.py.bak.*"), key=lambda p: p.stat().st_mtime, reverse=True)
    if not backups:
        print("[restore] ERROR: no backups found (main.py.bak.*)", file=sys.stderr)
        sys.exit(1)

    chosen = None
    for b in backups:
        try:
            txt = b.read_text(encoding="utf-8-sig")
        except Exception:
            txt = b.read_text(encoding="utf-8", errors="ignore")
        if compile_ok(txt, str(b)):
            chosen = b
            break

    if not chosen:
        print("[restore] ERROR: no compilable backup found.", file=sys.stderr)
        print("[restore] TIP: list backups in C:\\autobot\\app and choose manually.", file=sys.stderr)
        sys.exit(1)

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    broken = APP_DIR / f"main.py.broken.{ts}"
    broken.write_bytes(MAIN.read_bytes())

    MAIN.write_bytes(chosen.read_bytes())

    print("[restore] OK")
    print(f"[restore] saved broken -> {broken.name}")
    print(f"[restore] restored from -> {chosen.name}")
    print("[restore] next: start uvicorn with ORDER_POLL_ENABLE=0")

if __name__ == "__main__":
    main()

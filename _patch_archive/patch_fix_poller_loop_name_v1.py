# patch_fix_poller_loop_name_v1.py
# Usage:
#   cd C:\autobot
#   python .\patch_fix_poller_loop_name_v1.py

from __future__ import annotations
import sys
from pathlib import Path
from datetime import datetime

MAIN = Path(r"C:\autobot\app\main.py")

def die(msg: str) -> None:
    print(f"[patch-fix-poller-name-v1] ERROR: {msg}", file=sys.stderr)
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

    # 1) startup에서 잘못된 target 이름 교체
    txt = txt.replace("target=_poller_loop", "target=_poll_worker_loop")

    # 2) 혹시 다른 위치에서도 _poller_loop를 참조하면 안전하게 별칭 추가
    #    (이미 별칭이 있으면 추가하지 않음)
    if "_poller_loop = _poll_worker_loop" not in txt:
        marker = "# [ORDER_POLL_WORKER_V1]"
        idx = txt.find(marker)
        if idx >= 0:
            # marker 바로 아래에 alias 삽입(안전)
            insert_at = txt.find("\n", idx)
            if insert_at > 0:
                alias = "\n# alias for backward-compat (startup/thread target)\n_poller_loop = _poll_worker_loop\n"
                # 단, _poll_worker_loop 정의보다 위에 들어가면 NameError가 될 수 있으니,
                # 우선 alias는 "def _poll_worker_loop" 이후에만 삽입하도록 한다.
                def_pos = txt.find("def _poll_worker_loop")
                if def_pos > 0:
                    # def 블록 끝 대충 찾기(다음 'def ' 또는 '@app.' 전)
                    next_def = txt.find("\ndef ", def_pos + 10)
                    next_app = txt.find("\n@app.", def_pos + 10)
                    end_pos = min([p for p in [next_def, next_app, len(txt)] if p != -1], default=len(txt))
                    txt = txt[:end_pos] + alias + txt[end_pos:]

    if txt == before:
        print("[patch-fix-poller-name-v1] OK (no changes needed)")
        return

    bak = backup(MAIN)
    MAIN.write_text(txt, encoding="utf-8")
    print("[patch-fix-poller-name-v1] OK")
    print(f"[patch-fix-poller-name-v1] main.py -> {MAIN} (backup: {bak.name})")

if __name__ == "__main__":
    main()

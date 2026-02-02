from pathlib import Path

TARGET = Path(r"C:\autobot\app\main.py")
lines = TARGET.read_text(encoding="utf-8").splitlines()

# templates가 의존하는 헬퍼들(보통 아래 3개가 같이 주석처리되어 있음)
START_MARKERS = [
    "# def _canonical_values(",
    "# def _make_config_hash(",
    "# def _get_strategy_or_404(",
]

def find_start():
    for i, l in enumerate(lines):
        s = l.lstrip()
        if any(s.startswith(m) for m in START_MARKERS):
            return i
    return None

start = find_start()
if start is None:
    print("NOOP: helper blocks not found (already uncommented?)")
    raise SystemExit(0)

# start부터 다음 @app 데코레이터 블록 직전까지(헬퍼 영역만) 주석 해제
changed = 0
i = start
while i < len(lines):
    s = lines[i].lstrip()
    if s.startswith("# @app."):
        break

    if s.startswith("#"):
        # 원래 들여쓰기는 보존하면서 첫번째 # 또는 "# "만 제거
        idx = lines[i].find("#")
        prefix = lines[i][:idx]
        rest = lines[i][idx:]
        if rest.startswith("# "):
            rest = rest[2:]
        elif rest.startswith("#"):
            rest = rest[1:]
        lines[i] = prefix + rest
        changed += 1
    i += 1

TARGET.write_text("\n".join(lines) + "\n", encoding="utf-8")
print("patched_lines=", changed)

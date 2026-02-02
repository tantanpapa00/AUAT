from pathlib import Path
import re

TARGET = Path(r"C:\autobot\app\main.py")
lines = TARGET.read_text(encoding="utf-8").splitlines()

WANT = {
    "/api/home",
    "/api/accounts",
    "/api/strategies",
    "/api/assets",
    "/api/strategies/{strategy_id}/signal-params",
    "/api/strategies/{strategy_id}/templates/tradingview",
}

# "# @app.get(" / "# @app.post(" 등 라우트 주석 라인 탐지
ROUTE_RE = re.compile(r'^(?P<indent>\s*)#\s*@app\.(get|post|put|delete)\(')

def parse_path(s: str):
    # "# @app.get("/api/strategies")" 같은 형태에서 path만 추출
    s = s.strip()
    if not s.startswith("#"):
        return None
    # "@app.get(" 위치 찾기
    at = s.find("@app.")
    if at < 0:
        return None
    # 첫 따옴표 찾기
    qpos = s.find('"', at)
    if qpos < 0:
        qpos = s.find("'", at)
    if qpos < 0:
        return None
    q = s[qpos]
    end = s.find(q, qpos + 1)
    if end < 0:
        return None
    return s[qpos + 1:end]

def uncomment_line(raw: str) -> str:
    # 들여쓰기 유지하며 첫 '#'만 제거
    idx = raw.find("#")
    if idx < 0:
        return raw
    prefix = raw[:idx]
    rest = raw[idx:]
    if rest.startswith("# "):
        rest = rest[2:]
    elif rest.startswith("#"):
        rest = rest[1:]
    return prefix + rest

changed_blocks = 0
i = 0
while i < len(lines):
    m = ROUTE_RE.match(lines[i])
    if not m:
        i += 1
        continue

    path = parse_path(lines[i])
    if not path or path not in WANT:
        i += 1
        continue

    indent = m.group("indent")

    # 블록 끝: "같은 indent"로 시작하는 다음 "# @app.xxx(" 라인 전까지
    j = i + 1
    while j < len(lines):
        mj = ROUTE_RE.match(lines[j])
        if mj and mj.group("indent") == indent:
            break
        j += 1

    # i..j-1 범위: '#...' 라인은 주석 해제, 빈 줄은 그대로 유지(끊기지 않게)
    for k in range(i, j):
        if lines[k].lstrip().startswith("#"):
            lines[k] = uncomment_line(lines[k])
        # blank line은 그대로 둔다

    changed_blocks += 1
    i = j

TARGET.write_text("\n".join(lines) + "\n", encoding="utf-8")
print("patched_blocks=", changed_blocks)

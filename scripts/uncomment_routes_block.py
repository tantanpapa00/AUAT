from pathlib import Path

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

def parse_path_from_commented_get(s: str):
    # s like: # @app.get("/api/strategies")
    s = s.strip()
    if not s.startswith("# @app.get("):
        return None
    inside = s[len("# @app.get("):]
    if not inside:
        return None
    q = inside[0]
    if q not in ('"', "'"):
        return None
    end = inside.find(q, 1)
    if end <= 1:
        return None
    return inside[1:end]

changed = 0
i = 0
while i < len(lines):
    path = parse_path_from_commented_get(lines[i])
    if path and path in WANT:
        # 주석 블록 전체를 해제: 연속된 "#" 라인들을 '# ' 또는 '#' 제거
        j = i
        while j < len(lines) and lines[j].lstrip().startswith("#"):
            l = lines[j]
            # "    # ..." 형태도 있으니 lstrip 기준으로 처리하되 원본 들여쓰기는 보존
            idx = l.find("#")
            prefix = l[:idx]
            rest = l[idx:]
            if rest.startswith("# "):
                rest = rest[2:]
            elif rest.startswith("#"):
                rest = rest[1:]
            lines[j] = prefix + rest
            j += 1
        changed += 1
        i = j
        continue
    i += 1

TARGET.write_text("\n".join(lines) + "\n", encoding="utf-8")
print("patched_blocks=", changed)

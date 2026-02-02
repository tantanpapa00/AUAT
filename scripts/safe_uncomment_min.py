from pathlib import Path

TARGET = Path(r"C:\autobot\app\main.py")
lines = TARGET.read_text(encoding="utf-8").splitlines()

WANT = {
    "/api/home",
    "/api/accounts",
    "/api/strategies",
    "/api/assets",
    "/api/strategies/{strategy_id}/templates/tradingview",
}

def next_effective(idx: int):
    j = idx + 1
    while j < len(lines):
        t = lines[j].strip()
        if (not t) or t.startswith("#"):
            j += 1
            continue
        return j, t
    return None, None

changed = 0

for i, raw in enumerate(lines):
    s = raw.strip()
    if not s.startswith("# @app.get("):
        continue

    # parse "# @app.get("/path" ...)"
    try:
        inside = s[len("# @app.get("):]
        q = inside[0]
        if q not in ('"', "'"):
            continue
        path = inside[1:inside.find(q, 1)]
    except Exception:
        continue

    if path not in WANT:
        continue

    j, nxt = next_effective(i)
    if j is None:
        continue

    if nxt.startswith("def "):
        lines[i] = raw.replace("# @app.get(", "@app.get(", 1)
        changed += 1

TARGET.write_text("\n".join(lines) + "\n", encoding="utf-8")
print("patched_lines=", changed)

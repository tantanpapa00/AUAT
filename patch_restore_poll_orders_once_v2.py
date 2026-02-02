import os, glob, re
from datetime import datetime

MAIN = r"C:\autobot\app\main.py"
APPDIR = r"C:\autobot\app"

def read_text(p):
    with open(p, "r", encoding="utf-8", errors="replace") as f:
        return f.read()

def write_text(p, s):
    with open(p, "w", encoding="utf-8", newline="\n") as f:
        f.write(s)

def extract_func_block(text, func_name):
    lines = text.splitlines(True)
    start = None
    pat = f"def {func_name}("
    for i, line in enumerate(lines):
        if line.startswith(pat):
            start = i
            break
    if start is None:
        return None

    # 함수 블록은 "다음 top-level def" 또는 "top-level @app" 전까지로 본다
    end = len(lines)
    for j in range(start + 1, len(lines)):
        if re.match(r"^(def\s+|@app\.)", lines[j]):
            end = j
            break
    block = "".join(lines[start:end])
    return block

def main():
    if not os.path.exists(MAIN):
        print("[patch-restore-poll-orders-once-v2] FAIL: main.py not found:", MAIN)
        return 1

    cur = read_text(MAIN)

    # 이미 있으면 종료 (중복삽입 방지)
    if re.search(r"^def\s+poll_orders_once\s*\(", cur, flags=re.M):
        print("[patch-restore-poll-orders-once-v2] OK: poll_orders_once already exists (no change)")
        return 0

    backups = sorted(
        glob.glob(os.path.join(APPDIR, "main.py.bak.*")),
        key=lambda p: os.path.getmtime(p),
        reverse=True
    )

    picked = None
    picked_text = None
    for b in backups:
        t = read_text(b)
        if re.search(r"^def\s+poll_orders_once\s*\(", t, flags=re.M):
            picked = b
            picked_text = t
            break

    if not picked:
        print("[patch-restore-poll-orders-once-v2] FAIL: no backup contains def poll_orders_once(...)")
        return 2

    block = extract_func_block(picked_text, "poll_orders_once")
    if not block:
        print("[patch-restore-poll-orders-once-v2] FAIL: could not extract function block from:", picked)
        return 3

    # 원본 함수 이름을 _poll_orders_once_impl 로 바꿔서 삽입하고,
    # poll_orders_once는 stage/kwargs 받아도 안 터지게 래퍼로 둔다
    block2 = re.sub(r"^def\s+poll_orders_once\s*\(",
                    "def _poll_orders_once_impl(",
                    block, flags=re.M)

    inject = "\n\n# [POLL_ORDERS_ONCE_RESTORED_V2]\n" + block2 + """
def poll_orders_once(*, limit: int = 20, stage=None, **kwargs) -> dict:
    \"\"\"Compat wrapper: api/diag/poll-now may pass stage/kwargs.\"\"\"
    return _poll_orders_once_impl(limit=limit)

def call_poll_orders_once(limit: int = 20, stage=None, **kwargs) -> dict:
    \"\"\"Compat wrapper used by some diag wrappers.\"\"\"
    return poll_orders_once(limit=limit, stage=stage, **kwargs)
"""

    # 삽입 위치: def api_poll_now 바로 위 (없으면 diag endpoint 위)
    m = re.search(r"^def\s+api_poll_now\s*\(", cur, flags=re.M)
    if m:
        pos = m.start()
        out = cur[:pos] + inject + "\n\n" + cur[pos:]
    else:
        m2 = re.search(r"^@app\.post\([\"']\/api\/diag\/poll-now[\"']\)", cur, flags=re.M)
        if not m2:
            print("[patch-restore-poll-orders-once-v2] FAIL: cannot find insertion point (api_poll_now or @app.post('/api/diag/poll-now'))")
            return 4
        pos = m2.start()
        out = cur[:pos] + inject + "\n\n" + cur[pos:]

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    bak = MAIN + f".bak.{ts}"
    write_text(bak, cur)
    write_text(MAIN, out)

    print("[patch-restore-poll-orders-once-v2] OK")
    print("[patch-restore-poll-orders-once-v2] picked backup:", picked)
    print("[patch-restore-poll-orders-once-v2] backup ->", bak)
    print("[patch-restore-poll-orders-once-v2] wrote  ->", MAIN)
    return 0

if __name__ == "__main__":
    raise SystemExit(main())

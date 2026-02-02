import re
from pathlib import Path

TARGET = Path(r"C:\autobot\app\main.py")

# 최신 백업 찾기 (bak_routes 우선, 없으면 bak_uncomment)
cands = sorted(TARGET.parent.glob("main.py.bak_routes_*"), key=lambda p: p.stat().st_mtime, reverse=True)
if not cands:
    cands = sorted(TARGET.parent.glob("main.py.bak_uncomment_*"), key=lambda p: p.stat().st_mtime, reverse=True)

if not cands:
    raise SystemExit("No backup files found (main.py.bak_routes_* or main.py.bak_uncomment_*)")

BACKUP = cands[0]
print("Using BACKUP:", BACKUP)

need = [
  "_resolve_by_config_hash",
  "_resolve_strategy_by_secret",
  "_resolve_asset",
  "_create_order_if_new",
  "_enqueue_tv_event",
  "_db_connect",
]

cur = TARGET.read_text(encoding="utf-8", errors="ignore")
bak = BACKUP.read_text(encoding="utf-8", errors="ignore")

def has_def(src: str, name: str) -> bool:
    return re.search(rf"(?m)^[ \t]*def[ \t]+{re.escape(name)}\b", src) is not None

def extract_top_level_def(src: str, name: str) -> str | None:
    # top-level def 블록을 찾아서 다음 top-level def/class 전까지 추출
    m = re.search(rf"(?m)^(def[ \t]+{re.escape(name)}\b.*)$", src)
    if not m:
        return None
    start = m.start(0)
    # 다음 top-level def/class (컬럼0 시작) 탐색
    m2 = re.search(r"(?m)^(def\s+|class\s+)", src[m.end(0):])
    if not m2:
        return src[start:].rstrip() + "\n"
    end = m.end(0) + m2.start(0)
    return src[start:end].rstrip() + "\n"

missing = [n for n in need if not has_def(cur, n)]
print("Missing:", missing)

if not missing:
    print("Nothing to restore.")
    raise SystemExit(0)

blocks = []
for n in missing:
    b = extract_top_level_def(bak, n)
    if not b:
        print("!! Not found in backup:", n)
        continue
    blocks.append(b)

if not blocks:
    raise SystemExit("No blocks extracted. Cannot restore.")

stamp = "\n\n# ===== AUTO-RESTORED TV HELPERS (from backup) =====\n"
new_text = cur.rstrip() + stamp + "\n\n".join(blocks) + "\n"

TARGET.write_text(new_text, encoding="utf-8")
print("Restored blocks:", len(blocks))
print("Done =>", TARGET)

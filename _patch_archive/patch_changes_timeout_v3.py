# patch_changes_timeout_v3.py
# Usage:
#   cd C:\autobot
#   python .\patch_changes_timeout_v3.py

from __future__ import annotations
import re, sys
from pathlib import Path
from datetime import datetime

ROOT = Path.cwd()
MAIN = ROOT / "app" / "main.py"

def die(msg: str):
    print(f"[patch-changes-timeout-v3] ERROR: {msg}", file=sys.stderr)
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

    # 1) Ensure poll-now endpoint exists (with mode + lock). If not, stop.
    if 'mode: str = Query("changes"' not in txt or "_POLL_LOCK" not in txt:
        die("poll-now(mode+lock) not found. Apply patch_poll_lock_v1.py first.")

    # 2) Patch poll_orders_once wrapper to avoid '= any(:ids)' and add quick-exit if no candidates
    # We replace the AFTER snapshot query block that uses "where id = any(:ids)" with safe IN list.
    # Find the marker wrapper block
    m = re.search(r"# \[POLL_CHANGES_WRAPPER_V1\][\s\S]*?def poll_orders_once\(\*, limit: int = 20\) -> dict:[\s\S]*?(?=\n# \[ORDER_POLL_WORKER_V1\]|\n@app\.|\Z)", txt)
    if not m:
        die("cannot find POLL_CHANGES_WRAPPER_V1 block")

    block = txt[m.start():m.end()]

    # A) Add early return when no candidates
    if "if not candidate_ids:" not in block:
        block = re.sub(
            r"(# 2\) Run existing implementation[\s\S]*?impl_res = \{\}[\s\S]*?except Exception as e:[\s\S]*?return \{\"ok\": False, \"count\": 0, \"items\": \[\], \"note\": f\"impl_failed: \{e\}\"\}\n)",
            r"\1\n    # candidates 없으면 변경분도 없음 (즉시 반환)\n    if not candidate_ids:\n        return {\"ok\": True, \"count\": 0, \"items\": [], \"scanned\": 0, \"note\": \"changes_only | no_candidates\"}\n",
            block,
            count=1
        )

    # B) Replace any(:ids) query with dynamic IN (...) placeholders
    if "where id = any(:ids)" in block:
        # Replace whole after snapshot execution part with IN placeholders
        # We'll locate the after_rows query string and replace with safe formatting section
        pattern_after = r'after_rows = db2\.execute\(text\("""[\s\S]*?where id = any\(:ids\)[\s\S]*?"""[\s\S]*?\),\s*\{"ids": candidate_ids\}\)\.mappings\(\)\.all\(\)'
        if not re.search(pattern_after, block):
            die("cannot locate after_rows any(:ids) execute() in wrapper block")

        repl = (
            "                # psycopg/pg에서 any(:ids) 바인딩이 환경에 따라 지연될 수 있어,\n"
            "                # 안전하게 IN (:id0,:id1,...) 형태로 구성합니다.\n"
            "                params = {}\n"
            "                ph = []\n"
            "                for i, oid in enumerate(candidate_ids):\n"
            "                    k = f\"id{i}\"\n"
            "                    params[k] = int(oid)\n"
            "                    ph.append(f\":{k}\")\n"
            "                sql = f\"\"\"\n"
            "                    select id, asset_id, symbol, market, side, qty, order_type,\n"
            "                           status, okx_order_id, okx_state, filled_qty, avg_px, last_checked_at, reason\n"
            "                      from orders\n"
            "                     where id in ({', '.join(ph)})\n"
            "                     order by id asc\n"
            "                \"\"\"\n"
            "                after_rows = db2.execute(text(sql), params).mappings().all()"
        )
        block = re.sub(pattern_after, repl, block, count=1)

    # Put patched block back
    txt = txt[:m.start()] + block + txt[m.end():]

    # 3) Patch poll-now changes branch to fail-fast if busy and add hard timeout guard note
    # (Already has lock acquire(0.3), so we just ensure it returns quickly even if impl hangs.)
    # The best we can do without async is: reduce lock timeout and ensure changes path doesn't do network if no candidates.
    # Already handled by wrapper early return.

    bak = backup(MAIN)
    MAIN.write_text(txt, encoding="utf-8")
    print("[patch-changes-timeout-v3] OK")
    print(f"[patch-changes-timeout-v3] main.py -> {MAIN} (backup: {bak.name})")

if __name__ == "__main__":
    main()

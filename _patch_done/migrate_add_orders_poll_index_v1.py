# migrate_add_orders_poll_index_v1.py
# Usage:
#   cd C:\autobot
#   python .\migrate_add_orders_poll_index_v1.py

from __future__ import annotations
import os
from pathlib import Path

def load_env_file(path: Path) -> dict:
    if not path.exists():
        return {}
    d = {}
    for line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        d[k.strip()] = v.strip().strip('"').strip("'")
    return d

def pick_dsn() -> str:
    # env 우선
    for k in ["DATABASE_URL", "DB_URL", "SQLALCHEMY_DATABASE_URL", "POSTGRES_URL", "PG_DSN"]:
        v = os.environ.get(k)
        if v:
            return v

    # .env에서 찾기
    env_path = Path(r"C:\autobot\.env")
    d = load_env_file(env_path)
    for k in ["DATABASE_URL", "DB_URL", "SQLALCHEMY_DATABASE_URL", "POSTGRES_URL", "PG_DSN"]:
        if k in d and d[k]:
            return d[k]

    raise SystemExit("ERROR: DB DSN not found. Set DATABASE_URL (or put it in C:\\autobot\\.env).")

def main():
    dsn = pick_dsn()
    print(f"[migrate-orders-poll-index-v1] DSN loaded (hidden)")

    import psycopg2  # 이미 프로젝트에 있으니 사용 가능 가정
    conn = psycopg2.connect(dsn)
    conn.autocommit = True
    cur = conn.cursor()

    sqls = [
        # 추적 후보 뽑기 최적화(핵심)
        """
        CREATE INDEX CONCURRENTLY IF NOT EXISTS orders_poll_candidates_idx
        ON orders (last_checked_at ASC NULLS FIRST, id ASC)
        WHERE okx_order_id IS NOT NULL
          AND status IN ('sent','partial');
        """,
        # (옵션) okx_order_id 조회도 빠르게 (없으면 추가)
        """
        CREATE INDEX CONCURRENTLY IF NOT EXISTS orders_okx_order_id_idx
        ON orders (okx_order_id)
        WHERE okx_order_id IS NOT NULL;
        """,
    ]

    for s in sqls:
        print("[migrate-orders-poll-index-v1] running:", " ".join(s.split())[:120], "...")
        cur.execute(s)

    cur.close()
    conn.close()
    print("[migrate-orders-poll-index-v1] OK")

if __name__ == "__main__":
    main()

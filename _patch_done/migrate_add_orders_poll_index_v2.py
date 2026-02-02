# migrate_add_orders_poll_index_v2.py
# Usage:
#   cd C:\autobot
#   python .\migrate_add_orders_poll_index_v2.py

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

def normalize_sqlalchemy_url(url: str) -> str:
    u = url.strip()
    # SQLAlchemy driver prefix 제거
    if u.startswith("postgresql+psycopg2://"):
        u = "postgresql://" + u[len("postgresql+psycopg2://"):]
    if u.startswith("postgres+psycopg2://"):
        u = "postgresql://" + u[len("postgres+psycopg2://"):]
    if u.startswith("postgresql+pg8000://"):
        u = "postgresql://" + u[len("postgresql+pg8000://"):]
    return u

def pick_dsn() -> str:
    for k in ["DATABASE_URL", "DB_URL", "SQLALCHEMY_DATABASE_URL", "POSTGRES_URL", "PG_DSN"]:
        v = os.environ.get(k)
        if v:
            return normalize_sqlalchemy_url(v)

    env_path = Path(r"C:\autobot\.env")
    d = load_env_file(env_path)
    for k in ["DATABASE_URL", "DB_URL", "SQLALCHEMY_DATABASE_URL", "POSTGRES_URL", "PG_DSN"]:
        if k in d and d[k]:
            return normalize_sqlalchemy_url(d[k])

    raise SystemExit("ERROR: DB DSN not found. Set DATABASE_URL (or put it in C:\\autobot\\.env).")

def main():
    dsn = pick_dsn()
    print("[migrate-orders-poll-index-v2] DSN loaded (hidden)")

    import psycopg2
    conn = psycopg2.connect(dsn)
    conn.autocommit = True
    cur = conn.cursor()

    sqls = [
        """
        CREATE INDEX CONCURRENTLY IF NOT EXISTS orders_poll_candidates_idx
        ON orders (last_checked_at ASC NULLS FIRST, id ASC)
        WHERE okx_order_id IS NOT NULL
          AND status IN ('sent','partial');
        """,
        """
        CREATE INDEX CONCURRENTLY IF NOT EXISTS orders_okx_order_id_idx
        ON orders (okx_order_id)
        WHERE okx_order_id IS NOT NULL;
        """,
    ]

    for s in sqls:
        print("[migrate-orders-poll-index-v2] running:", " ".join(s.split())[:120], "...")
        cur.execute(s)

    cur.close()
    conn.close()
    print("[migrate-orders-poll-index-v2] OK")

if __name__ == "__main__":
    main()

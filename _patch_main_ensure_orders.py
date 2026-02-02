import re
from pathlib import Path

path = Path(r"C:\autobot\app\main.py")
src = path.read_text(encoding="utf-8", errors="replace")

# _ensure_orders_table 블록을 def _mk_idem_key 직전까지 교체
pattern = r"def _ensure_orders_table\(db: Session\):.*?\n\n(?=def _mk_idem_key)"
m = re.search(pattern, src, flags=re.S)
if not m:
    raise SystemExit("ERR: cannot find _ensure_orders_table() block (expected def _mk_idem_key after it)")

new_block = """def _ensure_orders_table(db: Session):
    try:
        # 1) base table (new installs)
        db.execute(text(\"\"\"
            create table if not exists orders (
                id              bigserial primary key,
                created_at      timestamptz not null default now(),
                updated_at      timestamptz not null default now(),

                account_id      int,
                strategy_id     int,
                config_id       int,
                config_hash     text,
                asset_id        int,

                alert_id        text,
                symbol          text,
                market          text,
                side            text,
                qty             numeric,
                order_type      text,

                idem_key        text,
                idem_source     text,

                status          text not null default 'received',
                reason          text,
                okx_order_id    text,
                okx_response    jsonb,

                payload         jsonb
            );
        \"\"\"))
        # 2) migrate existing installs
        db.execute(text("alter table orders add column if not exists idem_key text;"))
        db.execute(text("alter table orders add column if not exists idem_source text;"))

        # 3) backfill legacy rows (unique + not null)
        db.execute(text("update orders set idem_key = 'legacy:' || id::text where idem_key is null;"))

        # 4) enforce NOT NULL (safe now)
        db.execute(text("alter table orders alter column idem_key set not null;"))

        # 5) indexes
        db.execute(text("create unique index if not exists ux_orders_idem_key on orders(idem_key);"))
        db.execute(text("create index if not exists ix_orders_created_at on orders(created_at desc);"))
        db.execute(text("create index if not exists ix_orders_asset_id on orders(asset_id);"))
        db.execute(text("create index if not exists ix_orders_alert_id on orders(alert_id);"))

        db.commit()
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"ensure_orders_table_failed: {type(e).__name__}: {e}")


"""

patched = src[:m.start()] + new_block + src[m.end():]
tmp = path.with_suffix(".py.tmp")
tmp.write_text(patched, encoding="utf-8")

# 3바이트 사고 방지: 너무 작으면 중단
if tmp.stat().st_size < 20000:
    raise SystemExit(f"ERR: patched file too small: {tmp.stat().st_size}")

tmp.replace(path)
print("OK: patched main.py (_ensure_orders_table)")
print("SIZE:", path.stat().st_size)

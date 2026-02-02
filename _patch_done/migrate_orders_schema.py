from sqlalchemy import text
from app.db import SessionLocal

DDL = [
    # 0) 테이블 없으면 최신 스키마로 생성
    """
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
    """,

    # 1) 기존 테이블이 구버전이어도 컬럼 보강
    "alter table orders add column if not exists created_at timestamptz not null default now();",
    "alter table orders add column if not exists updated_at timestamptz not null default now();",
    "alter table orders add column if not exists account_id int;",
    "alter table orders add column if not exists strategy_id int;",
    "alter table orders add column if not exists config_id int;",
    "alter table orders add column if not exists config_hash text;",
    "alter table orders add column if not exists asset_id int;",
    "alter table orders add column if not exists alert_id text;",
    "alter table orders add column if not exists symbol text;",
    "alter table orders add column if not exists market text;",
    "alter table orders add column if not exists side text;",
    "alter table orders add column if not exists qty numeric;",
    "alter table orders add column if not exists order_type text;",
    "alter table orders add column if not exists idem_key text;",
    "alter table orders add column if not exists idem_source text;",
    "alter table orders add column if not exists reason text;",
    "alter table orders add column if not exists okx_order_id text;",
    "alter table orders add column if not exists okx_response jsonb;",
    "alter table orders add column if not exists payload jsonb;",
    "alter table orders add column if not exists status text;",

    # 2) 인덱스 생성 (idem_key 없어서 터지던 지점)
    "create unique index if not exists ux_orders_idem_key on orders(idem_key);",
    "create index if not exists ix_orders_created_at on orders(created_at desc);",
    "create index if not exists ix_orders_asset_id on orders(asset_id);",
    "create index if not exists ix_orders_alert_id on orders(alert_id);",
]

def main():
    db = SessionLocal()
    try:
        for q in DDL:
            db.execute(text(q))
        db.commit()
        print("OK: orders schema migrated")
    except Exception as e:
        db.rollback()
        print("FAILED:", type(e).__name__, e)
        raise
    finally:
        db.close()

if __name__ == "__main__":
    main()

import re, sys, ast
from pathlib import Path
from datetime import datetime

MAIN = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(r"C:\autobot\app\main.py")
if not MAIN.exists():
    raise SystemExit(f"Not found: {MAIN}")

txt = MAIN.read_text(encoding="utf-8-sig")
orig = txt

def must_find(pat, s, flags=0, label="pattern"):
    m = re.search(pat, s, flags)
    if not m:
        raise RuntimeError(f"Cannot find {label}")
    return m

# ------------------------------------------------------------
# 1) _ensure_orders_table 교체 (idem_key backfill + 중복정리 + 인덱스 생성 안정화)
# ------------------------------------------------------------
ensure_pat = r"def _ensure_orders_table\(db: Session\):\n.*?(?=^def _mk_idem_key)"
m = must_find(ensure_pat, txt, flags=re.S | re.M, label="_ensure_orders_table block")

new_ensure = r'''def _ensure_orders_table(db: Session):
    """
    orders 테이블 스키마 보강 + idem_key 마이그레이션
    - 기존 데이터에 idem_key NULL/중복이 있어도 인덱스 생성이 실패하지 않도록 보정
    """
    # 1) 최신 스키마로 테이블 생성(없을 때만)
    db.execute(text("""
        create table if not exists orders (
            id bigserial primary key,
            created_at timestamptz not null default now(),
            account_id bigint,
            strategy_id bigint,
            config_id bigint,
            config_hash text,
            asset_id bigint,
            alert_id text,
            symbol text,
            market text,
            side text,
            qty numeric,
            order_type text,
            status text not null default 'recv',
            payload jsonb,
            idem_key text,
            idem_source text
        );
    """))

    # 2) 컬럼 보강(기존 테이블에 없으면 추가)
    db.execute(text("alter table orders add column if not exists created_at timestamptz not null default now();"))
    db.execute(text("alter table orders add column if not exists account_id bigint;"))
    db.execute(text("alter table orders add column if not exists strategy_id bigint;"))
    db.execute(text("alter table orders add column if not exists config_id bigint;"))
    db.execute(text("alter table orders add column if not exists config_hash text;"))
    db.execute(text("alter table orders add column if not exists asset_id bigint;"))
    db.execute(text("alter table orders add column if not exists alert_id text;"))
    db.execute(text("alter table orders add column if not exists symbol text;"))
    db.execute(text("alter table orders add column if not exists market text;"))
    db.execute(text("alter table orders add column if not exists side text;"))
    db.execute(text("alter table orders add column if not exists qty numeric;"))
    db.execute(text("alter table orders add column if not exists order_type text;"))
    db.execute(text("alter table orders add column if not exists status text;"))
    db.execute(text("alter table orders add column if not exists payload jsonb;"))
    db.execute(text("alter table orders add column if not exists idem_key text;"))
    db.execute(text("alter table orders add column if not exists idem_source text;"))

    # 3) 데이터 보정: status/idempotency 키가 없거나 중복이면 정리
    db.execute(text("update orders set status='recv' where status is null;"))

    # idem_key가 없으면 (id + created_at 포함)으로 무조건 유니크하게 채움
    db.execute(text("""
        update orders
        set idem_key = md5(
            coalesce(config_hash,'') || '|' ||
            coalesce(symbol,'')      || '|' ||
            coalesce(market,'')      || '|' ||
            coalesce(side,'')        || '|' ||
            coalesce(alert_id,'')    || '|' ||
            id::text                 || '|' ||
            created_at::text
        )
        where idem_key is null or trim(idem_key) = '';
    """))

    # 기존에 idem_key가 이미 있었는데 중복이면 (idem_key + id)로 재해시해서 유니크화
    db.execute(text("""
        with d as (
            select idem_key
            from orders
            where idem_key is not null
            group by idem_key
            having count(*) > 1
        )
        update orders o
        set idem_key = md5(o.idem_key || '|' || o.id::text || '|' || o.created_at::text)
        where o.idem_key in (select idem_key from d);
    """))

    # 이제 NOT NULL + UNIQUE 인덱스 생성이 안전해짐
    db.execute(text("alter table orders alter column idem_key set not null;"))

    # 4) 인덱스 생성
    db.execute(text("create unique index if not exists ux_orders_idem_key on orders(idem_key);"))
    db.execute(text("create index if not exists ix_orders_created_at on orders(created_at desc);"))
    db.execute(text("create index if not exists ix_orders_asset_id on orders(asset_id);"))
'''

txt = txt[:m.start()] + new_ensure + "\n\n" + txt[m.end():]

# ------------------------------------------------------------
# 2) _create_order_if_new 내부: bucket/idem_key 계산 변경
#   - bucket: bar_ts/time/timestamp 숫자면 ms/epoch 그대로 사용
#   - idem_key: alert_id 제외, market 포함
# ------------------------------------------------------------
txt = txt.replace(
    '        bucket = datetime.now(timezone.utc).strftime("%Y%m%d%H%M") if not bar_ts else str(bar_ts)',
    '\n'.join([
        '        # bar_ts/time/timestamp 를 bucket으로 사용 (없으면 분단위 fallback)',
        '        if isinstance(bar_ts, (int, float)):',
        '            bucket = str(int(bar_ts))',
        '        elif bar_ts is None:',
        '            bucket = datetime.now(timezone.utc).strftime("%Y%m%d%H%M")',
        '        else:',
        '            bucket = str(bar_ts).strip()',
    ])
)

txt = txt.replace(
    '        idem_key = _mk_idem_key(config_hash, alert_id, symbol, side, bucket)',
    '        idem_key = _mk_idem_key(config_hash, symbol, market, side, bucket)'
)

# ------------------------------------------------------------
# 3) IntegrityError를 “진짜 idem_key 중복”일 때만 duplicate 처리
# ------------------------------------------------------------
integrity_pat = r"""
(?P<indent>^\s*)except\s+IntegrityError\s*:\s*\n
(?P<body>(?:.*\n)*?)
(?=^\s*except\s+Exception\s+as\s+e\s*:)
"""
m2 = must_find(integrity_pat, txt, flags=re.S | re.M | re.X, label="except IntegrityError block")
ind = m2.group("indent")

new_integrity = (
f"{ind}except IntegrityError as ie:\n"
f"{ind}    # ✅ idem_key 중복만 duplicate 처리, 그 외 IntegrityError는 원인을 그대로 노출\n"
f"{ind}    db.rollback()\n"
f"{ind}    cname = None\n"
f"{ind}    try:\n"
f"{ind}        cname = getattr(getattr(getattr(ie, 'orig', None), 'diag', None), 'constraint_name', None)\n"
f"{ind}    except Exception:\n"
f"{ind}        cname = None\n"
f"{ind}    msg = str(getattr(ie, 'orig', ie))\n"
f"{ind}    if cname == 'ux_orders_idem_key' or 'ux_orders_idem_key' in msg or 'duplicate key value violates unique constraint' in msg:\n"
f"{ind}        bar_ts = None\n"
f"{ind}        if isinstance(payload, dict):\n"
f"{ind}            bar_ts = payload.get('bar_ts') or payload.get('time') or payload.get('timestamp')\n"
f"{ind}\n"
f"{ind}        # bar_ts/time/timestamp 를 bucket으로 사용 (없으면 분단위 fallback)\n"
f"{ind}        if isinstance(bar_ts, (int, float)):\n"
f"{ind}            bucket = str(int(bar_ts))\n"
f"{ind}        elif bar_ts is None:\n"
f"{ind}            bucket = datetime.now(timezone.utc).strftime('%Y%m%d%H%M')\n"
f"{ind}        else:\n"
f"{ind}            bucket = str(bar_ts).strip()\n"
f"{ind}\n"
f"{ind}        idem_key = _mk_idem_key(config_hash, symbol, market, side, bucket)\n"
f"{ind}        return False, None, idem_key\n"
f"{ind}\n"
f"{ind}    raise HTTPException(status_code=400, detail=f\"orders_integrity_error[{cname}]: {msg}\")\n"
)

txt = txt[:m2.start()] + new_integrity + txt[m2.end():]

# ------------------------------------------------------------
# 4) 문법 체크 후 저장(백업 자동)
# ------------------------------------------------------------
# ast.parse는 BOM에 민감할 수 있어 strip
ast.parse(txt.lstrip("\ufeff"))

bak = MAIN.with_name(MAIN.name + ".bak_patch_" + datetime.now().strftime("%Y%m%d_%H%M%S"))
bak.write_text(orig, encoding="utf-8")
MAIN.write_text(txt, encoding="utf-8")

print(f"Backup: {bak}")
print(f"PATCH OK: {MAIN}")

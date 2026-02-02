from pathlib import Path
import re

TARGET = Path(r"C:\autobot\app\main.py")
text = TARGET.read_text(encoding="utf-8")

needed = [
  "_ensure_tv_events_table",
  "_insert_tv_event",
  "_resolve_by_config_hash",
  "_resolve_strategy_by_secret",
  "_resolve_asset",
  "_create_order_if_new",
  "_maybe_send_to_broker",
  "_mk_idem_key",
  "_safe_dumps",
  "_sanitize",
]

missing = []
for name in needed:
    if re.search(rf"^\s*def\s+{re.escape(name)}\s*\(", text, flags=re.M) is None:
        missing.append(name)

marker = "\n# === AUTOFIX_COMPAT_TV_HELPERS ===\n"
if marker in text:
    print("Compat block already exists. Nothing to do.")
    raise SystemExit(0)

if not missing:
    print("No missing helper defs detected (by signature). Still adding compat is skipped.")
    raise SystemExit(0)

compat = r'''
# === AUTOFIX_COMPAT_TV_HELPERS ===
# 목적: 라우트만 살리고 헬퍼가 죽어있어 500 나는 상황을 근본 차단
# 방식: 기존 주석 블록을 억지로 풀지 않고, 하단에 “호환 레이어”로 최소 구현을 제공

from sqlalchemy import text as _sql_text
import json as _json
import hashlib as _hashlib

def _sanitize(v):
    # JSON canonical 용도: dict/list는 ConvertTo-Json 순서 영향 줄이기 위해 안정화
    if isinstance(v, dict):
        return {k: _sanitize(v[k]) for k in sorted(v.keys())}
    if isinstance(v, list):
        return [_sanitize(x) for x in v]
    return v

def _safe_dumps(obj):
    return _json.dumps(obj, ensure_ascii=False, separators=(",", ":"), sort_keys=True)

def _mk_idem_key(*parts):
    raw = "|".join("" if p is None else str(p) for p in parts)
    return _hashlib.sha256(raw.encode("utf-8")).hexdigest()

def _ensure_tv_events_table(db):
    # SQLite/Postgres 모두 text 실행 가능한 형태로 작성
    db.execute(_sql_text("""
    CREATE TABLE IF NOT EXISTS tv_events (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        created_at TEXT NOT NULL,
        alert_id TEXT,
        secret TEXT,
        payload_json TEXT,
        remote_ip TEXT
    )
    """))
    db.commit()

def _insert_tv_event(db, created_at, alert_id, secret, payload_json, remote_ip):
    db.execute(_sql_text("""
        INSERT INTO tv_events(created_at, alert_id, secret, payload_json, remote_ip)
        VALUES (:created_at, :alert_id, :secret, :payload_json, :remote_ip)
    """), {
        "created_at": created_at,
        "alert_id": alert_id,
        "secret": secret,
        "payload_json": payload_json,
        "remote_ip": remote_ip,
    })
    db.commit()

def _resolve_by_config_hash(db, config_hash: str):
    # strategy_configs.config_hash 로 찾아서 account/strategy/config 세팅을 가져온다
    row = db.execute(_sql_text("""
        SELECT
            sc.id           AS config_id,
            sc.strategy_id  AS strategy_id,
            sc.account_id   AS account_id,
            sc.config_hash  AS config_hash,
            sc.values_json  AS values_json
        FROM strategy_configs sc
        WHERE sc.config_hash = :h
        LIMIT 1
    """), {"h": config_hash}).mappings().first()

    if not row:
        return None

    values = {}
    try:
        if row["values_json"]:
            values = _json.loads(row["values_json"])
    except Exception:
        values = {}

    # config values 에 tv_secret 있으면 우선
    expected_secret = (values.get("tv_secret") or "").strip()

    return {
        "config_id": row["config_id"],
        "strategy_id": row["strategy_id"],
        "account_id": row["account_id"],
        "config_hash": row["config_hash"],
        "values": values,
        "expected_secret": expected_secret,
    }

def _resolve_strategy_by_secret(db, secret: str):
    # fallback: strategies.tv_secret 로 찾기
    row = db.execute(_sql_text("""
        SELECT id, name, tv_secret, is_active
        FROM strategies
        WHERE tv_secret = :s
        LIMIT 1
    """), {"s": secret}).mappings().first()
    return row

def _resolve_asset(db, account_id: int, strategy_id: int, symbol: str, market: str):
    row = db.execute(_sql_text("""
        SELECT id, account_id, strategy_id, symbol, market, is_active
        FROM assets
        WHERE account_id=:a AND strategy_id=:st AND symbol=:sym AND market=:m
        LIMIT 1
    """), {"a": account_id, "st": strategy_id, "sym": symbol, "m": market}).mappings().first()
    return row

def _create_order_if_new(db, account_id, strategy_id, config_id, config_hash,
                         asset_id, alert_id, symbol, market, side, qty, order_type, payload):
    idem_key = _mk_idem_key(account_id, strategy_id, config_id, asset_id, alert_id, symbol, market, side, qty, order_type)

    exists = db.execute(_sql_text("""
        SELECT id FROM orders WHERE idem_key=:k LIMIT 1
    """), {"k": idem_key}).mappings().first()

    if exists:
        return {"created": False, "order_id": exists["id"], "idem_key": idem_key}

    db.execute(_sql_text("""
        INSERT INTO orders(
            created_at, updated_at,
            account_id, strategy_id, config_id, config_hash, asset_id,
            alert_id, symbol, market, side, qty, order_type,
            idem_key, status, reason, okx_order_id, filled_qty, avg_px, okx_state, last_checked_at,
            payload_json
        )
        VALUES(
            :created_at, :updated_at,
            :account_id, :strategy_id, :config_id, :config_hash, :asset_id,
            :alert_id, :symbol, :market, :side, :qty, :order_type,
            :idem_key, :status, :reason, :okx_order_id, :filled_qty, :avg_px, :okx_state, :last_checked_at,
            :payload_json
        )
    """), {
        "created_at": _now_kst_iso(),
        "updated_at": _now_kst_iso(),
        "account_id": account_id,
        "strategy_id": strategy_id,
        "config_id": config_id,
        "config_hash": config_hash,
        "asset_id": asset_id,
        "alert_id": alert_id,
        "symbol": symbol,
        "market": market,
        "side": side,
        "qty": qty,
        "order_type": order_type,
        "idem_key": idem_key,
        "status": "queued",
        "reason": None,
        "okx_order_id": None,
        "filled_qty": None,
        "avg_px": None,
        "okx_state": None,
        "last_checked_at": None,
        "payload_json": _safe_dumps(payload),
    })
    db.commit()

    newrow = db.execute(_sql_text("SELECT id FROM orders WHERE idem_key=:k LIMIT 1"), {"k": idem_key}).mappings().first()
    return {"created": True, "order_id": newrow["id"], "idem_key": idem_key}

def _maybe_send_to_broker(db, order_id: int):
    # ORDER_SUBMIT_ENABLE / DRY_RUN 은 기존 코드의 env 플래그를 그대로 존중
    o = db.execute(_sql_text("SELECT * FROM orders WHERE id=:id LIMIT 1"), {"id": order_id}).mappings().first()
    if not o:
        return {"ok": False, "reason": "order_not_found"}

    if str(os.getenv("ORDER_SUBMIT_ENABLE", "0")) != "1":
        db.execute(_sql_text("""
            UPDATE orders SET status='skipped', reason='submit_disabled', updated_at=:u WHERE id=:id
        """), {"u": _now_kst_iso(), "id": order_id})
        db.commit()
        return {"ok": True, "skipped": True, "reason": "submit_disabled"}

    if str(os.getenv("DRY_RUN", "0")) == "1":
        db.execute(_sql_text("""
            UPDATE orders SET status='dry_run', reason='dry_run', updated_at=:u WHERE id=:id
        """), {"u": _now_kst_iso(), "id": order_id})
        db.commit()
        return {"ok": True, "dry_run": True}

    # OKX spot market 주문만 최소 지원
    try:
        res = okx_place_order(
            instId=o["symbol"],
            tdMode="cash",
            side=o["side"],
            ordType=o.get("order_type") or "market",
            sz=str(o["qty"]),
        )
    except Exception as e:
        db.execute(_sql_text("""
            UPDATE orders SET status='failed', reason=:r, updated_at=:u WHERE id=:id
        """), {"r": f"send_failed: {e}", "u": _now_kst_iso(), "id": order_id})
        db.commit()
        return {"ok": False, "reason": f"send_failed: {e}"}

    # res 파싱(기존 okx 래퍼가 dict 반환한다고 가정)
    okx_order_id = None
    try:
        data = res.get("data") if isinstance(res, dict) else None
        if isinstance(data, list) and data:
            okx_order_id = data[0].get("ordId")
    except Exception:
        okx_order_id = None

    db.execute(_sql_text("""
        UPDATE orders
        SET status='sent', reason=NULL, okx_order_id=:oid, updated_at=:u
        WHERE id=:id
    """), {"oid": okx_order_id, "u": _now_kst_iso(), "id": order_id})
    db.commit()
    return {"ok": True, "okx_order_id": okx_order_id}
# === /AUTOFIX_COMPAT_TV_HELPERS ===
'''

TARGET.write_text(text + marker + compat, encoding="utf-8")
print("Patched. Added compat block. Missing defs were:", ", ".join(missing))

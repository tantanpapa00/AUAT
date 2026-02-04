-- BBooster Database Schema Initialization
-- Week 19: Docker化
-- Run: psql -U bbooster -d bbooster -f scripts/init_schema.sql

-- System Flags
CREATE TABLE IF NOT EXISTS system_flags (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL,
    reason TEXT NULL,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Accounts
CREATE TABLE IF NOT EXISTS accounts (
    id BIGSERIAL PRIMARY KEY,
    name TEXT NOT NULL UNIQUE,
    exchange TEXT NOT NULL,
    api_key TEXT NOT NULL,
    api_secret TEXT NOT NULL,
    api_passphrase TEXT,
    is_active BOOLEAN NOT NULL DEFAULT false,
    last_health_at TIMESTAMPTZ,
    last_health_ok BOOLEAN,
    last_health_msg TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Strategies
CREATE TABLE IF NOT EXISTS strategies (
    id BIGSERIAL PRIMARY KEY,
    name TEXT NOT NULL UNIQUE,
    tv_secret TEXT NOT NULL,
    is_active BOOLEAN NOT NULL DEFAULT true,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Assets
CREATE TABLE IF NOT EXISTS assets (
    id BIGSERIAL PRIMARY KEY,
    account_id INTEGER REFERENCES accounts(id),
    strategy_id INTEGER REFERENCES strategies(id),
    symbol TEXT NOT NULL,
    market TEXT DEFAULT 'spot',
    is_active BOOLEAN NOT NULL DEFAULT true,
    soft_deleted INTEGER DEFAULT 0,
    cooldown_sec INTEGER DEFAULT 60,
    max_orders_per_day INTEGER DEFAULT 10,
    last_signal_at TIMESTAMPTZ,
    last_signal_id TEXT,
    last_order_at TIMESTAMPTZ,
    last_order_status TEXT,
    last_order_reason TEXT,
    last_order_id BIGINT,
    last_okx_order_id TEXT,
    last_filled_qty NUMERIC,
    last_order_avg_px NUMERIC,
    last_checked_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Orders
CREATE TABLE IF NOT EXISTS orders (
    id BIGSERIAL PRIMARY KEY,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    account_id INTEGER,
    strategy_id INTEGER,
    config_id INTEGER,
    config_hash TEXT,
    asset_id INTEGER,
    alert_id TEXT,
    symbol TEXT,
    market TEXT,
    side TEXT,
    qty DOUBLE PRECISION,
    order_type TEXT DEFAULT 'market',
    idem_key TEXT,
    dedup_key TEXT DEFAULT '',
    payload_json TEXT,
    status TEXT,
    reason TEXT,
    okx_order_id TEXT,
    okx_clord_id TEXT,
    filled_qty DOUBLE PRECISION,
    avg_px DOUBLE PRECISION,
    okx_state TEXT,
    last_checked_at TIMESTAMPTZ,
    submit_status TEXT,
    exch_status TEXT,
    submit_err TEXT,
    exch_err TEXT,
    next_check_at TIMESTAMPTZ,
    check_count INTEGER DEFAULT 0,
    submit_try_count INTEGER DEFAULT 0,
    next_submit_at TIMESTAMPTZ,
    reason_code TEXT,
    reason_text TEXT,
    snapshot_id TEXT,
    exchange_order_id TEXT
);

-- Events (Timeline)
CREATE TABLE IF NOT EXISTS events (
    id BIGSERIAL PRIMARY KEY,
    event_type TEXT NOT NULL,
    asset_id BIGINT,
    order_id BIGINT,
    account_id BIGINT,
    summary TEXT NOT NULL,
    detail JSONB,
    reason_code TEXT,
    reason_text TEXT,
    snapshot_id TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- TV Events
CREATE TABLE IF NOT EXISTS tv_events (
    id BIGSERIAL PRIMARY KEY,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    payload_json TEXT,
    result_json TEXT,
    status TEXT,
    alert_id TEXT,
    exchange TEXT,
    symbol TEXT,
    side TEXT
);

-- ShortMsgs
CREATE TABLE IF NOT EXISTS shortmsgs (
    id BIGSERIAL PRIMARY KEY,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    raw_text TEXT,
    parsed_json TEXT,
    status TEXT,
    error_msg TEXT
);

-- Signal Events (Premium)
CREATE TABLE IF NOT EXISTS signal_events (
    id BIGSERIAL PRIMARY KEY,
    asset_id BIGINT,
    symbol TEXT,
    exchange TEXT,
    market TEXT DEFAULT 'spot',
    side TEXT,
    premium_mode TEXT,
    params_version TEXT,
    reason_code TEXT,
    reason_text TEXT,
    snapshot_id TEXT,
    tf TEXT,
    price_hint DOUBLE PRECISION,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Signal Snapshots (Premium)
CREATE TABLE IF NOT EXISTS signal_snapshots (
    id TEXT PRIMARY KEY,
    signal_id BIGINT,
    ohlcv JSONB,
    indicators JSONB,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Indexes
CREATE INDEX IF NOT EXISTS idx_orders_status ON orders(status);
CREATE INDEX IF NOT EXISTS idx_orders_asset_id ON orders(asset_id);
CREATE INDEX IF NOT EXISTS idx_events_asset_id ON events(asset_id);
CREATE INDEX IF NOT EXISTS idx_events_order_id ON events(order_id);
CREATE INDEX IF NOT EXISTS idx_events_created_at ON events(created_at);

-- Initial E-STOP flag (disabled by default)
INSERT INTO system_flags (key, value, reason) VALUES ('E_STOP', '0', 'Initial setup')
ON CONFLICT (key) DO NOTHING;

-- Confirmation
SELECT 'Schema initialization complete' AS status;

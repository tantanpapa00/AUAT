-- scripts/migrate_premium_tables.sql
-- Premium Engine DB Migration
-- Phase 2: premium_configs, strategy_states, candles, signal_events, signal_snapshots

-- =============================================================================
-- 1. premium_configs - 프리미엄 엔진 설정 저장
-- =============================================================================
CREATE TABLE IF NOT EXISTS premium_configs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    asset_id INTEGER NOT NULL,

    -- Timeframes
    signal_tf TEXT NOT NULL DEFAULT '15m',      -- Signal timeframe
    htf_tf TEXT NOT NULL DEFAULT '4h',          -- Higher timeframe

    -- Oscillator preset
    osc_preset TEXT NOT NULL DEFAULT 'preset1', -- preset1, preset2, etc.

    -- Buy settings
    buy_enabled INTEGER NOT NULL DEFAULT 1,
    buy_tranches TEXT NOT NULL DEFAULT '[25,50,75,100]',  -- JSON array
    buy_after_max TEXT NOT NULL DEFAULT 'extend',  -- extend, cycle, stop
    buy_stage_1_only INTEGER NOT NULL DEFAULT 0,

    -- Sell settings
    sell_enabled INTEGER NOT NULL DEFAULT 1,
    sell_tranches TEXT NOT NULL DEFAULT '[50,100]',  -- JSON array
    sell_after_max TEXT NOT NULL DEFAULT 'extend',
    sell_stage_1_only INTEGER NOT NULL DEFAULT 0,

    -- Filters
    use_lower_band_filter INTEGER NOT NULL DEFAULT 1,
    use_below_avg_filter INTEGER NOT NULL DEFAULT 1,
    use_prev_signal_filter INTEGER NOT NULL DEFAULT 1,
    use_prev_exec_filter INTEGER NOT NULL DEFAULT 1,

    -- Position sizing
    cash_use_pct REAL NOT NULL DEFAULT 90.0,
    hard_cap_pct REAL NOT NULL DEFAULT 95.0,
    min_profit_pct REAL NOT NULL DEFAULT 0.5,

    -- Regime settings
    use_4regime INTEGER NOT NULL DEFAULT 1,
    r1_pullback_enabled INTEGER NOT NULL DEFAULT 1,
    r3_breakout_enabled INTEGER NOT NULL DEFAULT 1,

    -- Misc
    one_trade_per_bar INTEGER NOT NULL DEFAULT 1,

    -- Timestamps
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now')),

    UNIQUE(asset_id)
);

-- Index for asset lookup
CREATE INDEX IF NOT EXISTS idx_premium_configs_asset_id ON premium_configs(asset_id);


-- =============================================================================
-- 2. strategy_states - 전략 상태 추적
-- =============================================================================
CREATE TABLE IF NOT EXISTS strategy_states (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    asset_id INTEGER NOT NULL,

    -- Signal stages (0-indexed)
    buy_stage INTEGER NOT NULL DEFAULT 0,
    sell_stage INTEGER NOT NULL DEFAULT 0,

    -- Last signal/execution prices
    last_buy_signal_price REAL,
    last_sell_signal_price REAL,
    last_buy_exec_price REAL,
    last_sell_exec_price REAL,

    -- Timestamps (milliseconds)
    last_buy_time INTEGER,
    last_sell_time INTEGER,
    last_signal_ts INTEGER,

    -- R1 specific
    r1_pullback_active INTEGER NOT NULL DEFAULT 0,
    r1_pullback_entry_price REAL,

    -- R3 specific
    r3_breakout_active INTEGER NOT NULL DEFAULT 0,
    r3_breakout_entry_price REAL,

    -- Timestamps
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now')),

    UNIQUE(asset_id)
);

CREATE INDEX IF NOT EXISTS idx_strategy_states_asset_id ON strategy_states(asset_id);


-- =============================================================================
-- 3. candles - 캔들 데이터 캐시
-- =============================================================================
CREATE TABLE IF NOT EXISTS candles (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    exchange TEXT NOT NULL,
    symbol TEXT NOT NULL,
    timeframe TEXT NOT NULL,

    -- OHLCV
    ts INTEGER NOT NULL,        -- Candle timestamp (milliseconds)
    open REAL NOT NULL,
    high REAL NOT NULL,
    low REAL NOT NULL,
    close REAL NOT NULL,
    volume REAL NOT NULL,

    -- Metadata
    fetched_at TEXT NOT NULL DEFAULT (datetime('now')),

    UNIQUE(exchange, symbol, timeframe, ts)
);

-- Composite index for efficient lookups
CREATE INDEX IF NOT EXISTS idx_candles_lookup
ON candles(exchange, symbol, timeframe, ts DESC);

-- Index for cleanup
CREATE INDEX IF NOT EXISTS idx_candles_fetched_at ON candles(fetched_at);


-- =============================================================================
-- 4. signal_events - 시그널 이벤트 기록
-- =============================================================================
CREATE TABLE IF NOT EXISTS signal_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    signal_id TEXT NOT NULL UNIQUE,
    asset_id INTEGER NOT NULL,
    symbol TEXT NOT NULL,
    exchange TEXT NOT NULL,
    market TEXT NOT NULL DEFAULT 'spot',

    -- Signal info
    side TEXT NOT NULL,             -- 'entry' or 'exit'
    action TEXT NOT NULL,           -- 'buy' or 'sell'
    premium_mode TEXT NOT NULL,     -- 'mr' for mean reversion
    params_version TEXT NOT NULL,

    -- Reason
    reason_code TEXT NOT NULL,
    reason_text TEXT NOT NULL,
    snapshot_id TEXT NOT NULL,

    -- Timeframe
    tf TEXT NOT NULL,
    tf_warning INTEGER NOT NULL DEFAULT 0,
    price_hint REAL,

    -- Tranche info
    tranche INTEGER,
    tranche_pct REAL,
    regime INTEGER,

    -- Timestamps
    ts INTEGER NOT NULL,            -- Signal timestamp (milliseconds)
    created_at TEXT NOT NULL DEFAULT (datetime('now')),

    -- Processing status
    processed INTEGER NOT NULL DEFAULT 0,
    processed_at TEXT,
    order_id TEXT
);

CREATE INDEX IF NOT EXISTS idx_signal_events_asset_id ON signal_events(asset_id);
CREATE INDEX IF NOT EXISTS idx_signal_events_ts ON signal_events(ts DESC);
CREATE INDEX IF NOT EXISTS idx_signal_events_processed ON signal_events(processed);


-- =============================================================================
-- 5. signal_snapshots - 시그널 스냅샷 (감사 추적)
-- =============================================================================
CREATE TABLE IF NOT EXISTS signal_snapshots (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    snapshot_id TEXT NOT NULL UNIQUE,
    signal_id TEXT NOT NULL,
    asset_id INTEGER NOT NULL,
    symbol TEXT NOT NULL,
    exchange TEXT NOT NULL,

    -- Candle info
    ts INTEGER NOT NULL,
    tf TEXT NOT NULL,
    ohlcv TEXT NOT NULL,            -- JSON: {o, h, l, c, v}

    -- Indicators
    indicators TEXT NOT NULL,       -- JSON: indicator values at signal time

    -- Signal info
    premium_mode TEXT NOT NULL,
    params_version TEXT NOT NULL,
    reason_code TEXT NOT NULL,
    reason_text TEXT NOT NULL,

    -- Timestamps
    created_at TEXT NOT NULL DEFAULT (datetime('now')),

    FOREIGN KEY (signal_id) REFERENCES signal_events(signal_id)
);

CREATE INDEX IF NOT EXISTS idx_signal_snapshots_signal_id ON signal_snapshots(signal_id);
CREATE INDEX IF NOT EXISTS idx_signal_snapshots_asset_id ON signal_snapshots(asset_id);


-- =============================================================================
-- 6. Cleanup: Old candles (keep last 7 days)
-- =============================================================================
-- Run periodically to clean old candle data
-- DELETE FROM candles WHERE fetched_at < datetime('now', '-7 days');


-- =============================================================================
-- Migration complete
-- =============================================================================

-- Migration: Day14 - Portfolio Snapshots + Trade History
-- For existing databases that need portfolio tracking support
-- Run: psql -U bbooster -d bbooster -f scripts/migrate_day14.sql

-- Portfolio Snapshots (일별 자산 스냅샷)
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.tables
        WHERE table_name = 'portfolio_snapshots'
    ) THEN
        CREATE TABLE portfolio_snapshots (
            id BIGSERIAL PRIMARY KEY,
            user_id BIGINT REFERENCES users(id),
            total_asset_krw NUMERIC DEFAULT 0,
            total_krw NUMERIC DEFAULT 0,
            total_usd NUMERIC DEFAULT 0,
            usd_krw_rate NUMERIC DEFAULT 0,
            snapshot_date DATE NOT NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            UNIQUE(user_id, snapshot_date)
        );
        CREATE INDEX idx_portfolio_snapshots_user_date ON portfolio_snapshots(user_id, snapshot_date);
        RAISE NOTICE 'Table portfolio_snapshots created';
    ELSE
        RAISE NOTICE 'Table portfolio_snapshots already exists';
    END IF;
END $$;

-- Trade History (매매 내역)
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.tables
        WHERE table_name = 'trade_history'
    ) THEN
        CREATE TABLE trade_history (
            id BIGSERIAL PRIMARY KEY,
            user_id BIGINT REFERENCES users(id),
            account_id BIGINT REFERENCES accounts(id),
            exchange TEXT NOT NULL,
            symbol TEXT NOT NULL,
            side TEXT NOT NULL,
            quantity NUMERIC NOT NULL,
            price NUMERIC NOT NULL,
            total_amount NUMERIC NOT NULL,
            currency TEXT DEFAULT 'KRW',
            fee NUMERIC DEFAULT 0,
            order_id TEXT,
            strategy_name TEXT,
            executed_at TIMESTAMPTZ NOT NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now()
        );
        CREATE INDEX idx_trade_history_user ON trade_history(user_id);
        CREATE INDEX idx_trade_history_executed ON trade_history(executed_at);
        RAISE NOTICE 'Table trade_history created';
    ELSE
        RAISE NOTICE 'Table trade_history already exists';
    END IF;
END $$;

-- Verification
SELECT table_name FROM information_schema.tables
WHERE table_name IN ('portfolio_snapshots', 'trade_history');

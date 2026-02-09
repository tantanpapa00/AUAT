-- scripts/migrate_trend_tables.sql
-- 추세매매(Trend) 프리미엄 엔진 DB 마이그레이션
-- 실행: psql -U postgres -d bbooster -f scripts/migrate_trend_tables.sql

-- ============================================================
-- 1. premium_configs 테이블에 추세매매 전용 컬럼 추가
-- ============================================================

-- strategy_type 컬럼 (mr/trend 구분)
ALTER TABLE premium_configs ADD COLUMN IF NOT EXISTS strategy_type VARCHAR(20) DEFAULT 'mr';

-- 타임프레임 분리 (핵심!)
ALTER TABLE premium_configs ADD COLUMN IF NOT EXISTS trend_entry_tf VARCHAR(10) DEFAULT '1D';
ALTER TABLE premium_configs ADD COLUMN IF NOT EXISTS trend_exit_tf VARCHAR(10) DEFAULT '1D';
ALTER TABLE premium_configs ADD COLUMN IF NOT EXISTS trend_htf_tf VARCHAR(10) DEFAULT '1W';

-- Entry 지표 (entry_tf 기준)
ALTER TABLE premium_configs ADD COLUMN IF NOT EXISTS trend_st_atr_len INTEGER DEFAULT 10;
ALTER TABLE premium_configs ADD COLUMN IF NOT EXISTS trend_st_factor FLOAT DEFAULT 3.0;
ALTER TABLE premium_configs ADD COLUMN IF NOT EXISTS trend_hvi_length INTEGER DEFAULT 200;
ALTER TABLE premium_configs ADD COLUMN IF NOT EXISTS trend_hvi_divisor FLOAT DEFAULT 3.6;
ALTER TABLE premium_configs ADD COLUMN IF NOT EXISTS trend_qqe_rsi_length INTEGER DEFAULT 6;
ALTER TABLE premium_configs ADD COLUMN IF NOT EXISTS trend_qqe_rsi_smoothing INTEGER DEFAULT 5;
ALTER TABLE premium_configs ADD COLUMN IF NOT EXISTS trend_qqe_factor FLOAT DEFAULT 3.0;
ALTER TABLE premium_configs ADD COLUMN IF NOT EXISTS trend_htf_vwma_len INTEGER DEFAULT 156;

-- Exit 지표 (exit_tf 기준)
ALTER TABLE premium_configs ADD COLUMN IF NOT EXISTS trend_exit_st_atr_len INTEGER DEFAULT 10;
ALTER TABLE premium_configs ADD COLUMN IF NOT EXISTS trend_exit_st_factor FLOAT DEFAULT 3.0;
ALTER TABLE premium_configs ADD COLUMN IF NOT EXISTS trend_exit_spo_smooth_len INTEGER DEFAULT 4;
ALTER TABLE premium_configs ADD COLUMN IF NOT EXISTS trend_exit_spo_threshold FLOAT DEFAULT 1.0;
ALTER TABLE premium_configs ADD COLUMN IF NOT EXISTS trend_exit_spo_std_len INTEGER DEFAULT 50;
ALTER TABLE premium_configs ADD COLUMN IF NOT EXISTS trend_exit_spo_hma_len INTEGER DEFAULT 30;

-- Exit 조건
ALTER TABLE premium_configs ADD COLUMN IF NOT EXISTS trend_hard_sl_pct FLOAT DEFAULT 7.0;
ALTER TABLE premium_configs ADD COLUMN IF NOT EXISTS trend_tp1_pct FLOAT DEFAULT 21.0;
ALTER TABLE premium_configs ADD COLUMN IF NOT EXISTS trend_tp1_sell_pct FLOAT DEFAULT 50.0;
ALTER TABLE premium_configs ADD COLUMN IF NOT EXISTS trend_use_spo_split BOOLEAN DEFAULT true;
ALTER TABLE premium_configs ADD COLUMN IF NOT EXISTS trend_use_st_flip_exit BOOLEAN DEFAULT true;

-- 분할매도 설정
ALTER TABLE premium_configs ADD COLUMN IF NOT EXISTS trend_sell_tranches JSONB DEFAULT '[10.0, 20.0, 30.0, 5.0, 2.5, 1.0]';
ALTER TABLE premium_configs ADD COLUMN IF NOT EXISTS trend_max_sell_tranches INTEGER DEFAULT 6;
ALTER TABLE premium_configs ADD COLUMN IF NOT EXISTS trend_after_max_sell VARCHAR(10) DEFAULT 'cycle';

-- 익절 게이트
ALTER TABLE premium_configs ADD COLUMN IF NOT EXISTS trend_use_profit_gate BOOLEAN DEFAULT true;
ALTER TABLE premium_configs ADD COLUMN IF NOT EXISTS trend_min_profit_pct FLOAT DEFAULT 0.10;
ALTER TABLE premium_configs ADD COLUMN IF NOT EXISTS trend_fee_buffer_pct FLOAT DEFAULT 0.20;

-- ============================================================
-- 2. strategy_states 테이블에 추세매매 상태 컬럼 추가
-- ============================================================

ALTER TABLE strategy_states ADD COLUMN IF NOT EXISTS trend_in_position BOOLEAN DEFAULT false;
ALTER TABLE strategy_states ADD COLUMN IF NOT EXISTS trend_entry_price FLOAT;
ALTER TABLE strategy_states ADD COLUMN IF NOT EXISTS trend_entry_ts BIGINT;
ALTER TABLE strategy_states ADD COLUMN IF NOT EXISTS trend_position_qty FLOAT DEFAULT 0;
ALTER TABLE strategy_states ADD COLUMN IF NOT EXISTS trend_highest_since_entry FLOAT;
ALTER TABLE strategy_states ADD COLUMN IF NOT EXISTS trend_tp1_triggered BOOLEAN DEFAULT false;
ALTER TABLE strategy_states ADD COLUMN IF NOT EXISTS trend_sell_stage INTEGER DEFAULT 0;
ALTER TABLE strategy_states ADD COLUMN IF NOT EXISTS trend_last_st_dir INTEGER DEFAULT 0;

-- ============================================================
-- 3. 인덱스 추가
-- ============================================================

CREATE INDEX IF NOT EXISTS idx_premium_configs_strategy_type ON premium_configs(strategy_type);

-- ============================================================
-- 4. 코멘트 추가
-- ============================================================

COMMENT ON COLUMN premium_configs.strategy_type IS '전략 타입: mr(역추세매매), trend(추세매매)';
COMMENT ON COLUMN premium_configs.trend_entry_tf IS '매수 판단 타임프레임 (15m/30m/1h/4h/1D/1W)';
COMMENT ON COLUMN premium_configs.trend_exit_tf IS '매도 판단 타임프레임 (15m/30m/1h/4h/1D/1W)';
COMMENT ON COLUMN premium_configs.trend_htf_tf IS 'HTF VWMA 기준 타임프레임 (보통 주봉)';

COMMENT ON COLUMN strategy_states.trend_in_position IS '추세매매 포지션 보유 여부';
COMMENT ON COLUMN strategy_states.trend_tp1_triggered IS 'TP1 발동 여부 (중복 방지)';
COMMENT ON COLUMN strategy_states.trend_sell_stage IS 'SPO 분할매도 차수 (0=SELL1, 1=SELL2, ...)';

-- ============================================================
-- 완료 메시지
-- ============================================================

DO $$
BEGIN
    RAISE NOTICE '추세매매(Trend) 테이블 마이그레이션 완료';
END $$;

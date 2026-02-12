-- scripts/migrate_trend_tables.sql
-- 추세매매(Trend) 프리미엄 엔진 DB 마이그레이션
-- 실행: psql -U postgres -d bbooster -f scripts/migrate_trend_tables.sql

-- ============================================================
-- 1. premium_configs 테이블에 추세매매 전용 컬럼 추가
-- ============================================================

-- strategy_type 컬럼 (mr/trend 구분)
ALTER TABLE premium_configs ADD COLUMN IF NOT EXISTS strategy_type VARCHAR(20) DEFAULT 'mr';

-- 타임프레임 (v8 최종: 2개로 단순화)
ALTER TABLE premium_configs ADD COLUMN IF NOT EXISTS trend_signal_tf VARCHAR(10) DEFAULT '1D';
ALTER TABLE premium_configs ADD COLUMN IF NOT EXISTS trend_exit_tf VARCHAR(10) DEFAULT '1W';

-- Supertrend (작가님 확정: 20/5.0)
ALTER TABLE premium_configs ADD COLUMN IF NOT EXISTS trend_st_atr_len INTEGER DEFAULT 20;
ALTER TABLE premium_configs ADD COLUMN IF NOT EXISTS trend_st_factor FLOAT DEFAULT 5.0;
ALTER TABLE premium_configs ADD COLUMN IF NOT EXISTS trend_hvi_length INTEGER DEFAULT 200;
ALTER TABLE premium_configs ADD COLUMN IF NOT EXISTS trend_hvi_divisor FLOAT DEFAULT 3.6;
ALTER TABLE premium_configs ADD COLUMN IF NOT EXISTS trend_qqe_rsi_length INTEGER DEFAULT 6;
ALTER TABLE premium_configs ADD COLUMN IF NOT EXISTS trend_qqe_rsi_smoothing INTEGER DEFAULT 5;
ALTER TABLE premium_configs ADD COLUMN IF NOT EXISTS trend_qqe_factor FLOAT DEFAULT 3.0;
ALTER TABLE premium_configs ADD COLUMN IF NOT EXISTS trend_htf_vwma_len INTEGER DEFAULT 156;

-- SPO 지표 (signal_tf 기준 분할매도용)
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

-- 분할매도 설정 (v8: 역피라미드 [5,5,10,15,25,40])
ALTER TABLE premium_configs ADD COLUMN IF NOT EXISTS trend_sell_tranches JSONB DEFAULT '[5.0, 5.0, 10.0, 15.0, 25.0, 40.0]';
ALTER TABLE premium_configs ADD COLUMN IF NOT EXISTS trend_max_sell_tranches INTEGER DEFAULT 6;
ALTER TABLE premium_configs ADD COLUMN IF NOT EXISTS trend_after_max_sell VARCHAR(10) DEFAULT 'cycle';

-- 익절 게이트
ALTER TABLE premium_configs ADD COLUMN IF NOT EXISTS trend_use_profit_gate BOOLEAN DEFAULT true;
ALTER TABLE premium_configs ADD COLUMN IF NOT EXISTS trend_min_profit_pct FLOAT DEFAULT 0.10;
ALTER TABLE premium_configs ADD COLUMN IF NOT EXISTS trend_fee_buffer_pct FLOAT DEFAULT 0.20;

-- ============================================================
-- v8 신규 컬럼 (피라미딩, ATR 손절, ST Exit Mode)
-- ============================================================

-- 피라미딩 (추가매수)
ALTER TABLE premium_configs ADD COLUMN IF NOT EXISTS trend_use_pyramiding BOOLEAN DEFAULT true;
ALTER TABLE premium_configs ADD COLUMN IF NOT EXISTS trend_max_pyr_entries INTEGER DEFAULT 4;
ALTER TABLE premium_configs ADD COLUMN IF NOT EXISTS trend_pyr_high_len INTEGER DEFAULT 60;
ALTER TABLE premium_configs ADD COLUMN IF NOT EXISTS trend_pyr_cooldown INTEGER DEFAULT 5;
ALTER TABLE premium_configs ADD COLUMN IF NOT EXISTS trend_pyr_refill_after_sell BOOLEAN DEFAULT false;
ALTER TABLE premium_configs ADD COLUMN IF NOT EXISTS trend_pyr_weights JSONB DEFAULT '[40.0, 30.0, 20.0, 10.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0]';

-- 손절 타입 (v8: ATR 기반 손절 지원)
ALTER TABLE premium_configs ADD COLUMN IF NOT EXISTS trend_stop_type VARCHAR(10) DEFAULT 'fixed';
ALTER TABLE premium_configs ADD COLUMN IF NOT EXISTS trend_atr_stop_len INTEGER DEFAULT 14;
ALTER TABLE premium_configs ADD COLUMN IF NOT EXISTS trend_atr_stop_mult FLOAT DEFAULT 2.0;

-- ST 전량매도 (exit_tf의 ST 사용)
ALTER TABLE premium_configs ADD COLUMN IF NOT EXISTS trend_use_st_exit BOOLEAN DEFAULT true;

-- v8 토글
ALTER TABLE premium_configs ADD COLUMN IF NOT EXISTS trend_use_tp1 BOOLEAN DEFAULT false;
ALTER TABLE premium_configs ADD COLUMN IF NOT EXISTS trend_st_invert BOOLEAN DEFAULT false;
ALTER TABLE premium_configs ADD COLUMN IF NOT EXISTS trend_use_htf_filter BOOLEAN DEFAULT true;

-- Entry Guard (v8)
ALTER TABLE premium_configs ADD COLUMN IF NOT EXISTS trend_enter_only_on_setup_start BOOLEAN DEFAULT true;
ALTER TABLE premium_configs ADD COLUMN IF NOT EXISTS trend_use_live_guard BOOLEAN DEFAULT false;

-- 수량 반올림 (주식용)
ALTER TABLE premium_configs ADD COLUMN IF NOT EXISTS trend_round_qty BOOLEAN DEFAULT true;
ALTER TABLE premium_configs ADD COLUMN IF NOT EXISTS trend_min_qty FLOAT DEFAULT 1.0;

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

-- v8 피라미딩 상태
ALTER TABLE strategy_states ADD COLUMN IF NOT EXISTS trend_pyr_count INTEGER DEFAULT 0;
ALTER TABLE strategy_states ADD COLUMN IF NOT EXISTS trend_last_pyr_bar INTEGER DEFAULT -999;
ALTER TABLE strategy_states ADD COLUMN IF NOT EXISTS trend_pyr_highest FLOAT DEFAULT 0;
ALTER TABLE strategy_states ADD COLUMN IF NOT EXISTS trend_avg_entry_price FLOAT DEFAULT 0;
ALTER TABLE strategy_states ADD COLUMN IF NOT EXISTS trend_total_cost FLOAT DEFAULT 0;
ALTER TABLE strategy_states ADD COLUMN IF NOT EXISTS trend_setup_start_bar INTEGER DEFAULT -999;
ALTER TABLE strategy_states ADD COLUMN IF NOT EXISTS trend_prev_setup_met BOOLEAN DEFAULT false;

-- ============================================================
-- 3. 인덱스 추가
-- ============================================================

CREATE INDEX IF NOT EXISTS idx_premium_configs_strategy_type ON premium_configs(strategy_type);

-- ============================================================
-- 4. 코멘트 추가
-- ============================================================

COMMENT ON COLUMN premium_configs.strategy_type IS '전략 타입: mr(역추세매매), trend(추세매매)';
COMMENT ON COLUMN premium_configs.trend_signal_tf IS '기준 TF (매수 + SPO + SL + TP1)';
COMMENT ON COLUMN premium_configs.trend_exit_tf IS '매도기준 TF (ST 전량매도 + HTF VWMA 필터)';

COMMENT ON COLUMN strategy_states.trend_in_position IS '추세매매 포지션 보유 여부';
COMMENT ON COLUMN strategy_states.trend_tp1_triggered IS 'TP1 발동 여부 (중복 방지)';
COMMENT ON COLUMN strategy_states.trend_sell_stage IS 'SPO 분할매도 차수 (0=SELL1, 1=SELL2, ...)';

-- v8 코멘트
COMMENT ON COLUMN premium_configs.trend_use_pyramiding IS 'v8: 피라미딩(추가매수) 사용 여부';
COMMENT ON COLUMN premium_configs.trend_max_pyr_entries IS 'v8: 최대 피라미딩 횟수';
COMMENT ON COLUMN premium_configs.trend_pyr_high_len IS 'v8: N-bar 최고가 기준 봉수';
COMMENT ON COLUMN premium_configs.trend_pyr_cooldown IS 'v8: 피라미딩 쿨다운 봉수';
COMMENT ON COLUMN premium_configs.trend_stop_type IS 'v8: 손절 타입 (fixed/atr)';
COMMENT ON COLUMN premium_configs.trend_use_st_exit IS 'v8: ST 전량매도 사용 여부';
COMMENT ON COLUMN premium_configs.trend_use_tp1 IS 'v8: TP1 사용 여부 (기본 OFF)';
COMMENT ON COLUMN strategy_states.trend_pyr_count IS 'v8: 피라미딩 차수 (0=1차, 1=2차...)';
COMMENT ON COLUMN strategy_states.trend_avg_entry_price IS 'v8: 평균 진입가 (피라미딩 포함)';

-- ============================================================
-- 완료 메시지
-- ============================================================

DO $$
BEGIN
    RAISE NOTICE '추세매매(Trend) v8 테이블 마이그레이션 완료';
END $$;

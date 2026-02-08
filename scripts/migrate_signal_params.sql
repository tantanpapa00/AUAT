-- BBooster Signal Params Migration
-- 전략설정 (Sizing/Risk/Limits) 지원을 위한 마이그레이션
-- Run: psql -U bbooster -d bbooster -f scripts/migrate_signal_params.sql

-- 1. strategies 테이블에 signal_params 컬럼 추가
ALTER TABLE strategies
ADD COLUMN IF NOT EXISTS signal_params JSONB DEFAULT NULL;

COMMENT ON COLUMN strategies.signal_params IS '전략 레벨 매매규칙 (sizing/risk/limits/meta)';

-- 2. assets 테이블에 signal_params_override 컬럼 추가
ALTER TABLE assets
ADD COLUMN IF NOT EXISTS signal_params_override JSONB DEFAULT NULL;

COMMENT ON COLUMN assets.signal_params_override IS '종목별 매매규칙 오버라이드. NULL이면 전략 기본값 사용. 변경할 부분만 넣음.';

-- 3. signal_params가 NULL인 전략에 기본값 세팅
UPDATE strategies
SET signal_params = '{
  "sizing": {
    "mode": "balance_pct",
    "value": 30,
    "base": "free",
    "max_notional_per_order": 0,
    "min_notional_per_order": 0,
    "reduce": {
      "default_pct": 0,
      "sequence_pct": []
    }
  },
  "risk": {
    "exec_mode": "tv_exit_signal",
    "leverage_policy": "fixed",
    "leverage_value": 1,
    "sl": {
      "enabled": false,
      "type": "pct",
      "value": 0,
      "basis": "entry",
      "order_type": "market"
    },
    "tp": {
      "enabled": false,
      "type": "pct",
      "value": 0,
      "basis": "entry",
      "order_type": "market"
    },
    "trailing": {
      "enabled": false,
      "type": "pct",
      "value": 0
    },
    "reduce_only": true
  },
  "limits": {
    "idempotency": {
      "enabled": true,
      "key": "alert_id"
    },
    "cooldown_seconds": 0,
    "one_trade_per_bar": false,
    "daily_max_trades": 0,
    "daily_max_notional": 0,
    "max_open_positions": 0,
    "allow_same_side_add": true
  },
  "meta": {
    "version": 1,
    "notes": ""
  }
}'::jsonb
WHERE signal_params IS NULL;

-- Confirmation
SELECT 'Signal params migration complete' AS status;

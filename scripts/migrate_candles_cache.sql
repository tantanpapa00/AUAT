-- 캔들 캐시 테이블 (백테스트용)
-- 거래소에서 조회한 캔들을 캐시하여 재요청 시 빠르게 반환

CREATE TABLE IF NOT EXISTS candles (
    id BIGSERIAL PRIMARY KEY,
    exchange TEXT NOT NULL,
    symbol TEXT NOT NULL,
    timeframe TEXT NOT NULL,
    ts BIGINT NOT NULL,
    o DOUBLE PRECISION NOT NULL,
    h DOUBLE PRECISION NOT NULL,
    l DOUBLE PRECISION NOT NULL,
    c DOUBLE PRECISION NOT NULL,
    v DOUBLE PRECISION NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW() NOT NULL,
    UNIQUE (exchange, symbol, timeframe, ts)
);

-- 조회 성능을 위한 인덱스
CREATE INDEX IF NOT EXISTS ix_candles_lookup
ON candles (exchange, symbol, timeframe, ts);

-- 오래된 캐시 정리를 위한 인덱스
CREATE INDEX IF NOT EXISTS ix_candles_created_at
ON candles (created_at);

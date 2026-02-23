-- 해외 종목 기업개요 번역 캐시 테이블
-- yfinance 영문 → Claude 한글 번역, 90일마다 갱신

CREATE TABLE IF NOT EXISTS company_summary_translations (
    id BIGSERIAL PRIMARY KEY,
    ticker VARCHAR(20) NOT NULL UNIQUE,
    description_en TEXT,
    description_ko TEXT,
    sector VARCHAR(100),
    industry VARCHAR(100),
    headquarters VARCHAR(200),
    employees BIGINT,
    website VARCHAR(300),
    translated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW() NOT NULL,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW() NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_translations_ticker ON company_summary_translations(ticker);

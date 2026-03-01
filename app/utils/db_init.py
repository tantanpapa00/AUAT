# app/utils/db_init.py
# DB 테이블 초기화 helper 함수

from sqlalchemy.orm import Session
from sqlalchemy import text

# AI 테이블 초기화 플래그 (서버 시작 시 1회만 실행)
_ai_tables_initialized = False


def ensure_ai_tables(db: Session):
    """AI/관심종목 테이블 생성 — 서버 시작 시 1회만 실행"""
    global _ai_tables_initialized
    if _ai_tables_initialized:
        return  # 이미 초기화됨

    print("[DB] AI 테이블 초기화 시작...")
    sqls = [
        """
        DO $$ BEGIN
            ALTER TABLE users ADD COLUMN IF NOT EXISTS ai_usage_count INTEGER DEFAULT 0;
            ALTER TABLE users ADD COLUMN IF NOT EXISTS ai_usage_date DATE;
            ALTER TABLE users ADD COLUMN IF NOT EXISTS ai_monthly_count INTEGER DEFAULT 0;
            ALTER TABLE users ADD COLUMN IF NOT EXISTS ai_monthly_date VARCHAR(7);
        EXCEPTION WHEN others THEN NULL;
        END $$;
        """,
        """
        CREATE TABLE IF NOT EXISTS ai_reports (
            id SERIAL PRIMARY KEY,
            symbol VARCHAR(50),
            exchange VARCHAR(50),
            report_text TEXT,
            data_snapshot JSONB,
            created_at TIMESTAMP DEFAULT NOW(),
            expires_at TIMESTAMP
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS market_timeline (
            id SERIAL PRIMARY KEY,
            created_at TIMESTAMP DEFAULT NOW(),
            market_status VARCHAR(20),
            kospi_change DECIMAL(5,2),
            kosdaq_change DECIMAL(5,2),
            summary TEXT,
            leading_sectors JSONB,
            lagging_sectors JSONB,
            featured_stocks JSONB,
            keywords JSONB
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS watchlist_groups (
            id SERIAL PRIMARY KEY,
            user_id INTEGER REFERENCES users(id),
            name VARCHAR(100),
            sort_order INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT NOW()
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS watchlist_items (
            id SERIAL PRIMARY KEY,
            group_id INTEGER REFERENCES watchlist_groups(id) ON DELETE CASCADE,
            user_id INTEGER REFERENCES users(id),
            symbol VARCHAR(50),
            exchange VARCHAR(50),
            added_at TIMESTAMP DEFAULT NOW()
        )
        """
    ]
    for sql in sqls:
        try:
            db.execute(text(sql))
            db.commit()
        except Exception:
            db.rollback()

    _ai_tables_initialized = True
    print("[DB] AI 테이블 초기화 완료")

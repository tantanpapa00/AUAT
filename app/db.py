import os
import time
import logging
from dotenv import load_dotenv
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from sqlalchemy.exc import OperationalError

load_dotenv()

logger = logging.getLogger(__name__)

DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    raise RuntimeError("DATABASE_URL is not set (.env)")

# Docker-friendly connection settings
# - pool_pre_ping: verify connections before use
# - pool_recycle: recycle connections after 1800s (30min)
# - pool_size: maintain 5 connections
# - max_overflow: allow 10 additional connections under load
engine = create_engine(
    DATABASE_URL,
    pool_pre_ping=True,
    pool_recycle=1800,
    pool_size=5,
    max_overflow=10,
)

SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


def wait_for_db(max_retries: int = 30, retry_interval: float = 2.0) -> bool:
    """Wait for database to be available (Docker startup sync).

    Args:
        max_retries: Maximum number of connection attempts
        retry_interval: Seconds to wait between retries

    Returns:
        True if connected, raises RuntimeError if all retries exhausted
    """
    for attempt in range(1, max_retries + 1):
        try:
            with engine.connect() as conn:
                conn.execute(text("SELECT 1"))
            logger.info(f"Database connected (attempt {attempt})")
            return True
        except OperationalError as e:
            if attempt == max_retries:
                logger.error(f"Database connection failed after {max_retries} attempts: {e}")
                raise RuntimeError(f"Cannot connect to database after {max_retries} attempts")
            logger.warning(f"Database not ready (attempt {attempt}/{max_retries}), retrying in {retry_interval}s...")
            time.sleep(retry_interval)
    return False


def get_db():
    """FastAPI dependency for database session.

    Note: idle_in_transaction 방지를 위해 반드시 commit/rollback 후 close
    """
    db = SessionLocal()
    try:
        yield db
        db.commit()  # 성공 시 커밋 (이미 커밋된 경우 no-op)
    except Exception:
        db.rollback()  # 예외 시 롤백
        raise
    finally:
        db.close()

#!/usr/bin/env python3
"""
Database initialization script for Docker environment.
Creates all tables defined in app/models.py.

Usage:
  python scripts/init_db.py

Or inside Docker:
  docker exec bbooster-app python scripts/init_db.py
"""
import sys
import os

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.db import engine, wait_for_db
from app.models import Base

def init_db():
    """Initialize database tables."""
    print("Waiting for database connection...")
    try:
        wait_for_db(max_retries=30, retry_interval=2.0)
    except RuntimeError as e:
        print(f"ERROR: {e}")
        sys.exit(1)

    print("Creating database tables...")
    Base.metadata.create_all(bind=engine)
    print("Database tables created successfully!")

    # List created tables
    from sqlalchemy import inspect
    inspector = inspect(engine)
    tables = inspector.get_table_names()
    print(f"Tables: {tables}")

if __name__ == "__main__":
    init_db()

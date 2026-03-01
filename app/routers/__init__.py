# app/routers/__init__.py
# FastAPI routers 모듈

from .watchlist import router as watchlist_router
from .admin import router as admin_router
from .market_kr import router as market_kr_router
from .market_us import router as market_us_router

__all__ = ["watchlist_router", "admin_router", "market_kr_router", "market_us_router"]

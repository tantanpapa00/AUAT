# app/routers/__init__.py
# FastAPI routers 모듈

from .watchlist import router as watchlist_router

__all__ = ["watchlist_router"]

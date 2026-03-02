# app/routers/__init__.py
# FastAPI routers 모듈

from .watchlist import router as watchlist_router
from .admin import router as admin_router
from .market_kr import router as market_kr_router
from .market_us import router as market_us_router
from .market_misc import router as market_misc_router
from .screener import router as screener_router
from .ai_report import router as ai_report_router
from .backtest import router as backtest_router
from .webhook import router as webhook_router
from .ws import router as ws_router
from .notifications import router as notifications_router
from .auth import router as auth_router

__all__ = ["watchlist_router", "admin_router", "market_kr_router", "market_us_router", "market_misc_router", "screener_router", "ai_report_router", "backtest_router", "webhook_router", "ws_router", "notifications_router", "auth_router"]

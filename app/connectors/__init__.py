# app/connectors/__init__.py
# Week 9: Multi-connector standardization
# Provides unified factory and registry for all connectors.

from __future__ import annotations

from typing import Dict, List, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from .base import Connector

# Connector cache (singleton per exchange)
_CONNECTOR_CACHE: Dict[str, "Connector"] = {}

# Supported exchanges
SUPPORTED_EXCHANGES = ["OKX", "KIS", "KIS_KR", "KIS_US", "BINANCE", "BYBIT", "UPBIT"]


def _norm_exchange(exchange: str | None) -> str:
    """Normalize exchange name to canonical form."""
    if not exchange:
        return ""
    ex = str(exchange).strip().upper()
    # Aliases
    if ex in ("OKEX",):
        return "OKX"
    if ex in ("KOREAINVESTMENT", "KOREA INVESTMENT", "KOREA_INVESTMENT", "KOREAINVESTMENTSEC"):
        return "KIS"
    if ex in ("KIS_KR", "KIS-KR", "KISKR"):
        return "KIS_KR"
    if ex in ("KIS_US", "KIS-US", "KISUS"):
        return "KIS_US"
    if ex in ("BINANCE.COM", "BINANCESPOT"):
        return "BINANCE"
    if ex in ("BYBIT.COM", "BYBITSPOT"):
        return "BYBIT"
    if ex in ("UPBIT.COM", "UPBITSPOT"):
        return "UPBIT"
    return ex


def get_connector(exchange: str) -> Optional["Connector"]:
    """
    Get connector instance by exchange name.

    Uses singleton pattern - same instance returned for same exchange.

    Args:
        exchange: Exchange name (OKX, KIS, etc.)

    Returns:
        Connector instance or None if unknown exchange.
    """
    ex = _norm_exchange(exchange)
    if ex in _CONNECTOR_CACHE:
        return _CONNECTOR_CACHE[ex]

    conn = None
    if ex == "OKX":
        from .okx import OKXConnector
        conn = OKXConnector()
    elif ex in ("KIS", "KIS_KR"):
        from .kis import KISConnector
        conn = KISConnector()
    elif ex == "KIS_US":
        # KIS_US는 현재 미지원 (해외주식 주문 API 별도 구현 필요)
        # 캐시하지 않고 None 반환
        return None
    elif ex == "BINANCE":
        from .binance import BinanceConnector
        conn = BinanceConnector()
    elif ex == "BYBIT":
        from .bybit import BybitConnector
        conn = BybitConnector()
    elif ex == "UPBIT":
        # UPBIT은 현재 미지원 (커넥터 미구현)
        return None

    if conn is not None:
        _CONNECTOR_CACHE[ex] = conn
    return conn


def list_connectors() -> List[str]:
    """List all supported exchange names."""
    return SUPPORTED_EXCHANGES.copy()


def get_all_connectors() -> Dict[str, "Connector"]:
    """
    Get all available connectors.

    Returns:
        Dict of exchange name -> connector instance
    """
    result = {}
    for ex in SUPPORTED_EXCHANGES:
        try:
            conn = get_connector(ex)
            if conn is not None:
                result[ex] = conn
        except Exception:
            pass  # Skip connectors that fail to initialize
    return result


def clear_cache():
    """Clear connector cache (for testing)."""
    global _CONNECTOR_CACHE
    _CONNECTOR_CACHE = {}


# Re-export base types for convenience
from .base import (
    Connector,
    PlaceOrderResult,
    OrderResult,
    BalanceSplit,
    MarketInfo,
    Side,
    OrderType,
)

__all__ = [
    # Factory
    "get_connector",
    "list_connectors",
    "get_all_connectors",
    "clear_cache",
    "SUPPORTED_EXCHANGES",
    # Types
    "Connector",
    "PlaceOrderResult",
    "OrderResult",
    "BalanceSplit",
    "MarketInfo",
    "Side",
    "OrderType",
]

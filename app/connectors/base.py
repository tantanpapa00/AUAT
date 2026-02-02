# app/connectors/base.py
# Week5 Day2: Connector interface skeleton (SSOT).
# Purpose: provide a stable, shared contract for exchange/broker connectors.
# NOTE: Keep this module dependency-free (std lib only).

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Protocol, Literal


Side = Literal["buy", "sell"]
OrderType = Literal["market", "limit"]


@dataclass(frozen=True)
class PlaceOrderResult:
    ok: bool
    exchange: str
    symbol: str
    side: Side
    qty: float
    order_type: OrderType
    exchange_order_id: Optional[str] = None  # 공통 필드 (OKX: ordId, KIS: ODNO)
    okx_order_id: Optional[str] = None  # deprecated: use exchange_order_id (backward compat)
    clord_id: Optional[str] = None
    state: Optional[str] = None
    avg_px: Optional[float] = None
    filled_qty: Optional[float] = None
    raw: Optional[Dict[str, Any]] = None
    err_code: Optional[str] = None
    err_msg: Optional[str] = None


@dataclass(frozen=True)
class OrderResult:
    ok: bool
    exchange: str
    symbol: str
    exchange_order_id: Optional[str] = None  # 공통 필드 (OKX: ordId, KIS: ODNO)
    okx_order_id: Optional[str] = None  # deprecated: use exchange_order_id (backward compat)
    clord_id: Optional[str] = None
    state: Optional[str] = None
    avg_px: Optional[float] = None
    filled_qty: Optional[float] = None
    raw: Optional[Dict[str, Any]] = None
    err_code: Optional[str] = None
    err_msg: Optional[str] = None


@dataclass(frozen=True)
class BalanceSplit:
    ok: bool
    exchange: str
    ccy: str
    total: float
    trading: float
    funding: float
    raw: Optional[Dict[str, Any]] = None
    err_code: Optional[str] = None
    err_msg: Optional[str] = None


@dataclass(frozen=True)
class MarketInfo:
    exchange: str
    symbol: str
    min_qty: Optional[float] = None
    lot_qty: Optional[float] = None
    min_notional: Optional[float] = None
    raw: Optional[Dict[str, Any]] = None


class Connector(Protocol):
    exchange: str

    def place_order(
        self,
        *,
        symbol: str,
        side: Side,
        qty: float,
        order_type: OrderType = "market",
        px: Optional[float] = None,
        payload: Optional[Dict[str, Any]] = None,
    ) -> PlaceOrderResult:
        ...

    def get_order(
        self,
        *,
        symbol: str,
        exchange_order_id: Optional[str] = None,
        clord_id: Optional[str] = None,
    ) -> OrderResult:
        ...

    def get_balance_split(self, *, ccy: str = "USDT") -> BalanceSplit:
        ...

    def get_markets(self, *, symbol: Optional[str] = None) -> List[MarketInfo]:
        ...

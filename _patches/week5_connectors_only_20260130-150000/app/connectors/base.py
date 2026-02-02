from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional, Protocol


@dataclass
class OrderLookup:
    symbol: str
    okx_order_id: Optional[str] = None
    okx_clord_id: Optional[str] = None


class Connector(Protocol):
    """Connector interface (Week5 v1). Minimal surface to decouple exchange-specific logic."""

    name: str

    def place_order(self, *, symbol: str, side: str, qty: float, order_type: str = "market",
                    px: float | None = None, payload: dict | None = None) -> dict: ...

    def get_order(self, *, symbol: str, okx_order_id: str | None = None, okx_clord_id: str | None = None) -> dict: ...

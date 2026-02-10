# app/connectors/upbit.py
# Upbit connector for Korean cryptocurrency exchange
# - JWT authentication
# - Market order (bid=buy, ask=sell)
# - Balance query

from __future__ import annotations

import hashlib
import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from typing import Any, Dict, List, Optional, Tuple

from .base import (
    BalanceSplit,
    Connector,
    MarketInfo,
    OrderResult,
    PlaceOrderResult,
    TickerInfo,
    Side,
    OrderType,
)

# Upbit API base URL
UPBIT_BASE_URL = "https://api.upbit.com/v1"


class UpbitConnector(Connector):
    """
    Upbit connector.
    - No testnet available (real trading only)
    - JWT authentication required for private endpoints
    - Market buy: price-based (KRW amount)
    - Market sell: volume-based (coin quantity)
    """

    exchange = "UPBIT"

    def __init__(self, *, timeout_sec: float = 10.0):
        self.timeout_sec = float(timeout_sec)
        self.base_url = UPBIT_BASE_URL
        self._access_key = (os.getenv("UPBIT_ACCESS_KEY") or "").strip()
        self._secret_key = (os.getenv("UPBIT_SECRET_KEY") or "").strip()

    def _get_jwt_token(self, query: Optional[Dict[str, Any]] = None) -> str:
        """Generate JWT token for Upbit API authentication."""
        try:
            import jwt
        except ImportError:
            raise ImportError("PyJWT is required for Upbit connector. Install with: pip install PyJWT")

        payload = {
            "access_key": self._access_key,
            "nonce": str(uuid.uuid4()),
        }

        if query:
            query_string = urllib.parse.urlencode(query).encode()
            m = hashlib.sha512()
            m.update(query_string)
            payload["query_hash"] = m.hexdigest()
            payload["query_hash_alg"] = "SHA512"

        return jwt.encode(payload, self._secret_key)

    def _request(
        self,
        *,
        method: str,
        path: str,
        params: Optional[Dict[str, Any]] = None,
        json_body: Optional[Dict[str, Any]] = None,
        require_auth: bool = True,
    ) -> Tuple[bool, int, Optional[Dict[str, Any]], str]:
        """Make HTTP request to Upbit API."""
        method_u = (method or "GET").upper()
        url = f"{self.base_url}{path}"

        if params and method_u == "GET":
            qs = urllib.parse.urlencode(params)
            url = f"{url}?{qs}"

        headers: Dict[str, str] = {
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

        if require_auth:
            if not self._access_key or not self._secret_key:
                return False, 0, None, "UPBIT_ACCESS_KEY or UPBIT_SECRET_KEY missing"
            query_for_hash = json_body if json_body else params
            jwt_token = self._get_jwt_token(query_for_hash)
            headers["Authorization"] = f"Bearer {jwt_token}"

        data = None
        if json_body is not None:
            data = json.dumps(json_body, ensure_ascii=False).encode("utf-8")

        req = urllib.request.Request(url, data=data, headers=headers, method=method_u)

        try:
            with urllib.request.urlopen(req, timeout=self.timeout_sec) as r:
                status = int(getattr(r, "status", 200) or 200)
                raw = r.read().decode("utf-8", errors="replace")
            try:
                j = json.loads(raw) if raw else None
            except Exception:
                j = None
            return True, status, j, raw

        except urllib.error.HTTPError as e:
            try:
                raw = e.read().decode("utf-8", errors="replace")
            except Exception:
                raw = str(e)
            try:
                j = json.loads(raw) if raw else None
            except Exception:
                j = None
            return False, int(getattr(e, "code", 0) or 0), j, raw
        except Exception as e:
            return False, 0, None, f"request_error:{type(e).__name__}:{e}"

    def get_current_price(self, symbol: str) -> Optional[float]:
        """
        Get current price for a symbol (public API, no auth required).
        symbol: "KRW-BTC", "KRW-ETH" etc.
        """
        # Normalize symbol format
        if not symbol.startswith("KRW-") and not symbol.startswith("BTC-"):
            symbol = f"KRW-{symbol}"

        ok, status, j, raw = self._request(
            method="GET",
            path="/ticker",
            params={"markets": symbol},
            require_auth=False,
        )

        if not ok or not j:
            return None

        if isinstance(j, list) and len(j) > 0:
            return float(j[0].get("trade_price", 0))
        return None

    def get_balance_split(self, *, ccy: str = "KRW") -> BalanceSplit:
        """Get balance for specified currency."""
        ok, status, j, raw = self._request(
            method="GET",
            path="/accounts",
            require_auth=True,
        )

        if not ok or not j:
            return BalanceSplit(
                ok=False, exchange=self.exchange, ccy=ccy,
                total=0, trading=0, funding=0,
                err_code=f"http_{status}" if status else "request_failed",
                err_msg=str(raw)[:100] if raw else "request_failed",
            )

        ccy_upper = ccy.upper()
        for acc in j if isinstance(j, list) else []:
            if acc.get("currency", "").upper() == ccy_upper:
                balance = float(acc.get("balance", 0))
                locked = float(acc.get("locked", 0))
                return BalanceSplit(
                    ok=True, exchange=self.exchange, ccy=ccy_upper,
                    total=balance + locked,
                    trading=balance,
                    funding=locked,
                    raw=acc,
                )

        return BalanceSplit(
            ok=True, exchange=self.exchange, ccy=ccy,
            total=0, trading=0, funding=0,
        )

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
        """
        Place order on Upbit.

        Market Buy: price-based (KRW amount to spend)
        Market Sell: volume-based (coin quantity to sell)

        Args:
            symbol: Market code (e.g., "KRW-BTC")
            side: "buy" or "sell"
            qty: For buy = KRW amount, for sell = coin quantity
            order_type: "market" only (limit not implemented)
            px: Not used for market orders
        """
        # Normalize symbol
        if not symbol.startswith("KRW-") and not symbol.startswith("BTC-"):
            symbol = f"KRW-{symbol}"

        side_lower = side.lower() if isinstance(side, str) else side

        if order_type != "market":
            return PlaceOrderResult(
                ok=False, exchange=self.exchange, symbol=symbol, side=side,
                qty=float(qty), order_type=order_type,
                err_code="unsupported_order_type",
                err_msg="Only market orders are supported for Upbit",
            )

        # Build order body
        body: Dict[str, Any] = {
            "market": symbol,
        }

        if side_lower == "buy":
            # Market buy: use "price" ord_type with KRW amount
            body["side"] = "bid"
            body["ord_type"] = "price"
            body["price"] = str(int(qty))  # KRW amount (integer)
        else:
            # Market sell: use "market" ord_type with volume
            body["side"] = "ask"
            body["ord_type"] = "market"
            body["volume"] = str(qty)  # Coin quantity

        try:
            ok, status, j, raw = self._request(
                method="POST",
                path="/orders",
                json_body=body,
                require_auth=True,
            )

            if not ok:
                err_msg = raw
                if isinstance(j, dict):
                    err_msg = j.get("error", {}).get("message", raw)
                return PlaceOrderResult(
                    ok=False, exchange=self.exchange, symbol=symbol, side=side,
                    qty=float(qty), order_type=order_type,
                    err_code=f"http_{status}", err_msg=str(err_msg)[:200],
                    raw=j,
                )

            if isinstance(j, dict):
                order_uuid = j.get("uuid")
                order_side = j.get("side")
                order_state = j.get("state")

                return PlaceOrderResult(
                    ok=True, exchange=self.exchange, symbol=symbol, side=side,
                    qty=float(qty), order_type=order_type,
                    exchange_order_id=order_uuid,
                    raw=j,
                )
            else:
                return PlaceOrderResult(
                    ok=False, exchange=self.exchange, symbol=symbol, side=side,
                    qty=float(qty), order_type=order_type,
                    err_code="invalid_response", err_msg="Unexpected response format",
                    raw={"raw": raw},
                )

        except Exception as e:
            return PlaceOrderResult(
                ok=False, exchange=self.exchange, symbol=symbol, side=side,
                qty=float(qty), order_type=order_type,
                err_code="exception", err_msg=f"{type(e).__name__}: {e}",
            )

    def get_order(
        self,
        *,
        symbol: str,
        exchange_order_id: Optional[str] = None,
        **kwargs,
    ) -> OrderResult:
        """Get order status by UUID."""
        if not exchange_order_id:
            return OrderResult(
                ok=False, exchange=self.exchange, symbol=symbol,
                err_code="missing_order_id", err_msg="exchange_order_id required",
            )

        ok, status, j, raw = self._request(
            method="GET",
            path="/order",
            params={"uuid": exchange_order_id},
            require_auth=True,
        )

        if not ok or not j:
            return OrderResult(
                ok=False, exchange=self.exchange, symbol=symbol,
                err_code=f"http_{status}", err_msg=raw[:200] if raw else "request_failed",
            )

        return OrderResult(
            ok=True, exchange=self.exchange, symbol=symbol,
            exchange_order_id=j.get("uuid"),
            state=j.get("state"),
            filled_qty=float(j.get("executed_volume", 0)),
            avg_px=float(j.get("avg_price", 0)) if j.get("avg_price") else None,
            raw=j,
        )

    def get_markets(self, *, symbol: Optional[str] = None) -> List[MarketInfo]:
        """Get market information (public API)."""
        ok, status, j, raw = self._request(
            method="GET",
            path="/market/all",
            require_auth=False,
        )

        if not ok or not j:
            return []

        markets = []
        for m in j if isinstance(j, list) else []:
            market_code = m.get("market", "")
            if symbol and symbol.upper() not in market_code.upper():
                continue
            markets.append(MarketInfo(
                exchange=self.exchange,
                symbol=market_code,
                raw=m,
            ))

        return markets

    def get_ticker(self, symbol: str) -> TickerInfo:
        """Get ticker information."""
        price = self.get_current_price(symbol)
        if price is None:
            return TickerInfo(
                ok=False, exchange=self.exchange, symbol=symbol,
                err_code="price_fetch_failed", err_msg="Failed to get current price",
            )

        return TickerInfo(
            ok=True, exchange=self.exchange, symbol=symbol,
            last_price=price,
        )

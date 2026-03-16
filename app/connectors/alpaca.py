# app/connectors/alpaca.py
# Alpaca connector for US stock trading (Paper & Live)
# - dependency-free (urllib)
# - implements Connector protocol (see app/connectors/base.py)

from __future__ import annotations

import json
import os
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime
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


class AlpacaConnector(Connector):
    """
    Alpaca connector for US equity trading.
    - auth: API Key/Secret headers
    - endpoints: Trading API (paper/live) + Data API
    """

    exchange = "ALPACA"

    def __init__(self, *, timeout_sec: float = 30.0):
        self.timeout_sec = float(os.getenv("ALPACA_TIMEOUT_SEC", str(timeout_sec)))

        # API credentials
        self.api_key = (os.getenv("ALPACA_API_KEY", "") or "").strip()
        self.api_secret = (os.getenv("ALPACA_API_SECRET", "") or "").strip()

        # Paper trading mode
        self.paper = (os.getenv("ALPACA_PAPER", "true") or "").strip().lower() in ("true", "1", "yes")

        # Base URLs
        default_base = "https://paper-api.alpaca.markets" if self.paper else "https://api.alpaca.markets"
        self.base_url = (os.getenv("ALPACA_BASE_URL", default_base) or default_base).rstrip("/")
        self.data_url = (os.getenv("ALPACA_DATA_URL", "https://data.alpaca.markets") or "https://data.alpaca.markets").rstrip("/")

    # ---------------------
    # helpers
    # ---------------------
    def _auth_headers(self) -> Dict[str, str]:
        """Alpaca authentication headers."""
        return {
            "APCA-API-KEY-ID": self.api_key,
            "APCA-API-SECRET-KEY": self.api_secret,
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

    def _ensure_creds(self) -> Tuple[bool, str]:
        if not self.api_key:
            return False, "missing ALPACA_API_KEY"
        if not self.api_secret:
            return False, "missing ALPACA_API_SECRET"
        return True, "ok"

    def _request(
        self,
        method: str,
        url: str,
        body: Optional[Dict[str, Any]] = None,
        headers: Optional[Dict[str, str]] = None,
    ) -> Tuple[bool, int, Dict[str, Any]]:
        """Make HTTP request and return (ok, status_code, response_data)."""
        hdrs = self._auth_headers()
        if headers:
            hdrs.update(headers)

        data = None
        if body is not None:
            data = json.dumps(body).encode("utf-8")

        req = urllib.request.Request(url, data=data, headers=hdrs, method=method)

        try:
            with urllib.request.urlopen(req, timeout=self.timeout_sec) as resp:
                status = resp.status
                raw = resp.read().decode("utf-8")
                result = json.loads(raw) if raw else {}
                return True, status, result
        except urllib.error.HTTPError as e:
            status = e.code
            raw = e.read().decode("utf-8", errors="replace")
            try:
                result = json.loads(raw) if raw else {}
            except json.JSONDecodeError:
                result = {"error": raw}
            return False, status, result
        except urllib.error.URLError as e:
            return False, 0, {"error": str(e.reason)}
        except Exception as e:
            return False, 0, {"error": str(e)}

    # ---------------------
    # Account / Balance
    # ---------------------
    def get_balance(self) -> Dict[str, Any]:
        """
        Get account balance.
        GET /v2/account
        Returns: {"cash": float, "equity": float, "currency": "USD", "buying_power": float}
        """
        ok, msg = self._ensure_creds()
        if not ok:
            return {"error": msg, "cash": 0, "equity": 0, "currency": "USD"}

        url = f"{self.base_url}/v2/account"
        ok, status, data = self._request("GET", url)

        if not ok:
            return {"error": data.get("error", f"HTTP {status}"), "cash": 0, "equity": 0, "currency": "USD"}

        return {
            "cash": float(data.get("cash", 0)),
            "equity": float(data.get("equity", 0)),
            "buying_power": float(data.get("buying_power", 0)),
            "currency": "USD",
            "raw": data,
        }

    def get_balance_split(self, *, ccy: str = "USD") -> BalanceSplit:
        """Connector protocol: get balance split."""
        balance = self.get_balance()

        if "error" in balance and balance.get("cash", 0) == 0:
            return BalanceSplit(
                ok=False,
                exchange=self.exchange,
                ccy=ccy,
                total=0,
                trading=0,
                funding=0,
                err_msg=balance.get("error"),
            )

        equity = balance.get("equity", 0)
        cash = balance.get("cash", 0)

        return BalanceSplit(
            ok=True,
            exchange=self.exchange,
            ccy=ccy,
            total=equity,
            trading=cash,
            funding=0,
            raw=balance.get("raw"),
        )

    # ---------------------
    # Current Price
    # ---------------------
    def get_current_price(self, symbol: str) -> float:
        """
        Get latest quote price for a symbol.
        GET /v2/stocks/{symbol}/quotes/latest (data URL)
        Returns: float (mid price or last trade)
        """
        ok, msg = self._ensure_creds()
        if not ok:
            return 0.0

        symbol = symbol.upper().strip()
        url = f"{self.data_url}/v2/stocks/{symbol}/quotes/latest"
        ok, status, data = self._request("GET", url)

        if not ok:
            return 0.0

        quote = data.get("quote", {})
        bid = float(quote.get("bp", 0) or 0)
        ask = float(quote.get("ap", 0) or 0)

        if bid > 0 and ask > 0:
            return (bid + ask) / 2
        elif ask > 0:
            return ask
        elif bid > 0:
            return bid
        return 0.0

    def get_ticker(self, symbol: str) -> TickerInfo:
        """Connector protocol: get ticker info."""
        ok, msg = self._ensure_creds()
        if not ok:
            return TickerInfo(
                ok=False,
                exchange=self.exchange,
                symbol=symbol,
                err_msg=msg,
            )

        symbol = symbol.upper().strip()
        url = f"{self.data_url}/v2/stocks/{symbol}/quotes/latest"
        success, status, data = self._request("GET", url)

        if not success:
            return TickerInfo(
                ok=False,
                exchange=self.exchange,
                symbol=symbol,
                err_msg=data.get("error", f"HTTP {status}"),
            )

        quote = data.get("quote", {})
        bid = float(quote.get("bp", 0) or 0)
        ask = float(quote.get("ap", 0) or 0)
        last = (bid + ask) / 2 if bid > 0 and ask > 0 else (ask or bid)

        return TickerInfo(
            ok=True,
            exchange=self.exchange,
            symbol=symbol,
            last=last,
            bid=bid,
            ask=ask,
            raw=data,
        )

    # ---------------------
    # Orders
    # ---------------------
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
        Place an order.
        POST /v2/orders
        """
        ok, msg = self._ensure_creds()
        if not ok:
            return PlaceOrderResult(
                ok=False,
                exchange=self.exchange,
                symbol=symbol,
                side=side,
                qty=qty,
                order_type=order_type,
                err_msg=msg,
            )

        symbol = symbol.upper().strip()
        url = f"{self.base_url}/v2/orders"

        body: Dict[str, Any] = {
            "symbol": symbol,
            "qty": str(qty),
            "side": side,
            "type": order_type,
            "time_in_force": "day",
        }

        if order_type == "limit" and px is not None:
            body["limit_price"] = str(px)

        if payload:
            body.update(payload)

        success, status, data = self._request("POST", url, body=body)

        if not success:
            return PlaceOrderResult(
                ok=False,
                exchange=self.exchange,
                symbol=symbol,
                side=side,
                qty=qty,
                order_type=order_type,
                err_code=str(status),
                err_msg=data.get("message", data.get("error", f"HTTP {status}")),
                raw=data,
            )

        return PlaceOrderResult(
            ok=True,
            exchange=self.exchange,
            symbol=symbol,
            side=side,
            qty=qty,
            order_type=order_type,
            exchange_order_id=data.get("id"),
            clord_id=data.get("client_order_id"),
            state=data.get("status"),
            filled_qty=float(data.get("filled_qty", 0) or 0),
            avg_px=float(data.get("filled_avg_price") or 0) if data.get("filled_avg_price") else None,
            raw=data,
        )

    def get_order(
        self,
        *,
        symbol: str,
        exchange_order_id: Optional[str] = None,
        clord_id: Optional[str] = None,
    ) -> OrderResult:
        """
        Get order status.
        GET /v2/orders/{order_id}
        """
        ok, msg = self._ensure_creds()
        if not ok:
            return OrderResult(
                ok=False,
                exchange=self.exchange,
                symbol=symbol,
                err_msg=msg,
            )

        order_id = exchange_order_id or clord_id
        if not order_id:
            return OrderResult(
                ok=False,
                exchange=self.exchange,
                symbol=symbol,
                err_msg="order_id required",
            )

        url = f"{self.base_url}/v2/orders/{order_id}"
        success, status, data = self._request("GET", url)

        if not success:
            return OrderResult(
                ok=False,
                exchange=self.exchange,
                symbol=symbol,
                err_code=str(status),
                err_msg=data.get("message", data.get("error", f"HTTP {status}")),
                raw=data,
            )

        return OrderResult(
            ok=True,
            exchange=self.exchange,
            symbol=data.get("symbol", symbol),
            exchange_order_id=data.get("id"),
            clord_id=data.get("client_order_id"),
            state=data.get("status"),
            filled_qty=float(data.get("filled_qty", 0) or 0),
            avg_px=float(data.get("filled_avg_price") or 0) if data.get("filled_avg_price") else None,
            raw=data,
        )

    def cancel_order(self, order_id: str) -> Dict[str, Any]:
        """
        Cancel an order.
        DELETE /v2/orders/{order_id}
        """
        ok, msg = self._ensure_creds()
        if not ok:
            return {"ok": False, "error": msg}

        url = f"{self.base_url}/v2/orders/{order_id}"
        success, status, data = self._request("DELETE", url)

        if not success:
            return {
                "ok": False,
                "error": data.get("message", data.get("error", f"HTTP {status}")),
                "raw": data,
            }

        return {"ok": True, "order_id": order_id, "raw": data}

    # ---------------------
    # Positions
    # ---------------------
    def get_positions(self) -> List[Dict[str, Any]]:
        """
        Get all open positions.
        GET /v2/positions
        """
        ok, msg = self._ensure_creds()
        if not ok:
            return []

        url = f"{self.base_url}/v2/positions"
        success, status, data = self._request("GET", url)

        if not success or not isinstance(data, list):
            return []

        positions = []
        for pos in data:
            positions.append({
                "symbol": pos.get("symbol"),
                "qty": float(pos.get("qty", 0)),
                "side": "long" if float(pos.get("qty", 0)) > 0 else "short",
                "avg_entry_price": float(pos.get("avg_entry_price", 0) or 0),
                "market_value": float(pos.get("market_value", 0) or 0),
                "unrealized_pl": float(pos.get("unrealized_pl", 0) or 0),
                "unrealized_plpc": float(pos.get("unrealized_plpc", 0) or 0),
                "current_price": float(pos.get("current_price", 0) or 0),
                "raw": pos,
            })

        return positions

    # ---------------------
    # Markets / Assets
    # ---------------------
    def get_markets(self, *, symbol: Optional[str] = None) -> List[MarketInfo]:
        """
        Get tradable assets.
        GET /v2/assets
        """
        ok, msg = self._ensure_creds()
        if not ok:
            return []

        url = f"{self.base_url}/v2/assets"
        params = {"status": "active", "asset_class": "us_equity"}

        if symbol:
            # Single asset lookup
            url = f"{self.base_url}/v2/assets/{symbol.upper()}"
            success, status, data = self._request("GET", url)
            if not success:
                return []
            return [MarketInfo(
                exchange=self.exchange,
                symbol=data.get("symbol", symbol),
                min_qty=1 if not data.get("fractionable") else 0.001,
                lot_qty=1 if not data.get("fractionable") else 0.001,
                raw=data,
            )]

        # List all assets
        url = f"{url}?{urllib.parse.urlencode(params)}"
        success, status, data = self._request("GET", url)

        if not success or not isinstance(data, list):
            return []

        markets = []
        for asset in data:
            if asset.get("tradable"):
                markets.append(MarketInfo(
                    exchange=self.exchange,
                    symbol=asset.get("symbol"),
                    min_qty=1 if not asset.get("fractionable") else 0.001,
                    lot_qty=1 if not asset.get("fractionable") else 0.001,
                    raw=asset,
                ))

        return markets

    # ---------------------
    # Historical Data (Candles)
    # ---------------------
    def get_candles(
        self,
        symbol: str,
        timeframe: str = "1Day",
        start: Optional[str] = None,
        end: Optional[str] = None,
        limit: int = 1000,
    ) -> List[Dict[str, Any]]:
        """
        Get historical bars/candles.
        GET https://data.alpaca.markets/v2/stocks/{symbol}/bars

        Args:
            symbol: Stock symbol (e.g., "AAPL")
            timeframe: "1Min", "5Min", "15Min", "1Hour", "4Hour", "1Day", "1Week"
            start: ISO format datetime (e.g., "2024-01-01")
            end: ISO format datetime
            limit: Max number of bars (default 1000)

        Returns: List of candle dicts with keys: t, o, h, l, c, v
        """
        ok, msg = self._ensure_creds()
        if not ok:
            return []

        symbol = symbol.upper().strip()
        url = f"{self.data_url}/v2/stocks/{symbol}/bars"

        params: Dict[str, Any] = {
            "timeframe": timeframe,
            "limit": min(limit, 10000),
        }

        if start:
            params["start"] = start
        if end:
            params["end"] = end

        url = f"{url}?{urllib.parse.urlencode(params)}"
        success, status, data = self._request("GET", url)

        if not success:
            return []

        bars = data.get("bars", [])
        if not bars:
            return []

        candles = []
        for bar in bars:
            candles.append({
                "t": bar.get("t"),  # timestamp
                "o": float(bar.get("o", 0)),  # open
                "h": float(bar.get("h", 0)),  # high
                "l": float(bar.get("l", 0)),  # low
                "c": float(bar.get("c", 0)),  # close
                "v": float(bar.get("v", 0)),  # volume
            })

        return candles

    # ---------------------
    # Assets List (for screener)
    # ---------------------
    def get_all_assets(
        self,
        exchanges: Optional[List[str]] = None,
        tradable_only: bool = True,
    ) -> List[Dict[str, Any]]:
        """
        Get all active US equity assets.
        GET /v2/assets?status=active&asset_class=us_equity

        Args:
            exchanges: Filter by exchange (e.g., ["NYSE", "NASDAQ", "AMEX"])
            tradable_only: Only return tradable assets

        Returns: List of asset dicts
        """
        ok, msg = self._ensure_creds()
        if not ok:
            return []

        url = f"{self.base_url}/v2/assets"
        params: Dict[str, str] = {
            "status": "active",
            "asset_class": "us_equity",
        }

        url = f"{url}?{urllib.parse.urlencode(params)}"
        success, status, data = self._request("GET", url)

        if not success or not isinstance(data, list):
            return []

        assets = []
        target_exchanges = set(ex.upper() for ex in (exchanges or ["NYSE", "NASDAQ", "AMEX"]))

        for asset in data:
            if tradable_only and not asset.get("tradable"):
                continue

            asset_exchange = (asset.get("exchange") or "").upper()
            if target_exchanges and asset_exchange not in target_exchanges:
                continue

            assets.append({
                "symbol": asset.get("symbol"),
                "name": asset.get("name"),
                "exchange": asset_exchange,
                "tradable": asset.get("tradable"),
                "fractionable": asset.get("fractionable"),
                "shortable": asset.get("shortable"),
                "easy_to_borrow": asset.get("easy_to_borrow"),
                "marginable": asset.get("marginable"),
            })

        return assets

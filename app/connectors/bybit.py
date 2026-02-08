# app/connectors/bybit.py
# Week12 Day4: Bybit Spot connector aligned to app.connectors.base.Connector.
# Dependency-free (urllib + stdlib only).
# API v5: https://bybit-exchange.github.io/docs/v5/intro

from __future__ import annotations

import hashlib
import hmac
import json
import os
import time
from dataclasses import asdict
from typing import Any, Dict, List, Optional, Tuple
from urllib import request as urlrequest
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode

from .base import (
    BalanceSplit,
    Connector,
    MarketInfo,
    OrderResult,
    PlaceOrderResult,
    TickerInfo,
    OrderType,
    Side,
)


def _bybit_env() -> Tuple[str, str, str, bool, float]:
    """Returns (base_url, api_key, api_secret, is_testnet, timeout_sec)"""
    # Testnet: https://api-testnet.bybit.com
    # Production: https://api.bybit.com
    simulated = os.getenv("BYBIT_SIMULATED", "0") == "1"
    if simulated:
        default_url = "https://api-testnet.bybit.com"
    else:
        default_url = "https://api.bybit.com"

    base_url = os.getenv("BYBIT_BASE_URL", default_url).rstrip("/")
    api_key = os.getenv("BYBIT_API_KEY", "")
    api_secret = os.getenv("BYBIT_API_SECRET", "")
    timeout_sec = float(os.getenv("BYBIT_TIMEOUT_SEC", "10"))
    return base_url, api_key, api_secret, simulated, timeout_sec


def _bybit_sign(timestamp: str, api_key: str, recv_window: str, params_str: str, secret: str) -> str:
    """
    Bybit v5 HMAC SHA256 signature.
    Sign: timestamp + api_key + recv_window + params_str
    """
    sign_str = f"{timestamp}{api_key}{recv_window}{params_str}"
    return hmac.new(
        secret.encode("utf-8"),
        sign_str.encode("utf-8"),
        hashlib.sha256
    ).hexdigest()


def _to_bybit_symbol(internal_symbol: str) -> str:
    """Convert internal symbol (BTC-USDT) to Bybit format (BTCUSDT)"""
    return internal_symbol.replace("-", "")


def _from_bybit_symbol(bybit_symbol: str) -> str:
    """Convert Bybit symbol to internal format (best effort)"""
    # Common quote currencies
    for quote in ["USDT", "USDC", "BTC", "ETH"]:
        if bybit_symbol.endswith(quote):
            base = bybit_symbol[:-len(quote)]
            return f"{base}-{quote}"
    return bybit_symbol


def _bybit_request(
    method: str,
    path: str,
    params: Dict[str, Any] | None = None,
    signed: bool = True
) -> Dict[str, Any]:
    """
    Make Bybit API v5 request.

    Args:
        method: HTTP method (GET, POST)
        path: API path (e.g., /v5/order/create)
        params: Query/body parameters
        signed: Whether to sign the request
    """
    base_url, api_key, api_secret, _, timeout_sec = _bybit_env()

    params = params or {}
    timestamp = str(int(time.time() * 1000))
    recv_window = "5000"

    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) bbooster-hub/0.1",
    }

    if signed and api_key:
        headers["X-BAPI-API-KEY"] = api_key
        headers["X-BAPI-TIMESTAMP"] = timestamp
        headers["X-BAPI-RECV-WINDOW"] = recv_window

    url = base_url + path

    if method.upper() == "GET":
        query_string = urlencode(params) if params else ""
        if signed and api_key and api_secret:
            signature = _bybit_sign(timestamp, api_key, recv_window, query_string, api_secret)
            headers["X-BAPI-SIGN"] = signature
        if query_string:
            url += "?" + query_string
        data = None
    else:  # POST
        body_str = json.dumps(params, separators=(",", ":"), ensure_ascii=False) if params else ""
        if signed and api_key and api_secret:
            signature = _bybit_sign(timestamp, api_key, recv_window, body_str, api_secret)
            headers["X-BAPI-SIGN"] = signature
        data = body_str.encode("utf-8") if body_str else None

    req = urlrequest.Request(url, data=data, method=method.upper(), headers=headers)

    try:
        with urlrequest.urlopen(req, timeout=timeout_sec) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
            try:
                return json.loads(raw)
            except Exception:
                return {"retCode": -1, "retMsg": "non_json_response", "raw": raw}
    except HTTPError as e:
        raw = e.read().decode("utf-8", errors="replace") if hasattr(e, "read") else str(e)
        try:
            j = json.loads(raw)
            j["_http_status"] = getattr(e, "code", None)
            return j
        except Exception:
            return {"retCode": -1, "retMsg": str(e), "_http_status": getattr(e, "code", None), "raw": raw}
    except URLError as e:
        return {"retCode": -1, "retMsg": f"network_error: {str(e)}"}


def _normalize_bybit_state(status: str) -> str:
    """Convert Bybit order status to internal state"""
    mapping = {
        "New": "sent",
        "PartiallyFilled": "partial",
        "Filled": "filled",
        "Cancelled": "canceled",
        "Rejected": "failed",
        "PartiallyFilledCanceled": "canceled",
        "Untriggered": "sent",
        "Triggered": "sent",
        "Deactivated": "canceled",
    }
    return mapping.get(status, "unknown")


class BybitConnector(Connector):
    exchange = "BYBIT"

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
        Place order on Bybit Spot (v5 API).

        Args:
            symbol: Internal symbol (e.g., BTC-USDT)
            side: "buy" or "sell"
            qty: Quantity in base currency
            order_type: "market" or "limit"
            px: Price (required for limit orders)
            payload: Additional parameters (e.g., orderLinkId)
        """
        bybit_symbol = _to_bybit_symbol(symbol)
        bybit_side = "Buy" if side.lower() == "buy" else "Sell"
        bybit_type = "Market" if order_type.lower() == "market" else "Limit"

        params: Dict[str, Any] = {
            "category": "spot",
            "symbol": bybit_symbol,
            "side": bybit_side,
            "orderType": bybit_type,
            "qty": str(qty),
        }

        # Limit order requires price and timeInForce
        if bybit_type == "Limit":
            if px is None:
                return PlaceOrderResult(
                    ok=False,
                    exchange=self.exchange,
                    symbol=symbol,
                    side=side,
                    qty=float(qty),
                    order_type=order_type,
                    err_code="missing_px",
                    err_msg="limit order requires px",
                )
            params["price"] = str(px)
            params["timeInForce"] = "GTC"  # Good Till Cancelled

        # Client order ID (orderLinkId)
        if payload and isinstance(payload, dict):
            cl = payload.get("orderLinkId") or payload.get("clord_id") or payload.get("clOrdId")
            if isinstance(cl, str) and cl.strip():
                params["orderLinkId"] = cl.strip()

        j = _bybit_request("POST", "/v5/order/create", params=params)

        # Check for error (retCode != 0 means error)
        ret_code = j.get("retCode")
        if ret_code != 0:
            return PlaceOrderResult(
                ok=False,
                exchange=self.exchange,
                symbol=symbol,
                side=side,
                qty=float(qty),
                order_type=order_type,
                err_code=str(ret_code) if ret_code else None,
                err_msg=str(j.get("retMsg", "bybit_error")),
                raw=j,
            )

        # Success - extract from result
        result = j.get("result", {})
        order_id = result.get("orderId")
        order_link_id = result.get("orderLinkId")

        return PlaceOrderResult(
            ok=True,
            exchange=self.exchange,
            symbol=symbol,
            side=side,
            qty=float(qty),
            order_type=order_type,
            exchange_order_id=str(order_id) if order_id else None,
            clord_id=str(order_link_id) if order_link_id else None,
            state="sent",  # Bybit doesn't return state on create
            raw=j,
        )

    def get_order(
        self,
        *,
        symbol: str,
        exchange_order_id: Optional[str] = None,
        clord_id: Optional[str] = None,
    ) -> OrderResult:
        """
        Get order status from Bybit (v5 API).

        Args:
            symbol: Internal symbol (e.g., BTC-USDT)
            exchange_order_id: Bybit order ID
            clord_id: Client order ID (orderLinkId)
        """
        if not exchange_order_id and not clord_id:
            return OrderResult(
                ok=False,
                exchange=self.exchange,
                symbol=symbol,
                err_code="missing_id",
                err_msg="need exchange_order_id or clord_id",
            )

        bybit_symbol = _to_bybit_symbol(symbol)
        params: Dict[str, Any] = {
            "category": "spot",
            "symbol": bybit_symbol,
        }

        if exchange_order_id:
            params["orderId"] = exchange_order_id
        if clord_id:
            params["orderLinkId"] = clord_id

        j = _bybit_request("GET", "/v5/order/realtime", params=params)

        # Check for error
        ret_code = j.get("retCode")
        if ret_code != 0:
            return OrderResult(
                ok=False,
                exchange=self.exchange,
                symbol=symbol,
                err_code=str(ret_code) if ret_code else None,
                err_msg=str(j.get("retMsg", "bybit_error")),
                raw=j,
            )

        # Extract order from result.list
        result = j.get("result", {})
        order_list = result.get("list", [])
        if not order_list:
            return OrderResult(
                ok=False,
                exchange=self.exchange,
                symbol=symbol,
                err_code="order_not_found",
                err_msg="order not found in response",
                raw=j,
            )

        order = order_list[0]
        order_id = order.get("orderId")
        order_link_id = order.get("orderLinkId")
        status = order.get("orderStatus", "")
        cum_exec_qty = order.get("cumExecQty")
        avg_price = order.get("avgPrice")

        def _to_f(x):
            try:
                return float(x)
            except Exception:
                return None

        return OrderResult(
            ok=True,
            exchange=self.exchange,
            symbol=symbol,
            exchange_order_id=str(order_id) if order_id else None,
            clord_id=str(order_link_id) if order_link_id else None,
            state=_normalize_bybit_state(status),
            avg_px=_to_f(avg_price),
            filled_qty=_to_f(cum_exec_qty),
            raw=j,
        )

    def get_balance_split(self, *, ccy: str = "USDT") -> BalanceSplit:
        """
        Get balance for a currency on Bybit (v5 API).

        Uses Unified Trading Account - returns wallet balance.
        """
        params = {
            "accountType": "UNIFIED",
            "coin": ccy,
        }

        j = _bybit_request("GET", "/v5/account/wallet-balance", params=params)

        # Check for error
        ret_code = j.get("retCode")
        if ret_code != 0:
            return BalanceSplit(
                ok=False,
                exchange=self.exchange,
                ccy=ccy,
                total=0.0,
                trading=0.0,
                funding=0.0,
                err_code=str(ret_code) if ret_code else None,
                err_msg=str(j.get("retMsg", "bybit_error")),
                raw=j,
            )

        # Extract balance from result
        result = j.get("result", {})
        accounts = result.get("list", [])

        total = 0.0
        for acc in accounts:
            coins = acc.get("coin", [])
            for c in coins:
                if c.get("coin") == ccy:
                    total = float(c.get("walletBalance", 0) or 0)
                    break

        return BalanceSplit(
            ok=True,
            exchange=self.exchange,
            ccy=ccy,
            total=total,
            trading=total,  # Bybit Unified has no split
            funding=0.0,
            raw=j,
        )

    def get_markets(self, *, symbol: Optional[str] = None) -> List[MarketInfo]:
        """
        Get market info from Bybit (v5 API).

        Uses public endpoint (no auth required).
        """
        base_url, _, _, _, timeout_sec = _bybit_env()

        params = {"category": "spot"}
        if symbol:
            params["symbol"] = _to_bybit_symbol(symbol)

        url = f"{base_url}/v5/market/instruments-info?" + urlencode(params)

        try:
            headers = {
                "Accept": "application/json",
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) bbooster-hub/0.1"
            }
            req = urlrequest.Request(url, headers=headers)
            with urlrequest.urlopen(req, timeout=timeout_sec) as resp:
                raw = resp.read().decode("utf-8", errors="replace")
                j = json.loads(raw)
        except Exception as e:
            return [MarketInfo(exchange=self.exchange, symbol=symbol or "-", raw={"error": str(e)})]

        # Check for error
        if j.get("retCode") != 0:
            return [MarketInfo(exchange=self.exchange, symbol=symbol or "-", raw=j)]

        out: List[MarketInfo] = []
        result = j.get("result", {})
        for item in result.get("list", []):
            if item.get("status") != "Trading":
                continue

            sym = item.get("symbol", "")
            internal_sym = _from_bybit_symbol(sym)

            lot_filter = item.get("lotSizeFilter", {})
            min_qty = float(lot_filter.get("minOrderQty", 0) or 0)
            lot_size = float(lot_filter.get("basePrecision", 0) or 0)

            out.append(
                MarketInfo(
                    exchange=self.exchange,
                    symbol=internal_sym,
                    min_qty=min_qty if min_qty else None,
                    lot_qty=lot_size if lot_size else None,
                    min_notional=None,  # Bybit doesn't have this in instruments-info
                    raw=item,
                )
            )

        return out

    def get_ticker(self, symbol: str) -> TickerInfo:
        """
        Bybit 현재가 조회 (Public API v5)
        GET /v5/market/tickers?category=spot&symbol=BTCUSDT
        """
        base_url, _, _, _, timeout_sec = _bybit_env()
        bybit_symbol = _to_bybit_symbol(symbol)
        url = f"{base_url}/v5/market/tickers?category=spot&symbol={bybit_symbol}"

        try:
            req = urlrequest.Request(url, method="GET", headers={
                "Accept": "application/json",
                "User-Agent": "bbooster-hub/0.1",
            })
            with urlrequest.urlopen(req, timeout=timeout_sec) as resp:
                raw = resp.read().decode("utf-8", errors="replace")
                j = json.loads(raw)
        except HTTPError as e:
            raw = e.read().decode("utf-8", errors="replace") if hasattr(e, "read") else str(e)
            return TickerInfo(
                ok=False,
                exchange=self.exchange,
                symbol=symbol,
                err_code="http_error",
                err_msg=str(e),
                raw={"error": raw},
            )
        except URLError as e:
            return TickerInfo(
                ok=False,
                exchange=self.exchange,
                symbol=symbol,
                err_code="network_error",
                err_msg=str(e),
            )
        except Exception as e:
            return TickerInfo(
                ok=False,
                exchange=self.exchange,
                symbol=symbol,
                err_code="exception",
                err_msg=str(e),
            )

        if j.get("retCode") != 0:
            return TickerInfo(
                ok=False,
                exchange=self.exchange,
                symbol=symbol,
                err_code=str(j.get("retCode")),
                err_msg=j.get("retMsg"),
                raw=j,
            )

        result = j.get("result", {})
        ticker_list = result.get("list", [])
        if not ticker_list:
            return TickerInfo(
                ok=False,
                exchange=self.exchange,
                symbol=symbol,
                err_code="no_data",
                err_msg="Empty ticker list",
                raw=j,
            )

        def _to_f(x):
            try:
                return float(x) if x else None
            except Exception:
                return None

        tick = ticker_list[0]
        return TickerInfo(
            ok=True,
            exchange=self.exchange,
            symbol=symbol,
            last=_to_f(tick.get("lastPrice")),
            bid=_to_f(tick.get("bid1Price")),
            ask=_to_f(tick.get("ask1Price")),
            high24h=_to_f(tick.get("highPrice24h")),
            low24h=_to_f(tick.get("lowPrice24h")),
            vol24h=_to_f(tick.get("volume24h")),
            raw=tick,
        )

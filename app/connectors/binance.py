# app/connectors/binance.py
# Week12 Day3: Binance Spot connector aligned to app.connectors.base.Connector.
# Dependency-free (urllib + stdlib only).

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


def _binance_env() -> Tuple[str, str, str, bool, float]:
    """Returns (base_url, api_key, api_secret, is_testnet, timeout_sec)"""
    # Testnet: https://testnet.binance.vision
    # Production: https://api.binance.com
    simulated = os.getenv("BINANCE_SIMULATED", "0") == "1"
    if simulated:
        default_url = "https://testnet.binance.vision"
    else:
        default_url = "https://api.binance.com"

    base_url = os.getenv("BINANCE_BASE_URL", default_url).rstrip("/")
    api_key = os.getenv("BINANCE_API_KEY", "")
    api_secret = os.getenv("BINANCE_API_SECRET", "")
    timeout_sec = float(os.getenv("BINANCE_TIMEOUT_SEC", "10"))
    return base_url, api_key, api_secret, simulated, timeout_sec


def _binance_sign(query_string: str, secret: str) -> str:
    """HMAC SHA256 signature for Binance"""
    return hmac.new(
        secret.encode("utf-8"),
        query_string.encode("utf-8"),
        hashlib.sha256
    ).hexdigest()


def _to_binance_symbol(internal_symbol: str) -> str:
    """Convert internal symbol (BTC-USDT) to Binance format (BTCUSDT)"""
    return internal_symbol.replace("-", "")


def _from_binance_symbol(binance_symbol: str) -> str:
    """Convert Binance symbol to internal format (best effort)"""
    # Common quote currencies
    for quote in ["USDT", "BUSD", "USDC", "BTC", "ETH", "BNB"]:
        if binance_symbol.endswith(quote):
            base = binance_symbol[:-len(quote)]
            return f"{base}-{quote}"
    return binance_symbol


def _binance_request(
    method: str,
    path: str,
    params: Dict[str, Any] | None = None,
    signed: bool = True
) -> Dict[str, Any]:
    """
    Make Binance API request.

    Args:
        method: HTTP method (GET, POST, DELETE)
        path: API path (e.g., /api/v3/order)
        params: Query/body parameters
        signed: Whether to sign the request
    """
    base_url, api_key, api_secret, _, timeout_sec = _binance_env()

    params = params or {}

    if signed:
        # Add timestamp and signature
        params["timestamp"] = int(time.time() * 1000)
        query_string = urlencode(params)
        signature = _binance_sign(query_string, api_secret)
        query_string += f"&signature={signature}"
    else:
        query_string = urlencode(params) if params else ""

    url = base_url + path
    if query_string:
        url += "?" + query_string

    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) bbooster-hub/0.1",
    }
    if api_key:
        headers["X-MBX-APIKEY"] = api_key

    req = urlrequest.Request(url, method=method.upper(), headers=headers)

    try:
        with urlrequest.urlopen(req, timeout=timeout_sec) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
            try:
                return json.loads(raw)
            except Exception:
                return {"code": "parse_error", "msg": "non_json_response", "raw": raw}
    except HTTPError as e:
        raw = e.read().decode("utf-8", errors="replace") if hasattr(e, "read") else str(e)
        try:
            j = json.loads(raw)
            j["_http_status"] = getattr(e, "code", None)
            return j
        except Exception:
            return {"code": "http_error", "msg": str(e), "_http_status": getattr(e, "code", None), "raw": raw}
    except URLError as e:
        return {"code": "network_error", "msg": str(e)}


def _normalize_binance_state(status: str) -> str:
    """Convert Binance order status to internal state"""
    mapping = {
        "NEW": "sent",
        "PARTIALLY_FILLED": "partial",
        "FILLED": "filled",
        "CANCELED": "canceled",
        "REJECTED": "failed",
        "EXPIRED": "expired",
        "PENDING_CANCEL": "sent",  # Still active
    }
    return mapping.get(status, "unknown")


class BinanceConnector(Connector):
    exchange = "BINANCE"

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
        Place order on Binance Spot.

        Args:
            symbol: Internal symbol (e.g., BTC-USDT)
            side: "buy" or "sell"
            qty: Quantity in base currency
            order_type: "market" or "limit"
            px: Price (required for limit orders)
            payload: Additional parameters (e.g., newClientOrderId)
        """
        binance_symbol = _to_binance_symbol(symbol)
        binance_side = side.upper()  # BUY or SELL
        binance_type = order_type.upper()  # MARKET or LIMIT

        params: Dict[str, Any] = {
            "symbol": binance_symbol,
            "side": binance_side,
            "type": binance_type,
            "quantity": str(qty),
        }

        # Limit order requires price and timeInForce
        if binance_type == "LIMIT":
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

        # Client order ID
        if payload and isinstance(payload, dict):
            cl = payload.get("newClientOrderId") or payload.get("clord_id") or payload.get("clOrdId")
            if isinstance(cl, str) and cl.strip():
                params["newClientOrderId"] = cl.strip()

        j = _binance_request("POST", "/api/v3/order", params=params)

        # Check for error
        if "code" in j and j.get("code") != 0:
            return PlaceOrderResult(
                ok=False,
                exchange=self.exchange,
                symbol=symbol,
                side=side,
                qty=float(qty),
                order_type=order_type,
                err_code=str(j.get("code", "")),
                err_msg=str(j.get("msg", "binance_error")),
                raw=j,
            )

        # Success
        order_id = j.get("orderId")
        client_order_id = j.get("clientOrderId")
        status = j.get("status", "")
        executed_qty = j.get("executedQty")
        avg_price = j.get("avgPrice") or j.get("price")

        def _to_f(x):
            try:
                return float(x)
            except Exception:
                return None

        return PlaceOrderResult(
            ok=True,
            exchange=self.exchange,
            symbol=symbol,
            side=side,
            qty=float(qty),
            order_type=order_type,
            exchange_order_id=str(order_id) if order_id else None,
            clord_id=str(client_order_id) if client_order_id else None,
            state=_normalize_binance_state(status),
            avg_px=_to_f(avg_price),
            filled_qty=_to_f(executed_qty),
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
        Get order status from Binance.

        Args:
            symbol: Internal symbol (e.g., BTC-USDT)
            exchange_order_id: Binance order ID
            clord_id: Client order ID
        """
        if not exchange_order_id and not clord_id:
            return OrderResult(
                ok=False,
                exchange=self.exchange,
                symbol=symbol,
                err_code="missing_id",
                err_msg="need exchange_order_id or clord_id",
            )

        binance_symbol = _to_binance_symbol(symbol)
        params: Dict[str, Any] = {"symbol": binance_symbol}

        if exchange_order_id:
            params["orderId"] = exchange_order_id
        if clord_id:
            params["origClientOrderId"] = clord_id

        j = _binance_request("GET", "/api/v3/order", params=params)

        # Check for error
        if "code" in j and j.get("code") != 0:
            return OrderResult(
                ok=False,
                exchange=self.exchange,
                symbol=symbol,
                err_code=str(j.get("code", "")),
                err_msg=str(j.get("msg", "binance_error")),
                raw=j,
            )

        # Success
        order_id = j.get("orderId")
        client_order_id = j.get("clientOrderId")
        status = j.get("status", "")
        executed_qty = j.get("executedQty")
        # Calculate average price from cummulativeQuoteQty / executedQty
        cumm_quote = j.get("cummulativeQuoteQty")

        def _to_f(x):
            try:
                return float(x)
            except Exception:
                return None

        avg_px = None
        exec_qty = _to_f(executed_qty)
        cumm_qty = _to_f(cumm_quote)
        if exec_qty and cumm_qty and exec_qty > 0:
            avg_px = cumm_qty / exec_qty

        return OrderResult(
            ok=True,
            exchange=self.exchange,
            symbol=symbol,
            exchange_order_id=str(order_id) if order_id else None,
            clord_id=str(client_order_id) if client_order_id else None,
            state=_normalize_binance_state(status),
            avg_px=avg_px,
            filled_qty=exec_qty,
            raw=j,
        )

    def get_balance_split(self, *, ccy: str = "USDT") -> BalanceSplit:
        """
        Get balance for a currency on Binance.

        Binance Spot uses single account (no trading/funding split).
        Returns trading = total, funding = 0.
        """
        j = _binance_request("GET", "/api/v3/account")

        # Check for error
        if "code" in j and j.get("code") != 0:
            return BalanceSplit(
                ok=False,
                exchange=self.exchange,
                ccy=ccy,
                total=0.0,
                trading=0.0,
                funding=0.0,
                err_code=str(j.get("code", "")),
                err_msg=str(j.get("msg", "binance_error")),
                raw=j,
            )

        # Find balance for currency
        balances = j.get("balances", [])
        total = 0.0
        for b in balances:
            if b.get("asset") == ccy:
                free = float(b.get("free", 0))
                locked = float(b.get("locked", 0))
                total = free + locked
                break

        return BalanceSplit(
            ok=True,
            exchange=self.exchange,
            ccy=ccy,
            total=total,
            trading=total,  # Binance Spot has no split
            funding=0.0,
            raw=j,
        )

    def get_markets(self, *, symbol: Optional[str] = None) -> List[MarketInfo]:
        """
        Get market info from Binance.

        Uses public endpoint (no auth required).
        """
        base_url, _, _, _, timeout_sec = _binance_env()
        url = f"{base_url}/api/v3/exchangeInfo"

        if symbol:
            binance_symbol = _to_binance_symbol(symbol)
            url += f"?symbol={binance_symbol}"

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
        if "code" in j:
            return [MarketInfo(exchange=self.exchange, symbol=symbol or "-", raw=j)]

        out: List[MarketInfo] = []
        for s in j.get("symbols", []):
            if s.get("status") != "TRADING":
                continue

            sym = s.get("symbol", "")
            internal_sym = _from_binance_symbol(sym)

            # Extract filters
            min_qty = None
            lot_size = None
            min_notional = None

            for f in s.get("filters", []):
                if f.get("filterType") == "LOT_SIZE":
                    min_qty = float(f.get("minQty", 0))
                    lot_size = float(f.get("stepSize", 0))
                elif f.get("filterType") == "NOTIONAL":
                    min_notional = float(f.get("minNotional", 0))

            out.append(
                MarketInfo(
                    exchange=self.exchange,
                    symbol=internal_sym,
                    min_qty=min_qty,
                    lot_qty=lot_size,
                    min_notional=min_notional,
                    raw=s,
                )
            )

        return out

    def get_ticker(self, symbol: str) -> TickerInfo:
        """
        Binance 현재가 조회 (Public API)
        GET /api/v3/ticker/24hr?symbol=BTCUSDT
        """
        base_url, _, _, _, timeout_sec = _binance_env()
        binance_symbol = _to_binance_symbol(symbol)
        url = f"{base_url}/api/v3/ticker/24hr?symbol={binance_symbol}"

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

        if "code" in j:
            return TickerInfo(
                ok=False,
                exchange=self.exchange,
                symbol=symbol,
                err_code=str(j.get("code")),
                err_msg=j.get("msg"),
                raw=j,
            )

        def _to_f(x):
            try:
                return float(x) if x else None
            except Exception:
                return None

        return TickerInfo(
            ok=True,
            exchange=self.exchange,
            symbol=symbol,
            last=_to_f(j.get("lastPrice")),
            bid=_to_f(j.get("bidPrice")),
            ask=_to_f(j.get("askPrice")),
            high24h=_to_f(j.get("highPrice")),
            low24h=_to_f(j.get("lowPrice")),
            vol24h=_to_f(j.get("volume")),
            raw=j,
        )

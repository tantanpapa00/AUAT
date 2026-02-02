# app/connectors/okx.py
# Week5 Day2: OKX connector aligned to app.connectors.base.Connector.
# Dependency-free (urllib + stdlib only).

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import time
from dataclasses import asdict
from typing import Any, Dict, List, Optional, Tuple
from urllib import request as urlrequest
from urllib.error import HTTPError, URLError

from .base import (
    BalanceSplit,
    Connector,
    MarketInfo,
    OrderResult,
    PlaceOrderResult,
    OrderType,
    Side,
)


def _okx_ts() -> str:
    # OKX expects ISO8601 with milliseconds, UTC, trailing Z.
    # Using time.time() to ms precision.
    ms = int(time.time() * 1000)
    sec = ms // 1000
    msec = ms % 1000
    return time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime(sec)) + f".{msec:03d}Z"


def _b64_hmac_sha256(secret: str, msg: str) -> str:
    mac = hmac.new(secret.encode("utf-8"), msg.encode("utf-8"), hashlib.sha256).digest()
    return base64.b64encode(mac).decode("utf-8")


def _okx_env() -> Tuple[str, str, str, str, str, float]:
    # Returns (base_url, api_key, api_secret, passphrase, simulated, timeout_sec)
    base_url = os.getenv("OKX_BASE_URL", "https://www.okx.com").rstrip("/")
    api_key = os.getenv("OKX_API_KEY", "")
    api_secret = os.getenv("OKX_API_SECRET", "")
    passphrase = os.getenv("OKX_API_PASSPHRASE", "")
    simulated = os.getenv("OKX_SIMULATED", "0")
    timeout_sec = float(os.getenv("OKX_TIMEOUT_SEC", "10"))
    return base_url, api_key, api_secret, passphrase, simulated, timeout_sec


def _okx_request(method: str, path: str, query: str = "", body: Dict[str, Any] | None = None) -> Dict[str, Any]:
    base_url, api_key, api_secret, passphrase, simulated, timeout_sec = _okx_env()

    url = base_url + path + (("?" + query) if query else "")
    ts = _okx_ts()
    body_str = "" if body is None else json.dumps(body, separators=(",", ":"), ensure_ascii=False)

    prehash = f"{ts}{method.upper()}{path}{('?' + query) if query else ''}{body_str}"
    sign = _b64_hmac_sha256(api_secret, prehash)

    headers = {
        "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) bbooster-hub/0.1",
        "OK-ACCESS-KEY": api_key,
        "OK-ACCESS-SIGN": sign,
        "OK-ACCESS-TIMESTAMP": ts,
        "OK-ACCESS-PASSPHRASE": passphrase,
    }
    if simulated == "1":
        headers["x-simulated-trading"] = "1"

    data = None if body_str == "" else body_str.encode("utf-8")
    req = urlrequest.Request(url, data=data, method=method.upper(), headers=headers)

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


def okx_place_order(
    *,
    symbol: str,
    side: str,
    qty: float,
    order_type: str = "market",
    px: float | None = None,
    payload: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    # Thin functional wrapper (kept for backwards compatibility / tests)
    conn = OKXConnector()
    r = conn.place_order(symbol=symbol, side=side, qty=qty, order_type=order_type, px=px, payload=payload)
    return {"ok": r.ok, **(r.raw or {}), "_result": asdict(r)}


def okx_get_order(
    *,
    symbol: str,
    okx_order_id: str | None = None,
    okx_clord_id: str | None = None,
) -> Dict[str, Any]:
    conn = OKXConnector()
    r = conn.get_order(symbol=symbol, exchange_order_id=okx_order_id, clord_id=okx_clord_id)
    return {"ok": r.ok, **(r.raw or {}), "_result": asdict(r)}


class OKXConnector(Connector):
    exchange = "OKX"

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
        inst_id = symbol
        ord_type = "market" if order_type == "market" else "limit"

        body: Dict[str, Any] = {
            "instId": inst_id,
            "tdMode": "cash",
            "side": side,
            "ordType": ord_type,
            "sz": str(qty),
        }

        # IMPORTANT (Spot Market): Hub qty is interpreted as base currency size.
        # OKX spot market BUY defaults can interpret sz as quote currency unless tgtCcy is set.
        # To keep Hub semantics stable (qty == base size), force tgtCcy=base_ccy for market orders.
        if ord_type == "market":
            body["tgtCcy"] = "base_ccy"

        # OKX limit requires px
        if ord_type == "limit":
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
            body["px"] = str(px)

        # clOrdId: prefer payload-provided id if exists (Hub usually sets it)
        if payload and isinstance(payload, dict):
            cl = payload.get("okx_clord_id") or payload.get("clOrdId") or payload.get("clord_id")
            if isinstance(cl, str) and cl.strip():
                body["clOrdId"] = cl.strip()

        j = _okx_request("POST", "/api/v5/trade/order", body=body)

        # Normalize OKX response
        code = str(j.get("code", ""))
        if code == "0":
            data = (j.get("data") or [{}])[0] if isinstance(j.get("data"), list) else {}
            ord_id = data.get("ordId")
            clord = data.get("clOrdId") or body.get("clOrdId")
            state = data.get("state") or "submitted"
            return PlaceOrderResult(
                ok=True,
                exchange=self.exchange,
                symbol=symbol,
                side=side,
                qty=float(qty),
                order_type=order_type,
                okx_order_id=str(ord_id) if ord_id else None,
                clord_id=str(clord) if clord else None,
                state=str(state) if state else None,
                raw=j,
            )

        # error (try to preserve OKX sCode/sMsg/clOrdId if present)
        d0 = None
        try:
            if isinstance(j.get("data"), list) and j["data"]:
                d0 = j["data"][0]
        except Exception:
            d0 = None

        s_code = None
        s_msg = None
        clord = None
        if isinstance(d0, dict):
            s_code = d0.get("sCode") or d0.get("code")
            s_msg = d0.get("sMsg") or d0.get("msg")
            clord = d0.get("clOrdId") or d0.get("clordId")

        err_code = None
        if s_code:
            err_code = str(s_code)
        elif code:
            err_code = str(code)

        err_msg = str(s_msg or j.get("msg") or j.get("sMsg") or "okx_error")

        return PlaceOrderResult(
            ok=False,
            exchange=self.exchange,
            symbol=symbol,
            side=side,
            qty=float(qty),
            order_type=order_type,
            okx_order_id=None,
            clord_id=clord,
            state=None,
            err_code=err_code,
            err_msg=err_msg,
            raw=j,
        )


    def get_order(
        self,
        *,
        symbol: str,
        exchange_order_id: Optional[str] = None,
        clord_id: Optional[str] = None,
    ) -> OrderResult:
        # OKX: GET /api/v5/trade/order?instId=...&ordId=... or clOrdId=...
        if not exchange_order_id and not clord_id:
            return OrderResult(
                ok=False,
                exchange=self.exchange,
                symbol=symbol,
                err_code="missing_id",
                err_msg="need exchange_order_id or clord_id",
            )
        q = f"instId={symbol}"
        if exchange_order_id:
            q += f"&ordId={exchange_order_id}"
        if clord_id:
            q += f"&clOrdId={clord_id}"

        j = _okx_request("GET", "/api/v5/trade/order", query=q)
        code = str(j.get("code", ""))
        if code == "0":
            data = (j.get("data") or [{}])[0] if isinstance(j.get("data"), list) else {}
            state = data.get("state")
            avg_px = data.get("avgPx")
            fill_sz = data.get("fillSz")
            ord_id = data.get("ordId")
            cl_id = data.get("clOrdId")
            def _to_f(x):
                try:
                    return float(x)
                except Exception:
                    return None
            return OrderResult(
                ok=True,
                exchange=self.exchange,
                symbol=symbol,
                okx_order_id=str(ord_id) if ord_id else None,
                clord_id=str(cl_id) if cl_id else None,
                state=str(state) if state else None,
                avg_px=_to_f(avg_px),
                filled_qty=_to_f(fill_sz),
                raw=j,
            )

        return OrderResult(
            ok=False,
            exchange=self.exchange,
            symbol=symbol,
            err_code=code or None,
            err_msg=str(j.get("msg") or j.get("sMsg") or "okx_error"),
            raw=j,
        )

    def get_balance_split(self, *, ccy: str = "USDT") -> BalanceSplit:
        # OKX: /api/v5/account/balance?ccy=USDT returns total but not split, funding requires asset endpoints.
        # We keep a best-effort split compatible with existing /diag/okx-balance-split patterns:
        # - trading: account balance
        # - funding: funding balance
        # - total: trading + funding
        #
        # trading balance
        j_tr = _okx_request("GET", "/api/v5/account/balance", query=f"ccy={ccy}")
        # funding balance
        j_fd = _okx_request("GET", "/api/v5/asset/balances", query=f"ccy={ccy}")

        def _extract_total(j: Dict[str, Any]) -> float:
            try:
                if str(j.get("code", "")) != "0":
                    return 0.0
                data = j.get("data") or []
                if not data:
                    return 0.0
                # account/balance: data[0].details[0].cashBal
                if "details" in data[0]:
                    det = data[0].get("details") or []
                    if det:
                        return float(det[0].get("cashBal") or 0.0)
                # asset/balances: data[0].bal
                if "bal" in data[0]:
                    return float(data[0].get("bal") or 0.0)
            except Exception:
                return 0.0
            return 0.0

        trading = _extract_total(j_tr)
        funding = _extract_total(j_fd)
        total = trading + funding

        ok = (str(j_tr.get("code", "")) == "0") or (str(j_fd.get("code", "")) == "0")
        if not ok:
            return BalanceSplit(
                ok=False,
                exchange=self.exchange,
                ccy=ccy,
                total=0.0,
                trading=0.0,
                funding=0.0,
                err_code=str(j_tr.get("code") or j_fd.get("code") or "") or None,
                err_msg=str(j_tr.get("msg") or j_fd.get("msg") or "okx_error"),
                raw={"trading": j_tr, "funding": j_fd},
            )

        return BalanceSplit(
            ok=True,
            exchange=self.exchange,
            ccy=ccy,
            total=float(total),
            trading=float(trading),
            funding=float(funding),
            raw={"trading": j_tr, "funding": j_fd},
        )

    def get_markets(self, *, symbol: Optional[str] = None) -> List[MarketInfo]:
        # Public endpoint, no auth needed, but we reuse _okx_request which signs.
        # For public, OKX accepts unsigned too; signing shouldn't break, but if keys absent it might fail.
        # Therefore implement a lightweight unsigned public request.
        base_url, _, _, _, _, timeout_sec = _okx_env()
        inst_id = symbol or ""
        url = f"{base_url}/api/v5/public/instruments?instType=SPOT" + (f"&instId={inst_id}" if inst_id else "")

        try:
            req_pub = urlrequest.Request(url, headers={"Accept":"application/json","User-Agent":"Mozilla/5.0 (Windows NT 10.0; Win64; x64) bbooster-hub/0.1"})
            with urlrequest.urlopen(req_pub, timeout=timeout_sec) as resp:
                raw = resp.read().decode("utf-8", errors="replace")
                j = json.loads(raw)
        except Exception as e:
            return [MarketInfo(exchange=self.exchange, symbol=inst_id or "-", raw={"error": str(e)})]

        if str(j.get("code", "")) != "0":
            return [MarketInfo(exchange=self.exchange, symbol=inst_id or "-", raw=j)]

        out: List[MarketInfo] = []
        for it in (j.get("data") or []):
            sym = it.get("instId") or inst_id or "-"
            def _to_f(x):
                try:
                    return float(x)
                except Exception:
                    return None
            out.append(
                MarketInfo(
                    exchange=self.exchange,
                    symbol=str(sym),
                    min_qty=_to_f(it.get("minSz")),
                    lot_qty=_to_f(it.get("lotSz")),
                    min_notional=_to_f(it.get("minNotional")),
                    raw=it,
                )
            )
        return out

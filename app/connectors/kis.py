# app/connectors/kis.py
# Week5 Day4 (updated): KIS connector aligned to official open-trading-api sample (kis_auth.py)
# - dependency-free (urllib)
# - implements Connector protocol (see app/connectors/base.py)
# - scope: tokenP + request wrapper + hashkey helper (NO real trading yet)

from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, Optional, Tuple

from .base import (
    BalanceSplit,
    Connector,
    MarketInfo,
    OrderResult,
    PlaceOrderResult,
    Side,
    OrderType,
)


# Official sample (open-trading-api) defaults:
# prod: https://openapi.koreainvestment.com:9443
# vps : https://openapivts.koreainvestment.com:29443
DEFAULT_PROD_BASE = "https://openapi.koreainvestment.com:9443"
DEFAULT_VPS_BASE = "https://openapivts.koreainvestment.com:29443"

DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/114.0.0.0 Safari/537.36"
)


@dataclass
class KISToken:
    access_token: str
    token_type: str = "Bearer"
    expires_at: float = 0.0  # epoch seconds

    @property
    def is_valid(self) -> bool:
        # refresh slightly earlier
        return bool(self.access_token) and (time.time() + 30.0) < float(self.expires_at or 0.0)


class KISConnector(Connector):
    """
    KIS connector (Week5 Day4).
    - auth: OAuth2 tokenP (client_credentials)
    - helper: /uapi/hashkey for POST body hash
    - request wrapper: dependency-free urllib
    - trading endpoints: NOT implemented yet (Week6~7)
    """

    exchange = "KIS"

    def __init__(self, *, timeout_sec: float = 10.0):
        self.timeout_sec = float(timeout_sec)
        self._token: Optional[KISToken] = None

        # Environment selection (align to official sample)
        # - KIS_SVR: 'prod' or 'vps' (optional)
        # - KIS_SIMULATED: '1' => vps (optional)
        self.svr = (os.getenv("KIS_SVR", "") or "").strip().lower()
        if self.svr not in ("prod", "vps"):
            self.svr = "vps" if os.getenv("KIS_SIMULATED", "0") == "1" else "prod"

        # Base URL
        # If KIS_BASE_URL is set, it overrides everything (advanced).
        base_override = (os.getenv("KIS_BASE_URL", "") or "").strip()
        if base_override:
            self.base_url = base_override.rstrip("/")
        else:
            self.base_url = (DEFAULT_VPS_BASE if self.svr == "vps" else DEFAULT_PROD_BASE).rstrip("/")

        # Credentials
        # - prod keys: KIS_APP_KEY / KIS_APP_SECRET
        # - vps keys (optional): KIS_PAPER_APP_KEY / KIS_PAPER_APP_SECRET
        self.app_key = (os.getenv("KIS_APP_KEY", "") or "").strip()
        self.app_secret = (os.getenv("KIS_APP_SECRET", "") or "").strip()

        if self.svr == "vps":
            paper_key = (os.getenv("KIS_PAPER_APP_KEY", "") or "").strip()
            paper_sec = (os.getenv("KIS_PAPER_APP_SECRET", "") or "").strip()
            if paper_key and paper_sec:
                self.app_key = paper_key
                self.app_secret = paper_sec

        self.user_agent = (os.getenv("KIS_USER_AGENT", "") or "").strip() or DEFAULT_USER_AGENT

    # ---------------------
    # helpers
    # ---------------------
    def _base_headers(self) -> Dict[str, str]:
        # Align to sample _base_headers:
        # Content-Type: application/json
        # Accept: text/plain
        # charset: UTF-8
        # User-Agent: my_agent
        return {
            "Content-Type": "application/json",
            "Accept": "text/plain",
            "charset": "UTF-8",
            "User-Agent": self.user_agent,
        }

    def _ensure_creds(self) -> Tuple[bool, str]:
        if not self.app_key:
            return False, "missing KIS_APP_KEY (or KIS_PAPER_APP_KEY for vps)"
        if not self.app_secret:
            return False, "missing KIS_APP_SECRET (or KIS_PAPER_APP_SECRET for vps)"
        return True, "ok"

    def _token_url(self) -> str:
        return f"{self.base_url}/oauth2/tokenP"

    # ---------------------
    # tokenP
    # ---------------------
    def get_access_token(self, *, force: bool = False) -> Tuple[bool, str, Optional[KISToken]]:
        """Returns (ok, msg, token_obj)."""
        ok, msg = self._ensure_creds()
        if not ok:
            return False, msg, None

        if not force and self._token is not None and self._token.is_valid:
            return True, "cached", self._token

        body = {
            "grant_type": "client_credentials",
            "appkey": self.app_key,
            "appsecret": self.app_secret,
        }
        data = json.dumps(body, ensure_ascii=False).encode("utf-8")
        headers = self._base_headers()

        req = urllib.request.Request(
            self._token_url(),
            data=data,
            headers=headers,
            method="POST",
        )

        try:
            with urllib.request.urlopen(req, timeout=self.timeout_sec) as r:
                status = int(getattr(r, "status", 200) or 200)
                raw = r.read().decode("utf-8", errors="replace")

            if status != 200:
                return False, f"http_status:{status}", None

            j = json.loads(raw) if raw else {}
            access_token = (j.get("access_token") or "").strip()
            token_type = (j.get("token_type") or "Bearer").strip()

            # Official sample also returns 'access_token_token_expired' like: "YYYY-MM-DD HH:MM:SS"
            exp_str = (j.get("access_token_token_expired") or "").strip()
            expires_in = float(j.get("expires_in") or 0.0)

            expires_at = 0.0
            if exp_str:
                try:
                    dt = datetime.strptime(exp_str, "%Y-%m-%d %H:%M:%S")
                    # dt is naive; time.mktime uses local timezone (KST on user's machine)
                    expires_at = float(time.mktime(dt.timetuple()))
                except Exception:
                    expires_at = 0.0
            if not expires_at and expires_in > 0:
                expires_at = time.time() + max(0.0, expires_in)

            if not access_token:
                return False, f"token_missing:{raw[:200]}", None

            tok = KISToken(access_token=access_token, token_type=token_type, expires_at=expires_at)
            self._token = tok
            return True, "ok", tok

        except urllib.error.HTTPError as e:
            try:
                err = e.read().decode("utf-8", errors="replace")
            except Exception:
                err = str(e)
            return False, f"http_error:{getattr(e,'code',0)}:{err[:200]}", None
        except Exception as e:
            return False, f"token_error:{type(e).__name__}:{e}", None

    # ---------------------
    # request wrapper
    # ---------------------
    def request(
        self,
        *,
        method: str,
        path: str,
        params: Optional[Dict[str, Any]] = None,
        json_body: Optional[Dict[str, Any]] = None,
        headers: Optional[Dict[str, str]] = None,
        require_token: bool = True,
    ) -> Tuple[bool, int, Optional[Dict[str, Any]], str]:
        """Returns (ok, http_status, json_or_none, raw_text)."""
        method_u = (method or "GET").upper()
        path = "/" + (path.lstrip("/"))
        url = f"{self.base_url}{path}"

        if params:
            qs = urllib.parse.urlencode(params)
            url = f"{url}?{qs}"

        hdrs: Dict[str, str] = self._base_headers()
        if headers:
            hdrs.update(headers)

        if require_token:
            ok, msg, tok = self.get_access_token()
            if not ok or tok is None:
                return False, 0, None, msg
            hdrs["authorization"] = f"{tok.token_type} {tok.access_token}"
            hdrs["appkey"] = self.app_key
            hdrs["appsecret"] = self.app_secret

        data = None
        if json_body is not None:
            data = json.dumps(json_body, ensure_ascii=False).encode("utf-8")

        req = urllib.request.Request(url, data=data, headers=hdrs, method=method_u)

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

    # ---------------------
    # hashkey helper
    # ---------------------
    def make_hashkey(self, *, body: Dict[str, Any]) -> Tuple[bool, str]:
        """Returns (ok, hashkey_or_msg)."""
        ok, status, j, raw = self.request(
            method="POST",
            path="/uapi/hashkey",
            json_body=body,
            require_token=True,
        )
        if not ok:
            return False, f"hashkey_failed({status}):{raw[:200] if raw else ''}"
        hk = (j or {}).get("HASH") or ""
        if not hk:
            return False, f"hashkey_missing:{raw[:200] if raw else ''}"
        return True, hk

    # ---------------------
    # Connector protocol stubs (Week6~7)
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
        return PlaceOrderResult(
            ok=False,
            exchange=self.exchange,
            symbol=symbol,
            side=side,
            qty=float(qty),
            order_type=order_type,
            err_code="not_implemented",
            err_msg="KIS place_order not implemented yet (Week6~7 scope)",
        )

    def get_order(
        self,
        *,
        symbol: str,
        exchange_order_id: Optional[str] = None,
        clord_id: Optional[str] = None,
    ) -> OrderResult:
        return OrderResult(
            ok=False,
            exchange=self.exchange,
            symbol=symbol,
            okx_order_id=exchange_order_id,
            clord_id=clord_id,
            err_code="not_implemented",
            err_msg="KIS get_order not implemented yet (Week6~7 scope)",
        )

    def get_balance_split(self, *, ccy: str = "KRW") -> BalanceSplit:
        return BalanceSplit(
            ok=False,
            exchange=self.exchange,
            ccy=ccy,
            total=0.0,
            trading=0.0,
            funding=0.0,
            err_code="not_implemented",
            err_msg="KIS balance not implemented yet (Week6 scope)",
        )

    def get_markets(self, *, symbol: Optional[str] = None) -> list[MarketInfo]:
        return []

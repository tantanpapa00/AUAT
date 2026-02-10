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
    TickerInfo,
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
    # Connector protocol (Week7)
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
        """KIS 국내주식 현금 주문 (매수/매도)."""
        import os as _os

        cano = (_os.getenv("KIS_CANO") or "").strip()
        acnt_prdt_cd = (_os.getenv("KIS_ACNT_PRDT_CD") or "").strip()
        if not cano or not acnt_prdt_cd:
            return PlaceOrderResult(
                ok=False, exchange=self.exchange, symbol=symbol, side=side,
                qty=float(qty), order_type=order_type,
                err_code="missing_env", err_msg="KIS_CANO or KIS_ACNT_PRDT_CD missing",
            )

        # TR ID: 매수 TTTC0802U/VTTC0802U, 매도 TTTC0801U/VTTC0801U
        if side == "buy":
            tr_id = "TTTC0802U" if self.svr == "prod" else "VTTC0802U"
        else:
            tr_id = "TTTC0801U" if self.svr == "prod" else "VTTC0801U"

        # 주문구분: 00=지정가, 01=시장가
        ord_dvsn = "01" if order_type == "market" else "00"
        ord_unpr = "0" if order_type == "market" else str(int(px or 0))

        body = {
            "CANO": cano,
            "ACNT_PRDT_CD": acnt_prdt_cd,
            "PDNO": symbol,  # 종목코드 6자리
            "ORD_DVSN": ord_dvsn,
            "ORD_QTY": str(int(qty)),
            "ORD_UNPR": ord_unpr,
        }

        try:
            ok, hk = self.make_hashkey(body=body)
            headers = {"tr_id": tr_id, "custtype": "P", "tr_cont": ""}
            if ok and hk:
                headers["hashkey"] = hk

            req_ok, status, j, raw = self.request(
                method="POST",
                path="/uapi/domestic-stock/v1/trading/order-cash",
                json_body=body,
                headers=headers,
                require_token=True,
            )

            if not req_ok or status != 200:
                return PlaceOrderResult(
                    ok=False, exchange=self.exchange, symbol=symbol, side=side,
                    qty=float(qty), order_type=order_type,
                    err_code=f"http_{status}", err_msg=raw[:200] if raw else "request_failed",
                    raw={"status": status, "raw": raw},
                )

            # 응답 파싱
            rt_cd = (j or {}).get("rt_cd")
            output = (j or {}).get("output") or {}
            odno = output.get("ODNO")  # 주문번호
            ord_tmd = output.get("ORD_TMD")  # 주문시각

            if rt_cd != "0":
                return PlaceOrderResult(
                    ok=False, exchange=self.exchange, symbol=symbol, side=side,
                    qty=float(qty), order_type=order_type,
                    err_code=rt_cd, err_msg=(j or {}).get("msg1", "kis_error"),
                    raw=j,
                )

            return PlaceOrderResult(
                ok=True, exchange=self.exchange, symbol=symbol, side=side,
                qty=float(qty), order_type=order_type,
                exchange_order_id=odno,  # KIS 주문번호 (ODNO)
                okx_order_id=odno,  # backward compat
                clord_id=ord_tmd,
                state="submitted",
                raw=j,
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
        clord_id: Optional[str] = None,
    ) -> OrderResult:
        """KIS 주문 체결 조회."""
        import os as _os

        cano = (_os.getenv("KIS_CANO") or "").strip()
        acnt_prdt_cd = (_os.getenv("KIS_ACNT_PRDT_CD") or "").strip()
        if not cano or not acnt_prdt_cd:
            return OrderResult(
                ok=False, exchange=self.exchange, symbol=symbol,
                err_code="missing_env", err_msg="KIS_CANO or KIS_ACNT_PRDT_CD missing",
            )

        # TR ID: TTTC8001R (실전), VTTC8001R (모의)
        tr_id = "TTTC8001R" if self.svr == "prod" else "VTTC8001R"

        # 오늘 날짜
        today = datetime.now().strftime("%Y%m%d")

        params = {
            "CANO": cano,
            "ACNT_PRDT_CD": acnt_prdt_cd,
            "INQR_STRT_DT": today,
            "INQR_END_DT": today,
            "SLL_BUY_DVSN_CD": "00",  # 전체
            "INQR_DVSN": "00",
            "PDNO": symbol or "",
            "CCLD_DVSN": "00",
            "ORD_GNO_BRNO": "",
            "ODNO": exchange_order_id or "",
            "INQR_DVSN_3": "00",
            "INQR_DVSN_1": "",
            "CTX_AREA_FK100": "",
            "CTX_AREA_NK100": "",
        }

        try:
            req_ok, status, j, raw = self.request(
                method="GET",
                path="/uapi/domestic-stock/v1/trading/inquire-daily-ccld",
                params=params,
                headers={"tr_id": tr_id, "custtype": "P", "tr_cont": ""},
                require_token=True,
            )

            if not req_ok or status != 200:
                return OrderResult(
                    ok=False, exchange=self.exchange, symbol=symbol,
                    err_code=f"http_{status}", err_msg=raw[:200] if raw else "request_failed",
                    raw={"status": status, "raw": raw},
                )

            rt_cd = (j or {}).get("rt_cd")
            if rt_cd != "0":
                return OrderResult(
                    ok=False, exchange=self.exchange, symbol=symbol,
                    err_code=rt_cd, err_msg=(j or {}).get("msg1", "kis_error"),
                    raw=j,
                )

            # output1에서 주문번호로 찾기
            output1 = (j or {}).get("output1") or []
            found = None
            for item in output1:
                if exchange_order_id and item.get("odno") == exchange_order_id:
                    found = item
                    break
            if not found and output1:
                found = output1[0]

            if not found:
                return OrderResult(
                    ok=True, exchange=self.exchange, symbol=symbol,
                    exchange_order_id=exchange_order_id,
                    okx_order_id=exchange_order_id,  # backward compat
                    state="not_found",
                    raw=j,
                )

            # 체결 정보 추출
            def _to_f(x):
                try:
                    return float(x) if x else None
                except:
                    return None

            return OrderResult(
                ok=True, exchange=self.exchange, symbol=symbol,
                exchange_order_id=found.get("odno"),
                okx_order_id=found.get("odno"),  # backward compat
                state=found.get("ord_dvsn_name", "unknown"),
                filled_qty=_to_f(found.get("tot_ccld_qty")),
                avg_px=_to_f(found.get("avg_prvs")),
                raw=j,
            )
        except Exception as e:
            return OrderResult(
                ok=False, exchange=self.exchange, symbol=symbol,
                err_code="exception", err_msg=f"{type(e).__name__}: {e}",
            )

    def get_balance_split(self, *, ccy: str = "KRW") -> BalanceSplit:
        """KIS 국내주식 잔고조회 (v1_국내주식-006).

        TR ID: TTTC8434R (prod) / VTTC8434R (vps)
        Returns:
            - total: 총 평가금액 (tot_evlu_amt)
            - trading: 예수금 총액 (dnca_tot_amt) - 매매 가능 현금
            - funding: 유가증권 평가금액 (scts_evlu_amt) - 보유주식 평가액
        """
        import os as _os

        cano = (_os.getenv("KIS_CANO") or "").strip()
        acnt_prdt_cd = (_os.getenv("KIS_ACNT_PRDT_CD") or "").strip()
        if not cano or not acnt_prdt_cd:
            return BalanceSplit(
                ok=False,
                exchange=self.exchange,
                ccy=ccy,
                total=0.0,
                trading=0.0,
                funding=0.0,
                err_code="missing_env",
                err_msg="KIS_CANO or KIS_ACNT_PRDT_CD missing",
            )

        tr_id = "TTTC8434R" if self.svr == "prod" else "VTTC8434R"

        params = {
            "CANO": cano,
            "ACNT_PRDT_CD": acnt_prdt_cd,
            "AFHR_FLPR_YN": "N",
            "OFL_YN": "",
            "INQR_DVSN": "01",
            "UNPR_DVSN": "01",
            "FUND_STTL_ICLD_YN": "N",
            "FNCG_AMT_AUTO_RDPT_YN": "N",
            "PRCS_DVSN": "00",
            "CTX_AREA_FK100": "",
            "CTX_AREA_NK100": "",
        }

        try:
            req_ok, status, j, raw = self.request(
                method="GET",
                path="/uapi/domestic-stock/v1/trading/inquire-balance",
                params=params,
                headers={"tr_id": tr_id, "custtype": "P", "tr_cont": ""},
                require_token=True,
            )

            if not req_ok or status != 200:
                return BalanceSplit(
                    ok=False,
                    exchange=self.exchange,
                    ccy=ccy,
                    total=0.0,
                    trading=0.0,
                    funding=0.0,
                    err_code=f"http_{status}",
                    err_msg=raw[:200] if raw else "request_failed",
                    raw={"status": status, "raw": raw},
                )

            rt_cd = (j or {}).get("rt_cd")
            if rt_cd != "0":
                return BalanceSplit(
                    ok=False,
                    exchange=self.exchange,
                    ccy=ccy,
                    total=0.0,
                    trading=0.0,
                    funding=0.0,
                    err_code=rt_cd,
                    err_msg=(j or {}).get("msg1", "kis_error"),
                    raw=j,
                )

            # output2에서 잔고 정보 추출
            output2 = (j or {}).get("output2") or []
            out2 = output2[0] if isinstance(output2, list) and len(output2) > 0 else {}

            def _to_f(x):
                try:
                    if x is None:
                        return 0.0
                    s = str(x).strip()
                    if s == "":
                        return 0.0
                    return float(s)
                except Exception:
                    return 0.0

            # dnca_tot_amt: 예수금 총액 (매매 가능 현금)
            # tot_evlu_amt: 총 평가금액
            # scts_evlu_amt: 유가증권 평가금액 (보유주식)
            trading = _to_f(out2.get("dnca_tot_amt"))
            funding = _to_f(out2.get("scts_evlu_amt"))
            total = _to_f(out2.get("tot_evlu_amt"))

            # tot_evlu_amt가 없으면 trading + funding으로 계산
            if total == 0.0 and (trading > 0 or funding > 0):
                total = trading + funding

            return BalanceSplit(
                ok=True,
                exchange=self.exchange,
                ccy=ccy,
                total=total,
                trading=trading,
                funding=funding,
                raw=j,
            )
        except Exception as e:
            return BalanceSplit(
                ok=False,
                exchange=self.exchange,
                ccy=ccy,
                total=0.0,
                trading=0.0,
                funding=0.0,
                err_code="exception",
                err_msg=f"{type(e).__name__}: {e}",
            )

    def get_markets(self, *, symbol: Optional[str] = None) -> list[MarketInfo]:
        """KIS 종목 정보 조회 (주식현재가 시세).

        TR ID: FHKST01010100 (prod/vps 동일)
        NOTE: KIS는 전체 종목 목록 API가 없으므로 symbol 필수.
              symbol 없으면 빈 리스트 반환.
        """
        if not symbol:
            return []

        # 현재가 시세 조회 (공개 API, 인증 필요)
        tr_id = "FHKST01010100"

        params = {
            "FID_COND_MRKT_DIV_CODE": "J",  # J: 주식, ETF, ETN
            "FID_INPUT_ISCD": symbol,
        }

        try:
            req_ok, status, j, raw = self.request(
                method="GET",
                path="/uapi/domestic-stock/v1/quotations/inquire-price",
                params=params,
                headers={"tr_id": tr_id, "custtype": "P", "tr_cont": ""},
                require_token=True,
            )

            if not req_ok or status != 200:
                return [MarketInfo(
                    exchange=self.exchange,
                    symbol=symbol,
                    raw={"error": f"http_{status}", "raw": raw[:200] if raw else None},
                )]

            rt_cd = (j or {}).get("rt_cd")
            if rt_cd != "0":
                return [MarketInfo(
                    exchange=self.exchange,
                    symbol=symbol,
                    raw={"error": rt_cd, "msg": (j or {}).get("msg1")},
                )]

            output = (j or {}).get("output") or {}

            def _to_f(x):
                try:
                    if x is None:
                        return None
                    s = str(x).strip()
                    if s == "":
                        return None
                    return float(s)
                except Exception:
                    return None

            # 국내 주식은 일반적으로 1주 단위 거래
            # stck_mxpr: 상한가, stck_llam: 하한가, stck_prpr: 현재가
            return [MarketInfo(
                exchange=self.exchange,
                symbol=symbol,
                min_qty=1.0,  # 국내 주식 최소 거래단위
                lot_qty=1.0,  # 1주 단위
                min_notional=None,  # 국내 주식은 최소 주문금액 제한 없음
                raw=output,
            )]
        except Exception as e:
            return [MarketInfo(
                exchange=self.exchange,
                symbol=symbol,
                raw={"error": "exception", "detail": f"{type(e).__name__}: {e}"},
            )]

    def get_domestic_price(self, symbol: str) -> Optional[Dict[str, Any]]:
        """
        KIS 국내주식 현재가 조회
        symbol: "005930" (삼성전자), "000660" (SK하이닉스) 등 6자리 종목코드
        Returns: {"price": 55000, "open": 54500, "high": 56000, "low": 54000, "volume": 12345678}
                 or None on failure
        """
        ok, status, j, raw = self.request(
            method="GET",
            path="/uapi/domestic-stock/v1/quotations/inquire-price",
            params={
                "FID_COND_MRKT_DIV_CODE": "J",  # J: 주식, ETF, ETN
                "FID_INPUT_ISCD": symbol,
            },
            headers={
                "tr_id": "FHKST01010100",
                "custtype": "P",
            },
            require_token=True,
        )

        if not ok or status != 200:
            return None

        rt_cd = (j or {}).get("rt_cd")
        if rt_cd != "0":
            return None

        output = (j or {}).get("output") or {}
        try:
            return {
                "price": float(output.get("stck_prpr", 0)),
                "open": float(output.get("stck_oprc", 0)),
                "high": float(output.get("stck_hgpr", 0)),
                "low": float(output.get("stck_lwpr", 0)),
                "volume": int(output.get("acml_vol", 0)),
                "change": float(output.get("prdy_vrss", 0)),
                "change_pct": float(output.get("prdy_ctrt", 0)),
            }
        except (ValueError, TypeError):
            return None

    def get_ticker(self, symbol: str, market: str = "KR") -> TickerInfo:
        """
        KIS 통합 현재가 조회
        market="KR": 국내주식 (get_domestic_price)
        market="US": 해외주식 (get_overseas_price)
        """
        if market == "US":
            price = self.get_overseas_price(symbol)
            if price is None:
                return TickerInfo(
                    ok=False,
                    exchange=self.exchange,
                    symbol=symbol,
                    err_code="price_fetch_failed",
                    err_msg="Failed to get overseas price",
                )
            return TickerInfo(
                ok=True,
                exchange=self.exchange,
                symbol=symbol,
                last=price,
            )

        # market == "KR" (default)
        data = self.get_domestic_price(symbol)
        if data is None:
            return TickerInfo(
                ok=False,
                exchange=self.exchange,
                symbol=symbol,
                err_code="price_fetch_failed",
                err_msg="Failed to get domestic price",
            )
        return TickerInfo(
            ok=True,
            exchange=self.exchange,
            symbol=symbol,
            last=data["price"],
            high24h=data.get("high"),
            low24h=data.get("low"),
            vol24h=float(data.get("volume", 0)),
            raw=data,
        )

    # ---------------------
    # 해외주식 API (KIS_US)
    # ---------------------
    def get_overseas_price(self, symbol: str, exchange_code: str = "NAS") -> Optional[float]:
        """
        KIS 해외주식 현재가 조회
        exchange_code: NAS(나스닥), NYS(뉴욕), AMS(아멕스)
        Returns: 현재가 (float) or None
        """
        # 거래소 코드 자동 시도 (NAS → NYS → AMS)
        exchanges_to_try = [exchange_code] if exchange_code else ["NAS", "NYS", "AMS"]
        if exchange_code not in exchanges_to_try:
            exchanges_to_try = [exchange_code] + ["NAS", "NYS", "AMS"]

        for excd in exchanges_to_try:
            ok, status, j, raw = self.request(
                method="GET",
                path="/uapi/overseas-price/v1/quotations/price",
                params={
                    "AUTH": "",
                    "EXCD": excd,
                    "SYMB": symbol.upper(),
                },
                headers={
                    "tr_id": "HHDFS00000300",
                    "custtype": "P",
                },
                require_token=True,
            )

            if not ok or status != 200:
                continue

            rt_cd = (j or {}).get("rt_cd")
            if rt_cd != "0":
                continue

            output = (j or {}).get("output") or {}
            last_price = output.get("last") or output.get("stck_prpr")
            if last_price:
                try:
                    return float(last_price)
                except (ValueError, TypeError):
                    continue

        return None

    def place_order_overseas(
        self,
        *,
        symbol: str,
        side: Side,
        qty: float,
        price: float,
        exchange_code: str = "NASD",
        payload: Optional[Dict[str, Any]] = None,
    ) -> PlaceOrderResult:
        """
        KIS 해외주식 주문 (지정가)
        exchange_code: NASD(나스닥), NYSE(뉴욕), AMEX(아멕스) - D가 붙음
        price: 현재가 (get_overseas_price로 미리 조회)
        """
        import os as _os

        cano = (_os.getenv("KIS_CANO") or "").strip()
        acnt_prdt_cd = (_os.getenv("KIS_ACNT_PRDT_CD") or "01").strip()
        if not cano:
            return PlaceOrderResult(
                ok=False, exchange="KIS_US", symbol=symbol, side=side,
                qty=float(qty), order_type="limit",
                err_code="missing_env", err_msg="KIS_CANO missing",
            )

        # TR ID: 미국 주식
        # 모의: VTTS0311U(매수), VTTS0312U(매도)
        # 실전: TTTS0311U(매수), TTTS0312U(매도)
        if side == "buy":
            tr_id = "TTTS0311U" if self.svr == "prod" else "VTTS0311U"
        else:
            tr_id = "TTTS0312U" if self.svr == "prod" else "VTTS0312U"

        # 거래소코드 정규화 (NAS → NASD 등)
        excd_map = {"NAS": "NASD", "NYS": "NYSE", "AMS": "AMEX"}
        ovrs_excg_cd = excd_map.get(exchange_code.upper(), exchange_code.upper())

        body = {
            "CANO": cano[:8],
            "ACNT_PRDT_CD": acnt_prdt_cd[:2] if len(acnt_prdt_cd) >= 2 else "01",
            "OVRS_EXCG_CD": ovrs_excg_cd,
            "PDNO": symbol.upper(),
            "ORD_DVSN": "00",  # 지정가
            "ORD_QTY": str(int(qty)),
            "OVRS_ORD_UNPR": f"{price:.2f}",
        }

        try:
            ok_hk, hk = self.make_hashkey(body=body)
            headers = {"tr_id": tr_id, "custtype": "P", "tr_cont": ""}
            if ok_hk and hk:
                headers["hashkey"] = hk

            req_ok, status, j, raw = self.request(
                method="POST",
                path="/uapi/overseas-stock/v1/trading/order",
                json_body=body,
                headers=headers,
                require_token=True,
            )

            if not req_ok or status != 200:
                return PlaceOrderResult(
                    ok=False, exchange="KIS_US", symbol=symbol, side=side,
                    qty=float(qty), order_type="limit",
                    err_code=f"http_{status}", err_msg=raw[:200] if raw else "request_failed",
                    raw={"status": status, "raw": raw},
                )

            rt_cd = (j or {}).get("rt_cd")
            output = (j or {}).get("output") or {}
            odno = output.get("ODNO") or output.get("odno")  # 주문번호
            ord_tmd = output.get("ORD_TMD")  # 주문시각

            if rt_cd != "0":
                return PlaceOrderResult(
                    ok=False, exchange="KIS_US", symbol=symbol, side=side,
                    qty=float(qty), order_type="limit",
                    err_code=rt_cd, err_msg=(j or {}).get("msg1", "kis_us_error"),
                    raw=j,
                )

            return PlaceOrderResult(
                ok=True, exchange="KIS_US", symbol=symbol, side=side,
                qty=float(qty), order_type="limit",
                exchange_order_id=odno,
                raw={"odno": odno, "ord_tmd": ord_tmd, "response": j},
            )

        except Exception as e:
            return PlaceOrderResult(
                ok=False, exchange="KIS_US", symbol=symbol, side=side,
                qty=float(qty), order_type="limit",
                err_code="exception", err_msg=f"{type(e).__name__}: {e}",
            )

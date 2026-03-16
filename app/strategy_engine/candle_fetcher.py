# app/strategy_engine/candle_fetcher.py
"""
Candle Fetcher - OHLCV data retrieval and caching.

Fetches candle data from exchanges and caches in DB.
Supports multiple timeframes and exchanges.

Architecture:
- Fetch from exchange API (OKX, Binance, Bybit, Upbit)
- Cache in candles table
- Return as numpy arrays for indicator calculation
"""

from typing import List, Optional, Tuple, Dict, Any
from dataclasses import dataclass
from datetime import datetime, timezone, timedelta
import time
import json
import logging
import urllib.error

import numpy as np
from sqlalchemy.orm import Session

from .models import Candle

logger = logging.getLogger(__name__)


def _get_db_session() -> Optional[Session]:
    """Get database session for candle caching."""
    try:
        from app.db import SessionLocal
        return SessionLocal()
    except Exception as e:
        logger.warning(f"DB session 생성 실패 (캐시 비활성화): {e}")
        return None


def _get_candle_cache_model():
    """Get CandleCache model."""
    try:
        from app.models import CandleCache
        return CandleCache
    except Exception as e:
        logger.warning(f"CandleCache 모델 로드 실패: {e}")
        return None


# Timeframe to milliseconds mapping
TF_TO_MS: Dict[str, int] = {
    "1m": 60 * 1000,
    "3m": 3 * 60 * 1000,
    "5m": 5 * 60 * 1000,
    "15m": 15 * 60 * 1000,
    "30m": 30 * 60 * 1000,
    "1h": 60 * 60 * 1000,
    "2h": 2 * 60 * 60 * 1000,
    "4h": 4 * 60 * 60 * 1000,
    "6h": 6 * 60 * 60 * 1000,
    "12h": 12 * 60 * 60 * 1000,
    "1D": 24 * 60 * 60 * 1000,
    "1W": 7 * 24 * 60 * 60 * 1000,
    # Uppercase variants
    "1H": 60 * 60 * 1000,
    "2H": 2 * 60 * 60 * 1000,
    "4H": 4 * 60 * 60 * 1000,
    "6H": 6 * 60 * 60 * 1000,
    "12H": 12 * 60 * 60 * 1000,
}

# Exchange timeframe format mapping
EXCHANGE_TF_MAP: Dict[str, Dict[str, str]] = {
    "OKX": {
        "1m": "1m", "3m": "3m", "5m": "5m", "15m": "15m", "30m": "30m",
        "1h": "1H", "2h": "2H", "4h": "4H", "6h": "6H", "12h": "12H",
        "1H": "1H", "2H": "2H", "4H": "4H", "6H": "6H", "12H": "12H",
        "1D": "1D", "1W": "1W",
    },
    "BINANCE": {
        "1m": "1m", "3m": "3m", "5m": "5m", "15m": "15m", "30m": "30m",
        "1h": "1h", "2h": "2h", "4h": "4h", "6h": "6h", "12h": "12h",
        "1H": "1h", "2H": "2h", "4H": "4h", "6H": "6h", "12H": "12h",
        "1D": "1d", "1W": "1w",
    },
    "BYBIT": {
        "1m": "1", "3m": "3", "5m": "5", "15m": "15", "30m": "30",
        "1h": "60", "2h": "120", "4h": "240", "6h": "360", "12h": "720",
        "1H": "60", "2H": "120", "4H": "240", "6H": "360", "12H": "720",
        "1D": "D", "1W": "W",
    },
    "UPBIT": {
        "1m": "minutes/1", "3m": "minutes/3", "5m": "minutes/5",
        "15m": "minutes/15", "30m": "minutes/30", "1h": "minutes/60",
        "4h": "minutes/240", "1D": "days", "1W": "weeks",
        "1H": "minutes/60", "2H": "minutes/120", "4H": "minutes/240",
    },
    # KIS는 일봉/주봉/월봉만 지원 (분봉은 당일만 가능)
    "KIS_KR": {
        "1D": "D", "1W": "W", "1M": "M",
    },
    "KIS_US": {
        "1D": "0", "1W": "1", "1M": "2",  # GUBN 파라미터 값
    },
    "ALPACA": {
        "1m": "1Min", "5m": "5Min", "15m": "15Min", "30m": "30Min",
        "1h": "1Hour", "1H": "1Hour", "4h": "4Hour", "4H": "4Hour",
        "1D": "1Day", "1W": "1Week",
    },
}

# KIS 토큰 캐시 (모듈 레벨)
_kis_token_cache: Dict[str, Any] = {
    "token": None,
    "expires_at": None,
    "app_key": None,
    "app_secret": None,
}


@dataclass
class CandleData:
    """Container for fetched candle arrays."""
    exchange: str
    symbol: str
    timeframe: str
    timestamps: np.ndarray  # Unix ms
    opens: np.ndarray
    highs: np.ndarray
    lows: np.ndarray
    closes: np.ndarray
    volumes: np.ndarray

    @property
    def count(self) -> int:
        return len(self.closes)

    def to_candles(self) -> List[Candle]:
        """Convert to list of Candle objects."""
        return [
            Candle(
                ts=int(self.timestamps[i]),
                o=float(self.opens[i]),
                h=float(self.highs[i]),
                l=float(self.lows[i]),
                c=float(self.closes[i]),
                v=float(self.volumes[i]),
            )
            for i in range(self.count)
        ]


def get_tf_ms(timeframe: str) -> int:
    """Get timeframe duration in milliseconds."""
    return TF_TO_MS.get(timeframe, 60 * 60 * 1000)  # Default 1h


def get_exchange_tf(exchange: str, timeframe: str) -> str:
    """Convert internal timeframe to exchange format."""
    ex_map = EXCHANGE_TF_MAP.get(exchange.upper(), {})
    return ex_map.get(timeframe, timeframe)


async def fetch_candles_from_exchange(
    exchange: str,
    symbol: str,
    timeframe: str,
    limit: int = 300,
    end_time: Optional[int] = None,
) -> CandleData:
    """
    Fetch candles from exchange API.

    Args:
        exchange: Exchange name (OKX, BINANCE, BYBIT, UPBIT)
        symbol: Symbol in internal format (BTC-USDT)
        timeframe: Timeframe (1m, 5m, 15m, 1h, 4h, 1D, etc.)
        limit: Number of candles to fetch (max varies by exchange)
        end_time: End timestamp in ms (default: now)

    Returns:
        CandleData with numpy arrays
    """
    exchange = exchange.upper()

    if exchange == "OKX":
        return await _fetch_okx_candles(symbol, timeframe, limit, end_time)
    elif exchange == "BINANCE":
        return await _fetch_binance_candles(symbol, timeframe, limit, end_time)
    elif exchange == "BYBIT":
        return await _fetch_bybit_candles(symbol, timeframe, limit, end_time)
    elif exchange == "UPBIT":
        return await _fetch_upbit_candles(symbol, timeframe, limit, end_time)
    elif exchange == "KIS_KR":
        return await _fetch_kis_kr_candles(symbol, timeframe, limit, end_time)
    elif exchange == "KIS_US":
        return await _fetch_kis_us_candles(symbol, timeframe, limit, end_time)
    elif exchange == "ALPACA":
        return await _fetch_alpaca_candles(symbol, timeframe, limit, end_time)
    else:
        raise ValueError(f"Unsupported exchange: {exchange}")


async def _fetch_okx_candles(
    symbol: str,
    timeframe: str,
    limit: int,
    end_time: Optional[int],
) -> CandleData:
    """Fetch candles from OKX."""
    import urllib.request
    import ssl

    # OKX uses instId format: BTC-USDT
    inst_id = symbol.upper()
    bar = get_exchange_tf("OKX", timeframe)

    url = f"https://www.okx.com/api/v5/market/candles?instId={inst_id}&bar={bar}&limit={limit}"
    if end_time:
        url += f"&after={end_time}"

    ctx = ssl.create_default_context()
    req = urllib.request.Request(url, headers={
        "Accept": "application/json",
        "User-Agent": "bbooster-hub/1.0",
    })

    try:
        with urllib.request.urlopen(req, timeout=10, context=ctx) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except Exception as e:
        logger.error(f"OKX candle fetch error: {e}")
        return _empty_candle_data("OKX", symbol, timeframe)

    if data.get("code") != "0" or not data.get("data"):
        logger.warning(f"OKX candle fetch failed: {data}")
        return _empty_candle_data("OKX", symbol, timeframe)

    # OKX format: [ts, o, h, l, c, vol, volCcy, volCcyQuote, confirm]
    # Data is in reverse order (newest first)
    candles = data["data"]
    candles.reverse()  # Oldest first

    n = len(candles)
    timestamps = np.zeros(n)
    opens = np.zeros(n)
    highs = np.zeros(n)
    lows = np.zeros(n)
    closes = np.zeros(n)
    volumes = np.zeros(n)

    for i, c in enumerate(candles):
        timestamps[i] = float(c[0])
        opens[i] = float(c[1])
        highs[i] = float(c[2])
        lows[i] = float(c[3])
        closes[i] = float(c[4])
        volumes[i] = float(c[5])

    return CandleData(
        exchange="OKX",
        symbol=symbol,
        timeframe=timeframe,
        timestamps=timestamps,
        opens=opens,
        highs=highs,
        lows=lows,
        closes=closes,
        volumes=volumes,
    )


async def _fetch_binance_candles(
    symbol: str,
    timeframe: str,
    limit: int,
    end_time: Optional[int],
) -> CandleData:
    """Fetch candles from Binance."""
    import urllib.request
    import ssl

    # Binance uses symbol format: BTCUSDT
    binance_symbol = symbol.replace("-", "").upper()
    interval = get_exchange_tf("BINANCE", timeframe)

    url = f"https://api.binance.com/api/v3/klines?symbol={binance_symbol}&interval={interval}&limit={limit}"
    if end_time:
        url += f"&endTime={end_time}"

    ctx = ssl.create_default_context()
    req = urllib.request.Request(url, headers={
        "Accept": "application/json",
        "User-Agent": "bbooster-hub/1.0",
    })

    try:
        with urllib.request.urlopen(req, timeout=10, context=ctx) as resp:
            candles = json.loads(resp.read().decode("utf-8"))
    except Exception as e:
        logger.error(f"Binance candle fetch error: {e}")
        return _empty_candle_data("BINANCE", symbol, timeframe)

    if not candles or isinstance(candles, dict):
        logger.warning(f"Binance candle fetch failed: {candles}")
        return _empty_candle_data("BINANCE", symbol, timeframe)

    # Binance format: [openTime, o, h, l, c, vol, closeTime, quoteVol, trades, ...]
    n = len(candles)
    timestamps = np.zeros(n)
    opens = np.zeros(n)
    highs = np.zeros(n)
    lows = np.zeros(n)
    closes = np.zeros(n)
    volumes = np.zeros(n)

    for i, c in enumerate(candles):
        timestamps[i] = float(c[0])
        opens[i] = float(c[1])
        highs[i] = float(c[2])
        lows[i] = float(c[3])
        closes[i] = float(c[4])
        volumes[i] = float(c[5])

    return CandleData(
        exchange="BINANCE",
        symbol=symbol,
        timeframe=timeframe,
        timestamps=timestamps,
        opens=opens,
        highs=highs,
        lows=lows,
        closes=closes,
        volumes=volumes,
    )


async def _fetch_bybit_candles(
    symbol: str,
    timeframe: str,
    limit: int,
    end_time: Optional[int],
) -> CandleData:
    """Fetch candles from Bybit."""
    import urllib.request
    import ssl

    # Bybit uses symbol format: BTCUSDT
    bybit_symbol = symbol.replace("-", "").upper()
    interval = get_exchange_tf("BYBIT", timeframe)

    url = f"https://api.bybit.com/v5/market/kline?category=spot&symbol={bybit_symbol}&interval={interval}&limit={limit}"
    if end_time:
        url += f"&end={end_time}"

    ctx = ssl.create_default_context()
    req = urllib.request.Request(url, headers={
        "Accept": "application/json",
        "User-Agent": "bbooster-hub/1.0",
    })

    try:
        with urllib.request.urlopen(req, timeout=10, context=ctx) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except Exception as e:
        logger.error(f"Bybit candle fetch error: {e}")
        return _empty_candle_data("BYBIT", symbol, timeframe)

    if data.get("retCode") != 0 or not data.get("result", {}).get("list"):
        logger.warning(f"Bybit candle fetch failed: {data}")
        return _empty_candle_data("BYBIT", symbol, timeframe)

    # Bybit format: [startTime, o, h, l, c, vol, turnover]
    # Data is in reverse order (newest first)
    candles = data["result"]["list"]
    candles.reverse()

    n = len(candles)
    timestamps = np.zeros(n)
    opens = np.zeros(n)
    highs = np.zeros(n)
    lows = np.zeros(n)
    closes = np.zeros(n)
    volumes = np.zeros(n)

    for i, c in enumerate(candles):
        timestamps[i] = float(c[0])
        opens[i] = float(c[1])
        highs[i] = float(c[2])
        lows[i] = float(c[3])
        closes[i] = float(c[4])
        volumes[i] = float(c[5])

    return CandleData(
        exchange="BYBIT",
        symbol=symbol,
        timeframe=timeframe,
        timestamps=timestamps,
        opens=opens,
        highs=highs,
        lows=lows,
        closes=closes,
        volumes=volumes,
    )


async def _fetch_upbit_candles(
    symbol: str,
    timeframe: str,
    limit: int,
    end_time: Optional[int],
) -> CandleData:
    """Fetch candles from Upbit."""
    import urllib.request
    import ssl

    # Upbit uses market format: KRW-BTC (quote-base)
    parts = symbol.upper().split("-")
    if len(parts) == 2:
        upbit_market = f"{parts[1]}-{parts[0]}"  # Reverse to quote-base
    else:
        upbit_market = symbol

    tf_path = get_exchange_tf("UPBIT", timeframe)
    url = f"https://api.upbit.com/v1/candles/{tf_path}?market={upbit_market}&count={min(limit, 200)}"

    if end_time:
        # Upbit uses ISO format for 'to' parameter
        dt = datetime.fromtimestamp(end_time / 1000, tz=timezone.utc)
        url += f"&to={dt.strftime('%Y-%m-%dT%H:%M:%S')}"

    ctx = ssl.create_default_context()
    req = urllib.request.Request(url, headers={
        "Accept": "application/json",
        "User-Agent": "bbooster-hub/1.0",
    })

    try:
        with urllib.request.urlopen(req, timeout=10, context=ctx) as resp:
            candles = json.loads(resp.read().decode("utf-8"))
    except Exception as e:
        logger.error(f"Upbit candle fetch error: {e}")
        return _empty_candle_data("UPBIT", symbol, timeframe)

    if not candles or isinstance(candles, dict):
        logger.warning(f"Upbit candle fetch failed: {candles}")
        return _empty_candle_data("UPBIT", symbol, timeframe)

    # Upbit returns newest first, reverse to oldest first
    candles.reverse()

    n = len(candles)
    timestamps = np.zeros(n)
    opens = np.zeros(n)
    highs = np.zeros(n)
    lows = np.zeros(n)
    closes = np.zeros(n)
    volumes = np.zeros(n)

    for i, c in enumerate(candles):
        # Upbit uses candle_date_time_utc
        ts_str = c.get("candle_date_time_utc", "")
        try:
            dt = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
            timestamps[i] = dt.timestamp() * 1000
        except:
            timestamps[i] = c.get("timestamp", 0)

        opens[i] = float(c.get("opening_price", 0))
        highs[i] = float(c.get("high_price", 0))
        lows[i] = float(c.get("low_price", 0))
        closes[i] = float(c.get("trade_price", 0))
        volumes[i] = float(c.get("candle_acc_trade_volume", 0))

    return CandleData(
        exchange="UPBIT",
        symbol=symbol,
        timeframe=timeframe,
        timestamps=timestamps,
        opens=opens,
        highs=highs,
        lows=lows,
        closes=closes,
        volumes=volumes,
    )


async def _get_kis_token() -> Optional[str]:
    """KIS API 토큰 가져오기 (kis_api.py 캐시 재사용)"""
    import os
    from datetime import datetime, timezone

    global _kis_token_cache

    # 환경변수에서 키 가져오기 (KIS_APP_KEY 우선, 없으면 KIS_PAPER_APP_KEY)
    app_key = os.getenv("KIS_APP_KEY", "").strip()
    app_secret = os.getenv("KIS_APP_SECRET", "").strip()

    # KIS_APP_KEY가 없으면 PAPER 키 사용 (VPS 환경)
    if not app_key or not app_secret:
        app_key = os.getenv("KIS_PAPER_APP_KEY", "").strip()
        app_secret = os.getenv("KIS_PAPER_APP_SECRET", "").strip()

    is_mock = os.getenv("KIS_MOCK", "true").lower() == "true"

    if not app_key or not app_secret:
        logger.warning("KIS_APP_KEY 또는 KIS_PAPER_APP_KEY가 설정되지 않았습니다")
        return None

    # 1. 로컬 캐시 확인
    if (_kis_token_cache.get("token") and
        _kis_token_cache.get("expires_at") and
        _kis_token_cache.get("app_key") == app_key and
        datetime.now(timezone.utc) < _kis_token_cache["expires_at"]):
        return _kis_token_cache["token"]

    # 2. kis_api.py의 글로벌 캐시에서 토큰 가져오기
    try:
        from app.kis_api import _token_cache as kis_global_cache
        # kis_api.py는 "system" 키로 서버 토큰을 저장
        if "system" in kis_global_cache:
            token_obj = kis_global_cache["system"]
            if token_obj and datetime.now(timezone.utc) < token_obj.expires_at:
                _kis_token_cache["token"] = token_obj.access_token
                _kis_token_cache["expires_at"] = token_obj.expires_at
                _kis_token_cache["app_key"] = app_key
                logger.info("kis_api 캐시에서 토큰 재사용")
                return token_obj.access_token
    except Exception as e:
        logger.debug(f"kis_api 캐시 접근 실패: {e}")

    # 3. 새 토큰 발급
    try:
        from app.kis_api import get_kis_token, KISToken, _token_cache as kis_global_cache
        token_obj = await get_kis_token(app_key, app_secret, is_mock)
        if token_obj:
            _kis_token_cache["token"] = token_obj.access_token
            _kis_token_cache["expires_at"] = token_obj.expires_at
            _kis_token_cache["app_key"] = app_key
            _kis_token_cache["app_secret"] = app_secret
            # kis_api.py 캐시에도 저장 (다른 모듈과 공유)
            kis_global_cache["system"] = token_obj
            logger.info(f"KIS 토큰 발급 완료 (만료: {token_obj.expires_at})")
            return token_obj.access_token
    except Exception as e:
        logger.error(f"KIS 토큰 발급 실패: {e}")

    return None


async def _fetch_kis_kr_candles(
    symbol: str,
    timeframe: str,
    limit: int,
    end_time: Optional[int],
) -> CandleData:
    """
    KIS 국내주식 캔들 조회 (일봉/주봉/월봉)

    Args:
        symbol: 종목코드 6자리 (예: "005930" 삼성전자)
        timeframe: "1D", "1W", "1M"
        limit: 조회할 봉 수
        end_time: 종료 시간 (ms, 미사용)
    """
    import urllib.request
    import ssl
    import os

    # KIS API 설정 (KIS_APP_KEY 우선, 없으면 KIS_PAPER_APP_KEY)
    app_key = os.getenv("KIS_APP_KEY", "").strip()
    app_secret = os.getenv("KIS_APP_SECRET", "").strip()
    if not app_key or not app_secret:
        app_key = os.getenv("KIS_PAPER_APP_KEY", "").strip()
        app_secret = os.getenv("KIS_PAPER_APP_SECRET", "").strip()
    is_mock = os.getenv("KIS_MOCK", "true").lower() == "true"

    access_token = await _get_kis_token()
    if not access_token:
        logger.error("KIS 토큰 없음 - 국내주식 캔들 조회 불가")
        return _empty_candle_data("KIS_KR", symbol, timeframe)

    # URL 설정
    base_url = "https://openapivts.koreainvestment.com:29443" if is_mock else "https://openapi.koreainvestment.com:9443"
    url = f"{base_url}/uapi/domestic-stock/v1/quotations/inquire-daily-itemchartprice"

    # 타임프레임 변환
    period_code = get_exchange_tf("KIS_KR", timeframe)
    if not period_code:
        period_code = "D"

    # 날짜 계산
    end_date = datetime.now().strftime("%Y%m%d")
    # 여유있게 조회 (일봉 기준 limit일 + 여유분)
    days_back = limit * 2 if timeframe == "1D" else limit * 14
    start_date = (datetime.now() - timedelta(days=days_back)).strftime("%Y%m%d")

    headers = {
        "Content-Type": "application/json; charset=utf-8",
        "authorization": f"Bearer {access_token}",
        "appkey": app_key,
        "appsecret": app_secret,
        "tr_id": "FHKST03010100",
        "custtype": "P",
    }

    params = {
        "FID_COND_MRKT_DIV_CODE": "J",
        "FID_INPUT_ISCD": symbol,
        "FID_INPUT_DATE_1": start_date,
        "FID_INPUT_DATE_2": end_date,
        "FID_PERIOD_DIV_CODE": period_code,
        "FID_ORG_ADJ_PRC": "0",  # 수정주가
    }

    query_string = "&".join([f"{k}={v}" for k, v in params.items()])
    full_url = f"{url}?{query_string}"

    ctx = ssl.create_default_context()
    req = urllib.request.Request(full_url, headers=headers)

    try:
        with urllib.request.urlopen(req, timeout=15, context=ctx) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except Exception as e:
        logger.error(f"KIS_KR 캔들 조회 에러: {e}")
        return _empty_candle_data("KIS_KR", symbol, timeframe)

    if data.get("rt_cd") != "0":
        logger.warning(f"KIS_KR 캔들 조회 실패: {data.get('msg1', 'Unknown error')}")
        return _empty_candle_data("KIS_KR", symbol, timeframe)

    # output2가 캔들 데이터 (최신→과거 순서)
    candles_raw = data.get("output2", [])
    if not candles_raw:
        logger.warning(f"KIS_KR 캔들 데이터 없음: {symbol}")
        return _empty_candle_data("KIS_KR", symbol, timeframe)

    # 역순 정렬 (과거→최신)
    candles_raw.reverse()

    # limit 적용
    candles_raw = candles_raw[-limit:] if len(candles_raw) > limit else candles_raw

    n = len(candles_raw)
    timestamps = np.zeros(n)
    opens = np.zeros(n)
    highs = np.zeros(n)
    lows = np.zeros(n)
    closes = np.zeros(n)
    volumes = np.zeros(n)

    for i, c in enumerate(candles_raw):
        # 날짜 -> timestamp 변환 (YYYYMMDD -> ms)
        date_str = c.get("stck_bsop_date", "")
        if date_str:
            try:
                dt = datetime.strptime(date_str, "%Y%m%d")
                timestamps[i] = dt.timestamp() * 1000
            except:
                timestamps[i] = 0

        opens[i] = float(c.get("stck_oprc", 0) or 0)
        highs[i] = float(c.get("stck_hgpr", 0) or 0)
        lows[i] = float(c.get("stck_lwpr", 0) or 0)
        closes[i] = float(c.get("stck_clpr", 0) or 0)
        volumes[i] = float(c.get("acml_vol", 0) or 0)

    logger.info(f"KIS_KR 캔들 조회 완료: {symbol} {timeframe} {n}봉")

    return CandleData(
        exchange="KIS_KR",
        symbol=symbol,
        timeframe=timeframe,
        timestamps=timestamps,
        opens=opens,
        highs=highs,
        lows=lows,
        closes=closes,
        volumes=volumes,
    )


async def _fetch_kis_us_candles(
    symbol: str,
    timeframe: str,
    limit: int,
    end_time: Optional[int],
) -> CandleData:
    """
    KIS 해외주식 캔들 조회 (일봉/주봉/월봉)

    Args:
        symbol: 종목심볼 (예: "AAPL", "SPY")
        timeframe: "1D", "1W", "1M"
        limit: 조회할 봉 수
        end_time: 종료 시간 (ms, 미사용)
    """
    import urllib.request
    import ssl
    import os

    # KIS API 설정
    app_key = os.getenv("KIS_APP_KEY", "").strip()
    app_secret = os.getenv("KIS_APP_SECRET", "").strip()
    # KIS_APP_KEY가 없으면 PAPER 키 사용 (VPS 환경)
    if not app_key or not app_secret:
        app_key = os.getenv("KIS_PAPER_APP_KEY", "").strip()
        app_secret = os.getenv("KIS_PAPER_APP_SECRET", "").strip()
    is_mock = os.getenv("KIS_MOCK", "true").lower() == "true"

    access_token = await _get_kis_token()
    if not access_token:
        logger.error("KIS 토큰 없음 - 해외주식 캔들 조회 불가")
        return _empty_candle_data("KIS_US", symbol, timeframe)

    # URL 설정
    base_url = "https://openapivts.koreainvestment.com:29443" if is_mock else "https://openapi.koreainvestment.com:9443"
    url = f"{base_url}/uapi/overseas-price/v1/quotations/dailyprice"

    # 타임프레임 변환 (GUBN: 0=일, 1=주, 2=월)
    gubn = get_exchange_tf("KIS_US", timeframe)
    if not gubn:
        gubn = "0"

    # 거래소 코드 자동 판별 (NAS -> NYS -> AMS 순서로 시도)
    exchanges_to_try = ["NAS", "NYS", "AMS"]

    for excd in exchanges_to_try:
        headers = {
            "Content-Type": "application/json; charset=utf-8",
            "authorization": f"Bearer {access_token}",
            "appkey": app_key,
            "appsecret": app_secret,
            "tr_id": "HHDFS76240000",
            "custtype": "P",
        }

        params = {
            "AUTH": "",
            "EXCD": excd,
            "SYMB": symbol.upper(),
            "GUBN": gubn,
            "BYMD": "",  # 빈값이면 최신부터
            "MODP": "1",  # 수정주가
        }

        query_string = "&".join([f"{k}={v}" for k, v in params.items()])
        full_url = f"{url}?{query_string}"

        ctx = ssl.create_default_context()
        req = urllib.request.Request(full_url, headers=headers)

        try:
            with urllib.request.urlopen(req, timeout=15, context=ctx) as resp:
                data = json.loads(resp.read().decode("utf-8"))
        except Exception as e:
            logger.warning(f"KIS_US 캔들 조회 에러 ({excd}): {e}")
            continue

        if data.get("rt_cd") != "0":
            # 다른 거래소로 재시도
            continue

        # output2가 캔들 데이터 (최신→과거 순서)
        candles_raw = data.get("output2", [])
        if not candles_raw:
            continue

        # 역순 정렬 (과거→최신)
        candles_raw.reverse()

        # limit 적용
        candles_raw = candles_raw[-limit:] if len(candles_raw) > limit else candles_raw

        n = len(candles_raw)
        timestamps = np.zeros(n)
        opens = np.zeros(n)
        highs = np.zeros(n)
        lows = np.zeros(n)
        closes = np.zeros(n)
        volumes = np.zeros(n)

        for i, c in enumerate(candles_raw):
            # 날짜 -> timestamp 변환 (YYYYMMDD -> ms)
            date_str = c.get("xymd", "")
            if date_str:
                try:
                    dt = datetime.strptime(date_str, "%Y%m%d")
                    timestamps[i] = dt.timestamp() * 1000
                except:
                    timestamps[i] = 0

            opens[i] = float(c.get("open", 0) or 0)
            highs[i] = float(c.get("high", 0) or 0)
            lows[i] = float(c.get("low", 0) or 0)
            closes[i] = float(c.get("clos", 0) or 0)
            volumes[i] = float(c.get("tvol", 0) or 0)

        logger.info(f"KIS_US 캔들 조회 완료: {symbol} ({excd}) {timeframe} {n}봉")

        return CandleData(
            exchange="KIS_US",
            symbol=symbol,
            timeframe=timeframe,
            timestamps=timestamps,
            opens=opens,
            highs=highs,
            lows=lows,
            closes=closes,
            volumes=volumes,
        )

    # 모든 거래소에서 실패
    logger.error(f"KIS_US 캔들 조회 실패: {symbol} - 모든 거래소(NAS/NYS/AMS)에서 데이터 없음")
    return _empty_candle_data("KIS_US", symbol, timeframe)


def _empty_candle_data(exchange: str, symbol: str, timeframe: str) -> CandleData:
    """Return empty CandleData for error cases."""
    return CandleData(
        exchange=exchange,
        symbol=symbol,
        timeframe=timeframe,
        timestamps=np.array([]),
        opens=np.array([]),
        highs=np.array([]),
        lows=np.array([]),
        closes=np.array([]),
        volumes=np.array([]),
    )


async def _fetch_alpaca_candles(
    symbol: str,
    timeframe: str,
    limit: int,
    end_time: Optional[int] = None,
) -> CandleData:
    """
    Fetch candles from Alpaca Data API.

    GET https://data.alpaca.markets/v2/stocks/{symbol}/bars

    Args:
        symbol: Stock symbol (e.g., AAPL)
        timeframe: Internal timeframe (1m, 5m, 1D, etc.)
        limit: Number of candles
        end_time: End timestamp in ms
    """
    import os
    import urllib.request
    import urllib.parse

    api_key = os.getenv("ALPACA_API_KEY", "").strip()
    api_secret = os.getenv("ALPACA_API_SECRET", "").strip()
    data_url = os.getenv("ALPACA_DATA_URL", "https://data.alpaca.markets").rstrip("/")

    if not api_key or not api_secret:
        logger.error("ALPACA API 키 없음")
        return _empty_candle_data("ALPACA", symbol, timeframe)

    # Convert timeframe to Alpaca format
    alpaca_tf = get_exchange_tf("ALPACA", timeframe)
    if not alpaca_tf:
        alpaca_tf = "1Day"

    # Build URL
    symbol = symbol.upper().strip()
    url = f"{data_url}/v2/stocks/{symbol}/bars"

    params: Dict[str, Any] = {
        "timeframe": alpaca_tf,
        "limit": min(limit, 10000),
    }

    # Calculate start/end dates
    if end_time:
        end_dt = datetime.fromtimestamp(end_time / 1000, tz=timezone.utc)
        params["end"] = end_dt.strftime("%Y-%m-%dT%H:%M:%SZ")

    # Start date: go back enough to get 'limit' candles
    tf_ms = get_tf_ms(timeframe)
    duration_ms = tf_ms * limit * 2  # Double for safety (weekends, holidays)
    start_ts = (end_time or int(datetime.now(timezone.utc).timestamp() * 1000)) - duration_ms
    start_dt = datetime.fromtimestamp(start_ts / 1000, tz=timezone.utc)
    params["start"] = start_dt.strftime("%Y-%m-%dT%H:%M:%SZ")

    full_url = f"{url}?{urllib.parse.urlencode(params)}"

    headers = {
        "APCA-API-KEY-ID": api_key,
        "APCA-API-SECRET-KEY": api_secret,
        "Accept": "application/json",
    }

    req = urllib.request.Request(full_url, headers=headers)

    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        logger.error(f"ALPACA 캔들 조회 HTTP 에러: {e.code} - {e.read().decode('utf-8', errors='replace')}")
        return _empty_candle_data("ALPACA", symbol, timeframe)
    except Exception as e:
        logger.error(f"ALPACA 캔들 조회 에러: {e}")
        return _empty_candle_data("ALPACA", symbol, timeframe)

    bars = data.get("bars", [])
    if not bars:
        logger.warning(f"ALPACA 캔들 데이터 없음: {symbol}")
        return _empty_candle_data("ALPACA", symbol, timeframe)

    # Limit to requested count
    bars = bars[-limit:] if len(bars) > limit else bars

    n = len(bars)
    timestamps = np.zeros(n)
    opens = np.zeros(n)
    highs = np.zeros(n)
    lows = np.zeros(n)
    closes = np.zeros(n)
    volumes = np.zeros(n)

    for i, bar in enumerate(bars):
        # Parse timestamp (ISO format)
        t_str = bar.get("t", "")
        if t_str:
            try:
                dt = datetime.fromisoformat(t_str.replace("Z", "+00:00"))
                timestamps[i] = dt.timestamp() * 1000
            except:
                timestamps[i] = 0

        opens[i] = float(bar.get("o", 0) or 0)
        highs[i] = float(bar.get("h", 0) or 0)
        lows[i] = float(bar.get("l", 0) or 0)
        closes[i] = float(bar.get("c", 0) or 0)
        volumes[i] = float(bar.get("v", 0) or 0)

    logger.info(f"ALPACA 캔들 조회 완료: {symbol} {timeframe} {n}봉")

    return CandleData(
        exchange="ALPACA",
        symbol=symbol,
        timeframe=timeframe,
        timestamps=timestamps,
        opens=opens,
        highs=highs,
        lows=lows,
        closes=closes,
        volumes=volumes,
    )


class CandleCache:
    """
    Candle cache manager with DB persistence.

    Uses candles table for storage.
    """

    def __init__(self, db_session=None):
        """
        Initialize cache.

        Args:
            db_session: SQLAlchemy session (optional, for DB caching)
        """
        self.db = db_session
        self._memory_cache: Dict[str, CandleData] = {}

    def _cache_key(self, exchange: str, symbol: str, timeframe: str) -> str:
        return f"{exchange}:{symbol}:{timeframe}"

    async def get_candles(
        self,
        exchange: str,
        symbol: str,
        timeframe: str,
        count: int = 300,
        use_cache: bool = True,
    ) -> CandleData:
        """
        Get candles, using cache if available.

        Args:
            exchange: Exchange name
            symbol: Symbol
            timeframe: Timeframe
            count: Number of candles needed
            use_cache: Whether to use cache

        Returns:
            CandleData
        """
        key = self._cache_key(exchange, symbol, timeframe)

        # Check memory cache
        if use_cache and key in self._memory_cache:
            cached = self._memory_cache[key]
            if cached.count >= count:
                # Return last 'count' candles
                return CandleData(
                    exchange=cached.exchange,
                    symbol=cached.symbol,
                    timeframe=cached.timeframe,
                    timestamps=cached.timestamps[-count:],
                    opens=cached.opens[-count:],
                    highs=cached.highs[-count:],
                    lows=cached.lows[-count:],
                    closes=cached.closes[-count:],
                    volumes=cached.volumes[-count:],
                )

        # Fetch from exchange
        candle_data = await fetch_candles_from_exchange(
            exchange, symbol, timeframe, limit=count
        )

        # Update memory cache
        if candle_data.count > 0:
            self._memory_cache[key] = candle_data

        return candle_data

    def update_latest(
        self,
        exchange: str,
        symbol: str,
        timeframe: str,
        candle: Candle,
    ):
        """
        Update the latest candle (for real-time updates).

        Args:
            exchange: Exchange name
            symbol: Symbol
            timeframe: Timeframe
            candle: Latest candle data
        """
        key = self._cache_key(exchange, symbol, timeframe)

        if key not in self._memory_cache:
            return

        cached = self._memory_cache[key]
        tf_ms = get_tf_ms(timeframe)

        # Check if this is a new candle or update to existing
        if cached.count > 0:
            last_ts = cached.timestamps[-1]

            if candle.ts >= last_ts + tf_ms:
                # New candle - append
                self._memory_cache[key] = CandleData(
                    exchange=cached.exchange,
                    symbol=cached.symbol,
                    timeframe=cached.timeframe,
                    timestamps=np.append(cached.timestamps, candle.ts),
                    opens=np.append(cached.opens, candle.o),
                    highs=np.append(cached.highs, candle.h),
                    lows=np.append(cached.lows, candle.l),
                    closes=np.append(cached.closes, candle.c),
                    volumes=np.append(cached.volumes, candle.v),
                )
            elif candle.ts >= last_ts:
                # Update last candle
                cached.opens[-1] = candle.o
                cached.highs[-1] = max(cached.highs[-1], candle.h)
                cached.lows[-1] = min(cached.lows[-1], candle.l)
                cached.closes[-1] = candle.c
                cached.volumes[-1] = candle.v

    def clear(self, exchange: str = None, symbol: str = None):
        """Clear cache entries."""
        if exchange is None and symbol is None:
            self._memory_cache.clear()
        else:
            keys_to_remove = []
            for key in self._memory_cache:
                parts = key.split(":")
                if exchange and parts[0] != exchange.upper():
                    continue
                if symbol and parts[1] != symbol.upper():
                    continue
                keys_to_remove.append(key)

            for key in keys_to_remove:
                del self._memory_cache[key]


# Global cache instance
_candle_cache = CandleCache()


def get_candle_cache() -> CandleCache:
    """Get the global candle cache instance."""
    return _candle_cache


# ============================================================================
# 백테스트용 과거 캔들 조회 함수 (페이지네이션 지원)
# ============================================================================

# TF별 봉/일 계산
BARS_PER_DAY: Dict[str, float] = {
    "1m": 1440, "3m": 480, "5m": 288, "15m": 96, "30m": 48,
    "1h": 24, "2h": 12, "4h": 6, "6h": 4, "12h": 2,
    "1D": 1, "1W": 1/7,
    # Uppercase variants
    "1H": 24, "2H": 12, "4H": 6, "6H": 4, "12H": 2,
}


async def fetch_candles_for_backtest(
    exchange: str,
    symbol: str,
    timeframe: str,
    days: int,
    timeout: int = 30,
) -> List[Candle]:
    """
    백테스트용 과거 캔들을 조회 (DB 캐싱 지원).

    1. DB에서 캐시된 캔들 조회
    2. 부족한 부분만 거래소 API에서 조회
    3. 새로 조회한 캔들은 DB에 저장

    Args:
        exchange: 거래소 (OKX, BINANCE, BYBIT)
        symbol: 종목 심볼 (BTC-USDT)
        timeframe: 타임프레임 (1m, 5m, 15m, 30m, 1h, 4h, 1D 등)
        days: 조회 기간 (일)
        timeout: 전체 타임아웃 (초)

    Returns:
        List[Candle]: oldest first 정렬된 캔들 목록

    Raises:
        ValueError: 시세 조회 실패 시 한글 에러 메시지
    """
    import urllib.request
    import ssl
    import asyncio

    exchange = exchange.upper()
    symbol = symbol.upper()

    # 지원 거래소 확인
    supported_exchanges = ["OKX", "BINANCE", "BYBIT", "UPBIT", "KIS_KR", "KIS_US", "ALPACA"]
    if exchange not in supported_exchanges:
        raise ValueError(
            f"{exchange} 거래소의 백테스트는 아직 지원되지 않습니다. "
            f"지원 거래소: {', '.join(supported_exchanges)}"
        )

    # KIS는 일봉/주봉/월봉만 지원
    if exchange in ["KIS_KR", "KIS_US"]:
        if timeframe not in ["1D", "1W", "1M"]:
            raise ValueError(
                f"한국투자증권({exchange})은 일봉/주봉/월봉만 지원합니다. "
                f"(선택됨: {timeframe}, 가능: 1D, 1W, 1M)"
            )

    # 타임프레임 확인
    if timeframe not in BARS_PER_DAY:
        raise ValueError(f"지원하지 않는 타임프레임입니다: {timeframe}")

    # 필요 봉수 계산
    needed = int(days * BARS_PER_DAY[timeframe])
    if needed < 1:
        raise ValueError(f"요청 기간이 너무 짧습니다: {days}일 × {timeframe}")

    # 최소 300봉 필요 (OSC bb_len=250 + HTF 지표 계산용)
    needed = max(needed, 300)

    start_time = time.time()
    tf_ms = TF_TO_MS.get(timeframe, 3600 * 1000)
    now_ms = int(time.time() * 1000)

    # 시작 시간 계산 (현재 - days)
    start_ms = now_ms - (days * 24 * 60 * 60 * 1000)

    # DB 캐시 체크
    db = _get_db_session()
    CandleCacheModel = _get_candle_cache_model()
    cached_candles: List[Candle] = []

    if db and CandleCacheModel:
        try:
            # DB에서 캐시된 캔들 조회
            cached_rows = db.query(CandleCacheModel).filter(
                CandleCacheModel.exchange == exchange,
                CandleCacheModel.symbol == symbol,
                CandleCacheModel.timeframe == timeframe,
                CandleCacheModel.ts >= start_ms,
            ).order_by(CandleCacheModel.ts).all()

            if cached_rows:
                cached_candles = [
                    Candle(ts=r.ts, o=r.o, h=r.h, l=r.l, c=r.c, v=r.v)
                    for r in cached_rows
                ]
                logger.info(f"DB 캐시: {len(cached_candles)}봉 (필요: {needed}봉)")

                # 캐시된 데이터가 충분하고 최근 데이터가 있는지 확인
                if len(cached_candles) >= needed:
                    last_ts = cached_candles[-1].ts
                    # 마지막 캔들이 현재 시간 기준 2봉 이내인지 (최신 데이터)
                    if now_ms - last_ts < tf_ms * 2:
                        logger.info(f"캐시 HIT: {len(cached_candles)}봉, {time.time() - start_time:.2f}초")
                        db.close()
                        return cached_candles[-needed:]

                # 캐시는 있지만 최신 데이터 필요 → 증분 조회
                if len(cached_candles) >= needed * 0.8:  # 80% 이상 있으면 증분 조회
                    last_ts = cached_candles[-1].ts
                    new_candles = await _fetch_incremental(
                        exchange, symbol, timeframe, last_ts, now_ms, timeout
                    )
                    if new_candles:
                        # 새 캔들 DB에 저장
                        _save_candles_to_db(db, CandleCacheModel, exchange, symbol, timeframe, new_candles)
                        # 기존 캐시 + 새 캔들 합치기
                        all_candles = cached_candles + new_candles
                        all_candles.sort(key=lambda c: c.ts)
                        # 중복 제거
                        seen = set()
                        unique = []
                        for c in all_candles:
                            if c.ts not in seen:
                                seen.add(c.ts)
                                unique.append(c)
                        db.close()
                        logger.info(f"증분 조회 완료: 캐시 {len(cached_candles)} + 새로 {len(new_candles)} = {len(unique)}봉")
                        return unique[-needed:] if len(unique) > needed else unique
        except Exception as e:
            logger.warning(f"DB 캐시 조회 실패: {e}")

    # 거래소에서 전체 조회
    ctx = ssl.create_default_context()
    all_candles: List[Candle] = []

    if exchange == "OKX":
        all_candles = await _fetch_okx_paginated(symbol, timeframe, needed, timeout, ctx)
    elif exchange == "BINANCE":
        all_candles = await _fetch_binance_paginated(symbol, timeframe, needed, timeout, ctx)
    elif exchange == "BYBIT":
        all_candles = await _fetch_bybit_paginated(symbol, timeframe, needed, timeout, ctx)
    elif exchange == "UPBIT":
        all_candles = await _fetch_upbit_paginated(symbol, timeframe, needed, timeout, ctx)
    elif exchange == "KIS_KR":
        all_candles = await _fetch_kis_kr_paginated(symbol, timeframe, needed, timeout)
    elif exchange == "KIS_US":
        all_candles = await _fetch_kis_us_paginated(symbol, timeframe, needed, timeout)
    elif exchange == "ALPACA":
        all_candles = await _fetch_alpaca_paginated(symbol, timeframe, needed, timeout)

    # 결과 검증
    if len(all_candles) < 50:
        if db:
            db.close()
        raise ValueError(
            f"시세 데이터가 부족합니다: {len(all_candles)}봉 조회됨 "
            f"(최소 50봉 필요). 기간을 늘리거나 타임프레임을 변경해보세요."
        )

    # oldest first 정렬
    all_candles.sort(key=lambda c: c.ts)

    # 필요한 봉수만 반환 (API가 더 많이 줄 수 있음)
    if len(all_candles) > needed:
        all_candles = all_candles[-needed:]

    # DB에 저장
    if db and CandleCacheModel:
        _save_candles_to_db(db, CandleCacheModel, exchange, symbol, timeframe, all_candles)
        db.close()
    elif db:
        db.close()

    logger.info(f"백테스트 캔들 조회 완료: {exchange} {symbol} {timeframe}, "
                f"{len(all_candles)}봉, {time.time() - start_time:.1f}초")

    return all_candles


def _save_candles_to_db(db, CandleCacheModel, exchange: str, symbol: str, timeframe: str, candles: List[Candle]):
    """캔들 DB 저장 (ON CONFLICT DO NOTHING)"""
    try:
        from sqlalchemy.dialects.postgresql import insert as pg_insert
        for c in candles:
            try:
                stmt = pg_insert(CandleCacheModel).values(
                    exchange=exchange,
                    symbol=symbol,
                    timeframe=timeframe,
                    ts=c.ts,
                    o=c.o,
                    h=c.h,
                    l=c.l,
                    c=c.c,
                    v=c.v,
                ).on_conflict_do_nothing(
                    index_elements=['exchange', 'symbol', 'timeframe', 'ts']
                )
                db.execute(stmt)
            except Exception:
                pass
        db.commit()
        logger.info(f"DB 캐시 저장: {len(candles)}봉")
    except Exception as e:
        logger.warning(f"DB 캐시 저장 실패: {e}")
        db.rollback()


async def _fetch_incremental(
    exchange: str,
    symbol: str,
    timeframe: str,
    from_ts: int,
    to_ts: int,
    timeout: int,
) -> List[Candle]:
    """마지막 캔들 이후 증분 조회"""
    import ssl
    ctx = ssl.create_default_context()
    tf_ms = TF_TO_MS.get(timeframe, 3600 * 1000)
    needed = int((to_ts - from_ts) / tf_ms) + 10  # 약간 여유
    needed = min(needed, 500)  # 최대 500봉

    if needed < 1:
        return []

    try:
        if exchange == "OKX":
            return await _fetch_okx_paginated(symbol, timeframe, needed, timeout, ctx)
        elif exchange == "BINANCE":
            return await _fetch_binance_paginated(symbol, timeframe, needed, timeout, ctx)
        elif exchange == "BYBIT":
            return await _fetch_bybit_paginated(symbol, timeframe, needed, timeout, ctx)
        elif exchange == "UPBIT":
            return await _fetch_upbit_paginated(symbol, timeframe, needed, timeout, ctx)
        elif exchange == "KIS_KR":
            return await _fetch_kis_kr_paginated(symbol, timeframe, needed, timeout)
        elif exchange == "KIS_US":
            return await _fetch_kis_us_paginated(symbol, timeframe, needed, timeout)
        elif exchange == "ALPACA":
            return await _fetch_alpaca_paginated(symbol, timeframe, needed, timeout)
    except Exception as e:
        logger.warning(f"증분 조회 실패: {e}")
        return []
    return []


async def _fetch_upbit_paginated(
    symbol: str,
    timeframe: str,
    needed: int,
    timeout: int,
    ctx,
) -> List[Candle]:
    """Upbit 페이지네이션 조회 (200개씩)"""
    import urllib.request
    import asyncio

    all_candles = []
    tf_path = get_exchange_tf("UPBIT", timeframe)
    # Upbit symbol: KRW-BTC -> KRW-BTC
    upbit_symbol = symbol.upper()
    start_time = time.time()

    # Upbit은 to 파라미터로 이전 데이터 조회
    to_param = ""

    while len(all_candles) < needed:
        if time.time() - start_time > timeout:
            raise ValueError(f"시세 조회 시간 초과 ({timeout}초)")

        url = f"https://api.upbit.com/v1/candles/{tf_path}?market={upbit_symbol}&count=200"
        if to_param:
            url += f"&to={to_param}"

        req = urllib.request.Request(url, headers={
            "Accept": "application/json",
            "User-Agent": "bbooster-hub/1.0",
        })

        try:
            with urllib.request.urlopen(req, timeout=15, context=ctx) as resp:
                data = json.loads(resp.read().decode("utf-8"))
        except Exception as e:
            logger.warning(f"Upbit 페이지네이션 에러: {e}")
            break

        if not data or not isinstance(data, list):
            break

        for c in data:
            ts_str = c.get("candle_date_time_utc", "")
            try:
                dt = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
                ts = int(dt.timestamp() * 1000)
            except:
                ts = c.get("timestamp", 0)

            all_candles.append(Candle(
                ts=ts,
                o=float(c.get("opening_price", 0)),
                h=float(c.get("high_price", 0)),
                l=float(c.get("low_price", 0)),
                c=float(c.get("trade_price", 0)),
                v=float(c.get("candle_acc_trade_volume", 0)),
            ))

        # 다음 페이지로 (가장 오래된 캔들의 시간)
        if data:
            oldest_time = data[-1].get("candle_date_time_utc", "")
            if oldest_time and oldest_time != to_param:
                to_param = oldest_time
            else:
                break
        else:
            break

        # Rate limit 방지
        await asyncio.sleep(0.2)

        # 더 이상 데이터가 없으면 중단
        if len(data) < 200:
            break

    # 시간순 정렬 (과거 → 최신)
    all_candles.sort(key=lambda c: c.ts)

    return all_candles


async def _fetch_kis_kr_paginated(
    symbol: str,
    timeframe: str,
    needed: int,
    timeout: int,
) -> List[Candle]:
    """KIS 국내주식 페이지네이션 조회 (최대 100일씩, 구간 분할)"""
    import os
    import httpx
    import asyncio

    # KIS API 설정
    app_key = os.getenv("KIS_APP_KEY", "").strip()
    app_secret = os.getenv("KIS_APP_SECRET", "").strip()
    # KIS_APP_KEY가 없으면 PAPER 키 사용 (VPS 환경)
    if not app_key or not app_secret:
        app_key = os.getenv("KIS_PAPER_APP_KEY", "").strip()
        app_secret = os.getenv("KIS_PAPER_APP_SECRET", "").strip()
    is_mock = os.getenv("KIS_MOCK", "true").lower() == "true"

    access_token = await _get_kis_token()
    if not access_token:
        raise ValueError("KIS 토큰 발급 실패 - 국내주식 캔들 조회 불가")

    base_url = "https://openapivts.koreainvestment.com:29443" if is_mock else "https://openapi.koreainvestment.com:9443"
    url = f"{base_url}/uapi/domestic-stock/v1/quotations/inquire-daily-itemchartprice"

    period_code = get_exchange_tf("KIS_KR", timeframe) or "D"

    all_candles = []
    start_time = time.time()

    # 구간별 조회 (100일씩)
    end_date = datetime.now()
    days_per_request = 100

    async with httpx.AsyncClient(timeout=30, verify=True) as client:
        while len(all_candles) < needed:
            if time.time() - start_time > timeout:
                raise ValueError(f"시세 조회 시간 초과 ({timeout}초)")

            start_date = end_date - timedelta(days=days_per_request)

            headers = {
                "Content-Type": "application/json; charset=utf-8",
                "authorization": f"Bearer {access_token}",
                "appkey": app_key,
                "appsecret": app_secret,
                "tr_id": "FHKST03010100",
                "custtype": "P",
            }

            params = {
                "FID_COND_MRKT_DIV_CODE": "J",
                "FID_INPUT_ISCD": symbol,
                "FID_INPUT_DATE_1": start_date.strftime("%Y%m%d"),
                "FID_INPUT_DATE_2": end_date.strftime("%Y%m%d"),
                "FID_PERIOD_DIV_CODE": period_code,
                "FID_ORG_ADJ_PRC": "0",
            }

            try:
                resp = await client.get(url, headers=headers, params=params)
                data = resp.json()
            except Exception as e:
                logger.warning(f"KIS_KR 페이지네이션 에러: {e}")
                break

            if data.get("rt_cd") != "0":
                logger.warning(f"KIS_KR API 에러: {data.get('msg1', '')}")
                break

            candles_raw = data.get("output2", [])
            if not candles_raw:
                break

            for c in candles_raw:
                date_str = c.get("stck_bsop_date", "")
                if not date_str:
                    continue
                try:
                    dt = datetime.strptime(date_str, "%Y%m%d")
                    ts = int(dt.timestamp() * 1000)
                except:
                    continue

                all_candles.append(Candle(
                    ts=ts,
                    o=float(c.get("stck_oprc", 0) or 0),
                    h=float(c.get("stck_hgpr", 0) or 0),
                    l=float(c.get("stck_lwpr", 0) or 0),
                    c=float(c.get("stck_clpr", 0) or 0),
                    v=float(c.get("acml_vol", 0) or 0),
                ))

            # 다음 구간으로
            end_date = start_date - timedelta(days=1)

            # Rate limit 방지
            await asyncio.sleep(0.5)

            # 더 이상 과거 데이터가 없으면 중단
            if len(candles_raw) < 10:
                break

    # 시간순 정렬 (과거 → 최신)
    all_candles.sort(key=lambda c: c.ts)

    return all_candles


async def _fetch_kis_us_paginated(
    symbol: str,
    timeframe: str,
    needed: int,
    timeout: int,
) -> List[Candle]:
    """KIS 해외주식 페이지네이션 조회 (BYMD로 과거 이동)"""
    import os
    import httpx
    import asyncio

    # KIS API 설정
    app_key = os.getenv("KIS_APP_KEY", "").strip()
    app_secret = os.getenv("KIS_APP_SECRET", "").strip()
    # KIS_APP_KEY가 없으면 PAPER 키 사용 (VPS 환경)
    if not app_key or not app_secret:
        app_key = os.getenv("KIS_PAPER_APP_KEY", "").strip()
        app_secret = os.getenv("KIS_PAPER_APP_SECRET", "").strip()
    is_mock = os.getenv("KIS_MOCK", "true").lower() == "true"

    access_token = await _get_kis_token()
    if not access_token:
        raise ValueError("KIS 토큰 발급 실패 - 해외주식 캔들 조회 불가")

    base_url = "https://openapivts.koreainvestment.com:29443" if is_mock else "https://openapi.koreainvestment.com:9443"
    url = f"{base_url}/uapi/overseas-price/v1/quotations/dailyprice"

    gubn = get_exchange_tf("KIS_US", timeframe) or "0"

    # 거래소 자동 판별 (NAS -> NYS -> AMS)
    exchanges_to_try = ["NAS", "NYS", "AMS"]

    all_candles = []
    start_time = time.time()

    async with httpx.AsyncClient(timeout=30, verify=True) as client:
        for excd in exchanges_to_try:
            all_candles = []
            bymd = ""  # 처음에는 빈값 (최신부터)

            while len(all_candles) < needed:
                if time.time() - start_time > timeout:
                    raise ValueError(f"시세 조회 시간 초과 ({timeout}초)")

                headers = {
                    "Content-Type": "application/json; charset=utf-8",
                    "authorization": f"Bearer {access_token}",
                    "appkey": app_key,
                    "appsecret": app_secret,
                    "tr_id": "HHDFS76240000",
                    "custtype": "P",
                }

                params = {
                    "AUTH": "",
                    "EXCD": excd,
                    "SYMB": symbol.upper(),
                    "GUBN": gubn,
                    "BYMD": bymd,
                    "MODP": "1",
                }

                try:
                    resp = await client.get(url, headers=headers, params=params)
                    data = resp.json()
                except Exception as e:
                    logger.warning(f"KIS_US 페이지네이션 에러 ({excd}): {e}")
                    break

                if data.get("rt_cd") != "0":
                    break

                candles_raw = data.get("output2", [])
                if not candles_raw:
                    break

                for c in candles_raw:
                    date_str = c.get("xymd", "")
                    if not date_str:
                        continue
                    try:
                        dt = datetime.strptime(date_str, "%Y%m%d")
                        ts = int(dt.timestamp() * 1000)
                    except:
                        continue

                    all_candles.append(Candle(
                        ts=ts,
                        o=float(c.get("open", 0) or 0),
                        h=float(c.get("high", 0) or 0),
                        l=float(c.get("low", 0) or 0),
                        c=float(c.get("clos", 0) or 0),
                        v=float(c.get("tvol", 0) or 0),
                    ))

                # 다음 페이지로 (가장 오래된 날짜 이전으로)
                if candles_raw:
                    oldest_date = candles_raw[-1].get("xymd", "")
                    if oldest_date and oldest_date != bymd:
                        bymd = oldest_date
                    else:
                        break
                else:
                    break

                # Rate limit 방지
                await asyncio.sleep(0.5)

            # 데이터를 찾았으면 루프 종료
            if all_candles:
                break

    # 시간순 정렬 (과거 → 최신)
    all_candles.sort(key=lambda c: c.ts)

    return all_candles


async def _fetch_alpaca_paginated(
    symbol: str,
    timeframe: str,
    needed: int,
    timeout: int,
) -> List[Candle]:
    """
    Alpaca 페이지네이션 조회 (next_page_token 기반)

    GET https://data.alpaca.markets/v2/stocks/{symbol}/bars
    """
    import os
    import urllib.request
    import urllib.parse
    import asyncio

    api_key = os.getenv("ALPACA_API_KEY", "").strip()
    api_secret = os.getenv("ALPACA_API_SECRET", "").strip()
    data_url = os.getenv("ALPACA_DATA_URL", "https://data.alpaca.markets").rstrip("/")

    if not api_key or not api_secret:
        logger.error("ALPACA API 키 없음 - 백테스트 캔들 조회 불가")
        return []

    # 타임프레임 변환
    alpaca_tf = get_exchange_tf("ALPACA", timeframe)
    if not alpaca_tf:
        alpaca_tf = "1Day"

    all_candles: List[Candle] = []
    start_time_check = time.time()

    # 시작/종료 날짜 계산 (needed 봉수 기준)
    tf_ms = TF_TO_MS.get(timeframe, 24 * 60 * 60 * 1000)
    now_ms = int(time.time() * 1000)

    # 충분한 과거 데이터 조회 (주말/공휴일 감안 2배)
    duration_ms = tf_ms * needed * 2
    start_ts = now_ms - duration_ms

    start_dt = datetime.fromtimestamp(start_ts / 1000, tz=timezone.utc)
    end_dt = datetime.fromtimestamp(now_ms / 1000, tz=timezone.utc)

    start_str = start_dt.strftime("%Y-%m-%dT00:00:00Z")
    end_str = end_dt.strftime("%Y-%m-%dT23:59:59Z")

    headers = {
        "APCA-API-KEY-ID": api_key,
        "APCA-API-SECRET-KEY": api_secret,
        "Accept": "application/json",
    }

    next_page_token = None
    symbol = symbol.upper().strip()

    while len(all_candles) < needed:
        if time.time() - start_time_check > timeout:
            logger.warning(f"ALPACA 백테스트 타임아웃 ({timeout}초)")
            break

        # URL 구성
        params: Dict[str, Any] = {
            "timeframe": alpaca_tf,
            "start": start_str,
            "end": end_str,
            "limit": 1000,
            "adjustment": "all",  # 수정주가
            "feed": "iex",        # 무료 데이터 피드
        }

        if next_page_token:
            params["page_token"] = next_page_token

        url = f"{data_url}/v2/stocks/{symbol}/bars?{urllib.parse.urlencode(params)}"
        req = urllib.request.Request(url, headers=headers)

        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                data = json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            error_body = e.read().decode("utf-8", errors="replace")
            logger.error(f"ALPACA 백테스트 HTTP 에러: {e.code} - {error_body}")
            if "not found" in error_body.lower() or e.code == 404:
                raise ValueError(f"종목을 찾을 수 없습니다: {symbol}. 미국 주식 심볼을 확인해주세요 (예: AAPL, MSFT)")
            break
        except Exception as e:
            logger.error(f"ALPACA 백테스트 조회 에러: {e}")
            break

        bars = data.get("bars", [])
        if not bars:
            logger.info(f"ALPACA 더 이상 데이터 없음: {symbol}")
            break

        for bar in bars:
            # Alpaca 타임스탬프: RFC3339 → Unix ms
            t_str = bar.get("t", "")
            if t_str:
                try:
                    dt = datetime.fromisoformat(t_str.replace("Z", "+00:00"))
                    ts = int(dt.timestamp() * 1000)
                except:
                    ts = 0
            else:
                ts = 0

            all_candles.append(Candle(
                ts=ts,
                o=float(bar.get("o", 0) or 0),
                h=float(bar.get("h", 0) or 0),
                l=float(bar.get("l", 0) or 0),
                c=float(bar.get("c", 0) or 0),
                v=float(bar.get("v", 0) or 0),
            ))

        # 다음 페이지 토큰 확인
        next_page_token = data.get("next_page_token")
        if not next_page_token:
            break

        # Rate limit 방지
        await asyncio.sleep(0.2)

    # 시간순 정렬 (과거 → 최신)
    all_candles.sort(key=lambda c: c.ts)

    logger.info(f"ALPACA 백테스트 캔들 조회 완료: {symbol} {timeframe} {len(all_candles)}봉")

    return all_candles


async def _fetch_okx_paginated(
    symbol: str,
    timeframe: str,
    needed: int,
    timeout: int,
    ctx,
) -> List[Candle]:
    """OKX 페이지네이션 조회 (100개씩, 429 시 1회 재시도)"""
    import urllib.request
    import asyncio

    all_candles = []
    after = ""
    bar = get_exchange_tf("OKX", timeframe)
    inst_id = symbol.upper()
    start_time = time.time()

    while len(all_candles) < needed:
        # 타임아웃 체크
        if time.time() - start_time > timeout:
            raise ValueError(f"시세 조회 시간 초과 ({timeout}초). 기간을 줄여보세요.")

        url = f"https://www.okx.com/api/v5/market/history-candles?instId={inst_id}&bar={bar}&limit=100"
        if after:
            url += f"&after={after}"

        req = urllib.request.Request(url, headers={
            "Accept": "application/json",
            "User-Agent": "bbooster-hub/1.0",
        })

        data = None
        for attempt in range(2):  # 최대 2회 시도
            try:
                with urllib.request.urlopen(req, timeout=10, context=ctx) as resp:
                    data = json.loads(resp.read().decode("utf-8"))
                break
            except urllib.error.HTTPError as e:
                if e.code == 429 and attempt == 0:
                    logger.warning("OKX 429 Rate Limit, 3초 대기 후 재시도")
                    await asyncio.sleep(3)
                    continue
                elif e.code == 429:
                    raise ValueError("OKX 요청이 제한되었습니다. 2~3분 후 다시 시도해주세요.")
                raise ValueError(f"OKX 연결 실패: HTTP {e.code}")
            except Exception as e:
                raise ValueError(f"OKX 연결 실패: {str(e)}")

        if data is None:
            raise ValueError("OKX 요청이 제한되었습니다. 2~3분 후 다시 시도해주세요.")

        if data.get("code") != "0":
            msg = data.get("msg", "알 수 없는 오류")
            if "instrument" in msg.lower() or "not found" in msg.lower():
                raise ValueError(f"종목을 찾을 수 없습니다: {symbol}. 종목명을 확인해주세요 (예: BTC-USDT)")
            raise ValueError(f"거래소 API 오류: {msg}")

        bars = data.get("data", [])
        if not bars:
            break

        for bar_data in bars:
            # OKX: [ts, o, h, l, c, vol, volCcy, volCcyQuote, confirm]
            all_candles.append(Candle(
                ts=int(bar_data[0]),
                o=float(bar_data[1]),
                h=float(bar_data[2]),
                l=float(bar_data[3]),
                c=float(bar_data[4]),
                v=float(bar_data[5]),
            ))

        after = bars[-1][0]

        if len(bars) < 100:
            break

    return all_candles


async def _fetch_binance_paginated(
    symbol: str,
    timeframe: str,
    needed: int,
    timeout: int,
    ctx,
) -> List[Candle]:
    """Binance 페이지네이션 조회 (1000개씩)"""
    import urllib.request

    all_candles = []
    end_time = None
    interval = get_exchange_tf("BINANCE", timeframe)
    binance_symbol = symbol.replace("-", "").upper()
    start_time = time.time()

    while len(all_candles) < needed:
        if time.time() - start_time > timeout:
            raise ValueError(f"시세 조회 시간 초과 ({timeout}초). 기간을 줄여보세요.")

        url = f"https://api.binance.com/api/v3/klines?symbol={binance_symbol}&interval={interval}&limit=1000"
        if end_time:
            url += f"&endTime={end_time}"

        req = urllib.request.Request(url, headers={
            "Accept": "application/json",
            "User-Agent": "bbooster-hub/1.0",
        })

        try:
            with urllib.request.urlopen(req, timeout=10, context=ctx) as resp:
                bars = json.loads(resp.read().decode("utf-8"))
        except Exception as e:
            raise ValueError(f"Binance 연결 실패: {str(e)}")

        if isinstance(bars, dict) and bars.get("code"):
            msg = bars.get("msg", "알 수 없는 오류")
            if "invalid symbol" in msg.lower():
                raise ValueError(f"종목을 찾을 수 없습니다: {symbol}. 종목명을 확인해주세요 (예: BTC-USDT)")
            raise ValueError(f"거래소 API 오류: {msg}")

        if not bars:
            break

        for bar_data in bars:
            # Binance: [openTime, o, h, l, c, vol, closeTime, ...]
            all_candles.append(Candle(
                ts=int(bar_data[0]),
                o=float(bar_data[1]),
                h=float(bar_data[2]),
                l=float(bar_data[3]),
                c=float(bar_data[4]),
                v=float(bar_data[5]),
            ))

        end_time = bars[0][0] - 1  # 이전 페이지

        if len(bars) < 1000:
            break

    return all_candles


async def _fetch_bybit_paginated(
    symbol: str,
    timeframe: str,
    needed: int,
    timeout: int,
    ctx,
) -> List[Candle]:
    """Bybit 페이지네이션 조회 (200개씩)"""
    import urllib.request

    all_candles = []
    end = None
    interval = get_exchange_tf("BYBIT", timeframe)
    bybit_symbol = symbol.replace("-", "").upper()
    start_time = time.time()

    while len(all_candles) < needed:
        if time.time() - start_time > timeout:
            raise ValueError(f"시세 조회 시간 초과 ({timeout}초). 기간을 줄여보세요.")

        url = f"https://api.bybit.com/v5/market/kline?category=spot&symbol={bybit_symbol}&interval={interval}&limit=200"
        if end:
            url += f"&end={end}"

        req = urllib.request.Request(url, headers={
            "Accept": "application/json",
            "User-Agent": "bbooster-hub/1.0",
        })

        try:
            with urllib.request.urlopen(req, timeout=10, context=ctx) as resp:
                data = json.loads(resp.read().decode("utf-8"))
        except Exception as e:
            raise ValueError(f"Bybit 연결 실패: {str(e)}")

        if data.get("retCode") != 0:
            msg = data.get("retMsg", "알 수 없는 오류")
            if "symbol" in msg.lower() or "invalid" in msg.lower():
                raise ValueError(f"종목을 찾을 수 없습니다: {symbol}. 종목명을 확인해주세요 (예: BTC-USDT)")
            raise ValueError(f"거래소 API 오류: {msg}")

        bars = data.get("result", {}).get("list", [])
        if not bars:
            break

        for bar_data in bars:
            # Bybit: [startTime, o, h, l, c, vol, turnover]
            all_candles.append(Candle(
                ts=int(bar_data[0]),
                o=float(bar_data[1]),
                h=float(bar_data[2]),
                l=float(bar_data[3]),
                c=float(bar_data[4]),
                v=float(bar_data[5]),
            ))

        end = bars[-1][0]

        if len(bars) < 200:
            break

    return all_candles

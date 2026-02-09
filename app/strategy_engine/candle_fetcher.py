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

import numpy as np

from .models import Candle

logger = logging.getLogger(__name__)


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
}

# Exchange timeframe format mapping
EXCHANGE_TF_MAP: Dict[str, Dict[str, str]] = {
    "OKX": {
        "1m": "1m", "3m": "3m", "5m": "5m", "15m": "15m", "30m": "30m",
        "1h": "1H", "2h": "2H", "4h": "4H", "6h": "6H", "12h": "12H",
        "1D": "1D", "1W": "1W",
    },
    "BINANCE": {
        "1m": "1m", "3m": "3m", "5m": "5m", "15m": "15m", "30m": "30m",
        "1h": "1h", "2h": "2h", "4h": "4h", "6h": "6h", "12h": "12h",
        "1D": "1d", "1W": "1w",
    },
    "BYBIT": {
        "1m": "1", "3m": "3", "5m": "5", "15m": "15", "30m": "30",
        "1h": "60", "2h": "120", "4h": "240", "6h": "360", "12h": "720",
        "1D": "D", "1W": "W",
    },
    "UPBIT": {
        "1m": "minutes/1", "3m": "minutes/3", "5m": "minutes/5",
        "15m": "minutes/15", "30m": "minutes/30", "1h": "minutes/60",
        "4h": "minutes/240", "1D": "days", "1W": "weeks",
    },
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

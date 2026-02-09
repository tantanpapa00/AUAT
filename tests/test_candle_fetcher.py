# tests/test_candle_fetcher.py
"""
Tests for candle_fetcher.py - OHLCV data fetching and caching.

Phase 2: Candle data management tests.
"""

import pytest
import numpy as np
from unittest.mock import AsyncMock, patch, MagicMock
from datetime import datetime, timezone

from app.strategy_engine.candle_fetcher import (
    CandleData,
    CandleCache,
    get_candle_cache,
)


class TestCandleData:
    """Test CandleData dataclass."""

    def test_candle_data_creation(self):
        """Test CandleData creation with numpy arrays."""
        candle_data = CandleData(
            exchange="okx",
            symbol="BTC-USDT",
            timeframe="15m",
            timestamps=np.array([1000, 2000, 3000]),
            opens=np.array([100.0, 101.0, 102.0]),
            highs=np.array([101.0, 102.0, 103.0]),
            lows=np.array([99.0, 100.0, 101.0]),
            closes=np.array([100.5, 101.5, 102.5]),
            volumes=np.array([1000.0, 1100.0, 1200.0]),
        )

        assert candle_data.count == 3
        assert len(candle_data.opens) == 3
        assert candle_data.closes[-1] == 102.5
        assert candle_data.exchange == "okx"
        assert candle_data.symbol == "BTC-USDT"

    def test_candle_data_empty(self):
        """Test CandleData with empty arrays."""
        candle_data = CandleData(
            exchange="okx",
            symbol="BTC-USDT",
            timeframe="15m",
            timestamps=np.array([]),
            opens=np.array([]),
            highs=np.array([]),
            lows=np.array([]),
            closes=np.array([]),
            volumes=np.array([]),
        )

        assert candle_data.count == 0

    def test_candle_data_count_property(self):
        """Test count property returns correct length."""
        n = 100
        candle_data = CandleData(
            exchange="okx",
            symbol="BTC-USDT",
            timeframe="15m",
            timestamps=np.arange(n),
            opens=np.zeros(n),
            highs=np.zeros(n),
            lows=np.zeros(n),
            closes=np.zeros(n),
            volumes=np.zeros(n),
        )

        assert candle_data.count == n


class TestCandleCache:
    """Test CandleCache class."""

    def test_cache_key_generation(self):
        """Test cache key format."""
        cache = CandleCache()
        key = cache._cache_key("okx", "BTC-USDT", "15m")
        assert key == "okx:BTC-USDT:15m"

    def test_cache_key_different_exchanges(self):
        """Test cache keys are unique per exchange."""
        cache = CandleCache()
        key1 = cache._cache_key("okx", "BTC-USDT", "15m")
        key2 = cache._cache_key("binance", "BTC-USDT", "15m")
        assert key1 != key2

    def test_cache_key_different_timeframes(self):
        """Test cache keys are unique per timeframe."""
        cache = CandleCache()
        key1 = cache._cache_key("okx", "BTC-USDT", "15m")
        key2 = cache._cache_key("okx", "BTC-USDT", "4h")
        assert key1 != key2


class TestGetCandleCache:
    """Test global cache singleton."""

    def test_get_candle_cache_singleton(self):
        """Test get_candle_cache returns same instance."""
        cache1 = get_candle_cache()
        cache2 = get_candle_cache()
        assert cache1 is cache2

    def test_cache_is_candle_cache_instance(self):
        """Test returned cache is CandleCache instance."""
        cache = get_candle_cache()
        assert isinstance(cache, CandleCache)


class TestCandleCacheGetCandles:
    """Test CandleCache.get_candles method."""

    @pytest.mark.asyncio
    async def test_get_candles_calls_fetcher(self):
        """Test get_candles calls fetch function when cache miss."""
        cache = CandleCache()
        cache._memory_cache = {}  # Clear cache

        mock_candles = CandleData(
            exchange="okx",
            symbol="BTC-USDT",
            timeframe="15m",
            timestamps=np.array([1000]),
            opens=np.array([100.0]),
            highs=np.array([101.0]),
            lows=np.array([99.0]),
            closes=np.array([100.5]),
            volumes=np.array([1000.0]),
        )

        with patch(
            "app.strategy_engine.candle_fetcher.fetch_candles_from_exchange",
            new_callable=AsyncMock,
        ) as mock_fetch:
            mock_fetch.return_value = mock_candles

            result = await cache.get_candles(
                exchange="okx",
                symbol="BTC-USDT",
                timeframe="15m",
                count=100,
            )

            mock_fetch.assert_called_once()
            assert result.count == 1

    @pytest.mark.asyncio
    async def test_get_candles_uses_cache_on_hit(self):
        """Test get_candles returns cached data when available and fresh."""
        cache = CandleCache()

        # Pre-populate cache with enough data
        mock_candles = CandleData(
            exchange="okx",
            symbol="BTC-USDT",
            timeframe="15m",
            timestamps=np.array([1000, 2000, 3000]),
            opens=np.array([100.0, 101.0, 102.0]),
            highs=np.array([101.0, 102.0, 103.0]),
            lows=np.array([99.0, 100.0, 101.0]),
            closes=np.array([100.5, 101.5, 102.5]),
            volumes=np.array([1000.0, 1100.0, 1200.0]),
        )
        key = "okx:BTC-USDT:15m"
        cache._memory_cache[key] = mock_candles

        with patch(
            "app.strategy_engine.candle_fetcher.fetch_candles_from_exchange",
            new_callable=AsyncMock,
        ) as mock_fetch:
            result = await cache.get_candles(
                exchange="okx",
                symbol="BTC-USDT",
                timeframe="15m",
                count=2,
            )

            # Should not call fetch - using cache
            mock_fetch.assert_not_called()
            assert result.count == 2


class TestCandleDataValidation:
    """Test CandleData validation scenarios."""

    def test_candle_data_with_nan_values(self):
        """Test CandleData handles NaN values."""
        candle_data = CandleData(
            exchange="okx",
            symbol="BTC-USDT",
            timeframe="15m",
            timestamps=np.array([1000, 2000, 3000]),
            opens=np.array([100.0, np.nan, 102.0]),
            highs=np.array([101.0, 102.0, 103.0]),
            lows=np.array([99.0, 100.0, 101.0]),
            closes=np.array([100.5, 101.5, 102.5]),
            volumes=np.array([1000.0, 1100.0, 1200.0]),
        )

        assert candle_data.count == 3
        assert np.isnan(candle_data.opens[1])

    def test_candle_data_preserves_order(self):
        """Test CandleData preserves chronological order."""
        timestamps = np.array([1000, 2000, 3000, 4000, 5000])
        closes = np.array([100.0, 101.0, 102.0, 103.0, 104.0])

        candle_data = CandleData(
            exchange="okx",
            symbol="BTC-USDT",
            timeframe="15m",
            timestamps=timestamps,
            opens=closes - 0.5,
            highs=closes + 0.5,
            lows=closes - 1.0,
            closes=closes,
            volumes=np.ones(5) * 1000,
        )

        # Verify order preserved
        assert candle_data.timestamps[0] < candle_data.timestamps[-1]
        assert candle_data.closes[0] < candle_data.closes[-1]


class TestCandleFetcherIntegration:
    """Integration tests for candle fetcher (mocked exchange calls)."""

    @pytest.mark.asyncio
    async def test_multiple_symbols_cached_separately(self):
        """Test different symbols are cached separately."""
        cache = CandleCache()
        cache._memory_cache = {}

        btc_candles = CandleData(
            exchange="okx",
            symbol="BTC-USDT",
            timeframe="15m",
            timestamps=np.array([1000]),
            opens=np.array([50000.0]),
            highs=np.array([51000.0]),
            lows=np.array([49000.0]),
            closes=np.array([50500.0]),
            volumes=np.array([100.0]),
        )

        eth_candles = CandleData(
            exchange="okx",
            symbol="ETH-USDT",
            timeframe="15m",
            timestamps=np.array([1000]),
            opens=np.array([3000.0]),
            highs=np.array([3100.0]),
            lows=np.array([2900.0]),
            closes=np.array([3050.0]),
            volumes=np.array([500.0]),
        )

        async def mock_fetch(exchange, symbol, timeframe, limit):
            if "BTC" in symbol:
                return btc_candles
            return eth_candles

        with patch(
            "app.strategy_engine.candle_fetcher.fetch_candles_from_exchange",
            new_callable=AsyncMock,
            side_effect=mock_fetch,
        ):
            btc_result = await cache.get_candles("okx", "BTC-USDT", "15m", 1)
            eth_result = await cache.get_candles("okx", "ETH-USDT", "15m", 1)

            assert btc_result.closes[0] == 50500.0
            assert eth_result.closes[0] == 3050.0

    @pytest.mark.asyncio
    async def test_multiple_timeframes_cached_separately(self):
        """Test different timeframes are cached separately."""
        cache = CandleCache()
        cache._memory_cache = {}

        candles_15m = CandleData(
            exchange="okx",
            symbol="BTC-USDT",
            timeframe="15m",
            timestamps=np.array([1000]),
            opens=np.array([100.0]),
            highs=np.array([101.0]),
            lows=np.array([99.0]),
            closes=np.array([100.5]),
            volumes=np.array([1000.0]),
        )

        candles_4h = CandleData(
            exchange="okx",
            symbol="BTC-USDT",
            timeframe="4h",
            timestamps=np.array([1000]),
            opens=np.array([100.0]),
            highs=np.array([105.0]),
            lows=np.array([95.0]),
            closes=np.array([103.0]),
            volumes=np.array([10000.0]),
        )

        async def mock_fetch(exchange, symbol, timeframe, limit):
            if timeframe == "15m":
                return candles_15m
            return candles_4h

        with patch(
            "app.strategy_engine.candle_fetcher.fetch_candles_from_exchange",
            new_callable=AsyncMock,
            side_effect=mock_fetch,
        ):
            result_15m = await cache.get_candles("okx", "BTC-USDT", "15m", 1)
            result_4h = await cache.get_candles("okx", "BTC-USDT", "4h", 1)

            assert result_15m.closes[0] == 100.5
            assert result_4h.closes[0] == 103.0


class TestCandleDataToCandles:
    """Test CandleData.to_candles method."""

    def test_to_candles_conversion(self):
        """Test conversion to Candle objects."""
        candle_data = CandleData(
            exchange="okx",
            symbol="BTC-USDT",
            timeframe="15m",
            timestamps=np.array([1000, 2000]),
            opens=np.array([100.0, 101.0]),
            highs=np.array([101.0, 102.0]),
            lows=np.array([99.0, 100.0]),
            closes=np.array([100.5, 101.5]),
            volumes=np.array([1000.0, 1100.0]),
        )

        candles = candle_data.to_candles()

        assert len(candles) == 2
        assert candles[0].ts == 1000
        assert candles[0].o == 100.0
        assert candles[0].c == 100.5
        assert candles[1].ts == 2000

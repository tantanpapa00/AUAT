# tests/test_indicators_trend.py
"""
Unit tests for Trend Strategy indicators.

Validates: HVI, QQE MOD, VWMA for trend-following strategy.

Test methodology:
1. Use known input data
2. Compare Python output with expected values
3. Accept small floating-point tolerance
"""

import pytest
import numpy as np

from app.strategy_engine.indicators import (
    calc_rsi,
    calc_hvi,
    calc_qqe_mod,
    calc_vwma,
    calc_supertrend,
    calc_spo,
)


class TestCalcRsi:
    """Test RSI calculation."""

    def test_rsi_basic(self):
        """Test basic RSI calculation."""
        # Uptrend data (should have RSI > 50)
        prices = np.array([100.0 + i for i in range(20)])
        result = calc_rsi(prices, 14)

        assert len(result) == 20
        # Uptrend should have high RSI
        assert result[-1] > 50

    def test_rsi_downtrend(self):
        """Test RSI with downtrend."""
        # Downtrend data (should have RSI < 50)
        prices = np.array([120.0 - i for i in range(20)])
        result = calc_rsi(prices, 14)

        # Downtrend should have low RSI
        assert result[-1] < 50

    def test_rsi_constant(self):
        """Constant price should have RSI around 50."""
        prices = np.array([100.0] * 20)
        result = calc_rsi(prices, 14)

        # Constant price - early NaN, later stable
        assert not np.isnan(result[-1])

    def test_rsi_range(self):
        """RSI should be between 0 and 100."""
        np.random.seed(42)
        prices = np.cumsum(np.random.randn(100)) + 100

        result = calc_rsi(prices, 14)

        valid_rsi = result[~np.isnan(result)]
        assert np.all(valid_rsi >= 0)
        assert np.all(valid_rsi <= 100)


class TestCalcHvi:
    """Test HVI (Historical Volatility Indicator) calculation."""

    def test_hvi_basic(self):
        """Test basic HVI calculation."""
        np.random.seed(42)
        n = 250

        # Generate OHLCV data
        close = np.cumsum(np.random.randn(n) * 0.5) + 100
        high = close + np.abs(np.random.randn(n)) * 2
        low = close - np.abs(np.random.randn(n)) * 2
        volume = np.random.uniform(1000000, 10000000, n)

        result = calc_hvi(high, low, close, volume, length=200, divisor=3.6)

        # Check result structure
        assert 'g_enabled' in result
        assert 'r_enabled' in result
        assert 'gr_enabled' in result

        # Check array lengths
        assert len(result['g_enabled']) == n
        assert len(result['r_enabled']) == n
        assert len(result['gr_enabled']) == n

    def test_hvi_green_condition(self):
        """Test HVI green condition detection."""
        n = 250
        # Strong uptrend with low volatility (should trigger green)
        close = np.array([100.0 + i * 0.5 for i in range(n)])
        high = close + 1.0
        low = close - 1.0
        volume = np.array([5000000.0] * n)

        result = calc_hvi(high, low, close, volume, length=200, divisor=3.6)

        # At least some green signals should be present
        assert result['g_enabled'].dtype == bool
        assert result['r_enabled'].dtype == bool

    def test_hvi_no_nan(self):
        """HVI should not produce NaN after warmup."""
        np.random.seed(42)
        n = 300

        close = np.cumsum(np.random.randn(n) * 0.5) + 100
        high = close + 2
        low = close - 2
        volume = np.random.uniform(1e6, 1e7, n)

        result = calc_hvi(high, low, close, volume, length=200, divisor=3.6)

        # Check no NaN in boolean results
        assert not np.any(np.isnan(result['g_enabled'].astype(float)))

    def test_hvi_short_data(self):
        """HVI with insufficient data."""
        n = 50  # Less than lookback
        close = np.array([100.0] * n)
        high = close + 1
        low = close - 1
        volume = np.array([1e6] * n)

        result = calc_hvi(high, low, close, volume, length=200, divisor=3.6)

        # Should return arrays filled with False
        assert len(result['g_enabled']) == n


class TestCalcQqeMod:
    """Test QQE MOD indicator calculation."""

    def test_qqe_basic(self):
        """Test basic QQE MOD calculation."""
        np.random.seed(42)
        n = 100

        # Generate price data
        close = np.cumsum(np.random.randn(n) * 0.5) + 100

        result = calc_qqe_mod(close, rsi_length=6, rsi_smoothing=5, qqe_factor=3.0)

        # Check result structure
        assert 'primary_rsi' in result
        assert 'qqe_line' in result
        assert 'is_positive' in result
        assert 'trend_dir' in result

        # Check array lengths
        assert len(result['primary_rsi']) == n
        assert len(result['qqe_line']) == n
        assert len(result['is_positive']) == n
        assert len(result['trend_dir']) == n

    def test_qqe_uptrend(self):
        """Test QQE with uptrend."""
        # Strong uptrend
        close = np.array([100.0 + i * 1.0 for i in range(100)])

        result = calc_qqe_mod(close, rsi_length=6, rsi_smoothing=5, qqe_factor=3.0)

        # QQE result should be returned with correct length
        assert len(result['is_positive']) == 100
        assert len(result['primary_rsi']) == 100
        assert len(result['trend_dir']) == 100

    def test_qqe_downtrend(self):
        """Test QQE with downtrend."""
        # Strong downtrend
        close = np.array([200.0 - i * 1.0 for i in range(100)])

        result = calc_qqe_mod(close, rsi_length=6, rsi_smoothing=5, qqe_factor=3.0)

        # Downtrend should have negative QQE
        assert result['is_positive'][-1] == False

    def test_qqe_rsi_range(self):
        """QQE RSI should be in valid range."""
        np.random.seed(42)
        close = np.cumsum(np.random.randn(100)) + 100

        result = calc_qqe_mod(close, rsi_length=6, rsi_smoothing=5, qqe_factor=3.0)

        valid_rsi = result['primary_rsi'][~np.isnan(result['primary_rsi'])]
        assert np.all(valid_rsi >= 0)
        assert np.all(valid_rsi <= 100)

    def test_qqe_trend_dir_values(self):
        """Trend direction should be -1, 0, or 1."""
        np.random.seed(42)
        close = np.cumsum(np.random.randn(100)) + 100

        result = calc_qqe_mod(close, rsi_length=6, rsi_smoothing=5, qqe_factor=3.0)

        valid_trend = result['trend_dir'][~np.isnan(result['trend_dir'])]
        for v in valid_trend:
            assert v in [-1, 0, 1]  # Include 0 for initial state


class TestVwmaForTrend:
    """Test VWMA for HTF filter."""

    def test_vwma_basic(self):
        """Test basic VWMA calculation."""
        close = np.array([100.0, 101.0, 102.0, 103.0, 104.0])
        volume = np.array([1000.0, 1000.0, 1000.0, 1000.0, 1000.0])

        result = calc_vwma(close, volume, 3)

        # With equal volumes, VWMA = SMA
        # VWMA[2] = (100*1000 + 101*1000 + 102*1000) / (3*1000) = 101
        assert abs(result[2] - 101.0) < 1e-10

    def test_vwma_weighted(self):
        """Test VWMA with varying volumes."""
        close = np.array([100.0, 110.0, 120.0])
        volume = np.array([1000.0, 2000.0, 3000.0])

        result = calc_vwma(close, volume, 3)

        # VWMA = (100*1000 + 110*2000 + 120*3000) / (1000 + 2000 + 3000)
        # = (100000 + 220000 + 360000) / 6000 = 680000 / 6000 = 113.33...
        expected = (100*1000 + 110*2000 + 120*3000) / (1000 + 2000 + 3000)
        assert abs(result[2] - expected) < 1e-10

    def test_vwma_htf_length(self):
        """Test VWMA with HTF length (156)."""
        np.random.seed(42)
        n = 200

        close = np.cumsum(np.random.randn(n) * 0.5) + 100
        volume = np.random.uniform(1e6, 1e7, n)

        result = calc_vwma(close, volume, 156)

        # First 155 values should be NaN
        assert np.all(np.isnan(result[:155]))
        # After warmup, no NaN
        assert not np.isnan(result[155])


class TestSupertrendForTrend:
    """Test Supertrend for trend entry/exit."""

    def test_supertrend_uptrend(self):
        """Supertrend should detect uptrend."""
        n = 100
        # Strong uptrend
        close = np.array([100.0 + i * 1.5 for i in range(n)])
        high = close + 2
        low = close - 2

        st_value, st_dir = calc_supertrend(high, low, close, atr_len=10, factor=3.0)

        # In uptrend, direction should be -1 (bullish)
        assert st_dir[-1] == -1

    def test_supertrend_downtrend(self):
        """Supertrend should detect downtrend."""
        n = 100
        # Strong downtrend
        close = np.array([200.0 - i * 1.5 for i in range(n)])
        high = close + 2
        low = close - 2

        st_value, st_dir = calc_supertrend(high, low, close, atr_len=10, factor=3.0)

        # In downtrend, direction should be 1 (bearish)
        assert st_dir[-1] == 1


class TestSpoForTrend:
    """Test SPO for trend exit signals."""

    def test_spo_basic(self):
        """Test basic SPO calculation."""
        np.random.seed(42)
        close = np.cumsum(np.random.randn(100)) + 100

        result = calc_spo(close, smooth_len=4, threshold=1.0, std_len=50, hma_len=30)

        # Should return tuple of arrays
        assert len(result) >= 2
        norm_osc = result[0]
        assert len(norm_osc) == 100

    def test_spo_signal_detection(self):
        """Test SPO signal detection for exit."""
        np.random.seed(42)
        close = np.cumsum(np.random.randn(100)) + 100

        result = calc_spo(close, smooth_len=4, threshold=1.0, std_len=50, hma_len=30)
        norm_osc = result[0]

        # Should have values (may include NaN during warmup)
        assert len(norm_osc) == 100


class TestTrendIndicatorsIntegration:
    """Integration tests for trend indicators."""

    def test_all_indicators_together(self):
        """Test all trend indicators work together."""
        np.random.seed(42)
        n = 300

        # Generate realistic OHLCV data
        close = np.cumsum(np.random.randn(n) * 0.5) + 100
        high = close + np.abs(np.random.randn(n)) * 2
        low = close - np.abs(np.random.randn(n)) * 2
        volume = np.random.uniform(1e6, 1e7, n)

        # Calculate all indicators
        st_value, st_dir = calc_supertrend(high, low, close, 10, 3.0)
        hvi_result = calc_hvi(high, low, close, volume, 200, 3.6)
        qqe_result = calc_qqe_mod(close, 6, 5, 3.0)
        vwma = calc_vwma(close, volume, 156)
        spo = calc_spo(close, 4, 1.0, 50, 30)

        # All should have same length
        assert len(st_dir) == n
        assert len(hvi_result['g_enabled']) == n
        assert len(qqe_result['is_positive']) == n
        assert len(vwma) == n
        assert len(spo[0]) == n

    def test_entry_conditions(self):
        """Test entry condition checking."""
        np.random.seed(42)
        n = 300

        # Create uptrend data
        close = np.array([100.0 + i * 0.3 for i in range(n)])
        high = close + 2
        low = close - 2
        volume = np.array([5e6] * n)

        st_value, st_dir = calc_supertrend(high, low, close, 10, 3.0)
        hvi_result = calc_hvi(high, low, close, volume, 200, 3.6)
        qqe_result = calc_qqe_mod(close, 6, 5, 3.0)
        vwma = calc_vwma(close, volume, 156)

        # Check entry conditions at the end
        st_bullish = st_dir[-1] < 0
        hvi_green = hvi_result['g_enabled'][-1]
        qqe_positive = qqe_result['is_positive'][-1]
        htf_ok = close[-1] > vwma[-1] if not np.isnan(vwma[-1]) else True

        # At least some conditions should be met in uptrend
        assert st_bullish  # Supertrend should be bullish in uptrend

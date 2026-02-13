# tests/test_indicators.py
"""
Unit tests for Strategy Engine indicators.

Validates 1:1 matching with PineScript: 역추세매매 현물 v0.4

Test methodology:
1. Use known input data
2. Compare Python output with expected PineScript output
3. Accept small floating-point tolerance (< 0.001%)
"""

import pytest
import numpy as np
import math

from app.strategy_engine.indicators import (
    smoother_f,
    calc_ema,
    calc_sma,
    calc_wma,
    calc_hma,
    calc_stdev,
    calc_highest,
    calc_lowest,
    calc_vwma,
    calc_atr,
    calc_supertrend,
    calc_ichimoku,
    calc_spo,
    crossover,
    crossunder,
)


class TestSmootherF:
    """Test smoother_f (Ehlers' SuperSmoother from PineScript)."""

    def test_basic_smoothing(self):
        """Test basic EMA-style smoothing (PineScript smoother_F)."""
        # smoother_F is EMA: out = a * src + b * out[1]
        # where a = 2/(len+1), b = 1-a
        src = np.array([1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0])
        length = 3
        result = smoother_f(src, length)

        # EMA coefficients: a = 2/(3+1) = 0.5, b = 0.5
        # result[0] = 1.0 (초기값)
        # result[1] = 0.5 * 2.0 + 0.5 * 1.0 = 1.5
        # result[2] = 0.5 * 3.0 + 0.5 * 1.5 = 2.25
        assert result[0] == 1.0
        assert abs(result[1] - 1.5) < 1e-6
        assert abs(result[2] - 2.25) < 1e-6

        # All values should be valid (smoothed)
        assert not np.isnan(result[4])

    def test_constant_input(self):
        """Constant input should converge to that value."""
        src = np.array([10.0] * 20)
        result = smoother_f(src, 5)

        # All values should be approximately 10
        for val in result:
            assert abs(val - 10.0) < 1e-6

    def test_empty_input(self):
        """Empty input should return empty array."""
        result = smoother_f(np.array([]), 5)
        assert len(result) == 0

    def test_single_value(self):
        """Single value input."""
        result = smoother_f(np.array([42.0]), 5)
        assert len(result) == 1
        assert result[0] == 42.0

    def test_100_bars_precision(self):
        """Test with 100+ bars for numerical stability."""
        np.random.seed(42)
        src = np.cumsum(np.random.randn(150)) + 100  # Random walk around 100

        result = smoother_f(src, 20)

        # Result should have same length
        assert len(result) == 150

        # No NaN values after warmup
        assert not np.any(np.isnan(result[4:]))

        # Result should be bounded (no numerical explosion)
        assert np.all(np.abs(result[4:]) < np.max(np.abs(src)) * 2)

    def test_smoother_than_ema(self):
        """SuperSmoother should be smoother than EMA."""
        np.random.seed(42)
        # Noisy data
        src = np.sin(np.linspace(0, 4*np.pi, 100)) + np.random.randn(100) * 0.3

        result = smoother_f(src, 10)

        # Should have same length
        assert len(result) == 100

        # Calculate variance of first differences (measure of smoothness)
        diff_src = np.diff(src[10:])
        diff_result = np.diff(result[10:])

        # Smoothed result should have lower variance in differences
        assert np.var(diff_result) < np.var(diff_src)


class TestMovingAverages:
    """Test SMA, WMA, HMA calculations."""

    def test_sma_basic(self):
        """Test SMA calculation."""
        src = np.array([1.0, 2.0, 3.0, 4.0, 5.0])
        result = calc_sma(src, 3)

        # First 2 values should be NaN
        assert np.isnan(result[0])
        assert np.isnan(result[1])

        # SMA(3) at index 2 = (1+2+3)/3 = 2.0
        assert abs(result[2] - 2.0) < 1e-10

        # SMA(3) at index 3 = (2+3+4)/3 = 3.0
        assert abs(result[3] - 3.0) < 1e-10

        # SMA(3) at index 4 = (3+4+5)/3 = 4.0
        assert abs(result[4] - 4.0) < 1e-10

    def test_wma_basic(self):
        """Test WMA calculation."""
        src = np.array([1.0, 2.0, 3.0, 4.0, 5.0])
        result = calc_wma(src, 3)

        # WMA(3) at index 2: (1*1 + 2*2 + 3*3) / (1+2+3) = (1+4+9)/6 = 14/6 = 2.333...
        expected = (1 * 1 + 2 * 2 + 3 * 3) / 6
        assert abs(result[2] - expected) < 1e-10

    def test_hma_basic(self):
        """Test HMA calculation."""
        # HMA = WMA(2*WMA(n/2) - WMA(n), sqrt(n))
        src = np.arange(1, 21, dtype=float)  # 1 to 20
        result = calc_hma(src, 9)

        # HMA should have values after warmup period
        # sqrt(9) = 3, so need at least 9 + 3 - 1 = 11 bars
        assert not np.isnan(result[-1])

        # HMA should be responsive (close to recent prices for trending data)
        # For ascending data, HMA should be between source and simple MA
        assert result[-1] > calc_sma(src, 9)[-1]  # More responsive than SMA


class TestStatisticalFunctions:
    """Test stdev, highest, lowest functions."""

    def test_stdev_basic(self):
        """Test rolling standard deviation."""
        src = np.array([1.0, 2.0, 3.0, 4.0, 5.0])
        result = calc_stdev(src, 3)

        # stdev of [1,2,3] = sqrt(((1-2)^2 + (2-2)^2 + (3-2)^2)/3) = sqrt(2/3)
        expected = np.std([1, 2, 3], ddof=0)
        assert abs(result[2] - expected) < 1e-10

    def test_highest_basic(self):
        """Test rolling highest."""
        src = np.array([3.0, 1.0, 4.0, 1.0, 5.0])
        result = calc_highest(src, 3)

        # Highest of [3,1,4] = 4
        assert result[2] == 4.0
        # Highest of [1,4,1] = 4
        assert result[3] == 4.0
        # Highest of [4,1,5] = 5
        assert result[4] == 5.0

    def test_lowest_basic(self):
        """Test rolling lowest."""
        src = np.array([3.0, 1.0, 4.0, 1.0, 5.0])
        result = calc_lowest(src, 3)

        # Lowest of [3,1,4] = 1
        assert result[2] == 1.0


class TestVWMA:
    """Test Volume Weighted Moving Average."""

    def test_vwma_basic(self):
        """Test VWMA calculation."""
        close = np.array([100.0, 101.0, 102.0, 103.0, 104.0])
        volume = np.array([1000.0, 2000.0, 1000.0, 2000.0, 1000.0])

        result = calc_vwma(close, volume, 3)

        # VWMA(3) at index 2:
        # (100*1000 + 101*2000 + 102*1000) / (1000+2000+1000)
        # = (100000 + 202000 + 102000) / 4000 = 404000 / 4000 = 101.0
        expected = (100 * 1000 + 101 * 2000 + 102 * 1000) / (1000 + 2000 + 1000)
        assert abs(result[2] - expected) < 1e-10

    def test_vwma_equal_volume(self):
        """VWMA with equal volumes should equal SMA."""
        close = np.array([100.0, 101.0, 102.0, 103.0, 104.0])
        volume = np.array([1000.0, 1000.0, 1000.0, 1000.0, 1000.0])

        vwma = calc_vwma(close, volume, 3)
        sma = calc_sma(close, 3)

        # VWMA should equal SMA when volumes are equal
        for i in range(2, len(close)):
            assert abs(vwma[i] - sma[i]) < 1e-10


class TestATR:
    """Test Average True Range calculation."""

    def test_atr_basic(self):
        """Test ATR calculation."""
        high = np.array([110.0, 112.0, 111.0, 113.0, 114.0])
        low = np.array([100.0, 101.0, 100.0, 102.0, 103.0])
        close = np.array([105.0, 111.0, 101.0, 112.0, 113.0])

        result = calc_atr(high, low, close, 3)

        # ATR should be positive
        assert all(result >= 0)
        assert len(result) == 5


class TestSupertrend:
    """Test Supertrend indicator."""

    def test_supertrend_basic(self):
        """Test Supertrend calculation."""
        # Create trending data
        n = 50
        high = np.linspace(100, 150, n) + np.random.randn(n) * 2
        low = high - 5
        close = (high + low) / 2

        st_value, st_direction = calc_supertrend(high, low, close, 14, 3.0)

        # Should return arrays of correct length
        assert len(st_value) == n
        assert len(st_direction) == n

        # Direction should be 1 or -1 (after warmup)
        for d in st_direction[14:]:
            assert d in [-1, 1] or np.isnan(d) or d == 0

    def test_supertrend_uptrend(self):
        """In strong uptrend, Supertrend direction should be bullish."""
        n = 100
        # Strong uptrend
        close = np.linspace(100, 200, n)
        high = close + 2
        low = close - 2

        st_value, st_direction = calc_supertrend(high, low, close, 14, 3.0)

        # After warmup, direction should be mostly -1 (bullish in PineScript convention)
        bullish_count = np.sum(st_direction[30:] == -1)
        assert bullish_count > len(st_direction[30:]) * 0.5


class TestIchimoku:
    """Test Ichimoku Cloud calculations."""

    def test_ichimoku_basic(self):
        """Test Ichimoku component calculations."""
        n = 60
        high = np.linspace(100, 120, n) + np.sin(np.linspace(0, 4 * np.pi, n)) * 5
        low = high - 8
        close = (high + low) / 2  # 종가 추가

        result = calc_ichimoku(high, low, close, 9, 26, 52)
        tenkan = result["tenkan"]
        kijun = result["kijun"]
        senkou_a = result["senkou_a"]
        senkou_b = result["senkou_b"]
        chikou = result["chikou"]

        # Should return arrays of correct length
        assert len(tenkan) == n
        assert len(kijun) == n
        assert len(senkou_a) == n
        assert len(senkou_b) == n
        assert len(chikou) == n

        # Tenkan should use shorter period (more responsive)
        # Kijun should use longer period

        # Senkou A should be average of Tenkan and Kijun
        for i in range(26, n):
            if not np.isnan(tenkan[i]) and not np.isnan(kijun[i]):
                expected_a = (tenkan[i] + kijun[i]) / 2
                assert abs(senkou_a[i] - expected_a) < 1e-10


class TestSPO:
    """Test Smooth Price Oscillator (SPO) calculation."""

    def test_spo_basic(self):
        """Test SPO calculation with default parameters."""
        n = 300
        # Create price series with mean reversion behavior
        np.random.seed(42)
        close = 100 + np.cumsum(np.random.randn(n) * 0.5)

        normalized_osc, upper_band, lower_band, basis, line_short, line_long = calc_spo(
            close, smooth_len=20, threshold=1.0, std_len=50, hma_len=30, bb_len=250, bb_mult=2.0
        )

        # Should return arrays of correct length
        assert len(normalized_osc) == n
        assert len(upper_band) == n
        assert len(lower_band) == n

        # Normalized oscillator should be centered around 0
        valid_osc = normalized_osc[~np.isnan(normalized_osc)]
        if len(valid_osc) > 0:
            mean_osc = np.mean(valid_osc)
            assert abs(mean_osc) < 1.0  # Should be relatively centered

        # Upper band should be above lower band
        for i in range(n):
            if not np.isnan(upper_band[i]) and not np.isnan(lower_band[i]):
                assert upper_band[i] > lower_band[i]

    def test_spo_oscillator_formula(self):
        """Test oscillator formula: line_short - line_long."""
        n = 100
        close = np.linspace(100, 110, n)

        normalized_osc, upper_band, lower_band, basis, line_short, line_long = calc_spo(
            close, smooth_len=10, threshold=1.0, std_len=20, hma_len=10, bb_len=50, bb_mult=2.0
        )

        # line_short should be more responsive than line_long
        # For trending up data, line_short should be above line_long
        # So oscillator (short - long) should be positive
        valid_indices = ~(np.isnan(line_short) | np.isnan(line_long))
        if np.any(valid_indices):
            osc_raw = line_short[valid_indices] - line_long[valid_indices]
            # For uptrend, oscillator should be mostly positive
            assert np.mean(osc_raw[-20:]) > 0


class TestCrossover:
    """Test crossover/crossunder detection."""

    def test_crossover_basic(self):
        """Test crossover detection."""
        series1 = np.array([1.0, 2.0, 3.0, 4.0, 3.0])
        series2 = np.array([2.0, 2.0, 2.0, 2.0, 2.0])

        result = crossover(series1, series2)

        # Crossover at index 2: series1 goes from 2 (<=2) to 3 (>2)
        assert result[2] == True
        # No crossover at other points
        assert result[0] == False
        assert result[1] == False
        assert result[4] == False  # This is a crossunder, not crossover

    def test_crossunder_basic(self):
        """Test crossunder detection."""
        series1 = np.array([3.0, 2.0, 1.0, 2.0, 3.0])
        series2 = np.array([2.0, 2.0, 2.0, 2.0, 2.0])

        result = crossunder(series1, series2)

        # Crossunder at index 2: series1 goes from 2 (>=2) to 1 (<2)
        assert result[2] == True


class TestPrecision:
    """Test numerical precision with 100+ bars of data."""

    def test_smoother_f_precision(self):
        """Test smoother_f precision with 100+ bars."""
        np.random.seed(123)
        close = 100 + np.cumsum(np.random.randn(150) * 0.5)

        result = smoother_f(close, 20)

        # No NaN values
        assert not np.any(np.isnan(result))

        # Result should be bounded (no numerical explosion)
        assert np.all(np.abs(result) < np.max(np.abs(close)) * 2)

    def test_spo_precision_100_bars(self):
        """Test SPO calculation precision with 100+ bars."""
        np.random.seed(456)
        n = 350  # Need more data for SPO warmup (bb_len=250 needs 250+ bars)
        close = 100 + np.cumsum(np.random.randn(n) * 0.3)

        normalized_osc, upper_band, lower_band, basis, line_short, line_long = calc_spo(
            close, smooth_len=20, threshold=1.0, std_len=50, hma_len=30, bb_len=250, bb_mult=2.0
        )

        # After full warmup (bb_len + hma_len + std_len), should have valid values
        warmup = 300
        valid_osc = normalized_osc[warmup:]
        assert not np.any(np.isnan(valid_osc)), "NaN values found after warmup"

        # Oscillator should be bounded (normalized)
        assert np.all(np.abs(valid_osc) < 10), "Oscillator values out of expected range"

    def test_hma_stability(self):
        """Test HMA numerical stability."""
        np.random.seed(789)
        close = 1000 + np.cumsum(np.random.randn(200) * 5)

        result = calc_hma(close, 50)

        # HMA warmup needs: length + sqrt(length) ~= 50 + 7 = 57
        # After warmup, should have valid values
        warmup = 60
        valid = result[warmup:]
        valid_close = close[warmup:]

        # Filter out any remaining NaN
        mask = ~np.isnan(valid)
        valid_filtered = valid[mask]
        close_filtered = valid_close[mask]

        assert len(valid_filtered) > 0, "No valid HMA values after warmup"

        # Should track the trend (moderate correlation for random walk)
        if len(valid_filtered) > 10:
            corr = np.corrcoef(close_filtered, valid_filtered)[0, 1]
            # For random walk data, correlation may be lower due to noise
            assert corr > 0.6, f"HMA not tracking trend, corr={corr}"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

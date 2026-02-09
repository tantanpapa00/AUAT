# app/strategy_engine/indicators.py
"""
Technical Indicators for Mean Reversion Strategy.

1:1 match with PineScript: 역추세매매 현물 v0.4

All functions operate on numpy arrays for efficiency.
Index 0 = oldest, Index -1 = newest (most recent)
"""

from typing import Tuple, List, Optional
import math

import numpy as np


def smoother_f(src: np.ndarray, length: int) -> np.ndarray:
    """
    PineScript smoother_F - EMA variant.

    Formula (from PineScript):
        a = 2.0 / (length + 1)
        b = 1 - a
        out[i] = a * src[i] + b * out[i-1]

    This is equivalent to EMA.

    Args:
        src: Source price series (oldest first)
        length: Smoothing length

    Returns:
        Smoothed series (same length as src)
    """
    if len(src) == 0:
        return np.array([])

    a = 2.0 / (length + 1)
    b = 1 - a

    out = np.zeros(len(src))
    out[0] = src[0]

    for i in range(1, len(src)):
        out[i] = a * src[i] + b * out[i - 1]

    return out


def calc_ema(src: np.ndarray, length: int) -> np.ndarray:
    """
    Exponential Moving Average.

    Same as smoother_f but named for clarity.
    """
    return smoother_f(src, length)


def calc_sma(src: np.ndarray, length: int) -> np.ndarray:
    """
    Simple Moving Average using rolling window.

    Args:
        src: Source series
        length: Window length

    Returns:
        SMA series (first length-1 values are NaN)
    """
    if len(src) < length:
        return np.full(len(src), np.nan)

    out = np.full(len(src), np.nan)

    # Cumsum approach for efficiency
    cumsum = np.cumsum(np.insert(src, 0, 0))
    out[length - 1:] = (cumsum[length:] - cumsum[:-length]) / length

    return out


def calc_wma(src: np.ndarray, length: int) -> np.ndarray:
    """
    Weighted Moving Average.

    Formula: sum(src[i] * weight[i]) / sum(weights)
    where weights = [1, 2, 3, ..., length]

    Args:
        src: Source series
        length: Window length

    Returns:
        WMA series (first length-1 values are NaN)
    """
    if len(src) < length:
        return np.full(len(src), np.nan)

    weights = np.arange(1, length + 1, dtype=float)
    weight_sum = weights.sum()

    out = np.full(len(src), np.nan)

    for i in range(length - 1, len(src)):
        window = src[i - length + 1:i + 1]
        out[i] = np.sum(window * weights) / weight_sum

    return out


def calc_hma(close: np.ndarray, length: int) -> np.ndarray:
    """
    Hull Moving Average (HMA).

    Formula: WMA(2 * WMA(n/2) - WMA(n), sqrt(n))

    PineScript: ta.hma(close, length)

    Args:
        close: Close price series
        length: HMA length

    Returns:
        HMA series
    """
    if len(close) < length:
        return np.full(len(close), np.nan)

    half_len = max(1, length // 2)
    sqrt_len = max(1, int(math.sqrt(length)))

    wma_half = calc_wma(close, half_len)
    wma_full = calc_wma(close, length)

    # 2 * WMA(n/2) - WMA(n)
    raw = 2 * wma_half - wma_full

    # Final WMA with sqrt(n)
    hma = calc_wma(raw, sqrt_len)

    return hma


def calc_stdev(src: np.ndarray, length: int) -> np.ndarray:
    """
    Rolling Standard Deviation.

    PineScript: ta.stdev(src, length)

    Args:
        src: Source series
        length: Window length

    Returns:
        Standard deviation series
    """
    if len(src) < length:
        return np.full(len(src), np.nan)

    out = np.full(len(src), np.nan)

    for i in range(length - 1, len(src)):
        window = src[i - length + 1:i + 1]
        out[i] = np.std(window, ddof=0)  # Population std (PineScript default)

    return out


def calc_highest(src: np.ndarray, length: int) -> np.ndarray:
    """
    Rolling Highest.

    PineScript: ta.highest(src, length)
    """
    if len(src) < length:
        return np.full(len(src), np.nan)

    out = np.full(len(src), np.nan)

    for i in range(length - 1, len(src)):
        window = src[i - length + 1:i + 1]
        out[i] = np.max(window)

    return out


def calc_lowest(src: np.ndarray, length: int) -> np.ndarray:
    """
    Rolling Lowest.

    PineScript: ta.lowest(src, length)
    """
    if len(src) < length:
        return np.full(len(src), np.nan)

    out = np.full(len(src), np.nan)

    for i in range(length - 1, len(src)):
        window = src[i - length + 1:i + 1]
        out[i] = np.min(window)

    return out


def calc_vwma(close: np.ndarray, volume: np.ndarray, length: int) -> np.ndarray:
    """
    Volume Weighted Moving Average.

    PineScript: ta.vwma(close, length)

    Formula: sum(close * volume, length) / sum(volume, length)

    Args:
        close: Close price series
        volume: Volume series
        length: Window length

    Returns:
        VWMA series
    """
    if len(close) < length or len(volume) < length:
        return np.full(len(close), np.nan)

    out = np.full(len(close), np.nan)

    cv = close * volume  # close * volume

    for i in range(length - 1, len(close)):
        cv_sum = np.sum(cv[i - length + 1:i + 1])
        v_sum = np.sum(volume[i - length + 1:i + 1])

        if v_sum > 0:
            out[i] = cv_sum / v_sum
        else:
            out[i] = close[i]  # Fallback to close if no volume

    return out


def calc_atr(high: np.ndarray, low: np.ndarray, close: np.ndarray, length: int) -> np.ndarray:
    """
    Average True Range.

    PineScript: ta.atr(length)

    Formula: RMA of True Range
    True Range = max(high - low, abs(high - close[1]), abs(low - close[1]))
    """
    if len(high) < 2:
        return np.full(len(high), np.nan)

    # True Range
    tr = np.zeros(len(high))
    tr[0] = high[0] - low[0]

    for i in range(1, len(high)):
        hl = high[i] - low[i]
        hc = abs(high[i] - close[i - 1])
        lc = abs(low[i] - close[i - 1])
        tr[i] = max(hl, hc, lc)

    # RMA (same as EMA but with different alpha)
    # PineScript RMA: alpha = 1/length
    alpha = 1.0 / length
    out = np.zeros(len(tr))
    out[0] = tr[0]

    for i in range(1, len(tr)):
        out[i] = alpha * tr[i] + (1 - alpha) * out[i - 1]

    return out


def calc_supertrend(
    high: np.ndarray,
    low: np.ndarray,
    close: np.ndarray,
    atr_len: int,
    factor: float
) -> Tuple[np.ndarray, np.ndarray]:
    """
    Supertrend Indicator.

    PineScript: ta.supertrend(factor, atr_len)

    Returns:
        Tuple of (st_value, st_direction)
        st_direction: 1 = bullish (price above ST), -1 = bearish (price below ST)

    Note: PineScript's direction is inverted from intuition.
          We follow PineScript convention: dir=-1 means bullish (green).
          Use invert_st_dir=True in PineScript to match visual expectation.
    """
    n = len(close)
    if n < atr_len + 1:
        return np.full(n, np.nan), np.full(n, 0)

    atr = calc_atr(high, low, close, atr_len)

    # HL2 (median price)
    hl2 = (high + low) / 2

    # Basic bands
    basic_upper = hl2 + factor * atr
    basic_lower = hl2 - factor * atr

    # Final bands with trailing logic
    final_upper = np.zeros(n)
    final_lower = np.zeros(n)
    st_value = np.zeros(n)
    direction = np.zeros(n, dtype=int)

    # Initialize
    final_upper[0] = basic_upper[0]
    final_lower[0] = basic_lower[0]
    st_value[0] = basic_upper[0]
    direction[0] = 1  # Start bearish (PineScript convention)

    for i in range(1, n):
        # Final Upper Band: min of current basic_upper and previous final_upper if close[i-1] > final_upper[i-1]
        if close[i - 1] > final_upper[i - 1]:
            final_upper[i] = basic_upper[i]
        else:
            final_upper[i] = min(basic_upper[i], final_upper[i - 1])

        # Final Lower Band: max of current basic_lower and previous final_lower if close[i-1] < final_lower[i-1]
        if close[i - 1] < final_lower[i - 1]:
            final_lower[i] = basic_lower[i]
        else:
            final_lower[i] = max(basic_lower[i], final_lower[i - 1])

        # Determine direction and ST value
        prev_st = st_value[i - 1]
        prev_dir = direction[i - 1]

        if prev_dir == 1:  # Was bearish (below upper band)
            if close[i] > final_upper[i]:
                # Switch to bullish
                direction[i] = -1
                st_value[i] = final_lower[i]
            else:
                direction[i] = 1
                st_value[i] = final_upper[i]
        else:  # Was bullish (above lower band)
            if close[i] < final_lower[i]:
                # Switch to bearish
                direction[i] = 1
                st_value[i] = final_upper[i]
            else:
                direction[i] = -1
                st_value[i] = final_lower[i]

    return st_value, direction


def calc_ichimoku(
    high: np.ndarray,
    low: np.ndarray,
    tenkan_len: int,
    kijun_len: int,
    senkou_len: int
) -> Tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """
    Ichimoku Cloud indicators (without displacement).

    PineScript (simplified, current values only):
        tenkan = (highest(high, tenkan_len) + lowest(low, tenkan_len)) / 2
        kijun = (highest(high, kijun_len) + lowest(low, kijun_len)) / 2
        senkouA = (tenkan + kijun) / 2
        senkouB = (highest(high, senkou_len) + lowest(low, senkou_len)) / 2

    Returns:
        Tuple of (tenkan, kijun, senkou_a, senkou_b)
    """
    n = len(high)

    # Tenkan-sen (Conversion Line)
    tenkan_high = calc_highest(high, tenkan_len)
    tenkan_low = calc_lowest(low, tenkan_len)
    tenkan = (tenkan_high + tenkan_low) / 2

    # Kijun-sen (Base Line)
    kijun_high = calc_highest(high, kijun_len)
    kijun_low = calc_lowest(low, kijun_len)
    kijun = (kijun_high + kijun_low) / 2

    # Senkou Span A (Leading Span A)
    senkou_a = (tenkan + kijun) / 2

    # Senkou Span B (Leading Span B)
    senkou_high = calc_highest(high, senkou_len)
    senkou_low = calc_lowest(low, senkou_len)
    senkou_b = (senkou_high + senkou_low) / 2

    return tenkan, kijun, senkou_a, senkou_b


def calc_spo(
    close: np.ndarray,
    smooth_len: int = 20,
    threshold: float = 1.0,
    std_len: int = 50,
    hma_len: int = 30,
    bb_len: int = 250,
    bb_mult: float = 2.0
) -> Tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """
    Smooth Price Oscillator (SPO) - BigBeluga style.

    PineScript logic:
        line_long = smoother_F(close, smooth_len * 2)
        line_short = smoother_F(close, smooth_len)
        oscillator = line_short - line_long

        stdev_osc = ta.stdev(oscillator, std_len)
        denom = max(highest(stdev_osc, std_len), 1e-10)
        normalized_osc = ta.hma(oscillator / denom, hma_len)

        basis = ta.ema(normalized_osc, bb_len)
        deviation = bb_mult * ta.stdev(normalized_osc, bb_len)
        upper_band = basis + deviation
        lower_band = basis - deviation

    Args:
        close: Close price series
        smooth_len: Smoothing length (default 20)
        threshold: Signal threshold (default 1.0)
        std_len: Stdev length (default 50)
        hma_len: HMA length for normalization (default 30)
        bb_len: Bollinger Band length (default 250)
        bb_mult: Bollinger Band multiplier (default 2.0)

    Returns:
        Tuple of (normalized_osc, upper_band, lower_band, basis, line_short, line_long)
    """
    n = len(close)
    if n < max(smooth_len * 2, std_len, hma_len, bb_len):
        # Return NaN arrays if insufficient data
        nan_arr = np.full(n, np.nan)
        return nan_arr, nan_arr, nan_arr, nan_arr, nan_arr, nan_arr

    # Smoother lines
    line_long = smoother_f(close, smooth_len * 2)
    line_short = smoother_f(close, smooth_len)

    # Raw oscillator
    oscillator = line_short - line_long

    # Standard deviation of oscillator
    stdev_osc = calc_stdev(oscillator, std_len)

    # Highest stdev over std_len period
    highest_stdev = calc_highest(stdev_osc, std_len)

    # Denominator with minimum to avoid division by zero
    denom = np.maximum(highest_stdev, 1e-10)

    # Normalized oscillator before HMA
    osc_normalized_raw = oscillator / denom

    # Apply HMA to normalized oscillator
    normalized_osc = calc_hma(osc_normalized_raw, hma_len)

    # Bollinger Bands on normalized oscillator
    basis = calc_ema(normalized_osc, bb_len)
    stdev_norm = calc_stdev(normalized_osc, bb_len)
    deviation = bb_mult * stdev_norm

    upper_band = basis + deviation
    lower_band = basis - deviation

    return normalized_osc, upper_band, lower_band, basis, line_short, line_long


def crossover(series1: np.ndarray, series2: np.ndarray) -> np.ndarray:
    """
    Detect crossover: series1 crosses above series2.

    PineScript: ta.crossover(series1, series2)

    Returns:
        Boolean array where True indicates crossover occurred
    """
    n = len(series1)
    if n < 2:
        return np.full(n, False)

    result = np.full(n, False)

    for i in range(1, n):
        # Current: series1 > series2
        # Previous: series1 <= series2
        if not np.isnan(series1[i]) and not np.isnan(series2[i]):
            if not np.isnan(series1[i - 1]) and not np.isnan(series2[i - 1]):
                curr_above = series1[i] > series2[i]
                prev_not_above = series1[i - 1] <= series2[i - 1]
                result[i] = curr_above and prev_not_above

    return result


def crossunder(series1: np.ndarray, series2: np.ndarray) -> np.ndarray:
    """
    Detect crossunder: series1 crosses below series2.

    PineScript: ta.crossunder(series1, series2) or ta.crossover(series2, series1)

    Returns:
        Boolean array where True indicates crossunder occurred
    """
    return crossover(series2, series1)

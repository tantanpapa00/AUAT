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
    Ehlers' SuperSmoother Filter (PineScript smoother_F 동일).

    PineScript 원본:
        float step = 2.0 * math.pi / period
        float a1 = math.exp(-math.sqrt(2) * math.pi / period)
        float b1 = 2 * a1 * math.cos(math.sqrt(2) * step / period)
        float c2 = b1
        float c3 = -a1 * a1
        float c1 = 1 - c2 - c3
        smoothed := bar_index >= 4 ? c1 * (price + price[1]) / 2 + c2 * smoothed[1] + c3 * smoothed[2] : price

    2차 IIR 필터로 EMA보다 부드럽고 지연이 적음.

    Args:
        src: Source price series (oldest first)
        length: Smoothing period

    Returns:
        Smoothed series (same length as src)
    """
    n = len(src)
    if n == 0:
        return np.array([])

    # Ehlers' coefficients
    step = 2.0 * np.pi / length
    a1 = np.exp(-np.sqrt(2) * np.pi / length)
    b1 = 2 * a1 * np.cos(np.sqrt(2) * step / length)
    c2 = b1
    c3 = -a1 * a1
    c1 = 1 - c2 - c3

    out = np.full(n, np.nan)

    # 첫 4봉은 원본 값 사용 (PineScript: bar_index < 4)
    warmup = min(4, n)
    for i in range(warmup):
        if not np.isnan(src[i]):
            out[i] = src[i]

    # 5번째 봉부터 SuperSmoother 적용
    for i in range(warmup, n):
        if np.isnan(src[i]) or np.isnan(src[i - 1]):
            out[i] = out[i - 1] if not np.isnan(out[i - 1]) else src[i]
        elif np.isnan(out[i - 1]) or np.isnan(out[i - 2]):
            out[i] = src[i]
        else:
            # c1 * (price + price[1]) / 2 + c2 * smoothed[1] + c3 * smoothed[2]
            out[i] = c1 * (src[i] + src[i - 1]) / 2 + c2 * out[i - 1] + c3 * out[i - 2]

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
    Weighted Moving Average (벡터화 최적화).

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

    # 벡터화: np.convolve 사용
    # convolve는 weights를 뒤집어서 적용하므로 weights[::-1] 사용
    conv = np.convolve(src, weights[::-1], mode='valid')
    out = np.full(len(src), np.nan)
    out[length - 1:] = conv / weight_sum

    return out

    # ============================================================
    # 기존 for 루프 코드 (느림)
    # ============================================================
    # for i in range(length - 1, len(src)):
    #     window = src[i - length + 1:i + 1]
    #     out[i] = np.sum(window * weights) / weight_sum
    # return out


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
    Rolling Standard Deviation (벡터화 최적화).

    PineScript: ta.stdev(src, length)

    Args:
        src: Source series
        length: Window length

    Returns:
        Standard deviation series
    """
    if len(src) < length:
        return np.full(len(src), np.nan)

    # 벡터화: sliding_window_view 또는 cumsum 기반 계산
    # E[X^2] - E[X]^2 공식 사용
    n = len(src)
    out = np.full(n, np.nan)

    # Cumsum으로 rolling sum과 rolling sum of squares 계산
    cumsum = np.cumsum(np.insert(src, 0, 0))
    cumsum_sq = np.cumsum(np.insert(src ** 2, 0, 0))

    # Rolling mean and variance
    roll_sum = cumsum[length:] - cumsum[:-length]
    roll_sum_sq = cumsum_sq[length:] - cumsum_sq[:-length]

    roll_mean = roll_sum / length
    roll_var = roll_sum_sq / length - roll_mean ** 2

    # Handle numerical errors (variance should be >= 0)
    roll_var = np.maximum(roll_var, 0)
    out[length - 1:] = np.sqrt(roll_var)

    return out

    # ============================================================
    # 기존 for 루프 코드 (느림)
    # ============================================================
    # for i in range(length - 1, len(src)):
    #     window = src[i - length + 1:i + 1]
    #     out[i] = np.std(window, ddof=0)  # Population std (PineScript default)
    # return out


def calc_highest(src: np.ndarray, length: int) -> np.ndarray:
    """
    Rolling Highest (벡터화 최적화).

    PineScript: ta.highest(src, length)
    """
    if len(src) < length:
        return np.full(len(src), np.nan)

    n = len(src)
    out = np.full(n, np.nan)

    # numpy sliding_window_view 사용 (numpy 1.20+)
    try:
        from numpy.lib.stride_tricks import sliding_window_view
        windows = sliding_window_view(src, length)
        out[length - 1:] = np.max(windows, axis=1)
    except (ImportError, AttributeError):
        # Fallback: for 루프 (older numpy)
        for i in range(length - 1, n):
            out[i] = np.max(src[i - length + 1:i + 1])

    return out

    # ============================================================
    # 기존 for 루프 코드 (느림)
    # ============================================================
    # for i in range(length - 1, len(src)):
    #     window = src[i - length + 1:i + 1]
    #     out[i] = np.max(window)
    # return out


def calc_lowest(src: np.ndarray, length: int) -> np.ndarray:
    """
    Rolling Lowest (벡터화 최적화).

    PineScript: ta.lowest(src, length)
    """
    if len(src) < length:
        return np.full(len(src), np.nan)

    n = len(src)
    out = np.full(n, np.nan)

    # numpy sliding_window_view 사용 (numpy 1.20+)
    try:
        from numpy.lib.stride_tricks import sliding_window_view
        windows = sliding_window_view(src, length)
        out[length - 1:] = np.min(windows, axis=1)
    except (ImportError, AttributeError):
        # Fallback: for 루프 (older numpy)
        for i in range(length - 1, n):
            out[i] = np.min(src[i - length + 1:i + 1])

    return out

    # ============================================================
    # 기존 for 루프 코드 (느림)
    # ============================================================
    # for i in range(length - 1, len(src)):
    #     window = src[i - length + 1:i + 1]
    #     out[i] = np.min(window)
    # return out


def calc_vwma(close: np.ndarray, volume: np.ndarray, length: int) -> np.ndarray:
    """
    Volume Weighted Moving Average (벡터화 최적화).

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

    n = len(close)
    out = np.full(n, np.nan)

    cv = close * volume  # close * volume

    # 벡터화: cumsum으로 rolling sum 계산
    cumsum_cv = np.cumsum(np.insert(cv, 0, 0))
    cumsum_v = np.cumsum(np.insert(volume, 0, 0))

    roll_cv = cumsum_cv[length:] - cumsum_cv[:-length]
    roll_v = cumsum_v[length:] - cumsum_v[:-length]

    # Division with fallback for zero volume
    with np.errstate(divide='ignore', invalid='ignore'):
        result = roll_cv / roll_v
        # Replace inf/nan with close values (fallback)
        mask = ~np.isfinite(result)
        result[mask] = close[length - 1:][mask]

    out[length - 1:] = result

    return out

    # ============================================================
    # 기존 for 루프 코드 (느림)
    # ============================================================
    # for i in range(length - 1, len(close)):
    #     cv_sum = np.sum(cv[i - length + 1:i + 1])
    #     v_sum = np.sum(volume[i - length + 1:i + 1])
    #     if v_sum > 0:
    #         out[i] = cv_sum / v_sum
    #     else:
    #         out[i] = close[i]  # Fallback to close if no volume
    # return out


def calc_atr(high: np.ndarray, low: np.ndarray, close: np.ndarray, length: int) -> np.ndarray:
    """
    Average True Range (벡터화 최적화).

    PineScript: ta.atr(length)

    Formula: RMA of True Range
    True Range = max(high - low, abs(high - close[1]), abs(low - close[1]))
    """
    n = len(high)
    if n < 2:
        return np.full(n, np.nan)

    # 벡터화: True Range 계산
    hl = high - low
    prev_close = np.roll(close, 1)
    prev_close[0] = close[0]  # 첫 번째 값 처리

    hc = np.abs(high - prev_close)
    lc = np.abs(low - prev_close)

    tr = np.maximum(hl, np.maximum(hc, lc))
    tr[0] = high[0] - low[0]

    # RMA (Wilder's smoothing) - alpha = 1/length
    # RMA는 재귀적이므로 for 루프 유지 (numba 없이는 벡터화 어려움)
    alpha = 1.0 / length
    out = np.zeros(n)
    out[0] = tr[0]

    for i in range(1, n):
        out[i] = alpha * tr[i] + (1 - alpha) * out[i - 1]

    return out

    # ============================================================
    # 기존 코드 (True Range 계산 부분 for 루프 - 이제 벡터화됨)
    # ============================================================
    # for i in range(1, len(high)):
    #     hl = high[i] - low[i]
    #     hc = abs(high[i] - close[i - 1])
    #     lc = abs(low[i] - close[i - 1])
    #     tr[i] = max(hl, hc, lc)


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


# ============================================================
# Trend Strategy Indicators (Stock Trend Auto v7)
# ============================================================

def calc_rsi(close: np.ndarray, length: int) -> np.ndarray:
    """
    Relative Strength Index.

    PineScript: ta.rsi(close, length)

    Formula:
        RSI = 100 - 100 / (1 + RS)
        RS = avg_gain / avg_loss

    Args:
        close: Close price series
        length: RSI period

    Returns:
        RSI values (0-100)
    """
    n = len(close)
    if n < length + 1:
        return np.full(n, np.nan)

    # Calculate price changes
    delta = np.diff(close)
    delta = np.insert(delta, 0, 0)  # Prepend 0 for first element

    gains = np.where(delta > 0, delta, 0.0)
    losses = np.where(delta < 0, -delta, 0.0)

    # Use RMA (Wilder's smoothing) - alpha = 1/length
    alpha = 1.0 / length

    avg_gain = np.zeros(n)
    avg_loss = np.zeros(n)

    # Initial SMA for first 'length' periods
    if n > length:
        avg_gain[length] = np.mean(gains[1:length + 1])
        avg_loss[length] = np.mean(losses[1:length + 1])

        # RMA for subsequent periods
        for i in range(length + 1, n):
            avg_gain[i] = alpha * gains[i] + (1 - alpha) * avg_gain[i - 1]
            avg_loss[i] = alpha * losses[i] + (1 - alpha) * avg_loss[i - 1]

    # Calculate RSI
    rsi = np.full(n, np.nan)
    for i in range(length, n):
        if avg_loss[i] == 0:
            rsi[i] = 100.0
        else:
            rs = avg_gain[i] / avg_loss[i]
            rsi[i] = 100.0 - (100.0 / (1.0 + rs))

    return rsi


def calc_hvi(
    high: np.ndarray,
    low: np.ndarray,
    close: np.ndarray,
    volume: np.ndarray,
    length: int = 200,
    divisor: float = 3.6
) -> dict:
    """
    Historical Volatility Indicator (HVI) by LazyBear.

    PineScript logic from Stock Trend Auto v7:
        rng = high - low
        rngAvg = ta.sma(rng, length)
        volA = ta.sma(volume, length)

        high1 = high[1], low1 = low[1], mid1 = hl2[1]
        u1 = mid1 + (high1 - low1) / divisor
        d1 = mid1 - (high1 - low1) / divisor

        r_enabled = (rng > rngAvg and close < d1 and volume > volA) or (close < mid1)
        g_enabled = (close > mid1) or (rng > rngAvg and close > u1 and volume > volA)
                    or (high > high1 and rng < rngAvg/1.5 and volume < volA)
                    or (low < low1 and rng < rngAvg/1.5 and volume > volA)

    Args:
        high: High price series
        low: Low price series
        close: Close price series
        volume: Volume series
        length: HVI length (default 200)
        divisor: Range divisor (default 3.6)

    Returns:
        dict with:
            - 'g_enabled': np.ndarray(bool) - Green enabled (bullish)
            - 'r_enabled': np.ndarray(bool) - Red enabled (bearish)
            - 'gr_enabled': np.ndarray(bool) - Gray enabled (neutral)
    """
    n = len(close)
    if n < length + 1:
        return {
            'g_enabled': np.full(n, False),
            'r_enabled': np.full(n, False),
            'gr_enabled': np.full(n, False),
        }

    # Range and averages
    rng = high - low
    rng_avg = calc_sma(rng, length)
    vol_avg = calc_sma(volume, length)

    # Previous bar values (shifted by 1)
    high1 = np.roll(high, 1)
    low1 = np.roll(low, 1)
    mid1 = (high1 + low1) / 2
    high1[0] = np.nan
    low1[0] = np.nan
    mid1[0] = np.nan

    # Upper and lower thresholds
    range1 = high1 - low1
    u1 = mid1 + range1 / divisor
    d1 = mid1 - range1 / divisor

    # Red (bearish) conditions
    r_enabled1 = (rng > rng_avg) & (close < d1) & (volume > vol_avg)
    r_enabled2 = close < mid1
    r_enabled = r_enabled1 | r_enabled2

    # Green (bullish) conditions
    g_enabled1 = close > mid1
    g_enabled2 = (rng > rng_avg) & (close > u1) & (volume > vol_avg)
    g_enabled3 = (high > high1) & (rng < rng_avg / 1.5) & (volume < vol_avg)
    g_enabled4 = (low < low1) & (rng < rng_avg / 1.5) & (volume > vol_avg)
    g_enabled = g_enabled1 | g_enabled2 | g_enabled3 | g_enabled4

    # Gray (neutral) conditions
    gr_enabled1 = (rng > rng_avg) & (close > d1) & (close < u1) & (volume > vol_avg) & \
                  (volume < vol_avg * 1.5) & (volume > np.roll(volume, 1))
    gr_enabled2 = (rng < rng_avg / 1.5) & (volume < vol_avg / 1.5)
    gr_enabled3 = (close > d1) & (close < u1)
    gr_enabled = gr_enabled1 | gr_enabled2 | gr_enabled3

    # Handle NaN values
    g_enabled = np.where(np.isnan(rng_avg) | np.isnan(vol_avg), False, g_enabled)
    r_enabled = np.where(np.isnan(rng_avg) | np.isnan(vol_avg), False, r_enabled)
    gr_enabled = np.where(np.isnan(rng_avg) | np.isnan(vol_avg), False, gr_enabled)

    return {
        'g_enabled': g_enabled.astype(bool),
        'r_enabled': r_enabled.astype(bool),
        'gr_enabled': gr_enabled.astype(bool),
    }


def calc_qqe_mod(
    close: np.ndarray,
    rsi_length: int = 6,
    rsi_smoothing: int = 5,
    qqe_factor: float = 3.0
) -> dict:
    """
    QQE MOD (Quantitative Qualitative Estimation) indicator.

    PineScript logic from Stock Trend Auto v7:
        calculateQQE(rsiLength, smoothingFactor, qqeFactor, source) =>
            wildersLength = rsiLength * 2 - 1
            rsi = ta.rsi(source, rsiLength)
            smoothedRsi = ta.ema(rsi, smoothingFactor)
            atrRsi = math.abs(smoothedRsi[1] - smoothedRsi)
            smoothedAtrRsi = ta.ema(atrRsi, wildersLength)
            dynamicAtrRsi = smoothedAtrRsi * qqeFactor

            longBand/shortBand trailing logic...
            trendDirection based on crossovers...

        qqePos = primaryRSI > 50

    Args:
        close: Close price series
        rsi_length: RSI period (default 6)
        rsi_smoothing: RSI EMA smoothing (default 5)
        qqe_factor: QQE factor (default 3.0)

    Returns:
        dict with:
            - 'primary_rsi': np.ndarray - Smoothed RSI values
            - 'qqe_line': np.ndarray - QQE trend line
            - 'is_positive': np.ndarray(bool) - primaryRSI > 50
            - 'trend_dir': np.ndarray - Trend direction (1=up, -1=down)
    """
    n = len(close)
    wilders_length = rsi_length * 2 - 1

    if n < max(rsi_length, rsi_smoothing, wilders_length) + 10:
        return {
            'primary_rsi': np.full(n, np.nan),
            'qqe_line': np.full(n, np.nan),
            'is_positive': np.full(n, False),
            'trend_dir': np.zeros(n, dtype=int),
        }

    # Step 1: Calculate RSI
    rsi = calc_rsi(close, rsi_length)

    # Step 2: Smooth RSI with EMA
    smoothed_rsi = calc_ema(rsi, rsi_smoothing)

    # Step 3: ATR of RSI (absolute difference)
    atr_rsi = np.zeros(n)
    for i in range(1, n):
        if not np.isnan(smoothed_rsi[i]) and not np.isnan(smoothed_rsi[i - 1]):
            atr_rsi[i] = abs(smoothed_rsi[i] - smoothed_rsi[i - 1])

    # Step 4: Smooth ATR RSI
    smoothed_atr_rsi = calc_ema(atr_rsi, wilders_length)

    # Step 5: Dynamic ATR RSI
    dynamic_atr_rsi = smoothed_atr_rsi * qqe_factor

    # Step 6: Calculate bands with trailing logic
    long_band = np.zeros(n)
    short_band = np.zeros(n)
    trend_dir = np.zeros(n, dtype=int)
    qqe_line = np.zeros(n)

    for i in range(1, n):
        if np.isnan(smoothed_rsi[i]) or np.isnan(dynamic_atr_rsi[i]):
            long_band[i] = long_band[i - 1]
            short_band[i] = short_band[i - 1]
            trend_dir[i] = trend_dir[i - 1]
            qqe_line[i] = qqe_line[i - 1]
            continue

        new_long_band = smoothed_rsi[i] - dynamic_atr_rsi[i]
        new_short_band = smoothed_rsi[i] + dynamic_atr_rsi[i]

        # Long band: trailing up
        if smoothed_rsi[i - 1] > long_band[i - 1] and smoothed_rsi[i] > long_band[i - 1]:
            long_band[i] = max(long_band[i - 1], new_long_band)
        else:
            long_band[i] = new_long_band

        # Short band: trailing down
        if smoothed_rsi[i - 1] < short_band[i - 1] and smoothed_rsi[i] < short_band[i - 1]:
            short_band[i] = min(short_band[i - 1], new_short_band)
        else:
            short_band[i] = new_short_band

        # Trend direction based on crossovers
        # Cross above short band -> trend up
        if smoothed_rsi[i] > short_band[i - 1] and smoothed_rsi[i - 1] <= short_band[i - 1]:
            trend_dir[i] = 1
        # Cross below long band -> trend down
        elif smoothed_rsi[i] < long_band[i - 1] and smoothed_rsi[i - 1] >= long_band[i - 1]:
            trend_dir[i] = -1
        else:
            trend_dir[i] = trend_dir[i - 1]

        # QQE line follows the appropriate band
        qqe_line[i] = long_band[i] if trend_dir[i] == 1 else short_band[i]

    # Is positive: primaryRSI > 50
    is_positive = smoothed_rsi > 50

    return {
        'primary_rsi': smoothed_rsi,
        'qqe_line': qqe_line,
        'is_positive': np.where(np.isnan(smoothed_rsi), False, is_positive).astype(bool),
        'trend_dir': trend_dir,
    }


def calc_vwma_simple(close: np.ndarray, volume: np.ndarray, length: int) -> np.ndarray:
    """
    Simple VWMA for HTF data without numpy volume check.

    Same as calc_vwma but with simpler handling.
    Used for HTF VWMA(156) calculation.
    """
    return calc_vwma(close, volume, length)

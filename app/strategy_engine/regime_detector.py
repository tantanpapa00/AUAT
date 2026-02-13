# app/strategy_engine/regime_detector.py
"""
4-Regime Detection for Mean Reversion Strategy.

Based on PineScript: 역추세매매 현물 v0.4

Regime definition (HTF-based):
- R1: 정배열 + ST상승 (bull_stack AND st_up)
- R2: 정배열 + ST하락 (bull_stack AND st_down)
- R3: 역배열 + ST상승 (bear_stack AND st_up)
- R4: 역배열 + ST하락 (bear_stack AND st_down)

Where:
- bull_stack (정배열): VWMA50 >= VWMA200
- bear_stack (역배열): VWMA50 < VWMA200
- st_up: Supertrend direction > 0 (bullish)
- st_down: Supertrend direction < 0 (bearish)
"""

from typing import Optional
import numpy as np

from .models import HTFIndicators
from .indicators import (
    calc_vwma,
    calc_hma,
    calc_ichimoku,
    calc_supertrend,
)
from .presets import HTF_DEFAULTS


def detect_regime(
    htf_indicators: HTFIndicators,
    use_4regime: bool = True
) -> int:
    """
    Detect current market regime based on HTF indicators.

    Args:
        htf_indicators: HTFIndicators dataclass with calculated values
        use_4regime: If False, returns 0 (no regime mode)

    Returns:
        Regime number: 0 (disabled), 1, 2, 3, or 4
    """
    if not use_4regime:
        return 0

    bull_stack = htf_indicators.bull_stack
    bear_stack = htf_indicators.bear_stack
    st_up = htf_indicators.st_direction > 0
    st_down = htf_indicators.st_direction < 0

    if bull_stack and st_up:
        return 1  # R1: 정배열 + ST상승
    elif bull_stack and st_down:
        return 2  # R2: 정배열 + ST하락
    elif bear_stack and st_up:
        return 3  # R3: 역배열 + ST상승
    elif bear_stack and st_down:
        return 4  # R4: 역배열 + ST하락
    else:
        return 0  # Undefined state


def calc_htf_indicators(
    high: np.ndarray,
    low: np.ndarray,
    close: np.ndarray,
    volume: np.ndarray,
    vwma50_len: int = 50,
    vwma200_len: int = 200,
    hull_len: int = 100,
    ichi_tenkan: int = 9,
    ichi_kijun: int = 26,
    ichi_senkou: int = 52,
    st_atr_len: int = 20,
    st_factor: float = 5.0,
    invert_st_dir: bool = True
) -> HTFIndicators:
    """
    Calculate all HTF indicators for regime detection.

    Args:
        high, low, close, volume: OHLCV data arrays (oldest first)
        vwma50_len: VWMA 50 period length
        vwma200_len: VWMA 200 period length
        hull_len: Hull MA length
        ichi_tenkan: Ichimoku Tenkan period
        ichi_kijun: Ichimoku Kijun period
        ichi_senkou: Ichimoku Senkou period
        st_atr_len: Supertrend ATR length
        st_factor: Supertrend factor
        invert_st_dir: Invert Supertrend direction (PineScript default: True)

    Returns:
        HTFIndicators dataclass with all calculated values
    """
    n = len(close)
    if n < 2:
        # Return default indicators for insufficient data
        return HTFIndicators(
            vwma50=close[-1] if n > 0 else 0.0,
            vwma200=close[-1] if n > 0 else 0.0,
            hull=close[-1] if n > 0 else 0.0,
            hull_up=False,
            hull_dn=False,
            tenkan=close[-1] if n > 0 else 0.0,
            kijun=close[-1] if n > 0 else 0.0,
            senkou_a=close[-1] if n > 0 else 0.0,
            senkou_b=close[-1] if n > 0 else 0.0,
            cloud_upper=close[-1] if n > 0 else 0.0,
            cloud_lower=close[-1] if n > 0 else 0.0,
            cloud_bull=False,
            cloud_bear=False,
            st_value=close[-1] if n > 0 else 0.0,
            st_direction=0,
            bull_stack=False,
            bear_stack=False,
        )

    # VWMA
    vwma50 = calc_vwma(close, volume, vwma50_len)
    vwma200 = calc_vwma(close, volume, vwma200_len)

    # Hull MA
    hull = calc_hma(close, hull_len)

    # Ichimoku
    ichimoku_result = calc_ichimoku(
        high, low, close, ichi_tenkan, ichi_kijun, ichi_senkou
    )
    tenkan = ichimoku_result["tenkan"]
    kijun = ichimoku_result["kijun"]
    senkou_a = ichimoku_result["senkou_a"]
    senkou_b = ichimoku_result["senkou_b"]

    # Supertrend
    st_value, st_direction = calc_supertrend(
        high, low, close, st_atr_len, st_factor
    )

    # Get latest values (most recent bar)
    idx = -1  # Last index

    # Handle NaN values
    def safe_get(arr: np.ndarray, i: int = -1) -> float:
        val = arr[i]
        return 0.0 if np.isnan(val) else float(val)

    v50 = safe_get(vwma50)
    v200 = safe_get(vwma200)
    h = safe_get(hull)
    h_prev = safe_get(hull, -2) if n > 1 else h
    t = safe_get(tenkan)
    k = safe_get(kijun)
    sa = safe_get(senkou_a)
    sb = safe_get(senkou_b)
    st_v = safe_get(st_value)
    st_d = int(st_direction[idx]) if not np.isnan(st_direction[idx]) else 0

    # Apply direction inversion if needed (PineScript default behavior)
    if invert_st_dir:
        st_d = -st_d

    # Derived values
    cloud_upper = max(sa, sb)
    cloud_lower = min(sa, sb)
    cloud_bull = sa > sb
    cloud_bear = sa < sb
    bull_stack = v50 >= v200
    bear_stack = v50 < v200
    hull_up = h > h_prev
    hull_dn = h < h_prev

    return HTFIndicators(
        vwma50=v50,
        vwma200=v200,
        hull=h,
        hull_up=hull_up,
        hull_dn=hull_dn,
        tenkan=t,
        kijun=k,
        senkou_a=sa,
        senkou_b=sb,
        cloud_upper=cloud_upper,
        cloud_lower=cloud_lower,
        cloud_bull=cloud_bull,
        cloud_bear=cloud_bear,
        st_value=st_v,
        st_direction=st_d,
        bull_stack=bull_stack,
        bear_stack=bear_stack,
    )


def calc_htf_indicators_from_defaults(
    high: np.ndarray,
    low: np.ndarray,
    close: np.ndarray,
    volume: np.ndarray,
    invert_st_dir: bool = True
) -> HTFIndicators:
    """
    Calculate HTF indicators using default parameters.

    Args:
        high, low, close, volume: OHLCV data arrays
        invert_st_dir: Invert Supertrend direction

    Returns:
        HTFIndicators dataclass
    """
    return calc_htf_indicators(
        high=high,
        low=low,
        close=close,
        volume=volume,
        vwma50_len=HTF_DEFAULTS["vwma50_len"],
        vwma200_len=HTF_DEFAULTS["vwma200_len"],
        hull_len=HTF_DEFAULTS["hull_len"],
        ichi_tenkan=HTF_DEFAULTS["ichi_tenkan"],
        ichi_kijun=HTF_DEFAULTS["ichi_kijun"],
        ichi_senkou=HTF_DEFAULTS["ichi_senkou"],
        st_atr_len=HTF_DEFAULTS["st_atr_len"],
        st_factor=HTF_DEFAULTS["st_factor"],
        invert_st_dir=invert_st_dir,
    )


def get_regime_name(regime: int) -> str:
    """Get human-readable regime name."""
    names = {
        0: "No Regime",
        1: "R1 (정배열+ST상승)",
        2: "R2 (정배열+ST하락)",
        3: "R3 (역배열+ST상승)",
        4: "R4 (역배열+ST하락)",
    }
    return names.get(regime, f"Unknown ({regime})")


def get_regime_policy(regime: int, config: dict) -> dict:
    """
    Get regime-specific policy from config.

    Args:
        regime: Regime number (1-4)
        config: MRConfig as dict

    Returns:
        Dict with regime-specific parameters
    """
    prefix = f"r{regime}_"

    return {
        "buy_mult": config.get(f"{prefix}buy_mult", 1.0),
        "sell_mult": config.get(f"{prefix}sell_mult", 1.0),
        "allow_osc_buy": config.get(f"{prefix}allow_osc_buy", True),
        "buy1_only": config.get(f"{prefix}buy1_only", False),
        "sell1_only": config.get(f"{prefix}sell1_only", False),
        "sell_mode": config.get(f"{prefix}sell_mode", "Normal"),
        "filt_below_avg": config.get(f"{prefix}filt_below_avg", False),
        "filt_prev_signal": config.get(f"{prefix}filt_prev_signal", False),
        "filt_prev_exec": config.get(f"{prefix}filt_prev_exec", False),
        # Special triggers
        "pullback_on": config.get(f"{prefix}pullback_on", False) if regime == 1 else False,
        "pullback_buy_mult": config.get(f"{prefix}pullback_buy_mult", 1.0) if regime == 1 else 0.0,
        "breakout_on": config.get(f"{prefix}breakout_on", False) if regime == 3 else False,
        "breakout_buy_mult": config.get(f"{prefix}breakout_buy_mult", 1.0) if regime == 3 else 0.0,
    }

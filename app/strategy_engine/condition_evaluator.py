# app/strategy_engine/condition_evaluator.py
"""
Condition Evaluator for Custom Strategy.

Evaluates trading conditions at each bar based on indicator values.
"""

import numpy as np
from typing import Optional

from app.strategy_engine.indicators import (
    calc_sma, calc_ema, calc_wma, calc_hma, calc_vwma,
    calc_bollinger_bands, calc_rsi, calc_macd, calc_stochastic,
    calc_cci, calc_adx, calc_supertrend, calc_atr, crossover, crossunder
)
from app.strategy_engine.custom_strategy import ConditionItem, CustomRule


def compute_indicator(
    candle_dict: dict,
    indicator: str,
    output: str,
    params: dict
) -> np.ndarray:
    """
    Compute indicator and return the specified output.

    Args:
        candle_dict: Dict with 'open', 'high', 'low', 'close', 'volume' numpy arrays
        indicator: Indicator name (e.g., "RSI", "MACD")
        output: Output name (e.g., "value", "macd", "signal")
        params: Indicator parameters

    Returns:
        numpy array of indicator values
    """
    closes = candle_dict["close"]
    highs = candle_dict["high"]
    lows = candle_dict["low"]
    opens = candle_dict["open"]
    volumes = candle_dict.get("volume", np.zeros_like(closes))

    # === Price ===
    if indicator == "PRICE":
        return candle_dict.get(output, closes)

    # === Moving Averages ===
    if indicator == "SMA":
        period = params.get("period", 20)
        return calc_sma(closes, period)

    if indicator == "EMA":
        period = params.get("period", 20)
        return calc_ema(closes, period)

    if indicator == "WMA":
        period = params.get("period", 20)
        return calc_wma(closes, period)

    if indicator == "HMA":
        period = params.get("period", 20)
        return calc_hma(closes, period)

    if indicator == "VWMA":
        period = params.get("period", 20)
        return calc_vwma(closes, volumes, period)

    if indicator == "BB":
        period = params.get("period", 20)
        std_mult = params.get("std_mult", 2.0)
        result = calc_bollinger_bands(closes, period, std_mult)
        return result.get(output, result["middle"])

    # === Oscillators ===
    if indicator == "RSI":
        period = params.get("period", 14)
        return calc_rsi(closes, period)

    if indicator == "MACD":
        fast = params.get("fast_length", 12)
        slow = params.get("slow_length", 26)
        signal = params.get("signal_length", 9)
        result = calc_macd(closes, fast, slow, signal)
        return result.get(output, result["macd"])

    if indicator == "STOCH":
        k_period = params.get("k_period", 14)
        d_period = params.get("d_period", 3)
        slowing = params.get("slowing", 3)
        result = calc_stochastic(highs, lows, closes, k_period, d_period, slowing)
        return result.get(output, result["k"])

    if indicator == "CCI":
        period = params.get("period", 20)
        return calc_cci(highs, lows, closes, period)

    # === Trend ===
    if indicator == "ADX":
        period = params.get("period", 14)
        result = calc_adx(highs, lows, closes, period)
        return result.get(output, result["adx"])

    if indicator == "SUPERTREND":
        atr_len = params.get("atr_len", 20)
        factor = params.get("factor", 5.0)
        st_value, st_direction = calc_supertrend(highs, lows, closes, atr_len, factor)
        if output == "direction":
            return st_direction.astype(float)
        return st_value

    # === Volatility ===
    if indicator == "ATR":
        period = params.get("period", 14)
        return calc_atr(highs, lows, closes, period)

    # Unknown indicator
    raise ValueError(f"Unknown indicator: {indicator}")


def evaluate_condition(
    candle_dict: dict,
    cond: ConditionItem,
    bar_idx: int,
    indicator_cache: Optional[dict] = None
) -> bool:
    """
    Evaluate a single condition at a specific bar.

    Args:
        candle_dict: Candle data arrays
        cond: Condition to evaluate
        bar_idx: Current bar index
        indicator_cache: Optional cache for computed indicators

    Returns:
        True if condition is met, False otherwise
    """
    if indicator_cache is None:
        indicator_cache = {}

    # Compute left side indicator
    left_key = f"{cond.indicator}_{cond.output}_{str(cond.params)}"
    if left_key not in indicator_cache:
        indicator_cache[left_key] = compute_indicator(
            candle_dict, cond.indicator, cond.output, cond.params
        )
    left = indicator_cache[left_key]

    # Get left value at current bar
    if bar_idx < 0 or bar_idx >= len(left):
        return False
    left_val = left[bar_idx]
    if np.isnan(left_val):
        return False

    # Compute right side
    if cond.compare_type == "value":
        if cond.compare_value is None:
            return False
        right_val = float(cond.compare_value)
        right = None  # Not an array
    else:
        # Compare to another indicator
        if not cond.compare_indicator:
            return False
        right_key = f"{cond.compare_indicator}_{cond.compare_output}_{str(cond.compare_params or {})}"
        if right_key not in indicator_cache:
            indicator_cache[right_key] = compute_indicator(
                candle_dict,
                cond.compare_indicator,
                cond.compare_output or "value",
                cond.compare_params or {}
            )
        right = indicator_cache[right_key]
        right_val = right[bar_idx] if bar_idx < len(right) else None
        if right_val is None or np.isnan(right_val):
            return False

    # Evaluate operator
    if cond.operator == ">":
        return left_val > right_val
    elif cond.operator == "<":
        return left_val < right_val
    elif cond.operator == ">=":
        return left_val >= right_val
    elif cond.operator == "<=":
        return left_val <= right_val
    elif cond.operator == "==":
        return abs(left_val - right_val) < 1e-10

    # Crossover / Crossunder
    elif cond.operator == "cross_above":
        if bar_idx < 1:
            return False
        prev_left = left[bar_idx - 1]
        if np.isnan(prev_left):
            return False

        if cond.compare_type == "value":
            prev_right = right_val
            curr_right = right_val
        else:
            prev_right = right[bar_idx - 1] if bar_idx - 1 < len(right) else None
            curr_right = right_val
            if prev_right is None or np.isnan(prev_right):
                return False

        # Cross above: was below or equal, now above
        return prev_left <= prev_right and left_val > curr_right

    elif cond.operator == "cross_below":
        if bar_idx < 1:
            return False
        prev_left = left[bar_idx - 1]
        if np.isnan(prev_left):
            return False

        if cond.compare_type == "value":
            prev_right = right_val
            curr_right = right_val
        else:
            prev_right = right[bar_idx - 1] if bar_idx - 1 < len(right) else None
            curr_right = right_val
            if prev_right is None or np.isnan(prev_right):
                return False

        # Cross below: was above or equal, now below
        return prev_left >= prev_right and left_val < curr_right

    return False


def evaluate_rule(
    candle_dict: dict,
    rule: CustomRule,
    bar_idx: int,
    indicator_cache: Optional[dict] = None
) -> bool:
    """
    Evaluate a complete rule (entry or exit).

    Rule structure: groups are joined by OR.
    Within each group, conditions use the group's logic (AND/OR).

    Args:
        candle_dict: Candle data arrays
        rule: Rule with condition groups
        bar_idx: Current bar index
        indicator_cache: Optional cache for computed indicators

    Returns:
        True if any group's conditions are met
    """
    if indicator_cache is None:
        indicator_cache = {}

    for group in rule.groups:
        if not group.conditions:
            continue

        if group.logic == "AND":
            # All conditions must be true
            all_true = all(
                evaluate_condition(candle_dict, c, bar_idx, indicator_cache)
                for c in group.conditions
            )
            if all_true:
                return True

        else:  # OR
            # Any condition must be true
            any_true = any(
                evaluate_condition(candle_dict, c, bar_idx, indicator_cache)
                for c in group.conditions
            )
            if any_true:
                return True

    return False

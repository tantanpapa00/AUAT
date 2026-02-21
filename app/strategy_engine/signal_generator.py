# app/strategy_engine/signal_generator.py
"""
Signal Generator for Mean Reversion Strategy.

Based on PineScript: 역추세매매 현물 v0.4

Generates buy/sell signals based on:
1. SPO oscillator signals (sig_up_raw, sig_dn_raw)
2. Regime-specific filters
3. R1 pullback trigger (눌림)
4. R3 breakout trigger (돌파)
5. Position filters (below avg, prev signal, prev exec)
6. Profit gate for sells
"""

from typing import Optional, Tuple
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
import time

import numpy as np

from .models import (
    SignalResult,
    OscillatorData,
    HTFIndicators,
    StrategyState,
    MRConfig,
)
from .indicators import calc_spo, crossover
from .presets import OSC_PRESETS


def calc_osc_data(
    close: np.ndarray,
    preset: str = "preset1"
) -> OscillatorData:
    """
    Calculate SPO oscillator data.

    Args:
        close: Close price series (oldest first)
        preset: Preset name ("preset1" or "preset2")

    Returns:
        OscillatorData with normalized_osc, bands, and raw signals
    """
    params = OSC_PRESETS.get(preset, OSC_PRESETS["preset1"])

    normalized_osc, upper_band, lower_band, basis, line_short, line_long = calc_spo(
        close,
        smooth_len=params["smooth_len"],
        threshold=params["threshold"],
        std_len=params["std_len"],
        hma_len=params["hma_len"],
        bb_len=params["bb_len"],
        bb_mult=params["bb_mult"],
    )

    threshold = params["threshold"]

    # Get latest values
    n = len(close)
    if n < 2:
        return OscillatorData(
            normalized_osc=0.0,
            upper_band=threshold,
            lower_band=-threshold,
            basis=0.0,
            threshold=threshold,
            line_short=close[-1] if n > 0 else 0.0,
            line_long=close[-1] if n > 0 else 0.0,
            oscillator_raw=0.0,
            sig_up_raw=False,
            sig_dn_raw=False,
        )

    # Safe get last values
    def safe_last(arr: np.ndarray, offset: int = 0) -> float:
        idx = -1 - offset
        if abs(idx) > len(arr):
            return np.nan
        val = arr[idx]
        return 0.0 if np.isnan(val) else float(val)

    osc_curr = safe_last(normalized_osc)
    osc_prev = safe_last(normalized_osc, 1)
    ub = safe_last(upper_band)
    lb = safe_last(lower_band)
    bs = safe_last(basis)
    ls = safe_last(line_short)
    ll = safe_last(line_long)
    osc_raw = ls - ll

    # Signal detection (from PineScript)
    # sig_up_raw = normalized_osc < -threshold AND crossover(normalized_osc, normalized_osc[1])
    # sig_dn_raw = normalized_osc > threshold AND crossover(normalized_osc[1], normalized_osc)

    # Crossover: current > prev AND prev_prev <= prev
    # For sig_up: osc crosses above (osc_curr > osc_prev AND osc_prev <= osc_prev_prev)
    osc_prev_prev = safe_last(normalized_osc, 2) if n > 2 else osc_prev

    # sig_up: osc was falling and now rising, while below -threshold
    sig_up_raw = (
        osc_curr < -threshold and
        osc_curr > osc_prev and
        osc_prev <= osc_prev_prev
    )

    # sig_dn: osc was rising and now falling, while above threshold
    sig_dn_raw = (
        osc_curr > threshold and
        osc_curr < osc_prev and
        osc_prev >= osc_prev_prev
    )

    return OscillatorData(
        normalized_osc=osc_curr,
        upper_band=ub,
        lower_band=lb,
        basis=bs,
        threshold=threshold,
        line_short=ls,
        line_long=ll,
        oscillator_raw=osc_raw,
        sig_up_raw=sig_up_raw,
        sig_dn_raw=sig_dn_raw,
    )


def check_buy_filters(
    close_price: float,
    osc_data: OscillatorData,
    state: StrategyState,
    config: MRConfig,
    regime: int,
    has_position: bool,
    avg_price: Optional[float],
) -> Tuple[bool, str]:
    """
    Check buy filters based on regime configuration.

    Returns:
        Tuple of (passed, fail_reason)
    """
    # Get regime-specific config
    prefix = f"r{regime}_" if regime > 0 else "r1_"

    # Below average price filter
    filt_below_avg = getattr(config, f"{prefix}filt_below_avg", False)
    if has_position and filt_below_avg and avg_price is not None:
        if close_price > avg_price:
            return False, "평단가 이하X"

    # Previous signal price filter
    filt_prev_signal = getattr(config, f"{prefix}filt_prev_signal", False)
    if has_position and filt_prev_signal and state.last_buy_signal_price is not None:
        if close_price >= state.last_buy_signal_price:
            return False, "직전신호가 하락X"

    # Previous execution price filter
    filt_prev_exec = getattr(config, f"{prefix}filt_prev_exec", False)
    if has_position and filt_prev_exec and state.last_buy_exec_price is not None:
        if close_price >= state.last_buy_exec_price:
            return False, "직전체결가 하락X"

    # Additional buy gap filter
    if has_position and config.use_add_buy_gap and state.last_buy_exec_price is not None:
        gap_threshold = state.last_buy_exec_price * (1 - config.add_buy_gap_pct / 100.0)
        if close_price > gap_threshold:
            return False, "직전체결가 갭X"

    return True, ""


def check_sell_profit_gate(
    close_price: float,
    avg_price: float,
    min_profit_pct: float,
    fee_buffer_pct: float
) -> bool:
    """
    Check minimum profit gate for sell.

    PineScript:
        need_pct = min_profit_pct + fee_roundtrip_buf
        sell_ok_price = close >= avg_price * (1 + need_pct / 100.0)
    """
    need_pct = min_profit_pct + fee_buffer_pct
    required_price = avg_price * (1 + need_pct / 100.0)
    return close_price >= required_price


def get_buy_tranche_pct(
    stage: int,
    config: MRConfig,
    regime: int,
    trigger_type: str = "osc"
) -> float:
    """
    Get buy tranche percentage for current stage.

    Args:
        stage: Current buy stage (0-indexed)
        config: Strategy configuration
        regime: Current regime
        trigger_type: "osc", "pullback", or "breakout"

    Returns:
        Tranche percentage (0-100)
    """
    prefix = f"r{regime}_" if regime > 0 else "r1_"

    # Get base tranche percentage
    if stage < len(config.buy_tranches):
        base_pct = config.buy_tranches[stage]
    else:
        base_pct = config.buy_tranches[-1]  # Use last value

    # Get regime multiplier
    buy_mult = getattr(config, f"{prefix}buy_mult", 1.0)

    # Special triggers
    if trigger_type == "pullback" and regime == 1:
        pullback_mult = getattr(config, "r1_pullback_buy_mult", 1.0)
        # Pullback uses BUY1 * pullback_mult * regime_mult
        return config.buy_tranches[0] * pullback_mult * buy_mult
    elif trigger_type == "breakout" and regime == 3:
        breakout_mult = getattr(config, "r3_breakout_buy_mult", 1.0)
        # Breakout uses BUY1 * breakout_mult * regime_mult
        return config.buy_tranches[0] * breakout_mult * buy_mult

    return base_pct * buy_mult


def get_sell_tranche_pct(
    stage: int,
    config: MRConfig,
    regime: int
) -> float:
    """
    Get sell tranche percentage for current stage.

    Args:
        stage: Current sell stage (0-indexed)
        config: Strategy configuration
        regime: Current regime

    Returns:
        Tranche percentage (0-100)
    """
    prefix = f"r{regime}_" if regime > 0 else "r1_"

    # Get base tranche percentage
    if stage < len(config.sell_tranches):
        base_pct = config.sell_tranches[stage]
    else:
        base_pct = config.sell_tranches[-1]

    # Get regime multiplier
    sell_mult = getattr(config, f"{prefix}sell_mult", 1.0)

    return min(base_pct * sell_mult, 100.0)


def generate_mr_signal(
    close: np.ndarray,
    high: np.ndarray,
    low: np.ndarray,
    osc_data: OscillatorData,
    htf_indicators: HTFIndicators,
    regime: int,
    state: StrategyState,
    config: MRConfig,
    has_position: bool,
    position_qty: float,
    avg_price: Optional[float],
    current_ts: int,
) -> Tuple[SignalResult, StrategyState]:
    """
    Generate Mean Reversion buy/sell signal.

    This is the main signal generation function that:
    1. Checks OSC signals (sig_up_raw, sig_dn_raw)
    2. Applies regime-specific filters
    3. Handles R1 pullback and R3 breakout triggers
    4. Returns SignalResult with action and reason

    Args:
        close: Close price series (for reference)
        high: High price series (for breakout detection)
        low: Low price series
        osc_data: Calculated oscillator data
        htf_indicators: HTF indicators for regime
        regime: Current regime (1-4)
        state: Current strategy state
        config: Strategy configuration
        has_position: Whether there's an open position
        position_qty: Current position quantity
        avg_price: Average position price
        current_ts: Current timestamp (ms)

    Returns:
        Tuple of (SignalResult, updated StrategyState)
    """
    # Clone state for modification
    new_state = StrategyState(
        buy_stage=state.buy_stage,
        sell_stage=state.sell_stage,
        last_buy_exec_price=state.last_buy_exec_price,
        last_buy_signal_price=state.last_buy_signal_price,
        last_buy_time=state.last_buy_time,
        last_sell_time=state.last_sell_time,
        r1_pb_armed=state.r1_pb_armed,
        r1_pb_used=state.r1_pb_used,
        r3_break_used=state.r3_break_used,
        alt_sell_toggle=state.alt_sell_toggle,
        current_regime=regime,
        last_bar_time=state.last_bar_time,
        prev_hull_dn=state.prev_hull_dn,
        prev_senkou_b=state.prev_senkou_b,
    )

    close_price = float(close[-1])
    high_price = float(high[-1]) if len(high) > 0 else close_price
    low_price = float(low[-1]) if len(low) > 0 else close_price

    # 현재 HTF 상태를 new_state에 저장 (다음 봉의 [1] 참조용)
    new_state.prev_hull_dn = htf_indicators.hull_dn
    new_state.prev_senkou_b = htf_indicators.senkou_b

    # Get regime-specific config
    prefix = f"r{regime}_" if regime > 0 else "r1_"
    allow_osc_buy = getattr(config, f"{prefix}allow_osc_buy", True)
    buy1_only = getattr(config, f"{prefix}buy1_only", False)
    sell1_only = getattr(config, f"{prefix}sell1_only", False)
    sell_mode = getattr(config, f"{prefix}sell_mode", "Normal")
    buy_mult = getattr(config, f"{prefix}buy_mult", 1.0)
    sell_mult = getattr(config, f"{prefix}sell_mult", 1.0)

    # ========== REGIME TRANSITION HANDLING ==========
    # R1 enter/exit
    if regime == 1 and new_state.current_regime != 1:
        # Entering R1 - reset pullback state
        new_state.r1_pb_armed = False
        new_state.r1_pb_used = False

    if regime != 1 and state.current_regime == 1:
        # Exiting R1 - reset pullback state
        new_state.r1_pb_armed = False
        new_state.r1_pb_used = False

    # R3 enter/exit
    if regime == 3 and state.current_regime != 3:
        # Entering R3 - reset breakout state
        new_state.r3_break_used = False

    if regime != 3 and state.current_regime == 3:
        # Exiting R3 - reset breakout state
        new_state.r3_break_used = False

    # ========== R1 PULLBACK TRIGGER ARMING ==========
    # PineScript: hull_dn_start = htfHullDn and not htfHullDn[1]
    # Hull 하락이 "시작"된 봉에서만 arming (이전 봉은 하락 아니었음)
    if regime == 1 and config.r1_pullback_on and not new_state.r1_pb_used:
        hull_dn_start = htf_indicators.hull_dn and not state.prev_hull_dn
        if hull_dn_start:
            new_state.r1_pb_armed = True

    # ========== BUY SIGNAL DETECTION ==========
    osc_trigger = osc_data.sig_up_raw

    # R1 Pullback trigger
    pullback_trigger = (
        regime == 1 and
        config.r1_pullback_on and
        not new_state.r1_pb_used and
        new_state.r1_pb_armed and
        htf_indicators.hull_dn and
        osc_trigger
    )

    # R3 Breakout trigger
    # PineScript: breakout_cond = close > htfSenkouB and close[1] <= htfSenkouB[1]
    close_prev = float(close[-2]) if len(close) > 1 else close_price
    senkou_b = htf_indicators.senkou_b
    prev_senkou_b = state.prev_senkou_b if state.prev_senkou_b is not None else senkou_b
    breakout_condition = close_price > senkou_b and close_prev <= prev_senkou_b
    cloud_ok = not getattr(config, "r3_breakout_require_cloud_bear", True) or htf_indicators.cloud_bear

    breakout_trigger = (
        regime == 3 and
        config.r3_breakout_on and
        not new_state.r3_break_used and
        breakout_condition and
        cloud_ok
    )

    # Combine triggers
    any_buy_trigger = (
        (osc_trigger and allow_osc_buy) or
        pullback_trigger or
        breakout_trigger
    )

    # ========== BUY STAGE HANDLING ==========
    eff_stage = 0 if buy1_only else state.buy_stage
    allow_buy_by_stage = True

    if not buy1_only:
        last_stage = config.max_buy_tranches - 1
        if eff_stage > last_stage:
            eff_stage = last_stage

        if state.buy_stage >= config.max_buy_tranches:
            if config.after_max_buy == "cycle":
                eff_stage = 0
            elif config.after_max_buy == "stop":
                allow_buy_by_stage = False
            else:  # extend
                eff_stage = last_stage

    # ========== CHECK BUY FILTERS ==========
    if any_buy_trigger and allow_buy_by_stage and buy_mult > 0:
        filters_ok, fail_reason = check_buy_filters(
            close_price, osc_data, state, config, regime, has_position, avg_price
        )

        if filters_ok:
            # Determine trigger type
            if breakout_trigger:
                trigger_type = "breakout"
                reason_code = "MR_ENTRY_R3_BREAKOUT"
                reason_text = f"돌파 매수: R3 선행스팬B 상향돌파 1회 트리거"
            elif pullback_trigger:
                trigger_type = "pullback"
                reason_code = "MR_ENTRY_R1_PULLBACK"
                reason_text = f"눌림 매수: R1 HULL 하락구간 1회 트리거"
            else:
                trigger_type = "osc"
                reason_code = "MR_ENTRY_OSC"
                reason_text = f"역추세 진입: OSC 하단밴드 신호 (R{regime})"

            tranche_pct = get_buy_tranche_pct(eff_stage, config, regime, trigger_type)

            if tranche_pct > 0:
                # Update state for buy
                new_state.last_buy_signal_price = close_price

                if pullback_trigger:
                    new_state.r1_pb_used = True
                    new_state.r1_pb_armed = False

                if breakout_trigger:
                    new_state.r3_break_used = True

                snapshot = {
                    "normalized_osc": osc_data.normalized_osc,
                    "lower_band": osc_data.lower_band,
                    "upper_band": osc_data.upper_band,
                    "regime": regime,
                    "buy_stage": eff_stage,
                    "vwma50": htf_indicators.vwma50,
                    "vwma200": htf_indicators.vwma200,
                    "st_direction": htf_indicators.st_direction,
                    "hull_dn": htf_indicators.hull_dn,
                    "trigger_type": trigger_type,
                }

                return SignalResult(
                    action="buy",
                    reason_code=reason_code,
                    reason_text=reason_text,
                    regime=regime,
                    tranche=eff_stage + 1,  # 1-indexed for display
                    tranche_pct=tranche_pct,
                    trigger_type=trigger_type,
                    price_hint=close_price,
                    ts=current_ts,
                    created_at=datetime.now(timezone.utc),
                    snapshot=snapshot,
                ), new_state

    # Update buy signal price even if not buying
    if osc_data.sig_up_raw:
        new_state.last_buy_signal_price = close_price

    # ========== SELL SIGNAL DETECTION ==========
    if has_position and osc_data.sig_dn_raw and sell_mult > 0:
        # Check profit gate
        profit_gate_ok = True
        if avg_price is not None:
            profit_gate_ok = check_sell_profit_gate(
                close_price, avg_price, config.min_profit_pct, config.fee_buffer_pct
            )

        if not profit_gate_ok:
            return SignalResult(
                action="none",
                reason_code="MR_EXIT_PROFIT_GATE",
                reason_text=f"익절게이트 미충족: 최소익절 {config.min_profit_pct}% 필요",
                regime=regime,
                snapshot={"avg_price": avg_price, "close": close_price},
                ts=current_ts,
            ), new_state

        # Check sell stage
        eff_sell_stage = 0 if sell1_only else state.sell_stage
        allow_sell_by_stage = True

        if not sell1_only:
            last_sell_stage = config.max_sell_tranches - 1
            if eff_sell_stage >= config.max_sell_tranches:
                if config.after_max_sell == "cycle":
                    eff_sell_stage = 0
                elif config.after_max_sell == "stop":
                    allow_sell_by_stage = False
                else:
                    eff_sell_stage = last_sell_stage

        if not allow_sell_by_stage:
            return SignalResult(
                action="none",
                reason_code="MR_BLOCKED_STAGE",
                reason_text="SELL 스테이지 제한",
                regime=regime,
                ts=current_ts,
            ), new_state

        # Alternate sell mode (교대매도)
        alt_allow = True
        if sell_mode == "Alternate":
            new_state.alt_sell_toggle = not state.alt_sell_toggle
            alt_allow = new_state.alt_sell_toggle

        if not alt_allow:
            return SignalResult(
                action="none",
                reason_code="MR_BLOCKED_ALTERNATE",
                reason_text="교대매도: 이번 신호 스킵",
                regime=regime,
                ts=current_ts,
            ), new_state

        # Generate sell signal
        tranche_pct = get_sell_tranche_pct(eff_sell_stage, config, regime)

        if tranche_pct > 0:
            snapshot = {
                "normalized_osc": osc_data.normalized_osc,
                "upper_band": osc_data.upper_band,
                "regime": regime,
                "sell_stage": eff_sell_stage,
                "avg_price": avg_price,
                "profit_pct": ((close_price / avg_price) - 1) * 100 if avg_price else 0,
            }

            return SignalResult(
                action="sell",
                reason_code="MR_EXIT_OSC_SPLIT",
                reason_text=f"역추세 분할청산: OSC 상단 SELL{eff_sell_stage + 1} ({tranche_pct:.1f}%)",
                regime=regime,
                tranche=eff_sell_stage + 1,
                tranche_pct=tranche_pct,
                trigger_type="osc",
                price_hint=close_price,
                ts=current_ts,
                created_at=datetime.now(timezone.utc),
                snapshot=snapshot,
            ), new_state

    # No signal
    return SignalResult(
        action="none",
        reason_code="NO_SIGNAL",
        reason_text="",
        regime=regime,
        ts=current_ts,
    ), new_state


def update_state_after_execution(
    state: StrategyState,
    signal: SignalResult,
    config: MRConfig,
    executed: bool = True
) -> StrategyState:
    """
    Update strategy state after order execution.

    This should be called by Hub after successfully executing an order.

    Args:
        state: Current state
        signal: The signal that was executed
        config: Strategy configuration
        executed: Whether the order was actually executed

    Returns:
        Updated StrategyState
    """
    if not executed:
        return state

    new_state = StrategyState(
        buy_stage=state.buy_stage,
        sell_stage=state.sell_stage,
        last_buy_exec_price=state.last_buy_exec_price,
        last_buy_signal_price=state.last_buy_signal_price,
        last_buy_time=state.last_buy_time,
        last_sell_time=state.last_sell_time,
        r1_pb_armed=state.r1_pb_armed,
        r1_pb_used=state.r1_pb_used,
        r3_break_used=state.r3_break_used,
        alt_sell_toggle=state.alt_sell_toggle,
        current_regime=state.current_regime,
        last_bar_time=state.last_bar_time,
        prev_hull_dn=state.prev_hull_dn,
        prev_senkou_b=state.prev_senkou_b,
    )

    regime = signal.regime
    prefix = f"r{regime}_" if regime > 0 else "r1_"

    if signal.is_buy:
        # Update buy stage
        buy1_only = getattr(config, f"{prefix}buy1_only", False)
        if buy1_only:
            new_state.buy_stage = 0
        else:
            last_stage = config.max_buy_tranches - 1
            if config.after_max_buy == "cycle":
                new_state.buy_stage = 0 if state.buy_stage >= last_stage else state.buy_stage + 1
            elif config.after_max_buy == "stop":
                new_state.buy_stage = min(state.buy_stage + 1, last_stage)
            else:  # extend
                new_state.buy_stage = min(state.buy_stage + 1, last_stage)

        new_state.last_buy_exec_price = signal.price_hint
        new_state.last_buy_time = signal.ts

        # Reset sell stage if configured
        reset_sell_on_buy = getattr(config, f"{prefix}reset_sell_on_buy", True) if regime > 0 else True
        if reset_sell_on_buy:
            new_state.sell_stage = 0

    elif signal.is_sell:
        # Update sell stage
        sell1_only = getattr(config, f"{prefix}sell1_only", False)
        if sell1_only:
            new_state.sell_stage = 0
        else:
            last_stage = config.max_sell_tranches - 1
            if config.after_max_sell == "cycle":
                new_state.sell_stage = 0 if state.sell_stage >= last_stage else state.sell_stage + 1
            elif config.after_max_sell == "stop":
                new_state.sell_stage = min(state.sell_stage + 1, last_stage)
            else:  # extend
                new_state.sell_stage = min(state.sell_stage + 1, last_stage)

        new_state.last_sell_time = signal.ts

        # Reset buy stage if configured
        reset_buy_on_sell = getattr(config, f"{prefix}reset_buy_on_sell", True) if regime > 0 else True
        if reset_buy_on_sell:
            new_state.buy_stage = 0
            new_state.last_buy_signal_price = None

    return new_state

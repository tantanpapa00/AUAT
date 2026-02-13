# app/strategy_engine/presets.py
"""
Oscillator Presets and HTF Defaults for Mean Reversion Strategy.

These are internal constants - UI shows only "Setting 1" / "Setting 2".
Based on PineScript: 역추세매매 현물 v0.4
"""

from typing import Dict, Any

# Oscillator Presets (SPO)
# preset1: Default (stable)
# preset2: Sensitive (more signals)
OSC_PRESETS: Dict[str, Dict[str, Any]] = {
    "preset1": {
        "smooth_len": 20,       # len_smooth in PineScript
        "threshold": 1.0,       # Signal threshold
        "std_len": 50,          # len_std in PineScript
        "hma_len": 30,          # HMA length for normalized_osc
        "bb_len": 250,          # Bollinger Band length
        "bb_mult": 2.0,         # Bollinger Band multiplier
    },
    "preset2": {
        "smooth_len": 14,
        "threshold": 0.7,
        "std_len": 50,
        "hma_len": 20,
        "bb_len": 200,
        "bb_mult": 1.8,
    },
}

# HTF (Higher Timeframe) Indicator Defaults
HTF_DEFAULTS: Dict[str, Any] = {
    # VWMA
    "vwma50_len": 50,
    "vwma200_len": 200,
    # Hull MA
    "hull_len": 100,
    # Ichimoku
    "ichi_tenkan": 9,
    "ichi_kijun": 26,
    "ichi_senkou": 52,
    # Supertrend (작가님 확정: 20/5.0)
    "st_atr_len": 20,
    "st_factor": 5.0,
}

# Default regime config for each regime (R1~R4)
# This matches the PineScript defaults
REGIME_DEFAULTS: Dict[int, Dict[str, Any]] = {
    1: {  # R1: 정배열 + ST상승 (눌림 1회 트리거)
        "buy_mult": 1.0,
        "sell_mult": 1.3,
        "allow_osc_buy": True,
        "pullback_on": True,
        "pullback_buy_mult": 1.0,
        "buy1_only": False,
        "sell1_only": False,
        "reset_sell_on_buy": True,
        "reset_buy_on_sell": True,
        "sell_mode": "Normal",
        "filt_below_avg": True,
        "filt_prev_signal": True,
        "filt_prev_exec": True,
    },
    2: {  # R2: 정배열 + ST하락 (매수 금지/극소, 매도 확대)
        "buy_mult": 0.0,
        "sell_mult": 1.6,
        "allow_osc_buy": False,
        "buy1_only": False,
        "sell1_only": False,
        "reset_sell_on_buy": True,
        "reset_buy_on_sell": True,
        "sell_mode": "Alternate",  # 교대매도
        "filt_below_avg": False,
        "filt_prev_signal": False,
        "filt_prev_exec": False,
    },
    3: {  # R3: 역배열 + ST상승 (돌파 1회 트리거)
        "buy_mult": 1.0,
        "sell_mult": 1.3,
        "allow_osc_buy": True,
        "breakout_on": True,
        "breakout_buy_mult": 1.0,
        "buy1_only": True,  # Default ON in PineScript
        "sell1_only": False,
        "reset_sell_on_buy": True,
        "reset_buy_on_sell": True,
        "sell_mode": "Normal",
        "filt_below_avg": False,
        "filt_prev_signal": True,
        "filt_prev_exec": True,
    },
    4: {  # R4: 역배열 + ST하락 (매수 확대, 매도 축소)
        "buy_mult": 1.2,
        "sell_mult": 0.7,
        "allow_osc_buy": True,
        "buy1_only": False,
        "sell1_only": False,
        "reset_sell_on_buy": True,
        "reset_buy_on_sell": False,  # Default OFF in PineScript
        "sell_mode": "Normal",
        "filt_below_avg": True,
        "filt_prev_signal": True,
        "filt_prev_exec": False,
    },
}

# Buy tranches default (10 stages, each 5%)
DEFAULT_BUY_TRANCHES = [5.0, 5.0, 5.0, 5.0, 5.0, 5.0, 5.0, 5.0, 5.0, 5.0]

# Sell tranches default (6 stages)
DEFAULT_SELL_TRANCHES = [10.0, 20.0, 30.0, 5.0, 2.5, 1.0]

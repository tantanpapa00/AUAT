# app/strategy_engine/__init__.py
"""
BBooster Premium Strategy Engine - Mean Reversion (Counter-Trend)

Phase 1: Engine Core
- indicators: SPO, VWMA, HMA, Ichimoku, Supertrend
- regime_detector: 4-Regime detection (R1~R4)
- signal_generator: Buy/Sell signal generation with filters

Architecture (PREMIUM_ENGINE_SPEC compliant):
- Strategy Engine generates signals only (no order execution)
- Hub executes orders based on signal_event
"""

from .models import Candle, SignalResult, HTFIndicators, OscillatorData
from .presets import OSC_PRESETS, HTF_DEFAULTS
from .indicators import (
    smoother_f,
    calc_spo,
    calc_vwma,
    calc_hma,
    calc_ichimoku,
    calc_supertrend,
)
from .regime_detector import detect_regime
from .signal_generator import generate_mr_signal

__all__ = [
    # Models
    "Candle",
    "SignalResult",
    "HTFIndicators",
    "OscillatorData",
    # Presets
    "OSC_PRESETS",
    "HTF_DEFAULTS",
    # Indicators
    "smoother_f",
    "calc_spo",
    "calc_vwma",
    "calc_hma",
    "calc_ichimoku",
    "calc_supertrend",
    # Regime
    "detect_regime",
    # Signal
    "generate_mr_signal",
]

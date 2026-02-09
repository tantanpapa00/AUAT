# app/strategy_engine/__init__.py
"""
BBooster Premium Strategy Engine - Mean Reversion (Counter-Trend)

Phase 1: Engine Core
- indicators: SPO, VWMA, HMA, Ichimoku, Supertrend
- regime_detector: 4-Regime detection (R1~R4)
- signal_generator: Buy/Sell signal generation with filters

Phase 2: Data + Execution
- candle_fetcher: Exchange OHLCV data fetching with cache
- position_manager: Tranche-based position sizing
- hub_integration: Signal to order execution bridge

Architecture (PREMIUM_ENGINE_SPEC compliant):
- Strategy Engine generates signals only (no order execution)
- Hub executes orders based on signal_event
"""

from .models import Candle, SignalResult, HTFIndicators, OscillatorData, MRConfig, StrategyState
from .presets import OSC_PRESETS, HTF_DEFAULTS
from .indicators import (
    smoother_f,
    calc_spo,
    calc_vwma,
    calc_hma,
    calc_ichimoku,
    calc_supertrend,
)
from .regime_detector import detect_regime, calc_htf_indicators
from .signal_generator import generate_mr_signal, calc_osc_data

# Phase 2 modules
from .candle_fetcher import CandleData, CandleCache, get_candle_cache, fetch_candles_from_exchange
from .position_manager import (
    PositionInfo,
    OrderQuantity,
    calculate_buy_quantity,
    calculate_sell_quantity,
    calculate_position_info,
    update_position_after_fill,
)
from .hub_integration import (
    SignalEvent,
    SignalSnapshot,
    process_asset,
    signal_to_order_request,
)
from .scheduler import (
    PremiumScheduler,
    SchedulerConfig,
    ScheduledAsset,
    get_scheduler,
    get_tf_seconds,
    get_current_bar_open_time,
    get_next_bar_close_time,
    seconds_until_bar_close,
)

__all__ = [
    # Models
    "Candle",
    "SignalResult",
    "HTFIndicators",
    "OscillatorData",
    "MRConfig",
    "StrategyState",
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
    "calc_htf_indicators",
    # Signal
    "generate_mr_signal",
    "calc_osc_data",
    # Phase 2: Candle Fetcher
    "CandleData",
    "CandleCache",
    "get_candle_cache",
    "fetch_candles_from_exchange",
    # Phase 2: Position Manager
    "PositionInfo",
    "OrderQuantity",
    "calculate_buy_quantity",
    "calculate_sell_quantity",
    "calculate_position_info",
    "update_position_after_fill",
    # Phase 2: Hub Integration
    "SignalEvent",
    "SignalSnapshot",
    "process_asset",
    "signal_to_order_request",
    # Phase 3: Scheduler
    "PremiumScheduler",
    "SchedulerConfig",
    "ScheduledAsset",
    "get_scheduler",
    "get_tf_seconds",
    "get_current_bar_open_time",
    "get_next_bar_close_time",
    "seconds_until_bar_close",
]

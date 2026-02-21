# app/strategy_engine/models.py
"""
Data models for the Strategy Engine.

Based on PREMIUM_ENGINE_SPEC.md signal_event schema.
"""

from dataclasses import dataclass, field
from typing import Optional, List, Dict, Any
from datetime import datetime


@dataclass(frozen=True)
class Candle:
    """OHLCV candle data."""
    ts: int              # Timestamp in milliseconds
    o: float             # Open
    h: float             # High
    l: float             # Low
    c: float             # Close
    v: float = 0.0       # Volume


@dataclass
class OscillatorData:
    """SPO (Smooth Price Oscillator) calculation result."""
    normalized_osc: float           # Normalized oscillator value
    upper_band: float               # Bollinger upper band
    lower_band: float               # Bollinger lower band
    basis: float                    # Bollinger basis (EMA)
    threshold: float                # Signal threshold
    line_short: float               # Short smoother line
    line_long: float                # Long smoother line
    oscillator_raw: float           # Raw oscillator (short - long)

    # Signal conditions (raw, before filters)
    sig_up_raw: bool = False        # Buy signal raw
    sig_dn_raw: bool = False        # Sell signal raw


@dataclass
class HTFIndicators:
    """Higher Timeframe indicators for regime detection."""
    # VWMA
    vwma50: float = 0.0
    vwma200: float = 0.0

    # Hull MA
    hull: float = 0.0
    hull_up: bool = False           # hull > hull[1]
    hull_dn: bool = False           # hull < hull[1]

    # Ichimoku
    tenkan: float = 0.0
    kijun: float = 0.0
    senkou_a: float = 0.0
    senkou_b: float = 0.0
    cloud_upper: float = 0.0
    cloud_lower: float = 0.0
    cloud_bull: bool = False        # senkou_a > senkou_b
    cloud_bear: bool = False        # senkou_a < senkou_b

    # Supertrend
    st_value: float = 0.0
    st_direction: int = 1           # 1 = up, -1 = down

    # Derived
    bull_stack: bool = False        # vwma50 >= vwma200
    bear_stack: bool = False        # vwma50 < vwma200


@dataclass
class StrategyState:
    """Strategy internal state (persisted in DB)."""
    buy_stage: int = 0
    sell_stage: int = 0
    last_buy_exec_price: Optional[float] = None
    last_buy_signal_price: Optional[float] = None
    last_buy_time: Optional[int] = None      # timestamp ms
    last_sell_time: Optional[int] = None     # timestamp ms

    # R1 pullback trigger state
    r1_pb_armed: bool = False
    r1_pb_used: bool = False

    # R3 breakout trigger state
    r3_break_used: bool = False

    # Alternate sell toggle
    alt_sell_toggle: bool = False

    # Current regime
    current_regime: int = 0

    # Last processed bar
    last_bar_time: Optional[int] = None

    # 이전 봉 HTF 상태 (PineScript [1] 참조용)
    prev_hull_dn: bool = False              # htfHullDn[1]
    prev_senkou_b: Optional[float] = None   # htfSenkouB[1]


@dataclass
class SignalResult:
    """
    Signal generation result.

    Based on PREMIUM_ENGINE_SPEC.md SignalEvent schema.
    """
    # Action
    action: str                     # "buy", "sell", "none"

    # Reason (audit trail)
    reason_code: str                # e.g., "MR_ENTRY_OSC", "MR_EXIT_OSC_SPLIT"
    reason_text: str                # Human readable description

    # Context
    regime: int                     # Current regime (0, 1, 2, 3, 4)
    tranche: int = 0                # Buy/Sell stage
    tranche_pct: float = 0.0        # Percentage for this tranche

    # Snapshot data for audit
    snapshot: Dict[str, Any] = field(default_factory=dict)

    # Trigger type (for special triggers)
    trigger_type: str = "osc"       # "osc", "pullback", "breakout"

    # Price info
    price_hint: Optional[float] = None

    # Timestamps
    ts: int = 0                     # Signal timestamp (ms)
    created_at: Optional[datetime] = None

    @property
    def is_buy(self) -> bool:
        return self.action == "buy"

    @property
    def is_sell(self) -> bool:
        return self.action == "sell"

    @property
    def is_none(self) -> bool:
        return self.action == "none"


@dataclass
class MRConfig:
    """
    Mean Reversion strategy configuration.

    Maps to premium_configs table in DB.
    """
    # Basic
    signal_tf: str = "30m"          # Signal timeframe
    htf_tf: str = "1D"              # HTF timeframe
    osc_preset: str = "preset1"     # "preset1" or "preset2" or "custom"
    osc_smooth_len: int = 20        # Oscillator smoothing length
    osc_threshold: float = 1.0      # Oscillator threshold

    # Cash management
    cash_use_pct: float = 55.0      # % of available cash to use
    hard_cap_pct: float = 100.0     # Max exposure % of equity

    # Profit gate
    min_profit_pct: float = 0.10    # Minimum profit % for sell
    fee_buffer_pct: float = 0.20    # Fee buffer %

    # Trade limits
    one_trade_per_bar: bool = True

    # Buy tranches
    buy_tranches: List[float] = field(default_factory=lambda: [5.0] * 10)
    max_buy_tranches: int = 10
    after_max_buy: str = "extend"   # "extend", "cycle", "stop"

    # Sell tranches
    sell_tranches: List[float] = field(default_factory=lambda: [10.0, 20.0, 30.0, 5.0, 2.5, 1.0])
    max_sell_tranches: int = 6
    after_max_sell: str = "cycle"   # "extend", "cycle", "stop"

    # 4-Regime mode
    use_4regime: bool = True

    # R1 config
    r1_buy_mult: float = 1.0
    r1_sell_mult: float = 1.3
    r1_allow_osc_buy: bool = True
    r1_pullback_on: bool = True
    r1_pullback_buy_mult: float = 1.0
    r1_buy1_only: bool = False
    r1_sell1_only: bool = False
    r1_sell_mode: str = "Normal"
    r1_filt_below_avg: bool = True
    r1_filt_prev_signal: bool = True
    r1_filt_prev_exec: bool = True

    # R2 config
    r2_buy_mult: float = 0.0
    r2_sell_mult: float = 1.6
    r2_allow_osc_buy: bool = False
    r2_buy1_only: bool = False
    r2_sell1_only: bool = False
    r2_sell_mode: str = "Alternate"
    r2_filt_below_avg: bool = False
    r2_filt_prev_signal: bool = False
    r2_filt_prev_exec: bool = False

    # R3 config
    r3_buy_mult: float = 1.0
    r3_sell_mult: float = 1.3
    r3_allow_osc_buy: bool = True
    r3_breakout_on: bool = True
    r3_breakout_buy_mult: float = 1.0
    r3_buy1_only: bool = True
    r3_sell1_only: bool = False
    r3_sell_mode: str = "Normal"
    r3_filt_below_avg: bool = False
    r3_filt_prev_signal: bool = True
    r3_filt_prev_exec: bool = True

    # R4 config
    r4_buy_mult: float = 1.2
    r4_sell_mult: float = 0.7
    r4_allow_osc_buy: bool = True
    r4_buy1_only: bool = False
    r4_sell1_only: bool = False
    r4_sell_mode: str = "Normal"
    r4_filt_below_avg: bool = True
    r4_filt_prev_signal: bool = True
    r4_filt_prev_exec: bool = False

    # Filters (use_lower_band_buy 제거됨 - 불필요한 숨은 필터였음)
    use_add_buy_gap: bool = False
    add_buy_gap_pct: float = 2.0

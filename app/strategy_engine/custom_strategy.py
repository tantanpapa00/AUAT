# app/strategy_engine/custom_strategy.py
"""
Custom Strategy Models for Condition Builder.

Defines the data structures for user-defined trading strategies.
"""

from pydantic import BaseModel, Field
from typing import List, Optional, Literal


class ConditionItem(BaseModel):
    """
    Single condition: e.g., RSI(14) < 30
    """
    # Left side: indicator and its configuration
    indicator: str                    # "RSI", "MACD", "SMA", etc. (registry key)
    output: str                       # "value", "macd", "signal", "k", "upper", etc.
    params: dict = Field(default_factory=dict)  # {"period": 14}, etc.

    # Operator
    operator: Literal[
        ">", "<", ">=", "<=", "==",
        "cross_above", "cross_below"  # Golden cross, Death cross
    ]

    # Right side: compare to fixed value or another indicator
    compare_type: Literal["value", "indicator"]  # Fixed value vs another indicator

    # If compare_type == "value"
    compare_value: Optional[float] = None

    # If compare_type == "indicator"
    compare_indicator: Optional[str] = None       # e.g., "MACD"
    compare_output: Optional[str] = None          # e.g., "signal"
    compare_params: Optional[dict] = None         # e.g., {"fast_length": 12, ...}


class ConditionGroup(BaseModel):
    """
    Condition group: conditions joined by AND or OR.
    """
    conditions: List[ConditionItem]
    logic: Literal["AND", "OR"] = "AND"


class CustomRule(BaseModel):
    """
    Entry or exit rule: groups are joined by OR.
    Within each group, conditions use the group's logic (AND/OR).
    """
    groups: List[ConditionGroup]


class CustomStrategyConfig(BaseModel):
    """
    Complete custom strategy configuration.
    """
    name: str = "내 전략"

    # Trading rules
    entry_rules: CustomRule           # Buy conditions
    exit_rules: CustomRule            # Sell conditions

    # Position sizing
    position_size_pct: float = Field(default=100.0, ge=1, le=100)  # Entry size %

    # Risk management
    stop_loss_pct: Optional[float] = Field(default=None, ge=0.1, le=50)  # Stop loss %
    take_profit_pct: Optional[float] = Field(default=None, ge=0.1, le=100)  # Take profit %

    # Trade settings
    max_positions: int = Field(default=1, ge=1, le=10)  # Max concurrent positions
    commission_pct: float = Field(default=0.015, ge=0, le=1)  # Commission %


class CustomBacktestRequest(BaseModel):
    """
    Request payload for custom strategy backtest.
    """
    exchange: str
    symbol: str
    timeframe: str = "1D"
    start_date: Optional[str] = None   # YYYY-MM-DD format
    end_date: Optional[str] = None     # YYYY-MM-DD format
    days: int = Field(default=365, ge=30, le=3650)  # Fallback if dates not provided
    initial_capital: float = Field(default=10000000, ge=1000)
    strategy: CustomStrategyConfig


class CustomBacktestResponse(BaseModel):
    """
    Response for custom strategy backtest.
    """
    success: bool
    message: Optional[str] = None
    metrics: Optional[dict] = None
    trades: Optional[List[dict]] = None
    equity_curve: Optional[List[dict]] = None
    candles: Optional[List[dict]] = None

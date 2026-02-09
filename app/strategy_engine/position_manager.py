# app/strategy_engine/position_manager.py
"""
Position Manager - Tranche calculations and position tracking.

Handles:
- Buy/Sell quantity calculations based on tranches
- Position size tracking
- Cash management (A-type: available * use_pct * tranche_pct)
- Exposure limits
"""

from typing import Optional, Dict, Any, Tuple
from dataclasses import dataclass
from datetime import datetime
import logging

from .models import MRConfig, StrategyState, SignalResult

logger = logging.getLogger(__name__)


@dataclass
class PositionInfo:
    """Current position information."""
    symbol: str
    exchange: str
    quantity: float
    avg_price: float
    market_price: float
    market_value: float
    unrealized_pnl: float
    unrealized_pnl_pct: float

    @property
    def has_position(self) -> bool:
        return self.quantity > 0


@dataclass
class OrderQuantity:
    """Calculated order quantity."""
    qty: float                  # Quantity to order
    notional: float             # Order value in quote currency
    tranche_pct: float          # Tranche percentage used
    tranche_stage: int          # Tranche stage (1-indexed)
    available_cash: float       # Available cash before order
    post_order_exposure: float  # Exposure after order
    reason: str                 # Calculation reason/notes


def calculate_buy_quantity(
    signal: SignalResult,
    config: MRConfig,
    available_cash: float,
    current_position_value: float,
    equity: float,
    market_price: float,
) -> OrderQuantity:
    """
    Calculate buy order quantity based on A-type formula.

    A-type: buy_amount = available_cash * cash_use_pct * tranche_pct

    Args:
        signal: Generated signal with tranche info
        config: Strategy configuration
        available_cash: Available cash (equity - position_value)
        current_position_value: Current position market value
        equity: Total account equity
        market_price: Current market price

    Returns:
        OrderQuantity with calculated values
    """
    if signal.action != "buy" or market_price <= 0:
        return OrderQuantity(
            qty=0.0,
            notional=0.0,
            tranche_pct=0.0,
            tranche_stage=0,
            available_cash=available_cash,
            post_order_exposure=current_position_value,
            reason="No buy signal or invalid price",
        )

    tranche_pct = signal.tranche_pct
    tranche_stage = signal.tranche

    if tranche_pct <= 0:
        return OrderQuantity(
            qty=0.0,
            notional=0.0,
            tranche_pct=0.0,
            tranche_stage=tranche_stage,
            available_cash=available_cash,
            post_order_exposure=current_position_value,
            reason="Tranche percentage is 0",
        )

    # A-type formula
    # spend_base = available_cash * (cash_use_pct / 100)
    # spend = spend_base * (tranche_pct / 100)
    spend_base = available_cash * (config.cash_use_pct / 100.0)
    spend = spend_base * (tranche_pct / 100.0)

    # Check hard cap (maximum exposure limit)
    max_exposure = equity * (config.hard_cap_pct / 100.0)
    post_order_exposure = current_position_value + spend

    if post_order_exposure > max_exposure:
        # Reduce spend to stay within cap
        allowed_spend = max(0, max_exposure - current_position_value)
        if allowed_spend <= 0:
            return OrderQuantity(
                qty=0.0,
                notional=0.0,
                tranche_pct=tranche_pct,
                tranche_stage=tranche_stage,
                available_cash=available_cash,
                post_order_exposure=current_position_value,
                reason=f"Hard cap reached ({config.hard_cap_pct}%)",
            )
        spend = allowed_spend
        post_order_exposure = current_position_value + spend

    # Calculate quantity
    qty = spend / market_price

    if qty <= 0:
        return OrderQuantity(
            qty=0.0,
            notional=0.0,
            tranche_pct=tranche_pct,
            tranche_stage=tranche_stage,
            available_cash=available_cash,
            post_order_exposure=current_position_value,
            reason="Calculated quantity is 0",
        )

    return OrderQuantity(
        qty=qty,
        notional=spend,
        tranche_pct=tranche_pct,
        tranche_stage=tranche_stage,
        available_cash=available_cash,
        post_order_exposure=post_order_exposure,
        reason=f"BUY{tranche_stage}: {tranche_pct}% of {config.cash_use_pct}% available",
    )


def calculate_sell_quantity(
    signal: SignalResult,
    config: MRConfig,
    position_qty: float,
    market_price: float,
) -> OrderQuantity:
    """
    Calculate sell order quantity based on position percentage.

    Sell uses position-based percentage (not cash-based).

    Args:
        signal: Generated signal with tranche info
        config: Strategy configuration
        position_qty: Current position quantity
        market_price: Current market price

    Returns:
        OrderQuantity with calculated values
    """
    if signal.action != "sell" or position_qty <= 0:
        return OrderQuantity(
            qty=0.0,
            notional=0.0,
            tranche_pct=0.0,
            tranche_stage=0,
            available_cash=0.0,
            post_order_exposure=position_qty * market_price if market_price > 0 else 0,
            reason="No sell signal or no position",
        )

    tranche_pct = signal.tranche_pct
    tranche_stage = signal.tranche

    if tranche_pct <= 0:
        return OrderQuantity(
            qty=0.0,
            notional=0.0,
            tranche_pct=0.0,
            tranche_stage=tranche_stage,
            available_cash=0.0,
            post_order_exposure=position_qty * market_price,
            reason="Tranche percentage is 0",
        )

    # Calculate sell quantity as percentage of position
    qty = position_qty * (tranche_pct / 100.0)
    qty = min(qty, position_qty)  # Can't sell more than we have

    notional = qty * market_price
    remaining_qty = position_qty - qty
    post_order_exposure = remaining_qty * market_price

    return OrderQuantity(
        qty=qty,
        notional=notional,
        tranche_pct=tranche_pct,
        tranche_stage=tranche_stage,
        available_cash=0.0,  # Not relevant for sells
        post_order_exposure=post_order_exposure,
        reason=f"SELL{tranche_stage}: {tranche_pct}% of position",
    )


def calculate_position_info(
    symbol: str,
    exchange: str,
    position_qty: float,
    avg_price: float,
    market_price: float,
) -> PositionInfo:
    """
    Calculate position information.

    Args:
        symbol: Trading symbol
        exchange: Exchange name
        position_qty: Position quantity
        avg_price: Average entry price
        market_price: Current market price

    Returns:
        PositionInfo with calculated values
    """
    market_value = position_qty * market_price if market_price > 0 else 0

    if position_qty > 0 and avg_price > 0:
        unrealized_pnl = (market_price - avg_price) * position_qty
        unrealized_pnl_pct = ((market_price / avg_price) - 1) * 100
    else:
        unrealized_pnl = 0.0
        unrealized_pnl_pct = 0.0

    return PositionInfo(
        symbol=symbol,
        exchange=exchange,
        quantity=position_qty,
        avg_price=avg_price,
        market_price=market_price,
        market_value=market_value,
        unrealized_pnl=unrealized_pnl,
        unrealized_pnl_pct=unrealized_pnl_pct,
    )


def update_position_after_fill(
    position: PositionInfo,
    side: str,
    fill_qty: float,
    fill_price: float,
) -> PositionInfo:
    """
    Update position after order fill.

    Uses moving average for buy fills.

    Args:
        position: Current position
        side: "buy" or "sell"
        fill_qty: Filled quantity
        fill_price: Fill price

    Returns:
        Updated PositionInfo
    """
    if side == "buy":
        # Moving average formula
        old_qty = position.quantity
        old_avg = position.avg_price if position.quantity > 0 else 0

        new_qty = old_qty + fill_qty
        if new_qty > 0:
            # new_avg = (old_avg * old_qty + fill_price * fill_qty) / new_qty
            if old_qty > 0:
                new_avg = (old_avg * old_qty + fill_price * fill_qty) / new_qty
            else:
                new_avg = fill_price
        else:
            new_avg = 0

        return PositionInfo(
            symbol=position.symbol,
            exchange=position.exchange,
            quantity=new_qty,
            avg_price=new_avg,
            market_price=fill_price,  # Update market price to fill price
            market_value=new_qty * fill_price,
            unrealized_pnl=0.0,  # Reset after fill
            unrealized_pnl_pct=0.0,
        )

    elif side == "sell":
        # Sell doesn't change average price (only quantity)
        new_qty = max(0, position.quantity - fill_qty)

        # If fully closed, reset avg price
        if new_qty <= 0:
            return PositionInfo(
                symbol=position.symbol,
                exchange=position.exchange,
                quantity=0.0,
                avg_price=0.0,
                market_price=fill_price,
                market_value=0.0,
                unrealized_pnl=0.0,
                unrealized_pnl_pct=0.0,
            )

        return PositionInfo(
            symbol=position.symbol,
            exchange=position.exchange,
            quantity=new_qty,
            avg_price=position.avg_price,  # Keep avg price
            market_price=fill_price,
            market_value=new_qty * fill_price,
            unrealized_pnl=(fill_price - position.avg_price) * new_qty,
            unrealized_pnl_pct=((fill_price / position.avg_price) - 1) * 100 if position.avg_price > 0 else 0,
        )

    return position


def check_trading_limits(
    signal: SignalResult,
    state: StrategyState,
    config: MRConfig,
    current_ts: int,
) -> Tuple[bool, str]:
    """
    Check trading limits before order.

    Args:
        signal: Generated signal
        state: Strategy state
        config: Configuration
        current_ts: Current timestamp (ms)

    Returns:
        Tuple of (allowed, reason)
    """
    # One trade per bar check
    if config.one_trade_per_bar:
        if signal.is_buy and state.last_buy_time:
            # Check if we already traded this bar
            # This is simplified - actual implementation needs bar timestamp
            pass

        if signal.is_sell and state.last_sell_time:
            pass

    return True, ""


def get_effective_tranche_stage(
    current_stage: int,
    max_stages: int,
    after_max: str,
    stage_1_only: bool,
) -> Tuple[int, bool]:
    """
    Get effective tranche stage considering cycling/stopping.

    Args:
        current_stage: Current stage (0-indexed)
        max_stages: Maximum number of stages
        after_max: "extend", "cycle", or "stop"
        stage_1_only: Whether to always use stage 1

    Returns:
        Tuple of (effective_stage, allow_trade)
    """
    if stage_1_only:
        return 0, True

    last_stage = max_stages - 1

    if current_stage >= max_stages:
        if after_max == "cycle":
            return 0, True
        elif after_max == "stop":
            return last_stage, False
        else:  # extend
            return last_stage, True

    return current_stage, True

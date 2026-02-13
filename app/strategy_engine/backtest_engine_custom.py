# app/strategy_engine/backtest_engine_custom.py
"""
Custom Strategy Backtest Engine.

Runs backtests for user-defined strategies with condition-based rules.
"""

import math
from dataclasses import dataclass, asdict
from typing import List, Dict, Any, Optional
from datetime import datetime

import numpy as np

from app.strategy_engine.custom_strategy import CustomStrategyConfig, CustomBacktestRequest
from app.strategy_engine.condition_evaluator import evaluate_rule
from app.strategy_engine.models import Candle


@dataclass
class CustomBacktestTrade:
    """Trade record for custom backtest"""
    bar_index: int
    timestamp: int
    action: str  # "buy" or "sell"
    price: float
    quantity: float
    reason: str  # "entry", "exit", "stop_loss", "take_profit"
    pnl: Optional[float] = None
    pnl_pct: Optional[float] = None
    commission: float = 0.0


@dataclass
class CustomBacktestMetrics:
    """Performance metrics (TradingView format)"""
    initial_capital: float = 0.0
    final_capital: float = 0.0
    total_return_pct: float = 0.0
    cagr_pct: float = 0.0
    max_drawdown_pct: float = 0.0
    max_drawdown: float = 0.0
    sharpe_ratio: float = 0.0
    win_rate_pct: float = 0.0
    total_trades: int = 0
    winning_trades: int = 0
    losing_trades: int = 0
    avg_win_pct: float = 0.0
    avg_loss_pct: float = 0.0
    profit_factor: float = 0.0
    max_consecutive_wins: int = 0
    max_consecutive_losses: int = 0
    net_profit: float = 0.0
    net_profit_pct: float = 0.0
    gross_profit: float = 0.0
    gross_profit_pct: float = 0.0
    gross_loss: float = 0.0
    gross_loss_pct: float = 0.0
    commission_paid: float = 0.0
    expected_value: float = 0.0
    unrealized_pnl: float = 0.0
    unrealized_pnl_pct: float = 0.0

    # Buy/Sell separated stats (for TradingView table)
    buy_trades: int = 0
    buy_winning: int = 0
    buy_losing: int = 0
    buy_gross_profit: float = 0.0
    buy_gross_profit_pct: float = 0.0
    buy_gross_loss: float = 0.0
    buy_gross_loss_pct: float = 0.0
    buy_net_profit: float = 0.0
    buy_net_profit_pct: float = 0.0
    buy_avg_profit: float = 0.0
    buy_avg_profit_pct: float = 0.0
    buy_avg_loss: float = 0.0
    buy_avg_loss_pct: float = 0.0
    buy_commission: float = 0.0
    buy_max_consecutive_wins: int = 0
    buy_max_consecutive_losses: int = 0

    # Sell side (0 for long-only strategies)
    sell_trades: int = 0
    sell_winning: int = 0
    sell_losing: int = 0
    sell_gross_profit: float = 0.0
    sell_gross_profit_pct: float = 0.0
    sell_gross_loss: float = 0.0
    sell_gross_loss_pct: float = 0.0
    sell_net_profit: float = 0.0
    sell_net_profit_pct: float = 0.0
    sell_avg_profit: float = 0.0
    sell_avg_profit_pct: float = 0.0
    sell_avg_loss: float = 0.0
    sell_avg_loss_pct: float = 0.0
    sell_commission: float = 0.0
    sell_max_consecutive_wins: int = 0
    sell_max_consecutive_losses: int = 0


def calculate_custom_metrics(
    trades: List[CustomBacktestTrade],
    initial_capital: float,
    final_equity: float,
    unrealized_pnl: float,
    unrealized_pnl_pct: float,
    equity_curve: List[Dict[str, Any]],
    total_commission: float,
) -> CustomBacktestMetrics:
    """Calculate performance metrics"""
    metrics = CustomBacktestMetrics()
    metrics.initial_capital = initial_capital
    metrics.final_capital = final_equity

    if not equity_curve:
        return metrics

    # Total return
    metrics.total_return_pct = (final_equity - initial_capital) / initial_capital * 100 if initial_capital > 0 else 0

    # CAGR
    days = len(equity_curve)
    years = days / 365
    if years > 0 and final_equity > 0 and initial_capital > 0:
        metrics.cagr_pct = ((final_equity / initial_capital) ** (1 / years) - 1) * 100

    # MDD
    peak = initial_capital
    max_dd = 0
    max_dd_amount = 0
    for point in equity_curve:
        eq = point["equity"]
        peak = max(peak, eq)
        dd = (peak - eq) / peak * 100 if peak > 0 else 0
        dd_amount = peak - eq
        if dd > max_dd:
            max_dd = dd
            max_dd_amount = dd_amount
    metrics.max_drawdown_pct = -max_dd
    metrics.max_drawdown = -max_dd_amount

    # Sharpe ratio
    if len(equity_curve) > 1:
        returns = []
        for i in range(1, len(equity_curve)):
            prev_eq = equity_curve[i - 1]["equity"]
            curr_eq = equity_curve[i]["equity"]
            if prev_eq > 0:
                returns.append((curr_eq - prev_eq) / prev_eq)

        if returns:
            avg_ret = sum(returns) / len(returns)
            std_ret = math.sqrt(sum((r - avg_ret) ** 2 for r in returns) / len(returns)) if len(returns) > 1 else 0
            if std_ret > 0:
                metrics.sharpe_ratio = avg_ret / std_ret * math.sqrt(252)

    # Commission and unrealized PnL
    metrics.commission_paid = total_commission
    metrics.unrealized_pnl = unrealized_pnl
    metrics.unrealized_pnl_pct = unrealized_pnl_pct

    # Trade statistics
    sell_trades = [t for t in trades if t.action == "sell" and t.pnl is not None]
    buy_trades = [t for t in trades if t.action == "buy"]
    metrics.total_trades = len(sell_trades)

    wins = [t for t in sell_trades if t.pnl > 0]
    losses = [t for t in sell_trades if t.pnl <= 0]

    gross_profit = sum(t.pnl for t in wins) if wins else 0
    gross_loss = abs(sum(t.pnl for t in losses)) if losses else 0
    net_profit = gross_profit - gross_loss

    metrics.gross_profit = gross_profit
    metrics.gross_profit_pct = (gross_profit / initial_capital) * 100 if initial_capital > 0 else 0
    metrics.gross_loss = gross_loss
    metrics.gross_loss_pct = (gross_loss / initial_capital) * 100 if initial_capital > 0 else 0
    metrics.net_profit = net_profit
    metrics.net_profit_pct = (net_profit / initial_capital) * 100 if initial_capital > 0 else 0

    # Win/Loss stats
    metrics.winning_trades = len(wins)
    metrics.losing_trades = len(losses)
    metrics.win_rate_pct = len(wins) / len(sell_trades) * 100 if sell_trades else 0

    if wins:
        total_win = sum(t.pnl for t in wins)
        metrics.avg_win_pct = (total_win / len(wins)) / initial_capital * 100

    if losses:
        total_loss = sum(t.pnl for t in losses)
        metrics.avg_loss_pct = (total_loss / len(losses)) / initial_capital * 100

    # Profit Factor
    if gross_loss > 0:
        metrics.profit_factor = gross_profit / gross_loss
    elif gross_profit > 0:
        metrics.profit_factor = float('inf')

    # Expected value
    if sell_trades:
        metrics.expected_value = net_profit / len(sell_trades)

    # Consecutive wins/losses
    current_streak = 0
    max_win_streak = 0
    max_loss_streak = 0
    last_was_win = None

    for t in sell_trades:
        is_win = t.pnl > 0
        if last_was_win is None or is_win == last_was_win:
            current_streak += 1
        else:
            current_streak = 1

        if is_win:
            max_win_streak = max(max_win_streak, current_streak)
        else:
            max_loss_streak = max(max_loss_streak, current_streak)

        last_was_win = is_win

    metrics.max_consecutive_wins = max_win_streak
    metrics.max_consecutive_losses = max_loss_streak

    # Buy side stats (long-only)
    buy_commission = sum(t.commission for t in buy_trades)
    sell_commission = sum(t.commission for t in sell_trades)

    metrics.buy_trades = len(sell_trades)
    metrics.buy_winning = len(wins)
    metrics.buy_losing = len(losses)
    metrics.buy_gross_profit = gross_profit
    metrics.buy_gross_profit_pct = metrics.gross_profit_pct
    metrics.buy_gross_loss = gross_loss
    metrics.buy_gross_loss_pct = metrics.gross_loss_pct
    metrics.buy_net_profit = net_profit
    metrics.buy_net_profit_pct = metrics.net_profit_pct
    metrics.buy_commission = buy_commission + sell_commission
    metrics.buy_max_consecutive_wins = max_win_streak
    metrics.buy_max_consecutive_losses = max_loss_streak

    if wins:
        metrics.buy_avg_profit = gross_profit / len(wins)
        metrics.buy_avg_profit_pct = metrics.avg_win_pct

    if losses:
        metrics.buy_avg_loss = gross_loss / len(losses)
        metrics.buy_avg_loss_pct = metrics.avg_loss_pct

    return metrics


async def run_custom_backtest(
    candles: List[Candle],
    config: CustomStrategyConfig,
    initial_capital: float,
) -> Dict[str, Any]:
    """
    Run custom strategy backtest.

    Args:
        candles: List of Candle objects (oldest first)
        config: Custom strategy configuration
        initial_capital: Starting capital

    Returns:
        Dict with metrics, trades, equity_curve, candles
    """
    if not candles or len(candles) < 200:
        return {
            "success": False,
            "message": f"Insufficient candle data: {len(candles) if candles else 0} bars (need at least 200)",
            "metrics": None,
            "trades": [],
            "equity_curve": [],
            "candles": [],
        }

    # Convert candles to numpy arrays
    n = len(candles)
    opens = np.array([c.o for c in candles], dtype=float)
    highs = np.array([c.h for c in candles], dtype=float)
    lows = np.array([c.l for c in candles], dtype=float)
    closes = np.array([c.c for c in candles], dtype=float)
    volumes = np.array([c.v for c in candles], dtype=float)
    timestamps = [c.ts for c in candles]

    candle_dict = {
        "open": opens,
        "high": highs,
        "low": lows,
        "close": closes,
        "volume": volumes,
    }

    # State variables
    equity = initial_capital
    position_qty = 0.0
    entry_price = 0.0
    trades: List[CustomBacktestTrade] = []
    equity_curve: List[Dict[str, Any]] = []
    total_commission = 0.0

    fee_rate = config.commission_pct / 100.0
    start_bar = 200  # Skip first bars for indicator warmup

    # Indicator cache for efficiency
    indicator_cache: Dict[str, np.ndarray] = {}

    for i in range(start_bar, n):
        curr_close = closes[i]
        curr_high = highs[i]
        curr_low = lows[i]
        curr_ts = timestamps[i]

        # No position -> check entry
        if position_qty == 0:
            if evaluate_rule(candle_dict, config.entry_rules, i, indicator_cache):
                # Buy
                size_pct = config.position_size_pct / 100.0
                invest_amount = equity * size_pct
                commission = invest_amount * fee_rate
                position_qty = (invest_amount - commission) / curr_close
                entry_price = curr_close
                equity -= invest_amount
                total_commission += commission

                trades.append(CustomBacktestTrade(
                    bar_index=i,
                    timestamp=curr_ts,
                    action="buy",
                    price=curr_close,
                    quantity=position_qty,
                    reason="entry",
                    commission=commission,
                ))

        # Has position -> check exit conditions
        elif position_qty > 0:
            sold = False

            # 1. Stop loss check
            if config.stop_loss_pct and not sold:
                sl_price = entry_price * (1 - config.stop_loss_pct / 100.0)
                if curr_low <= sl_price:
                    exit_price = sl_price  # Assume hit at SL price
                    sell_amount = position_qty * exit_price
                    commission = sell_amount * fee_rate
                    pnl = (exit_price - entry_price) * position_qty - commission
                    pnl_pct = (exit_price / entry_price - 1) * 100

                    equity += sell_amount - commission
                    total_commission += commission

                    trades.append(CustomBacktestTrade(
                        bar_index=i,
                        timestamp=curr_ts,
                        action="sell",
                        price=exit_price,
                        quantity=position_qty,
                        reason="stop_loss",
                        pnl=pnl,
                        pnl_pct=pnl_pct,
                        commission=commission,
                    ))
                    position_qty = 0
                    sold = True

            # 2. Take profit check
            if config.take_profit_pct and not sold:
                tp_price = entry_price * (1 + config.take_profit_pct / 100.0)
                if curr_high >= tp_price:
                    exit_price = tp_price  # Assume hit at TP price
                    sell_amount = position_qty * exit_price
                    commission = sell_amount * fee_rate
                    pnl = (exit_price - entry_price) * position_qty - commission
                    pnl_pct = (exit_price / entry_price - 1) * 100

                    equity += sell_amount - commission
                    total_commission += commission

                    trades.append(CustomBacktestTrade(
                        bar_index=i,
                        timestamp=curr_ts,
                        action="sell",
                        price=exit_price,
                        quantity=position_qty,
                        reason="take_profit",
                        pnl=pnl,
                        pnl_pct=pnl_pct,
                        commission=commission,
                    ))
                    position_qty = 0
                    sold = True

            # 3. Exit rule check
            if not sold and evaluate_rule(candle_dict, config.exit_rules, i, indicator_cache):
                sell_amount = position_qty * curr_close
                commission = sell_amount * fee_rate
                pnl = (curr_close - entry_price) * position_qty - commission
                pnl_pct = (curr_close / entry_price - 1) * 100

                equity += sell_amount - commission
                total_commission += commission

                trades.append(CustomBacktestTrade(
                    bar_index=i,
                    timestamp=curr_ts,
                    action="sell",
                    price=curr_close,
                    quantity=position_qty,
                    reason="exit",
                    pnl=pnl,
                    pnl_pct=pnl_pct,
                    commission=commission,
                ))
                position_qty = 0

        # Update equity curve
        current_equity = equity + position_qty * curr_close
        equity_curve.append({
            "timestamp": curr_ts,
            "equity": current_equity,
        })

    # Calculate unrealized PnL
    unrealized_pnl = 0.0
    unrealized_pnl_pct = 0.0
    if position_qty > 0:
        last_price = closes[-1]
        estimated_commission = position_qty * last_price * fee_rate
        unrealized_pnl = (last_price - entry_price) * position_qty - estimated_commission
        unrealized_pnl_pct = (unrealized_pnl / initial_capital) * 100 if initial_capital > 0 else 0

    final_equity = equity + position_qty * closes[-1] if position_qty > 0 else equity

    # Calculate metrics
    metrics = calculate_custom_metrics(
        trades=trades,
        initial_capital=initial_capital,
        final_equity=final_equity,
        unrealized_pnl=unrealized_pnl,
        unrealized_pnl_pct=unrealized_pnl_pct,
        equity_curve=equity_curve,
        total_commission=total_commission,
    )

    # Sample candles (max 1000 for chart)
    candle_data = sample_candles(candles, 1000)

    return {
        "success": True,
        "message": None,
        "metrics": asdict(metrics),
        "trades": [asdict(t) for t in trades],
        "equity_curve": equity_curve,
        "candles": candle_data,
    }


def sample_candles(candles: List[Candle], max_count: int = 1000) -> List[Dict]:
    """Sample candles for chart display"""
    if len(candles) <= max_count:
        return [
            {
                "timestamp": c.ts,
                "open": c.o,
                "high": c.h,
                "low": c.l,
                "close": c.c,
                "volume": c.v,
            }
            for c in candles
        ]

    # Sample every Nth candle
    step = len(candles) // max_count
    sampled = candles[::step][:max_count]

    return [
        {
            "timestamp": c.ts,
            "open": c.o,
            "high": c.h,
            "low": c.l,
            "close": c.c,
            "volume": c.v,
        }
        for c in sampled
    ]

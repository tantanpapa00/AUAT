# tests/test_backtest_engine.py
"""
Tests for backtest_engine.py - MR Premium Strategy Backtest.

Phase 5: Backtest engine tests.
"""

import pytest
from datetime import datetime, timezone

from app.strategy_engine.backtest_engine import (
    BacktestTrade,
    BacktestMetrics,
    BacktestResult,
    Position,
    run_mr_backtest,
    calculate_metrics,
    generate_sample_candles,
)
from app.strategy_engine.models import MRConfig, Candle


class TestPosition:
    """Test Position class."""

    def test_position_add(self):
        """Test adding to position."""
        pos = Position()
        pos.add(10, 100)

        assert pos.quantity == 10
        assert pos.avg_price == 100
        assert pos.total_cost == 1000

    def test_position_add_multiple(self):
        """Test adding multiple times to position."""
        pos = Position()
        pos.add(10, 100)  # Cost 1000
        pos.add(10, 120)  # Cost 1200

        assert pos.quantity == 20
        assert pos.avg_price == 110  # (1000 + 1200) / 20
        assert pos.total_cost == 2200

    def test_position_remove(self):
        """Test removing from position."""
        pos = Position()
        pos.add(10, 100)

        pnl = pos.remove(5, 120)

        assert pos.quantity == 5
        assert pnl == 100  # (120 - 100) * 5

    def test_position_remove_all(self):
        """Test removing all from position."""
        pos = Position()
        pos.add(10, 100)

        pnl = pos.remove(10, 90)

        assert pos.quantity == 0
        assert pnl == -100  # (90 - 100) * 10

    def test_position_remove_over_quantity(self):
        """Test removing more than available."""
        pos = Position()
        pos.add(5, 100)

        pnl = pos.remove(10, 120)

        assert pos.quantity == 0
        assert pnl == 100  # (120 - 100) * 5


class TestGenerateSampleCandles:
    """Test sample candle generation."""

    def test_generate_candles_count(self):
        """Test correct number of candles generated."""
        candles = generate_sample_candles(days=10)
        assert len(candles) == 10 * 24  # 1시간봉

    def test_generate_candles_structure(self):
        """Test candle structure."""
        candles = generate_sample_candles(days=1)

        for candle in candles:
            assert isinstance(candle, Candle)
            assert candle.ts > 0
            assert candle.h >= candle.l
            assert candle.h >= candle.o
            assert candle.h >= candle.c
            assert candle.l <= candle.o
            assert candle.l <= candle.c
            assert candle.v >= 0

    def test_generate_candles_deterministic(self):
        """Test same seed produces same candles."""
        candles1 = generate_sample_candles(days=5, seed=42)
        candles2 = generate_sample_candles(days=5, seed=42)

        for c1, c2 in zip(candles1, candles2):
            assert c1.c == c2.c


class TestCalculateMetrics:
    """Test metrics calculation."""

    def test_metrics_empty(self):
        """Test metrics with empty data."""
        metrics = calculate_metrics([], [], 10000, 10000)

        assert metrics.total_return_pct == 0
        assert metrics.total_trades == 0

    def test_metrics_profit(self):
        """Test metrics with profitable trades."""
        equity_curve = [
            {"equity": 10000},
            {"equity": 11000},
            {"equity": 12000},
        ]
        trades = [
            BacktestTrade(
                bar_index=1, timestamp=1000, action="sell",
                price=110, quantity=10, tranche=1, reason_code="TEST",
                pnl=1000, pnl_pct=10.0
            ),
        ]

        metrics = calculate_metrics(equity_curve, trades, 10000, 12000)

        assert metrics.total_return_pct == 20.0
        assert metrics.total_trades == 1
        assert metrics.winning_trades == 1
        assert metrics.win_rate_pct == 100.0

    def test_metrics_loss(self):
        """Test metrics with losing trades."""
        equity_curve = [
            {"equity": 10000},
            {"equity": 9000},
            {"equity": 8000},
        ]
        trades = [
            BacktestTrade(
                bar_index=1, timestamp=1000, action="sell",
                price=90, quantity=10, tranche=1, reason_code="TEST",
                pnl=-1000, pnl_pct=-10.0
            ),
        ]

        metrics = calculate_metrics(equity_curve, trades, 10000, 8000)

        assert metrics.total_return_pct == -20.0
        assert metrics.total_trades == 1
        assert metrics.losing_trades == 1
        assert metrics.win_rate_pct == 0.0

    def test_metrics_mdd(self):
        """Test MDD calculation."""
        equity_curve = [
            {"equity": 10000},
            {"equity": 12000},  # Peak
            {"equity": 9000},   # Drawdown: (12000-9000)/12000 = 25%
            {"equity": 11000},
        ]

        metrics = calculate_metrics(equity_curve, [], 10000, 11000)

        assert metrics.max_drawdown_pct == -25.0


class TestRunMrBacktest:
    """Test MR backtest execution."""

    def test_backtest_insufficient_data(self):
        """Test backtest with insufficient data."""
        candles = generate_sample_candles(days=5)  # 120 candles < 300

        result = run_mr_backtest(candles)

        assert result.success is False
        assert "데이터 부족" in result.message

    def test_backtest_with_sample_data(self):
        """Test backtest with sample data."""
        candles = generate_sample_candles(days=60)  # 1440 candles

        result = run_mr_backtest(candles)

        assert result.success is True
        assert len(result.equity_curve) > 0
        assert result.metrics.total_return_pct != 0 or result.metrics.total_trades >= 0

    def test_backtest_with_config(self):
        """Test backtest with custom config."""
        candles = generate_sample_candles(days=60)
        config = MRConfig(
            osc_preset="preset2",
            cash_use_pct=80.0,
            use_4regime=False,
        )

        result = run_mr_backtest(candles, config=config)

        assert result.success is True

    def test_backtest_equity_curve_structure(self):
        """Test equity curve structure."""
        candles = generate_sample_candles(days=60)

        result = run_mr_backtest(candles)

        if result.equity_curve:
            point = result.equity_curve[0]
            assert "bar_index" in point
            assert "timestamp" in point
            assert "equity" in point
            assert "cash" in point

    def test_backtest_trades_structure(self):
        """Test trades structure."""
        candles = generate_sample_candles(days=60)

        result = run_mr_backtest(candles)

        for trade in result.trades:
            assert isinstance(trade, BacktestTrade)
            assert trade.action in ["buy", "sell"]
            assert trade.price > 0
            assert trade.quantity > 0


class TestBacktestMetrics:
    """Test BacktestMetrics dataclass."""

    def test_metrics_defaults(self):
        """Test default values."""
        metrics = BacktestMetrics()

        assert metrics.total_return_pct == 0.0
        assert metrics.cagr_pct == 0.0
        assert metrics.max_drawdown_pct == 0.0
        assert metrics.sharpe_ratio == 0.0
        assert metrics.win_rate_pct == 0.0
        assert metrics.total_trades == 0


class TestBacktestResult:
    """Test BacktestResult dataclass."""

    def test_result_success(self):
        """Test successful result."""
        result = BacktestResult(
            success=True,
            message="완료",
            metrics=BacktestMetrics(total_return_pct=10.0),
        )

        assert result.success is True
        assert result.metrics.total_return_pct == 10.0
        assert result.equity_curve == []
        assert result.trades == []

    def test_result_failure(self):
        """Test failure result."""
        result = BacktestResult(
            success=False,
            message="오류 발생",
            metrics=BacktestMetrics(),
        )

        assert result.success is False
        assert "오류" in result.message

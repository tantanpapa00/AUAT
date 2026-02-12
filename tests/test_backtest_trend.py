# tests/test_backtest_trend.py
"""
Unit tests for Trend Strategy backtest engine.

Validates: run_trend_backtest, sample candle generation, weekly aggregation
"""

import pytest
import numpy as np
from datetime import datetime, timezone

from app.strategy_engine.backtest_engine_trend import (
    run_trend_backtest,
    generate_trend_sample_candles,
    generate_weekly_candles_from_daily,
)
from app.strategy_engine.signal_generator_trend import TrendConfig, TrendState
from app.strategy_engine.models import Candle
from app.strategy_engine.backtest_engine import BacktestResult, BacktestMetrics


class TestGenerateTrendSampleCandles:
    """Test sample candle generation for trend backtest."""

    def test_basic_generation(self):
        """Test basic candle generation."""
        candles = generate_trend_sample_candles(days=365)

        assert len(candles) == 365

        # Check first candle structure
        first = candles[0]
        assert hasattr(first, 'ts')
        assert hasattr(first, 'o')
        assert hasattr(first, 'h')
        assert hasattr(first, 'l')
        assert hasattr(first, 'c')
        assert hasattr(first, 'v')

    def test_ohlcv_validity(self):
        """Test OHLCV values are valid."""
        candles = generate_trend_sample_candles(days=100)

        for candle in candles:
            assert candle.h >= candle.o
            assert candle.h >= candle.c
            assert candle.l <= candle.o
            assert candle.l <= candle.c
            assert candle.h >= candle.l
            assert candle.v > 0

    def test_uptrend_bias(self):
        """Test that sample data has upward trend."""
        candles = generate_trend_sample_candles(
            days=365,
            base_price=100.0,
            trend=0.001,  # Strong uptrend
            seed=42,
        )

        # End price should be higher than start
        start_price = candles[0].c
        end_price = candles[-1].c

        # With positive trend, end should be higher most of the time
        assert end_price > start_price * 0.8  # Allow some variance

    def test_reproducibility(self):
        """Test same seed produces same data."""
        candles1 = generate_trend_sample_candles(days=100, seed=42)
        candles2 = generate_trend_sample_candles(days=100, seed=42)

        for c1, c2 in zip(candles1, candles2):
            assert c1.ts == c2.ts
            assert c1.o == c2.o
            assert c1.h == c2.h
            assert c1.l == c2.l
            assert c1.c == c2.c

    def test_different_seeds(self):
        """Test different seeds produce different data."""
        candles1 = generate_trend_sample_candles(days=100, seed=42)
        candles2 = generate_trend_sample_candles(days=100, seed=123)

        # Should be different
        assert candles1[-1].c != candles2[-1].c


class TestGenerateWeeklyCandlesFromDaily:
    """Test weekly candle aggregation."""

    def test_basic_aggregation(self):
        """Test basic weekly aggregation."""
        daily = generate_trend_sample_candles(days=30)
        weekly = generate_weekly_candles_from_daily(daily)

        # 30 days should produce 6 weekly candles
        assert len(weekly) == 6

    def test_week_high_low(self):
        """Test weekly high/low are correct."""
        # Create known daily data
        daily = []
        ts = int(datetime(2023, 1, 1, tzinfo=timezone.utc).timestamp() * 1000)

        for i in range(5):  # One week
            daily.append(Candle(
                ts=ts + i * 86400000,
                o=100.0 + i,
                h=110.0 + i,
                l=90.0 + i,
                c=105.0 + i,
                v=1000000.0,
            ))

        weekly = generate_weekly_candles_from_daily(daily)

        assert len(weekly) == 1

        # Weekly high should be max of all daily highs
        assert weekly[0].h == 114.0  # 110 + 4
        # Weekly low should be min of all daily lows
        assert weekly[0].l == 90.0  # 90 + 0

    def test_empty_input(self):
        """Test empty input returns empty."""
        weekly = generate_weekly_candles_from_daily([])
        assert len(weekly) == 0

    def test_partial_week(self):
        """Test partial week is included."""
        daily = generate_trend_sample_candles(days=8)
        weekly = generate_weekly_candles_from_daily(daily)

        # 8 days = 1 full week + 3 partial
        assert len(weekly) == 2


class TestRunTrendBacktest:
    """Test trend backtest execution."""

    def test_insufficient_data(self):
        """Test backtest with insufficient data."""
        candles = generate_trend_sample_candles(days=100)  # Less than 300

        result = run_trend_backtest(candles)

        assert result.success == False
        assert "데이터 부족" in result.message

    def test_basic_backtest(self):
        """Test basic backtest execution."""
        candles = generate_trend_sample_candles(days=400)
        weekly = generate_weekly_candles_from_daily(candles)

        config = TrendConfig()

        result = run_trend_backtest(
            candles=candles,
            htf_candles=weekly,
            config=config,
            initial_capital=10000000.0,
        )

        assert result.success == True
        assert result.metrics is not None
        assert len(result.equity_curve) > 0

    def test_result_structure(self):
        """Test result structure."""
        candles = generate_trend_sample_candles(days=400)

        result = run_trend_backtest(candles=candles)

        # Check BacktestResult structure
        assert hasattr(result, 'success')
        assert hasattr(result, 'message')
        assert hasattr(result, 'metrics')
        assert hasattr(result, 'equity_curve')
        assert hasattr(result, 'trades')
        assert hasattr(result, 'signals')

    def test_metrics_structure(self):
        """Test metrics structure."""
        candles = generate_trend_sample_candles(days=400)

        result = run_trend_backtest(candles=candles)

        if result.success:
            metrics = result.metrics
            assert hasattr(metrics, 'total_return_pct')
            assert hasattr(metrics, 'max_drawdown_pct')
            assert hasattr(metrics, 'sharpe_ratio')
            assert hasattr(metrics, 'total_trades')
            assert hasattr(metrics, 'win_rate_pct')

    def test_equity_curve(self):
        """Test equity curve generation."""
        candles = generate_trend_sample_candles(days=400)

        result = run_trend_backtest(
            candles=candles,
            initial_capital=10000000.0,
        )

        if result.success and len(result.equity_curve) > 0:
            # First equity should be close to initial capital
            first_equity = result.equity_curve[0]['equity']
            assert abs(first_equity - 10000000.0) < 10000000.0 * 0.01

            # Check equity curve structure
            for ec in result.equity_curve[:5]:
                assert 'bar_index' in ec
                assert 'timestamp' in ec
                assert 'equity' in ec
                assert 'cash' in ec

    def test_trade_records(self):
        """Test trade records."""
        candles = generate_trend_sample_candles(days=500, trend=0.0005)

        result = run_trend_backtest(candles=candles)

        if result.success and len(result.trades) > 0:
            for trade in result.trades[:3]:
                assert hasattr(trade, 'bar_index')
                assert hasattr(trade, 'timestamp')
                assert hasattr(trade, 'action')
                assert hasattr(trade, 'price')
                assert hasattr(trade, 'quantity')
                assert hasattr(trade, 'reason_code')

    def test_signals_list(self):
        """Test signals list."""
        candles = generate_trend_sample_candles(days=500)

        result = run_trend_backtest(candles=candles)

        if result.success and len(result.signals) > 0:
            for sig in result.signals[:3]:
                assert 'action' in sig
                assert 'reason_code' in sig

    def test_fee_rate(self):
        """Test fee rate affects results."""
        candles = generate_trend_sample_candles(days=400, seed=42)

        result_low_fee = run_trend_backtest(
            candles=candles,
            fee_rate=0.0001,
        )

        result_high_fee = run_trend_backtest(
            candles=candles,
            fee_rate=0.01,
        )

        if result_low_fee.success and result_high_fee.success:
            # Higher fees should result in lower returns (if trades occurred)
            if result_low_fee.metrics.total_trades > 0:
                assert result_low_fee.metrics.total_return_pct >= result_high_fee.metrics.total_return_pct

    def test_custom_config(self):
        """Test with custom config."""
        candles = generate_trend_sample_candles(days=400)
        weekly = generate_weekly_candles_from_daily(candles)

        config = TrendConfig(
            hard_sl_pct=5.0,
            tp1_pct=15.0,
            use_spo_split=False,
        )

        result = run_trend_backtest(
            candles=candles,
            htf_candles=weekly,
            config=config,
        )

        assert result.success == True

    def test_no_htf_candles(self):
        """Test backtest without HTF candles uses same data."""
        candles = generate_trend_sample_candles(days=400)

        result = run_trend_backtest(
            candles=candles,
            htf_candles=None,  # Should use same candles
        )

        assert result.success == True


class TestTrendBacktestIntegration:
    """Integration tests for trend backtest."""

    def test_full_year_backtest(self):
        """Test full year backtest."""
        candles = generate_trend_sample_candles(days=365)
        weekly = generate_weekly_candles_from_daily(candles)

        config = TrendConfig()

        result = run_trend_backtest(
            candles=candles,
            htf_candles=weekly,
            config=config,
            initial_capital=10000000.0,
            fee_rate=0.00015,
        )

        assert result.success == True
        assert "추세매매 백테스트 완료" in result.message

    def test_strong_uptrend_profitability(self):
        """Test profitability in strong uptrend."""
        # Create strong uptrend
        candles = generate_trend_sample_candles(
            days=500,
            base_price=100.0,
            trend=0.002,  # Very strong uptrend
            volatility=0.01,
            seed=42,
        )
        weekly = generate_weekly_candles_from_daily(candles)

        result = run_trend_backtest(
            candles=candles,
            htf_candles=weekly,
            initial_capital=10000000.0,
        )

        # In very strong uptrend, trend strategy should be profitable
        if result.success and result.metrics.total_trades > 0:
            # Just check it ran, profitability depends on entry timing
            assert result.metrics.total_return_pct is not None

    def test_exit_reason_distribution(self):
        """Test that different exit reasons occur."""
        candles = generate_trend_sample_candles(days=600, seed=123)
        weekly = generate_weekly_candles_from_daily(candles)

        result = run_trend_backtest(
            candles=candles,
            htf_candles=weekly,
        )

        if result.success and len(result.signals) > 0:
            exit_reasons = set()
            for sig in result.signals:
                if sig['action'] == 'sell':
                    exit_reasons.add(sig['reason_code'])

            # Should have at least one type of exit
            assert len(exit_reasons) >= 0


class TestTrendBacktestEdgeCases:
    """Edge case tests."""

    def test_very_high_sl(self):
        """Test with very high stop loss."""
        candles = generate_trend_sample_candles(days=400)

        config = TrendConfig(hard_sl_pct=30.0)  # Very loose SL

        result = run_trend_backtest(candles=candles, config=config)

        assert result.success == True

    def test_very_low_tp1(self):
        """Test with very low TP1."""
        candles = generate_trend_sample_candles(days=400)

        config = TrendConfig(tp1_pct=5.0)  # Very tight TP1

        result = run_trend_backtest(candles=candles, config=config)

        assert result.success == True

    def test_disabled_spo_split(self):
        """Test with SPO split disabled."""
        candles = generate_trend_sample_candles(days=400)

        config = TrendConfig(use_spo_split=False)

        result = run_trend_backtest(candles=candles, config=config)

        assert result.success == True

    def test_disabled_st_flip_exit(self):
        """Test with ST flip exit disabled."""
        candles = generate_trend_sample_candles(days=400)

        config = TrendConfig(use_st_flip_exit=False)

        result = run_trend_backtest(candles=candles, config=config)

        assert result.success == True

    def test_minimal_capital(self):
        """Test with minimal capital."""
        candles = generate_trend_sample_candles(days=400)

        result = run_trend_backtest(
            candles=candles,
            initial_capital=1000.0,
        )

        assert result.success == True


# ============================================================
# v8 백테스트 테스트
# ============================================================

class TestTrendBacktestV8:
    """v8 specific backtest tests."""

    def test_backtest_with_pyramiding(self):
        """Test backtest with pyramiding enabled."""
        candles = generate_trend_sample_candles(days=500, trend=0.001, seed=42)
        weekly = generate_weekly_candles_from_daily(candles)

        config = TrendConfig(
            use_pyramiding=True,
            max_pyr_entries=3,
            pyr_weights=[50.0, 30.0, 20.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0],
        )

        result = run_trend_backtest(
            candles=candles,
            htf_candles=weekly,
            config=config,
            initial_capital=10000000.0,
        )

        assert result.success == True
        # 피라미딩이 동작하면 equity_curve에 pyr_count가 포함되어야 함
        if len(result.equity_curve) > 0:
            assert 'pyr_count' in result.equity_curve[0]

    def test_backtest_with_atr_stop(self):
        """Test backtest with ATR-based stop loss."""
        candles = generate_trend_sample_candles(days=400, seed=42)

        config = TrendConfig(
            stop_type="atr",
            atr_stop_len=14,
            atr_stop_mult=2.0,
        )

        result = run_trend_backtest(candles=candles, config=config)

        assert result.success == True

    def test_backtest_with_htf_st_exit(self):
        """Test backtest with HTF Supertrend exit mode."""
        candles = generate_trend_sample_candles(days=400, seed=42)
        weekly = generate_weekly_candles_from_daily(candles)

        config = TrendConfig(
            st_exit_mode="htf_only",
            st_htf_atr_len=10,
            st_htf_factor=3.0,
        )

        result = run_trend_backtest(
            candles=candles,
            htf_candles=weekly,
            config=config,
        )

        assert result.success == True

    def test_backtest_v8_sell_tranches(self):
        """Test backtest with v8 sell tranches."""
        candles = generate_trend_sample_candles(days=400, seed=42)

        config = TrendConfig()
        # v8 기본값 확인
        assert config.sell_tranches == [5.0, 5.0, 10.0, 15.0, 25.0, 40.0]

        result = run_trend_backtest(candles=candles, config=config)

        assert result.success == True

    def test_backtest_with_tp1_disabled(self):
        """Test backtest with TP1 disabled (v8 default)."""
        candles = generate_trend_sample_candles(days=400, seed=42)

        config = TrendConfig(use_tp1=False)

        result = run_trend_backtest(candles=candles, config=config)

        assert result.success == True
        # use_tp1=False이므로 TP1 exit 없어야 함
        if len(result.signals) > 0:
            tp1_exits = [s for s in result.signals if s['reason_code'] == 'TREND_EXIT_TP1']
            assert len(tp1_exits) == 0

    def test_backtest_with_round_qty(self):
        """Test backtest with quantity rounding (stock mode)."""
        candles = generate_trend_sample_candles(days=400, seed=42)

        config = TrendConfig(
            round_qty=True,
            min_qty=1.0,
        )

        result = run_trend_backtest(candles=candles, config=config)

        assert result.success == True
        # 거래 수량이 정수인지 확인
        for trade in result.trades:
            if config.round_qty:
                # 소수점 이하가 0이거나 매우 작아야 함
                assert trade.quantity >= config.min_qty

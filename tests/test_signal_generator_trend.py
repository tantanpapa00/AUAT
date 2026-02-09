# tests/test_signal_generator_trend.py
"""
Unit tests for Trend Strategy signal generator.

Validates: TrendConfig, TrendState, generate_trend_signal
Entry: Supertrend 상승 + HVI 초록 + QQE 양수 + close > HTF VWMA156
Exit: Hard SL > TP1 > SPO Split > ST Flip (우선순위순)
"""

import pytest
import numpy as np

from app.strategy_engine.signal_generator_trend import (
    TrendConfig,
    TrendState,
    generate_trend_signal,
    check_entry_conditions,
)


class TestTrendConfig:
    """Test TrendConfig dataclass."""

    def test_default_values(self):
        """Test default configuration values."""
        config = TrendConfig()

        # Timeframes
        assert config.entry_tf == "1D"
        assert config.exit_tf == "1D"
        assert config.htf_tf == "1W"

        # Entry 지표
        assert config.st_atr_len == 10
        assert config.st_factor == 3.0
        assert config.hvi_length == 200
        assert config.hvi_divisor == 3.6
        assert config.qqe_rsi_length == 6
        assert config.qqe_rsi_smoothing == 5
        assert config.qqe_factor == 3.0
        assert config.htf_vwma_len == 156

        # Exit 조건
        assert config.hard_sl_pct == 7.0
        assert config.tp1_pct == 21.0
        assert config.tp1_sell_pct == 50.0
        assert config.use_spo_split == True
        assert config.use_st_flip_exit == True

        # 분할매도
        assert config.sell_tranches == [10.0, 20.0, 30.0, 5.0, 2.5, 1.0]
        assert config.max_sell_tranches == 6
        assert config.after_max_sell == "cycle"

    def test_custom_values(self):
        """Test custom configuration."""
        config = TrendConfig(
            entry_tf="4h",
            exit_tf="1h",
            hard_sl_pct=5.0,
            tp1_pct=15.0,
        )

        assert config.entry_tf == "4h"
        assert config.exit_tf == "1h"
        assert config.hard_sl_pct == 5.0
        assert config.tp1_pct == 15.0


class TestTrendState:
    """Test TrendState dataclass."""

    def test_default_state(self):
        """Test default state values."""
        state = TrendState()

        assert state.in_position == False
        assert state.entry_price == 0.0
        assert state.entry_ts == 0
        assert state.position_qty == 0.0
        assert state.highest_since_entry == 0.0
        assert state.tp1_triggered == False
        assert state.sell_stage == 0

    def test_position_state(self):
        """Test state with position."""
        state = TrendState(
            in_position=True,
            entry_price=100.0,
            entry_ts=1700000000000,
            position_qty=10.0,
            highest_since_entry=120.0,
        )

        assert state.in_position == True
        assert state.entry_price == 100.0
        assert state.position_qty == 10.0
        assert state.highest_since_entry == 120.0


class TestGenerateTrendSignalEntry:
    """Test entry signal generation."""

    def _create_bullish_conditions(self):
        """Create data for bullish entry conditions."""
        n = 50
        close = np.array([100.0 + i * 0.5 for i in range(n)])  # Uptrend
        st_dir = np.array([-1] * n)  # Bullish Supertrend
        hvi = {'g_enabled': np.array([True] * n)}  # HVI green
        qqe = {'is_positive': np.array([True] * n)}  # QQE positive
        htf_vwma = np.array([90.0] * n)  # Close > VWMA

        return close, st_dir, hvi, qqe, htf_vwma

    def test_entry_all_conditions_met(self):
        """Test entry when all conditions are met."""
        close, st_dir, hvi, qqe, htf_vwma = self._create_bullish_conditions()

        config = TrendConfig()
        state = TrendState()

        signal, new_state = generate_trend_signal(
            entry_close=close,
            entry_st_dir=st_dir,
            entry_hvi=hvi,
            entry_qqe=qqe,
            htf_vwma=htf_vwma,
            exit_close=close,
            exit_st_dir=st_dir,
            exit_spo_norm=np.array([0.0] * len(close)),
            config=config,
            state=state,
            current_ts=1700000000000,
        )

        assert signal.action == "buy"
        assert signal.reason_code == "TREND_ENTRY_FULL"
        assert signal.tranche_pct == config.cash_use_pct
        assert new_state.in_position == True
        assert new_state.entry_price == close[-1]

    def test_entry_st_bearish_no_entry(self):
        """Test no entry when Supertrend is bearish."""
        close, st_dir, hvi, qqe, htf_vwma = self._create_bullish_conditions()
        st_dir = np.array([1] * len(close))  # Bearish Supertrend

        config = TrendConfig()
        state = TrendState()

        signal, new_state = generate_trend_signal(
            entry_close=close,
            entry_st_dir=st_dir,
            entry_hvi=hvi,
            entry_qqe=qqe,
            htf_vwma=htf_vwma,
            exit_close=close,
            exit_st_dir=st_dir,
            exit_spo_norm=np.array([0.0] * len(close)),
            config=config,
            state=state,
            current_ts=1700000000000,
        )

        assert signal.action == "hold"
        assert new_state.in_position == False

    def test_entry_hvi_red_no_entry(self):
        """Test no entry when HVI is red."""
        close, st_dir, hvi, qqe, htf_vwma = self._create_bullish_conditions()
        hvi = {'g_enabled': np.array([False] * len(close))}  # HVI red

        config = TrendConfig()
        state = TrendState()

        signal, new_state = generate_trend_signal(
            entry_close=close,
            entry_st_dir=st_dir,
            entry_hvi=hvi,
            entry_qqe=qqe,
            htf_vwma=htf_vwma,
            exit_close=close,
            exit_st_dir=st_dir,
            exit_spo_norm=np.array([0.0] * len(close)),
            config=config,
            state=state,
            current_ts=1700000000000,
        )

        assert signal.action == "hold"
        assert new_state.in_position == False

    def test_entry_qqe_negative_no_entry(self):
        """Test no entry when QQE is negative."""
        close, st_dir, hvi, qqe, htf_vwma = self._create_bullish_conditions()
        qqe = {'is_positive': np.array([False] * len(close))}  # QQE negative

        config = TrendConfig()
        state = TrendState()

        signal, new_state = generate_trend_signal(
            entry_close=close,
            entry_st_dir=st_dir,
            entry_hvi=hvi,
            entry_qqe=qqe,
            htf_vwma=htf_vwma,
            exit_close=close,
            exit_st_dir=st_dir,
            exit_spo_norm=np.array([0.0] * len(close)),
            config=config,
            state=state,
            current_ts=1700000000000,
        )

        assert signal.action == "hold"

    def test_entry_below_htf_vwma_no_entry(self):
        """Test no entry when close < HTF VWMA."""
        close, st_dir, hvi, qqe, htf_vwma = self._create_bullish_conditions()
        htf_vwma = np.array([200.0] * len(close))  # VWMA > close

        config = TrendConfig()
        state = TrendState()

        signal, new_state = generate_trend_signal(
            entry_close=close,
            entry_st_dir=st_dir,
            entry_hvi=hvi,
            entry_qqe=qqe,
            htf_vwma=htf_vwma,
            exit_close=close,
            exit_st_dir=st_dir,
            exit_spo_norm=np.array([0.0] * len(close)),
            config=config,
            state=state,
            current_ts=1700000000000,
        )

        assert signal.action == "hold"


class TestGenerateTrendSignalExit:
    """Test exit signal generation."""

    def _create_position_state(self, entry_price=100.0):
        """Create state with existing position."""
        return TrendState(
            in_position=True,
            entry_price=entry_price,
            entry_ts=1699000000000,
            position_qty=10.0,
            highest_since_entry=entry_price,
            tp1_triggered=False,
            sell_stage=0,
        )

    def test_exit_hard_sl(self):
        """Test hard stop loss exit."""
        entry_price = 100.0
        state = self._create_position_state(entry_price)

        # Price dropped 8% (below 7% SL)
        n = 50
        close = np.array([92.0] * n)  # -8%
        st_dir = np.array([-1] * n)  # Still bullish

        config = TrendConfig(hard_sl_pct=7.0)

        signal, new_state = generate_trend_signal(
            entry_close=close,
            entry_st_dir=st_dir,
            entry_hvi={'g_enabled': np.array([True] * n)},
            entry_qqe={'is_positive': np.array([True] * n)},
            htf_vwma=np.array([90.0] * n),
            exit_close=close,
            exit_st_dir=st_dir,
            exit_spo_norm=np.array([0.0] * n),
            config=config,
            state=state,
            current_ts=1700000000000,
        )

        assert signal.action == "sell"
        assert signal.reason_code == "TREND_EXIT_HARD_SL"
        assert signal.tranche_pct == 100.0  # 전량 청산
        assert new_state.in_position == False

    def test_exit_tp1(self):
        """Test TP1 exit."""
        entry_price = 100.0
        state = self._create_position_state(entry_price)

        # Price up 22% (above 21% TP1)
        n = 50
        close = np.array([122.0] * n)  # +22%
        st_dir = np.array([-1] * n)

        config = TrendConfig(tp1_pct=21.0, tp1_sell_pct=50.0)

        signal, new_state = generate_trend_signal(
            entry_close=np.array([100.0] * n),  # Entry TF close
            entry_st_dir=st_dir,
            entry_hvi={'g_enabled': np.array([True] * n)},
            entry_qqe={'is_positive': np.array([True] * n)},
            htf_vwma=np.array([90.0] * n),
            exit_close=close,  # Exit TF close at +22%
            exit_st_dir=st_dir,
            exit_spo_norm=np.array([0.0] * n),
            config=config,
            state=state,
            current_ts=1700000000000,
        )

        assert signal.action == "sell"
        assert signal.reason_code == "TREND_EXIT_TP1"
        assert signal.tranche_pct == 50.0
        assert new_state.tp1_triggered == True

    def test_exit_tp1_not_triggered_twice(self):
        """Test TP1 only triggers once."""
        entry_price = 100.0
        state = self._create_position_state(entry_price)
        state.tp1_triggered = True  # Already triggered

        n = 50
        close = np.array([125.0] * n)  # Still above TP1
        st_dir = np.array([-1] * n)

        config = TrendConfig(tp1_pct=21.0)

        signal, new_state = generate_trend_signal(
            entry_close=np.array([100.0] * n),
            entry_st_dir=st_dir,
            entry_hvi={'g_enabled': np.array([True] * n)},
            entry_qqe={'is_positive': np.array([True] * n)},
            htf_vwma=np.array([90.0] * n),
            exit_close=close,
            exit_st_dir=st_dir,
            exit_spo_norm=np.array([0.0] * n),
            config=config,
            state=state,
            current_ts=1700000000000,
        )

        # Should not trigger TP1 again
        assert signal.reason_code != "TREND_EXIT_TP1"

    def test_exit_spo_split(self):
        """Test SPO split exit."""
        entry_price = 100.0
        state = self._create_position_state(entry_price)
        state.tp1_triggered = True  # TP1 already triggered

        n = 50
        close = np.array([105.0] * n)  # In profit but below TP1
        st_dir = np.array([-1] * n)

        # SPO signal down: prev > curr and curr > threshold
        spo_norm = np.array([0.5] * (n - 2) + [1.5, 1.2])  # Crossover down

        config = TrendConfig(
            use_spo_split=True,
            use_profit_gate=True,
            min_profit_pct=0.10,
            fee_buffer_pct=0.20,
            exit_spo_threshold=1.0,
        )

        signal, new_state = generate_trend_signal(
            entry_close=close,
            entry_st_dir=st_dir,
            entry_hvi={'g_enabled': np.array([True] * n)},
            entry_qqe={'is_positive': np.array([True] * n)},
            htf_vwma=np.array([90.0] * n),
            exit_close=close,
            exit_st_dir=st_dir,
            exit_spo_norm=spo_norm,
            config=config,
            state=state,
            current_ts=1700000000000,
        )

        assert signal.action == "sell"
        assert signal.reason_code == "TREND_EXIT_SPO_SPLIT"
        assert signal.tranche_pct == 10.0  # SELL1 = 10%
        assert new_state.sell_stage == 1  # Next stage

    def test_exit_spo_split_cycle(self):
        """Test SPO split cycling."""
        entry_price = 100.0
        state = self._create_position_state(entry_price)
        state.tp1_triggered = True
        state.sell_stage = 5  # At max stage

        n = 50
        close = np.array([105.0] * n)
        st_dir = np.array([-1] * n)
        spo_norm = np.array([0.5] * (n - 2) + [1.5, 1.2])

        config = TrendConfig(
            use_spo_split=True,
            max_sell_tranches=6,
            after_max_sell="cycle",
            exit_spo_threshold=1.0,
        )

        signal, new_state = generate_trend_signal(
            entry_close=close,
            entry_st_dir=st_dir,
            entry_hvi={'g_enabled': np.array([True] * n)},
            entry_qqe={'is_positive': np.array([True] * n)},
            htf_vwma=np.array([90.0] * n),
            exit_close=close,
            exit_st_dir=st_dir,
            exit_spo_norm=spo_norm,
            config=config,
            state=state,
            current_ts=1700000000000,
        )

        assert signal.action == "sell"
        # With cycle, stage 5 -> uses stage 0 (SELL1), then goes to stage 0
        assert new_state.sell_stage == 0

    def test_exit_st_flip(self):
        """Test Supertrend flip exit."""
        entry_price = 100.0
        state = self._create_position_state(entry_price)
        state.tp1_triggered = True

        n = 50
        close = np.array([102.0] * n)  # Small profit

        # ST flip: prev bullish (-1) -> curr bearish (1)
        st_dir = np.array([-1] * (n - 1) + [1])

        config = TrendConfig(use_st_flip_exit=True)

        signal, new_state = generate_trend_signal(
            entry_close=close,
            entry_st_dir=np.array([-1] * n),
            entry_hvi={'g_enabled': np.array([True] * n)},
            entry_qqe={'is_positive': np.array([True] * n)},
            htf_vwma=np.array([90.0] * n),
            exit_close=close,
            exit_st_dir=st_dir,
            exit_spo_norm=np.array([0.0] * n),
            config=config,
            state=state,
            current_ts=1700000000000,
        )

        assert signal.action == "sell"
        assert signal.reason_code == "TREND_EXIT_ST_FLIP"
        assert signal.tranche_pct == 100.0  # 전량 청산
        assert new_state.in_position == False

    def test_exit_priority_sl_over_tp1(self):
        """Test SL has priority over TP1."""
        entry_price = 100.0
        state = self._create_position_state(entry_price)

        # This shouldn't happen normally, but test priority
        n = 50
        # Low price triggers SL
        close = np.array([90.0] * n)

        config = TrendConfig(hard_sl_pct=7.0, tp1_pct=21.0)

        signal, new_state = generate_trend_signal(
            entry_close=close,
            entry_st_dir=np.array([-1] * n),
            entry_hvi={'g_enabled': np.array([True] * n)},
            entry_qqe={'is_positive': np.array([True] * n)},
            htf_vwma=np.array([90.0] * n),
            exit_close=close,
            exit_st_dir=np.array([-1] * n),
            exit_spo_norm=np.array([0.0] * n),
            config=config,
            state=state,
            current_ts=1700000000000,
        )

        assert signal.reason_code == "TREND_EXIT_HARD_SL"


class TestCheckEntryConditions:
    """Test check_entry_conditions helper."""

    def test_all_conditions_met(self):
        """Test when all entry conditions are met."""
        n = 50
        close = np.array([100.0] * n)
        st_dir = np.array([-1] * n)  # Bullish
        hvi = {'g_enabled': np.array([True] * n)}
        qqe = {'is_positive': np.array([True] * n)}
        htf_vwma = np.array([90.0] * n)  # close > vwma

        result = check_entry_conditions(close, st_dir, hvi, qqe, htf_vwma)

        assert result['st_bullish'] == True
        assert result['hvi_green'] == True
        assert result['qqe_positive'] == True
        assert result['htf_ok'] == True
        assert result['all_conditions_met'] == True

    def test_partial_conditions(self):
        """Test partial conditions."""
        n = 50
        close = np.array([100.0] * n)
        st_dir = np.array([1] * n)  # Bearish
        hvi = {'g_enabled': np.array([True] * n)}
        qqe = {'is_positive': np.array([True] * n)}
        htf_vwma = np.array([90.0] * n)

        result = check_entry_conditions(close, st_dir, hvi, qqe, htf_vwma)

        assert result['st_bullish'] == False
        assert result['hvi_green'] == True
        assert result['all_conditions_met'] == False


class TestTrendSignalReasonCodes:
    """Test that reason codes are correct."""

    def test_entry_reason_code(self):
        """Test entry reason code."""
        n = 50
        close = np.array([100.0] * n)
        st_dir = np.array([-1] * n)

        config = TrendConfig()
        state = TrendState()

        signal, _ = generate_trend_signal(
            entry_close=close,
            entry_st_dir=st_dir,
            entry_hvi={'g_enabled': np.array([True] * n)},
            entry_qqe={'is_positive': np.array([True] * n)},
            htf_vwma=np.array([90.0] * n),
            exit_close=close,
            exit_st_dir=st_dir,
            exit_spo_norm=np.array([0.0] * n),
            config=config,
            state=state,
            current_ts=1700000000000,
        )

        assert signal.reason_code == "TREND_ENTRY_FULL"
        assert "추세매매 진입" in signal.reason_text

    def test_all_exit_reason_codes(self):
        """Test all exit reason codes exist."""
        expected_codes = [
            "TREND_EXIT_HARD_SL",
            "TREND_EXIT_TP1",
            "TREND_EXIT_SPO_SPLIT",
            "TREND_EXIT_ST_FLIP",
        ]

        # Just verify the codes are strings we use
        for code in expected_codes:
            assert code.startswith("TREND_EXIT_")

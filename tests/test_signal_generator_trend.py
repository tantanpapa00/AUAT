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

        # Entry 지표 (v8 파인스크립트: stAtrLen=10, stFactor=3.0)
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

        # 분할매도 (v8: 역피라미드 [5,5,10,15,25,40])
        assert config.sell_tranches == [5.0, 5.0, 10.0, 15.0, 25.0, 40.0]
        assert config.max_sell_tranches == 6
        assert config.after_max_sell == "cycle"

        # v8 신규 필드 기본값 확인
        assert config.use_pyramiding == True
        assert config.max_pyr_entries == 4
        assert config.stop_type == "fixed"
        assert config.st_exit_mode == "current_tf"
        assert config.use_tp1 == False  # v8에서 기본 OFF
        assert config.st_invert == False
        assert config.use_htf_filter == True
        assert config.enter_only_on_setup_start == True

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
        # v8: 1차 진입 비중 = cash_use_pct * pyr_weights[0]/100 = 100 * 40/100 = 40
        expected_pct = config.cash_use_pct * (config.pyr_weights[0] / 100.0)
        assert signal.tranche_pct == expected_pct
        assert new_state.in_position == True
        assert new_state.entry_price == close[-1]
        assert new_state.pyr_count == 1  # v8: 1차 진입

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
            # v8 필드
            pyr_count=1,
            avg_entry_price=entry_price,
            total_cost=entry_price * 10.0,
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

        config = TrendConfig(tp1_pct=21.0, tp1_sell_pct=50.0, use_tp1=True)  # v8: use_tp1 활성화

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

        config = TrendConfig(tp1_pct=21.0, use_tp1=True)  # v8: use_tp1 활성화

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
        assert signal.tranche_pct == 5.0  # SELL1 = 5% (v8 역피라미드)
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
            # v8 추가
            "TREND_EXIT_ATR_SL",
            "TREND_EXIT_HTF_ST_FLIP",
        ]

        # Just verify the codes are strings we use
        for code in expected_codes:
            assert code.startswith("TREND_EXIT_")


# ============================================================
# v8 테스트
# ============================================================

class TestTrendV8Pyramiding:
    """Test v8 pyramiding (추가매수) functionality."""

    def _create_position_state(self, entry_price=100.0, pyr_count=1):
        """Create state with existing position."""
        return TrendState(
            in_position=True,
            entry_price=entry_price,
            entry_ts=1699000000000,
            position_qty=10.0,
            highest_since_entry=entry_price,
            tp1_triggered=False,
            sell_stage=0,
            pyr_count=pyr_count,
            avg_entry_price=entry_price,
            total_cost=entry_price * 10.0,
            last_pyr_bar=0,
        )

    def test_pyramiding_entry(self):
        """Test pyramiding additional entry on breakout."""
        entry_price = 100.0
        state = self._create_position_state(entry_price, pyr_count=1)
        state.last_pyr_bar = 0  # 피라미딩 가능하도록 쿨다운 충분

        n = 100
        # 신고가 돌파 조건: close > max(high[-pyr_high_len:-1])
        highs = np.array([100.0] * (n - 10) + [105.0] * 10)  # 마지막 10봉만 105
        close = np.array([100.0] * (n - 1) + [110.0])  # 마지막 봉 110 (신고가 돌파)
        st_dir = np.array([-1] * n)

        config = TrendConfig(
            use_pyramiding=True,
            max_pyr_entries=4,
            pyr_high_len=60,
            pyr_cooldown=5,
        )

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
            entry_high=highs,
            bar_index=100,  # 쿨다운 충족 (100 - 0 >= 5)
        )

        assert signal.action == "buy"
        assert signal.reason_code == "TREND_ENTRY_PYR"
        assert new_state.pyr_count == 2

    def test_pyramiding_cooldown(self):
        """Test pyramiding cooldown prevents entry."""
        entry_price = 100.0
        state = self._create_position_state(entry_price, pyr_count=1)
        state.last_pyr_bar = 98  # 최근에 진입

        n = 100
        highs = np.array([100.0] * n)
        close = np.array([100.0] * (n - 1) + [110.0])
        st_dir = np.array([-1] * n)

        config = TrendConfig(
            use_pyramiding=True,
            max_pyr_entries=4,
            pyr_high_len=60,
            pyr_cooldown=5,
        )

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
            entry_high=highs,
            bar_index=100,  # 100 - 98 = 2 < 5 (쿨다운 미충족)
        )

        # 쿨다운 미충족으로 피라미딩 안됨
        assert signal.action == "hold"

    def test_pyramiding_max_entries(self):
        """Test pyramiding stops at max entries."""
        entry_price = 100.0
        state = self._create_position_state(entry_price, pyr_count=4)  # 이미 최대
        state.last_pyr_bar = 0

        n = 100
        highs = np.array([100.0] * n)
        close = np.array([100.0] * (n - 1) + [110.0])
        st_dir = np.array([-1] * n)

        config = TrendConfig(
            use_pyramiding=True,
            max_pyr_entries=4,  # 최대 4회
            pyr_high_len=60,
            pyr_cooldown=5,
        )

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
            entry_high=highs,
            bar_index=100,
        )

        # 최대 횟수 도달로 피라미딩 안됨
        assert signal.action == "hold"
        assert new_state.pyr_count == 4

    def test_pyramiding_weights(self):
        """Test pyramiding weight calculation."""
        n = 50
        close = np.array([100.0] * n)
        st_dir = np.array([-1] * n)

        config = TrendConfig(
            use_pyramiding=True,
            pyr_weights=[50.0, 30.0, 20.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0],
            cash_use_pct=100.0,
        )
        state = TrendState()

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

        assert signal.action == "buy"
        # 1차 진입: cash_use_pct * pyr_weights[0]/100 = 100 * 50/100 = 50
        assert signal.tranche_pct == 50.0


class TestTrendV8StopType:
    """Test v8 stop loss types."""

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
            pyr_count=1,
            avg_entry_price=entry_price,
            total_cost=entry_price * 10.0,
        )

    def test_atr_stop_loss(self):
        """Test ATR-based stop loss."""
        entry_price = 100.0
        state = self._create_position_state(entry_price)

        n = 50
        # ATR = 5라고 가정, atr_stop_mult = 2.0
        # SL = 100 - (5 * 2) = 90
        atr = np.array([5.0] * n)
        close = np.array([88.0] * n)  # ATR SL(90) 이하
        st_dir = np.array([-1] * n)

        config = TrendConfig(
            stop_type="atr",
            atr_stop_len=14,
            atr_stop_mult=2.0,
        )

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
            entry_atr=atr,
        )

        assert signal.action == "sell"
        assert signal.reason_code == "TREND_EXIT_ATR_SL"
        assert new_state.in_position == False

    def test_fixed_stop_loss(self):
        """Test fixed % stop loss (unchanged from v7)."""
        entry_price = 100.0
        state = self._create_position_state(entry_price)

        n = 50
        close = np.array([92.0] * n)  # -8% (7% SL 이하)
        st_dir = np.array([-1] * n)

        config = TrendConfig(
            stop_type="fixed",
            hard_sl_pct=7.0,
        )

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


class TestTrendV8StExitMode:
    """Test v8 ST Exit Mode (4가지 모드)."""

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
            pyr_count=1,
            avg_entry_price=entry_price,
        )

    def test_st_exit_current_tf(self):
        """Test current TF ST exit mode."""
        entry_price = 100.0
        state = self._create_position_state(entry_price)

        n = 50
        close = np.array([102.0] * n)
        # Current TF ST flip
        exit_st_dir = np.array([-1] * (n - 1) + [1])
        # HTF ST no flip
        htf_st_dir = np.array([-1] * n)

        config = TrendConfig(st_exit_mode="current_tf", use_st_flip_exit=True)

        signal, new_state = generate_trend_signal(
            entry_close=close,
            entry_st_dir=np.array([-1] * n),
            entry_hvi={'g_enabled': np.array([True] * n)},
            entry_qqe={'is_positive': np.array([True] * n)},
            htf_vwma=np.array([90.0] * n),
            exit_close=close,
            exit_st_dir=exit_st_dir,
            exit_spo_norm=np.array([0.0] * n),
            config=config,
            state=state,
            current_ts=1700000000000,
            htf_st_dir=htf_st_dir,
        )

        assert signal.action == "sell"
        assert signal.reason_code == "TREND_EXIT_ST_FLIP"

    def test_st_exit_htf_only(self):
        """Test HTF only ST exit mode."""
        entry_price = 100.0
        state = self._create_position_state(entry_price)

        n = 50
        close = np.array([102.0] * n)
        # Current TF no flip
        exit_st_dir = np.array([-1] * n)
        # HTF ST flip
        htf_st_dir = np.array([-1] * (n - 1) + [1])

        config = TrendConfig(st_exit_mode="htf_only", use_st_flip_exit=True)

        signal, new_state = generate_trend_signal(
            entry_close=close,
            entry_st_dir=np.array([-1] * n),
            entry_hvi={'g_enabled': np.array([True] * n)},
            entry_qqe={'is_positive': np.array([True] * n)},
            htf_vwma=np.array([90.0] * n),
            exit_close=close,
            exit_st_dir=exit_st_dir,
            exit_spo_norm=np.array([0.0] * n),
            config=config,
            state=state,
            current_ts=1700000000000,
            htf_st_dir=htf_st_dir,
        )

        assert signal.action == "sell"
        assert signal.reason_code == "TREND_EXIT_HTF_ST_FLIP"

    def test_st_exit_both(self):
        """Test Both ST exit mode (any flip triggers)."""
        entry_price = 100.0
        state = self._create_position_state(entry_price)

        n = 50
        close = np.array([102.0] * n)
        # Current TF flip
        exit_st_dir = np.array([-1] * (n - 1) + [1])
        # HTF no flip
        htf_st_dir = np.array([-1] * n)

        config = TrendConfig(st_exit_mode="both", use_st_flip_exit=True)

        signal, new_state = generate_trend_signal(
            entry_close=close,
            entry_st_dir=np.array([-1] * n),
            entry_hvi={'g_enabled': np.array([True] * n)},
            entry_qqe={'is_positive': np.array([True] * n)},
            htf_vwma=np.array([90.0] * n),
            exit_close=close,
            exit_st_dir=exit_st_dir,
            exit_spo_norm=np.array([0.0] * n),
            config=config,
            state=state,
            current_ts=1700000000000,
            htf_st_dir=htf_st_dir,
        )

        assert signal.action == "sell"
        assert signal.reason_code == "TREND_EXIT_ST_FLIP"

    def test_st_exit_none(self):
        """Test None ST exit mode (no ST exit)."""
        entry_price = 100.0
        state = self._create_position_state(entry_price)

        n = 50
        close = np.array([102.0] * n)
        # ST flip 발생
        exit_st_dir = np.array([-1] * (n - 1) + [1])

        config = TrendConfig(st_exit_mode="none", use_st_flip_exit=True)

        signal, new_state = generate_trend_signal(
            entry_close=close,
            entry_st_dir=np.array([-1] * n),
            entry_hvi={'g_enabled': np.array([True] * n)},
            entry_qqe={'is_positive': np.array([True] * n)},
            htf_vwma=np.array([90.0] * n),
            exit_close=close,
            exit_st_dir=exit_st_dir,
            exit_spo_norm=np.array([0.0] * n),
            config=config,
            state=state,
            current_ts=1700000000000,
        )

        # st_exit_mode="none"이므로 ST exit 안함
        assert signal.action == "hold"


class TestTrendV8Toggles:
    """Test v8 toggle options (TP1, SPO, HTF filter, ST invert)."""

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
            pyr_count=1,
            avg_entry_price=entry_price,
        )

    def test_tp1_disabled(self):
        """Test TP1 disabled skips TP1 exit."""
        entry_price = 100.0
        state = self._create_position_state(entry_price)

        n = 50
        close = np.array([125.0] * n)  # +25% (TP1 21% 이상)
        st_dir = np.array([-1] * n)

        config = TrendConfig(use_tp1=False, tp1_pct=21.0)

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

        # use_tp1=False이므로 TP1 스킵
        assert signal.reason_code != "TREND_EXIT_TP1"

    def test_spo_disabled(self):
        """Test SPO disabled skips SPO split."""
        entry_price = 100.0
        state = self._create_position_state(entry_price)
        state.tp1_triggered = True

        n = 50
        close = np.array([105.0] * n)
        st_dir = np.array([-1] * n)
        spo_norm = np.array([0.5] * (n - 2) + [1.5, 1.2])  # SPO signal

        config = TrendConfig(use_spo_split=False)

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

        # use_spo_split=False이므로 SPO 분할매도 스킵
        assert signal.reason_code != "TREND_EXIT_SPO_SPLIT"

    def test_htf_filter_disabled(self):
        """Test HTF filter disabled allows entry below VWMA."""
        n = 50
        close = np.array([80.0] * n)  # close < HTF VWMA
        st_dir = np.array([-1] * n)
        htf_vwma = np.array([100.0] * n)  # VWMA > close

        config = TrendConfig(use_htf_filter=False)
        state = TrendState()

        signal, new_state = generate_trend_signal(
            entry_close=close,
            entry_st_dir=st_dir,
            entry_hvi={'g_enabled': np.array([True] * n)},
            entry_qqe={'is_positive': np.array([True] * n)},
            htf_vwma=htf_vwma,
            exit_close=close,
            exit_st_dir=st_dir,
            exit_spo_norm=np.array([0.0] * n),
            config=config,
            state=state,
            current_ts=1700000000000,
        )

        # use_htf_filter=False이므로 VWMA 조건 스킵, 진입 허용
        assert signal.action == "buy"

    def test_st_invert(self):
        """Test ST invert reverses direction."""
        n = 50
        close = np.array([100.0] * n)
        st_dir = np.array([1] * n)  # Bearish (normally no entry)

        config = TrendConfig(st_invert=True)  # 반전: bearish -> bullish
        state = TrendState()

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

        # st_invert=True이면 dir=1도 bullish로 처리
        assert signal.action == "buy"

    def test_sell_tranches_v8(self):
        """Test v8 sell tranches default values."""
        config = TrendConfig()
        assert config.sell_tranches == [5.0, 5.0, 10.0, 15.0, 25.0, 40.0]


class TestTrendV8EntryGuard:
    """Test v8 entry guard (셋업 시작봉)."""

    def test_entry_guard_setup_start(self):
        """Test entry only on setup start bar."""
        n = 50
        close = np.array([100.0] * n)
        st_dir = np.array([-1] * n)

        config = TrendConfig(enter_only_on_setup_start=True)
        state = TrendState(prev_setup_met=True)  # 이전에 셋업 충족

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
            bar_index=100,
        )

        # 이전 봉에서도 셋업 충족이었으므로 진입 안함
        assert signal.action == "hold"

    def test_entry_guard_new_setup(self):
        """Test entry allowed on new setup."""
        n = 50
        close = np.array([100.0] * n)
        st_dir = np.array([-1] * n)

        config = TrendConfig(enter_only_on_setup_start=True)
        state = TrendState(prev_setup_met=False)  # 이전 봉에서 셋업 미충족

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
            bar_index=100,
        )

        # 새로운 셋업 시작이므로 진입 허용
        assert signal.action == "buy"
        assert new_state.setup_start_bar == 100

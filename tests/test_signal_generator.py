# tests/test_signal_generator.py
"""
Unit tests for Signal Generator.

Tests the Mean Reversion signal generation logic
matching PineScript: 역추세매매 현물 v0.4

Test cases:
1. OSC buy signal (sig_up_raw)
2. OSC sell signal (sig_dn_raw)
3. R1 pullback trigger
4. R3 breakout trigger
5. Regime-specific filters
6. Profit gate for sells
7. Tranche calculations
"""

import pytest
import numpy as np
from datetime import datetime

from app.strategy_engine.models import (
    OscillatorData,
    HTFIndicators,
    StrategyState,
    MRConfig,
    SignalResult,
)
from app.strategy_engine.signal_generator import (
    calc_osc_data,
    check_buy_filters,
    check_sell_profit_gate,
    get_buy_tranche_pct,
    get_sell_tranche_pct,
    generate_mr_signal,
    update_state_after_execution,
)
from app.strategy_engine.regime_detector import detect_regime, calc_htf_indicators
from app.strategy_engine.presets import OSC_PRESETS


class TestOscillatorData:
    """Test oscillator data calculation."""

    def test_calc_osc_data_basic(self):
        """Test basic oscillator calculation."""
        np.random.seed(42)
        # Need enough data for BB calculation (bb_len=250 + warmup)
        close = 100 + np.cumsum(np.random.randn(350) * 0.5)

        osc_data = calc_osc_data(close, preset="preset1")

        # Should return valid OscillatorData
        assert isinstance(osc_data, OscillatorData)
        assert osc_data.threshold == 1.0  # preset1 default
        # After sufficient warmup, bands should be valid
        # Note: upper_band may equal lower_band if stdev is 0, but generally different
        assert osc_data.upper_band >= osc_data.lower_band

    def test_calc_osc_data_preset2(self):
        """Test oscillator with preset2 (more sensitive)."""
        np.random.seed(42)
        close = 100 + np.cumsum(np.random.randn(300) * 0.5)

        osc_data = calc_osc_data(close, preset="preset2")

        assert osc_data.threshold == 0.7  # preset2 threshold

    def test_sig_up_raw_detection(self):
        """Test buy signal raw detection."""
        # Create data that should trigger sig_up_raw
        # normalized_osc < -threshold AND crossover
        n = 100
        # Create descending then ascending oscillator
        close = np.zeros(n)
        close[:50] = np.linspace(100, 90, 50)  # Descending
        close[50:] = np.linspace(90, 100, 50)  # Ascending

        osc_data = calc_osc_data(close, preset="preset1")

        # Signal detection depends on actual oscillator values
        # Just verify the calculation runs
        assert isinstance(osc_data.sig_up_raw, bool)
        assert isinstance(osc_data.sig_dn_raw, bool)


class TestBuyFilters:
    """Test buy filter logic."""

    def test_lower_band_filter(self):
        """Test lower band filter."""
        osc_data = OscillatorData(
            normalized_osc=-0.5,  # Above lower band
            upper_band=1.5,
            lower_band=-1.5,
            basis=0.0,
            threshold=1.0,
            line_short=100.0,
            line_long=100.0,
            oscillator_raw=0.0,
        )

        state = StrategyState()
        config = MRConfig(use_lower_band_buy=True, lower_band_buffer=0.0)

        # normalized_osc (-0.5) > lower_band (-1.5) -> should fail
        passed, reason = check_buy_filters(
            close_price=100.0,
            osc_data=osc_data,
            state=state,
            config=config,
            regime=1,
            has_position=False,
            avg_price=None,
        )

        assert passed == False
        assert "하단밴드" in reason

    def test_lower_band_filter_pass(self):
        """Test lower band filter passes when below."""
        osc_data = OscillatorData(
            normalized_osc=-2.0,  # Below lower band
            upper_band=1.5,
            lower_band=-1.5,
            basis=0.0,
            threshold=1.0,
            line_short=100.0,
            line_long=100.0,
            oscillator_raw=0.0,
        )

        state = StrategyState()
        config = MRConfig(use_lower_band_buy=True, lower_band_buffer=0.0)

        passed, reason = check_buy_filters(
            close_price=100.0,
            osc_data=osc_data,
            state=state,
            config=config,
            regime=1,
            has_position=False,
            avg_price=None,
        )

        assert passed == True

    def test_below_avg_filter(self):
        """Test below average price filter."""
        osc_data = OscillatorData(
            normalized_osc=-2.0,
            upper_band=1.5,
            lower_band=-1.5,
            basis=0.0,
            threshold=1.0,
            line_short=100.0,
            line_long=100.0,
            oscillator_raw=0.0,
        )

        state = StrategyState()
        config = MRConfig(
            use_lower_band_buy=False,
            r1_filt_below_avg=True,
        )

        # Price 105 > avg 100 -> should fail
        passed, reason = check_buy_filters(
            close_price=105.0,
            osc_data=osc_data,
            state=state,
            config=config,
            regime=1,
            has_position=True,
            avg_price=100.0,
        )

        assert passed == False
        assert "평단가" in reason

    def test_prev_exec_filter(self):
        """Test previous execution price filter."""
        osc_data = OscillatorData(
            normalized_osc=-2.0,
            upper_band=1.5,
            lower_band=-1.5,
            basis=0.0,
            threshold=1.0,
            line_short=100.0,
            line_long=100.0,
            oscillator_raw=0.0,
        )

        state = StrategyState(last_buy_exec_price=100.0)
        config = MRConfig(
            use_lower_band_buy=False,
            r1_filt_below_avg=False,
            r1_filt_prev_exec=True,
        )

        # Price 100 >= last_exec 100 -> should fail
        passed, reason = check_buy_filters(
            close_price=100.0,
            osc_data=osc_data,
            state=state,
            config=config,
            regime=1,
            has_position=True,
            avg_price=100.0,
        )

        assert passed == False
        assert "직전체결가" in reason


class TestProfitGate:
    """Test sell profit gate logic."""

    def test_profit_gate_pass(self):
        """Test profit gate passes when profitable."""
        # close >= avg * (1 + (min_profit + fee_buffer) / 100)
        # 101 >= 100 * (1 + (0.1 + 0.2) / 100) = 100 * 1.003 = 100.3
        result = check_sell_profit_gate(
            close_price=101.0,
            avg_price=100.0,
            min_profit_pct=0.1,
            fee_buffer_pct=0.2,
        )
        assert result == True

    def test_profit_gate_fail(self):
        """Test profit gate fails when not profitable enough."""
        # 100.2 < 100 * 1.003 = 100.3
        result = check_sell_profit_gate(
            close_price=100.2,
            avg_price=100.0,
            min_profit_pct=0.1,
            fee_buffer_pct=0.2,
        )
        assert result == False

    def test_profit_gate_exact(self):
        """Test profit gate at exact threshold."""
        # Exactly at threshold
        avg_price = 100.0
        min_profit = 0.1
        fee_buffer = 0.2
        threshold = avg_price * (1 + (min_profit + fee_buffer) / 100)

        result = check_sell_profit_gate(
            close_price=threshold,
            avg_price=avg_price,
            min_profit_pct=min_profit,
            fee_buffer_pct=fee_buffer,
        )
        assert result == True


class TestTrancheCalculations:
    """Test buy/sell tranche percentage calculations."""

    def test_buy_tranche_stage_0(self):
        """Test first buy tranche."""
        config = MRConfig(
            buy_tranches=[5.0, 5.0, 5.0, 5.0, 5.0, 5.0, 5.0, 5.0, 5.0, 5.0],
            r1_buy_mult=1.0,
        )

        pct = get_buy_tranche_pct(stage=0, config=config, regime=1, trigger_type="osc")
        assert pct == 5.0  # 5.0 * 1.0

    def test_buy_tranche_with_multiplier(self):
        """Test buy tranche with regime multiplier."""
        config = MRConfig(
            buy_tranches=[5.0, 5.0, 5.0, 5.0, 5.0, 5.0, 5.0, 5.0, 5.0, 5.0],
            r4_buy_mult=1.2,  # R4 expands buys
        )

        pct = get_buy_tranche_pct(stage=0, config=config, regime=4, trigger_type="osc")
        assert abs(pct - 6.0) < 0.01  # 5.0 * 1.2

    def test_sell_tranche_stage_0(self):
        """Test first sell tranche."""
        config = MRConfig(
            sell_tranches=[10.0, 20.0, 30.0, 5.0, 2.5, 1.0],
            r1_sell_mult=1.3,
        )

        pct = get_sell_tranche_pct(stage=0, config=config, regime=1)
        assert abs(pct - 13.0) < 0.01  # 10.0 * 1.3

    def test_sell_tranche_capped_at_100(self):
        """Test sell tranche capped at 100%."""
        config = MRConfig(
            sell_tranches=[90.0, 20.0, 30.0, 5.0, 2.5, 1.0],
            r2_sell_mult=1.6,  # R2 expands sells
        )

        pct = get_sell_tranche_pct(stage=0, config=config, regime=2)
        # 90 * 1.6 = 144, but should be capped at 100
        assert pct == 100.0


class TestGenerateMRSignal:
    """Test main signal generation function."""

    def create_test_data(self, n=300):
        """Create test OHLCV data."""
        np.random.seed(42)
        close = 100 + np.cumsum(np.random.randn(n) * 0.5)
        high = close + np.abs(np.random.randn(n))
        low = close - np.abs(np.random.randn(n))
        volume = np.abs(np.random.randn(n) * 1000) + 100
        return high, low, close, volume

    def test_no_signal_without_trigger(self):
        """Test that no signal is generated without OSC trigger."""
        high, low, close, volume = self.create_test_data()

        # Create oscillator data without signals
        osc_data = OscillatorData(
            normalized_osc=0.0,  # Neutral
            upper_band=1.5,
            lower_band=-1.5,
            basis=0.0,
            threshold=1.0,
            line_short=100.0,
            line_long=100.0,
            oscillator_raw=0.0,
            sig_up_raw=False,
            sig_dn_raw=False,
        )

        htf_indicators = HTFIndicators(
            vwma50=100.0,
            vwma200=100.0,
            hull=100.0,
            hull_up=True,
            hull_dn=False,
            tenkan=100.0,
            kijun=100.0,
            senkou_a=100.0,
            senkou_b=100.0,
            cloud_upper=100.0,
            cloud_lower=100.0,
            cloud_bull=True,
            cloud_bear=False,
            st_value=95.0,
            st_direction=1,
            bull_stack=True,
            bear_stack=False,
        )

        state = StrategyState()
        config = MRConfig()

        signal, new_state = generate_mr_signal(
            close=close,
            high=high,
            low=low,
            osc_data=osc_data,
            htf_indicators=htf_indicators,
            regime=1,
            state=state,
            config=config,
            has_position=False,
            position_qty=0.0,
            avg_price=None,
            current_ts=1000000,
        )

        assert signal.action == "none"

    def test_buy_signal_with_osc_trigger(self):
        """Test buy signal generation with OSC trigger."""
        high, low, close, volume = self.create_test_data()

        # Create oscillator data with buy signal
        osc_data = OscillatorData(
            normalized_osc=-2.0,  # Below lower band
            upper_band=1.5,
            lower_band=-1.5,
            basis=0.0,
            threshold=1.0,
            line_short=98.0,
            line_long=100.0,
            oscillator_raw=-2.0,
            sig_up_raw=True,  # Buy signal!
            sig_dn_raw=False,
        )

        htf_indicators = HTFIndicators(
            vwma50=100.0,
            vwma200=100.0,
            hull=100.0,
            hull_up=True,
            hull_dn=False,
            tenkan=100.0,
            kijun=100.0,
            senkou_a=100.0,
            senkou_b=100.0,
            cloud_upper=100.0,
            cloud_lower=100.0,
            cloud_bull=True,
            cloud_bear=False,
            st_value=95.0,
            st_direction=1,
            bull_stack=True,
            bear_stack=False,
        )

        state = StrategyState()
        config = MRConfig(
            use_lower_band_buy=True,
            r1_allow_osc_buy=True,
            r1_buy_mult=1.0,
        )

        signal, new_state = generate_mr_signal(
            close=close,
            high=high,
            low=low,
            osc_data=osc_data,
            htf_indicators=htf_indicators,
            regime=1,
            state=state,
            config=config,
            has_position=False,
            position_qty=0.0,
            avg_price=None,
            current_ts=1000000,
        )

        assert signal.action == "buy"
        assert signal.reason_code == "MR_ENTRY_OSC"
        assert signal.tranche == 1
        assert signal.tranche_pct > 0

    def test_sell_signal_with_profit_gate(self):
        """Test sell signal generation with profit gate check."""
        # Create price data with specific last price for profit calculation
        n = 300
        np.random.seed(42)
        close = np.full(n, 101.0)  # Fixed price for predictable profit gate
        high = np.full(n, 102.0)
        low = np.full(n, 100.0)

        # Create oscillator data with sell signal
        osc_data = OscillatorData(
            normalized_osc=2.0,  # Above upper band
            upper_band=1.5,
            lower_band=-1.5,
            basis=0.0,
            threshold=1.0,
            line_short=102.0,
            line_long=100.0,
            oscillator_raw=2.0,
            sig_up_raw=False,
            sig_dn_raw=True,  # Sell signal!
        )

        htf_indicators = HTFIndicators(
            vwma50=100.0,
            vwma200=100.0,
            hull=100.0,
            hull_up=True,
            hull_dn=False,
            tenkan=100.0,
            kijun=100.0,
            senkou_a=100.0,
            senkou_b=100.0,
            cloud_upper=100.0,
            cloud_lower=100.0,
            cloud_bull=True,
            cloud_bear=False,
            st_value=95.0,
            st_direction=1,
            bull_stack=True,
            bear_stack=False,
        )

        state = StrategyState()
        config = MRConfig(
            min_profit_pct=0.1,
            fee_buffer_pct=0.2,
            r1_sell_mult=1.0,
        )

        # Position with profit: close=101, avg=99
        # Required price = 99 * (1 + 0.3/100) = 99.297, close=101 > 99.297 -> pass
        signal, new_state = generate_mr_signal(
            close=close,
            high=high,
            low=low,
            osc_data=osc_data,
            htf_indicators=htf_indicators,
            regime=1,
            state=state,
            config=config,
            has_position=True,
            position_qty=10.0,
            avg_price=99.0,  # Profitable at close=101
            current_ts=1000000,
        )

        assert signal.action == "sell", f"Expected sell but got {signal.action}, reason: {signal.reason_code}"
        assert signal.reason_code == "MR_EXIT_OSC_SPLIT"

    def test_r2_buy_blocked(self):
        """Test that R2 blocks OSC buys by default."""
        high, low, close, volume = self.create_test_data()

        osc_data = OscillatorData(
            normalized_osc=-2.0,
            upper_band=1.5,
            lower_band=-1.5,
            basis=0.0,
            threshold=1.0,
            line_short=98.0,
            line_long=100.0,
            oscillator_raw=-2.0,
            sig_up_raw=True,
            sig_dn_raw=False,
        )

        htf_indicators = HTFIndicators(
            vwma50=100.0,
            vwma200=100.0,
            hull=100.0,
            hull_up=False,
            hull_dn=True,
            tenkan=100.0,
            kijun=100.0,
            senkou_a=100.0,
            senkou_b=100.0,
            cloud_upper=100.0,
            cloud_lower=100.0,
            cloud_bull=True,
            cloud_bear=False,
            st_value=105.0,
            st_direction=-1,  # ST down
            bull_stack=True,
            bear_stack=False,
        )

        state = StrategyState()
        config = MRConfig(
            r2_allow_osc_buy=False,  # R2 default
            r2_buy_mult=0.0,
        )

        signal, new_state = generate_mr_signal(
            close=close,
            high=high,
            low=low,
            osc_data=osc_data,
            htf_indicators=htf_indicators,
            regime=2,  # R2!
            state=state,
            config=config,
            has_position=False,
            position_qty=0.0,
            avg_price=None,
            current_ts=1000000,
        )

        # R2 should block buy
        assert signal.action == "none"


class TestRegimeTransitions:
    """Test regime transition handling."""

    def test_r1_pullback_arm_on_hull_dn(self):
        """Test R1 pullback arming when Hull starts falling."""
        high, low, close, volume = TestGenerateMRSignal().create_test_data()

        osc_data = OscillatorData(
            normalized_osc=0.0,
            upper_band=1.5,
            lower_band=-1.5,
            basis=0.0,
            threshold=1.0,
            line_short=100.0,
            line_long=100.0,
            oscillator_raw=0.0,
            sig_up_raw=False,
            sig_dn_raw=False,
        )

        # Hull just started falling
        htf_indicators = HTFIndicators(
            vwma50=100.0,
            vwma200=95.0,  # Bull stack
            hull=99.0,
            hull_up=False,
            hull_dn=True,  # Hull falling
            tenkan=100.0,
            kijun=100.0,
            senkou_a=100.0,
            senkou_b=100.0,
            cloud_upper=100.0,
            cloud_lower=100.0,
            cloud_bull=True,
            cloud_bear=False,
            st_value=95.0,
            st_direction=1,  # ST up
            bull_stack=True,
            bear_stack=False,
        )

        state = StrategyState(
            current_regime=1,
            r1_pb_armed=False,
            r1_pb_used=False,
        )

        config = MRConfig(r1_pullback_on=True)

        signal, new_state = generate_mr_signal(
            close=close,
            high=high,
            low=low,
            osc_data=osc_data,
            htf_indicators=htf_indicators,
            regime=1,
            state=state,
            config=config,
            has_position=False,
            position_qty=0.0,
            avg_price=None,
            current_ts=1000000,
        )

        # Pullback should be armed (but not triggered yet, no osc signal)
        assert new_state.r1_pb_armed == True
        assert new_state.r1_pb_used == False

    def test_r3_breakout_reset_on_exit(self):
        """Test R3 breakout state resets when exiting R3."""
        high, low, close, volume = TestGenerateMRSignal().create_test_data()

        osc_data = OscillatorData(
            normalized_osc=0.0,
            upper_band=1.5,
            lower_band=-1.5,
            basis=0.0,
            threshold=1.0,
            line_short=100.0,
            line_long=100.0,
            oscillator_raw=0.0,
            sig_up_raw=False,
            sig_dn_raw=False,
        )

        htf_indicators = HTFIndicators(
            vwma50=95.0,
            vwma200=100.0,  # Bear stack
            hull=100.0,
            hull_up=True,
            hull_dn=False,
            tenkan=100.0,
            kijun=100.0,
            senkou_a=100.0,
            senkou_b=100.0,
            cloud_upper=100.0,
            cloud_lower=100.0,
            cloud_bull=True,
            cloud_bear=False,
            st_value=105.0,
            st_direction=-1,  # ST down -> now R4
            bull_stack=False,
            bear_stack=True,
        )

        # Previous state was R3 with breakout used
        state = StrategyState(
            current_regime=3,  # Was R3
            r3_break_used=True,
        )

        config = MRConfig()

        signal, new_state = generate_mr_signal(
            close=close,
            high=high,
            low=low,
            osc_data=osc_data,
            htf_indicators=htf_indicators,
            regime=4,  # Now R4
            state=state,
            config=config,
            has_position=False,
            position_qty=0.0,
            avg_price=None,
            current_ts=1000000,
        )

        # Breakout used should reset since we left R3
        assert new_state.r3_break_used == False


class TestStateUpdate:
    """Test state update after execution."""

    def test_buy_stage_increment(self):
        """Test buy stage increments after buy execution."""
        state = StrategyState(buy_stage=0, sell_stage=0)
        config = MRConfig(
            max_buy_tranches=10,
            after_max_buy="extend",
            # r1_reset_sell_on_buy defaults to True via getattr
        )

        signal = SignalResult(
            action="buy",
            reason_code="MR_ENTRY_OSC",
            reason_text="Test buy",
            regime=1,
            tranche=1,
            tranche_pct=5.0,
            price_hint=100.0,
            ts=1000000,
        )

        new_state = update_state_after_execution(state, signal, config, executed=True)

        assert new_state.buy_stage == 1
        assert new_state.sell_stage == 0  # Reset after buy
        assert new_state.last_buy_exec_price == 100.0

    def test_sell_stage_increment(self):
        """Test sell stage increments after sell execution."""
        state = StrategyState(buy_stage=5, sell_stage=0)
        config = MRConfig(
            max_sell_tranches=6,
            after_max_sell="cycle",
            # r1_reset_buy_on_sell defaults to True via getattr
        )

        signal = SignalResult(
            action="sell",
            reason_code="MR_EXIT_OSC_SPLIT",
            reason_text="Test sell",
            regime=1,
            tranche=1,
            tranche_pct=10.0,
            price_hint=105.0,
            ts=1000000,
        )

        new_state = update_state_after_execution(state, signal, config, executed=True)

        assert new_state.sell_stage == 1
        assert new_state.buy_stage == 0  # Reset after sell

    def test_buy_stage_cycle(self):
        """Test buy stage cycles after max."""
        state = StrategyState(buy_stage=9)  # Last stage (0-indexed)
        config = MRConfig(
            max_buy_tranches=10,
            after_max_buy="cycle",
        )

        signal = SignalResult(
            action="buy",
            reason_code="MR_ENTRY_OSC",
            reason_text="Test buy",
            regime=1,
            tranche=10,
            tranche_pct=5.0,
            price_hint=100.0,
            ts=1000000,
        )

        new_state = update_state_after_execution(state, signal, config, executed=True)

        # Should cycle back to 0
        assert new_state.buy_stage == 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

# tests/test_position_manager.py
"""
Tests for position_manager.py - Tranche calculations and position tracking.

Phase 2: Position management tests.
"""

import pytest
from app.strategy_engine.models import MRConfig, SignalResult
from app.strategy_engine.position_manager import (
    PositionInfo,
    OrderQuantity,
    calculate_buy_quantity,
    calculate_sell_quantity,
    calculate_position_info,
    update_position_after_fill,
    check_trading_limits,
    get_effective_tranche_stage,
)


class TestPositionInfo:
    """Test PositionInfo dataclass."""

    def test_position_info_has_position_true(self):
        """Test has_position returns True when quantity > 0."""
        position = PositionInfo(
            symbol="BTC-USDT",
            exchange="okx",
            quantity=1.0,
            avg_price=50000.0,
            market_price=51000.0,
            market_value=51000.0,
            unrealized_pnl=1000.0,
            unrealized_pnl_pct=2.0,
        )
        assert position.has_position is True

    def test_position_info_has_position_false(self):
        """Test has_position returns False when quantity is 0."""
        position = PositionInfo(
            symbol="BTC-USDT",
            exchange="okx",
            quantity=0.0,
            avg_price=0.0,
            market_price=50000.0,
            market_value=0.0,
            unrealized_pnl=0.0,
            unrealized_pnl_pct=0.0,
        )
        assert position.has_position is False


class TestCalculateBuyQuantity:
    """Test calculate_buy_quantity function."""

    @pytest.fixture
    def config(self):
        """Create test configuration."""
        return MRConfig(
            signal_tf="15m",
            htf_tf="4h",
            osc_preset="preset1",
            buy_tranches=[25, 50, 75, 100],
            sell_tranches=[50, 100],
            cash_use_pct=90.0,
            hard_cap_pct=95.0,
        )

    def test_buy_quantity_basic(self, config):
        """Test basic buy quantity calculation."""
        signal = SignalResult(
            action="buy",
            reason_code="R1_PULLBACK",
            reason_text="R1 pullback buy",
            regime=1,
            tranche=1,
            tranche_pct=25.0,
        )

        result = calculate_buy_quantity(
            signal=signal,
            config=config,
            available_cash=10000.0,
            current_position_value=0.0,
            equity=10000.0,
            market_price=100.0,
        )

        # 10000 * 0.9 * 0.25 = 2250 notional
        # 2250 / 100 = 22.5 qty
        assert result.qty == pytest.approx(22.5, rel=0.01)
        assert result.notional == pytest.approx(2250.0, rel=0.01)
        assert result.tranche_pct == 25.0
        assert result.tranche_stage == 1

    def test_buy_quantity_second_tranche(self, config):
        """Test second tranche buy quantity."""
        signal = SignalResult(
            action="buy",
            reason_code="R1_PULLBACK",
            reason_text="R1 pullback buy",
            regime=1,
            tranche=2,
            tranche_pct=50.0,
        )

        result = calculate_buy_quantity(
            signal=signal,
            config=config,
            available_cash=7750.0,  # After first buy
            current_position_value=2250.0,
            equity=10000.0,
            market_price=100.0,
        )

        # 7750 * 0.9 * 0.5 = 3487.5 notional
        assert result.qty == pytest.approx(34.875, rel=0.01)
        assert result.tranche_stage == 2

    def test_buy_quantity_respects_hard_cap(self, config):
        """Test buy quantity limited by hard cap."""
        signal = SignalResult(
            action="buy",
            reason_code="R1_PULLBACK",
            reason_text="R1 pullback buy",
            regime=1,
            tranche=4,
            tranche_pct=100.0,
        )

        result = calculate_buy_quantity(
            signal=signal,
            config=config,
            available_cash=1000.0,
            current_position_value=9400.0,  # Near hard cap
            equity=10000.0,
            market_price=100.0,
        )

        # Hard cap = 10000 * 0.95 = 9500
        # Max allowed = 9500 - 9400 = 100 notional
        assert result.notional <= 100.0
        assert "Hard cap" in result.reason or result.qty <= 1.0

    def test_buy_quantity_zero_for_non_buy_action(self, config):
        """Test returns zero for non-buy actions."""
        signal = SignalResult(
            action="sell",
            reason_code="PROFIT_GATE",
            reason_text="Profit gate sell",
            regime=1,
            tranche=1,
            tranche_pct=50.0,
        )

        result = calculate_buy_quantity(
            signal=signal,
            config=config,
            available_cash=10000.0,
            current_position_value=0.0,
            equity=10000.0,
            market_price=100.0,
        )

        assert result.qty == 0.0

    def test_buy_quantity_zero_tranche_pct(self, config):
        """Test returns zero when tranche_pct is 0."""
        signal = SignalResult(
            action="buy",
            reason_code="R1_PULLBACK",
            reason_text="R1 pullback buy",
            regime=1,
            tranche=1,
            tranche_pct=0.0,
        )

        result = calculate_buy_quantity(
            signal=signal,
            config=config,
            available_cash=10000.0,
            current_position_value=0.0,
            equity=10000.0,
            market_price=100.0,
        )

        assert result.qty == 0.0
        assert "Tranche percentage is 0" in result.reason

    def test_buy_quantity_invalid_price(self, config):
        """Test returns zero for invalid market price."""
        signal = SignalResult(
            action="buy",
            reason_code="R1_PULLBACK",
            reason_text="R1 pullback buy",
            regime=1,
            tranche=1,
            tranche_pct=25.0,
        )

        result = calculate_buy_quantity(
            signal=signal,
            config=config,
            available_cash=10000.0,
            current_position_value=0.0,
            equity=10000.0,
            market_price=0.0,
        )

        assert result.qty == 0.0


class TestCalculateSellQuantity:
    """Test calculate_sell_quantity function."""

    @pytest.fixture
    def config(self):
        """Create test configuration."""
        return MRConfig(
            signal_tf="15m",
            htf_tf="4h",
            osc_preset="preset1",
            buy_tranches=[25, 50, 75, 100],
            sell_tranches=[50, 100],
        )

    def test_sell_quantity_basic(self, config):
        """Test basic sell quantity calculation."""
        signal = SignalResult(
            action="sell",
            reason_code="PROFIT_GATE",
            reason_text="Profit gate sell",
            regime=1,
            tranche=1,
            tranche_pct=50.0,
        )

        result = calculate_sell_quantity(
            signal=signal,
            config=config,
            position_qty=10.0,
            market_price=100.0,
        )

        # 10 * 0.5 = 5 qty
        assert result.qty == 5.0
        assert result.notional == 500.0
        assert result.tranche_pct == 50.0

    def test_sell_quantity_full_exit(self, config):
        """Test full position exit."""
        signal = SignalResult(
            action="sell",
            reason_code="PROFIT_GATE",
            reason_text="Profit gate sell",
            regime=1,
            tranche=2,
            tranche_pct=100.0,
        )

        result = calculate_sell_quantity(
            signal=signal,
            config=config,
            position_qty=5.0,
            market_price=100.0,
        )

        assert result.qty == 5.0
        assert result.post_order_exposure == 0.0

    def test_sell_quantity_zero_for_non_sell_action(self, config):
        """Test returns zero for non-sell actions."""
        signal = SignalResult(
            action="buy",
            reason_code="R1_PULLBACK",
            reason_text="R1 pullback buy",
            regime=1,
            tranche=1,
            tranche_pct=25.0,
        )

        result = calculate_sell_quantity(
            signal=signal,
            config=config,
            position_qty=10.0,
            market_price=100.0,
        )

        assert result.qty == 0.0

    def test_sell_quantity_no_position(self, config):
        """Test returns zero when no position."""
        signal = SignalResult(
            action="sell",
            reason_code="PROFIT_GATE",
            reason_text="Profit gate sell",
            regime=1,
            tranche=1,
            tranche_pct=50.0,
        )

        result = calculate_sell_quantity(
            signal=signal,
            config=config,
            position_qty=0.0,
            market_price=100.0,
        )

        assert result.qty == 0.0

    def test_sell_quantity_cannot_exceed_position(self, config):
        """Test sell quantity capped at position size."""
        signal = SignalResult(
            action="sell",
            reason_code="PROFIT_GATE",
            reason_text="Profit gate sell",
            regime=1,
            tranche=1,
            tranche_pct=150.0,  # More than 100%
        )

        result = calculate_sell_quantity(
            signal=signal,
            config=config,
            position_qty=10.0,
            market_price=100.0,
        )

        assert result.qty == 10.0  # Capped at position


class TestCalculatePositionInfo:
    """Test calculate_position_info function."""

    def test_position_info_with_profit(self):
        """Test position info calculation with profit."""
        position = calculate_position_info(
            symbol="BTC-USDT",
            exchange="okx",
            position_qty=1.0,
            avg_price=50000.0,
            market_price=55000.0,
        )

        assert position.quantity == 1.0
        assert position.market_value == 55000.0
        assert position.unrealized_pnl == 5000.0
        assert position.unrealized_pnl_pct == pytest.approx(10.0, rel=0.01)

    def test_position_info_with_loss(self):
        """Test position info calculation with loss."""
        position = calculate_position_info(
            symbol="BTC-USDT",
            exchange="okx",
            position_qty=1.0,
            avg_price=50000.0,
            market_price=45000.0,
        )

        assert position.unrealized_pnl == -5000.0
        assert position.unrealized_pnl_pct == pytest.approx(-10.0, rel=0.01)

    def test_position_info_zero_position(self):
        """Test position info with zero position."""
        position = calculate_position_info(
            symbol="BTC-USDT",
            exchange="okx",
            position_qty=0.0,
            avg_price=0.0,
            market_price=50000.0,
        )

        assert position.quantity == 0.0
        assert position.market_value == 0.0
        assert position.unrealized_pnl == 0.0


class TestUpdatePositionAfterFill:
    """Test update_position_after_fill function."""

    def test_buy_fill_first_position(self):
        """Test buy fill creates new position."""
        position = PositionInfo(
            symbol="BTC-USDT",
            exchange="okx",
            quantity=0.0,
            avg_price=0.0,
            market_price=50000.0,
            market_value=0.0,
            unrealized_pnl=0.0,
            unrealized_pnl_pct=0.0,
        )

        updated = update_position_after_fill(
            position=position,
            side="buy",
            fill_qty=1.0,
            fill_price=50000.0,
        )

        assert updated.quantity == 1.0
        assert updated.avg_price == 50000.0

    def test_buy_fill_adds_to_position(self):
        """Test buy fill adds to existing position with moving average."""
        position = PositionInfo(
            symbol="BTC-USDT",
            exchange="okx",
            quantity=1.0,
            avg_price=50000.0,
            market_price=51000.0,
            market_value=51000.0,
            unrealized_pnl=1000.0,
            unrealized_pnl_pct=2.0,
        )

        updated = update_position_after_fill(
            position=position,
            side="buy",
            fill_qty=1.0,
            fill_price=52000.0,
        )

        assert updated.quantity == 2.0
        # Moving average: (50000 * 1 + 52000 * 1) / 2 = 51000
        assert updated.avg_price == 51000.0

    def test_sell_fill_partial(self):
        """Test partial sell reduces position."""
        position = PositionInfo(
            symbol="BTC-USDT",
            exchange="okx",
            quantity=2.0,
            avg_price=50000.0,
            market_price=55000.0,
            market_value=110000.0,
            unrealized_pnl=10000.0,
            unrealized_pnl_pct=10.0,
        )

        updated = update_position_after_fill(
            position=position,
            side="sell",
            fill_qty=1.0,
            fill_price=55000.0,
        )

        assert updated.quantity == 1.0
        assert updated.avg_price == 50000.0  # Avg price unchanged

    def test_sell_fill_full_exit(self):
        """Test full position exit resets everything."""
        position = PositionInfo(
            symbol="BTC-USDT",
            exchange="okx",
            quantity=1.0,
            avg_price=50000.0,
            market_price=55000.0,
            market_value=55000.0,
            unrealized_pnl=5000.0,
            unrealized_pnl_pct=10.0,
        )

        updated = update_position_after_fill(
            position=position,
            side="sell",
            fill_qty=1.0,
            fill_price=55000.0,
        )

        assert updated.quantity == 0.0
        assert updated.avg_price == 0.0
        assert updated.unrealized_pnl == 0.0


class TestGetEffectiveTrancheStage:
    """Test get_effective_tranche_stage function."""

    def test_normal_stage_progression(self):
        """Test normal stage within range."""
        stage, allowed = get_effective_tranche_stage(
            current_stage=1,
            max_stages=4,
            after_max="extend",
            stage_1_only=False,
        )
        assert stage == 1
        assert allowed is True

    def test_stage_1_only(self):
        """Test stage_1_only always returns 0."""
        stage, allowed = get_effective_tranche_stage(
            current_stage=3,
            max_stages=4,
            after_max="extend",
            stage_1_only=True,
        )
        assert stage == 0
        assert allowed is True

    def test_after_max_extend(self):
        """Test extend behavior after max stages."""
        stage, allowed = get_effective_tranche_stage(
            current_stage=5,
            max_stages=4,
            after_max="extend",
            stage_1_only=False,
        )
        assert stage == 3  # Last stage (0-indexed)
        assert allowed is True

    def test_after_max_cycle(self):
        """Test cycle behavior after max stages."""
        stage, allowed = get_effective_tranche_stage(
            current_stage=4,
            max_stages=4,
            after_max="cycle",
            stage_1_only=False,
        )
        assert stage == 0  # Reset to first
        assert allowed is True

    def test_after_max_stop(self):
        """Test stop behavior after max stages."""
        stage, allowed = get_effective_tranche_stage(
            current_stage=4,
            max_stages=4,
            after_max="stop",
            stage_1_only=False,
        )
        assert stage == 3
        assert allowed is False


class TestOrderQuantityDataclass:
    """Test OrderQuantity dataclass."""

    def test_order_quantity_creation(self):
        """Test OrderQuantity fields."""
        order = OrderQuantity(
            qty=10.0,
            notional=1000.0,
            tranche_pct=25.0,
            tranche_stage=1,
            available_cash=5000.0,
            post_order_exposure=1000.0,
            reason="BUY1: 25% of 90% available",
        )

        assert order.qty == 10.0
        assert order.notional == 1000.0
        assert order.tranche_pct == 25.0
        assert order.tranche_stage == 1


class TestATypeFormula:
    """Test A-type position sizing formula specifically."""

    def test_a_type_formula_calculation(self):
        """Test A-type: available_cash * cash_use_pct * tranche_pct."""
        config = MRConfig(
            signal_tf="15m",
            htf_tf="4h",
            osc_preset="preset1",
            buy_tranches=[25, 50, 75, 100],
            sell_tranches=[50, 100],
            cash_use_pct=90.0,
            hard_cap_pct=95.0,
        )

        signal = SignalResult(
            action="buy",
            reason_code="R1_PULLBACK",
            reason_text="Test",
            regime=1,
            tranche=1,
            tranche_pct=25.0,
        )

        available_cash = 10000.0
        market_price = 100.0

        result = calculate_buy_quantity(
            signal=signal,
            config=config,
            available_cash=available_cash,
            current_position_value=0.0,
            equity=10000.0,
            market_price=market_price,
        )

        # Manual calculation:
        # spend_base = 10000 * (90/100) = 9000
        # spend = 9000 * (25/100) = 2250
        # qty = 2250 / 100 = 22.5
        expected_spend = available_cash * 0.9 * 0.25
        expected_qty = expected_spend / market_price

        assert result.notional == pytest.approx(expected_spend, rel=0.01)
        assert result.qty == pytest.approx(expected_qty, rel=0.01)

    def test_a_type_sequential_tranches(self):
        """Test sequential tranche calculations."""
        config = MRConfig(
            signal_tf="15m",
            htf_tf="4h",
            osc_preset="preset1",
            buy_tranches=[25, 50, 75, 100],
            sell_tranches=[50, 100],
            cash_use_pct=90.0,
            hard_cap_pct=95.0,
        )

        equity = 10000.0
        market_price = 100.0
        position_value = 0.0
        total_spent = 0.0

        # Simulate 4 sequential buys
        for i, tranche_pct in enumerate([25, 50, 75, 100], 1):
            available_cash = equity - position_value

            signal = SignalResult(
                action="buy",
                reason_code="R1_PULLBACK",
                reason_text="Test",
                regime=1,
                tranche=i,
                tranche_pct=float(tranche_pct),
            )

            result = calculate_buy_quantity(
                signal=signal,
                config=config,
                available_cash=available_cash,
                current_position_value=position_value,
                equity=equity,
                market_price=market_price,
            )

            if result.qty > 0:
                position_value += result.notional
                total_spent += result.notional

        # Should not exceed hard cap (95%)
        assert position_value <= equity * 0.95

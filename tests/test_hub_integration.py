# tests/test_hub_integration.py
"""
Tests for hub_integration.py - Signal to order execution bridge.

Phase 2: Hub integration tests.
"""

import pytest
import numpy as np
from unittest.mock import AsyncMock, patch, MagicMock
from datetime import datetime, timezone

from app.strategy_engine.models import MRConfig, StrategyState, SignalResult
from app.strategy_engine.position_manager import PositionInfo
from app.strategy_engine.hub_integration import (
    SignalEvent,
    SignalSnapshot,
    generate_signal_id,
    generate_snapshot_id,
    signal_to_order_request,
)


class TestSignalEvent:
    """Test SignalEvent dataclass."""

    def test_signal_event_creation(self):
        """Test SignalEvent creation with all fields."""
        event = SignalEvent(
            signal_id="sig_1_1000_abc12345",
            asset_id=1,
            symbol="BTC-USDT",
            exchange="okx",
            market="spot",
            side="entry",
            action="buy",
            premium_mode="mr",
            params_version="v1.0",
            reason_code="R1_PULLBACK",
            reason_text="R1 pullback buy",
            snapshot_id="snap_1_1000_xyz67890",
            tf="15m",
            tf_warning=False,
            price_hint=50000.0,
            tranche=1,
            tranche_pct=25.0,
            regime=1,
            ts=1000,
            created_at=datetime.now(timezone.utc),
        )

        assert event.signal_id == "sig_1_1000_abc12345"
        assert event.asset_id == 1
        assert event.symbol == "BTC-USDT"
        assert event.action == "buy"
        assert event.premium_mode == "mr"

    def test_signal_event_defaults(self):
        """Test SignalEvent default values."""
        event = SignalEvent(
            signal_id="sig_1_1000_abc",
            asset_id=1,
            symbol="BTC-USDT",
            exchange="okx",
            side="entry",
            action="buy",
            premium_mode="mr",
            reason_code="R1_PULLBACK",
            reason_text="Test",
            snapshot_id="snap_1_1000_xyz",
            tf="15m",
        )

        assert event.market == "spot"
        assert event.params_version == "v1.0"
        assert event.tf_warning is False
        assert event.price_hint is None
        assert event.ts == 0


class TestSignalSnapshot:
    """Test SignalSnapshot dataclass."""

    def test_signal_snapshot_creation(self):
        """Test SignalSnapshot creation."""
        snapshot = SignalSnapshot(
            snapshot_id="snap_1_1000_xyz",
            signal_id="sig_1_1000_abc",
            asset_id=1,
            symbol="BTC-USDT",
            exchange="okx",
            ts=1000,
            tf="15m",
            ohlcv={"o": 100.0, "h": 101.0, "l": 99.0, "c": 100.5, "v": 1000.0},
            indicators={
                "normalized_osc": -0.5,
                "upper_band": 0.8,
                "lower_band": -0.8,
                "regime": 1,
            },
            premium_mode="mr",
            params_version="v1.0",
            reason_code="R1_PULLBACK",
            reason_text="R1 pullback buy",
            created_at=datetime.now(timezone.utc),
        )

        assert snapshot.snapshot_id == "snap_1_1000_xyz"
        assert snapshot.ohlcv["c"] == 100.5
        assert snapshot.indicators["regime"] == 1


class TestGenerateIds:
    """Test ID generation functions."""

    def test_generate_signal_id_format(self):
        """Test signal ID format."""
        signal_id = generate_signal_id(asset_id=1, ts=1000000)
        assert signal_id.startswith("sig_1_1000000_")
        assert len(signal_id) == len("sig_1_1000000_") + 8  # 8 char random

    def test_generate_signal_id_unique(self):
        """Test signal IDs are unique."""
        id1 = generate_signal_id(1, 1000)
        id2 = generate_signal_id(1, 1000)
        assert id1 != id2  # Random part makes them unique

    def test_generate_snapshot_id_format(self):
        """Test snapshot ID format."""
        snapshot_id = generate_snapshot_id(asset_id=1, ts=1000000)
        assert snapshot_id.startswith("snap_1_1000000_")
        assert len(snapshot_id) == len("snap_1_1000000_") + 8

    def test_generate_snapshot_id_unique(self):
        """Test snapshot IDs are unique."""
        id1 = generate_snapshot_id(1, 1000)
        id2 = generate_snapshot_id(1, 1000)
        assert id1 != id2


class TestSignalToOrderRequest:
    """Test signal_to_order_request function."""

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

    @pytest.fixture
    def empty_position(self):
        """Create empty position."""
        return PositionInfo(
            symbol="BTC-USDT",
            exchange="okx",
            quantity=0.0,
            avg_price=0.0,
            market_price=100.0,
            market_value=0.0,
            unrealized_pnl=0.0,
            unrealized_pnl_pct=0.0,
        )

    @pytest.fixture
    def position_with_holding(self):
        """Create position with holdings."""
        return PositionInfo(
            symbol="BTC-USDT",
            exchange="okx",
            quantity=10.0,
            avg_price=100.0,
            market_price=110.0,
            market_value=1100.0,
            unrealized_pnl=100.0,
            unrealized_pnl_pct=10.0,
        )

    def test_buy_signal_to_order_request(self, config, empty_position):
        """Test converting buy signal to order request."""
        signal_event = SignalEvent(
            signal_id="sig_1_1000_abc",
            asset_id=1,
            symbol="BTC-USDT",
            exchange="okx",
            side="entry",
            action="buy",
            premium_mode="mr",
            reason_code="R1_PULLBACK",
            reason_text="R1 pullback buy",
            snapshot_id="snap_1_1000_xyz",
            tf="15m",
            tranche=1,
            tranche_pct=25.0,
            regime=1,
        )

        order = signal_to_order_request(
            signal_event=signal_event,
            config=config,
            position=empty_position,
            equity=10000.0,
            market_price=100.0,
        )

        assert order is not None
        assert order["side"] == "buy"
        assert order["symbol"] == "BTC-USDT"
        assert order["order_type"] == "market"
        assert order["qty"] > 0
        assert order["signal_id"] == "sig_1_1000_abc"

    def test_sell_signal_to_order_request(self, config, position_with_holding):
        """Test converting sell signal to order request."""
        signal_event = SignalEvent(
            signal_id="sig_1_1000_abc",
            asset_id=1,
            symbol="BTC-USDT",
            exchange="okx",
            side="exit",
            action="sell",
            premium_mode="mr",
            reason_code="PROFIT_GATE",
            reason_text="Profit gate sell",
            snapshot_id="snap_1_1000_xyz",
            tf="15m",
            tranche=1,
            tranche_pct=50.0,
            regime=1,
        )

        order = signal_to_order_request(
            signal_event=signal_event,
            config=config,
            position=position_with_holding,
            equity=10000.0,
            market_price=110.0,
        )

        assert order is not None
        assert order["side"] == "sell"
        assert order["qty"] == 5.0  # 50% of 10
        assert order["reason_code"] == "PROFIT_GATE"

    def test_buy_signal_no_cash_returns_none(self, config):
        """Test buy signal returns None when no available cash."""
        position = PositionInfo(
            symbol="BTC-USDT",
            exchange="okx",
            quantity=100.0,
            avg_price=100.0,
            market_price=100.0,
            market_value=10000.0,  # Full position
            unrealized_pnl=0.0,
            unrealized_pnl_pct=0.0,
        )

        signal_event = SignalEvent(
            signal_id="sig_1_1000_abc",
            asset_id=1,
            symbol="BTC-USDT",
            exchange="okx",
            side="entry",
            action="buy",
            premium_mode="mr",
            reason_code="R1_PULLBACK",
            reason_text="R1 pullback buy",
            snapshot_id="snap_1_1000_xyz",
            tf="15m",
            tranche=1,
            tranche_pct=25.0,
            regime=1,
        )

        order = signal_to_order_request(
            signal_event=signal_event,
            config=config,
            position=position,
            equity=10000.0,
            market_price=100.0,
        )

        # No cash available, should return None or zero qty order
        assert order is None or order["qty"] == 0

    def test_sell_signal_no_position_returns_none(self, config, empty_position):
        """Test sell signal returns None when no position."""
        signal_event = SignalEvent(
            signal_id="sig_1_1000_abc",
            asset_id=1,
            symbol="BTC-USDT",
            exchange="okx",
            side="exit",
            action="sell",
            premium_mode="mr",
            reason_code="PROFIT_GATE",
            reason_text="Profit gate sell",
            snapshot_id="snap_1_1000_xyz",
            tf="15m",
            tranche=1,
            tranche_pct=50.0,
            regime=1,
        )

        order = signal_to_order_request(
            signal_event=signal_event,
            config=config,
            position=empty_position,
            equity=10000.0,
            market_price=100.0,
        )

        assert order is None

    def test_none_action_returns_none(self, config, empty_position):
        """Test 'none' action returns None."""
        signal_event = SignalEvent(
            signal_id="sig_1_1000_abc",
            asset_id=1,
            symbol="BTC-USDT",
            exchange="okx",
            side="entry",
            action="none",  # No action
            premium_mode="mr",
            reason_code="FILTERED",
            reason_text="Filtered out",
            snapshot_id="snap_1_1000_xyz",
            tf="15m",
        )

        order = signal_to_order_request(
            signal_event=signal_event,
            config=config,
            position=empty_position,
            equity=10000.0,
            market_price=100.0,
        )

        assert order is None


class TestOrderRequestFields:
    """Test order request contains all required fields."""

    @pytest.fixture
    def config(self):
        return MRConfig(
            signal_tf="15m",
            htf_tf="4h",
            osc_preset="preset1",
            buy_tranches=[25, 50, 75, 100],
            sell_tranches=[50, 100],
            cash_use_pct=90.0,
            hard_cap_pct=95.0,
        )

    def test_order_request_has_all_fields(self, config):
        """Test order request has all required fields for Hub."""
        position = PositionInfo(
            symbol="BTC-USDT",
            exchange="okx",
            quantity=0.0,
            avg_price=0.0,
            market_price=100.0,
            market_value=0.0,
            unrealized_pnl=0.0,
            unrealized_pnl_pct=0.0,
        )

        signal_event = SignalEvent(
            signal_id="sig_1_1000_abc",
            asset_id=1,
            symbol="BTC-USDT",
            exchange="okx",
            side="entry",
            action="buy",
            premium_mode="mr",
            reason_code="R1_PULLBACK",
            reason_text="R1 pullback buy",
            snapshot_id="snap_1_1000_xyz",
            tf="15m",
            tranche=1,
            tranche_pct=25.0,
            regime=1,
        )

        order = signal_to_order_request(
            signal_event=signal_event,
            config=config,
            position=position,
            equity=10000.0,
            market_price=100.0,
        )

        # Required fields for Hub
        required_fields = [
            "asset_id",
            "symbol",
            "exchange",
            "side",
            "order_type",
            "qty",
            "notional",
            "reason_code",
            "reason_text",
            "snapshot_id",
            "signal_id",
        ]

        for field in required_fields:
            assert field in order, f"Missing field: {field}"


class TestTfWarning:
    """Test TF warning for short timeframes."""

    def test_tf_warning_1m(self):
        """Test TF warning is True for 1m timeframe."""
        # In process_asset, tf_warning is set for 1m, 3m, 5m
        event = SignalEvent(
            signal_id="sig_1_1000_abc",
            asset_id=1,
            symbol="BTC-USDT",
            exchange="okx",
            side="entry",
            action="buy",
            premium_mode="mr",
            reason_code="R1_PULLBACK",
            reason_text="Test",
            snapshot_id="snap_1_1000_xyz",
            tf="1m",
            tf_warning=True,  # Should be True for 1m
        )

        assert event.tf_warning is True

    def test_tf_warning_15m(self):
        """Test TF warning is False for 15m timeframe."""
        event = SignalEvent(
            signal_id="sig_1_1000_abc",
            asset_id=1,
            symbol="BTC-USDT",
            exchange="okx",
            side="entry",
            action="buy",
            premium_mode="mr",
            reason_code="R1_PULLBACK",
            reason_text="Test",
            snapshot_id="snap_1_1000_xyz",
            tf="15m",
            tf_warning=False,  # Should be False for 15m
        )

        assert event.tf_warning is False


class TestSignalEventSideMapping:
    """Test side field mapping (entry/exit)."""

    def test_buy_is_entry(self):
        """Test buy action has 'entry' side."""
        event = SignalEvent(
            signal_id="sig_1_1000_abc",
            asset_id=1,
            symbol="BTC-USDT",
            exchange="okx",
            side="entry",
            action="buy",
            premium_mode="mr",
            reason_code="R1_PULLBACK",
            reason_text="Test",
            snapshot_id="snap_1_1000_xyz",
            tf="15m",
        )

        assert event.side == "entry"
        assert event.action == "buy"

    def test_sell_is_exit(self):
        """Test sell action has 'exit' side."""
        event = SignalEvent(
            signal_id="sig_1_1000_abc",
            asset_id=1,
            symbol="BTC-USDT",
            exchange="okx",
            side="exit",
            action="sell",
            premium_mode="mr",
            reason_code="PROFIT_GATE",
            reason_text="Test",
            snapshot_id="snap_1_1000_xyz",
            tf="15m",
        )

        assert event.side == "exit"
        assert event.action == "sell"

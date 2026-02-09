# tests/test_integration.py
"""
Integration tests for MR Premium Strategy Engine.

Phase 6: End-to-end integration tests for live trading validation.
Tests the full flow from candle data to signal generation.
"""

import pytest
import asyncio
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch
import numpy as np

from app.strategy_engine.models import (
    Candle,
    MRConfig,
    StrategyState,
    HTFIndicators,
    OscillatorData,
)
from app.strategy_engine.hub_integration import (
    SignalEvent,
    SignalSnapshot,
    process_asset,
    generate_signal_id,
    generate_snapshot_id,
    signal_to_order_request,
)
from app.strategy_engine.position_manager import PositionInfo
from app.strategy_engine.candle_fetcher import CandleData, CandleCache
from app.strategy_engine.scheduler import PremiumScheduler, SchedulerConfig
from app.strategy_engine.backtest_engine import generate_sample_candles


class TestSignalIdGeneration:
    """Test signal and snapshot ID generation."""

    def test_signal_id_format(self):
        """Test signal ID format."""
        signal_id = generate_signal_id(asset_id=1, ts=1000000)

        assert signal_id.startswith("sig_1_1000000_")
        assert len(signal_id) > 15

    def test_signal_id_unique(self):
        """Test signal IDs are unique."""
        id1 = generate_signal_id(asset_id=1, ts=1000000)
        id2 = generate_signal_id(asset_id=1, ts=1000000)

        assert id1 != id2

    def test_snapshot_id_format(self):
        """Test snapshot ID format."""
        snapshot_id = generate_snapshot_id(asset_id=1, ts=1000000)

        assert snapshot_id.startswith("snap_1_1000000_")


class TestProcessAssetIntegration:
    """Integration tests for process_asset function."""

    @pytest.mark.asyncio
    async def test_process_asset_insufficient_candles(self):
        """Test process_asset with insufficient candles."""
        # Create mock candle data with few candles
        mock_candle_data = CandleData(
            exchange="okx",
            symbol="BTC-USDT",
            timeframe="15m",
            opens=np.array([50000.0] * 50),
            highs=np.array([50100.0] * 50),
            lows=np.array([49900.0] * 50),
            closes=np.array([50050.0] * 50),
            volumes=np.array([1000.0] * 50),
            timestamps=np.array([i * 900000 for i in range(50)]),
        )

        with patch('app.strategy_engine.hub_integration.get_candle_cache') as mock_cache:
            cache_instance = MagicMock()
            cache_instance.get_candles = AsyncMock(return_value=mock_candle_data)
            mock_cache.return_value = cache_instance

            config = MRConfig()
            state = StrategyState()
            position = PositionInfo(
                symbol="BTC-USDT",
                exchange="okx",
                quantity=0.0,
                avg_price=0.0,
                market_price=50050.0,
                market_value=0.0,
                unrealized_pnl=0.0,
                unrealized_pnl_pct=0.0,
            )

            result = await process_asset(
                asset_id=1,
                symbol="BTC-USDT",
                exchange="okx",
                config=config,
                state=state,
                position=position,
                equity=10000.0,
            )

            # Should return None due to insufficient candles
            signal_event, snapshot, new_state = result
            assert signal_event is None

    @pytest.mark.asyncio
    async def test_process_asset_with_mock_candles(self):
        """Test process_asset with mocked candle data."""
        # Generate sample candles
        candles = generate_sample_candles(days=30, seed=42)

        mock_candle_data = CandleData(
            exchange="okx",
            symbol="BTC-USDT",
            timeframe="1h",
            opens=np.array([c.o for c in candles]),
            highs=np.array([c.h for c in candles]),
            lows=np.array([c.l for c in candles]),
            closes=np.array([c.c for c in candles]),
            volumes=np.array([c.v for c in candles]),
            timestamps=np.array([c.ts for c in candles]),
        )

        with patch('app.strategy_engine.hub_integration.get_candle_cache') as mock_cache:
            cache_instance = MagicMock()
            cache_instance.get_candles = AsyncMock(return_value=mock_candle_data)
            mock_cache.return_value = cache_instance

            config = MRConfig(
                signal_tf="1h",
                htf_tf="4h",
                osc_preset="preset1",
            )
            state = StrategyState()
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

            result = await process_asset(
                asset_id=1,
                symbol="BTC-USDT",
                exchange="okx",
                config=config,
                state=state,
                position=position,
                equity=10000.0,
            )

            signal_event, snapshot, new_state = result

            # State should be updated
            assert new_state is not None

            # If signal generated, verify structure
            if signal_event is not None:
                assert isinstance(signal_event, SignalEvent)
                assert signal_event.asset_id == 1
                assert signal_event.symbol == "BTC-USDT"
                assert signal_event.exchange == "okx"
                assert signal_event.action in ["buy", "sell"]


class TestSignalToOrderIntegration:
    """Test signal to order conversion."""

    def test_signal_to_order_buy(self):
        """Test converting buy signal to order request."""
        signal = SignalEvent(
            signal_id="sig_1_1000_abc",
            asset_id=1,
            symbol="BTC-USDT",
            exchange="okx",
            side="entry",
            action="buy",
            premium_mode="mr",
            reason_code="OSC_BUY",
            reason_text="OSC buy signal",
            snapshot_id="snap_1_1000_xyz",
            tf="1h",
            price_hint=50000.0,
            tranche=1,
            tranche_pct=25.0,
        )

        config = MRConfig()
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

        order = signal_to_order_request(
            signal_event=signal,
            config=config,
            position=position,
            equity=10000.0,
            market_price=50000.0,
        )

        assert order is not None
        assert order["side"] == "buy"
        assert order["symbol"] == "BTC-USDT"
        assert order["exchange"] == "okx"

    def test_signal_to_order_sell(self):
        """Test converting sell signal to order request."""
        signal = SignalEvent(
            signal_id="sig_1_1000_abc",
            asset_id=1,
            symbol="BTC-USDT",
            exchange="okx",
            side="exit",
            action="sell",
            premium_mode="mr",
            reason_code="OSC_SELL",
            reason_text="OSC sell signal",
            snapshot_id="snap_1_1000_xyz",
            tf="1h",
            price_hint=55000.0,
            tranche=1,
            tranche_pct=50.0,
        )

        config = MRConfig()
        position = PositionInfo(
            symbol="BTC-USDT",
            exchange="okx",
            quantity=0.1,
            avg_price=50000.0,
            market_price=55000.0,
            market_value=5500.0,
            unrealized_pnl=500.0,
            unrealized_pnl_pct=10.0,
        )

        order = signal_to_order_request(
            signal_event=signal,
            config=config,
            position=position,
            equity=10000.0,
            market_price=55000.0,
        )

        assert order is not None
        assert order["side"] == "sell"


class TestSchedulerIntegration:
    """Integration tests for scheduler."""

    @pytest.mark.asyncio
    async def test_scheduler_lifecycle(self):
        """Test scheduler start/stop cycle."""
        scheduler = PremiumScheduler()

        # Register an asset
        scheduler.register_asset(
            asset_id=1,
            symbol="BTC-USDT",
            exchange="okx",
            timeframe="15m",
            htf_timeframe="4h",
        )

        assert scheduler.asset_count == 1

        # Start scheduler
        await scheduler.start()
        assert scheduler.state.value == "running"

        # Stop scheduler
        await scheduler.stop()
        assert scheduler.state.value == "stopped"

    @pytest.mark.asyncio
    async def test_scheduler_with_callback(self):
        """Test scheduler with process callback."""
        processed_assets = []

        async def mock_callback(asset):
            processed_assets.append(asset.asset_id)
            return True

        scheduler = PremiumScheduler(process_callback=mock_callback)
        scheduler.register_asset(
            asset_id=1,
            symbol="BTC-USDT",
            exchange="okx",
            timeframe="15m",
            htf_timeframe="4h",
        )

        # Manually trigger processing
        result = await scheduler.process_now(1)

        assert result is True
        assert 1 in processed_assets

    @pytest.mark.asyncio
    async def test_scheduler_dry_run_mode(self):
        """Test scheduler in dry run mode."""
        orders_executed = []

        async def mock_callback(asset):
            # In dry run, we log but don't execute
            orders_executed.append({
                "asset_id": asset.asset_id,
                "dry_run": True,
            })
            return True

        config = SchedulerConfig()
        scheduler = PremiumScheduler(config=config, process_callback=mock_callback)
        scheduler.register_asset(
            asset_id=1,
            symbol="ETH-USDT",
            exchange="binance",
            timeframe="1h",
            htf_timeframe="4h",
        )

        await scheduler.process_now(1)

        assert len(orders_executed) == 1
        assert orders_executed[0]["dry_run"] is True


class TestFullPipelineIntegration:
    """Test the complete signal generation pipeline."""

    def test_config_to_signal_flow(self):
        """Test config -> indicators -> regime -> signal flow."""
        from app.strategy_engine.signal_generator import calc_osc_data, generate_mr_signal
        from app.strategy_engine.regime_detector import detect_regime, calc_htf_indicators

        # Generate test data
        candles = generate_sample_candles(days=30, seed=123)
        closes = np.array([c.c for c in candles])
        highs = np.array([c.h for c in candles])
        lows = np.array([c.l for c in candles])
        volumes = np.array([c.v for c in candles])

        # Step 1: Calculate oscillator data
        osc_data = calc_osc_data(closes, preset="preset1")
        assert osc_data is not None
        assert not np.isnan(osc_data.normalized_osc)

        # Step 2: Calculate HTF indicators
        htf_ind = calc_htf_indicators(closes, highs, lows, volumes)
        assert htf_ind is not None

        # Step 3: Detect regime
        regime = detect_regime(htf_ind, use_4regime=True)
        assert regime in [0, 1, 2, 3, 4]

        # Step 4: Generate signal
        config = MRConfig()
        state = StrategyState()

        signal, new_state = generate_mr_signal(
            close=closes,
            high=highs,
            low=lows,
            osc_data=osc_data,
            htf_indicators=htf_ind,
            regime=regime,
            state=state,
            config=config,
            has_position=False,
            position_qty=0.0,
            avg_price=None,
            current_ts=int(datetime.now().timestamp() * 1000),
        )

        assert signal is not None
        assert signal.action in ["buy", "sell", "none"]
        assert new_state is not None


class TestSignalEventStructure:
    """Test SignalEvent data structure."""

    def test_signal_event_creation(self):
        """Test creating a SignalEvent."""
        event = SignalEvent(
            signal_id="sig_test_123",
            asset_id=1,
            symbol="BTC-USDT",
            exchange="okx",
            side="entry",
            action="buy",
            premium_mode="mr",
            reason_code="TEST",
            reason_text="Test signal",
            snapshot_id="snap_test_123",
            tf="1h",
        )

        assert event.signal_id == "sig_test_123"
        assert event.market == "spot"  # default
        assert event.params_version == "v1.0"  # default

    def test_signal_event_with_all_fields(self):
        """Test SignalEvent with all optional fields."""
        now = datetime.now(timezone.utc)

        event = SignalEvent(
            signal_id="sig_full_123",
            asset_id=2,
            symbol="ETH-USDT",
            exchange="binance",
            side="exit",
            action="sell",
            premium_mode="mr",
            reason_code="PROFIT_TAKE",
            reason_text="Profit take at R1",
            snapshot_id="snap_full_123",
            tf="15m",
            market="spot",
            params_version="v1.1",
            tf_warning=True,
            price_hint=3500.0,
            tranche=2,
            tranche_pct=50.0,
            regime=1,
            ts=int(now.timestamp() * 1000),
            created_at=now,
        )

        assert event.tf_warning is True
        assert event.price_hint == 3500.0
        assert event.tranche == 2
        assert event.regime == 1


class TestPositionTracking:
    """Test position tracking across signals."""

    def test_position_info_empty(self):
        """Test empty position (quantity=0)."""
        pos = PositionInfo(
            symbol="BTC-USDT",
            exchange="okx",
            quantity=0.0,
            avg_price=0.0,
            market_price=50000.0,
            market_value=0.0,
            unrealized_pnl=0.0,
            unrealized_pnl_pct=0.0,
        )

        assert pos.has_position is False
        assert pos.quantity == 0.0

    def test_position_info_with_data(self):
        """Test position with data."""
        pos = PositionInfo(
            symbol="BTC-USDT",
            exchange="okx",
            quantity=0.1,
            avg_price=50000.0,
            market_price=51000.0,
            market_value=5100.0,
            unrealized_pnl=100.0,
            unrealized_pnl_pct=2.0,
        )

        assert pos.has_position is True
        assert pos.quantity == 0.1
        assert pos.unrealized_pnl == 100.0

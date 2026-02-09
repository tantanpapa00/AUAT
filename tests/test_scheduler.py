# tests/test_scheduler.py
"""
Tests for scheduler.py - Premium strategy scheduler.

Phase 3: Scheduler tests.
"""

import pytest
import asyncio
from datetime import datetime, timezone, timedelta
from unittest.mock import AsyncMock, patch, MagicMock

from app.strategy_engine.scheduler import (
    PremiumScheduler,
    SchedulerConfig,
    ScheduledAsset,
    SchedulerState,
    get_scheduler,
    get_tf_seconds,
    get_current_bar_open_time,
    get_next_bar_close_time,
    seconds_until_bar_close,
    TF_TO_SECONDS,
)


class TestTimeframeHelpers:
    """Test timeframe helper functions."""

    def test_get_tf_seconds_known_timeframes(self):
        """Test get_tf_seconds for known timeframes."""
        assert get_tf_seconds("1m") == 60
        assert get_tf_seconds("5m") == 300
        assert get_tf_seconds("15m") == 900
        assert get_tf_seconds("1h") == 3600
        assert get_tf_seconds("4h") == 14400
        assert get_tf_seconds("1D") == 86400

    def test_get_tf_seconds_unknown_timeframe(self):
        """Test get_tf_seconds returns default for unknown timeframe."""
        assert get_tf_seconds("unknown") == 3600  # Default 1h

    def test_get_current_bar_open_time_15m(self):
        """Test current bar open time calculation for 15m."""
        bar_open = get_current_bar_open_time("15m")

        # Should be on a 15-minute boundary
        assert bar_open.minute % 15 == 0
        assert bar_open.second == 0
        assert bar_open.microsecond == 0
        assert bar_open.tzinfo == timezone.utc

    def test_get_current_bar_open_time_1h(self):
        """Test current bar open time calculation for 1h."""
        bar_open = get_current_bar_open_time("1h")

        # Should be on an hour boundary
        assert bar_open.minute == 0
        assert bar_open.second == 0
        assert bar_open.tzinfo == timezone.utc

    def test_get_current_bar_open_time_4h(self):
        """Test current bar open time calculation for 4h."""
        bar_open = get_current_bar_open_time("4h")

        # Should be on a 4-hour boundary (0, 4, 8, 12, 16, 20)
        assert bar_open.hour % 4 == 0
        assert bar_open.minute == 0
        assert bar_open.second == 0

    def test_get_next_bar_close_time(self):
        """Test next bar close time is bar_open + tf_seconds."""
        bar_open = get_current_bar_open_time("15m")
        next_close = get_next_bar_close_time("15m")

        delta = next_close - bar_open
        assert delta.total_seconds() == 900  # 15 minutes

    def test_seconds_until_bar_close_positive(self):
        """Test seconds_until_bar_close returns positive value."""
        seconds = seconds_until_bar_close("15m")

        # Should be between 0 and 900 (15 minutes)
        assert 0 <= seconds <= 900

    def test_seconds_until_bar_close_different_timeframes(self):
        """Test seconds_until_bar_close for different timeframes."""
        for tf, max_seconds in [("1m", 60), ("15m", 900), ("1h", 3600)]:
            seconds = seconds_until_bar_close(tf)
            assert 0 <= seconds <= max_seconds


class TestScheduledAsset:
    """Test ScheduledAsset dataclass."""

    def test_scheduled_asset_creation(self):
        """Test ScheduledAsset creation."""
        asset = ScheduledAsset(
            asset_id=1,
            symbol="BTC-USDT",
            exchange="okx",
            timeframe="15m",
            htf_timeframe="4h",
        )

        assert asset.asset_id == 1
        assert asset.symbol == "BTC-USDT"
        assert asset.exchange == "okx"
        assert asset.timeframe == "15m"
        assert asset.htf_timeframe == "4h"
        assert asset.enabled is True
        assert asset.last_processed is None
        assert asset.error_count == 0

    def test_scheduled_asset_disabled(self):
        """Test ScheduledAsset with disabled flag."""
        asset = ScheduledAsset(
            asset_id=1,
            symbol="BTC-USDT",
            exchange="okx",
            timeframe="15m",
            htf_timeframe="4h",
            enabled=False,
        )

        assert asset.enabled is False


class TestSchedulerConfig:
    """Test SchedulerConfig dataclass."""

    def test_scheduler_config_defaults(self):
        """Test SchedulerConfig default values."""
        config = SchedulerConfig()

        assert config.bar_close_delay_seconds == 2.0
        assert config.min_process_interval_seconds == 30.0
        assert config.max_consecutive_errors == 5
        assert config.max_concurrent_assets == 10

    def test_scheduler_config_custom(self):
        """Test SchedulerConfig custom values."""
        config = SchedulerConfig(
            bar_close_delay_seconds=5.0,
            max_concurrent_assets=20,
        )

        assert config.bar_close_delay_seconds == 5.0
        assert config.max_concurrent_assets == 20


class TestPremiumScheduler:
    """Test PremiumScheduler class."""

    def test_scheduler_creation(self):
        """Test scheduler creation."""
        scheduler = PremiumScheduler()

        assert scheduler.state == SchedulerState.STOPPED
        assert scheduler.asset_count == 0
        assert scheduler.active_timeframes == []

    def test_scheduler_with_config(self):
        """Test scheduler with custom config."""
        config = SchedulerConfig(bar_close_delay_seconds=10.0)
        scheduler = PremiumScheduler(config=config)

        assert scheduler.config.bar_close_delay_seconds == 10.0

    def test_register_asset(self):
        """Test registering an asset."""
        scheduler = PremiumScheduler()

        result = scheduler.register_asset(
            asset_id=1,
            symbol="BTC-USDT",
            exchange="okx",
            timeframe="15m",
            htf_timeframe="4h",
        )

        assert result is True
        assert scheduler.asset_count == 1
        assert "15m" in scheduler.active_timeframes

    def test_register_multiple_assets(self):
        """Test registering multiple assets."""
        scheduler = PremiumScheduler()

        scheduler.register_asset(1, "BTC-USDT", "okx", "15m", "4h")
        scheduler.register_asset(2, "ETH-USDT", "okx", "15m", "4h")
        scheduler.register_asset(3, "SOL-USDT", "binance", "1h", "4h")

        assert scheduler.asset_count == 3
        assert set(scheduler.active_timeframes) == {"15m", "1h"}

    def test_register_asset_update_existing(self):
        """Test registering an asset that already exists."""
        scheduler = PremiumScheduler()

        scheduler.register_asset(1, "BTC-USDT", "okx", "15m", "4h")
        scheduler.register_asset(1, "BTC-USDT", "okx", "1h", "4h")  # Update

        assert scheduler.asset_count == 1
        asset = scheduler.get_asset(1)
        assert asset.timeframe == "1h"

    def test_unregister_asset(self):
        """Test unregistering an asset."""
        scheduler = PremiumScheduler()

        scheduler.register_asset(1, "BTC-USDT", "okx", "15m", "4h")
        result = scheduler.unregister_asset(1)

        assert result is True
        assert scheduler.asset_count == 0

    def test_unregister_nonexistent_asset(self):
        """Test unregistering a non-existent asset."""
        scheduler = PremiumScheduler()
        result = scheduler.unregister_asset(999)
        assert result is False

    def test_enable_disable_asset(self):
        """Test enabling and disabling an asset."""
        scheduler = PremiumScheduler()

        scheduler.register_asset(1, "BTC-USDT", "okx", "15m", "4h")

        # Disable
        result = scheduler.disable_asset(1)
        assert result is True
        asset = scheduler.get_asset(1)
        assert asset.enabled is False

        # Enable
        result = scheduler.enable_asset(1)
        assert result is True
        asset = scheduler.get_asset(1)
        assert asset.enabled is True

    def test_get_asset(self):
        """Test getting an asset by ID."""
        scheduler = PremiumScheduler()

        scheduler.register_asset(1, "BTC-USDT", "okx", "15m", "4h")
        asset = scheduler.get_asset(1)

        assert asset is not None
        assert asset.asset_id == 1
        assert asset.symbol == "BTC-USDT"

    def test_get_asset_nonexistent(self):
        """Test getting a non-existent asset."""
        scheduler = PremiumScheduler()
        asset = scheduler.get_asset(999)
        assert asset is None

    def test_get_assets_for_timeframe(self):
        """Test getting assets for a specific timeframe."""
        scheduler = PremiumScheduler()

        scheduler.register_asset(1, "BTC-USDT", "okx", "15m", "4h")
        scheduler.register_asset(2, "ETH-USDT", "okx", "15m", "4h")
        scheduler.register_asset(3, "SOL-USDT", "binance", "1h", "4h")

        assets_15m = scheduler.get_assets_for_timeframe("15m")
        assert len(assets_15m) == 2

        assets_1h = scheduler.get_assets_for_timeframe("1h")
        assert len(assets_1h) == 1

    def test_get_assets_for_timeframe_excludes_disabled(self):
        """Test getting assets excludes disabled ones."""
        scheduler = PremiumScheduler()

        scheduler.register_asset(1, "BTC-USDT", "okx", "15m", "4h")
        scheduler.register_asset(2, "ETH-USDT", "okx", "15m", "4h", enabled=False)

        assets = scheduler.get_assets_for_timeframe("15m")
        assert len(assets) == 1
        assert assets[0].asset_id == 1

    def test_get_status(self):
        """Test getting scheduler status."""
        scheduler = PremiumScheduler()

        scheduler.register_asset(1, "BTC-USDT", "okx", "15m", "4h")

        status = scheduler.get_status()

        assert status["state"] == "stopped"
        assert status["asset_count"] == 1
        assert "15m" in status["active_timeframes"]
        assert len(status["assets"]) == 1


class TestSchedulerLifecycle:
    """Test scheduler start/stop/pause/resume."""

    @pytest.mark.asyncio
    async def test_start_scheduler(self):
        """Test starting the scheduler."""
        scheduler = PremiumScheduler()

        await scheduler.start()

        assert scheduler.state == SchedulerState.RUNNING

        # Cleanup
        await scheduler.stop()

    @pytest.mark.asyncio
    async def test_stop_scheduler(self):
        """Test stopping the scheduler."""
        scheduler = PremiumScheduler()

        await scheduler.start()
        await scheduler.stop()

        assert scheduler.state == SchedulerState.STOPPED

    @pytest.mark.asyncio
    async def test_pause_resume_scheduler(self):
        """Test pausing and resuming the scheduler."""
        scheduler = PremiumScheduler()

        await scheduler.start()

        await scheduler.pause()
        assert scheduler.state == SchedulerState.PAUSED

        await scheduler.resume()
        assert scheduler.state == SchedulerState.RUNNING

        # Cleanup
        await scheduler.stop()

    @pytest.mark.asyncio
    async def test_start_already_running(self):
        """Test starting an already running scheduler."""
        scheduler = PremiumScheduler()

        await scheduler.start()
        await scheduler.start()  # Should not raise

        assert scheduler.state == SchedulerState.RUNNING

        # Cleanup
        await scheduler.stop()


class TestSchedulerProcessing:
    """Test scheduler asset processing."""

    @pytest.mark.asyncio
    async def test_process_now(self):
        """Test manual processing trigger."""
        callback_called = False

        async def mock_callback(asset):
            nonlocal callback_called
            callback_called = True
            return True

        scheduler = PremiumScheduler(process_callback=mock_callback)
        scheduler.register_asset(1, "BTC-USDT", "okx", "15m", "4h")

        result = await scheduler.process_now(1)

        assert result is True
        assert callback_called is True

    @pytest.mark.asyncio
    async def test_process_now_nonexistent_asset(self):
        """Test processing non-existent asset."""
        scheduler = PremiumScheduler()
        result = await scheduler.process_now(999)
        assert result is False

    @pytest.mark.asyncio
    async def test_process_callback_failure_increments_error(self):
        """Test that callback failure increments error count."""
        async def failing_callback(asset):
            return False

        scheduler = PremiumScheduler(process_callback=failing_callback)
        scheduler.register_asset(1, "BTC-USDT", "okx", "15m", "4h")

        await scheduler.process_now(1)
        asset = scheduler.get_asset(1)

        assert asset.error_count == 1

    @pytest.mark.asyncio
    async def test_process_callback_exception_increments_error(self):
        """Test that callback exception increments error count."""
        async def raising_callback(asset):
            raise Exception("Test error")

        scheduler = PremiumScheduler(process_callback=raising_callback)
        scheduler.register_asset(1, "BTC-USDT", "okx", "15m", "4h")

        await scheduler.process_now(1)
        asset = scheduler.get_asset(1)

        assert asset.error_count == 1

    @pytest.mark.asyncio
    async def test_asset_disabled_after_max_errors(self):
        """Test that asset is disabled after max consecutive errors."""
        async def failing_callback(asset):
            return False

        config = SchedulerConfig(max_consecutive_errors=3)
        scheduler = PremiumScheduler(config=config, process_callback=failing_callback)
        scheduler.register_asset(1, "BTC-USDT", "okx", "15m", "4h")

        # Process 3 times to hit max errors
        for _ in range(3):
            await scheduler.process_now(1)

        asset = scheduler.get_asset(1)
        assert asset.enabled is False
        assert asset.error_count == 3


class TestGlobalScheduler:
    """Test global scheduler singleton."""

    def test_get_scheduler_singleton(self):
        """Test get_scheduler returns same instance."""
        scheduler1 = get_scheduler()
        scheduler2 = get_scheduler()
        assert scheduler1 is scheduler2

    def test_get_scheduler_is_premium_scheduler(self):
        """Test get_scheduler returns PremiumScheduler instance."""
        scheduler = get_scheduler()
        assert isinstance(scheduler, PremiumScheduler)

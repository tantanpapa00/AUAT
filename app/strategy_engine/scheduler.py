# app/strategy_engine/scheduler.py
"""
Premium Strategy Scheduler - Candle-based execution timing.

Handles:
- Tracking candle close times for multiple timeframes
- Triggering strategy evaluation at candle boundaries
- Managing multiple assets with different timeframes

Architecture (PREMIUM_ENGINE_SPEC compliant):
- Scheduler triggers process_asset() at candle close
- Strategy Engine generates signals only
- Hub executes orders based on signals
"""

import asyncio
import logging
from typing import Dict, List, Optional, Set, Callable, Any
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from enum import Enum

logger = logging.getLogger(__name__)


# Timeframe to seconds mapping
TF_TO_SECONDS: Dict[str, int] = {
    "1m": 60,
    "3m": 180,
    "5m": 300,
    "15m": 900,
    "30m": 1800,
    "1h": 3600,
    "2h": 7200,
    "4h": 14400,
    "6h": 21600,
    "12h": 43200,
    "1D": 86400,
    "1W": 604800,
}


def get_tf_seconds(timeframe: str) -> int:
    """Get timeframe duration in seconds."""
    return TF_TO_SECONDS.get(timeframe, 3600)  # Default 1h


def get_current_bar_open_time(timeframe: str) -> datetime:
    """
    Get the open time of the current bar for a given timeframe.

    Args:
        timeframe: Timeframe string (e.g., "15m", "4h")

    Returns:
        datetime of current bar open (UTC)
    """
    now = datetime.now(timezone.utc)
    tf_seconds = get_tf_seconds(timeframe)

    # Calculate bar open time by flooring to timeframe boundary
    epoch_seconds = int(now.timestamp())
    bar_open_seconds = (epoch_seconds // tf_seconds) * tf_seconds

    return datetime.fromtimestamp(bar_open_seconds, tz=timezone.utc)


def get_next_bar_close_time(timeframe: str) -> datetime:
    """
    Get the close time of the current bar (= open time of next bar).

    Args:
        timeframe: Timeframe string

    Returns:
        datetime of next bar open (= current bar close) (UTC)
    """
    bar_open = get_current_bar_open_time(timeframe)
    tf_seconds = get_tf_seconds(timeframe)
    return bar_open + timedelta(seconds=tf_seconds)


def seconds_until_bar_close(timeframe: str) -> float:
    """
    Get seconds until the current bar closes.

    Args:
        timeframe: Timeframe string

    Returns:
        Seconds until bar close
    """
    now = datetime.now(timezone.utc)
    next_close = get_next_bar_close_time(timeframe)
    delta = (next_close - now).total_seconds()
    return max(0, delta)


class SchedulerState(Enum):
    """Scheduler state."""
    STOPPED = "stopped"
    RUNNING = "running"
    PAUSED = "paused"


@dataclass
class ScheduledAsset:
    """Asset scheduled for processing."""
    asset_id: int
    symbol: str
    exchange: str
    timeframe: str  # Signal timeframe
    htf_timeframe: str  # Higher timeframe
    enabled: bool = True
    last_processed: Optional[datetime] = None
    last_bar_time: Optional[datetime] = None
    error_count: int = 0
    max_errors: int = 5


@dataclass
class SchedulerConfig:
    """Scheduler configuration."""
    # Processing delays
    bar_close_delay_seconds: float = 2.0  # Wait after bar close before processing
    min_process_interval_seconds: float = 30.0  # Minimum time between processing same asset

    # Error handling
    max_consecutive_errors: int = 5  # Disable asset after this many errors
    error_backoff_seconds: float = 60.0  # Wait time after error

    # Batch processing
    max_concurrent_assets: int = 10  # Max assets to process simultaneously
    batch_interval_seconds: float = 1.0  # Interval between batches

    # Live trading control
    dry_run: bool = True  # Dry run mode - signals generated but orders not executed
    log_signals: bool = True  # Log all generated signals
    log_level: str = "INFO"  # Logging level (DEBUG, INFO, WARNING, ERROR)


@dataclass
class ProcessingStats:
    """Processing statistics for monitoring."""
    total_processed: int = 0
    total_signals: int = 0
    total_buy_signals: int = 0
    total_sell_signals: int = 0
    total_errors: int = 0
    last_error: Optional[str] = None
    last_error_time: Optional[datetime] = None
    start_time: Optional[datetime] = None


@dataclass
class SignalLog:
    """Log entry for generated signal."""
    timestamp: datetime
    asset_id: int
    symbol: str
    exchange: str
    action: str  # buy, sell, hold
    reason_code: str
    dry_run: bool
    executed: bool = False
    error: Optional[str] = None


class PremiumScheduler:
    """
    Premium Strategy Scheduler.

    Manages timing of strategy evaluation for multiple assets.
    Triggers process_asset() at candle boundaries.
    Supports dry_run mode for paper trading validation.
    """

    def __init__(
        self,
        config: Optional[SchedulerConfig] = None,
        process_callback: Optional[Callable] = None,
    ):
        """
        Initialize scheduler.

        Args:
            config: Scheduler configuration
            process_callback: Async callback for processing assets
                             Signature: async def callback(asset: ScheduledAsset) -> bool
        """
        self.config = config or SchedulerConfig()
        self.process_callback = process_callback

        self._state = SchedulerState.STOPPED
        self._assets: Dict[int, ScheduledAsset] = {}
        self._timeframe_assets: Dict[str, Set[int]] = {}  # tf -> asset_ids
        self._task: Optional[asyncio.Task] = None
        self._lock = asyncio.Lock()

        # Monitoring and logging
        self._stats = ProcessingStats()
        self._signal_history: List[SignalLog] = []
        self._max_signal_history = 1000  # Keep last 1000 signals

    @property
    def is_dry_run(self) -> bool:
        """Check if running in dry run mode."""
        return self.config.dry_run

    @property
    def stats(self) -> ProcessingStats:
        """Get processing statistics."""
        return self._stats

    @property
    def signal_history(self) -> List[SignalLog]:
        """Get signal history."""
        return self._signal_history.copy()

    @property
    def state(self) -> SchedulerState:
        """Get current scheduler state."""
        return self._state

    @property
    def asset_count(self) -> int:
        """Get number of registered assets."""
        return len(self._assets)

    @property
    def active_timeframes(self) -> List[str]:
        """Get list of active timeframes."""
        return list(self._timeframe_assets.keys())

    def register_asset(
        self,
        asset_id: int,
        symbol: str,
        exchange: str,
        timeframe: str,
        htf_timeframe: str,
        enabled: bool = True,
    ) -> bool:
        """
        Register an asset for scheduled processing.

        Args:
            asset_id: Asset ID
            symbol: Trading symbol
            exchange: Exchange name
            timeframe: Signal timeframe
            htf_timeframe: Higher timeframe
            enabled: Whether to process this asset

        Returns:
            True if registered successfully
        """
        if asset_id in self._assets:
            logger.warning(f"Asset {asset_id} already registered, updating")

        asset = ScheduledAsset(
            asset_id=asset_id,
            symbol=symbol,
            exchange=exchange,
            timeframe=timeframe,
            htf_timeframe=htf_timeframe,
            enabled=enabled,
        )

        self._assets[asset_id] = asset

        # Track by timeframe
        if timeframe not in self._timeframe_assets:
            self._timeframe_assets[timeframe] = set()
        self._timeframe_assets[timeframe].add(asset_id)

        logger.info(f"Registered asset {asset_id} ({symbol}) with TF={timeframe}")
        return True

    def unregister_asset(self, asset_id: int) -> bool:
        """
        Unregister an asset.

        Args:
            asset_id: Asset ID to remove

        Returns:
            True if removed successfully
        """
        if asset_id not in self._assets:
            return False

        asset = self._assets.pop(asset_id)

        # Remove from timeframe tracking
        if asset.timeframe in self._timeframe_assets:
            self._timeframe_assets[asset.timeframe].discard(asset_id)
            if not self._timeframe_assets[asset.timeframe]:
                del self._timeframe_assets[asset.timeframe]

        logger.info(f"Unregistered asset {asset_id}")
        return True

    def enable_asset(self, asset_id: int) -> bool:
        """Enable an asset for processing."""
        if asset_id not in self._assets:
            return False
        self._assets[asset_id].enabled = True
        self._assets[asset_id].error_count = 0  # Reset errors
        return True

    def disable_asset(self, asset_id: int) -> bool:
        """Disable an asset from processing."""
        if asset_id not in self._assets:
            return False
        self._assets[asset_id].enabled = False
        return True

    def get_asset(self, asset_id: int) -> Optional[ScheduledAsset]:
        """Get asset by ID."""
        return self._assets.get(asset_id)

    def get_assets_for_timeframe(self, timeframe: str) -> List[ScheduledAsset]:
        """Get all enabled assets for a timeframe."""
        asset_ids = self._timeframe_assets.get(timeframe, set())
        return [
            self._assets[aid]
            for aid in asset_ids
            if aid in self._assets and self._assets[aid].enabled
        ]

    async def start(self):
        """Start the scheduler."""
        if self._state == SchedulerState.RUNNING:
            logger.warning("Scheduler already running")
            return

        self._state = SchedulerState.RUNNING
        self._stats.start_time = datetime.now(timezone.utc)
        self._task = asyncio.create_task(self._run_loop())

        mode = "DRY-RUN (paper trading)" if self.config.dry_run else "LIVE"
        logger.warning(f"Scheduler started in {mode} mode with {len(self._assets)} assets")

    async def stop(self):
        """Stop the scheduler."""
        if self._state == SchedulerState.STOPPED:
            return

        self._state = SchedulerState.STOPPED

        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None

        logger.info("Scheduler stopped")

    async def pause(self):
        """Pause the scheduler."""
        if self._state == SchedulerState.RUNNING:
            self._state = SchedulerState.PAUSED
            logger.info("Scheduler paused")

    async def resume(self):
        """Resume the scheduler."""
        if self._state == SchedulerState.PAUSED:
            self._state = SchedulerState.RUNNING
            logger.info("Scheduler resumed")

    async def _run_loop(self):
        """Main scheduler loop."""
        logger.info("Scheduler loop started")

        while self._state != SchedulerState.STOPPED:
            try:
                if self._state == SchedulerState.PAUSED:
                    await asyncio.sleep(1)
                    continue

                # Find next bar close time across all timeframes
                next_wake = await self._get_next_wake_time()

                if next_wake is None:
                    # No assets registered, sleep and retry
                    await asyncio.sleep(5)
                    continue

                # Sleep until next bar close + delay
                now = datetime.now(timezone.utc)
                sleep_seconds = (next_wake - now).total_seconds()

                if sleep_seconds > 0:
                    logger.debug(f"Sleeping {sleep_seconds:.1f}s until next bar close")
                    await asyncio.sleep(min(sleep_seconds, 60))  # Wake up at least every minute
                    continue

                # Process assets whose bars have closed
                await self._process_due_assets()

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Scheduler loop error: {e}")
                await asyncio.sleep(5)

        logger.info("Scheduler loop ended")

    async def _get_next_wake_time(self) -> Optional[datetime]:
        """Get the next time the scheduler should wake up."""
        if not self._timeframe_assets:
            return None

        next_times = []
        for tf in self._timeframe_assets:
            close_time = get_next_bar_close_time(tf)
            wake_time = close_time + timedelta(seconds=self.config.bar_close_delay_seconds)
            next_times.append(wake_time)

        return min(next_times) if next_times else None

    async def _process_due_assets(self):
        """Process all assets whose bars have closed."""
        now = datetime.now(timezone.utc)

        # Find assets ready for processing
        due_assets = []
        for tf, asset_ids in self._timeframe_assets.items():
            bar_close = get_next_bar_close_time(tf) - timedelta(seconds=get_tf_seconds(tf))

            for asset_id in asset_ids:
                asset = self._assets.get(asset_id)
                if not asset or not asset.enabled:
                    continue

                # Skip if already processed this bar
                if asset.last_bar_time and asset.last_bar_time >= bar_close:
                    continue

                # Skip if processed too recently
                if asset.last_processed:
                    since_last = (now - asset.last_processed).total_seconds()
                    if since_last < self.config.min_process_interval_seconds:
                        continue

                due_assets.append(asset)

        if not due_assets:
            return

        logger.info(f"Processing {len(due_assets)} due assets")

        # Process in batches
        for i in range(0, len(due_assets), self.config.max_concurrent_assets):
            batch = due_assets[i:i + self.config.max_concurrent_assets]
            tasks = [self._process_asset(asset) for asset in batch]
            await asyncio.gather(*tasks, return_exceptions=True)

            if i + self.config.max_concurrent_assets < len(due_assets):
                await asyncio.sleep(self.config.batch_interval_seconds)

    async def _process_asset(self, asset: ScheduledAsset):
        """Process a single asset with comprehensive logging."""
        now = datetime.now(timezone.utc)
        dry_run_prefix = "[DRY-RUN] " if self.config.dry_run else ""

        try:
            logger.info(
                f"{dry_run_prefix}Processing asset {asset.asset_id} "
                f"({asset.symbol}@{asset.exchange}) TF={asset.timeframe}"
            )

            result = None
            if self.process_callback:
                result = await self.process_callback(asset)
                success = result is not False  # Allow True or signal data
            else:
                # No callback, just mark as processed
                success = True

            # Update tracking
            asset.last_processed = now
            asset.last_bar_time = get_current_bar_open_time(asset.timeframe)
            self._stats.total_processed += 1

            if success:
                asset.error_count = 0

                # Log signal if returned
                if result and isinstance(result, dict):
                    self._log_signal(asset, result, now)
            else:
                asset.error_count += 1

            logger.info(
                f"{dry_run_prefix}Completed asset {asset.asset_id} "
                f"({asset.symbol}) success={success}"
            )

        except Exception as e:
            error_msg = str(e)
            logger.error(
                f"{dry_run_prefix}Error processing asset {asset.asset_id} "
                f"({asset.symbol}): {error_msg}"
            )
            asset.error_count += 1
            self._stats.total_errors += 1
            self._stats.last_error = error_msg
            self._stats.last_error_time = now

        # Disable if too many errors
        if asset.error_count >= self.config.max_consecutive_errors:
            logger.warning(
                f"{dry_run_prefix}Disabling asset {asset.asset_id} "
                f"after {asset.error_count} consecutive errors"
            )
            asset.enabled = False

    def _log_signal(self, asset: ScheduledAsset, result: dict, timestamp: datetime):
        """Log a generated signal to history."""
        action = result.get("action", "hold")
        reason_code = result.get("reason_code", "UNKNOWN")

        signal_log = SignalLog(
            timestamp=timestamp,
            asset_id=asset.asset_id,
            symbol=asset.symbol,
            exchange=asset.exchange,
            action=action,
            reason_code=reason_code,
            dry_run=self.config.dry_run,
            executed=not self.config.dry_run and action != "hold",
        )

        # Update stats
        self._stats.total_signals += 1
        if action == "buy":
            self._stats.total_buy_signals += 1
        elif action == "sell":
            self._stats.total_sell_signals += 1

        # Add to history (with size limit)
        self._signal_history.append(signal_log)
        if len(self._signal_history) > self._max_signal_history:
            self._signal_history = self._signal_history[-self._max_signal_history:]

        # Log the signal
        if self.config.log_signals:
            dry_run_tag = "[DRY-RUN]" if self.config.dry_run else "[LIVE]"
            logger.info(
                f"{dry_run_tag} SIGNAL: {asset.symbol}@{asset.exchange} "
                f"action={action} reason={reason_code}"
            )

    async def process_now(self, asset_id: int) -> bool:
        """
        Immediately process an asset (manual trigger).

        Args:
            asset_id: Asset to process

        Returns:
            True if processed successfully
        """
        asset = self._assets.get(asset_id)
        if not asset:
            return False

        await self._process_asset(asset)
        return asset.error_count == 0

    def get_status(self) -> Dict[str, Any]:
        """Get scheduler status with monitoring data."""
        return {
            "state": self._state.value,
            "dry_run": self.config.dry_run,
            "asset_count": len(self._assets),
            "active_timeframes": list(self._timeframe_assets.keys()),
            "stats": {
                "total_processed": self._stats.total_processed,
                "total_signals": self._stats.total_signals,
                "total_buy_signals": self._stats.total_buy_signals,
                "total_sell_signals": self._stats.total_sell_signals,
                "total_errors": self._stats.total_errors,
                "last_error": self._stats.last_error,
                "last_error_time": self._stats.last_error_time.isoformat() if self._stats.last_error_time else None,
                "start_time": self._stats.start_time.isoformat() if self._stats.start_time else None,
            },
            "assets": [
                {
                    "asset_id": a.asset_id,
                    "symbol": a.symbol,
                    "exchange": a.exchange,
                    "timeframe": a.timeframe,
                    "enabled": a.enabled,
                    "error_count": a.error_count,
                    "last_processed": a.last_processed.isoformat() if a.last_processed else None,
                }
                for a in self._assets.values()
            ],
        }

    def reset_stats(self):
        """Reset processing statistics."""
        self._stats = ProcessingStats()
        self._signal_history.clear()
        logger.info("Scheduler stats reset")

    def set_dry_run(self, enabled: bool):
        """Enable or disable dry run mode."""
        old_mode = self.config.dry_run
        self.config.dry_run = enabled
        logger.warning(
            f"Dry run mode changed: {old_mode} -> {enabled} "
            f"({'PAPER TRADING' if enabled else 'LIVE TRADING'})"
        )

    def get_recent_signals(self, limit: int = 50) -> List[Dict[str, Any]]:
        """Get recent signal history."""
        recent = self._signal_history[-limit:]
        return [
            {
                "timestamp": s.timestamp.isoformat(),
                "asset_id": s.asset_id,
                "symbol": s.symbol,
                "exchange": s.exchange,
                "action": s.action,
                "reason_code": s.reason_code,
                "dry_run": s.dry_run,
                "executed": s.executed,
                "error": s.error,
            }
            for s in reversed(recent)
        ]


# Global scheduler instance
_global_scheduler: Optional[PremiumScheduler] = None


def get_scheduler() -> PremiumScheduler:
    """Get the global scheduler instance."""
    global _global_scheduler
    if _global_scheduler is None:
        _global_scheduler = PremiumScheduler()
    return _global_scheduler


def set_scheduler(scheduler: PremiumScheduler):
    """Set the global scheduler instance."""
    global _global_scheduler
    _global_scheduler = scheduler

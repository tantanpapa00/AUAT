# scripts/validate_live.py
"""
Live Trading Validation Script for MR Premium Strategy Engine.

Phase 6: Validates signal generation against expected behavior.
Can run in parallel with dry-run mode to verify signals.

Usage:
    python scripts/validate_live.py --symbol BTC-USDT --exchange okx --duration 24h
    python scripts/validate_live.py --config config.json --duration 1h --dry-run
"""

import asyncio
import argparse
import json
import logging
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, asdict

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from app.strategy_engine.scheduler import (
    PremiumScheduler,
    SchedulerConfig,
    ScheduledAsset,
    get_tf_seconds,
)
from app.strategy_engine.models import MRConfig, StrategyState
from app.strategy_engine.hub_integration import process_asset
from app.strategy_engine.position_manager import PositionInfo

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler("validate_live.log"),
    ],
)
logger = logging.getLogger("validate_live")


@dataclass
class ValidationResult:
    """Result of a validation run."""
    start_time: datetime
    end_time: datetime
    duration_seconds: float
    total_checks: int
    signals_generated: int
    buy_signals: int
    sell_signals: int
    errors: int
    assets_validated: List[str]
    signal_log: List[Dict[str, Any]]
    dry_run: bool
    success: bool
    message: str


class LiveValidator:
    """Validates live signal generation."""

    def __init__(
        self,
        dry_run: bool = True,
        log_file: Optional[str] = None,
    ):
        self.dry_run = dry_run
        self.log_file = log_file or "validation_signals.jsonl"

        self.scheduler: Optional[PremiumScheduler] = None
        self.configs: Dict[int, MRConfig] = {}
        self.states: Dict[int, StrategyState] = {}
        self.signals: List[Dict[str, Any]] = []
        self.errors: List[str] = []
        self._running = False

    async def setup(self, assets: List[Dict[str, Any]]):
        """Setup validator with assets to monitor."""
        config = SchedulerConfig(
            dry_run=self.dry_run,
            log_signals=True,
            bar_close_delay_seconds=3.0,
        )

        self.scheduler = PremiumScheduler(
            config=config,
            process_callback=self._process_asset_callback,
        )

        for asset_info in assets:
            asset_id = asset_info["asset_id"]
            self.scheduler.register_asset(
                asset_id=asset_id,
                symbol=asset_info["symbol"],
                exchange=asset_info["exchange"],
                timeframe=asset_info.get("timeframe", "1h"),
                htf_timeframe=asset_info.get("htf_timeframe", "4h"),
                enabled=True,
            )

            # Setup config and state
            self.configs[asset_id] = MRConfig(
                signal_tf=asset_info.get("timeframe", "1h"),
                htf_tf=asset_info.get("htf_timeframe", "4h"),
                osc_preset=asset_info.get("osc_preset", "preset1"),
            )
            self.states[asset_id] = StrategyState()

        logger.info(f"Validator setup with {len(assets)} assets (dry_run={self.dry_run})")

    async def _process_asset_callback(self, asset: ScheduledAsset) -> Any:
        """Process callback for scheduler."""
        try:
            config = self.configs.get(asset.asset_id, MRConfig())
            state = self.states.get(asset.asset_id, StrategyState())

            # Create mock position (no actual position in validation)
            position = PositionInfo(
                symbol=asset.symbol,
                exchange=asset.exchange,
                quantity=0.0,
                avg_price=0.0,
                market_price=0.0,
                market_value=0.0,
                unrealized_pnl=0.0,
                unrealized_pnl_pct=0.0,
            )

            # Process asset
            signal_event, snapshot, new_state = await process_asset(
                asset_id=asset.asset_id,
                symbol=asset.symbol,
                exchange=asset.exchange,
                config=config,
                state=state,
                position=position,
                equity=10000.0,  # Mock equity
            )

            # Update state
            if new_state:
                self.states[asset.asset_id] = new_state

            # Log signal
            if signal_event:
                signal_data = {
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "asset_id": asset.asset_id,
                    "symbol": asset.symbol,
                    "exchange": asset.exchange,
                    "action": signal_event.action,
                    "side": signal_event.side,
                    "reason_code": signal_event.reason_code,
                    "reason_text": signal_event.reason_text,
                    "regime": signal_event.regime,
                    "dry_run": self.dry_run,
                }
                self.signals.append(signal_data)
                self._write_signal_log(signal_data)

                logger.info(
                    f"[{'DRY-RUN' if self.dry_run else 'LIVE'}] "
                    f"Signal: {asset.symbol} {signal_event.action} "
                    f"({signal_event.reason_code})"
                )

                return {
                    "action": signal_event.action,
                    "reason_code": signal_event.reason_code,
                }

            return {"action": "hold", "reason_code": "NO_SIGNAL"}

        except Exception as e:
            error_msg = f"Error processing {asset.symbol}: {e}"
            logger.error(error_msg)
            self.errors.append(error_msg)
            return False

    def _write_signal_log(self, signal_data: Dict[str, Any]):
        """Append signal to log file."""
        try:
            with open(self.log_file, "a") as f:
                f.write(json.dumps(signal_data) + "\n")
        except Exception as e:
            logger.error(f"Failed to write signal log: {e}")

    async def run(self, duration_seconds: float) -> ValidationResult:
        """Run validation for specified duration."""
        start_time = datetime.now(timezone.utc)
        self._running = True

        logger.info(f"Starting validation for {duration_seconds}s")
        logger.info(f"Mode: {'DRY-RUN' if self.dry_run else 'LIVE'}")

        await self.scheduler.start()

        # Run for duration
        try:
            await asyncio.sleep(duration_seconds)
        except asyncio.CancelledError:
            logger.info("Validation cancelled")
        finally:
            await self.scheduler.stop()
            self._running = False

        end_time = datetime.now(timezone.utc)

        # Calculate results
        buy_signals = len([s for s in self.signals if s["action"] == "buy"])
        sell_signals = len([s for s in self.signals if s["action"] == "sell"])

        result = ValidationResult(
            start_time=start_time,
            end_time=end_time,
            duration_seconds=(end_time - start_time).total_seconds(),
            total_checks=self.scheduler.stats.total_processed,
            signals_generated=len(self.signals),
            buy_signals=buy_signals,
            sell_signals=sell_signals,
            errors=len(self.errors),
            assets_validated=[
                f"{a.symbol}@{a.exchange}"
                for a in self.scheduler._assets.values()
            ],
            signal_log=self.signals,
            dry_run=self.dry_run,
            success=len(self.errors) == 0,
            message="Validation completed successfully" if not self.errors else f"{len(self.errors)} errors occurred",
        )

        return result

    async def stop(self):
        """Stop validation."""
        self._running = False
        if self.scheduler:
            await self.scheduler.stop()


def parse_duration(duration_str: str) -> float:
    """Parse duration string like '1h', '30m', '24h' to seconds."""
    unit = duration_str[-1].lower()
    value = float(duration_str[:-1])

    if unit == "s":
        return value
    elif unit == "m":
        return value * 60
    elif unit == "h":
        return value * 3600
    elif unit == "d":
        return value * 86400
    else:
        raise ValueError(f"Invalid duration unit: {unit}")


async def main():
    parser = argparse.ArgumentParser(description="MR Premium Strategy Live Validator")
    parser.add_argument("--symbol", type=str, help="Symbol to validate (e.g., BTC-USDT)")
    parser.add_argument("--exchange", type=str, default="okx", help="Exchange")
    parser.add_argument("--timeframe", type=str, default="1h", help="Timeframe")
    parser.add_argument("--htf", type=str, default="4h", help="Higher timeframe")
    parser.add_argument("--config", type=str, help="Config file path (JSON)")
    parser.add_argument("--duration", type=str, default="1h", help="Duration (e.g., 1h, 30m)")
    parser.add_argument("--dry-run", action="store_true", default=True, help="Dry run mode")
    parser.add_argument("--live", action="store_true", help="Live mode (disables dry-run)")
    parser.add_argument("--output", type=str, default="validation_result.json", help="Output file")

    args = parser.parse_args()

    # Determine dry run mode
    dry_run = not args.live

    # Build asset list
    assets = []
    if args.config:
        with open(args.config) as f:
            config_data = json.load(f)
            assets = config_data.get("assets", [])
    elif args.symbol:
        assets = [{
            "asset_id": 1,
            "symbol": args.symbol,
            "exchange": args.exchange,
            "timeframe": args.timeframe,
            "htf_timeframe": args.htf,
        }]
    else:
        # Default test asset
        assets = [{
            "asset_id": 1,
            "symbol": "BTC-USDT",
            "exchange": "okx",
            "timeframe": "1h",
            "htf_timeframe": "4h",
        }]

    # Parse duration
    duration = parse_duration(args.duration)

    # Run validation
    validator = LiveValidator(dry_run=dry_run)
    await validator.setup(assets)

    print(f"\n{'='*60}")
    print(f"MR Premium Strategy Live Validator")
    print(f"{'='*60}")
    print(f"Mode: {'DRY-RUN (paper trading)' if dry_run else 'LIVE'}")
    print(f"Duration: {args.duration} ({duration}s)")
    print(f"Assets: {len(assets)}")
    for asset in assets:
        print(f"  - {asset['symbol']}@{asset['exchange']} TF={asset['timeframe']}")
    print(f"{'='*60}\n")

    result = await validator.run(duration)

    # Print results
    print(f"\n{'='*60}")
    print("VALIDATION RESULTS")
    print(f"{'='*60}")
    print(f"Duration: {result.duration_seconds:.1f}s")
    print(f"Total Checks: {result.total_checks}")
    print(f"Signals Generated: {result.signals_generated}")
    print(f"  - Buy: {result.buy_signals}")
    print(f"  - Sell: {result.sell_signals}")
    print(f"Errors: {result.errors}")
    print(f"Status: {'SUCCESS' if result.success else 'FAILED'}")
    print(f"{'='*60}\n")

    # Save result
    result_dict = asdict(result)
    result_dict["start_time"] = result.start_time.isoformat()
    result_dict["end_time"] = result.end_time.isoformat()

    with open(args.output, "w") as f:
        json.dump(result_dict, f, indent=2)

    print(f"Results saved to: {args.output}")
    print(f"Signal log saved to: validation_signals.jsonl")


if __name__ == "__main__":
    asyncio.run(main())

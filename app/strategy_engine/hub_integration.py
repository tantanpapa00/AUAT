# app/strategy_engine/hub_integration.py
"""
Hub Integration - Connect Premium signals to order execution.

This module bridges the Strategy Engine (signal generation) with
the Hub (order execution). Following PREMIUM_ENGINE_SPEC:
- Premium Engine generates signals only
- Hub executes orders based on signals

Flow:
1. Scheduler calls process_asset()
2. Fetch candles + calculate indicators
3. Generate signal
4. If signal, create signal_event and pass to Hub
5. Hub executes order via connector
"""

from typing import Optional, Dict, Any, Tuple
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
import logging
import uuid
import hashlib

import numpy as np

from .models import (
    SignalResult,
    StrategyState,
    MRConfig,
    HTFIndicators,
    OscillatorData,
)
from .indicators import calc_spo
from .regime_detector import detect_regime, calc_htf_indicators
from .signal_generator import (
    calc_osc_data,
    generate_mr_signal,
    update_state_after_execution,
)
from .position_manager import (
    PositionInfo,
    OrderQuantity,
    calculate_buy_quantity,
    calculate_sell_quantity,
    calculate_position_info,
)
from .candle_fetcher import CandleData, get_candle_cache
from .presets import OSC_PRESETS, HTF_DEFAULTS

logger = logging.getLogger(__name__)


@dataclass
class SignalEvent:
    """
    Signal event for Hub processing.

    Matches PREMIUM_ENGINE_SPEC.md schema.
    """
    # Required fields (no defaults)
    signal_id: str
    asset_id: int
    symbol: str
    exchange: str
    side: str           # "entry" or "exit"
    action: str         # "buy" or "sell"
    premium_mode: str   # "mr" for mean reversion
    reason_code: str
    reason_text: str
    snapshot_id: str
    tf: str

    # Optional fields (with defaults)
    market: str = "spot"
    params_version: str = "v1.0"
    tf_warning: bool = False
    price_hint: Optional[float] = None
    tranche: Optional[int] = None
    tranche_pct: Optional[float] = None
    regime: Optional[int] = None
    ts: int = 0
    created_at: Optional[datetime] = None


@dataclass
class SignalSnapshot:
    """
    Snapshot of signal context for audit trail.

    Matches PREMIUM_ENGINE_SPEC.md schema.
    """
    snapshot_id: str
    signal_id: str
    asset_id: int
    symbol: str
    exchange: str

    ts: int
    tf: str

    ohlcv: Dict[str, float]
    indicators: Dict[str, Any]

    premium_mode: str
    params_version: str
    reason_code: str
    reason_text: str

    created_at: datetime


def generate_signal_id(asset_id: int, ts: int) -> str:
    """Generate unique signal ID."""
    random_part = uuid.uuid4().hex[:8]
    return f"sig_{asset_id}_{ts}_{random_part}"


def generate_snapshot_id(asset_id: int, ts: int) -> str:
    """Generate unique snapshot ID."""
    random_part = uuid.uuid4().hex[:8]
    return f"snap_{asset_id}_{ts}_{random_part}"


async def process_asset(
    asset_id: int,
    symbol: str,
    exchange: str,
    config: MRConfig,
    state: StrategyState,
    position: PositionInfo,
    equity: float,
) -> Tuple[Optional[SignalEvent], Optional[SignalSnapshot], StrategyState]:
    """
    Process a single asset for signal generation.

    This is the main entry point called by the scheduler.

    Args:
        asset_id: Asset ID
        symbol: Trading symbol (e.g., "BTC-USDT")
        exchange: Exchange name
        config: Strategy configuration
        state: Current strategy state
        position: Current position info
        equity: Account equity

    Returns:
        Tuple of (signal_event, snapshot, updated_state)
    """
    cache = get_candle_cache()
    current_ts = int(datetime.now(timezone.utc).timestamp() * 1000)

    # 1. Fetch signal timeframe candles
    signal_tf = config.signal_tf
    signal_candles = await cache.get_candles(
        exchange=exchange,
        symbol=symbol,
        timeframe=signal_tf,
        count=350,  # Need enough for SPO calculation (bb_len=250)
    )

    if signal_candles.count < 100:
        logger.warning(f"Insufficient candles for {symbol}: {signal_candles.count}")
        return None, None, state

    # 2. Fetch HTF candles
    htf_tf = config.htf_tf
    htf_candles = await cache.get_candles(
        exchange=exchange,
        symbol=symbol,
        timeframe=htf_tf,
        count=250,  # Need enough for VWMA200
    )

    if htf_candles.count < 50:
        logger.warning(f"Insufficient HTF candles for {symbol}: {htf_candles.count}")
        return None, None, state

    # 3. Calculate oscillator data (signal TF)
    osc_preset = config.osc_preset
    osc_data = calc_osc_data(signal_candles.closes, preset=osc_preset)

    # 4. Calculate HTF indicators
    htf_indicators = calc_htf_indicators(
        high=htf_candles.highs,
        low=htf_candles.lows,
        close=htf_candles.closes,
        volume=htf_candles.volumes,
        vwma50_len=HTF_DEFAULTS["vwma50_len"],
        vwma200_len=HTF_DEFAULTS["vwma200_len"],
        hull_len=HTF_DEFAULTS["hull_len"],
        ichi_tenkan=HTF_DEFAULTS["ichi_tenkan"],
        ichi_kijun=HTF_DEFAULTS["ichi_kijun"],
        ichi_senkou=HTF_DEFAULTS["ichi_senkou"],
        st_atr_len=HTF_DEFAULTS["st_atr_len"],
        st_factor=HTF_DEFAULTS["st_factor"],
    )

    # 5. Detect regime
    regime = detect_regime(htf_indicators, use_4regime=config.use_4regime)

    # 6. Generate signal
    signal_result, new_state = generate_mr_signal(
        close=signal_candles.closes,
        high=signal_candles.highs,
        low=signal_candles.lows,
        osc_data=osc_data,
        htf_indicators=htf_indicators,
        regime=regime,
        state=state,
        config=config,
        has_position=position.has_position,
        position_qty=position.quantity,
        avg_price=position.avg_price if position.has_position else None,
        current_ts=current_ts,
    )

    # 7. If no actionable signal, return early
    if signal_result.action == "none":
        return None, None, new_state

    # 8. Create signal event and snapshot
    signal_id = generate_signal_id(asset_id, current_ts)
    snapshot_id = generate_snapshot_id(asset_id, current_ts)

    # Determine side
    side = "entry" if signal_result.is_buy else "exit"

    # TF warning for short timeframes
    tf_warning = signal_tf in ["1m", "3m", "5m"]

    # Current candle OHLCV
    ohlcv = {
        "o": float(signal_candles.opens[-1]),
        "h": float(signal_candles.highs[-1]),
        "l": float(signal_candles.lows[-1]),
        "c": float(signal_candles.closes[-1]),
        "v": float(signal_candles.volumes[-1]),
    }

    # Indicator snapshot
    indicators = {
        "normalized_osc": osc_data.normalized_osc,
        "upper_band": osc_data.upper_band,
        "lower_band": osc_data.lower_band,
        "threshold": osc_data.threshold,
        "regime": regime,
        "vwma50": htf_indicators.vwma50,
        "vwma200": htf_indicators.vwma200,
        "hull": htf_indicators.hull,
        "hull_dn": htf_indicators.hull_dn,
        "st_direction": htf_indicators.st_direction,
        "senkou_b": htf_indicators.senkou_b,
    }

    signal_event = SignalEvent(
        signal_id=signal_id,
        asset_id=asset_id,
        symbol=symbol,
        exchange=exchange,
        market="spot",
        side=side,
        action=signal_result.action,
        premium_mode="mr",
        params_version="v1.0",
        reason_code=signal_result.reason_code,
        reason_text=signal_result.reason_text,
        snapshot_id=snapshot_id,
        tf=signal_tf,
        tf_warning=tf_warning,
        price_hint=signal_result.price_hint,
        tranche=signal_result.tranche,
        tranche_pct=signal_result.tranche_pct,
        regime=regime,
        ts=current_ts,
        created_at=datetime.now(timezone.utc),
    )

    snapshot = SignalSnapshot(
        snapshot_id=snapshot_id,
        signal_id=signal_id,
        asset_id=asset_id,
        symbol=symbol,
        exchange=exchange,
        ts=current_ts,
        tf=signal_tf,
        ohlcv=ohlcv,
        indicators=indicators,
        premium_mode="mr",
        params_version="v1.0",
        reason_code=signal_result.reason_code,
        reason_text=signal_result.reason_text,
        created_at=datetime.now(timezone.utc),
    )

    logger.info(
        f"Signal generated: {signal_id} | {symbol} | {signal_result.action} | "
        f"{signal_result.reason_code} | R{regime}"
    )

    return signal_event, snapshot, new_state


def signal_to_order_request(
    signal_event: SignalEvent,
    config: MRConfig,
    position: PositionInfo,
    equity: float,
    market_price: float,
) -> Optional[Dict[str, Any]]:
    """
    Convert signal event to order request.

    This is called by Hub after receiving a signal.

    Args:
        signal_event: The signal event
        config: Strategy configuration
        position: Current position
        equity: Account equity
        market_price: Current market price

    Returns:
        Order request dict or None if order should not be placed
    """
    # Create a minimal SignalResult for quantity calculation
    signal_result = SignalResult(
        action=signal_event.action,
        reason_code=signal_event.reason_code,
        reason_text=signal_event.reason_text,
        regime=signal_event.regime or 0,
        tranche=signal_event.tranche or 1,
        tranche_pct=signal_event.tranche_pct or 0.0,
    )

    if signal_event.action == "buy":
        available_cash = max(0, equity - position.market_value)

        order_qty = calculate_buy_quantity(
            signal=signal_result,
            config=config,
            available_cash=available_cash,
            current_position_value=position.market_value,
            equity=equity,
            market_price=market_price,
        )

        if order_qty.qty <= 0:
            logger.info(f"Buy quantity is 0: {order_qty.reason}")
            return None

        return {
            "asset_id": signal_event.asset_id,
            "symbol": signal_event.symbol,
            "exchange": signal_event.exchange,
            "side": "buy",
            "order_type": "market",
            "qty": order_qty.qty,
            "notional": order_qty.notional,
            "reason_code": signal_event.reason_code,
            "reason_text": signal_event.reason_text,
            "snapshot_id": signal_event.snapshot_id,
            "signal_id": signal_event.signal_id,
        }

    elif signal_event.action == "sell":
        order_qty = calculate_sell_quantity(
            signal=signal_result,
            config=config,
            position_qty=position.quantity,
            market_price=market_price,
        )

        if order_qty.qty <= 0:
            logger.info(f"Sell quantity is 0: {order_qty.reason}")
            return None

        return {
            "asset_id": signal_event.asset_id,
            "symbol": signal_event.symbol,
            "exchange": signal_event.exchange,
            "side": "sell",
            "order_type": "market",
            "qty": order_qty.qty,
            "notional": order_qty.notional,
            "reason_code": signal_event.reason_code,
            "reason_text": signal_event.reason_text,
            "snapshot_id": signal_event.snapshot_id,
            "signal_id": signal_event.signal_id,
        }

    return None


async def save_signal_event(
    signal_event: SignalEvent,
    snapshot: SignalSnapshot,
    db_session,
) -> bool:
    """
    Save signal event and snapshot to database.

    Args:
        signal_event: Signal event
        snapshot: Signal snapshot
        db_session: Database session

    Returns:
        True if saved successfully
    """
    try:
        # This would use the actual DB models
        # For now, just log
        logger.info(f"Saving signal: {signal_event.signal_id}")
        logger.info(f"Saving snapshot: {snapshot.snapshot_id}")

        # TODO: Implement actual DB save when models are ready
        # db_session.add(SignalEventModel(**asdict(signal_event)))
        # db_session.add(SignalSnapshotModel(**asdict(snapshot)))
        # db_session.commit()

        return True

    except Exception as e:
        logger.error(f"Failed to save signal: {e}")
        return False

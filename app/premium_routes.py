# app/premium_routes.py
"""
Premium Strategy API Routes.

FastAPI router for premium strategy management:
- Premium config CRUD
- Strategy state management
- Scheduler control
- Manual signal triggers

Architecture (PREMIUM_ENGINE_SPEC compliant):
- API routes for premium strategy configuration
- Scheduler management endpoints
- Signal generation triggers (no order execution here)
"""

from fastapi import APIRouter, Depends, HTTPException, Query, BackgroundTasks
from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
from datetime import datetime, timezone
import logging

from sqlalchemy.orm import Session
from sqlalchemy import text

logger = logging.getLogger(__name__)

# Create router
router = APIRouter(prefix="/api/premium", tags=["premium"])


# ============================================================================
# Pydantic Models
# ============================================================================

class PremiumConfigBase(BaseModel):
    """Base premium config model."""
    signal_tf: str = Field(default="15m", description="Signal timeframe")
    htf_tf: str = Field(default="4h", description="Higher timeframe")
    osc_preset: str = Field(default="preset1", description="Oscillator preset")

    # Position sizing
    cash_use_pct: float = Field(default=90.0, ge=0, le=100)
    hard_cap_pct: float = Field(default=95.0, ge=0, le=100)
    min_profit_pct: float = Field(default=0.5, ge=0, le=100)

    # Tranches
    buy_tranches: List[int] = Field(default=[25, 50, 75, 100])
    sell_tranches: List[int] = Field(default=[50, 100])
    buy_after_max: str = Field(default="extend")  # extend, cycle, stop
    sell_after_max: str = Field(default="extend")
    buy_stage_1_only: bool = Field(default=False)
    sell_stage_1_only: bool = Field(default=False)

    # Filters
    use_lower_band_filter: bool = Field(default=True)
    use_below_avg_filter: bool = Field(default=True)
    use_prev_signal_filter: bool = Field(default=True)
    use_prev_exec_filter: bool = Field(default=True)

    # Regime settings
    use_4regime: bool = Field(default=True)
    r1_pullback_enabled: bool = Field(default=True)
    r3_breakout_enabled: bool = Field(default=True)

    # Misc
    one_trade_per_bar: bool = Field(default=True)


class PremiumConfigCreate(PremiumConfigBase):
    """Model for creating premium config."""
    asset_id: int


class PremiumConfigUpdate(PremiumConfigBase):
    """Model for updating premium config."""
    pass


class PremiumConfigResponse(PremiumConfigBase):
    """Response model for premium config."""
    id: int
    asset_id: int
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class StrategyStateResponse(BaseModel):
    """Response model for strategy state."""
    id: int
    asset_id: int
    buy_stage: int = 0
    sell_stage: int = 0
    last_buy_signal_price: Optional[float] = None
    last_sell_signal_price: Optional[float] = None
    last_buy_exec_price: Optional[float] = None
    last_sell_exec_price: Optional[float] = None
    r1_pullback_active: bool = False
    r3_breakout_active: bool = False
    updated_at: Optional[datetime] = None


class SchedulerStatusResponse(BaseModel):
    """Response model for scheduler status."""
    state: str
    asset_count: int
    active_timeframes: List[str]
    assets: List[Dict[str, Any]]


class SignalTriggerRequest(BaseModel):
    """Request model for manual signal trigger."""
    asset_id: int


class SignalTriggerResponse(BaseModel):
    """Response model for signal trigger."""
    success: bool
    signal_id: Optional[str] = None
    action: Optional[str] = None
    reason_code: Optional[str] = None
    message: Optional[str] = None


# ============================================================================
# Dependency: Get DB Session
# ============================================================================

def get_db():
    """Get database session - imported from main app."""
    from .db import SessionLocal
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# ============================================================================
# Premium Config Endpoints
# ============================================================================

@router.get("/configs", response_model=List[PremiumConfigResponse])
async def list_premium_configs(
    db: Session = Depends(get_db),
    limit: int = Query(default=100, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
):
    """List all premium configs."""
    result = db.execute(
        text("""
            SELECT id, asset_id, signal_tf, htf_tf, osc_preset,
                   cash_use_pct, hard_cap_pct, min_profit_pct,
                   buy_tranches, sell_tranches,
                   buy_after_max, sell_after_max,
                   buy_stage_1_only, sell_stage_1_only,
                   use_lower_band_filter, use_below_avg_filter,
                   use_prev_signal_filter, use_prev_exec_filter,
                   use_4regime, r1_pullback_enabled, r3_breakout_enabled,
                   one_trade_per_bar, created_at, updated_at
            FROM premium_configs
            ORDER BY id DESC
            LIMIT :limit OFFSET :offset
        """),
        {"limit": limit, "offset": offset},
    )
    rows = result.fetchall()

    configs = []
    for row in rows:
        import json
        configs.append(PremiumConfigResponse(
            id=row[0],
            asset_id=row[1],
            signal_tf=row[2],
            htf_tf=row[3],
            osc_preset=row[4],
            cash_use_pct=row[5],
            hard_cap_pct=row[6],
            min_profit_pct=row[7],
            buy_tranches=json.loads(row[8]) if row[8] else [25, 50, 75, 100],
            sell_tranches=json.loads(row[9]) if row[9] else [50, 100],
            buy_after_max=row[10] or "extend",
            sell_after_max=row[11] or "extend",
            buy_stage_1_only=bool(row[12]),
            sell_stage_1_only=bool(row[13]),
            use_lower_band_filter=bool(row[14]),
            use_below_avg_filter=bool(row[15]),
            use_prev_signal_filter=bool(row[16]),
            use_prev_exec_filter=bool(row[17]),
            use_4regime=bool(row[18]),
            r1_pullback_enabled=bool(row[19]),
            r3_breakout_enabled=bool(row[20]),
            one_trade_per_bar=bool(row[21]),
            created_at=row[22],
            updated_at=row[23],
        ))

    return configs


@router.get("/configs/{asset_id}", response_model=PremiumConfigResponse)
async def get_premium_config(
    asset_id: int,
    db: Session = Depends(get_db),
):
    """Get premium config for an asset."""
    result = db.execute(
        text("""
            SELECT id, asset_id, signal_tf, htf_tf, osc_preset,
                   cash_use_pct, hard_cap_pct, min_profit_pct,
                   buy_tranches, sell_tranches,
                   buy_after_max, sell_after_max,
                   buy_stage_1_only, sell_stage_1_only,
                   use_lower_band_filter, use_below_avg_filter,
                   use_prev_signal_filter, use_prev_exec_filter,
                   use_4regime, r1_pullback_enabled, r3_breakout_enabled,
                   one_trade_per_bar, created_at, updated_at
            FROM premium_configs
            WHERE asset_id = :asset_id
        """),
        {"asset_id": asset_id},
    )
    row = result.fetchone()

    if not row:
        raise HTTPException(status_code=404, detail="Premium config not found")

    import json
    return PremiumConfigResponse(
        id=row[0],
        asset_id=row[1],
        signal_tf=row[2],
        htf_tf=row[3],
        osc_preset=row[4],
        cash_use_pct=row[5],
        hard_cap_pct=row[6],
        min_profit_pct=row[7],
        buy_tranches=json.loads(row[8]) if row[8] else [25, 50, 75, 100],
        sell_tranches=json.loads(row[9]) if row[9] else [50, 100],
        buy_after_max=row[10] or "extend",
        sell_after_max=row[11] or "extend",
        buy_stage_1_only=bool(row[12]),
        sell_stage_1_only=bool(row[13]),
        use_lower_band_filter=bool(row[14]),
        use_below_avg_filter=bool(row[15]),
        use_prev_signal_filter=bool(row[16]),
        use_prev_exec_filter=bool(row[17]),
        use_4regime=bool(row[18]),
        r1_pullback_enabled=bool(row[19]),
        r3_breakout_enabled=bool(row[20]),
        one_trade_per_bar=bool(row[21]),
        created_at=row[22],
        updated_at=row[23],
    )


@router.post("/configs", response_model=PremiumConfigResponse)
async def create_premium_config(
    config: PremiumConfigCreate,
    db: Session = Depends(get_db),
):
    """Create premium config for an asset."""
    import json

    # Check if asset exists
    asset_result = db.execute(
        text("SELECT id FROM assets WHERE id = :asset_id"),
        {"asset_id": config.asset_id},
    )
    if not asset_result.fetchone():
        raise HTTPException(status_code=404, detail="Asset not found")

    # Check if config already exists
    existing = db.execute(
        text("SELECT id FROM premium_configs WHERE asset_id = :asset_id"),
        {"asset_id": config.asset_id},
    )
    if existing.fetchone():
        raise HTTPException(status_code=400, detail="Config already exists for this asset")

    # Insert config
    result = db.execute(
        text("""
            INSERT INTO premium_configs (
                asset_id, signal_tf, htf_tf, osc_preset,
                cash_use_pct, hard_cap_pct, min_profit_pct,
                buy_tranches, sell_tranches,
                buy_after_max, sell_after_max,
                buy_stage_1_only, sell_stage_1_only,
                use_lower_band_filter, use_below_avg_filter,
                use_prev_signal_filter, use_prev_exec_filter,
                use_4regime, r1_pullback_enabled, r3_breakout_enabled,
                one_trade_per_bar
            ) VALUES (
                :asset_id, :signal_tf, :htf_tf, :osc_preset,
                :cash_use_pct, :hard_cap_pct, :min_profit_pct,
                :buy_tranches, :sell_tranches,
                :buy_after_max, :sell_after_max,
                :buy_stage_1_only, :sell_stage_1_only,
                :use_lower_band_filter, :use_below_avg_filter,
                :use_prev_signal_filter, :use_prev_exec_filter,
                :use_4regime, :r1_pullback_enabled, :r3_breakout_enabled,
                :one_trade_per_bar
            )
        """),
        {
            "asset_id": config.asset_id,
            "signal_tf": config.signal_tf,
            "htf_tf": config.htf_tf,
            "osc_preset": config.osc_preset,
            "cash_use_pct": config.cash_use_pct,
            "hard_cap_pct": config.hard_cap_pct,
            "min_profit_pct": config.min_profit_pct,
            "buy_tranches": json.dumps(config.buy_tranches),
            "sell_tranches": json.dumps(config.sell_tranches),
            "buy_after_max": config.buy_after_max,
            "sell_after_max": config.sell_after_max,
            "buy_stage_1_only": config.buy_stage_1_only,
            "sell_stage_1_only": config.sell_stage_1_only,
            "use_lower_band_filter": config.use_lower_band_filter,
            "use_below_avg_filter": config.use_below_avg_filter,
            "use_prev_signal_filter": config.use_prev_signal_filter,
            "use_prev_exec_filter": config.use_prev_exec_filter,
            "use_4regime": config.use_4regime,
            "r1_pullback_enabled": config.r1_pullback_enabled,
            "r3_breakout_enabled": config.r3_breakout_enabled,
            "one_trade_per_bar": config.one_trade_per_bar,
        },
    )
    db.commit()

    # Also create strategy state
    db.execute(
        text("""
            INSERT OR IGNORE INTO strategy_states (asset_id)
            VALUES (:asset_id)
        """),
        {"asset_id": config.asset_id},
    )
    db.commit()

    return await get_premium_config(config.asset_id, db)


@router.put("/configs/{asset_id}", response_model=PremiumConfigResponse)
async def update_premium_config(
    asset_id: int,
    config: PremiumConfigUpdate,
    db: Session = Depends(get_db),
):
    """Update premium config for an asset."""
    import json

    # Check if config exists
    existing = db.execute(
        text("SELECT id FROM premium_configs WHERE asset_id = :asset_id"),
        {"asset_id": asset_id},
    )
    if not existing.fetchone():
        raise HTTPException(status_code=404, detail="Config not found")

    # Update config
    db.execute(
        text("""
            UPDATE premium_configs SET
                signal_tf = :signal_tf,
                htf_tf = :htf_tf,
                osc_preset = :osc_preset,
                cash_use_pct = :cash_use_pct,
                hard_cap_pct = :hard_cap_pct,
                min_profit_pct = :min_profit_pct,
                buy_tranches = :buy_tranches,
                sell_tranches = :sell_tranches,
                buy_after_max = :buy_after_max,
                sell_after_max = :sell_after_max,
                buy_stage_1_only = :buy_stage_1_only,
                sell_stage_1_only = :sell_stage_1_only,
                use_lower_band_filter = :use_lower_band_filter,
                use_below_avg_filter = :use_below_avg_filter,
                use_prev_signal_filter = :use_prev_signal_filter,
                use_prev_exec_filter = :use_prev_exec_filter,
                use_4regime = :use_4regime,
                r1_pullback_enabled = :r1_pullback_enabled,
                r3_breakout_enabled = :r3_breakout_enabled,
                one_trade_per_bar = :one_trade_per_bar,
                updated_at = datetime('now')
            WHERE asset_id = :asset_id
        """),
        {
            "asset_id": asset_id,
            "signal_tf": config.signal_tf,
            "htf_tf": config.htf_tf,
            "osc_preset": config.osc_preset,
            "cash_use_pct": config.cash_use_pct,
            "hard_cap_pct": config.hard_cap_pct,
            "min_profit_pct": config.min_profit_pct,
            "buy_tranches": json.dumps(config.buy_tranches),
            "sell_tranches": json.dumps(config.sell_tranches),
            "buy_after_max": config.buy_after_max,
            "sell_after_max": config.sell_after_max,
            "buy_stage_1_only": config.buy_stage_1_only,
            "sell_stage_1_only": config.sell_stage_1_only,
            "use_lower_band_filter": config.use_lower_band_filter,
            "use_below_avg_filter": config.use_below_avg_filter,
            "use_prev_signal_filter": config.use_prev_signal_filter,
            "use_prev_exec_filter": config.use_prev_exec_filter,
            "use_4regime": config.use_4regime,
            "r1_pullback_enabled": config.r1_pullback_enabled,
            "r3_breakout_enabled": config.r3_breakout_enabled,
            "one_trade_per_bar": config.one_trade_per_bar,
        },
    )
    db.commit()

    return await get_premium_config(asset_id, db)


@router.delete("/configs/{asset_id}")
async def delete_premium_config(
    asset_id: int,
    db: Session = Depends(get_db),
):
    """Delete premium config for an asset."""
    # Delete config
    result = db.execute(
        text("DELETE FROM premium_configs WHERE asset_id = :asset_id"),
        {"asset_id": asset_id},
    )
    db.commit()

    if result.rowcount == 0:
        raise HTTPException(status_code=404, detail="Config not found")

    # Also delete strategy state
    db.execute(
        text("DELETE FROM strategy_states WHERE asset_id = :asset_id"),
        {"asset_id": asset_id},
    )
    db.commit()

    return {"message": "Config deleted"}


# ============================================================================
# Strategy State Endpoints
# ============================================================================

@router.get("/states/{asset_id}", response_model=StrategyStateResponse)
async def get_strategy_state(
    asset_id: int,
    db: Session = Depends(get_db),
):
    """Get strategy state for an asset."""
    result = db.execute(
        text("""
            SELECT id, asset_id, buy_stage, sell_stage,
                   last_buy_signal_price, last_sell_signal_price,
                   last_buy_exec_price, last_sell_exec_price,
                   r1_pullback_active, r3_breakout_active,
                   updated_at
            FROM strategy_states
            WHERE asset_id = :asset_id
        """),
        {"asset_id": asset_id},
    )
    row = result.fetchone()

    if not row:
        raise HTTPException(status_code=404, detail="Strategy state not found")

    return StrategyStateResponse(
        id=row[0],
        asset_id=row[1],
        buy_stage=row[2] or 0,
        sell_stage=row[3] or 0,
        last_buy_signal_price=row[4],
        last_sell_signal_price=row[5],
        last_buy_exec_price=row[6],
        last_sell_exec_price=row[7],
        r1_pullback_active=bool(row[8]),
        r3_breakout_active=bool(row[9]),
        updated_at=row[10],
    )


@router.post("/states/{asset_id}/reset")
async def reset_strategy_state(
    asset_id: int,
    db: Session = Depends(get_db),
):
    """Reset strategy state for an asset."""
    result = db.execute(
        text("""
            UPDATE strategy_states SET
                buy_stage = 0,
                sell_stage = 0,
                last_buy_signal_price = NULL,
                last_sell_signal_price = NULL,
                last_buy_exec_price = NULL,
                last_sell_exec_price = NULL,
                r1_pullback_active = 0,
                r3_breakout_active = 0,
                updated_at = datetime('now')
            WHERE asset_id = :asset_id
        """),
        {"asset_id": asset_id},
    )
    db.commit()

    if result.rowcount == 0:
        raise HTTPException(status_code=404, detail="Strategy state not found")

    return {"message": "Strategy state reset"}


# ============================================================================
# Scheduler Endpoints
# ============================================================================

@router.get("/scheduler/status", response_model=SchedulerStatusResponse)
async def get_scheduler_status():
    """Get scheduler status."""
    from .strategy_engine.scheduler import get_scheduler

    scheduler = get_scheduler()
    status = scheduler.get_status()

    return SchedulerStatusResponse(**status)


@router.post("/scheduler/start")
async def start_scheduler(background_tasks: BackgroundTasks):
    """Start the scheduler."""
    from .strategy_engine.scheduler import get_scheduler

    scheduler = get_scheduler()

    if scheduler.state.value == "running":
        return {"message": "Scheduler already running"}

    background_tasks.add_task(scheduler.start)
    return {"message": "Scheduler starting"}


@router.post("/scheduler/stop")
async def stop_scheduler():
    """Stop the scheduler."""
    from .strategy_engine.scheduler import get_scheduler

    scheduler = get_scheduler()
    await scheduler.stop()
    return {"message": "Scheduler stopped"}


@router.post("/scheduler/pause")
async def pause_scheduler():
    """Pause the scheduler."""
    from .strategy_engine.scheduler import get_scheduler

    scheduler = get_scheduler()
    await scheduler.pause()
    return {"message": "Scheduler paused"}


@router.post("/scheduler/resume")
async def resume_scheduler():
    """Resume the scheduler."""
    from .strategy_engine.scheduler import get_scheduler

    scheduler = get_scheduler()
    await scheduler.resume()
    return {"message": "Scheduler resumed"}


@router.post("/scheduler/register/{asset_id}")
async def register_asset_to_scheduler(
    asset_id: int,
    db: Session = Depends(get_db),
):
    """Register an asset to the scheduler."""
    from .strategy_engine.scheduler import get_scheduler

    # Get asset info
    asset_result = db.execute(
        text("""
            SELECT a.id, a.symbol, acc.exchange
            FROM assets a
            JOIN accounts acc ON a.account_id = acc.id
            WHERE a.id = :asset_id
        """),
        {"asset_id": asset_id},
    )
    asset_row = asset_result.fetchone()
    if not asset_row:
        raise HTTPException(status_code=404, detail="Asset not found")

    # Get premium config
    config_result = db.execute(
        text("SELECT signal_tf, htf_tf FROM premium_configs WHERE asset_id = :asset_id"),
        {"asset_id": asset_id},
    )
    config_row = config_result.fetchone()
    if not config_row:
        raise HTTPException(status_code=404, detail="Premium config not found")

    scheduler = get_scheduler()
    success = scheduler.register_asset(
        asset_id=asset_row[0],
        symbol=asset_row[1],
        exchange=asset_row[2],
        timeframe=config_row[0],
        htf_timeframe=config_row[1],
        enabled=True,
    )

    return {"message": "Asset registered", "success": success}


@router.post("/scheduler/unregister/{asset_id}")
async def unregister_asset_from_scheduler(asset_id: int):
    """Unregister an asset from the scheduler."""
    from .strategy_engine.scheduler import get_scheduler

    scheduler = get_scheduler()
    success = scheduler.unregister_asset(asset_id)

    if not success:
        raise HTTPException(status_code=404, detail="Asset not found in scheduler")

    return {"message": "Asset unregistered"}


# ============================================================================
# Signal Trigger Endpoints
# ============================================================================

@router.post("/signal/trigger", response_model=SignalTriggerResponse)
async def trigger_signal(
    request: SignalTriggerRequest,
    db: Session = Depends(get_db),
):
    """
    Manually trigger signal generation for an asset.

    This is for testing/debugging purposes.
    """
    from .strategy_engine.scheduler import get_scheduler

    scheduler = get_scheduler()
    asset = scheduler.get_asset(request.asset_id)

    if not asset:
        # Try to register first
        try:
            await register_asset_to_scheduler(request.asset_id, db)
            asset = scheduler.get_asset(request.asset_id)
        except HTTPException:
            return SignalTriggerResponse(
                success=False,
                message="Asset not found or not configured",
            )

    if not asset:
        return SignalTriggerResponse(
            success=False,
            message="Failed to register asset",
        )

    # Trigger processing
    success = await scheduler.process_now(request.asset_id)

    return SignalTriggerResponse(
        success=success,
        message="Signal processing triggered" if success else "Processing failed",
    )


# ============================================================================
# Signal Events Endpoints
# ============================================================================

@router.get("/signals")
async def list_signals(
    db: Session = Depends(get_db),
    asset_id: Optional[int] = Query(default=None),
    limit: int = Query(default=50, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
):
    """List signal events."""
    query = """
        SELECT signal_id, asset_id, symbol, exchange, side, action,
               premium_mode, reason_code, reason_text, tf, regime,
               tranche, tranche_pct, ts, created_at, processed
        FROM signal_events
    """
    params = {"limit": limit, "offset": offset}

    if asset_id:
        query += " WHERE asset_id = :asset_id"
        params["asset_id"] = asset_id

    query += " ORDER BY ts DESC LIMIT :limit OFFSET :offset"

    result = db.execute(text(query), params)
    rows = result.fetchall()

    return [
        {
            "signal_id": row[0],
            "asset_id": row[1],
            "symbol": row[2],
            "exchange": row[3],
            "side": row[4],
            "action": row[5],
            "premium_mode": row[6],
            "reason_code": row[7],
            "reason_text": row[8],
            "tf": row[9],
            "regime": row[10],
            "tranche": row[11],
            "tranche_pct": row[12],
            "ts": row[13],
            "created_at": row[14],
            "processed": row[15],
        }
        for row in rows
    ]


@router.get("/signals/{signal_id}")
async def get_signal(
    signal_id: str,
    db: Session = Depends(get_db),
):
    """Get a signal event with its snapshot."""
    # Get signal
    signal_result = db.execute(
        text("""
            SELECT signal_id, asset_id, symbol, exchange, side, action,
                   premium_mode, reason_code, reason_text, snapshot_id,
                   tf, tf_warning, price_hint, tranche, tranche_pct,
                   regime, ts, created_at, processed
            FROM signal_events
            WHERE signal_id = :signal_id
        """),
        {"signal_id": signal_id},
    )
    signal_row = signal_result.fetchone()

    if not signal_row:
        raise HTTPException(status_code=404, detail="Signal not found")

    # Get snapshot
    snapshot_result = db.execute(
        text("""
            SELECT snapshot_id, ohlcv, indicators, created_at
            FROM signal_snapshots
            WHERE signal_id = :signal_id
        """),
        {"signal_id": signal_id},
    )
    snapshot_row = snapshot_result.fetchone()

    import json
    snapshot = None
    if snapshot_row:
        snapshot = {
            "snapshot_id": snapshot_row[0],
            "ohlcv": json.loads(snapshot_row[1]) if snapshot_row[1] else None,
            "indicators": json.loads(snapshot_row[2]) if snapshot_row[2] else None,
            "created_at": snapshot_row[3],
        }

    return {
        "signal_id": signal_row[0],
        "asset_id": signal_row[1],
        "symbol": signal_row[2],
        "exchange": signal_row[3],
        "side": signal_row[4],
        "action": signal_row[5],
        "premium_mode": signal_row[6],
        "reason_code": signal_row[7],
        "reason_text": signal_row[8],
        "snapshot_id": signal_row[9],
        "tf": signal_row[10],
        "tf_warning": signal_row[11],
        "price_hint": signal_row[12],
        "tranche": signal_row[13],
        "tranche_pct": signal_row[14],
        "regime": signal_row[15],
        "ts": signal_row[16],
        "created_at": signal_row[17],
        "processed": signal_row[18],
        "snapshot": snapshot,
    }


# ============================================================================
# Backtest Endpoints (Phase 5)
# ============================================================================

class MRBacktestRequest(BaseModel):
    """Request model for MR backtest."""
    exchange: str = Field(..., description="거래소 (okx, binance, etc)")
    symbol: str = Field(..., description="종목 심볼 (BTC-USDT)")
    timeframe: str = Field(default="1h", description="타임프레임")
    htf_timeframe: str = Field(default="4h", description="HTF 타임프레임")
    days: int = Field(default=365, ge=30, le=1000, description="백테스트 기간 (일)")
    initial_capital: float = Field(default=10000000, ge=1000)
    osc_preset: str = Field(default="preset1")
    cash_use_pct: float = Field(default=90.0, ge=0, le=100)
    use_4regime: bool = Field(default=True)
    buy_tranches: List[int] = Field(default=[25, 50, 75, 100])
    sell_tranches: List[int] = Field(default=[50, 100])


class MRBacktestResponse(BaseModel):
    """Response model for MR backtest."""
    success: bool
    message: str
    metrics: Dict[str, Any]
    equity_curve: List[Dict[str, Any]]
    trades: List[Dict[str, Any]]
    signals_count: int


@router.post("/backtest/mr", response_model=MRBacktestResponse)
async def run_mr_backtest_endpoint(
    request: MRBacktestRequest,
):
    """
    MR 프리미엄 전략 백테스트 실행.

    샘플 데이터 또는 캐시된 OHLCV 데이터로 백테스트를 실행합니다.
    """
    from .strategy_engine.backtest_engine import (
        run_mr_backtest,
        generate_sample_candles,
        BacktestResult,
    )
    from .strategy_engine.models import MRConfig

    try:
        # MR 설정 생성
        config = MRConfig(
            osc_preset=request.osc_preset,
            cash_use_pct=request.cash_use_pct,
            use_4regime=request.use_4regime,
            buy_tranches=request.buy_tranches,
            sell_tranches=request.sell_tranches,
        )

        # 캔들 데이터 생성 (실제 운영시 candle_fetcher 사용)
        # 여기서는 샘플 데이터로 테스트
        candles = generate_sample_candles(
            days=request.days,
            base_price=50000.0 if "BTC" in request.symbol.upper() else 1000.0,
            seed=hash(f"{request.exchange}_{request.symbol}") % 100000,
        )

        # 백테스트 실행
        result = run_mr_backtest(
            candles=candles,
            htf_candles=None,  # HTF 없으면 동일 데이터 사용
            config=config,
            initial_capital=request.initial_capital,
        )

        # 결과 변환
        trades_list = []
        for t in result.trades:
            trades_list.append({
                "bar_index": t.bar_index,
                "timestamp": t.timestamp,
                "action": t.action,
                "price": t.price,
                "quantity": t.quantity,
                "tranche": t.tranche,
                "reason_code": t.reason_code,
                "pnl": t.pnl,
                "pnl_pct": t.pnl_pct,
            })

        # equity_curve 샘플링 (너무 많으면 줄임)
        equity_curve = result.equity_curve
        if len(equity_curve) > 500:
            step = len(equity_curve) // 500
            equity_curve = equity_curve[::step]

        return MRBacktestResponse(
            success=result.success,
            message=result.message,
            metrics={
                "total_return_pct": round(result.metrics.total_return_pct, 2),
                "cagr_pct": round(result.metrics.cagr_pct, 2),
                "max_drawdown_pct": round(result.metrics.max_drawdown_pct, 2),
                "sharpe_ratio": round(result.metrics.sharpe_ratio, 2),
                "win_rate_pct": round(result.metrics.win_rate_pct, 1),
                "total_trades": result.metrics.total_trades,
                "winning_trades": result.metrics.winning_trades,
                "losing_trades": result.metrics.losing_trades,
                "avg_win_pct": round(result.metrics.avg_win_pct, 2),
                "avg_loss_pct": round(result.metrics.avg_loss_pct, 2),
                "profit_factor": round(result.metrics.profit_factor, 2),
                "max_consecutive_wins": result.metrics.max_consecutive_wins,
                "max_consecutive_losses": result.metrics.max_consecutive_losses,
            },
            equity_curve=equity_curve,
            trades=trades_list,
            signals_count=len(result.signals),
        )

    except Exception as e:
        logger.error(f"MR 백테스트 오류: {e}")
        return MRBacktestResponse(
            success=False,
            message=f"백테스트 오류: {str(e)}",
            metrics={},
            equity_curve=[],
            trades=[],
            signals_count=0,
        )

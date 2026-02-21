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
    buy_tranches: List[float] = Field(default=[25.0, 50.0, 75.0, 100.0])
    sell_tranches: List[float] = Field(default=[50.0, 100.0])
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
    # asset_id 또는 exchange+symbol 둘 중 하나 필수
    asset_id: Optional[int] = None
    exchange: Optional[str] = None
    symbol: Optional[str] = None


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
            osc_preset=f"preset{row[4]}" if isinstance(row[4], int) else (row[4] or "preset1"),
            cash_use_pct=row[5],
            hard_cap_pct=row[6],
            min_profit_pct=row[7],
            buy_tranches=row[8] if row[8] else [25, 50, 75, 100],
            sell_tranches=row[9] if row[9] else [50, 100],
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
        osc_preset=f"preset{row[4]}" if isinstance(row[4], int) else (row[4] or "preset1"),
        cash_use_pct=row[5],
        hard_cap_pct=row[6],
        min_profit_pct=row[7],
        buy_tranches=row[8] if row[8] else [25, 50, 75, 100],
        sell_tranches=row[9] if row[9] else [50, 100],
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
    """Create premium config for an asset.

    asset_id 또는 exchange+symbol 둘 중 하나 필수.
    exchange+symbol이 제공되면 자동으로 asset을 찾거나 생성함.
    """
    import json

    asset_id = config.asset_id

    # exchange+symbol로 asset 찾기/생성
    if not asset_id and config.exchange and config.symbol:
        exchange = config.exchange.upper()
        symbol = config.symbol

        # 1. 해당 거래소의 계정 찾기
        account_row = db.execute(
            text("SELECT id FROM accounts WHERE UPPER(exchange) = :exchange LIMIT 1"),
            {"exchange": exchange}
        ).fetchone()

        if not account_row:
            # 계정이 없으면 기본 계정 생성 (user_id=1 사용)
            db.execute(
                text("""
                    INSERT INTO accounts (user_id, exchange, name, is_active)
                    VALUES (1, :exchange, :name, true)
                """),
                {"exchange": exchange, "name": f"{exchange} Account"}
            )
            db.commit()
            account_row = db.execute(
                text("SELECT id FROM accounts WHERE UPPER(exchange) = :exchange LIMIT 1"),
                {"exchange": exchange}
            ).fetchone()

        account_id = account_row[0]

        # 2. 기본 전략 찾기 (MR 전략)
        strategy_row = db.execute(
            text("SELECT id FROM strategies WHERE name LIKE '%MR%' OR name LIKE '%역추세%' LIMIT 1")
        ).fetchone()

        if not strategy_row:
            # MR 전략 생성
            db.execute(
                text("""
                    INSERT INTO strategies (user_id, name, description, source, entry_webhook, is_active)
                    VALUES (1, 'MR 역추세매매', '프리미엄 역추세 전략', 'premium', '', true)
                """)
            )
            db.commit()
            strategy_row = db.execute(
                text("SELECT id FROM strategies WHERE name LIKE '%MR%' OR name LIKE '%역추세%' LIMIT 1")
            ).fetchone()

        strategy_id = strategy_row[0]

        # 3. asset 찾거나 생성
        asset_row = db.execute(
            text("""
                SELECT a.id FROM assets a
                JOIN accounts acc ON acc.id = a.account_id
                WHERE a.symbol = :symbol AND UPPER(acc.exchange) = :exchange
                LIMIT 1
            """),
            {"symbol": symbol, "exchange": exchange}
        ).fetchone()

        if not asset_row:
            # asset 생성
            db.execute(
                text("""
                    INSERT INTO assets (account_id, strategy_id, symbol, market, is_active)
                    VALUES (:account_id, :strategy_id, :symbol, 'spot', true)
                """),
                {"account_id": account_id, "strategy_id": strategy_id, "symbol": symbol}
            )
            db.commit()
            asset_row = db.execute(
                text("""
                    SELECT a.id FROM assets a
                    JOIN accounts acc ON acc.id = a.account_id
                    WHERE a.symbol = :symbol AND UPPER(acc.exchange) = :exchange
                    LIMIT 1
                """),
                {"symbol": symbol, "exchange": exchange}
            ).fetchone()

        asset_id = asset_row[0]

    # asset_id 확인
    if not asset_id:
        raise HTTPException(status_code=400, detail="asset_id 또는 exchange+symbol이 필요합니다")

    # Check if asset exists
    asset_result = db.execute(
        text("SELECT id FROM assets WHERE id = :asset_id"),
        {"asset_id": asset_id},
    )
    if not asset_result.fetchone():
        raise HTTPException(status_code=404, detail="Asset not found")

    # Check if config already exists - 있으면 업데이트
    existing = db.execute(
        text("SELECT id FROM premium_configs WHERE asset_id = :asset_id"),
        {"asset_id": asset_id},
    )
    if existing.fetchone():
        # 기존 설정이 있으면 업데이트
        db.execute(
            text("""
                UPDATE premium_configs SET
                    signal_tf = :signal_tf, htf_tf = :htf_tf, osc_preset = :osc_preset,
                    cash_use_pct = :cash_use_pct, hard_cap_pct = :hard_cap_pct, min_profit_pct = :min_profit_pct,
                    buy_tranches = :buy_tranches, sell_tranches = :sell_tranches,
                    buy_after_max = :buy_after_max, sell_after_max = :sell_after_max,
                    buy_stage_1_only = :buy_stage_1_only, sell_stage_1_only = :sell_stage_1_only,
                    use_lower_band_filter = :use_lower_band_filter, use_below_avg_filter = :use_below_avg_filter,
                    use_prev_signal_filter = :use_prev_signal_filter, use_prev_exec_filter = :use_prev_exec_filter,
                    use_4regime = :use_4regime, r1_pullback_enabled = :r1_pullback_enabled, r3_breakout_enabled = :r3_breakout_enabled,
                    one_trade_per_bar = :one_trade_per_bar, updated_at = now()
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
            }
        )
        db.commit()

        # 업데이트된 설정 조회
        row = db.execute(
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
                FROM premium_configs WHERE asset_id = :asset_id
            """),
            {"asset_id": asset_id}
        ).fetchone()

        return PremiumConfigResponse(
            id=row[0], asset_id=row[1], signal_tf=row[2], htf_tf=row[3],
            osc_preset=f"preset{row[4]}" if isinstance(row[4], int) else (row[4] or "preset1"),
            cash_use_pct=row[5], hard_cap_pct=row[6], min_profit_pct=row[7],
            buy_tranches=row[8] if row[8] else [25, 50, 75, 100],
            sell_tranches=row[9] if row[9] else [50, 100],
            buy_after_max=row[10] or "extend", sell_after_max=row[11] or "extend",
            buy_stage_1_only=bool(row[12]), sell_stage_1_only=bool(row[13]),
            use_lower_band_filter=bool(row[14]), use_below_avg_filter=bool(row[15]),
            use_prev_signal_filter=bool(row[16]), use_prev_exec_filter=bool(row[17]),
            use_4regime=bool(row[18]), r1_pullback_enabled=bool(row[19]), r3_breakout_enabled=bool(row[20]),
            one_trade_per_bar=bool(row[21]), created_at=row[22], updated_at=row[23],
        )

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

    # Also create strategy state
    db.execute(
        text("""
            INSERT OR IGNORE INTO strategy_states (asset_id)
            VALUES (:asset_id)
        """),
        {"asset_id": asset_id},
    )
    db.commit()

    return await get_premium_config(asset_id, db)


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
# Candle Preload API (캔들 사전 로딩)
# ============================================================================

class PreloadRequest(BaseModel):
    """캔들 프리로드 요청"""
    exchange: str = Field(..., description="거래소 (OKX, BINANCE, BYBIT)")
    symbol: str = Field(..., description="종목 심볼 (BTC-USDT)")
    timeframe: str = Field(default="1h", description="타임프레임")
    days: int = Field(default=365, ge=7, le=1000, description="기간 (일)")


class PreloadResponse(BaseModel):
    """캔들 프리로드 응답"""
    success: bool
    candles: int = 0
    cached: bool = False
    time_sec: float = 0.0
    message: str = ""


@router.post("/backtest/preload", response_model=PreloadResponse)
async def preload_candles(request: PreloadRequest):
    """
    캔들 데이터를 사전 로딩하여 DB에 캐시.
    백테스트 실행 전에 호출하면 백테스트가 빨라짐.
    """
    import time
    from .strategy_engine.candle_fetcher import fetch_candles_for_backtest

    start_time = time.time()

    try:
        candles = await fetch_candles_for_backtest(
            exchange=request.exchange,
            symbol=request.symbol,
            timeframe=request.timeframe,
            days=request.days,
            timeout=90,
        )

        elapsed = time.time() - start_time
        cached = elapsed < 2.0  # 2초 이내면 캐시에서 가져온 것

        return PreloadResponse(
            success=True,
            candles=len(candles),
            cached=cached,
            time_sec=round(elapsed, 2),
            message=f"{'캐시에서 로드' if cached else '거래소에서 다운로드'}: {len(candles)}봉",
        )

    except ValueError as e:
        return PreloadResponse(
            success=False,
            message=str(e),
            time_sec=round(time.time() - start_time, 2),
        )
    except Exception as e:
        logger.error(f"캔들 프리로드 오류: {e}")
        return PreloadResponse(
            success=False,
            message=f"캔들 로드 실패: {type(e).__name__}",
            time_sec=round(time.time() - start_time, 2),
        )


# ============================================================================
# Backtest Endpoints (Phase 5)
# ============================================================================

class MRBacktestRequest(BaseModel):
    """Request model for MR backtest."""
    exchange: str = Field(..., description="거래소 (OKX, BINANCE, BYBIT)")
    symbol: str = Field(..., description="종목 심볼 (BTC-USDT)")
    timeframe: str = Field(default="30m", description="시그널 타임프레임")
    htf_tf: str = Field(default="1D", description="HTF 타임프레임")
    days: int = Field(default=365, ge=7, le=1000, description="백테스트 기간 (일)")
    initial_capital: float = Field(default=10000000, ge=1000)

    # 오실레이터 설정
    osc_preset: str = Field(default="custom")
    osc_smooth_len: int = Field(default=4, ge=2, le=100)
    osc_threshold: float = Field(default=1.0, ge=0.1, le=5.0)

    # 자금관리
    cash_use_pct: float = Field(default=55.0, ge=0, le=100)
    min_profit_pct: float = Field(default=0.1, ge=0, le=50)
    fee_buffer_pct: float = Field(default=0.2, ge=0, le=5)
    buy_tranches: List[float] = Field(default=[5.0, 5.0, 5.0, 5.0, 5.0, 5.0, 5.0, 5.0, 5.0, 5.0])
    sell_tranches: List[float] = Field(default=[10.0, 20.0, 30.0, 5.0, 2.5, 1.0])
    max_buy_tranches: int = Field(default=10, ge=1, le=20)
    max_sell_tranches: int = Field(default=6, ge=1, le=20)

    # 국면 설정
    use_4regime: bool = Field(default=True)

    # R1 상승장
    r1_buy_mult: float = Field(default=1.0, ge=0, le=5)
    r1_sell_mult: float = Field(default=1.3, ge=0, le=5)
    r1_allow_osc_buy: bool = Field(default=True)
    r1_pullback_on: bool = Field(default=True)
    r1_filt_below_avg: bool = Field(default=True)
    r1_filt_prev_signal: bool = Field(default=True)
    r1_filt_prev_exec: bool = Field(default=True)

    # R2 조정장
    r2_buy_mult: float = Field(default=0.0, ge=0, le=5)
    r2_sell_mult: float = Field(default=1.6, ge=0, le=5)
    r2_allow_osc_buy: bool = Field(default=False)
    r2_filt_below_avg: bool = Field(default=False)
    r2_filt_prev_signal: bool = Field(default=False)
    r2_filt_prev_exec: bool = Field(default=False)

    # R3 반등장
    r3_buy_mult: float = Field(default=1.0, ge=0, le=5)
    r3_sell_mult: float = Field(default=1.3, ge=0, le=5)
    r3_allow_osc_buy: bool = Field(default=True)
    r3_breakout_on: bool = Field(default=True)
    r3_filt_below_avg: bool = Field(default=False)
    r3_filt_prev_signal: bool = Field(default=True)
    r3_filt_prev_exec: bool = Field(default=True)

    # R4 하락장
    r4_buy_mult: float = Field(default=1.2, ge=0, le=5)
    r4_sell_mult: float = Field(default=0.7, ge=0, le=5)
    r4_allow_osc_buy: bool = Field(default=True)
    r4_filt_below_avg: bool = Field(default=True)
    r4_filt_prev_signal: bool = Field(default=True)
    r4_filt_prev_exec: bool = Field(default=False)


class MRBacktestResponse(BaseModel):
    """Response model for MR backtest."""
    success: bool
    message: str = ""
    error: Optional[str] = None
    exchange: Optional[str] = None  # 화폐 단위 결정용
    symbol: Optional[str] = None    # 화폐 단위 결정용 (USDT/USDC 등)
    metrics: Dict[str, Any] = {}
    equity_curve: List[Dict[str, Any]] = []
    trades: List[Dict[str, Any]] = []
    candles: List[Dict[str, Any]] = []  # 캔들차트용 OHLCV 데이터
    signals_count: int = 0


@router.post("/backtest/mr", response_model=MRBacktestResponse)
async def run_mr_backtest_endpoint(
    request: MRBacktestRequest,
):
    """
    MR 프리미엄 전략 백테스트 실행.

    실제 거래소 OHLCV 데이터로 백테스트를 실행합니다.
    """
    import time as _time
    _t0 = _time.time()

    from .strategy_engine.backtest_engine import run_mr_backtest
    from .strategy_engine.candle_fetcher import fetch_candles_for_backtest
    from .strategy_engine.models import MRConfig

    try:
        # ① 실제 거래소 캔들 조회 (시그널 TF)
        _t1 = _time.time()
        candles = await fetch_candles_for_backtest(
            exchange=request.exchange,
            symbol=request.symbol,
            timeframe=request.timeframe,
            days=request.days,
            timeout=60,
        )
        print(f"[MR Backtest] 캔들 조회: {_time.time() - _t1:.2f}초, {len(candles)}개")

        # ② HTF 캔들 조회 (국면 판별용)
        htf_candles = None
        if request.use_4regime and request.htf_tf and request.htf_tf != request.timeframe:
            try:
                _t_htf = _time.time()
                htf_candles = await fetch_candles_for_backtest(
                    exchange=request.exchange,
                    symbol=request.symbol,
                    timeframe=request.htf_tf,
                    days=request.days,
                    timeout=30,
                )
                print(f"[MR Backtest] HTF 캔들 조회: {_time.time() - _t_htf:.2f}초, {len(htf_candles)}개")
            except ValueError:
                pass  # HTF 조회 실패 시 단일 국면으로 진행

        # ③ MR 설정 생성 (모든 국면별 파라미터 포함)
        config = MRConfig(
            osc_preset=request.osc_preset,
            osc_smooth_len=request.osc_smooth_len,
            osc_threshold=request.osc_threshold,
            cash_use_pct=request.cash_use_pct,
            min_profit_pct=request.min_profit_pct,
            fee_buffer_pct=request.fee_buffer_pct,
            use_4regime=request.use_4regime,
            buy_tranches=request.buy_tranches,
            sell_tranches=request.sell_tranches,
            max_buy_tranches=request.max_buy_tranches,
            max_sell_tranches=request.max_sell_tranches,
            # R1
            r1_buy_mult=request.r1_buy_mult,
            r1_sell_mult=request.r1_sell_mult,
            r1_allow_osc_buy=request.r1_allow_osc_buy,
            r1_pullback_on=request.r1_pullback_on,
            r1_filt_below_avg=request.r1_filt_below_avg,
            r1_filt_prev_signal=request.r1_filt_prev_signal,
            r1_filt_prev_exec=request.r1_filt_prev_exec,
            # R2
            r2_buy_mult=request.r2_buy_mult,
            r2_sell_mult=request.r2_sell_mult,
            r2_allow_osc_buy=request.r2_allow_osc_buy,
            r2_filt_below_avg=request.r2_filt_below_avg,
            r2_filt_prev_signal=request.r2_filt_prev_signal,
            r2_filt_prev_exec=request.r2_filt_prev_exec,
            # R3
            r3_buy_mult=request.r3_buy_mult,
            r3_sell_mult=request.r3_sell_mult,
            r3_allow_osc_buy=request.r3_allow_osc_buy,
            r3_breakout_on=request.r3_breakout_on,
            r3_filt_below_avg=request.r3_filt_below_avg,
            r3_filt_prev_signal=request.r3_filt_prev_signal,
            r3_filt_prev_exec=request.r3_filt_prev_exec,
            # R4
            r4_buy_mult=request.r4_buy_mult,
            r4_sell_mult=request.r4_sell_mult,
            r4_allow_osc_buy=request.r4_allow_osc_buy,
            r4_filt_below_avg=request.r4_filt_below_avg,
            r4_filt_prev_signal=request.r4_filt_prev_signal,
            r4_filt_prev_exec=request.r4_filt_prev_exec,
        )

        # ④ 백테스트 실행
        _t2 = _time.time()
        result = run_mr_backtest(
            candles=candles,
            htf_candles=htf_candles,
            config=config,
            initial_capital=request.initial_capital,
        )
        print(f"[MR Backtest] 백테스트 계산: {_time.time() - _t2:.2f}초")
        print(f"[MR Backtest] 총 소요시간: {_time.time() - _t0:.2f}초")

        # 백테스트 실패 시
        if not result.success:
            return MRBacktestResponse(
                success=False,
                message=result.message,
                error=result.message,
            )

        # 결과 변환 - trades 확장 (트레이딩뷰 동일)
        trades_list = []
        cumulative_pnl = 0.0
        for idx, t in enumerate(result.trades):
            if t.action == "sell" and t.pnl is not None:
                cumulative_pnl += t.pnl

            # 거래 타입 (한글)
            type_text = "매수" if t.action == "buy" else "매도"

            # 차수 (B0→매수1차, S0→매도1차)
            if t.action == "buy":
                tranche_text = f"매수{t.tranche + 1}차"
            else:
                tranche_text = f"매도{t.tranche + 1}차"

            # 날짜 포맷
            from datetime import datetime
            date_str = ""
            if t.timestamp:
                dt = datetime.fromtimestamp(t.timestamp / 1000)
                date_str = dt.strftime("%Y-%m-%d %H:%M")

            trades_list.append({
                "no": idx + 1,
                "type": type_text,
                "date": date_str,
                "bar_index": t.bar_index,
                "timestamp": t.timestamp,
                "action": t.action,
                "price": round(t.price, 2),
                "qty": round(t.quantity, 6),
                "quantity": t.quantity,
                "tranche": tranche_text,
                "tranche_idx": t.tranche,
                "reason_code": t.reason_code,
                "pnl": round(t.pnl, 2) if t.pnl is not None else None,
                "pnl_pct": round(t.pnl_pct, 2) if t.pnl_pct is not None else None,
                "cumulative_pnl": round(cumulative_pnl, 2) if t.action == "sell" else None,
                "commission": round(t.commission, 4) if t.commission else 0,
                "regime": getattr(t, 'regime', None),
            })

        # equity_curve 샘플링 (최대 200포인트로 제한)
        equity_curve = result.equity_curve
        if len(equity_curve) > 200:
            step = max(1, len(equity_curve) // 200)
            equity_curve = equity_curve[::step]

        # 추가 메트릭 계산
        sell_trades = [t for t in result.trades if t.action == "sell" and t.pnl_pct is not None]
        max_profit_pct = max((t.pnl_pct for t in sell_trades if t.pnl_pct > 0), default=0.0)
        max_loss_pct = min((t.pnl_pct for t in sell_trades if t.pnl_pct <= 0), default=0.0)

        m = result.metrics  # 편의상 alias

        # 캔들 데이터 (차트용, 최대 1000개로 샘플링)
        candle_data = []
        step = max(1, len(candles) // 1000)
        for i in range(0, len(candles), step):
            c = candles[i]
            candle_data.append({
                "time": c.ts // 1000,  # Unix 초 단위
                "open": c.o,
                "high": c.h,
                "low": c.l,
                "close": c.c,
                "volume": c.v,
            })

        return MRBacktestResponse(
            success=True,
            message=f"백테스트 완료: {len(candles)}봉 분석, {m.total_trades}거래",
            exchange=request.exchange,  # 화폐 단위 결정용
            symbol=request.symbol,      # 화폐 단위 결정용 (USDT/USDC 등)
            metrics={
                # === 기본 ===
                "initial_capital": round(m.initial_capital, 0),
                "final_capital": round(m.final_capital, 0),
                "total_return_pct": round(m.total_return_pct, 2),
                "cagr_pct": round(m.cagr_pct, 2),
                "max_drawdown_pct": round(m.max_drawdown_pct, 2),
                "sharpe_ratio": round(m.sharpe_ratio, 2),
                "win_rate_pct": round(m.win_rate_pct, 1),
                "total_trades": m.total_trades,
                "winning_trades": m.winning_trades,
                "losing_trades": m.losing_trades,
                "profit_factor": round(m.profit_factor, 3) if m.profit_factor != float('inf') else 999.99,

                # === 트레이딩뷰 추가 필드 ===
                "net_profit": round(m.net_profit, 2),
                "net_profit_pct": round(m.net_profit_pct, 2),
                "gross_profit": round(m.gross_profit, 2),
                "gross_profit_pct": round(m.gross_profit_pct, 2),
                "gross_loss": round(m.gross_loss, 2),
                "gross_loss_pct": round(m.gross_loss_pct, 2),
                "max_drawdown": round(m.max_drawdown, 2),
                "commission_paid": round(m.commission_paid, 4),
                "expected_value": round(m.expected_value, 2),
                "unrealized_pnl": round(m.unrealized_pnl, 2),
                "unrealized_pnl_pct": round(m.unrealized_pnl_pct, 2),

                # === 매수 분리 ===
                "buy_net_profit": round(m.buy_net_profit, 2),
                "buy_net_profit_pct": round(m.buy_net_profit_pct, 2),
                "buy_gross_profit": round(m.buy_gross_profit, 2),
                "buy_gross_profit_pct": round(m.buy_gross_profit_pct, 2),
                "buy_gross_loss": round(m.buy_gross_loss, 2),
                "buy_gross_loss_pct": round(m.buy_gross_loss_pct, 2),
                "buy_profit_factor": round(m.buy_profit_factor, 3) if m.buy_profit_factor != float('inf') else 999.99,
                "buy_commission": round(m.buy_commission, 4),
                "buy_expected_value": round(m.buy_expected_value, 2),
                "buy_trades": m.buy_trades,
                "buy_winning": m.buy_winning,
                "buy_losing": m.buy_losing,

                # === 매도 분리 (역추세는 0) ===
                "sell_net_profit": 0,
                "sell_net_profit_pct": 0,
                "sell_gross_profit": 0,
                "sell_gross_profit_pct": 0,
                "sell_gross_loss": 0,
                "sell_gross_loss_pct": 0,
                "sell_profit_factor": 0,
                "sell_commission": 0,
                "sell_expected_value": 0,
                "sell_trades": 0,
                "sell_winning": 0,
                "sell_losing": 0,

                # === 기존 호환 ===
                "avg_win_pct": round(m.avg_win_pct, 2),
                "avg_loss_pct": round(m.avg_loss_pct, 2),
                "max_consecutive_wins": m.max_consecutive_wins,
                "max_consecutive_losses": m.max_consecutive_losses,
                "avg_profit_pct": round(m.avg_win_pct, 2) if m.avg_win_pct else 0.0,
                "max_profit_pct": round(max_profit_pct, 2),
                "max_loss_pct": round(max_loss_pct, 2),
            },
            equity_curve=equity_curve,
            trades=trades_list,
            candles=candle_data,
            signals_count=len(result.signals),
        )

    except ValueError as e:
        # 사용자 친화적 에러 (한글)
        logger.warning(f"MR 백테스트 입력 오류: {e}")
        return MRBacktestResponse(
            success=False,
            message=str(e),
            error=str(e),
        )
    except Exception as e:
        # 예상치 못한 에러
        logger.error(f"MR 백테스트 오류: {e}", exc_info=True)
        return MRBacktestResponse(
            success=False,
            message=f"백테스트 실행 중 오류가 발생했습니다. 설정을 확인해주세요. ({type(e).__name__})",
            error=f"백테스트 실행 중 오류가 발생했습니다. 설정을 확인해주세요. ({type(e).__name__})",
        )


# ============================================================================
# Trend Backtest Endpoints (추세매매)
# ============================================================================

class TrendBacktestRequest(BaseModel):
    """Request model for Trend backtest (v8 최종)."""
    exchange: str = Field(..., description="거래소 (okx, binance, etc)")
    symbol: str = Field(..., description="종목 심볼 (BTC-USDT)")
    signal_tf: str = Field(default="1D", description="기준 TF (매수 + SPO + SL + TP1)")
    exit_tf: str = Field(default="1W", description="매도기준 TF (ST 전량매도 전용)")
    htf_tf: str = Field(default="1W", description="상위기준 TF (HTF VWMA 필터 전용)")
    days: int = Field(default=365, ge=30, le=1000, description="백테스트 기간 (일)")
    initial_capital: float = Field(default=10000000, ge=1000)

    # Supertrend 설정 (작가님 확정: 20/5.0)
    st_atr_len: int = Field(default=20, ge=1, le=50)
    st_factor: float = Field(default=5.0, ge=0.5, le=10.0)
    hvi_length: int = Field(default=200, ge=10, le=500)
    hvi_divisor: float = Field(default=3.6, ge=1.0, le=10.0)
    qqe_rsi_length: int = Field(default=6, ge=2, le=50)
    qqe_rsi_smoothing: int = Field(default=5, ge=1, le=20)
    qqe_factor: float = Field(default=3.0, ge=0.5, le=10.0)
    htf_vwma_len: int = Field(default=156, ge=10, le=500, description="HTF VWMA 길이 (주식용)")
    htf_sma_len: int = Field(default=200, ge=10, le=500, description="HTF SMA 길이 (크립토용)")
    asset_type: str = Field(default="stock", description="자산 유형 (stock/crypto)")

    # SPO 지표 설정 (signal_tf 기준)
    exit_spo_smooth_len: int = Field(default=4, ge=1, le=20)
    exit_spo_threshold: float = Field(default=1.0, ge=0.0, le=5.0)
    exit_spo_std_len: int = Field(default=50, ge=10, le=200)
    exit_spo_hma_len: int = Field(default=30, ge=5, le=100)

    # Exit 조건
    hard_sl_pct: float = Field(default=7.0, ge=1.0, le=30.0)
    tp1_pct: float = Field(default=21.0, ge=1.0, le=100.0)
    tp1_sell_pct: float = Field(default=50.0, ge=10.0, le=100.0)
    use_spo_split: bool = Field(default=True)
    use_st_flip_exit: bool = Field(default=True)

    # 분할매도 설정 (v8: 역피라미드 [5,5,10,15,25,40])
    sell_tranches: List[float] = Field(default=[5.0, 5.0, 10.0, 15.0, 25.0, 40.0])
    max_sell_tranches: int = Field(default=6, ge=1, le=10)
    after_max_sell: str = Field(default="cycle")

    # 익절 게이트
    use_profit_gate: bool = Field(default=True)
    min_profit_pct: float = Field(default=0.10, ge=0.0, le=10.0)
    fee_buffer_pct: float = Field(default=0.20, ge=0.0, le=5.0)

    # 포지션 사이징
    cash_use_pct: float = Field(default=100.0, ge=0, le=100)

    # ============ v8 신규 필드 ============
    # 피라미딩 (추가매수)
    use_pyramiding: bool = Field(default=True, description="피라미딩 사용 여부")
    max_pyr_entries: int = Field(default=4, ge=1, le=10, description="최대 피라미딩 횟수")
    pyr_high_len: int = Field(default=60, ge=5, le=200, description="N-bar 최고가 기준 봉수")
    pyr_cooldown: int = Field(default=5, ge=1, le=50, description="피라미딩 쿨다운 (봉)")
    pyr_refill_after_sell: bool = Field(default=False, description="분할매도 후 피라미딩 카운트 리필")
    pyr_weights: List[float] = Field(
        default=[40.0, 30.0, 20.0, 10.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0],
        description="피라미딩 가중치 (%)"
    )

    # 손절 타입 (v8: ATR 기반 손절 지원)
    stop_type: str = Field(default="fixed", description="손절 타입 (fixed/atr)")
    atr_stop_len: int = Field(default=14, ge=5, le=50, description="ATR 손절 기간")
    atr_stop_mult: float = Field(default=2.0, ge=0.5, le=5.0, description="ATR 손절 배수")

    # ST 전량매도 (exit_tf의 ST 사용)
    use_st_exit: bool = Field(default=True, description="ST 하락 전환 시 전량매도")

    # v8 토글
    use_tp1: bool = Field(default=False, description="TP1 사용 여부 (v8 기본 OFF)")
    st_invert: bool = Field(default=False, description="Supertrend 반전")
    use_htf_filter: bool = Field(default=True, description="HTF VWMA 필터 사용")

    # Entry Guard (v8)
    enter_only_on_setup_start: bool = Field(default=True, description="조건 시작시에만 진입")
    use_live_guard: bool = Field(default=False, description="실시간 가드 (백테스트 OFF)")

    # 수량 반올림 (주식용)
    round_qty: bool = Field(default=True, description="수량 정수 반올림")
    min_qty: float = Field(default=1.0, ge=0.0001, description="최소 수량")


class TrendBacktestResponse(BaseModel):
    """Response model for Trend backtest (MR과 동일 구조)."""
    success: bool
    message: str = ""
    error: Optional[str] = None
    exchange: Optional[str] = None  # 화폐 단위 결정용
    symbol: Optional[str] = None    # 화폐 단위 결정용 (USDT/USDC 등)
    metrics: Dict[str, Any] = {}
    equity_curve: List[Dict[str, Any]] = []
    trades: List[Dict[str, Any]] = []
    candles: List[Dict[str, Any]] = []  # 캔들차트용 OHLCV 데이터
    signals_count: int = 0


@router.post("/backtest/trend", response_model=TrendBacktestResponse)
async def run_trend_backtest_endpoint(
    request: TrendBacktestRequest,
):
    """
    추세매매(Trend) 전략 백테스트 실행.

    실제 거래소 OHLCV 데이터로 백테스트를 실행합니다 (MR과 동일 인프라).
    Entry: Supertrend 상승 + HVI 초록 + QQE 양수 + close > HTF VWMA156
    Exit: Hard SL > TP1 > SPO Split > ST Flip (우선순위순)
    """
    import time as _time
    _t0 = _time.time()

    from .strategy_engine.backtest_engine_trend import run_trend_backtest
    from .strategy_engine.candle_fetcher import fetch_candles_for_backtest
    from .strategy_engine.signal_generator_trend import TrendConfig

    try:
        # ① 실제 거래소 캔들 조회 (signal_tf 기준)
        _t1 = _time.time()
        candles = await fetch_candles_for_backtest(
            exchange=request.exchange,
            symbol=request.symbol,
            timeframe=request.signal_tf,
            days=request.days,
            timeout=60,
        )

        # ② exit_tf 캔들 조회 (ST 전량매도 전용)
        # KIS는 주봉 조회가 느리므로 signal_tf만 사용
        exit_candles = None
        skip_htf_for_kis = request.exchange.upper() in ["KIS_KR", "KIS_US"]
        if not skip_htf_for_kis and request.exit_tf and request.exit_tf != request.signal_tf:
            try:
                exit_candles = await fetch_candles_for_backtest(
                    exchange=request.exchange,
                    symbol=request.symbol,
                    timeframe=request.exit_tf,
                    days=request.days,
                    timeout=30,
                )
            except ValueError:
                pass  # exit_tf 조회 실패 시 signal_tf 단독 사용

        # ③ htf_tf 캔들 조회 (HTF VWMA 필터 전용)
        htf_candles = None
        if not skip_htf_for_kis and request.htf_tf and request.htf_tf != request.signal_tf:
            try:
                htf_candles = await fetch_candles_for_backtest(
                    exchange=request.exchange,
                    symbol=request.symbol,
                    timeframe=request.htf_tf,
                    days=request.days,
                    timeout=30,
                )
            except ValueError:
                pass  # htf_tf 조회 실패 시 signal_tf 단독 사용

        _t2 = _time.time()

        # ④ Trend 설정 생성 (v8 최종 - TF 3개)
        config = TrendConfig(
            signal_tf=request.signal_tf,
            exit_tf=request.exit_tf,
            htf_tf=request.htf_tf,
            st_atr_len=request.st_atr_len,
            st_factor=request.st_factor,
            hvi_length=request.hvi_length,
            hvi_divisor=request.hvi_divisor,
            qqe_rsi_length=request.qqe_rsi_length,
            qqe_rsi_smoothing=request.qqe_rsi_smoothing,
            qqe_factor=request.qqe_factor,
            htf_vwma_len=request.htf_vwma_len,
            htf_sma_len=request.htf_sma_len,
            asset_type=request.asset_type,
            exit_spo_smooth_len=request.exit_spo_smooth_len,
            exit_spo_threshold=request.exit_spo_threshold,
            exit_spo_std_len=request.exit_spo_std_len,
            exit_spo_hma_len=request.exit_spo_hma_len,
            hard_sl_pct=request.hard_sl_pct,
            tp1_pct=request.tp1_pct,
            tp1_sell_pct=request.tp1_sell_pct,
            use_spo_split=request.use_spo_split,
            use_st_flip_exit=request.use_st_flip_exit,
            sell_tranches=request.sell_tranches,
            max_sell_tranches=request.max_sell_tranches,
            after_max_sell=request.after_max_sell,
            use_profit_gate=request.use_profit_gate,
            min_profit_pct=request.min_profit_pct,
            fee_buffer_pct=request.fee_buffer_pct,
            cash_use_pct=request.cash_use_pct,
            # v8 신규 필드
            use_pyramiding=request.use_pyramiding,
            max_pyr_entries=request.max_pyr_entries,
            pyr_high_len=request.pyr_high_len,
            pyr_cooldown=request.pyr_cooldown,
            pyr_refill_after_sell=request.pyr_refill_after_sell,
            pyr_weights=request.pyr_weights,
            stop_type=request.stop_type,
            atr_stop_len=request.atr_stop_len,
            atr_stop_mult=request.atr_stop_mult,
            use_st_exit=request.use_st_exit,
            use_tp1=request.use_tp1,
            st_invert=request.st_invert,
            use_htf_filter=request.use_htf_filter,
            enter_only_on_setup_start=request.enter_only_on_setup_start,
            use_live_guard=request.use_live_guard,
            round_qty=request.round_qty,
            min_qty=request.min_qty,
        )

        # ⑤ 백테스트 실행
        _t3 = _time.time()
        result = run_trend_backtest(
            candles=candles,
            exit_candles=exit_candles,
            htf_candles=htf_candles,
            config=config,
            initial_capital=request.initial_capital,
        )
        _t4 = _time.time()

        # 백테스트 실패 시
        if not result.success:
            return TrendBacktestResponse(
                success=False,
                message=result.message,
                error=result.message,
            )

        # 결과 변환 - trades 확장 (MR과 동일, 트레이딩뷰 동일)
        trades_list = []
        cumulative_pnl = 0.0
        for idx, t in enumerate(result.trades):
            if t.action == "sell" and t.pnl is not None:
                cumulative_pnl += t.pnl

            # 거래 타입 (한글)
            type_text = "매수" if t.action == "buy" else "매도"

            # 차수 (피라미딩 포함)
            if t.action == "buy":
                tranche_text = f"매수{t.tranche + 1}차"
            else:
                tranche_text = f"매도{t.tranche + 1}차"

            # 날짜 포맷
            from datetime import datetime
            date_str = ""
            if t.timestamp:
                dt = datetime.fromtimestamp(t.timestamp / 1000)
                date_str = dt.strftime("%Y-%m-%d %H:%M")

            trades_list.append({
                "no": idx + 1,
                "type": type_text,
                "date": date_str,
                "bar_index": t.bar_index,
                "timestamp": t.timestamp,
                "action": t.action,
                "price": round(t.price, 2),
                "qty": round(t.quantity, 6),
                "quantity": t.quantity,
                "tranche": tranche_text,
                "tranche_idx": t.tranche,
                "reason_code": t.reason_code,
                "pnl": round(t.pnl, 2) if t.pnl is not None else None,
                "pnl_pct": round(t.pnl_pct, 2) if t.pnl_pct is not None else None,
                "cumulative_pnl": round(cumulative_pnl, 2) if t.action == "sell" else None,
                "commission": round(t.commission, 4) if t.commission else 0,
            })

        # equity_curve 샘플링 (최대 200포인트로 제한)
        equity_curve = result.equity_curve
        if len(equity_curve) > 200:
            step = max(1, len(equity_curve) // 200)
            equity_curve = equity_curve[::step]

        # 추가 메트릭 계산
        sell_trades = [t for t in result.trades if t.action == "sell" and t.pnl_pct is not None]
        max_profit_pct = max((t.pnl_pct for t in sell_trades if t.pnl_pct > 0), default=0.0)
        max_loss_pct = min((t.pnl_pct for t in sell_trades if t.pnl_pct <= 0), default=0.0)

        m = result.metrics  # 편의상 alias

        # 캔들 데이터 (차트용, 최대 1000개로 샘플링)
        candle_data = []
        step = max(1, len(candles) // 1000)
        for i in range(0, len(candles), step):
            c = candles[i]
            candle_data.append({
                "time": c.ts // 1000,  # Unix 초 단위
                "open": c.o,
                "high": c.h,
                "low": c.l,
                "close": c.c,
                "volume": c.v,
            })

        return TrendBacktestResponse(
            success=True,
            message=f"백테스트 완료: {len(candles)}봉 분석, {m.total_trades}거래",
            exchange=request.exchange,  # 화폐 단위 결정용
            symbol=request.symbol,      # 화폐 단위 결정용 (USDT/USDC 등)
            metrics={
                # === 기본 ===
                "initial_capital": round(m.initial_capital, 0),
                "final_capital": round(m.final_capital, 0),
                "total_return_pct": round(m.total_return_pct, 2),
                "cagr_pct": round(m.cagr_pct, 2),
                "max_drawdown_pct": round(m.max_drawdown_pct, 2),
                "sharpe_ratio": round(m.sharpe_ratio, 2),
                "win_rate_pct": round(m.win_rate_pct, 1),
                "total_trades": m.total_trades,
                "winning_trades": m.winning_trades,
                "losing_trades": m.losing_trades,
                "profit_factor": round(m.profit_factor, 3) if m.profit_factor != float('inf') else 999.99,

                # === 트레이딩뷰 추가 필드 ===
                "net_profit": round(m.net_profit, 2),
                "net_profit_pct": round(m.net_profit_pct, 2),
                "gross_profit": round(m.gross_profit, 2),
                "gross_profit_pct": round(m.gross_profit_pct, 2),
                "gross_loss": round(m.gross_loss, 2),
                "gross_loss_pct": round(m.gross_loss_pct, 2),
                "max_drawdown": round(m.max_drawdown, 2),
                "commission_paid": round(m.commission_paid, 4),
                "expected_value": round(m.expected_value, 2),
                "unrealized_pnl": round(m.unrealized_pnl, 2),
                "unrealized_pnl_pct": round(m.unrealized_pnl_pct, 2),

                # === 매수 분리 ===
                "buy_net_profit": round(m.buy_net_profit, 2),
                "buy_net_profit_pct": round(m.buy_net_profit_pct, 2),
                "buy_gross_profit": round(m.buy_gross_profit, 2),
                "buy_gross_profit_pct": round(m.buy_gross_profit_pct, 2),
                "buy_gross_loss": round(m.buy_gross_loss, 2),
                "buy_gross_loss_pct": round(m.buy_gross_loss_pct, 2),
                "buy_profit_factor": round(m.buy_profit_factor, 3) if m.buy_profit_factor != float('inf') else 999.99,
                "buy_commission": round(m.buy_commission, 4),
                "buy_expected_value": round(m.buy_expected_value, 2),
                "buy_trades": m.buy_trades,
                "buy_winning": m.buy_winning,
                "buy_losing": m.buy_losing,

                # === 매도 분리 (추세매매는 롱 전용이므로 0) ===
                "sell_net_profit": 0,
                "sell_net_profit_pct": 0,
                "sell_gross_profit": 0,
                "sell_gross_profit_pct": 0,
                "sell_gross_loss": 0,
                "sell_gross_loss_pct": 0,
                "sell_profit_factor": 0,
                "sell_commission": 0,
                "sell_expected_value": 0,
                "sell_trades": 0,
                "sell_winning": 0,
                "sell_losing": 0,

                # === 기존 호환 ===
                "avg_win_pct": round(m.avg_win_pct, 2),
                "avg_loss_pct": round(m.avg_loss_pct, 2),
                "max_consecutive_wins": m.max_consecutive_wins,
                "max_consecutive_losses": m.max_consecutive_losses,
                "avg_profit_pct": round(m.avg_win_pct, 2) if m.avg_win_pct else 0.0,
                "max_profit_pct": round(max_profit_pct, 2),
                "max_loss_pct": round(max_loss_pct, 2),
            },
            equity_curve=equity_curve,
            trades=trades_list,
            candles=candle_data,
            signals_count=len(result.signals),
        )

    except ValueError as e:
        # 사용자 친화적 에러 (한글)
        logger.warning(f"Trend 백테스트 입력 오류: {e}")
        return TrendBacktestResponse(
            success=False,
            message=str(e),
            error=str(e),
        )
    except Exception as e:
        # 예상치 못한 에러
        logger.error(f"Trend 백테스트 오류: {e}", exc_info=True)
        return TrendBacktestResponse(
            success=False,
            message=f"백테스트 실행 중 오류가 발생했습니다. 설정을 확인해주세요. ({type(e).__name__})",
            error=f"백테스트 실행 중 오류가 발생했습니다. 설정을 확인해주세요. ({type(e).__name__})",
        )


# ============================================================================
# CUSTOM STRATEGY BACKTEST (조건 빌더)
# ============================================================================

from app.strategy_engine.custom_strategy import (
    CustomBacktestRequest,
    CustomBacktestResponse,
)
from app.strategy_engine.indicator_registry import INDICATOR_REGISTRY, OPERATORS


@router.get("/indicators")
async def get_indicators():
    """
    프론트엔드 조건 빌더에서 사용할 지표 목록 반환.
    """
    return {
        "success": True,
        "indicators": INDICATOR_REGISTRY,
        "operators": OPERATORS,
    }


@router.post("/backtest/custom", response_model=CustomBacktestResponse)
async def run_custom_backtest_endpoint(request: CustomBacktestRequest):
    """
    커스텀 전략 백테스트 실행.

    사용자가 조건 빌더로 생성한 전략을 실제 OHLCV 데이터로 백테스트합니다.
    """
    import time as _time
    from datetime import datetime

    from app.strategy_engine.backtest_engine_custom import run_custom_backtest
    from app.strategy_engine.candle_fetcher import fetch_candles_for_backtest

    _t0 = _time.time()

    try:
        # ① 캔들 조회
        candles = await fetch_candles_for_backtest(
            exchange=request.exchange,
            symbol=request.symbol,
            timeframe=request.timeframe,
            days=request.days,
            timeout=60,
        )

        if not candles:
            return CustomBacktestResponse(
                success=False,
                message=f"캔들 데이터 조회 실패: {request.exchange} {request.symbol}",
            )

        _t1 = _time.time()

        # ② 백테스트 실행
        result = await run_custom_backtest(
            candles=candles,
            config=request.strategy,
            initial_capital=request.initial_capital,
        )

        _t2 = _time.time()

        if not result.get("success"):
            return CustomBacktestResponse(
                success=False,
                message=result.get("message", "백테스트 실패"),
            )

        # ③ 결과 처리 (트레이딩뷰 형식 맞추기)
        trades_list = []
        cumulative_pnl = 0.0

        for idx, t in enumerate(result.get("trades", [])):
            if t.get("action") == "sell" and t.get("pnl") is not None:
                cumulative_pnl += t["pnl"]

            type_text = "매수" if t.get("action") == "buy" else "매도"
            reason_map = {
                "entry": "진입",
                "exit": "청산",
                "stop_loss": "손절",
                "take_profit": "익절",
            }
            tranche_text = reason_map.get(t.get("reason", ""), t.get("reason", ""))

            date_str = ""
            if t.get("timestamp"):
                dt = datetime.fromtimestamp(t["timestamp"] / 1000)
                date_str = dt.strftime("%Y-%m-%d %H:%M")

            trades_list.append({
                "no": idx + 1,
                "type": type_text,
                "date": date_str,
                "bar_index": t.get("bar_index"),
                "timestamp": t.get("timestamp"),
                "action": t.get("action"),
                "price": round(t.get("price", 0), 2),
                "qty": round(t.get("quantity", 0), 6),
                "quantity": t.get("quantity"),
                "tranche": tranche_text,
                "reason": t.get("reason"),
                "pnl": round(t["pnl"], 2) if t.get("pnl") is not None else None,
                "pnl_pct": round(t["pnl_pct"], 2) if t.get("pnl_pct") is not None else None,
                "cumulative_pnl": round(cumulative_pnl, 2) if t.get("action") == "sell" else None,
                "commission": round(t.get("commission", 0), 4),
            })

        # equity_curve 샘플링 (최대 200포인트)
        equity_curve = result.get("equity_curve", [])
        if len(equity_curve) > 200:
            step = max(1, len(equity_curve) // 200)
            equity_curve = equity_curve[::step]

        # 캔들 데이터 (차트용)
        candle_data = []
        raw_candles = result.get("candles", [])
        for c in raw_candles[:1000]:
            candle_data.append({
                "time": c.get("timestamp", 0) // 1000,
                "open": c.get("open"),
                "high": c.get("high"),
                "low": c.get("low"),
                "close": c.get("close"),
                "volume": c.get("volume"),
            })

        m = result.get("metrics", {})

        return CustomBacktestResponse(
            success=True,
            message=f"백테스트 완료: {len(candles)}봉 분석, {m.get('total_trades', 0)}거래",
            metrics={
                "initial_capital": round(m.get("initial_capital", 0), 0),
                "final_capital": round(m.get("final_capital", 0), 0),
                "total_return_pct": round(m.get("total_return_pct", 0), 2),
                "cagr_pct": round(m.get("cagr_pct", 0), 2),
                "max_drawdown_pct": round(m.get("max_drawdown_pct", 0), 2),
                "sharpe_ratio": round(m.get("sharpe_ratio", 0), 2),
                "win_rate_pct": round(m.get("win_rate_pct", 0), 1),
                "total_trades": m.get("total_trades", 0),
                "winning_trades": m.get("winning_trades", 0),
                "losing_trades": m.get("losing_trades", 0),
                "profit_factor": round(m.get("profit_factor", 0), 3) if m.get("profit_factor") != float('inf') else 999.99,
                "net_profit": round(m.get("net_profit", 0), 2),
                "net_profit_pct": round(m.get("net_profit_pct", 0), 2),
                "gross_profit": round(m.get("gross_profit", 0), 2),
                "gross_profit_pct": round(m.get("gross_profit_pct", 0), 2),
                "gross_loss": round(m.get("gross_loss", 0), 2),
                "gross_loss_pct": round(m.get("gross_loss_pct", 0), 2),
                "max_drawdown": round(m.get("max_drawdown", 0), 2),
                "commission_paid": round(m.get("commission_paid", 0), 4),
                "expected_value": round(m.get("expected_value", 0), 2),
                "unrealized_pnl": round(m.get("unrealized_pnl", 0), 2),
                "unrealized_pnl_pct": round(m.get("unrealized_pnl_pct", 0), 2),
                "avg_win_pct": round(m.get("avg_win_pct", 0), 2),
                "avg_loss_pct": round(m.get("avg_loss_pct", 0), 2),
                "max_consecutive_wins": m.get("max_consecutive_wins", 0),
                "max_consecutive_losses": m.get("max_consecutive_losses", 0),

                # 매수 분리
                "buy_net_profit": round(m.get("buy_net_profit", 0), 2),
                "buy_net_profit_pct": round(m.get("buy_net_profit_pct", 0), 2),
                "buy_gross_profit": round(m.get("buy_gross_profit", 0), 2),
                "buy_gross_profit_pct": round(m.get("buy_gross_profit_pct", 0), 2),
                "buy_gross_loss": round(m.get("buy_gross_loss", 0), 2),
                "buy_gross_loss_pct": round(m.get("buy_gross_loss_pct", 0), 2),
                "buy_commission": round(m.get("buy_commission", 0), 4),
                "buy_trades": m.get("buy_trades", 0),
                "buy_winning": m.get("buy_winning", 0),
                "buy_losing": m.get("buy_losing", 0),

                # 매도 분리 (롱 전용이므로 0)
                "sell_net_profit": 0,
                "sell_net_profit_pct": 0,
                "sell_gross_profit": 0,
                "sell_gross_profit_pct": 0,
                "sell_gross_loss": 0,
                "sell_gross_loss_pct": 0,
                "sell_commission": 0,
                "sell_trades": 0,
                "sell_winning": 0,
                "sell_losing": 0,
            },
            equity_curve=equity_curve,
            trades=trades_list,
            candles=candle_data,
        )

    except ValueError as e:
        logger.warning(f"Custom 백테스트 입력 오류: {e}")
        return CustomBacktestResponse(
            success=False,
            message=str(e),
        )
    except Exception as e:
        logger.error(f"Custom 백테스트 오류: {e}", exc_info=True)
        return CustomBacktestResponse(
            success=False,
            message=f"백테스트 실행 중 오류가 발생했습니다. ({type(e).__name__})",
        )


# ============================================================================
# DEBUG: MR 봉별 지표 데이터 (PineScript 비교용)
# ============================================================================

class MRDebugRequest(BaseModel):
    """MR 디버그 요청 모델."""
    exchange: str = Field(default="OKX")
    symbol: str = Field(default="BTC-USDT")
    timeframe: str = Field(default="1D")
    days: int = Field(default=30, ge=1, le=365)
    osc_preset: str = Field(default="preset1")
    start_bar: int = Field(default=0, ge=0, description="시작 봉 인덱스")
    limit: int = Field(default=20, ge=1, le=100, description="출력할 봉 수")


class MRDebugBarData(BaseModel):
    """MR 봉별 데이터."""
    bar_index: int
    timestamp: int
    date: str
    close: float
    line_short: float
    line_long: float
    oscillator: float
    normalized_osc: float
    upper_band: float
    lower_band: float
    basis: float
    threshold: float
    sig_up_raw: bool
    sig_dn_raw: bool


class MRDebugResponse(BaseModel):
    """MR 디버그 응답 모델."""
    success: bool
    message: str
    exchange: str = ""
    symbol: str = ""
    timeframe: str = ""
    total_bars: int = 0
    preset: str = ""
    smooth_len: int = 0
    bars: List[MRDebugBarData] = []


@router.post("/debug/mr-indicators", response_model=MRDebugResponse)
async def debug_mr_indicators(request: MRDebugRequest):
    """
    역추세매매 봉별 지표 데이터 출력 (PineScript Data Window 비교용).

    출력 항목:
    - line_short, line_long (smoother_f 결과)
    - oscillator (line_short - line_long)
    - normalized_osc (HMA 적용 후)
    - upper_band, lower_band, basis (볼린저 밴드)
    - sig_up_raw, sig_dn_raw (매수/매도 신호)
    """
    import numpy as np
    from datetime import datetime, timezone
    from app.strategy_engine.candle_fetcher import fetch_candles_for_backtest
    from app.strategy_engine.indicators import smoother_f, calc_hma, calc_stdev, calc_highest
    from app.strategy_engine.presets import OSC_PRESETS

    try:
        # 캔들 조회
        candles = await fetch_candles_for_backtest(
            exchange=request.exchange,
            symbol=request.symbol,
            timeframe=request.timeframe,
            days=request.days,
        )

        if not candles or len(candles) < 50:
            return MRDebugResponse(
                success=False,
                message=f"캔들 데이터 부족: {len(candles) if candles else 0}봉",
            )

        # 프리셋 파라미터
        params = OSC_PRESETS.get(request.osc_preset, OSC_PRESETS["preset1"])
        smooth_len = params["smooth_len"]
        threshold = params["threshold"]
        std_len = params["std_len"]
        hma_len = params["hma_len"]
        bb_len = params["bb_len"]
        bb_mult = params["bb_mult"]

        # 종가 배열
        closes = np.array([c.c for c in candles])

        # 지표 계산 (PineScript와 동일)
        # line_long = smoother_F(close, smooth_len * 2)
        # line_short = smoother_F(close, smooth_len)
        line_long = smoother_f(closes, smooth_len * 2)
        line_short = smoother_f(closes, smooth_len)

        # oscillator = line_short - line_long
        oscillator = line_short - line_long

        # stdev_osc = ta.stdev(oscillator, std_len)
        stdev_osc = calc_stdev(oscillator, std_len)

        # denom = max(highest(stdev_osc, std_len), 1e-10)
        highest_stdev = calc_highest(stdev_osc, std_len)
        denom = np.maximum(highest_stdev, 1e-10)

        # normalized_osc = ta.hma(oscillator / denom, hma_len)
        osc_normalized_raw = oscillator / denom
        normalized_osc = calc_hma(osc_normalized_raw, hma_len)

        # 볼린저 밴드: basis = ta.ema(normalized_osc, bb_len)
        basis = smoother_f(normalized_osc, bb_len)
        stdev_norm = calc_stdev(normalized_osc, bb_len)
        deviation = bb_mult * stdev_norm
        upper_band = basis + deviation
        lower_band = basis - deviation

        # 신호 생성
        # sig_up_raw = normalized_osc < -threshold AND crossover(normalized_osc, normalized_osc[1])
        # sig_dn_raw = normalized_osc > threshold AND crossover(normalized_osc[1], normalized_osc)
        n = len(closes)
        sig_up_raw = np.zeros(n, dtype=bool)
        sig_dn_raw = np.zeros(n, dtype=bool)

        for i in range(2, n):
            osc_curr = normalized_osc[i]
            osc_prev = normalized_osc[i-1]
            osc_prev_prev = normalized_osc[i-2]

            if not (np.isnan(osc_curr) or np.isnan(osc_prev) or np.isnan(osc_prev_prev)):
                # sig_up: osc < -threshold AND osc_curr > osc_prev AND osc_prev <= osc_prev_prev
                sig_up_raw[i] = (
                    osc_curr < -threshold and
                    osc_curr > osc_prev and
                    osc_prev <= osc_prev_prev
                )
                # sig_dn: osc > threshold AND osc_curr < osc_prev AND osc_prev >= osc_prev_prev
                sig_dn_raw[i] = (
                    osc_curr > threshold and
                    osc_curr < osc_prev and
                    osc_prev >= osc_prev_prev
                )

        # 결과 생성
        bars = []
        start = max(request.start_bar, 0)
        end = min(start + request.limit, n)

        for i in range(start, end):
            candle = candles[i]
            dt = datetime.fromtimestamp(candle.ts / 1000, tz=timezone.utc)

            def safe_float(v):
                return round(float(v), 6) if not np.isnan(v) else 0.0

            bars.append(MRDebugBarData(
                bar_index=i,
                timestamp=candle.ts,
                date=dt.strftime("%Y-%m-%d %H:%M"),
                close=round(candle.c, 2),
                line_short=safe_float(line_short[i]),
                line_long=safe_float(line_long[i]),
                oscillator=safe_float(oscillator[i]),
                normalized_osc=safe_float(normalized_osc[i]),
                upper_band=safe_float(upper_band[i]),
                lower_band=safe_float(lower_band[i]),
                basis=safe_float(basis[i]),
                threshold=threshold,
                sig_up_raw=bool(sig_up_raw[i]),
                sig_dn_raw=bool(sig_dn_raw[i]),
            ))

        return MRDebugResponse(
            success=True,
            message=f"총 {n}봉 중 {len(bars)}봉 출력",
            exchange=request.exchange,
            symbol=request.symbol,
            timeframe=request.timeframe,
            total_bars=n,
            preset=request.osc_preset,
            smooth_len=smooth_len,
            bars=bars,
        )

    except Exception as e:
        logger.error(f"MR 디버그 오류: {e}", exc_info=True)
        return MRDebugResponse(
            success=False,
            message=f"오류: {str(e)}",
        )


# ============================================================================
# Trend Debug Endpoint (추세매매 지표 디버깅)
# ============================================================================

class TrendDebugRequest(BaseModel):
    """Trend 디버그 요청 모델."""
    exchange: str = Field(default="KIS_KR")
    symbol: str = Field(default="005930")
    timeframe: str = Field(default="1D")
    days: int = Field(default=365, ge=30, le=1000)
    start_bar: int = Field(default=0, ge=0)
    limit: int = Field(default=20, ge=1, le=100)


class TrendDebugBarData(BaseModel):
    """Trend 봉별 데이터."""
    bar_index: int
    timestamp: int
    date: str
    close: float
    st_direction: int  # -1=bullish, 1=bearish
    st_value: float
    hvi_green: bool
    hvi_red: bool
    qqe_positive: bool
    htf_vwma: float
    above_htf: bool
    entry_condition: bool  # 4조건 모두 충족 여부


class TrendDebugResponse(BaseModel):
    """Trend 디버그 응답 모델."""
    success: bool
    message: str
    exchange: str = ""
    symbol: str = ""
    timeframe: str = ""
    total_bars: int = 0
    bars: List[TrendDebugBarData] = []


@router.post("/debug/trend-indicators", response_model=TrendDebugResponse)
async def debug_trend_indicators(request: TrendDebugRequest):
    """
    추세매매 봉별 지표 데이터 출력 (신호 검증용).

    출력 항목:
    - Supertrend direction/value
    - HVI green/red
    - QQE positive
    - HTF VWMA 및 close > vwma 여부
    - 4조건 진입 조건 충족 여부
    """
    import numpy as np
    from datetime import datetime, timezone
    from app.strategy_engine.candle_fetcher import fetch_candles_for_backtest
    from app.strategy_engine.indicators import calc_supertrend, calc_hvi, calc_qqe_mod

    try:
        # 캔들 조회
        candles = await fetch_candles_for_backtest(
            exchange=request.exchange,
            symbol=request.symbol,
            timeframe=request.timeframe,
            days=request.days,
        )

        if not candles or len(candles) < 250:
            return TrendDebugResponse(
                success=False,
                message=f"캔들 데이터 부족: {len(candles) if candles else 0}봉 (최소 250봉 필요)",
            )

        # 가격 배열
        opens = np.array([c.o for c in candles])
        highs = np.array([c.h for c in candles])
        lows = np.array([c.l for c in candles])
        closes = np.array([c.c for c in candles])
        volumes = np.array([c.v for c in candles])
        n = len(closes)

        # 지표 계산
        st_values, st_directions = calc_supertrend(highs, lows, closes, atr_len=20, factor=5.0)
        hvi = calc_hvi(highs, lows, closes, volumes, length=200, divisor=3.6)
        qqe = calc_qqe_mod(closes, rsi_length=6, rsi_smoothing=5, qqe_factor=3.0)

        # HTF VWMA (SMA로 대체 - 주식용 156, 크립토 200)
        vwma_len = 156 if request.exchange.startswith("KIS") else 200
        htf_vwma = np.full(n, np.nan)
        for i in range(vwma_len - 1, n):
            htf_vwma[i] = np.mean(closes[i - vwma_len + 1:i + 1])

        # 결과 생성
        bars = []
        start = max(request.start_bar, 0)
        end = min(start + request.limit, n)

        for i in range(start, end):
            candle = candles[i]
            dt = datetime.fromtimestamp(candle.ts / 1000, tz=timezone.utc)

            st_dir = int(st_directions[i]) if not np.isnan(st_directions[i]) else 0
            st_val = float(st_values[i]) if not np.isnan(st_values[i]) else 0.0
            hvi_g = bool(hvi["g_enabled"][i]) if not np.isnan(hvi["g_enabled"][i]) else False
            hvi_r = bool(hvi["r_enabled"][i]) if not np.isnan(hvi["r_enabled"][i]) else False
            qqe_pos = bool(qqe["is_positive"][i]) if not np.isnan(qqe["is_positive"][i]) else False
            htf_val = float(htf_vwma[i]) if not np.isnan(htf_vwma[i]) else 0.0
            above_htf = closes[i] > htf_vwma[i] if not np.isnan(htf_vwma[i]) else False

            # 4조건 진입 조건
            entry_cond = (st_dir < 0) and hvi_g and qqe_pos and above_htf

            bars.append(TrendDebugBarData(
                bar_index=i,
                timestamp=candle.ts,
                date=dt.strftime("%Y-%m-%d %H:%M"),
                close=round(candle.c, 2),
                st_direction=st_dir,
                st_value=round(st_val, 2),
                hvi_green=hvi_g,
                hvi_red=hvi_r,
                qqe_positive=qqe_pos,
                htf_vwma=round(htf_val, 2),
                above_htf=above_htf,
                entry_condition=entry_cond,
            ))

        return TrendDebugResponse(
            success=True,
            message=f"총 {n}봉 중 {len(bars)}봉 출력",
            exchange=request.exchange,
            symbol=request.symbol,
            timeframe=request.timeframe,
            total_bars=n,
            bars=bars,
        )

    except Exception as e:
        logger.error(f"Trend 디버그 오류: {e}", exc_info=True)
        return TrendDebugResponse(
            success=False,
            message=f"오류: {str(e)}",
        )

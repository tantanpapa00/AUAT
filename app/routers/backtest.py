# app/routers/backtest.py
# 백테스트 및 전략 관리 API 엔드포인트

import json
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session
from sqlalchemy import text

from app.db import get_db
from app.auth import get_current_user, get_current_user_optional
from app.models import User

from app.backtest import run_backtest, BacktestRequest, BacktestResult
from app.strategy_engine.backtest_engine_trend import run_trend_backtest as run_trend_v8
from app.strategy_engine.signal_generator_trend import TrendConfig
from app.strategy_engine.indicator_registry import INDICATOR_REGISTRY, INDICATOR_CATEGORIES, OPERATORS
from app.strategy_engine.custom_strategy import (
    CustomStrategyConfig, CustomBacktestRequest, CustomBacktestResponse,
    ConditionItem, ConditionGroup, CustomRule
)
from app.strategy_engine.backtest_engine_custom import run_custom_backtest
from app.strategy_engine.candle_fetcher import fetch_candles_for_backtest
from app.strategy_engine.models import Candle

router = APIRouter(prefix="/api", tags=["backtest"])


def _ensure_strategies_table(db: Session):
    """strategies 테이블이 없으면 생성"""
    create_sql = text("""
        CREATE TABLE IF NOT EXISTS strategies (
            id SERIAL PRIMARY KEY,
            user_id INTEGER REFERENCES users(id),
            name VARCHAR(255),
            strategy_type VARCHAR(50),
            exchange VARCHAR(50),
            symbol VARCHAR(50),
            params JSONB,
            order_settings JSONB,
            is_active BOOLEAN DEFAULT false,
            created_at TIMESTAMP DEFAULT NOW(),
            updated_at TIMESTAMP DEFAULT NOW()
        )
    """)
    db.execute(create_sql)
    db.commit()


class BacktestRequestBody(BaseModel):
    strategy_type: str  # custom, reversal, trend
    exchange: str
    symbol: str
    start_date: str
    end_date: str
    initial_capital: float = 10000000
    params: Optional[dict] = {}
    order_settings: Optional[dict] = {}


class StrategyCreateRequest(BaseModel):
    name: str
    strategy_type: str
    exchange: str
    symbol: str
    params: Optional[dict] = {}
    order_settings: Optional[dict] = {}
    is_active: bool = False


@router.post("/backtest")
async def api_run_backtest(
    request: BacktestRequestBody,
    current_user: User = Depends(get_current_user_optional)
):
    """백테스팅 실행 (trend는 v8 엔진 사용)"""
    if current_user:
        plan = getattr(current_user, "plan", "free")
        role = getattr(current_user, "role", "user")
        if plan != "premium" and role != "admin":
            raise HTTPException(status_code=403, detail="프리미엄 요금제에서 이용 가능합니다")

    try:
        if request.strategy_type == "trend":
            return await _run_trend_v8_backtest(request)

        backtest_request = BacktestRequest(
            strategy_type=request.strategy_type,
            exchange=request.exchange,
            symbol=request.symbol,
            start_date=request.start_date,
            end_date=request.end_date,
            initial_capital=request.initial_capital,
            params=request.params or {},
            order_settings=request.order_settings or {}
        )

        result = run_backtest(backtest_request)
        return result.dict()

    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"백테스팅 실행 오류: {str(e)}")


async def _run_trend_v8_backtest(request: BacktestRequestBody) -> dict:
    """Trend v8 백테스트 실행"""
    from datetime import datetime

    try:
        d1 = datetime.strptime(request.start_date, "%Y-%m-%d")
        d2 = datetime.strptime(request.end_date, "%Y-%m-%d")
        days = (d2 - d1).days + 50
    except:
        days = 400

    exchange_lower = request.exchange.lower()
    is_crypto = exchange_lower in ("okx", "binance", "bybit")
    asset_type = "crypto" if is_crypto else "stock"

    candles = await fetch_candles_for_backtest(
        exchange=exchange_lower,
        symbol=request.symbol,
        timeframe="1D",
        days=days,
        timeout=60,
    )

    if not candles or len(candles) < 200:
        return {
            "success": False,
            "message": f"캔들 부족: {len(candles) if candles else 0}개 (최소 200개 필요)",
            "trades": [],
            "summary": {},
        }

    config = TrendConfig(
        st_atr_len=20,
        st_factor=5.0,
        asset_type=asset_type,
        htf_sma_len=200 if is_crypto else 156,
        htf_vwma_len=156,
        use_pyramiding=True,
        max_pyr_entries=4,
        pyr_weights=[0.25, 0.25, 0.25, 0.25],
        use_spo_split=True,
        use_st_flip_exit=True,
    )

    result = run_trend_v8(
        candles=candles,
        config=config,
        initial_capital=request.initial_capital,
    )

    if not result.success:
        return {
            "success": False,
            "message": result.message,
            "trades": [],
            "summary": {},
        }

    trades_list = []
    for t in result.trades:
        date_str = datetime.fromtimestamp(t.timestamp / 1000).strftime("%Y-%m-%d") if t.timestamp else ""
        trades_list.append({
            "date": date_str,
            "type": t.action,
            "price": t.price,
            "qty": t.quantity,
            "pnl": t.pnl,
            "reason": t.reason_code,
        })

    return {
        "success": True,
        "engine": "trend_v8",
        "total_trades": len(trades_list),
        "trades": trades_list,
        "summary": {
            "initial_capital": result.metrics.initial_capital,
            "final_capital": result.metrics.final_capital,
            "total_return_pct": result.metrics.total_return_pct,
            "max_drawdown_pct": result.metrics.max_drawdown_pct,
            "win_rate_pct": result.metrics.win_rate_pct,
            "profit_factor": result.metrics.profit_factor,
            "total_trades": result.metrics.total_trades,
        },
        "equity_curve": result.equity_curve,
    }


@router.get("/strategies/indicators")
async def api_get_indicators():
    """커스텀 전략 빌더용 지표 목록"""
    return {
        "indicators": INDICATOR_REGISTRY,
        "categories": INDICATOR_CATEGORIES,
        "operators": OPERATORS,
    }


@router.post("/backtest/custom")
async def api_run_custom_backtest(
    request: CustomBacktestRequest,
    current_user: User = Depends(get_current_user_optional)
):
    """커스텀 전략 백테스트 실행"""
    if current_user:
        plan = getattr(current_user, "plan", "free")
        role = getattr(current_user, "role", "user")
        if plan != "premium" and role != "admin":
            raise HTTPException(status_code=403, detail="프리미엄 요금제에서 이용 가능합니다")

    try:
        candles = await fetch_candles_for_backtest(
            exchange=request.exchange,
            symbol=request.symbol,
            timeframe=request.timeframe,
            days=request.days,
        )

        if not candles:
            return CustomBacktestResponse(
                success=False,
                message="캔들 데이터를 조회할 수 없습니다",
            ).model_dump()

        result = await run_custom_backtest(
            candles=candles,
            config=request.strategy,
            initial_capital=request.initial_capital,
        )

        return result

    except Exception as e:
        import traceback
        traceback.print_exc()
        return CustomBacktestResponse(
            success=False,
            message=f"백테스트 실행 오류: {str(e)}",
        ).model_dump()


@router.post("/strategies")
async def create_strategy(
    request: StrategyCreateRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """전략 저장"""
    plan = getattr(current_user, "plan", "free")
    role = getattr(current_user, "role", "user")
    if plan != "premium" and role != "admin":
        raise HTTPException(status_code=403, detail="프리미엄 요금제에서 이용 가능합니다")

    try:
        _ensure_strategies_table(db)

        insert_sql = text("""
            INSERT INTO strategies (user_id, name, strategy_type, exchange, symbol, params, order_settings, is_active)
            VALUES (:user_id, :name, :strategy_type, :exchange, :symbol, :params, :order_settings, :is_active)
            RETURNING id
        """)

        result = db.execute(insert_sql, {
            "user_id": current_user.id,
            "name": request.name,
            "strategy_type": request.strategy_type,
            "exchange": request.exchange,
            "symbol": request.symbol,
            "params": json.dumps(request.params or {}),
            "order_settings": json.dumps(request.order_settings or {}),
            "is_active": request.is_active
        })
        db.commit()

        strategy_id = result.fetchone()[0]
        return {"ok": True, "id": strategy_id, "message": "전략이 저장되었습니다"}

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"전략 저장 오류: {str(e)}")


@router.get("/strategies")
async def get_strategies(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """사용자 전략 목록"""
    try:
        _ensure_strategies_table(db)

        sql = text("""
            SELECT id, name, strategy_type, exchange, symbol, params, order_settings, is_active, created_at
            FROM strategies
            WHERE user_id = :user_id
            ORDER BY created_at DESC
        """)
        rows = db.execute(sql, {"user_id": current_user.id}).mappings().all()

        strategies = []
        for row in rows:
            strategies.append({
                "id": row["id"],
                "name": row["name"],
                "strategy_type": row["strategy_type"],
                "exchange": row["exchange"],
                "symbol": row["symbol"],
                "params": row["params"] if isinstance(row["params"], dict) else json.loads(row["params"] or "{}"),
                "order_settings": row["order_settings"] if isinstance(row["order_settings"], dict) else json.loads(row["order_settings"] or "{}"),
                "is_active": row["is_active"],
                "created_at": str(row["created_at"])
            })

        return {"strategies": strategies}

    except Exception as e:
        return {"strategies": [], "error": str(e)}


@router.put("/strategies/{strategy_id}/toggle")
async def toggle_strategy(
    strategy_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """전략 활성화/비활성화"""
    try:
        _ensure_strategies_table(db)

        sql = text("SELECT is_active FROM strategies WHERE id = :id AND user_id = :user_id")
        row = db.execute(sql, {"id": strategy_id, "user_id": current_user.id}).mappings().first()

        if not row:
            raise HTTPException(status_code=404, detail="전략을 찾을 수 없습니다")

        new_active = not row["is_active"]

        update_sql = text("UPDATE strategies SET is_active = :active, updated_at = NOW() WHERE id = :id")
        db.execute(update_sql, {"active": new_active, "id": strategy_id})
        db.commit()

        return {"ok": True, "is_active": new_active}

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"전략 토글 오류: {str(e)}")


@router.delete("/strategies/{strategy_id}")
async def delete_strategy(
    strategy_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """전략 삭제"""
    try:
        _ensure_strategies_table(db)

        sql = text("DELETE FROM strategies WHERE id = :id AND user_id = :user_id")
        result = db.execute(sql, {"id": strategy_id, "user_id": current_user.id})
        db.commit()

        if result.rowcount == 0:
            raise HTTPException(status_code=404, detail="전략을 찾을 수 없습니다")

        return {"ok": True, "message": "전략이 삭제되었습니다"}

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"전략 삭제 오류: {str(e)}")

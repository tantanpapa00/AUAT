"""
자산(Assets) 라우터 - 전략-종목 연결 관리
"""
import json
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from pydantic import BaseModel

from app.db import get_db
from app.models import User
from app.auth import get_current_user_optional
from app.utils.merge import deep_merge, get_overridden_keys, DEFAULT_SIGNAL_PARAMS

router = APIRouter(prefix="/api/assets", tags=["assets"])


def _safe_dumps(obj) -> str:
    """JSON 직렬화 (null-safe, 정렬)"""
    if obj is None:
        return "null"
    return json.dumps(obj, ensure_ascii=False, separators=(",", ":"), sort_keys=True)


class SignalParamsOverrideRequest(BaseModel):
    """종목별 signal_params 오버라이드 요청"""
    signal_params_override: Optional[dict] = None


# =============================================================================
# Assets CRUD
# =============================================================================

@router.get("")
def api_list_assets(db: Session = Depends(get_db)):
    """자산 목록 조회"""
    # best-effort: ensure dashboard columns exist (avoid 500 on older DBs)
    try:
        db.execute(text("alter table assets add column if not exists last_okx_order_id text;"))
        db.execute(text("alter table assets add column if not exists last_filled_qty numeric;"))
        db.execute(text("alter table assets add column if not exists last_order_avg_px numeric;"))
        db.execute(text("alter table assets add column if not exists last_checked_at timestamptz;"))
        db.commit()
    except Exception:
        try:
            db.rollback()
        except Exception:
            pass

    rows = db.execute(text("""
        select
            a.id,
            a.account_id,
            ac.name as account_name,
            a.strategy_id,
            s.name as strategy_name,
            a.symbol,
            a.market,
            a.is_active,
            a.cooldown_sec,
            a.max_orders_per_day,
            a.last_signal_at,
            a.last_signal_id,
            a.last_order_at,
            a.last_order_id,
            a.last_order_status,
            a.last_order_reason,
            a.last_okx_order_id,
            a.last_filled_qty,
            a.last_order_avg_px,
            a.last_checked_at,
            a.created_at,
            a.updated_at
        from assets a
        join accounts ac on ac.id = a.account_id
        join strategies s on s.id = a.strategy_id
        order by a.id asc
    """)).mappings().all()
    return [dict(r) for r in rows]


@router.post("")
def api_create_asset(payload: dict, db: Session = Depends(get_db)):
    """자산 생성"""
    required = ["account_id", "strategy_id", "symbol"]
    for k in required:
        if payload.get(k) in (None, ""):
            raise HTTPException(status_code=400, detail=f"missing: {k}")

    market = (payload.get("market") or "spot").strip()
    symbol = str(payload["symbol"]).strip()

    try:
        row = db.execute(
            text("""
                insert into assets(account_id, strategy_id, symbol, market, is_active)
                values (:account_id, :strategy_id, :symbol, :market, :is_active)
                returning id
            """),
            {
                "account_id": int(payload["account_id"]),
                "strategy_id": int(payload["strategy_id"]),
                "symbol": symbol,
                "market": market,
                "is_active": bool(payload.get("is_active", True)),
            }
        ).mappings().first()
        db.commit()
        return {"ok": True, "id": row["id"]}
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="Duplicate asset (account_id+strategy_id+symbol+market)")
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(e))


# =============================================================================
# Signal Params Override
# =============================================================================

@router.get("/{asset_id}/signal-params-override")
def api_get_asset_signal_params_override(asset_id: int, db: Session = Depends(get_db)):
    """종목의 signal_params_override 조회"""
    row = db.execute(
        text("SELECT id, symbol, signal_params_override FROM assets WHERE id = :id"),
        {"id": asset_id}
    ).mappings().first()

    if not row:
        raise HTTPException(status_code=404, detail="종목을 찾을 수 없습니다")

    return {
        "ok": True,
        "asset_id": asset_id,
        "symbol": row["symbol"],
        "signal_params_override": row["signal_params_override"]
    }


@router.put("/{asset_id}/signal-params-override")
def api_put_asset_signal_params_override(
    asset_id: int,
    req: SignalParamsOverrideRequest,
    db: Session = Depends(get_db)
):
    """종목의 signal_params_override 저장"""
    row = db.execute(
        text("SELECT id FROM assets WHERE id = :id"),
        {"id": asset_id}
    ).mappings().first()

    if not row:
        raise HTTPException(status_code=404, detail="종목을 찾을 수 없습니다")

    try:
        db.execute(
            text("""
                UPDATE assets
                SET signal_params_override = CAST(:params AS jsonb),
                    updated_at = now()
                WHERE id = :id
            """),
            {"id": asset_id, "params": _safe_dumps(req.signal_params_override)}
        )
        db.commit()

        return {
            "ok": True,
            "message": "저장 완료",
            "signal_params_override": req.signal_params_override
        }
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=400, detail=f"저장 실패: {str(e)}")


@router.delete("/{asset_id}/signal-params-override")
def api_delete_asset_signal_params_override(asset_id: int, db: Session = Depends(get_db)):
    """종목의 signal_params_override 초기화 (전략 기본값으로 복귀)"""
    row = db.execute(
        text("SELECT id FROM assets WHERE id = :id"),
        {"id": asset_id}
    ).mappings().first()

    if not row:
        raise HTTPException(status_code=404, detail="종목을 찾을 수 없습니다")

    try:
        db.execute(
            text("""
                UPDATE assets
                SET signal_params_override = NULL,
                    updated_at = now()
                WHERE id = :id
            """),
            {"id": asset_id}
        )
        db.commit()

        return {
            "ok": True,
            "message": "오버라이드 초기화 완료"
        }
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=400, detail=f"초기화 실패: {str(e)}")


@router.get("/{asset_id}/effective-params")
def api_get_asset_effective_params(asset_id: int, db: Session = Depends(get_db)):
    """
    종목의 최종 적용값 조회 (merged).
    Hub가 매매 시 이 엔드포인트를 사용하여 최종 설정을 가져옴.
    """
    row = db.execute(
        text("""
            SELECT
                a.id as asset_id,
                a.symbol,
                a.signal_params_override,
                s.id as strategy_id,
                s.name as strategy_name,
                s.signal_params
            FROM assets a
            JOIN strategies s ON a.strategy_id = s.id
            WHERE a.id = :id
        """),
        {"id": asset_id}
    ).mappings().first()

    if not row:
        raise HTTPException(status_code=404, detail="종목을 찾을 수 없습니다")

    # 전략 기본값 (없으면 DEFAULT_SIGNAL_PARAMS 사용)
    base_params = row["signal_params"] or DEFAULT_SIGNAL_PARAMS
    override_params = row["signal_params_override"]

    # deep_merge 수행
    effective_params = deep_merge(base_params, override_params)

    # 오버라이드된 키 목록
    overridden_keys = get_overridden_keys(base_params, override_params)

    return {
        "ok": True,
        "asset_id": asset_id,
        "symbol": row["symbol"],
        "strategy_id": row["strategy_id"],
        "strategy_name": row["strategy_name"],
        "effective_params": effective_params,
        "overridden_keys": overridden_keys
    }


# =============================================================================
# TradingView Template
# =============================================================================

@router.get("/{asset_id}/template/tradingview")
def api_asset_template_tradingview(
    asset_id: int,
    side: str = Query("buy", description="buy 또는 sell"),
    qty: float = Query(1, description="수량"),
    order_type: str = Query("market", description="주문 유형"),
    db: Session = Depends(get_db),
):
    """
    특정 자산에 대한 TradingView 얼러트 템플릿 생성.
    복사하여 TradingView에 붙여넣기 가능.
    """
    row = db.execute(text("""
        SELECT
            a.id AS asset_id,
            a.symbol,
            a.market,
            ac.exchange,
            s.id AS strategy_id,
            s.tv_secret
        FROM assets a
        JOIN accounts ac ON ac.id = a.account_id
        JOIN strategies s ON s.id = a.strategy_id
        WHERE a.id = :aid
    """), {"aid": asset_id}).mappings().first()

    if not row:
        raise HTTPException(status_code=404, detail=f"자산 미존재: asset_id={asset_id}")

    if not row["tv_secret"]:
        raise HTTPException(status_code=400, detail="전략에 tv_secret 미설정")

    # side 검증
    side_lower = side.strip().lower()
    if side_lower not in ("buy", "sell"):
        raise HTTPException(status_code=400, detail=f"invalid side: {side} (buy 또는 sell)")

    template = {
        "secret": row["tv_secret"],
        "symbol": row["symbol"],
        "side": side_lower,
        "qty": qty,
        "alert_id": "{{timenow}}",
        "type": order_type,
    }

    template_json = json.dumps(template, ensure_ascii=False, indent=2)

    return {
        "ok": True,
        "asset_id": asset_id,
        "symbol": row["symbol"],
        "exchange": row["exchange"],
        "market": row["market"],
        "template": template,
        "template_json": template_json,
        "instruction": "이 JSON을 TradingView 얼러트 메시지에 붙여넣으세요"
    }


# =============================================================================
# Asset Toggle & Delete
# =============================================================================

@router.put("/{asset_id}/toggle")
async def toggle_asset_active(
    asset_id: int,
    current_user: User = Depends(get_current_user_optional),
    db: Session = Depends(get_db)
):
    """자산(전략-종목 연결) 활성/비활성 토글"""
    try:
        row = db.execute(
            text("SELECT id, is_active FROM assets WHERE id = :id"),
            {"id": asset_id}
        ).mappings().first()
        if not row:
            raise HTTPException(status_code=404, detail="Asset not found")

        new_active = not row["is_active"]
        db.execute(
            text("UPDATE assets SET is_active = :active, updated_at = now() WHERE id = :id"),
            {"active": new_active, "id": asset_id}
        )
        db.commit()
        return {"ok": True, "is_active": new_active, "asset_id": asset_id}
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(e))


@router.delete("/{asset_id}")
async def delete_asset(
    asset_id: int,
    current_user: User = Depends(get_current_user_optional),
    db: Session = Depends(get_db)
):
    """자산(전략-종목 연결) 소프트 삭제"""
    try:
        row = db.execute(
            text("SELECT id FROM assets WHERE id = :id AND soft_deleted = 0"),
            {"id": asset_id}
        ).mappings().first()
        if not row:
            raise HTTPException(status_code=404, detail="Asset not found")

        db.execute(
            text("UPDATE assets SET soft_deleted = 1, is_active = false, updated_at = now() WHERE id = :id"),
            {"id": asset_id}
        )
        db.commit()
        return {"ok": True, "deleted": True, "asset_id": asset_id}
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(e))

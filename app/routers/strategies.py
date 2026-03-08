"""
전략 라우터 - 전략 CRUD
"""
import json
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import text
from app.db import get_db

router = APIRouter(prefix="/api/strategies", tags=["strategies"])


def _safe_dumps(obj):
    return json.dumps(obj, ensure_ascii=False, separators=(",", ":"), sort_keys=True)


@router.get("")
def api_list_strategies(db: Session = Depends(get_db)):
    rows = db.execute(text("""
        select id, name, tv_secret, is_active, created_at, updated_at
        from strategies
        order by id asc
    """)).mappings().all()
    return [dict(r) for r in rows]


@router.post("")
def api_create_strategy(payload: dict, db: Session = Depends(get_db)):
    if not payload.get("name"):
        raise HTTPException(status_code=400, detail="missing: name")
    if not payload.get("tv_secret"):
        raise HTTPException(status_code=400, detail="missing: tv_secret")

    signal_params = payload.get("signal_params")

    try:
        if signal_params:
            row = db.execute(
                text("""
                    insert into strategies(name, tv_secret, is_active, signal_params)
                    values (:name, :tv_secret, :is_active, CAST(:signal_params AS jsonb))
                    returning id
                """),
                {
                    "name": payload["name"],
                    "tv_secret": payload["tv_secret"],
                    "is_active": bool(payload.get("is_active", False)),
                    "signal_params": _safe_dumps(signal_params),
                }
            ).mappings().first()
        else:
            row = db.execute(
                text("""
                    insert into strategies(name, tv_secret, is_active)
                    values (:name, :tv_secret, :is_active)
                    returning id
                """),
                {
                    "name": payload["name"],
                    "tv_secret": payload["tv_secret"],
                    "is_active": bool(payload.get("is_active", False)),
                }
            ).mappings().first()

        db.commit()
        return {"ok": True, "id": row["id"] if row else None}
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/{strategy_id}")
def api_update_strategy(strategy_id: int, payload: dict, db: Session = Depends(get_db)):
    # 기존 전략 확인
    row = db.execute(
        text("select id from strategies where id = :sid"),
        {"sid": strategy_id}
    ).mappings().first()

    if not row:
        raise HTTPException(status_code=404, detail="Strategy not found")

    # 업데이트 가능한 필드
    sets = []
    params = {"sid": strategy_id}

    if "name" in payload:
        sets.append("name = :name")
        params["name"] = payload["name"]
    if "tv_secret" in payload:
        sets.append("tv_secret = :tv_secret")
        params["tv_secret"] = payload["tv_secret"]
    if "is_active" in payload:
        sets.append("is_active = :is_active")
        params["is_active"] = bool(payload["is_active"])

    if sets:
        sets.append("updated_at = now()")
        sql = f"update strategies set {', '.join(sets)} where id = :sid"
        db.execute(text(sql), params)
        db.commit()

    return {"ok": True}

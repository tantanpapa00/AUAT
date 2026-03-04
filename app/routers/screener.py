# app/routers/screener.py
# 종목검색기 API 엔드포인트

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.orm import Session

from app.db import get_db
from app.auth import get_current_user_optional
from app.models import User, ScreenerPreset
from app.utils.plan_limits import check_pro_plan
from app.screener.kr_screener import screener_kr

router = APIRouter(prefix="/api/screener", tags=["screener"])


@router.get("")
async def api_screener(
    market: str = Query("kr", description="시장: kr, us, etf"),
    filters: str = Query("{}", description="필터 JSON 문자열"),
    sort: str = Query("market_cap", description="정렬 기준"),
    order: str = Query("desc", description="정렬 방향: asc, desc"),
    page: int = Query(1, description="페이지"),
    per_page: int = Query(50, description="페이지당 개수"),
    current_user: User = Depends(get_current_user_optional),
    db: Session = Depends(get_db)
):
    """종목검색기 - 스크리너"""
    # Pro 이상 체크
    if current_user and current_user.role == "admin":
        pass
    elif not check_pro_plan(current_user):
        if not current_user:
            raise HTTPException(status_code=401, detail="로그인이 필요합니다")
        raise HTTPException(status_code=403, detail="Pro 이상 요금제에서 이용 가능합니다")

    import json
    try:
        filter_dict = json.loads(filters)
    except:
        filter_dict = {}

    try:
        if market == "kr":
            result = await screener_kr(filter_dict, sort, order, page, per_page)
        elif market == "us":
            from app.screener.us_screener import screener_us
            result = await screener_us(filter_dict, sort, order, page, per_page)
        elif market == "etf":
            from app.screener.etf_screener import screener_etf
            result = await screener_etf(filter_dict, sort, order, page, per_page)
        else:
            result = {"items": [], "total": 0, "message": "지원하지 않는 시장"}

        return result

    except Exception as e:
        print(f"[API] Screener error: {e}")
        import traceback
        traceback.print_exc()
        return {
            "items": [],
            "total": 0,
            "success": False,
            "error": str(e),
        }


@router.get("/presets")
async def api_screener_presets_list(
    market: str = Query("kr", description="시장: kr, us, etf"),
    current_user: User = Depends(get_current_user_optional),
    db: Session = Depends(get_db)
):
    """사용자 프리셋 목록 조회"""
    if not current_user:
        return {"presets": [], "success": False, "error": "로그인이 필요합니다"}

    presets = db.query(ScreenerPreset).filter(
        ScreenerPreset.user_id == current_user.id,
        ScreenerPreset.market == market
    ).order_by(ScreenerPreset.is_default.desc(), ScreenerPreset.name).all()

    return {
        "presets": [
            {
                "id": p.id,
                "name": p.name,
                "market": p.market,
                "filters": p.filters,
                "sort_by": p.sort_by,
                "sort_order": p.sort_order,
                "is_default": p.is_default,
                "created_at": p.created_at.isoformat() if p.created_at else None,
            }
            for p in presets
        ],
        "success": True,
    }


@router.post("/presets")
async def api_screener_preset_create(
    request: Request,
    current_user: User = Depends(get_current_user_optional),
    db: Session = Depends(get_db)
):
    """프리셋 저장"""
    if not current_user:
        raise HTTPException(status_code=401, detail="로그인이 필요합니다")

    body = await request.json()
    name = body.get("name", "").strip()
    market = body.get("market", "kr")
    filters = body.get("filters", {})
    sort_by = body.get("sort_by", "market_cap")
    sort_order = body.get("sort_order", "desc")
    is_default = body.get("is_default", False)

    if not name:
        raise HTTPException(status_code=400, detail="프리셋 이름을 입력하세요")

    # 중복 이름 체크
    existing = db.query(ScreenerPreset).filter(
        ScreenerPreset.user_id == current_user.id,
        ScreenerPreset.name == name,
        ScreenerPreset.market == market
    ).first()

    if existing:
        # 덮어쓰기
        existing.filters = filters
        existing.sort_by = sort_by
        existing.sort_order = sort_order
        existing.is_default = is_default
        db.commit()
        preset_id = existing.id
    else:
        # 신규 생성
        preset = ScreenerPreset(
            user_id=current_user.id,
            name=name,
            market=market,
            filters=filters,
            sort_by=sort_by,
            sort_order=sort_order,
            is_default=is_default,
        )
        db.add(preset)
        db.commit()
        preset_id = preset.id

    # is_default가 True면 다른 프리셋의 is_default를 False로
    if is_default:
        db.query(ScreenerPreset).filter(
            ScreenerPreset.user_id == current_user.id,
            ScreenerPreset.market == market,
            ScreenerPreset.id != preset_id
        ).update({"is_default": False})
        db.commit()

    return {"success": True, "preset_id": preset_id}


@router.delete("/presets/{preset_id}")
async def api_screener_preset_delete(
    preset_id: int,
    current_user: User = Depends(get_current_user_optional),
    db: Session = Depends(get_db)
):
    """프리셋 삭제"""
    if not current_user:
        raise HTTPException(status_code=401, detail="로그인이 필요합니다")

    preset = db.query(ScreenerPreset).filter(
        ScreenerPreset.id == preset_id,
        ScreenerPreset.user_id == current_user.id
    ).first()

    if not preset:
        raise HTTPException(status_code=404, detail="프리셋을 찾을 수 없습니다")

    db.delete(preset)
    db.commit()

    return {"success": True}

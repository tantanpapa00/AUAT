# app/routers/market_kr.py
# 국내시장 API 엔드포인트

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db import get_db
from app.auth import get_current_user_optional
from app.models import User
from app.utils.plan_limits import check_pro_plan
from app.data_provider import get_kr_market_overview

router = APIRouter(prefix="/api/market", tags=["market-kr"])


@router.get("/kr/overview")
async def get_market_kr_overview(
    current_user: User = Depends(get_current_user_optional),
    db: Session = Depends(get_db)
):
    """국내시장 현황 - data_provider 사용"""
    # admin이면 무조건 통과
    if current_user and current_user.role == "admin":
        pass
    elif not check_pro_plan(current_user):
        if not current_user:
            raise HTTPException(status_code=401, detail="로그인이 필요합니다")
        raise HTTPException(status_code=403, detail="Pro 이상 요금제에서 이용 가능합니다")

    try:
        data = await get_kr_market_overview()
        return {
            "indices": {
                "kospi": data.get("kospi", {"name": "코스피", "current": 0, "change": 0, "change_percent": 0}),
                "kosdaq": data.get("kosdaq", {"name": "코스닥", "current": 0, "change": 0, "change_percent": 0}),
            },
            "investor": data.get("investors", {"foreign": 0, "institution": 0, "individual": 0}),
            "sectors": data.get("sectors", [])[:5],
            "success": True,
        }

    except Exception as e:
        print(f"[API] KR market error: {e}")
        return {
            "indices": {},
            "investor": {},
            "sectors": [],
            "success": False,
            "error": str(e),
        }

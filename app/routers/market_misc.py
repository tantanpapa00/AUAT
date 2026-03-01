# app/routers/market_misc.py
# ETF, Crypto 등 기타 시장 API 엔드포인트

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.db import get_db
from app.auth import get_current_user_optional
from app.models import User
from app.utils.plan_limits import check_pro_plan
from app.data_provider import get_etf_overview, get_crypto_overview

router = APIRouter(prefix="/api/market", tags=["market-misc"])


@router.get("/etf")
async def api_market_etf(
    current_user: User = Depends(get_current_user_optional),
    db: Session = Depends(get_db)
):
    """ETF 시장 현황 - ETFCheck 수준"""
    if current_user and current_user.role == "admin":
        pass
    elif not check_pro_plan(current_user):
        if not current_user:
            raise HTTPException(status_code=401, detail="로그인이 필요합니다")
        raise HTTPException(status_code=403, detail="Pro 이상 요금제에서 이용 가능합니다")

    try:
        data = await get_etf_overview()
        return data
    except Exception as e:
        print(f"[API] ETF error: {e}")
        return {
            "total_count": 0, "total_up": 0, "total_down": 0,
            "themes_up": [], "themes_down": [],
            "distribution": [],
            "top_by_return": [], "bottom_by_return": [],
            "top_by_volume": [], "top_by_market": [],
            "major_etfs": [],
            "success": False, "error": str(e),
        }


@router.get("/crypto")
async def api_market_crypto(
    exchange: str = Query("all", description="거래소 필터: all, binance, upbit"),
    current_user: User = Depends(get_current_user_optional),
    db: Session = Depends(get_db)
):
    """코인 시장 현황 - data_provider 사용"""
    if current_user and current_user.role == "admin":
        pass
    elif not check_pro_plan(current_user):
        if not current_user:
            raise HTTPException(status_code=401, detail="로그인이 필요합니다")
        raise HTTPException(status_code=403, detail="Pro 이상 요금제에서 이용 가능합니다")

    try:
        data = await get_crypto_overview()

        coins = []
        if exchange in ("all", "binance"):
            coins.extend(data.get("binance", []))
        if exchange in ("all", "upbit"):
            coins.extend(data.get("upbit", []))

        return {
            "coins": coins,
            "global": {
                "btc_dominance": data.get("btc_dominance", 0),
                "total_market_cap": data.get("total_market_cap", 0),
            },
            "kimchi_premium": data.get("kimchi_premium", 0),
            "success": True,
        }

    except Exception as e:
        print(f"[API] Crypto error: {e}")
        return {
            "coins": [],
            "global": {},
            "kimchi_premium": None,
            "success": False,
            "error": str(e),
        }

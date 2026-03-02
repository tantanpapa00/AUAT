# app/routers/ai_report.py
# AI 분석 및 리포트 관련 API 엔드포인트

import os
import uuid
import asyncio
import re
import io
import base64
from datetime import datetime, timezone, timedelta
from typing import Optional, Dict, Any, List

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import FileResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session
from sqlalchemy import text

import httpx

# Matplotlib 설정
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from matplotlib.patches import Rectangle

from app.db import get_db, SessionLocal
from app.auth import get_current_user_optional, get_current_user
from app.models import User
from app.utils.plan_limits import (
    check_pro_plan, check_standard_plan,
    get_ai_daily_limit, get_ai_monthly_limit,
    check_feature_allowed, get_plan_limits,
    AI_DAILY_LIMITS, AI_MONTHLY_LIMITS, WATCHLIST_LIMITS
)
from app.data_provider import (
    get_naver_stock_price,
    get_stock_financials_kr,
    get_stock_news_kr,
    get_rs_ranking,
    get_new_high_stocks,
    get_valuation,
)
from app.report_data import fetch_report_data, format_financial_data_for_prompt

router = APIRouter(prefix="/api", tags=["ai"])

# KST timezone
KST = timezone(timedelta(hours=9))

# Static/Charts directory
STATIC_DIR = "/app/static"
CHARTS_DIR = os.path.join(STATIC_DIR, "charts")
os.makedirs(CHARTS_DIR, exist_ok=True)


# =============================================================================
# PRESET_STRATEGIES (AI 추천 전략)
# =============================================================================
PRESET_STRATEGIES = {
    "kr": {
        "momentum": {
            "title": "모멘텀 상승세",
            "description": "거래량 급증 + 상승 추세 종목",
            "sort": "change_pct",
            "order": "desc",
            "filters": {"change_filter": {"min": 2}},
            "limit": 10
        },
        "value": {
            "title": "저평가 가치주",
            "description": "PER 15 이하 + ROE 15% 이상 + PBR 1.5 이하",
            "sort": "roe",
            "order": "desc",
            "filters": {"per": {"min": 0.1, "max": 15}, "roe": {"min": 15}, "pbr": {"min": 0.1, "max": 1.5}},
            "limit": 10
        },
        "dividend": {
            "title": "배당성장주",
            "description": "5년 이상 연속으로 배당금을 늘려온 기업",
            "sort": "dividend_yield",
            "order": "desc",
            "filters": {"dividend_growth_5y": True},
            "limit": 10
        },
        "large_cap": {
            "title": "대형 우량주",
            "description": "시가총액 상위 대형주",
            "sort": "market_cap",
            "order": "desc",
            "filters": {},
            "limit": 10
        }
    },
    "us": {
        "momentum": {
            "title": "강세 모멘텀",
            "description": "상승률 상위 종목",
            "sort": "change_pct",
            "order": "desc",
            "filters": {"change_filter": {"min": 2}},
            "limit": 10
        },
        "value": {
            "title": "저평가 가치주",
            "description": "PER 15 이하 + ROE 15% 이상 + PBR 1.5 이하",
            "sort": "roe",
            "order": "desc",
            "filters": {"per": {"min": 0.1, "max": 15}, "roe": {"min": 15}, "pbr": {"min": 0.1, "max": 1.5}},
            "limit": 10
        },
        "large_cap": {
            "title": "대형 기술주",
            "description": "시가총액 상위 종목",
            "sort": "market_cap",
            "order": "desc",
            "filters": {},
            "limit": 10
        },
        "growth": {
            "title": "성장주",
            "description": "높은 성장률 기대 종목",
            "sort": "eps_growth",
            "order": "desc",
            "filters": {},
            "limit": 10
        }
    },
    "etf": {
        "top_return": {
            "title": "수익률 TOP",
            "description": "최근 수익률 상위 ETF",
            "sort": "change_1m",
            "order": "desc",
            "filters": {},
            "limit": 10
        },
        "high_volume": {
            "title": "거래 활발",
            "description": "거래량 상위 ETF",
            "sort": "volume",
            "order": "desc",
            "filters": {},
            "limit": 10
        },
        "low_fee": {
            "title": "저비용",
            "description": "총보수 낮은 ETF",
            "sort": "expense_ratio",
            "order": "asc",
            "filters": {},
            "limit": 10
        },
        "high_aum": {
            "title": "순자산 대형",
            "description": "순자산총액 상위 ETF",
            "sort": "nav",
            "order": "desc",
            "filters": {},
            "limit": 10
        }
    }
}


# =============================================================================
# AI 테이블 초기화
# =============================================================================
_ai_tables_initialized = False


def _ensure_ai_tables(db: Session):
    """AI/관심종목 테이블 생성 - 서버 시작 시 1회만 실행"""
    global _ai_tables_initialized
    if _ai_tables_initialized:
        return

    print("[DB] AI 테이블 초기화 시작...")
    sqls = [
        """
        DO $$ BEGIN
            ALTER TABLE users ADD COLUMN IF NOT EXISTS ai_usage_count INTEGER DEFAULT 0;
            ALTER TABLE users ADD COLUMN IF NOT EXISTS ai_usage_date DATE;
            ALTER TABLE users ADD COLUMN IF NOT EXISTS ai_monthly_count INTEGER DEFAULT 0;
            ALTER TABLE users ADD COLUMN IF NOT EXISTS ai_monthly_date VARCHAR(7);
        EXCEPTION WHEN others THEN NULL;
        END $$;
        """,
        """
        CREATE TABLE IF NOT EXISTS ai_reports (
            id SERIAL PRIMARY KEY,
            symbol VARCHAR(50),
            exchange VARCHAR(50),
            report_text TEXT,
            data_snapshot JSONB,
            created_at TIMESTAMP DEFAULT NOW(),
            expires_at TIMESTAMP
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS market_timeline (
            id SERIAL PRIMARY KEY,
            created_at TIMESTAMP DEFAULT NOW(),
            market_status VARCHAR(20),
            kospi_change DECIMAL(5,2),
            kosdaq_change DECIMAL(5,2),
            summary TEXT,
            leading_sectors JSONB,
            lagging_sectors JSONB,
            featured_stocks JSONB,
            keywords JSONB
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS watchlist_groups (
            id SERIAL PRIMARY KEY,
            user_id INTEGER REFERENCES users(id),
            name VARCHAR(100),
            sort_order INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT NOW()
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS watchlist_items (
            id SERIAL PRIMARY KEY,
            group_id INTEGER REFERENCES watchlist_groups(id) ON DELETE CASCADE,
            user_id INTEGER REFERENCES users(id),
            symbol VARCHAR(50),
            exchange VARCHAR(50),
            added_at TIMESTAMP DEFAULT NOW()
        )
        """
    ]
    for sql in sqls:
        try:
            db.execute(text(sql))
            db.commit()
        except Exception:
            db.rollback()

    _ai_tables_initialized = True
    print("[DB] AI 테이블 초기화 완료")


# =============================================================================
# AI 작업 큐 시스템
# =============================================================================
_ai_jobs: Dict[str, Dict[str, Any]] = {}


def _cleanup_old_jobs():
    """24시간 지난 작업 삭제"""
    cutoff = datetime.now(KST) - timedelta(hours=24)
    expired = [k for k, v in _ai_jobs.items() if v.get("created_at", datetime.now(KST)) < cutoff]
    for k in expired:
        del _ai_jobs[k]


# =============================================================================
# Helper functions (from main.py)
# =============================================================================

def _get_ai_daily_limit(user: User) -> int:
    """요금제별 AI 일일 사용 제한"""
    return get_ai_daily_limit(user)


def _get_ai_monthly_limit(user: User) -> int:
    """요금제별 AI 월간 사용 제한"""
    return get_ai_monthly_limit(user)


def _get_watchlist_limit(user: User) -> int:
    """요금제별 관심종목 제한"""
    role = getattr(user, "role", "user")
    if role == "admin":
        return 99999
    plan = getattr(user, "plan", "free")
    return WATCHLIST_LIMITS.get(plan, 10)


# =============================================================================
# Master Cache (import from main.py context)
# =============================================================================
def get_master_cache():
    """Master cache accessor - import lazily to avoid circular import"""
    from app.main import get_master_cache as _get_master_cache
    return _get_master_cache()


# =============================================================================
# /api/ai/recommendations
# =============================================================================
@router.get("/ai/recommendations")
async def api_ai_recommendations(
    market: str = "kr",
    current_user: User = Depends(get_current_user_optional)
):
    """
    BBooster AI 추천 - 프리셋 전략 기반 종목 추천
    """
    strategies = PRESET_STRATEGIES.get(market, {})
    if not strategies:
        return {"market": market, "categories": [], "updated_at": datetime.now().isoformat()}

    categories = []

    for strategy_id, config in strategies.items():
        try:
            items = []

            if market == "kr":
                from app.screener.kr_screener import load_kr_stocks, apply_cached_financial
                from app.screener.filters import apply_screener_filters, sort_screener_results
                stocks = await load_kr_stocks()

                stocks = apply_cached_financial(stocks[:500])

                if config.get("filters"):
                    stocks = apply_screener_filters(stocks, config["filters"])
                stocks = sort_screener_results(stocks, config.get("sort", "market_cap"), config.get("order", "desc"))
                items = stocks[:config.get("limit", 10)]

            elif market == "us":
                from app.screener.us_screener import load_us_stocks
                from app.screener.filters import apply_screener_filters, sort_screener_results
                stocks = await load_us_stocks()
                if config.get("filters"):
                    stocks = apply_screener_filters(stocks, config["filters"])
                stocks = sort_screener_results(stocks, config.get("sort", "market_cap"), config.get("order", "desc"))
                items = stocks[:config.get("limit", 10)]

            elif market == "etf":
                from app.screener.etf_screener import load_etf_stocks
                from app.screener.filters import apply_screener_filters, sort_screener_results
                stocks = await load_etf_stocks()
                if config.get("filters"):
                    stocks = apply_screener_filters(stocks, config["filters"])
                stocks = sort_screener_results(stocks, config.get("sort", "nav"), config.get("order", "desc"))
                items = stocks[:config.get("limit", 10)]

            # 필드 정리
            cleaned_items = []
            for item in items:
                cleaned = {
                    "code": item.get("code") or item.get("symbol"),
                    "name": item.get("name", ""),
                    "price": item.get("price", 0),
                    "change_pct": item.get("change_pct", 0),
                }
                if strategy_id == "value":
                    per_val = item.get('per', 0)
                    roe_val = item.get('roe', 0)
                    pbr_val = item.get('pbr', 0)
                    cleaned["signal"] = f"PER {per_val:.1f} ROE {roe_val:.0f}% PBR {pbr_val:.2f}"
                elif strategy_id == "dividend":
                    div_yield = item.get('dividend_yield', 0)
                    cleaned["signal"] = f"배당 {div_yield:.1f}% (5년+)"
                elif config.get("sort") == "change_pct":
                    cleaned["signal"] = f"+{item.get('change_pct', 0):.1f}% 상승"
                elif config.get("sort") == "dividend_yield":
                    cleaned["signal"] = f"배당 {item.get('dividend_yield', 0):.1f}%"
                elif config.get("sort") == "roe":
                    cleaned["signal"] = f"ROE {item.get('roe', 0):.1f}%"
                elif config.get("sort") == "per":
                    cleaned["signal"] = f"PER {item.get('per', 0):.1f}"
                elif config.get("sort") == "market_cap":
                    mc = item.get("market_cap", 0)
                    if market == "us":
                        if mc >= 1:
                            cleaned["signal"] = f"${mc:.1f}T"
                        elif mc >= 0.001:
                            cleaned["signal"] = f"${mc*1000:.0f}B"
                        else:
                            cleaned["signal"] = f"${mc*1000000:.0f}M"
                    else:
                        if mc >= 1_000_000_000_000:
                            cleaned["signal"] = f"시총 {mc/1_000_000_000_000:.1f}조"
                        else:
                            cleaned["signal"] = f"시총 {mc/100_000_000:.0f}억"
                else:
                    cleaned["signal"] = ""
                cleaned_items.append(cleaned)

            categories.append({
                "id": strategy_id,
                "title": config["title"],
                "description": config["description"],
                "items": cleaned_items
            })

        except Exception as e:
            print(f"[AI] Error in {market}/{strategy_id}: {e}")
            categories.append({
                "id": strategy_id,
                "title": config["title"],
                "description": config["description"],
                "items": []
            })

    return {
        "market": market,
        "updated_at": datetime.now().isoformat(),
        "categories": categories
    }


# =============================================================================
# /api/analysis/rs - RS ranking
# =============================================================================
@router.get("/analysis/rs")
async def api_analysis_rs(
    market: str = Query("all", description="시장: all, kospi, kosdaq"),
    limit: int = Query(100, description="최대 개수"),
    current_user: User = Depends(get_current_user_optional),
    db: Session = Depends(get_db)
):
    """종합RS 순위 - pykrx 실제 데이터 사용"""
    try:
        rs_data = await get_rs_ranking(market.upper(), limit)

        return {
            "stocks": rs_data,
            "market": market,
            "success": True,
        }

    except Exception as e:
        print(f"[API] RS error: {e}")
        return {
            "stocks": [],
            "market": market,
            "success": False,
            "error": str(e),
        }


# =============================================================================
# /api/analysis/new-high
# =============================================================================
@router.get("/analysis/new-high")
async def api_analysis_new_high(
    limit: int = Query(50, description="최대 개수"),
    current_user: User = Depends(get_current_user_optional),
    db: Session = Depends(get_db)
):
    """52주 신고가 돌파 종목 - pykrx 사용"""
    try:
        stocks = await get_new_high_stocks(limit)
        return {
            "stocks": stocks,
            "success": True,
        }
    except Exception as e:
        print(f"[API] New high error: {e}")
        return {
            "stocks": [],
            "success": False,
            "error": str(e),
        }


# =============================================================================
# /api/analysis/valuation
# =============================================================================
@router.get("/analysis/valuation")
async def api_analysis_valuation(
    market: str = Query("all", description="시장: all, kospi, kosdaq"),
    sort_by: str = Query("per", description="정렬: per, pbr, market_cap"),
    limit: int = Query(200, description="최대 개수"),
    current_user: User = Depends(get_current_user_optional),
    db: Session = Depends(get_db)
):
    """밸류에이션 데이터 - pykrx 사용"""
    try:
        valuation_data = await get_valuation(market.upper(), limit)

        if sort_by == "per":
            valuation_data.sort(key=lambda x: x["per"] if x["per"] > 0 else 9999)
        elif sort_by == "pbr":
            valuation_data.sort(key=lambda x: x["pbr"] if x["pbr"] > 0 else 9999)
        elif sort_by == "market_cap":
            valuation_data.sort(key=lambda x: x["market_cap"], reverse=True)

        return {
            "stocks": valuation_data[:limit],
            "market": market,
            "success": True,
        }

    except Exception as e:
        print(f"[API] Valuation error: {e}")
        return {
            "stocks": [],
            "market": market,
            "success": False,
            "error": str(e),
        }


# =============================================================================
# /api/analysis/reports
# =============================================================================
@router.get("/analysis/reports")
async def get_analysis_reports(
    code: str = Query(None, description="종목코드 필터"),
    current_user: User = Depends(get_current_user_optional),
    db: Session = Depends(get_db)
):
    """증권사 리포트 요약 - KIS 계정 필요"""
    from app.kis_api import get_kis_token, get_invest_opinion
    from app.main import _get_kis_credentials

    if not current_user:
        return {
            "reports": [],
            "has_kis_account": False,
            "message": "로그인이 필요합니다.",
        }

    kis_creds = await _get_kis_credentials(db, current_user.id)
    if not kis_creds:
        return {
            "reports": [],
            "has_kis_account": False,
            "message": "KIS 계정을 등록하면 증권사 리포트를 확인할 수 있습니다.",
        }

    try:
        app_key, app_secret = kis_creds
        token = await get_kis_token(app_key, app_secret)

        if not token:
            return {
                "reports": [],
                "has_kis_account": True,
                "message": "KIS 토큰 발급에 실패했습니다.",
            }

        if code:
            opinions = await get_invest_opinion(app_key, app_secret, token.access_token, code)
        else:
            opinions = []

        return {
            "reports": opinions or [],
            "has_kis_account": True,
            "success": True,
        }

    except Exception as e:
        return {
            "reports": [],
            "has_kis_account": True,
            "success": False,
            "error": str(e),
        }


# =============================================================================
# /api/ai/usage
# =============================================================================
@router.get("/ai/usage")
async def get_ai_usage(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """AI 사용량 조회 (일일 + 월간)"""
    _ensure_ai_tables(db)

    daily_max = _get_ai_daily_limit(current_user)
    monthly_max = _get_ai_monthly_limit(current_user)
    plan = getattr(current_user, "plan", "free")
    today = datetime.now(KST).date()
    this_month = today.strftime("%Y-%m")

    daily_count = 0
    monthly_count = 0

    try:
        result = db.execute(
            text("SELECT ai_usage_count, ai_usage_date, ai_monthly_count, ai_monthly_date FROM users WHERE id = :uid"),
            {"uid": current_user.id}
        )
        row = result.fetchone()
        if row:
            usage_date = row[1]
            monthly_date = row[3] or ""

            if usage_date == today:
                daily_count = row[0] or 0
            else:
                daily_count = 0

            if monthly_date == this_month:
                monthly_count = row[2] or 0
            else:
                monthly_count = 0

    except Exception as e:
        print(f"AI usage query error: {e}")

    return {
        "daily_used": daily_count,
        "daily_max": daily_max,
        "daily_remaining": max(0, daily_max - daily_count),
        "monthly_used": monthly_count,
        "monthly_max": monthly_max,
        "monthly_remaining": max(0, monthly_max - monthly_count),
        "plan": plan,
    }


# =============================================================================
# /api/usage - 통합 사용량 조회 (명령서65)
# =============================================================================
@router.get("/usage")
async def get_all_usage(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """통합 사용량 조회 (AI, 백테스트, 슬롯, 관심종목)"""
    _ensure_ai_tables(db)

    limits = get_plan_limits(current_user)
    plan = getattr(current_user, "plan", "free")
    today = datetime.now(KST).date()
    this_month = today.strftime("%Y-%m")

    # AI 사용량
    ai_daily_used = 0
    ai_monthly_used = 0
    try:
        result = db.execute(
            text("SELECT ai_usage_count, ai_usage_date, ai_monthly_count, ai_monthly_date FROM users WHERE id = :uid"),
            {"uid": current_user.id}
        )
        row = result.fetchone()
        if row:
            if row[1] == today:
                ai_daily_used = row[0] or 0
            if (row[3] or "") == this_month:
                ai_monthly_used = row[2] or 0
    except Exception as e:
        print(f"AI usage query error: {e}")

    # 백테스트 사용량
    backtest_monthly_used = 0
    try:
        result = db.execute(
            text("""
                SELECT COALESCE(SUM(count), 0) FROM usage_tracking
                WHERE user_id = :uid AND feature = 'backtest' AND month_key = :month
            """),
            {"uid": current_user.id, "month": this_month}
        )
        backtest_monthly_used = result.scalar() or 0
    except Exception as e:
        print(f"Backtest usage query error: {e}")

    # 슬롯 사용량
    slots_used = 0
    try:
        result = db.execute(
            text("""
                SELECT COUNT(*) FROM premium_configs pc
                JOIN assets a ON a.id = pc.asset_id
                JOIN accounts acc ON acc.id = a.account_id
                WHERE acc.owner_id = :uid AND a.is_active = true AND a.soft_deleted = 0
            """),
            {"uid": current_user.id}
        )
        slots_used = result.scalar() or 0
    except Exception as e:
        print(f"Slots usage query error: {e}")

    # 관심종목 사용량
    watchlist_used = 0
    try:
        result = db.execute(
            text("SELECT COUNT(*) FROM watchlist_items WHERE user_id = :uid"),
            {"uid": current_user.id}
        )
        watchlist_used = result.scalar() or 0
    except Exception as e:
        print(f"Watchlist usage query error: {e}")

    return {
        "plan": plan,
        "ai": {
            "daily_used": ai_daily_used,
            "daily_max": limits["ai_daily"],
            "daily_remaining": max(0, limits["ai_daily"] - ai_daily_used),
            "monthly_used": ai_monthly_used,
            "monthly_max": limits["ai_monthly"],
            "monthly_remaining": max(0, limits["ai_monthly"] - ai_monthly_used),
            "can_use": limits["can_ai"],
        },
        "backtest": {
            "monthly_used": backtest_monthly_used,
            "monthly_max": limits["backtest_monthly"],
            "monthly_remaining": max(0, limits["backtest_monthly"] - backtest_monthly_used) if limits["backtest_monthly"] < 99999 else 99999,
            "is_unlimited": limits["backtest_monthly"] >= 99999,
            "can_use": limits["can_backtest"],
        },
        "slots": {
            "used": slots_used,
            "max": limits["slots"],
            "remaining": max(0, limits["slots"] - slots_used),
            "can_use": limits["can_autotrading"],
        },
        "watchlist": {
            "used": watchlist_used,
            "max": limits["watchlist"],
            "remaining": max(0, limits["watchlist"] - watchlist_used) if limits["watchlist"] < 99999 else 99999,
            "is_unlimited": limits["watchlist"] >= 99999,
        },
        "upgrade_url": "/pricing",
    }


# =============================================================================
# Request/Response Models
# =============================================================================
class AIAnalyzeRequest(BaseModel):
    symbol: str
    exchange: str


class AIChatRequest(BaseModel):
    message: str


# =============================================================================
# /api/ai/analyze
# =============================================================================
@router.post("/ai/analyze")
async def request_ai_analysis(
    request: AIAnalyzeRequest,
    current_user: User = Depends(get_current_user_optional),
    db: Session = Depends(get_db)
):
    """AI 종합분석 요청 -> job_id 즉시 반환 (백그라운드 처리)"""
    import time as time_module
    t0 = time_module.time()
    print(f"[AI Analyze] === 요청 시작: {request.symbol} ===")

    _ensure_ai_tables(db)
    print(f"[AI Analyze] _ensure_ai_tables: {time_module.time()-t0:.2f}초")

    # 요금제 제한 체크 (check_feature_allowed 사용)
    if current_user:
        allowed, error_msg, upgrade_url = check_feature_allowed(current_user, "ai", db, increment=False)
        if not allowed:
            raise HTTPException(
                status_code=403,
                detail={"message": error_msg, "upgrade_url": upgrade_url}
            )

    print(f"[AI Analyze] usage check: {time_module.time()-t0:.2f}초")

    # 캐시 확인
    try:
        cache_result = db.execute(
            text("""
                SELECT report_text FROM ai_reports
                WHERE symbol = :sym AND exchange = :ex AND expires_at > NOW()
                ORDER BY created_at DESC LIMIT 1
            """),
            {"sym": request.symbol, "ex": request.exchange}
        )
        cache_row = cache_result.fetchone()
        if cache_row:
            _cleanup_old_jobs()
            cache_job_id = str(uuid.uuid4())[:8]

            stock_name = request.symbol
            master = get_master_cache()
            stock = master.get_stock(request.symbol)
            if stock and hasattr(stock, 'name'):
                stock_name = stock.name

            _ai_jobs[cache_job_id] = {
                "status": "done",
                "progress": "캐시 로드 완료",
                "result": cache_row[0],
                "created_at": datetime.now(KST),
                "user_id": current_user.id if current_user else None,
                "symbol": request.symbol,
                "exchange": request.exchange,
                "stock": {"name": stock_name, "code": request.symbol},
                "charts": {},
                "cached": True,
            }
            print(f"[AI Analyze] 캐시 HIT: {stock_name}({request.symbol}), cache_job_id={cache_job_id}")
            return {"success": True, "status": "done", "report": cache_row[0], "job_id": cache_job_id, "cached": True}
    except Exception as e:
        print(f"[AI Analyze] 캐시 조회 오류: {e}")

    _cleanup_old_jobs()
    job_id = str(uuid.uuid4())[:8]

    exchange_lower = request.exchange.lower()
    is_domestic = exchange_lower in ("kis_kr", "kis_kr_etf")
    market = "kr" if is_domestic else "us"

    is_etf = "etf" in exchange_lower
    if not is_etf:
        master = get_master_cache()
        stock = master.get_stock(request.symbol)
        if stock and getattr(stock, 'is_etf', False):
            is_etf = True

    _ai_jobs[job_id] = {
        "status": "pending",
        "progress": "요청 접수됨",
        "result": None,
        "created_at": datetime.now(KST),
        "user_id": current_user.id if current_user else None,
        "symbol": request.symbol,
        "exchange": request.exchange,
        "is_etf": is_etf,
    }

    # 사용량 증가 (캐시 HIT가 아닌 경우만)
    if current_user:
        check_feature_allowed(current_user, "ai", db, increment=True)

    asyncio.create_task(_run_ai_analysis_job(job_id, request.symbol, market, is_etf))

    print(f"[AI Analyze] === 총 소요: {time_module.time()-t0:.2f}초, job_id={job_id} ===")
    return {"success": True, "job_id": job_id, "status": "pending"}


# =============================================================================
# /api/ai/status/{job_id}
# =============================================================================
@router.get("/ai/status/{job_id}")
async def get_ai_job_status(job_id: str):
    """AI 분석 작업 상태 조회"""
    job = _ai_jobs.get(job_id)

    if not job:
        return {"success": False, "error": "작업을 찾을 수 없습니다", "status": "not_found"}

    if job["status"] == "done":
        report_text = job["result"] or ""
        sections = split_ai_report(report_text)

        response = {
            "success": True,
            "status": "done",
            "report": report_text,
            "sections": sections,
            "progress": "완료"
        }
        if "charts" in job:
            response["charts"] = job["charts"]
        if "stock" in job:
            response["stock"] = job["stock"]
        return response
    elif job["status"] == "error":
        return {
            "success": False,
            "status": "error",
            "error": job.get("error", "알 수 없는 오류"),
            "progress": "오류 발생"
        }
    else:
        return {
            "success": True,
            "status": job["status"],
            "progress": job.get("progress", "처리 중...")
        }


# =============================================================================
# /api/ai/report/pdf/{job_id}
# =============================================================================
@router.get("/ai/report/pdf/{job_id}")
async def download_ai_report_pdf(job_id: str):
    """AI 분석 리포트 PDF 다운로드"""
    from reportlab.lib.pagesizes import A4
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Image as RLImage
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.units import inch, cm
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    from reportlab.platypus import HRFlowable, Table, TableStyle
    from reportlab.lib import colors
    import tempfile
    import base64 as b64_module

    job = _ai_jobs.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="작업을 찾을 수 없습니다")

    if job["status"] != "done":
        raise HTTPException(status_code=400, detail="분석이 완료되지 않았습니다")

    # 한글 폰트 등록
    font_paths = [
        '/usr/share/fonts/truetype/nanum/NanumGothic.ttf',
        'C:/Windows/Fonts/malgun.ttf',
    ]
    font_registered = False
    for fp in font_paths:
        if os.path.exists(fp):
            try:
                pdfmetrics.registerFont(TTFont('Korean', fp))
                font_registered = True
                break
            except:
                pass

    pdf_path = os.path.join(CHARTS_DIR, f"report_{job_id}.pdf")

    doc = SimpleDocTemplate(
        pdf_path,
        pagesize=A4,
        rightMargin=2*cm, leftMargin=2*cm,
        topMargin=2*cm, bottomMargin=2*cm
    )

    styles = getSampleStyleSheet()

    if font_registered:
        styles.add(ParagraphStyle(
            name='KoreanTitle',
            fontName='Korean',
            fontSize=18,
            spaceAfter=20,
            alignment=1
        ))
        styles.add(ParagraphStyle(
            name='KoreanBody',
            fontName='Korean',
            fontSize=10,
            leading=14,
            spaceAfter=10
        ))
        styles.add(ParagraphStyle(
            name='KoreanHeading',
            fontName='Korean',
            fontSize=14,
            spaceBefore=15,
            spaceAfter=10
        ))
    else:
        styles.add(ParagraphStyle(name='KoreanTitle', parent=styles['Title']))
        styles.add(ParagraphStyle(name='KoreanBody', parent=styles['Normal']))
        styles.add(ParagraphStyle(name='KoreanHeading', parent=styles['Heading2']))

    story = []

    stock_info = job.get("stock", {})
    stock_name = stock_info.get("name", "종목")
    stock_code = stock_info.get("code", "")
    title = f"{stock_name}({stock_code}) AI 분석 리포트"
    story.append(Paragraph(title, styles['KoreanTitle']))
    story.append(Spacer(1, 0.3*inch))

    def _base64_to_rl_image(chart_data, width=6*inch, height=3*inch):
        """base64 data URL을 reportlab Image로 변환"""
        if not chart_data:
            return None
        try:
            if chart_data.startswith("data:image"):
                b64_str = chart_data.split(",", 1)[1]
            else:
                b64_str = chart_data
            img_bytes = b64_module.b64decode(b64_str)
            img_buf = io.BytesIO(img_bytes)
            return RLImage(img_buf, width=width, height=height)
        except Exception as e:
            print(f"[PDF] Chart base64 decode error: {e}")
            return None

    charts = job.get("charts", {})

    if not charts or job.get("cached"):
        try:
            symbol = job.get("symbol", stock_code)
            exchange = job.get("exchange", "")
            is_domestic = exchange.lower() in ("kis_kr", "kis_kr_etf", "upbit")
            market = "kr" if is_domestic else "us"
            print(f"[PDF] 캐시 리포트 - 차트 재생성: {stock_name}({symbol})")
            charts = await _generate_ai_charts(symbol, stock_name, market)
            job["charts"] = charts
        except Exception as e:
            print(f"[PDF] 차트 재생성 실패: {e}")
            charts = {}

    def clean_section_markers(txt):
        markers = ['[SECTION_1_4]', '[SECTION_51]', '[SECTION_52]', '[SECTION_53]', '[SECTION_54_END]']
        for m in markers:
            txt = txt.replace(m, '')
        return txt.strip()

    report_text = clean_section_markers(job.get("result", ""))

    def convert_markdown(txt):
        txt = re.sub(r'\*\*(.+?)\*\*', r'<b>\1</b>', txt)
        txt = re.sub(r'(?<!\*)\*(?!\*)(.+?)(?<!\*)\*(?!\*)', r'<i>\1</i>', txt)
        return txt

    def parse_markdown_table(table_lines):
        rows = []
        for tl in table_lines:
            tl = tl.strip()
            if tl.startswith('|') and tl.endswith('|'):
                cells = [c.strip() for c in tl[1:-1].split('|')]
                if all(c.replace('-', '').replace(':', '') == '' for c in cells):
                    continue
                rows.append(cells)
        if not rows:
            return None
        table_data = []
        for row in rows:
            table_data.append([Paragraph(convert_markdown(c), styles['KoreanBody']) for c in row])
        t = Table(table_data, repeatRows=1)
        t.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.lightgrey),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.black),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('FONTNAME', (0, 0), (-1, -1), 'Korean' if font_registered else 'Helvetica'),
            ('FONTSIZE', (0, 0), (-1, -1), 9),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
            ('TOPPADDING', (0, 0), (-1, -1), 6),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
        ]))
        return t

    sections = split_ai_report(report_text)
    charts = job.get("charts", {})

    def insert_section_with_chart(section_text, chart_key, section_title):
        if not section_text:
            return
        story.append(Spacer(1, 0.15*inch))
        story.append(Paragraph(f"<b>{section_title}</b>", styles['KoreanBody']))
        story.append(Spacer(1, 0.1*inch))
        chart_data = charts.get(chart_key)
        if chart_data:
            img = _base64_to_rl_image(chart_data)
            if img:
                story.append(img)
                story.append(Spacer(1, 0.12*inch))
        clean_text = re.sub(r'^#{1,4}\s*5\.\d[^\n]*\n?', '', section_text, flags=re.MULTILINE)
        clean_text = re.sub(r'^#{1,4}\s*5\.\s*기술적\s*분석\s*\n?', '', clean_text, flags=re.MULTILINE)
        for para_line in clean_text.split('\n'):
            para_line = para_line.strip()
            if para_line:
                story.append(Paragraph(convert_markdown(para_line), styles['KoreanBody']))

    before_ta = sections.get('before_ta', '')
    if not before_ta.strip():
        match = re.search(r'(?:#{1,4}\s*)?5\.1\s', report_text)
        if match:
            before_ta = report_text[:match.start()].strip()
        else:
            before_ta = report_text

    before_ta = re.sub(r'\n*#{1,4}\s*5\.\s*기술적\s*분석\s*$', '', before_ta).strip()

    lines = before_ta.split('\n')
    i = 0

    while i < len(lines):
        line = lines[i].strip()

        if not line:
            story.append(Spacer(1, 0.08*inch))
            i += 1
            continue

        if line in ['---', '***', '___'] or (len(line) >= 3 and all(c == '-' for c in line)):
            story.append(HRFlowable(width="100%", thickness=1, color=colors.grey, spaceAfter=10, spaceBefore=10))
            i += 1
            continue

        if line.startswith('|'):
            table_lines = []
            while i < len(lines) and lines[i].strip().startswith('|'):
                table_lines.append(lines[i])
                i += 1
            table = parse_markdown_table(table_lines)
            if table:
                story.append(table)
                story.append(Spacer(1, 0.15*inch))
            continue

        if line.startswith('## '):
            text_content = convert_markdown(line[3:])
            story.append(Spacer(1, 0.15*inch))
            story.append(Paragraph(text_content, styles['KoreanHeading']))
            story.append(Spacer(1, 0.08*inch))
            i += 1
            continue
        elif line.startswith('# '):
            text_content = convert_markdown(line[2:])
            story.append(Spacer(1, 0.15*inch))
            story.append(Paragraph(text_content, styles['KoreanHeading']))
            story.append(Spacer(1, 0.08*inch))
            i += 1
            continue
        elif line.startswith('### '):
            text_content = convert_markdown(line[4:])
            story.append(Paragraph(f"<b>{text_content}</b>", styles['KoreanBody']))
            story.append(Spacer(1, 0.08*inch))
            i += 1
            continue
        elif line.startswith('#### '):
            text_content = convert_markdown(line[5:])
            story.append(Paragraph(f"<b>{text_content}</b>", styles['KoreanBody']))
            i += 1
            continue

        if line.startswith('- ') or line.startswith('* '):
            text_content = convert_markdown(line[2:])
            story.append(Paragraph(f"* {text_content}", styles['KoreanBody']))
            i += 1
            continue
        if line.startswith('* '):
            text_content = convert_markdown(line[2:])
            story.append(Paragraph(f"* {text_content}", styles['KoreanBody']))
            i += 1
            continue

        if line.startswith('**') and line.endswith('**') and line.count('**') == 2:
            text_content = line[2:-2]
            story.append(Paragraph(f"<b>{text_content}</b>", styles['KoreanBody']))
            i += 1
            continue

        text_content = convert_markdown(line)
        story.append(Paragraph(text_content, styles['KoreanBody']))
        i += 1

    story.append(Spacer(1, 0.2*inch))

    insert_section_with_chart(sections.get('section_51'), 'price_chart', '5.1 주가 및 지지/저항선 분석')
    insert_section_with_chart(sections.get('section_52'), 'trend_chart', '5.2 추세추종 지표 분석')
    insert_section_with_chart(sections.get('section_53'), 'momentum_chart', '5.3 모멘텀 지표 분석')

    if sections.get('after_53'):
        after_53_text = sections['after_53']
        after_53_text = re.sub(r'(?:#{1,4}\s*)?(?:6|7)\.\s*면책조항.*', '', after_53_text, flags=re.DOTALL).strip()

        if after_53_text:
            story.append(Spacer(1, 0.15*inch))
            for para_line in after_53_text.split('\n'):
                para_line = para_line.strip()
                if para_line:
                    story.append(Paragraph(convert_markdown(para_line), styles['KoreanBody']))

    story.append(Spacer(1, 0.3*inch))
    story.append(HRFlowable(width="100%", thickness=1, color=colors.grey, spaceAfter=10, spaceBefore=10))
    story.append(Spacer(1, 0.1*inch))
    story.append(Paragraph("<b>6. 면책조항</b>", styles['KoreanHeading']))
    story.append(Spacer(1, 0.08*inch))
    disclaimer_text = (
        "본 보고서는 투자 참고 자료로만 활용하시기 바라며, "
        "특정 종목의 매수/매도를 권유하지 않습니다. "
        "투자 결정은 본인의 투자 성향, 시간 범위, 재정 상황을 고려하여 "
        "신중하게 내려주시기 바랍니다. "
        "과거 성과는 미래 결과를 보장하지 않으며, "
        "투자 손실 위험이 존재합니다. "
        "기술적 분석은 확률 기반 분석으로, 모든 신호가 정확히 작동하지 않을 수 있습니다."
    )
    story.append(Paragraph(disclaimer_text, styles['KoreanBody']))

    doc.build(story)

    return FileResponse(
        pdf_path,
        media_type="application/pdf",
        filename=f"{stock_name}_{stock_code}_분석리포트.pdf"
    )


# =============================================================================
# /api/ai/chat
# =============================================================================
@router.post("/ai/chat")
async def request_ai_chat(
    request: AIChatRequest,
    current_user: User = Depends(get_current_user_optional),
    db: Session = Depends(get_db)
):
    """AI 채팅 요청 -> job_id 즉시 반환 (백그라운드 처리)"""
    _ensure_ai_tables(db)

    # 요금제 제한 체크 (check_feature_allowed 사용)
    if current_user:
        allowed, error_msg, upgrade_url = check_feature_allowed(current_user, "ai", db, increment=False)
        if not allowed:
            raise HTTPException(
                status_code=403,
                detail={"message": error_msg, "upgrade_url": upgrade_url}
            )

    _cleanup_old_jobs()
    job_id = str(uuid.uuid4())[:8]

    _ai_jobs[job_id] = {
        "status": "pending",
        "progress": "AI가 생각 중...",
        "result": None,
        "created_at": datetime.now(KST),
        "user_id": current_user.id if current_user else None,
        "type": "chat",
    }

    # 사용량 증가
    if current_user:
        check_feature_allowed(current_user, "ai", db, increment=True)

    asyncio.create_task(_run_ai_chat_job(job_id, request.message, current_user.id if current_user else None))

    return {"success": True, "job_id": job_id, "status": "pending"}


# =============================================================================
# Helper Functions for AI Report Generation
# =============================================================================

def split_ai_report(text: str) -> dict:
    """AI 보고서를 섹션별로 분리"""
    sections = {
        'before_ta': '',
        'section_51': '',
        'section_52': '',
        'section_53': '',
        'after_53': ''
    }

    if not text:
        return sections

    if '[SECTION_1_4]' in text and '[SECTION_51]' in text:
        parts = text.split('[SECTION_51]', 1)
        sections['before_ta'] = parts[0].replace('[SECTION_1_4]', '').strip()
        rest = parts[1] if len(parts) > 1 else ''
    elif '[SECTION_51]' in text:
        parts = text.split('[SECTION_51]', 1)
        sections['before_ta'] = parts[0].strip()
        rest = parts[1] if len(parts) > 1 else ''
    else:
        pattern = r'(?=(?:#{1,4}\s*)?5\.1\s)'
        split_result = re.split(pattern, text, maxsplit=1)
        sections['before_ta'] = split_result[0].strip()
        rest = split_result[1] if len(split_result) > 1 else ''

    if '[SECTION_52]' in rest:
        parts52 = rest.split('[SECTION_52]', 1)
        sections['section_51'] = parts52[0].replace('[SECTION_51]', '').strip()
        rest2 = parts52[1] if len(parts52) > 1 else ''
    else:
        pattern52 = r'(?=(?:#{1,4}\s*)?5\.2\s)'
        split52 = re.split(pattern52, rest, maxsplit=1)
        sections['section_51'] = split52[0].replace('[SECTION_51]', '').strip()
        rest2 = split52[1] if len(split52) > 1 else ''

    if '[SECTION_53]' in rest2:
        parts53 = rest2.split('[SECTION_53]', 1)
        sections['section_52'] = parts53[0].replace('[SECTION_52]', '').strip()
        rest3 = parts53[1] if len(parts53) > 1 else ''
    else:
        pattern53 = r'(?=(?:#{1,4}\s*)?5\.3\s)'
        split53 = re.split(pattern53, rest2, maxsplit=1)
        sections['section_52'] = split53[0].replace('[SECTION_52]', '').strip()
        rest3 = split53[1] if len(split53) > 1 else ''

    if '[SECTION_54_END]' in rest3:
        parts54 = rest3.split('[SECTION_54_END]', 1)
        sections['section_53'] = parts54[0].replace('[SECTION_53]', '').strip()
        sections['after_53'] = parts54[1].strip() if len(parts54) > 1 else ''
    else:
        pattern_after = r'(?=(?:#{1,4}\s*)?(?:5\.4|6\.)\s)'
        split_after = re.split(pattern_after, rest3, maxsplit=1)
        sections['section_53'] = split_after[0].replace('[SECTION_53]', '').strip()
        sections['after_53'] = split_after[1].strip() if len(split_after) > 1 else ''

    for key in sections:
        for marker in ['[SECTION_1_4]', '[SECTION_51]', '[SECTION_52]', '[SECTION_53]', '[SECTION_54_END]']:
            sections[key] = sections[key].replace(marker, '')

    return sections


def _generate_simple_report(data: dict) -> str:
    """간단 템플릿 기반 보고서 생성"""
    name = data.get("name", data.get("symbol", "종목"))
    symbol = data.get("symbol", "")
    price = data.get("current_price", 0)
    change = data.get("change", 0)
    high = data.get("high", 0)
    low = data.get("low", 0)
    volume = data.get("volume", 0)

    trend = "상승" if change > 0 else ("하락" if change < 0 else "보합")

    report = f"""# {name} ({symbol}) 종합분석 보고서

## 1. 핵심 요약

**{name}**은(는) 현재 **{trend}** 추세를 보이고 있습니다.
- 현재가: {price:,}원 ({'+' if change >= 0 else ''}{change:.2f}%)
- 금일 고가: {high:,}원 / 저가: {low:,}원
- 거래량: {volume:,}주

## 2. 기술적 분석

### 가격 위치
- 금일 변동폭: {high - low:,}원
- 고가 대비: {((price - high) / high * 100) if high else 0:.1f}%
- 저가 대비: {((price - low) / low * 100) if low else 0:.1f}%

### 추세 분석
현재 {trend} 추세에 있으며, {'추가 상승 여력이 있어 보입니다.' if change > 2 else ('지지선 확인이 필요합니다.' if change < -2 else '횡보 구간으로 판단됩니다.')}

## 3. 종합 의견

### 시나리오별 전망

**상승 시나리오**
- 단기 저항선 돌파 시 추가 상승 가능
- 목표가: 현재가 대비 +5~10%

**횡보 시나리오**
- 현 가격대에서 박스권 형성 가능
- 거래량 증가 여부 주시 필요

**조정 시나리오**
- 지지선 이탈 시 추가 하락 가능
- 손절가: 현재가 대비 -3~5%

---

**면책조항**: 본 보고서는 투자 참고용으로 작성되었으며, 투자 결정에 대한 책임은 투자자 본인에게 있습니다. 과거 실적이 미래 수익을 보장하지 않습니다.

_BBooster AI 분석 시스템에서 생성됨_
"""
    return report


async def _generate_ai_charts(code: str, name: str, market: str = "kr") -> dict:
    """AI 분석용 차트 3종 생성 - base64로 반환"""
    from .ai_report_charts import generate_ai_charts
    return await generate_ai_charts(code, name, market)


async def _run_ai_analysis_job(job_id: str, symbol: str, market: str, is_etf: bool = False):
    """백그라운드에서 AI 분석 실행"""
    from .ai_report_engine import run_ai_analysis_job
    await run_ai_analysis_job(job_id, symbol, market, is_etf, _ai_jobs, get_master_cache)


async def _run_ai_chat_job(job_id: str, message: str, user_id: int = None):
    """백그라운드에서 AI 채팅 실행"""
    from .ai_report_engine import run_ai_chat_job
    await run_ai_chat_job(job_id, message, user_id, _ai_jobs, get_master_cache)

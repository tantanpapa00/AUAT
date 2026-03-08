"""
종목 상세 라우터 - 국내/해외 주식 상세 정보 API
"""
from typing import Optional
from fastapi import APIRouter, Depends, Query
from app.models import User
from app.auth import get_current_user_optional
from app.data_provider import (
    # Stock Detail Renewal (Phase 1)
    get_stock_financial_summary, get_stock_financial_trend, get_stock_company,
    get_stock_financial_statement, get_stock_news, get_stock_disclosures,
    get_stock_consensus,
    get_chart_data,
    # Phase 8-2: 국내 종목 상세 API
    get_stock_summary_kr, get_stock_financials_kr, get_stock_news_kr,
    get_eps_revision_history,
    # Phase 8-3: 기업 탭 + 재무제표 + 투자지표
    get_stock_company_kr, get_stock_statement_kr, get_invest_indicators_kr,
    # Phase 9: 해외 종목 상세 (yfinance)
    get_stock_summary_us, get_stock_chart_us, get_stock_news_us,
    get_stock_company_us, get_stock_financials_us,
    get_stock_filings_us, get_stock_analyst_us,
)

router = APIRouter(prefix="/api/stock", tags=["stock"])


def _check_hub_plan(user: Optional[User]) -> bool:
    """Hub 이상 요금제 체크 (종목 상세용)"""
    if not user:
        return False
    role = getattr(user, "role", "user")
    plan = getattr(user, "plan", "free")
    if role == "admin":
        return True
    return plan in ("hub", "pro", "premium")


# =============================================================================
# [STOCK DETAIL RENEWAL] 종목 상세 - 스탁이지 스타일 (Phase 1)
# =============================================================================

@router.get("/{code}/financial-summary")
async def api_stock_financial_summary(
    code: str,
    current_user: User = Depends(get_current_user_optional)
):
    """
    종목 재무 요약 (요약 탭)
    - 시가총액, PER, PBR, EPS, ROE, 52주 고저
    - Hub 이상 요금제 필요 (Free는 blur 처리)
    """
    data = await get_stock_financial_summary(code)
    is_premium = _check_hub_plan(current_user)
    return {
        "data": data,
        "is_premium": is_premium,
        "blur_fields": [] if is_premium else ["revenue", "operating_profit", "net_income", "roe", "eps", "foreign_ratio"]
    }


@router.get("/{code}/financial-trend")
async def api_stock_financial_trend(
    code: str,
    current_user: User = Depends(get_current_user_optional)
):
    """
    종목 실적 추이 (재무 탭)
    - 분기별/연간별 매출액, 영업이익, 당기순이익
    - Hub 이상 요금제 필요
    """
    is_premium = _check_hub_plan(current_user)
    if not is_premium:
        return {
            "data": {"annual": [], "quarter": []},
            "is_premium": False,
            "message": "Hub 이상 요금제에서 이용 가능합니다"
        }
    data = await get_stock_financial_trend(code)
    return {
        "data": data,
        "is_premium": True
    }


@router.get("/{code}/company")
async def api_stock_company(
    code: str,
    current_user: User = Depends(get_current_user_optional)
):
    """
    기업 정보 (기업 탭)
    - 회사 개요, CEO, 설립일, 사업 내용
    - 누구나 접근 가능
    """
    data = await get_stock_company(code)
    return {"data": data}


@router.get("/{code}/financial-statement")
async def api_stock_financial_statement(
    code: str,
    current_user: User = Depends(get_current_user_optional)
):
    """
    재무제표 상세 (재무 탭)
    - 대차대조표, 손익계산서, 현금흐름표
    - Hub 이상 요금제 필요
    """
    is_premium = _check_hub_plan(current_user)
    if not is_premium:
        return {
            "data": {"balance_sheet": [], "income_statement": [], "cash_flow": []},
            "is_premium": False,
            "message": "Hub 이상 요금제에서 이용 가능합니다"
        }
    data = await get_stock_financial_statement(code)
    return {
        "data": data,
        "is_premium": True
    }


@router.get("/{code}/news")
async def api_stock_news(
    code: str,
    limit: int = Query(20, ge=1, le=50),
    current_user: User = Depends(get_current_user_optional)
):
    """
    종목 뉴스/리포트 (소식 탭)
    - 누구나 접근 가능 (리포트는 Hub+)
    """
    data = await get_stock_news(code, limit)
    is_premium = _check_hub_plan(current_user)
    return {
        "data": {
            "news": data.get("news", []),
            "reports": data.get("reports", []) if is_premium else []
        },
        "is_premium": is_premium,
        "reports_locked": not is_premium
    }


@router.get("/{code}/disclosures")
async def api_stock_disclosures(
    code: str,
    limit: int = Query(20, ge=1, le=50),
    current_user: User = Depends(get_current_user_optional)
):
    """
    공시 정보 (소식 탭)
    - 누구나 접근 가능
    """
    data = await get_stock_disclosures(code, limit)
    return {"data": data}


@router.get("/{code}/consensus")
async def api_stock_consensus(
    code: str,
    current_user: User = Depends(get_current_user_optional)
):
    """
    투자 의견/컨센서스 (요약 탭)
    - Hub 이상 요금제 필요
    """
    is_premium = _check_hub_plan(current_user)
    if not is_premium:
        return {
            "data": {"target_price": 0, "opinion": "", "analyst_count": 0, "target_price_list": []},
            "is_premium": False,
            "message": "Hub 이상 요금제에서 이용 가능합니다"
        }
    data = await get_stock_consensus(code)
    return {
        "data": data,
        "is_premium": True
    }


# =============================================================================
# Phase 8: 국내 종목 상세 API
# =============================================================================

@router.get("/kr/{code}/chart")
async def api_stock_chart_kr(
    code: str,
    timeframe: str = Query("daily", regex="^(daily|weekly|monthly)$"),
    period: str = Query("3m", description="기간: 1d, 1w, 1m, 3m, 6m, 1y"),
    current_user: User = Depends(get_current_user_optional)
):
    """
    국내 종목 차트 데이터
    - timeframe: daily(일봉), weekly(주봉), monthly(월봉)
    - 누구나 접근 가능
    """
    candles = await get_chart_data(code, period, timeframe)
    return {
        "code": code,
        "timeframe": timeframe,
        "candles": candles
    }


@router.get("/kr/{code}/summary")
async def api_stock_summary_kr(
    code: str,
    current_user: User = Depends(get_current_user_optional)
):
    """
    국내 종목 요약 정보 (기본정보 + 재무지표)
    - 누구나 접근 가능
    """
    data = await get_stock_summary_kr(code)
    return {"data": data}


@router.get("/kr/{code}/financials")
async def api_stock_financials_kr(
    code: str,
    fin_type: str = Query("annual", description="annual 또는 quarter"),
    current_user: User = Depends(get_current_user_optional)
):
    """
    국내 종목 재무 추이 (연간/분기)
    - 누구나 접근 가능
    """
    data = await get_stock_financials_kr(code, fin_type)
    return {"data": data}


@router.get("/kr/{code}/news")
async def api_stock_news_kr(
    code: str,
    limit: int = Query(20, ge=1, le=50),
    current_user: User = Depends(get_current_user_optional)
):
    """
    국내 종목 뉴스
    - 누구나 접근 가능
    """
    data = await get_stock_news_kr(code, limit)
    return {"data": data}


@router.get("/kr/{code}/eps-revision")
async def api_eps_revision_history(
    code: str,
    current_user: User = Depends(get_current_user_optional)
):
    """
    국내 종목 EPS 추정 변화 이력 (FnGuide 컨센서스)
    - FY1/FY2/FY3 각각 5개 시점 데이터
    - 누구나 접근 가능
    """
    data = await get_eps_revision_history(code)
    return {"data": data}


@router.get("/kr/{code}/company")
async def api_stock_company_kr(
    code: str,
    current_user: User = Depends(get_current_user_optional)
):
    """
    국내 종목 기업 정보 탭
    - 동종업계 종목, 리서치 리포트, 투자의견/목표가
    - 누구나 접근 가능
    """
    data = await get_stock_company_kr(code)
    return {"data": data}


@router.get("/kr/{code}/statement")
async def api_stock_statement_kr(
    code: str,
    period_type: str = Query("annual", regex="^(annual|quarter)$"),
    current_user: User = Depends(get_current_user_optional)
):
    """
    국내 종목 상세 재무제표 (손익계산서)
    - period_type: annual(연간), quarter(분기)
    - 누구나 접근 가능
    """
    data = await get_stock_statement_kr(code, period_type)
    return {"data": data}


@router.get("/kr/{code}/invest-indicators")
async def api_stock_invest_indicators_kr(
    code: str,
    current_user: User = Depends(get_current_user_optional)
):
    """
    국내 종목 투자지표 4카테고리 (성장성/수익성/안정성/밸류에이션)
    - 데이터 소스: FnGuide 재무비율 + 네이버
    - 누구나 접근 가능
    """
    data = await get_invest_indicators_kr(code)
    return {"data": data}


# =============================================================================
# Phase 9: 해외 종목 상세 API (yfinance)
# =============================================================================

@router.get("/us/{ticker}/summary")
async def api_stock_summary_us(
    ticker: str,
    current_user: User = Depends(get_current_user_optional)
):
    """
    해외 종목 요약 정보
    - 데이터 소스: yfinance
    - 누구나 접근 가능
    """
    data = await get_stock_summary_us(ticker)
    return {"data": data}


@router.get("/us/{ticker}/chart")
async def api_stock_chart_us(
    ticker: str,
    timeframe: str = Query("daily", regex="^(daily|weekly|monthly)$"),
    period: str = Query("3m", regex="^(1d|5d|1w|1m|3m|6m|1y|2y|5y)$"),
    current_user: User = Depends(get_current_user_optional)
):
    """
    해외 종목 차트 데이터
    - 데이터 소스: Yahoo Finance Chart API
    - timeframe: daily(일봉), weekly(주봉), monthly(월봉)
    - 누구나 접근 가능
    """
    data = await get_stock_chart_us(ticker, period, timeframe)
    return {"data": data}


@router.get("/us/{ticker}/news")
async def api_stock_news_us(
    ticker: str,
    limit: int = Query(20, ge=1, le=50),
    current_user: User = Depends(get_current_user_optional)
):
    """
    해외 종목 뉴스
    - 데이터 소스: yfinance
    - 누구나 접근 가능
    """
    data = await get_stock_news_us(ticker, limit)
    return {"data": data}


@router.get("/us/{ticker}/filings")
async def api_stock_filings_us(
    ticker: str,
    limit: int = Query(30, ge=1, le=50),
    current_user: User = Depends(get_current_user_optional)
):
    """
    해외 종목 SEC 공시
    - 데이터 소스: yfinance sec_filings
    - 누구나 접근 가능
    """
    data = await get_stock_filings_us(ticker, limit)
    return {"data": data}


@router.get("/us/{ticker}/analyst")
async def api_stock_analyst_us(
    ticker: str,
    limit: int = Query(30, ge=1, le=50),
    current_user: User = Depends(get_current_user_optional)
):
    """
    해외 종목 애널리스트 의견
    - 데이터 소스: yfinance upgrades_downgrades
    - 누구나 접근 가능
    """
    data = await get_stock_analyst_us(ticker, limit)
    return {"data": data}


@router.get("/us/{ticker}/company")
async def api_stock_company_us(
    ticker: str,
    current_user: User = Depends(get_current_user_optional)
):
    """
    해외 종목 기업 정보
    - 데이터 소스: yfinance
    - 누구나 접근 가능
    """
    data = await get_stock_company_us(ticker)
    return {"data": data}


@router.get("/us/{ticker}/financials")
async def api_stock_financials_us(
    ticker: str,
    current_user: User = Depends(get_current_user_optional)
):
    """
    해외 종목 재무 정보 (연간 + 분기)
    - 데이터 소스: yfinance
    - 누구나 접근 가능
    """
    data = await get_stock_financials_us(ticker)
    return {"data": data}


@router.get("/us/{ticker}/statement")
async def api_stock_statement_us(
    ticker: str,
    period_type: str = Query("annual", regex="^(annual|quarter)$"),
    current_user: User = Depends(get_current_user_optional)
):
    """
    해외 종목 상세 재무제표 (국내와 동일 구조)
    - period_type: annual(연간), quarter(분기)
    - 데이터 소스: yfinance
    - 누구나 접근 가능
    """
    from app.yahoo_finance import get_stock_statement_us
    data = await get_stock_statement_us(ticker, period_type)
    return {"data": data}


@router.get("/us/{ticker}/invest-indicators")
async def api_stock_invest_indicators_us(
    ticker: str,
    current_user: User = Depends(get_current_user_optional)
):
    """
    해외 종목 투자지표 4카테고리 (국내와 동일 구조)
    - 성장성/수익성/안정성/밸류에이션
    - 데이터 소스: yfinance
    - 누구나 접근 가능
    """
    from app.yahoo_finance import get_invest_indicators_us
    data = await get_invest_indicators_us(ticker)
    return {"data": data}

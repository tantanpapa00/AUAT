# app/routers/market_us.py
# 해외시장 API 엔드포인트

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from datetime import datetime

from app.db import get_db
from app.auth import get_current_user_optional
from app.models import User
from app.utils.plan_limits import check_pro_plan
from app.data_provider import get_us_market_overview

router = APIRouter(prefix="/api/market/us", tags=["market-us"])

# 섹터 ETF 한글 이름 매핑
US_SECTOR_NAME_MAP = {
    "XLK": "기술", "XLF": "금융", "XLV": "헬스케어",
    "XLE": "에너지", "XLY": "임의소비재", "XLP": "필수소비재",
    "XLI": "산업재", "XLB": "소재", "XLU": "유틸리티",
    "XLRE": "부동산", "XLC": "커뮤니케이션"
}

# 섹터 ETF 영문 이름 매핑
US_SECTOR_NAME_MAP_EN = {
    "XLK": "Technology", "XLF": "Financials", "XLV": "Healthcare",
    "XLE": "Energy", "XLY": "Consumer Disc.", "XLP": "Consumer Staples",
    "XLI": "Industrials", "XLB": "Materials", "XLU": "Utilities",
    "XLRE": "Real Estate", "XLC": "Communication"
}

# 섹터별 대표종목 매핑
SECTOR_TOP_STOCKS = {
    "XLK": [{"name": "AAPL", "rs": 95}, {"name": "NVDA", "rs": 98}, {"name": "MSFT", "rs": 90}, {"name": "AVGO", "rs": 92}, {"name": "CRM", "rs": 85}],
    "XLF": [{"name": "JPM", "rs": 88}, {"name": "BRK-B", "rs": 82}, {"name": "V", "rs": 86}, {"name": "MA", "rs": 84}, {"name": "BAC", "rs": 80}],
    "XLV": [{"name": "UNH", "rs": 75}, {"name": "LLY", "rs": 96}, {"name": "JNJ", "rs": 65}, {"name": "ABBV", "rs": 78}, {"name": "MRK", "rs": 72}],
    "XLE": [{"name": "XOM", "rs": 70}, {"name": "CVX", "rs": 68}, {"name": "COP", "rs": 72}, {"name": "EOG", "rs": 74}, {"name": "SLB", "rs": 66}],
    "XLY": [{"name": "AMZN", "rs": 88}, {"name": "TSLA", "rs": 92}, {"name": "HD", "rs": 76}, {"name": "MCD", "rs": 80}, {"name": "NKE", "rs": 60}],
    "XLP": [{"name": "PG", "rs": 72}, {"name": "KO", "rs": 68}, {"name": "PEP", "rs": 70}, {"name": "COST", "rs": 85}, {"name": "WMT", "rs": 78}],
    "XLI": [{"name": "CAT", "rs": 88}, {"name": "GE", "rs": 90}, {"name": "UNP", "rs": 75}, {"name": "RTX", "rs": 82}, {"name": "DE", "rs": 78}],
    "XLB": [{"name": "LIN", "rs": 80}, {"name": "APD", "rs": 72}, {"name": "SHW", "rs": 78}, {"name": "ECL", "rs": 70}, {"name": "NEM", "rs": 65}],
    "XLU": [{"name": "NEE", "rs": 75}, {"name": "SO", "rs": 70}, {"name": "DUK", "rs": 68}, {"name": "CEG", "rs": 85}, {"name": "SRE", "rs": 72}],
    "XLRE": [{"name": "PLD", "rs": 78}, {"name": "AMT", "rs": 72}, {"name": "EQIX", "rs": 80}, {"name": "SPG", "rs": 70}, {"name": "PSA", "rs": 68}],
    "XLC": [{"name": "META", "rs": 95}, {"name": "GOOGL", "rs": 88}, {"name": "NFLX", "rs": 90}, {"name": "DIS", "rs": 65}, {"name": "TMUS", "rs": 78}],
}


@router.get("/overview")
async def api_market_us_overview(
    current_user: User = Depends(get_current_user_optional),
    db: Session = Depends(get_db)
):
    """해외시장 현황 - yfinance 사용"""
    if current_user and current_user.role == "admin":
        pass
    elif not check_pro_plan(current_user):
        if not current_user:
            raise HTTPException(status_code=401, detail="로그인이 필요합니다")
        raise HTTPException(status_code=403, detail="Pro 이상 요금제에서 이용 가능합니다")

    try:
        data = await get_us_market_overview()
        return {
            "indices": data.get("indices", []),
            "stocks": data.get("stocks", []),
            "success": True,
        }
    except Exception as e:
        print(f"[API] US market error: {e}")
        return {
            "indices": [],
            "stocks": [],
            "success": False,
            "error": str(e),
        }


@router.get("/full")
async def api_market_us_full(
    lang: str = Query(default="kr", description="언어 설정 (kr=한글, en=영문)"),
    current_user: User = Depends(get_current_user_optional),
    db: Session = Depends(get_db)
):
    """
    해외시장 전체 데이터 (Phase 5)
    - 지수 4개 + VIX
    - 섹터 ETF 11개
    - 히트맵 30종목
    - Fear & Greed Index
    - 시장신호 (Big Picture)
    """
    if current_user and current_user.role == "admin":
        pass
    elif not check_pro_plan(current_user):
        if not current_user:
            raise HTTPException(status_code=401, detail="로그인이 필요합니다")
        raise HTTPException(status_code=403, detail="Pro 이상 요금제에서 이용 가능합니다")

    try:
        from app.market_analysis.data_collector_us import get_us_market_summary
        from app.market_analysis.signal_engine import BIG_PICTURE_CONFIG

        # 1. 미국시장 전체 요약 수집 (병렬) - lang 파라미터 전달
        summary = await get_us_market_summary(lang=lang)

        def calc_us_signal_from_indices(indices: dict, market_key: str) -> tuple:
            """US 지수 데이터로 신호 계산"""
            idx_data = indices.get(market_key, {})
            change_pct = idx_data.get("change_percent", 0)

            # 단순 변동률 기반 신호 (데이터 없을 때 fallback)
            if change_pct <= -3.0:
                return ("red", "red")
            elif change_pct <= -1.0:
                return ("yellow", "yellow")
            elif change_pct >= 1.0:
                return ("green", "green")
            else:
                return ("yellow", "yellow")

        # 2. 시장신호 조회 (SP500/NASDAQ) - 실시간 계산 사용
        signal_result = {}
        try:
            from app.models import MarketSignal
            from app.market_analysis.data_collector_us import calculate_us_signal
            indices = summary.get("indices", {})

            for market in ["SP500", "NASDAQ"]:
                # DB에서 조회
                signal_row = db.query(MarketSignal).filter(MarketSignal.market == market).first()

                # DB 데이터가 있으면 사용 (개별 컬럼 참조)
                if signal_row and signal_row.status:
                    status = signal_row.status
                    cfg = BIG_PICTURE_CONFIG.get(status, BIG_PICTURE_CONFIG["confirmed_uptrend"])
                    db_short = signal_row.short_term_signal or "yellow"
                    db_long = signal_row.long_term_signal or "yellow"
                    active_dd = signal_row.active_dd_count or 0

                    # 실시간 지수 데이터로 신호 보정 (급락 시 즉시 반영)
                    idx_key = "sp500" if market == "SP500" else "nasdaq"
                    idx_data = indices.get(idx_key, {})
                    change_pct = idx_data.get("change_pct", 0)

                    # 급락 시 DB 신호 무시하고 실시간 반영
                    if change_pct <= -4.0:
                        short_signal, long_signal = "red", "yellow"
                    elif change_pct <= -1.5:
                        short_signal, long_signal = "yellow", db_long
                    else:
                        short_signal, long_signal = db_short, db_long

                    signal_result[market.lower()] = {
                        "status": status,
                        "status_label": cfg["label"],
                        "exposure": cfg["exposure"],
                        "active_dd_count": active_dd,
                        "rally_day_count": signal_row.rally_day_count or 0,
                        "short_term_signal": short_signal,
                        "long_term_signal": long_signal,
                    }
                else:
                    # DB 데이터 없음 → 실시간 계산 (yfinance)
                    idx_symbol = "^GSPC" if market == "SP500" else "^IXIC"
                    try:
                        sig = await calculate_us_signal(idx_symbol)
                        status = sig.get("status", "unknown")
                        cfg = BIG_PICTURE_CONFIG.get(status, BIG_PICTURE_CONFIG.get("confirmed_uptrend", {}))

                        signal_result[market.lower()] = {
                            "status": status,
                            "status_label": sig.get("status_label", cfg.get("label", "알 수 없음")),
                            "exposure": cfg.get("exposure", "0-20%"),
                            "active_dd_count": sig.get("active_dd_count", 0),
                            "rally_day_count": 0,
                            "short_term_signal": sig.get("short_term_signal", "yellow"),
                            "long_term_signal": sig.get("long_term_signal", "yellow"),
                            "distribution_days": sig.get("distribution_days", []),
                        }
                    except Exception as calc_err:
                        print(f"[US] calculate_us_signal error for {market}: {calc_err}")
                        idx_key = "sp500" if market == "SP500" else "nasdaq"
                        short_signal, long_signal = calc_us_signal_from_indices(indices, idx_key)
                        signal_result[market.lower()] = {
                            "status": "unknown",
                            "status_label": "계산 중",
                            "exposure": "0-20%",
                            "active_dd_count": 0,
                            "rally_day_count": 0,
                            "short_term_signal": short_signal,
                            "long_term_signal": long_signal,
                        }
        except Exception as sig_err:
            print(f"[US] signal query error: {sig_err}")
            # 에러 시 "yellow" (불확실) 반환, 절대 "green" 아님
            for market in ["sp500", "nasdaq"]:
                signal_result[market] = {
                    "status": "unknown",
                    "status_label": "조회 실패",
                    "exposure": "0-20%",
                    "active_dd_count": 0,
                    "rally_day_count": 0,
                    "short_term_signal": "yellow",
                    "long_term_signal": "yellow",
                }

        return {
            "success": True,
            "indices": summary.get("indices", {}),
            "sectors": summary.get("sectors", []),
            "heatmap": summary.get("heatmap", []),
            "fear_greed": summary.get("fear_greed", {}),
            "breadth": summary.get("breadth", {}),
            "rising_stocks": summary.get("rising_stocks", 0),
            "falling_stocks": summary.get("falling_stocks", 0),
            "unchanged_stocks": summary.get("unchanged_stocks", 0),
            "signal": signal_result,
            "updated_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
        }

    except Exception as e:
        print(f"[API] US market full error: {e}")
        import traceback
        traceback.print_exc()
        return {
            "success": False,
            "indices": {},
            "sectors": [],
            "heatmap": [],
            "fear_greed": {},
            "breadth": {},
            "rising_stocks": 0,
            "falling_stocks": 0,
            "unchanged_stocks": 0,
            "signal": {},
            "error": str(e),
        }


@router.get("/ranking")
async def get_us_stock_ranking(
    sort: str = Query("change", description="정렬 기준: change(등락률), volume(거래대금)"),
    order: str = Query("desc", description="정렬 순서: desc(내림차순), asc(오름차순)"),
    limit: int = Query(20, description="반환 개수"),
    current_user: User = Depends(get_current_user_optional),
):
    """
    해외(US) 특징주 API - 상승률/하락률/거래대금 상위 종목
    국내 /api/market/ranking과 동일한 응답 구조
    """
    if current_user and current_user.role == "admin":
        pass
    elif not check_pro_plan(current_user):
        if not current_user:
            raise HTTPException(status_code=401, detail="로그인이 필요합니다")
        raise HTTPException(status_code=403, detail="Pro 이상 요금제에서 이용 가능합니다")

    try:
        from app.screener.us_screener import load_us_stocks

        # US 종목 데이터 로드 (캐시됨)
        stocks = await load_us_stocks()

        if not stocks:
            return {"success": True, "ranking_type": sort, "market": "us", "stocks": []}

        # 정렬
        reverse = (order == "desc")
        if sort == "change":
            stocks.sort(key=lambda x: x.get("change_pct") or 0, reverse=reverse)
        elif sort == "volume":
            # yfinance fast_info에서 volume 미제공 → market_cap으로 대체
            stocks.sort(key=lambda x: x.get("market_cap") or 0, reverse=reverse)

        # 상위 limit개 추출
        top_stocks = stocks[:limit]

        # 응답 형식 맞추기 (프론트와 동일한 키 사용)
        result = []
        for i, s in enumerate(top_stocks):
            result.append({
                "rank": i + 1,
                "name": s.get("name", ""),
                "code": s.get("symbol") or s.get("code", ""),
                "symbol": s.get("symbol") or s.get("code", ""),
                "market": s.get("exchange", "NYSE/NASDAQ"),
                "price": s.get("price", 0),
                "change_pct": s.get("change_pct", 0),
                "value": s.get("market_cap", 0),
                "market_cap": s.get("market_cap", 0),
            })

        return {
            "success": True,
            "ranking_type": sort,
            "market": "us",
            "stocks": result,
        }

    except Exception as e:
        print(f"[API] /api/market/us/ranking 오류: {e}")
        import traceback
        traceback.print_exc()
        return {"success": False, "ranking_type": sort, "market": "us", "stocks": [], "error": str(e)}


@router.get("/sectors")
async def get_us_market_sectors(
    sort: str = Query("change", description="정렬 기준: change(등락률), volume(거래대금)"),
    order: str = Query("desc", description="정렬 순서: desc(내림차순), asc(오름차순)"),
    current_user: User = Depends(get_current_user_optional),
):
    """
    해외(US) 섹터별 등락률 API - S&P 500 GICS 11개 섹터
    국내 /api/market/sectors와 동일한 응답 구조
    """
    if current_user and current_user.role == "admin":
        pass
    elif not check_pro_plan(current_user):
        if not current_user:
            raise HTTPException(status_code=401, detail="로그인이 필요합니다")
        raise HTTPException(status_code=403, detail="Pro 이상 요금제에서 이용 가능합니다")

    try:
        from app.market_analysis.data_collector_us import US_SECTOR_ETFS, fetch_sector_etf_daily
        import yfinance as yf

        result = []

        for etf in US_SECTOR_ETFS:
            symbol = etf["symbol"]
            try:
                # yfinance로 현재가 및 등락률 가져오기
                ticker = yf.Ticker(symbol)
                hist = ticker.history(period="2d")

                if len(hist) >= 2:
                    current_price = float(hist["Close"].iloc[-1])
                    prev_price = float(hist["Close"].iloc[-2])
                    change_pct = ((current_price - prev_price) / prev_price) * 100
                    volume = int(hist["Volume"].iloc[-1]) if "Volume" in hist.columns else 0
                elif len(hist) == 1:
                    current_price = float(hist["Close"].iloc[-1])
                    change_pct = 0
                    volume = int(hist["Volume"].iloc[-1]) if "Volume" in hist.columns else 0
                else:
                    current_price = 0
                    change_pct = 0
                    volume = 0

                result.append({
                    "name": etf["name"],
                    "name_en": etf["name_en"],
                    "symbol": symbol,
                    "etf": symbol,
                    "change_pct": round(change_pct, 2),
                    "change_percent": round(change_pct, 2),
                    "trading_value": volume,
                    "price": round(current_price, 2),
                })
            except Exception as etf_err:
                print(f"[US Sectors] {symbol} 오류: {etf_err}")
                result.append({
                    "name": etf["name"],
                    "name_en": etf["name_en"],
                    "symbol": symbol,
                    "etf": symbol,
                    "change_pct": 0,
                    "change_percent": 0,
                    "trading_value": 0,
                    "price": 0,
                })

        # 정렬
        reverse = (order == "desc")
        if sort == "change":
            result.sort(key=lambda x: abs(x.get("change_percent") or 0), reverse=reverse)
        elif sort == "volume":
            result.sort(key=lambda x: x.get("trading_value") or 0, reverse=reverse)

        return {
            "success": True,
            "sectors": result,
            "updated_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
        }

    except Exception as e:
        print(f"[API] /api/market/us/sectors 오류: {e}")
        import traceback
        traceback.print_exc()
        return {"success": False, "sectors": [], "error": str(e)}


@router.get("/trend-maintain")
async def get_us_trend_maintain(
    current_user: User = Depends(get_current_user_optional),
):
    """해외 섹터 ETF 추세유지 분석 (20MA 기준)"""
    if current_user and current_user.role == "admin":
        pass
    elif not check_pro_plan(current_user):
        if not current_user:
            raise HTTPException(status_code=401, detail="로그인이 필요합니다")
        raise HTTPException(status_code=403, detail="Pro 이상 요금제에서 이용 가능합니다")

    result = []
    try:
        from app.market_analysis.data_collector_us import US_SECTOR_ETFS, fetch_sector_etf_daily
        from app.market_analysis.trend_maintain import calculate_trend_maintain

        for etf in US_SECTOR_ETFS:
            symbol = etf["symbol"]
            closes = await fetch_sector_etf_daily(symbol, 60)

            if len(closes) >= 20:
                trend = calculate_trend_maintain(closes)
                if trend:
                    current_price = closes[-1] if closes else 0
                    prev_price = closes[-2] if len(closes) >= 2 else current_price
                    change_pct_val = ((current_price - prev_price) / prev_price * 100) if prev_price else 0

                    result.append({
                        "sector": etf["name"],
                        "name": symbol,
                        "etf": symbol,
                        "etf_name": etf["name_en"],
                        "change_percent": round(change_pct_val, 2),
                        "change_pct": round(change_pct_val, 2),
                        "position": trend["position"],
                        "days": trend["days"],
                        "gap_percent": trend["gap_percent"],
                        "signal": trend["signal"],
                        "return_since_entry": trend.get("return_since_entry"),
                        "ma20": trend["ma20"],
                        "current_price": trend["current_price"],
                        "top_holdings": SECTOR_TOP_STOCKS.get(symbol, []),
                    })
            else:
                result.append({
                    "sector": etf["name"],
                    "name": symbol,
                    "etf": symbol,
                    "etf_name": etf["name_en"],
                    "change_percent": 0,
                    "change_pct": 0,
                    "position": "-",
                    "days": 0,
                    "gap_percent": 0,
                    "signal": "gray",
                    "top_holdings": SECTOR_TOP_STOCKS.get(symbol, []),
                })

        # 정렬: 유지 > 이탈, 일수 내림차순
        result.sort(key=lambda x: (0 if x["position"] == "유지" else 1, -x["days"]))

    except Exception as e:
        print(f"[API] /api/market/us/trend-maintain 오류: {e}")
        import traceback
        traceback.print_exc()

    return {
        "success": True,
        "data": result,
        "updated_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
    }

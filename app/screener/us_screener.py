"""
해외(미국) 주식 스크리너
Alpaca API + GitHub S&P500 CSV(fallback) + yfinance 기반
"""

import asyncio
import csv
import io
import os
import httpx
import time as _time
import json
import urllib.request
import urllib.error
import urllib.parse
from typing import List, Dict, Any, Optional
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor

from .filters import apply_screener_filters, sort_screener_results

# ========== 상수 정의 ==========

# GitHub S&P 500 CSV URL (fallback)
SP500_CSV_URL = "https://raw.githubusercontent.com/datasets/s-and-p-500-companies/main/data/constituents.csv"

# Alpaca API URLs
ALPACA_ASSETS_URL = "https://paper-api.alpaca.markets/v2/assets"

# GICS 섹터 한글 변환
SECTOR_KR = {
    "Information Technology": "기술",
    "Technology": "기술",
    "Health Care": "헬스케어",
    "Healthcare": "헬스케어",
    "Financials": "금융",
    "Financial": "금융",
    "Financial Services": "금융",
    "Consumer Discretionary": "임의소비재",
    "Consumer Cyclical": "임의소비재",
    "Consumer Staples": "필수소비재",
    "Consumer Defensive": "필수소비재",
    "Communication Services": "커뮤니케이션",
    "Industrials": "산업재",
    "Energy": "에너지",
    "Utilities": "유틸리티",
    "Real Estate": "부동산",
    "Materials": "소재",
    "Basic Materials": "소재",
}

# ========== 캐시 ==========

# S&P 500 목록 캐시 (24시간)
_sp500_list_cache: Dict[str, Any] = {"data": None, "ts": 0}
_SP500_LIST_TTL = 86400  # 24시간

# 가격 데이터 캐시 (5분)
_price_cache: Dict[str, Any] = {"data": {}, "ts": 0}
_PRICE_TTL = 300  # 5분

# 전체 종목 캐시 (10분)
_us_stock_cache = None
_us_cache_ts = 0
_US_CACHE_TTL = 600  # 10분

# yfinance 작업용 ThreadPoolExecutor
_executor = ThreadPoolExecutor(max_workers=2)


# ========== S&P 500 목록 (GitHub CSV) ==========

async def get_sp500_list() -> List[Dict]:
    """
    S&P 500 종목 목록을 GitHub CSV에서 가져옴 (24시간 캐시)
    Returns: [{"symbol": "AAPL", "name": "Apple Inc.", "sector": "기술", "sub_industry": "..."}, ...]
    """
    global _sp500_list_cache
    now = _time.time()

    # 캐시 확인
    if _sp500_list_cache["data"] and (now - _sp500_list_cache["ts"]) < _SP500_LIST_TTL:
        return _sp500_list_cache["data"]

    stocks = []
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.get(SP500_CSV_URL)
            if resp.status_code == 200:
                text = resp.text
                reader = csv.DictReader(io.StringIO(text))
                for row in reader:
                    symbol = row.get("Symbol", "").strip()
                    if not symbol:
                        continue

                    # BRK.B → BRK-B (yfinance 호환)
                    symbol = symbol.replace(".", "-")

                    sector_en = row.get("GICS Sector", row.get("Sector", "")).strip()
                    sector_kr = SECTOR_KR.get(sector_en, sector_en)

                    stocks.append({
                        "symbol": symbol,
                        "name": row.get("Security", row.get("Name", symbol)).strip(),
                        "sector": sector_kr,
                        "sector_en": sector_en,
                        "sub_industry": row.get("GICS Sub-Industry", "").strip(),
                    })

                _sp500_list_cache = {"data": stocks, "ts": now}
                print(f"[US] S&P 500 목록 로드: {len(stocks)}개")

    except Exception as e:
        print(f"[US] S&P 500 CSV 로드 실패: {e}")

    # 캐시에 이전 데이터가 있으면 반환
    if not stocks and _sp500_list_cache["data"]:
        return _sp500_list_cache["data"]

    return stocks


# ========== Alpaca 종목 목록 ==========

# Alpaca 종목 캐시 (1시간)
_alpaca_assets_cache: Dict[str, Any] = {"data": None, "ts": 0}
_ALPACA_ASSETS_TTL = 3600  # 1시간


async def get_alpaca_assets(
    exchanges: Optional[List[str]] = None,
    tradable_only: bool = True,
) -> List[Dict]:
    """
    Alpaca API에서 거래 가능한 미국 전체 종목 가져오기 (1시간 캐시)

    GET https://paper-api.alpaca.markets/v2/assets
    파라미터: status=active&asset_class=us_equity

    Args:
        exchanges: 거래소 필터 (예: ["NYSE", "NASDAQ", "AMEX"])
        tradable_only: tradable=true인 종목만 반환

    Returns: [{"symbol": "AAPL", "name": "Apple Inc.", "exchange": "NASDAQ", "tradable": True, "fractionable": True}, ...]
    """
    global _alpaca_assets_cache
    now = _time.time()

    # 캐시 확인
    if _alpaca_assets_cache["data"] and (now - _alpaca_assets_cache["ts"]) < _ALPACA_ASSETS_TTL:
        cached = _alpaca_assets_cache["data"]
        # 필터링 적용
        return _filter_alpaca_assets(cached, exchanges, tradable_only)

    # Alpaca API 키 확인
    api_key = os.getenv("ALPACA_API_KEY", "").strip()
    api_secret = os.getenv("ALPACA_API_SECRET", "").strip()
    base_url = os.getenv("ALPACA_BASE_URL", "https://paper-api.alpaca.markets").rstrip("/")

    if not api_key or not api_secret:
        print("[US] Alpaca API 키 없음 - S&P 500 fallback 사용")
        return await _get_alpaca_fallback_sp500()

    # API 호출
    url = f"{base_url}/v2/assets"
    params = {
        "status": "active",
        "asset_class": "us_equity",
    }
    full_url = f"{url}?{urllib.parse.urlencode(params)}"

    headers = {
        "APCA-API-KEY-ID": api_key,
        "APCA-API-SECRET-KEY": api_secret,
        "Accept": "application/json",
    }

    req = urllib.request.Request(full_url, headers=headers)

    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        print(f"[US] Alpaca API HTTP 에러: {e.code}")
        return await _get_alpaca_fallback_sp500()
    except Exception as e:
        print(f"[US] Alpaca API 에러: {e}")
        return await _get_alpaca_fallback_sp500()

    if not isinstance(data, list):
        print("[US] Alpaca API 응답 형식 오류")
        return await _get_alpaca_fallback_sp500()

    # 데이터 변환
    assets = []
    for asset in data:
        assets.append({
            "symbol": asset.get("symbol", ""),
            "name": asset.get("name", ""),
            "exchange": asset.get("exchange", ""),
            "tradable": asset.get("tradable", False),
            "fractionable": asset.get("fractionable", False),
            "shortable": asset.get("shortable", False),
            "easy_to_borrow": asset.get("easy_to_borrow", False),
            "marginable": asset.get("marginable", False),
        })

    _alpaca_assets_cache = {"data": assets, "ts": now}
    print(f"[US] Alpaca 종목 목록 로드: {len(assets)}개")

    return _filter_alpaca_assets(assets, exchanges, tradable_only)


def _filter_alpaca_assets(
    assets: List[Dict],
    exchanges: Optional[List[str]] = None,
    tradable_only: bool = True,
) -> List[Dict]:
    """Alpaca 종목 필터링"""
    result = assets

    # tradable 필터
    if tradable_only:
        result = [a for a in result if a.get("tradable")]

    # 거래소 필터
    if exchanges:
        target = set(ex.upper() for ex in exchanges)
        result = [a for a in result if a.get("exchange", "").upper() in target]

    return result


async def _get_alpaca_fallback_sp500() -> List[Dict]:
    """Alpaca 실패 시 S&P 500을 Alpaca 형식으로 변환"""
    sp500 = await get_sp500_list()
    return [
        {
            "symbol": s["symbol"],
            "name": s["name"],
            "exchange": "NYSE/NASDAQ",
            "tradable": True,
            "fractionable": False,
            "shortable": False,
            "easy_to_borrow": False,
            "marginable": False,
            "sector": s.get("sector", ""),
            "sector_en": s.get("sector_en", ""),
        }
        for s in sp500
    ]


# ========== 가격 데이터 (DB에서 읽기) ==========

def _get_prices_from_db_sync(symbols: List[str]) -> Dict[str, Dict]:
    """
    DB에서 가격 데이터 읽기 (동기).
    스케줄러가 5분마다 yfinance → DB 업데이트.
    """
    from app.db import engine
    from sqlalchemy import text

    result = {}
    try:
        with engine.connect() as conn:
            # IN 절로 일괄 조회
            placeholders = ", ".join([f":s{i}" for i in range(len(symbols))])
            params = {f"s{i}": sym for i, sym in enumerate(symbols)}

            query = text(f"""
                SELECT symbol, price, prev_close, change_pct, market_cap, volume
                FROM us_price_cache
                WHERE symbol IN ({placeholders})
            """)

            rows = conn.execute(query, params).fetchall()

            for row in rows:
                symbol, price, prev_close, change_pct, market_cap, volume = row
                result[symbol] = {
                    "price": round(float(price or 0), 2),
                    "prev_close": round(float(prev_close or 0), 2),
                    "change_pct": round(float(change_pct or 0), 2),
                    "market_cap": market_cap or 0,
                    "market_cap_t": round((market_cap or 0) / 1e12, 3),  # 조 달러
                    "volume": volume or 0,
                }
    except Exception as e:
        print(f"[US] DB 가격 조회 실패: {e}")

    return result


async def get_us_prices(symbols: List[str], force_refresh: bool = False) -> Dict[str, Dict]:
    """
    US 종목 가격 조회 - DB에서 읽기 (yfinance 직접 호출 X).
    스케줄러가 5분마다 DB 업데이트.
    """
    global _price_cache
    now = _time.time()

    # 메모리 캐시 확인 (30초 TTL - DB 부하 줄이기)
    if not force_refresh and _price_cache["data"] and (now - _price_cache["ts"]) < 30:
        return _price_cache["data"]

    loop = asyncio.get_event_loop()
    prices = await loop.run_in_executor(_executor, _get_prices_from_db_sync, symbols)

    if prices:
        _price_cache = {"data": prices, "ts": now}
        print(f"[US] DB 가격 로드: {len(prices)}개 종목")

    return prices


# ========== 메인 스크리너 함수 ==========

async def load_us_stocks() -> List[Dict]:
    """US 종목 목록 + 가격 — 메모리 캐시 우선 (서버 워밍업용)"""
    global _us_stock_cache, _us_cache_ts
    now = _time.time()

    if _us_stock_cache and now - _us_cache_ts < _US_CACHE_TTL:
        return [s.copy() for s in _us_stock_cache]

    # 캐시 만료 → 새로 로드
    stocks = await fetch_all_us_stocks()
    _us_stock_cache = stocks
    _us_cache_ts = now
    return [s.copy() for s in stocks]


async def fetch_all_us_stocks() -> List[Dict]:
    """
    미국 전체 종목 데이터 조합
    1. Alpaca API → 8,000개+ 종목 (우선)
    2. S&P 500 CSV → fallback (Alpaca 실패 시)
    3. DB → 가격, 변동률, 시가총액
    """
    # 1. Alpaca에서 전체 종목 가져오기 (우선)
    alpaca_assets = await get_alpaca_assets(tradable_only=True)

    if alpaca_assets and len(alpaca_assets) > 500:
        # Alpaca 성공 - 전체 종목 사용
        stock_list = alpaca_assets
        source = "Alpaca"
        print(f"[US Screener] Alpaca에서 {len(stock_list)}개 종목 로드")
    else:
        # Alpaca 실패 - S&P 500 fallback
        sp500_list = await get_sp500_list()
        if not sp500_list:
            print("[US Screener] S&P 500 목록 로드 실패")
            return []
        stock_list = [
            {
                "symbol": s["symbol"],
                "name": s["name"],
                "exchange": "NYSE/NASDAQ",
                "sector": s.get("sector", ""),
                "sector_en": s.get("sector_en", ""),
                "sub_industry": s.get("sub_industry", ""),
            }
            for s in sp500_list
        ]
        source = "S&P500 CSV"
        print(f"[US Screener] S&P 500 fallback 사용: {len(stock_list)}개")

    # 2. 심볼 목록 추출
    symbols = [s["symbol"] for s in stock_list]

    # 3. 가격 데이터 가져오기 (DB에서)
    prices = await get_us_prices(symbols)

    # 4. 결합
    stocks = []
    for item in stock_list:
        sym = item["symbol"]
        price_info = prices.get(sym, {})

        stock = {
            "code": sym,
            "name": item.get("name", sym),
            "sector": item.get("sector", ""),
            "sector_en": item.get("sector_en", ""),
            "sub_industry": item.get("sub_industry", ""),
            "price": price_info.get("price", 0),
            "prev_close": price_info.get("prev_close", 0),
            "change_pct": price_info.get("change_pct", 0),
            "market_cap": price_info.get("market_cap_t", 0),  # 조 달러 단위
            "market_cap_raw": price_info.get("market_cap", 0),  # 원본 (달러)
            "volume": 0,
            "exchange": item.get("exchange", "NYSE/NASDAQ"),
        }
        stocks.append(stock)

    # 가격 있는 종목 수 카운트
    with_price = sum(1 for s in stocks if s["price"] > 0)
    print(f"[US Screener] {len(stocks)}개 종목 로드 완료 ({source}, 가격 있음: {with_price}개)")

    return stocks


async def screener_us(filters: dict, sort: str, order: str, page: int, per_page: int) -> dict:
    """
    미국 주식 스크리너 - GitHub CSV + yfinance 기반

    [흐름]
    1. S&P 500 종목 목록 가져오기 (메모리 캐시)
    2. 필터 적용 (섹터, 시총, 등락률)
    3. 정렬 + 페이지네이션
    """
    t0 = _time.time()

    # 메모리 캐시에서 S&P 500 전종목 데이터 가져오기
    all_stocks = await load_us_stocks()
    t1 = _time.time()
    print(f"[PERF] US 종목로드: {t1-t0:.2f}초, {len(all_stocks)}개")

    if not all_stocks:
        return {"items": [], "total": 0, "page": page, "per_page": per_page, "message": "데이터를 불러올 수 없습니다"}

    # 필터 적용
    filtered = apply_us_filters(all_stocks, filters)
    t2 = _time.time()
    print(f"[PERF] US 필터: {t2-t1:.2f}초, {len(filtered)}개")

    # 정렬
    filtered = sort_screener_results(filtered, sort, order)

    total = len(filtered)

    # 페이지네이션
    start = (page - 1) * per_page
    end = start + per_page
    items = filtered[start:end]

    t3 = _time.time()
    print(f"[PERF] US 전체: {t3-t0:.2f}초")

    # 시총 문자열 추가 (달러 기준)
    for item in items:
        cap = item.get("market_cap", 0)  # 조 달러 단위
        if cap >= 1:
            item["market_cap_str"] = f"${cap:.1f}T"
        elif cap >= 0.001:
            item["market_cap_str"] = f"${cap * 1000:.0f}B"
        else:
            item["market_cap_str"] = "-"

    return {
        "items": items,
        "total": total,
        "page": page,
        "per_page": per_page,
        "filters_applied": list(filters.keys()),
    }


def apply_us_filters(stocks: List[Dict], filters: dict) -> List[Dict]:
    """US 전용 필터 적용"""
    result = stocks

    # 섹터 필터
    if filters.get("sector"):
        sector = filters["sector"]
        if isinstance(sector, dict):
            sector = sector.get("value", sector)
        result = [s for s in result if s.get("sector") == sector]

    # 시총 필터 (프론트: B$단위, 데이터: 조달러단위)
    if filters.get("market_cap"):
        mc_filter = filters["market_cap"]
        if isinstance(mc_filter, dict):
            min_val = mc_filter.get("min")
            max_val = mc_filter.get("max")
            # B$ → T$ 변환 (200B = 0.2T)
            if min_val is not None:
                min_trillion = min_val / 1000
                result = [s for s in result if s.get("market_cap", 0) >= min_trillion]
            if max_val is not None:
                max_trillion = max_val / 1000
                result = [s for s in result if s.get("market_cap", 0) <= max_trillion]

    # 등락률 필터
    if filters.get("change_pct"):
        cp_filter = filters["change_pct"]
        if isinstance(cp_filter, dict):
            min_val = cp_filter.get("min")
            max_val = cp_filter.get("max")
            if min_val is not None:
                result = [s for s in result if (s.get("change_pct") or 0) >= min_val]
            if max_val is not None:
                result = [s for s in result if (s.get("change_pct") or 0) <= max_val]

    # 재무 필터 (공통 로직 사용) - yfinance에서는 재무데이터 미제공
    # 향후 필요시 별도 API로 확장 가능

    return result


# ========== 히트맵 데이터 ==========

async def get_us_heatmap() -> Dict[str, Any]:
    """
    US 섹터별 히트맵 데이터 생성 (S&P500 전용)
    Returns: {"sectors": [...], "stocks": [...]}
    """
    # 히트맵은 S&P500만 사용 (시각화 성능)
    sp500_list = await get_sp500_list()
    if sp500_list:
        # S&P500 목록에서 가격 데이터 가져오기
        symbols = [s["symbol"] for s in sp500_list]
        prices = await get_us_prices(symbols)
        stocks = []
        for item in sp500_list:
            sym = item["symbol"]
            price_info = prices.get(sym, {})
            stocks.append({
                "code": sym,
                "name": item.get("name", sym),
                "sector": item.get("sector", ""),
                "price": price_info.get("price", 0),
                "change_pct": price_info.get("change_pct", 0),
                "market_cap": price_info.get("market_cap_t", 0),
                "market_cap_raw": price_info.get("market_cap", 0),
            })
    else:
        # Fallback: 전체 종목
        stocks = await load_us_stocks()

    if not stocks:
        return {"sectors": [], "stocks": []}

    # 섹터별 그룹핑
    sector_data = {}
    stock_list = []

    for stock in stocks:
        sector = stock.get("sector", "기타")
        if sector not in sector_data:
            sector_data[sector] = {
                "name": sector,
                "stocks": [],
                "total_market_cap": 0,
                "weighted_change": 0,
            }

        market_cap_raw = stock.get("market_cap_raw", 0)
        change_pct = stock.get("change_pct", 0)

        item = {
            "symbol": stock["code"],
            "name": stock["name"],
            "sector": sector,
            "price": stock.get("price", 0),
            "change_pct": change_pct,
            "market_cap": stock.get("market_cap", 0),  # 조 달러
        }

        sector_data[sector]["stocks"].append(item)
        sector_data[sector]["total_market_cap"] += market_cap_raw
        sector_data[sector]["weighted_change"] += change_pct * market_cap_raw
        stock_list.append(item)

    # 섹터 평균 변동률 (시가총액 가중)
    sectors = []
    for sec in sector_data.values():
        if sec["total_market_cap"] > 0:
            sec["change_pct"] = round(sec["weighted_change"] / sec["total_market_cap"], 2)
        else:
            sec["change_pct"] = 0
        del sec["weighted_change"]
        sec["stock_count"] = len(sec["stocks"])
        # 개별 종목 리스트 제거 (응답 크기 줄임)
        del sec["stocks"]
        sec["total_market_cap"] = round(sec["total_market_cap"] / 1e12, 2)  # 조 달러
        sectors.append(sec)

    sectors.sort(key=lambda x: x["change_pct"], reverse=True)

    return {
        "sectors": sectors,
        "stocks": stock_list,
    }


# ========== 워밍업 함수 ==========

async def warmup_us_screener():
    """서버 시작 시 US 스크리너 캐시 채움"""
    print("[US Screener] 워밍업 시작...")
    try:
        stocks = await fetch_all_us_stocks()
        if stocks:
            global _us_stock_cache, _us_cache_ts
            _us_stock_cache = stocks
            _us_cache_ts = _time.time()
            print(f"[US Screener] 워밍업 완료: {len(stocks)}개 종목")
        else:
            print("[US Screener] 워밍업 실패: 데이터 없음")
    except Exception as e:
        print(f"[US Screener] 워밍업 오류: {e}")


# ========== 필터 키 정의 ==========

US_FILTER_KEYS = [
    "sector", "market_cap", "change_pct",
]

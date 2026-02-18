"""
국내 주식 스크리너 (KOSPI/KOSDAQ)
네이버 금융 API 기반
"""

import asyncio
import httpx
from typing import List, Dict, Any

from .cache import screener_cache, CACHE_TTL
from .filters import apply_screener_filters, sort_screener_results


def _parse_float(val) -> float:
    """문자열을 float로 변환"""
    if val is None:
        return None
    if isinstance(val, (int, float)):
        return float(val)
    try:
        cleaned = str(val).replace(",", "").replace(" ", "").strip()
        if not cleaned or cleaned == "-":
            return None
        return float(cleaned)
    except (ValueError, TypeError):
        return None


def _parse_price(val) -> int:
    """문자열을 int 가격으로 변환"""
    if val is None:
        return 0
    if isinstance(val, (int, float)):
        return int(val)
    try:
        cleaned = str(val).replace(",", "").replace(" ", "").strip()
        if not cleaned or cleaned == "-":
            return 0
        return int(float(cleaned))
    except (ValueError, TypeError):
        return 0


async def screener_kr(filters: dict, sort: str, order: str, page: int, per_page: int) -> dict:
    """
    국내 주식 스크리너 — 네이버 금융 기반 (2단계 필터링)

    filters 예시:
    {
        "exchange": "KOSPI",       # 전체/KOSPI/KOSDAQ
        "sector": "반도체",         # 전체/업종명
        "market_cap": "large",     # 전체/mega/large/mid/small/micro
        "price_min": 10000,        # 현재가 최소
        "price_max": 100000,       # 현재가 최대
        "volume_min": 100000       # 최소 거래량
    }
    """
    # 캐시에서 전종목 데이터 가져오기
    all_stocks = await screener_cache.get_or_fetch(
        key="kr_all_stocks",
        ttl_seconds=CACHE_TTL["kr_all_stocks"],
        fetch_fn=fetch_all_kr_stocks
    )

    if not all_stocks:
        return {"items": [], "total": 0, "page": page, "per_page": per_page}

    # === 1단계: 기본 필터 적용 (빠름) ===
    basic_filters = {k: v for k, v in filters.items()
                     if k in ["exchange", "sector", "market_cap", "price_min", "price_max", "volume_min"]}
    filtered = apply_screener_filters(all_stocks, basic_filters)

    # === 2단계: 재무/기술 필터가 있으면 데이터 보강 후 필터 적용 ===
    financial_filter_keys = ["per", "pbr", "roe", "operating_margin", "debt_ratio", "dividend_yield",
                             "change_filter", "w52_high", "volume_surge", "sma20", "sma60", "sma120"]
    has_financial_filters = any(filters.get(k) for k in financial_filter_keys)

    # 재무 필터가 있으면 상위 500개 보강 후 필터 적용
    if has_financial_filters:
        stocks_to_enrich = filtered[:500]
        enriched = await enrich_financial_data(stocks_to_enrich)
        filtered = enriched + filtered[500:]

    # 재무/기술 필터 적용
    advanced_filters = {k: v for k, v in filters.items() if k in financial_filter_keys}
    if advanced_filters:
        filtered = apply_screener_filters(filtered, advanced_filters)

    # 정렬
    filtered = sort_screener_results(filtered, sort, order)

    total = len(filtered)

    # 페이지네이션
    start = (page - 1) * per_page
    end = start + per_page
    items = filtered[start:end]

    # 페이지 결과에 대해 재무 데이터 보강 (항상)
    items = await enrich_financial_data(list(items))

    # 시총 문자열 추가
    for item in items:
        cap = item.get("market_cap", 0)
        if cap >= 10_000_000_000_000:  # 10조 이상
            item["market_cap_str"] = f"{cap / 1_000_000_000_000:.1f}조"
        elif cap >= 100_000_000:  # 1억 이상
            item["market_cap_str"] = f"{int(cap / 100_000_000)}억"
        else:
            item["market_cap_str"] = "-"

    return {
        "items": items,
        "total": total,
        "page": page,
        "per_page": per_page,
        "filters_applied": list(filters.keys()),
    }


async def fetch_all_kr_stocks() -> List[Dict]:
    """네이버 금융에서 KOSPI/KOSDAQ 전종목 시세 가져오기"""
    all_stocks = []

    # KOSPI
    kospi_stocks = await fetch_naver_market_stocks("KOSPI")
    all_stocks.extend(kospi_stocks)

    # KOSDAQ
    kosdaq_stocks = await fetch_naver_market_stocks("KOSDAQ")
    all_stocks.extend(kosdaq_stocks)

    print(f"[Screener] Fetched {len(all_stocks)} stocks (KOSPI: {len(kospi_stocks)}, KOSDAQ: {len(kosdaq_stocks)})")
    return all_stocks


async def fetch_naver_market_stocks(market: str) -> List[Dict]:
    """네이버 모바일 API로 특정 시장 전종목 가져오기 (JSON API)"""
    stocks = []
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Referer": "https://m.stock.naver.com/"
    }

    try:
        async with httpx.AsyncClient(timeout=30, headers=headers) as client:
            page = 1
            page_size = 100

            while True:
                # 네이버 모바일 시총순 API
                url = f"https://m.stock.naver.com/api/stocks/marketValue/{market}?page={page}&pageSize={page_size}"
                resp = await client.get(url)

                if resp.status_code != 200:
                    print(f"[Screener] API error {resp.status_code} for {market} page {page}")
                    break

                data = resp.json()
                items = data.get("stocks", [])

                if not items:
                    break

                for item in items:
                    # ETF, ETN, 스팩 등 제외 (일반 주식만)
                    stock_end_type = item.get("stockEndType", "")
                    if stock_end_type != "stock":
                        continue

                    # 종목명으로 추가 필터링 (ETF 브랜드명)
                    stock_name = item.get("stockName", "")
                    etf_keywords = ["TIGER", "KODEX", "ARIRANG", "KBSTAR", "HANARO", "SOL", "ACE",
                                    "ETF", "ETN", "스팩", "리츠", "인프라"]
                    if any(kw in stock_name for kw in etf_keywords):
                        continue

                    # 가격 파싱 (콤마 제거, "-"는 0으로)
                    close_price = item.get("closePrice", "0")
                    if isinstance(close_price, str):
                        close_price = close_price.replace(",", "").replace("-", "").strip()
                        close_price = int(close_price) if close_price.isdigit() else 0

                    # 등락률 파싱
                    change_pct = item.get("fluctuationsRatio", "0")
                    if isinstance(change_pct, str):
                        try:
                            # "-" 문자는 음수가 아니라 데이터 없음을 의미
                            if change_pct.strip() == "-":
                                change_pct = 0.0
                            else:
                                change_pct = float(change_pct.replace(",", "") or 0)
                        except:
                            change_pct = 0

                    # 거래량 파싱 ("-"는 0으로)
                    volume = item.get("accumulatedTradingVolume", "0")
                    if isinstance(volume, str):
                        volume = volume.replace(",", "").replace("-", "").strip()
                        volume = int(volume) if volume.isdigit() else 0

                    # 시가총액 파싱 (억 단위)
                    market_value = item.get("marketValue", "0")
                    if isinstance(market_value, str):
                        market_value = market_value.replace(",", "").replace("-", "").strip()
                        market_value = int(market_value) * 100_000_000 if market_value.isdigit() else 0

                    stock = {
                        "code": item.get("itemCode", ""),
                        "name": item.get("stockName", ""),
                        "exchange": market,
                        "price": close_price,
                        "change_pct": change_pct,
                        "volume": volume,
                        "market_cap": market_value,
                        "per": None,
                        "pbr": None,
                        "roe": None,
                        "dividend_yield": None,
                        "w52_high_pct": None,
                    }
                    stocks.append(stock)

                # 다음 페이지 확인
                total_count = data.get("totalCount", 0)
                if page * page_size >= total_count:
                    break

                page += 1
                if page > 30:  # 최대 30페이지 (3000종목)
                    break

    except Exception as e:
        print(f"[Screener] Error fetching {market}: {e}")
        import traceback
        traceback.print_exc()

    print(f"[Screener] Fetched {len(stocks)} stocks from {market}")
    return stocks


async def enrich_financial_data(stocks: List[Dict]) -> List[Dict]:
    """
    재무 데이터 보강 (PER, PBR, ROE, 배당수익률, 52주고가 등)
    네이버 integration API 사용
    """
    if not stocks:
        return stocks

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
    }

    async def fetch_single(client, stock, semaphore):
        """단일 종목 재무 데이터 조회"""
        code = stock.get("code")
        if not code:
            return stock

        async with semaphore:
            try:
                url = f"https://m.stock.naver.com/api/stock/{code}/integration"
                resp = await client.get(url, timeout=10)
                if resp.status_code != 200:
                    return stock

                data = resp.json()
                total_infos = data.get("totalInfos", [])

                for info in total_infos:
                    key = info.get("code", "")
                    value = info.get("value", "")

                    if key == "per":
                        stock["per"] = _parse_float(value.replace("배", ""))
                    elif key == "pbr":
                        stock["pbr"] = _parse_float(value.replace("배", ""))
                    elif key == "dividendYieldRatio":
                        stock["dividend_yield"] = _parse_float(value.replace("%", ""))
                    elif key == "highPriceOf52Weeks":
                        high_52w = _parse_price(value)
                        stock["high_52w"] = high_52w
                        # 52주 고가 대비 현재가 거리 계산 (비율)
                        if high_52w > 0 and stock.get("price", 0) > 0:
                            stock["w52_high_pct"] = (high_52w - stock["price"]) / high_52w
                        else:
                            stock["w52_high_pct"] = None
                    elif key == "lowPriceOf52Weeks":
                        stock["low_52w"] = _parse_price(value)

            except Exception as e:
                # 개별 종목 에러는 무시하고 계속 진행
                pass

            return stock

    # 동시 요청 수 제한 (10개씩)
    semaphore = asyncio.Semaphore(10)

    async with httpx.AsyncClient(headers=headers) as client:
        tasks = [fetch_single(client, dict(s), semaphore) for s in stocks]
        enriched = await asyncio.gather(*tasks, return_exceptions=True)

    # 예외 발생한 항목은 원본 유지
    result = []
    for i, r in enumerate(enriched):
        if isinstance(r, Exception):
            result.append(stocks[i])
        else:
            result.append(r)

    print(f"[Screener] Enriched {len(result)} stocks with financial data")
    return result

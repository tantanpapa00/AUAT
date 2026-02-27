"""
국내 주식 스크리너 (KOSPI/KOSDAQ)
네이버 금융 API 기반 + 기술적 지표 계산
"""

import asyncio
import httpx
from typing import List, Dict, Any
from datetime import datetime, timedelta

from .cache import screener_cache, CACHE_TTL
from .filters import apply_screener_filters, sort_screener_results
from .technicals import compute_all_technicals

# 재무 데이터 메모리 캐시 (서버 시작 시 수집, 1시간마다 갱신)
# code -> {"per": float, "pbr": float, "roe": float, "dividend_yield": float}
_financial_cache: Dict[str, Dict[str, float]] = {}
_financial_cache_ts: datetime = None

# ROE 캐시 (레거시 호환)
_roe_cache: Dict[str, float] = {}
_roe_cache_ts: datetime = None

# 기술적 지표 필터 키 목록
TECHNICAL_FILTER_KEYS = [
    "rsi", "sma20", "sma50", "sma200", "sma_cross",
    "bollinger", "macd", "stochastic", "atr",
    "volume_surge", "w52_high", "w52_low",
    "period_return"
]

# 재무 지표 필터 키 목록 (네이버 integration API 기반)
FINANCIAL_FILTER_KEYS = [
    "per", "pbr", "roe", "roa",
    "operating_margin", "profit_margin",
    "debt_ratio", "current_ratio", "dividend_yield",
    "revenue_growth", "earnings_growth", "eps_growth",
    "foreign_ratio", "change_filter", "change"
]


def extract_technical_params(filters: dict) -> dict:
    """
    필터에서 기술적 지표 파라미터 추출

    V2 필터 포맷: {"rsi": {"min": 70, "params": {"period": 7}}}
    반환: {"rsi": {"period": 7}, "macd": {"fast": 12, "slow": 26, "signal": 9}}
    """
    params = {}

    # RSI 파라미터
    if isinstance(filters.get("rsi"), dict):
        rsi_params = filters["rsi"].get("params", {})
        if rsi_params:
            params["rsi"] = rsi_params

    # MACD 파라미터
    if isinstance(filters.get("macd"), dict):
        macd_params = filters["macd"].get("params", {})
        if macd_params:
            params["macd"] = macd_params

    # 볼린저 파라미터
    if isinstance(filters.get("bollinger"), dict):
        bb_params = filters["bollinger"].get("params", {})
        if bb_params:
            params["bollinger"] = bb_params

    # 스토캐스틱 파라미터
    if isinstance(filters.get("stochastic"), dict):
        stoch_params = filters["stochastic"].get("params", {})
        if stoch_params:
            params["stochastic"] = stoch_params

    # ATR 파라미터
    if isinstance(filters.get("atr"), dict):
        atr_params = filters["atr"].get("params", {})
        if atr_params:
            params["atr"] = atr_params

    # 동적 이동평균선 (sma_SMA_20, sma_EMA_7 등)
    sma_list = []
    for key, value in filters.items():
        if key.startswith("sma_") and "_" in key[4:]:
            # 예: sma_SMA_20 → type=SMA, period=20
            parts = key.split("_")
            if len(parts) >= 3:
                ma_type = parts[1]
                try:
                    period = int(parts[2])
                    sma_list.append({"type": ma_type, "period": period})
                except ValueError:
                    pass
    if sma_list:
        params["sma"] = sma_list

    return params


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


import time as _time

# 모듈 레벨 메모리 캐시 (서버 시작 시 워밍업)
_kr_stock_cache = None
_kr_cache_ts = 0
_KR_CACHE_TTL = 3600  # 1시간


async def load_kr_stocks():
    """KR 종목 목록 — 메모리 캐시 우선 (서버 워밍업용)"""
    global _kr_stock_cache, _kr_cache_ts
    now = _time.time()

    if _kr_stock_cache and now - _kr_cache_ts < _KR_CACHE_TTL:
        return [s.copy() for s in _kr_stock_cache]  # 복사본 반환

    # 캐시 만료 → 네이버에서 새로 로드
    stocks = await fetch_all_kr_stocks()
    _kr_stock_cache = stocks
    _kr_cache_ts = now
    return [s.copy() for s in stocks]


async def screener_kr(filters: dict, sort: str, order: str, page: int, per_page: int) -> dict:
    """
    국내 주식 스크리너 — 네이버 금융 기반 + 기술적 지표

    [흐름]
    1. 전종목 기본 시세 (메모리 캐시 — 5분)
    2. 기본정보 필터 적용 (거래소, 업종, 시총, 현재가, 거래량)
    3. 재무 데이터 보강 (PER, PBR, 배당수익률, 52주고가)
    4. 재무 필터 적용
    5. 기술적 지표 보강 (RSI, SMA, 볼린저, MACD 등) - 상위 200건
    6. 기술적 필터 적용
    7. 정렬 + 페이지네이션
    """
    t0 = _time.time()

    # 메모리 캐시에서 전종목 데이터 가져오기 (서버 워밍업 후 즉시 반환)
    all_stocks = await load_kr_stocks()
    t1 = _time.time()
    print(f"[PERF] KR 종목로드: {t1-t0:.2f}초, {len(all_stocks)}개")

    if not all_stocks:
        return {"items": [], "total": 0, "page": page, "per_page": per_page}

    # === 1단계: 기본 필터 적용 (빠름) ===
    basic_filter_keys = ["exchange", "sector", "market_cap", "price_min", "price_max", "volume_min"]
    basic_filters = {k: v for k, v in filters.items() if k in basic_filter_keys}
    filtered = apply_screener_filters(all_stocks, basic_filters)
    t2 = _time.time()
    print(f"[PERF] KR 기본필터: {t2-t1:.2f}초, {len(filtered)}개")

    # === 2단계: 재무 데이터 보강 + 필터 ===
    has_financial_filters = any(filters.get(k) for k in FINANCIAL_FILTER_KEYS)
    if has_financial_filters:
        stocks_to_enrich = filtered[:500]
        enriched = await enrich_financial_data(stocks_to_enrich)
        filtered = enriched + filtered[500:]

    # 재무 필터 적용
    financial_filters = {k: v for k, v in filters.items() if k in FINANCIAL_FILTER_KEYS}
    if financial_filters:
        filtered = apply_screener_filters(filtered, financial_filters)
    t3 = _time.time()
    print(f"[PERF] KR 재무보강: {t3-t2:.2f}초")

    # === 3단계: 기술적 지표 보강 + 필터 (상위 200건) ===
    has_technical_filters = any(filters.get(k) for k in TECHNICAL_FILTER_KEYS)
    # 동적 SMA 필터도 확인
    has_dynamic_sma = any(k.startswith("sma_") and "_" in k[4:] for k in filters.keys())
    technical_sort_keys = ["rsi", "sma20", "sma50", "sma200", "volume_surge", "atr"]
    needs_technicals = has_technical_filters or has_dynamic_sma or sort in technical_sort_keys

    # 기술적 지표 파라미터 추출
    technical_params = extract_technical_params(filters)

    if needs_technicals:
        stocks_to_enrich = filtered[:200]
        enriched = await enrich_with_technicals(stocks_to_enrich, technical_params)
        filtered = enriched + filtered[200:]

    # 기술적 필터 적용
    technical_filters = {k: v for k, v in filters.items() if k in TECHNICAL_FILTER_KEYS}
    if technical_filters:
        filtered = apply_screener_filters(filtered, technical_filters)

    # 정렬
    filtered = sort_screener_results(filtered, sort, order)

    total = len(filtered)

    # 페이지네이션
    start = (page - 1) * per_page
    end = start + per_page
    items = filtered[start:end]
    t4 = _time.time()
    print(f"[PERF] KR 기술+정렬: {t4-t3:.2f}초")

    # 페이지 결과에 대해 재무 + 기술 데이터 보강 (항상)
    items = await enrich_financial_data(list(items))
    items = await enrich_with_technicals(items, technical_params)
    t5 = _time.time()
    print(f"[PERF] KR 페이지보강: {t5-t4:.2f}초")
    print(f"[PERF] KR 전체: {t5-t0:.2f}초")

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
                    elif key == "eps":
                        stock["eps"] = _parse_float(value.replace("원", "").replace(",", ""))
                    elif key == "cnsEps":
                        # 컨센서스 EPS (애널리스트 추정치)
                        stock["cns_eps"] = _parse_float(value.replace("원", "").replace(",", ""))
                    elif key == "bps":
                        stock["bps"] = _parse_float(value.replace("원", "").replace(",", ""))
                    elif key == "roe":
                        stock["roe"] = _parse_float(value.replace("%", ""))
                    elif key == "roa":
                        stock["roa"] = _parse_float(value.replace("%", ""))
                    elif key == "dividendYieldRatio":
                        stock["dividend_yield"] = _parse_float(value.replace("%", ""))
                    elif key == "foreignRatio":
                        stock["foreign_ratio"] = _parse_float(value.replace("%", ""))
                    elif key == "debtRatio":
                        stock["debt_ratio"] = _parse_float(value.replace("%", ""))
                    elif key == "currentRatio":
                        stock["current_ratio"] = _parse_float(value.replace("%", ""))
                    elif key == "operatingMargin":
                        stock["operating_margin"] = _parse_float(value.replace("%", ""))
                    elif key == "netMargin":
                        stock["profit_margin"] = _parse_float(value.replace("%", ""))
                    elif key == "salesGrowth":
                        stock["revenue_growth"] = _parse_float(value.replace("%", ""))
                    elif key == "operatingProfitGrowth":
                        stock["earnings_growth"] = _parse_float(value.replace("%", ""))
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

                # EPS 성장률 계산 (컨센서스 기반)
                # eps_growth = (cnsEps - eps) / abs(eps) * 100
                eps = stock.get("eps")
                cns_eps = stock.get("cns_eps")
                if eps and cns_eps and eps != 0:
                    stock["eps_growth"] = round((cns_eps - eps) / abs(eps) * 100, 2)

                # ROE가 없으면 캐시에서 조회
                if not stock.get("roe") and code in _roe_cache:
                    stock["roe"] = _roe_cache[code]

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

    print(f"[Screener] Enriched {len(result)} stocks with financial data (Naver)")
    return result


async def warmup_roe_cache(stocks: List[Dict] = None) -> None:
    """
    재무 데이터 캐시 초기화 (서버 시작 시 호출)
    상위 500개 종목의 PER/PBR/ROE/배당수익률을 네이버 API에서 수집
    """
    global _roe_cache, _roe_cache_ts, _financial_cache, _financial_cache_ts

    print("[Financial Cache] 캐시 초기화 시작...")

    if stocks is None:
        stocks = await load_kr_stocks()

    # 상위 500개 종목만
    target_stocks = stocks[:500]

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
    }

    async def fetch_financial(client, code, semaphore):
        """단일 종목 재무 데이터 조회 (네이버 모바일 integration API)"""
        async with semaphore:
            result = {"per": None, "pbr": None, "roe": None, "dividend_yield": None}
            try:
                url = f"https://m.stock.naver.com/api/stock/{code}/integration"
                r = await client.get(url, timeout=10)
                if r.status_code == 200:
                    data = r.json()
                    total_infos = data.get("totalInfos", [])
                    for info in total_infos:
                        key = info.get("code", "")
                        value = info.get("value", "")
                        if key == "per":
                            result["per"] = _parse_float(value.replace("배", ""))
                        elif key == "pbr":
                            result["pbr"] = _parse_float(value.replace("배", ""))
                        elif key == "roe":
                            result["roe"] = _parse_float(value.replace("%", ""))
                        elif key == "dividendYieldRatio":
                            result["dividend_yield"] = _parse_float(value.replace("%", ""))
            except Exception:
                pass
            return code, result

    semaphore = asyncio.Semaphore(20)  # 동시 20개 요청

    async with httpx.AsyncClient(headers=headers, timeout=15) as client:
        tasks = [fetch_financial(client, s.get("code"), semaphore) for s in target_stocks if s.get("code")]
        results = await asyncio.gather(*tasks, return_exceptions=True)

    # 캐시 업데이트
    count = 0
    roe_count = 0
    for r in results:
        if isinstance(r, tuple):
            code, data = r
            if any(v is not None for v in data.values()):
                _financial_cache[code] = data
                count += 1
            # ROE 캐시도 업데이트 (레거시 호환)
            if data.get("roe") is not None:
                _roe_cache[code] = data["roe"]
                roe_count += 1

    _financial_cache_ts = datetime.now()
    _roe_cache_ts = datetime.now()
    print(f"[Financial Cache] 완료: {count}개 종목 재무데이터 수집 (ROE: {roe_count}개)")


def apply_cached_roe(stocks: List[Dict]) -> List[Dict]:
    """
    캐시된 ROE 데이터만 적용 (레거시 호환)
    """
    return apply_cached_financial(stocks)


def apply_cached_financial(stocks: List[Dict]) -> List[Dict]:
    """
    캐시된 재무 데이터 적용 (네트워크 호출 없음, 즉시 반환)
    AI 종목추천 등 빠른 응답이 필요한 곳에서 사용
    PER, PBR, ROE, dividend_yield 적용
    """
    global _financial_cache, _roe_cache

    result = []
    for stock in stocks:
        s = dict(stock)
        code = s.get("code", "")

        # 재무 캐시에서 데이터 적용
        if code in _financial_cache:
            cached = _financial_cache[code]
            if not s.get("per") and cached.get("per") is not None:
                s["per"] = cached["per"]
            if not s.get("pbr") and cached.get("pbr") is not None:
                s["pbr"] = cached["pbr"]
            if not s.get("roe") and cached.get("roe") is not None:
                s["roe"] = cached["roe"]
            if not s.get("dividend_yield") and cached.get("dividend_yield") is not None:
                s["dividend_yield"] = cached["dividend_yield"]

        # ROE 캐시에서 보충 (레거시 호환)
        if not s.get("roe") and code in _roe_cache:
            s["roe"] = _roe_cache[code]

        result.append(s)

    return result


async def enrich_with_technicals(stocks: List[Dict], params: Dict = None) -> List[Dict]:
    """
    기술적 지표 보강 (RSI, SMA, 볼린저, MACD, 스토캐스틱, ATR 등)
    네이버 일봉 API 기반 + 동적 파라미터 지원

    params: 기술적 지표 파라미터
    {
        "rsi": {"period": 7},
        "macd": {"fast": 12, "slow": 26, "signal": 9},
        "sma": [{"type": "SMA", "period": 20}, {"type": "EMA", "period": 7}]
    }
    """
    if not stocks:
        return stocks

    params = params or {}
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
    }

    # 파라미터 해시 (캐시 키용)
    import hashlib
    import json
    params_hash = hashlib.md5(json.dumps(params, sort_keys=True).encode()).hexdigest()[:8] if params else ""

    async def fetch_and_compute(client, stock, semaphore):
        """단일 종목 기술적 지표 계산"""
        code = stock.get("code")
        if not code:
            return stock

        # 캐시 확인 (파라미터별 캐시, 24시간)
        cache_key = f"technicals_{code}_{params_hash}" if params_hash else f"technicals_{code}"
        cached = screener_cache.get(cache_key)
        if cached:
            stock.update(cached)
            return stock

        async with semaphore:
            try:
                # 네이버 일봉 API (최근 1년)
                end_date = datetime.now().strftime("%Y%m%d")
                start_date = (datetime.now() - timedelta(days=365)).strftime("%Y%m%d")
                url = f"https://api.stock.naver.com/chart/domestic/item/{code}/day?startDateTime={start_date}&endDateTime={end_date}"

                resp = await client.get(url, timeout=15)
                if resp.status_code != 200:
                    return stock

                candles = resp.json()
                if not candles or not isinstance(candles, list):
                    return stock

                # 기술적 지표 계산 (동적 파라미터 전달)
                technicals = compute_all_technicals(candles, params)

                if technicals:
                    # 캐시 저장 (24시간)
                    screener_cache.set(cache_key, technicals, 86400)
                    stock.update(technicals)

            except Exception as e:
                # 개별 종목 에러는 무시
                pass

            return stock

    # 동시 요청 수 제한 (5개씩 - 네이버 차트 API 제한)
    semaphore = asyncio.Semaphore(5)

    async with httpx.AsyncClient(headers=headers) as client:
        tasks = [fetch_and_compute(client, dict(s), semaphore) for s in stocks]
        enriched = await asyncio.gather(*tasks, return_exceptions=True)

    # 예외 발생한 항목은 원본 유지
    result = []
    for i, r in enumerate(enriched):
        if isinstance(r, Exception):
            result.append(stocks[i])
        else:
            result.append(r)

    print(f"[Screener] Enriched {len(result)} stocks with technical indicators")
    return result

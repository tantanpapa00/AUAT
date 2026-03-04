"""
해외시장 데이터 수집기 (Yahoo Finance + CNN Fear & Greed + Finviz Breadth)
Phase 5: 국내시장과 동일한 구조의 해외시장 분석
"""
import asyncio
import re
import httpx
from typing import Dict, List, Optional, Any
from datetime import datetime, timezone

# ========== 상수 정의 ==========

# S&P 500 GICS 11개 섹터 ETF
US_SECTOR_ETFS = [
    {"symbol": "XLK", "name": "기술", "name_en": "Technology"},
    {"symbol": "XLF", "name": "금융", "name_en": "Financials"},
    {"symbol": "XLV", "name": "헬스케어", "name_en": "Healthcare"},
    {"symbol": "XLC", "name": "커뮤니케이션", "name_en": "Communication Services"},
    {"symbol": "XLY", "name": "임의소비재", "name_en": "Consumer Discretionary"},
    {"symbol": "XLP", "name": "필수소비재", "name_en": "Consumer Staples"},
    {"symbol": "XLI", "name": "산업재", "name_en": "Industrials"},
    {"symbol": "XLE", "name": "에너지", "name_en": "Energy"},
    {"symbol": "XLU", "name": "유틸리티", "name_en": "Utilities"},
    {"symbol": "XLRE", "name": "부동산", "name_en": "Real Estate"},
    {"symbol": "XLB", "name": "소재", "name_en": "Materials"},
]

# 히트맵용 시가총액 상위 30종목 (market_cap: 조 달러 단위 추정치)
HEATMAP_STOCKS = [
    {"symbol": "AAPL", "name": "Apple", "sector": "기술", "market_cap": 3.5},
    {"symbol": "MSFT", "name": "Microsoft", "sector": "기술", "market_cap": 3.1},
    {"symbol": "NVDA", "name": "NVIDIA", "sector": "기술", "market_cap": 2.0},
    {"symbol": "GOOGL", "name": "Alphabet", "sector": "커뮤니케이션", "market_cap": 1.9},
    {"symbol": "AMZN", "name": "Amazon", "sector": "임의소비재", "market_cap": 1.8},
    {"symbol": "META", "name": "Meta", "sector": "커뮤니케이션", "market_cap": 1.3},
    {"symbol": "TSLA", "name": "Tesla", "sector": "임의소비재", "market_cap": 0.8},
    {"symbol": "BRK-B", "name": "Berkshire", "sector": "금융", "market_cap": 0.9},
    {"symbol": "JPM", "name": "JPMorgan", "sector": "금융", "market_cap": 0.6},
    {"symbol": "V", "name": "Visa", "sector": "금융", "market_cap": 0.5},
    {"symbol": "UNH", "name": "UnitedHealth", "sector": "헬스케어", "market_cap": 0.5},
    {"symbol": "MA", "name": "Mastercard", "sector": "금융", "market_cap": 0.4},
    {"symbol": "HD", "name": "Home Depot", "sector": "임의소비재", "market_cap": 0.4},
    {"symbol": "PG", "name": "P&G", "sector": "필수소비재", "market_cap": 0.4},
    {"symbol": "COST", "name": "Costco", "sector": "필수소비재", "market_cap": 0.4},
    {"symbol": "ABBV", "name": "AbbVie", "sector": "헬스케어", "market_cap": 0.3},
    {"symbol": "CRM", "name": "Salesforce", "sector": "기술", "market_cap": 0.3},
    {"symbol": "AVGO", "name": "Broadcom", "sector": "기술", "market_cap": 0.8},
    {"symbol": "NFLX", "name": "Netflix", "sector": "커뮤니케이션", "market_cap": 0.3},
    {"symbol": "AMD", "name": "AMD", "sector": "기술", "market_cap": 0.3},
    {"symbol": "LLY", "name": "Eli Lilly", "sector": "헬스케어", "market_cap": 0.7},
    {"symbol": "WMT", "name": "Walmart", "sector": "필수소비재", "market_cap": 0.5},
    {"symbol": "XOM", "name": "Exxon", "sector": "에너지", "market_cap": 0.5},
    {"symbol": "CVX", "name": "Chevron", "sector": "에너지", "market_cap": 0.3},
    {"symbol": "BAC", "name": "Bank of America", "sector": "금융", "market_cap": 0.3},
    {"symbol": "ORCL", "name": "Oracle", "sector": "기술", "market_cap": 0.4},
    {"symbol": "KO", "name": "Coca-Cola", "sector": "필수소비재", "market_cap": 0.3},
    {"symbol": "PEP", "name": "PepsiCo", "sector": "필수소비재", "market_cap": 0.2},
    {"symbol": "MRK", "name": "Merck", "sector": "헬스케어", "market_cap": 0.3},
    {"symbol": "DIS", "name": "Disney", "sector": "커뮤니케이션", "market_cap": 0.2},
]

# 지수 심볼 매핑
US_INDICES = {
    "sp500": "^GSPC",
    "nasdaq": "^IXIC",
    "dow": "^DJI",
    "russell": "^RUT",
    "vix": "^VIX",
}

# Fear & Greed 레이블 한글 변환
FG_LABELS = {
    "Extreme Fear": "극심한 공포",
    "Fear": "공포",
    "Neutral": "중립",
    "Greed": "탐욕",
    "Extreme Greed": "극심한 탐욕",
}


YAHOO_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7",
    "Accept-Language": "en-US,en;q=0.9",
    "Accept-Encoding": "gzip, deflate, br",
    "Cache-Control": "max-age=0",
    "Sec-Ch-Ua": '"Chromium";v="122", "Not(A:Brand";v="24", "Google Chrome";v="122"',
    "Sec-Ch-Ua-Mobile": "?0",
    "Sec-Ch-Ua-Platform": '"Windows"',
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "none",
    "Sec-Fetch-User": "?1",
    "Upgrade-Insecure-Requests": "1",
}

# US 시장 데이터 캐시 (5분)
import time as _time
_us_indices_cache: Dict[str, Any] = {"data": {}, "ts": 0}
_us_sectors_cache: Dict[str, Any] = {"data": [], "ts": 0}
_US_CACHE_TTL = 300  # 5분


def _fetch_yfinance_quote(symbol: str) -> Optional[Dict]:
    """yfinance로 종목 시세 조회 (동기)"""
    try:
        import yfinance as yf
        ticker = yf.Ticker(symbol)
        info = ticker.fast_info
        price = getattr(info, 'last_price', 0) or 0
        prev_close = getattr(info, 'previous_close', 0) or getattr(info, 'regularMarketPreviousClose', 0) or 0

        if not price and hasattr(ticker, 'history'):
            hist = ticker.history(period="2d")
            if not hist.empty:
                price = float(hist['Close'].iloc[-1])
                if len(hist) > 1:
                    prev_close = float(hist['Close'].iloc[-2])

        change = price - prev_close if prev_close else 0
        change_pct = (change / prev_close * 100) if prev_close else 0

        return {
            "price": price,
            "prev_close": prev_close,
            "change": round(change, 2),
            "change_pct": round(change_pct, 2),
            "volume": getattr(info, 'last_volume', 0) or 0,
            "name": symbol,
        }
    except Exception as e:
        print(f"[US] yfinance error for {symbol}: {e}")
        return None


async def fetch_yahoo_quote(client: httpx.AsyncClient, symbol: str, retries: int = 2) -> Optional[Dict]:
    """
    Yahoo Finance에서 단일 종목 시세 조회
    1순위: Yahoo Finance API
    2순위: yfinance 라이브러리 fallback
    Returns: {price, prev_close, change, change_pct, volume, name} or None
    """
    for attempt in range(retries + 1):
        try:
            url = f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}?interval=1d&range=2d"
            resp = await client.get(url, headers=YAHOO_HEADERS, timeout=10)
            if resp.status_code == 429:
                # Rate limited - wait and retry
                if attempt < retries:
                    await asyncio.sleep(1 + attempt)
                    continue
            if resp.status_code not in (200, 401):
                print(f"[US] Yahoo API error for {symbol}: {resp.status_code}")
                if attempt < retries:
                    await asyncio.sleep(1)
                    continue

            if resp.status_code == 401:
                # Yahoo API 차단 - yfinance fallback
                print(f"[US] Yahoo API blocked, trying yfinance for {symbol}")
                loop = asyncio.get_event_loop()
                result = await loop.run_in_executor(None, _fetch_yfinance_quote, symbol)
                return result

            data = resp.json()
            chart = data.get("chart", {})
            result = chart.get("result", [])
            if not result:
                # No data - try yfinance
                loop = asyncio.get_event_loop()
                return await loop.run_in_executor(None, _fetch_yfinance_quote, symbol)

            meta = result[0].get("meta", {})
            price = meta.get("regularMarketPrice", 0)
            prev_close = meta.get("chartPreviousClose", 0) or meta.get("previousClose", 0)
            volume = meta.get("regularMarketVolume", 0)
            name = meta.get("shortName", symbol)

            change = price - prev_close if prev_close else 0
            change_pct = (change / prev_close * 100) if prev_close else 0

            return {
                "price": price,
                "prev_close": prev_close,
                "change": round(change, 2),
                "change_pct": round(change_pct, 2),
                "volume": volume,
                "name": name,
            }
        except Exception as e:
            print(f"[US] fetch_yahoo_quote error for {symbol}: {e}")
            if attempt < retries:
                await asyncio.sleep(1)
                continue
            # Final fallback to yfinance
            try:
                loop = asyncio.get_event_loop()
                return await loop.run_in_executor(None, _fetch_yfinance_quote, symbol)
            except:
                return None
    return None


async def collect_us_indices() -> Dict[str, Dict]:
    """
    미국 지수 4개 + VIX 수집 (5분 캐시)
    Returns: {"sp500": {...}, "nasdaq": {...}, "dow": {...}, "russell": {...}, "vix": {...}}
    """
    global _us_indices_cache
    now = _time.time()

    # 캐시 체크
    if _us_indices_cache["data"] and (now - _us_indices_cache["ts"]) < _US_CACHE_TTL:
        return _us_indices_cache["data"]

    result = {}
    async with httpx.AsyncClient() as client:
        tasks = []
        keys = list(US_INDICES.keys())
        for key in keys:
            symbol = US_INDICES[key]
            tasks.append(fetch_yahoo_quote(client, symbol))

        responses = await asyncio.gather(*tasks, return_exceptions=True)

        for i, key in enumerate(keys):
            resp = responses[i]
            if isinstance(resp, Exception) or resp is None:
                result[key] = {"value": 0, "change": 0, "change_pct": 0, "volume": 0}
            else:
                result[key] = {
                    "value": resp["price"],
                    "change": resp["change"],
                    "change_pct": resp["change_pct"],
                    "volume": resp["volume"],
                }

    # 캐시 저장
    if any(v.get("value", 0) > 0 for v in result.values()):
        _us_indices_cache = {"data": result, "ts": now}

    return result


async def collect_us_sectors() -> List[Dict]:
    """
    S&P 500 GICS 11개 섹터 ETF 수집 (5분 캐시)
    Returns: [{"symbol": "XLK", "name": "기술", "name_en": "Technology", "price": ..., "change_pct": ..., "volume": ...}, ...]
    """
    global _us_sectors_cache
    now = _time.time()

    # 캐시 체크
    if _us_sectors_cache["data"] and (now - _us_sectors_cache["ts"]) < _US_CACHE_TTL:
        return _us_sectors_cache["data"]

    result = []
    async with httpx.AsyncClient() as client:
        tasks = [fetch_yahoo_quote(client, etf["symbol"]) for etf in US_SECTOR_ETFS]
        responses = await asyncio.gather(*tasks, return_exceptions=True)

        for i, etf in enumerate(US_SECTOR_ETFS):
            resp = responses[i]
            if isinstance(resp, Exception) or resp is None:
                result.append({
                    "symbol": etf["symbol"],
                    "name": etf["name"],
                    "name_en": etf["name_en"],
                    "price": 0,
                    "change_pct": 0,
                    "volume": 0,
                })
            else:
                result.append({
                    "symbol": etf["symbol"],
                    "name": etf["name"],
                    "name_en": etf["name_en"],
                    "price": resp["price"],
                    "change_pct": resp["change_pct"],
                    "volume": resp["volume"],
                })

    # 등락률 기준 정렬
    result.sort(key=lambda x: x["change_pct"], reverse=True)

    # 캐시 저장 (유효한 데이터가 있을 때만)
    if any(s.get("price", 0) > 0 for s in result):
        _us_sectors_cache = {"data": result, "ts": now}

    return result


async def collect_us_heatmap() -> List[Dict]:
    """
    히트맵용 S&P 500 전체 종목 데이터 수집 (503개)

    1순위: Finviz API (등락률) + Finviz Screener (섹터/시가총액)
    2순위: Finviz API + HEATMAP_STOCKS 메타데이터 (30개 폴백)
    """
    result = []

    # 1) Finviz API에서 등락률 가져오기
    finviz_data = await collect_finviz_heatmap()

    if not finviz_data:
        # Finviz API 실패 시: 기존 30개 방식으로 폴백
        print("[US Heatmap] Finviz API 실패 - 30개 종목 폴백")
        for stock in HEATMAP_STOCKS:
            result.append({
                "symbol": stock["symbol"],
                "name": stock["name"],
                "sector": stock["sector"],
                "price": 0,
                "change_pct": 0,
                "volume": 0,
                "market_cap": stock.get("market_cap", 0.1),
            })
        return result

    # 2) S&P 500 메타데이터 가져오기 (섹터, 시가총액)
    metadata = await _fetch_sp500_metadata_async()

    # 3) 메타데이터 없으면 HEATMAP_STOCKS로 폴백
    if not metadata:
        print("[US Heatmap] Screener 실패 - HEATMAP_STOCKS 30개 사용")
        # 기존 30개 종목에 Finviz 등락률 적용
        for stock in HEATMAP_STOCKS:
            symbol = stock["symbol"]
            finviz_symbol = symbol.replace("-", ".")
            change_pct = finviz_data.get(symbol, finviz_data.get(finviz_symbol, 0))
            result.append({
                "symbol": symbol,
                "name": stock["name"],
                "sector": stock["sector"],
                "price": 0,
                "change_pct": round(float(change_pct), 2) if change_pct else 0,
                "volume": 0,
                "market_cap": stock.get("market_cap", 0.1),
            })
        result.sort(key=lambda x: x["market_cap"], reverse=True)
        return result

    # 4) 503개 전체 종목 조합 (Finviz API + Screener 메타데이터)
    print(f"[US Heatmap] {len(finviz_data)}개 종목 + {len(metadata)}개 메타데이터 조합")
    for symbol, change_pct in finviz_data.items():
        meta = metadata.get(symbol, {})
        if meta:
            result.append({
                "symbol": symbol,
                "name": meta.get("name", symbol),
                "sector": meta.get("sector", "기타"),
                "price": 0,
                "change_pct": round(float(change_pct), 2),
                "volume": 0,
                "market_cap": meta.get("market_cap", 0.01),
            })
        else:
            # 메타데이터 없는 종목은 '기타' 섹터로 추가
            result.append({
                "symbol": symbol,
                "name": symbol,
                "sector": "기타",
                "price": 0,
                "change_pct": round(float(change_pct), 2),
                "volume": 0,
                "market_cap": 0.01,
            })

    # 시가총액 기준 내림차순 정렬
    result.sort(key=lambda x: x["market_cap"], reverse=True)
    print(f"[US Heatmap] 최종 {len(result)}개 종목")
    return result


async def collect_fear_greed_index() -> Dict:
    """
    CNN Fear & Greed Index 수집
    Returns: {"value": 65, "label": "탐욕", "label_en": "Greed"}
    """
    try:
        async with httpx.AsyncClient() as client:
            url = "https://production.dataviz.cnn.io/index/fearandgreed/graphdata"
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                "Accept": "application/json",
            }
            resp = await client.get(url, headers=headers, timeout=10)
            if resp.status_code != 200:
                print(f"[US] CNN Fear & Greed API error: {resp.status_code}")
                return {"value": 50, "label": "중립", "label_en": "Neutral"}

            data = resp.json()
            fg = data.get("fear_and_greed", {})
            score = fg.get("score", 50)
            rating = fg.get("rating", "Neutral")
            label = FG_LABELS.get(rating, "중립")

            return {
                "value": round(score),
                "label": label,
                "label_en": rating,
            }
    except Exception as e:
        print(f"[US] collect_fear_greed_index error: {e}")
        return {"value": 50, "label": "중립", "label_en": "Neutral"}


async def collect_finviz_breadth() -> Dict[str, Any]:
    """
    Finviz 메인페이지에서 전체 시장 breadth 데이터 수집

    파싱 대상 (HTML 구조는 docs/finviz_analysis.md 참조):
      Advancing  62.5% (3485)  Declining  (1849) 33.2%
      New High   50.4% (198)   New Low    (195) 49.6%
      Above SMA50  48.5% (2697)  Below (2699)
      Above SMA200 51.8% (2879)  Below (2589)
    """
    result = {
        "advancing": 0, "declining": 0, "unchanged": 0,
        "advancing_pct": 0.0, "declining_pct": 0.0,
        "new_high": 0, "new_low": 0,
        "above_sma50": 0, "below_sma50": 0,
        "above_sma200": 0, "below_sma200": 0,
    }

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                "Accept": "text/html,application/xhtml+xml",
                "Accept-Language": "en-US,en;q=0.9",
            }
            r = await client.get("https://finviz.com/", headers=headers)
            if r.status_code != 200:
                print(f"[Finviz] 메인 접속 실패: {r.status_code}")
                return result

            html = r.text

            # Advancing: <p>Advancing</p><p>62.5% (3485)</p>
            m = re.search(r'Advancing</p><p>(\d+\.\d+)%\s*\((\d+)\)', html)
            if m:
                result["advancing_pct"] = float(m.group(1))
                result["advancing"] = int(m.group(2))
            else:
                # 대안 패턴
                m = re.search(r'>Advancing<.*?>(\d+\.\d+)%.*?\((\d+)\)', html, re.DOTALL)
                if m:
                    result["advancing_pct"] = float(m.group(1))
                    result["advancing"] = int(m.group(2))

            # Declining: <p>Declining</p><p>(1849) 33.2%</p>
            m = re.search(r'Declining</p><p>\((\d+)\)\s*(\d+\.\d+)%', html)
            if m:
                result["declining"] = int(m.group(1))
                result["declining_pct"] = float(m.group(2))
            else:
                # 대안 패턴
                m = re.search(r'>Declining<.*?\((\d+)\).*?(\d+\.\d+)%', html, re.DOTALL)
                if m:
                    result["declining"] = int(m.group(1))
                    result["declining_pct"] = float(m.group(2))

            # New High: <p>New High</p><p>50.4% (198)</p>
            m = re.search(r'New High</p><p>(\d+\.\d+)%\s*\((\d+)\)', html)
            if m:
                result["new_high"] = int(m.group(2))
            else:
                m = re.search(r'>New High<.*?>(\d+\.\d+)%.*?\((\d+)\)', html, re.DOTALL)
                if m:
                    result["new_high"] = int(m.group(2))

            # New Low: <p>New Low</p><p>(195) 49.6%</p>
            m = re.search(r'New Low</p><p>\((\d+)\)', html)
            if m:
                result["new_low"] = int(m.group(1))
            else:
                m = re.search(r'>New Low<.*?\((\d+)\)', html, re.DOTALL)
                if m:
                    result["new_low"] = int(m.group(1))

            # SMA50 영역 찾기: "SMA50 / Below SMA50" 근처에서 Above/Below 파싱
            # Above: <p>Above</p><p>48.5% (2697)</p>
            sma50_section = re.search(r'SMA50.*?Above</p><p>(\d+\.\d+)%\s*\((\d+)\).*?Below</p><p>\((\d+)\)', html, re.DOTALL)
            if sma50_section:
                result["above_sma50"] = int(sma50_section.group(2))
                result["below_sma50"] = int(sma50_section.group(3))
            else:
                # 개별 패턴
                m = re.search(r'SMA50.*?Above</p><p>.*?\((\d+)\)', html, re.DOTALL)
                if m:
                    result["above_sma50"] = int(m.group(1))
                m = re.search(r'SMA50.*?Below</p><p>\((\d+)\)', html, re.DOTALL)
                if m:
                    result["below_sma50"] = int(m.group(1))

            # SMA200 영역 찾기
            sma200_section = re.search(r'SMA200.*?Above</p><p>(\d+\.\d+)%\s*\((\d+)\).*?Below</p><p>\((\d+)\)', html, re.DOTALL)
            if sma200_section:
                result["above_sma200"] = int(sma200_section.group(2))
                result["below_sma200"] = int(sma200_section.group(3))
            else:
                # 개별 패턴
                m = re.search(r'SMA200.*?Above</p><p>.*?\((\d+)\)', html, re.DOTALL)
                if m:
                    result["above_sma200"] = int(m.group(1))
                m = re.search(r'SMA200.*?Below</p><p>\((\d+)\)', html, re.DOTALL)
                if m:
                    result["below_sma200"] = int(m.group(1))

            # advancing_pct 계산 (파싱 안 됐을 때)
            total = result["advancing"] + result["declining"]
            if total > 0 and result["advancing_pct"] == 0:
                result["advancing_pct"] = round(result["advancing"] / total * 100, 1)
                result["declining_pct"] = round(result["declining"] / total * 100, 1)

            print(f"[Finviz] breadth: ▲{result['advancing']}({result['advancing_pct']}%) "
                  f"▼{result['declining']}({result['declining_pct']}%) "
                  f"NH={result['new_high']} NL={result['new_low']} "
                  f"SMA50={result['above_sma50']}/{result['below_sma50']} "
                  f"SMA200={result['above_sma200']}/{result['below_sma200']}")

    except Exception as e:
        print(f"[Finviz] breadth 수집 오류: {e}")

    return result


# Finviz 히트맵 API 캐시
_finviz_heatmap_cache: Dict[str, Any] = {"data": {}, "timestamp": 0}


async def collect_finviz_heatmap() -> Dict[str, float]:
    """
    Finviz 히트맵 API에서 S&P 500 전체 종목 등락률 수집

    URL: https://finviz.com/api/map_perf.ashx?t=sec
    응답: {"nodes": {"AAPL": -7.16, "MSFT": -0.75, ...}, ...}

    5분 캐시 적용
    Returns: {"AAPL": -7.16, "MSFT": -0.75, ...}
    """
    import time

    now = time.time()
    if _finviz_heatmap_cache["data"] and (now - _finviz_heatmap_cache["timestamp"]) < 300:
        return _finviz_heatmap_cache["data"]

    result = {}

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            }
            r = await client.get(
                "https://finviz.com/api/map_perf.ashx?t=sec",
                headers=headers
            )
            if r.status_code != 200:
                print(f"[Finviz] 히트맵 API 실패: {r.status_code}")
                return result

            data = r.json()

            # 응답 구조: {"nodes": {"AAPL": -7.16, ...}, ...}
            if isinstance(data, dict):
                if "nodes" in data:
                    result = data["nodes"]
                else:
                    # 키가 티커 심볼인지 확인
                    sample_key = next(iter(data), "")
                    if sample_key.isupper() and len(sample_key) <= 5:
                        result = data

            if result:
                _finviz_heatmap_cache["data"] = result
                _finviz_heatmap_cache["timestamp"] = now
                print(f"[Finviz] 히트맵: {len(result)}개 종목 수집")

    except Exception as e:
        print(f"[Finviz] 히트맵 수집 오류: {e}")

    return result


# S&P 500 메타데이터 캐시 (섹터, 시가총액) - 1시간 캐시
_sp500_metadata_cache: Dict[str, Any] = {"data": {}, "timestamp": 0}

# Finviz 섹터 → 한글 변환
FINVIZ_SECTOR_KR = {
    "Technology": "기술",
    "Healthcare": "헬스케어",
    "Financial": "금융",
    "Financials": "금융",
    "Financial Services": "금융",
    "Consumer Cyclical": "임의소비재",
    "Consumer Defensive": "필수소비재",
    "Communication Services": "커뮤니케이션",
    "Industrials": "산업재",
    "Energy": "에너지",
    "Utilities": "유틸리티",
    "Real Estate": "부동산",
    "Basic Materials": "소재",
    "Materials": "소재",
}


def _parse_market_cap(mcap_str: str) -> float:
    """시가총액 문자열을 조 달러 단위로 변환 ('4442.28B' → 4.44)"""
    if not mcap_str:
        return 0.01
    mcap_str = mcap_str.strip().upper()
    try:
        if mcap_str.endswith("T"):
            return float(mcap_str[:-1])
        elif mcap_str.endswith("B"):
            return float(mcap_str[:-1]) / 1000
        elif mcap_str.endswith("M"):
            return float(mcap_str[:-1]) / 1000000
        else:
            return float(mcap_str) / 1e12
    except:
        return 0.01


async def _fetch_sp500_metadata_async() -> Dict[str, Dict]:
    """
    Finviz Screener 페이지 직접 스크래핑으로 S&P 500 메타데이터 수집
    1시간 캐시 적용
    Returns: {"AAPL": {"sector": "기술", "market_cap": 3.5, "name": "Apple Inc"}, ...}
    """
    import time
    from bs4 import BeautifulSoup

    now = time.time()
    if _sp500_metadata_cache["data"] and (now - _sp500_metadata_cache["timestamp"]) < 3600:
        return _sp500_metadata_cache["data"]

    result = {}
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml",
    }

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            # S&P 500 필터 + 시가총액 정렬
            page = 1
            all_stocks = []

            while True:
                # Finviz Screener URL (페이지네이션)
                offset = (page - 1) * 20 + 1
                url = f"https://finviz.com/screener.ashx?v=111&f=idx_sp500&o=-marketcap&r={offset}"

                r = await client.get(url, headers=headers)
                if r.status_code != 200:
                    print(f"[Finviz Screener] 페이지 {page} 실패: {r.status_code}")
                    break

                soup = BeautifulSoup(r.text, 'lxml')

                # 테이블 행 찾기 (class="screener-body-table-nw")
                rows = soup.select('table.screener-body-table-nw tr[valign="top"]')
                if not rows:
                    # 대안: 다른 클래스 시도
                    rows = soup.select('tr.styled-row')

                if not rows:
                    break

                for row in rows:
                    cols = row.find_all('td')
                    if len(cols) < 10:
                        continue

                    try:
                        # 컬럼 순서: No, Ticker, Company, Sector, Industry, Country, Market Cap, P/E, Price, Change, Volume
                        ticker_link = cols[1].find('a')
                        ticker = ticker_link.text.strip() if ticker_link else ""
                        company = cols[2].text.strip()
                        sector_en = cols[3].text.strip()
                        mcap_str = cols[6].text.strip()

                        if ticker:
                            sector_kr = FINVIZ_SECTOR_KR.get(sector_en, sector_en)
                            mcap = _parse_market_cap(mcap_str)
                            all_stocks.append({
                                "symbol": ticker,
                                "name": company,
                                "sector": sector_kr,
                                "market_cap": mcap,
                            })
                    except Exception:
                        continue

                # 다음 페이지
                if len(rows) < 20 or page >= 30:  # 최대 30페이지 (600종목)
                    break
                page += 1

            # 결과 저장
            for stock in all_stocks:
                result[stock["symbol"]] = {
                    "sector": stock["sector"],
                    "market_cap": stock["market_cap"],
                    "name": stock["name"],
                }

            if result:
                _sp500_metadata_cache["data"] = result
                _sp500_metadata_cache["timestamp"] = now
                print(f"[Finviz Screener] S&P 500 메타데이터: {len(result)}개 종목 ({page}페이지)")

    except Exception as e:
        print(f"[Finviz Screener] 메타데이터 수집 오류: {e}")
        import traceback
        traceback.print_exc()

    return result


def _fetch_sp500_metadata_sync() -> Dict[str, Dict]:
    """동기 래퍼 - asyncio.run 사용"""
    import asyncio
    try:
        loop = asyncio.get_running_loop()
        # 이미 이벤트 루프 실행 중이면 빈 결과 반환 (async에서 직접 호출)
        return _sp500_metadata_cache.get("data", {})
    except RuntimeError:
        # 이벤트 루프 없으면 새로 생성
        return asyncio.run(_fetch_sp500_metadata_async())


async def get_us_market_summary() -> Dict[str, Any]:
    """
    미국 시장 요약 데이터 전체 수집 (국내시장 get_market_summary 대응)
    """
    # 병렬 수집 (Finviz breadth 추가)
    indices_task = collect_us_indices()
    sectors_task = collect_us_sectors()
    heatmap_task = collect_us_heatmap()
    fg_task = collect_fear_greed_index()
    breadth_task = collect_finviz_breadth()

    indices, sectors, heatmap, fear_greed, breadth = await asyncio.gather(
        indices_task, sectors_task, heatmap_task, fg_task, breadth_task,
        return_exceptions=True
    )

    # 예외 처리
    if isinstance(indices, Exception):
        print(f"[US DataCollector] indices error: {indices}")
        indices = {}
    if isinstance(sectors, Exception):
        print(f"[US DataCollector] sectors error: {sectors}")
        sectors = []
    if isinstance(heatmap, Exception):
        print(f"[US DataCollector] heatmap error: {heatmap}")
        heatmap = []
    if isinstance(fear_greed, Exception):
        print(f"[US DataCollector] fear_greed error: {fear_greed}")
        fear_greed = {"value": 50, "label": "중립", "label_en": "Neutral"}
    if isinstance(breadth, Exception):
        print(f"[US DataCollector] breadth error: {breadth}")
        breadth = {
            "advancing": 0, "declining": 0, "unchanged": 0,
            "advancing_pct": 0, "declining_pct": 0,
            "new_high": 0, "new_low": 0,
            "above_sma50": 0, "below_sma50": 0,
            "above_sma200": 0, "below_sma200": 0,
        }

    # Finviz breadth 사용 (전체 시장 기준)
    rising = breadth.get("advancing", 0)
    falling = breadth.get("declining", 0)
    unchanged = breadth.get("unchanged", 0)

    # Finviz 실패 시 히트맵 기준 폴백
    if rising == 0 and falling == 0:
        rising = sum(1 for s in heatmap if s.get("change_pct", 0) > 0)
        falling = sum(1 for s in heatmap if s.get("change_pct", 0) < 0)
        unchanged = sum(1 for s in heatmap if s.get("change_pct", 0) == 0)

    return {
        "indices": indices,
        "sectors": sectors,
        "heatmap": heatmap,
        "fear_greed": fear_greed,
        "breadth": breadth,
        "rising_stocks": rising,
        "falling_stocks": falling,
        "unchanged_stocks": unchanged,
    }


async def fetch_us_index_history(market: str, days: int = 100) -> List[Dict]:
    """
    지수 히스토리 조회 (Big Picture 초기화용)
    market: "SP500" or "NASDAQ"
    Returns: [{"date": "2026-02-14", "close": 6000.12, "volume": ...}, ...]
    """
    symbol_map = {
        "SP500": "^GSPC",
        "NASDAQ": "^IXIC",
    }
    symbol = symbol_map.get(market.upper(), "^GSPC")

    try:
        async with httpx.AsyncClient() as client:
            url = f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}?interval=1d&range={days}d"
            resp = await client.get(url, timeout=15)
            if resp.status_code != 200:
                return []

            data = resp.json()
            result_data = data.get("chart", {}).get("result", [])
            if not result_data:
                return []

            timestamps = result_data[0].get("timestamp", [])
            indicators = result_data[0].get("indicators", {})
            quote = indicators.get("quote", [{}])[0]
            closes = quote.get("close", [])
            volumes = quote.get("volume", [])

            history = []
            for i, ts in enumerate(timestamps):
                if i < len(closes) and closes[i] is not None:
                    dt = datetime.fromtimestamp(ts, tz=timezone.utc)
                    history.append({
                        "date": dt.strftime("%Y-%m-%d"),
                        "close": closes[i],
                        "volume": volumes[i] if i < len(volumes) else 0,
                    })

            return history
    except Exception as e:
        print(f"[US] fetch_us_index_history error: {e}")
        return []


async def fetch_sector_etf_daily(symbol: str, days: int = 60) -> List[float]:
    """
    섹터 ETF 일봉 종가 조회 (추세유지 분석용)
    Returns: [close1, close2, ..., closeN] (오래된 것부터)
    """
    import asyncio
    try:
        # yfinance 사용 (동기 함수이므로 run_in_executor로 실행)
        import yfinance as yf

        def _fetch():
            ticker = yf.Ticker(symbol)
            hist = ticker.history(period=f"{days}d")
            if hist.empty:
                return []
            closes = hist["Close"].tolist()
            return [c for c in closes if c is not None]

        loop = asyncio.get_event_loop()
        closes = await loop.run_in_executor(None, _fetch)
        return closes
    except Exception as e:
        print(f"[US] fetch_sector_etf_daily error for {symbol}: {e}")
        return []

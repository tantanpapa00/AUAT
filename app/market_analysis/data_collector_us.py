"""
해외시장 데이터 수집기 (Yahoo Finance + yfinance + CNN Fear & Greed)
Finviz 완전 제거 - GitHub S&P500 CSV + yfinance 사용
"""
import asyncio
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
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
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
    """
    for attempt in range(retries + 1):
        try:
            url = f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}?interval=1d&range=2d"
            resp = await client.get(url, headers=YAHOO_HEADERS, timeout=10)
            if resp.status_code == 429:
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
                loop = asyncio.get_event_loop()
                return await loop.run_in_executor(None, _fetch_yfinance_quote, symbol)

            data = resp.json()
            chart = data.get("chart", {})
            result = chart.get("result", [])
            if not result:
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
            try:
                loop = asyncio.get_event_loop()
                return await loop.run_in_executor(None, _fetch_yfinance_quote, symbol)
            except:
                return None
    return None


async def collect_us_indices() -> Dict[str, Dict]:
    """미국 지수 4개 + VIX 수집 (5분 캐시)"""
    global _us_indices_cache
    now = _time.time()

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

    if any(v.get("value", 0) > 0 for v in result.values()):
        _us_indices_cache = {"data": result, "ts": now}

    return result


async def collect_us_sectors() -> List[Dict]:
    """S&P 500 GICS 11개 섹터 ETF 수집 (5분 캐시)"""
    global _us_sectors_cache
    now = _time.time()

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

    result.sort(key=lambda x: x["change_pct"], reverse=True)

    if any(s.get("price", 0) > 0 for s in result):
        _us_sectors_cache = {"data": result, "ts": now}

    return result


async def collect_us_heatmap() -> List[Dict]:
    """
    히트맵용 S&P 500 전체 종목 데이터 수집
    us_screener.py의 get_us_heatmap() 사용
    """
    try:
        from app.screener.us_screener import get_us_heatmap
        heatmap_data = await get_us_heatmap()
        stocks = heatmap_data.get("stocks", [])
        print(f"[US Heatmap] {len(stocks)}개 종목 로드")
        return stocks
    except Exception as e:
        print(f"[US Heatmap] 오류: {e}")
        return []


async def collect_fear_greed_index() -> Dict:
    """CNN Fear & Greed Index 수집"""
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


async def get_us_market_summary() -> Dict[str, Any]:
    """미국 시장 요약 데이터 전체 수집"""
    indices_task = collect_us_indices()
    sectors_task = collect_us_sectors()
    heatmap_task = collect_us_heatmap()
    fg_task = collect_fear_greed_index()

    indices, sectors, heatmap, fear_greed = await asyncio.gather(
        indices_task, sectors_task, heatmap_task, fg_task,
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

    # 히트맵 기준으로 상승/하락 종목 수 계산
    rising = sum(1 for s in heatmap if s.get("change_pct", 0) > 0)
    falling = sum(1 for s in heatmap if s.get("change_pct", 0) < 0)
    unchanged = sum(1 for s in heatmap if s.get("change_pct", 0) == 0)

    # breadth 데이터 (히트맵 기반 계산)
    total = rising + falling + unchanged
    breadth = {
        "advancing": rising,
        "declining": falling,
        "unchanged": unchanged,
        "advancing_pct": round(rising / total * 100, 1) if total > 0 else 0,
        "declining_pct": round(falling / total * 100, 1) if total > 0 else 0,
        "new_high": 0,
        "new_low": 0,
        "above_sma50": 0,
        "below_sma50": 0,
        "above_sma200": 0,
        "below_sma200": 0,
    }

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
    """
    symbol_map = {
        "SP500": "^GSPC",
        "NASDAQ": "^IXIC",
    }
    symbol = symbol_map.get(market.upper(), "^GSPC")

    try:
        async with httpx.AsyncClient() as client:
            url = f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}?interval=1d&range={days}d"
            resp = await client.get(url, headers=YAHOO_HEADERS, timeout=15)
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
    """섹터 ETF 일봉 종가 조회 (추세유지 분석용)"""
    try:
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

"""
해외시장 데이터 수집기 (Yahoo Finance + CNN Fear & Greed)
Phase 5: 국내시장과 동일한 구조의 해외시장 분석
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

# 히트맵용 시가총액 상위 30종목
HEATMAP_STOCKS = [
    {"symbol": "AAPL", "name": "Apple", "sector": "기술"},
    {"symbol": "MSFT", "name": "Microsoft", "sector": "기술"},
    {"symbol": "NVDA", "name": "NVIDIA", "sector": "기술"},
    {"symbol": "GOOGL", "name": "Alphabet", "sector": "커뮤니케이션"},
    {"symbol": "AMZN", "name": "Amazon", "sector": "임의소비재"},
    {"symbol": "META", "name": "Meta", "sector": "커뮤니케이션"},
    {"symbol": "TSLA", "name": "Tesla", "sector": "임의소비재"},
    {"symbol": "BRK-B", "name": "Berkshire", "sector": "금융"},
    {"symbol": "JPM", "name": "JPMorgan", "sector": "금융"},
    {"symbol": "V", "name": "Visa", "sector": "금융"},
    {"symbol": "UNH", "name": "UnitedHealth", "sector": "헬스케어"},
    {"symbol": "MA", "name": "Mastercard", "sector": "금융"},
    {"symbol": "HD", "name": "Home Depot", "sector": "임의소비재"},
    {"symbol": "PG", "name": "P&G", "sector": "필수소비재"},
    {"symbol": "COST", "name": "Costco", "sector": "필수소비재"},
    {"symbol": "ABBV", "name": "AbbVie", "sector": "헬스케어"},
    {"symbol": "CRM", "name": "Salesforce", "sector": "기술"},
    {"symbol": "AVGO", "name": "Broadcom", "sector": "기술"},
    {"symbol": "NFLX", "name": "Netflix", "sector": "커뮤니케이션"},
    {"symbol": "AMD", "name": "AMD", "sector": "기술"},
    {"symbol": "LLY", "name": "Eli Lilly", "sector": "헬스케어"},
    {"symbol": "WMT", "name": "Walmart", "sector": "필수소비재"},
    {"symbol": "XOM", "name": "Exxon", "sector": "에너지"},
    {"symbol": "CVX", "name": "Chevron", "sector": "에너지"},
    {"symbol": "BAC", "name": "Bank of America", "sector": "금융"},
    {"symbol": "ORCL", "name": "Oracle", "sector": "기술"},
    {"symbol": "KO", "name": "Coca-Cola", "sector": "필수소비재"},
    {"symbol": "PEP", "name": "PepsiCo", "sector": "필수소비재"},
    {"symbol": "MRK", "name": "Merck", "sector": "헬스케어"},
    {"symbol": "DIS", "name": "Disney", "sector": "커뮤니케이션"},
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


async def fetch_yahoo_quote(client: httpx.AsyncClient, symbol: str) -> Optional[Dict]:
    """
    Yahoo Finance에서 단일 종목 시세 조회
    Returns: {price, prev_close, change, change_pct, volume, name} or None
    """
    try:
        url = f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}?interval=1d&range=2d"
        resp = await client.get(url, timeout=10)
        if resp.status_code != 200:
            print(f"[US] Yahoo API error for {symbol}: {resp.status_code}")
            return None

        data = resp.json()
        chart = data.get("chart", {})
        result = chart.get("result", [])
        if not result:
            return None

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
        return None


async def collect_us_indices() -> Dict[str, Dict]:
    """
    미국 지수 4개 + VIX 수집
    Returns: {"sp500": {...}, "nasdaq": {...}, "dow": {...}, "russell": {...}, "vix": {...}}
    """
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
    return result


async def collect_us_sectors() -> List[Dict]:
    """
    S&P 500 GICS 11개 섹터 ETF 수집
    Returns: [{"symbol": "XLK", "name": "기술", "name_en": "Technology", "price": ..., "change_pct": ..., "volume": ...}, ...]
    """
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
    return result


async def collect_us_heatmap() -> List[Dict]:
    """
    히트맵용 주요 30종목 수집
    Returns: [{"symbol": "AAPL", "name": "Apple", "sector": "기술", "price": ..., "change_pct": ..., "volume": ...}, ...]
    """
    result = []
    async with httpx.AsyncClient() as client:
        tasks = [fetch_yahoo_quote(client, stock["symbol"]) for stock in HEATMAP_STOCKS]
        responses = await asyncio.gather(*tasks, return_exceptions=True)

        for i, stock in enumerate(HEATMAP_STOCKS):
            resp = responses[i]
            if isinstance(resp, Exception) or resp is None:
                result.append({
                    "symbol": stock["symbol"],
                    "name": stock["name"],
                    "sector": stock["sector"],
                    "price": 0,
                    "change_pct": 0,
                    "volume": 0,
                })
            else:
                result.append({
                    "symbol": stock["symbol"],
                    "name": stock["name"],
                    "sector": stock["sector"],
                    "price": resp["price"],
                    "change_pct": resp["change_pct"],
                    "volume": resp["volume"],
                })

    # 등락률 기준 정렬 (히트맵에서 큰 종목이 위쪽에)
    result.sort(key=lambda x: x["change_pct"], reverse=True)
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


async def get_us_market_summary() -> Dict:
    """
    해외시장 전체 요약 (병렬 수집)
    Returns: {
        "indices": {...},
        "sectors": [...],
        "heatmap": [...],
        "fear_greed": {...},
        "rising_stocks": int,
        "falling_stocks": int,
        "unchanged_stocks": int,
    }
    """
    # 병렬 수집
    indices_task = collect_us_indices()
    sectors_task = collect_us_sectors()
    heatmap_task = collect_us_heatmap()
    fear_greed_task = collect_fear_greed_index()

    indices, sectors, heatmap, fear_greed = await asyncio.gather(
        indices_task, sectors_task, heatmap_task, fear_greed_task,
        return_exceptions=True
    )

    # 예외 처리
    if isinstance(indices, Exception):
        indices = {}
    if isinstance(sectors, Exception):
        sectors = []
    if isinstance(heatmap, Exception):
        heatmap = []
    if isinstance(fear_greed, Exception):
        fear_greed = {"value": 50, "label": "중립", "label_en": "Neutral"}

    # 히트맵에서 상승/하락/보합 집계
    rising = sum(1 for s in heatmap if s.get("change_pct", 0) > 0)
    falling = sum(1 for s in heatmap if s.get("change_pct", 0) < 0)
    unchanged = len(heatmap) - rising - falling

    return {
        "indices": indices,
        "sectors": sectors,
        "heatmap": heatmap,
        "fear_greed": fear_greed,
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

            indicators = result_data[0].get("indicators", {})
            quote = indicators.get("quote", [{}])[0]
            closes = quote.get("close", [])

            # None 제거
            valid_closes = [c for c in closes if c is not None]
            return valid_closes
    except Exception as e:
        print(f"[US] fetch_sector_etf_daily error for {symbol}: {e}")
        return []

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
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "application/json",
    "Accept-Language": "en-US,en;q=0.9",
}


async def fetch_yahoo_quote(client: httpx.AsyncClient, symbol: str, retries: int = 2) -> Optional[Dict]:
    """
    Yahoo Finance에서 단일 종목 시세 조회
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
            if attempt < retries:
                await asyncio.sleep(1)
                continue
            return None
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
    히트맵용 주요 30종목 수집 (시가총액 포함)
    Returns: [{"symbol": "AAPL", "name": "Apple", "sector": "기술", "price": ..., "change_pct": ..., "market_cap": ...}, ...]
    """
    result = []
    async with httpx.AsyncClient() as client:
        tasks = [fetch_yahoo_quote(client, stock["symbol"]) for stock in HEATMAP_STOCKS]
        responses = await asyncio.gather(*tasks, return_exceptions=True)

        for i, stock in enumerate(HEATMAP_STOCKS):
            resp = responses[i]
            market_cap = stock.get("market_cap", 0.1)  # 조 달러 단위
            if isinstance(resp, Exception) or resp is None:
                result.append({
                    "symbol": stock["symbol"],
                    "name": stock["name"],
                    "sector": stock["sector"],
                    "price": 0,
                    "change_pct": 0,
                    "volume": 0,
                    "market_cap": market_cap,
                })
            else:
                result.append({
                    "symbol": stock["symbol"],
                    "name": stock["name"],
                    "sector": stock["sector"],
                    "price": resp["price"],
                    "change_pct": resp["change_pct"],
                    "volume": resp["volume"],
                    "market_cap": market_cap,
                })

    # 시가총액 기준 내림차순 정렬 (트리맵에서 큰 종목이 먼저)
    result.sort(key=lambda x: x["market_cap"], reverse=True)
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


async def collect_finviz_breadth() -> Dict:
    """
    Finviz에서 S&P 500 시장 브레드스 데이터 수집
    Returns: {
        "sp500_advancing": int,
        "sp500_declining": int,
        "sp500_new_high": int,
        "sp500_new_low": int,
        "sp500_above_sma50": float (퍼센트),
        "sp500_above_sma200": float (퍼센트)
    }
    """
    result = {
        "sp500_advancing": 0,
        "sp500_declining": 0,
        "sp500_new_high": 0,
        "sp500_new_low": 0,
        "sp500_above_sma50": 50.0,
        "sp500_above_sma200": 50.0,
    }

    try:
        async with httpx.AsyncClient() as client:
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Accept-Language": "en-US,en;q=0.9",
            }

            # Finviz 메인 페이지에서 S&P 500 브레드스 파싱
            url = "https://finviz.com/groups.ashx?g=sp500"
            resp = await client.get(url, headers=headers, timeout=15)

            if resp.status_code != 200:
                print(f"[US] Finviz breadth request failed: {resp.status_code}")
                return result

            html = resp.text

            # S&P 500 상승/하락 종목 수 파싱 (예: "347" / "156")
            # Finviz 페이지 구조에 따라 정규식 조정 필요
            adv_match = re.search(r'Advancing[^\d]*(\d+)', html)
            dec_match = re.search(r'Declining[^\d]*(\d+)', html)

            if adv_match:
                result["sp500_advancing"] = int(adv_match.group(1))
            if dec_match:
                result["sp500_declining"] = int(dec_match.group(1))

            # New High / New Low 파싱
            nh_match = re.search(r'New High[^\d]*(\d+)', html)
            nl_match = re.search(r'New Low[^\d]*(\d+)', html)

            if nh_match:
                result["sp500_new_high"] = int(nh_match.group(1))
            if nl_match:
                result["sp500_new_low"] = int(nl_match.group(1))

            # SMA 위 비율 (Finviz 제공 시)
            sma50_match = re.search(r'Above SMA50[^\d]*(\d+\.?\d*)%', html)
            sma200_match = re.search(r'Above SMA200[^\d]*(\d+\.?\d*)%', html)

            if sma50_match:
                result["sp500_above_sma50"] = float(sma50_match.group(1))
            if sma200_match:
                result["sp500_above_sma200"] = float(sma200_match.group(1))

    except Exception as e:
        print(f"[US] collect_finviz_breadth error: {e}")

    return result


async def get_us_market_summary() -> Dict:
    """
    해외시장 전체 요약 (병렬 수집)
    Returns: {
        "indices": {...},
        "sectors": [...],
        "heatmap": [...],
        "fear_greed": {...},
        "breadth": {...},  # Finviz 브레드스 데이터
        "rising_stocks": int,
        "falling_stocks": int,
        "unchanged_stocks": int,
    }
    """
    # 병렬 수집 (Finviz 브레드스 추가)
    indices_task = collect_us_indices()
    sectors_task = collect_us_sectors()
    heatmap_task = collect_us_heatmap()
    fear_greed_task = collect_fear_greed_index()
    breadth_task = collect_finviz_breadth()

    indices, sectors, heatmap, fear_greed, breadth = await asyncio.gather(
        indices_task, sectors_task, heatmap_task, fear_greed_task, breadth_task,
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
    if isinstance(breadth, Exception):
        breadth = {
            "sp500_advancing": 0,
            "sp500_declining": 0,
            "sp500_new_high": 0,
            "sp500_new_low": 0,
            "sp500_above_sma50": 50.0,
            "sp500_above_sma200": 50.0,
        }

    # Finviz 브레드스 데이터 사용 (실제 S&P 500 상승/하락 종목 수)
    rising = breadth.get("sp500_advancing", 0)
    falling = breadth.get("sp500_declining", 0)

    # Finviz 데이터가 없으면 히트맵 30종목 비율로 추정
    if rising == 0 and falling == 0:
        heatmap_rising = sum(1 for s in heatmap if s.get("change_pct", 0) > 0)
        heatmap_falling = sum(1 for s in heatmap if s.get("change_pct", 0) < 0)
        heatmap_total = len(heatmap) or 1
        sp500_total = 503
        rising = round(heatmap_rising / heatmap_total * sp500_total)
        falling = round(heatmap_falling / heatmap_total * sp500_total)

    # 보합 = 503 - 상승 - 하락
    sp500_total = 503
    unchanged = max(0, sp500_total - rising - falling)

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

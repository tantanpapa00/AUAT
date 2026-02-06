"""
Yahoo Finance 데이터 수집 모듈
- 미국 주요 지수 (S&P500, 나스닥, 다우, 러셀)
- 미국 개별 종목 시세
- 미국 종목 차트 데이터
"""

import httpx
from typing import Optional, List, Dict, Any
from datetime import datetime

# 공통 헤더
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
}

# 타임아웃 설정
TIMEOUT = 10.0

# 주요 미국 지수 심볼
US_INDICES = {
    "^GSPC": "S&P 500",
    "^IXIC": "NASDAQ",
    "^DJI": "Dow Jones",
    "^RUT": "Russell 2000",
}

# 시가총액 상위 미국 종목
TOP_US_STOCKS = [
    "AAPL", "MSFT", "GOOGL", "AMZN", "NVDA", "META", "TSLA", "BRK-B",
    "UNH", "XOM", "JPM", "JNJ", "V", "PG", "MA", "HD", "CVX", "MRK",
    "ABBV", "LLY"
]


async def get_us_indices() -> Dict[str, Dict[str, Any]]:
    """미국 주요 지수 (S&P500, 나스닥, 다우, 러셀)"""
    results = {}

    async with httpx.AsyncClient(timeout=TIMEOUT) as client:
        for symbol, name in US_INDICES.items():
            try:
                url = f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}?interval=1d&range=1d"
                resp = await client.get(url, headers=HEADERS)
                data = resp.json()

                if "chart" in data and "result" in data["chart"] and data["chart"]["result"]:
                    result = data["chart"]["result"][0]
                    meta = result.get("meta", {})

                    current = meta.get("regularMarketPrice", 0)
                    prev_close = meta.get("chartPreviousClose", meta.get("previousClose", current))
                    change = current - prev_close
                    change_pct = (change / prev_close * 100) if prev_close else 0

                    results[symbol] = {
                        "name": name,
                        "symbol": symbol,
                        "current": round(current, 2),
                        "change": round(change, 2),
                        "change_percent": round(change_pct, 2),
                    }
                else:
                    results[symbol] = {"name": name, "symbol": symbol, "current": 0, "error": "No data"}

            except Exception as e:
                print(f"[YahooFinance] {symbol} 조회 실패: {e}")
                results[symbol] = {"name": name, "symbol": symbol, "current": 0, "error": str(e)}

    return results


async def get_stock_price_us(symbol: str) -> Dict[str, Any]:
    """미국 개별 종목 시세"""
    try:
        async with httpx.AsyncClient(timeout=TIMEOUT) as client:
            url = f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}?interval=1d&range=5d"
            resp = await client.get(url, headers=HEADERS)
            data = resp.json()

            if "chart" in data and "result" in data["chart"] and data["chart"]["result"]:
                result = data["chart"]["result"][0]
                meta = result.get("meta", {})
                quote = result.get("indicators", {}).get("quote", [{}])[0]

                current = meta.get("regularMarketPrice", 0)
                prev_close = meta.get("chartPreviousClose", meta.get("previousClose", current))
                change = current - prev_close
                change_pct = (change / prev_close * 100) if prev_close else 0

                # 오늘 시가/고가/저가
                opens = quote.get("open", [])
                highs = quote.get("high", [])
                lows = quote.get("low", [])
                volumes = quote.get("volume", [])

                open_price = opens[-1] if opens and opens[-1] else 0
                high = highs[-1] if highs and highs[-1] else 0
                low = lows[-1] if lows and lows[-1] else 0
                volume = volumes[-1] if volumes and volumes[-1] else 0

                # 52주 최고/최저
                high52 = meta.get("fiftyTwoWeekHigh", 0)
                low52 = meta.get("fiftyTwoWeekLow", 0)

                return {
                    "symbol": symbol,
                    "name": meta.get("shortName", symbol),
                    "price": round(current, 2),
                    "change": round(change, 2),
                    "change_percent": round(change_pct, 2),
                    "open": round(open_price, 2) if open_price else 0,
                    "high": round(high, 2) if high else 0,
                    "low": round(low, 2) if low else 0,
                    "volume": int(volume) if volume else 0,
                    "high52": round(high52, 2),
                    "low52": round(low52, 2),
                    "market_cap": meta.get("marketCap", 0),
                    "currency": meta.get("currency", "USD"),
                }
            else:
                return {"symbol": symbol, "name": symbol, "price": 0, "error": "No data"}

    except Exception as e:
        print(f"[YahooFinance] {symbol} 시세 조회 실패: {e}")
        return {"symbol": symbol, "name": symbol, "price": 0, "error": str(e)}


async def get_stock_chart_us(symbol: str, period: str = "1y") -> List[Dict[str, Any]]:
    """미국 종목 차트 데이터"""
    # period: 1d, 5d, 1mo, 3mo, 6mo, 1y, 2y, 5y, max
    # interval: 1m, 2m, 5m, 15m, 30m, 60m, 90m, 1h, 1d, 5d, 1wk, 1mo

    interval_map = {
        "1d": ("1d", "5m"),
        "5d": ("5d", "15m"),
        "1mo": ("1mo", "1d"),
        "3mo": ("3mo", "1d"),
        "1y": ("1y", "1d"),
    }

    range_val, interval = interval_map.get(period, ("1y", "1d"))

    try:
        async with httpx.AsyncClient(timeout=TIMEOUT) as client:
            url = f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}?interval={interval}&range={range_val}"
            resp = await client.get(url, headers=HEADERS)
            data = resp.json()

            if "chart" in data and "result" in data["chart"] and data["chart"]["result"]:
                result = data["chart"]["result"][0]
                timestamps = result.get("timestamp", [])
                quote = result.get("indicators", {}).get("quote", [{}])[0]

                opens = quote.get("open", [])
                highs = quote.get("high", [])
                lows = quote.get("low", [])
                closes = quote.get("close", [])
                volumes = quote.get("volume", [])

                chart_data = []
                for i, ts in enumerate(timestamps):
                    if ts and closes[i]:
                        chart_data.append({
                            "time": ts,
                            "date": datetime.fromtimestamp(ts).strftime("%Y-%m-%d"),
                            "open": round(opens[i], 2) if opens[i] else 0,
                            "high": round(highs[i], 2) if highs[i] else 0,
                            "low": round(lows[i], 2) if lows[i] else 0,
                            "close": round(closes[i], 2) if closes[i] else 0,
                            "volume": int(volumes[i]) if volumes[i] else 0,
                        })

                return chart_data
            else:
                return []

    except Exception as e:
        print(f"[YahooFinance] {symbol} 차트 조회 실패: {e}")
        return []


async def get_top_us_stocks() -> List[Dict[str, Any]]:
    """시가총액 상위 미국 종목 20개 시세"""
    results = []

    async with httpx.AsyncClient(timeout=TIMEOUT) as client:
        for symbol in TOP_US_STOCKS:
            try:
                stock = await get_stock_price_us(symbol)
                if not stock.get("error"):
                    results.append(stock)
            except Exception as e:
                print(f"[YahooFinance] {symbol} 조회 실패: {e}")

    # 시가총액 순 정렬
    results.sort(key=lambda x: x.get("market_cap", 0), reverse=True)
    return results


async def get_crypto_prices() -> List[Dict[str, Any]]:
    """주요 암호화폐 시세 (Yahoo Finance)"""
    symbols = ["BTC-USD", "ETH-USD", "SOL-USD", "XRP-USD", "ADA-USD", "DOGE-USD"]
    results = []

    async with httpx.AsyncClient(timeout=TIMEOUT) as client:
        for symbol in symbols:
            try:
                url = f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}?interval=1d&range=1d"
                resp = await client.get(url, headers=HEADERS)
                data = resp.json()

                if "chart" in data and "result" in data["chart"] and data["chart"]["result"]:
                    result = data["chart"]["result"][0]
                    meta = result.get("meta", {})

                    current = meta.get("regularMarketPrice", 0)
                    prev_close = meta.get("chartPreviousClose", current)
                    change = current - prev_close
                    change_pct = (change / prev_close * 100) if prev_close else 0

                    results.append({
                        "symbol": symbol.replace("-USD", ""),
                        "name": meta.get("shortName", symbol),
                        "price": round(current, 2),
                        "change": round(change, 2),
                        "change_percent": round(change_pct, 2),
                        "volume": meta.get("regularMarketVolume", 0),
                        "market_cap": meta.get("marketCap", 0),
                    })

            except Exception as e:
                print(f"[YahooFinance] {symbol} 조회 실패: {e}")

    return results

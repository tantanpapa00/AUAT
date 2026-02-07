"""
BBooster 데이터 제공 모듈
네이버 모바일 API + yfinance + 코인거래소 API
"""
import asyncio
from datetime import datetime, timedelta
import yfinance as yf
import httpx
import traceback
import json
import re
from bs4 import BeautifulSoup

# ===== 캐싱 =====
_cache = {}

def _cached(key, ttl_seconds=3600):
    """캐시에서 데이터 가져오기. 없거나 만료되면 None"""
    if key in _cache:
        data, ts = _cache[key]
        if (datetime.now() - ts).total_seconds() < ttl_seconds:
            return data
    return None

def _set_cache(key, data):
    _cache[key] = (data, datetime.now())

# ===== 공통 HTTP 헤더 =====
NAVER_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Referer": "https://m.stock.naver.com/",
}

# ===== 국내 시장 (네이버 모바일 API) =====

async def get_kr_market_overview():
    """국내 시장 개요: 지수 + 투자자동향 + 업종"""
    cached = _cached("kr_overview", 300)  # 5분 캐싱
    if cached:
        return cached

    result = {
        "kospi": {"name": "코스피", "current": 0, "change": 0, "change_percent": 0},
        "kosdaq": {"name": "코스닥", "current": 0, "change": 0, "change_percent": 0},
        "investors": {"foreign": 0, "institution": 0, "individual": 0},
        "sectors": []
    }

    try:
        async with httpx.AsyncClient(timeout=10, headers=NAVER_HEADERS) as client:
            # 코스피 지수
            try:
                r = await client.get("https://m.stock.naver.com/api/index/KOSPI/basic")
                if r.status_code == 200:
                    data = r.json()
                    result["kospi"] = {
                        "name": "코스피",
                        "current": _parse_price(data.get("closePrice", "0")),
                        "change": _parse_price(data.get("compareToPreviousClosePrice", "0")),
                        "change_percent": _parse_float(data.get("fluctuationsRatio", "0")),
                        "volume": _parse_int(data.get("accumulatedTradingVolume", "0"))
                    }
            except Exception as e:
                print(f"[DataProvider] KOSPI error: {e}")

            # 코스닥 지수
            try:
                r = await client.get("https://m.stock.naver.com/api/index/KOSDAQ/basic")
                if r.status_code == 200:
                    data = r.json()
                    result["kosdaq"] = {
                        "name": "코스닥",
                        "current": _parse_price(data.get("closePrice", "0")),
                        "change": _parse_price(data.get("compareToPreviousClosePrice", "0")),
                        "change_percent": _parse_float(data.get("fluctuationsRatio", "0")),
                        "volume": _parse_int(data.get("accumulatedTradingVolume", "0"))
                    }
            except Exception as e:
                print(f"[DataProvider] KOSDAQ error: {e}")

            # 투자자 동향 (메인 페이지에서 파싱)
            try:
                r = await client.get("https://finance.naver.com/sise/")
                if r.status_code == 200:
                    r.encoding = "euc-kr"
                    inv_soup = BeautifulSoup(r.text, "lxml")
                    links = inv_soup.find_all("a")
                    foreign_val = 0
                    institution_val = 0
                    for link in links:
                        text = link.get_text(strip=True)
                        if "억" in text and text.startswith("외국인"):
                            try:
                                val_str = text.replace("외국인", "").replace("억", "").replace(",", "").replace("+", "")
                                foreign_val = int(float(val_str))
                                break
                            except:
                                pass
                    for link in links:
                        text = link.get_text(strip=True)
                        if "억" in text and text.startswith("기관"):
                            try:
                                val_str = text.replace("기관", "").replace("억", "").replace(",", "").replace("+", "")
                                institution_val = int(float(val_str))
                                break
                            except:
                                pass
                    individual_val = -(foreign_val + institution_val)
                    result["investors"] = {
                        "foreign": foreign_val,
                        "institution": institution_val,
                        "individual": individual_val
                    }
            except Exception as e:
                print(f"[DataProvider] Investor error: {e}")

            # 업종별 현황 (HTML 파싱)
            try:
                r = await client.get("https://finance.naver.com/sise/sise_group.naver?type=upjong")
                if r.status_code == 200:
                    r.encoding = "euc-kr"
                    soup = BeautifulSoup(r.text, "lxml")
                    sectors = []
                    rows = soup.select("table.type_1 tr")
                    for row in rows:
                        cells = row.select("td")
                        if len(cells) >= 4:
                            name_el = cells[0].select_one("a")
                            if name_el:
                                name = name_el.get_text(strip=True)
                                change_pct_str = cells[1].get_text(strip=True).replace("%", "").replace("+", "")
                                try:
                                    change_val = float(change_pct_str) if change_pct_str else 0
                                    sectors.append({"name": name, "change_percent": change_val, "volume": 0})
                                except:
                                    pass
                    sectors.sort(key=lambda x: x["change_percent"], reverse=True)
                    result["sectors"] = sectors[:15]
            except Exception as e:
                print(f"[DataProvider] Sectors error: {e}")


        _set_cache("kr_overview", result)
        return result

    except Exception as e:
        print(f"[DataProvider] KR overview error: {e}")
        traceback.print_exc()
        return result


def _parse_price(val):
    """가격 문자열 파싱 (콤마 제거)"""
    if isinstance(val, (int, float)):
        return float(val)
    if isinstance(val, str):
        return float(val.replace(",", "").replace(" ", "") or "0")
    return 0.0


def _parse_float(val):
    """실수 파싱"""
    try:
        if isinstance(val, (int, float)):
            return float(val)
        if isinstance(val, str):
            return float(val.replace(",", "").replace("%", "").replace(" ", "") or "0")
    except:
        pass
    return 0.0


def _parse_int(val):
    """정수 파싱"""
    try:
        if isinstance(val, int):
            return val
        if isinstance(val, float):
            return int(val)
        if isinstance(val, str):
            return int(float(val.replace(",", "").replace(" ", "") or "0"))
    except:
        pass
    return 0


# ===== RS 순위 (네이버 API 기반) =====

async def get_rs_ranking(market="ALL", limit=100):
    """RS 순위 - 백분위 기반 RS 계산"""
    cache_key = f"rs_{market}_{limit}"
    cached = _cached(cache_key, 3600)  # 1시간 캐싱
    if cached:
        return cached

    stocks = []
    market_upper = market.upper()

    try:
        async with httpx.AsyncClient(timeout=30, headers=NAVER_HEADERS) as client:
            # 시가총액 상위 종목 가져오기 (더 많이)
            markets_to_fetch = []
            if market_upper in ["ALL", "KOSPI"]:
                markets_to_fetch.append(("KOSPI", "KOSPI"))
            if market_upper in ["ALL", "KOSDAQ"]:
                markets_to_fetch.append(("KOSDAQ", "KOSDAQ"))

            all_stocks = []
            for mkt_name, mkt_code in markets_to_fetch:
                try:
                    # 시총 상위 100개씩 (총 200개)
                    url = f"https://m.stock.naver.com/api/stocks/marketValue/{mkt_code}?page=1&pageSize=100"
                    r = await client.get(url)
                    if r.status_code == 200:
                        data = r.json()
                        items = data.get("stocks", [])
                        for item in items:
                            all_stocks.append({
                                "code": item.get("itemCode", ""),
                                "name": item.get("stockName", ""),
                                "market": mkt_name,
                                "price": _parse_price(item.get("closePrice", "0")),
                                "change": _parse_float(item.get("fluctuationsRatio", "0")),
                            })
                except Exception as e:
                    print(f"[DataProvider] RS {mkt_name} error: {e}")

            # 병렬로 차트 데이터 가져오기 (수익률 계산용)
            tasks = [_calculate_returns_from_chart(client, s["code"]) for s in all_stocks]
            returns_data = await asyncio.gather(*tasks, return_exceptions=True)

            # 수익률 데이터 매핑
            for i, stock in enumerate(all_stocks):
                ret_data = returns_data[i]
                if isinstance(ret_data, Exception):
                    stock["ret_1m"] = 0
                    stock["ret_3m"] = 0
                    stock["ret_6m"] = 0
                else:
                    stock["ret_1m"] = ret_data.get("ret_1m", 0)
                    stock["ret_3m"] = ret_data.get("ret_3m", 0)
                    stock["ret_6m"] = ret_data.get("ret_6m", 0)

            # 백분위 RS 계산
            n = len(all_stocks)
            if n > 0:
                # 각 기간별로 정렬 후 백분위 할당
                sorted_1m = sorted(all_stocks, key=lambda x: x["ret_1m"])
                sorted_3m = sorted(all_stocks, key=lambda x: x["ret_3m"])
                sorted_6m = sorted(all_stocks, key=lambda x: x["ret_6m"])

                for i, s in enumerate(sorted_1m):
                    s["rs_1m"] = max(1, min(99, int((i + 1) / n * 99)))
                for i, s in enumerate(sorted_3m):
                    s["rs_3m"] = max(1, min(99, int((i + 1) / n * 99)))
                for i, s in enumerate(sorted_6m):
                    s["rs_6m"] = max(1, min(99, int((i + 1) / n * 99)))

                # 종합 RS 계산 (1개월 40%, 3개월 30%, 6개월 30%)
                for s in all_stocks:
                    s["rs_total"] = int(s["rs_1m"] * 0.4 + s["rs_3m"] * 0.3 + s["rs_6m"] * 0.3)

            # RS 순위로 정렬
            all_stocks.sort(key=lambda x: x["rs_total"], reverse=True)

            # 결과 정리
            for stock in all_stocks[:limit]:
                stocks.append({
                    "code": stock["code"],
                    "name": stock["name"],
                    "market": stock["market"],
                    "price": int(stock["price"]),
                    "change": round(stock["change"], 2),
                    "rs_total": stock["rs_total"],
                    "rs_1m": stock["rs_1m"],
                    "rs_3m": stock["rs_3m"],
                    "rs_6m": stock["rs_6m"]
                })

        _set_cache(cache_key, stocks)
        return stocks

    except Exception as e:
        print(f"[DataProvider] RS ranking error: {e}")
        traceback.print_exc()
        return []


async def _calculate_returns_from_chart(client, code):
    """일봉 차트 데이터에서 수익률 계산 (네이버 fchart API)"""
    try:
        # 네이버 일봉 차트 API (XML 형식)
        url = f"https://fchart.stock.naver.com/sise.nhn?symbol={code}&timeframe=day&count=150&requestType=0"
        r = await client.get(url)

        if r.status_code == 200:
            text = r.text
            # XML에서 종가 추출: <item data="날짜|시가|고가|저가|종가|거래량" />
            import re
            pattern = r'data="(\d+)\|(\d+)\|(\d+)\|(\d+)\|(\d+)\|(\d+)"'
            matches = re.findall(pattern, text)

            if len(matches) >= 10:
                # 종가 리스트 (index 4가 종가)
                prices = [int(m[4]) for m in matches]
                current = prices[-1]
                total_days = len(prices)

                # 1개월 (20거래일)
                idx_1m = min(20, total_days - 1)
                price_1m = prices[-(idx_1m + 1)] if idx_1m + 1 <= total_days else prices[0]
                ret_1m = (current / price_1m - 1) * 100 if price_1m > 0 else 0

                # 3개월 (60거래일)
                idx_3m = min(60, total_days - 1)
                price_3m = prices[-(idx_3m + 1)] if idx_3m + 1 <= total_days else prices[0]
                ret_3m = (current / price_3m - 1) * 100 if price_3m > 0 else 0

                # 6개월 (120거래일)
                idx_6m = min(120, total_days - 1)
                price_6m = prices[-(idx_6m + 1)] if idx_6m + 1 <= total_days else prices[0]
                ret_6m = (current / price_6m - 1) * 100 if price_6m > 0 else 0

                return {"ret_1m": ret_1m, "ret_3m": ret_3m, "ret_6m": ret_6m}
    except Exception as e:
        print(f"[DataProvider] Returns calc error for {code}: {e}")

    return {"ret_1m": 0, "ret_3m": 0, "ret_6m": 0}


# ===== 52주 신고가 =====

async def _fetch_stock_integration(client, code):
    """개별 종목 integration API에서 상세 정보 조회"""
    try:
        url = f"https://m.stock.naver.com/api/stock/{code}/integration"
        r = await client.get(url)
        if r.status_code == 200:
            data = r.json()
            result = {"code": code}
            for info in data.get("totalInfos", []):
                key = info.get("code", "")
                value = info.get("value", "0")
                if key == "highPriceOf52Weeks":
                    result["high_52w"] = _parse_price(value)
                elif key == "lowPriceOf52Weeks":
                    result["low_52w"] = _parse_price(value)
                elif key == "per":
                    result["per"] = _parse_float(value.replace("배", ""))
                elif key == "pbr":
                    result["pbr"] = _parse_float(value.replace("배", ""))
            return result
    except Exception as e:
        print(f"[DataProvider] Integration error for {code}: {e}")
    return {"code": code, "high_52w": 0, "low_52w": 0, "per": 0, "pbr": 0}


async def get_new_high_stocks(limit=50):
    """52주 신고가 종목 - 네이버 API (integration 사용)"""
    cached = _cached("new_high", 3600)  # 1시간 캐싱
    if cached:
        return cached

    results = []
    stocks_to_check = []

    try:
        async with httpx.AsyncClient(timeout=30, headers=NAVER_HEADERS) as client:
            # KOSPI/KOSDAQ 시가총액 상위 50개씩 가져오기
            for market in ["KOSPI", "KOSDAQ"]:
                try:
                    url = f"https://m.stock.naver.com/api/stocks/marketValue/{market}?page=1&pageSize=50"
                    r = await client.get(url)
                    if r.status_code == 200:
                        data = r.json()
                        items = data.get("stocks", [])
                        for item in items:
                            stocks_to_check.append({
                                "code": item.get("itemCode", ""),
                                "name": item.get("stockName", ""),
                                "price": _parse_price(item.get("closePrice", "0")),
                                "change": _parse_float(item.get("fluctuationsRatio", "0")),
                                "market_cap": _parse_int(item.get("marketValue", "0")),
                                "market": market
                            })
                except Exception as e:
                    print(f"[DataProvider] New high list {market} error: {e}")

            # 상위 60개만 상세 조회 (속도)
            stocks_to_check = stocks_to_check[:60]

            # 병렬로 integration API 호출
            tasks = [_fetch_stock_integration(client, s["code"]) for s in stocks_to_check]
            integration_data = await asyncio.gather(*tasks, return_exceptions=True)

            for i, stock in enumerate(stocks_to_check):
                int_data = integration_data[i]
                if isinstance(int_data, Exception):
                    continue

                high_52w = int_data.get("high_52w", 0)
                if high_52w > 0 and stock["price"] > 0:
                    distance = round((stock["price"] / high_52w - 1) * 100, 2)

                    # 52주 고가의 90% 이상인 종목만 (-10% 이상)
                    if distance >= -10:
                        results.append({
                            "code": stock["code"],
                            "name": stock["name"],
                            "price": int(stock["price"]),
                            "change": stock["change"],
                            "high_52w": int(high_52w),
                            "distance": distance,
                            "market_cap": stock["market_cap"]
                        })

        # 고가 근접순 정렬
        results.sort(key=lambda x: x["distance"], reverse=True)
        results = results[:limit]

        _set_cache("new_high", results)
        return results

    except Exception as e:
        print(f"[DataProvider] New high error: {e}")
        traceback.print_exc()
        return []


# ===== 밸류에이션 =====

async def get_valuation(market="ALL", limit=200):
    """PER/PBR 밸류에이션 - 네이버 API (integration 사용)"""
    cache_key = f"valuation_{market}"
    cached = _cached(cache_key, 3600)  # 1시간 캐싱
    if cached:
        return cached

    results = []
    stocks_to_check = []
    market_upper = market.upper()

    try:
        async with httpx.AsyncClient(timeout=30, headers=NAVER_HEADERS) as client:
            markets_to_fetch = []
            if market_upper in ["ALL", "KOSPI"]:
                markets_to_fetch.append("KOSPI")
            if market_upper in ["ALL", "KOSDAQ"]:
                markets_to_fetch.append("KOSDAQ")

            # 시가총액 상위 종목 목록 가져오기
            for mkt in markets_to_fetch:
                try:
                    url = f"https://m.stock.naver.com/api/stocks/marketValue/{mkt}?page=1&pageSize=60"
                    r = await client.get(url)
                    if r.status_code == 200:
                        data = r.json()
                        items = data.get("stocks", [])
                        for item in items:
                            stocks_to_check.append({
                                "code": item.get("itemCode", ""),
                                "name": item.get("stockName", ""),
                                "price": _parse_price(item.get("closePrice", "0")),
                                "market_cap": _parse_int(item.get("marketValue", "0")),
                                "market": mkt
                            })
                except Exception as e:
                    print(f"[DataProvider] Valuation list {mkt} error: {e}")

            # 상위 80개만 상세 조회 (속도)
            stocks_to_check = sorted(stocks_to_check, key=lambda x: x["market_cap"], reverse=True)[:80]

            # 병렬로 integration API 호출
            tasks = [_fetch_stock_integration(client, s["code"]) for s in stocks_to_check]
            integration_data = await asyncio.gather(*tasks, return_exceptions=True)

            for i, stock in enumerate(stocks_to_check):
                int_data = integration_data[i]
                if isinstance(int_data, Exception):
                    continue

                per = int_data.get("per", 0)
                pbr = int_data.get("pbr", 0)

                results.append({
                    "code": stock["code"],
                    "name": stock["name"],
                    "price": int(stock["price"]),
                    "per": per if per > 0 else 0,
                    "pbr": pbr if pbr > 0 else 0,
                    "market_cap": stock["market_cap"],
                    "market": stock["market"]
                })

        # PER 낮은 순 정렬 (0 제외하고 정렬)
        with_per = [r for r in results if r["per"] > 0]
        without_per = [r for r in results if r["per"] == 0]
        with_per.sort(key=lambda x: x["per"])
        results = with_per + without_per
        results = results[:limit]

        _set_cache(cache_key, results)
        return results

    except Exception as e:
        print(f"[DataProvider] Valuation error: {e}")
        traceback.print_exc()
        return []


# ===== ETF =====

async def get_etf_overview():
    """ETF 시세 - 주요 ETF 개별 조회"""
    cached = _cached("etf_overview", 1800)
    if cached:
        return cached

    # 주요 ETF 코드 목록 (섹터별)
    ETF_LIST = {
        "반도체": ["091160", "091170", "395160", "395170"],  # KODEX 반도체, TIGER 반도체 등
        "2차전지": ["305720", "371460", "305540", "373220"],  # KODEX 2차전지, TIGER 2차전지 등
        "AI": ["418660", "460850", "474220"],  # KODEX AI, TIGER AI 등
        "바이오": ["143860", "227540", "203780"],  # KODEX 헬스케어, TIGER 헬스케어 등
        "배당": ["161510", "148020", "278530"],  # KODEX 고배당, TIGER 배당 등
        "해외(미국)": ["360750", "133690", "379810", "379800", "261240"],  # TIGER 미국S&P500, 나스닥 등
        "기타": ["069500", "102110", "114800", "252670", "278240"]  # KODEX 200, TIGER 200 등
    }

    sector_etfs = {k: [] for k in ETF_LIST.keys()}
    all_etfs = []

    try:
        async with httpx.AsyncClient(timeout=15, headers=NAVER_HEADERS) as client:
            for sector, codes in ETF_LIST.items():
                for code in codes:
                    try:
                        url = f"https://m.stock.naver.com/api/stock/{code}/basic"
                        r = await client.get(url)
                        if r.status_code == 200:
                            data = r.json()
                            name = data.get("stockName", "")
                            close_str = data.get("closePrice", "0")
                            change_str = data.get("fluctuationsRatio", "0")
                            volume_str = data.get("accumulatedTradingVolume", "0")
                            
                            close_price = _parse_price(close_str)
                            change_pct = _parse_float(change_str)
                            volume = _parse_int(volume_str)
                            
                            etf_item = {
                                "code": code,
                                "name": name,
                                "price": int(close_price),
                                "change_percent": change_pct,
                                "volume": volume,
                                "sector": sector
                            }
                            sector_etfs[sector].append(etf_item)
                            all_etfs.append(etf_item)
                    except Exception as e:
                        print(f"[DataProvider] ETF {code} error: {e}")
                        
    except Exception as e:
        print(f"[DataProvider] ETF overview error: {e}")
        traceback.print_exc()

    result = {"sectors": sector_etfs, "all": all_etfs}
    _set_cache("etf_overview", result)
    return result

# ===== 해외 시장 =====

async def get_us_market_overview():
    """해외 시장 개요 - Yahoo Finance 직접 API"""
    cached = _cached("us_overview", 600)
    if cached:
        return cached

    result = {"indices": [], "stocks": [], "success": True}
    
    YAHOO_HEADERS = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    }
    
    indices_info = [("^GSPC", "S&P 500"), ("^IXIC", "나스닥"), ("^DJI", "다우존스"), ("^RUT", "러셀2000")]
    top_symbols = ["AAPL", "MSFT", "NVDA", "GOOGL", "AMZN", "META", "TSLA", "BRK-B", "JPM", "V",
                   "UNH", "MA", "HD", "PG", "COST", "ABBV", "CRM", "AVGO", "NFLX", "AMD"]
    
    try:
        async with httpx.AsyncClient(timeout=15, headers=YAHOO_HEADERS) as client:
            # 지수 데이터
            for symbol, name in indices_info:
                try:
                    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}?interval=1d&range=2d"
                    r = await client.get(url)
                    if r.status_code == 200:
                        data = r.json()
                        chart_result = data.get("chart", {}).get("result", [])
                        if chart_result:
                            meta = chart_result[0].get("meta", {})
                            price = meta.get("regularMarketPrice", 0)
                            prev = meta.get("chartPreviousClose", 0)
                            change = price - prev if prev else 0
                            change_pct = (change / prev * 100) if prev else 0
                            result["indices"].append({
                                "name": name,
                                "current": round(price, 2),
                                "change": round(change, 2),
                                "change_percent": round(change_pct, 2)
                            })
                        else:
                            result["indices"].append({"name": name, "current": 0, "change": 0, "change_percent": 0})
                    else:
                        result["indices"].append({"name": name, "current": 0, "change": 0, "change_percent": 0})
                except Exception as e:
                    print(f"[DataProvider] US index {symbol} error: {e}")
                    result["indices"].append({"name": name, "current": 0, "change": 0, "change_percent": 0})
            
            # 주요 종목 데이터
            for symbol in top_symbols:
                try:
                    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}?interval=1d&range=2d"
                    r = await client.get(url)
                    if r.status_code == 200:
                        data = r.json()
                        chart_result = data.get("chart", {}).get("result", [])
                        if chart_result:
                            meta = chart_result[0].get("meta", {})
                            price = meta.get("regularMarketPrice", 0)
                            prev = meta.get("chartPreviousClose", 0)
                            volume = meta.get("regularMarketVolume", 0)
                            change_pct = ((price - prev) / prev * 100) if prev else 0
                            result["stocks"].append({
                                "symbol": symbol,
                                "name": meta.get("shortName", symbol),
                                "price": round(price, 2),
                                "change_percent": round(change_pct, 2),
                                "volume": volume
                            })
                        else:
                            result["stocks"].append({"symbol": symbol, "price": 0, "change_percent": 0, "volume": 0})
                    else:
                        result["stocks"].append({"symbol": symbol, "price": 0, "change_percent": 0, "volume": 0})
                except Exception as e:
                    print(f"[DataProvider] US stock {symbol} error: {e}")
                    result["stocks"].append({"symbol": symbol, "price": 0, "change_percent": 0, "volume": 0})
                    
    except Exception as e:
        print(f"[DataProvider] US overview error: {e}")
        result["success"] = False

    _set_cache("us_overview", result)
    return result

# ===== 코인 =====

async def get_crypto_overview():
    """코인 시장 개요"""
    cached = _cached("crypto_overview", 60)
    if cached:
        return cached

    try:
        result = {}
        async with httpx.AsyncClient(timeout=10) as client:
            # Binance 시세
            try:
                r = await client.get("https://api.binance.com/api/v3/ticker/24hr")
                if r.status_code == 200:
                    data = r.json()
                    main_coins = {s["symbol"]: s for s in data if s["symbol"] in
                                  ["BTCUSDT","ETHUSDT","XRPUSDT","SOLUSDT","DOGEUSDT","ADAUSDT","AVAXUSDT","DOTUSDT","LINKUSDT","MATICUSDT"]}
                    result["binance"] = [{
                        "symbol": k.replace("USDT",""),
                        "price": float(v["lastPrice"]),
                        "change_24h": float(v["priceChangePercent"]),
                        "volume": float(v["quoteVolume"]),
                        "exchange": "binance"
                    } for k, v in main_coins.items()]
                else:
                    result["binance"] = []
            except Exception as e:
                print(f"[DataProvider] Binance error: {e}")
                result["binance"] = []

            # Upbit 시세
            try:
                r = await client.get("https://api.upbit.com/v1/ticker?markets=KRW-BTC,KRW-ETH,KRW-XRP,KRW-SOL,KRW-DOGE")
                if r.status_code == 200:
                    data = r.json()
                    result["upbit"] = [{
                        "symbol": d["market"].replace("KRW-",""),
                        "price": float(d["trade_price"]),
                        "change_24h": float(d["signed_change_rate"]) * 100,
                        "volume": float(d["acc_trade_price_24h"]),
                        "exchange": "upbit"
                    } for d in data]
                else:
                    result["upbit"] = []
            except Exception as e:
                print(f"[DataProvider] Upbit error: {e}")
                result["upbit"] = []

            # BTC 도미넌스 (CoinGecko)
            try:
                r = await client.get("https://api.coingecko.com/api/v3/global")
                if r.status_code == 200:
                    data = r.json()["data"]
                    result["btc_dominance"] = round(data["market_cap_percentage"]["btc"], 2)
                    result["total_market_cap"] = int(data["total_market_cap"]["usd"])
                else:
                    result["btc_dominance"] = 0
                    result["total_market_cap"] = 0
            except:
                result["btc_dominance"] = 0
                result["total_market_cap"] = 0

            # 김치 프리미엄 계산
            try:
                if result.get("binance") and result.get("upbit"):
                    btc_usd = next((c["price"] for c in result["binance"] if c["symbol"] == "BTC"), 0)
                    btc_krw = next((c["price"] for c in result["upbit"] if c["symbol"] == "BTC"), 0)
                    if btc_usd > 0:
                        r = await client.get("https://api.exchangerate-api.com/v4/latest/USD")
                        usd_krw = r.json()["rates"]["KRW"] if r.status_code == 200 else 1450
                        result["kimchi_premium"] = round((btc_krw / (btc_usd * usd_krw) - 1) * 100, 2)
                    else:
                        result["kimchi_premium"] = 0
                else:
                    result["kimchi_premium"] = 0
            except:
                result["kimchi_premium"] = 0

        _set_cache("crypto_overview", result)
        return result
    except Exception as e:
        print(f"[DataProvider] Crypto error: {e}")
        return {"binance": [], "upbit": [], "btc_dominance": 0, "total_market_cap": 0, "kimchi_premium": 0}


# ===== 개별 종목 =====

async def get_stock_detail(code):
    """개별 종목 상세 - 네이버 API"""
    try:
        async with httpx.AsyncClient(timeout=10, headers=NAVER_HEADERS) as client:
            url = f"https://m.stock.naver.com/api/stock/{code}/basic"
            r = await client.get(url)

            if r.status_code == 200:
                data = r.json()
                return {
                    "code": code,
                    "name": data.get("stockName", f"종목{code}"),
                    "close": _parse_price(data.get("closePrice", "0")),
                    "open": _parse_price(data.get("openPrice", "0")),
                    "high": _parse_price(data.get("highPrice", "0")),
                    "low": _parse_price(data.get("lowPrice", "0")),
                    "volume": _parse_int(data.get("accumulatedTradingVolume", "0")),
                    "change": _parse_price(data.get("compareToPreviousClosePrice", "0")),
                    "change_percent": _parse_float(data.get("fluctuationsRatio", "0")),
                    "per": _parse_float(data.get("per", "0")),
                    "pbr": _parse_float(data.get("pbr", "0")),
                    "market_cap": _parse_int(data.get("marketValue", "0")),
                    "sector": data.get("industryName", "")
                }
    except Exception as e:
        print(f"[DataProvider] Stock detail error for {code}: {e}")

    # 기본값 반환
    return {
        "code": code,
        "name": f"종목{code}",
        "close": 0,
        "open": 0,
        "high": 0,
        "low": 0,
        "volume": 0,
        "change": 0,
        "change_percent": 0,
        "per": 0,
        "pbr": 0,
        "market_cap": 0,
        "sector": ""
    }


async def get_chart_data(code, period="3m"):
    """차트 데이터 - 네이버 API"""
    try:
        async with httpx.AsyncClient(timeout=10, headers=NAVER_HEADERS) as client:
            period_map = {"1d": 1, "1w": 7, "1m": 30, "3m": 90, "6m": 180, "1y": 365}
            days = period_map.get(period, 90)

            today = datetime.now()
            start_date = (today - timedelta(days=days)).strftime("%Y%m%d")
            end_date = today.strftime("%Y%m%d")

            url = f"https://api.stock.naver.com/chart/domestic/item/{code}?periodType=day&startDateTime={start_date}&endDateTime={end_date}"
            r = await client.get(url)

            if r.status_code == 200:
                data = r.json()
                result = []
                for d in data:
                    result.append({
                        "date": d.get("localDate", ""),
                        "open": int(_parse_price(d.get("openPrice", "0"))),
                        "high": int(_parse_price(d.get("highPrice", "0"))),
                        "low": int(_parse_price(d.get("lowPrice", "0"))),
                        "close": int(_parse_price(d.get("closePrice", "0"))),
                        "volume": _parse_int(d.get("accumulatedTradingVolume", "0"))
                    })
                return result
    except Exception as e:
        print(f"[DataProvider] Chart error for {code}: {e}")

    # 빈 배열 반환
    return []

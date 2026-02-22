"""
BBooster 데이터 제공 모듈
네이버 모바일 API + 코인거래소 API
"""
import asyncio
from datetime import datetime, timedelta
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

            # 업종별 현황 (HTML 파싱) - 전체 섹터 반환 (상승+하락 모두)
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
                                # 등락률 파싱: +, - 부호 유지
                                change_pct_str = cells[1].get_text(strip=True).replace("%", "").replace("+", "").strip()
                                try:
                                    change_val = float(change_pct_str) if change_pct_str else 0
                                    sectors.append({"name": name, "change_percent": change_val, "volume": 0})
                                except:
                                    pass
                    # 전체 섹터 반환 (등락률 순 정렬)
                    sectors.sort(key=lambda x: x["change_percent"], reverse=True)
                    result["sectors"] = sectors  # 전체 반환 (상위 15개 제한 제거)
                    print(f"[DataProvider] 섹터 {len(sectors)}개 로드 (양수: {len([s for s in sectors if s['change_percent'] > 0])}, 음수: {len([s for s in sectors if s['change_percent'] < 0])})")
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
                                "volume": _parse_int(item.get("accumulatedTradingVolume", "0")),
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
                            "market_cap": stock["market_cap"],
                            "volume": stock.get("volume", 0)
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
    """ETF 시장 현황 - 네이버 금융 ETF 전체 목록 + 테마 분류"""
    cached = _cached("etf_overview", 600)  # 10분 캐시
    if cached:
        return cached

    # === 테마 분류를 위한 키워드 매핑 (26개 테마) ===
    THEME_KEYWORDS = {
        "반도체": ["반도체", "SOX", "필라델피아반도체", "semiconductor", "HBM"],
        "AI": ["AI", "인공지능", "ChatGPT", "빅데이터", "클라우드"],
        "로봇": ["로봇", "자율주행", "드론", "UAM", "로보틱스"],
        "2차전지": ["2차전지", "배터리", "리튬", "에코프로", "전기차", "EV"],
        "바이오": ["바이오", "헬스케어", "제약", "게놈", "의료기기", "신약"],
        "금융": ["금융", "은행", "증권", "보험", "금융지주"],
        "에너지": ["에너지", "원유", "천연가스", "신재생", "태양광", "풍력"],
        "원자력": ["원자력", "우라늄", "원전", "SMR"],
        "우주항공": ["우주", "항공", "방산", "K방산", "국방"],
        "배당": ["배당", "고배당", "월배당", "커버드콜", "인컴", "KOFR"],
        "미국지수": ["S&P", "나스닥", "미국", "다우", "Russell"],
        "중국": ["중국", "차이나", "CSI", "항셍", "HSCEI"],
        "인도·신흥": ["인도", "베트남", "신흥", "이머징", "브라질"],
        "금·원자재": ["금", "골드", "은", "원자재", "구리", "팔라듐", "백금"],
        "채권": ["채권", "국채", "회사채", "단기채", "장기채", "CD금리", "통안채"],
        "리츠": ["리츠", "부동산", "REITs", "오피스"],
        "인버스": ["인버스", "곱버스", "숏", "베어"],
        "레버리지": ["레버리지", "2X", "3X", "불"],
        "게임·미디어": ["게임", "엔터", "미디어", "콘텐츠", "K-POP"],
        "자동차": ["자동차", "모빌리티", "현대차"],
        "건설·인프라": ["건설", "인프라", "SOC"],
        "철강·소재": ["철강", "소재", "화학", "정유"],
        "식품": ["식품", "음식", "농산물"],
        "우선주": ["우선주", "프리미엄"],
        "명품": ["명품", "럭셔리", "글로벌브랜드"],
        "AI전력": ["AI전력", "전력인프라", "데이터센터", "전력설비"],
    }

    def classify_theme(name):
        """ETF 이름으로 테마 분류"""
        for theme, keywords in THEME_KEYWORDS.items():
            for kw in keywords:
                if kw in name:
                    return theme
        return "기타"

    def classify_asset_type(name, etf_type):
        """ETF를 주식/채권/원자재/기타로 분류"""
        if etf_type == 6:  # 채권
            return "채권"
        if etf_type == 5:  # 원자재
            return "원자재"
        bond_keywords = ["채권", "국채", "회사채", "CD금리", "단기", "머니마켓", "KOFR", "통안", "금리"]
        commodity_keywords = ["금", "골드", "은", "원유", "천연가스", "원자재", "구리", "팔라듐", "농산물"]
        for kw in bond_keywords:
            if kw in name:
                return "채권"
        for kw in commodity_keywords:
            if kw in name:
                return "원자재"
        return "주식"

    all_etfs = []
    seen_codes = set()  # 중복 방지

    try:
        async with httpx.AsyncClient(timeout=20, headers=NAVER_HEADERS) as client:
            # 네이버 ETF 시세 API (etfType=0이 전체 목록)
            for etf_type in [0]:
                try:
                    url = f"https://finance.naver.com/api/sise/etfItemList.nhn?etfType={etf_type}"
                    r = await client.get(url, headers={
                        "Referer": "https://finance.naver.com/sise/etf.naver",
                        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
                    })
                    if r.status_code == 200:
                        # 네이버 금융 API는 EUC-KR 인코딩
                        try:
                            text = r.content.decode('euc-kr')
                        except:
                            text = r.content.decode('cp949', errors='ignore')
                        data = json.loads(text)
                        items = data.get("result", {}).get("etfItemList", [])
                        for item in items:
                            code = str(item.get("itemcode", ""))
                            name = item.get("itemname", "")
                            if not code or not name:
                                continue
                            if code in seen_codes:
                                continue
                            seen_codes.add(code)

                            close_price = int(item.get("nowVal", 0) or 0)
                            change_val = int(item.get("changeVal", 0) or 0)
                            change_rate = float(item.get("changeRate", 0) or 0)
                            volume = int(item.get("quant", 0) or 0)
                            market_sum = int(item.get("marketSum", 0) or 0)
                            nav = int(item.get("nav", 0) or 0)

                            theme = classify_theme(name)
                            asset_type = classify_asset_type(name, 0)

                            all_etfs.append({
                                "code": code,
                                "name": name,
                                "price": close_price,
                                "change_val": change_val,
                                "change_pct": change_rate,
                                "volume": volume,
                                "market_sum": market_sum,
                                "nav": nav,
                                "theme": theme,
                                "asset_type": asset_type,
                                "etf_type": etf_type,
                            })
                except Exception as e:
                    print(f"[ETF] type={etf_type} error: {e}")
                    continue

            # Fallback: 방법 1 실패 시 개별 ETF 조회
            if len(all_etfs) < 50:
                print("[ETF] API 방식 실패, 주요 ETF 개별 조회로 fallback")
                MAJOR_ETFS = [
                    "069500", "102110", "252670", "114800", "360750", "133690",
                    "379810", "379800", "261240", "091160", "395160", "446720",
                    "305720", "371460", "418660", "474220", "143860", "227540",
                    "161510", "148020", "449170", "278530", "234310", "453810",
                ]
                all_etfs = []
                seen_codes = set()
                for code in MAJOR_ETFS:
                    if code in seen_codes:
                        continue
                    seen_codes.add(code)
                    try:
                        url = f"https://m.stock.naver.com/api/stock/{code}/basic"
                        r = await client.get(url)
                        if r.status_code == 200:
                            d = r.json()
                            if d.get("stockEndType") != "etf":
                                continue
                            name = d.get("stockName", "")
                            close_price = _parse_price(d.get("closePrice", "0"))
                            change_pct = _parse_float(d.get("fluctuationsRatio", "0"))
                            volume = _parse_int(d.get("accumulatedTradingVolume", "0"))

                            all_etfs.append({
                                "code": code,
                                "name": name,
                                "price": int(close_price),
                                "change_val": 0,
                                "change_pct": change_pct,
                                "volume": volume,
                                "market_sum": 0,
                                "nav": 0,
                                "theme": classify_theme(name),
                                "asset_type": classify_asset_type(name, 0),
                                "etf_type": 0,
                            })
                    except Exception as e:
                        print(f"[ETF] {code} error: {e}")

    except Exception as e:
        print(f"[ETF] overview error: {e}")
        traceback.print_exc()

    # === 테마별 집계 ===
    theme_map = {}
    for etf in all_etfs:
        theme = etf["theme"]
        if theme not in theme_map:
            theme_map[theme] = {"name": theme, "etfs": [], "up": 0, "down": 0, "total_change": 0}
        theme_map[theme]["etfs"].append(etf)
        if etf["change_pct"] > 0:
            theme_map[theme]["up"] += 1
        elif etf["change_pct"] < 0:
            theme_map[theme]["down"] += 1
        theme_map[theme]["total_change"] += etf["change_pct"]

    themes = []
    for t in theme_map.values():
        count = len(t["etfs"])
        avg_change = round(t["total_change"] / count, 2) if count > 0 else 0
        top_etf = max(t["etfs"], key=lambda x: x["volume"]) if t["etfs"] else None
        themes.append({
            "name": t["name"],
            "avg_change": avg_change,
            "count": count,
            "up": t["up"],
            "down": t["down"],
            "top_etf_name": top_etf["name"] if top_etf else "",
            "top_etf_change": top_etf["change_pct"] if top_etf else 0,
        })

    # === 상승하락 분포 (ETFCheck 11개 빈) ===
    bin_defs = [
        ("-10%~",    lambda p: p <= -10, "down"),
        ("-10~-5%",  lambda p: -10 < p <= -5, "down"),
        ("-5~-3%",   lambda p: -5 < p <= -3, "down"),
        ("-3~-1%",   lambda p: -3 < p <= -1, "down"),
        ("-1~0%",    lambda p: -1 < p < -0.005, "down"),
        ("0",        lambda p: -0.005 <= p <= 0.005, "neutral"),
        ("0~1%",     lambda p: 0.005 < p < 1, "up"),
        ("1~3%",     lambda p: 1 <= p < 3, "up"),
        ("3~5%",     lambda p: 3 <= p < 5, "up"),
        ("5~10%",    lambda p: 5 <= p < 10, "up"),
        ("10%~",     lambda p: p >= 10, "up"),
    ]

    distribution = []
    for label, cond, dtype in bin_defs:
        count = sum(1 for e in all_etfs if cond(e["change_pct"]))
        distribution.append({"label": label, "count": count, "type": dtype})

    # === 정렬 + 중복 제거 ===
    def unique_by_code(items):
        """code 기준 중복 제거 (순서 유지)"""
        seen = set()
        result = []
        for e in items:
            if e['code'] not in seen:
                seen.add(e['code'])
                result.append(e)
        return result

    themes_up = sorted([t for t in themes if t["avg_change"] > 0], key=lambda x: x["avg_change"], reverse=True)
    themes_down = sorted([t for t in themes if t["avg_change"] <= 0], key=lambda x: x["avg_change"])
    top_by_return = unique_by_code(sorted(all_etfs, key=lambda x: x["change_pct"], reverse=True))[:10]
    bottom_by_return = unique_by_code(sorted(all_etfs, key=lambda x: x["change_pct"]))[:10]
    top_by_volume = unique_by_code(sorted(all_etfs, key=lambda x: x["volume"], reverse=True))[:10]
    top_by_market = unique_by_code(sorted(all_etfs, key=lambda x: x["market_sum"], reverse=True))[:10]

    # 주요 대표 ETF (ETFCheck 기준)
    MAJOR_CODES = [
        "069500", "360750", "459580", "379800", "133690",
        "102110", "379810", "091160", "161510", "305720"
    ]
    major_etfs = []
    major_seen = set()
    for code in MAJOR_CODES:
        for e in all_etfs:
            if e["code"] == code and code not in major_seen:
                major_seen.add(code)
                major_etfs.append(e)
                break

    total_up = sum(1 for e in all_etfs if e["change_pct"] > 0)
    total_down = sum(1 for e in all_etfs if e["change_pct"] < 0)

    # === 자산유형별 분류 ===
    by_asset = {"전체": all_etfs, "주식": [], "채권": [], "원자재": []}
    for e in all_etfs:
        at = e.get("asset_type", "주식")
        if at in by_asset:
            by_asset[at].append(e)

    # 자산유형별 분포 (11개 빈 - bin_defs 재사용)
    dist_by_asset = {}
    for asset_name, asset_etfs in by_asset.items():
        bins_arr = [sum(1 for e in asset_etfs if cond(e["change_pct"])) for _, cond, _ in bin_defs]
        dist_by_asset[asset_name] = bins_arr

    # 자산유형별 TOP (중복 제거 적용)
    top_return_by_asset = {}
    bottom_return_by_asset = {}
    top_volume_by_asset = {}
    top_market_by_asset = {}
    for asset_name, asset_etfs in by_asset.items():
        top_return_by_asset[asset_name] = unique_by_code(sorted(asset_etfs, key=lambda x: x["change_pct"], reverse=True))[:10]
        bottom_return_by_asset[asset_name] = unique_by_code(sorted(asset_etfs, key=lambda x: x["change_pct"]))[:10]
        top_volume_by_asset[asset_name] = unique_by_code(sorted(asset_etfs, key=lambda x: x["volume"], reverse=True))[:10]
        top_market_by_asset[asset_name] = unique_by_code(sorted(asset_etfs, key=lambda x: x["market_sum"], reverse=True))[:10]

    # 거래량 TOP3 (상승하락 섹션의 TOP3거래량 탭용)
    top3_volume = unique_by_code(sorted(all_etfs, key=lambda x: x["volume"], reverse=True))[:3]

    # 주요 종목 — 자산유형별 거래량 상위 10개씩
    major_by_asset = {}
    for asset_name in ["전체", "주식", "채권", "원자재"]:
        if asset_name == "전체":
            pool = all_etfs
        else:
            pool = [e for e in all_etfs if e.get("asset_type") == asset_name]
        top = unique_by_code(sorted(pool, key=lambda x: x["market_sum"], reverse=True))[:10]
        major_by_asset[asset_name] = top

    # sparkline 데이터 수집 — major_by_asset의 모든 고유 ETF에 대해
    all_major_etfs = {}
    for asset_name, items in major_by_asset.items():
        for e in items:
            if e["code"] not in all_major_etfs:
                all_major_etfs[e["code"]] = e

    try:
        async with httpx.AsyncClient(timeout=10, headers=NAVER_HEADERS) as client:
            for code, etf in all_major_etfs.items():
                try:
                    url = f"https://api.stock.naver.com/chart/domestic/item/{code}/minute?range=1"
                    r = await client.get(url)
                    if r.status_code == 200:
                        minutes = r.json()
                        prices = [m.get("currentPrice", 0) for m in minutes if m.get("currentPrice")]
                        if len(prices) > 40:
                            step = len(prices) // 40
                            prices = prices[::step]
                        etf["sparkline"] = prices
                    else:
                        etf["sparkline"] = []
                except:
                    etf["sparkline"] = []
    except:
        for etf in all_major_etfs.values():
            etf["sparkline"] = []

    result = {
        "total_count": len(all_etfs),
        "total_up": total_up,
        "total_down": total_down,
        "themes_up": themes_up,
        "themes_down": themes_down,
        "distribution": distribution,
        "dist_by_asset": dist_by_asset,
        "top_by_return": top_by_return,
        "bottom_by_return": bottom_by_return,
        "top_by_volume": top_by_volume,
        "top_by_market": top_by_market,
        "top_return_by_asset": top_return_by_asset,
        "bottom_return_by_asset": bottom_return_by_asset,
        "top_volume_by_asset": top_volume_by_asset,
        "top_market_by_asset": top_market_by_asset,
        "top3_volume": top3_volume,
        "major_etfs": major_etfs,
        "major_by_asset": major_by_asset,
        "success": True,
    }
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
    """개별 종목 상세 - 네이버 API + fchart(시가/고가/저가/거래량)"""
    import re
    result = {
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
    try:
        async with httpx.AsyncClient(timeout=10, headers=NAVER_HEADERS) as client:
            # 1. 기본 정보 (종목명, 종가, 변동, PER, PBR 등)
            url = f"https://m.stock.naver.com/api/stock/{code}/basic"
            r = await client.get(url)
            if r.status_code == 200:
                data = r.json()
                result["name"] = data.get("stockName", f"종목{code}")
                result["close"] = _parse_price(data.get("closePrice", "0"))
                result["change"] = _parse_price(data.get("compareToPreviousClosePrice", "0"))
                result["change_percent"] = _parse_float(data.get("fluctuationsRatio", "0"))
                result["per"] = _parse_float(data.get("per", "0"))
                result["pbr"] = _parse_float(data.get("pbr", "0"))
                result["market_cap"] = _parse_int(data.get("marketValue", "0"))
                result["sector"] = data.get("industryName", "")

            # 2. fchart에서 시가/고가/저가/거래량 (basic API에 없음)
            # count=2로 전일 데이터도 가져옴 (비거래일 대응)
            fchart_url = f"https://fchart.stock.naver.com/sise.nhn?symbol={code}&timeframe=day&count=2&requestType=0"
            fchart_r = await client.get(fchart_url)
            if fchart_r.status_code == 200:
                items = re.findall(r'<item data="([^"]+)"', fchart_r.text)
                if items:
                    parts = items[-1].split("|")  # 가장 최근 캔들
                    if len(parts) >= 6:
                        o, h, l, v = int(parts[1]), int(parts[2]), int(parts[3]), int(parts[5])
                        # 비거래일(토/일/공휴일)이면 시가=0 → 전일 데이터 사용
                        if o == 0 and len(items) >= 2:
                            prev = items[-2].split("|")
                            if len(prev) >= 6:
                                o, h, l, v = int(prev[1]), int(prev[2]), int(prev[3]), int(prev[5])
                        result["open"] = o
                        result["high"] = h
                        result["low"] = l
                        result["volume"] = v

            return result
    except Exception as e:
        print(f"[DataProvider] Stock detail error for {code}: {e}")
    return result


async def get_chart_data(code, period="3m"):
    """차트 데이터 - 네이버 fchart API (일봉)"""
    import re
    try:
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Referer": "https://finance.naver.com"
        }
        async with httpx.AsyncClient(timeout=15, headers=headers) as client:
            # 기간별 캔들 수 (SMA 200 계산을 위해 충분한 데이터)
            period_map = {
                "1d": 5, "1w": 7, "1m": 25, "3m": 70,
                "6m": 130, "1y": 260, "2y": 520, "3y": 780
            }
            count = period_map.get(period, 260)

            url = f"https://fchart.stock.naver.com/sise.nhn?symbol={code}&timeframe=day&count={count}&requestType=0"
            r = await client.get(url)

            if r.status_code == 200:
                # XML 파싱: <item data="20250919|81100|81200|79600|79700|20898386" />
                text = r.text
                items = re.findall(r'<item data="([^"]+)"', text)

                result = []
                for item in items:
                    parts = item.split("|")
                    if len(parts) >= 6:
                        result.append({
                            "date": parts[0],           # 20250919
                            "open": int(parts[1]),      # 시가
                            "high": int(parts[2]),      # 고가
                            "low": int(parts[3]),       # 저가
                            "close": int(parts[4]),     # 종가
                            "volume": int(parts[5])     # 거래량
                        })

                # 날짜순 정렬 (오래된 것 → 최신)
                result.sort(key=lambda x: x.get("date", ""))
                return result
    except Exception as e:
        print(f"[DataProvider] Chart error for {code}: {e}")
        import traceback
        traceback.print_exc()

    # 빈 배열 반환
    return []


# ===== 종목 상세 - 스탁이지 스타일 (Phase 1) =====

def _parse_korean_market_cap(value_str: str) -> int:
    """
    한글 시가총액 파싱: "938조 8,546억" → 원 단위
    """
    if not value_str:
        return 0
    try:
        value_str = value_str.replace(",", "").replace(" ", "")
        total = 0
        # 조 단위 추출
        if "조" in value_str:
            parts = value_str.split("조")
            total += int(parts[0]) * 1_0000_0000_0000  # 1조 = 10^12
            value_str = parts[1] if len(parts) > 1 else ""
        # 억 단위 추출
        if "억" in value_str:
            parts = value_str.split("억")
            total += int(parts[0]) * 100000000  # 1억 = 10^8
        return total
    except:
        return 0


async def get_stock_financial_summary(code: str):
    """
    종목 재무 요약 (요약 탭)
    - 네이버 모바일 API에서 매출액, 영업이익, EPS, PER, PBR 등
    - 네이버 데스크톱에서 ROE, 부채비율, 영업이익률 등 추가 수집
    """
    cache_key = f"fin_summary_{code}"
    cached = _cached(cache_key, 3600)
    if cached:
        return cached

    result = {
        "code": code,
        "name": "",
        "sector": "",
        "market": "",
        "market_cap": 0,
        "market_cap_formatted": "",
        "per": 0,
        "pbr": 0,
        "eps": 0,
        "bps": 0,
        "dividend_yield": 0,
        "roe": 0,
        "roa": 0,
        "debt_ratio": 0,
        "reserve_ratio": 0,
        "operating_margin": 0,
        "revenue": 0,
        "revenue_formatted": "",
        "revenue_growth": 0,
        "operating_profit": 0,
        "operating_profit_formatted": "",
        "operating_profit_growth": 0,
        "net_income": 0,
        "net_income_formatted": "",
        "high_52w": 0,
        "low_52w": 0,
        "foreign_ratio": 0,
        "target_price": 0,
        "recommendation": "",
    }

    try:
        async with httpx.AsyncClient(timeout=15, headers=NAVER_HEADERS) as client:
            # 1. 기본 정보 API
            r = await client.get(f"https://m.stock.naver.com/api/stock/{code}/basic")
            if r.status_code == 200:
                data = r.json()
                result["name"] = data.get("stockName", "")
                result["market"] = data.get("stockExchangeName", "")
                result["sector"] = data.get("industryName", "")

            # 2. Integration API (PER, PBR, 52주 고저, 시가총액, 외인비율, 배당률)
            r = await client.get(f"https://m.stock.naver.com/api/stock/{code}/integration")
            if r.status_code == 200:
                data = r.json()
                for info in data.get("totalInfos", []):
                    key = info.get("code", "")
                    value = info.get("value", "0")
                    if key == "per":
                        result["per"] = _parse_float(value.replace("배", ""))
                    elif key == "pbr":
                        result["pbr"] = _parse_float(value.replace("배", ""))
                    elif key == "eps":
                        result["eps"] = _parse_int(value.replace("원", "").replace(",", ""))
                    elif key == "bps":
                        result["bps"] = _parse_int(value.replace("원", "").replace(",", ""))
                    elif key == "dividendYieldRatio":  # 수정: dividendYield → dividendYieldRatio
                        result["dividend_yield"] = _parse_float(value.replace("%", ""))
                    elif key == "highPriceOf52Weeks":
                        result["high_52w"] = _parse_price(value)
                    elif key == "lowPriceOf52Weeks":
                        result["low_52w"] = _parse_price(value)
                    elif key == "foreignRate":  # 수정: foreignerRatio → foreignRate
                        result["foreign_ratio"] = _parse_float(value.replace("%", ""))
                    elif key == "marketValue":  # 시가총액 (예: "938조 8,546억")
                        result["market_cap"] = _parse_korean_market_cap(value)
                        result["market_cap_formatted"] = _format_korean_num(result["market_cap"])

                # 컨센서스 정보 (목표가, 투자의견)
                consensus = data.get("consensusInfo", {})
                if consensus:
                    result["target_price"] = _parse_int(consensus.get("priceTargetMean", "0"))
                    recomm = _parse_float(consensus.get("recommMean", "0"))
                    if recomm >= 4:
                        result["recommendation"] = "적극매수"
                    elif recomm >= 3.5:
                        result["recommendation"] = "매수"
                    elif recomm >= 2.5:
                        result["recommendation"] = "보유"
                    elif recomm >= 1.5:
                        result["recommendation"] = "비중축소"
                    else:
                        result["recommendation"] = "매도"

            # 3. 재무 정보 (Summary) - chartIncomeStatement 형식
            r = await client.get(f"https://m.stock.naver.com/api/stock/{code}/finance/summary")
            if r.status_code == 200:
                data = r.json()
                # chartIncomeStatement.annual.columns에서 최신 데이터 추출
                annual_data = data.get("chartIncomeStatement", {}).get("annual", {})
                columns = annual_data.get("columns", [])
                if len(columns) >= 3:
                    revenues = columns[1] if len(columns) > 1 else []
                    op_profits = columns[2] if len(columns) > 2 else []
                    # 최신 데이터 (마지막 값)
                    if len(revenues) > 1:
                        rev = _parse_int(revenues[-1]) * 100000000  # 억 단위 → 원
                        result["revenue"] = rev
                        result["revenue_formatted"] = _format_korean_num(rev)
                        # 매출 성장률 계산
                        if len(revenues) > 2:
                            prev_rev = _parse_int(revenues[-2])
                            if prev_rev > 0:
                                result["revenue_growth"] = round((_parse_int(revenues[-1]) - prev_rev) / prev_rev * 100, 1)
                    if len(op_profits) > 1:
                        op = _parse_int(op_profits[-1]) * 100000000
                        result["operating_profit"] = op
                        result["operating_profit_formatted"] = _format_korean_num(op)
                        # 영업이익 성장률 계산
                        if len(op_profits) > 2:
                            prev_op = _parse_int(op_profits[-2])
                            if prev_op > 0:
                                result["operating_profit_growth"] = round((_parse_int(op_profits[-1]) - prev_op) / prev_op * 100, 1)
                        # 영업이익률 계산
                        if result["revenue"] > 0:
                            result["operating_margin"] = round(op / result["revenue"] * 100, 2)

            # 4. 네이버 데스크톱 페이지에서 ROE, 부채비율 등 추가 크롤링
            try:
                desktop_headers = {
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                    "Accept-Language": "ko-KR,ko;q=0.9"
                }
                r = await client.get(f"https://finance.naver.com/item/main.naver?code={code}", headers=desktop_headers)
                if r.status_code == 200:
                    # EUC-KR 인코딩 처리
                    r.encoding = "euc-kr"
                    soup = BeautifulSoup(r.text, "lxml")

                    # ROE 파싱 (클래스 th_cop_anal13)
                    roe_th = soup.find("th", class_="th_cop_anal13")
                    if roe_th:
                        roe_tr = roe_th.find_parent("tr")
                        if roe_tr:
                            tds = roe_tr.find_all("td")
                            for td in tds:
                                txt = td.get_text(strip=True)
                                if txt and txt != "-":
                                    val = _parse_float(txt.replace(",", ""))
                                    if val != 0:
                                        result["roe"] = val
                                        break

                    # 부채비율 파싱 (클래스 th_cop_anal14)
                    debt_th = soup.find("th", class_="th_cop_anal14")
                    if debt_th:
                        debt_tr = debt_th.find_parent("tr")
                        if debt_tr:
                            tds = debt_tr.find_all("td")
                            for td in tds:
                                txt = td.get_text(strip=True)
                                if txt and txt != "-":
                                    val = _parse_float(txt.replace(",", ""))
                                    if val != 0:
                                        result["debt_ratio"] = val
                                        break

                    # 영업이익률 파싱 (클래스 th_cop_anal11)
                    opm_th = soup.find("th", class_="th_cop_anal11")
                    if opm_th:
                        opm_tr = opm_th.find_parent("tr")
                        if opm_tr:
                            tds = opm_tr.find_all("td")
                            for td in tds:
                                txt = td.get_text(strip=True)
                                if txt and txt != "-":
                                    val = _parse_float(txt.replace(",", ""))
                                    if val != 0 and result["operating_margin"] == 0:
                                        result["operating_margin"] = val
                                        break

                    # 유보율 파싱 (클래스 th_cop_anal16)
                    rsv_th = soup.find("th", class_="th_cop_anal16")
                    if rsv_th:
                        rsv_tr = rsv_th.find_parent("tr")
                        if rsv_tr:
                            tds = rsv_tr.find_all("td")
                            for td in tds:
                                txt = td.get_text(strip=True)
                                if txt and txt != "-":
                                    val = _parse_float(txt.replace(",", ""))
                                    if val != 0:
                                        result["reserve_ratio"] = val
                                        break

            except Exception as e2:
                print(f"[DataProvider] Desktop scraping error for {code}: {e2}")

        _set_cache(cache_key, result)
        return result

    except Exception as e:
        print(f"[DataProvider] Financial summary error for {code}: {e}")
        traceback.print_exc()
        return result


async def get_stock_financial_trend(code: str):
    """
    종목 실적 추이 (재무 탭)
    - 분기별/연간별 매출액, 영업이익, 당기순이익
    """
    cache_key = f"fin_trend_{code}"
    cached = _cached(cache_key, 3600)
    if cached:
        return cached

    result = {
        "annual": [],
        "quarter": []
    }

    try:
        async with httpx.AsyncClient(timeout=15, headers=NAVER_HEADERS) as client:
            # 네이버 finance/summary API
            r = await client.get(f"https://m.stock.naver.com/api/stock/{code}/finance/summary")
            if r.status_code == 200:
                data = r.json()
                income_stmt = data.get("chartIncomeStatement", {})
                eps_data = data.get("chartEps", {})

                # 연간 데이터 파싱
                annual_cols = income_stmt.get("annual", {}).get("columns", [])
                annual_titles = income_stmt.get("annual", {}).get("trTitleList", [])
                if len(annual_cols) >= 3:
                    periods = annual_cols[0][1:] if annual_cols else []
                    revenues = annual_cols[1][1:] if len(annual_cols) > 1 else []
                    op_profits = annual_cols[2][1:] if len(annual_cols) > 2 else []
                    for i, period in enumerate(periods):
                        is_consensus = annual_titles[i].get("isConsensus", "N") == "Y" if i < len(annual_titles) else False
                        result["annual"].append({
                            "period": period,
                            "revenue": _parse_int(revenues[i]) * 100000000 if i < len(revenues) else 0,
                            "operating_profit": _parse_int(op_profits[i]) * 100000000 if i < len(op_profits) else 0,
                            "is_estimate": is_consensus
                        })

                # 분기 데이터 파싱
                quarter_cols = income_stmt.get("quarter", {}).get("columns", [])
                quarter_titles = income_stmt.get("quarter", {}).get("trTitleList", [])
                if len(quarter_cols) >= 3:
                    periods = quarter_cols[0][1:] if quarter_cols else []
                    revenues = quarter_cols[1][1:] if len(quarter_cols) > 1 else []
                    op_profits = quarter_cols[2][1:] if len(quarter_cols) > 2 else []
                    for i, period in enumerate(periods):
                        is_consensus = quarter_titles[i].get("isConsensus", "N") == "Y" if i < len(quarter_titles) else False
                        result["quarter"].append({
                            "period": period,
                            "revenue": _parse_int(revenues[i]) * 100000000 if i < len(revenues) else 0,
                            "operating_profit": _parse_int(op_profits[i]) * 100000000 if i < len(op_profits) else 0,
                            "is_estimate": is_consensus
                        })

                # EPS 데이터 추가
                eps_cols = eps_data.get("columns", [])
                if len(eps_cols) >= 2:
                    eps_periods = eps_cols[0][1:] if eps_cols else []
                    eps_values = eps_cols[1][1:] if len(eps_cols) > 1 else []
                    result["eps_trend"] = [
                        {"period": eps_periods[i], "eps": _parse_int(eps_values[i])}
                        for i in range(len(eps_periods)) if i < len(eps_values)
                    ]

        _set_cache(cache_key, result)
        return result

    except Exception as e:
        print(f"[DataProvider] Financial trend error for {code}: {e}")
        traceback.print_exc()
        return result


async def get_stock_company(code: str):
    """
    기업 정보 (기업 탭)
    - basic API + integration API에서 추출
    - 동종업계 비교 정보 포함
    """
    cache_key = f"company_{code}"
    cached = _cached(cache_key, 86400)  # 24시간 캐싱
    if cached:
        return cached

    result = {
        "name": "",
        "sector": "",
        "market": "",
        "comparables": []
    }

    try:
        async with httpx.AsyncClient(timeout=15, headers=NAVER_HEADERS) as client:
            # 기본 정보
            r = await client.get(f"https://m.stock.naver.com/api/stock/{code}/basic")
            if r.status_code == 200:
                data = r.json()
                result["name"] = data.get("stockName", "")
                result["sector"] = data.get("industryName", "")
                result["market"] = data.get("stockExchangeName", "")

            # integration API에서 동종업계 비교
            r = await client.get(f"https://m.stock.naver.com/api/stock/{code}/integration")
            if r.status_code == 200:
                data = r.json()
                for comp in data.get("industryCompareInfo", [])[:6]:
                    result["comparables"].append({
                        "code": comp.get("itemCode", ""),
                        "name": comp.get("stockName", ""),
                        "price": _parse_price(comp.get("closePrice", "0")),
                        "change": _parse_float(comp.get("fluctuationsRatio", "0")),
                        "market_cap": _parse_int(comp.get("marketValue", "0")),
                    })

        _set_cache(cache_key, result)
        return result

    except Exception as e:
        print(f"[DataProvider] Company info error for {code}: {e}")
        traceback.print_exc()
        return result


async def get_stock_financial_statement(code: str):
    """
    재무제표 상세 (재무 탭)
    - 대차대조표, 손익계산서, 현금흐름표
    """
    cache_key = f"fin_stmt_{code}"
    cached = _cached(cache_key, 3600)
    if cached:
        return cached

    result = {
        "balance_sheet": [],
        "income_statement": [],
        "cash_flow": []
    }

    try:
        async with httpx.AsyncClient(timeout=15, headers=NAVER_HEADERS) as client:
            # 대차대조표
            r = await client.get(f"https://m.stock.naver.com/api/stock/{code}/finance/balanceSheet")
            if r.status_code == 200:
                data = r.json()
                for item in data.get("balanceSheet", [])[:4]:
                    result["balance_sheet"].append({
                        "period": item.get("date", ""),
                        "total_assets": _parse_finance_value(item.get("totalAssets", "0")),
                        "total_liabilities": _parse_finance_value(item.get("totalLiabilities", "0")),
                        "total_equity": _parse_finance_value(item.get("totalEquity", "0")),
                        "current_assets": _parse_finance_value(item.get("currentAssets", "0")),
                        "current_liabilities": _parse_finance_value(item.get("currentLiabilities", "0")),
                    })

            # 손익계산서
            r = await client.get(f"https://m.stock.naver.com/api/stock/{code}/finance/incomeStatement")
            if r.status_code == 200:
                data = r.json()
                for item in data.get("incomeStatement", [])[:4]:
                    result["income_statement"].append({
                        "period": item.get("date", ""),
                        "revenue": _parse_finance_value(item.get("revenue", "0")),
                        "cost_of_sales": _parse_finance_value(item.get("costOfSales", "0")),
                        "gross_profit": _parse_finance_value(item.get("grossProfit", "0")),
                        "operating_profit": _parse_finance_value(item.get("operatingProfit", "0")),
                        "net_income": _parse_finance_value(item.get("netIncome", "0")),
                    })

            # 현금흐름표
            r = await client.get(f"https://m.stock.naver.com/api/stock/{code}/finance/cashFlow")
            if r.status_code == 200:
                data = r.json()
                for item in data.get("cashFlow", [])[:4]:
                    result["cash_flow"].append({
                        "period": item.get("date", ""),
                        "operating": _parse_finance_value(item.get("operatingCashFlow", "0")),
                        "investing": _parse_finance_value(item.get("investingCashFlow", "0")),
                        "financing": _parse_finance_value(item.get("financingCashFlow", "0")),
                    })

        _set_cache(cache_key, result)
        return result

    except Exception as e:
        print(f"[DataProvider] Financial statement error for {code}: {e}")
        traceback.print_exc()
        return result


async def get_stock_news(code: str, limit: int = 20):
    """
    종목 뉴스/리포트 (소식 탭)
    - 네이버 뉴스 + 애널리스트 리포트
    """
    cache_key = f"news_{code}_{limit}"
    cached = _cached(cache_key, 1800)  # 30분 캐싱
    if cached:
        return cached

    result = {
        "news": [],
        "reports": []
    }

    try:
        async with httpx.AsyncClient(timeout=15, headers=NAVER_HEADERS) as client:
            # 뉴스 (올바른 API 경로: /api/news/stock/{code})
            r = await client.get(f"https://m.stock.naver.com/api/news/stock/{code}?pageSize={limit}")
            if r.status_code == 200:
                data = r.json()
                # 응답이 배열 형태
                for group in data:
                    for item in group.get("items", []):
                        result["news"].append({
                            "title": item.get("title", ""),
                            "source": item.get("officeName", ""),
                            "date": item.get("datetime", ""),
                            "url": f"https://n.news.naver.com/article/{item.get('officeId', '')}/{item.get('articleId', '')}",
                            "summary": item.get("body", "")[:200] if item.get("body") else "",
                            "image": item.get("imageOriginLink", ""),
                        })

            # 리포트 (integration API에서 가져옴)
            r = await client.get(f"https://m.stock.naver.com/api/stock/{code}/integration")
            if r.status_code == 200:
                data = r.json()
                for item in data.get("researches", []):
                    result["reports"].append({
                        "title": item.get("tit", ""),
                        "source": item.get("bnm", ""),
                        "date": item.get("wdt", ""),
                        "read_count": _parse_int(item.get("rcnt", "0")),
                    })

        _set_cache(cache_key, result)
        return result

    except Exception as e:
        print(f"[DataProvider] News error for {code}: {e}")
        traceback.print_exc()
        return result


async def get_stock_disclosures(code: str, limit: int = 20):
    """
    공시 정보 (소식 탭)
    - 네이버 공시 API (배열 직접 반환)
    """
    cache_key = f"disclosures_{code}_{limit}"
    cached = _cached(cache_key, 1800)
    if cached:
        return cached

    result = []

    try:
        async with httpx.AsyncClient(timeout=15, headers=NAVER_HEADERS) as client:
            r = await client.get(f"https://m.stock.naver.com/api/stock/{code}/disclosure")
            if r.status_code == 200:
                data = r.json()
                # 응답이 배열 형태
                items = data if isinstance(data, list) else data.get("disclosureList", [])
                for item in items[:limit]:
                    result.append({
                        "title": item.get("title", ""),
                        "date": item.get("datetime", ""),
                        "author": item.get("author", ""),
                    })

        _set_cache(cache_key, result)
        return result

    except Exception as e:
        print(f"[DataProvider] Disclosures error for {code}: {e}")
        traceback.print_exc()
        return result


async def get_stock_consensus(code: str):
    """
    투자 의견/컨센서스 (요약 탭)
    - integration API에서 consensusInfo, researches 사용
    """
    cache_key = f"consensus_{code}"
    cached = _cached(cache_key, 3600)
    if cached:
        return cached

    result = {
        "target_price": 0,
        "recommendation": "",
        "reports": []
    }

    try:
        async with httpx.AsyncClient(timeout=15, headers=NAVER_HEADERS) as client:
            # integration API
            r = await client.get(f"https://m.stock.naver.com/api/stock/{code}/integration")
            if r.status_code == 200:
                data = r.json()
                # 컨센서스 정보
                consensus = data.get("consensusInfo", {})
                if consensus:
                    result["target_price"] = _parse_int(consensus.get("priceTargetMean", "0"))
                    recomm = float(consensus.get("recommMean", "0") or "0")
                    # recommMean: 1=강력매도, 2=매도, 3=중립, 4=매수, 5=강력매수
                    if recomm >= 4.5:
                        result["recommendation"] = "강력매수"
                    elif recomm >= 3.5:
                        result["recommendation"] = "매수"
                    elif recomm >= 2.5:
                        result["recommendation"] = "중립"
                    elif recomm >= 1.5:
                        result["recommendation"] = "매도"
                    else:
                        result["recommendation"] = "강력매도" if recomm > 0 else ""

                # 최근 리포트
                for item in data.get("researches", [])[:5]:
                    result["reports"].append({
                        "title": item.get("tit", ""),
                        "broker": item.get("bnm", ""),
                        "date": item.get("wdt", ""),
                    })

        _set_cache(cache_key, result)
        return result

    except Exception as e:
        print(f"[DataProvider] Consensus error for {code}: {e}")
        traceback.print_exc()
        return result


def _parse_finance_value(val):
    """재무 데이터 파싱 (억, 조 단위 처리)"""
    if isinstance(val, (int, float)):
        return int(val)
    if isinstance(val, str):
        val = val.replace(",", "").replace(" ", "")
        if not val or val == "-":
            return 0
        try:
            # 조 단위
            if "조" in val:
                parts = val.split("조")
                jo = float(parts[0]) * 10000  # 조 → 억
                if len(parts) > 1 and parts[1]:
                    eok = parts[1].replace("억", "")
                    if eok:
                        jo += float(eok)
                return int(jo * 100000000)  # 억 → 원
            # 억 단위
            if "억" in val:
                return int(float(val.replace("억", "")) * 100000000)
            return int(float(val))
        except:
            return 0
    return 0


def _format_korean_num(val):
    """한국식 숫자 포맷 (억/조 단위)"""
    if val >= 1000000000000:  # 1조
        return f"{val / 1000000000000:.1f}조"
    if val >= 100000000:  # 1억
        return f"{val / 100000000:.0f}억"
    if val >= 10000:  # 1만
        return f"{val / 10000:.0f}만"
    return f"{val:,}"


# ===================================================================
# 환율 조회 (USD/KRW)
# ===================================================================
import time
import hmac
import hashlib
import base64
import uuid

_exchange_rate_cache = {"rate": 0, "updated": 0}


async def get_usd_krw_rate():
    """USD/KRW 환율 조회 (6시간 캐시)"""
    global _exchange_rate_cache
    now = time.time()
    cache = _exchange_rate_cache

    # 6시간(21600초) 이내면 캐시 사용
    if cache["rate"] > 0 and (now - cache["updated"]) < 21600:
        return cache["rate"]

    try:
        async with httpx.AsyncClient(timeout=10, headers=NAVER_HEADERS) as client:
            # 네이버 금융 환율 API
            url = "https://m.stock.naver.com/front-api/v1/marketIndex/productDetail?category=exchange&reutersCode=FX_USDKRW"
            r = await client.get(url)
            if r.status_code == 200:
                data = r.json()
                rate_str = data.get("result", {}).get("closePrice", "0")
                rate = float(rate_str.replace(",", ""))
                _exchange_rate_cache["rate"] = rate
                _exchange_rate_cache["updated"] = now
                return rate
    except Exception as e:
        print(f"[DataProvider] Exchange rate error: {e}")

    # 실패 시 캐시값 또는 기본값 반환
    return cache["rate"] if cache["rate"] > 0 else 1450.0


# ===================================================================
# 거래소별 잔고 조회 함수
# ===================================================================

async def fetch_upbit_balances(api_key: str, secret_key: str):
    """업비트 잔고 조회 + 현재가 + 평가손익 (avg_buy_price 직접 제공)"""
    try:
        import jwt as pyjwt

        payload = {
            'access_key': api_key,
            'nonce': str(uuid.uuid4()),
        }
        jwt_token = pyjwt.encode(payload, secret_key)
        headers = {"Authorization": f"Bearer {jwt_token}"}

        async with httpx.AsyncClient(timeout=15) as client:
            # 1. 잔고 조회
            r = await client.get("https://api.upbit.com/v1/accounts", headers=headers)
            print(f"[Upbit DEBUG] Balance API status: {r.status_code}")
            if r.status_code != 200:
                print(f"[Upbit DEBUG] Balance error: {r.text[:300]}")
                return []

            data = r.json()
            balances = []
            symbols_to_price = []

            for item in data:
                currency = item.get("currency", "")
                balance = float(item.get("balance", 0))
                locked = float(item.get("locked", 0))
                avg_buy_price = float(item.get("avg_buy_price", 0))
                total_qty = balance + locked

                if total_qty > 0:
                    balances.append({
                        "symbol": currency,
                        "quantity": total_qty,
                        "avg_price": avg_buy_price,
                        "current_price": 0,
                        "value_krw": 0,
                        "profit_loss": 0,
                        "profit_rate": 0,
                        "currency": "KRW"
                    })
                    if currency != "KRW":
                        symbols_to_price.append(currency)

            # 2. 현재가 조회 (KRW 마켓)
            if symbols_to_price:
                markets = ",".join([f"KRW-{s}" for s in symbols_to_price])
                try:
                    tr = await client.get(f"https://api.upbit.com/v1/ticker?markets={markets}")
                    if tr.status_code == 200:
                        ticker_data = tr.json()
                        price_map = {t["market"].replace("KRW-", ""): float(t["trade_price"]) for t in ticker_data}

                        for b in balances:
                            sym = b["symbol"]
                            if sym == "KRW":
                                b["current_price"] = 1
                                b["avg_price"] = 1
                                b["value_krw"] = b["quantity"]
                            elif sym in price_map:
                                current_price = price_map[sym]
                                avg_price = b["avg_price"]
                                qty = b["quantity"]

                                b["current_price"] = current_price
                                b["value_krw"] = current_price * qty

                                if avg_price > 0:
                                    b["profit_loss"] = (current_price - avg_price) * qty
                                    b["profit_rate"] = ((current_price - avg_price) / avg_price) * 100
                                print(f"[Upbit DEBUG] {sym}: price={current_price}, avg={avg_price}, profit_rate={b['profit_rate']:.2f}%")
                except Exception as te:
                    print(f"[Upbit DEBUG] Ticker error: {te}")

            print(f"[Upbit DEBUG] Returning {len(balances)} assets")
            return balances
    except Exception as e:
        print(f"[Upbit DEBUG] Balance error: {e}")
        traceback.print_exc()
        return []


async def fetch_binance_balances(api_key: str, secret_key: str):
    """바이낸스 잔고 조회 + 현재가 + 거래내역 기반 평균단가"""
    try:
        headers = {"X-MBX-APIKEY": api_key}

        async with httpx.AsyncClient(timeout=15) as client:
            # 1. 잔고 조회
            timestamp = int(time.time() * 1000)
            query = f"timestamp={timestamp}"
            signature = hmac.new(secret_key.encode(), query.encode(), hashlib.sha256).hexdigest()
            url = f"https://api.binance.com/api/v3/account?{query}&signature={signature}"

            r = await client.get(url, headers=headers)
            print(f"[Binance DEBUG] Balance API status: {r.status_code}")
            if r.status_code != 200:
                print(f"[Binance DEBUG] Balance error: {r.text[:300]}")
                return []

            data = r.json()
            balances = []
            symbols_with_balance = []

            for b in data.get("balances", []):
                free = float(b.get("free", 0))
                locked = float(b.get("locked", 0))
                total = free + locked
                if total > 0.00001:
                    symbol = b["asset"]
                    balances.append({
                        "symbol": symbol,
                        "quantity": total,
                        "avg_price": 0,
                        "current_price": 0,
                        "value_usd": 0,
                        "profit_loss": 0,
                        "profit_rate": 0,
                        "currency": "USD"
                    })
                    if symbol not in ["USDT", "USDC", "BUSD", "USD"]:
                        symbols_with_balance.append(symbol)

            # 2. 현재가 일괄 조회
            prices = {"USDT": 1.0, "USDC": 1.0, "BUSD": 1.0, "USD": 1.0}
            try:
                tr = await client.get("https://api.binance.com/api/v3/ticker/price")
                if tr.status_code == 200:
                    for t in tr.json():
                        sym = t["symbol"]
                        if sym.endswith("USDT"):
                            base = sym.replace("USDT", "")
                            prices[base] = float(t["price"])
            except Exception as pe:
                print(f"[Binance DEBUG] Price fetch error: {pe}")

            # 3. 거래내역 조회 및 평균단가 계산
            cost_basis = {}
            for symbol in symbols_with_balance[:10]:  # 상위 10개만 (API 제한)
                try:
                    ts = int(time.time() * 1000)
                    q = f"symbol={symbol}USDT&timestamp={ts}&limit=500"
                    sig = hmac.new(secret_key.encode(), q.encode(), hashlib.sha256).hexdigest()
                    trades_url = f"https://api.binance.com/api/v3/myTrades?{q}&signature={sig}"

                    tr = await client.get(trades_url, headers=headers)
                    if tr.status_code == 200:
                        trades = tr.json()
                        if trades:
                            # 이동평균법으로 계산
                            total_qty = 0.0
                            total_cost = 0.0
                            avg_cost = 0.0

                            for trade in sorted(trades, key=lambda x: x["time"]):
                                qty = float(trade["qty"])
                                price = float(trade["price"])
                                is_buyer = trade["isBuyer"]

                                if is_buyer:
                                    total_cost += qty * price
                                    total_qty += qty
                                    avg_cost = total_cost / total_qty if total_qty > 0 else 0
                                else:
                                    total_qty -= qty
                                    if total_qty > 0:
                                        total_cost = avg_cost * total_qty
                                    else:
                                        total_qty = 0
                                        total_cost = 0
                                        avg_cost = 0

                            if total_qty > 0:
                                cost_basis[symbol] = {"avg_cost": avg_cost, "total_qty": total_qty}
                                print(f"[Binance DEBUG] {symbol} avg_cost=${avg_cost:.4f}")
                except Exception as te:
                    print(f"[Binance DEBUG] Trade history error for {symbol}: {te}")

            # 4. 최종 데이터 조합
            for b in balances:
                sym = b["symbol"]
                current_price = prices.get(sym, 0)
                b["current_price"] = current_price
                b["value_usd"] = b["quantity"] * current_price

                if sym in ["USDT", "USDC", "BUSD", "USD"]:
                    b["avg_price"] = 1.0
                    b["profit_loss"] = 0
                    b["profit_rate"] = 0
                elif sym in cost_basis:
                    avg_price = cost_basis[sym]["avg_cost"]
                    b["avg_price"] = round(avg_price, 4)
                    if avg_price > 0 and current_price > 0:
                        b["profit_loss"] = round((current_price - avg_price) * b["quantity"], 2)
                        b["profit_rate"] = round(((current_price - avg_price) / avg_price) * 100, 2)

            print(f"[Binance DEBUG] Returning {len(balances)} assets")
            return balances
    except Exception as e:
        print(f"[Binance DEBUG] Balance error: {e}")
        traceback.print_exc()
        return []


async def fetch_okx_balances(api_key: str, secret_key: str, passphrase: str, include_cost_basis: bool = True):
    """OKX 잔고 조회 + 현재가 조회 + 평균단가 계산"""
    try:
        from datetime import datetime, timezone

        timestamp = datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%S.') + \
                    f"{datetime.now(timezone.utc).microsecond // 1000:03d}Z"
        message = f"{timestamp}GET/api/v5/account/balance"
        signature = base64.b64encode(
            hmac.new(secret_key.encode(), message.encode(), hashlib.sha256).digest()
        ).decode()

        headers = {
            "OK-ACCESS-KEY": api_key,
            "OK-ACCESS-SIGN": signature,
            "OK-ACCESS-TIMESTAMP": timestamp,
            "OK-ACCESS-PASSPHRASE": passphrase,
        }

        async with httpx.AsyncClient(timeout=15) as client:
            r = await client.get("https://www.okx.com/api/v5/account/balance", headers=headers)
            print(f"[OKX DEBUG] Balance API status: {r.status_code}")
            if r.status_code == 200:
                data = r.json()
                print(f"[OKX DEBUG] Balance response code: {data.get('code')}, msg: {data.get('msg')}")
                balances = []

                # 수집할 자산 목록
                assets_with_balance = []
                for account in data.get("data", []):
                    for detail in account.get("details", []):
                        ccy = detail.get("ccy", "")
                        eq = float(detail.get("eq", 0))  # 총 자산 (USD 환산)
                        cash_bal = float(detail.get("cashBal", 0))  # 현금 잔고
                        print(f"[OKX DEBUG] Asset: {ccy}, cashBal={cash_bal}, eq={eq}")
                        # 0보다 큰 모든 자산 포함 (필터 완화)
                        if cash_bal > 0:
                            assets_with_balance.append({
                                "ccy": ccy,
                                "cash_bal": cash_bal,
                                "eq": eq
                            })

                # 현재가 조회 (USDT 제외한 코인들)
                prices = {"USDT": 1.0, "USDC": 1.0}  # 스테이블코인은 $1 고정
                for asset in assets_with_balance:
                    ccy = asset["ccy"]
                    if ccy not in prices:
                        try:
                            ticker_url = f"https://www.okx.com/api/v5/market/ticker?instId={ccy}-USDT"
                            tr = await client.get(ticker_url, timeout=5)
                            if tr.status_code == 200:
                                ticker_data = tr.json()
                                if ticker_data.get("data"):
                                    last_price = float(ticker_data["data"][0].get("last", 0))
                                    prices[ccy] = last_price
                                    print(f"[OKX DEBUG] Ticker {ccy}: ${last_price}")
                        except Exception as te:
                            print(f"[OKX DEBUG] Ticker error for {ccy}: {te}")
                            prices[ccy] = 0

                # 평균단가 계산 (거래내역 기반)
                cost_basis = {}
                if include_cost_basis:
                    try:
                        symbols = [a["ccy"] for a in assets_with_balance if a["ccy"] not in ["USDT", "USDC"]]
                        if symbols:
                            cost_basis = await get_okx_cost_basis(api_key, secret_key, passphrase, symbols)
                            print(f"[OKX DEBUG] Cost basis loaded for {len(cost_basis)} symbols")
                    except Exception as cb_err:
                        print(f"[OKX DEBUG] Cost basis error: {cb_err}")

                # 잔고 데이터 구성
                for asset in assets_with_balance:
                    ccy = asset["ccy"]
                    cash_bal = asset["cash_bal"]
                    current_price = prices.get(ccy, 0)
                    value_usd = cash_bal * current_price if current_price else asset["eq"]

                    # 평균단가 적용
                    avg_price = 0
                    profit_loss = 0
                    profit_rate = 0

                    if ccy in cost_basis:
                        avg_price = cost_basis[ccy].get("avg_cost", 0)
                        if avg_price > 0 and current_price > 0:
                            # 평가손익 = (현재가 - 평균단가) × 수량
                            profit_loss = (current_price - avg_price) * cash_bal
                            # 수익률 = (현재가 - 평균단가) / 평균단가 × 100
                            profit_rate = ((current_price - avg_price) / avg_price) * 100
                    elif ccy in ["USDT", "USDC"]:
                        # 스테이블코인은 평균단가 = 현재가 = $1
                        avg_price = 1.0
                        profit_loss = 0
                        profit_rate = 0

                    balances.append({
                        "symbol": ccy,
                        "quantity": cash_bal,
                        "avg_price": round(avg_price, 4),
                        "current_price": current_price,
                        "value_usd": value_usd,
                        "profit_loss": round(profit_loss, 2),
                        "profit_rate": round(profit_rate, 2),
                        "currency": "USD"
                    })

                print(f"[OKX DEBUG] Returning {len(balances)} assets with cost basis")
                return balances
            else:
                print(f"[OKX DEBUG] Balance API error: {r.text[:500]}")
            return []
    except Exception as e:
        print(f"[OKX DEBUG] OKX balance error: {e}")
        import traceback
        traceback.print_exc()
        return []


async def fetch_bybit_balances(api_key: str, secret_key: str):
    """바이비트 잔고 조회 + 현재가 + 거래내역 기반 평균단가"""
    try:
        recv_window = "5000"

        def make_bybit_headers(query_str):
            ts = str(int(time.time() * 1000))
            sign_str = f"{ts}{api_key}{recv_window}{query_str}"
            sig = hmac.new(secret_key.encode(), sign_str.encode(), hashlib.sha256).hexdigest()
            return {
                "X-BAPI-API-KEY": api_key,
                "X-BAPI-SIGN": sig,
                "X-BAPI-TIMESTAMP": ts,
                "X-BAPI-RECV-WINDOW": recv_window,
            }

        async with httpx.AsyncClient(timeout=15) as client:
            # 1. 잔고 조회
            query = "accountType=UNIFIED"
            r = await client.get(
                f"https://api.bybit.com/v5/account/wallet-balance?{query}",
                headers=make_bybit_headers(query)
            )
            print(f"[Bybit DEBUG] Balance API status: {r.status_code}")
            if r.status_code != 200:
                print(f"[Bybit DEBUG] Balance error: {r.text[:300]}")
                return []

            data = r.json()
            if data.get("retCode") != 0:
                print(f"[Bybit DEBUG] API error: {data.get('retMsg')}")
                return []

            balances = []
            symbols_with_balance = []

            for account in data.get("result", {}).get("list", []):
                for coin in account.get("coin", []):
                    symbol = coin.get("coin", "")
                    wallet_bal = float(coin.get("walletBalance", 0))
                    usd_value = float(coin.get("usdValue", 0))
                    if wallet_bal > 0.00001:
                        balances.append({
                            "symbol": symbol,
                            "quantity": wallet_bal,
                            "avg_price": 0,
                            "current_price": 0,
                            "value_usd": usd_value,
                            "profit_loss": 0,
                            "profit_rate": 0,
                            "currency": "USD"
                        })
                        if symbol not in ["USDT", "USDC"]:
                            symbols_with_balance.append(symbol)

            # 2. 현재가 조회
            prices = {"USDT": 1.0, "USDC": 1.0}
            try:
                tr = await client.get("https://api.bybit.com/v5/market/tickers?category=spot")
                if tr.status_code == 200:
                    ticker_data = tr.json()
                    for t in ticker_data.get("result", {}).get("list", []):
                        sym = t.get("symbol", "")
                        if sym.endswith("USDT"):
                            base = sym.replace("USDT", "")
                            prices[base] = float(t.get("lastPrice", 0))
            except Exception as pe:
                print(f"[Bybit DEBUG] Price fetch error: {pe}")

            # 3. 거래내역 조회 및 평균단가 계산
            cost_basis = {}
            for symbol in symbols_with_balance[:10]:
                try:
                    q = f"category=spot&symbol={symbol}USDT&limit=200"
                    tr = await client.get(
                        f"https://api.bybit.com/v5/execution/list?{q}",
                        headers=make_bybit_headers(q)
                    )
                    if tr.status_code == 200:
                        exec_data = tr.json()
                        if exec_data.get("retCode") == 0:
                            executions = exec_data.get("result", {}).get("list", [])
                            if executions:
                                total_qty = 0.0
                                total_cost = 0.0
                                avg_cost = 0.0

                                # 시간 역순이므로 reverse
                                for ex in reversed(executions):
                                    qty = float(ex.get("execQty", 0))
                                    price = float(ex.get("execPrice", 0))
                                    side = ex.get("side", "")

                                    if side == "Buy":
                                        total_cost += qty * price
                                        total_qty += qty
                                        avg_cost = total_cost / total_qty if total_qty > 0 else 0
                                    elif side == "Sell":
                                        total_qty -= qty
                                        if total_qty > 0:
                                            total_cost = avg_cost * total_qty
                                        else:
                                            total_qty = 0
                                            total_cost = 0
                                            avg_cost = 0

                                if total_qty > 0:
                                    cost_basis[symbol] = {"avg_cost": avg_cost}
                                    print(f"[Bybit DEBUG] {symbol} avg_cost=${avg_cost:.4f}")
                except Exception as te:
                    print(f"[Bybit DEBUG] Execution history error for {symbol}: {te}")

            # 4. 최종 데이터 조합
            for b in balances:
                sym = b["symbol"]
                current_price = prices.get(sym, 0)
                b["current_price"] = current_price
                if current_price > 0:
                    b["value_usd"] = b["quantity"] * current_price

                if sym in ["USDT", "USDC"]:
                    b["avg_price"] = 1.0
                elif sym in cost_basis:
                    avg_price = cost_basis[sym]["avg_cost"]
                    b["avg_price"] = round(avg_price, 4)
                    if avg_price > 0 and current_price > 0:
                        b["profit_loss"] = round((current_price - avg_price) * b["quantity"], 2)
                        b["profit_rate"] = round(((current_price - avg_price) / avg_price) * 100, 2)

            print(f"[Bybit DEBUG] Returning {len(balances)} assets")
            return balances
    except Exception as e:
        print(f"[Bybit DEBUG] Balance error: {e}")
        traceback.print_exc()
        return []


# ===================================================================
# KIS (한국투자증권) 잔고 조회
# ===================================================================

_kis_token_cache = {}


async def get_kis_token(api_key: str, secret_key: str, is_mock: bool = False):
    """KIS 토큰 발급 (캐시 사용)"""
    cache_key = f"kis_token_{api_key[:8]}_{is_mock}"
    now = time.time()

    # 캐시 확인 (토큰 유효시간 23시간으로 가정)
    if cache_key in _kis_token_cache:
        token, issued_at = _kis_token_cache[cache_key]
        if (now - issued_at) < 82800:  # 23시간
            print(f"[KIS DEBUG] Using cached token for key={api_key[:8]}, is_mock={is_mock}")
            return token

    try:
        base_url = "https://openapivts.koreainvestment.com:29443" if is_mock else "https://openapi.koreainvestment.com:9443"
        url = f"{base_url}/oauth2/tokenP"
        print(f"[KIS DEBUG] Requesting token from {url}, is_mock={is_mock}")

        body = {
            "grant_type": "client_credentials",
            "appkey": api_key,
            "appsecret": secret_key
        }

        async with httpx.AsyncClient(timeout=10) as client:
            r = await client.post(url, json=body)
            print(f"[KIS DEBUG] Token response status: {r.status_code}")
            if r.status_code == 200:
                data = r.json()
                token = data.get("access_token", "")
                if token:
                    _kis_token_cache[cache_key] = (token, now)
                    print(f"[KIS DEBUG] Token acquired successfully, length={len(token)}")
                    return token
                else:
                    print(f"[KIS DEBUG] Token response had no access_token: {data}")
            else:
                print(f"[KIS DEBUG] Token request failed: {r.status_code}, body={r.text[:500]}")
    except Exception as e:
        print(f"[DataProvider] KIS token error: {e}")

    return ""


async def fetch_kis_kr_balances(api_key: str, secret_key: str, account_number: str, is_mock: bool = False):
    """한국투자증권 국내주식 잔고 조회"""
    print(f"[KIS DEBUG] fetch_kis_kr_balances called, account_number={account_number}, is_mock={is_mock}")
    try:
        token = await get_kis_token(api_key, secret_key, is_mock)
        print(f"[KIS DEBUG] token acquired: {bool(token)}")
        if not token:
            print("[KIS DEBUG] No token, returning empty")
            return []

        # 계좌번호 파싱 (XXXXXXXX-XX 형식)
        if "-" in account_number:
            cano, acnt = account_number.split("-")
        else:
            cano = account_number[:8]
            acnt = account_number[8:10] if len(account_number) > 8 else "01"

        base_url = "https://openapivts.koreainvestment.com:29443" if is_mock else "https://openapi.koreainvestment.com:9443"

        headers = {
            "authorization": f"Bearer {token}",
            "appkey": api_key,
            "appsecret": secret_key,
            "tr_id": "VTTC8434R" if is_mock else "TTTC8434R",  # 주식잔고조회
            "content-type": "application/json; charset=utf-8",
        }

        params = {
            "CANO": cano,
            "ACNT_PRDT_CD": acnt,
            "AFHR_FLPR_YN": "N",
            "OFL_YN": "",
            "INQR_DVSN": "02",
            "UNPR_DVSN": "01",
            "FUND_STTL_ICLD_YN": "N",
            "FNCG_AMT_AUTO_RDPT_YN": "N",
            "PRCS_DVSN": "01",
            "CTX_AREA_FK100": "",
            "CTX_AREA_NK100": "",
        }

        url = f"{base_url}/uapi/domestic-stock/v1/trading/inquire-balance"
        print(f"[KIS DEBUG] Calling URL: {url}, CANO={cano}, ACNT={acnt}")

        async with httpx.AsyncClient(timeout=15) as client:
            r = await client.get(url, headers=headers, params=params)
            print(f"[KIS DEBUG] API response status: {r.status_code}")
            if r.status_code == 200:
                data = r.json()
                output2_raw = data.get("output2", [])
                output2_type = type(output2_raw).__name__
                output2_len = len(output2_raw) if isinstance(output2_raw, (list, dict)) else 0
                print(f"[KIS DEBUG] Response rt_cd={data.get('rt_cd')}, msg1={data.get('msg1')}, output1_count={len(data.get('output1', []))}, output2_type={output2_type}, output2_len={output2_len}")
                holdings = []

                # 예수금 정보 (output2) - 리스트 또는 딕셔너리 처리
                output2 = data.get("output2", [])
                cash = 0.0
                if output2:
                    # output2가 리스트인 경우 첫 번째 요소 사용
                    if isinstance(output2, list) and len(output2) > 0:
                        cash_data = output2[0]
                    else:
                        # output2가 딕셔너리인 경우 직접 사용
                        cash_data = output2

                    # dnca_tot_amt 추출
                    if isinstance(cash_data, dict):
                        cash_str = cash_data.get("dnca_tot_amt", "0")
                        try:
                            cash = float(cash_str) if cash_str else 0.0
                        except (ValueError, TypeError):
                            cash = 0.0
                        print(f"[KIS DEBUG] 예수금(dnca_tot_amt): {cash_str} -> {cash}")

                if cash > 0:
                    holdings.append({
                        "symbol": "KRW",
                        "name": "예수금",
                        "quantity": cash,  # 실제 금액을 quantity로
                        "avg_price": 1,
                        "current_price": 1,
                        "value_krw": cash,
                        "profit_loss": 0,
                        "profit_rate": 0,
                        "currency": "KRW"
                    })

                # 보유종목 (output1)
                for item in data.get("output1", []):
                    pdno = item.get("pdno", "")  # 종목코드
                    prdt_name = item.get("prdt_name", "")  # 종목명
                    hldg_qty = int(item.get("hldg_qty", 0))  # 보유수량
                    if hldg_qty > 0:
                        holdings.append({
                            "symbol": pdno,
                            "name": prdt_name,
                            "quantity": hldg_qty,
                            "avg_price": float(item.get("pchs_avg_pric", 0)),
                            "current_price": float(item.get("prpr", 0)),
                            "value_krw": float(item.get("evlu_amt", 0)),
                            "profit_loss": float(item.get("evlu_pfls_amt", 0)),
                            "profit_rate": float(item.get("evlu_pfls_rt", 0)),
                            "currency": "KRW"
                        })
                print(f"[KIS DEBUG] Returning {len(holdings)} holdings")
                return holdings
            else:
                print(f"[KIS DEBUG] Non-200 response: {r.text[:500]}")
            return []
    except Exception as e:
        print(f"[KIS DEBUG] KIS KR balance error: {e}")
        traceback.print_exc()
        return []


async def fetch_kis_us_balances(api_key: str, secret_key: str, account_number: str, is_mock: bool = False):
    """한국투자증권 해외주식 잔고 조회"""
    try:
        token = await get_kis_token(api_key, secret_key, is_mock)
        if not token:
            return []

        # 계좌번호 파싱
        if "-" in account_number:
            cano, acnt = account_number.split("-")
        else:
            cano = account_number[:8]
            acnt = account_number[8:10] if len(account_number) > 8 else "01"

        base_url = "https://openapivts.koreainvestment.com:29443" if is_mock else "https://openapi.koreainvestment.com:9443"

        headers = {
            "authorization": f"Bearer {token}",
            "appkey": api_key,
            "appsecret": secret_key,
            "tr_id": "VTTS3012R" if is_mock else "TTTS3012R",  # 해외주식잔고조회
            "content-type": "application/json; charset=utf-8",
        }

        params = {
            "CANO": cano,
            "ACNT_PRDT_CD": acnt,
            "OVRS_EXCG_CD": "NASD",  # 나스닥 (필요시 NYSE도 별도 조회)
            "TR_CRCY_CD": "USD",
            "CTX_AREA_FK200": "",
            "CTX_AREA_NK200": "",
        }

        url = f"{base_url}/uapi/overseas-stock/v1/trading/inquire-balance"

        async with httpx.AsyncClient(timeout=15) as client:
            r = await client.get(url, headers=headers, params=params)
            if r.status_code == 200:
                data = r.json()
                holdings = []
                for item in data.get("output1", []):
                    ovrs_pdno = item.get("ovrs_pdno", "")  # 해외종목코드
                    ovrs_item_name = item.get("ovrs_item_name", "")  # 종목명
                    ovrs_cblc_qty = int(item.get("ovrs_cblc_qty", 0))  # 보유수량
                    if ovrs_cblc_qty > 0:
                        holdings.append({
                            "symbol": ovrs_pdno,
                            "name": ovrs_item_name,
                            "quantity": ovrs_cblc_qty,
                            "avg_price": float(item.get("pchs_avg_pric", 0)),
                            "current_price": float(item.get("now_pric2", 0)),
                            "value_usd": float(item.get("ovrs_stck_evlu_amt", 0)),
                            "profit_loss_usd": float(item.get("frcr_evlu_pfls_amt", 0)),
                            "currency": "USD"
                        })
                return holdings
            return []
    except Exception as e:
        print(f"[DataProvider] KIS US balance error: {e}")
        traceback.print_exc()
        return []


# ===================================================================
# OKX 거래내역 조회 및 평균단가 계산
# ===================================================================

async def fetch_okx_trade_history(api_key: str, secret_key: str, passphrase: str, inst_id: str = None):
    """
    OKX 거래내역 조회 (최근 3개월)
    - GET /api/v5/trade/fills-history
    - instType=SPOT
    """
    try:
        from datetime import datetime, timezone

        def make_okx_signature(method, path, query=""):
            """OKX API 서명 생성 (매 요청마다 새 타임스탬프)"""
            ts = datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%S.') + \
                 f"{datetime.now(timezone.utc).microsecond // 1000:03d}Z"
            msg = f"{ts}{method}{path}"
            if query:
                msg += f"?{query}"
            sig = base64.b64encode(
                hmac.new(secret_key.encode(), msg.encode(), hashlib.sha256).digest()
            ).decode()
            return ts, sig

        path = "/api/v5/trade/fills-history"
        base_query = "instType=SPOT"
        if inst_id:
            base_query += f"&instId={inst_id}"

        all_trades = []
        async with httpx.AsyncClient(timeout=15) as client:
            after = ""
            for page_num in range(10):  # 최대 1000건
                query = base_query + (f"&after={after}" if after else "")
                ts, sig = make_okx_signature("GET", path, query)

                headers = {
                    "OK-ACCESS-KEY": api_key,
                    "OK-ACCESS-SIGN": sig,
                    "OK-ACCESS-TIMESTAMP": ts,
                    "OK-ACCESS-PASSPHRASE": passphrase,
                }

                url = f"https://www.okx.com{path}?{query}"
                r = await client.get(url, headers=headers)

                if r.status_code == 200:
                    data = r.json()
                    if data.get("code") != "0":
                        print(f"[OKX DEBUG] Trade history API error: {data.get('msg')}")
                        break
                    trades = data.get("data", [])
                    if not trades:
                        print(f"[OKX DEBUG] No more trades at page {page_num}")
                        break
                    all_trades.extend(trades)
                    after = trades[-1].get("billId", "")
                    print(f"[OKX DEBUG] Page {page_num}: got {len(trades)} trades")
                else:
                    print(f"[OKX DEBUG] Trade history error: {r.status_code} - {r.text[:200]}")
                    break

        # 거래내역 파싱
        parsed_trades = []
        for trade in all_trades:
            parsed_trades.append({
                "instId": trade.get("instId", ""),
                "side": trade.get("side", ""),
                "fillPx": float(trade.get("fillPx", 0)),
                "fillSz": float(trade.get("fillSz", 0)),
                "fee": float(trade.get("fee", 0)),
                "feeCcy": trade.get("feeCcy", ""),
                "ts": trade.get("ts", ""),
            })

        print(f"[OKX DEBUG] Total fetched {len(parsed_trades)} trades")
        return parsed_trades

    except Exception as e:
        print(f"[OKX DEBUG] Trade history error: {e}")
        traceback.print_exc()
        return []


def calculate_moving_average_cost(trades: list, symbol: str) -> dict:
    """
    이동평균법으로 평균단가 계산
    - 매수: (기존총액 + 매수금액) / (기존수량 + 매수수량)
    - 매도: 평균단가 변동 없음, 수량만 감소

    trades: 시간순 정렬된 거래내역 (오래된 것부터)
    symbol: 계산할 심볼 (예: BTC)
    """
    total_qty = 0.0
    total_cost = 0.0
    avg_cost = 0.0

    # 시간순 정렬 (오래된 것부터)
    sorted_trades = sorted(trades, key=lambda x: x.get("ts", "0"))

    for trade in sorted_trades:
        inst_id = trade.get("instId", "")
        # instId에서 심볼 추출 (BTC-USDT → BTC)
        trade_symbol = inst_id.split("-")[0] if "-" in inst_id else inst_id

        if trade_symbol != symbol:
            continue

        side = trade.get("side", "")
        fill_px = trade.get("fillPx", 0)
        fill_sz = trade.get("fillSz", 0)

        if side == "buy":
            # 매수: 총액 증가, 수량 증가
            buy_cost = fill_px * fill_sz
            total_cost += buy_cost
            total_qty += fill_sz
            # 새 평균단가 계산
            avg_cost = total_cost / total_qty if total_qty > 0 else 0
        elif side == "sell":
            # 매도: 평균단가 유지, 수량만 감소
            total_qty -= fill_sz
            if total_qty > 0:
                total_cost = avg_cost * total_qty
            else:
                # 전량 매도 시 초기화
                total_qty = 0
                total_cost = 0
                avg_cost = 0

    return {
        "symbol": symbol,
        "avg_cost": round(avg_cost, 8),
        "total_qty": round(total_qty, 8),
    }


async def get_okx_cost_basis(api_key: str, secret_key: str, passphrase: str, symbols: list = None):
    """
    OKX 보유자산 평균단가 일괄 계산
    - 거래내역 조회 후 각 심볼별 이동평균법 적용
    """
    # 거래내역 조회
    trades = await fetch_okx_trade_history(api_key, secret_key, passphrase)

    if not trades:
        print("[OKX DEBUG] No trades found, returning empty cost basis")
        return {}

    # 심볼 목록 추출 (지정 안 했으면 거래내역에서 자동 추출)
    if not symbols:
        symbols = set()
        for trade in trades:
            inst_id = trade.get("instId", "")
            if "-" in inst_id:
                symbols.add(inst_id.split("-")[0])

    # 각 심볼별 평균단가 계산
    cost_basis = {}
    for symbol in symbols:
        result = calculate_moving_average_cost(trades, symbol)
        if result["total_qty"] > 0:  # 보유 수량이 있는 것만
            cost_basis[symbol] = result

    print(f"[OKX DEBUG] Calculated cost basis for {len(cost_basis)} symbols")
    return cost_basis


# ===================================================================
# Cost Basis DB 캐싱 함수
# ===================================================================

async def save_cost_basis_to_db(db_session, user_id: int, account_id: int, cost_basis: dict):
    """
    계산된 평균단가를 DB에 저장 (upsert)
    cost_basis: {"BTC": {"avg_cost": 50000.0, "total_qty": 0.5}, ...}
    """
    try:
        from sqlalchemy import text
        for symbol, data in cost_basis.items():
            avg_cost = data.get("avg_cost", 0)
            total_qty = data.get("total_qty", 0)

            # Upsert (PostgreSQL ON CONFLICT)
            sql = """
                INSERT INTO cost_basis (user_id, account_id, symbol, avg_cost, total_qty, updated_at)
                VALUES (:user_id, :account_id, :symbol, :avg_cost, :total_qty, NOW())
                ON CONFLICT (account_id, symbol) DO UPDATE SET
                    avg_cost = EXCLUDED.avg_cost,
                    total_qty = EXCLUDED.total_qty,
                    updated_at = NOW()
            """
            db_session.execute(text(sql), {
                "user_id": user_id,
                "account_id": account_id,
                "symbol": symbol,
                "avg_cost": avg_cost,
                "total_qty": total_qty
            })
        db_session.commit()
        print(f"[CostBasis] Saved {len(cost_basis)} symbols to DB for account_id={account_id}")
    except Exception as e:
        print(f"[CostBasis] DB save error: {e}")
        traceback.print_exc()


async def load_cost_basis_from_db(db_session, account_id: int) -> dict:
    """
    DB에서 평균단가 캐시 로드
    Returns: {"BTC": {"avg_cost": 50000.0, "total_qty": 0.5}, ...}
    """
    try:
        from sqlalchemy import text
        sql = """
            SELECT symbol, avg_cost, total_qty, updated_at
            FROM cost_basis
            WHERE account_id = :account_id
        """
        rows = db_session.execute(text(sql), {"account_id": account_id}).fetchall()

        cost_basis = {}
        for row in rows:
            cost_basis[row.symbol] = {
                "avg_cost": float(row.avg_cost or 0),
                "total_qty": float(row.total_qty or 0),
                "updated_at": row.updated_at.isoformat() if row.updated_at else None
            }
        print(f"[CostBasis] Loaded {len(cost_basis)} symbols from DB for account_id={account_id}")
        return cost_basis
    except Exception as e:
        print(f"[CostBasis] DB load error: {e}")
        return {}


async def get_or_calculate_cost_basis(
    db_session,
    user_id: int,
    account_id: int,
    api_key: str,
    secret_key: str,
    passphrase: str,
    symbols: list,
    force_refresh: bool = False,
    cache_ttl_hours: int = 6
) -> dict:
    """
    평균단가 조회 (캐시 우선, 만료 시 재계산)
    - DB 캐시 확인 → 유효하면 반환
    - 캐시 만료 or force_refresh → API 조회 후 DB 저장
    """
    from datetime import datetime, timedelta

    # 캐시 확인
    if not force_refresh:
        cached = await load_cost_basis_from_db(db_session, account_id)
        if cached:
            # 캐시 만료 체크 (가장 최근 updated_at 기준)
            latest = None
            for sym, data in cached.items():
                if data.get("updated_at"):
                    try:
                        ts = datetime.fromisoformat(data["updated_at"])
                        if latest is None or ts > latest:
                            latest = ts
                    except:
                        pass

            if latest:
                cache_age = datetime.now() - latest.replace(tzinfo=None)
                if cache_age < timedelta(hours=cache_ttl_hours):
                    print(f"[CostBasis] Using cached data (age: {cache_age})")
                    return cached

    # API에서 조회 후 계산
    print(f"[CostBasis] Refreshing from API for account_id={account_id}")
    cost_basis = await get_okx_cost_basis(api_key, secret_key, passphrase, symbols)

    # DB에 저장
    if cost_basis:
        await save_cost_basis_to_db(db_session, user_id, account_id, cost_basis)

    return cost_basis


# =============================================================================
# Phase 8-2: 국내 종목 상세 API
# =============================================================================

async def get_stock_summary_kr(code: str) -> dict:
    """
    국내 종목 요약 정보 (기본정보 + 재무지표)
    데이터 소스: 네이버 basic + integration API
    """
    cache_key = f"stock_summary_kr_{code}"
    cached = _cached(cache_key, 300)  # 5분 캐싱
    if cached:
        return cached

    result = {
        "code": code,
        "name": "",
        "market": "",
        "price": 0,
        "change": 0,
        "change_pct": 0,
        "open": 0,
        "high": 0,
        "low": 0,
        "market_cap": "",
        "market_cap_raw": 0,
        "per": 0,
        "pbr": 0,
        "roe": 0,
        "eps": 0,
        "bps": 0,
        "dividend_yield": 0,
        "debt_ratio": 0,
        "operating_margin": 0,
        "high_52w": 0,
        "low_52w": 0,
        "volume": 0,
        "sector": "",
        "foreign_ratio": 0,
    }

    try:
        async with httpx.AsyncClient(timeout=15, headers=NAVER_HEADERS) as client:
            # 1. Basic API
            basic_url = f"https://m.stock.naver.com/api/stock/{code}/basic"
            r1 = await client.get(basic_url)
            if r1.status_code == 200:
                basic = r1.json()
                result["name"] = basic.get("stockName", "")
                result["market"] = basic.get("stockExchangeType", {}).get("nameKor", "")
                result["price"] = _parse_price(basic.get("closePrice", "0"))
                result["change"] = _parse_price(basic.get("compareToPreviousClosePrice", "0"))
                result["change_pct"] = _parse_float(basic.get("fluctuationsRatio", "0"))

            # 2. Integration API
            int_url = f"https://m.stock.naver.com/api/stock/{code}/integration"
            r2 = await client.get(int_url)
            if r2.status_code == 200:
                data = r2.json()
                total_infos = data.get("totalInfos", [])

                for info in total_infos:
                    key = info.get("code", "")
                    val = info.get("value", "")

                    if key == "marketValue":
                        result["market_cap"] = val
                        result["market_cap_raw"] = _parse_korean_market_cap(val)
                    elif key == "per":
                        result["per"] = _parse_float(val.replace("배", "").strip())
                    elif key == "pbr":
                        result["pbr"] = _parse_float(val.replace("배", "").strip())
                    elif key == "eps":
                        result["eps"] = _parse_price(val.replace("원", "").strip())
                    elif key == "bps":
                        result["bps"] = _parse_price(val.replace("원", "").strip())
                    elif key == "dividendYieldRatio":
                        result["dividend_yield"] = _parse_float(val.replace("%", "").strip())
                    elif key == "roe":
                        result["roe"] = _parse_float(val.replace("%", "").strip())
                    elif key == "highPriceOf52Weeks":
                        result["high_52w"] = _parse_price(val)
                    elif key == "lowPriceOf52Weeks":
                        result["low_52w"] = _parse_price(val)
                    elif key == "accumulatedTradingVolume":
                        result["volume"] = _parse_price(val)
                    elif key == "foreignRate":
                        result["foreign_ratio"] = _parse_float(val.replace("%", "").strip())
                    elif key == "debtRatio":
                        result["debt_ratio"] = _parse_float(val.replace("%", "").strip())
                    elif key == "operatingMargin":
                        result["operating_margin"] = _parse_float(val.replace("%", "").strip())

            # 3. fchart에서 시가/고가/저가 (count=2: 비거래일 대응)
            fchart_url = f"https://fchart.stock.naver.com/sise.nhn?symbol={code}&timeframe=day&count=2&requestType=0"
            fchart_r = await client.get(fchart_url)
            if fchart_r.status_code == 200:
                import re
                items = re.findall(r'<item data="([^"]+)"', fchart_r.text)
                if items:
                    parts = items[-1].split("|")
                    if len(parts) >= 6:
                        o, h, l = int(parts[1]), int(parts[2]), int(parts[3])
                        # 비거래일이면 전일 데이터 사용
                        if o == 0 and len(items) >= 2:
                            prev = items[-2].split("|")
                            if len(prev) >= 6:
                                o, h, l = int(prev[1]), int(prev[2]), int(prev[3])
                        result["open"] = o
                        result["high"] = h
                        result["low"] = l

        _set_cache(cache_key, result)
    except Exception as e:
        print(f"[DataProvider] get_stock_summary_kr error for {code}: {e}")
        traceback.print_exc()

    return result


async def _fetch_fnguide_consensus(code: str) -> dict:
    """
    FnGuide에서 컨센서스 데이터 가져오기 (6년: 2022-2027E)
    SVD_Main 페이지의 Table 10/11에서 추출
    EPS는 지배주주순이익 기준 (stockeasy 동일)
    """
    result = {
        "periods": [],
        "isConsensus": [],
        "revenue": [],
        "operating_profit": [],
        "net_income": [],
        "eps": [],
        "opm": [],
        "gross_profit": [],  # 매출총이익 (GPM 계산용)
        "gpm": [],  # 매출총이익률
    }

    try:
        url = f"http://comp.fnguide.com/SVO2/ASP/SVD_Main.asp?pGB=1&gicode=A{code}"
        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}

        async with httpx.AsyncClient(timeout=15) as client:
            r = await client.get(url, headers=headers)
            r.encoding = "utf-8"

            if r.status_code != 200:
                return result

            soup = BeautifulSoup(r.text, "html.parser")
            tables = soup.find_all("table")

            # Table 11 찾기 (IFRS 연결 Annual - 6년 데이터)
            for table in tables:
                rows = table.find_all("tr")
                if len(rows) < 8:
                    continue

                header_row = rows[1] if len(rows) > 1 else None
                if not header_row:
                    continue

                header_cells = header_row.find_all(["th", "td"])
                header_texts = [c.get_text(strip=True) for c in header_cells]

                if not any("2024" in h for h in header_texts):
                    continue
                # (E) = Estimate, (P) = Provisional (잠정실적)
                if not any("(E)" in h or "(P)" in h or "Estimate" in h or "Provisional" in h for h in header_texts):
                    continue

                # 연도 컬럼 위치 파싱 (연간 데이터만 - 분기 제외)
                year_cols = []
                estimate_count = 0
                for i, h in enumerate(header_texts):
                    # 분기 데이터 제외 (2025/03, 2025/06, 2025/09 등)
                    if any(q in h for q in ["/03", "/06", "/09"]):
                        continue
                    # 연간 데이터만 처리 (2022/12, 2023/12, etc.)
                    if any(y in h for y in ["2020", "2021", "2022", "2023", "2024"]):
                        year_str = h.replace("/12", "")
                        year_cols.append((i, year_str, False))
                    elif "2025" in h or ((("(P)" in h or "Provisional" in h) and "2025" not in "".join(header_texts[:i]))):
                        # 2025년 또는 (P) Provisional
                        if not any(y == "2025(E)" for _, y, _ in year_cols):
                            year_cols.append((i, "2025(E)", True))
                    elif "2026" in h or ((("(E)" in h or "Estimate" in h) and estimate_count == 0)):
                        if not any(y == "2026(E)" for _, y, _ in year_cols):
                            year_cols.append((i, "2026(E)", True))
                            estimate_count = 1
                    elif "2027" in h or ((("(E)" in h or "Estimate" in h) and estimate_count == 1)):
                        if not any(y == "2027(E)" for _, y, _ in year_cols):
                            year_cols.append((i, "2027(E)", True))
                            estimate_count = 2

                # 최소 6개 연도 필요 (Table 10은 4개, Table 11은 8개)
                if len(year_cols) < 6:
                    continue

                # 중복 연도 제외 시 최소 6개 필요
                unique_years = set(y for _, y, _ in year_cols)
                if len(unique_years) < 6:
                    continue

                # 2026(E) 또는 2027(E) 전망치 포함 필수
                has_future_estimate = any("2026" in y or "2027" in y for y in unique_years)
                if not has_future_estimate:
                    continue

                year_cols = year_cols[-6:] if len(year_cols) > 6 else year_cols

                result["periods"] = [y for _, y, _ in year_cols]
                result["isConsensus"] = [is_est for _, _, is_est in year_cols]

                for row in rows[2:]:
                    cells = row.find_all(["th", "td"])
                    if len(cells) < 2:
                        continue

                    row_label = cells[0].get_text(strip=True)
                    row_values = []

                    # 데이터 행은 첫 열이 row label이므로 +1 offset
                    for col_idx, _, _ in year_cols:
                        data_idx = col_idx + 1  # header vs data offset
                        if data_idx < len(cells):
                            val_text = cells[data_idx].get_text(strip=True)
                            val_text = val_text.replace(",", "").replace("-", "").strip()
                            try:
                                row_values.append(int(float(val_text)) if val_text else 0)
                            except:
                                row_values.append(0)
                        else:
                            row_values.append(0)

                    if "매출액" in row_label and "증가" not in row_label:
                        result["revenue"] = row_values
                    elif "영업이익" in row_label and "발표" not in row_label and "증가" not in row_label and "률" not in row_label:
                        result["operating_profit"] = row_values
                    elif "지배주주순이익" in row_label and "EPS" not in row_label and "률" not in row_label:
                        result["net_income"] = row_values
                    elif "EPS(원)" in row_label or ("EPS" in row_label and "지배" in row_label):
                        # EPS(원)지배주주순이익 / 발행주식수 - stockeasy와 동일 기준
                        result["eps"] = row_values
                    elif "매출총이익" in row_label:
                        result["gross_profit"] = row_values

                if result["revenue"] and result["operating_profit"] and result["eps"]:
                    break

            # OPM 계산
            if result["revenue"] and result["operating_profit"]:
                result["opm"] = []
                for rev, op in zip(result["revenue"], result["operating_profit"]):
                    if rev and rev > 0:
                        result["opm"].append(round(op / rev * 100, 1))
                    else:
                        result["opm"].append(0)

            # GPM 계산 (매출총이익률)
            if result["revenue"] and result["gross_profit"]:
                result["gpm"] = []
                for rev, gp in zip(result["revenue"], result["gross_profit"]):
                    if rev and rev > 0 and gp:
                        result["gpm"].append(round(gp / rev * 100, 1))
                    else:
                        result["gpm"].append(None)

            print(f"[FnGuide] {code} parsed: periods={result['periods']}, eps={result['eps'][:3] if result['eps'] else []}")

            # SVD_Finance에서 매출총이익 추가 파싱 (SVD_Main에는 없음)
            if result["periods"] and not result["gross_profit"]:
                try:
                    finance_url = f"http://comp.fnguide.com/SVO2/ASP/SVD_Finance.asp?pGB=1&gicode=A{code}&cID=&MenuYn=Y&ReportGB=D&NewMenuID=103&stkGb=701"
                    r2 = await client.get(finance_url, headers=headers)
                    r2.encoding = "utf-8"
                    if r2.status_code == 200:
                        soup2 = BeautifulSoup(r2.text, "html.parser")
                        tables2 = soup2.find_all("table")
                        for t2 in tables2[:2]:  # 첫 2개 테이블만 (연간/분기 손익계산서)
                            rows2 = t2.find_all("tr")
                            if len(rows2) < 4:
                                continue
                            header2 = rows2[0].find_all(["th", "td"])
                            header_texts2 = [c.get_text(strip=True) for c in header2]
                            # 연간 테이블 확인 (2022, 2023, 2024 포함)
                            if not any("2022" in h or "2023" in h for h in header_texts2):
                                continue
                            for row2 in rows2[1:10]:
                                cells2 = row2.find_all(["th", "td"])
                                if len(cells2) < 4:
                                    continue
                                label2 = cells2[0].get_text(strip=True)
                                if "매출총이익" in label2:
                                    gp_values = []
                                    for idx, p in enumerate(result["periods"]):
                                        # 연도 매칭: 2022 → cells2[1], 2023 → cells2[2], etc.
                                        cell_idx = idx + 1
                                        if cell_idx < len(cells2):
                                            val = cells2[cell_idx].get_text(strip=True).replace(",", "").replace("-", "").strip()
                                            try:
                                                gp_values.append(int(float(val)) if val else None)
                                            except:
                                                gp_values.append(None)
                                        else:
                                            gp_values.append(None)
                                    if gp_values:
                                        result["gross_profit"] = gp_values
                                        # GPM 계산
                                        result["gpm"] = []
                                        for rev, gp in zip(result["revenue"], gp_values):
                                            if rev and rev > 0 and gp:
                                                result["gpm"].append(round(gp / rev * 100, 1))
                                            else:
                                                result["gpm"].append(None)
                                        print(f"[FnGuide] {code} GPM: {result['gpm'][:3]}")
                                    break
                            if result["gross_profit"]:
                                break
                except Exception as e2:
                    print(f"[FnGuide] GPM fetch error for {code}: {e2}")

    except Exception as e:
        print(f"[FnGuide] Error fetching consensus for {code}: {e}")
        traceback.print_exc()

    return result


async def get_stock_financials_kr(code: str, fin_type: str = "annual") -> dict:
    """
    국내 종목 재무 추이 (연간/분기) - StockEasy 스타일
    데이터 소스:
    - 연간: FnGuide (6년, 2022-2027E 컨센서스)
    - 분기: 네이버 finance/quarter API
    """
    cache_key = f"stock_financials_kr_{code}_{fin_type}"
    cached = _cached(cache_key, 3600)
    if cached:
        return cached

    result = {
        "code": code,
        "type": fin_type,  # annual 또는 quarter
        "periods": [],      # ["2022.12", "2023.12", "2024.12", "2025.12(E)"]
        "isConsensus": [],  # [false, false, false, true] - 전망치 여부
        "revenue": [],      # 매출액 (억원)
        "operating_profit": [],  # 영업이익 (억원)
        "net_income": [],   # 당기순이익 (억원) - 지배주주 귀속
        "eps": [],          # EPS (원) - 지배주주순이익 기준
        "opm": [],          # 영업이익률 (%)
        "gross_profit": [],  # 매출총이익 (억원)
        "gpm": [],          # 매출총이익률 (%)
    }

    try:
        # 연간 데이터: FnGuide 먼저 시도 (6년 컨센서스 포함)
        if fin_type == "annual":
            fnguide_data = await _fetch_fnguide_consensus(code)
            if fnguide_data.get("revenue") and len(fnguide_data["revenue"]) >= 4:
                result["periods"] = fnguide_data["periods"]
                result["isConsensus"] = fnguide_data["isConsensus"]
                result["revenue"] = fnguide_data["revenue"]
                result["operating_profit"] = fnguide_data["operating_profit"]
                result["net_income"] = fnguide_data["net_income"]
                result["opm"] = fnguide_data["opm"]
                # FnGuide EPS 사용 (지배주주 기준)
                if fnguide_data.get("eps"):
                    result["eps"] = fnguide_data["eps"]
                # GPM 데이터
                if fnguide_data.get("gross_profit"):
                    result["gross_profit"] = fnguide_data["gross_profit"]
                if fnguide_data.get("gpm"):
                    result["gpm"] = fnguide_data["gpm"]
                print(f"[DataProvider] FnGuide 성공 {code}: {len(result['periods'])}년, EPS={result['eps'][:3] if result['eps'] else 'N/A'}")

        # FnGuide 실패 또는 분기: 네이버 API
        if not result["periods"]:
            async with httpx.AsyncClient(timeout=15, headers=NAVER_HEADERS) as client:
                endpoint = "annual" if fin_type == "annual" else "quarter"
                url = f"https://m.stock.naver.com/api/stock/{code}/finance/{endpoint}"
                r = await client.get(url)

                if r.status_code == 200:
                    fin_data = r.json()
                    fin_info = fin_data.get("financeInfo", {})
                    title_list = fin_info.get("trTitleList", [])
                    row_list = fin_info.get("rowList", [])

                    periods = []
                    is_consensus = []
                    keys = []

                    for t in title_list:
                        period_title = t.get("title", "")
                        is_est = t.get("isConsensus", "") == "Y"
                        if is_est and not period_title.endswith("(E)"):
                            period_title = period_title + "(E)"
                        periods.append(period_title)
                        is_consensus.append(is_est)
                        keys.append(t.get("key", ""))

                    result["periods"] = periods
                    result["isConsensus"] = is_consensus

                    for row in row_list:
                        title = row.get("title", "")
                        columns_data = row.get("columns", {})
                        values = []

                        for k in keys:
                            col = columns_data.get(k, {})
                            v = col.get("value", "0")
                            cleaned = v.replace(",", "").replace("-", "").strip()
                            if not cleaned:
                                cleaned = "0"
                            is_negative = v.startswith("-") or (v.startswith("(") and v.endswith(")"))
                            try:
                                val = int(float(cleaned))
                                if is_negative and val > 0:
                                    val = -val
                                values.append(val)
                            except:
                                values.append(0)

                        if title == "매출액":
                            result["revenue"] = values
                        elif title == "영업이익":
                            result["operating_profit"] = values
                        elif title == "당기순이익":
                            result["net_income"] = values
                        elif title == "EPS" or title == "EPS(원)":
                            result["eps"] = values
                        elif title == "영업이익률":
                            result["opm"] = values

        # EPS: FnGuide EPS가 없으면 네이버 API 폴백 (분기 데이터용)
        # 연간은 FnGuide EPS (지배주주 기준) 사용, 분기는 네이버
        if fin_type == "quarter" and (not result["eps"] or len(result["eps"]) < len(result["periods"])):
            async with httpx.AsyncClient(timeout=15, headers=NAVER_HEADERS) as client:
                url = f"https://m.stock.naver.com/api/stock/{code}/finance/annual"
                r = await client.get(url)
                if r.status_code == 200:
                    fin_data = r.json()
                    fin_info = fin_data.get("financeInfo", {})
                    row_list = fin_info.get("rowList", [])
                    title_list = fin_info.get("trTitleList", [])
                    keys = [t.get("key", "") for t in title_list]

                    for row in row_list:
                        title = row.get("title", "")
                        if title == "EPS" or title == "EPS(원)":
                            columns_data = row.get("columns", {})
                            eps_values = []
                            for k in keys:
                                col = columns_data.get(k, {})
                                v = col.get("value", "0")
                                cleaned = v.replace(",", "").replace("-", "").strip()
                                try:
                                    eps_values.append(int(float(cleaned)) if cleaned else 0)
                                except:
                                    eps_values.append(0)
                            if eps_values:
                                # FnGuide 기간에 맞춰 확장 (부족분 0으로)
                                if len(result["periods"]) > len(eps_values):
                                    diff = len(result["periods"]) - len(eps_values)
                                    eps_values = eps_values + [0] * diff
                                result["eps"] = eps_values[-len(result["periods"]):]
                            break

                if not result["eps"]:
                    summary_url = f"https://m.stock.naver.com/api/stock/{code}/finance/summary"
                    r2 = await client.get(summary_url)
                    if r2.status_code == 200:
                        summary_data = r2.json()
                        chart_eps = summary_data.get("chartEps", {})
                        eps_columns = chart_eps.get("columns", [])
                        if len(eps_columns) >= 2:
                            eps_values_raw = eps_columns[1][1:] if len(eps_columns) > 1 else []
                            result["eps"] = [_parse_int(v) for v in eps_values_raw]

        _set_cache(cache_key, result)
    except Exception as e:
        print(f"[DataProvider] get_stock_financials_kr error for {code}: {e}")
        traceback.print_exc()

    return result


async def get_stock_news_kr(code: str, limit: int = 20) -> dict:
    """
    국내 종목 뉴스
    데이터 소스: 네이버 news/stock API
    """
    cache_key = f"stock_news_kr_{code}"
    cached = _cached(cache_key, 600)  # 10분 캐싱
    if cached:
        return cached

    result = {"items": []}

    try:
        async with httpx.AsyncClient(timeout=15, headers=NAVER_HEADERS) as client:
            url = f"https://m.stock.naver.com/api/news/stock/{code}?page=1&size={limit}"
            r = await client.get(url)

            if r.status_code == 200:
                data = r.json()
                # data is array of groups, each with "items"
                if isinstance(data, list):
                    for group in data:
                        items = group.get("items", [])
                        for item in items:
                            news = {
                                "title": item.get("title", ""),
                                "source": item.get("officeName", ""),
                                "date": _format_news_date(item.get("datetime", "")),
                                "url": f"https://n.news.naver.com/mnews/article/{item.get('officeId', '')}/{item.get('articleId', '')}"
                            }
                            result["items"].append(news)
                            if len(result["items"]) >= limit:
                                break
                        if len(result["items"]) >= limit:
                            break

        _set_cache(cache_key, result)
    except Exception as e:
        print(f"[DataProvider] get_stock_news_kr error for {code}: {e}")
        traceback.print_exc()

    return result


def _format_news_date(dt_str: str) -> str:
    """뉴스 날짜 포맷: '202602201922' → '2026.02.20'"""
    if len(dt_str) >= 8:
        return f"{dt_str[:4]}.{dt_str[4:6]}.{dt_str[6:8]}"
    return dt_str


async def get_stock_company_kr(code: str) -> dict:
    """
    국내 종목 기업 정보 탭
    - 동종업계 종목
    - 리서치 리포트
    - 투자의견/목표가
    데이터 소스: 네이버 integration API
    """
    cache_key = f"stock_company_kr_{code}"
    cached = _cached(cache_key, 1800)  # 30분 캐싱
    if cached:
        return cached

    result = {
        "code": code,
        "industry_code": None,
        "peers": [],  # 동종업계 종목
        "researches": [],  # 리서치 리포트
        "consensus": None,  # 투자의견/목표가
    }

    try:
        async with httpx.AsyncClient(timeout=15, headers=NAVER_HEADERS) as client:
            url = f"https://m.stock.naver.com/api/stock/{code}/integration"
            r = await client.get(url)

            if r.status_code == 200:
                data = r.json()

                # 업종 코드
                result["industry_code"] = data.get("industryCode")

                # 동종업계 종목
                peers = data.get("industryCompareInfo", [])
                for p in peers:
                    peer_code = p.get("itemCode", "")
                    if peer_code == code:
                        continue  # 자기 자신 제외
                    close_price = p.get("closePrice", "0")
                    change = p.get("compareToPreviousClosePrice", "0")
                    change_pct = p.get("fluctuationsRatio", "0")
                    result["peers"].append({
                        "code": peer_code,
                        "name": p.get("stockName", ""),
                        "price": _parse_price(close_price),
                        "change": _parse_price(change),
                        "change_percent": _parse_float(change_pct),
                        "market_cap": _parse_int(p.get("marketValue", "0")),
                    })

                # 리서치 리포트
                researches = data.get("researches", [])
                for r_item in researches[:5]:  # 최근 5개
                    result["researches"].append({
                        "id": r_item.get("id"),
                        "title": r_item.get("tit", ""),
                        "broker": r_item.get("bnm", ""),
                        "date": r_item.get("wdt", ""),
                    })

                # 투자의견/목표가
                consensus = data.get("consensusInfo")
                if consensus:
                    result["consensus"] = {
                        "rating": _parse_float(consensus.get("recommMean", "0")),
                        "target_price": _parse_int(consensus.get("priceTargetMean", "0")),
                        "date": consensus.get("createDate", ""),
                    }

        _set_cache(cache_key, result)
    except Exception as e:
        print(f"[DataProvider] get_stock_company_kr error for {code}: {e}")
        traceback.print_exc()

    return result


async def get_stock_statement_kr(code: str, period_type: str = "annual") -> dict:
    """
    국내 종목 상세 재무제표 (손익계산서)
    period_type: annual(연간), quarter(분기)
    데이터 소스: 네이버 finance/annual, finance/quarter API
    """
    cache_key = f"stock_statement_kr_{code}_{period_type}"
    cached = _cached(cache_key, 3600)  # 1시간 캐싱
    if cached:
        return cached

    result = {
        "code": code,
        "period_type": period_type,
        "periods": [],  # 기간 목록 ["2022.12", "2023.12", ...]
        "rows": [
            {"label": "매출액", "values": []},
            {"label": "영업이익", "values": []},
            {"label": "당기순이익", "values": []},
            {"label": "EPS", "values": []},
            {"label": "영업이익률", "values": []},
            {"label": "순이익률", "values": []},
        ],
    }

    try:
        async with httpx.AsyncClient(timeout=15, headers=NAVER_HEADERS) as client:
            # 연간 또는 분기 재무 API
            endpoint = "annual" if period_type == "annual" else "quarter"
            url = f"https://m.stock.naver.com/api/stock/{code}/finance/{endpoint}"
            r = await client.get(url)

            if r.status_code == 200:
                data = r.json()
                fin_info = data.get("financeInfo", {})
                title_list = fin_info.get("trTitleList", [])
                row_list = fin_info.get("rowList", [])

                # 기간 목록
                periods = [t.get("title", "") for t in title_list]
                keys = [t.get("key", "") for t in title_list]
                result["periods"] = periods

                # 재무 데이터 매핑
                revenue = []
                op_profit = []
                net_income = []

                for row in row_list:
                    title = row.get("title", "")
                    columns = row.get("columns", {})
                    values = []
                    for k in keys:
                        v = columns.get(k, {}).get("value", "0")
                        # 숫자 파싱 (콤마, 하이픈 처리)
                        cleaned = v.replace(",", "").replace("-", "0").strip()
                        try:
                            values.append(int(float(cleaned)) if cleaned else 0)
                        except:
                            values.append(0)

                    if title == "매출액":
                        revenue = values
                    elif title == "영업이익":
                        op_profit = values
                    elif title == "당기순이익":
                        net_income = values

                # 결과 데이터 구성
                result["rows"] = [
                    {"label": "매출액", "values": revenue, "unit": "억원"},
                    {"label": "영업이익", "values": op_profit, "unit": "억원"},
                    {"label": "당기순이익", "values": net_income, "unit": "억원"},
                ]

                # 영업이익률, 순이익률 계산
                op_margin = []
                net_margin = []
                for i in range(len(revenue)):
                    rev = revenue[i] if i < len(revenue) else 0
                    op = op_profit[i] if i < len(op_profit) else 0
                    net = net_income[i] if i < len(net_income) else 0

                    if rev and rev > 0:
                        op_margin.append(round(op / rev * 100, 1))
                        net_margin.append(round(net / rev * 100, 1))
                    else:
                        op_margin.append(0)
                        net_margin.append(0)

                result["rows"].append({"label": "영업이익률", "values": op_margin, "unit": "%"})
                result["rows"].append({"label": "순이익률", "values": net_margin, "unit": "%"})

        _set_cache(cache_key, result)
    except Exception as e:
        print(f"[DataProvider] get_stock_statement_kr error for {code}: {e}")
        traceback.print_exc()

    return result


# =============================================================================
# Phase 9: 해외 종목 상세 (Finviz + Yahoo Finance)
# =============================================================================

FINVIZ_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Accept": "text/html,application/xhtml+xml",
    "Accept-Language": "en-US,en;q=0.9",
}


async def get_stock_summary_us(ticker: str) -> dict:
    """
    해외 종목 요약 정보
    데이터 소스: Finviz snapshot 테이블
    """
    ticker = ticker.upper()
    cache_key = f"stock_summary_us_{ticker}"
    cached = _cached(cache_key, 1800)  # 30분 캐싱
    if cached:
        return cached

    result = {
        "ticker": ticker,
        "name": "",
        "sector": "",
        "industry": "",
        "country": "",
        "exchange": "",
        "price": 0,
        "change": 0,
        "change_pct": 0,
        "market_cap": "",
        "market_cap_raw": 0,
        "per": 0,
        "forward_per": 0,
        "pbr": 0,
        "eps": 0,
        "roe": 0,
        "roa": 0,
        "dividend_yield": 0,
        "debt_equity": 0,
        "operating_margin": 0,
        "profit_margin": 0,
        "high_52w": 0,
        "low_52w": 0,
        "volume": 0,
        "avg_volume": 0,
        "target_price": 0,
        "recommendation": "",
    }

    try:
        async with httpx.AsyncClient(timeout=15, headers=FINVIZ_HEADERS) as client:
            url = f"https://finviz.com/quote.ashx?t={ticker}&ty=c&ta=1&p=d"
            r = await client.get(url)

            if r.status_code == 200:
                html = r.text
                data = _parse_finviz_snapshot(html)
                result.update(data)
                result["ticker"] = ticker

        _set_cache(cache_key, result)
    except Exception as e:
        print(f"[DataProvider] get_stock_summary_us error for {ticker}: {e}")
        traceback.print_exc()

    return result


def _parse_finviz_snapshot(html: str) -> dict:
    """Finviz snapshot 테이블 파싱 (BeautifulSoup 사용)"""
    data = {}

    try:
        soup = BeautifulSoup(html, 'lxml')

        # 종목명 추출 (title 태그에서)
        title_tag = soup.find('title')
        if title_tag:
            title_text = title_tag.get_text()
            # "NVDA - NVIDIA Corp Stock Price and Quote" → "NVIDIA Corp"
            if ' - ' in title_text:
                name_part = title_text.split(' - ', 1)[1]
                # "NVIDIA Corp Stock Price..." → "NVIDIA Corp"
                name_part = name_part.replace('Stock Price and Quote', '').strip()
                data["name"] = name_part

        # 현재가 추출 (quote-price_wrapper_price 클래스)
        price_el = soup.find(class_='quote-price_wrapper_price')
        if price_el:
            data["price"] = _parse_float(price_el.get_text(strip=True))

        # 섹터/인더스트리 추출 (링크에서)
        sector_link = soup.find('a', href=lambda x: x and 'sec_' in x)
        if sector_link:
            data["sector"] = sector_link.get_text(strip=True)
        industry_link = soup.find('a', href=lambda x: x and 'ind_' in x)
        if industry_link:
            data["industry"] = industry_link.get_text(strip=True)

        # snapshot-table2 파싱
        table = soup.find('table', class_='snapshot-table2')
        if table:
            cells = table.find_all('td', class_='snapshot-td2')

            # 셀은 key, value 쌍으로 나옴 (BeautifulSoup get_text 사용)
            snapshot = {}
            for i in range(0, len(cells) - 1, 2):
                key = cells[i].get_text(strip=True)
                value = cells[i + 1].get_text(strip=True) if i + 1 < len(cells) else ""
                snapshot[key] = value

            # 값 매핑 (링크에서 이미 추출된 sector/industry 유지)
            if not data.get("sector"):
                data["sector"] = snapshot.get("Sector", "")
            if not data.get("industry"):
                data["industry"] = snapshot.get("Industry", "")
            data["country"] = snapshot.get("Country", "")

            # 변동률 (Perf Week 등에서 추출하거나 Prev Close로 계산)
            prev_close = _parse_float(snapshot.get("Prev Close", "0"))
            if prev_close > 0 and data.get("price", 0) > 0:
                change = data["price"] - prev_close
                change_pct = (change / prev_close) * 100
                data["change"] = round(change, 2)
                data["change_pct"] = round(change_pct, 2)
            else:
                data["change"] = 0
                data["change_pct"] = 0

            # 시가총액
            mcap = snapshot.get("Market Cap", "")
            data["market_cap"] = mcap
            data["market_cap_raw"] = _parse_market_cap_us(mcap)

            # 재무 지표
            data["per"] = _parse_float(snapshot.get("P/E", "0"))
            data["forward_per"] = _parse_float(snapshot.get("Forward P/E", "0"))
            data["pbr"] = _parse_float(snapshot.get("P/B", "0"))
            data["eps"] = _parse_float(snapshot.get("EPS (ttm)", "0"))
            data["roe"] = _parse_float(snapshot.get("ROE", "0%").replace("%", ""))
            data["roa"] = _parse_float(snapshot.get("ROA", "0%").replace("%", ""))
            data["dividend_yield"] = _parse_float(snapshot.get("Dividend TTM", "0%").split("(")[-1].replace("%)", ""))
            data["debt_equity"] = _parse_float(snapshot.get("Debt/Eq", "0"))
            data["operating_margin"] = _parse_float(snapshot.get("Oper. Margin", "0%").replace("%", ""))
            data["profit_margin"] = _parse_float(snapshot.get("Profit Margin", "0%").replace("%", ""))

            # 52주 고저 (값이 "212.19-10.54%" 형식이므로 첫 번째 숫자만 추출)
            high_52w_str = snapshot.get("52W High", "0")
            low_52w_str = snapshot.get("52W Low", "0")
            # 정규식으로 첫 번째 숫자 추출 (212.19-10.54% → 212.19)
            high_match = re.match(r'([\d.]+)', high_52w_str)
            low_match = re.match(r'([\d.]+)', low_52w_str)
            data["high_52w"] = _parse_float(high_match.group(1)) if high_match else 0
            data["low_52w"] = _parse_float(low_match.group(1)) if low_match else 0

            # 거래량
            data["volume"] = _parse_volume_us(snapshot.get("Volume", "0"))
            data["avg_volume"] = _parse_volume_us(snapshot.get("Avg Volume", "0"))

            # 애널리스트
            data["target_price"] = _parse_float(snapshot.get("Target Price", "0"))
            data["recommendation"] = snapshot.get("Recom", "")

    except Exception as e:
        print(f"[Finviz] Parse error: {e}")
        traceback.print_exc()

    return data


def _parse_market_cap_us(mcap_str: str) -> float:
    """시가총액 파싱: 2.87T → 2870000000000"""
    if not mcap_str:
        return 0
    mcap_str = mcap_str.strip().upper()
    try:
        if mcap_str.endswith("T"):
            return float(mcap_str[:-1]) * 1e12
        elif mcap_str.endswith("B"):
            return float(mcap_str[:-1]) * 1e9
        elif mcap_str.endswith("M"):
            return float(mcap_str[:-1]) * 1e6
        else:
            return float(mcap_str.replace(",", ""))
    except:
        return 0


def _parse_volume_us(vol_str: str) -> int:
    """거래량 파싱: 48.23M → 48230000"""
    if not vol_str:
        return 0
    vol_str = vol_str.strip().upper()
    try:
        if vol_str.endswith("M"):
            return int(float(vol_str[:-1]) * 1e6)
        elif vol_str.endswith("K"):
            return int(float(vol_str[:-1]) * 1e3)
        elif vol_str.endswith("B"):
            return int(float(vol_str[:-1]) * 1e9)
        else:
            return int(float(vol_str.replace(",", "")))
    except:
        return 0


async def get_stock_chart_us(ticker: str, period: str = "3m") -> dict:
    """
    해외 종목 차트 데이터
    데이터 소스: Yahoo Finance Chart API
    """
    ticker = ticker.upper()
    cache_key = f"stock_chart_us_{ticker}_{period}"
    cached = _cached(cache_key, 300)  # 5분 캐싱
    if cached:
        return cached

    result = {
        "ticker": ticker,
        "period": period,
        "candles": []
    }

    # Yahoo Finance 기간 매핑
    range_map = {
        "1d": "1d",
        "5d": "5d",
        "1w": "5d",
        "1m": "1mo",
        "3m": "3mo",
        "6m": "6mo",
        "1y": "1y",
        "2y": "2y",
        "5y": "5y"
    }
    yf_range = range_map.get(period.lower(), "3mo")

    # 인터벌 결정
    interval = "1d"
    if period.lower() in ["1d", "5d", "1w"]:
        interval = "5m" if period.lower() == "1d" else "15m"

    try:
        async with httpx.AsyncClient(timeout=15) as client:
            url = f"https://query1.finance.yahoo.com/v8/finance/chart/{ticker}?range={yf_range}&interval={interval}"
            headers = {"User-Agent": "Mozilla/5.0"}
            r = await client.get(url, headers=headers)

            if r.status_code == 200:
                data = r.json()
                chart_data = data.get("chart", {}).get("result", [])
                if chart_data:
                    res = chart_data[0]
                    timestamps = res.get("timestamp", [])
                    quote = res.get("indicators", {}).get("quote", [{}])[0]

                    opens = quote.get("open", [])
                    highs = quote.get("high", [])
                    lows = quote.get("low", [])
                    closes = quote.get("close", [])
                    volumes = quote.get("volume", [])

                    candles = []
                    for i, ts in enumerate(timestamps):
                        if ts and i < len(opens) and opens[i] and i < len(closes) and closes[i]:
                            dt = datetime.fromtimestamp(ts)
                            candles.append({
                                "date": dt.strftime("%Y-%m-%d"),
                                "time": dt.strftime("%H:%M") if interval != "1d" else None,
                                "open": round(opens[i], 2) if opens[i] else 0,
                                "high": round(highs[i], 2) if i < len(highs) and highs[i] else 0,
                                "low": round(lows[i], 2) if i < len(lows) and lows[i] else 0,
                                "close": round(closes[i], 2) if closes[i] else 0,
                                "volume": volumes[i] if i < len(volumes) and volumes[i] else 0
                            })

                    result["candles"] = candles

        _set_cache(cache_key, result)
    except Exception as e:
        print(f"[DataProvider] get_stock_chart_us error for {ticker}: {e}")
        traceback.print_exc()

    return result


async def get_stock_news_us(ticker: str, limit: int = 20) -> dict:
    """
    해외 종목 뉴스
    데이터 소스: Finviz news-table
    """
    ticker = ticker.upper()
    cache_key = f"stock_news_us_{ticker}_{limit}"
    cached = _cached(cache_key, 900)  # 15분 캐싱
    if cached:
        return cached

    result = {
        "ticker": ticker,
        "items": []
    }

    try:
        async with httpx.AsyncClient(timeout=15, headers=FINVIZ_HEADERS) as client:
            url = f"https://finviz.com/quote.ashx?t={ticker}"
            r = await client.get(url)

            if r.status_code == 200:
                html = r.text
                news_items = _parse_finviz_news(html, limit)
                result["items"] = news_items

        _set_cache(cache_key, result)
    except Exception as e:
        print(f"[DataProvider] get_stock_news_us error for {ticker}: {e}")
        traceback.print_exc()

    return result


def _parse_finviz_news(html: str, limit: int = 20) -> list:
    """Finviz 뉴스 테이블 파싱"""
    news = []

    try:
        # news-table 찾기
        table_match = re.search(r'id="news-table"[^>]*>(.*?)</table>', html, re.DOTALL)
        if table_match:
            table_html = table_match.group(1)
            # 각 뉴스 행 파싱
            rows = re.findall(r'<tr[^>]*>(.*?)</tr>', table_html, re.DOTALL)

            current_date = ""
            for row in rows:
                # 시간/날짜 추출
                time_match = re.search(r'<td[^>]*>\s*([\w\-]+\s+\d+:\d+[AP]M|\d+:\d+[AP]M|Today\s+\d+:\d+[AP]M)\s*</td>', row)
                time_str = ""
                if time_match:
                    time_str = time_match.group(1).strip()
                    if "Today" not in time_str and len(time_str) > 10:
                        current_date = time_str.split()[0] if " " in time_str else time_str

                # 뉴스 링크/제목 추출
                link_match = re.search(r"trackAndOpenNews\([^,]+,\s*'([^']+)',\s*'([^']+)'\)", row)
                if link_match:
                    source = link_match.group(1)
                    url = link_match.group(2)

                    # 제목 추출
                    title_match = re.search(r'class="tab-link[^"]*"[^>]*>([^<]+)</a>', row)
                    title = title_match.group(1).strip() if title_match else ""

                    if title:
                        news.append({
                            "title": title,
                            "source": source,
                            "url": url,
                            "date": current_date or "Today",
                            "time": time_str
                        })

                if len(news) >= limit:
                    break

    except Exception as e:
        print(f"[Finviz] News parse error: {e}")

    return news


async def get_stock_company_us(ticker: str) -> dict:
    """
    해외 종목 기업 정보
    데이터 소스: Finviz snapshot + 기업 설명
    """
    ticker = ticker.upper()
    cache_key = f"stock_company_us_{ticker}"
    cached = _cached(cache_key, 3600)  # 1시간 캐싱
    if cached:
        return cached

    result = {
        "ticker": ticker,
        "name": "",
        "sector": "",
        "industry": "",
        "country": "",
        "exchange": "",
        "description": "",
        "employees": "",
        "website": "",
        "target_price": 0,
        "recommendation": "",
        "peers": []
    }

    try:
        async with httpx.AsyncClient(timeout=15, headers=FINVIZ_HEADERS) as client:
            url = f"https://finviz.com/quote.ashx?t={ticker}"
            r = await client.get(url)

            if r.status_code == 200:
                html = r.text

                # 기본 정보 (snapshot에서)
                summary = _parse_finviz_snapshot(html)
                result["name"] = summary.get("name", "")
                result["sector"] = summary.get("sector", "")
                result["industry"] = summary.get("industry", "")
                result["country"] = summary.get("country", "")
                result["target_price"] = summary.get("target_price", 0)
                result["recommendation"] = summary.get("recommendation", "")

                # 기업 설명 (fullview-profile 클래스에서)
                desc_match = re.search(r'class="fullview-profile"[^>]*>(.*?)</td>', html, re.DOTALL)
                if desc_match:
                    desc_html = desc_match.group(1)
                    # HTML 태그 제거
                    desc_text = re.sub(r'<[^>]+>', '', desc_html).strip()
                    result["description"] = desc_text[:1000]  # 최대 1000자

                # 직원 수
                emp_match = re.search(r'Employees[^<]*</td>\s*<td[^>]*>([^<]+)</td>', html)
                if emp_match:
                    result["employees"] = emp_match.group(1).strip()

        _set_cache(cache_key, result)
    except Exception as e:
        print(f"[DataProvider] get_stock_company_us error for {ticker}: {e}")
        traceback.print_exc()

    return result


async def get_stock_financials_us(ticker: str, fin_type: str = "annual") -> dict:
    """
    해외 종목 재무 추이
    Yahoo Finance 차단으로 추이 데이터 없음 - Finviz 스냅샷 지표만 제공
    """
    ticker = ticker.upper()
    cache_key = f"stock_financials_us_{ticker}_{fin_type}"
    cached = _cached(cache_key, 1800)  # 30분 캐싱
    if cached:
        return cached

    result = {
        "ticker": ticker,
        "type": fin_type,
        "periods": [],
        "revenue": [],
        "operating_profit": [],
        "net_income": [],
        "eps": [],
        "note": "Detailed financial trends are not available."
    }

    # Finviz에서 현재 스냅샷 지표만 가져옴
    try:
        summary = await get_stock_summary_us(ticker)
        if summary:
            # 현재 데이터만 제공
            result["eps"] = [summary.get("eps", 0)]
            result["per"] = summary.get("per", 0)
            result["operating_margin"] = summary.get("operating_margin", 0)
            result["profit_margin"] = summary.get("profit_margin", 0)

        _set_cache(cache_key, result)
    except Exception as e:
        print(f"[DataProvider] get_stock_financials_us error for {ticker}: {e}")
        traceback.print_exc()

    return result


# =============================================================================
# Phase 10: ETF 상세 페이지
# =============================================================================

async def get_etf_summary(code: str) -> dict:
    """
    ETF 개요 정보
    데이터 소스: 네이버 integration + basic API
    """
    cache_key = f"etf_summary_{code}"
    cached = _cached(cache_key, 300)  # 5분 캐싱
    if cached:
        return cached

    result = {
        "code": code,
        "name": "",
        "price": 0,
        "change": 0,
        "change_pct": 0,
        "nav": 0,
        "premium_discount": 0,
        "market_cap": "",
        "total_expense_ratio": 0,
        "fund_company": "",
        "dividend_yield": 0,
        "volume": 0,
        "aum": "",
        "return_1m": 0,
        "return_3m": 0,
        "return_1y": 0
    }

    try:
        async with httpx.AsyncClient(timeout=15) as client:
            headers = {"User-Agent": "Mozilla/5.0"}

            # integration API
            url_int = f"https://m.stock.naver.com/api/stock/{code}/integration"
            r_int = await client.get(url_int, headers=headers)

            if r_int.status_code == 200:
                data = r_int.json()

                result["name"] = data.get("stockName", "")

                # etfKeyIndicator
                etf_ind = data.get("etfKeyIndicator", {})
                if etf_ind:
                    result["fund_company"] = etf_ind.get("issuerName", "")
                    result["market_cap"] = etf_ind.get("marketValue", "")
                    result["aum"] = etf_ind.get("totalNav", "")
                    result["dividend_yield"] = etf_ind.get("dividendYieldTtm", 0) or 0
                    result["total_expense_ratio"] = etf_ind.get("totalFee", 0) or 0
                    result["return_1m"] = etf_ind.get("returnRate1m", 0) or 0
                    result["return_3m"] = etf_ind.get("returnRate3m", 0) or 0
                    result["return_1y"] = etf_ind.get("returnRate1y", 0) or 0

                    # NAV 파싱
                    nav_str = etf_ind.get("nav", "0")
                    if isinstance(nav_str, str):
                        nav_str = nav_str.replace(",", "")
                    try:
                        result["nav"] = float(nav_str)
                    except:
                        result["nav"] = 0

                    # 괴리율
                    dev_sign = etf_ind.get("deviationSign", "")
                    dev_rate = etf_ind.get("deviationRate", 0) or 0
                    if dev_sign == "-":
                        result["premium_discount"] = -dev_rate
                    else:
                        result["premium_discount"] = dev_rate

            # basic API로 가격 정보
            url_basic = f"https://m.stock.naver.com/api/stock/{code}/basic"
            r_basic = await client.get(url_basic, headers=headers)

            if r_basic.status_code == 200:
                basic = r_basic.json()

                # 현재가
                price_str = basic.get("closePrice", "0")
                if isinstance(price_str, str):
                    price_str = price_str.replace(",", "")
                try:
                    result["price"] = int(float(price_str))
                except:
                    pass

                # 변동
                change_str = basic.get("compareToPreviousClosePrice", "0")
                if isinstance(change_str, str):
                    change_str = change_str.replace(",", "")
                try:
                    result["change"] = int(float(change_str))
                except:
                    pass

                # 변동률
                rate_str = basic.get("fluctuationsRatio", "0")
                try:
                    result["change_pct"] = float(rate_str)
                except:
                    pass

                # 이름 (없으면 basic에서)
                if not result["name"]:
                    result["name"] = basic.get("stockName", code)

        _set_cache(cache_key, result)
    except Exception as e:
        print(f"[DataProvider] get_etf_summary error for {code}: {e}")
        traceback.print_exc()

    return result


async def get_etf_chart(code: str, period: str = "3m") -> dict:
    """
    ETF 차트 데이터
    데이터 소스: 네이버 fchart (국내 주식과 동일)
    """
    # 국내 주식 차트 API 재활용
    return await get_stock_chart_kr(code, period)


async def get_etf_performance(code: str) -> dict:
    """
    ETF 수익률 및 분배금 정보
    데이터 소스: 네이버 integration API
    """
    cache_key = f"etf_performance_{code}"
    cached = _cached(cache_key, 300)
    if cached:
        return cached

    result = {
        "code": code,
        "returns": {
            "1m": 0,
            "3m": 0,
            "6m": 0,
            "1y": 0,
            "ytd": 0
        },
        "dividend_yield": 0,
        "dividends": []
    }

    try:
        async with httpx.AsyncClient(timeout=15) as client:
            headers = {"User-Agent": "Mozilla/5.0"}

            url = f"https://m.stock.naver.com/api/stock/{code}/integration"
            r = await client.get(url, headers=headers)

            if r.status_code == 200:
                data = r.json()

                etf_ind = data.get("etfKeyIndicator", {})
                if etf_ind:
                    result["returns"]["1m"] = etf_ind.get("returnRate1m", 0) or 0
                    result["returns"]["3m"] = etf_ind.get("returnRate3m", 0) or 0
                    result["returns"]["1y"] = etf_ind.get("returnRate1y", 0) or 0
                    result["dividend_yield"] = etf_ind.get("dividendYieldTtm", 0) or 0

        _set_cache(cache_key, result)
    except Exception as e:
        print(f"[DataProvider] get_etf_performance error for {code}: {e}")
        traceback.print_exc()

    return result


# =============================================================================
# EPS 추정추이 (FnGuide Consensus Revision History)
# =============================================================================

async def get_eps_revision_history(code: str) -> dict:
    """
    FnGuide 컨센서스 EPS 추정 변화 이력 가져오기
    데이터 소스: comp.fnguide.com 02_ JSON

    반환:
    {
        "fy1": {"year": "2026", "eps": [1832, 1178, 1171, 1255, 1220], "labels": ["1년전", "6개월전", "3개월전", "1개월전", "현재"]},
        "fy2": {"year": "2027", "eps": [...], "labels": [...]},
        "fy3": {"year": "2028", "eps": [...], "labels": [...]}
    }
    """
    cache_key = f"eps_revision_{code}"
    cached = _cached(cache_key, 3600)  # 1시간 캐싱
    if cached:
        return cached

    result = {}

    try:
        async with httpx.AsyncClient(timeout=15) as client:
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                "Referer": "http://comp.fnguide.com/"
            }

            # FY1, FY2, FY3 → 올해+1, 올해+2, 올해+3 (FnGuide 기준)
            current_year = datetime.now().year
            fy_year_map = {
                "FY1": str(current_year),      # 2026
                "FY2": str(current_year + 1),  # 2027
                "FY3": str(current_year + 2),  # 2028
            }

            for fy in ["FY1", "FY2", "FY3"]:
                url = f"http://comp.fnguide.com/SVO2/json/data/01_06/02_A{code}_A_D_{fy}.json"

                try:
                    r = await client.get(url, headers=headers)
                    if r.status_code == 200:
                        data = r.json()
                        comp = data.get("comp", [])

                        # EPS 행 찾기
                        eps_data = []
                        for row in comp:
                            if row.get("D_0", "").startswith("EPS"):
                                # D_5(1년전), D_4(6개월전), D_3(3개월전), D_2(1개월전), D_1(현재)
                                for col in ["D_5", "D_4", "D_3", "D_2", "D_1"]:
                                    val = row.get(col, "")
                                    if val:
                                        # 숫자만 추출
                                        val_clean = val.replace(",", "").replace("원", "").strip()
                                        try:
                                            eps_data.append(int(float(val_clean)))
                                        except:
                                            eps_data.append(None)
                                    else:
                                        eps_data.append(None)
                                break

                        if eps_data and any(v is not None for v in eps_data):
                            result[fy.lower()] = {
                                "year": fy_year_map[fy],
                                "eps": eps_data,
                                "labels": ["1년전", "6개월전", "3개월전", "1개월전", "현재"]
                            }
                except Exception as e:
                    print(f"[EPS Revision] {fy} fetch error: {e}")
                    continue

        if result:
            _set_cache(cache_key, result)

    except Exception as e:
        print(f"[DataProvider] get_eps_revision_history error for {code}: {e}")
        traceback.print_exc()

    return result

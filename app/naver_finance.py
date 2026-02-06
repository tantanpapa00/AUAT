"""
네이버 금융 데이터 수집 모듈 (모바일 API 기반)
- 코스피/코스닥 지수
- 투자자별 순매수
- 업종별 등락률
- 개별 종목 시세
- 일봉 데이터
- 52주 신고가
- ETF 목록

네이버 모바일 API는 JSON 반환 (HTML 파싱 불필요)
"""

import httpx
from typing import Optional, List, Dict, Any
from datetime import datetime, timedelta

# 공통 헤더 (모바일 API용)
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "application/json",
    "Referer": "https://m.stock.naver.com/",
}

# 타임아웃 설정
TIMEOUT = 10.0


def _safe_int(value, default=0) -> int:
    """안전한 정수 변환"""
    if value is None:
        return default
    try:
        if isinstance(value, str):
            return int(value.replace(",", "").replace("+", "").strip())
        return int(value)
    except (ValueError, TypeError):
        return default


def _safe_float(value, default=0.0) -> float:
    """안전한 실수 변환"""
    if value is None:
        return default
    try:
        if isinstance(value, str):
            return float(value.replace(",", "").replace("+", "").replace("%", "").strip())
        return float(value)
    except (ValueError, TypeError):
        return default


async def get_kospi_index() -> Dict[str, Any]:
    """코스피 지수 가져오기 (모바일 API)"""
    try:
        async with httpx.AsyncClient(timeout=TIMEOUT) as client:
            resp = await client.get(
                "https://m.stock.naver.com/api/index/KOSPI/basic",
                headers=HEADERS
            )
            if resp.status_code != 200:
                raise Exception(f"HTTP {resp.status_code}")

            data = resp.json()

            current = _safe_float(data.get("closePrice"))
            change = _safe_float(data.get("compareToPreviousClosePrice"))
            change_pct = _safe_float(data.get("fluctuationsRatio"))
            volume = _safe_int(data.get("accumulatedTradingVolume"))

            return {
                "name": "KOSPI",
                "current": current,
                "change": change,
                "change_percent": change_pct,
                "volume": volume,
            }
    except Exception as e:
        print(f"[NaverFinance] KOSPI 지수 조회 실패: {e}")
        return {"name": "KOSPI", "current": 0, "change": 0, "change_percent": 0, "error": str(e)}


async def get_kosdaq_index() -> Dict[str, Any]:
    """코스닥 지수 가져오기 (모바일 API)"""
    try:
        async with httpx.AsyncClient(timeout=TIMEOUT) as client:
            resp = await client.get(
                "https://m.stock.naver.com/api/index/KOSDAQ/basic",
                headers=HEADERS
            )
            if resp.status_code != 200:
                raise Exception(f"HTTP {resp.status_code}")

            data = resp.json()

            current = _safe_float(data.get("closePrice"))
            change = _safe_float(data.get("compareToPreviousClosePrice"))
            change_pct = _safe_float(data.get("fluctuationsRatio"))

            return {
                "name": "KOSDAQ",
                "current": current,
                "change": change,
                "change_percent": change_pct,
            }
    except Exception as e:
        print(f"[NaverFinance] KOSDAQ 지수 조회 실패: {e}")
        return {"name": "KOSDAQ", "current": 0, "change": 0, "change_percent": 0, "error": str(e)}


async def get_investor_trend() -> Dict[str, Any]:
    """투자자별 순매수 가져오기 (외인/기관/개인)"""
    try:
        async with httpx.AsyncClient(timeout=TIMEOUT) as client:
            # 코스피 투자자별 매매동향
            resp = await client.get(
                "https://m.stock.naver.com/api/index/KOSPI/investorTrend",
                headers=HEADERS
            )
            if resp.status_code != 200:
                raise Exception(f"HTTP {resp.status_code}")

            data = resp.json()
            investors = data.get("investorTrends", [])

            today_data = {"foreign": 0, "institution": 0, "individual": 0}

            for inv in investors:
                name = inv.get("name", "")
                net = _safe_int(inv.get("netPurchaseVolume"))

                if "외국인" in name or "foreign" in name.lower():
                    today_data["foreign"] = net
                elif "기관" in name or "institution" in name.lower():
                    today_data["institution"] = net
                elif "개인" in name or "individual" in name.lower():
                    today_data["individual"] = net

            return today_data
    except Exception as e:
        print(f"[NaverFinance] 투자자별 동향 조회 실패: {e}")
        return {"foreign": 0, "institution": 0, "individual": 0, "error": str(e)}


async def get_sector_ranking() -> List[Dict[str, Any]]:
    """업종별 등락률 TOP 10 (모바일 API - 업종 지수 기반)"""
    try:
        async with httpx.AsyncClient(timeout=TIMEOUT) as client:
            # 업종 지수 조회 (KOSPI 섹터)
            resp = await client.get(
                "https://m.stock.naver.com/api/index/KOSPI/all",
                headers=HEADERS
            )
            if resp.status_code != 200:
                raise Exception(f"HTTP {resp.status_code}")

            data = resp.json()
            sectors_data = data.get("sectors", [])

            sectors = []
            for sector in sectors_data:
                name = sector.get("sectorName", "")
                if not name:
                    continue
                sectors.append({
                    "code": sector.get("code", ""),
                    "name": name,
                    "current": _safe_float(sector.get("closePrice")),
                    "change": _safe_float(sector.get("compareToPreviousClosePrice")),
                    "change_percent": _safe_float(sector.get("fluctuationsRatio")),
                })

            # 등락률 순 정렬
            sectors.sort(key=lambda x: x["change_percent"], reverse=True)
            return sectors[:10]
    except Exception as e:
        print(f"[NaverFinance] 업종 순위 조회 실패: {e}")
        return []


async def get_stock_price(code: str) -> Dict[str, Any]:
    """개별 종목 현재가 (모바일 API)"""
    try:
        async with httpx.AsyncClient(timeout=TIMEOUT) as client:
            resp = await client.get(
                f"https://m.stock.naver.com/api/stock/{code}/basic",
                headers=HEADERS
            )
            if resp.status_code != 200:
                raise Exception(f"HTTP {resp.status_code}")

            data = resp.json()

            current = _safe_int(data.get("closePrice"))
            change = _safe_int(data.get("compareToPreviousClosePrice"))
            change_pct = _safe_float(data.get("fluctuationsRatio"))
            volume = _safe_int(data.get("accumulatedTradingVolume"))
            open_price = _safe_int(data.get("openPrice"))
            high = _safe_int(data.get("highPrice"))
            low = _safe_int(data.get("lowPrice"))
            market_cap = _safe_int(data.get("marketValue"))

            # PER/PBR
            per = data.get("per", "-")
            pbr = data.get("pbr", "-")

            return {
                "code": code,
                "name": data.get("stockName", code),
                "price": current,
                "change": change,
                "change_percent": change_pct,
                "volume": volume,
                "open": open_price,
                "high": high,
                "low": low,
                "market_cap": market_cap,
                "per": per if per else "-",
                "pbr": pbr if pbr else "-",
            }
    except Exception as e:
        print(f"[NaverFinance] 종목 {code} 시세 조회 실패: {e}")
        return {"code": code, "name": code, "price": 0, "error": str(e)}


async def get_stock_daily_prices(code: str, days: int = 252) -> List[Dict[str, Any]]:
    """일봉 데이터 (모바일 API 차트 데이터)"""
    try:
        async with httpx.AsyncClient(timeout=TIMEOUT) as client:
            resp = await client.get(
                f"https://m.stock.naver.com/api/stock/{code}/price",
                params={"pageSize": min(days, 365), "page": 1},
                headers=HEADERS
            )
            if resp.status_code != 200:
                raise Exception(f"HTTP {resp.status_code}")

            data = resp.json()
            items = data if isinstance(data, list) else data.get("priceInfos", [])

            results = []
            for item in items[:days]:
                date_str = item.get("localDate", "")
                if not date_str:
                    continue

                results.append({
                    "date": date_str.replace("-", ""),
                    "open": _safe_int(item.get("openPrice")),
                    "high": _safe_int(item.get("highPrice")),
                    "low": _safe_int(item.get("lowPrice")),
                    "close": _safe_int(item.get("closePrice")),
                    "volume": _safe_int(item.get("accumulatedTradingVolume")),
                })

            # 날짜 순 정렬 (오래된 것부터)
            results.reverse()
            return results
    except Exception as e:
        print(f"[NaverFinance] 종목 {code} 일봉 조회 실패: {e}")
        return []


async def get_new_high_stocks() -> List[Dict[str, Any]]:
    """52주 신고가 종목 리스트 (모바일 API)"""
    try:
        async with httpx.AsyncClient(timeout=TIMEOUT) as client:
            # 상승률 상위 종목 조회 (신고가 대용)
            resp = await client.get(
                "https://m.stock.naver.com/api/stocks/rise/KOSPI",
                params={"page": 1, "pageSize": 30},
                headers=HEADERS
            )
            if resp.status_code != 200:
                raise Exception(f"HTTP {resp.status_code}")

            data = resp.json()
            stocks = data.get("stocks", [])

            results = []
            for stock in stocks:
                results.append({
                    "code": stock.get("itemCode", ""),
                    "name": stock.get("stockName", ""),
                    "price": _safe_int(stock.get("closePrice")),
                    "change": stock.get("compareToPreviousClosePrice", "0"),
                    "change_percent": _safe_float(stock.get("fluctuationsRatio")),
                    "high52": _safe_int(stock.get("closePrice")),  # 실제 52주 고가는 별도 API 필요
                })

            return results[:30]
    except Exception as e:
        print(f"[NaverFinance] 52주 신고가 조회 실패: {e}")
        return []


async def get_etf_list() -> List[Dict[str, Any]]:
    """ETF 전체 목록 + 시세 (모바일 API)"""
    try:
        async with httpx.AsyncClient(timeout=TIMEOUT) as client:
            # ETF 리스트 조회
            resp = await client.get(
                "https://m.stock.naver.com/api/stocks/marketType/ETF",
                params={"page": 1, "pageSize": 100},
                headers=HEADERS
            )
            if resp.status_code != 200:
                raise Exception(f"HTTP {resp.status_code}")

            data = resp.json()
            stocks = data.get("stocks", [])

            etfs = []
            for stock in stocks:
                name = stock.get("stockName", "")
                code = stock.get("itemCode", "")

                etfs.append({
                    "code": code,
                    "name": name,
                    "price": _safe_int(stock.get("closePrice")),
                    "nav": 0,  # NAV는 별도 API 필요
                    "change": stock.get("compareToPreviousClosePrice", "0"),
                    "change_percent": _safe_float(stock.get("fluctuationsRatio")),
                    "volume": _safe_int(stock.get("accumulatedTradingVolume")),
                    "sector": categorize_etf(name),
                })

            return etfs
    except Exception as e:
        print(f"[NaverFinance] ETF 목록 조회 실패: {e}")
        return []


def categorize_etf(name: str) -> str:
    """ETF 이름 기반 섹터 분류"""
    name_upper = name.upper()

    if any(kw in name_upper for kw in ["반도체", "SEMICONDUCTOR"]):
        return "반도체"
    elif any(kw in name_upper for kw in ["2차전지", "배터리", "BATTERY"]):
        return "2차전지"
    elif any(kw in name_upper for kw in ["AI", "인공지능", "소프트", "SOFTWARE"]):
        return "AI"
    elif any(kw in name_upper for kw in ["바이오", "헬스", "제약", "BIO", "HEALTH"]):
        return "바이오"
    elif any(kw in name_upper for kw in ["자동차", "전기차", "모빌리티", "EV", "AUTO"]):
        return "자동차"
    elif any(kw in name_upper for kw in ["배당", "고배당", "DIVIDEND"]):
        return "배당"
    elif any(kw in name_upper for kw in ["인버스", "곱버스", "INVERSE"]):
        return "인버스"
    elif any(kw in name_upper for kw in ["레버리지", "LEVERAGE", "2X", "3X"]):
        return "레버리지"
    elif any(kw in name_upper for kw in ["미국", "S&P", "나스닥", "NASDAQ", "글로벌", "US", "GLOBAL"]):
        return "해외"
    elif any(kw in name_upper for kw in ["금", "원유", "원자재", "GOLD", "OIL", "COMMODITY"]):
        return "원자재"
    elif any(kw in name_upper for kw in ["채권", "BOND"]):
        return "채권"
    else:
        return "기타"


async def calculate_rs_score(code: str) -> Dict[str, Any]:
    """종목 RS(Relative Strength) 점수 계산"""
    try:
        prices = await get_stock_daily_prices(code, 130)  # 6개월치
        if len(prices) < 22:
            return {"rs_1m": None, "rs_3m": None, "rs_6m": None, "rs_total": None}

        current = prices[-1]["close"]
        if current == 0:
            return {"rs_1m": None, "rs_3m": None, "rs_6m": None, "rs_total": None}

        # 1개월 전 (약 22거래일)
        price_1m = prices[-22]["close"] if len(prices) >= 22 else prices[0]["close"]
        rs_1m = ((current - price_1m) / price_1m) * 100 if price_1m else 0

        # 3개월 전 (약 66거래일)
        price_3m = prices[-66]["close"] if len(prices) >= 66 else prices[0]["close"]
        rs_3m = ((current - price_3m) / price_3m) * 100 if price_3m else 0

        # 6개월 전 (약 130거래일)
        price_6m = prices[0]["close"]
        rs_6m = ((current - price_6m) / price_6m) * 100 if price_6m else 0

        # 종합 RS (가중 평균)
        rs_total = (rs_1m * 0.4 + rs_3m * 0.35 + rs_6m * 0.25)

        return {
            "rs_1m": round(rs_1m, 2),
            "rs_3m": round(rs_3m, 2),
            "rs_6m": round(rs_6m, 2),
            "rs_total": round(rs_total, 2),
        }
    except Exception as e:
        print(f"[NaverFinance] RS 계산 실패 {code}: {e}")
        return {"rs_1m": None, "rs_3m": None, "rs_6m": None, "rs_total": None}


async def get_volume_rank(limit: int = 50) -> List[Dict[str, Any]]:
    """거래량 순위 (모바일 API)"""
    try:
        async with httpx.AsyncClient(timeout=TIMEOUT) as client:
            resp = await client.get(
                "https://m.stock.naver.com/api/stocks/volume/KOSPI",
                params={"page": 1, "pageSize": limit},
                headers=HEADERS
            )
            if resp.status_code != 200:
                raise Exception(f"HTTP {resp.status_code}")

            data = resp.json()
            stocks = data.get("stocks", [])

            results = []
            for i, stock in enumerate(stocks[:limit]):
                results.append({
                    "rank": i + 1,
                    "code": stock.get("itemCode", ""),
                    "name": stock.get("stockName", ""),
                    "current": _safe_int(stock.get("closePrice")),
                    "change": _safe_float(stock.get("fluctuationsRatio")),
                    "volume": _safe_int(stock.get("accumulatedTradingVolume")),
                })

            return results
    except Exception as e:
        print(f"[NaverFinance] 거래량 순위 조회 실패: {e}")
        return []


async def get_fluctuation_rank(is_rise: bool = True, limit: int = 50) -> List[Dict[str, Any]]:
    """등락률 순위 (모바일 API)"""
    try:
        endpoint = "rise" if is_rise else "fall"
        async with httpx.AsyncClient(timeout=TIMEOUT) as client:
            resp = await client.get(
                f"https://m.stock.naver.com/api/stocks/{endpoint}/KOSPI",
                params={"page": 1, "pageSize": limit},
                headers=HEADERS
            )
            if resp.status_code != 200:
                raise Exception(f"HTTP {resp.status_code}")

            data = resp.json()
            stocks = data.get("stocks", [])

            results = []
            for i, stock in enumerate(stocks[:limit]):
                results.append({
                    "rank": i + 1,
                    "code": stock.get("itemCode", ""),
                    "name": stock.get("stockName", ""),
                    "current": _safe_int(stock.get("closePrice")),
                    "change": _safe_float(stock.get("fluctuationsRatio")),
                    "volume": _safe_int(stock.get("accumulatedTradingVolume")),
                })

            return results
    except Exception as e:
        print(f"[NaverFinance] 등락률 순위 조회 실패: {e}")
        return []

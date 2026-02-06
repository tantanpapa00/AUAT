"""
네이버 금융 데이터 수집 모듈
- 코스피/코스닥 지수
- 투자자별 순매수
- 업종별 등락률
- 개별 종목 시세
- 일봉 데이터
- 52주 신고가
- ETF 목록
"""

import httpx
import re
import json
from typing import Optional, List, Dict, Any
from datetime import datetime, timedelta
from bs4 import BeautifulSoup

# 공통 헤더
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7",
}

# 타임아웃 설정
TIMEOUT = 10.0


async def get_kospi_index() -> Dict[str, Any]:
    """코스피 지수 가져오기"""
    try:
        async with httpx.AsyncClient(timeout=TIMEOUT) as client:
            resp = await client.get(
                "https://finance.naver.com/sise/sise_index.naver?code=KOSPI",
                headers=HEADERS
            )
            soup = BeautifulSoup(resp.text, "lxml")

            # 현재가
            now_val = soup.select_one("#now_value")
            current = float(now_val.text.replace(",", "")) if now_val else 0

            # 전일대비
            change_val = soup.select_one("#change_value_and_rate")
            if change_val:
                text = change_val.get_text(strip=True)
                parts = text.split()
                change = float(parts[0].replace(",", "").replace("+", "")) if parts else 0
                change_pct = float(parts[1].replace("%", "").replace("+", "")) if len(parts) > 1 else 0
            else:
                change, change_pct = 0, 0

            # 거래량/거래대금
            volume_el = soup.select_one(".subtop_sise_detail .lst_kos dd:nth-child(4)")
            volume = volume_el.text.replace(",", "") if volume_el else "0"

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
    """코스닥 지수 가져오기"""
    try:
        async with httpx.AsyncClient(timeout=TIMEOUT) as client:
            resp = await client.get(
                "https://finance.naver.com/sise/sise_index.naver?code=KOSDAQ",
                headers=HEADERS
            )
            soup = BeautifulSoup(resp.text, "lxml")

            now_val = soup.select_one("#now_value")
            current = float(now_val.text.replace(",", "")) if now_val else 0

            change_val = soup.select_one("#change_value_and_rate")
            if change_val:
                text = change_val.get_text(strip=True)
                parts = text.split()
                change = float(parts[0].replace(",", "").replace("+", "")) if parts else 0
                change_pct = float(parts[1].replace("%", "").replace("+", "")) if len(parts) > 1 else 0
            else:
                change, change_pct = 0, 0

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
            resp = await client.get(
                "https://finance.naver.com/sise/investorDealTrendDay.naver",
                headers=HEADERS
            )
            soup = BeautifulSoup(resp.text, "lxml")

            # 테이블에서 오늘 데이터 추출
            rows = soup.select("table.type2 tr")
            today_data = {"foreign": 0, "institution": 0, "individual": 0}

            for row in rows[2:3]:  # 첫 번째 데이터 행 (오늘)
                cols = row.select("td")
                if len(cols) >= 4:
                    # 개인, 외국인, 기관 순서
                    individual = cols[1].get_text(strip=True).replace(",", "").replace("+", "")
                    foreign = cols[2].get_text(strip=True).replace(",", "").replace("+", "")
                    institution = cols[3].get_text(strip=True).replace(",", "").replace("+", "")

                    today_data = {
                        "individual": int(individual) if individual.lstrip('-').isdigit() else 0,
                        "foreign": int(foreign) if foreign.lstrip('-').isdigit() else 0,
                        "institution": int(institution) if institution.lstrip('-').isdigit() else 0,
                    }

            return today_data
    except Exception as e:
        print(f"[NaverFinance] 투자자별 동향 조회 실패: {e}")
        return {"foreign": 0, "institution": 0, "individual": 0, "error": str(e)}


async def get_sector_ranking() -> List[Dict[str, Any]]:
    """업종별 등락률 TOP 10"""
    try:
        async with httpx.AsyncClient(timeout=TIMEOUT) as client:
            resp = await client.get(
                "https://finance.naver.com/sise/sise_group.naver?type=upjong",
                headers=HEADERS
            )
            soup = BeautifulSoup(resp.text, "lxml")

            sectors = []
            rows = soup.select("table.type_1 tr")

            for row in rows:
                cols = row.select("td")
                if len(cols) >= 4:
                    name_el = cols[0].select_one("a")
                    if name_el:
                        name = name_el.get_text(strip=True)
                        change_pct = cols[1].get_text(strip=True).replace("%", "").replace("+", "")

                        sectors.append({
                            "name": name,
                            "change_percent": float(change_pct) if change_pct.lstrip('-').replace('.','').isdigit() else 0,
                        })

            # 등락률 순 정렬
            sectors.sort(key=lambda x: x["change_percent"], reverse=True)
            return sectors[:10]
    except Exception as e:
        print(f"[NaverFinance] 업종 순위 조회 실패: {e}")
        return []


async def get_stock_price(code: str) -> Dict[str, Any]:
    """개별 종목 현재가 (네이버)"""
    try:
        async with httpx.AsyncClient(timeout=TIMEOUT) as client:
            resp = await client.get(
                f"https://finance.naver.com/item/main.naver?code={code}",
                headers=HEADERS
            )
            soup = BeautifulSoup(resp.text, "lxml")

            # 종목명
            name_el = soup.select_one(".wrap_company h2 a")
            name = name_el.get_text(strip=True) if name_el else code

            # 현재가
            price_el = soup.select_one(".no_today .blind")
            current = int(price_el.text.replace(",", "")) if price_el else 0

            # 전일대비
            change_el = soup.select_one(".no_exday .blind")
            change_text = change_el.text.replace(",", "") if change_el else "0"

            # 상승/하락 확인
            is_up = soup.select_one(".no_exday .ico.up") is not None
            is_down = soup.select_one(".no_exday .ico.down") is not None
            change = int(change_text) if change_text.isdigit() else 0
            if is_down:
                change = -change

            # 등락률
            rate_el = soup.select_one(".no_exday em:nth-child(4) .blind")
            change_pct = float(rate_el.text.replace("%", "")) if rate_el else 0
            if is_down:
                change_pct = -change_pct

            # 거래량
            vol_el = soup.select_one("#_quant")
            volume = int(vol_el.text.replace(",", "")) if vol_el else 0

            # 시가/고가/저가
            sise_list = soup.select(".no_info tr td .blind")
            open_price = int(sise_list[0].text.replace(",", "")) if len(sise_list) > 0 else 0
            high = int(sise_list[1].text.replace(",", "")) if len(sise_list) > 1 else 0
            low = int(sise_list[4].text.replace(",", "")) if len(sise_list) > 4 else 0

            # 시가총액
            market_cap_el = soup.select_one("#_market_sum")
            market_cap = market_cap_el.text.strip().replace(",", "").replace("조", "") if market_cap_el else "0"

            # PER/PBR
            per_el = soup.select_one("#_per")
            per = per_el.text.strip() if per_el else "-"
            pbr_el = soup.select_one("#_pbr")
            pbr = pbr_el.text.strip() if pbr_el else "-"

            return {
                "code": code,
                "name": name,
                "price": current,
                "change": change,
                "change_percent": change_pct,
                "volume": volume,
                "open": open_price,
                "high": high,
                "low": low,
                "market_cap": market_cap,
                "per": per,
                "pbr": pbr,
            }
    except Exception as e:
        print(f"[NaverFinance] 종목 {code} 시세 조회 실패: {e}")
        return {"code": code, "name": code, "price": 0, "error": str(e)}


async def get_stock_daily_prices(code: str, days: int = 252) -> List[Dict[str, Any]]:
    """일봉 데이터 (최대 1년)"""
    try:
        end_date = datetime.now().strftime("%Y%m%d")
        start_date = (datetime.now() - timedelta(days=days + 30)).strftime("%Y%m%d")

        async with httpx.AsyncClient(timeout=TIMEOUT) as client:
            url = f"https://fchart.stock.naver.com/siseJson.nhn?symbol={code}&requestType=1&startTime={start_date}&endTime={end_date}&timeframe=day"
            resp = await client.get(url, headers=HEADERS)

            # 응답 파싱 (JavaScript 배열 형태)
            text = resp.text.strip()
            # 불필요한 문자 제거
            text = text.replace("'", '"')

            # JSON 파싱 시도
            try:
                data = json.loads(text)
            except:
                # 수동 파싱
                lines = text.split('\n')
                data = []
                for line in lines[1:]:  # 첫 줄은 헤더
                    line = line.strip().strip(',').strip('[').strip(']')
                    if line:
                        parts = line.split(',')
                        if len(parts) >= 6:
                            date = parts[0].strip('"').strip()
                            try:
                                data.append({
                                    "date": date,
                                    "open": int(parts[1].strip('"')),
                                    "high": int(parts[2].strip('"')),
                                    "low": int(parts[3].strip('"')),
                                    "close": int(parts[4].strip('"')),
                                    "volume": int(parts[5].strip('"')),
                                })
                            except:
                                continue

            return data[-days:] if len(data) > days else data
    except Exception as e:
        print(f"[NaverFinance] 종목 {code} 일봉 조회 실패: {e}")
        return []


async def get_new_high_stocks() -> List[Dict[str, Any]]:
    """52주 신고가 종목 리스트"""
    try:
        async with httpx.AsyncClient(timeout=TIMEOUT) as client:
            resp = await client.get(
                "https://finance.naver.com/sise/sise_new_high.naver",
                headers=HEADERS
            )
            soup = BeautifulSoup(resp.text, "lxml")

            stocks = []
            rows = soup.select("table.type_5 tr")

            for row in rows:
                cols = row.select("td")
                if len(cols) >= 6:
                    code_el = cols[1].select_one("a")
                    if code_el and 'href' in code_el.attrs:
                        href = code_el['href']
                        code_match = re.search(r'code=(\d+)', href)
                        code = code_match.group(1) if code_match else ""
                        name = code_el.get_text(strip=True)

                        price = cols[2].get_text(strip=True).replace(",", "")
                        change = cols[3].get_text(strip=True).replace(",", "")
                        change_pct = cols[4].get_text(strip=True).replace("%", "")
                        high52 = cols[5].get_text(strip=True).replace(",", "")

                        stocks.append({
                            "code": code,
                            "name": name,
                            "price": int(price) if price.isdigit() else 0,
                            "change": change,
                            "change_percent": float(change_pct) if change_pct.lstrip('-').replace('.','').isdigit() else 0,
                            "high52": int(high52) if high52.isdigit() else 0,
                        })

            return stocks[:30]
    except Exception as e:
        print(f"[NaverFinance] 52주 신고가 조회 실패: {e}")
        return []


async def get_etf_list() -> List[Dict[str, Any]]:
    """ETF 전체 목록 + 시세"""
    try:
        async with httpx.AsyncClient(timeout=TIMEOUT) as client:
            resp = await client.get(
                "https://finance.naver.com/sise/etf.naver",
                headers=HEADERS
            )
            soup = BeautifulSoup(resp.text, "lxml")

            etfs = []
            rows = soup.select("table.type_1 tr")

            for row in rows:
                cols = row.select("td")
                if len(cols) >= 6:
                    name_el = cols[0].select_one("a")
                    if name_el and 'href' in name_el.attrs:
                        href = name_el['href']
                        code_match = re.search(r'code=(\d+)', href)
                        code = code_match.group(1) if code_match else ""
                        name = name_el.get_text(strip=True)

                        price = cols[1].get_text(strip=True).replace(",", "")
                        nav = cols[2].get_text(strip=True).replace(",", "")  # 순자산가치
                        change = cols[3].get_text(strip=True)
                        change_pct = cols[4].get_text(strip=True).replace("%", "")
                        volume = cols[5].get_text(strip=True).replace(",", "")

                        # 섹터 분류 (이름 기반)
                        sector = categorize_etf(name)

                        etfs.append({
                            "code": code,
                            "name": name,
                            "price": int(price) if price.isdigit() else 0,
                            "nav": int(nav) if nav.isdigit() else 0,
                            "change": change,
                            "change_percent": float(change_pct) if change_pct.lstrip('-').replace('.','').isdigit() else 0,
                            "volume": int(volume) if volume.isdigit() else 0,
                            "sector": sector,
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

        # 1개월 전 (약 22거래일)
        price_1m = prices[-22]["close"] if len(prices) >= 22 else prices[0]["close"]
        rs_1m = ((current - price_1m) / price_1m) * 100

        # 3개월 전 (약 66거래일)
        price_3m = prices[-66]["close"] if len(prices) >= 66 else prices[0]["close"]
        rs_3m = ((current - price_3m) / price_3m) * 100

        # 6개월 전 (약 130거래일)
        price_6m = prices[0]["close"]
        rs_6m = ((current - price_6m) / price_6m) * 100

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

"""
시장 데이터 수집 (네이버 API)

- KOSPI/KOSDAQ 지수 및 종목수
- 외국인/기관/개인 순매수
"""

import httpx
from datetime import datetime, date
from typing import Dict, Any, Optional
from bs4 import BeautifulSoup
import re

from .signal_engine import MarketData


NAVER_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Referer": "https://m.stock.naver.com/",
}


async def collect_daily_market_data(market: str) -> Optional[MarketData]:
    """
    네이버 API에서 일별 시장 데이터 수집

    Args:
        market: 'KOSPI' | 'KOSDAQ'

    Returns: MarketData 또는 None
    """
    try:
        async with httpx.AsyncClient(timeout=30.0, headers=NAVER_HEADERS) as client:
            # 1. 지수 기본 정보
            url = f"https://m.stock.naver.com/api/index/{market}/basic"
            r = await client.get(url)
            if r.status_code != 200:
                print(f"[DataCollector] {market} basic API 실패: {r.status_code}")
                return None

            data = r.json()

            index_value = float(data.get("closePrice", "0").replace(",", ""))
            change_str = data.get("compareToPreviousClosePrice", "0").replace(",", "")
            change_amount = float(change_str) if change_str else 0

            change_pct_str = data.get("fluctuationsRatio", "0").replace(",", "")
            change_percent = float(change_pct_str) if change_pct_str else 0

            trading_volume = int(data.get("accumulatedTradingVolume", "0").replace(",", ""))
            trading_value = int(data.get("accumulatedTradingValue", "0").replace(",", ""))

            # 2. 상승/하락 종목수 (네이버 HTML 파싱)
            rising = falling = unchanged = upper = lower = listed = 0
            rising, falling, unchanged, upper, lower, listed = await get_stock_count_from_naver(market)

            # 3. 투자자 동향
            foreign_net, institution_net, individual_net = await get_investor_trend_from_naver(market)

            return MarketData(
                date=date.today(),
                market=market,
                index_value=index_value,
                change_amount=change_amount,
                change_percent=change_percent,
                trading_volume=trading_volume,
                trading_value=trading_value,
                rising_stocks=rising,
                falling_stocks=falling,
                unchanged_stocks=unchanged,
                upper_limit_stocks=upper,
                lower_limit_stocks=lower,
                listed_stocks=listed,
                foreign_net=foreign_net,
                institution_net=institution_net,
                individual_net=individual_net,
            )

    except Exception as e:
        print(f"[DataCollector] {market} 데이터 수집 오류: {e}")
        return None


async def get_investor_trend_from_naver(market: str) -> tuple:
    """
    네이버 finance에서 외국인/기관/개인 순매수 파싱

    Returns: (foreign_net, institution_net, individual_net) 억원 단위
    """
    foreign_net = 0
    institution_net = 0
    individual_net = 0

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            # 네이버 증시 메인 페이지에서 투자자별 매매 동향 파싱
            url = "https://finance.naver.com/sise/"
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
            }
            r = await client.get(url, headers=headers)
            if r.status_code != 200:
                return (0, 0, 0)

            soup = BeautifulSoup(r.text, 'html.parser')

            # 외국인/기관 매매동향 추출
            # <table class="tbl_home"> 내 외국인/기관 순매수 금액
            for td in soup.find_all('td'):
                text = td.get_text(strip=True)

                # 외국인 순매수
                if "억" in text and "외국인" in str(td.parent):
                    try:
                        val_str = text.replace("외국인", "").replace("억", "").replace(",", "").replace("+", "")
                        foreign_net = int(float(val_str))
                    except:
                        pass

                # 기관 순매수
                if "억" in text and "기관" in str(td.parent):
                    try:
                        val_str = text.replace("기관", "").replace("억", "").replace(",", "").replace("+", "")
                        institution_net = int(float(val_str))
                    except:
                        pass

            # 개인 = -(외국인 + 기관)
            individual_net = -(foreign_net + institution_net)

    except Exception as e:
        print(f"[DataCollector] 투자자 동향 파싱 오류: {e}")

    return (foreign_net, institution_net, individual_net)


async def get_stock_count_from_naver(market: str) -> tuple:
    """
    네이버 finance에서 상승/하락/보합 종목수 파싱

    Returns: (rising, falling, unchanged, upper_limit, lower_limit, listed)
    """
    rising = falling = unchanged = upper = lower = listed = 0

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            # 네이버 증시 페이지에서 상승/하락 종목수 파싱
            if market == "KOSPI":
                url = "https://finance.naver.com/sise/sise_index.naver?code=KOSPI"
            else:
                url = "https://finance.naver.com/sise/sise_index.naver?code=KOSDAQ"

            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
            }
            r = await client.get(url, headers=headers)
            if r.status_code != 200:
                print(f"[DataCollector] {market} 종목수 페이지 실패: {r.status_code}")
                return (0, 0, 0, 0, 0, 0)

            r.encoding = "euc-kr"
            soup = BeautifulSoup(r.text, 'html.parser')

            # 상승/하락/보합 종목수 파싱
            # <div class="subtop_sise_graph2"> 내의 상승, 하락, 보합 숫자
            graph_div = soup.find('div', class_='subtop_sise_graph2')
            if graph_div:
                # 상한/상승/보합/하락/하한 텍스트 추출
                text = graph_div.get_text()
                numbers = re.findall(r'(\d+)', text)
                if len(numbers) >= 5:
                    upper = int(numbers[0])  # 상한
                    rising = int(numbers[1])  # 상승
                    unchanged = int(numbers[2])  # 보합
                    falling = int(numbers[3])  # 하락
                    lower = int(numbers[4])  # 하한
                    listed = upper + rising + unchanged + falling + lower

            # 대체 파싱: tab_con1 내의 데이터
            if rising == 0 and falling == 0:
                tab_con = soup.find('div', class_='tab_con1')
                if tab_con:
                    # <span class="tah">숫자</span> 형태로 존재
                    spans = tab_con.find_all('span', class_='tah')
                    nums = []
                    for span in spans:
                        txt = span.get_text(strip=True).replace(",", "")
                        if txt.isdigit():
                            nums.append(int(txt))
                    # 순서: 상한, 상승, 보합, 하락, 하한
                    if len(nums) >= 5:
                        upper = nums[0]
                        rising = nums[1]
                        unchanged = nums[2]
                        falling = nums[3]
                        lower = nums[4]
                        listed = sum(nums[:5])

            # 마지막 대체: sise 메인 페이지에서 파싱
            if rising == 0 and falling == 0:
                main_url = "https://finance.naver.com/sise/"
                r2 = await client.get(main_url, headers=headers)
                if r2.status_code == 200:
                    r2.encoding = "euc-kr"
                    soup2 = BeautifulSoup(r2.text, 'html.parser')

                    # 지수별 상승/하락 정보 찾기
                    market_row = None
                    for tr in soup2.find_all('tr'):
                        if market in tr.get_text():
                            market_row = tr
                            break

                    if market_row:
                        tds = market_row.find_all('td')
                        for td in tds:
                            text = td.get_text(strip=True)
                            # "상승 587 하락 376 보합 12" 형태 파싱
                            up_match = re.search(r'상승\s*(\d+)', text)
                            down_match = re.search(r'하락\s*(\d+)', text)
                            even_match = re.search(r'보합\s*(\d+)', text)
                            if up_match:
                                rising = int(up_match.group(1))
                            if down_match:
                                falling = int(down_match.group(1))
                            if even_match:
                                unchanged = int(even_match.group(1))

    except Exception as e:
        print(f"[DataCollector] {market} 종목수 파싱 오류: {e}")

    print(f"[DataCollector] {market} 종목수: rising={rising}, falling={falling}, unchanged={unchanged}")
    return (rising, falling, unchanged, upper, lower, listed)


async def get_market_summary() -> Dict[str, Any]:
    """
    KOSPI/KOSDAQ 시장 요약 데이터 조회

    Returns: {
        kospi: {index_value, change_percent, rising, falling, ...},
        kosdaq: {index_value, change_percent, rising, falling, ...}
    }
    """
    result = {
        "kospi": None,
        "kosdaq": None,
        "investors": {"foreign": 0, "institution": 0, "individual": 0}
    }

    for market in ["KOSPI", "KOSDAQ"]:
        data = await collect_daily_market_data(market)
        if data:
            result[market.lower()] = {
                "index_value": data.index_value,
                "change_amount": data.change_amount,
                "change_percent": data.change_percent,
                "trading_volume": data.trading_volume,
                "trading_value": data.trading_value,
                "rising_stocks": data.rising_stocks,
                "falling_stocks": data.falling_stocks,
                "unchanged_stocks": data.unchanged_stocks,
                "upper_limit_stocks": data.upper_limit_stocks,
                "lower_limit_stocks": data.lower_limit_stocks,
                "listed_stocks": data.listed_stocks,
            }

            # 투자자 동향 (KOSPI 기준으로 1번만)
            if market == "KOSPI":
                result["investors"] = {
                    "foreign": data.foreign_net,
                    "institution": data.institution_net,
                    "individual": data.individual_net
                }

    return result


async def fetch_index_history(market: str, days: int = 365) -> list:
    """
    네이버 차트 API에서 지수 히스토리 조회

    Args:
        market: 'KOSPI' | 'KOSDAQ'
        days: 조회 일수

    Returns: [{date, open, high, low, close, volume}, ...]
    """
    result = []

    try:
        # 네이버 차트 API
        code = "KOSPI" if market == "KOSPI" else "KOSDAQ"
        url = f"https://fchart.stock.naver.com/sise.nhn?symbol={code}&timeframe=day&count={days}&requestType=0"

        async with httpx.AsyncClient(timeout=30.0) as client:
            r = await client.get(url)
            if r.status_code != 200:
                return []

            # XML 파싱
            from xml.etree import ElementTree as ET
            root = ET.fromstring(r.text)

            for item in root.findall('.//item'):
                data_str = item.get('data', '')
                parts = data_str.split('|')
                if len(parts) >= 6:
                    result.append({
                        'date': parts[0],  # YYYYMMDD
                        'open': float(parts[1]),
                        'high': float(parts[2]),
                        'low': float(parts[3]),
                        'close': float(parts[4]),
                        'volume': int(parts[5])
                    })

    except Exception as e:
        print(f"[DataCollector] 지수 히스토리 조회 오류: {e}")

    return result

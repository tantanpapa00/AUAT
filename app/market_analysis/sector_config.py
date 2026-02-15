"""
섹터 ETF 설정 (스탁이지 동일)
- 섹터별 대표 ETF 목록
- ETF 구성종목 조회 함수
"""
import httpx
import asyncio
from typing import List, Dict, Optional
from bs4 import BeautifulSoup
import re

# 섹터 ETF 목록 (스탁이지 CSV 기반)
SECTOR_ETFS = [
    # 마켓
    {"symbol": "069500", "name": "KODEX 200", "sector": "코스피", "industry": "마켓"},
    {"symbol": "229200", "name": "KODEX 코스닥150", "sector": "코스닥", "industry": "마켓"},

    # 금융/보험
    {"symbol": "102970", "name": "KODEX 증권", "sector": "증권", "industry": "금융/보험"},
    {"symbol": "140700", "name": "KODEX 보험", "sector": "보험", "industry": "금융/보험"},
    {"symbol": "139270", "name": "TIGER 200 금융", "sector": "금융", "industry": "금융/보험"},
    {"symbol": "091170", "name": "KODEX 은행", "sector": "은행", "industry": "금융/보험"},

    # 방산/우주항공
    {"symbol": "449450", "name": "PLUS K방산", "sector": "방산", "industry": "방산/우주항공"},
    {"symbol": "421320", "name": "PLUS 우주항공&UAM", "sector": "우주항공&UAM", "industry": "방산/우주항공"},

    # 조선
    {"symbol": "466920", "name": "SOL 조선TOP3플러스", "sector": "조선", "industry": "조선"},
    {"symbol": "140710", "name": "KODEX 운송", "sector": "운송", "industry": "조선"},

    # 전력기기
    {"symbol": "433500", "name": "ACE 원자력테마딥서치", "sector": "에너지", "industry": "전력기기"},
    {"symbol": "487240", "name": "KODEX AI전력핵심설비", "sector": "전력기기", "industry": "전력기기"},
    {"symbol": "457990", "name": "PLUS 태양광&ESS", "sector": "전력/태양광/ESS", "industry": "전력기기"},

    # 소비재/음식료
    {"symbol": "438900", "name": "HANARO Fn K-푸드", "sector": "식품", "industry": "소비재/음식료"},
    {"symbol": "228790", "name": "TIGER 화장품", "sector": "화장품", "industry": "소비재/음식료"},

    # 기타 테마
    {"symbol": "447430", "name": "ACE 주주환원가치주액티브", "sector": "상법개정안", "industry": "기타"},
    {"symbol": "147970", "name": "TIGER 모멘텀", "sector": "모멘텀", "industry": "기타"},
    {"symbol": "228800", "name": "TIGER 여행레저", "sector": "여행레저", "industry": "기타"},
    {"symbol": "444200", "name": "SOL KEDI메가테크액티브", "sector": "메가테크", "industry": "기타"},
    {"symbol": "307520", "name": "TIGER 지주회사", "sector": "지주회사", "industry": "기타"},
    {"symbol": "475050", "name": "ACE KPOP포커스", "sector": "엔터", "industry": "기타"},
    {"symbol": "364990", "name": "TIGER 게임TOP10", "sector": "게임", "industry": "기타"},
    {"symbol": "445290", "name": "KODEX K-로봇액티브", "sector": "로봇", "industry": "기타"},

    # 건설
    {"symbol": "139220", "name": "TIGER 200 건설", "sector": "건설", "industry": "건설"},

    # 헬스케어
    {"symbol": "227540", "name": "TIGER 200 헬스케어", "sector": "헬스케어", "industry": "헬스케어"},
    {"symbol": "261070", "name": "TIGER 코스닥150바이오테크", "sector": "바이오", "industry": "헬스케어"},
    {"symbol": "463050", "name": "TIMEFOLIO K바이오액티브", "sector": "바이오(액티브)", "industry": "헬스케어"},
    {"symbol": "483020", "name": "KIWOOM 의료AI", "sector": "의료AI", "industry": "헬스케어"},
    {"symbol": "464610", "name": "SOL 의료기기소부장Fn", "sector": "의료기기", "industry": "헬스케어"},

    # 통신
    {"symbol": "365000", "name": "TIGER 인터넷TOP10", "sector": "인터넷", "industry": "통신"},
    {"symbol": "157490", "name": "TIGER 소프트웨어", "sector": "소프트웨어", "industry": "통신"},
    {"symbol": "098560", "name": "TIGER 방송통신", "sector": "통신사/데이터", "industry": "통신"},

    # 철강/화학/금속
    {"symbol": "139250", "name": "TIGER 200 에너지화학", "sector": "석유화학", "industry": "철강/화학/금속"},
    {"symbol": "139240", "name": "TIGER 200 철강소재", "sector": "철강/금속", "industry": "철강/화학/금속"},

    # 반도체
    {"symbol": "091160", "name": "KODEX 반도체", "sector": "반도체", "industry": "반도체"},
    {"symbol": "475310", "name": "SOL 반도체후공정", "sector": "반도체후공정", "industry": "반도체"},
    {"symbol": "475300", "name": "SOL 반도체전공정", "sector": "반도체전공정", "industry": "반도체"},

    # 자동차
    {"symbol": "091180", "name": "KODEX 자동차", "sector": "자동차", "industry": "자동차"},
    {"symbol": "464600", "name": "SOL 자동차소부장Fn", "sector": "자동차소부장", "industry": "자동차"},

    # 2차전지
    {"symbol": "364980", "name": "TIGER 2차전지TOP10", "sector": "2차전지", "industry": "2차전지"},
    {"symbol": "455860", "name": "SOL 2차전지소부장Fn", "sector": "2차전지소부장", "industry": "2차전지"},
]


async def get_etf_components(etf_symbol: str, top_n: int = 6) -> List[Dict]:
    """
    ETF 구성종목 상위 N개 조회 (네이버 Finance)

    Args:
        etf_symbol: ETF 종목코드 (예: "069500")
        top_n: 상위 N개 (기본 6)

    Returns: [{"symbol": "005930", "name": "삼성전자", "weight": 30.5}, ...]
    """
    url = f"https://finance.naver.com/item/coinfo.naver?code={etf_symbol}&target=finsum_more"
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.get(url, headers=headers)
            if resp.status_code != 200:
                return []

            resp.encoding = 'euc-kr'
            soup = BeautifulSoup(resp.text, 'html.parser')

            components = []

            # 구성종목 테이블 파싱
            # 네이버 ETF 상세: 구성종목 테이블
            tables = soup.find_all('table', class_='type_1')
            for table in tables:
                rows = table.find_all('tr')
                for row in rows:
                    cols = row.find_all('td')
                    if len(cols) >= 2:
                        # 종목명 링크에서 종목코드 추출
                        link = cols[0].find('a')
                        if link and link.get('href'):
                            href = link.get('href', '')
                            code_match = re.search(r'code=(\d{6})', href)
                            if code_match:
                                stock_code = code_match.group(1)
                                stock_name = link.get_text(strip=True)

                                # 비중 (있으면)
                                weight = 0.0
                                if len(cols) >= 3:
                                    weight_text = cols[2].get_text(strip=True).replace('%', '').replace(',', '')
                                    try:
                                        weight = float(weight_text)
                                    except:
                                        pass

                                components.append({
                                    "symbol": stock_code,
                                    "name": stock_name,
                                    "weight": weight
                                })

                                if len(components) >= top_n:
                                    break

                    if len(components) >= top_n:
                        break

                if len(components) >= top_n:
                    break

            # 네이버 모바일 API 시도 (구성종목이 안 나오면)
            if not components:
                components = await get_etf_components_mobile(etf_symbol, top_n)

            return components[:top_n]

    except Exception as e:
        print(f"[Sector] ETF 구성종목 조회 오류 ({etf_symbol}): {e}")
        return []


async def get_etf_components_mobile(etf_symbol: str, top_n: int = 6) -> List[Dict]:
    """
    네이버 모바일 API에서 ETF 구성종목 조회
    URL: https://m.stock.naver.com/api/stock/{symbol}/integration
    """
    url = f"https://m.stock.naver.com/api/stock/{etf_symbol}/integration"
    headers = {
        "User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 16_0 like Mac OS X)",
        "Referer": "https://m.stock.naver.com/"
    }

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.get(url, headers=headers)
            if resp.status_code != 200:
                return []

            data = resp.json()
            components = []

            # 보유종목 정보
            holdings = data.get('etfHoldings', [])
            for h in holdings[:top_n]:
                components.append({
                    "symbol": h.get('stockCode', ''),
                    "name": h.get('stockNameKor', ''),
                    "weight": float(h.get('holdingRatio', 0))
                })

            return components

    except Exception as e:
        print(f"[Sector] 모바일 API 오류 ({etf_symbol}): {e}")
        return []


async def fetch_etf_daily_data(etf_symbol: str, days: int = 30) -> List[Dict]:
    """
    ETF 일봉 데이터 조회 (네이버 차트 API)

    Returns: [{date, open, high, low, close, volume}, ...]
    """
    from xml.etree import ElementTree as ET

    url = f"https://fchart.stock.naver.com/sise.nhn?symbol={etf_symbol}&timeframe=day&count={days}"

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.get(url)
            if resp.status_code != 200:
                return []

            root = ET.fromstring(resp.text)
            result = []

            for item in root.findall('.//item'):
                data_str = item.get('data', '')
                parts = data_str.split('|')
                if len(parts) >= 6:
                    try:
                        result.append({
                            'date': parts[0],  # YYYYMMDD
                            'open': float(parts[1]),
                            'high': float(parts[2]),
                            'low': float(parts[3]),
                            'close': float(parts[4]),
                            'volume': int(parts[5])
                        })
                    except ValueError:
                        continue

            return result

    except Exception as e:
        print(f"[Sector] ETF 일봉 조회 오류 ({etf_symbol}): {e}")
        return []


async def fetch_etf_current_price(etf_symbol: str) -> Optional[Dict]:
    """
    ETF 현재가 조회

    Returns: {close, change_percent, volume, ...}
    """
    url = f"https://m.stock.naver.com/api/stock/{etf_symbol}/basic"
    headers = {
        "User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 16_0 like Mac OS X)",
        "Referer": "https://m.stock.naver.com/"
    }

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.get(url, headers=headers)
            if resp.status_code != 200:
                return None

            data = resp.json()

            close_price = float(data.get('closePrice', '0').replace(',', ''))
            change_str = data.get('fluctuationsRatio', '0').replace(',', '')
            change_percent = float(change_str) if change_str else 0

            return {
                'close': close_price,
                'change_percent': change_percent,
                'volume': int(data.get('accumulatedTradingVolume', '0').replace(',', '')),
            }

    except Exception as e:
        print(f"[Sector] ETF 현재가 조회 오류 ({etf_symbol}): {e}")
        return None


# 테스트용
async def test_sector_config():
    """섹터 설정 테스트"""
    print(f"총 {len(SECTOR_ETFS)}개 섹터 ETF")

    # KODEX 200 구성종목 테스트
    components = await get_etf_components("069500", 6)
    print(f"\nKODEX 200 구성종목: {components}")

    # 현재가 테스트
    price = await fetch_etf_current_price("069500")
    print(f"KODEX 200 현재가: {price}")


if __name__ == "__main__":
    asyncio.run(test_sector_config())

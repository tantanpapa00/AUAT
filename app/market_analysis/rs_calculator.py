"""
RS (Relative Strength) 점수 계산 엔진
IBD 방식: 3/6/9/12개월 수익률 가중 평균 → 백분위

RS 90 = 전체 종목 중 상위 10%
"""
import numpy as np
from typing import Dict, List, Optional, Tuple
from datetime import datetime, date
import httpx
from xml.etree import ElementTree as ET
import asyncio

# RS 계산에 필요한 기간 (영업일 기준)
RS_PERIODS = {
    '3M': 63,    # 3개월 ≈ 63 영업일
    '6M': 126,   # 6개월
    '9M': 189,   # 9개월
    '12M': 252,  # 12개월
}

# 가중치 (최근 3개월 2배 = 40%)
RS_WEIGHTS = {
    '3M': 0.4,
    '6M': 0.2,
    '9M': 0.2,
    '12M': 0.2,
}


def calculate_roc(closes: List[float], period: int) -> Optional[float]:
    """
    Rate of Change (수익률) 계산
    ROC = (현재가 - N일전가) / N일전가 * 100
    """
    if len(closes) < period + 1:
        return None
    current = closes[-1]
    past = closes[-(period + 1)]
    if past == 0:
        return 0.0
    return (current - past) / past * 100


def calculate_strength_factor(closes: List[float]) -> Optional[float]:
    """
    개별 종목의 Strength Factor 계산
    SF = 0.4 * ROC(63) + 0.2 * ROC(126) + 0.2 * ROC(189) + 0.2 * ROC(252)

    최소 253일 데이터 필요 (252 + 1)
    """
    rocs = {}
    for period_name, period_days in RS_PERIODS.items():
        roc = calculate_roc(closes, period_days)
        if roc is None:
            return None
        rocs[period_name] = roc

    strength = sum(RS_WEIGHTS[k] * rocs[k] for k in RS_PERIODS.keys())
    return strength


def calculate_rs_scores(all_stocks_closes: Dict[str, List[float]]) -> Dict[str, int]:
    """
    전체 종목의 RS 점수 계산 (백분위)

    Args:
        all_stocks_closes: {"005930": [종가리스트], "000660": [종가리스트], ...}

    Returns:
        {"005930": 94, "000660": 95, ...}
    """
    # 1. 각 종목의 Strength Factor 계산
    strength_factors: Dict[str, float] = {}
    roc_data: Dict[str, Dict[str, float]] = {}  # 개별 ROC 저장

    for symbol, closes in all_stocks_closes.items():
        if len(closes) < 253:
            continue

        sf = calculate_strength_factor(closes)
        if sf is not None:
            strength_factors[symbol] = sf
            # 개별 ROC도 저장
            roc_data[symbol] = {
                'roc_3m': calculate_roc(closes, 63) or 0,
                'roc_6m': calculate_roc(closes, 126) or 0,
                'roc_9m': calculate_roc(closes, 189) or 0,
                'roc_12m': calculate_roc(closes, 252) or 0,
                'strength_factor': sf,
            }

    if not strength_factors:
        return {}

    # 2. 전체 정렬 후 백분위 계산
    sorted_symbols = sorted(strength_factors.keys(), key=lambda s: strength_factors[s])
    total = len(sorted_symbols)

    rs_scores = {}
    for rank, symbol in enumerate(sorted_symbols):
        percentile = int((rank / total) * 100)
        rs_scores[symbol] = percentile

    return rs_scores


def calculate_rs_with_details(all_stocks_closes: Dict[str, List[float]]) -> Dict[str, Dict]:
    """
    RS 점수와 상세 데이터 함께 반환

    Returns:
        {
            "005930": {
                "rs_score": 94,
                "roc_3m": 15.2,
                "roc_6m": 22.1,
                "roc_9m": 18.5,
                "roc_12m": 25.0,
                "strength_factor": 18.7
            },
            ...
        }
    """
    # 1. 각 종목의 Strength Factor 계산
    details: Dict[str, Dict] = {}

    for symbol, closes in all_stocks_closes.items():
        if len(closes) < 253:
            continue

        sf = calculate_strength_factor(closes)
        if sf is not None:
            details[symbol] = {
                'roc_3m': round(calculate_roc(closes, 63) or 0, 2),
                'roc_6m': round(calculate_roc(closes, 126) or 0, 2),
                'roc_9m': round(calculate_roc(closes, 189) or 0, 2),
                'roc_12m': round(calculate_roc(closes, 252) or 0, 2),
                'strength_factor': round(sf, 2),
            }

    if not details:
        return {}

    # 2. 전체 정렬 후 백분위 계산
    sorted_symbols = sorted(details.keys(), key=lambda s: details[s]['strength_factor'])
    total = len(sorted_symbols)

    for rank, symbol in enumerate(sorted_symbols):
        details[symbol]['rs_score'] = int((rank / total) * 100)

    return details


async def fetch_naver_daily_closes(symbol: str, count: int = 253) -> List[float]:
    """
    네이버 차트 API에서 일봉 종가 가져오기
    URL: https://fchart.stock.naver.com/sise.nhn?symbol={symbol}&timeframe=day&count={count}

    Returns: [종가1, 종가2, ...] (오래된 것 먼저)
    """
    url = f"https://fchart.stock.naver.com/sise.nhn?symbol={symbol}&timeframe=day&count={count}"

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.get(url)
            if resp.status_code != 200:
                return []

            # XML 파싱
            root = ET.fromstring(resp.text)
            closes = []

            for item in root.findall('.//item'):
                data_str = item.get('data', '')
                parts = data_str.split('|')
                if len(parts) >= 5:
                    try:
                        close = float(parts[4])
                        closes.append(close)
                    except ValueError:
                        continue

            return closes

    except Exception as e:
        print(f"[RS] {symbol} 종가 조회 오류: {e}")
        return []


async def fetch_stock_list_from_naver(market: str = 'KOSPI') -> List[Dict]:
    """
    네이버에서 종목 리스트 가져오기

    Returns: [{"symbol": "005930", "name": "삼성전자"}, ...]
    """
    # sosok: 0 = KOSPI, 1 = KOSDAQ
    sosok = 0 if market == 'KOSPI' else 1
    stocks = []

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            # 페이지별로 종목 수집 (최대 100페이지)
            for page in range(1, 101):
                url = f"https://finance.naver.com/sise/sise_market_sum.naver?sosok={sosok}&page={page}"
                headers = {"User-Agent": "Mozilla/5.0"}

                resp = await client.get(url, headers=headers)
                if resp.status_code != 200:
                    break

                # 간단한 정규식으로 종목코드 추출
                import re
                resp.encoding = 'euc-kr'
                html = resp.text

                # 종목코드 패턴: /item/main.naver?code=005930
                pattern = r'/item/main\.naver\?code=(\d{6})'
                codes = re.findall(pattern, html)

                if not codes:
                    break

                # 중복 제거
                unique_codes = list(dict.fromkeys(codes))

                for code in unique_codes:
                    if code not in [s['symbol'] for s in stocks]:
                        stocks.append({"symbol": code, "name": "", "market": market})

                await asyncio.sleep(0.1)  # rate limit

                # 더 이상 새 종목이 없으면 종료
                if len(unique_codes) < 20:
                    break

    except Exception as e:
        print(f"[RS] 종목 리스트 조회 오류: {e}")

    print(f"[RS] {market} 종목 수: {len(stocks)}")
    return stocks


async def collect_all_stocks_closes(markets: List[str] = None, days: int = 253) -> Dict[str, List[float]]:
    """
    전체 상장종목의 일봉 종가 수집

    Args:
        markets: ['KOSPI', 'KOSDAQ'] or None for both
        days: 조회 일수 (기본 253 = 약 1년)

    Returns:
        {"005930": [종가1, 종가2, ...], "000660": [종가1, 종가2, ...], ...}

    주의:
    - KOSPI 약 950개 + KOSDAQ 약 1,700개 = 약 2,650개 종목
    - 전체 수집 시간: 약 5~10분
    """
    if markets is None:
        markets = ['KOSPI', 'KOSDAQ']

    all_closes = {}
    total_stocks = []

    # 1. 전체 종목 리스트 수집
    for market in markets:
        stocks = await fetch_stock_list_from_naver(market)
        total_stocks.extend(stocks)

    print(f"[RS] 총 {len(total_stocks)}개 종목 수집 시작...")

    # 2. 각 종목의 일봉 종가 수집
    for i, stock in enumerate(total_stocks):
        symbol = stock['symbol']
        closes = await fetch_naver_daily_closes(symbol, days)

        if closes and len(closes) >= days:
            all_closes[symbol] = closes

        # 진행률 출력 (100개마다)
        if (i + 1) % 100 == 0:
            print(f"[RS] 진행: {i + 1}/{len(total_stocks)} ({len(all_closes)} 유효)")

        await asyncio.sleep(0.05)  # rate limit (0.05초)

    print(f"[RS] 수집 완료: {len(all_closes)}개 종목")
    return all_closes


# 테스트용 함수
async def test_rs_calculation():
    """RS 계산 테스트"""
    # 삼성전자 일봉 데이터로 테스트
    closes = await fetch_naver_daily_closes("005930", 253)
    if len(closes) >= 253:
        sf = calculate_strength_factor(closes)
        print(f"삼성전자 Strength Factor: {sf:.2f}")

        rocs = {
            '3M': calculate_roc(closes, 63),
            '6M': calculate_roc(closes, 126),
            '9M': calculate_roc(closes, 189),
            '12M': calculate_roc(closes, 252),
        }
        print(f"ROC: {rocs}")
    else:
        print(f"데이터 부족: {len(closes)}일")


if __name__ == "__main__":
    asyncio.run(test_rs_calculation())

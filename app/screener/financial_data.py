"""
yfinance 기반 재무 데이터 모듈
KR/US 공통 사용

13개 재무지표:
1. per (PER)
2. pbr (PBR)
3. roe
4. roa
5. operating_margin
6. gross_margin
7. profit_margin
8. debt_ratio
9. current_ratio
10. dividend_yield
11. revenue_growth
12. earnings_growth
13. eps_growth
"""

import asyncio
from typing import Dict, Any, Optional
from concurrent.futures import ThreadPoolExecutor

# yfinance import (thread-safe 사용)
try:
    import yfinance as yf
    YFINANCE_AVAILABLE = True
except ImportError:
    YFINANCE_AVAILABLE = False


# yfinance → 내부 필드 매핑
YFINANCE_FIELD_MAP = {
    "returnOnEquity": "roe",
    "returnOnAssets": "roa",
    "operatingMargins": "operating_margin",
    "grossMargins": "gross_margin",
    "profitMargins": "profit_margin",
    "debtToEquity": "debt_ratio",
    "currentRatio": "current_ratio",
    "dividendYield": "dividend_yield",
    "revenueGrowth": "revenue_growth",
    "earningsGrowth": "earnings_growth",
    "trailingPE": "per",
    "forwardPE": "forward_per",
    "priceToBook": "pbr",
}


def _convert_to_percent(val: Any) -> Optional[float]:
    """소수점 비율을 % 단위로 변환 (0.15 → 15.0)"""
    if val is None:
        return None
    try:
        return round(float(val) * 100, 2)
    except (ValueError, TypeError):
        return None


def _convert_direct(val: Any) -> Optional[float]:
    """그대로 반환 (이미 적절한 단위)"""
    if val is None:
        return None
    try:
        return round(float(val), 2)
    except (ValueError, TypeError):
        return None


# 필드별 변환 함수
FIELD_CONVERTERS = {
    "roe": _convert_to_percent,
    "roa": _convert_to_percent,
    "operating_margin": _convert_to_percent,
    "gross_margin": _convert_to_percent,
    "profit_margin": _convert_to_percent,
    "debt_ratio": _convert_direct,  # 이미 % 단위
    "current_ratio": _convert_direct,
    "dividend_yield": _convert_to_percent,
    "revenue_growth": _convert_to_percent,
    "earnings_growth": _convert_to_percent,
    "per": _convert_direct,
    "forward_per": _convert_direct,
    "pbr": _convert_direct,
}


def fetch_financial_data_sync(symbol: str, market: str = "US") -> Dict[str, Any]:
    """
    yfinance로 재무 데이터 조회 (동기)

    Args:
        symbol: 종목코드 (예: "AAPL", "005930")
        market: "US" 또는 "KR"

    Returns:
        재무 데이터 딕셔너리
    """
    if not YFINANCE_AVAILABLE:
        return {}

    result = {}

    try:
        # 심볼 변환 (한국 주식은 .KS 접미사)
        if market == "KR":
            # 6자리 코드로 패딩
            code = str(symbol).zfill(6)
            yf_symbol = f"{code}.KS"
        else:
            yf_symbol = symbol

        ticker = yf.Ticker(yf_symbol)
        info = ticker.info

        if not info:
            return {}

        # 필드 매핑 및 변환
        for yf_field, our_field in YFINANCE_FIELD_MAP.items():
            raw_val = info.get(yf_field)
            if raw_val is not None:
                converter = FIELD_CONVERTERS.get(our_field, _convert_direct)
                converted = converter(raw_val)
                if converted is not None:
                    result[our_field] = converted

        # PER fallback: trailingPE 없으면 forwardPE 사용
        if "per" not in result and "forward_per" in result:
            result["per"] = result["forward_per"]

    except Exception as e:
        print(f"[FinancialData] {symbol} 조회 실패: {e}")

    return result


async def fetch_financial_data(symbol: str, market: str = "US") -> Dict[str, Any]:
    """
    yfinance로 재무 데이터 조회 (비동기)

    Args:
        symbol: 종목코드
        market: "US" 또는 "KR"

    Returns:
        재무 데이터 딕셔너리
    """
    loop = asyncio.get_event_loop()
    with ThreadPoolExecutor() as executor:
        result = await loop.run_in_executor(
            executor,
            fetch_financial_data_sync,
            symbol,
            market
        )
    return result


async def fetch_financial_data_batch(
    symbols: list,
    market: str = "US",
    max_concurrent: int = 10
) -> Dict[str, Dict[str, Any]]:
    """
    여러 종목의 재무 데이터 일괄 조회

    Args:
        symbols: 종목코드 리스트
        market: "US" 또는 "KR"
        max_concurrent: 동시 요청 수

    Returns:
        {symbol: financial_data} 딕셔너리
    """
    results = {}

    # 세마포어로 동시 요청 제한
    semaphore = asyncio.Semaphore(max_concurrent)

    async def fetch_one(symbol: str):
        async with semaphore:
            data = await fetch_financial_data(symbol, market)
            if data:
                results[symbol] = data

    tasks = [fetch_one(s) for s in symbols]
    await asyncio.gather(*tasks, return_exceptions=True)

    return results


def get_available_financial_fields() -> list:
    """사용 가능한 재무 필드 목록"""
    return [
        "per",
        "pbr",
        "roe",
        "roa",
        "operating_margin",
        "gross_margin",
        "profit_margin",
        "debt_ratio",
        "current_ratio",
        "dividend_yield",
        "revenue_growth",
        "earnings_growth",
    ]

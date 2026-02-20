"""
yfinance 기반 재무 데이터 모듈
KR/US 공통 사용 + 백그라운드 캐시

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
import json
import os
import time
from typing import Dict, Any, Optional, List, Tuple
from concurrent.futures import ThreadPoolExecutor

# yfinance import (thread-safe 사용)
try:
    import yfinance as yf
    YFINANCE_AVAILABLE = True
except ImportError:
    YFINANCE_AVAILABLE = False


# =====================================================
# 캐시 설정
# =====================================================
CACHE_FILE = '/tmp/yfinance_cache.json'
CACHE_TTL = 24 * 3600  # 24시간

# 메모리 캐시: {symbol: (data, timestamp)}
_memory_cache: Dict[str, Tuple[Dict, float]] = {}


# =====================================================
# yfinance → 내부 필드 매핑
# =====================================================
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


# =====================================================
# 디스크 캐시 함수
# =====================================================
def load_disk_cache() -> Dict[str, Any]:
    """디스크 캐시 로드"""
    if os.path.exists(CACHE_FILE):
        try:
            with open(CACHE_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception:
            pass
    return {}


def save_disk_cache(cache_data: Dict[str, Any]):
    """디스크 캐시 저장"""
    try:
        with open(CACHE_FILE, 'w', encoding='utf-8') as f:
            json.dump(cache_data, f, ensure_ascii=False)
    except Exception as e:
        print(f"[yfinance cache] 저장 실패: {e}")


def _get_yf_symbol(code: str, market: str) -> str:
    """종목코드를 yfinance 심볼로 변환"""
    if market.upper() == "KR":
        return f"{str(code).zfill(6)}.KS"
    return code


# =====================================================
# 메인 조회 함수 (캐시 우선)
# =====================================================
def fetch_financial_data_sync(symbol: str, market: str = "US") -> Dict[str, Any]:
    """
    yfinance로 재무 데이터 조회 (동기, 캐시 우선)

    Args:
        symbol: 종목코드 (예: "AAPL", "005930")
        market: "US" 또는 "KR"

    Returns:
        재무 데이터 딕셔너리
    """
    if not YFINANCE_AVAILABLE:
        return {}

    yf_symbol = _get_yf_symbol(symbol, market)
    now = time.time()

    # 1순위: 메모리 캐시
    if yf_symbol in _memory_cache:
        data, ts = _memory_cache[yf_symbol]
        if now - ts < CACHE_TTL:
            return data

    # 2순위: 디스크 캐시
    disk_cache = load_disk_cache()
    if yf_symbol in disk_cache:
        cached_entry = disk_cache[yf_symbol]
        cached_time = cached_entry.get('_ts', 0)
        if now - cached_time < CACHE_TTL:
            # _ts 제외한 데이터 반환
            data = {k: v for k, v in cached_entry.items() if k != '_ts'}
            _memory_cache[yf_symbol] = (data, now)
            return data

    # 3순위: yfinance API 호출 (캐시 없을 때만)
    result = _fetch_from_yfinance(yf_symbol)

    if result:
        # 메모리 캐시 업데이트
        _memory_cache[yf_symbol] = (result, now)
        # 디스크 캐시 업데이트
        disk_cache[yf_symbol] = {**result, '_ts': now}
        save_disk_cache(disk_cache)

    return result


def _fetch_from_yfinance(yf_symbol: str) -> Dict[str, Any]:
    """yfinance API에서 직접 조회"""
    result = {}

    try:
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
        print(f"[FinancialData] {yf_symbol} 조회 실패: {e}")

    return result


async def fetch_financial_data(symbol: str, market: str = "US") -> Dict[str, Any]:
    """
    yfinance로 재무 데이터 조회 (비동기, 캐시 우선)
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
    여러 종목의 재무 데이터 일괄 조회 (캐시 우선)
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


# =====================================================
# 백그라운드 사전 캐싱
# =====================================================
async def prefetch_all(
    symbols_with_market: List[Tuple[str, str]],
    delay: float = 1.0
) -> int:
    """
    백그라운드 사전 캐싱. 천천히(delay초 간격) 호출하여 rate limit 방지.

    Args:
        symbols_with_market: [(종목코드, 마켓), ...] 예: [('005930','kr'), ('AAPL','us')]
        delay: 요청 간 대기 시간 (초)

    Returns:
        캐시된 종목 수
    """
    if not YFINANCE_AVAILABLE:
        return 0

    disk_cache = load_disk_cache()
    now = time.time()
    cached_count = 0
    new_count = 0

    for code, market in symbols_with_market:
        yf_symbol = _get_yf_symbol(code, market)

        # 이미 24시간 내 캐시 있으면 스킵
        if yf_symbol in disk_cache:
            cached_time = disk_cache[yf_symbol].get('_ts', 0)
            if now - cached_time < CACHE_TTL:
                cached_count += 1
                continue

        # yfinance 호출
        try:
            data = _fetch_from_yfinance(yf_symbol)
            if data:
                data['_ts'] = now
                disk_cache[yf_symbol] = data
                _memory_cache[yf_symbol] = ({k: v for k, v in data.items() if k != '_ts'}, now)
                new_count += 1
        except Exception as e:
            print(f"[prefetch] {yf_symbol} 실패: {e}")

        # rate limit 방지를 위한 대기
        await asyncio.sleep(delay)

    # 디스크에 저장
    save_disk_cache(disk_cache)
    print(f"[yfinance prefetch] 신규 {new_count}개 + 기존캐시 {cached_count}개 = 총 {len(disk_cache)}개")

    return len(disk_cache)


def get_cache_stats() -> Dict[str, Any]:
    """캐시 통계"""
    disk_cache = load_disk_cache()
    now = time.time()
    valid_count = sum(1 for v in disk_cache.values() if now - v.get('_ts', 0) < CACHE_TTL)
    return {
        "total": len(disk_cache),
        "valid": valid_count,
        "memory": len(_memory_cache),
        "ttl_hours": CACHE_TTL / 3600
    }


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

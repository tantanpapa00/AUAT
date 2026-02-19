"""
스크리너 캐싱 유틸리티
TTL 기반 인메모리 캐시 + 동시 요청 중복 방지
"""

import time
import asyncio
from typing import Any, Callable, Optional

# TTL 정책 (초)
CACHE_TTL = {
    "kr_all_stocks": 300,       # 전종목 기본 시세: 5분
    "kr_financial": 3600,       # 재무 데이터: 1시간
    "kr_stock_detail": 3600,    # 개별 종목 상세: 1시간
    "us_screener": 900,         # 해외: 15분
    "us_all_stocks": 3600,      # US 전종목: 1시간 (Finviz 스크래핑)
    "etf_screener": 300,        # ETF: 5분
    "etf_all_stocks": 600,      # ETF 전종목: 10분
}


class ScreenerCache:
    """TTL 기반 인메모리 캐시"""

    def __init__(self):
        self._store = {}  # key: {"data": ..., "expires": timestamp}
        self._locks = {}  # key: asyncio.Lock (동시 요청 중복 방지)

    async def get_or_fetch(self, key: str, ttl_seconds: int, fetch_fn: Callable):
        """캐시에 있으면 반환, 없으면 fetch_fn 실행 후 캐시"""
        cached = self._store.get(key)
        if cached and time.time() < cached["expires"]:
            return cached["data"]

        # 동일 키에 대한 동시 요청 방지 (Lock)
        if key not in self._locks:
            self._locks[key] = asyncio.Lock()

        async with self._locks[key]:
            # 다른 요청이 이미 캐시를 갱신했을 수 있음
            cached = self._store.get(key)
            if cached and time.time() < cached["expires"]:
                return cached["data"]

            data = await fetch_fn()
            self._store[key] = {"data": data, "expires": time.time() + ttl_seconds}
            return data

    def get(self, key: str) -> Optional[Any]:
        """캐시에서 직접 조회 (TTL 체크)"""
        cached = self._store.get(key)
        if cached and time.time() < cached["expires"]:
            return cached["data"]
        return None

    def set(self, key: str, data: Any, ttl_seconds: int):
        """캐시에 직접 저장"""
        self._store[key] = {"data": data, "expires": time.time() + ttl_seconds}

    def invalidate(self, key: str):
        """특정 키 캐시 삭제"""
        self._store.pop(key, None)

    def invalidate_all(self):
        """전체 캐시 삭제"""
        self._store.clear()

    def stats(self) -> dict:
        """캐시 상태 조회 (디버깅용)"""
        now = time.time()
        return {
            "total_keys": len(self._store),
            "active_keys": sum(1 for v in self._store.values() if now < v["expires"]),
            "expired_keys": sum(1 for v in self._store.values() if now >= v["expires"]),
        }


# 싱글턴 인스턴스
screener_cache = ScreenerCache()

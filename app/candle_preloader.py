# app/candle_preloader.py
"""
Candle Preloader - 주요 종목 캔들 자동 캐싱

서버 시작 시 + 1시간마다 주요 종목의 캔들 데이터를 DB에 저장.
백테스트 시 DB 캐시에서 즉시 로드할 수 있도록 함.
"""

import asyncio
import logging
from typing import List, Tuple

logger = logging.getLogger(__name__)

# 프리로드 대상 종목
PRELOAD_TARGETS: List[Tuple[str, str]] = [
    ("BINANCE", "BTCUSDT"),
    ("BINANCE", "ETHUSDT"),
    ("BINANCE", "SOLUSDT"),
    ("BINANCE", "XRPUSDT"),
    ("BINANCE", "BNBUSDT"),
]

# 프리로드 타임프레임
PRELOAD_TIMEFRAMES = ["1D", "4h", "1h"]

# 프리로드 기간 (일)
PRELOAD_DAYS = 1000


async def preload_single(exchange: str, symbol: str, timeframe: str, days: int):
    """단일 종목/타임프레임 프리로드"""
    from .strategy_engine.candle_fetcher import fetch_candles_for_backtest

    try:
        candles = await fetch_candles_for_backtest(
            exchange=exchange,
            symbol=symbol,
            timeframe=timeframe,
            days=days,
            timeout=120,
        )
        logger.info(f"프리로드 완료: {exchange} {symbol} {timeframe} → {len(candles)}봉")
        return len(candles)
    except Exception as e:
        logger.warning(f"프리로드 실패: {exchange} {symbol} {timeframe} → {e}")
        return 0


async def run_preload():
    """전체 프리로드 실행"""
    logger.info("=== 캔들 프리로드 시작 ===")
    total = 0

    for exchange, symbol in PRELOAD_TARGETS:
        for tf in PRELOAD_TIMEFRAMES:
            count = await preload_single(exchange, symbol, tf, PRELOAD_DAYS)
            total += count
            # Rate limit 방지
            await asyncio.sleep(0.5)

    logger.info(f"=== 캔들 프리로드 완료: 총 {total}봉 ===")
    return total


async def preload_loop():
    """1시간마다 프리로드 반복"""
    while True:
        try:
            await run_preload()
        except Exception as e:
            logger.error(f"프리로드 루프 에러: {e}")

        # 1시간 대기
        await asyncio.sleep(3600)


def start_preloader():
    """프리로더 백그라운드 시작 (main.py에서 호출)"""
    asyncio.create_task(preload_loop())
    logger.info("캔들 프리로더 백그라운드 시작됨")

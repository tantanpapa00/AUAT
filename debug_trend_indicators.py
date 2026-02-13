#!/usr/bin/env python3
"""
추세매매 지표 디버그 스크립트
파인스크립트 v8 값과 비교하기 위한 봉별 지표 출력
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import asyncio
import numpy as np
from datetime import datetime, timezone

from app.strategy_engine.indicators import (
    calc_supertrend,
    calc_hvi,
    calc_qqe_mod,
    calc_vwma,
    calc_spo,
    calc_sma,  # 크립토용 SMA
)
from app.strategy_engine.candle_fetcher import fetch_candles_for_backtest


async def main():
    # OKX BTC-USDT 일봉 데이터 (API 키 없이도 조회 가능)
    exchange = "OKX"
    symbol = "BTC-USDT"
    timeframe = "1D"
    days = 400  # 지표 계산에 충분한 일수

    print(f"=== {exchange} {symbol} {timeframe} 지표 디버그 ===\n")

    candles = await fetch_candles_for_backtest(exchange, symbol, timeframe, days)

    if not candles:
        print("캔들 데이터를 가져올 수 없습니다.")
        return

    print(f"총 {len(candles)}봉 로드\n")

    # numpy 배열 변환
    closes = np.array([c.c for c in candles])
    highs = np.array([c.h for c in candles])
    lows = np.array([c.l for c in candles])
    volumes = np.array([c.v for c in candles])

    # ===== 작가님 확정 파라미터 =====
    st_atr_len = 20  # 작가님 확정!
    st_factor = 5.0  # 작가님 확정!
    hvi_len = 200
    hvi_div = 3.6
    qqe_rsi_len = 6
    qqe_rsi_smooth = 5
    qqe_factor = 3.0

    # HTF 필터 설정 (PineScript v8)
    # 주식: 주봉 VWMA(156)
    # 크립토: 일봉 SMA(200)
    is_crypto = True  # BTC-USDT는 크립토
    htf_sma_len = 200  # 크립토용 SMA 길이

    # 지표 계산
    print("지표 계산 중...")

    # Supertrend
    st_value, st_dir = calc_supertrend(highs, lows, closes, st_atr_len, st_factor)

    # HVI
    hvi = calc_hvi(highs, lows, closes, volumes, hvi_len, hvi_div)

    # QQE
    qqe = calc_qqe_mod(closes, qqe_rsi_len, qqe_rsi_smooth, qqe_factor)

    # HTF 필터: 크립토는 일봉 SMA(200), 주식은 주봉 VWMA(156)
    if is_crypto:
        # 크립토: 일봉 SMA(200) - PineScript와 동일
        htf_filter = calc_sma(closes, htf_sma_len)
        htf_name = f"SMA({htf_sma_len})"
    else:
        # 주식: 주봉 VWMA(156) - 별도 주봉 데이터 필요
        htf_filter = calc_vwma(closes, volumes, 156)
        htf_name = "VWMA(156)"

    # SPO
    spo_result = calc_spo(closes, smooth_len=4, threshold=1.0, std_len=50, hma_len=30)
    spo_norm = spo_result[0]  # normalized_osc

    print("\n" + "="*130)
    print(f"{'날짜':^12} | {'종가':>10} | ST방향 | {'ST값':>10} | HVI초록 | {'QQE RSI':>8} | QQE+ | {htf_name:>12} | close>HTF | {'SPO':>8}")
    print("="*130)

    # 최근 50봉 출력
    start_idx = max(0, len(candles) - 50)
    for i in range(start_idx, len(candles)):
        candle = candles[i]
        date_str = datetime.fromtimestamp(candle.ts / 1000, tz=timezone.utc).strftime('%Y-%m-%d')

        st_dir_str = "UP" if st_dir[i] < 0 else "DN"  # PineScript: dir < 0 = bullish
        st_val = st_value[i] if not np.isnan(st_value[i]) else 0

        hvi_green = "YES" if hvi['g_enabled'][i] else "NO"

        qqe_rsi = qqe['primary_rsi'][i] if not np.isnan(qqe['primary_rsi'][i]) else 0
        qqe_pos = "YES" if qqe['is_positive'][i] else "NO"

        htf_val = htf_filter[i] if not np.isnan(htf_filter[i]) else 0
        above_htf = "YES" if candle.c > htf_val and htf_val > 0 else "NO"

        spo_val = spo_norm[i] if not np.isnan(spo_norm[i]) else 0

        print(f"{date_str:^12} | {candle.c:>10.0f} | {st_dir_str:^6} | {st_val:>10.2f} | {hvi_green:^7} | {qqe_rsi:>8.2f} | {qqe_pos:^4} | {htf_val:>12.2f} | {above_htf:^9} | {spo_val:>8.4f}")

    print("="*130)

    # Entry 조건 체크 (최근 50봉) - HTF 필터 포함
    print(f"\n\n=== ENTRY 조건 충족 봉 (ST상승 AND HVI초록 AND QQE양수 AND close>{htf_name}) ===")
    entry_count = 0
    for i in range(start_idx, len(candles)):
        candle = candles[i]
        date_str = datetime.fromtimestamp(candle.ts / 1000, tz=timezone.utc).strftime('%Y-%m-%d')

        st_bull = st_dir[i] < 0
        hvi_green_flag = hvi['g_enabled'][i]
        qqe_pos = qqe['is_positive'][i]

        # HTF 필터 조건
        htf_val = htf_filter[i] if not np.isnan(htf_filter[i]) else 0
        htf_ok = candle.c > htf_val if htf_val > 0 else True

        all_met = st_bull and hvi_green_flag and qqe_pos and htf_ok

        if all_met:
            entry_count += 1
            print(f"  {date_str}: 종가={candle.c:.0f}, ST방향=UP, HVI=GREEN, QQE=+, {htf_name}={htf_val:.2f}")

    print(f"\n총 {entry_count}봉에서 ENTRY 조건 충족")

    # Entry 조건 체크 (HTF 필터 없이) - 디버그용
    print(f"\n\n=== ENTRY 조건 충족 봉 (HTF 필터 OFF: ST상승 AND HVI초록 AND QQE양수) ===")
    entry_no_htf_count = 0
    for i in range(start_idx, len(candles)):
        candle = candles[i]
        date_str = datetime.fromtimestamp(candle.ts / 1000, tz=timezone.utc).strftime('%Y-%m-%d')

        st_bull = st_dir[i] < 0
        hvi_green_flag = hvi['g_enabled'][i]
        qqe_pos = qqe['is_positive'][i]

        all_met = st_bull and hvi_green_flag and qqe_pos

        if all_met:
            entry_no_htf_count += 1
            htf_val = htf_filter[i] if not np.isnan(htf_filter[i]) else 0
            print(f"  {date_str}: 종가={candle.c:.0f}, ST방향=UP, HVI=GREEN, QQE=+, {htf_name}={htf_val:.2f} (close>HTF={candle.c > htf_val})")

    print(f"\n총 {entry_no_htf_count}봉에서 ENTRY 조건 충족 (HTF 필터 OFF)")

    # 파라미터 요약
    print("\n\n=== 사용된 파라미터 (파인스크립트 v8 기본값) ===")
    print(f"Supertrend: ATR Length={st_atr_len}, Factor={st_factor}")
    print(f"HVI: Length={hvi_len}, Divisor={hvi_div}")
    print(f"QQE: RSI Length={qqe_rsi_len}, RSI Smoothing={qqe_rsi_smooth}, Factor={qqe_factor}")
    print(f"HTF 필터: {htf_name} (크립토={is_crypto})")


if __name__ == "__main__":
    asyncio.run(main())

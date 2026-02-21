#!/usr/bin/env python3
"""차단된 7건 상세 분석"""
import sys
sys.path.insert(0, "/app")

from sqlalchemy import create_engine, text
import os
import numpy as np
from datetime import datetime
from app.strategy_engine.backtest_engine import (
    precompute_spo_arrays, precompute_signal_arrays,
    precompute_htf_arrays, get_htf_indicators_at_index
)
from app.strategy_engine.regime_detector import detect_regime
from app.strategy_engine.models import Candle

def ts_to_date(ts):
    return datetime.utcfromtimestamp(ts / 1000).strftime("%Y-%m-%d")

def main():
    db_url = os.environ.get("DATABASE_URL")
    engine = create_engine(db_url)

    with engine.connect() as conn:
        result = conn.execute(text(
            "SELECT ts, o, h, l, c, v FROM candles "
            "WHERE exchange = 'KIS_KR' AND symbol = '005930' AND timeframe = '1D' "
            "ORDER BY ts ASC"
        ))
        rows = result.fetchall()

    all_candles = [Candle(ts=r[0], o=float(r[1]), h=float(r[2]), l=float(r[3]), c=float(r[4]), v=float(r[5])) for r in rows]
    candles = all_candles[-1000:]

    closes = np.array([c.c for c in candles])
    highs = np.array([c.h for c in candles])
    lows = np.array([c.l for c in candles])
    volumes = np.array([c.v for c in candles])

    spo = precompute_spo_arrays(closes, "custom", custom_smooth_len=4, custom_threshold=1.0)
    sig = precompute_signal_arrays(spo["normalized_osc"], spo["threshold"])
    htf = precompute_htf_arrays(closes, highs, lows, volumes)

    # HTML 기본값 (MRConfig와 다름!)
    html_defaults = {
        1: {"buy_mult": 1.0, "allow_osc": True, "filt_below_avg": True, "filt_prev_signal": True, "filt_prev_exec": True},
        2: {"buy_mult": 0.0, "allow_osc": False, "filt_below_avg": False, "filt_prev_signal": False, "filt_prev_exec": False},
        3: {"buy_mult": 1.0, "allow_osc": True, "filt_below_avg": False, "filt_prev_signal": True, "filt_prev_exec": True},
        4: {"buy_mult": 1.2, "allow_osc": True, "filt_below_avg": True, "filt_prev_signal": True, "filt_prev_exec": False},
    }

    print("=" * 110)
    print("차단된 7건 상세 분석 (HTML 기본값 기준)")
    print("=" * 110)
    print(f"{'날짜':<12} | {'국면':^4} | {'close':>10} | {'결과':^6} | {'차단 원인'}")
    print("-" * 110)

    # 평단가/직전체결가 시뮬레이션
    avg_price = None
    last_exec_price = None
    last_signal_price = None
    has_position = False

    passed = []
    blocked = []

    for i, c in enumerate(candles):
        if not sig["sig_up_raw"][i]:
            continue

        htf_ind = get_htf_indicators_at_index(htf, i)
        regime = detect_regime(htf_ind, True)
        dt = ts_to_date(c.ts)
        close = c.c

        cfg = html_defaults[regime]
        reasons = []

        # 1. buy_mult = 0?
        if cfg["buy_mult"] == 0:
            reasons.append(f"r{regime}_buy_mult=0")

        # 2. allow_osc_buy = False?
        if not cfg["allow_osc"]:
            reasons.append(f"r{regime}_allow_osc_buy=False")

        # 3. filt_below_avg (포지션 있을 때만)
        if has_position and cfg["filt_below_avg"] and avg_price is not None:
            if close > avg_price:
                reasons.append(f"r{regime}_filt_below_avg: close({close:,.0f}) > avg({avg_price:,.0f})")

        # 4. filt_prev_signal (포지션 있을 때만)
        if has_position and cfg["filt_prev_signal"] and last_signal_price is not None:
            if close >= last_signal_price:
                reasons.append(f"r{regime}_filt_prev_signal: close >= last_signal")

        # 5. filt_prev_exec (포지션 있을 때만)
        if has_position and cfg["filt_prev_exec"] and last_exec_price is not None:
            if close >= last_exec_price:
                reasons.append(f"r{regime}_filt_prev_exec: close >= last_exec")

        if reasons:
            result = "차단"
            blocked.append({"date": dt, "regime": regime, "reasons": reasons, "close": close})
        else:
            result = "통과"
            passed.append(dt)
            # 매수 성공 시 상태 업데이트
            if not has_position:
                avg_price = close
            else:
                # 단순화: 평균 계산
                avg_price = (avg_price + close) / 2
            last_exec_price = close
            has_position = True

        last_signal_price = close  # 신호가마다 갱신

        reason_str = ", ".join(reasons) if reasons else "-"
        print(f"{dt:<12} | R{regime:^3} | {close:>10,.0f} | {result:^6} | {reason_str}")

    print("\n" + "=" * 110)
    print("[요약]")
    print("=" * 110)
    print(f"sig_up_raw=True: 10건")
    print(f"통과 (BUY): {len(passed)}건 → {passed}")
    print(f"차단: {len(blocked)}건")

    print("\n" + "-" * 110)
    print("[차단 상세]")
    print("-" * 110)
    for b in blocked:
        print(f"  {b['date']} (R{b['regime']}): {', '.join(b['reasons'])}")

if __name__ == "__main__":
    main()

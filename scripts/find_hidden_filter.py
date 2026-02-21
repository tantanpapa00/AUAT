#!/usr/bin/env python3
"""숨은 필터 찾기: 필터 OFF + 배수 1.0인데 4건만 나오는 이유"""
import sys
sys.path.insert(0, "/app")

from sqlalchemy import create_engine, text
import os
import numpy as np
from datetime import datetime
from app.strategy_engine.backtest_engine import run_mr_backtest, precompute_spo_arrays, precompute_signal_arrays, precompute_htf_arrays, get_htf_indicators_at_index
from app.strategy_engine.regime_detector import detect_regime
from app.strategy_engine.models import MRConfig, Candle

def ts_to_date(ts):
    return datetime.utcfromtimestamp(ts / 1000).strftime("%Y-%m-%d")

def test_config(candles, name, **kwargs):
    config = MRConfig(osc_preset="custom", osc_smooth_len=4, osc_threshold=1.0, **kwargs)
    result = run_mr_backtest(candles=candles, config=config, initial_capital=10000000.0, fee_rate=0.0, debug=False)
    trades = result.trades if result.success else []
    buy_trades = [t for t in trades if t.action.upper() == "BUY"]
    print(f"{name}: BUY {len(buy_trades)}건 → {[ts_to_date(t.timestamp) for t in buy_trades]}")
    return len(buy_trades)

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

    print("=" * 100)
    print("숨은 필터 찾기: 필터 OFF + 배수 1.0인데 왜 10건이 안 나오나?")
    print("=" * 100)

    # 기본 설정 (필터 OFF, 배수 1.0)
    base = {
        "r1_buy_mult": 1.0, "r1_allow_osc_buy": True,
        "r1_filt_below_avg": False, "r1_filt_prev_signal": False, "r1_filt_prev_exec": False,
        "r2_buy_mult": 1.0, "r2_allow_osc_buy": True,
        "r2_filt_below_avg": False, "r2_filt_prev_signal": False, "r2_filt_prev_exec": False,
        "r3_buy_mult": 1.0, "r3_allow_osc_buy": True,
        "r3_filt_below_avg": False, "r3_filt_prev_signal": False, "r3_filt_prev_exec": False,
        "r4_buy_mult": 1.0, "r4_allow_osc_buy": True,
        "r4_filt_below_avg": False, "r4_filt_prev_signal": False, "r4_filt_prev_exec": False,
    }

    print("\n[1] 기본 설정 (필터 OFF, 배수 1.0)")
    test_config(candles, "기본", **base)

    print("\n[2] 숨은 조건 하나씩 해제")

    # r3_buy1_only 해제
    test1 = base.copy()
    test1["r3_buy1_only"] = False
    test_config(candles, "r3_buy1_only=False", **test1)

    # r1_buy1_only 해제
    test2 = base.copy()
    test2["r1_buy1_only"] = False
    test_config(candles, "r1_buy1_only=False", **test2)

    # max_buy_tranches 확대
    test3 = base.copy()
    test3["max_buy_tranches"] = 100
    test_config(candles, "max_buy_tranches=100", **test3)

    # 전부 해제
    test4 = base.copy()
    test4["r1_buy1_only"] = False
    test4["r2_buy1_only"] = False
    test4["r3_buy1_only"] = False
    test4["r4_buy1_only"] = False
    test4["max_buy_tranches"] = 100
    test_config(candles, "모든 buy1_only=False + max=100", **test4)

    # MRConfig 기본값 확인
    print("\n[3] MRConfig 기본값 확인")
    default_cfg = MRConfig()
    print(f"  r1_buy1_only: {default_cfg.r1_buy1_only}")
    print(f"  r2_buy1_only: {default_cfg.r2_buy1_only}")
    print(f"  r3_buy1_only: {default_cfg.r3_buy1_only}")
    print(f"  r4_buy1_only: {default_cfg.r4_buy1_only}")
    print(f"  max_buy_tranches: {default_cfg.max_buy_tranches}")
    print(f"  one_trade_per_bar: {default_cfg.one_trade_per_bar}")

    # 디버그 모드로 상세 분석
    print("\n[4] 상세 분석 (debug=True)")
    config = MRConfig(osc_preset="custom", osc_smooth_len=4, osc_threshold=1.0, **base)
    result = run_mr_backtest(candles=candles, config=config, initial_capital=10000000.0, fee_rate=0.0, debug=True)

    # sig_up_raw 분석
    print("\n[5] sig_up_raw 봉별 분석")
    closes = np.array([c.c for c in candles])
    highs = np.array([c.h for c in candles])
    lows = np.array([c.l for c in candles])
    volumes = np.array([c.v for c in candles])

    spo = precompute_spo_arrays(closes, "custom", custom_smooth_len=4, custom_threshold=1.0)
    sig = precompute_signal_arrays(spo["normalized_osc"], spo["threshold"])
    htf = precompute_htf_arrays(closes, highs, lows, volumes)

    trades = result.trades if result.success else []
    buy_dates = set(ts_to_date(t.timestamp) for t in trades if t.action.upper() == "BUY")

    print(f"\n{'날짜':<12} | {'국면':^4} | {'close':>10} | {'BUY?':^5} | {'비고'}")
    print("-" * 70)

    for i, c in enumerate(candles):
        if not sig["sig_up_raw"][i]:
            continue

        htf_ind = get_htf_indicators_at_index(htf, i)
        regime = detect_regime(htf_ind, True)
        dt = ts_to_date(c.ts)

        bought = "O" if dt in buy_dates else "X"
        note = ""
        if dt not in buy_dates:
            # 왜 안 샀는지 추론
            if regime == 3 and config.r3_buy1_only:
                note = "r3_buy1_only=True?"
            else:
                note = "???"

        print(f"{dt:<12} | R{regime:^3} | {c.c:>10,.0f} | {bought:^5} | {note}")

if __name__ == "__main__":
    main()

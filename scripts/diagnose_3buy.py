#!/usr/bin/env python3
"""진단: R2 OSC 매수허용=True인데 BUY 3건만 나오는 원인"""
import sys
sys.path.insert(0, "/app")

from sqlalchemy import create_engine, text
import os
import numpy as np
from datetime import datetime
from app.strategy_engine.backtest_engine import (
    run_mr_backtest, precompute_spo_arrays, precompute_signal_arrays,
    precompute_htf_arrays, get_htf_indicators_at_index
)
from app.strategy_engine.regime_detector import detect_regime
from app.strategy_engine.models import MRConfig, Candle

def ts_to_date(ts):
    if isinstance(ts, int):
        return datetime.utcfromtimestamp(ts / 1000).strftime("%Y-%m-%d")
    return str(ts)

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
    candles = all_candles[-1000:] if len(all_candles) >= 1000 else all_candles

    print("=" * 100)
    print("진단: R2 OSC 매수허용=True인데 BUY 3건만 나오는 원인")
    print("=" * 100)

    # 여러 시나리오 테스트
    scenarios = [
        {
            "name": "시나리오 1: 필터 OFF + R2 buy_mult=0 (기본값)",
            "r2_buy_mult": 0.0,
            "r2_allow_osc_buy": True,
        },
        {
            "name": "시나리오 2: 필터 OFF + R2 buy_mult=1.0, allow_osc=True",
            "r2_buy_mult": 1.0,
            "r2_allow_osc_buy": True,
        },
        {
            "name": "시나리오 3: 필터 ON (기본값) + R2 buy_mult=1.0, allow_osc=True",
            "r2_buy_mult": 1.0,
            "r2_allow_osc_buy": True,
            "filters_on": True,
        },
        {
            "name": "시나리오 4: 모든 제한 해제 (이상적)",
            "r2_buy_mult": 1.0,
            "r2_allow_osc_buy": True,
            "all_off": True,
        },
    ]

    for scenario in scenarios:
        print(f"\n{'='*100}")
        print(f"[{scenario['name']}]")
        print("=" * 100)

        filters_on = scenario.get("filters_on", False)
        all_off = scenario.get("all_off", False)

        config = MRConfig(
            osc_preset="custom",
            osc_smooth_len=4,
            osc_threshold=1.0,
            # R1
            r1_buy_mult=1.0,
            r1_allow_osc_buy=True,
            r1_filt_below_avg=True if filters_on else False,
            r1_filt_prev_signal=True if filters_on else False,
            r1_filt_prev_exec=True if filters_on else False,
            # R2
            r2_buy_mult=scenario["r2_buy_mult"],
            r2_allow_osc_buy=scenario["r2_allow_osc_buy"],
            r2_filt_below_avg=False,
            r2_filt_prev_signal=False,
            r2_filt_prev_exec=False,
            # R3
            r3_buy_mult=1.0,
            r3_allow_osc_buy=True,
            r3_buy1_only=False if all_off else True,  # 기본값은 True
            r3_filt_below_avg=False,
            r3_filt_prev_signal=True if filters_on else False,
            r3_filt_prev_exec=True if filters_on else False,
            # R4
            r4_buy_mult=1.2,
            r4_allow_osc_buy=True,
            r4_filt_below_avg=True if filters_on else False,
            r4_filt_prev_signal=True if filters_on else False,
            r4_filt_prev_exec=False,
        )

        result = run_mr_backtest(
            candles=candles,
            config=config,
            initial_capital=10000000.0,
            fee_rate=0.0
        )

        trades = result.trades if result.success else []
        buy_trades = [t for t in trades if t.action.upper() == "BUY"]

        print(f"BUY: {len(buy_trades)}건")
        for t in buy_trades:
            print(f"  {ts_to_date(t.timestamp)} | {t.price:>9,.0f}")

    # 상세 분석: 시나리오 1 (R2 buy_mult=0인 경우)
    print("\n" + "=" * 100)
    print("[상세 분석] R2 allow_osc=True이지만 buy_mult=0일 때")
    print("=" * 100)

    closes = np.array([c.c for c in candles])
    highs = np.array([c.h for c in candles])
    lows = np.array([c.l for c in candles])
    volumes = np.array([c.v for c in candles])

    spo = precompute_spo_arrays(closes, "custom", custom_smooth_len=4, custom_threshold=1.0)
    sig = precompute_signal_arrays(spo["normalized_osc"], spo["threshold"])
    htf = precompute_htf_arrays(closes, highs, lows, volumes)

    print(f"\n{'날짜':<12} | {'국면':^4} | {'buy_mult':^8} | {'allow_osc':^9} | {'차단 원인'}")
    print("-" * 80)

    for i, c in enumerate(candles):
        if not sig["sig_up_raw"][i]:
            continue

        htf_ind = get_htf_indicators_at_index(htf, i)
        regime = detect_regime(htf_ind, True)
        dt = ts_to_date(c.ts)

        # R2 allow=True, mult=0 기준
        if regime == 2:
            buy_mult = 0.0  # 기본값
            allow_osc = True  # 사용자가 켰다고 가정
            reason = "buy_mult=0 → 트랜치%=0 → 매수금액=0"
        else:
            buy_mult = 1.0 if regime != 4 else 1.2
            allow_osc = True
            reason = "통과"

        print(f"{dt:<12} | R{regime:^3} | {buy_mult:^8.1f} | {str(allow_osc):^9} | {reason}")

    print("\n" + "=" * 100)
    print("[결론]")
    print("=" * 100)
    print("""
★ R2 'OSC 매수 허용' 체크만으로는 부족함!
  - allow_osc_buy=True → 신호는 통과
  - BUT buy_mult=0.0 → 트랜치 비율 = 5% × 0.0 = 0% → 매수금액 = 0원

★ R2에서 실제 매수하려면:
  1. 'OSC 매수 허용' 체크 (allow_osc_buy=True)
  2. '매수비중 배수'를 1.0 이상으로 설정 (buy_mult >= 1.0)

★ 현재 상태 (추정):
  - R2 allow_osc_buy = True (체크함)
  - R2 buy_mult = 0.0 (기본값 그대로)
  → 5건 R2 신호가 통과는 하지만 금액 0원이라 실제 매수 안 됨
""")

if __name__ == "__main__":
    main()

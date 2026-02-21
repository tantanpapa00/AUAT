#!/usr/bin/env python3
"""삼성전자 1000일: 국면별 sig_up_raw 분석"""
import sys
sys.path.insert(0, "/app")

from sqlalchemy import create_engine, text
import os
import numpy as np
from datetime import datetime
from app.strategy_engine.backtest_engine import (
    run_mr_backtest, precompute_spo_arrays, precompute_signal_arrays,
    precompute_htf_arrays, detect_regime, get_htf_indicators_at_index
)
from app.strategy_engine.models import MRConfig, Candle

def ts_to_date(ts):
    if isinstance(ts, int):
        return datetime.utcfromtimestamp(ts / 1000).strftime("%Y-%m-%d")
    return str(ts)

def main():
    print("=" * 90)
    print("삼성전자 1000일: 국면별 sig_up_raw 상세 분석")
    print("=" * 90)

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
    
    print(f"\n캔들: {len(candles)}개 ({ts_to_date(candles[0].ts)} ~ {ts_to_date(candles[-1].ts)})")

    # 필터 전부 OFF 설정
    config = MRConfig(
        osc_preset="custom",
        osc_smooth_len=4,
        osc_threshold=1.0,
        r1_filt_below_avg=False,
        r1_filt_prev_signal=False,
        r1_filt_prev_exec=False,
        r2_filt_below_avg=False,
        r2_filt_prev_signal=False,
        r2_filt_prev_exec=False,
        r3_filt_below_avg=False,
        r3_filt_prev_signal=False,
        r3_filt_prev_exec=False,
        r4_filt_below_avg=False,
        r4_filt_prev_signal=False,
        r4_filt_prev_exec=False,
    )
    
    # 국면별 설정 출력
    print("\n" + "=" * 90)
    print("[국면별 설정] (필터 OFF 상태)")
    print("=" * 90)
    for r in [1, 2, 3, 4]:
        buy_mult = getattr(config, f"r{r}_buy_mult")
        allow_osc = getattr(config, f"r{r}_allow_osc_buy")
        print(f"  R{r}: buy_mult={buy_mult}, allow_osc_buy={allow_osc}")
    
    # 지표 계산
    closes = np.array([c.c for c in candles])
    highs = np.array([c.h for c in candles])
    lows = np.array([c.l for c in candles])
    volumes = np.array([c.v for c in candles])
    
    spo = precompute_spo_arrays(closes, "custom", custom_smooth_len=4, custom_threshold=1.0)
    sig = precompute_signal_arrays(spo["normalized_osc"], spo["threshold"])
    htf = precompute_htf_arrays(closes, highs, lows, volumes)
    
    # 국면별 봉 수 카운트
    regime_counts = {1: 0, 2: 0, 3: 0, 4: 0}
    sig_up_by_regime = {1: [], 2: [], 3: [], 4: []}
    
    for i, c in enumerate(candles):
        htf_ind = get_htf_indicators_at_index(htf, i)
        regime = detect_regime(htf_ind, config.use_4regime)
        regime_counts[regime] += 1
        
        if i < len(sig["sig_up_raw"]) and sig["sig_up_raw"][i]:
            sig_up_by_regime[regime].append((i, c, regime))
    
    print("\n" + "=" * 90)
    print("[국면별 봉 수]")
    print("=" * 90)
    for r in [1, 2, 3, 4]:
        pct = regime_counts[r] / len(candles) * 100
        print(f"  R{r}: {regime_counts[r]}봉 ({pct:.1f}%)")
    
    # sig_up_raw=True 분석
    print("\n" + "=" * 90)
    print("[sig_up_raw=True인 봉 분석]")
    print("=" * 90)
    
    total_sig_up = sum(len(v) for v in sig_up_by_regime.values())
    print(f"\n총 sig_up_raw=True: {total_sig_up}개")
    
    for r in [1, 2, 3, 4]:
        buy_mult = getattr(config, f"r{r}_buy_mult")
        allow_osc = getattr(config, f"r{r}_allow_osc_buy")
        count = len(sig_up_by_regime[r])
        
        can_buy = buy_mult > 0 and allow_osc
        status = "BUY 가능" if can_buy else f"BUY 불가 (buy_mult={buy_mult}, allow_osc={allow_osc})"
        
        print(f"\n  R{r}: {count}개 → {status}")
        for idx, c, regime in sig_up_by_regime[r]:
            dt = ts_to_date(c.ts)
            print(f"      {dt} | close={c.c:>9,.0f} | R{regime}")
    
    # 백테스트 실행해서 실제 BUY 목록
    print("\n" + "=" * 90)
    print("[실제 백테스트 결과]")
    print("=" * 90)
    
    result = run_mr_backtest(
        candles=candles,
        config=config,
        initial_capital=10000000.0,
        fee_rate=0.001
    )
    
    trades = result.trades if result.success else []
    buy_trades = [t for t in trades if t.action.upper() == "BUY"]
    sell_trades = [t for t in trades if t.action.upper() == "SELL"]
    
    print(f"\n총 거래: {len(trades)}건 (BUY {len(buy_trades)}, SELL {len(sell_trades)})")
    
    print("\n[BUY 목록]")
    buy_dates = set()
    for t in buy_trades:
        dt = ts_to_date(t.timestamp)
        buy_dates.add(dt)
        print(f"  {dt} | price={t.price:>9,.0f}")
    
    # sig_up_raw=True인데 BUY 안 된 이유 분석
    print("\n" + "=" * 90)
    print("[sig_up_raw=True인데 BUY 안 된 봉 - 이유 분석]")
    print("=" * 90)
    
    missed_count = 0
    for r in [1, 2, 3, 4]:
        buy_mult = getattr(config, f"r{r}_buy_mult")
        allow_osc = getattr(config, f"r{r}_allow_osc_buy")
        
        for idx, c, regime in sig_up_by_regime[r]:
            dt = ts_to_date(c.ts)
            if dt not in buy_dates:
                missed_count += 1
                
                # 이유 분석
                reasons = []
                if buy_mult == 0:
                    reasons.append(f"buy_mult=0")
                if not allow_osc:
                    reasons.append(f"allow_osc_buy=False")
                if not reasons:
                    reasons.append("다른 이유 (buy_stage>=max? 같은봉 중복?)")
                
                reason_str = ", ".join(reasons)
                print(f"  {dt} | R{r} | close={c.c:>9,.0f} | 이유: {reason_str}")
    
    print(f"\n총 미실행: {missed_count}개 / {total_sig_up}개")
    
    # 결론
    print("\n" + "=" * 90)
    print("[결론]")
    print("=" * 90)
    
    r2_sig_count = len(sig_up_by_regime[2])
    if r2_sig_count > 0:
        print(f"\n★ R2 국면에서 sig_up_raw=True가 {r2_sig_count}개 발생했으나,")
        print(f"  R2 기본값: buy_mult=0.0, allow_osc_buy=False → 전부 BUY 불가")
        print(f"\n★ Pine Script에서 R2 buy_mult가 0이면 Python과 동일 (정상).")
        print(f"  Pine에서 R2에서도 매수한다면 Pine과 Python 설정이 다른 것.")

if __name__ == "__main__":
    main()

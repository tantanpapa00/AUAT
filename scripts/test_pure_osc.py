#!/usr/bin/env python3
"""순수 오실레이터 신호 비교: 필터 전부 OFF, 모든 국면 매수/매도 허용"""
import sys
sys.path.insert(0, "/app")

from sqlalchemy import create_engine, text
import os
import numpy as np
from datetime import datetime
from app.strategy_engine.backtest_engine import (
    run_mr_backtest, precompute_spo_arrays, precompute_signal_arrays
)
from app.strategy_engine.models import MRConfig, Candle

def ts_to_date(ts):
    if isinstance(ts, int):
        return datetime.utcfromtimestamp(ts / 1000).strftime("%Y-%m-%d")
    return str(ts)

def main():
    print("=" * 80)
    print("순수 오실레이터 신호 비교")
    print("삼성전자 005930, 일봉 1000봉, 스무딩=4, threshold=1")
    print("=" * 80)

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

    # 순수 오실레이터 신호 계산
    closes = np.array([c.c for c in candles])

    spo = precompute_spo_arrays(closes, "custom", custom_smooth_len=4, custom_threshold=1.0)
    sig = precompute_signal_arrays(spo["normalized_osc"], spo["threshold"])

    sig_up_count = np.sum(sig["sig_up_raw"])
    sig_dn_count = np.sum(sig["sig_dn_raw"])

    print(f"\n" + "=" * 80)
    print("[순수 오실레이터 신호]")
    print("=" * 80)
    print(f"sig_up_raw=True 총: {sig_up_count}건")
    print(f"sig_dn_raw=True 총: {sig_dn_count}건")

    # sig_up_raw=True인 날짜 목록
    print(f"\n[sig_up_raw=True 날짜 목록]")
    for i, c in enumerate(candles):
        if sig["sig_up_raw"][i]:
            print(f"  {ts_to_date(c.ts)} | close={c.c:>9,.0f} | osc={spo['normalized_osc'][i]:.3f}")

    # 필터 전부 OFF, 모든 국면 매수/매도 허용 설정
    config = MRConfig(
        osc_preset="custom",
        osc_smooth_len=4,
        osc_threshold=1.0,
        # R1: 모든 필터 OFF, 매수/매도 허용
        r1_buy_mult=1.0,
        r1_sell_mult=1.0,
        r1_allow_osc_buy=True,
        r1_filt_below_avg=False,
        r1_filt_prev_signal=False,
        r1_filt_prev_exec=False,
        # R2: 모든 필터 OFF, 매수/매도 허용 (기본값과 다름!)
        r2_buy_mult=1.0,
        r2_sell_mult=1.0,
        r2_allow_osc_buy=True,
        r2_filt_below_avg=False,
        r2_filt_prev_signal=False,
        r2_filt_prev_exec=False,
        # R3: 모든 필터 OFF, 매수/매도 허용
        r3_buy_mult=1.0,
        r3_sell_mult=1.0,
        r3_allow_osc_buy=True,
        r3_buy1_only=False,  # 1회 제한도 해제
        r3_filt_below_avg=False,
        r3_filt_prev_signal=False,
        r3_filt_prev_exec=False,
        # R4: 모든 필터 OFF, 매수/매도 허용
        r4_buy_mult=1.0,
        r4_sell_mult=1.0,
        r4_allow_osc_buy=True,
        r4_filt_below_avg=False,
        r4_filt_prev_signal=False,
        r4_filt_prev_exec=False,
    )

    result = run_mr_backtest(
        candles=candles,
        config=config,
        initial_capital=10000000.0,
        fee_rate=0.0  # 수수료 0으로 순수 비교
    )

    trades = result.trades if result.success else []
    buy_trades = [t for t in trades if t.action.upper() == "BUY"]
    sell_trades = [t for t in trades if t.action.upper() == "SELL"]

    print(f"\n" + "=" * 80)
    print("[백테스트 결과]")
    print("=" * 80)
    print(f"실제 BUY 실행: {len(buy_trades)}건")
    print(f"실제 SELL 실행: {len(sell_trades)}건")

    print(f"\nBUY 목록:")
    for t in buy_trades:
        dt = ts_to_date(t.timestamp)
        print(f"  {dt} | {t.price:>9,.0f}")

    print(f"\nSELL 목록:")
    for t in sell_trades:
        dt = ts_to_date(t.timestamp)
        pnl = getattr(t, 'pnl', None)
        pnl_str = f" | pnl={pnl:>+,.0f}" if pnl is not None else ""
        print(f"  {dt} | {t.price:>9,.0f}{pnl_str}")

    # 차이 분석
    print(f"\n" + "=" * 80)
    print("[분석]")
    print("=" * 80)

    buy_dates = set(ts_to_date(t.timestamp) for t in buy_trades)
    sig_up_dates = set(ts_to_date(candles[i].ts) for i in range(len(candles)) if sig["sig_up_raw"][i])

    missed = sig_up_dates - buy_dates
    if missed:
        print(f"\nsig_up_raw=True인데 BUY 안 된 날짜: {len(missed)}건")
        for dt in sorted(missed):
            print(f"  {dt}")
    else:
        print(f"\n모든 sig_up_raw=True 봉에서 BUY 실행됨")

if __name__ == "__main__":
    main()

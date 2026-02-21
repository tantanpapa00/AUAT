#!/usr/bin/env python3
"""API가 실제로 받는 파라미터만으로 테스트"""
import sys
sys.path.insert(0, "/app")

from sqlalchemy import create_engine, text
import os
from datetime import datetime
from app.strategy_engine.backtest_engine import run_mr_backtest
from app.strategy_engine.models import MRConfig, Candle

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

    print("=" * 100)
    print("API가 받는 파라미터만으로 테스트 (buy1_only 등은 MRConfig 기본값 사용)")
    print("=" * 100)

    # 사용자가 설정한 값 (필터 OFF, buy_mult=1.0)
    # 단, API가 받지 않는 파라미터는 제외 → MRConfig 기본값 적용됨

    print("\n[테스트] API 파라미터 (필터 OFF, buy_mult=1.0)")
    print("  - r3_buy1_only는 API가 안 받음 → MRConfig 기본값 True 적용")

    config = MRConfig(
        osc_preset="custom",
        osc_smooth_len=4,
        osc_threshold=1.0,
        use_4regime=True,
        # R1 (API가 받는 파라미터만)
        r1_buy_mult=1.0,
        r1_sell_mult=1.3,
        r1_allow_osc_buy=True,
        r1_pullback_on=True,
        r1_filt_below_avg=False,  # 필터 OFF
        r1_filt_prev_signal=False,
        r1_filt_prev_exec=False,
        # R2
        r2_buy_mult=1.0,  # 사용자가 1.0으로 설정
        r2_sell_mult=1.6,
        r2_allow_osc_buy=True,  # OSC 매수 허용
        r2_filt_below_avg=False,
        r2_filt_prev_signal=False,
        r2_filt_prev_exec=False,
        # R3
        r3_buy_mult=1.0,
        r3_sell_mult=1.3,
        r3_allow_osc_buy=True,
        r3_breakout_on=True,
        r3_filt_below_avg=False,
        r3_filt_prev_signal=False,  # 필터 OFF
        r3_filt_prev_exec=False,    # 필터 OFF
        # r3_buy1_only → API가 안 받음 → MRConfig 기본값 True
        # R4
        r4_buy_mult=1.0,  # 사용자가 1.0으로 설정
        r4_sell_mult=0.7,
        r4_allow_osc_buy=True,
        r4_filt_below_avg=False,
        r4_filt_prev_signal=False,
        r4_filt_prev_exec=False,
    )

    # MRConfig 기본값 확인
    print(f"\n  MRConfig 기본값 (API가 안 받는 파라미터):")
    print(f"    r3_buy1_only = {config.r3_buy1_only}")
    print(f"    r1_buy1_only = {config.r1_buy1_only}")
    print(f"    r4_buy1_only = {config.r4_buy1_only}")

    result = run_mr_backtest(
        candles=candles,
        config=config,
        initial_capital=10000000.0,
        fee_rate=0.0
    )

    trades = result.trades if result.success else []
    buy_trades = [t for t in trades if t.action.upper() == "BUY"]

    print(f"\n  결과: BUY {len(buy_trades)}건")
    for t in buy_trades:
        print(f"    {ts_to_date(t.timestamp)} | {t.price:>9,.0f}")

    # 365일 테스트
    print("\n" + "=" * 100)
    print("[365일 테스트]")
    candles_365 = all_candles[-365:]

    result_365 = run_mr_backtest(
        candles=candles_365,
        config=config,
        initial_capital=10000000.0,
        fee_rate=0.0
    )

    trades_365 = result_365.trades if result_365.success else []
    buy_trades_365 = [t for t in trades_365 if t.action.upper() == "BUY"]

    print(f"  결과: BUY {len(buy_trades_365)}건")
    for t in buy_trades_365:
        print(f"    {ts_to_date(t.timestamp)} | {t.price:>9,.0f}")

if __name__ == "__main__":
    main()

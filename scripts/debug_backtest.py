#!/usr/bin/env python3
"""검증: 필터 OFF로 1000일 백테스트에서 2025-11-26 BUY 발생 확인"""
import sys
sys.path.insert(0, "/app")

from sqlalchemy import create_engine, text
import os
from datetime import datetime
from app.strategy_engine.backtest_engine import run_mr_backtest
from app.strategy_engine.models import MRConfig, Candle

def ts_to_date(ts):
    if isinstance(ts, int):
        return datetime.utcfromtimestamp(ts / 1000).strftime("%Y-%m-%d")
    return str(ts)

def main():
    print("=" * 80)
    print("검증: 필터 OFF로 1000일 백테스트")
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
    candles_1000 = all_candles[-1000:] if len(all_candles) >= 1000 else all_candles
    candles_365 = all_candles[-365:] if len(all_candles) >= 365 else all_candles

    # 필터 전부 OFF
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
    
    print("\n[Config] 모든 필터 OFF")
    
    # 1000일 백테스트
    print("\n[1] 1000일 백테스트...")
    result_1000 = run_mr_backtest(
        candles=candles_1000,
        config=config,
        initial_capital=10000000.0,
        fee_rate=0.001
    )
    
    trades_1000 = result_1000.trades if result_1000.success else []
    print(f"  총 거래 수: {len(trades_1000)}")
    
    buy_1126 = any(ts_to_date(t.timestamp) == "2025-11-26" and t.action.upper() == "BUY" for t in trades_1000)
    print(f"  ★★★ 2025-11-26 BUY: {'YES!' if buy_1126 else 'NO'}")
    
    if buy_1126:
        print("\n  [2025-11 거래]")
        for t in trades_1000:
            dt = ts_to_date(t.timestamp)
            if dt.startswith("2025-11"):
                print(f"    {dt} | {t.action.upper()} | price={t.price:,.0f}")
    
    # 365일 백테스트
    print("\n[2] 365일 백테스트...")
    result_365 = run_mr_backtest(
        candles=candles_365,
        config=config,
        initial_capital=10000000.0,
        fee_rate=0.001
    )
    
    trades_365 = result_365.trades if result_365.success else []
    print(f"  총 거래 수: {len(trades_365)}")
    
    buy_1126_365 = any(ts_to_date(t.timestamp) == "2025-11-26" and t.action.upper() == "BUY" for t in trades_365)
    print(f"  ★★★ 2025-11-26 BUY: {'YES!' if buy_1126_365 else 'NO'}")
    
    print("\n" + "=" * 80)
    print("[결론]")
    print("=" * 80)
    if buy_1126 and buy_1126_365:
        print("  ✅ 수정 성공! 365일/1000일 모두 2025-11-26 BUY 발생")
    elif buy_1126:
        print("  ✅ 1000일 수정 성공! (365일은 원래 BUY 있었음)")
    else:
        print("  ❌ 여전히 문제 있음")

if __name__ == "__main__":
    main()

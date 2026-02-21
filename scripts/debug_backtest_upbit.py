#!/usr/bin/env python3
"""검증: UPBIT BTC 1000일 백테스트 (기존 BUY 유지 확인)"""
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
    print("검증: UPBIT BTC 1000일 백테스트")
    print("=" * 80)

    db_url = os.environ.get("DATABASE_URL")
    engine = create_engine(db_url)

    # UPBIT BTC 캔들 확인
    with engine.connect() as conn:
        result = conn.execute(text(
            "SELECT COUNT(*), MIN(ts), MAX(ts) FROM candles "
            "WHERE exchange = 'UPBIT' AND symbol = 'KRW-BTC' AND timeframe = '1D'"
        ))
        row = result.fetchone()
        print(f"\nUPBIT KRW-BTC 1D 캔들: {row[0]}개")
        if row[0] == 0:
            print("  캔들 없음 - 다른 심볼 확인")
            result2 = conn.execute(text(
                "SELECT DISTINCT symbol FROM candles WHERE exchange = 'UPBIT' LIMIT 10"
            ))
            symbols = [r[0] for r in result2.fetchall()]
            print(f"  UPBIT 심볼: {symbols}")
            return
        
        result = conn.execute(text(
            "SELECT ts, o, h, l, c, v FROM candles "
            "WHERE exchange = 'UPBIT' AND symbol = 'KRW-BTC' AND timeframe = '1D' "
            "ORDER BY ts ASC"
        ))
        rows = result.fetchall()

    all_candles = [Candle(ts=r[0], o=float(r[1]), h=float(r[2]), l=float(r[3]), c=float(r[4]), v=float(r[5])) for r in rows]
    candles_1000 = all_candles[-1000:] if len(all_candles) >= 1000 else all_candles
    
    print(f"  사용 캔들: {len(candles_1000)}개")

    # 기본 설정 (필터 ON)
    config = MRConfig(
        osc_preset="custom",
        osc_smooth_len=4,
        osc_threshold=1.0,
    )
    
    print("\n[1] 1000일 백테스트 (필터 기본값)...")
    result = run_mr_backtest(
        candles=candles_1000,
        config=config,
        initial_capital=10000000.0,
        fee_rate=0.001
    )
    
    trades = result.trades if result.success else []
    buy_count = sum(1 for t in trades if t.action.upper() == "BUY")
    print(f"  총 거래 수: {len(trades)}")
    print(f"  BUY 횟수: {buy_count}")
    
    print("\n  [BUY 목록]")
    for t in trades:
        if t.action.upper() == "BUY":
            dt = ts_to_date(t.timestamp)
            print(f"    {dt} | BUY | price={t.price:,.0f}")

if __name__ == "__main__":
    main()

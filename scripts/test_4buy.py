#!/usr/bin/env python3
"""사용자가 보고한 4건 상황 재현"""
import sys
sys.path.insert(0, "/app")

from sqlalchemy import create_engine, text
import os
from datetime import datetime
from app.strategy_engine.backtest_engine import run_mr_backtest
from app.strategy_engine.models import MRConfig, Candle

def ts_to_date(ts):
    return datetime.utcfromtimestamp(ts / 1000).strftime("%Y-%m-%d")

def test(candles, name, **kwargs):
    config = MRConfig(osc_preset="custom", osc_smooth_len=4, osc_threshold=1.0, **kwargs)
    result = run_mr_backtest(candles=candles, config=config, initial_capital=10000000.0, fee_rate=0.0)
    trades = result.trades if result.success else []
    buy_trades = [t for t in trades if t.action.upper() == "BUY"]
    print(f"{name}: BUY {len(buy_trades)}건")
    for t in buy_trades:
        print(f"  {ts_to_date(t.timestamp)} | {t.price:>9,.0f}")
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
    print("BUY 4건 재현 테스트")
    print("=" * 100)

    # 시나리오들 테스트
    scenarios = [
        # 1. R2만 허용, R3/R4 필터 일부 ON
        {
            "name": "R2허용 + R3 filt_prev ON + R4 filt_below ON",
            "params": {
                "r1_buy_mult": 1.0, "r1_allow_osc_buy": True,
                "r1_filt_below_avg": False, "r1_filt_prev_signal": False, "r1_filt_prev_exec": False,
                "r2_buy_mult": 1.0, "r2_allow_osc_buy": True,
                "r2_filt_below_avg": False, "r2_filt_prev_signal": False, "r2_filt_prev_exec": False,
                "r3_buy_mult": 1.0, "r3_allow_osc_buy": True,
                "r3_filt_below_avg": False, "r3_filt_prev_signal": True, "r3_filt_prev_exec": True,  # ON
                "r4_buy_mult": 1.0, "r4_allow_osc_buy": True,
                "r4_filt_below_avg": True, "r4_filt_prev_signal": True, "r4_filt_prev_exec": False,  # 일부 ON
            }
        },
        # 2. R1 필터만 ON
        {
            "name": "R1 필터 ON, 나머지 OFF, R2 buy=1",
            "params": {
                "r1_buy_mult": 1.0, "r1_allow_osc_buy": True,
                "r1_filt_below_avg": True, "r1_filt_prev_signal": True, "r1_filt_prev_exec": True,  # ON
                "r2_buy_mult": 1.0, "r2_allow_osc_buy": True,
                "r2_filt_below_avg": False, "r2_filt_prev_signal": False, "r2_filt_prev_exec": False,
                "r3_buy_mult": 1.0, "r3_allow_osc_buy": True,
                "r3_filt_below_avg": False, "r3_filt_prev_signal": False, "r3_filt_prev_exec": False,
                "r4_buy_mult": 1.0, "r4_allow_osc_buy": True,
                "r4_filt_below_avg": False, "r4_filt_prev_signal": False, "r4_filt_prev_exec": False,
            }
        },
        # 3. 전부 필터 OFF, R2 buy=1
        {
            "name": "전부 필터 OFF, R2 buy=1",
            "params": {
                "r1_buy_mult": 1.0, "r1_allow_osc_buy": True,
                "r1_filt_below_avg": False, "r1_filt_prev_signal": False, "r1_filt_prev_exec": False,
                "r2_buy_mult": 1.0, "r2_allow_osc_buy": True,
                "r2_filt_below_avg": False, "r2_filt_prev_signal": False, "r2_filt_prev_exec": False,
                "r3_buy_mult": 1.0, "r3_allow_osc_buy": True,
                "r3_filt_below_avg": False, "r3_filt_prev_signal": False, "r3_filt_prev_exec": False,
                "r4_buy_mult": 1.0, "r4_allow_osc_buy": True,
                "r4_filt_below_avg": False, "r4_filt_prev_signal": False, "r4_filt_prev_exec": False,
            }
        },
        # 4. HTML 기본값 + R2 buy=1 (사용자가 R2만 변경한 경우)
        {
            "name": "HTML 기본값 + R2 buy=1 허용",
            "params": {
                "r1_buy_mult": 1.0, "r1_allow_osc_buy": True,
                "r1_filt_below_avg": True, "r1_filt_prev_signal": True, "r1_filt_prev_exec": True,
                "r2_buy_mult": 1.0, "r2_allow_osc_buy": True,  # 변경
                "r2_filt_below_avg": False, "r2_filt_prev_signal": False, "r2_filt_prev_exec": False,
                "r3_buy_mult": 1.0, "r3_allow_osc_buy": True,
                "r3_filt_below_avg": False, "r3_filt_prev_signal": True, "r3_filt_prev_exec": True,
                "r4_buy_mult": 1.0, "r4_allow_osc_buy": True,
                "r4_filt_below_avg": True, "r4_filt_prev_signal": True, "r4_filt_prev_exec": False,
            }
        },
    ]

    for s in scenarios:
        print(f"\n[{s['name']}]")
        test(candles, s['name'], **s['params'])

if __name__ == "__main__":
    main()

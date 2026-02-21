#!/usr/bin/env python3
"""진단: 정확히 BUY 3건이 나오는 설정 조합 찾기"""
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

def test_config(candles, **kwargs):
    config = MRConfig(
        osc_preset="custom",
        osc_smooth_len=4,
        osc_threshold=1.0,
        **kwargs
    )
    result = run_mr_backtest(candles=candles, config=config, initial_capital=10000000.0, fee_rate=0.0)
    trades = result.trades if result.success else []
    buy_trades = [t for t in trades if t.action.upper() == "BUY"]
    return len(buy_trades), [ts_to_date(t.timestamp) for t in buy_trades]

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
    print("BUY 3건이 나오는 설정 조합 찾기")
    print("=" * 100)

    # 앱 UI HTML 기본값 (MRConfig 기본값과 다름!)
    # HTML에서 확인된 실제 기본값
    html_defaults = {
        # R1: 필터 전부 ON
        "r1_buy_mult": 1.0,
        "r1_allow_osc_buy": True,
        "r1_filt_below_avg": True,    # checked
        "r1_filt_prev_signal": True,  # checked
        "r1_filt_prev_exec": True,    # checked
        # R2: 기본 매수 금지
        "r2_buy_mult": 0.0,
        "r2_allow_osc_buy": False,
        "r2_filt_below_avg": False,
        "r2_filt_prev_signal": False,
        "r2_filt_prev_exec": False,
        # R3: buy1_only=True
        "r3_buy_mult": 1.0,
        "r3_allow_osc_buy": True,
        "r3_buy1_only": True,
        "r3_filt_below_avg": False,
        "r3_filt_prev_signal": True,
        "r3_filt_prev_exec": True,
        # R4: 필터 일부 ON
        "r4_buy_mult": 1.2,
        "r4_allow_osc_buy": True,
        "r4_filt_below_avg": True,
        "r4_filt_prev_signal": True,
        "r4_filt_prev_exec": False,
    }

    # 테스트 1: HTML 기본값 그대로
    print("\n[테스트 1] HTML 기본값 (앱 초기상태)")
    count, dates = test_config(candles, **html_defaults)
    print(f"BUY: {count}건 → {dates}")

    # 테스트 2: R2 OSC 매수허용=True (사용자가 체크)
    print("\n[테스트 2] R2 OSC 매수허용=True (체크함), buy_mult=0 (그대로)")
    test2 = html_defaults.copy()
    test2["r2_allow_osc_buy"] = True
    count, dates = test_config(candles, **test2)
    print(f"BUY: {count}건 → {dates}")

    # 테스트 3: R2 OSC 허용 + buy_mult=1.0
    print("\n[테스트 3] R2 OSC 허용=True + buy_mult=1.0")
    test3 = html_defaults.copy()
    test3["r2_allow_osc_buy"] = True
    test3["r2_buy_mult"] = 1.0
    count, dates = test_config(candles, **test3)
    print(f"BUY: {count}건 → {dates}")

    # 테스트 4: 필터 전부 OFF
    print("\n[테스트 4] 필터 전부 OFF (R2 buy_mult=0 그대로)")
    test4 = html_defaults.copy()
    for r in [1, 2, 3, 4]:
        test4[f"r{r}_filt_below_avg"] = False
        test4[f"r{r}_filt_prev_signal"] = False
        test4[f"r{r}_filt_prev_exec"] = False
    count, dates = test_config(candles, **test4)
    print(f"BUY: {count}건 → {dates}")

    # 테스트 5: 필터 전부 OFF + R2 OSC 허용
    print("\n[테스트 5] 필터 OFF + R2 OSC 허용 (buy_mult=0)")
    test5 = test4.copy()
    test5["r2_allow_osc_buy"] = True
    count, dates = test_config(candles, **test5)
    print(f"BUY: {count}건 → {dates}")

    # 테스트 6: 3건 나오는 조합 탐색
    print("\n" + "=" * 100)
    print("[3건이 나오는 조합 탐색]")
    print("=" * 100)

    # R1 필터 ON으로 2025-11-26 차단되면?
    test6 = html_defaults.copy()
    test6["r1_filt_below_avg"] = True  # 평단가 필터
    count, dates = test_config(candles, **test6)
    print(f"R1 필터 ON: BUY {count}건 → {dates}")

    # 365일만?
    candles_365 = all_candles[-365:] if len(all_candles) >= 365 else all_candles
    print(f"\n[365일 테스트]")
    count, dates = test_config(candles_365, **html_defaults)
    print(f"HTML 기본값: BUY {count}건 → {dates}")

    count, dates = test_config(candles_365, **test4)
    print(f"필터 OFF: BUY {count}건 → {dates}")

if __name__ == "__main__":
    main()

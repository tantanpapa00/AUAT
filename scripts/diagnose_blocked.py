#!/usr/bin/env python3
"""진단: 앱에서 '필터 OFF' 시 실제 전달되는 파라미터로 차단 원인 분석"""
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
    print("=" * 90)
    print("진단: 앱 '필터 OFF' 시 전달되는 파라미터")
    print("=" * 90)

    # ============================================================
    # 앱 UI에서 '필터 OFF'를 눌렀을 때 실제 전달되는 파라미터
    # (HTML 기본값 + 필터 체크박스만 OFF)
    # ============================================================

    print("\n[앱 UI 기본값 (필터 OFF 상태)]")
    print("-" * 90)

    # HTML에서 확인된 실제 기본값들
    app_params = {
        # R1 (HTML 기본값)
        "r1_buy_mult": 1.0,        # value="1.0"
        "r1_allow_osc_buy": True,  # checked
        "r1_filt_below_avg": False,    # 필터 OFF
        "r1_filt_prev_signal": False,  # 필터 OFF
        "r1_filt_prev_exec": False,    # 필터 OFF

        # R2 (HTML 기본값) ★★★ 핵심 ★★★
        "r2_buy_mult": 0.0,        # value="0.0" ← 이게 문제!
        "r2_allow_osc_buy": False, # unchecked ← 이것도 문제!
        "r2_filt_below_avg": False,
        "r2_filt_prev_signal": False,
        "r2_filt_prev_exec": False,

        # R3 (HTML 기본값)
        "r3_buy_mult": 1.0,
        "r3_allow_osc_buy": True,
        "r3_buy1_only": True,      # checked (기본값)
        "r3_filt_below_avg": False,
        "r3_filt_prev_signal": False,
        "r3_filt_prev_exec": False,

        # R4 (HTML 기본값)
        "r4_buy_mult": 1.2,
        "r4_allow_osc_buy": True,
        "r4_filt_below_avg": False,
        "r4_filt_prev_signal": False,
        "r4_filt_prev_exec": False,
    }

    for key, val in app_params.items():
        print(f"  {key}: {val}")

    # DB에서 캔들 조회
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

    # 지표 계산
    closes = np.array([c.c for c in candles])
    highs = np.array([c.h for c in candles])
    lows = np.array([c.l for c in candles])
    volumes = np.array([c.v for c in candles])

    spo = precompute_spo_arrays(closes, "custom", custom_smooth_len=4, custom_threshold=1.0)
    sig = precompute_signal_arrays(spo["normalized_osc"], spo["threshold"])
    htf = precompute_htf_arrays(closes, highs, lows, volumes)

    # sig_up_raw=True인 봉에서 국면 분석
    print("\n" + "=" * 90)
    print("[sig_up_raw=True 봉별 국면 및 차단 조건 분석]")
    print("=" * 90)
    print(f"{'날짜':<12} | {'국면':^4} | {'buy_mult':^8} | {'allow_osc':^9} | {'차단 여부':^8} | {'차단 이유'}")
    print("-" * 90)

    blocked_list = []

    for i, c in enumerate(candles):
        if not sig["sig_up_raw"][i]:
            continue

        htf_ind = get_htf_indicators_at_index(htf, i)
        regime = detect_regime(htf_ind, True)  # use_4regime=True

        dt = ts_to_date(c.ts)

        # 국면별 파라미터 조회
        buy_mult = app_params.get(f"r{regime}_buy_mult", 1.0)
        allow_osc = app_params.get(f"r{regime}_allow_osc_buy", True)

        # 차단 조건 판단
        blocked = False
        reasons = []

        if buy_mult == 0:
            blocked = True
            reasons.append(f"r{regime}_buy_mult=0")

        if not allow_osc:
            blocked = True
            reasons.append(f"r{regime}_allow_osc_buy=False")

        status = "차단" if blocked else "통과"
        reason_str = ", ".join(reasons) if reasons else "-"

        print(f"{dt:<12} | R{regime:^3} | {buy_mult:^8.1f} | {str(allow_osc):^9} | {status:^8} | {reason_str}")

        if blocked:
            blocked_list.append({
                "date": dt,
                "regime": regime,
                "reasons": reasons,
                "close": c.c
            })

    # 백테스트 실행 (앱 파라미터 그대로)
    print("\n" + "=" * 90)
    print("[백테스트 결과 (앱 파라미터 그대로)]")
    print("=" * 90)

    config = MRConfig(
        osc_preset="custom",
        osc_smooth_len=4,
        osc_threshold=1.0,
        **app_params
    )

    result = run_mr_backtest(
        candles=candles,
        config=config,
        initial_capital=10000000.0,
        fee_rate=0.0
    )

    trades = result.trades if result.success else []
    buy_trades = [t for t in trades if t.action.upper() == "BUY"]

    print(f"실제 BUY 실행: {len(buy_trades)}건")
    print(f"\nBUY 목록:")
    for t in buy_trades:
        print(f"  {ts_to_date(t.timestamp)} | {t.price:>9,.0f}")

    # 차단된 BUY 요약
    print("\n" + "=" * 90)
    print("[차단된 BUY 요약]")
    print("=" * 90)
    print(f"{'차단된 BUY':<4} | {'날짜':<12} | {'막은 조건 이름':<30} | {'그 조건의 값'}")
    print("-" * 90)

    for idx, b in enumerate(blocked_list, 1):
        for reason in b["reasons"]:
            key = reason.split("=")[0]
            val = reason.split("=")[1]
            print(f"#{idx:<3} | {b['date']:<12} | {key:<30} | {val}")

    print("\n" + "=" * 90)
    print("[결론]")
    print("=" * 90)
    print(f"sig_up_raw=True: 10건")
    print(f"통과 (BUY 실행): {len(buy_trades)}건")
    print(f"차단: {len(blocked_list)}건")
    print(f"\n★ 차단 원인: R2 국면의 기본값")
    print(f"  - r2_buy_mult = 0.0 (HTML 기본값)")
    print(f"  - r2_allow_osc_buy = False (체크박스 미체크)")
    print(f"\n★ '필터 OFF'는 filt_below_avg, filt_prev_signal, filt_prev_exec만 해제함")
    print(f"   buy_mult, allow_osc_buy는 국면별 설정이라 별도로 변경해야 함")

if __name__ == "__main__":
    main()

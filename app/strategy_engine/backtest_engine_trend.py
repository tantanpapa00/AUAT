# app/strategy_engine/backtest_engine_trend.py
"""
Trend Strategy Backtest Engine (v8).

추세매매 전략 백테스트 엔진.
기존 BacktestResult, BacktestMetrics 재사용.

v8 신규 기능:
- 피라미딩 (추가매수) 지원
- ATR 기반 손절
- HTF Supertrend (st_exit_mode)
"""

from typing import List, Optional, Dict, Any
from dataclasses import dataclass
from datetime import datetime, timezone
import numpy as np

from .models import Candle
from .backtest_engine import (
    BacktestTrade,
    BacktestMetrics,
    BacktestResult,
    Position,
    calculate_metrics,
)
from .signal_generator_trend import (
    TrendConfig,
    TrendState,
    generate_trend_signal,
)
from .indicators import (
    calc_supertrend,
    calc_hvi,
    calc_qqe_mod,
    calc_spo,
    calc_vwma,
    calc_atr,  # v8: ATR 기반 손절용
)


def run_trend_backtest(
    candles: List[Candle],
    htf_candles: Optional[List[Candle]] = None,
    config: Optional[TrendConfig] = None,
    initial_capital: float = 10000000.0,
    fee_rate: float = 0.00015,  # 0.015% 수수료
) -> BacktestResult:
    """
    추세매매 전략 백테스트 실행 (v8).

    Args:
        candles: 시그널 타임프레임 캔들 데이터 (entry_tf = exit_tf 가정)
        htf_candles: HTF 캔들 데이터 (주봉 등, HTF VWMA용)
        config: 추세매매 설정 (없으면 기본값 사용)
        initial_capital: 초기 자본
        fee_rate: 거래 수수료율

    Returns:
        BacktestResult: 백테스트 결과

    v8 신규:
        - 피라미딩 지원 (복수 진입, 평균단가 계산)
        - ATR 기반 손절
        - HTF Supertrend (st_exit_mode)
    """
    if len(candles) < 300:
        return BacktestResult(
            success=False,
            message=f"데이터 부족: 최소 300봉 필요 (현재 {len(candles)}봉)",
            metrics=BacktestMetrics(),
        )

    # 기본 설정
    if config is None:
        config = TrendConfig()

    if htf_candles is None:
        htf_candles = candles

    # 상태 초기화
    state = TrendState()
    position = Position()
    capital = initial_capital

    # 결과 저장
    trades: List[BacktestTrade] = []
    signals: List[Dict[str, Any]] = []
    equity_curve: List[Dict[str, Any]] = []

    # numpy 배열 변환
    closes = np.array([c.c for c in candles])
    highs = np.array([c.h for c in candles])
    lows = np.array([c.l for c in candles])
    volumes = np.array([c.v for c in candles])

    htf_closes = np.array([c.c for c in htf_candles])
    htf_highs = np.array([c.h for c in htf_candles])
    htf_lows = np.array([c.l for c in htf_candles])
    htf_volumes = np.array([c.v for c in htf_candles])

    # 지표 계산에 필요한 최소 봉 수
    lookback = 300

    for i in range(lookback, len(candles)):
        candle = candles[i]
        price = candle.c

        # 현재 자산 평가
        equity = capital + (position.quantity * price)
        equity_curve.append({
            "bar_index": i,
            "timestamp": candle.ts,
            "equity": equity,
            "position_qty": position.quantity,
            "position_value": position.quantity * price,
            "cash": capital,
            "avg_entry_price": position.avg_price,  # v8: 평균단가 추가
            "pyr_count": state.pyr_count,           # v8: 피라미딩 횟수
        })

        # 슬라이스 데이터
        slice_closes = closes[max(0, i - lookback + 1):i + 1]
        slice_highs = highs[max(0, i - lookback + 1):i + 1]
        slice_lows = lows[max(0, i - lookback + 1):i + 1]
        slice_volumes = volumes[max(0, i - lookback + 1):i + 1]

        # HTF 데이터 매핑
        htf_ratio = len(htf_candles) / len(candles)
        htf_idx = min(int(i * htf_ratio), len(htf_candles) - 1)
        htf_slice_closes = htf_closes[max(0, htf_idx - lookback + 1):htf_idx + 1]
        htf_slice_highs = htf_highs[max(0, htf_idx - lookback + 1):htf_idx + 1]
        htf_slice_lows = htf_lows[max(0, htf_idx - lookback + 1):htf_idx + 1]
        htf_slice_volumes = htf_volumes[max(0, htf_idx - lookback + 1):htf_idx + 1]

        # Entry 지표 계산
        st_value, st_dir = calc_supertrend(
            slice_highs, slice_lows, slice_closes,
            config.st_atr_len, config.st_factor
        )

        hvi_result = calc_hvi(
            slice_highs, slice_lows, slice_closes, slice_volumes,
            config.hvi_length, config.hvi_divisor
        )

        qqe_result = calc_qqe_mod(
            slice_closes,
            config.qqe_rsi_length, config.qqe_rsi_smoothing, config.qqe_factor
        )

        # HTF VWMA
        if len(htf_slice_closes) >= config.htf_vwma_len:
            htf_vwma = calc_vwma(htf_slice_closes, htf_slice_volumes, config.htf_vwma_len)
        else:
            htf_vwma = np.full(len(htf_slice_closes), np.nan)

        # Exit ST 계산 (exit_tf 데이터 = htf_candles 사용)
        # Note: exit_tf ST는 htf 데이터에서 계산
        exit_st_value, exit_st_dir = calc_supertrend(
            htf_slice_highs, htf_slice_lows, htf_slice_closes,
            config.st_atr_len, config.st_factor
        )

        spo_result = calc_spo(
            slice_closes,
            smooth_len=config.exit_spo_smooth_len,
            threshold=config.exit_spo_threshold,
            std_len=config.exit_spo_std_len,
            hma_len=config.exit_spo_hma_len,
        )
        spo_norm = spo_result[0]  # normalized_osc

        # v8: ATR 계산 (ATR 기반 손절용)
        entry_atr = None
        if config.stop_type == "atr":
            entry_atr = calc_atr(slice_highs, slice_lows, slice_closes, config.atr_stop_len)

        # 신호 생성 (v8 최종: TF 단순화)
        signal, state = generate_trend_signal(
            entry_close=slice_closes,
            entry_st_dir=st_dir,
            entry_hvi=hvi_result,
            entry_qqe=qqe_result,
            htf_vwma=htf_vwma,
            exit_close=htf_slice_closes,
            exit_st_dir=exit_st_dir,
            exit_spo_norm=spo_norm,
            config=config,
            state=state,
            current_ts=candle.ts,
            entry_atr=entry_atr,
            entry_high=slice_highs,
            bar_index=i,
        )

        if signal.action != "hold":
            signals.append({
                "bar_index": i,
                "timestamp": candle.ts,
                "action": signal.action,
                "reason_code": signal.reason_code,
                "tranche_pct": signal.tranche_pct,
                "pyr_count": state.pyr_count,  # v8
            })

            # 거래 실행
            if signal.action == "buy" and capital > 0:
                # 매수 (1차 진입 또는 피라미딩)
                use_pct = signal.tranche_pct / 100.0
                use_amount = capital * use_pct
                use_amount = min(use_amount, capital)

                if use_amount > 0:
                    fee = use_amount * fee_rate
                    net_amount = use_amount - fee
                    qty = net_amount / price

                    # v8: 수량 반올림 (주식용)
                    if config.round_qty:
                        qty = max(config.min_qty, round(qty))
                    qty = max(config.min_qty, qty)

                    # 재계산 (반올림 후)
                    actual_amount = qty * price
                    if actual_amount <= capital:
                        position.add(qty, price)
                        capital -= actual_amount + (actual_amount * fee_rate)

                        # v8: 평균단가 업데이트
                        state.avg_entry_price = position.avg_price

                        trades.append(BacktestTrade(
                            bar_index=i,
                            timestamp=candle.ts,
                            action="buy",
                            price=price,
                            quantity=qty,
                            tranche=state.pyr_count,  # v8: 피라미딩 차수
                            reason_code=signal.reason_code,
                        ))

            elif signal.action == "sell" and position.quantity > 0:
                # 매도
                sell_pct = signal.tranche_pct / 100.0
                sell_qty = position.quantity * sell_pct
                sell_qty = min(sell_qty, position.quantity)

                # v8: 수량 반올림
                if config.round_qty:
                    sell_qty = round(sell_qty)
                    if sell_qty < config.min_qty and position.quantity >= config.min_qty:
                        sell_qty = config.min_qty
                sell_qty = min(sell_qty, position.quantity)

                if sell_qty > 0:
                    avg_price_before = position.avg_price
                    pnl = position.remove(sell_qty, price)
                    proceeds = sell_qty * price
                    fee = proceeds * fee_rate
                    net_proceeds = proceeds - fee
                    pnl -= fee

                    capital += net_proceeds
                    pnl_pct = (price - avg_price_before) / avg_price_before * 100 if avg_price_before > 0 else 0

                    trades.append(BacktestTrade(
                        bar_index=i,
                        timestamp=candle.ts,
                        action="sell",
                        price=price,
                        quantity=sell_qty,
                        tranche=state.sell_stage,
                        reason_code=signal.reason_code,
                        pnl=pnl,
                        pnl_pct=pnl_pct,
                    ))

                    # 전량 청산 시 상태 리셋
                    if position.quantity <= 0:
                        state.in_position = False
                        state.entry_price = 0.0
                        state.tp1_triggered = False
                        state.sell_stage = 0
                        state.pyr_count = 0
                        state.avg_entry_price = 0.0
                        state.total_cost = 0.0

    # 마지막 포지션 정리
    if position.quantity > 0:
        last_price = candles[-1].c
        avg_price_before = position.avg_price
        pnl = position.remove(position.quantity, last_price)
        proceeds = position.quantity * last_price
        fee = proceeds * fee_rate
        capital += proceeds - fee

    # 최종 자산
    final_equity = capital

    # 성과 지표 계산
    metrics = calculate_metrics(
        equity_curve=equity_curve,
        trades=trades,
        initial_capital=initial_capital,
        final_equity=final_equity,
    )

    return BacktestResult(
        success=True,
        message=f"추세매매 백테스트 완료: {len(candles)}봉, {len(trades)}거래",
        metrics=metrics,
        equity_curve=equity_curve,
        trades=trades,
        signals=signals,
    )


def generate_trend_sample_candles(
    days: int = 365,
    base_price: float = 100000.0,
    volatility: float = 0.015,
    trend: float = 0.0002,  # 상승 추세 (추세매매에 유리)
    seed: int = 42,
) -> List[Candle]:
    """
    추세매매 백테스트용 샘플 캔들 데이터 생성 (상승 추세 포함).

    Args:
        days: 생성할 일수
        base_price: 시작 가격
        volatility: 변동성
        trend: 추세 강도 (양수=상승, 음수=하락)
        seed: 랜덤 시드

    Returns:
        List[Candle]: 일봉 기준 캔들 데이터
    """
    import random
    random.seed(seed)

    candles = []
    price = base_price
    ts = int(datetime(2023, 1, 1, tzinfo=timezone.utc).timestamp() * 1000)

    for i in range(days):
        # 가격 변동 (추세 포함)
        change = (random.random() - 0.5 + trend) * volatility * price
        open_price = price
        price = max(price + change, price * 0.5)

        high = max(open_price, price) * (1 + random.random() * volatility * 0.5)
        low = min(open_price, price) * (1 - random.random() * volatility * 0.5)
        volume = random.uniform(1000000, 10000000)

        candles.append(Candle(
            ts=ts,
            o=open_price,
            h=high,
            l=low,
            c=price,
            v=volume,
        ))

        ts += 86400 * 1000  # 1일 증가 (일봉)

    return candles


def generate_weekly_candles_from_daily(daily_candles: List[Candle]) -> List[Candle]:
    """
    일봉 캔들에서 주봉 캔들 생성.

    Args:
        daily_candles: 일봉 캔들 리스트

    Returns:
        List[Candle]: 주봉 캔들 리스트
    """
    if not daily_candles:
        return []

    weekly_candles = []
    week_open = daily_candles[0].o
    week_high = daily_candles[0].h
    week_low = daily_candles[0].l
    week_volume = 0.0
    week_ts = daily_candles[0].ts
    day_count = 0

    for candle in daily_candles:
        week_high = max(week_high, candle.h)
        week_low = min(week_low, candle.l)
        week_volume += candle.v
        day_count += 1

        # 5일마다 주봉 생성 (간단한 구현)
        if day_count >= 5:
            weekly_candles.append(Candle(
                ts=week_ts,
                o=week_open,
                h=week_high,
                l=week_low,
                c=candle.c,
                v=week_volume,
            ))

            # 다음 주 시작
            day_count = 0
            if len(daily_candles) > daily_candles.index(candle) + 1:
                next_candle = daily_candles[daily_candles.index(candle) + 1]
                week_open = next_candle.o
                week_high = next_candle.h
                week_low = next_candle.l
                week_volume = 0.0
                week_ts = next_candle.ts

    # 마지막 미완성 주봉 추가
    if day_count > 0:
        weekly_candles.append(Candle(
            ts=week_ts,
            o=week_open,
            h=week_high,
            l=week_low,
            c=daily_candles[-1].c,
            v=week_volume,
        ))

    return weekly_candles

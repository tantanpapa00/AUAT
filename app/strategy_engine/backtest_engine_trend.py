# app/strategy_engine/backtest_engine_trend.py
"""
Trend Strategy Backtest Engine (v8 + Vectorized).

추세매매 전략 백테스트 엔진.
기존 BacktestResult, BacktestMetrics 재사용.

v8 신규 기능:
- 피라미딩 (추가매수) 지원
- ATR 기반 손절
- HTF Supertrend (st_exit_mode)

v8.1 벡터화 최적화:
- 모든 지표를 루프 전 한 번만 계산
- 20~50배 속도 향상
"""

from typing import List, Optional, Dict, Any, Tuple
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
    calc_sma,
    calc_atr,
)


# ============================================================
# 벡터화 사전 계산 함수들
# ============================================================

def build_htf_index_map(
    signal_candles: List[Candle],
    htf_candles: List[Candle],
) -> np.ndarray:
    """
    타임스탬프 기반 HTF 인덱스 매핑 테이블 생성.

    PineScript request.security(lookahead=off) 동작 모방:
    - 현재 signal_tf 봉 시점에서 "확정된" HTF 봉 인덱스 반환
    - 현재 봉 타임스탬프 <= HTF 봉 타임스탬프인 가장 최근 HTF 봉

    Args:
        signal_candles: 시그널 TF 캔들 리스트
        htf_candles: HTF 캔들 리스트

    Returns:
        np.ndarray: signal_candles 각 인덱스에 대응하는 htf_candles 인덱스
    """
    n_signal = len(signal_candles)
    n_htf = len(htf_candles)

    if n_htf == 0:
        return np.zeros(n_signal, dtype=int)

    # HTF 타임스탬프 배열
    htf_timestamps = np.array([c.ts for c in htf_candles])

    # 각 signal 봉에 대해 대응하는 HTF 인덱스 찾기
    htf_indices = np.zeros(n_signal, dtype=int)

    htf_ptr = 0
    for i, candle in enumerate(signal_candles):
        curr_ts = candle.ts

        # 현재 signal 봉 타임스탬프보다 작거나 같은 가장 큰 HTF 인덱스 찾기
        while htf_ptr < n_htf - 1 and htf_timestamps[htf_ptr + 1] <= curr_ts:
            htf_ptr += 1

        htf_indices[i] = htf_ptr

    return htf_indices


def precompute_supertrend(
    highs: np.ndarray,
    lows: np.ndarray,
    closes: np.ndarray,
    atr_len: int,
    factor: float,
) -> Dict[str, np.ndarray]:
    """Supertrend 지표를 전체 시리즈에서 한 번만 계산."""
    st_value, st_dir = calc_supertrend(highs, lows, closes, atr_len, factor)
    return {
        "value": st_value,
        "direction": st_dir,
    }


def precompute_hvi(
    highs: np.ndarray,
    lows: np.ndarray,
    closes: np.ndarray,
    volumes: np.ndarray,
    length: int,
    divisor: float,
) -> Dict[str, np.ndarray]:
    """HVI 지표를 전체 시리즈에서 한 번만 계산."""
    result = calc_hvi(highs, lows, closes, volumes, length, divisor)
    return result  # dict with 'hvi', 'g_enabled', 'r_enabled' etc.


def precompute_qqe(
    closes: np.ndarray,
    rsi_length: int,
    rsi_smoothing: int,
    factor: float,
) -> Dict[str, np.ndarray]:
    """QQE Mod 지표를 전체 시리즈에서 한 번만 계산."""
    result = calc_qqe_mod(closes, rsi_length, rsi_smoothing, factor)
    return result  # dict with 'primary_rsi', 'secondary_rsi', etc.


def precompute_vwma(
    closes: np.ndarray,
    volumes: np.ndarray,
    length: int,
) -> np.ndarray:
    """VWMA를 전체 시리즈에서 한 번만 계산."""
    if len(closes) < length:
        return np.full(len(closes), np.nan)
    return calc_vwma(closes, volumes, length)


def precompute_sma(
    closes: np.ndarray,
    length: int,
) -> np.ndarray:
    """SMA를 전체 시리즈에서 한 번만 계산 (크립토 HTF 필터용)."""
    if len(closes) < length:
        return np.full(len(closes), np.nan)
    return calc_sma(closes, length)


def precompute_spo(
    closes: np.ndarray,
    smooth_len: int,
    threshold: float,
    std_len: int,
    hma_len: int,
) -> Dict[str, np.ndarray]:
    """SPO 지표를 전체 시리즈에서 한 번만 계산."""
    # calc_spo returns: normalized_osc, upper_band, lower_band, basis, line_short, line_long
    normalized_osc, upper_band, lower_band, basis, line_short, line_long = calc_spo(
        closes, smooth_len, threshold, std_len, hma_len
    )
    return {
        "normalized_osc": normalized_osc,
        "upper_band": upper_band,
        "lower_band": lower_band,
        "basis": basis,
        "line_short": line_short,
        "line_long": line_long,
    }


def precompute_atr(
    highs: np.ndarray,
    lows: np.ndarray,
    closes: np.ndarray,
    length: int,
) -> np.ndarray:
    """ATR을 전체 시리즈에서 한 번만 계산."""
    return calc_atr(highs, lows, closes, length)


# ============================================================
# 메인 백테스트 함수 (벡터화 버전)
# ============================================================

def run_trend_backtest(
    candles: List[Candle],
    exit_candles: Optional[List[Candle]] = None,
    htf_candles: Optional[List[Candle]] = None,
    config: Optional[TrendConfig] = None,
    initial_capital: float = 10000000.0,
    fee_rate: float = 0.00015,  # 0.015% 수수료
) -> BacktestResult:
    """
    추세매매 전략 백테스트 실행 (v8 + 벡터화).

    Args:
        candles: 시그널 타임프레임 캔들 데이터 (매수/분할매도/손절/TP1)
        exit_candles: 매도기준 타임프레임 캔들 (ST 전량매도 전용)
        htf_candles: 상위기준 타임프레임 캔들 (HTF VWMA 필터 전용)
        config: 추세매매 설정 (없으면 기본값 사용)
        initial_capital: 초기 자본
        fee_rate: 거래 수수료율

    Returns:
        BacktestResult: 백테스트 결과

    v8.1 벡터화:
        - 모든 지표를 루프 전 한 번만 계산
        - 20~50배 속도 향상
    """
    # 지표별 최소 필요 봉 수 동적 계산
    if config is None:
        config = TrendConfig()

    required_bars = max(
        config.hvi_length + 50,           # HVI (가장 긴 지표)
        config.htf_vwma_len + 20,         # VWMA
        config.exit_spo_std_len + 30,     # SPO
        config.pyr_high_len + 20,         # 피라미딩 신고가
        config.st_atr_len * 3,            # Supertrend
        100                               # 최소 안전선
    )

    if len(candles) < required_bars:
        return BacktestResult(
            success=False,
            message=f"데이터 부족: 최소 {required_bars}봉 필요 (현재 {len(candles)}봉)",
            metrics=BacktestMetrics(),
        )

    # 캔들 폴백 (None이면 signal_tf 캔들 사용)
    if exit_candles is None:
        exit_candles = candles
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

    # ============================================================
    # numpy 배열 변환
    # ============================================================
    # signal_tf 배열
    closes = np.array([c.c for c in candles])
    highs = np.array([c.h for c in candles])
    lows = np.array([c.l for c in candles])
    volumes = np.array([c.v for c in candles])

    # exit_tf 배열 (ST 전량매도 전용)
    exit_closes = np.array([c.c for c in exit_candles])
    exit_highs = np.array([c.h for c in exit_candles])
    exit_lows = np.array([c.l for c in exit_candles])

    # htf_tf 배열 (HTF VWMA 필터 전용)
    htf_closes = np.array([c.c for c in htf_candles])
    htf_volumes = np.array([c.v for c in htf_candles])

    # ============================================================
    # 벡터화 최적화: 전체 시리즈에서 지표 사전 계산
    # ============================================================
    # 1. Entry Supertrend (signal_tf)
    entry_st = precompute_supertrend(
        highs, lows, closes,
        config.st_atr_len, config.st_factor
    )

    # 2. HVI (signal_tf)
    entry_hvi = precompute_hvi(
        highs, lows, closes, volumes,
        config.hvi_length, config.hvi_divisor
    )

    # 3. QQE Mod (signal_tf)
    entry_qqe = precompute_qqe(
        closes,
        config.qqe_rsi_length, config.qqe_rsi_smoothing, config.qqe_factor
    )

    # 4. HTF 필터 (htf_tf)
    # PineScript v8: 주식=VWMA(156), 크립토=SMA(200)
    if config.asset_type == "crypto":
        # 크립토: 일봉 SMA(200)
        htf_vwma_full = precompute_sma(htf_closes, config.htf_sma_len)
    else:
        # 주식: 주봉 VWMA(156)
        htf_vwma_full = precompute_vwma(htf_closes, htf_volumes, config.htf_vwma_len)

    # 5. Exit Supertrend (exit_tf)
    exit_st = precompute_supertrend(
        exit_highs, exit_lows, exit_closes,
        config.st_atr_len, config.st_factor
    )

    # 6. SPO (signal_tf - 분할매도용)
    entry_spo = precompute_spo(
        closes,
        config.exit_spo_smooth_len, config.exit_spo_threshold,
        config.exit_spo_std_len, config.exit_spo_hma_len
    )

    # 7. ATR (signal_tf - ATR 손절용)
    entry_atr_full = None
    if config.stop_type == "atr":
        entry_atr_full = precompute_atr(
            highs, lows, closes, config.atr_stop_len
        )

    # 8. 타임스탬프 기반 HTF 인덱스 매핑 (request.security 모방)
    exit_idx_map = build_htf_index_map(candles, exit_candles)
    htf_idx_map = build_htf_index_map(candles, htf_candles)

    # 지표 계산에 필요한 최소 봉 수 (동적 계산값 사용)
    lookback = required_bars

    # ============================================================
    # 메인 루프 (지표는 인덱스로만 조회)
    # ============================================================
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
            "avg_entry_price": position.avg_price,
            "pyr_count": state.pyr_count,
        })

        # TF 인덱스 매핑 (타임스탬프 기반, request.security 모방)
        exit_idx = exit_idx_map[i]
        htf_idx = htf_idx_map[i]

        # 슬라이스 범위 (신호 생성기가 배열을 기대하므로)
        slice_start = max(0, i - lookback + 1)
        slice_end = i + 1

        exit_slice_start = max(0, exit_idx - lookback + 1)
        exit_slice_end = exit_idx + 1

        htf_slice_start = max(0, htf_idx - lookback + 1)
        htf_slice_end = htf_idx + 1

        # 신호 생성 (사전 계산된 지표 슬라이스 사용)
        # 참고: generate_trend_signal은 배열의 마지막 값을 사용하므로
        # 슬라이스 대신 전체 배열의 현재 인덱스까지의 슬라이스 전달

        # HVI dict 슬라이스 (g_enabled, r_enabled, gr_enabled)
        hvi_slice = {
            k: v[slice_start:slice_end] if isinstance(v, np.ndarray) else v
            for k, v in entry_hvi.items()
        }

        # QQE dict 슬라이스 (primary_rsi, qqe_line, is_positive, trend_dir)
        qqe_slice = {
            k: v[slice_start:slice_end] if isinstance(v, np.ndarray) else v
            for k, v in entry_qqe.items()
        }

        signal, state = generate_trend_signal(
            entry_close=closes[slice_start:slice_end],
            entry_st_dir=entry_st["direction"][slice_start:slice_end],
            entry_hvi=hvi_slice,
            entry_qqe=qqe_slice,
            htf_vwma=htf_vwma_full[htf_slice_start:htf_slice_end],
            exit_close=htf_closes[htf_slice_start:htf_slice_end],
            exit_st_dir=exit_st["direction"][exit_slice_start:exit_slice_end],
            exit_spo_norm=entry_spo["normalized_osc"][slice_start:slice_end],
            config=config,
            state=state,
            current_ts=candle.ts,
            entry_atr=entry_atr_full[slice_start:slice_end] if entry_atr_full is not None else None,
            entry_high=highs[slice_start:slice_end],
            bar_index=i,
            is_bar_confirmed=True,  # 백테스트는 항상 확정 봉 사용
        )

        if signal.action != "hold":
            signals.append({
                "bar_index": i,
                "timestamp": candle.ts,
                "action": signal.action,
                "reason_code": signal.reason_code,
                "tranche_pct": signal.tranche_pct,
                "pyr_count": state.pyr_count,
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
                            tranche=state.pyr_count,
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

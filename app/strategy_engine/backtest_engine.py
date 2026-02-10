# app/strategy_engine/backtest_engine.py
"""
MR Premium Strategy Backtest Engine

Phase 5: 역추세매매(MR) 프리미엄 전략 백테스트
- 실제 OHLCV 데이터 사용 (candle_fetcher)
- MR signal_generator 실행
- 트랜치 기반 포지션 관리
- 성과 지표 계산 (수익률, MDD, 샤프비율, 승률)

Phase 5.1: 벡터화 최적화 (2000봉 20초 → 5초 이내)
- 전체 시리즈에서 SPO 지표 한 번만 계산
- sig_up_raw, sig_dn_raw 배열 사전 계산
- HTF 지표 사전 계산
- 루프에서는 인덱스 접근만
"""

from typing import List, Dict, Optional, Any
from dataclasses import dataclass, field
from datetime import datetime, timezone
import math
import numpy as np

from .models import Candle, SignalResult, MRConfig, StrategyState, HTFIndicators, OscillatorData
from .indicators import calc_spo, calc_vwma, calc_hma, calc_ichimoku, calc_supertrend
from .regime_detector import detect_regime, calc_htf_indicators
from .signal_generator import generate_mr_signal, calc_osc_data
from .presets import OSC_PRESETS, HTF_DEFAULTS


# ============================================================
# 벡터화 사전 계산 함수들
# ============================================================

def precompute_spo_arrays(
    closes: np.ndarray,
    preset: str = "preset1"
) -> Dict[str, np.ndarray]:
    """
    전체 시리즈에서 SPO 지표를 한 번에 계산.

    Returns:
        Dict with normalized_osc, upper_band, lower_band, basis, line_short, line_long arrays
    """
    params = OSC_PRESETS.get(preset, OSC_PRESETS["preset1"])

    normalized_osc, upper_band, lower_band, basis, line_short, line_long = calc_spo(
        closes,
        smooth_len=params["smooth_len"],
        threshold=params["threshold"],
        std_len=params["std_len"],
        hma_len=params["hma_len"],
        bb_len=params["bb_len"],
        bb_mult=params["bb_mult"],
    )

    return {
        "normalized_osc": normalized_osc,
        "upper_band": upper_band,
        "lower_band": lower_band,
        "basis": basis,
        "line_short": line_short,
        "line_long": line_long,
        "threshold": params["threshold"],
    }


def precompute_signal_arrays(
    normalized_osc: np.ndarray,
    threshold: float
) -> Dict[str, np.ndarray]:
    """
    전체 시리즈에서 sig_up_raw, sig_dn_raw 배열을 한 번에 계산.

    sig_up_raw: osc < -threshold AND osc가 상승 반전 (이전에 하락하다가 상승)
    sig_dn_raw: osc > threshold AND osc가 하락 반전 (이전에 상승하다가 하락)
    """
    n = len(normalized_osc)
    sig_up_raw = np.zeros(n, dtype=bool)
    sig_dn_raw = np.zeros(n, dtype=bool)

    if n < 3:
        return {"sig_up_raw": sig_up_raw, "sig_dn_raw": sig_dn_raw}

    # 벡터화: osc[i] vs osc[i-1] vs osc[i-2]
    osc = normalized_osc

    # osc[2:] = current, osc[1:-1] = prev, osc[:-2] = prev_prev
    osc_curr = osc[2:]
    osc_prev = osc[1:-1]
    osc_prev_prev = osc[:-2]

    # sig_up: osc < -threshold AND osc_curr > osc_prev AND osc_prev <= osc_prev_prev
    sig_up_cond = (
        (osc_curr < -threshold) &
        (osc_curr > osc_prev) &
        (osc_prev <= osc_prev_prev) &
        ~np.isnan(osc_curr) &
        ~np.isnan(osc_prev) &
        ~np.isnan(osc_prev_prev)
    )
    sig_up_raw[2:] = sig_up_cond

    # sig_dn: osc > threshold AND osc_curr < osc_prev AND osc_prev >= osc_prev_prev
    sig_dn_cond = (
        (osc_curr > threshold) &
        (osc_curr < osc_prev) &
        (osc_prev >= osc_prev_prev) &
        ~np.isnan(osc_curr) &
        ~np.isnan(osc_prev) &
        ~np.isnan(osc_prev_prev)
    )
    sig_dn_raw[2:] = sig_dn_cond

    return {"sig_up_raw": sig_up_raw, "sig_dn_raw": sig_dn_raw}


def precompute_htf_arrays(
    htf_closes: np.ndarray,
    htf_highs: np.ndarray,
    htf_lows: np.ndarray,
    htf_volumes: np.ndarray,
) -> Dict[str, np.ndarray]:
    """
    전체 HTF 시리즈에서 모든 지표를 한 번에 계산.

    Returns:
        Dict with vwma50, vwma200, hull, st_value, st_direction, tenkan, kijun, senkou_a, senkou_b arrays
    """
    n = len(htf_closes)

    # VWMA
    vwma50 = calc_vwma(htf_closes, htf_volumes, HTF_DEFAULTS["vwma50_len"])
    vwma200 = calc_vwma(htf_closes, htf_volumes, HTF_DEFAULTS["vwma200_len"])

    # Hull MA
    hull = calc_hma(htf_closes, HTF_DEFAULTS["hull_len"])

    # Supertrend
    st_value, st_direction = calc_supertrend(
        htf_highs, htf_lows, htf_closes,
        HTF_DEFAULTS["st_atr_len"], HTF_DEFAULTS["st_factor"]
    )
    # Invert direction (PineScript default)
    st_direction = -st_direction

    # Ichimoku
    tenkan, kijun, senkou_a, senkou_b = calc_ichimoku(
        htf_highs, htf_lows,
        HTF_DEFAULTS["ichi_tenkan"],
        HTF_DEFAULTS["ichi_kijun"],
        HTF_DEFAULTS["ichi_senkou"],
    )

    return {
        "vwma50": vwma50,
        "vwma200": vwma200,
        "hull": hull,
        "st_value": st_value,
        "st_direction": st_direction.astype(int),
        "tenkan": tenkan,
        "kijun": kijun,
        "senkou_a": senkou_a,
        "senkou_b": senkou_b,
    }


def get_htf_indicators_at_index(
    htf_arrays: Dict[str, np.ndarray],
    idx: int
) -> HTFIndicators:
    """
    사전 계산된 HTF 배열에서 특정 인덱스의 HTFIndicators 추출.
    """
    def safe_get(arr: np.ndarray, i: int) -> float:
        if i < 0 or i >= len(arr):
            return 0.0
        val = arr[i]
        return 0.0 if np.isnan(val) else float(val)

    v50 = safe_get(htf_arrays["vwma50"], idx)
    v200 = safe_get(htf_arrays["vwma200"], idx)
    h = safe_get(htf_arrays["hull"], idx)
    h_prev = safe_get(htf_arrays["hull"], idx - 1) if idx > 0 else h
    t = safe_get(htf_arrays["tenkan"], idx)
    k = safe_get(htf_arrays["kijun"], idx)
    sa = safe_get(htf_arrays["senkou_a"], idx)
    sb = safe_get(htf_arrays["senkou_b"], idx)
    st_v = safe_get(htf_arrays["st_value"], idx)
    st_d = int(htf_arrays["st_direction"][idx]) if idx < len(htf_arrays["st_direction"]) else 0

    cloud_upper = max(sa, sb)
    cloud_lower = min(sa, sb)
    cloud_bull = sa > sb
    cloud_bear = sa < sb
    bull_stack = v50 >= v200
    bear_stack = v50 < v200
    hull_up = h > h_prev
    hull_dn = h < h_prev

    return HTFIndicators(
        vwma50=v50,
        vwma200=v200,
        hull=h,
        hull_up=hull_up,
        hull_dn=hull_dn,
        tenkan=t,
        kijun=k,
        senkou_a=sa,
        senkou_b=sb,
        cloud_upper=cloud_upper,
        cloud_lower=cloud_lower,
        cloud_bull=cloud_bull,
        cloud_bear=cloud_bear,
        st_value=st_v,
        st_direction=st_d,
        bull_stack=bull_stack,
        bear_stack=bear_stack,
    )


def get_osc_data_at_index(
    spo_arrays: Dict[str, np.ndarray],
    sig_arrays: Dict[str, np.ndarray],
    closes: np.ndarray,
    idx: int
) -> OscillatorData:
    """
    사전 계산된 SPO/신호 배열에서 특정 인덱스의 OscillatorData 추출.
    """
    def safe_get(arr: np.ndarray, i: int) -> float:
        if i < 0 or i >= len(arr):
            return 0.0
        val = arr[i]
        return 0.0 if np.isnan(val) else float(val)

    osc_curr = safe_get(spo_arrays["normalized_osc"], idx)
    ub = safe_get(spo_arrays["upper_band"], idx)
    lb = safe_get(spo_arrays["lower_band"], idx)
    bs = safe_get(spo_arrays["basis"], idx)
    ls = safe_get(spo_arrays["line_short"], idx)
    ll = safe_get(spo_arrays["line_long"], idx)
    osc_raw = ls - ll

    sig_up = sig_arrays["sig_up_raw"][idx] if idx < len(sig_arrays["sig_up_raw"]) else False
    sig_dn = sig_arrays["sig_dn_raw"][idx] if idx < len(sig_arrays["sig_dn_raw"]) else False

    return OscillatorData(
        normalized_osc=osc_curr,
        upper_band=ub,
        lower_band=lb,
        basis=bs,
        threshold=spo_arrays["threshold"],
        line_short=ls,
        line_long=ll,
        oscillator_raw=osc_raw,
        sig_up_raw=bool(sig_up),
        sig_dn_raw=bool(sig_dn),
    )


@dataclass
class BacktestTrade:
    """백테스트 거래 기록"""
    bar_index: int
    timestamp: int
    action: str  # "buy" or "sell"
    price: float
    quantity: float
    tranche: int
    reason_code: str
    pnl: Optional[float] = None
    pnl_pct: Optional[float] = None


@dataclass
class BacktestMetrics:
    """백테스트 성과 지표"""
    total_return_pct: float = 0.0
    cagr_pct: float = 0.0
    max_drawdown_pct: float = 0.0
    sharpe_ratio: float = 0.0
    win_rate_pct: float = 0.0
    total_trades: int = 0
    winning_trades: int = 0
    losing_trades: int = 0
    avg_win_pct: float = 0.0
    avg_loss_pct: float = 0.0
    profit_factor: float = 0.0
    max_consecutive_wins: int = 0
    max_consecutive_losses: int = 0


@dataclass
class BacktestResult:
    """백테스트 결과"""
    success: bool
    message: str
    metrics: BacktestMetrics
    equity_curve: List[Dict[str, Any]] = field(default_factory=list)
    trades: List[BacktestTrade] = field(default_factory=list)
    signals: List[Dict[str, Any]] = field(default_factory=list)


@dataclass
class Position:
    """현재 포지션 상태"""
    quantity: float = 0.0
    avg_price: float = 0.0
    total_cost: float = 0.0

    def add(self, qty: float, price: float):
        """포지션 추가 (매수)"""
        new_cost = qty * price
        self.total_cost += new_cost
        self.quantity += qty
        if self.quantity > 0:
            self.avg_price = self.total_cost / self.quantity

    def remove(self, qty: float, price: float) -> float:
        """포지션 감소 (매도), 실현 손익 반환"""
        if qty > self.quantity:
            qty = self.quantity
        pnl = (price - self.avg_price) * qty
        self.quantity -= qty
        self.total_cost = self.avg_price * self.quantity
        return pnl


def run_mr_backtest(
    candles: List[Candle],
    htf_candles: Optional[List[Candle]] = None,
    config: Optional[MRConfig] = None,
    initial_capital: float = 10000000.0,
    fee_rate: float = 0.001,  # 0.1% 수수료
) -> BacktestResult:
    """
    MR 프리미엄 전략 백테스트 실행 (벡터화 최적화 버전)

    Args:
        candles: 시그널 타임프레임 캔들 데이터
        htf_candles: HTF 캔들 데이터 (없으면 candles 사용)
        config: MR 설정 (없으면 기본값 사용)
        initial_capital: 초기 자본
        fee_rate: 거래 수수료율

    Returns:
        BacktestResult: 백테스트 결과
    """
    if len(candles) < 50:
        return BacktestResult(
            success=False,
            message=f"시세 데이터가 부족합니다: {len(candles)}봉 (최소 50봉 필요). 기간을 늘리거나 타임프레임을 변경해보세요.",
            metrics=BacktestMetrics(),
        )

    # 기본 설정
    if config is None:
        config = MRConfig()

    if htf_candles is None:
        htf_candles = candles

    # 상태 초기화
    state = StrategyState()
    position = Position()
    capital = initial_capital

    # 결과 저장
    trades: List[BacktestTrade] = []
    signals: List[Dict[str, Any]] = []
    equity_curve: List[Dict[str, Any]] = []

    # 지표 계산에 필요한 데이터 준비 (numpy 배열로 변환)
    closes = np.array([c.c for c in candles])
    highs = np.array([c.h for c in candles])
    lows = np.array([c.l for c in candles])
    volumes = np.array([c.v for c in candles])

    htf_closes = np.array([c.c for c in htf_candles])
    htf_highs = np.array([c.h for c in htf_candles])
    htf_lows = np.array([c.l for c in htf_candles])
    htf_volumes = np.array([c.v for c in htf_candles])

    # ============================================================
    # 벡터화 최적화: 전체 시리즈에서 지표 사전 계산
    # ============================================================
    # 1. SPO 지표 사전 계산 (전체 시리즈에서 한 번만)
    spo_arrays = precompute_spo_arrays(closes, config.osc_preset)

    # 2. 신호 배열 사전 계산 (sig_up_raw, sig_dn_raw)
    sig_arrays = precompute_signal_arrays(
        spo_arrays["normalized_osc"],
        spo_arrays["threshold"]
    )

    # 3. HTF 지표 사전 계산 (전체 HTF 시리즈에서 한 번만)
    htf_arrays = precompute_htf_arrays(htf_closes, htf_highs, htf_lows, htf_volumes)

    # HTF 비율 계산 (시그널TF → HTF 인덱스 매핑용)
    htf_ratio = len(htf_candles) / len(candles)

    # 각 봉에 대해 시뮬레이션
    # OSC preset1: bb_len=250 필요, HTF 지표: 200 필요 → 300으로 설정
    lookback = min(300, len(candles) - 1)

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
        })

        # ============================================================
        # 기존 코드 (매 봉마다 지표 재계산 - 느림)
        # ============================================================
        # # 지표 데이터 슬라이스
        # slice_closes = closes[max(0, i - lookback + 1):i + 1]
        # slice_highs = highs[max(0, i - lookback + 1):i + 1]
        # slice_lows = lows[max(0, i - lookback + 1):i + 1]
        # slice_volumes = volumes[max(0, i - lookback + 1):i + 1]
        #
        # # 오실레이터 데이터 계산
        # osc_data = calc_osc_data(slice_closes, config.osc_preset)
        #
        # # HTF 지표 계산 (비율로 매핑)
        # htf_idx = min(int(i * htf_ratio), len(htf_candles) - 1)
        # htf_slice_closes = htf_closes[max(0, htf_idx - lookback + 1):htf_idx + 1]
        # htf_slice_highs = htf_highs[max(0, htf_idx - lookback + 1):htf_idx + 1]
        # htf_slice_lows = htf_lows[max(0, htf_idx - lookback + 1):htf_idx + 1]
        # htf_slice_volumes = htf_volumes[max(0, htf_idx - lookback + 1):htf_idx + 1]
        #
        # if len(htf_slice_closes) >= 200:
        #     htf_ind = calc_htf_indicators(
        #         htf_slice_closes, htf_slice_highs, htf_slice_lows, htf_slice_volumes
        #     )
        # else:
        #     htf_ind = HTFIndicators()
        # ============================================================

        # 벡터화: 사전 계산된 배열에서 인덱스로 접근
        osc_data = get_osc_data_at_index(spo_arrays, sig_arrays, closes, i)

        # HTF 지표 (비율로 매핑)
        htf_idx = min(int(i * htf_ratio), len(htf_candles) - 1)
        htf_ind = get_htf_indicators_at_index(htf_arrays, htf_idx)

        # 국면 판별
        regime = detect_regime(htf_ind, config.use_4regime)
        state.current_regime = regime

        # 신호 생성
        # 슬라이스 데이터는 여전히 generate_mr_signal에 필요 (breakout 조건 등)
        slice_closes = closes[max(0, i - 10):i + 1]  # 최소한의 슬라이스만 (10봉)
        slice_highs = highs[max(0, i - 10):i + 1]
        slice_lows = lows[max(0, i - 10):i + 1]

        signal, state = generate_mr_signal(
            close=slice_closes,
            high=slice_highs,
            low=slice_lows,
            osc_data=osc_data,
            htf_indicators=htf_ind,
            regime=regime,
            state=state,
            config=config,
            has_position=position.quantity > 0,
            position_qty=position.quantity,
            avg_price=position.avg_price if position.quantity > 0 else None,
            current_ts=candle.ts,
        )

        if signal.action != "none":
            signals.append({
                "bar_index": i,
                "timestamp": candle.ts,
                "action": signal.action,
                "reason_code": signal.reason_code,
                "regime": signal.regime,
                "tranche_pct": signal.tranche_pct,
            })

            # 거래 실행
            if signal.action == "buy" and capital > 0:
                # 매수: 현금의 tranche_pct만큼 사용
                use_pct = signal.tranche_pct / 100.0
                use_amount = capital * use_pct * (config.cash_use_pct / 100.0)
                use_amount = min(use_amount, capital)

                if use_amount > 0:
                    fee = use_amount * fee_rate
                    net_amount = use_amount - fee
                    qty = net_amount / price

                    position.add(qty, price)
                    capital -= use_amount

                    trades.append(BacktestTrade(
                        bar_index=i,
                        timestamp=candle.ts,
                        action="buy",
                        price=price,
                        quantity=qty,
                        tranche=state.buy_stage,
                        reason_code=signal.reason_code,
                    ))

            elif signal.action == "sell" and position.quantity > 0:
                # 매도: 포지션의 tranche_pct만큼 청산
                sell_pct = signal.tranche_pct / 100.0
                sell_qty = position.quantity * sell_pct

                if sell_qty > 0:
                    pnl = position.remove(sell_qty, price)
                    proceeds = sell_qty * price
                    fee = proceeds * fee_rate
                    net_proceeds = proceeds - fee
                    pnl -= fee  # 수수료 차감

                    capital += net_proceeds
                    pnl_pct = (price - position.avg_price) / position.avg_price * 100 if position.avg_price > 0 else 0

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

    # 마지막 포지션 정리
    if position.quantity > 0:
        last_price = candles[-1].c
        last_qty = position.quantity
        pnl = position.remove(last_qty, last_price)
        proceeds = last_qty * last_price
        fee = proceeds * fee_rate
        capital += proceeds - fee

    # 최종 자산
    final_equity = capital

    # 최종 equity_curve 업데이트 (마지막 포지션 청산 반영)
    if equity_curve:
        last_candle = candles[-1]
        equity_curve.append({
            "bar_index": len(candles) - 1,
            "timestamp": last_candle.ts,
            "equity": final_equity,
            "position_qty": 0,
            "position_value": 0,
            "cash": final_equity,
        })

    # 성과 지표 계산
    metrics = calculate_metrics(
        equity_curve=equity_curve,
        trades=trades,
        initial_capital=initial_capital,
        final_equity=final_equity,
    )

    return BacktestResult(
        success=True,
        message=f"백테스트 완료: {len(candles)}봉, {len(trades)}거래",
        metrics=metrics,
        equity_curve=equity_curve,
        trades=trades,
        signals=signals,
    )


def calculate_metrics(
    equity_curve: List[Dict[str, Any]],
    trades: List[BacktestTrade],
    initial_capital: float,
    final_equity: float,
) -> BacktestMetrics:
    """성과 지표 계산"""
    metrics = BacktestMetrics()

    if not equity_curve:
        return metrics

    # 총 수익률
    metrics.total_return_pct = (final_equity - initial_capital) / initial_capital * 100

    # CAGR (연환산 수익률)
    days = len(equity_curve)
    years = days / 365
    if years > 0 and final_equity > 0 and initial_capital > 0:
        metrics.cagr_pct = ((final_equity / initial_capital) ** (1 / years) - 1) * 100

    # MDD (최대 낙폭)
    peak = initial_capital
    max_dd = 0
    for point in equity_curve:
        eq = point["equity"]
        peak = max(peak, eq)
        dd = (peak - eq) / peak * 100 if peak > 0 else 0
        max_dd = max(max_dd, dd)
    metrics.max_drawdown_pct = -max_dd

    # 샤프 비율
    if len(equity_curve) > 1:
        returns = []
        for i in range(1, len(equity_curve)):
            prev_eq = equity_curve[i - 1]["equity"]
            curr_eq = equity_curve[i]["equity"]
            if prev_eq > 0:
                returns.append((curr_eq - prev_eq) / prev_eq)

        if returns:
            avg_ret = sum(returns) / len(returns)
            std_ret = math.sqrt(sum((r - avg_ret) ** 2 for r in returns) / len(returns))
            if std_ret > 0:
                metrics.sharpe_ratio = avg_ret / std_ret * math.sqrt(252)

    # 거래 통계
    sell_trades = [t for t in trades if t.action == "sell" and t.pnl is not None]
    metrics.total_trades = len(sell_trades)

    if sell_trades:
        wins = [t for t in sell_trades if t.pnl > 0]
        losses = [t for t in sell_trades if t.pnl <= 0]

        metrics.winning_trades = len(wins)
        metrics.losing_trades = len(losses)
        metrics.win_rate_pct = len(wins) / len(sell_trades) * 100

        if wins:
            total_win = sum(t.pnl for t in wins)
            metrics.avg_win_pct = (total_win / len(wins)) / initial_capital * 100

        if losses:
            total_loss = sum(t.pnl for t in losses)
            metrics.avg_loss_pct = (total_loss / len(losses)) / initial_capital * 100

        # Profit Factor
        total_wins = sum(t.pnl for t in wins) if wins else 0
        total_losses = abs(sum(t.pnl for t in losses)) if losses else 0
        if total_losses > 0:
            metrics.profit_factor = total_wins / total_losses

        # 연속 승/패
        current_streak = 0
        max_win_streak = 0
        max_loss_streak = 0
        last_was_win = None

        for t in sell_trades:
            is_win = t.pnl > 0
            if last_was_win is None or is_win == last_was_win:
                current_streak += 1
            else:
                current_streak = 1

            if is_win:
                max_win_streak = max(max_win_streak, current_streak)
            else:
                max_loss_streak = max(max_loss_streak, current_streak)

            last_was_win = is_win

        metrics.max_consecutive_wins = max_win_streak
        metrics.max_consecutive_losses = max_loss_streak

    return metrics


def generate_sample_candles(
    days: int = 365,
    base_price: float = 50000.0,
    volatility: float = 0.02,
    trend: float = 0.0001,
    seed: int = 42,
) -> List[Candle]:
    """
    백테스트용 샘플 캔들 데이터 생성 (더미 데이터)

    실제 운영에서는 candle_fetcher를 사용해야 함
    """
    import random
    random.seed(seed)

    candles = []
    price = base_price
    ts = int(datetime(2023, 1, 1, tzinfo=timezone.utc).timestamp() * 1000)

    for i in range(days * 24):  # 1시간봉 기준
        # 가격 변동
        change = (random.random() - 0.5 + trend) * volatility * price
        open_price = price
        price = max(price + change, price * 0.5)

        high = max(open_price, price) * (1 + random.random() * volatility * 0.5)
        low = min(open_price, price) * (1 - random.random() * volatility * 0.5)
        volume = random.uniform(100, 10000)

        candles.append(Candle(
            ts=ts,
            o=open_price,
            h=high,
            l=low,
            c=price,
            v=volume,
        ))

        ts += 3600 * 1000  # 1시간 증가

    return candles

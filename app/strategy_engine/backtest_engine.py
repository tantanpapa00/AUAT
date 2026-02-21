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
from .signal_generator import generate_mr_signal, calc_osc_data, update_state_after_execution
from .presets import OSC_PRESETS, HTF_DEFAULTS


# ============================================================
# 벡터화 사전 계산 함수들
# ============================================================

def precompute_spo_arrays(
    closes: np.ndarray,
    preset: str = "preset1",
    custom_smooth_len: Optional[int] = None,
    custom_threshold: Optional[float] = None,
) -> Dict[str, np.ndarray]:
    """
    전체 시리즈에서 SPO 지표를 한 번에 계산.

    Args:
        closes: 종가 배열
        preset: 프리셋 이름 ("preset1", "preset2", "custom")
        custom_smooth_len: custom 프리셋일 때 사용할 smooth_len
        custom_threshold: custom 프리셋일 때 사용할 threshold

    Returns:
        Dict with normalized_osc, upper_band, lower_band, basis, line_short, line_long arrays
    """
    # custom 프리셋이면 사용자 지정 값 사용, 아니면 프리셋 값
    if preset == "custom" and custom_smooth_len is not None:
        params = OSC_PRESETS.get("preset1", OSC_PRESETS["preset1"]).copy()
        params["smooth_len"] = custom_smooth_len
        if custom_threshold is not None:
            params["threshold"] = custom_threshold
    else:
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


def build_htf_index_map(
    signal_candles: List,
    htf_candles: List,
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
    ichimoku_result = calc_ichimoku(
        htf_highs, htf_lows, htf_closes,
        HTF_DEFAULTS["ichi_tenkan"],
        HTF_DEFAULTS["ichi_kijun"],
        HTF_DEFAULTS["ichi_senkou"],
    )
    tenkan = ichimoku_result["tenkan"]
    kijun = ichimoku_result["kijun"]
    senkou_a = ichimoku_result["senkou_a"]
    senkou_b = ichimoku_result["senkou_b"]

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
    commission: float = 0.0  # 이 거래의 수수료


@dataclass
class BacktestMetrics:
    """백테스트 성과 지표 (트레이딩뷰 동일 구조)"""
    # 기본
    initial_capital: float = 0.0
    final_capital: float = 0.0
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

    # 트레이딩뷰 추가 필드
    net_profit: float = 0.0           # 순손익 금액
    net_profit_pct: float = 0.0       # 순손익 %
    gross_profit: float = 0.0         # 총수익 금액
    gross_profit_pct: float = 0.0     # 총수익 %
    gross_loss: float = 0.0           # 총손실 금액 (양수로)
    gross_loss_pct: float = 0.0       # 총손실 %
    max_drawdown: float = 0.0         # 최대 자본 감소 금액
    commission_paid: float = 0.0      # 지불된 수수료 총액
    expected_value: float = 0.0       # 기대수익 (순손익 / 총거래)
    unrealized_pnl: float = 0.0       # 미실현 손익 금액
    unrealized_pnl_pct: float = 0.0   # 미실현 손익 %

    # 매수/매도 분리 통계
    buy_net_profit: float = 0.0
    buy_net_profit_pct: float = 0.0
    buy_gross_profit: float = 0.0
    buy_gross_profit_pct: float = 0.0
    buy_gross_loss: float = 0.0
    buy_gross_loss_pct: float = 0.0
    buy_profit_factor: float = 0.0
    buy_commission: float = 0.0
    buy_expected_value: float = 0.0
    buy_trades: int = 0
    buy_winning: int = 0
    buy_losing: int = 0

    sell_net_profit: float = 0.0      # 역추세는 0
    sell_net_profit_pct: float = 0.0
    sell_gross_profit: float = 0.0
    sell_gross_profit_pct: float = 0.0
    sell_gross_loss: float = 0.0
    sell_gross_loss_pct: float = 0.0
    sell_profit_factor: float = 0.0
    sell_commission: float = 0.0
    sell_expected_value: float = 0.0
    sell_trades: int = 0
    sell_winning: int = 0
    sell_losing: int = 0


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
    fee_rate: float = 0.0,  # PineScript 동일: 0% 수수료 (트레이딩뷰 기본값)
    debug: bool = False,  # 디버그 로깅 활성화
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
    # 기본 설정
    if config is None:
        config = MRConfig()

    # 지표별 최소 필요 봉 수 계산
    # 핵심 신호(sig_up_raw)에 필요한 지표:
    # - smoother_F(close, smooth_len*2): EMA warmup ~40봉 (smooth=20) 또는 ~8봉 (smooth=4)
    # - ta.stdev(oscillator, 50): 50봉
    # - ta.highest(stdev_osc, 50): 50봉
    # - ta.hma(osc, 30): 30봉
    # - HTF VWMA200: 200봉 (가장 긴 지표)

    osc_preset = config.osc_preset
    smooth_len = config.osc_smooth_len if osc_preset == "custom" else (20 if osc_preset == "preset1" else 14)

    # 신호 생성에 필요한 봉 수: OSC(~60봉) vs HTF VWMA(200봉)
    osc_warmup = max(smooth_len * 2, 50, 30) + 10  # OSC 지표 + 여유
    htf_warmup = 200  # HTF VWMA200이 가장 긴 지표

    required_bars = max(osc_warmup, htf_warmup, 100)  # = 200봉

    if len(candles) < required_bars:
        return BacktestResult(
            success=False,
            message=f"시세 데이터가 부족합니다: {len(candles)}봉 (최소 {required_bars}봉 필요). 기간을 늘리거나 타임프레임을 변경해보세요.",
            metrics=BacktestMetrics(),
        )

    if htf_candles is None:
        htf_candles = candles

    # 상태 초기화
    state = StrategyState()
    position = Position()
    capital = initial_capital
    total_commission = 0.0  # 수수료 누적

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
    spo_arrays = precompute_spo_arrays(
        closes,
        config.osc_preset,
        custom_smooth_len=config.osc_smooth_len if config.osc_preset == "custom" else None,
        custom_threshold=config.osc_threshold if config.osc_preset == "custom" else None,
    )

    # 2. 신호 배열 사전 계산 (sig_up_raw, sig_dn_raw)
    sig_arrays = precompute_signal_arrays(
        spo_arrays["normalized_osc"],
        spo_arrays["threshold"]
    )

    # 디버그: sig_up_raw 통계
    if debug:
        sig_up_count = np.sum(sig_arrays["sig_up_raw"])
        sig_dn_count = np.sum(sig_arrays["sig_dn_raw"])
        print(f"[DEBUG] 전체 봉 수: {len(candles)}")
        print(f"[DEBUG] sig_up_raw=True 봉: {sig_up_count}개")
        print(f"[DEBUG] sig_dn_raw=True 봉: {sig_dn_count}개")
        print(f"[DEBUG] threshold: {spo_arrays['threshold']}")

        # warmup 기간의 신호 확인
        lookback_val = min(required_bars, len(candles) - 1)
        warmup_sig_up = np.sum(sig_arrays["sig_up_raw"][:lookback_val])
        active_sig_up = np.sum(sig_arrays["sig_up_raw"][lookback_val:])
        print(f"[DEBUG] warmup 기간(0~{lookback_val-1}) sig_up: {warmup_sig_up}개 (스킵됨)")
        print(f"[DEBUG] 활성 기간({lookback_val}~{len(candles)-1}) sig_up: {active_sig_up}개")

    # 3. HTF 지표 사전 계산 (전체 HTF 시리즈에서 한 번만)
    htf_arrays = precompute_htf_arrays(htf_closes, htf_highs, htf_lows, htf_volumes)

    # 4. 타임스탬프 기반 HTF 인덱스 매핑 (request.security 모방)
    htf_idx_map = build_htf_index_map(candles, htf_candles)

    # 각 봉에 대해 시뮬레이션 (동적 계산된 required_bars 사용)
    lookback = min(required_bars, len(candles) - 1)

    for i in range(lookback, len(candles)):
        candle = candles[i]
        price = candle.c

        # 현재 자산 평가
        equity = capital + (position.quantity * price)
        pct = ((equity - initial_capital) / initial_capital) * 100 if initial_capital > 0 else 0.0
        equity_curve.append({
            "bar_index": i,
            "timestamp": candle.ts,
            "equity": equity,
            "pct": round(pct, 2),  # 수익률 %
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

        # 디버그: sig_up_raw=True인 봉에서 lower_band 필터 체크
        if debug and osc_data.sig_up_raw:
            from datetime import datetime as dt
            ts_str = dt.fromtimestamp(candle.ts / 1000).strftime("%Y-%m-%d")
            print(f"[DEBUG] {ts_str} | sig_up=True | osc={osc_data.normalized_osc:.3f} | price={price:.0f}")

        # HTF 지표 (타임스탬프 기반 매핑, request.security 모방)
        htf_idx = htf_idx_map[i]
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

        if debug and osc_data.sig_up_raw and signal.action == "none":
            from datetime import datetime as dt
            ts_str = dt.fromtimestamp(candle.ts / 1000).strftime("%Y-%m-%d")
            print(f"[DEBUG] {ts_str} | sig_up=True BUT action=none | reason={signal.reason_code} | regime={regime}")

        if signal.action != "none":
            signals.append({
                "bar_index": i,
                "timestamp": candle.ts,
                "action": signal.action,
                "reason_code": signal.reason_code,
                "regime": signal.regime,
                "tranche_pct": signal.tranche_pct,
            })
            if debug:
                from datetime import datetime as dt
                ts_str = dt.fromtimestamp(candle.ts / 1000).strftime("%Y-%m-%d")
                print(f"[DEBUG] {ts_str} | ACTION={signal.action.upper()} | reason={signal.reason_code} | regime={regime} | price={price:.0f}")

            # 거래 실행
            if signal.action == "buy" and capital > 0:
                # 매수: 현금의 tranche_pct만큼 사용
                use_pct = signal.tranche_pct / 100.0
                use_amount = capital * use_pct * (config.cash_use_pct / 100.0)
                use_amount = min(use_amount, capital)

                if use_amount > 0:
                    fee = use_amount * fee_rate
                    total_commission += fee  # 수수료 누적
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
                        commission=fee,  # 이 거래의 수수료
                    ))

                    # 매수 후 state 업데이트 (last_buy_exec_price, buy_stage 등)
                    state = update_state_after_execution(state, signal, config, executed=True)

            elif signal.action == "sell" and position.quantity > 0:
                # 매도: 포지션의 tranche_pct만큼 청산
                sell_pct = signal.tranche_pct / 100.0
                sell_qty = position.quantity * sell_pct

                if sell_qty > 0:
                    avg_price_before = position.avg_price  # 매도 전 평균단가 저장
                    pnl = position.remove(sell_qty, price)
                    proceeds = sell_qty * price
                    fee = proceeds * fee_rate
                    total_commission += fee  # 수수료 누적
                    net_proceeds = proceeds - fee
                    pnl -= fee  # 수수료 차감

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
                        commission=fee,  # 이 거래의 수수료
                    ))

                    # 매도 후 state 업데이트 (sell_stage, buy_stage 리셋 등)
                    state = update_state_after_execution(state, signal, config, executed=True)

    # 미실현 손익 계산 (포지션 강제 청산 전)
    unrealized_pnl = 0.0
    unrealized_pnl_pct = 0.0
    if position.quantity > 0:
        last_price = candles[-1].c
        # 미실현 PnL = (현재가 - 평균단가) * 수량 - 예상 매도 수수료
        estimated_sell_fee = position.quantity * last_price * fee_rate
        unrealized_pnl = (last_price - position.avg_price) * position.quantity - estimated_sell_fee
        unrealized_pnl_pct = (unrealized_pnl / initial_capital) * 100 if initial_capital > 0 else 0

    # 마지막 포지션 정리 (백테스트 종료 시 강제 청산)
    if position.quantity > 0:
        last_price = candles[-1].c
        last_qty = position.quantity
        pnl = position.remove(last_qty, last_price)
        proceeds = last_qty * last_price
        fee = proceeds * fee_rate
        total_commission += fee  # 수수료 누적
        capital += proceeds - fee

    # 최종 자산
    final_equity = capital

    # 최종 equity_curve 업데이트 (마지막 포지션 청산 반영)
    if equity_curve:
        last_candle = candles[-1]
        final_pct = ((final_equity - initial_capital) / initial_capital) * 100 if initial_capital > 0 else 0.0
        equity_curve.append({
            "bar_index": len(candles) - 1,
            "timestamp": last_candle.ts,
            "equity": final_equity,
            "pct": round(final_pct, 2),  # 수익률 %
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
        total_commission=total_commission,
        unrealized_pnl=unrealized_pnl,
        unrealized_pnl_pct=unrealized_pnl_pct,
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
    total_commission: float = 0.0,
    unrealized_pnl: float = 0.0,
    unrealized_pnl_pct: float = 0.0,
) -> BacktestMetrics:
    """성과 지표 계산 (트레이딩뷰 동일 구조)"""
    metrics = BacktestMetrics()

    # 기본 자본 정보
    metrics.initial_capital = initial_capital
    metrics.final_capital = final_equity

    if not equity_curve:
        return metrics

    # === 기본 메트릭 ===
    # 총 수익률
    metrics.total_return_pct = (final_equity - initial_capital) / initial_capital * 100 if initial_capital > 0 else 0

    # CAGR (연환산 수익률)
    days = len(equity_curve)
    years = days / 365
    if years > 0 and final_equity > 0 and initial_capital > 0:
        metrics.cagr_pct = ((final_equity / initial_capital) ** (1 / years) - 1) * 100

    # MDD (최대 낙폭)
    peak = initial_capital
    max_dd = 0
    max_dd_amount = 0
    for point in equity_curve:
        eq = point["equity"]
        peak = max(peak, eq)
        dd = (peak - eq) / peak * 100 if peak > 0 else 0
        dd_amount = peak - eq
        if dd > max_dd:
            max_dd = dd
            max_dd_amount = dd_amount
    metrics.max_drawdown_pct = -max_dd
    metrics.max_drawdown = -max_dd_amount

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

    # === 수수료 & 미실현 손익 ===
    metrics.commission_paid = total_commission
    metrics.unrealized_pnl = unrealized_pnl
    metrics.unrealized_pnl_pct = unrealized_pnl_pct

    # === 거래 통계 ===
    sell_trades = [t for t in trades if t.action == "sell" and t.pnl is not None]
    buy_trades = [t for t in trades if t.action == "buy"]
    metrics.total_trades = len(sell_trades)

    # 총수익 / 총손실 계산
    wins = [t for t in sell_trades if t.pnl > 0]
    losses = [t for t in sell_trades if t.pnl <= 0]

    gross_profit = sum(t.pnl for t in wins) if wins else 0
    gross_loss = abs(sum(t.pnl for t in losses)) if losses else 0
    net_profit = gross_profit - gross_loss

    metrics.gross_profit = gross_profit
    metrics.gross_profit_pct = (gross_profit / initial_capital) * 100 if initial_capital > 0 else 0
    metrics.gross_loss = gross_loss
    metrics.gross_loss_pct = (gross_loss / initial_capital) * 100 if initial_capital > 0 else 0
    metrics.net_profit = net_profit
    metrics.net_profit_pct = (net_profit / initial_capital) * 100 if initial_capital > 0 else 0

    # 승/패 통계
    metrics.winning_trades = len(wins)
    metrics.losing_trades = len(losses)
    metrics.win_rate_pct = len(wins) / len(sell_trades) * 100 if sell_trades else 0

    if wins:
        total_win = sum(t.pnl for t in wins)
        metrics.avg_win_pct = (total_win / len(wins)) / initial_capital * 100

    if losses:
        total_loss = sum(t.pnl for t in losses)
        metrics.avg_loss_pct = (total_loss / len(losses)) / initial_capital * 100

    # Profit Factor
    if gross_loss > 0:
        metrics.profit_factor = gross_profit / gross_loss
    elif gross_profit > 0:
        metrics.profit_factor = float('inf')

    # 기대수익
    if sell_trades:
        metrics.expected_value = net_profit / len(sell_trades)

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

    # === 매수/매도 분리 통계 ===
    # 역추세 매매에서 매수는 "진입", 매도는 "청산"
    # 손익은 매도 시점에 계산됨 → 모든 손익은 "매수 포지션"의 손익
    # 따라서 buy_* 에 전체 통계를 넣고, sell_* 은 0으로

    # 매수 수수료 계산
    buy_commission = sum(t.commission for t in buy_trades)
    sell_commission = sum(t.commission for t in sell_trades)

    metrics.buy_trades = len(sell_trades)  # 매수 포지션 = 청산(매도) 건수
    metrics.buy_winning = len(wins)
    metrics.buy_losing = len(losses)
    metrics.buy_gross_profit = gross_profit
    metrics.buy_gross_profit_pct = metrics.gross_profit_pct
    metrics.buy_gross_loss = gross_loss
    metrics.buy_gross_loss_pct = metrics.gross_loss_pct
    metrics.buy_net_profit = net_profit
    metrics.buy_net_profit_pct = metrics.net_profit_pct
    metrics.buy_profit_factor = metrics.profit_factor
    metrics.buy_commission = buy_commission + sell_commission  # 매수+매도 수수료 합
    metrics.buy_expected_value = metrics.expected_value

    # 매도 분리 (역추세에서는 공매도 없음)
    metrics.sell_trades = 0
    metrics.sell_winning = 0
    metrics.sell_losing = 0
    metrics.sell_gross_profit = 0
    metrics.sell_gross_profit_pct = 0
    metrics.sell_gross_loss = 0
    metrics.sell_gross_loss_pct = 0
    metrics.sell_net_profit = 0
    metrics.sell_net_profit_pct = 0
    metrics.sell_profit_factor = 0
    metrics.sell_commission = 0
    metrics.sell_expected_value = 0

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

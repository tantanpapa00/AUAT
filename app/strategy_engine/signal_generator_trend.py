# app/strategy_engine/signal_generator_trend.py
"""
Trend Strategy Signal Generator (Stock Trend Auto v7).

추세매매 엔진 - 파인스크립트 1:1 재구현.

Entry: Supertrend 상승 AND HVI 초록 AND QQE 양수 AND close > HTF VWMA156
Exit: Hard SL > TP1 > SPO Split > ST Flip (우선순위순)
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional, List, Tuple
import numpy as np

from .models import SignalResult


@dataclass
class TrendConfig:
    """추세매매 설정 (premium_configs에서 로드)"""

    # 타임프레임 분리 (핵심!)
    entry_tf: str = "1D"      # 매수 판단 타임프레임
    exit_tf: str = "1D"       # 매도 판단 타임프레임
    htf_tf: str = "1W"        # HTF VWMA 기준 타임프레임

    # Entry 지표 (entry_tf 기준)
    st_atr_len: int = 20
    st_factor: float = 5.0
    hvi_length: int = 200
    hvi_divisor: float = 3.6
    qqe_rsi_length: int = 6
    qqe_rsi_smoothing: int = 5
    qqe_factor: float = 3.0
    htf_vwma_len: int = 156   # HTF VWMA 길이

    # Exit 지표 (exit_tf 기준)
    exit_st_atr_len: int = 20
    exit_st_factor: float = 5.0
    exit_spo_smooth_len: int = 4
    exit_spo_threshold: float = 1.0
    exit_spo_std_len: int = 50
    exit_spo_hma_len: int = 30

    # Exit 조건
    hard_sl_pct: float = 7.0          # 하드 손절 %
    tp1_pct: float = 21.0             # TP1 목표 %
    tp1_sell_pct: float = 50.0        # TP1 도달 시 매도 비율 %
    use_spo_split: bool = True        # SPO 분할 매도 사용
    use_st_flip_exit: bool = True     # ST 전환 전량 청산 사용

    # 분할 매도 (SPO Split용) - SELL1~6
    sell_tranches: List[float] = field(default_factory=lambda: [10.0, 20.0, 30.0, 5.0, 2.5, 1.0])
    max_sell_tranches: int = 6
    after_max_sell: str = "cycle"     # extend/cycle/stop

    # 익절 게이트 (분할매도 조건)
    use_profit_gate: bool = True
    min_profit_pct: float = 0.10
    fee_buffer_pct: float = 0.20

    # 현금 사용 비율 (포지션 사이징)
    cash_use_pct: float = 100.0


@dataclass
class TrendState:
    """추세매매 실행 상태"""
    in_position: bool = False
    entry_price: float = 0.0
    entry_ts: int = 0
    position_qty: float = 0.0
    highest_since_entry: float = 0.0  # TP 계산용
    tp1_triggered: bool = False        # TP1 이미 발동 여부
    sell_stage: int = 0                # SPO 분할매도 차수 (0=SELL1, 1=SELL2, ...)
    last_bar_ts: int = 0
    last_st_dir: int = 0               # 마지막 Supertrend 방향


def generate_trend_signal(
    # Entry 판단용 (entry_tf 캔들로 계산한 지표)
    entry_close: np.ndarray,
    entry_st_dir: np.ndarray,        # Supertrend direction (-1=bullish, 1=bearish)
    entry_hvi: dict,                  # calc_hvi() result
    entry_qqe: dict,                  # calc_qqe_mod() result
    htf_vwma: np.ndarray,             # HTF VWMA(156)

    # Exit 판단용 (exit_tf 캔들로 계산한 지표)
    exit_close: np.ndarray,
    exit_st_dir: np.ndarray,          # Exit TF Supertrend direction
    exit_spo_norm: np.ndarray,        # Normalized SPO oscillator

    # 상태 및 설정
    config: TrendConfig,
    state: TrendState,
    current_ts: int,
) -> Tuple[SignalResult, TrendState]:
    """
    추세매매 신호 생성.

    Entry 조건 (4가지 모두 충족, entry_tf 기준):
    1. Supertrend 상승 (st_dir < 0 = bullish)
    2. HVI 초록 (g_enabled = True)
    3. QQE 양수 (primary_rsi > 50)
    4. close > HTF VWMA(156)

    Exit 우선순위 (exit_tf 기준):
    1. Hard SL: entry_close[-1] <= entry_price * (1 - hard_sl_pct/100)
    2. TP1: exit_close[-1] >= entry_price * (1 + tp1_pct/100)
    3. SPO Split: SPO signal_dn 발생 시 분할 매도
    4. ST Flip: Supertrend 하락 전환 시 전량 청산

    Returns:
        Tuple of (SignalResult, updated TrendState)
    """
    new_state = TrendState(
        in_position=state.in_position,
        entry_price=state.entry_price,
        entry_ts=state.entry_ts,
        position_qty=state.position_qty,
        highest_since_entry=state.highest_since_entry,
        tp1_triggered=state.tp1_triggered,
        sell_stage=state.sell_stage,
        last_bar_ts=state.last_bar_ts,
        last_st_dir=state.last_st_dir,
    )

    # 최신 값 추출
    curr_entry_close = entry_close[-1] if len(entry_close) > 0 else 0.0
    curr_exit_close = exit_close[-1] if len(exit_close) > 0 else 0.0
    curr_entry_st_dir = entry_st_dir[-1] if len(entry_st_dir) > 0 else 1
    curr_exit_st_dir = exit_st_dir[-1] if len(exit_st_dir) > 0 else 1
    prev_exit_st_dir = exit_st_dir[-2] if len(exit_st_dir) > 1 else curr_exit_st_dir

    # HVI/QQE 조건
    hvi_green = entry_hvi.get('g_enabled', np.array([False]))[-1] if len(entry_hvi.get('g_enabled', [])) > 0 else False
    qqe_positive = entry_qqe.get('is_positive', np.array([False]))[-1] if len(entry_qqe.get('is_positive', [])) > 0 else False

    # HTF VWMA 조건
    curr_htf_vwma = htf_vwma[-1] if len(htf_vwma) > 0 and not np.isnan(htf_vwma[-1]) else 0.0

    # SPO 값
    curr_spo = exit_spo_norm[-1] if len(exit_spo_norm) > 0 else 0.0
    prev_spo = exit_spo_norm[-2] if len(exit_spo_norm) > 1 else curr_spo

    # ──────────────────────────────────────────────────────
    # EXIT 로직 (포지션 있을 때만)
    # ──────────────────────────────────────────────────────
    if new_state.in_position:
        # 최고가 업데이트
        if curr_exit_close > new_state.highest_since_entry:
            new_state.highest_since_entry = curr_exit_close

        # Exit 1: Hard Stop Loss (최우선)
        sl_price = new_state.entry_price * (1 - config.hard_sl_pct / 100.0)
        if curr_entry_close <= sl_price:
            new_state.in_position = False
            new_state.entry_price = 0.0
            new_state.tp1_triggered = False
            new_state.sell_stage = 0

            return SignalResult(
                action="sell",
                reason_code="TREND_EXIT_HARD_SL",
                reason_text=f"하드손절 발동: -{config.hard_sl_pct}% 도달",
                tranche_pct=100.0,  # 전량 청산
                regime=0,
            ), new_state

        # Exit 2: TP1 (목표 익절)
        tp1_price = new_state.entry_price * (1 + config.tp1_pct / 100.0)
        if not new_state.tp1_triggered and curr_exit_close >= tp1_price:
            new_state.tp1_triggered = True

            return SignalResult(
                action="sell",
                reason_code="TREND_EXIT_TP1",
                reason_text=f"목표익절(TP1): +{config.tp1_pct}% 도달, {config.tp1_sell_pct}% 청산",
                tranche_pct=config.tp1_sell_pct,
                regime=0,
            ), new_state

        # Exit 3: SPO Split (분할매도)
        if config.use_spo_split:
            # SPO signal_dn: norm_osc > threshold AND crossover(prev, curr) [하락 전환]
            spo_signal_dn = (curr_spo > config.exit_spo_threshold) and (prev_spo > curr_spo)

            if spo_signal_dn:
                # 익절 게이트 체크
                gate_ok = True
                if config.use_profit_gate:
                    need_pct = config.min_profit_pct + config.fee_buffer_pct
                    gate_price = new_state.entry_price * (1 + need_pct / 100.0)
                    gate_ok = curr_exit_close >= gate_price

                if gate_ok:
                    # 분할매도 차수 결정
                    eff_stage = new_state.sell_stage
                    if eff_stage >= config.max_sell_tranches:
                        if config.after_max_sell == "cycle":
                            eff_stage = 0
                        elif config.after_max_sell == "stop":
                            # 더 이상 분할매도 안 함
                            eff_stage = -1
                        else:  # extend
                            eff_stage = config.max_sell_tranches - 1

                    if eff_stage >= 0 and eff_stage < len(config.sell_tranches):
                        sell_pct = config.sell_tranches[eff_stage]

                        # 다음 차수로 이동
                        if config.after_max_sell == "cycle":
                            new_state.sell_stage = (new_state.sell_stage + 1) % config.max_sell_tranches
                        else:
                            new_state.sell_stage = min(new_state.sell_stage + 1, config.max_sell_tranches - 1)

                        return SignalResult(
                            action="sell",
                            reason_code="TREND_EXIT_SPO_SPLIT",
                            reason_text=f"SPO 분할매도: SELL{eff_stage + 1} 실행 ({sell_pct}%)",
                            tranche_pct=sell_pct,
                            regime=0,
                        ), new_state

        # Exit 4: ST Flip (Supertrend 전환)
        if config.use_st_flip_exit:
            # Supertrend 하락 전환: prev < 0 (bullish) -> curr >= 0 (bearish)
            st_bear_flip = (prev_exit_st_dir < 0) and (curr_exit_st_dir >= 0)

            if st_bear_flip:
                new_state.in_position = False
                new_state.entry_price = 0.0
                new_state.tp1_triggered = False
                new_state.sell_stage = 0

                return SignalResult(
                    action="sell",
                    reason_code="TREND_EXIT_ST_FLIP",
                    reason_text="추세전환 전량청산: Supertrend 하락",
                    tranche_pct=100.0,  # 전량 청산
                    regime=0,
                ), new_state

    # ──────────────────────────────────────────────────────
    # ENTRY 로직 (포지션 없을 때만)
    # ──────────────────────────────────────────────────────
    if not new_state.in_position:
        # Entry 조건 4가지
        st_bullish = curr_entry_st_dir < 0  # Supertrend 상승 (PineScript convention)
        htf_ok = curr_entry_close > curr_htf_vwma if curr_htf_vwma > 0 else True

        buy_signal = st_bullish and hvi_green and qqe_positive and htf_ok

        if buy_signal:
            new_state.in_position = True
            new_state.entry_price = curr_entry_close
            new_state.entry_ts = current_ts
            new_state.highest_since_entry = curr_entry_close
            new_state.tp1_triggered = False
            new_state.sell_stage = 0

            return SignalResult(
                action="buy",
                reason_code="TREND_ENTRY_FULL",
                reason_text="추세매매 진입: ST상승+HVI초록+QQE양수+HTF VWMA 상위",
                tranche_pct=config.cash_use_pct,
                regime=0,
            ), new_state

    # ──────────────────────────────────────────────────────
    # 신호 없음
    # ──────────────────────────────────────────────────────
    new_state.last_bar_ts = current_ts
    new_state.last_st_dir = int(curr_entry_st_dir)

    return SignalResult(
        action="hold",
        reason_code="NO_SIGNAL",
        reason_text="",
        tranche_pct=0.0,
        regime=0,
    ), new_state


def check_entry_conditions(
    entry_close: np.ndarray,
    entry_st_dir: np.ndarray,
    entry_hvi: dict,
    entry_qqe: dict,
    htf_vwma: np.ndarray,
) -> dict:
    """
    Entry 조건 개별 체크 (디버깅/UI용).

    Returns:
        dict with each condition status
    """
    curr_close = entry_close[-1] if len(entry_close) > 0 else 0.0
    curr_st_dir = entry_st_dir[-1] if len(entry_st_dir) > 0 else 1
    hvi_green = entry_hvi.get('g_enabled', np.array([False]))[-1] if len(entry_hvi.get('g_enabled', [])) > 0 else False
    qqe_pos = entry_qqe.get('is_positive', np.array([False]))[-1] if len(entry_qqe.get('is_positive', [])) > 0 else False
    curr_htf_vwma = htf_vwma[-1] if len(htf_vwma) > 0 and not np.isnan(htf_vwma[-1]) else 0.0

    return {
        'st_bullish': curr_st_dir < 0,
        'hvi_green': bool(hvi_green),
        'qqe_positive': bool(qqe_pos),
        'htf_ok': curr_close > curr_htf_vwma if curr_htf_vwma > 0 else True,
        'all_conditions_met': (curr_st_dir < 0) and hvi_green and qqe_pos and (curr_close > curr_htf_vwma if curr_htf_vwma > 0 else True),
    }

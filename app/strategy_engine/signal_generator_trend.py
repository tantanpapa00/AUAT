# app/strategy_engine/signal_generator_trend.py
"""
Trend Strategy Signal Generator (Stock Trend Auto v8).

추세매매 엔진 - 파인스크립트 1:1 재구현.

v8 신규 기능:
- 피라미딩 (추가매수)
- ATR 기반 손절
- ST Exit Mode (4가지 모드)
- TP1/SPO 토글
- ST 반전
- HTF 필터 토글
- 진입 가드

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
    """추세매매 설정 (premium_configs에서 로드) - v8 최종"""

    # 타임프레임 (3개)
    signal_tf: str = "1D"     # 기준 TF (매수 + SPO + SL + TP1)
    exit_tf: str = "1W"       # 매도기준 TF (ST 전량매도 전용)
    htf_tf: str = "1W"        # 상위기준 TF (HTF VWMA 필터 전용)

    # 슈퍼트렌드 (작가님 확정: 20/5.0)
    st_atr_len: int = 20      # ATR 길이
    st_factor: float = 5.0    # 팩터
    hvi_length: int = 200
    hvi_divisor: float = 3.6
    qqe_rsi_length: int = 6
    qqe_rsi_smoothing: int = 5
    qqe_factor: float = 3.0
    htf_vwma_len: int = 156   # HTF VWMA 길이 (exit_tf에서 계산)

    # Exit 지표 (signal_tf 기준 SPO용)
    exit_spo_smooth_len: int = 4
    exit_spo_threshold: float = 1.0
    exit_spo_std_len: int = 50
    exit_spo_hma_len: int = 30

    # Exit 조건
    hard_sl_pct: float = 7.0          # 하드 손절 %
    tp1_pct: float = 21.0             # TP1 목표 %
    tp1_sell_pct: float = 50.0        # TP1 도달 시 매도 비율 % (최소 50%)
    use_spo_split: bool = True        # SPO 분할 매도 사용 (useSPO)
    use_st_flip_exit: bool = True     # ST 전환 전량 청산 사용

    # 분할 매도 (SPO Split용) - SELL1~6 (v8: 역피라미드 기본값)
    sell_tranches: List[float] = field(default_factory=lambda: [5.0, 5.0, 10.0, 15.0, 25.0, 40.0])
    max_sell_tranches: int = 6
    after_max_sell: str = "cycle"     # extend/cycle/stop

    # 익절 게이트 (분할매도 조건)
    use_profit_gate: bool = True
    min_profit_pct: float = 0.10
    fee_buffer_pct: float = 0.20

    # 현금 사용 비율 (포지션 사이징)
    cash_use_pct: float = 100.0

    # ============================================================
    # v8 신규 필드
    # ============================================================

    # 피라미딩 (추가매수)
    use_pyramiding: bool = True          # 피라미딩 사용 여부
    max_pyr_entries: int = 4             # 1차 포함 최대 진입 횟수 (1~10)
    pyr_high_len: int = 60               # N봉 신고가 돌파 기준
    pyr_cooldown: int = 5                # 추가매수 최소 봉 간격
    pyr_refill_after_sell: bool = False  # 매도 후 pyrCount 감소 허용
    pyr_weights: List[float] = field(default_factory=lambda: [40.0, 30.0, 20.0, 10.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0])

    # 손절 방식
    stop_type: str = "fixed"             # "fixed" (고정%) | "atr" (ATR 기반)
    atr_stop_len: int = 14               # ATR 손절용 ATR 길이
    atr_stop_mult: float = 2.0           # ATR 손절 배수

    # ST 전량매도 (exit_tf의 ST 사용)
    use_st_exit: bool = True             # ST 하락 전환 시 전량매도

    # TP1 토글 (v8에서 기본 OFF)
    use_tp1: bool = False                # TP1 사용 여부 (v7에서는 항상 ON이었음!)

    # ST 반전
    st_invert: bool = False              # Supertrend 방향 반전

    # HTF 필터 토글
    use_htf_filter: bool = True          # HTF VWMA 필터 사용 여부
    htf_mode: str = "auto"               # "auto" | "manual"
    manual_htf_type: str = "VWMA"        # "VWMA" | "SMA" | "EMA"

    # 진입 가드
    enter_only_on_setup_start: bool = True   # 셋업 시작 첫봉에서만 진입
    use_live_guard: bool = True              # 실전 가드 (늦은 진입 방지)

    # 자산 유형
    asset_type: str = "stock"            # "stock" | "crypto" (HTF 자동 결정용)

    # 수량 옵션
    round_qty: bool = True               # 정수 수량 (주식용)
    min_qty: float = 1.0                 # 최소 수량


@dataclass
class TrendState:
    """추세매매 실행 상태 - v8"""
    in_position: bool = False
    entry_price: float = 0.0
    entry_ts: int = 0
    position_qty: float = 0.0
    highest_since_entry: float = 0.0  # TP 계산용
    tp1_triggered: bool = False        # TP1 이미 발동 여부
    sell_stage: int = 0                # SPO 분할매도 차수 (0=SELL1, 1=SELL2, ...)
    last_bar_ts: int = 0
    last_st_dir: int = 0               # 마지막 Supertrend 방향

    # ============================================================
    # v8 신규 필드 - 피라미딩
    # ============================================================
    pyr_count: int = 0                 # 현재 진입 횟수 (1차 진입 포함)
    last_pyr_bar: int = -999           # 마지막 피라미딩 봉 인덱스
    pyr_highest: float = 0.0           # 포지션 보유 중 N봉 신고가 추적용
    total_cost: float = 0.0            # 피라미딩 평균단가 계산용 (총 투입금액)
    avg_entry_price: float = 0.0       # 피라미딩 평균 진입가

    # 진입 가드
    setup_start_bar: int = -999        # 셋업 시작 봉 인덱스
    prev_setup_met: bool = False       # 이전 봉 셋업 충족 여부


def generate_trend_signal(
    # 기준 TF 데이터 (signal_tf 캔들로 계산한 지표)
    entry_close: np.ndarray,          # signal_tf close
    entry_st_dir: np.ndarray,         # signal_tf Supertrend direction (-1=bullish, 1=bearish)
    entry_hvi: dict,                  # calc_hvi() result
    entry_qqe: dict,                  # calc_qqe_mod() result
    htf_vwma: np.ndarray,             # exit_tf VWMA (HTF 필터)

    # 매도기준 TF 데이터 (exit_tf 캔들로 계산한 지표)
    exit_close: np.ndarray,           # exit_tf close
    exit_st_dir: np.ndarray,          # exit_tf Supertrend direction (전량매도용)
    exit_spo_norm: np.ndarray,        # signal_tf SPO oscillator (분할매도용)

    # 상태 및 설정
    config: TrendConfig,
    state: TrendState,
    current_ts: int,

    # 추가 파라미터
    entry_atr: Optional[np.ndarray] = None,    # ATR 값 (ATR 손절용)
    entry_high: Optional[np.ndarray] = None,   # high 배열 (피라미딩 N봉 신고가용)
    bar_index: int = 0,                        # 현재 봉 인덱스 (피라미딩 쿨다운용)
) -> Tuple[SignalResult, TrendState]:
    """
    추세매매 신호 생성 (v8 최종).

    TF 구조 (단순화):
    - signal_tf: 기준 TF (매수 + SPO 분할매도 + SL + TP1)
    - exit_tf: 매도기준 TF (ST 전량매도 + HTF VWMA 필터)

    Entry 조건 (4가지 모두 충족, signal_tf 기준):
    1. Supertrend 상승 (st_dir < 0 = bullish)
    2. HVI 초록 (g_enabled = True)
    3. QQE 양수 (primary_rsi > 50)
    4. close > exit_tf VWMA - use_htf_filter=False면 스킵

    Exit 우선순위:
    1. Hard SL: Fixed% 또는 ATR-based (signal_tf 기준)
    2. TP1: use_tp1=True일 때만
    3. SPO Split: use_spo_split=True일 때만 (signal_tf 기준)
    4. ST Flip: use_st_exit=True일 때 exit_tf ST 하락 전환

    피라미딩 (v8):
    - 포지션 보유 중 N봉 신고가 돌파 시 추가매수
    - 최대 max_pyr_entries회까지

    Returns:
        Tuple of (SignalResult, updated TrendState)
    """
    # 상태 복사 (모든 필드 포함)
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
        # v8 필드
        pyr_count=state.pyr_count,
        last_pyr_bar=state.last_pyr_bar,
        pyr_highest=state.pyr_highest,
        total_cost=state.total_cost,
        avg_entry_price=state.avg_entry_price,
        setup_start_bar=state.setup_start_bar,
        prev_setup_met=state.prev_setup_met,
    )

    # 최신 값 추출
    curr_entry_close = entry_close[-1] if len(entry_close) > 0 else 0.0
    curr_exit_close = exit_close[-1] if len(exit_close) > 0 else 0.0
    curr_entry_st_dir = entry_st_dir[-1] if len(entry_st_dir) > 0 else 1
    curr_exit_st_dir = exit_st_dir[-1] if len(exit_st_dir) > 0 else 1
    prev_exit_st_dir = exit_st_dir[-2] if len(exit_st_dir) > 1 else curr_exit_st_dir

    # ATR 값 (v8)
    curr_atr = entry_atr[-1] if entry_atr is not None and len(entry_atr) > 0 and not np.isnan(entry_atr[-1]) else 0.0

    # ST 반전 적용 (v8)
    if config.st_invert:
        curr_entry_st_dir = -curr_entry_st_dir
        curr_exit_st_dir = -curr_exit_st_dir
        prev_exit_st_dir = -prev_exit_st_dir

    # HVI/QQE 조건
    hvi_green = entry_hvi.get('g_enabled', np.array([False]))[-1] if len(entry_hvi.get('g_enabled', [])) > 0 else False
    qqe_positive = entry_qqe.get('is_positive', np.array([False]))[-1] if len(entry_qqe.get('is_positive', [])) > 0 else False

    # HTF VWMA 조건
    curr_htf_vwma = htf_vwma[-1] if len(htf_vwma) > 0 and not np.isnan(htf_vwma[-1]) else 0.0

    # SPO 값
    curr_spo = exit_spo_norm[-1] if len(exit_spo_norm) > 0 else 0.0
    prev_spo = exit_spo_norm[-2] if len(exit_spo_norm) > 1 else curr_spo

    # N봉 신고가 계산 (피라미딩용, v8)
    pyr_high_threshold = 0.0
    if entry_high is not None and len(entry_high) >= config.pyr_high_len:
        pyr_high_threshold = np.max(entry_high[-config.pyr_high_len:-1]) if len(entry_high) > 1 else entry_high[-1]

    # 손절 가격 계산 (v8: Fixed% 또는 ATR-based)
    if config.stop_type == "atr" and curr_atr > 0:
        # 피라미딩 시 평균단가 기준
        base_price = new_state.avg_entry_price if new_state.avg_entry_price > 0 else new_state.entry_price
        sl_price = base_price - (curr_atr * config.atr_stop_mult)
        sl_reason = f"ATR손절 발동: ATR({config.atr_stop_len})×{config.atr_stop_mult}"
        sl_code = "TREND_EXIT_ATR_SL"
    else:
        base_price = new_state.avg_entry_price if new_state.avg_entry_price > 0 else new_state.entry_price
        sl_price = base_price * (1 - config.hard_sl_pct / 100.0)
        sl_reason = f"하드손절 발동: -{config.hard_sl_pct}% 도달"
        sl_code = "TREND_EXIT_HARD_SL"

    # ──────────────────────────────────────────────────────
    # EXIT 로직 (포지션 있을 때만)
    # ──────────────────────────────────────────────────────
    if new_state.in_position:
        # 최고가 업데이트
        if curr_exit_close > new_state.highest_since_entry:
            new_state.highest_since_entry = curr_exit_close

        # Exit 1: Hard Stop Loss (최우선) - Fixed% 또는 ATR-based
        if curr_entry_close <= sl_price and base_price > 0:
            # 상태 리셋
            new_state.in_position = False
            new_state.entry_price = 0.0
            new_state.tp1_triggered = False
            new_state.sell_stage = 0
            new_state.pyr_count = 0
            new_state.avg_entry_price = 0.0
            new_state.total_cost = 0.0

            return SignalResult(
                action="sell",
                reason_code=sl_code,
                reason_text=sl_reason,
                tranche_pct=100.0,  # 전량 청산
                regime=0,
            ), new_state

        # Exit 2: TP1 (목표 익절) - use_tp1=True일 때만 (v8)
        if config.use_tp1:
            tp1_base = new_state.avg_entry_price if new_state.avg_entry_price > 0 else new_state.entry_price
            tp1_price = tp1_base * (1 + config.tp1_pct / 100.0)
            if not new_state.tp1_triggered and curr_exit_close >= tp1_price:
                new_state.tp1_triggered = True

                # 피라미딩 리필 (v8)
                if config.pyr_refill_after_sell and new_state.pyr_count > 1:
                    new_state.pyr_count -= 1

                return SignalResult(
                    action="sell",
                    reason_code="TREND_EXIT_TP1",
                    reason_text=f"목표익절(TP1): +{config.tp1_pct}% 도달, {config.tp1_sell_pct}% 청산",
                    tranche_pct=config.tp1_sell_pct,
                    regime=0,
                ), new_state

        # Exit 3: SPO Split (분할매도) - use_spo_split=True일 때만 (v8)
        if config.use_spo_split:
            # SPO signal_dn: norm_osc > threshold AND crossover(prev, curr) [하락 전환]
            spo_signal_dn = (curr_spo > config.exit_spo_threshold) and (prev_spo > curr_spo)

            if spo_signal_dn:
                # 익절 게이트 체크
                gate_ok = True
                if config.use_profit_gate:
                    need_pct = config.min_profit_pct + config.fee_buffer_pct
                    gate_base = new_state.avg_entry_price if new_state.avg_entry_price > 0 else new_state.entry_price
                    gate_price = gate_base * (1 + need_pct / 100.0)
                    gate_ok = curr_exit_close >= gate_price

                if gate_ok:
                    # 분할매도 차수 결정
                    eff_stage = new_state.sell_stage
                    if eff_stage >= config.max_sell_tranches:
                        if config.after_max_sell == "cycle":
                            eff_stage = 0
                        elif config.after_max_sell == "stop":
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

                        # 피라미딩 리필 (v8)
                        if config.pyr_refill_after_sell and new_state.pyr_count > 1:
                            new_state.pyr_count -= 1

                        return SignalResult(
                            action="sell",
                            reason_code="TREND_EXIT_SPO_SPLIT",
                            reason_text=f"SPO 분할매도: SELL{eff_stage + 1} 실행 ({sell_pct}%)",
                            tranche_pct=sell_pct,
                            regime=0,
                        ), new_state

        # Exit 4: ST Flip (exit_tf Supertrend 하락 전환)
        if config.use_st_exit:
            # exit_tf ST가 bullish→bearish 전환 체크
            st_bear_flip = (prev_exit_st_dir < 0) and (curr_exit_st_dir >= 0)

            if st_bear_flip:
                # 상태 리셋
                new_state.in_position = False
                new_state.entry_price = 0.0
                new_state.tp1_triggered = False
                new_state.sell_stage = 0
                new_state.pyr_count = 0
                new_state.avg_entry_price = 0.0
                new_state.total_cost = 0.0

                return SignalResult(
                    action="sell",
                    reason_code="TREND_EXIT_ST_FLIP",
                    reason_text="추세전환 전량청산: exit_tf Supertrend 하락",
                    tranche_pct=100.0,
                    regime=0,
                ), new_state

        # ──────────────────────────────────────────────────────
        # 피라미딩 (추가매수) 체크 (v8)
        # ──────────────────────────────────────────────────────
        if config.use_pyramiding and new_state.pyr_count < config.max_pyr_entries:
            # 조건: N봉 신고가 돌파 AND 쿨다운 OK AND ST bullish AND HTF OK
            cooldown_ok = (bar_index - new_state.last_pyr_bar) >= config.pyr_cooldown
            breakout_ok = curr_entry_close > pyr_high_threshold if pyr_high_threshold > 0 else False
            st_bullish = curr_entry_st_dir < 0

            # HTF 조건 (use_htf_filter에 따라)
            htf_ok = True
            if config.use_htf_filter:
                htf_ok = curr_entry_close > curr_htf_vwma if curr_htf_vwma > 0 else True

            pyr_signal = cooldown_ok and breakout_ok and st_bullish and htf_ok

            if pyr_signal:
                # 피라미딩 진입
                pyr_idx = new_state.pyr_count  # 현재 몇 번째 진입인지 (0-indexed)
                weight = config.pyr_weights[pyr_idx] if pyr_idx < len(config.pyr_weights) else 0.0

                if weight > 0:
                    new_state.pyr_count += 1
                    new_state.last_pyr_bar = bar_index

                    return SignalResult(
                        action="buy",
                        reason_code="TREND_ENTRY_PYR",
                        reason_text=f"피라미딩 {new_state.pyr_count}차: {config.pyr_high_len}봉 신고가 돌파",
                        tranche_pct=weight,  # 피라미딩 비중
                        regime=0,
                    ), new_state

    # ──────────────────────────────────────────────────────
    # ENTRY 로직 (포지션 없을 때만)
    # ──────────────────────────────────────────────────────
    if not new_state.in_position:
        # Entry 조건 4가지
        st_bullish = curr_entry_st_dir < 0  # Supertrend 상승 (PineScript convention)

        # HTF 필터 (v8: use_htf_filter=False면 스킵)
        htf_ok = True
        if config.use_htf_filter:
            htf_ok = curr_entry_close > curr_htf_vwma if curr_htf_vwma > 0 else True

        setup_conditions = st_bullish and hvi_green and qqe_positive and htf_ok

        # 진입 가드: 셋업 시작봉 추적 (v8)
        prev_setup_met = new_state.prev_setup_met
        new_state.prev_setup_met = setup_conditions

        # enter_only_on_setup_start 체크
        entry_allowed = True
        if config.enter_only_on_setup_start:
            # 셋업이 새로 시작된 경우에만 진입 (이전 봉에서 셋업 미충족 → 현재 충족)
            if setup_conditions and not prev_setup_met:
                new_state.setup_start_bar = bar_index
                entry_allowed = True
            elif setup_conditions and prev_setup_met:
                # 이미 진행 중인 셋업 - 진입 불가
                entry_allowed = False
            else:
                entry_allowed = False
        else:
            entry_allowed = setup_conditions

        buy_signal = setup_conditions and entry_allowed

        if buy_signal:
            new_state.in_position = True
            new_state.entry_price = curr_entry_close
            new_state.entry_ts = current_ts
            new_state.highest_since_entry = curr_entry_close
            new_state.tp1_triggered = False
            new_state.sell_stage = 0

            # 피라미딩 상태 초기화 (v8)
            new_state.pyr_count = 1  # 1차 진입
            new_state.last_pyr_bar = bar_index
            new_state.total_cost = curr_entry_close  # 초기 진입가 * 1 (수량은 별도 계산)
            new_state.avg_entry_price = curr_entry_close

            # 1차 진입 비중 (v8: pyr_weights[0] 사용)
            first_weight = config.pyr_weights[0] if len(config.pyr_weights) > 0 else 100.0
            entry_pct = config.cash_use_pct * (first_weight / 100.0)

            return SignalResult(
                action="buy",
                reason_code="TREND_ENTRY_FULL",
                reason_text="추세매매 진입: ST상승+HVI초록+QQE양수+HTF VWMA 상위",
                tranche_pct=entry_pct,
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
    config: Optional[TrendConfig] = None,
) -> dict:
    """
    Entry 조건 개별 체크 (디버깅/UI용).

    Args:
        entry_close: Close price array
        entry_st_dir: Supertrend direction array
        entry_hvi: HVI indicator result
        entry_qqe: QQE indicator result
        htf_vwma: HTF VWMA array
        config: TrendConfig (optional, for v8 options like st_invert, use_htf_filter)

    Returns:
        dict with each condition status
    """
    curr_close = entry_close[-1] if len(entry_close) > 0 else 0.0
    curr_st_dir = entry_st_dir[-1] if len(entry_st_dir) > 0 else 1

    # v8: ST 반전 적용
    if config is not None and config.st_invert:
        curr_st_dir = -curr_st_dir

    hvi_green = entry_hvi.get('g_enabled', np.array([False]))[-1] if len(entry_hvi.get('g_enabled', [])) > 0 else False
    qqe_pos = entry_qqe.get('is_positive', np.array([False]))[-1] if len(entry_qqe.get('is_positive', [])) > 0 else False
    curr_htf_vwma = htf_vwma[-1] if len(htf_vwma) > 0 and not np.isnan(htf_vwma[-1]) else 0.0

    # v8: HTF 필터 토글
    use_htf = True
    if config is not None:
        use_htf = config.use_htf_filter

    htf_ok = True
    if use_htf:
        htf_ok = curr_close > curr_htf_vwma if curr_htf_vwma > 0 else True

    st_bullish = curr_st_dir < 0

    return {
        'st_bullish': st_bullish,
        'hvi_green': bool(hvi_green),
        'qqe_positive': bool(qqe_pos),
        'htf_ok': htf_ok,
        'all_conditions_met': st_bullish and hvi_green and qqe_pos and htf_ok,
    }


def check_pyramiding_conditions(
    entry_close: np.ndarray,
    entry_high: np.ndarray,
    entry_st_dir: np.ndarray,
    htf_vwma: np.ndarray,
    config: TrendConfig,
    state: TrendState,
    bar_index: int,
) -> dict:
    """
    피라미딩 조건 개별 체크 (디버깅/UI용, v8).

    Returns:
        dict with each condition status
    """
    curr_close = entry_close[-1] if len(entry_close) > 0 else 0.0
    curr_st_dir = entry_st_dir[-1] if len(entry_st_dir) > 0 else 1

    # ST 반전 적용
    if config.st_invert:
        curr_st_dir = -curr_st_dir

    # N봉 신고가
    pyr_high_threshold = 0.0
    if len(entry_high) >= config.pyr_high_len:
        pyr_high_threshold = np.max(entry_high[-config.pyr_high_len:-1]) if len(entry_high) > 1 else entry_high[-1]

    # 조건들
    cooldown_ok = (bar_index - state.last_pyr_bar) >= config.pyr_cooldown
    breakout_ok = curr_close > pyr_high_threshold if pyr_high_threshold > 0 else False
    st_bullish = curr_st_dir < 0
    entries_ok = state.pyr_count < config.max_pyr_entries

    # HTF 조건
    curr_htf_vwma = htf_vwma[-1] if len(htf_vwma) > 0 and not np.isnan(htf_vwma[-1]) else 0.0
    htf_ok = True
    if config.use_htf_filter:
        htf_ok = curr_close > curr_htf_vwma if curr_htf_vwma > 0 else True

    return {
        'in_position': state.in_position,
        'pyr_count': state.pyr_count,
        'max_entries': config.max_pyr_entries,
        'entries_ok': entries_ok,
        'cooldown_ok': cooldown_ok,
        'cooldown_bars': bar_index - state.last_pyr_bar,
        'required_cooldown': config.pyr_cooldown,
        'breakout_ok': breakout_ok,
        'current_close': curr_close,
        'pyr_high_threshold': pyr_high_threshold,
        'st_bullish': st_bullish,
        'htf_ok': htf_ok,
        'all_conditions_met': entries_ok and cooldown_ok and breakout_ok and st_bullish and htf_ok,
    }

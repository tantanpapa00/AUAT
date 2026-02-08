"""
BBooster Signal Params Validation
effective_params 검증 로직
"""
from typing import List, Optional


class ValidationError(Exception):
    """설정 검증 실패 예외"""
    pass


def validate_effective_params(params: dict, exchange_capabilities: dict = None) -> List[str]:
    """
    effective_params를 검증한다.

    Args:
        params: 머지된 effective_params
        exchange_capabilities: 거래소 기능 정보 (supports_bracket 등)

    Returns:
        경고 메시지 리스트 (빈 리스트 = 문제 없음)

    Raises:
        ValidationError: 치명적 오류
    """
    errors = []
    warnings = []

    sizing = params.get("sizing", {})
    risk = params.get("risk", {})
    limits = params.get("limits", {})

    # ─── Sizing 검증 ───
    mode = sizing.get("mode", "balance_pct")
    value = sizing.get("value", 0)

    if mode == "balance_pct":
        if not (1 <= value <= 100):
            errors.append(f"사이징: 가용자금 비율은 1~100% 범위여야 합니다 (현재: {value}%)")
    elif mode == "fixed_amount":
        if value <= 0:
            errors.append(f"사이징: 고정금액은 0보다 커야 합니다 (현재: {value})")

    max_notional = sizing.get("max_notional_per_order", 0)
    if max_notional < 0:
        errors.append(f"사이징: 1회 최대 주문금액은 음수일 수 없습니다 (현재: {max_notional})")

    min_notional = sizing.get("min_notional_per_order", 0)
    if min_notional < 0:
        errors.append(f"사이징: 1회 최소 주문금액은 음수일 수 없습니다 (현재: {min_notional})")

    if max_notional > 0 and min_notional > 0 and min_notional > max_notional:
        errors.append(f"사이징: 최소금액({min_notional})이 최대금액({max_notional})보다 큽니다")

    reduce_pct = sizing.get("reduce", {}).get("default_pct", 0)
    if reduce_pct < 0 or reduce_pct > 100:
        errors.append(f"사이징: 부분청산 비율은 0~100% 범위여야 합니다 (현재: {reduce_pct}%)")

    sequence = sizing.get("reduce", {}).get("sequence_pct", [])
    if sequence:
        if any(p <= 0 or p > 100 for p in sequence):
            errors.append("사이징: 분할청산 순서의 각 값은 1~100% 범위여야 합니다")
        if sum(sequence) != 100:
            warnings.append(f"사이징: 분할청산 순서 합계가 100%가 아닙니다 (현재: {sum(sequence)}%)")

    # ─── Risk 검증 ───
    exec_mode = risk.get("exec_mode", "tv_exit_signal")
    leverage = risk.get("leverage_value", 1)

    if leverage < 1:
        errors.append(f"리스크: 레버리지는 1 이상이어야 합니다 (현재: {leverage})")

    # 거래소가 브라켓 주문을 지원하지 않으면 경고
    if exec_mode == "exchange_bracket":
        if exchange_capabilities and not exchange_capabilities.get("supports_bracket", False):
            warnings.append("리스크: 거래소가 브라켓 주문을 지원하지 않아 tv_exit_signal로 자동 전환됩니다")

    for label, section in [("손절", risk.get("sl", {})), ("익절", risk.get("tp", {}))]:
        if section.get("enabled"):
            val = section.get("value", 0)
            if val <= 0:
                errors.append(f"리스크: {label} 활성화됨 - 값이 0보다 커야 합니다")

    trailing = risk.get("trailing", {})
    if trailing.get("enabled") and trailing.get("value", 0) <= 0:
        errors.append("리스크: 트레일링 스탑 활성화됨 - 값이 0보다 커야 합니다")

    # ─── Limits 검증 ───
    for field in ["cooldown_seconds", "daily_max_trades", "daily_max_notional", "max_open_positions"]:
        val = limits.get(field, 0)
        if val < 0:
            errors.append(f"리밋: {field}은(는) 음수일 수 없습니다 (현재: {val})")

    # ─── 결과 ───
    if errors:
        raise ValidationError("설정 검증 실패:\n" + "\n".join(f"  - {e}" for e in errors))

    return warnings


def validate_reduce_pct(reduce_pct) -> Optional[float]:
    """
    웹훅으로 들어온 reduce_pct 검증 (1~100 범위)

    Args:
        reduce_pct: 웹훅에서 전달된 부분청산 비율

    Returns:
        검증된 float 값 또는 None

    Raises:
        ValidationError: 범위 초과
    """
    if reduce_pct is None:
        return None
    pct = float(reduce_pct)
    if not (1 <= pct <= 100):
        raise ValidationError(f"reduce_pct는 1~100 범위여야 합니다 (현재: {pct})")
    return pct

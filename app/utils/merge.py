"""
BBooster Deep Merge Utility
전략 signal_params + 종목별 override 병합
"""
from typing import Optional, List
import copy


def deep_merge(base: Optional[dict], override: Optional[dict]) -> dict:
    """
    base(전략 기본값)에 override(종목 오버라이드)를 깊은 병합.

    머지 규칙:
    - dict: 재귀적으로 키 merge
    - scalar(number/string/bool): override 값으로 교체
    - array: 통째로 교체 (merge하지 않음)
    - null: override에 null 키가 있으면 무시 (키 삭제 방식 권장)

    Args:
        base: 전략 레벨 signal_params
        override: 종목별 signal_params_override

    Returns:
        병합된 설정 dict

    Examples:
        >>> base = {"sizing": {"mode": "balance_pct", "value": 30}}
        >>> override = {"sizing": {"value": 20}}
        >>> deep_merge(base, override)
        {"sizing": {"mode": "balance_pct", "value": 20}}
    """
    if override is None:
        return copy.deepcopy(base) if base else {}

    result = {}

    # base 키 먼저 복사
    if base:
        for key, value in base.items():
            if isinstance(value, dict):
                result[key] = deep_merge(value, {})  # dict는 깊은 복사
            elif isinstance(value, list):
                result[key] = value.copy()  # array는 복사
            else:
                result[key] = value

    # override 적용
    for key, value in override.items():
        if value is None:
            continue  # null 값은 무시 (키 삭제 방식 권장)

        if isinstance(value, dict) and key in result and isinstance(result[key], dict):
            # object: 재귀적으로 merge
            result[key] = deep_merge(result[key], value)
        elif isinstance(value, list):
            # array: 통째로 교체
            result[key] = value.copy()
        else:
            # scalar: override로 교체
            result[key] = value

    return result


def get_overridden_keys(base: Optional[dict], override: Optional[dict], prefix: str = "") -> List[str]:
    """
    override에서 변경된 키 목록 추출 (점 표기법).

    Args:
        base: 전략 레벨 signal_params
        override: 종목별 signal_params_override
        prefix: 현재 경로 접두사 (재귀용)

    Returns:
        변경된 키 목록 (예: ["sizing.value", "limits.cooldown_seconds"])

    Examples:
        >>> base = {"sizing": {"mode": "balance_pct", "value": 30}}
        >>> override = {"sizing": {"value": 20}}
        >>> get_overridden_keys(base, override)
        ["sizing.value"]
    """
    if override is None:
        return []

    keys = []
    for key, value in override.items():
        full_key = f"{prefix}.{key}" if prefix else key

        if isinstance(value, dict):
            # 재귀적으로 중첩 dict 탐색
            base_value = base.get(key, {}) if base else {}
            if isinstance(base_value, dict):
                keys.extend(get_overridden_keys(base_value, value, full_key))
            else:
                keys.append(full_key)
        else:
            keys.append(full_key)

    return keys


# 기본값 상수 v2 (API에서 사용)
DEFAULT_SIGNAL_PARAMS = {
    "sizing": {
        "mode": "balance_pct",  # balance_pct / fixed_amount / fixed_qty
        "value": 30,
        "base": "free",  # free / total (mode=balance_pct일 때만)
        "currency": "USDT",  # KRW / USD / USDT / USDC
        "max_notional_per_order": 0,
        "min_notional_per_order": 0,
        "reduce": {
            "mode": "full",  # full / partial
            "default_pct": 100
        }
    },
    "risk": {
        "exec_mode": "tv_exit_signal",  # tv_exit_signal / exchange_bracket
        "leverage_policy": "fixed",
        "leverage_value": 1,
        "sl": {
            "enabled": False,
            "type": "pct",
            "value": 0,
            "basis": "entry",
            "order_type": "market"
        },
        "tp": {
            "enabled": False,
            "type": "pct",
            "value": 0,
            "basis": "entry",
            "order_type": "market"
        },
        "trailing": {
            "enabled": False,
            "type": "pct",
            "value": 0
        },
        "reduce_only": True
    },
    "limits": {
        "idempotency": {
            "enabled": True,
            "key": "alert_id"
        },
        "cooldown_seconds": 0,
        "one_trade_per_bar": False,
        "daily_max_trades": {"enabled": False, "value": 0},
        "daily_max_notional": {"enabled": False, "value": 0},
        "max_open_positions": {"enabled": False, "value": 0},
        "allow_same_side_add": True
    },
    "meta": {
        "version": 2,
        "notes": ""
    }
}

# app/utils/plan_limits.py
# 요금제별 제한 상수 및 helper 함수

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.models import User

# 요금제별 AI 사용 제한 (일일)
AI_DAILY_LIMITS = {
    "starter": 0,
    "free": 0,
    "standard": 3,
    "hub": 3,          # legacy alias for standard
    "pro": 7,
    "proplus": 10,
    "promax": 15,
    "premium": 15,     # legacy alias for promax
}

# 요금제별 AI 사용 제한 (월간)
# Standard: 30, Pro: 100, Pro+: 150, Pro Max: 200
AI_MONTHLY_LIMITS = {
    "starter": 0,
    "free": 0,
    "standard": 30,
    "hub": 30,          # legacy alias for standard
    "pro": 100,
    "proplus": 150,
    "promax": 200,
    "premium": 200,     # legacy alias for promax
}

# 요금제별 자동매매 슬롯 제한
# Pro: 3, Pro+: 10, Pro Max: 30
SLOT_LIMITS = {
    "starter": 0,
    "free": 0,
    "standard": 0,
    "hub": 0,
    "pro": 3,
    "proplus": 10,
    "promax": 30,
    "premium": 30,      # legacy alias for promax
}

# 요금제별 백테스트 월간 제한
# Pro: 100, Pro+/Pro Max: 무제한(99999)
BACKTEST_MONTHLY_LIMITS = {
    "starter": 0,
    "free": 0,
    "standard": 0,
    "hub": 0,
    "pro": 100,
    "proplus": 99999,   # 무제한
    "promax": 99999,    # 무제한
    "premium": 99999,   # legacy alias for promax
}

# 요금제별 관심종목 제한
WATCHLIST_LIMITS = {
    "starter": 10,
    "free": 10,
    "standard": 50,
    "hub": 50,
    "pro": 200,
    "proplus": 500,
    "promax": 99999,
    "premium": 99999,
}


def get_watchlist_limit(user: "User") -> int:
    """요금제별 관심종목 제한"""
    role = getattr(user, "role", "user")
    if role == "admin":
        return 99999
    plan = getattr(user, "plan", "free")
    return WATCHLIST_LIMITS.get(plan, 10)


def get_ai_daily_limit(user: "User") -> int:
    """요금제별 AI 일일 사용 제한"""
    role = getattr(user, "role", "user")
    if role == "admin":
        return 99999
    plan = getattr(user, "plan", "free")
    return AI_DAILY_LIMITS.get(plan, 0)


def get_ai_monthly_limit(user: "User") -> int:
    """요금제별 AI 월간 사용 제한"""
    role = getattr(user, "role", "user")
    if role == "admin":
        return 99999
    plan = getattr(user, "plan", "free")
    return AI_MONTHLY_LIMITS.get(plan, 0)


def get_slot_limit(user: "User") -> int:
    """요금제별 자동매매 슬롯 제한 (Pro:3, Pro+:10, Pro Max:30)"""
    role = getattr(user, "role", "user")
    if role == "admin":
        return 99999
    plan = getattr(user, "plan", "free")
    return SLOT_LIMITS.get(plan, 0)


def get_backtest_monthly_limit(user: "User") -> int:
    """요금제별 백테스트 월간 제한 (Pro:100, Pro+/Pro Max:무제한)"""
    role = getattr(user, "role", "user")
    if role == "admin":
        return 99999
    plan = getattr(user, "plan", "free")
    return BACKTEST_MONTHLY_LIMITS.get(plan, 0)


def check_standard_plan(user: "User") -> bool:
    """Standard 이상 요금제 체크 (종목분석/AI 분석용)"""
    if not user:
        return False
    role = getattr(user, "role", "user")
    plan = getattr(user, "plan", "free")
    if role == "admin":
        return True
    return plan in ("standard", "hub", "pro", "proplus", "promax", "premium")


def check_pro_plan(user: "User") -> bool:
    """Pro 이상 요금제 체크 (자동매매/백테스트용)"""
    if not user:
        return False
    role = getattr(user, "role", "user")
    plan = getattr(user, "plan", "free")
    if role == "admin":
        return True
    return plan in ("pro", "proplus", "promax", "premium")

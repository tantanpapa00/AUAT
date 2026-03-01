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
    "hub": 3,
    "pro": 7,
    "premium": 15,
}

# 요금제별 AI 사용 제한 (월간)
AI_MONTHLY_LIMITS = {
    "starter": 0,
    "free": 0,
    "standard": 30,
    "hub": 30,
    "pro": 100,
    "premium": 200,
}

# 요금제별 관심종목 제한
WATCHLIST_LIMITS = {
    "starter": 10,
    "free": 10,
    "standard": 50,
    "hub": 50,
    "pro": 200,
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


def check_standard_plan(user: "User") -> bool:
    """Standard 이상 요금제 체크 (AI 분석용)"""
    if not user:
        return False
    role = getattr(user, "role", "user")
    plan = getattr(user, "plan", "free")
    if role == "admin":
        return True
    return plan in ("standard", "pro", "premium")

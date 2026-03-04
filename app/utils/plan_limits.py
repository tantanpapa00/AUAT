# app/utils/plan_limits.py
# 요금제별 제한 상수 및 helper 함수
# SSOT: 명령서65 - 요금제별 실제 기능 제한 구현

from typing import TYPE_CHECKING, Tuple, Optional
from datetime import datetime, timezone, timedelta

if TYPE_CHECKING:
    from app.models import User
    from sqlalchemy.orm import Session

# KST timezone
KST = timezone(timedelta(hours=9))

# =============================================================================
# PLAN_LIMITS SSOT (Single Source of Truth)
# 모든 요금제 제한을 한 곳에서 관리
# =============================================================================
PLAN_LIMITS = {
    "free": {
        "ai_daily": 0,
        "ai_monthly": 0,
        "backtest_monthly": 0,
        "slots": 0,
        "watchlist": 10,
        "can_ai": False,
        "can_backtest": False,
        "can_autotrading": False,
    },
    "starter": {
        "ai_daily": 0,
        "ai_monthly": 0,
        "backtest_monthly": 0,
        "slots": 0,
        "watchlist": 10,
        "can_ai": False,
        "can_backtest": False,
        "can_autotrading": False,
    },
    "standard": {
        "ai_daily": 3,
        "ai_monthly": 30,
        "backtest_monthly": 0,
        "slots": 0,
        "watchlist": 50,
        "can_ai": True,
        "can_backtest": False,
        "can_autotrading": False,
    },
    "hub": {  # legacy alias for standard
        "ai_daily": 3,
        "ai_monthly": 30,
        "backtest_monthly": 0,
        "slots": 0,
        "watchlist": 50,
        "can_ai": True,
        "can_backtest": False,
        "can_autotrading": False,
    },
    "pro": {
        "ai_daily": 7,
        "ai_monthly": 100,
        "backtest_monthly": 100,
        "slots": 5,
        "watchlist": 200,
        "can_ai": True,
        "can_backtest": True,
        "can_autotrading": True,
    },
    "proplus": {
        "ai_daily": 10,
        "ai_monthly": 150,
        "backtest_monthly": 99999,  # 무제한
        "slots": 15,
        "watchlist": 500,
        "can_ai": True,
        "can_backtest": True,
        "can_autotrading": True,
    },
    "promax": {
        "ai_daily": 15,
        "ai_monthly": 200,
        "backtest_monthly": 99999,  # 무제한
        "slots": 50,
        "watchlist": 99999,
        "can_ai": True,
        "can_backtest": True,
        "can_autotrading": True,
    },
    "premium": {  # legacy alias for promax
        "ai_daily": 15,
        "ai_monthly": 200,
        "backtest_monthly": 99999,
        "slots": 50,
        "watchlist": 99999,
        "can_ai": True,
        "can_backtest": True,
        "can_autotrading": True,
    },
}

# 기능별 업그레이드 URL
UPGRADE_URLS = {
    "ai": "/pricing?feature=ai",
    "backtest": "/pricing?feature=backtest",
    "slots": "/pricing?feature=autotrading",
    "watchlist": "/pricing?feature=watchlist",
}

# 기능별 최소 요금제
MIN_PLAN_FOR_FEATURE = {
    "ai": "standard",
    "backtest": "pro",
    "slots": "pro",
    "watchlist": "free",  # 모두 가능하나 제한 다름
}

# =============================================================================
# 기존 개별 딕셔너리 (하위 호환성 유지)
# =============================================================================

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


# =============================================================================
# 통합 사용량 체크 함수
# =============================================================================

def get_plan_limits(user: "User") -> dict:
    """사용자의 요금제 제한 정보 반환"""
    if not user:
        return PLAN_LIMITS["free"]
    role = getattr(user, "role", "user")
    if role == "admin":
        return {
            "ai_daily": 99999,
            "ai_monthly": 99999,
            "backtest_monthly": 99999,
            "slots": 99999,
            "watchlist": 99999,
            "can_ai": True,
            "can_backtest": True,
            "can_autotrading": True,
        }
    plan = getattr(user, "plan", "free")
    return PLAN_LIMITS.get(plan, PLAN_LIMITS["free"])


def check_feature_allowed(
    user: "User",
    feature: str,
    db: "Session",
    increment: bool = False
) -> Tuple[bool, Optional[str], Optional[str]]:
    """
    기능 사용 가능 여부 체크 + 사용량 증가

    Args:
        user: User 객체
        feature: "ai", "backtest", "slots", "watchlist"
        db: SQLAlchemy Session
        increment: True면 사용량 +1 증가

    Returns:
        (allowed, error_message, upgrade_url)
        - allowed: True면 사용 가능
        - error_message: 불가 시 에러 메시지
        - upgrade_url: 업그레이드 페이지 URL
    """
    from sqlalchemy import text

    if not user:
        return False, "로그인이 필요합니다.", "/login"

    limits = get_plan_limits(user)
    today = datetime.now(KST).date()
    this_month = today.strftime("%Y-%m")
    upgrade_url = UPGRADE_URLS.get(feature, "/pricing")

    # 1. AI 분석
    if feature == "ai":
        if not limits["can_ai"]:
            return False, "AI 종목분석은 Standard 이상에서 이용 가능합니다.", upgrade_url

        daily_max = limits["ai_daily"]
        monthly_max = limits["ai_monthly"]

        # 현재 사용량 조회
        try:
            result = db.execute(
                text("SELECT ai_usage_count, ai_usage_date, ai_monthly_count, ai_monthly_date FROM users WHERE id = :uid"),
                {"uid": user.id}
            )
            row = result.fetchone()

            daily_count = 0
            monthly_count = 0

            if row:
                usage_date = row[1]
                monthly_date = row[3] or ""

                # 날짜 리셋 체크
                if usage_date != today:
                    db.execute(
                        text("UPDATE users SET ai_usage_count = 0, ai_usage_date = :today WHERE id = :uid"),
                        {"uid": user.id, "today": today}
                    )
                    daily_count = 0
                else:
                    daily_count = row[0] or 0

                if monthly_date != this_month:
                    db.execute(
                        text("UPDATE users SET ai_monthly_count = 0, ai_monthly_date = :month WHERE id = :uid"),
                        {"uid": user.id, "month": this_month}
                    )
                    monthly_count = 0
                else:
                    monthly_count = row[2] or 0

                db.commit()

            # 제한 체크
            if daily_count >= daily_max:
                return False, f"오늘의 AI 분석 횟수({daily_max}회)를 모두 사용했습니다.", upgrade_url

            if monthly_count >= monthly_max:
                return False, f"이번 달 AI 분석 횟수({monthly_max}회)를 모두 사용했습니다.", upgrade_url

            # 사용량 증가
            if increment:
                db.execute(
                    text("""
                        UPDATE users
                        SET ai_usage_count = ai_usage_count + 1,
                            ai_monthly_count = ai_monthly_count + 1
                        WHERE id = :uid
                    """),
                    {"uid": user.id}
                )
                db.commit()

            return True, None, None

        except Exception as e:
            print(f"[check_feature_allowed] AI usage check error: {e}")
            return True, None, None  # 에러 시 허용 (fail-open)

    # 2. 백테스트
    elif feature == "backtest":
        if not limits["can_backtest"]:
            return False, "백테스트는 Pro 이상에서 이용 가능합니다.", upgrade_url

        monthly_max = limits["backtest_monthly"]
        if monthly_max >= 99999:
            # 무제한
            return True, None, None

        # 백테스트 사용량 조회 (usage_tracking 테이블 사용)
        try:
            result = db.execute(
                text("""
                    SELECT COALESCE(SUM(count), 0) FROM usage_tracking
                    WHERE user_id = :uid AND feature = 'backtest' AND month_key = :month
                """),
                {"uid": user.id, "month": this_month}
            )
            monthly_count = result.scalar() or 0

            if monthly_count >= monthly_max:
                return False, f"이번 달 백테스트 횟수({monthly_max}회)를 모두 사용했습니다.", upgrade_url

            if increment:
                # UPSERT
                db.execute(
                    text("""
                        INSERT INTO usage_tracking (user_id, feature, month_key, count, updated_at)
                        VALUES (:uid, 'backtest', :month, 1, NOW())
                        ON CONFLICT (user_id, feature, month_key)
                        DO UPDATE SET count = usage_tracking.count + 1, updated_at = NOW()
                    """),
                    {"uid": user.id, "month": this_month}
                )
                db.commit()

            return True, None, None

        except Exception as e:
            print(f"[check_feature_allowed] Backtest usage check error: {e}")
            # 테이블이 없으면 생성 시도
            if "usage_tracking" in str(e):
                try:
                    _ensure_usage_tracking_table(db)
                    return True, None, None
                except:
                    pass
            return True, None, None  # 에러 시 허용

    # 3. 자동매매 슬롯
    elif feature == "slots":
        if not limits["can_autotrading"]:
            return False, "자동매매는 Pro 이상에서 이용 가능합니다.", upgrade_url

        slots_max = limits["slots"]

        # 현재 활성 슬롯 수 조회
        try:
            result = db.execute(
                text("""
                    SELECT COUNT(*) FROM premium_configs pc
                    JOIN assets a ON a.id = pc.asset_id
                    JOIN accounts acc ON acc.id = a.account_id
                    WHERE acc.owner_id = :uid AND a.is_active = true AND a.soft_deleted = 0
                """),
                {"uid": user.id}
            )
            current_slots = result.scalar() or 0

            if current_slots >= slots_max:
                return False, f"자동매매 슬롯({slots_max}개)을 모두 사용 중입니다.", upgrade_url

            return True, None, None

        except Exception as e:
            print(f"[check_feature_allowed] Slots check error: {e}")
            return True, None, None

    # 4. 관심종목
    elif feature == "watchlist":
        watchlist_max = limits["watchlist"]

        try:
            result = db.execute(
                text("SELECT COUNT(*) FROM watchlist_items WHERE user_id = :uid"),
                {"uid": user.id}
            )
            current_count = result.scalar() or 0

            if current_count >= watchlist_max:
                return False, f"관심종목({watchlist_max}개)을 모두 사용했습니다.", upgrade_url

            return True, None, None

        except Exception as e:
            print(f"[check_feature_allowed] Watchlist check error: {e}")
            return True, None, None

    return True, None, None


def _ensure_usage_tracking_table(db: "Session"):
    """usage_tracking 테이블 생성"""
    from sqlalchemy import text

    db.execute(text("""
        CREATE TABLE IF NOT EXISTS usage_tracking (
            id SERIAL PRIMARY KEY,
            user_id INTEGER NOT NULL REFERENCES users(id),
            feature VARCHAR(50) NOT NULL,
            month_key VARCHAR(7) NOT NULL,
            count INTEGER NOT NULL DEFAULT 0,
            created_at TIMESTAMP DEFAULT NOW(),
            updated_at TIMESTAMP DEFAULT NOW(),
            UNIQUE(user_id, feature, month_key)
        )
    """))
    db.execute(text("""
        CREATE INDEX IF NOT EXISTS ix_usage_tracking_user_feature
        ON usage_tracking(user_id, feature)
    """))
    db.commit()
    print("[DB] usage_tracking 테이블 생성 완료")

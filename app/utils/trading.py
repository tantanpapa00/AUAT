"""
BBooster Trading Utilities
Hub 매매 로직 - Limits 체크, Sizing 계산, 시장 시간 체크
"""
from datetime import datetime, timezone, timedelta
from typing import Tuple, Optional, Dict, Any
from sqlalchemy.orm import Session
from sqlalchemy import text


# =====================
# US Market Hours Check
# =====================

def is_us_market_open() -> bool:
    """
    미국 정규장 운영 시간 체크 (EST 09:30~16:00, 월~금)

    Returns:
        True if US market is open, False otherwise
    """
    from zoneinfo import ZoneInfo
    now_et = datetime.now(ZoneInfo("America/New_York"))

    # 주말 체크
    if now_et.weekday() >= 5:  # 5=토요일, 6=일요일
        return False

    # 정규장 시간 체크 (09:30 ~ 16:00 ET)
    market_open = now_et.replace(hour=9, minute=30, second=0, microsecond=0)
    market_close = now_et.replace(hour=16, minute=0, second=0, microsecond=0)

    return market_open <= now_et <= market_close


def get_us_market_status() -> Dict[str, Any]:
    """
    미국장 상태 반환

    Returns:
        {
            "is_open": bool,
            "current_time_et": str,
            "weekday": str,
            "next_open": str (장 마감 시)
        }
    """
    from zoneinfo import ZoneInfo
    now_et = datetime.now(ZoneInfo("America/New_York"))

    is_open = is_us_market_open()

    result = {
        "is_open": is_open,
        "current_time_et": now_et.strftime("%Y-%m-%d %H:%M:%S ET"),
        "weekday": now_et.strftime("%A"),
    }

    # 장 마감 시 다음 개장 시간 계산
    if not is_open:
        # 현재 시간 기준으로 다음 개장일 계산
        next_open = now_et.replace(hour=9, minute=30, second=0, microsecond=0)

        # 오늘 이미 장이 마감됐으면 내일로
        if now_et.hour >= 16:
            next_open += timedelta(days=1)

        # 주말이면 월요일로
        while next_open.weekday() >= 5:
            next_open += timedelta(days=1)

        result["next_open"] = next_open.strftime("%Y-%m-%d %H:%M:%S ET")

    return result


async def check_limits(
    db: Session,
    params: dict,
    asset_id: int,
    account_id: int,
    alert_id: str,
    signal_side: str,
    bar_time: Optional[datetime] = None
) -> Tuple[bool, str]:
    """
    Limits 체크 - 주문 전 가드레일 검증

    Args:
        db: 데이터베이스 세션
        params: effective_params (머지된 설정)
        asset_id: 종목 ID
        account_id: 계정 ID
        alert_id: 웹훅 alert_id (중복 체크용)
        signal_side: 신호 방향 (buy/sell)
        bar_time: 봉 시간 (1봉 1회 체크용)

    Returns:
        (통과여부, 거부사유)
    """
    limits = params.get("limits", {})
    now = datetime.now(timezone.utc)
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)

    # 1. 멱등성(중복방지)
    idempotency = limits.get("idempotency", {})
    if idempotency.get("enabled", True):
        key_type = idempotency.get("key", "alert_id")
        if key_type == "alert_id" and alert_id:
            # 같은 alert_id로 이미 주문이 있는지 확인
            existing = db.execute(text("""
                SELECT id FROM orders
                WHERE asset_id = :asset_id AND alert_id = :alert_id
                AND created_at > :since
                LIMIT 1
            """), {
                "asset_id": asset_id,
                "alert_id": alert_id,
                "since": now - timedelta(hours=24)  # 24시간 내 중복 체크
            }).first()
            if existing:
                return False, "중복 신호 (alert_id)"

    # 2. 쿨다운
    cooldown = limits.get("cooldown_seconds", 0)
    if cooldown > 0:
        last_order = db.execute(text("""
            SELECT created_at FROM orders
            WHERE asset_id = :asset_id
            ORDER BY created_at DESC
            LIMIT 1
        """), {"asset_id": asset_id}).first()

        if last_order and last_order[0]:
            last_time = last_order[0]
            if last_time.tzinfo is None:
                last_time = last_time.replace(tzinfo=timezone.utc)
            elapsed = (now - last_time).total_seconds()
            if elapsed < cooldown:
                return False, f"쿨다운 {cooldown}초 미경과 ({int(cooldown - elapsed)}초 남음)"

    # 3. 1봉 1회
    if limits.get("one_trade_per_bar", False) and bar_time:
        bar_start = bar_time
        bar_end = bar_time + timedelta(hours=1)  # 기본 1시간봉 가정
        existing = db.execute(text("""
            SELECT id FROM orders
            WHERE asset_id = :asset_id
            AND created_at >= :bar_start AND created_at < :bar_end
            LIMIT 1
        """), {
            "asset_id": asset_id,
            "bar_start": bar_start,
            "bar_end": bar_end
        }).first()
        if existing:
            return False, "이번 봉에서 이미 거래함"

    # 4. 일일 최대 거래 횟수 (v2: 객체 구조)
    daily_max_obj = limits.get("daily_max_trades", {})
    if isinstance(daily_max_obj, dict) and daily_max_obj.get("enabled"):
        daily_max_trades = daily_max_obj.get("value", 0)
    elif isinstance(daily_max_obj, (int, float)):
        daily_max_trades = daily_max_obj  # v1 호환
    else:
        daily_max_trades = 0

    if daily_max_trades > 0:
        today_count = db.execute(text("""
            SELECT COUNT(*) FROM orders
            WHERE asset_id = :asset_id
            AND created_at >= :today_start
        """), {
            "asset_id": asset_id,
            "today_start": today_start
        }).scalar() or 0

        if today_count >= daily_max_trades:
            return False, f"일일 최대 거래 횟수 {daily_max_trades} 도달"

    # 5. 일일 최대 거래 금액 (v2: 객체 구조)
    daily_notional_obj = limits.get("daily_max_notional", {})
    if isinstance(daily_notional_obj, dict) and daily_notional_obj.get("enabled"):
        daily_max_notional = daily_notional_obj.get("value", 0)
    elif isinstance(daily_notional_obj, (int, float)):
        daily_max_notional = daily_notional_obj  # v1 호환
    else:
        daily_max_notional = 0

    if daily_max_notional > 0:
        today_notional = db.execute(text("""
            SELECT COALESCE(SUM(qty * COALESCE(avg_px, 0)), 0) FROM orders
            WHERE asset_id = :asset_id
            AND created_at >= :today_start
            AND status IN ('filled', 'partially_filled')
        """), {
            "asset_id": asset_id,
            "today_start": today_start
        }).scalar() or 0

        if today_notional >= daily_max_notional:
            return False, f"일일 최대 거래 금액 도달 ({today_notional:,.0f})"

    # 6. 최대 동시 포지션 (v2: 객체 구조)
    max_pos_obj = limits.get("max_open_positions", {})
    if isinstance(max_pos_obj, dict) and max_pos_obj.get("enabled"):
        max_open_positions = max_pos_obj.get("value", 0)
    elif isinstance(max_pos_obj, (int, float)):
        max_open_positions = max_pos_obj  # v1 호환
    else:
        max_open_positions = 0

    if max_open_positions > 0:
        # 현재 열린 포지션 수 (간단 버전: 잔고 > 0인 자산 수)
        open_count = db.execute(text("""
            SELECT COUNT(DISTINCT asset_id) FROM orders
            WHERE account_id = :account_id
            AND status = 'filled'
            AND side = 'buy'
            AND NOT EXISTS (
                SELECT 1 FROM orders o2
                WHERE o2.asset_id = orders.asset_id
                AND o2.side = 'sell'
                AND o2.status = 'filled'
                AND o2.created_at > orders.created_at
            )
        """), {"account_id": account_id}).scalar() or 0

        if open_count >= max_open_positions:
            return False, f"최대 포지션 수 {max_open_positions} 도달"

    # 7. 같은 방향 추가 진입
    if not limits.get("allow_same_side_add", True):
        # 현재 같은 방향 포지션이 있는지 확인
        same_side = db.execute(text("""
            SELECT id FROM orders
            WHERE asset_id = :asset_id
            AND side = :side
            AND status = 'filled'
            ORDER BY created_at DESC
            LIMIT 1
        """), {
            "asset_id": asset_id,
            "side": signal_side
        }).first()

        if same_side:
            return False, "같은 방향 추가 진입 비허용"

    return True, "통과"


def calculate_qty(
    params: dict,
    signal_type: str,
    current_price: float,
    free_balance: float,
    total_balance: float,
    current_position_qty: float = 0,
    reduce_pct_from_signal: Optional[float] = None
) -> float:
    """
    Sizing 계산 - 주문 수량 결정

    Args:
        params: effective_params (머지된 설정)
        signal_type: OPEN | REDUCE | CLOSE
        current_price: 현재가
        free_balance: 가용 잔고
        total_balance: 총 자산
        current_position_qty: 현재 보유 수량
        reduce_pct_from_signal: 웹훅에서 전달된 부분청산 비율

    Returns:
        주문 수량
    """
    sizing = params.get("sizing", {})
    risk = params.get("risk", {})
    leverage = risk.get("leverage_value", 1)

    if signal_type == "CLOSE":
        return current_position_qty  # 전량청산

    if signal_type == "REDUCE":
        # 신호에서 reduce_pct가 왔으면 그거 사용
        pct = reduce_pct_from_signal
        if pct is None or pct == 0:
            # v2 구조: reduce.mode + reduce.default_pct
            reduce_obj = sizing.get("reduce", {})
            reduce_mode = reduce_obj.get("mode", "full")
            if reduce_mode == "full":
                return current_position_qty  # 전량청산
            pct = reduce_obj.get("default_pct", 100)
        if pct == 0 or pct >= 100:
            return current_position_qty  # 전량청산
        return current_position_qty * (pct / 100)

    # OPEN
    mode = sizing.get("mode", "balance_pct")
    value = sizing.get("value", 30)
    base = sizing.get("base", "free")

    # fixed_qty 모드: 수량 직접 반환
    if mode == "fixed_qty":
        return value * leverage

    base_balance = free_balance if base == "free" else total_balance

    if mode == "balance_pct":
        notional = base_balance * (value / 100) * leverage
    elif mode == "fixed_amount":
        notional = value * leverage
    else:
        notional = 0

    # max/min 클램프
    max_n = sizing.get("max_notional_per_order", 0)
    min_n = sizing.get("min_notional_per_order", 0)
    if max_n > 0:
        notional = min(notional, max_n)
    if min_n > 0:
        notional = max(notional, min_n)

    if current_price <= 0:
        return 0

    qty = notional / current_price

    return qty


def get_effective_params(db: Session, asset_id: int) -> dict:
    """
    종목의 effective_params 조회 (deep_merge 수행)

    Args:
        db: 데이터베이스 세션
        asset_id: 종목 ID

    Returns:
        머지된 effective_params
    """
    from app.utils.merge import deep_merge, DEFAULT_SIGNAL_PARAMS

    row = db.execute(text("""
        SELECT
            a.signal_params_override,
            s.signal_params
        FROM assets a
        JOIN strategies s ON a.strategy_id = s.id
        WHERE a.id = :id
    """), {"id": asset_id}).mappings().first()

    if not row:
        return DEFAULT_SIGNAL_PARAMS.copy()

    base_params = row["signal_params"] or DEFAULT_SIGNAL_PARAMS
    override_params = row["signal_params_override"]

    return deep_merge(base_params, override_params)


def determine_signal_type(action: str, current_position_qty: float = 0) -> str:
    """
    웹훅 action에서 signal_type 결정

    Args:
        action: buy, sell, close, reduce 등
        current_position_qty: 현재 포지션 수량

    Returns:
        OPEN | REDUCE | CLOSE
    """
    action_lower = action.lower() if action else ""

    if action_lower in ("close", "close_all", "exit"):
        return "CLOSE"
    elif action_lower in ("reduce", "partial_close", "take_profit"):
        return "REDUCE"
    else:
        # buy/sell은 포지션 유무에 따라 OPEN 또는 추가진입
        return "OPEN"

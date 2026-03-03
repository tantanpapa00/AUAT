"""
토스페이먼츠 빌링 API 라우터 (명령서66)
- 카드 등록, 구독, 상태조회, 해지, 웹훅
"""
import os
import logging
from datetime import datetime, timezone
from typing import Optional
from fastapi import APIRouter, Request, HTTPException, Depends
from pydantic import BaseModel
import asyncpg

from app.services.billing import (
    issue_billing_key,
    charge_billing,
    generate_order_id,
    generate_customer_key,
    calculate_subscription_amount,
    get_next_billing_date,
    PLAN_PRICES,
    PLAN_NAMES,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/billing", tags=["billing"])

DATABASE_URL = os.getenv("DATABASE_URL", "")


async def get_db():
    """DB 연결"""
    conn = await asyncpg.connect(DATABASE_URL)
    try:
        yield conn
    finally:
        await conn.close()


async def get_current_user(request: Request):
    """현재 로그인 사용자 (JWT에서 추출)"""
    user = getattr(request.state, "user", None)
    if not user:
        raise HTTPException(status_code=401, detail="로그인이 필요합니다")
    return user


# === Request/Response Models ===

class CardRegisterRequest(BaseModel):
    auth_key: str  # 토스 SDK에서 받은 인증키


class SubscribeRequest(BaseModel):
    plan: str  # standard, pro, proplus, promax


class CardRegisterResponse(BaseModel):
    success: bool
    card_last4: Optional[str] = None
    card_company: Optional[str] = None
    message: Optional[str] = None


class SubscribeResponse(BaseModel):
    success: bool
    plan: Optional[str] = None
    amount: Optional[int] = None
    next_billing_at: Optional[str] = None
    message: Optional[str] = None


class SubscriptionStatusResponse(BaseModel):
    has_subscription: bool
    plan: str = "free"
    status: str = "none"
    card_last4: Optional[str] = None
    card_company: Optional[str] = None
    started_at: Optional[str] = None
    expires_at: Optional[str] = None
    next_billing_at: Optional[str] = None
    cancelled_at: Optional[str] = None


class CancelResponse(BaseModel):
    success: bool
    expires_at: Optional[str] = None
    message: Optional[str] = None


class ConfirmRequest(BaseModel):
    auth_key: str  # 토스 빌링 인증 후 받은 authKey
    customer_key: str  # 고객 키
    plan: str  # 구독할 플랜


class ConfirmResponse(BaseModel):
    success: bool
    plan: Optional[str] = None
    amount: Optional[int] = None
    next_billing_at: Optional[str] = None
    message: Optional[str] = None


# === Endpoints ===

@router.post("/card-register", response_model=CardRegisterResponse)
async def register_card(
    body: CardRegisterRequest,
    request: Request,
):
    """
    카드 등록 + 빌링키 발급
    1. 프론트에서 토스 SDK로 카드 인증 → authKey 발급
    2. authKey로 빌링키 발급
    3. DB에 빌링키 저장
    """
    user = await get_current_user(request)
    user_id = user.get("id")

    customer_key = generate_customer_key(user_id)

    # 토스 빌링키 발급
    result = await issue_billing_key(body.auth_key, customer_key)

    if result.get("error"):
        logger.error(f"카드 등록 실패 (user {user_id}): {result}")
        return CardRegisterResponse(
            success=False,
            message=result.get("message", "카드 등록에 실패했습니다")
        )

    billing_key = result.get("billingKey")
    card_number = result.get("cardNumber", "")
    card_last4 = card_number[-4:] if card_number else ""
    card_company = result.get("cardCompany", "")

    # DB에 저장 (subscriptions 테이블 upsert)
    conn = await asyncpg.connect(DATABASE_URL)
    try:
        await conn.execute("""
            INSERT INTO subscriptions (user_id, billing_key, customer_key, card_last4, card_company)
            VALUES ($1, $2, $3, $4, $5)
            ON CONFLICT (user_id) DO UPDATE SET
                billing_key = $2,
                customer_key = $3,
                card_last4 = $4,
                card_company = $5,
                updated_at = NOW()
        """, user_id, billing_key, customer_key, card_last4, card_company)
    finally:
        await conn.close()

    logger.info(f"카드 등록 성공 (user {user_id}): {card_company} ****{card_last4}")

    return CardRegisterResponse(
        success=True,
        card_last4=card_last4,
        card_company=card_company,
    )


@router.post("/subscribe", response_model=SubscribeResponse)
async def subscribe(
    body: SubscribeRequest,
    request: Request,
):
    """
    플랜 구독 (첫 결제 실행)
    1. 등록된 빌링키로 결제
    2. 성공 시 users.plan 업데이트 + subscriptions 업데이트
    """
    user = await get_current_user(request)
    user_id = user.get("id")
    plan = body.plan.lower()

    if plan not in PLAN_PRICES or plan == "free":
        raise HTTPException(status_code=400, detail="유효하지 않은 플랜입니다")

    conn = await asyncpg.connect(DATABASE_URL)
    try:
        # 빌링키 조회
        sub = await conn.fetchrow(
            "SELECT billing_key, customer_key FROM subscriptions WHERE user_id = $1",
            user_id
        )

        if not sub or not sub["billing_key"]:
            return SubscribeResponse(
                success=False,
                message="등록된 카드가 없습니다. 먼저 카드를 등록해주세요."
            )

        billing_key = sub["billing_key"]
        customer_key = sub["customer_key"]

        # 첫 결제 여부 확인
        existing_payment = await conn.fetchval(
            "SELECT COUNT(*) FROM payment_history WHERE user_id = $1 AND status = 'paid'",
            user_id
        )
        is_first = existing_payment == 0

        # 결제 금액 계산
        amount = calculate_subscription_amount(plan, is_first_payment=is_first)
        order_id = generate_order_id()
        order_name = f"QUBE System {PLAN_NAMES.get(plan, plan)} 구독"

        # payment_history 레코드 생성 (pending)
        await conn.execute("""
            INSERT INTO payment_history (user_id, order_id, amount, plan, status)
            VALUES ($1, $2, $3, $4, 'pending')
        """, user_id, order_id, amount, plan)

        # 토스 결제 실행
        result = await charge_billing(billing_key, customer_key, amount, order_id, order_name)

        if result.get("error"):
            # 결제 실패
            await conn.execute("""
                UPDATE payment_history SET status = 'failed', failure_reason = $2
                WHERE order_id = $1
            """, order_id, result.get("message", "결제 실패"))

            return SubscribeResponse(
                success=False,
                message=result.get("message", "결제에 실패했습니다")
            )

        # 결제 성공
        payment_key = result.get("paymentKey", "")
        now = datetime.now(timezone.utc)
        next_billing = get_next_billing_date(now)

        # payment_history 업데이트
        await conn.execute("""
            UPDATE payment_history SET status = 'paid', payment_key = $2, paid_at = $3
            WHERE order_id = $1
        """, order_id, payment_key, now)

        # subscription 업데이트
        subscription_id = await conn.fetchval(
            "SELECT id FROM subscriptions WHERE user_id = $1", user_id
        )

        await conn.execute("""
            UPDATE subscriptions SET
                plan = $2,
                status = 'active',
                started_at = COALESCE(started_at, $3),
                expires_at = $4,
                next_billing_at = $4,
                cancelled_at = NULL,
                updated_at = NOW()
            WHERE user_id = $1
        """, user_id, plan, now, next_billing)

        # payment_history에 subscription_id 연결
        await conn.execute("""
            UPDATE payment_history SET subscription_id = $2 WHERE order_id = $1
        """, order_id, subscription_id)

        # users.plan 업데이트
        await conn.execute("""
            UPDATE users SET plan = $2, plan_expires_at = $3, updated_at = NOW()
            WHERE id = $1
        """, user_id, plan, next_billing)

        logger.info(f"구독 성공 (user {user_id}): {plan}, {amount}원")

        return SubscribeResponse(
            success=True,
            plan=plan,
            amount=amount,
            next_billing_at=next_billing.isoformat(),
        )

    finally:
        await conn.close()


@router.get("/status", response_model=SubscriptionStatusResponse)
async def get_subscription_status(request: Request):
    """현재 구독 상태 조회"""
    user = await get_current_user(request)
    user_id = user.get("id")

    conn = await asyncpg.connect(DATABASE_URL)
    try:
        sub = await conn.fetchrow("""
            SELECT plan, status, card_last4, card_company,
                   started_at, expires_at, next_billing_at, cancelled_at
            FROM subscriptions WHERE user_id = $1
        """, user_id)

        if not sub:
            return SubscriptionStatusResponse(
                has_subscription=False,
                plan="free",
                status="none",
            )

        return SubscriptionStatusResponse(
            has_subscription=True,
            plan=sub["plan"],
            status=sub["status"],
            card_last4=sub["card_last4"],
            card_company=sub["card_company"],
            started_at=sub["started_at"].isoformat() if sub["started_at"] else None,
            expires_at=sub["expires_at"].isoformat() if sub["expires_at"] else None,
            next_billing_at=sub["next_billing_at"].isoformat() if sub["next_billing_at"] else None,
            cancelled_at=sub["cancelled_at"].isoformat() if sub["cancelled_at"] else None,
        )

    finally:
        await conn.close()


@router.post("/cancel", response_model=CancelResponse)
async def cancel_subscription(request: Request):
    """
    구독 해지 (즉시 해지 아님)
    - expires_at까지 서비스 이용 가능
    - next_billing_at에 자동결제 안 함
    """
    user = await get_current_user(request)
    user_id = user.get("id")

    conn = await asyncpg.connect(DATABASE_URL)
    try:
        sub = await conn.fetchrow(
            "SELECT status, expires_at FROM subscriptions WHERE user_id = $1",
            user_id
        )

        if not sub:
            return CancelResponse(success=False, message="구독 정보가 없습니다")

        if sub["status"] == "cancelled":
            return CancelResponse(success=False, message="이미 해지된 구독입니다")

        now = datetime.now(timezone.utc)

        await conn.execute("""
            UPDATE subscriptions SET
                status = 'cancelled',
                cancelled_at = $2,
                next_billing_at = NULL,
                updated_at = NOW()
            WHERE user_id = $1
        """, user_id, now)

        expires_at = sub["expires_at"]
        logger.info(f"구독 해지 (user {user_id}), expires_at: {expires_at}")

        return CancelResponse(
            success=True,
            expires_at=expires_at.isoformat() if expires_at else None,
            message=f"구독이 해지되었습니다. {expires_at.strftime('%Y-%m-%d') if expires_at else '만료일'}까지 이용 가능합니다."
        )

    finally:
        await conn.close()


@router.post("/webhook")
async def toss_webhook(request: Request):
    """
    토스 웹훅 수신
    - 자동결제 성공/실패 알림
    """
    body = await request.json()
    event_type = body.get("eventType", "")
    data = body.get("data", {})

    logger.info(f"토스 웹훅 수신: {event_type}")

    if event_type == "BILLING_PAYMENT_COMPLETED":
        # 자동결제 성공
        order_id = data.get("orderId", "")
        payment_key = data.get("paymentKey", "")

        conn = await asyncpg.connect(DATABASE_URL)
        try:
            await conn.execute("""
                UPDATE payment_history SET status = 'paid', payment_key = $2, paid_at = NOW()
                WHERE order_id = $1
            """, order_id, payment_key)
        finally:
            await conn.close()

    elif event_type == "BILLING_PAYMENT_FAILED":
        # 자동결제 실패
        order_id = data.get("orderId", "")
        message = data.get("message", "결제 실패")

        conn = await asyncpg.connect(DATABASE_URL)
        try:
            # 결제 실패 기록
            ph = await conn.fetchrow(
                "SELECT user_id FROM payment_history WHERE order_id = $1", order_id
            )

            if ph:
                await conn.execute("""
                    UPDATE payment_history SET status = 'failed', failure_reason = $2
                    WHERE order_id = $1
                """, order_id, message)

                # 구독 상태 past_due로 변경
                await conn.execute("""
                    UPDATE subscriptions SET status = 'past_due', updated_at = NOW()
                    WHERE user_id = $1
                """, ph["user_id"])

        finally:
            await conn.close()

    return {"status": "ok"}


@router.post("/confirm", response_model=ConfirmResponse)
async def confirm_billing(
    body: ConfirmRequest,
    request: Request,
):
    """
    빌링 인증 완료 후 결제 확정
    1. authKey로 빌링키 발급
    2. 빌링키로 첫 결제 실행
    3. 성공 시 구독 활성화
    """
    user = await get_current_user(request)
    user_id = user.get("id")
    plan = body.plan.lower()

    if plan not in PLAN_PRICES or plan == "free":
        return ConfirmResponse(success=False, message="유효하지 않은 플랜입니다")

    # 1. 빌링키 발급
    billing_result = await issue_billing_key(body.auth_key, body.customer_key)

    if billing_result.get("error"):
        logger.error(f"빌링키 발급 실패 (user {user_id}): {billing_result}")
        return ConfirmResponse(
            success=False,
            message=billing_result.get("message", "카드 등록에 실패했습니다")
        )

    billing_key = billing_result.get("billingKey")
    card_number = billing_result.get("cardNumber", "")
    card_last4 = card_number[-4:] if card_number else ""
    card_company = billing_result.get("cardCompany", "")

    conn = await asyncpg.connect(DATABASE_URL)
    try:
        # 2. subscriptions 테이블에 빌링키 저장
        await conn.execute("""
            INSERT INTO subscriptions (user_id, billing_key, customer_key, card_last4, card_company, plan)
            VALUES ($1, $2, $3, $4, $5, $6)
            ON CONFLICT (user_id) DO UPDATE SET
                billing_key = $2,
                customer_key = $3,
                card_last4 = $4,
                card_company = $5,
                updated_at = NOW()
        """, user_id, billing_key, body.customer_key, card_last4, card_company, plan)

        # 3. 첫 결제 여부 확인
        existing_payment = await conn.fetchval(
            "SELECT COUNT(*) FROM payment_history WHERE user_id = $1 AND status = 'paid'",
            user_id
        )
        is_first = existing_payment == 0

        # 4. 결제 금액 계산
        amount = calculate_subscription_amount(plan, is_first_payment=is_first)
        order_id = generate_order_id()
        order_name = f"QUBE System {PLAN_NAMES.get(plan, plan)} 구독"

        # 5. payment_history 레코드 생성
        await conn.execute("""
            INSERT INTO payment_history (user_id, order_id, amount, plan, status)
            VALUES ($1, $2, $3, $4, 'pending')
        """, user_id, order_id, amount, plan)

        # 6. 토스 결제 실행
        charge_result = await charge_billing(billing_key, body.customer_key, amount, order_id, order_name)

        if charge_result.get("error"):
            # 결제 실패
            await conn.execute("""
                UPDATE payment_history SET status = 'failed', failure_reason = $2
                WHERE order_id = $1
            """, order_id, charge_result.get("message", "결제 실패"))

            return ConfirmResponse(
                success=False,
                message=charge_result.get("message", "결제에 실패했습니다")
            )

        # 7. 결제 성공 처리
        payment_key = charge_result.get("paymentKey", "")
        now = datetime.now(timezone.utc)
        next_billing = get_next_billing_date(now)

        # payment_history 업데이트
        await conn.execute("""
            UPDATE payment_history SET status = 'paid', payment_key = $2, paid_at = $3
            WHERE order_id = $1
        """, order_id, payment_key, now)

        # subscription 업데이트
        subscription_id = await conn.fetchval(
            "SELECT id FROM subscriptions WHERE user_id = $1", user_id
        )

        await conn.execute("""
            UPDATE subscriptions SET
                plan = $2,
                status = 'active',
                started_at = COALESCE(started_at, $3),
                expires_at = $4,
                next_billing_at = $4,
                cancelled_at = NULL,
                updated_at = NOW()
            WHERE user_id = $1
        """, user_id, plan, now, next_billing)

        # payment_history에 subscription_id 연결
        await conn.execute("""
            UPDATE payment_history SET subscription_id = $2 WHERE order_id = $1
        """, order_id, subscription_id)

        # users.plan 업데이트
        await conn.execute("""
            UPDATE users SET plan = $2, plan_expires_at = $3, updated_at = NOW()
            WHERE id = $1
        """, user_id, plan, next_billing)

        logger.info(f"빌링 확정 성공 (user {user_id}): {plan}, {amount}원")

        return ConfirmResponse(
            success=True,
            plan=plan,
            amount=amount,
            next_billing_at=next_billing.isoformat(),
        )

    finally:
        await conn.close()


@router.get("/prices")
async def get_plan_prices():
    """플랜별 가격 조회"""
    return {
        "prices": PLAN_PRICES,
        "names": PLAN_NAMES,
    }

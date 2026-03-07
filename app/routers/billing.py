"""
포트원 V2 + NHN KCP 빌링 API 라우터
- 기존 토스페이먼츠 코드 교체
- 카드 등록(빌링키), 구독, 상태조회, 해지, 웹훅
"""
import os
import logging
from datetime import datetime, timezone
from typing import Optional
from fastapi import APIRouter, Request, HTTPException
from pydantic import BaseModel
import asyncpg

from app.services.portone import (
    pay_with_billing_key,
    get_billing_key_info,
    delete_billing_key,
    generate_payment_id,
    calculate_subscription_amount,
    get_next_billing_date,
    PLAN_PRICES,
    PLAN_NAMES,
    PORTONE_STORE_ID,
    PORTONE_CHANNEL_KEY,
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

class SubscribeRequest(BaseModel):
    """구독 요청 (포트원 SDK에서 빌링키 발급 후)"""
    billing_key: str  # 포트원 SDK에서 발급받은 빌링키
    plan: str  # standard, pro, proplus, promax


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


class PaymentHistoryItem(BaseModel):
    date: str
    amount: int
    plan: str
    status: str


class PaymentHistoryResponse(BaseModel):
    payments: list[PaymentHistoryItem]


# === Endpoints ===

@router.get("/config")
async def get_billing_config():
    """포트원 SDK 설정 정보 (프론트에서 사용)"""
    return {
        "storeId": PORTONE_STORE_ID,
        "channelKey": PORTONE_CHANNEL_KEY,
    }


@router.post("/subscribe", response_model=SubscribeResponse)
async def subscribe(
    body: SubscribeRequest,
    request: Request,
):
    """
    구독 시작 (포트원 SDK에서 빌링키 발급 후 호출)
    1. 프론트에서 포트원 SDK로 빌링키 발급
    2. 빌링키로 첫 결제 실행
    3. 성공 시 users.plan 업데이트 + subscriptions 저장
    """
    user = await get_current_user(request)
    user_id = user.get("id")
    plan = body.plan.lower()

    if plan not in PLAN_PRICES or plan == "free":
        raise HTTPException(status_code=400, detail="유효하지 않은 플랜입니다")

    billing_key = body.billing_key
    if not billing_key:
        return SubscribeResponse(
            success=False,
            message="빌링키가 없습니다. 카드를 다시 등록해주세요."
        )

    conn = await asyncpg.connect(DATABASE_URL)
    try:
        # 빌링키 정보 조회 (카드 정보 추출)
        billing_info = await get_billing_key_info(billing_key)
        if billing_info.get("error"):
            logger.warning(f"빌링키 조회 실패, 계속 진행: {billing_info}")
            card_last4 = ""
            card_company = ""
        else:
            # 포트원 빌링키 응답에서 카드 정보 추출
            methods = billing_info.get("methods", [])
            if methods and len(methods) > 0:
                card_info = methods[0].get("card", {})
                card_number = card_info.get("number", "")
                card_last4 = card_number[-4:] if card_number else ""
                card_company = card_info.get("issuer", {}).get("name", "") or card_info.get("publisher", {}).get("name", "")
            else:
                card_last4 = ""
                card_company = ""

        # 첫 결제 여부 확인
        existing_payment = await conn.fetchval(
            "SELECT COUNT(*) FROM payment_history WHERE user_id = $1 AND status = 'paid'",
            user_id
        )
        is_first = existing_payment == 0

        # 결제 금액 계산
        amount = calculate_subscription_amount(plan, is_first_payment=is_first)
        payment_id = generate_payment_id()
        order_name = f"QUBE System {PLAN_NAMES.get(plan, plan)} 구독"

        # 사용자 정보 조회
        user_info = await conn.fetchrow(
            "SELECT email, name FROM users WHERE id = $1", user_id
        )
        customer_email = user_info["email"] if user_info else ""
        customer_name = user_info["name"] if user_info else "BBooster사용자"

        # payment_history 레코드 생성 (pending)
        await conn.execute("""
            INSERT INTO payment_history (user_id, order_id, amount, plan, status)
            VALUES ($1, $2, $3, $4, 'pending')
        """, user_id, payment_id, amount, plan)

        # 포트원 결제 실행
        result = await pay_with_billing_key(
            billing_key=billing_key,
            payment_id=payment_id,
            amount=amount,
            order_name=order_name,
            customer_id=str(user_id),
            customer_name=customer_name,
            customer_email=customer_email
        )

        if result.get("error"):
            # 결제 실패
            await conn.execute("""
                UPDATE payment_history SET status = 'failed', failure_reason = $2
                WHERE order_id = $1
            """, payment_id, result.get("message", "결제 실패"))

            return SubscribeResponse(
                success=False,
                message=result.get("message", "결제에 실패했습니다")
            )

        # 결제 성공
        now = datetime.now(timezone.utc)
        next_billing = get_next_billing_date(now)

        # payment_history 업데이트
        await conn.execute("""
            UPDATE payment_history SET status = 'paid', payment_key = $2, paid_at = $3
            WHERE order_id = $1
        """, payment_id, payment_id, now)

        # subscription upsert
        await conn.execute("""
            INSERT INTO subscriptions (user_id, billing_key, customer_key, card_last4, card_company, plan, status, started_at, expires_at, next_billing_at)
            VALUES ($1, $2, $3, $4, $5, $6, 'active', $7, $8, $8)
            ON CONFLICT (user_id) DO UPDATE SET
                billing_key = $2,
                card_last4 = $4,
                card_company = $5,
                plan = $6,
                status = 'active',
                started_at = COALESCE(subscriptions.started_at, $7),
                expires_at = $8,
                next_billing_at = $8,
                cancelled_at = NULL,
                updated_at = NOW()
        """, user_id, billing_key, f"QUBE_USER_{user_id}", card_last4, card_company, plan, now, next_billing)

        # subscription_id 조회 후 payment_history 연결
        subscription_id = await conn.fetchval(
            "SELECT id FROM subscriptions WHERE user_id = $1", user_id
        )
        await conn.execute("""
            UPDATE payment_history SET subscription_id = $2 WHERE order_id = $1
        """, payment_id, subscription_id)

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
            plan=sub["plan"] or "free",
            status=sub["status"] or "none",
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
    - 빌링키 삭제
    """
    user = await get_current_user(request)
    user_id = user.get("id")

    conn = await asyncpg.connect(DATABASE_URL)
    try:
        sub = await conn.fetchrow(
            "SELECT status, expires_at, billing_key FROM subscriptions WHERE user_id = $1",
            user_id
        )

        if not sub:
            return CancelResponse(success=False, message="구독 정보가 없습니다")

        if sub["status"] == "cancelled":
            return CancelResponse(success=False, message="이미 해지된 구독입니다")

        now = datetime.now(timezone.utc)

        # 빌링키 삭제 (포트원)
        if sub["billing_key"]:
            try:
                await delete_billing_key(sub["billing_key"])
            except Exception as e:
                logger.warning(f"빌링키 삭제 실패 (계속 진행): {e}")

        await conn.execute("""
            UPDATE subscriptions SET
                status = 'cancelled',
                cancelled_at = $2,
                next_billing_at = NULL,
                billing_key = NULL,
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


@router.get("/history", response_model=PaymentHistoryResponse)
async def get_payment_history(request: Request):
    """결제 내역 조회"""
    user = await get_current_user(request)
    user_id = user.get("id")

    conn = await asyncpg.connect(DATABASE_URL)
    try:
        rows = await conn.fetch("""
            SELECT paid_at, amount, plan, status
            FROM payment_history
            WHERE user_id = $1
            ORDER BY created_at DESC
            LIMIT 50
        """, user_id)

        payments = []
        for row in rows:
            payments.append(PaymentHistoryItem(
                date=row["paid_at"].isoformat() if row["paid_at"] else "",
                amount=row["amount"] or 0,
                plan=row["plan"] or "",
                status=row["status"] or ""
            ))

        return PaymentHistoryResponse(payments=payments)

    finally:
        await conn.close()


@router.post("/webhook")
async def portone_webhook(request: Request):
    """
    포트원 웹훅 수신
    - 자동결제 성공/실패 알림
    """
    body = await request.json()
    event_type = body.get("type", "")
    data = body.get("data", {})

    logger.info(f"포트원 웹훅 수신: {event_type}")

    if event_type == "Transaction.Paid":
        # 결제 성공
        payment_id = data.get("paymentId", "")

        conn = await asyncpg.connect(DATABASE_URL)
        try:
            await conn.execute("""
                UPDATE payment_history SET status = 'paid', paid_at = NOW()
                WHERE order_id = $1
            """, payment_id)
        finally:
            await conn.close()

    elif event_type == "Transaction.Failed":
        # 결제 실패
        payment_id = data.get("paymentId", "")
        message = data.get("failure", {}).get("message", "결제 실패")

        conn = await asyncpg.connect(DATABASE_URL)
        try:
            ph = await conn.fetchrow(
                "SELECT user_id FROM payment_history WHERE order_id = $1", payment_id
            )

            if ph:
                await conn.execute("""
                    UPDATE payment_history SET status = 'failed', failure_reason = $2
                    WHERE order_id = $1
                """, payment_id, message)

                # 구독 상태 past_due로 변경
                await conn.execute("""
                    UPDATE subscriptions SET status = 'past_due', updated_at = NOW()
                    WHERE user_id = $1
                """, ph["user_id"])

        finally:
            await conn.close()

    elif event_type == "Transaction.Cancelled":
        # 결제 취소
        payment_id = data.get("paymentId", "")

        conn = await asyncpg.connect(DATABASE_URL)
        try:
            await conn.execute("""
                UPDATE payment_history SET status = 'cancelled'
                WHERE order_id = $1
            """, payment_id)
        finally:
            await conn.close()

    return {"status": "ok"}


@router.get("/prices")
async def get_plan_prices():
    """플랜별 가격 조회"""
    return {
        "prices": PLAN_PRICES,
        "names": PLAN_NAMES,
    }

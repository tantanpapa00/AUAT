"""
포트원 V2 + NHN KCP 빌링 API 서비스
- 기존 토스페이먼츠 코드 교체
- 빌링키 발급, 자동결제, 결제 취소
"""
import httpx
import os
import logging
import uuid
from datetime import datetime, timedelta
from typing import Optional, Dict, Any

logger = logging.getLogger(__name__)

# 포트원 API 설정
PORTONE_API_URL = "https://api.portone.io"
PORTONE_API_SECRET = os.getenv("PORTONE_API_SECRET", "")
PORTONE_STORE_ID = os.getenv("PORTONE_STORE_ID", "store-c7371fef-c966-442e-a7f4-7ff3f568b3f9")
PORTONE_CHANNEL_KEY = os.getenv("PORTONE_CHANNEL_KEY", "channel-key-56bec8c5-8208-4612-8239-f595c1fd8844")

# 플랜별 가격 (원) - 기존 코드와 호환
PLAN_PRICES = {
    "free": 0,
    "standard": 19900,
    "pro": 99000,
    "proplus": 149000,
    "promax": 249000,
}

# 플랜 표시명
PLAN_NAMES = {
    "free": "Free",
    "standard": "Standard",
    "pro": "Pro",
    "proplus": "Pro+",
    "promax": "Pro Max",
}


def _headers() -> Dict[str, str]:
    """포트원 API 헤더"""
    return {
        "Authorization": f"PortOne {PORTONE_API_SECRET}",
        "Content-Type": "application/json"
    }


def generate_payment_id() -> str:
    """고유 결제 ID 생성"""
    return f"pay_{datetime.now().strftime('%Y%m%d%H%M%S')}_{uuid.uuid4().hex[:8]}"


def generate_billing_key_id(user_id: int) -> str:
    """빌링키 ID 생성"""
    return f"bk_{user_id}_{uuid.uuid4().hex[:8]}"


def generate_customer_key(user_id: int) -> str:
    """고객키 생성 (기존 코드 호환)"""
    return f"QUBE_USER_{user_id}"


async def get_billing_key_info(billing_key: str) -> Dict[str, Any]:
    """
    빌링키 정보 조회
    - 프론트에서 SDK로 빌링키 발급 후 서버에서 확인용
    """
    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.get(
            f"{PORTONE_API_URL}/billing-keys/{billing_key}",
            headers=_headers()
        )
        result = resp.json()

        if resp.status_code != 200:
            logger.error(f"빌링키 조회 실패: {result}")
            return {"error": True, "code": result.get("code"), "message": result.get("message")}

        return result


async def pay_with_billing_key(
    billing_key: str,
    payment_id: str,
    amount: int,
    order_name: str,
    customer_id: str,
    customer_name: str = "",
    customer_email: str = ""
) -> Dict[str, Any]:
    """
    빌링키로 결제 실행 (정기결제)

    Args:
        billing_key: 발급된 빌링키
        payment_id: 고유 결제 ID (generate_payment_id()로 생성)
        amount: 결제 금액 (원)
        order_name: 주문명
        customer_id: 고객 식별자
        customer_name: 고객명
        customer_email: 고객 이메일

    Returns:
        성공 시: {"status": "PAID", "paymentId": "...", ...}
        실패 시: {"error": True, "code": "...", "message": "..."}
    """
    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.post(
            f"{PORTONE_API_URL}/payments/{payment_id}/billing-key",
            headers=_headers(),
            json={
                "billingKey": billing_key,
                "orderName": order_name,
                "amount": {"total": amount},
                "currency": "KRW",
                "customer": {
                    "id": customer_id,
                    "name": customer_name or "BBooster사용자",
                    "email": customer_email or ""
                }
            }
        )
        result = resp.json()

        if resp.status_code not in (200, 201):
            logger.error(f"빌링 결제 실패 ({payment_id}): {result}")
            return {"error": True, "code": result.get("code"), "message": result.get("message")}

        logger.info(f"빌링 결제 성공: {payment_id}, {amount}원")
        return result


async def get_payment(payment_id: str) -> Dict[str, Any]:
    """결제 조회"""
    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.get(
            f"{PORTONE_API_URL}/payments/{payment_id}",
            headers=_headers()
        )
        return resp.json()


async def cancel_payment(payment_id: str, reason: str = "구독 해지") -> Dict[str, Any]:
    """결제 취소 (환불)"""
    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.post(
            f"{PORTONE_API_URL}/payments/{payment_id}/cancel",
            headers=_headers(),
            json={"reason": reason}
        )
        result = resp.json()

        if resp.status_code not in (200, 201):
            logger.error(f"결제 취소 실패 ({payment_id}): {result}")
            return {"error": True, "code": result.get("code"), "message": result.get("message")}

        logger.info(f"결제 취소 성공: {payment_id}")
        return result


async def delete_billing_key(billing_key: str) -> Dict[str, Any]:
    """빌링키 삭제 (카드 해지)"""
    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.delete(
            f"{PORTONE_API_URL}/billing-keys/{billing_key}",
            headers=_headers()
        )
        result = resp.json() if resp.text else {}

        if resp.status_code not in (200, 204):
            logger.error(f"빌링키 삭제 실패: {result}")
            return {"error": True, "code": result.get("code"), "message": result.get("message")}

        logger.info(f"빌링키 삭제 성공: {billing_key}")
        return {"success": True}


def calculate_subscription_amount(plan: str, is_first_payment: bool = False) -> int:
    """
    구독 결제 금액 계산
    - 첫 결제 30% 할인 적용
    """
    base_price = PLAN_PRICES.get(plan, 0)
    if base_price == 0:
        return 0

    if is_first_payment:
        # 첫 결제 30% 할인
        discount = int(base_price * 0.3)
        return base_price - discount

    return base_price


def get_next_billing_date(from_date: Optional[datetime] = None) -> datetime:
    """다음 결제일 계산 (30일 후)"""
    base = from_date or datetime.now()
    return base + timedelta(days=30)

"""
토스페이먼츠 빌링 API 서비스 (명령서66)
- SDK v2, 테스트 모드
- 빌링키 발급, 자동결제
"""
import httpx
import base64
import os
import uuid
import logging
from datetime import datetime, timedelta
from typing import Optional, Dict, Any

logger = logging.getLogger(__name__)

TOSS_CLIENT_KEY = os.getenv("TOSS_CLIENT_KEY", "")
TOSS_SECRET_KEY = os.getenv("TOSS_SECRET_KEY", "")
TOSS_BASE_URL = "https://api.tosspayments.com/v1/billing"

# 플랜별 가격 (원)
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


def _auth_header() -> Dict[str, str]:
    """토스 Basic Auth 헤더 생성"""
    if not TOSS_SECRET_KEY:
        raise ValueError("TOSS_SECRET_KEY 환경변수가 설정되지 않았습니다")
    encoded = base64.b64encode(f"{TOSS_SECRET_KEY}:".encode()).decode()
    return {
        "Authorization": f"Basic {encoded}",
        "Content-Type": "application/json",
    }


def generate_order_id() -> str:
    """주문번호 생성 (UUID 기반)"""
    return f"QUBE-{datetime.now().strftime('%Y%m%d')}-{uuid.uuid4().hex[:12].upper()}"


def generate_customer_key(user_id: int) -> str:
    """고객키 생성 (user_id 기반)"""
    return f"QUBE_USER_{user_id}"


async def issue_billing_key(auth_key: str, customer_key: str) -> Dict[str, Any]:
    """
    카드 등록 후 빌링키 발급
    - auth_key: 프론트에서 토스 SDK로 카드 등록 후 받은 인증키
    - customer_key: 고객 식별자

    Returns:
        {
            "mId": "상점ID",
            "customerKey": "고객키",
            "billingKey": "빌링키",
            "method": "카드",
            "cardCompany": "카드사",
            "cardNumber": "마스킹된 카드번호",
            "authenticatedAt": "인증시간"
        }
    """
    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.post(
            f"{TOSS_BASE_URL}/authorizations/issue",
            headers=_auth_header(),
            json={
                "authKey": auth_key,
                "customerKey": customer_key,
            }
        )
        result = resp.json()

        if resp.status_code != 200:
            logger.error(f"빌링키 발급 실패: {result}")
            return {"error": True, "code": result.get("code"), "message": result.get("message")}

        logger.info(f"빌링키 발급 성공: {customer_key}")
        return result


async def charge_billing(
    billing_key: str,
    customer_key: str,
    amount: int,
    order_id: str,
    order_name: str
) -> Dict[str, Any]:
    """
    빌링키로 자동결제 실행

    Returns:
        성공 시: {"paymentKey": "...", "orderId": "...", ...}
        실패 시: {"error": True, "code": "...", "message": "..."}
    """
    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.post(
            f"{TOSS_BASE_URL}/{billing_key}",
            headers=_auth_header(),
            json={
                "customerKey": customer_key,
                "amount": amount,
                "orderId": order_id,
                "orderName": order_name,
            }
        )
        result = resp.json()

        if resp.status_code != 200:
            logger.error(f"자동결제 실패: {order_id} - {result}")
            return {"error": True, "code": result.get("code"), "message": result.get("message")}

        logger.info(f"자동결제 성공: {order_id}, {amount}원")
        return result


async def get_billing_info(billing_key: str, customer_key: str) -> Dict[str, Any]:
    """빌링키 정보 조회"""
    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.get(
            f"{TOSS_BASE_URL}/{billing_key}",
            headers=_auth_header(),
            params={"customerKey": customer_key}
        )
        return resp.json()


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

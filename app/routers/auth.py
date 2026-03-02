"""
인증 라우터 (명령서64)
- 카카오 OAuth
- 약관 동의 시스템
- 가입 완료 처리
"""
import os
import httpx
from datetime import datetime, timedelta, timezone
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session
from sqlalchemy import text
from pydantic import BaseModel
from jose import jwt, JWTError

from app.db import get_db
from app.models import User
from app.auth import (
    JWT_SECRET_KEY, JWT_ALGORITHM, ADMIN_EMAILS,
    create_tokens_for_user, hash_password
)

router = APIRouter(tags=["auth"])

# =====================================================
# 환경 변수
# =====================================================
KAKAO_CLIENT_ID = os.getenv("KAKAO_CLIENT_ID", "")
KAKAO_CLIENT_SECRET = os.getenv("KAKAO_CLIENT_SECRET", "")
BASE_URL = os.getenv("BASE_URL", "https://qube-system.com")
FRONTEND_URL = os.getenv("FRONTEND_URL", "/")

# =====================================================
# Pydantic 모델
# =====================================================
class CompleteSignupRequest(BaseModel):
    """가입 완료 요청 (약관 동의 포함)"""
    token: str  # 임시 가입 토큰
    terms_agreed: bool
    privacy_agreed: bool
    age_confirmed: bool
    investment_risk_agreed: bool
    marketing_agreed: bool = False


class TermsResponse(BaseModel):
    """약관 정보 응답"""
    title: str
    version: str
    summary: str
    url: str


# =====================================================
# 임시 가입 토큰 (약관 동의 전)
# =====================================================
def create_temp_signup_token(social_data: dict) -> str:
    """약관 동의 전 소셜 로그인 정보를 담은 임시 토큰 (10분 만료)."""
    payload = {
        **social_data,
        "purpose": "signup",
        "exp": datetime.now(timezone.utc) + timedelta(minutes=10)
    }
    return jwt.encode(payload, JWT_SECRET_KEY, algorithm=JWT_ALGORITHM)


def verify_temp_signup_token(token: str) -> dict:
    """임시 가입 토큰 검증."""
    try:
        payload = jwt.decode(token, JWT_SECRET_KEY, algorithms=[JWT_ALGORITHM])
        if payload.get("purpose") != "signup":
            raise ValueError("Invalid token purpose")
        return payload
    except JWTError as e:
        raise ValueError(f"Token verification failed: {e}")


# =====================================================
# 약관 동의 저장
# =====================================================
async def save_user_consent(
    db: Session,
    user_id: int,
    terms_agreed: bool,
    privacy_agreed: bool,
    age_confirmed: bool,
    investment_risk_agreed: bool,
    marketing_agreed: bool
):
    """사용자 약관 동의 기록 저장."""
    # 테이블 확인/생성
    db.execute(text("""
        CREATE TABLE IF NOT EXISTS user_consents (
            id SERIAL PRIMARY KEY,
            user_id INTEGER NOT NULL,
            terms_agreed BOOLEAN NOT NULL DEFAULT FALSE,
            privacy_agreed BOOLEAN NOT NULL DEFAULT FALSE,
            age_confirmed BOOLEAN NOT NULL DEFAULT FALSE,
            investment_risk_agreed BOOLEAN NOT NULL DEFAULT FALSE,
            marketing_agreed BOOLEAN NOT NULL DEFAULT FALSE,
            agreed_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
            terms_version VARCHAR(20) DEFAULT '1.0',
            privacy_version VARCHAR(20) DEFAULT '1.0'
        )
    """))
    db.execute(text("""
        CREATE INDEX IF NOT EXISTS idx_user_consents_user_id ON user_consents(user_id)
    """))

    # 동의 기록 저장
    db.execute(text("""
        INSERT INTO user_consents (
            user_id, terms_agreed, privacy_agreed, age_confirmed,
            investment_risk_agreed, marketing_agreed
        ) VALUES (
            :user_id, :terms_agreed, :privacy_agreed, :age_confirmed,
            :investment_risk_agreed, :marketing_agreed
        )
    """), {
        "user_id": user_id,
        "terms_agreed": terms_agreed,
        "privacy_agreed": privacy_agreed,
        "age_confirmed": age_confirmed,
        "investment_risk_agreed": investment_risk_agreed,
        "marketing_agreed": marketing_agreed
    })
    db.commit()


# =====================================================
# 카카오 OAuth
# =====================================================
@router.get("/api/auth/kakao/login")
async def kakao_login():
    """카카오 로그인 페이지로 리다이렉트."""
    if not KAKAO_CLIENT_ID:
        raise HTTPException(status_code=500, detail="카카오 OAuth가 설정되지 않았습니다")

    redirect_uri = f"{BASE_URL}/api/auth/kakao/callback"
    kakao_auth_url = (
        f"https://kauth.kakao.com/oauth/authorize"
        f"?client_id={KAKAO_CLIENT_ID}"
        f"&redirect_uri={redirect_uri}"
        f"&response_type=code"
        f"&scope=profile_nickname,account_email"
    )
    return RedirectResponse(url=kakao_auth_url)


@router.get("/api/auth/kakao/callback")
async def kakao_callback(
    code: str = Query(...),
    db: Session = Depends(get_db)
):
    """카카오 인증 코드 → 토큰 교환 → 사용자 처리."""
    if not KAKAO_CLIENT_ID:
        raise HTTPException(status_code=500, detail="카카오 OAuth가 설정되지 않았습니다")

    redirect_uri = f"{BASE_URL}/api/auth/kakao/callback"

    try:
        async with httpx.AsyncClient() as client:
            # 1. 인증 코드 → 액세스 토큰
            token_resp = await client.post(
                "https://kauth.kakao.com/oauth/token",
                data={
                    "grant_type": "authorization_code",
                    "client_id": KAKAO_CLIENT_ID,
                    "client_secret": KAKAO_CLIENT_SECRET,
                    "redirect_uri": redirect_uri,
                    "code": code
                },
                headers={"Content-Type": "application/x-www-form-urlencoded"}
            )

            if token_resp.status_code != 200:
                raise HTTPException(
                    status_code=400,
                    detail=f"카카오 토큰 교환 실패: {token_resp.text}"
                )

            token_data = token_resp.json()
            access_token = token_data.get("access_token")

            # 2. 사용자 정보 조회
            user_resp = await client.get(
                "https://kapi.kakao.com/v2/user/me",
                headers={"Authorization": f"Bearer {access_token}"}
            )

            if user_resp.status_code != 200:
                raise HTTPException(
                    status_code=400,
                    detail=f"카카오 사용자 정보 조회 실패: {user_resp.text}"
                )

            kakao_user = user_resp.json()

        # 3. 사용자 정보 추출
        kakao_id = str(kakao_user.get("id"))
        kakao_account = kakao_user.get("kakao_account", {})
        email = kakao_account.get("email")
        profile = kakao_account.get("profile", {})
        nickname = profile.get("nickname", "")
        picture = profile.get("profile_image_url", "")

        # 4. 기존 사용자 확인
        user = None

        # kakao_id로 검색
        user = db.query(User).filter(User.kakao_id == kakao_id).first()

        # 이메일로 검색 (kakao_id 없는 경우)
        if not user and email:
            user = db.query(User).filter(User.email == email.lower()).first()
            if user:
                # 기존 사용자에 kakao_id 연결
                user.kakao_id = kakao_id
                if nickname and not user.name:
                    user.name = nickname
                if picture and not user.picture:
                    user.picture = picture
                user.last_login_at = datetime.now(timezone.utc)
                db.commit()
                db.refresh(user)

        # 5. 신규 사용자 → 약관 동의 페이지로
        if not user:
            temp_token = create_temp_signup_token({
                "provider": "kakao",
                "provider_id": kakao_id,
                "email": email,
                "nickname": nickname,
                "picture": picture
            })
            # 약관 동의 페이지로 리다이렉트
            return RedirectResponse(url=f"{FRONTEND_URL}?signup=consent&token={temp_token}")

        # 6. 기존 사용자 → 바로 로그인
        user.last_login_at = datetime.now(timezone.utc)
        db.commit()

        tokens = create_tokens_for_user(user)
        return RedirectResponse(
            url=f"{FRONTEND_URL}?access_token={tokens.access_token}&refresh_token={tokens.refresh_token}"
        )

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"카카오 인증 실패: {str(e)}")


# =====================================================
# 가입 완료 (약관 동의 후)
# =====================================================
@router.post("/api/auth/complete-signup")
async def complete_signup(
    request: CompleteSignupRequest,
    db: Session = Depends(get_db)
):
    """약관 동의 후 회원 가입 완료."""
    # 1. 필수 동의 확인
    if not all([
        request.terms_agreed,
        request.privacy_agreed,
        request.age_confirmed,
        request.investment_risk_agreed
    ]):
        raise HTTPException(status_code=400, detail="필수 약관에 모두 동의해야 합니다")

    # 2. 임시 토큰에서 소셜 정보 추출
    try:
        social_data = verify_temp_signup_token(request.token)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    provider = social_data.get("provider")
    provider_id = social_data.get("provider_id")
    email = social_data.get("email", "")
    nickname = social_data.get("nickname", "")
    picture = social_data.get("picture", "")

    # 3. 이메일 중복 확인
    if email:
        existing = db.query(User).filter(User.email == email.lower()).first()
        if existing:
            raise HTTPException(status_code=400, detail="이미 등록된 이메일입니다")

    # 4. 관리자 확인
    role = "admin" if email and email.lower() in ADMIN_EMAILS else "user"

    # 5. 사용자 생성
    new_user = User(
        email=email.lower() if email else f"{provider}_{provider_id}@bbooster.temp",
        name=nickname or (email.split("@")[0] if email else f"{provider}_user"),
        picture=picture,
        role=role,
        plan="free",
        last_login_at=datetime.now(timezone.utc),
    )

    # Provider별 ID 설정
    if provider == "kakao":
        new_user.kakao_id = provider_id
    elif provider == "google":
        new_user.google_id = provider_id

    db.add(new_user)
    db.commit()
    db.refresh(new_user)

    # 6. 동의 기록 저장
    await save_user_consent(
        db=db,
        user_id=new_user.id,
        terms_agreed=request.terms_agreed,
        privacy_agreed=request.privacy_agreed,
        age_confirmed=request.age_confirmed,
        investment_risk_agreed=request.investment_risk_agreed,
        marketing_agreed=request.marketing_agreed
    )

    # 7. JWT 발급
    tokens = create_tokens_for_user(new_user)

    return {
        "success": True,
        "access_token": tokens.access_token,
        "refresh_token": tokens.refresh_token,
        "expires_in": tokens.expires_in,
        "user": {
            "id": new_user.id,
            "email": new_user.email,
            "name": new_user.name
        }
    }


# =====================================================
# 약관 내용 API (SSOT from data/policies/)
# =====================================================
from app.utils.policy_parser import parse_policy


# Summary texts for each policy type (used when full=false)
POLICY_SUMMARIES = {
    "terms": "BBooster 서비스 이용에 관한 기본 약관입니다.",
    "privacy": "수집하는 개인정보: 이메일, 거래소 API 키(암호화 저장)",
    "refund": "결제 후 7일 이내, 서비스 미이용 시 전액 환불 가능합니다.",
    "risk": "투자 판단과 결과 책임은 사용자에게 있으며, BBooster는 정보 제공 및 자동 실행 도구입니다.",
    "investment_risk": "투자 판단과 결과 책임은 사용자에게 있으며, BBooster는 정보 제공 및 자동 실행 도구입니다.",
}


@router.get("/api/auth/terms/{term_type}")
async def get_terms(term_type: str, full: bool = False):
    """
    약관 내용 조회 (SSOT: data/policies/*.md).
    type: terms, privacy, refund, risk, investment_risk
    full=true면 전문(content_md) 반환.
    """
    # Parse policy from SSOT markdown file
    doc = parse_policy(term_type)

    if not doc:
        raise HTTPException(status_code=404, detail=f"약관을 찾을 수 없습니다: {term_type}")

    # Base response
    response = {
        "ok": True,
        "type": doc.type,
        "title": doc.title,
        "effective_date": doc.effective_date,
        "version": doc.version,
        "last_updated": doc.last_updated,
        "url": f"/{doc.type}",
    }

    # Full content if requested
    if full:
        response["content_md"] = doc.content_md
        response["content_html"] = doc.content_html
    else:
        response["summary"] = POLICY_SUMMARIES.get(term_type, "")

    return response


# =====================================================
# 이메일 가입 (약관 동의 포함)
# =====================================================
class EmailRegisterRequest(BaseModel):
    """이메일 회원가입 요청 (약관 동의 포함)"""
    email: str
    password: str
    name: Optional[str] = None
    terms_agreed: bool
    privacy_agreed: bool
    age_confirmed: bool
    investment_risk_agreed: bool
    marketing_agreed: bool = False


@router.post("/api/auth/register-with-consent")
async def register_with_consent(
    request: EmailRegisterRequest,
    db: Session = Depends(get_db)
):
    """이메일/비밀번호 회원가입 (약관 동의 포함)."""
    # 1. 필수 동의 확인
    if not all([
        request.terms_agreed,
        request.privacy_agreed,
        request.age_confirmed,
        request.investment_risk_agreed
    ]):
        raise HTTPException(status_code=400, detail="필수 약관에 모두 동의해야 합니다")

    # 2. 이메일 중복 확인
    email = request.email.lower().strip()
    existing = db.query(User).filter(User.email == email).first()
    if existing:
        raise HTTPException(status_code=400, detail="이미 등록된 이메일입니다")

    # 3. 비밀번호 정책 확인
    password = request.password
    if len(password) < 12:
        raise HTTPException(status_code=400, detail="비밀번호는 12자리 이상이어야 합니다")

    import re
    if not re.search(r'[A-Za-z]', password):
        raise HTTPException(status_code=400, detail="비밀번호에 영문자를 포함해야 합니다")
    if not re.search(r'[0-9]', password):
        raise HTTPException(status_code=400, detail="비밀번호에 숫자를 포함해야 합니다")
    if not re.search(r'[!@#$%^&*()_+\-=\[\]{}|;:,.<>?/~`]', password):
        raise HTTPException(status_code=400, detail="비밀번호에 특수문자를 포함해야 합니다")

    # 4. 관리자 확인
    role = "admin" if email in ADMIN_EMAILS else "user"

    # 5. 사용자 생성
    new_user = User(
        email=email,
        name=request.name or email.split("@")[0],
        password_hash=hash_password(password),
        role=role,
        plan="free",
        last_login_at=datetime.now(timezone.utc),
    )
    db.add(new_user)
    db.commit()
    db.refresh(new_user)

    # 6. 동의 기록 저장
    await save_user_consent(
        db=db,
        user_id=new_user.id,
        terms_agreed=request.terms_agreed,
        privacy_agreed=request.privacy_agreed,
        age_confirmed=request.age_confirmed,
        investment_risk_agreed=request.investment_risk_agreed,
        marketing_agreed=request.marketing_agreed
    )

    # 7. JWT 발급
    tokens = create_tokens_for_user(new_user)

    return {
        "success": True,
        "access_token": tokens.access_token,
        "refresh_token": tokens.refresh_token,
        "expires_in": tokens.expires_in,
        "user": {
            "id": new_user.id,
            "email": new_user.email,
            "name": new_user.name
        }
    }


# =====================================================
# 인증 상태 확인
# =====================================================
@router.get("/api/auth/providers")
async def get_auth_providers():
    """사용 가능한 인증 방식 조회."""
    return {
        "success": True,
        "providers": {
            "google": bool(os.getenv("GOOGLE_CLIENT_ID")),
            "kakao": bool(KAKAO_CLIENT_ID),
            "email": True
        }
    }

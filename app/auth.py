"""
BBooster 인증 모듈
- 이메일/비밀번호 로그인 (자체 회원가입)
- Google OAuth 2.0 로그인
- JWT 기반 세션 관리
- 관리자 자동 지정
"""
import os
import re
from datetime import datetime, timedelta, timezone
from typing import Optional
from functools import wraps

from fastapi import Depends, HTTPException, status, Request
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from jose import JWTError, jwt
from pydantic import BaseModel, EmailStr, field_validator
from sqlalchemy.orm import Session
from authlib.integrations.starlette_client import OAuth

# bcrypt for password hashing
try:
    import bcrypt
    BCRYPT_AVAILABLE = True
except ImportError:
    BCRYPT_AVAILABLE = False
    # Fallback: use hashlib (less secure but works)
    import hashlib

from app.db import get_db
from app.models import User

# =====================================================
# 환경 변수
# =====================================================
GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID", "")
GOOGLE_CLIENT_SECRET = os.getenv("GOOGLE_CLIENT_SECRET", "")
JWT_SECRET_KEY = os.getenv("JWT_SECRET_KEY", "bbooster-secret-key-change-in-production")
JWT_ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24  # 24시간
REFRESH_TOKEN_EXPIRE_DAYS = 30

# 개발/테스트용: SKIP_AUTH=true 면 인증 우회
SKIP_AUTH = os.getenv("SKIP_AUTH", "").lower() in ("true", "1", "yes")

# 관리자 이메일 목록 (쉼표로 구분)
ADMIN_EMAILS = [
    email.strip().lower()
    for email in os.getenv("ADMIN_EMAILS", "").split(",")
    if email.strip()
]

# =====================================================
# OAuth 설정
# =====================================================
oauth = OAuth()

# Google OAuth 등록
if GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET:
    oauth.register(
        name="google",
        client_id=GOOGLE_CLIENT_ID,
        client_secret=GOOGLE_CLIENT_SECRET,
        server_metadata_url="https://accounts.google.com/.well-known/openid-configuration",
        client_kwargs={"scope": "openid email profile"},
    )

# =====================================================
# Pydantic 모델
# =====================================================
class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int


class UserResponse(BaseModel):
    id: int
    email: str
    name: Optional[str]
    picture: Optional[str]
    role: str
    plan: str
    plan_expires_at: Optional[datetime]
    created_at: datetime

    class Config:
        from_attributes = True


class TokenData(BaseModel):
    user_id: Optional[int] = None
    email: Optional[str] = None
    role: Optional[str] = None


class RegisterRequest(BaseModel):
    """회원가입 요청"""
    email: str
    password: str
    name: Optional[str] = None

    @field_validator('email')
    @classmethod
    def validate_email(cls, v):
        # 간단한 이메일 검증
        email_regex = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
        if not re.match(email_regex, v):
            raise ValueError('유효한 이메일 주소를 입력하세요')
        return v.lower()

    @field_validator('password')
    @classmethod
    def validate_password(cls, v):
        if len(v) < 6:
            raise ValueError('비밀번호는 최소 6자 이상이어야 합니다')
        return v


class LoginRequest(BaseModel):
    """로그인 요청"""
    email: str
    password: str

    @field_validator('email')
    @classmethod
    def normalize_email(cls, v):
        return v.lower().strip()


# =====================================================
# JWT 토큰 생성/검증
# =====================================================
def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    """액세스 토큰 생성"""
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + (expires_delta or timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES))
    to_encode.update({"exp": expire, "type": "access"})
    return jwt.encode(to_encode, JWT_SECRET_KEY, algorithm=JWT_ALGORITHM)


def create_refresh_token(data: dict) -> str:
    """리프레시 토큰 생성"""
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS)
    to_encode.update({"exp": expire, "type": "refresh"})
    return jwt.encode(to_encode, JWT_SECRET_KEY, algorithm=JWT_ALGORITHM)


def verify_token(token: str, expected_type: str = "access") -> Optional[TokenData]:
    """토큰 검증"""
    try:
        payload = jwt.decode(token, JWT_SECRET_KEY, algorithms=[JWT_ALGORITHM])
        if payload.get("type") != expected_type:
            return None
        user_id = payload.get("sub")
        email = payload.get("email")
        role = payload.get("role")
        if user_id is None:
            return None
        return TokenData(user_id=int(user_id), email=email, role=role)
    except JWTError:
        return None


def create_tokens_for_user(user: User) -> TokenResponse:
    """사용자에 대한 토큰 쌍 생성"""
    token_data = {"sub": str(user.id), "email": user.email, "role": user.role}
    access_token = create_access_token(token_data)
    refresh_token = create_refresh_token(token_data)
    return TokenResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        expires_in=ACCESS_TOKEN_EXPIRE_MINUTES * 60,
    )


# =====================================================
# 비밀번호 해싱 (bcrypt)
# =====================================================
def hash_password(password: str) -> str:
    """비밀번호 해시 생성"""
    if BCRYPT_AVAILABLE:
        salt = bcrypt.gensalt()
        return bcrypt.hashpw(password.encode('utf-8'), salt).decode('utf-8')
    else:
        # Fallback: SHA256 (bcrypt 미설치 시)
        return hashlib.sha256(password.encode('utf-8')).hexdigest()


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """비밀번호 검증"""
    if not hashed_password:
        return False
    if BCRYPT_AVAILABLE:
        try:
            return bcrypt.checkpw(
                plain_password.encode('utf-8'),
                hashed_password.encode('utf-8')
            )
        except Exception:
            return False
    else:
        # Fallback: SHA256
        return hashlib.sha256(plain_password.encode('utf-8')).hexdigest() == hashed_password


# =====================================================
# 자체 회원가입/로그인
# =====================================================
def register_user(
    db: Session,
    email: str,
    password: str,
    name: Optional[str] = None,
) -> User:
    """이메일/비밀번호로 회원가입"""
    email = email.lower().strip()

    # 이메일 중복 체크
    existing = db.query(User).filter(User.email == email).first()
    if existing:
        raise ValueError("이미 등록된 이메일입니다")

    # 관리자 이메일인지 확인
    role = "admin" if email in ADMIN_EMAILS else "user"

    # 사용자 생성
    new_user = User(
        email=email,
        name=name or email.split("@")[0],  # 이름 없으면 이메일 앞부분 사용
        password_hash=hash_password(password),
        role=role,
        plan="free",
        last_login_at=datetime.now(timezone.utc),
    )
    db.add(new_user)
    db.commit()
    db.refresh(new_user)
    return new_user


def authenticate_user(
    db: Session,
    email: str,
    password: str,
) -> Optional[User]:
    """이메일/비밀번호로 로그인 인증"""
    email = email.lower().strip()
    user = db.query(User).filter(User.email == email).first()

    if not user:
        return None

    # 비밀번호 확인 (password_hash가 있는 경우에만)
    if not user.password_hash:
        # Google OAuth로만 가입한 사용자
        return None

    if not verify_password(password, user.password_hash):
        return None

    # 마지막 로그인 시간 업데이트
    user.last_login_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(user)
    return user


# =====================================================
# 인증 의존성
# =====================================================
security = HTTPBearer(auto_error=False)


async def get_current_user_optional(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
    db: Session = Depends(get_db),
) -> Optional[User]:
    """현재 사용자 가져오기 (선택적 - 인증 없어도 None 반환)"""
    # SKIP_AUTH 모드: 개발용 사용자 반환
    if SKIP_AUTH:
        dev_user = db.query(User).filter(User.email == "dev@localhost").first()
        if not dev_user:
            dev_user = User(
                email="dev@localhost",
                name="개발자",
                role="admin",
                plan="premium",
            )
            db.add(dev_user)
            db.commit()
            db.refresh(dev_user)
        return dev_user

    # [DEBUG] 인증 정보 로그
    if credentials:
        token_preview = credentials.credentials[:20] + "..." if len(credentials.credentials) > 20 else credentials.credentials
        print(f"[AUTH DEBUG] credentials.scheme={credentials.scheme}, token={token_preview}")
    else:
        print("[AUTH DEBUG] credentials is None (no Authorization header)")

    if not credentials:
        return None

    token_data = verify_token(credentials.credentials)
    if not token_data or not token_data.user_id:
        print(f"[AUTH DEBUG] token_data invalid: {token_data}")
        return None

    user = db.query(User).filter(User.id == token_data.user_id).first()
    if user:
        print(f"[AUTH DEBUG] user found: id={user.id}, email={user.email}, role={user.role}, plan={user.plan}")
    else:
        print(f"[AUTH DEBUG] user not found for user_id={token_data.user_id}")
    return user


async def get_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
    db: Session = Depends(get_db),
) -> User:
    """현재 사용자 가져오기 (필수 - 인증 없으면 401)"""
    # SKIP_AUTH 모드: 개발/테스트용 우회
    if SKIP_AUTH:
        # 더미 사용자 반환 (개발용)
        dev_user = db.query(User).filter(User.email == "dev@localhost").first()
        if not dev_user:
            # 개발용 사용자 자동 생성
            dev_user = User(
                email="dev@localhost",
                name="개발자",
                role="admin",
                plan="premium",
            )
            db.add(dev_user)
            db.commit()
            db.refresh(dev_user)
        return dev_user

    if not credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="인증이 필요합니다",
            headers={"WWW-Authenticate": "Bearer"},
        )

    token_data = verify_token(credentials.credentials)
    if not token_data or not token_data.user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="유효하지 않은 토큰입니다",
            headers={"WWW-Authenticate": "Bearer"},
        )

    user = db.query(User).filter(User.id == token_data.user_id).first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="사용자를 찾을 수 없습니다",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return user


async def get_admin_user(current_user: User = Depends(get_current_user)) -> User:
    """관리자 전용 의존성"""
    if current_user.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="관리자 권한이 필요합니다",
        )
    return current_user


# =====================================================
# 사용자 생성/업데이트 (Google OAuth용)
# =====================================================
def get_or_create_user_from_google(
    db: Session,
    google_id: str,
    email: str,
    name: Optional[str],
    picture: Optional[str],
) -> User:
    """Google 로그인 후 사용자 생성 또는 조회"""
    # 이메일로 먼저 검색
    user = db.query(User).filter(User.email == email.lower()).first()

    if user:
        # 기존 사용자 - 정보 업데이트
        user.google_id = google_id
        if name:
            user.name = name
        if picture:
            user.picture = picture
        user.last_login_at = datetime.now(timezone.utc)
        db.commit()
        db.refresh(user)
        return user

    # 신규 사용자 생성
    # 관리자 이메일인지 확인
    role = "admin" if email.lower() in ADMIN_EMAILS else "user"

    new_user = User(
        email=email.lower(),
        name=name,
        picture=picture,
        google_id=google_id,
        role=role,
        plan="free",
        last_login_at=datetime.now(timezone.utc),
    )
    db.add(new_user)
    db.commit()
    db.refresh(new_user)
    return new_user


# =====================================================
# 인증 불필요 경로 목록
# =====================================================
PUBLIC_PATHS = [
    "/",
    "/ui",
    "/docs",
    "/redoc",
    "/openapi.json",
    "/api/health",
    "/api/auth/register",      # 자체 회원가입
    "/api/auth/login",         # 자체 로그인
    "/api/auth/google/login",
    "/api/auth/google/callback",
    "/api/auth/refresh",
    "/tv",  # TradingView webhook은 별도 인증 (TV_SECRET)
    "/landing",
]

PUBLIC_PATH_PREFIXES = [
    "/landing/",
    "/static/",
]


def is_public_path(path: str) -> bool:
    """인증이 필요 없는 경로인지 확인"""
    if path in PUBLIC_PATHS:
        return True
    for prefix in PUBLIC_PATH_PREFIXES:
        if path.startswith(prefix):
            return True
    return False

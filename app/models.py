from sqlalchemy.orm import DeclarativeBase
from sqlalchemy import Column, BigInteger, Text, Boolean, DateTime, ForeignKey, Float, Index, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.sql import func

class Base(DeclarativeBase):
    pass


class CandleCache(Base):
    """
    캔들 데이터 캐시 (PostgreSQL)
    백테스트용 캔들 데이터를 거래소에서 조회 후 저장하여 재사용
    """
    __tablename__ = "candles"

    id = Column(BigInteger, primary_key=True)
    exchange = Column(Text, nullable=False)   # OKX, BINANCE, BYBIT
    symbol = Column(Text, nullable=False)     # BTC-USDT
    timeframe = Column(Text, nullable=False)  # 1h, 4h, 1D
    ts = Column(BigInteger, nullable=False)   # timestamp (ms)
    o = Column(Float, nullable=False)         # open
    h = Column(Float, nullable=False)         # high
    l = Column(Float, nullable=False)         # low
    c = Column(Float, nullable=False)         # close
    v = Column(Float, nullable=False)         # volume
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    __table_args__ = (
        Index('ix_candles_lookup', 'exchange', 'symbol', 'timeframe', 'ts'),
        UniqueConstraint('exchange', 'symbol', 'timeframe', 'ts', name='uq_candles'),
    )

class Account(Base):
    __tablename__ = "accounts"

    id = Column(BigInteger, primary_key=True)
    name = Column(Text, nullable=False, unique=True)
    exchange = Column(Text, nullable=False)
    api_key = Column(Text, nullable=False)
    api_secret = Column(Text, nullable=False)
    api_passphrase = Column(Text, nullable=True)  # OKX용 passphrase
    account_number = Column(Text, nullable=True)  # KIS용 계좌번호 (CANO-ACNT_PRDT_CD)

    is_active = Column(Boolean, nullable=False, default=False)

    last_health_at = Column(DateTime(timezone=True), nullable=True)
    last_health_ok = Column(Boolean, nullable=True)
    last_health_msg = Column(Text, nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)


class User(Base):
    """
    사용자 모델 (이메일/비밀번호 + Google OAuth)
    """
    __tablename__ = "users"

    id = Column(BigInteger, primary_key=True)
    email = Column(Text, nullable=False, unique=True, index=True)
    name = Column(Text, nullable=True)
    picture = Column(Text, nullable=True)  # Google 프로필 사진 URL
    role = Column(Text, nullable=False, default="user")  # admin, user

    # 이메일/비밀번호 인증
    password_hash = Column(Text, nullable=True)  # bcrypt 해시 (자체 로그인용)

    # Google OAuth
    google_id = Column(Text, nullable=True, unique=True)

    # 구독 정보
    plan = Column(Text, nullable=False, default="free")  # free, hub, premium
    plan_expires_at = Column(DateTime(timezone=True), nullable=True)

    # 메타
    last_login_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)


class Event(Base):
    """
    타임라인 이벤트 모델 (Week 10)
    SSOT: docs/TIMELINE_SPEC.md
    """
    __tablename__ = "events"

    id = Column(BigInteger, primary_key=True)
    event_type = Column(Text, nullable=False)  # signal, order_created, order_sent, ...

    # 관계 (nullable - 시스템 이벤트는 asset/order 없을 수 있음)
    asset_id = Column(BigInteger, ForeignKey("assets.id"), nullable=True)
    order_id = Column(BigInteger, ForeignKey("orders.id"), nullable=True)
    account_id = Column(BigInteger, ForeignKey("accounts.id"), nullable=True)

    # 이벤트 상세
    summary = Column(Text, nullable=False)  # 짧은 요약 (UI 표시용)
    detail = Column(JSONB, nullable=True)   # 상세 데이터 (flexible)

    # Week12 Day2: reason/snapshot 필드 (audit trail)
    reason_code = Column(Text, nullable=True)   # 표준 코드 (기계용)
    reason_text = Column(Text, nullable=True)   # 설명 (사람용)
    snapshot_id = Column(Text, nullable=True)   # 스냅샷 참조 ID

    # 메타
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class KISOrderSettings(Base):
    """
    KIS 주문 설정 (계정별)
    - KIS_KR: 주문 방식, 타이밍, 시장가
    - KIS_US: 종가마감 신호, 지정가, 슬리피지
    """
    __tablename__ = "kis_order_settings"

    id = Column(BigInteger, primary_key=True)
    account_id = Column(BigInteger, ForeignKey("accounts.id"), nullable=False, unique=True)
    exchange_type = Column(Text, nullable=False)  # KIS_KR or KIS_US

    # KIS_KR 설정
    kr_order_method = Column(Text, nullable=True, default="regular_close")  # regular_close, next_trade, next_day_open
    kr_timing_seconds = Column(BigInteger, nullable=True, default=30)  # 마감 N초 전

    # KIS_US 설정
    us_signal_minutes = Column(BigInteger, nullable=True, default=2)  # 마감 N분 전
    us_slippage_ticks = Column(BigInteger, nullable=True, default=3)  # 슬리피지 N틱

    # 메타
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

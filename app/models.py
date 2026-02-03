from sqlalchemy.orm import DeclarativeBase
from sqlalchemy import Column, BigInteger, Text, Boolean, DateTime, ForeignKey
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.sql import func

class Base(DeclarativeBase):
    pass

class Account(Base):
    __tablename__ = "accounts"

    id = Column(BigInteger, primary_key=True)
    name = Column(Text, nullable=False, unique=True)
    exchange = Column(Text, nullable=False)
    api_key = Column(Text, nullable=False)
    api_secret = Column(Text, nullable=False)
    api_passphrase = Column(Text, nullable=True)

    is_active = Column(Boolean, nullable=False, default=False)

    last_health_at = Column(DateTime(timezone=True), nullable=True)
    last_health_ok = Column(Boolean, nullable=True)
    last_health_msg = Column(Text, nullable=True)

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

    # 메타
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

from sqlalchemy.orm import DeclarativeBase
from sqlalchemy import Column, BigInteger, Text, Boolean, DateTime
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

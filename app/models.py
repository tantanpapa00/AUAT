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

    # Kakao OAuth
    kakao_id = Column(Text, nullable=True, unique=True)

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


class PortfolioSnapshot(Base):
    """
    포트폴리오 일별 스냅샷 (수익률 계산용)
    - 매일 자정 또는 포트폴리오 조회 시 저장
    - 총 자산, KRW/USD 잔고, 환율 기록
    """
    __tablename__ = "portfolio_snapshots"

    id = Column(BigInteger, primary_key=True)
    user_id = Column(BigInteger, ForeignKey("users.id"), nullable=False)
    snapshot_date = Column(DateTime(timezone=True), nullable=False)  # 스냅샷 날짜 (일별 1개)

    total_asset_krw = Column(Float, nullable=False, default=0)  # 총 자산 (KRW 환산)
    total_krw = Column(Float, nullable=False, default=0)  # KRW 자산
    total_usd = Column(Float, nullable=False, default=0)  # USD 자산
    usd_krw_rate = Column(Float, nullable=False, default=1350)  # 환율

    holdings_json = Column(JSONB, nullable=True)  # 보유 자산 상세 (선택)

    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    __table_args__ = (
        Index('ix_portfolio_snapshots_user_date', 'user_id', 'snapshot_date'),
        UniqueConstraint('user_id', 'snapshot_date', name='uq_portfolio_snapshot_user_date'),
    )


class MarketSignal(Base):
    """
    시장신호 테이블 (IBD Big Picture 기반)
    - 매일 장 마감 후 업데이트
    - Distribution Day, FTD, Big Picture 상태 추적
    """
    __tablename__ = "market_signals"

    id = Column(BigInteger, primary_key=True)
    date = Column(DateTime(timezone=True), nullable=False)  # 날짜
    market = Column(Text, nullable=False)  # 'KOSPI' | 'KOSDAQ'

    # 지수 데이터
    index_value = Column(Float, nullable=True)
    change_amount = Column(Float, nullable=True)
    change_percent = Column(Float, nullable=True)
    trading_volume = Column(BigInteger, nullable=True)
    trading_value = Column(BigInteger, nullable=True)

    # 종목수
    rising_stocks = Column(BigInteger, default=0)
    falling_stocks = Column(BigInteger, default=0)
    unchanged_stocks = Column(BigInteger, default=0)
    upper_limit_stocks = Column(BigInteger, default=0)
    lower_limit_stocks = Column(BigInteger, default=0)
    listed_stocks = Column(BigInteger, default=0)

    # Big Picture 상태
    # confirmed_uptrend | uptrend_under_pressure | market_in_correction | rally_attempt
    status = Column(Text, default='confirmed_uptrend')

    # Distribution Day 추적
    active_dd_count = Column(BigInteger, default=0)
    distribution_days = Column(JSONB, default=[])
    # [{date, change_percent, volume, prev_volume, index_value, is_active}]

    # Rally/FTD 추적
    rally_start_date = Column(DateTime(timezone=True), nullable=True)
    rally_day_count = Column(BigInteger, default=0)
    last_ftd_date = Column(DateTime(timezone=True), nullable=True)

    # 신호 (green | yellow | red)
    short_term_signal = Column(Text, default='green')
    long_term_signal = Column(Text, default='green')

    # 투자자 동향 (억원)
    foreign_net = Column(BigInteger, default=0)
    institution_net = Column(BigInteger, default=0)
    individual_net = Column(BigInteger, default=0)

    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    __table_args__ = (
        Index('ix_market_signals_date', 'date'),
        Index('ix_market_signals_market_date', 'market', 'date'),
        UniqueConstraint('date', 'market', name='uq_market_signals_date_market'),
    )


class MarketBreadth(Base):
    """
    시장 너비 테이블 (20/200일선 하락비율 등)
    - 매일 장 마감 후 업데이트
    """
    __tablename__ = "market_breadth"

    id = Column(BigInteger, primary_key=True)
    date = Column(DateTime(timezone=True), nullable=False)
    market = Column(Text, nullable=False)  # 'KOSPI' | 'KOSDAQ'

    # 이동평균선 하락비율 (0~1)
    below_ma20_ratio = Column(Float, nullable=True)
    below_ma200_ratio = Column(Float, nullable=True)

    # 52주 신고가/신저가
    new_high_52w = Column(BigInteger, default=0)
    new_low_52w = Column(BigInteger, default=0)

    # ADR (Advance-Decline Ratio) = (상승/하락) * 100
    adr = Column(Float, nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    __table_args__ = (
        Index('ix_market_breadth_date', 'date'),
        Index('ix_market_breadth_market_date', 'market', 'date'),
        UniqueConstraint('date', 'market', name='uq_market_breadth_date_market'),
    )


class StockRS(Base):
    """
    개별 종목 RS(Relative Strength) 점수
    - IBD 방식: 3/6/9/12개월 수익률 가중 평균 → 백분위
    - RS 90 = 전체 종목 중 상위 10%
    - 매일 장 마감 후 업데이트
    """
    __tablename__ = "stock_rs"

    id = Column(BigInteger, primary_key=True)
    date = Column(DateTime(timezone=True), nullable=False)
    symbol = Column(Text, nullable=False)
    name = Column(Text, nullable=True)
    market = Column(Text, nullable=True)  # KOSPI | KOSDAQ

    # 수익률
    roc_3m = Column(Float, nullable=True)   # 3개월 수익률
    roc_6m = Column(Float, nullable=True)   # 6개월
    roc_9m = Column(Float, nullable=True)   # 9개월
    roc_12m = Column(Float, nullable=True)  # 12개월
    strength_factor = Column(Float, nullable=True)  # 가중 평균

    # RS 점수 (0~100 백분위)
    rs_score = Column(BigInteger, nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    __table_args__ = (
        Index('ix_stock_rs_date', 'date'),
        Index('ix_stock_rs_score', 'date', 'rs_score'),
        Index('ix_stock_rs_symbol', 'symbol', 'date'),
        UniqueConstraint('date', 'symbol', name='uq_stock_rs_date_symbol'),
    )


class SectorTrend(Base):
    """
    섹터 ETF 추세유지 상태
    - 20일 이동평균 기준 유지/이탈
    - 이격률, 신호등
    - 대표종목 + RS 점수
    """
    __tablename__ = "sector_trends"

    id = Column(BigInteger, primary_key=True)
    date = Column(DateTime(timezone=True), nullable=False)

    # ETF 정보
    etf_symbol = Column(Text, nullable=False)
    etf_name = Column(Text, nullable=True)
    sector = Column(Text, nullable=True)
    industry = Column(Text, nullable=True)

    # 등락률
    change_percent = Column(Float, nullable=True)
    return_since_entry = Column(Float, nullable=True)  # 유지 시작 후 수익률

    # 추세유지 상태
    position = Column(Text, nullable=True)  # 유지 | 이탈
    position_days = Column(BigInteger, nullable=True)
    gap_percent = Column(Float, nullable=True)  # 이격률
    signal = Column(Text, nullable=True)  # green | yellow | red

    # 기술적 지표
    ma20 = Column(Float, nullable=True)
    current_price = Column(Float, nullable=True)

    # 대표종목 (상위 6개 + RS 점수)
    # [{"symbol": "005930", "name": "삼성전자", "rs": 94}, ...]
    top_stocks = Column(JSONB, nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    __table_args__ = (
        Index('ix_sector_trends_date', 'date'),
        Index('ix_sector_trends_etf', 'etf_symbol', 'date'),
        UniqueConstraint('date', 'etf_symbol', name='uq_sector_trends_date_etf'),
    )


class ScreenerPreset(Base):
    """
    스크리너 필터 프리셋 (Phase 7 Stage 3)
    - 사용자별 필터 설정 저장
    - 빠른 필터 적용을 위한 프리셋
    """
    __tablename__ = "screener_presets"

    id = Column(BigInteger, primary_key=True)
    user_id = Column(BigInteger, ForeignKey("users.id"), nullable=False)
    name = Column(Text, nullable=False)  # 프리셋 이름
    market = Column(Text, nullable=False, default="kr")  # kr, us, etf

    # 필터 설정 (JSON)
    # {"per": {"min": 0, "max": 10}, "rsi": {"min": 30, "max": 70, "params": {"period": 14}}, ...}
    filters = Column(JSONB, nullable=False, default={})

    # 정렬 설정
    sort_by = Column(Text, nullable=True, default="market_cap")
    sort_order = Column(Text, nullable=True, default="desc")

    # 메타
    is_default = Column(Boolean, nullable=False, default=False)  # 기본 프리셋 여부
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    __table_args__ = (
        Index('ix_screener_presets_user', 'user_id'),
        UniqueConstraint('user_id', 'name', 'market', name='uq_screener_preset_user_name_market'),
    )


class CompanySummaryTranslation(Base):
    """
    해외 종목 기업개요 번역 캐시
    - yfinance 영문 longBusinessSummary → Claude 한글 번역
    - 90일마다 갱신, 이후 무료 ($0)
    """
    __tablename__ = "company_summary_translations"

    id = Column(BigInteger, primary_key=True)
    ticker = Column(Text, nullable=False, unique=True, index=True)  # NVDA, AAPL, ...

    # 기업개요
    description_en = Column(Text, nullable=True)   # 영문 원문
    description_ko = Column(Text, nullable=True)   # 한글 번역

    # 추가 정보
    sector = Column(Text, nullable=True)           # Technology
    industry = Column(Text, nullable=True)         # Semiconductors
    headquarters = Column(Text, nullable=True)     # Santa Clara, CA, USA
    employees = Column(BigInteger, nullable=True)  # 29600
    website = Column(Text, nullable=True)          # https://www.nvidia.com

    # 메타
    translated_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

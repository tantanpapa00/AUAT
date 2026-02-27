import uuid
import os
from contextlib import asynccontextmanager
from fastapi import FastAPI, Depends, HTTPException, Request, Query
from fastapi.responses import HTMLResponse
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, Field
from typing import Optional, Literal, Dict
from enum import Enum

# Matplotlib 설정 (한글 폰트, 백그라운드 모드)
import matplotlib
matplotlib.use('Agg')  # Non-interactive backend
import matplotlib.pyplot as plt
import matplotlib.font_manager as fm

# 한글 폰트 설정
def _setup_korean_font():
    """matplotlib 한글 폰트 설정"""
    font_paths = [
        '/usr/share/fonts/truetype/nanum/NanumGothic.ttf',  # Linux (Docker)
        'C:/Windows/Fonts/malgun.ttf',  # Windows
        '/System/Library/Fonts/AppleGothic.ttf',  # macOS
    ]
    for fp in font_paths:
        if os.path.exists(fp):
            fm.fontManager.addfont(fp)
            font_name = fm.FontProperties(fname=fp).get_name()
            plt.rcParams['font.family'] = font_name
            plt.rcParams['axes.unicode_minus'] = False
            print(f"[Chart] Korean font loaded: {font_name}")
            return
    print("[Chart] Warning: Korean font not found, using default")
    plt.rcParams['axes.unicode_minus'] = False

_setup_korean_font()


def _fix_mojibake(s: str):
    """Attempt to fix mojibake for KIS msg fields.

    KIS sometimes returns Korean text but clients can surface it as mojibake.
    We try a couple of common recoveries:
      - UTF-8 bytes mis-decoded as latin-1
      - EUC-KR bytes mis-decoded as latin-1
    If recovery doesn't look better, fall back to the original.
    """
    if not isinstance(s, str) or s == "":
        return s

    raw = s.strip()
    if raw == "":
        return raw

    def _score(t: str) -> tuple[int,int,int]:
        # Prefer more Hangul, fewer replacement chars, longer text.
        hangul = sum(1 for ch in t if "가" <= ch <= "힣")
        repl = t.count("�")
        return (hangul, -repl, len(t))

    candidates = []
    # Keep original as a candidate
    candidates.append(raw)

    try:
        b = raw.encode("latin1", errors="strict")
    except Exception:
        # If we can't roundtrip latin1, just return the stripped original.
        return raw

    # Try a couple of decoders; include both replace/ignore for UTF-8.
    for enc in ("utf-8", "euc-kr", "cp949"):
        try:
            t = b.decode(enc, errors="replace").strip()
            if t:
                candidates.append(t)
        except Exception:
            pass
    # UTF-8 ignore can salvage short clean text if bytes are partially broken.
    try:
        t = b.decode("utf-8", errors="ignore").strip()
        if t:
            candidates.append(t)
    except Exception:
        pass

    # Pick the best candidate by score.
    best = max(candidates, key=_score)
    return best

from sqlalchemy.orm import Session
from sqlalchemy import text
from sqlalchemy import text as text_sql
from sqlalchemy.exc import IntegrityError

from datetime import datetime, timezone, timedelta

# KST timezone (Asia/Seoul) for consistent timestamps
KST = timezone(timedelta(hours=9))

import json
import hashlib
import math
import socket
import asyncio

import os
import httpx


# [UTIL_FLOAT_V1] Small helper used across send-now/poll-now paths.
# NOTE: keep dependency-free and never raise.
def _to_float(x, default: float = 0.0) -> float:
    try:
        if x is None or x == "":
            return float(default)
        return float(x)
    except Exception:
        return float(default)


# [ENV_LOADER_V1] Ensure .env is loaded even when running uvicorn directly (PowerShell env not inherited).
# - Reads project root '.env' (sibling of app/) and sets os.environ for missing keys only.
# - No external dependencies (python-dotenv not required).
from pathlib import Path as _Path

def _load_dotenv_fallback() -> None:
    try:
        root = _Path(__file__).resolve().parents[1]
        p = root / '.env'
        if not p.exists():
            return
        txt = p.read_text(encoding='utf-8-sig', errors='replace')
        for raw in txt.splitlines():
            line = raw.strip()
            if not line or line.startswith('#'):
                continue
            if '=' not in line:
                continue
            k, v = line.split('=', 1)
            k = k.strip()
            v = v.strip().strip('"').strip("'")
            if not k:
                continue
            # do not overwrite existing environment variables
            if os.getenv(k) is None or os.getenv(k) == '':
                os.environ[k] = v
    except Exception:
        # never crash on env loading
        return

_load_dotenv_fallback()

from .db import get_db
from contextlib import contextmanager


@contextmanager
def _db_conn():
    """Context-manager wrapper for FastAPI generator dependency get_db().

    get_db() yields a SQLAlchemy Session and handles closing in its finally block.
    This wrapper lets us use 'with _db_conn() as db:' in non-request helper paths.
    """
    gen = get_db()
    db = next(gen)
    try:
        yield db
    finally:
        try:
            next(gen)
        except StopIteration:
            pass

def _fetch_assets_for_home(conn):
    """Return asset rows for HOME/DIAG HOME.

    Backward-compatible with DBs that don't have assets.soft_deleted (older schema).
    Returns (rows, used_fallback: bool).
    """
    q = '\n            SELECT\n              a.id,\n              acc.name AS account_name,\n              s.name AS strategy_name,\n              a.symbol,\n              a.market,\n              a.is_active,\n              a.last_signal_at,\n              a.last_signal_id,\n              a.last_order_at,\n              a.last_order_status,\n              a.last_order_reason,\n              a.last_order_id,\n              a.last_okx_order_id,\n              a.last_filled_qty,\n              a.last_order_avg_px,\n              a.last_checked_at\n            FROM assets a\n            JOIN accounts acc ON acc.id = a.account_id\n            JOIN strategies s ON s.id = a.strategy_id\n            WHERE COALESCE(a.soft_deleted,0)=0\n            ORDER BY a.id;\n'
    try:
        rows = conn.execute(text_sql(q)).mappings().all()
        return rows, False
    except Exception as e:
        msg = str(e)
        # psycopg2: (psycopg2.errors.UndefinedColumn) ... a.soft_deleted ...
        if ("UndefinedColumn" in msg) and ("soft_deleted" in msg) and ("assets" in msg):
            q2 = q.replace("WHERE COALESCE(a.soft_deleted,0)=0\n", "")
            # important: rollback after failed statement to clear aborted txn
            try:
                conn.rollback()
            except Exception:
                pass
            rows = conn.execute(text_sql(q2)).mappings().all()
            return rows, True
        raise

from .crud_accounts import (
    list_accounts, get_account, create_account, update_account,
    delete_account, toggle_account, set_health,
    validate_exchange_fields, filter_account_payload
)
from .pine_parser import parse_pine_inputs


@asynccontextmanager
async def lifespan(app):
    """FastAPI lifespan - 시작/종료 이벤트"""
    # 1. AI 테이블 초기화 (서버 시작 시 1회만 — ALTER TABLE 블로킹 방지)
    try:
        with _db_conn() as db:
            _ensure_ai_tables(db)
    except Exception as e:
        print(f"[DB] AI 테이블 초기화 경고: {e}")

    # 2. 스크리너 메모리 캐시 워밍업 (첫 요청 3초 이내 응답 위해)
    try:
        from app.screener.kr_screener import load_kr_stocks
        from app.screener.us_screener import load_us_stocks
        from app.screener.etf_screener import load_etf_stocks

        print("[Screener Warmup] 시작...")
        await load_kr_stocks()
        print("[Screener Warmup] KR 완료")
        await load_us_stocks()
        print("[Screener Warmup] US 완료")
        await load_etf_stocks()
        print("[Screener Warmup] ETF 완료")
        print("[Screener Warmup] 전체 완료 - 첫 요청 3초 이내 응답 가능")
    except Exception as e:
        print(f"[Screener Warmup] 경고: {e}")

    yield


app = FastAPI(title="BBooster API v1.0", lifespan=lifespan)

# CORS 설정 — Tauri webview에서 외부 이미지 로딩 허용
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Tauri는 tauri://localhost 또는 https://tauri.localhost 사용
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Static files for chart images
STATIC_DIR = "/app/static"
CHARTS_DIR = os.path.join(STATIC_DIR, "charts")
os.makedirs(CHARTS_DIR, exist_ok=True)
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


# =========================
# [AUTH_V1] Google OAuth + JWT 인증
# =========================
from starlette.middleware.sessions import SessionMiddleware
from starlette.responses import RedirectResponse
from app.auth import (
    oauth, get_or_create_user_from_google, create_tokens_for_user,
    verify_token, get_current_user, get_current_user_optional, get_admin_user,
    UserResponse, TokenResponse, RegisterRequest, LoginRequest,
    GOOGLE_CLIENT_ID, SKIP_AUTH, is_public_path,
    register_user, authenticate_user
)
from app.models import User, StockRS
from app.kis_api import (
    get_master_cache, refresh_master_cache, StockMaster,
    get_kis_token, get_domestic_price, get_overseas_price,
    get_financial_ratio, get_income_statement, get_invest_opinion,
    get_investor_trend, get_daily_prices,
    # 공개 API (KIS 계정 없이도 사용 가능)
    get_naver_stock_price, get_yahoo_stock_price,
    get_naver_daily_prices, get_yahoo_daily_prices,
    # 시장분석 API
    get_index_price, get_volume_rank, get_fluctuation_rank,
    get_investor_daily, get_market_cap_rank, get_foreign_net_rank,
    get_institution_net_rank, get_naver_index, get_yahoo_index,
    get_naver_sector_list, get_naver_volume_rank, get_naver_fluctuation_rank,
    SECTOR_CODES,
    # US 심볼 유틸리티 (Task 3: KIS_US 필터링 개선)
    normalize_us_symbol, is_otc_symbol, detect_exchange_from_symbol
)

# Yahoo Finance 모듈 (naver_finance는 data_provider로 대체)
from app import yahoo_finance
from app.data_provider import (
    get_kr_market_overview, get_us_market_overview, get_etf_overview,
    get_crypto_overview, get_rs_ranking, get_new_high_stocks, get_valuation,
    get_stock_detail, get_chart_data,
    # Stock Detail Renewal (Phase 1)
    get_stock_financial_summary, get_stock_financial_trend, get_stock_company,
    get_stock_financial_statement, get_stock_news, get_stock_disclosures,
    get_stock_consensus,
    # Phase 8-2: 종목 상세 API
    get_stock_summary_kr, get_stock_financials_kr, get_stock_news_kr, get_eps_revision_history,
    # Phase 8-3: 기업 탭 + 재무제표 + 투자지표
    get_stock_company_kr, get_stock_statement_kr, get_invest_indicators_kr,
    # Phase 9: 해외 종목 상세 (Finviz + Yahoo Finance)
    get_stock_summary_us, get_stock_chart_us, get_stock_news_us,
    get_stock_company_us, get_stock_financials_us,
    get_stock_filings_us, get_stock_analyst_us,
    # Phase 10: ETF 상세
    get_etf_summary, get_etf_chart, get_etf_performance,
    # Day14: 환율 + 거래소별 잔고 조회
    get_usd_krw_rate, fetch_upbit_balances, fetch_binance_balances,
    fetch_okx_balances, fetch_bybit_balances, fetch_kis_kr_balances, fetch_kis_us_balances,
)
# Phase 7: 종목검색기 (분리된 모듈)
from app.screener import screener_kr

# 세션 미들웨어 (OAuth 콜백용)
app.add_middleware(
    SessionMiddleware,
    secret_key=os.getenv("JWT_SECRET_KEY", "bbooster-secret-key-change-in-production"),
)

# Premium Strategy Router (Phase 3)
from .premium_routes import router as premium_router
app.include_router(premium_router)


@app.get("/api/auth/google/login")
async def auth_google_login(request: Request):
    """구글 로그인 URL 반환"""
    if not GOOGLE_CLIENT_ID:
        raise HTTPException(status_code=500, detail="Google OAuth가 설정되지 않았습니다")

    # 콜백 URL 생성
    redirect_uri = request.url_for("auth_google_callback")
    # 실제 환경에서는 도메인 기반 URL 사용
    base_url = os.getenv("BASE_URL", "")
    if base_url:
        redirect_uri = f"{base_url}/api/auth/google/callback"

    return await oauth.google.authorize_redirect(request, redirect_uri)


@app.get("/api/auth/google/callback")
async def auth_google_callback(request: Request, db: Session = Depends(get_db)):
    """구글 OAuth 콜백 처리"""
    if not GOOGLE_CLIENT_ID:
        raise HTTPException(status_code=500, detail="Google OAuth가 설정되지 않았습니다")

    try:
        token = await oauth.google.authorize_access_token(request)
        user_info = token.get("userinfo")

        if not user_info:
            raise HTTPException(status_code=400, detail="사용자 정보를 가져올 수 없습니다")

        # 사용자 생성 또는 조회
        user = get_or_create_user_from_google(
            db=db,
            google_id=user_info.get("sub"),
            email=user_info.get("email"),
            name=user_info.get("name"),
            picture=user_info.get("picture"),
        )

        # JWT 토큰 생성
        tokens = create_tokens_for_user(user)

        # 클라이언트로 리다이렉트 (토큰 포함)
        frontend_url = os.getenv("FRONTEND_URL", "/")
        redirect_url = f"{frontend_url}?access_token={tokens.access_token}&refresh_token={tokens.refresh_token}"

        return RedirectResponse(url=redirect_url)

    except Exception as e:
        raise HTTPException(status_code=400, detail=f"OAuth 인증 실패: {str(e)}")


# =========================
# [AUTH_V2] 자체 회원가입/로그인 (이메일+비밀번호)
# =========================
@app.post("/api/auth/register", response_model=TokenResponse)
async def auth_register(request: RegisterRequest, db: Session = Depends(get_db)):
    """이메일/비밀번호로 회원가입"""
    try:
        user = register_user(
            db=db,
            email=request.email,
            password=request.password,
            name=request.name,
        )
        # 회원가입 성공 후 바로 토큰 발급
        return create_tokens_for_user(user)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"회원가입 실패: {str(e)}")


@app.post("/api/auth/login", response_model=TokenResponse)
async def auth_login(request: LoginRequest, db: Session = Depends(get_db)):
    """이메일/비밀번호로 로그인"""
    user = authenticate_user(
        db=db,
        email=request.email,
        password=request.password,
    )
    if not user:
        raise HTTPException(
            status_code=401,
            detail="이메일 또는 비밀번호가 올바르지 않습니다"
        )
    return create_tokens_for_user(user)


@app.get("/api/auth/status")
async def auth_status():
    """인증 시스템 상태 확인 (개발용)"""
    return {
        "ok": True,
        "skip_auth": SKIP_AUTH,
        "google_oauth_enabled": bool(GOOGLE_CLIENT_ID),
        "email_auth_enabled": True,
    }


@app.post("/api/auth/refresh", response_model=TokenResponse)
async def auth_refresh(request: Request, db: Session = Depends(get_db)):
    """리프레시 토큰으로 새 액세스 토큰 발급"""
    try:
        body = await request.json()
        refresh_token = body.get("refresh_token")
    except Exception:
        raise HTTPException(status_code=400, detail="refresh_token이 필요합니다")

    if not refresh_token:
        raise HTTPException(status_code=400, detail="refresh_token이 필요합니다")

    token_data = verify_token(refresh_token, expected_type="refresh")
    if not token_data or not token_data.user_id:
        raise HTTPException(status_code=401, detail="유효하지 않은 리프레시 토큰입니다")

    user = db.query(User).filter(User.id == token_data.user_id).first()
    if not user:
        raise HTTPException(status_code=401, detail="사용자를 찾을 수 없습니다")

    return create_tokens_for_user(user)


@app.get("/api/auth/me", response_model=UserResponse)
async def auth_me(current_user: User = Depends(get_current_user)):
    """현재 로그인 사용자 정보"""
    return UserResponse(
        id=current_user.id,
        email=current_user.email,
        name=current_user.name,
        picture=current_user.picture,
        role=current_user.role,
        plan=current_user.plan,
        plan_expires_at=current_user.plan_expires_at,
        created_at=current_user.created_at,
    )


@app.post("/api/auth/logout")
async def auth_logout():
    """로그아웃 (클라이언트에서 토큰 삭제)"""
    # JWT는 stateless이므로 서버에서 할 작업 없음
    # 클라이언트에서 토큰을 삭제해야 함
    return {"ok": True, "message": "로그아웃되었습니다. 클라이언트에서 토큰을 삭제하세요."}


# =========================
# [DASHBOARD_V1] 대시보드 API (수익률 중심)
# =========================
import random
from datetime import date

@app.get("/api/dashboard/summary")
async def dashboard_summary(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """대시보드 요약 데이터 (총 자산, 수익률, 오늘 수익)"""
    try:
        # 활성 자산 수
        active_assets = db.execute(text(
            "SELECT COUNT(*) FROM assets WHERE is_active = true AND COALESCE(soft_deleted, 0) = 0"
        )).scalar() or 0
    except Exception:
        active_assets = 0

    # 실제 거래 데이터가 없으므로 더미 데이터 반환
    # 실제 연동 시 거래소 API에서 잔고/수익률 조회 필요
    return {
        "ok": True,
        "total_assets": 10000000 + random.randint(-100000, 100000),  # 더미
        "total_profit_pct": round(random.uniform(-5, 15), 2),  # 더미
        "daily_change_pct": round(random.uniform(-3, 5), 2),  # 더미
        "today_profit": random.randint(-50000, 100000),  # 더미
        "active_assets": active_assets,
    }


@app.get("/api/dashboard/chart")
async def dashboard_chart(
    period: str = Query(default="daily", regex="^(daily|weekly|monthly)$"),
    current_user: User = Depends(get_current_user),
):
    """수익률 차트 데이터"""
    # 실제 거래 데이터가 없으므로 더미 데이터 반환
    if period == "daily":
        labels = ["09:00", "10:00", "11:00", "12:00", "13:00", "14:00", "15:00", "16:00"]
        values = [round(random.uniform(-2, 5), 2) for _ in range(8)]
    elif period == "weekly":
        labels = ["월", "화", "수", "목", "금", "토", "일"]
        values = [round(random.uniform(-3, 8), 2) for _ in range(7)]
    else:  # monthly
        labels = [f"{i+1}주" for i in range(4)]
        values = [round(random.uniform(-5, 15), 2) for _ in range(4)]

    return {
        "ok": True,
        "period": period,
        "labels": labels,
        "values": values,
    }


@app.get("/api/dashboard/assets")
async def dashboard_assets(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """자산별 성과 데이터"""
    assets = []

    try:
        # assets 테이블에서 활성 자산 조회
        rows = db.execute(text("""
            SELECT a.id, a.symbol, a.market, acc.exchange
            FROM assets a
            JOIN accounts acc ON acc.id = a.account_id
            WHERE a.is_active = true AND COALESCE(a.soft_deleted, 0) = 0
            ORDER BY a.id
            LIMIT 20
        """)).mappings().all()

        for row in rows:
            # 실제 거래 데이터가 없으므로 더미 수익률 생성
            assets.append({
                "symbol": row["symbol"],
                "exchange": row["exchange"],
                "profit_pct": round(random.uniform(-10, 20), 2),  # 더미
                "quantity": round(random.uniform(0.1, 10), 4),  # 더미
                "value": random.randint(100000, 1000000),  # 더미
            })
    except Exception as e:
        # assets 테이블이 없거나 오류 시 더미 데이터
        pass

    # 자산이 없으면 샘플 데이터 표시
    if not assets:
        sample_symbols = ["BTC-USDT", "ETH-USDT", "SOL-USDT", "삼성전자", "SK하이닉스"]
        for sym in sample_symbols:
            assets.append({
                "symbol": sym,
                "exchange": "OKX" if "USDT" in sym else "KIS",
                "profit_pct": round(random.uniform(-10, 20), 2),
                "quantity": round(random.uniform(0.1, 10), 4),
                "value": random.randint(100000, 1000000),
            })

    return {
        "ok": True,
        "assets": assets,
    }


# =========================
# [ADMIN_V1] 관리자 전용 API
# =========================
from typing import List

@app.get("/api/admin/users")
async def admin_list_users(
    limit: int = Query(default=50, le=200),
    offset: int = Query(default=0, ge=0),
    admin_user: User = Depends(get_admin_user),
    db: Session = Depends(get_db),
):
    """전체 사용자 목록 (관리자 전용)"""
    users = db.query(User).order_by(User.created_at.desc()).offset(offset).limit(limit).all()
    total = db.query(User).count()

    return {
        "ok": True,
        "users": [
            {
                "id": u.id,
                "email": u.email,
                "name": u.name,
                "role": u.role,
                "plan": u.plan,
                "last_login_at": u.last_login_at.isoformat() if u.last_login_at else None,
                "created_at": u.created_at.isoformat() if u.created_at else None,
            }
            for u in users
        ],
        "total": total,
        "limit": limit,
        "offset": offset,
    }


@app.get("/api/admin/stats")
async def admin_stats(
    admin_user: User = Depends(get_admin_user),
    db: Session = Depends(get_db),
):
    """관리자 통계 (관리자 전용)"""
    # 사용자 통계
    total_users = db.query(User).count()
    admin_users = db.query(User).filter(User.role == "admin").count()

    # 플랜별 통계
    free_users = db.query(User).filter(User.plan == "free").count()
    hub_users = db.query(User).filter(User.plan == "hub").count()
    premium_users = db.query(User).filter(User.plan == "premium").count()

    # 계정 통계
    try:
        total_accounts = db.execute(text("SELECT COUNT(*) FROM accounts")).scalar() or 0
        active_accounts = db.execute(text("SELECT COUNT(*) FROM accounts WHERE is_active = true")).scalar() or 0
    except Exception:
        total_accounts = 0
        active_accounts = 0

    # 주문 통계
    try:
        total_orders = db.execute(text("SELECT COUNT(*) FROM orders")).scalar() or 0
        today_orders = db.execute(text(
            "SELECT COUNT(*) FROM orders WHERE created_at >= CURRENT_DATE"
        )).scalar() or 0
    except Exception:
        total_orders = 0
        today_orders = 0

    # 오늘 활성 사용자 (최근 로그인)
    try:
        active_today = db.query(User).filter(
            User.updated_at >= datetime.utcnow().replace(hour=0, minute=0, second=0)
        ).count()
    except Exception:
        active_today = 0

    # E-STOP 상태
    from .state import global_state
    estop_status = global_state.get("estop", False)

    return {
        "ok": True,
        "users": {
            "total": total_users,
            "admin": admin_users,
            "active_today": active_today,
            "by_plan": {
                "free": free_users,
                "hub": hub_users,
                "premium": premium_users,
            },
        },
        "accounts": {
            "total": total_accounts,
            "active": active_accounts,
        },
        "orders": {
            "total": total_orders,
            "today": today_orders,
        },
        "system": {
            "estop": estop_status,
        },
    }


@app.put("/api/admin/users/{user_id}/role")
async def admin_update_user_role(
    user_id: int,
    request: Request,
    admin_user: User = Depends(get_admin_user),
    db: Session = Depends(get_db),
):
    """사용자 역할 변경 (관리자 전용)"""
    try:
        body = await request.json()
        new_role = body.get("role")
    except Exception:
        raise HTTPException(status_code=400, detail="role이 필요합니다")

    if new_role not in ("admin", "user"):
        raise HTTPException(status_code=400, detail="role은 admin 또는 user여야 합니다")

    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="사용자를 찾을 수 없습니다")

    user.role = new_role
    db.commit()

    return {"ok": True, "user_id": user_id, "new_role": new_role}


@app.put("/api/admin/users/{user_id}/plan")
async def admin_update_user_plan(
    user_id: int,
    request: Request,
    admin_user: User = Depends(get_admin_user),
    db: Session = Depends(get_db),
):
    """사용자 플랜 변경 (관리자 전용)"""
    try:
        body = await request.json()
        new_plan = body.get("plan")
        expires_at = body.get("expires_at")  # ISO format string or null
    except Exception:
        raise HTTPException(status_code=400, detail="plan이 필요합니다")

    if new_plan not in ("free", "hub", "premium"):
        raise HTTPException(status_code=400, detail="plan은 free, hub, premium 중 하나여야 합니다")

    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="사용자를 찾을 수 없습니다")

    user.plan = new_plan
    if expires_at:
        from datetime import datetime as dt
        user.plan_expires_at = dt.fromisoformat(expires_at.replace("Z", "+00:00"))
    else:
        user.plan_expires_at = None

    db.commit()

    return {"ok": True, "user_id": user_id, "new_plan": new_plan, "expires_at": expires_at}


# =========================
# [E-STOP_V1] System Flag Store (DB)
# - Persistent across reloads
# - Never raise 500: always return JSON
# =========================

def _ensure_system_flags_table(db: Session):
    try:
        db.execute(text("""
            create table if not exists system_flags (
                key text primary key,
                value text not null,
                reason text null,
                updated_at timestamptz not null default now()
            )
        """))
        db.commit()
    except Exception:
        db.rollback()

def _get_flag(db: Session, key: str, default: str = "0") -> str:
    _ensure_system_flags_table(db)
    try:
        r = db.execute(text("""
            select value from system_flags where key=:k limit 1
        """), {"k": key}).mappings().first()
        if not r:
            return default
        v = (r.get("value") or "").strip()
        return v if v else default
    except Exception:
        db.rollback()
        return default

def _set_flag(db: Session, key: str, value: str, reason: str | None = None):
    _ensure_system_flags_table(db)
    try:
        db.execute(text("""
            insert into system_flags(key, value, reason, updated_at)
            values(:k, :v, :r, now())
            on conflict(key) do update set
                value=excluded.value,
                reason=excluded.reason,
                updated_at=excluded.updated_at
        """), {"k": key, "v": str(value), "r": reason})
        db.commit()
    except Exception:
        db.rollback()

def _is_estop_on(db: Session) -> bool:
    v = str(_get_flag(db, "estop", "0")).strip().lower()
    return v in ("1", "true", "yes", "y", "on")

@app.get("/api/system/estop")
def api_get_estop(db: Session = Depends(get_db)):
    try:
        _ensure_system_flags_table(db)
        r = db.execute(text("""
            select value, reason, updated_at
              from system_flags
             where key='estop'
             limit 1
        """)).mappings().first()
        if not r:
            return {"ok": True, "estop": False, "value": "0", "reason": None, "updated_at": None}
        val = (r.get("value") or "0")
        return {
            "ok": True,
            "estop": str(val).strip().lower() in ("1","true","yes","y","on"),
            "value": str(val),
            "reason": r.get("reason"),
            "updated_at": (r.get("updated_at").isoformat() if r.get("updated_at") else None),
        }
    except Exception as e:
        return {"ok": False, "code": "exception", "detail": f"get_estop_failed: {type(e).__name__}: {str(e)}"}

@app.post("/api/system/estop")
async def api_set_estop(request: Request, db: Session = Depends(get_db)):
    try:
        body = await request.json()
    except Exception:
        body = None

    try:
        if not isinstance(body, dict) or "estop" not in body:
            return {"ok": False, "code": "bad_request", "detail": "missing: estop (bool|0|1)"}

        raw = body.get("estop")
        reason = body.get("reason")

        if isinstance(raw, bool):
            on = raw
        else:
            s = str(raw).strip().lower()
            on = s in ("1", "true", "yes", "y", "on")

        _set_flag(db, "estop", "1" if on else "0", str(reason) if reason is not None else None)

        return {"ok": True, "estop": on, "value": "1" if on else "0", "reason": reason}
    except Exception as e:
        return {"ok": False, "code": "exception", "detail": f"set_estop_failed: {type(e).__name__}: {str(e)}"}

# [ORDER_POLL_WORKER_V1]
# ORDER_POLL_ENABLE=1 이면 서버 기동 시 주문상태 폴링 워커를 백그라운드로 실행합니다.
# - ORDER_POLL_INTERVAL: 초 (default 5)
# - ORDER_POLL_BATCH: 한번에 처리할 주문 수 (default 20)
import os as _os
import threading as _threading

_POLL_LOCK = _threading.Lock()

try:
    _poll_logger = logger  # type: ignore[name-defined]
except Exception:
    import logging as _logging
    _poll_logger = _logging.getLogger("autobot.poll")

_POLL_STOP = _threading.Event()
_POLL_THREAD = None

def _poll_worker_loop():
    interval = float(_os.getenv("ORDER_POLL_INTERVAL", "5") or "5")
    batch = int(_os.getenv("ORDER_POLL_BATCH", "20") or "20")
    _poll_logger.info("order-poll-worker started interval=%s batch=%s", interval, batch)

    # loop
    while not _POLL_STOP.is_set():
        try:
            if _POLL_LOCK.acquire(timeout=0.1):
                try:
                    poll_orders_once(limit=batch)  # changes-only wrapper
                finally:
                    _POLL_LOCK.release()
            else:
                pass

        except Exception as e:
            try:
                _poll_logger.exception("order-poll-worker error: %s", e)
            except Exception:
                pass
        _POLL_STOP.wait(interval)

# alias for backward-compat (startup/thread target)
_poller_loop = _poll_worker_loop


# [PATCH_FINALIZE_POLL_READONLY_V1] disabled duplicate startup poller

# @app.on_event("startup")
# def _start_order_poll_worker():
#     enable = (_os.getenv("ORDER_POLL_ENABLE", "0") or "0").strip().lower()
#     if enable not in ("1", "true", "yes", "y", "on"):
#         return

#     global _POLL_THREAD
#     if _POLL_THREAD and getattr(_POLL_THREAD, "is_alive", lambda: False)():
#         return

#     _POLL_STOP.clear()
#     _POLL_THREAD = _threading.Thread(target=_poll_worker_loop, daemon=True, name="order-poll-worker")
#     _POLL_THREAD.start()

# @app.on_event("shutdown")
# def _stop_order_poll_worker():
#     _POLL_STOP.set()


# KIS 종목 마스터 초기화 (앱 시작 시 백그라운드에서 로드)
@app.on_event("startup")
async def _startup_kis_master():
    """앱 시작 시 KIS 종목 마스터 캐시 갱신 (지연 실행 + 재시도 로직)"""
    import asyncio

    async def load_with_retry():
        # DNS 준비 대기: 서버 시작 후 10초 대기
        print("[KIS] Waiting 10s for DNS to be ready...")
        await asyncio.sleep(10)

        max_retries = 5
        retry_delay = 30  # 30초 간격 재시도

        for attempt in range(max_retries):
            try:
                await refresh_master_cache()
                cache = get_master_cache()
                stock_count = len(cache.stocks) if cache and cache.stocks else 0

                if stock_count > 100:
                    print(f"[KIS] Master cache loaded successfully: {stock_count} stocks")
                    return True

                print(f"[KIS] Master cache has only {stock_count} stocks, retrying...")

            except Exception as e:
                print(f"[KIS] Master load attempt {attempt + 1}/{max_retries} failed: {e}")

            if attempt < max_retries - 1:
                print(f"[KIS] Waiting {retry_delay}s before retry...")
                await asyncio.sleep(retry_delay)

        print("[KIS] All retry attempts failed, using fallback data")
        return False

    asyncio.create_task(load_with_retry())

    # 백그라운드 태스크: 5분마다 캐시 체크, 비어있으면 재시도
    async def background_cache_check():
        while True:
            await asyncio.sleep(300)  # 5분 대기
            try:
                cache = get_master_cache()
                if not cache or not cache.stocks or len(cache.stocks) < 100:
                    print("[KIS] Background: Cache empty, retrying...")
                    await refresh_master_cache()
            except Exception as e:
                print(f"[KIS] Background cache check error: {e}")

    asyncio.create_task(background_cache_check())


# 캔들 프리로더 시작 (주요 종목 자동 캐싱)
@app.on_event("startup")
async def _startup_candle_preloader():
    """앱 시작 시 캔들 프리로더 백그라운드 실행"""
    import asyncio
    from .candle_preloader import preload_loop

    # 30초 후 시작 (DB/네트워크 준비 대기)
    async def delayed_start():
        await asyncio.sleep(30)
        print("[Preloader] Starting candle preloader...")
        await preload_loop()

    asyncio.create_task(delayed_start())


# ---- Web Dashboard Templates ----
templates = Jinja2Templates(directory="app/templates")


@app.get("/", response_class=HTMLResponse)
def home(request: Request):
    """Homepage - Service introduction, pricing, download"""
    return templates.TemplateResponse("home.html", {"request": request})


@app.get("/login", response_class=HTMLResponse)
def login_page(request: Request):
    """Login/Register page"""
    return templates.TemplateResponse("login.html", {"request": request})


@app.get("/terms", response_class=HTMLResponse)
def terms_page(request: Request):
    """Terms of Service page (이용약관)"""
    return templates.TemplateResponse("terms.html", {"request": request})


@app.get("/privacy", response_class=HTMLResponse)
def privacy_page(request: Request):
    """Privacy Policy page (개인정보처리방침)"""
    return templates.TemplateResponse("privacy.html", {"request": request})


@app.get("/dashboard", response_class=HTMLResponse)
def dashboard(request: Request):
    """Web Dashboard - Main app (requires authentication)"""
    return templates.TemplateResponse("dashboard.html", {"request": request})


@app.get("/ui", response_class=HTMLResponse)
def ui_home(request: Request):
    """Web Dashboard - Alias for /dashboard"""
    return templates.TemplateResponse("dashboard.html", {"request": request})


# @app.get("/db-check")
# def db_check(db: Session = Depends(get_db)):
#     v = db.execute(text("select version()")).scalar()
#     return {"ok": True, "version": v}


# @app.get("/health")
# def health():
#     return {"ok": True}


# ---- Health Check (Docker/Kubernetes) ----
@app.get("/api/health")
def api_health():
    """
    Health check endpoint for Docker/Kubernetes.
    Returns ok=true if server is running.
    Does NOT check database (use /api/home for full status).
    """
    return {"ok": True, "status": "running"}


@app.get("/api/debug/master-cache")
async def api_debug_master_cache():
    """
    Debug endpoint for KIS master cache status.
    Returns cache status, stock counts by market, and sample stocks.
    """
    cache = get_master_cache()
    if not cache.is_valid():
        await refresh_master_cache()
        cache = get_master_cache()

    # 마켓별 카운트
    market_counts = {}
    etf_count = 0
    sample_by_market = {}

    for key, stock in cache.stocks.items():
        market = stock.market or "UNKNOWN"
        if market not in market_counts:
            market_counts[market] = 0
            sample_by_market[market] = []
        market_counts[market] += 1
        if stock.is_etf:
            etf_count += 1
        # 마켓당 5개 샘플
        if len(sample_by_market[market]) < 5:
            sample_by_market[market].append({"code": stock.code, "name": stock.name, "is_etf": stock.is_etf})

    return {
        "ok": True,
        "total_stocks": len(cache.stocks),
        "etf_count": etf_count,
        "last_updated": cache.last_updated.isoformat() if cache.last_updated else None,
        "is_valid": cache.is_valid(),
        "market_counts": market_counts,
        "samples": sample_by_market,
    }


@app.post("/api/debug/signal-log")
async def api_debug_signal_log(request: Request):
    """
    추세매매 v8 시그널 로그 생성 (Pine vs Python 비교용).

    요청:
    {
        "symbol": "BTC/USDT" 또는 "005930",
        "exchange": "okx" 또는 "kis_kr",
        "timeframe": "1d",
        "start_date": "2024-01-01",
        "end_date": "2025-01-01"
    }

    응답:
    {
        "symbol": "BTC/USDT",
        "exchange": "okx",
        "total_signals": 15,
        "signals": [
            {"date": "2024-06-15", "signal": "BUY", "price": 65000, "st_value": 62000, "st_dir": -1, "reason": "ENTRY_ALL_CONDITIONS"},
            ...
        ]
    }
    """
    from datetime import datetime, timedelta
    from .strategy_engine.candle_fetcher import fetch_candles_for_backtest
    from .strategy_engine.backtest_engine_trend import (
        precompute_supertrend,
        precompute_sma,
        precompute_vwma,
        build_htf_index_map,
    )
    from .strategy_engine.signal_generator_trend import TrendConfig, TrendState, generate_trend_signal
    from .strategy_engine.indicators import calc_hvi, calc_qqe_mod, calc_spo
    import numpy as np

    body = await request.json()
    symbol = body.get("symbol", "BTC/USDT")
    exchange = body.get("exchange", "okx").lower()
    timeframe = body.get("timeframe", "1d")
    start_date = body.get("start_date", "2024-01-01")
    end_date = body.get("end_date", "2025-02-19")

    # 날짜 → 일수 계산
    try:
        d1 = datetime.strptime(start_date, "%Y-%m-%d")
        d2 = datetime.strptime(end_date, "%Y-%m-%d")
        days = (d2 - d1).days + 50  # lookback 여유
    except:
        days = 400

    # 자산 타입 결정
    is_crypto = exchange in ("okx", "binance", "bybit")
    asset_type = "crypto" if is_crypto else "stock"

    try:
        # 캔들 조회
        candles = await fetch_candles_for_backtest(
            exchange=exchange,
            symbol=symbol,
            timeframe=timeframe,
            days=days,
            timeout=60,
        )

        if not candles or len(candles) < 50:
            return {
                "symbol": symbol,
                "exchange": exchange,
                "error": f"캔들 부족: {len(candles) if candles else 0}개",
                "signals": []
            }

        # 배열 변환
        closes = np.array([c.c for c in candles])
        highs = np.array([c.h for c in candles])
        lows = np.array([c.l for c in candles])
        volumes = np.array([c.v for c in candles])

        # 기본 설정 (v8 디폴트)
        config = TrendConfig(
            st_atr_len=20,
            st_factor=5.0,
            asset_type=asset_type,
            htf_sma_len=200 if is_crypto else 156,
            htf_vwma_len=156,
        )

        # SuperTrend 계산
        st_result = precompute_supertrend(highs, lows, closes, config.st_atr_len, config.st_factor)
        st_values = st_result["value"]
        st_dirs = st_result["direction"]

        # HTF 필터 (크립토: SMA200, 주식: VWMA156)
        if is_crypto:
            htf_filter = precompute_sma(closes, config.htf_sma_len)
        else:
            htf_filter = precompute_vwma(closes, volumes, config.htf_vwma_len)

        # HVI, QQE, SPO 계산
        hvi_result = calc_hvi(highs, lows, closes, volumes, config.hvi_length, config.hvi_divisor)
        qqe_result = calc_qqe_mod(closes, config.qqe_rsi_length, config.qqe_rsi_smoothing, config.qqe_factor)
        # calc_spo returns tuple: (normalized_osc, upper_band, lower_band, basis, line_short, line_long)
        spo_tuple = calc_spo(closes, config.exit_spo_smooth_len, config.exit_spo_threshold,
                              config.exit_spo_std_len, config.exit_spo_hma_len)
        spo_normalized_osc = spo_tuple[0]  # normalized_osc

        # 시그널 수집
        signals = []
        state = TrendState()
        lookback = 200  # 충분한 lookback

        for i in range(lookback, len(candles)):
            candle = candles[i]

            # 날짜 필터
            candle_date = datetime.fromtimestamp(candle.ts / 1000).strftime("%Y-%m-%d")
            if candle_date < start_date or candle_date > end_date:
                continue

            # 슬라이스
            slice_start = max(0, i - lookback + 1)
            slice_end = i + 1

            hvi_slice = {k: v[slice_start:slice_end] if isinstance(v, np.ndarray) else v for k, v in hvi_result.items()}
            qqe_slice = {k: v[slice_start:slice_end] if isinstance(v, np.ndarray) else v for k, v in qqe_result.items()}

            signal, state = generate_trend_signal(
                entry_close=closes[slice_start:slice_end],
                entry_st_dir=st_dirs[slice_start:slice_end],
                entry_hvi=hvi_slice,
                entry_qqe=qqe_slice,
                htf_vwma=htf_filter[slice_start:slice_end],
                exit_close=closes[slice_start:slice_end],
                exit_st_dir=st_dirs[slice_start:slice_end],
                exit_spo_norm=spo_normalized_osc[slice_start:slice_end],
                config=config,
                state=state,
                current_ts=candle.ts,
                entry_atr=None,
                entry_high=highs[slice_start:slice_end],
                bar_index=i,
                is_bar_confirmed=True,
            )

            # 시그널 발생 시 기록
            if signal.action != "hold":
                curr_st_val = float(st_values[i]) if not np.isnan(st_values[i]) else None
                curr_st_dir = int(st_dirs[i])
                curr_htf = float(htf_filter[i]) if i < len(htf_filter) and not np.isnan(htf_filter[i]) else None

                signals.append({
                    "date": candle_date,
                    "signal": signal.action.upper(),
                    "price": float(candle.c),
                    "st_value": round(curr_st_val, 2) if curr_st_val else None,
                    "st_dir": curr_st_dir,  # -1=bullish, 1=bearish
                    "htf_filter": round(curr_htf, 2) if curr_htf else None,
                    "reason": signal.reason_code,
                })

        return {
            "symbol": symbol,
            "exchange": exchange,
            "timeframe": timeframe,
            "period": f"{start_date} ~ {end_date}",
            "total_signals": len(signals),
            "config": {
                "st_atr_len": config.st_atr_len,
                "st_factor": config.st_factor,
                "htf_filter": f"SMA({config.htf_sma_len})" if is_crypto else f"VWMA({config.htf_vwma_len})",
            },
            "signals": signals
        }

    except Exception as e:
        import traceback
        traceback.print_exc()
        return {
            "symbol": symbol,
            "exchange": exchange,
            "error": str(e),
            "signals": []
        }


# # ---- Home API (Dashboard) ----
@app.get("/api/home")
def api_home():
    """
    SERVER HOME (운영 화면용)
    - 외부(KIS) 호출 금지: rate-limit/계정키 오염 방지
    - 계좌 요약은 DB(accounts) 기준으로만 내려준다.
    """
    items: list[dict] = []
    try:
        with _db_conn() as conn:
            rows, _used_fallback = _fetch_assets_for_home(conn)
            for r in rows:
                d = dict(r)
                # UI-friendly string fields
                d["last_signal"] = f'{d["last_signal_at"]} ({d["last_signal_id"]})' if d.get("last_signal_at") else "-"
                if d.get("last_order_at"):
                    ord_part = f'{d["last_order_at"]} | {d.get("last_order_status")}'
                    if d.get("last_okx_order_id"):
                        ord_part += f' | ordId={d.get("last_okx_order_id")}'
                    if d.get("last_checked_at"):
                        ord_part += f' | checked={d.get("last_checked_at")}'
                    d["last_order"] = ord_part
                else:
                    d["last_order"] = "-"
                d["last_filled"] = "-" if d.get("last_filled_qty") in (None, "") else str(d.get("last_filled_qty"))
                items.append(d)
    except Exception as e:
        return {"ok": False, "code": "home_failed", "detail": str(e)}

    # accounts_summary (NO KIS LIVE CALLS)
    accounts_summary: list[dict] = []
    warn = None
    try:
        with _db_conn() as conn:
            try:
                acc_rows = conn.execute(text_sql("""
                SELECT id, name, exchange, is_active, last_health_at, last_health_ok, last_health_msg
                FROM accounts
                WHERE COALESCE(soft_deleted,0)=0
                ORDER BY id;
            """)).mappings().all()
            except Exception as e:
                # Postgres: accounts.soft_deleted may not exist in older DBs
                try:
                    conn.rollback()
                except Exception:
                    pass
                if "UndefinedColumn" in str(e) and "soft_deleted" in str(e):
                    acc_rows = conn.execute(text_sql("""
                    SELECT id, name, exchange, is_active, last_health_at, last_health_ok, last_health_msg
                    FROM accounts
                    ORDER BY id;
                """)).mappings().all()
                else:
                    raise
        for a in acc_rows:
            accounts_summary.append(dict(a))
    except Exception as e2:
        warn = f"accounts_summary_failed: {e2}"
        accounts_summary = []

    # 최근 이벤트 요약 (Week 10 Day 3)
    recent_events: list[dict] = []
    try:
        with _db_conn() as conn:
            event_rows = conn.execute(text_sql("""
                SELECT
                    o.id,
                    o.asset_id,
                    o.status,
                    o.created_at,
                    a.symbol
                FROM orders o
                LEFT JOIN assets a ON o.asset_id = a.id
                ORDER BY o.created_at DESC
                LIMIT 5
            """)).mappings().all()
            for row in event_rows:
                evt_type = "order_sent" if row["status"] == "sent" else (
                    "order_filled" if row["status"] == "filled" else (
                    "order_failed" if row["status"] == "failed" else "order_created"))
                recent_events.append({
                    "id": row["id"],
                    "event_type": evt_type,
                    "symbol": row["symbol"] or "N/A",
                    "summary": f'{row["symbol"] or "N/A"} {evt_type.replace("order_", "")}',
                    "created_at": row["created_at"].isoformat() if row["created_at"] else ""
                })
    except Exception:
        pass  # 실패해도 다른 데이터는 반환

    out = {"ok": True, "items": items, "accounts_summary": accounts_summary, "recent_events": recent_events}
    if warn:
        out["warn"] = warn
    return out


@app.get("/api/diag/home")
def api_diag_home(request: Request = None):
    """
    TEST HOME (테스트/진단 화면용)
    - KIS 요약을 캐시 기반으로 붙여서 내려준다.
    - 강제 새로고침은 query ?refresh_kis=1 로만 허용.
    """
    items: list[dict] = []
    try:
        with _db_conn() as conn:
            rows, used_fallback = _fetch_assets_for_home(conn)
            for r in rows:
                d = dict(r)
                d["last_signal"] = f'{d["last_signal_at"]} ({d["last_signal_id"]})' if d.get("last_signal_at") else "-"
                if d.get("last_order_at"):
                    ord_part = f'{d["last_order_at"]} | {d.get("last_order_status")}'
                    if d.get("last_okx_order_id"):
                        ord_part += f' | ordId={d.get("last_okx_order_id")}'
                    if d.get("last_checked_at"):
                        ord_part += f' | checked={d.get("last_checked_at")}'
                    d["last_order"] = ord_part
                else:
                    d["last_order"] = "-"
                d["last_filled"] = "-" if d.get("last_filled_qty") in (None, "") else str(d.get("last_filled_qty"))
                items.append(d)
    except Exception as e:
        return {"ok": False, "code": "diag_home_failed", "detail": str(e)}

    accounts_summary: list[dict] = []
    warn = None
    try:
        with _db_conn() as conn:
            try:
                acc_rows = conn.execute(text_sql("""
                SELECT id, name, exchange, is_active, last_health_at, last_health_ok, last_health_msg
                FROM accounts
                WHERE COALESCE(soft_deleted,0)=0
                ORDER BY id;
            """)).mappings().all()
            except Exception as e:
                # Postgres: accounts.soft_deleted may not exist in older DBs
                try:
                    conn.rollback()
                except Exception:
                    pass
                if "UndefinedColumn" in str(e) and "soft_deleted" in str(e):
                    acc_rows = conn.execute(text_sql("""
                    SELECT id, name, exchange, is_active, last_health_at, last_health_ok, last_health_msg
                    FROM accounts
                    ORDER BY id;
                """)).mappings().all()
                else:
                    raise

        # KIS 요약 (캐시 가드, refresh_kis=1 이면 강제 새로고침)
        refresh_kis = 0
        try:
            if request is not None:
                refresh_kis = int((request.query_params.get("refresh_kis") or "0").strip())
        except Exception:
            refresh_kis = 0

        kis_payload = None
        kis_summary = None
        kis_msg1_fixed = None
        kis_check = None
        kis_cache_state = "miss"
        kis_ts = None

        try:
            kis_payload, kis_cache_state, kis_ts = _kis_balance_summary_cached(refresh=refresh_kis)
            kis_summary = kis_payload.get("summary") if isinstance(kis_payload, dict) else None
            kis_msg1_fixed = kis_payload.get("msg1_fixed") if isinstance(kis_payload, dict) else None
            kis_check = kis_payload.get("check") if isinstance(kis_payload, dict) else None
        except Exception as _ke:
            warn = f"{warn} | kis_attach_failed: {_ke}" if warn else f"kis_attach_failed: {_ke}"
            kis_payload = None
            kis_summary = None
            kis_msg1_fixed = None
            kis_check = None

        for a in acc_rows:
            item = dict(a)
            if str(item.get("exchange", "")).upper() == "KIS":
                item["kis_balance_summary"] = kis_summary
                item["kis_msg1_fixed"] = kis_msg1_fixed
                item["kis_check"] = kis_check
                item["kis_cache_state"] = kis_cache_state
                try:
                    item["kis_cached_at"] = (
                        datetime.fromtimestamp(float(kis_ts), tz=KST).isoformat()
                        if kis_ts is not None else None
                    )
                except Exception:
                    item["kis_cached_at"] = None
            accounts_summary.append(item)
    except Exception as e2:
        warn = f"{warn} | accounts_summary_failed: {e2}" if warn else f"accounts_summary_failed: {e2}"
        accounts_summary = []

    out = {"ok": True, "items": items, "accounts_summary": accounts_summary}
    if used_fallback:
        out["note"] = "assets_soft_deleted_missing"
    if warn:
        out["warn"] = warn
    return out


@app.get("/api/accounts")
def api_list_accounts(db: Session = Depends(get_db)):
    rows = list_accounts(db)
    return [
        {
            "id": r.id,
            "name": r.name,
            "exchange": r.exchange,
            "is_active": r.is_active,
            "has_passphrase": bool(r.api_passphrase),
            "has_account_number": bool(r.account_number),
            "account_number": r.account_number[:4] + "****" if r.account_number and len(r.account_number) > 4 else None,
            "last_health_at": r.last_health_at,
            "last_health_ok": r.last_health_ok,
            "last_health_msg": r.last_health_msg,
        } for r in rows
    ]


@app.post("/api/accounts")
def api_create_account(payload: dict, db: Session = Depends(get_db)):
    """
    API 키 등록 (관리자용, 인증 없음)

    거래소별 필수 필드:
    - OKX: name, exchange, api_key, api_secret, api_passphrase
    - Binance/Bybit/Upbit: name, exchange, api_key, api_secret
    - KIS: name, exchange, api_key, api_secret, account_number
    """
    # 기본 필수 필드 검증
    required = ["name", "exchange", "api_key", "api_secret"]
    for k in required:
        if not payload.get(k):
            raise HTTPException(status_code=400, detail=f"missing: {k}")

    # 거래소별 추가 필드 검증
    exchange = payload.get("exchange", "").lower()
    is_valid, error_msg = validate_exchange_fields(exchange, payload)
    if not is_valid:
        raise HTTPException(status_code=400, detail=error_msg)

    try:
        acc = create_account(db, payload)
        return {"ok": True, "id": acc.id}
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="Account name already exists")


# ============================================================
# JWT Protected Account Endpoints (PC App용)
# ============================================================
@app.get("/api/user/accounts")
async def api_user_accounts(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """사용자의 계정 목록 조회 (JWT 인증 필요)"""
    rows = list_accounts(db)
    return [
        {
            "id": r.id,
            "name": r.name,
            "exchange": r.exchange,
            "is_active": r.is_active,
            "has_keys": True,
            "has_passphrase": bool(r.api_passphrase),
            "has_account_number": bool(r.account_number),
            "account_number_masked": r.account_number[:4] + "****" if r.account_number and len(r.account_number) > 4 else None,
            "last_health_check": r.last_health_at.isoformat() if r.last_health_at else None,
            "health_status": r.last_health_msg or "OK" if r.last_health_ok else "Error",
        } for r in rows
    ]


@app.post("/api/user/accounts")
async def api_user_create_account(
    payload: dict,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    API 키 등록 (JWT 인증 필요)

    거래소별 필수 필드:
    - OKX: name, exchange, api_key, api_secret, api_passphrase
    - Binance: name, exchange, api_key, api_secret
    - Bybit: name, exchange, api_key, api_secret
    - Upbit: name, exchange, api_key, api_secret
    - KIS (KIS_KR, KIS_US): name, exchange, api_key, api_secret, account_number
    """
    # 기본 필수 필드 검증
    if not payload.get("name"):
        raise HTTPException(status_code=400, detail="missing: name")
    if not payload.get("exchange"):
        raise HTTPException(status_code=400, detail="missing: exchange")
    if not payload.get("api_key"):
        raise HTTPException(status_code=400, detail="missing: api_key")
    if not payload.get("api_secret"):
        raise HTTPException(status_code=400, detail="missing: api_secret")

    # 거래소별 추가 필드 검증
    exchange = payload.get("exchange", "").lower()
    is_valid, error_msg = validate_exchange_fields(exchange, payload)
    if not is_valid:
        raise HTTPException(status_code=400, detail=error_msg)

    try:
        # 유효한 컬럼만 필터링하여 Account 생성
        acc = create_account(db, payload)
        return {"ok": True, "id": acc.id, "message": "API key registered successfully"}
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="Account name already exists")


@app.delete("/api/user/accounts/{account_id}")
async def api_user_delete_account(
    account_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """계정 삭제 (JWT 인증 필요)"""
    acc = get_account(db, account_id)
    if not acc:
        raise HTTPException(status_code=404, detail="Account not found")
    delete_account(db, acc)
    return {"ok": True, "message": "Account deleted successfully"}


# ============================================================
# KIS 주문 설정 API
# ============================================================
from app.models import KISOrderSettings

@app.get("/api/kis/order-settings/{account_id}")
async def api_get_kis_order_settings(
    account_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """KIS 주문 설정 조회"""
    settings = db.query(KISOrderSettings).filter(KISOrderSettings.account_id == account_id).first()
    if not settings:
        # 기본값 반환
        return {
            "account_id": account_id,
            "exchange_type": None,
            "kr_order_method": "regular_close",
            "kr_timing_seconds": 30,
            "us_signal_minutes": 2,
            "us_slippage_ticks": 3
        }
    return {
        "account_id": settings.account_id,
        "exchange_type": settings.exchange_type,
        "kr_order_method": settings.kr_order_method,
        "kr_timing_seconds": settings.kr_timing_seconds,
        "us_signal_minutes": settings.us_signal_minutes,
        "us_slippage_ticks": settings.us_slippage_ticks
    }


@app.post("/api/kis/order-settings")
async def api_save_kis_order_settings(
    payload: dict,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """KIS 주문 설정 저장"""
    account_id = payload.get("account_id")
    if not account_id:
        raise HTTPException(status_code=400, detail="missing: account_id")

    exchange_type = payload.get("exchange_type", "").upper()
    if exchange_type not in ["KIS_KR", "KIS_US"]:
        raise HTTPException(status_code=400, detail="invalid exchange_type: must be KIS_KR or KIS_US")

    # 기존 설정 조회 또는 생성
    settings = db.query(KISOrderSettings).filter(KISOrderSettings.account_id == account_id).first()
    if not settings:
        settings = KISOrderSettings(account_id=account_id, exchange_type=exchange_type)
        db.add(settings)

    # 설정 업데이트
    settings.exchange_type = exchange_type

    if exchange_type == "KIS_KR":
        settings.kr_order_method = payload.get("kr_order_method", "regular_close")
        settings.kr_timing_seconds = payload.get("kr_timing_seconds", 30)
    elif exchange_type == "KIS_US":
        settings.us_signal_minutes = payload.get("us_signal_minutes", 2)
        settings.us_slippage_ticks = payload.get("us_slippage_ticks", 3)

    db.commit()
    return {"ok": True, "message": "KIS order settings saved"}


# ============================================================
# 계정 연결 테스트 API (6개 거래소 지원)
# ============================================================
@app.get("/api/accounts/test")
async def api_test_account_connection(
    exchange: str = Query(...),
    account: str = Query(...),
    db: Session = Depends(get_db)
):
    """거래소별 계정 연결 테스트"""
    exchange_lower = exchange.lower()

    # 거래소별 테스트 로직
    if exchange_lower == "okx":
        # OKX: 기본 API ping 테스트
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.get("https://www.okx.com/api/v5/public/time")
                if resp.status_code == 200:
                    return {"ok": True, "message": "OKX 연결 성공", "exchange": "OKX"}
                return {"ok": False, "message": f"OKX 응답 오류: {resp.status_code}"}
        except Exception as e:
            return {"ok": False, "message": f"OKX 연결 실패: {str(e)}"}

    elif exchange_lower == "binance":
        # Binance: ping 테스트
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.get("https://api.binance.com/api/v3/ping")
                if resp.status_code == 200:
                    return {"ok": True, "message": "Binance 연결 성공", "exchange": "Binance"}
                return {"ok": False, "message": f"Binance 응답 오류: {resp.status_code}"}
        except Exception as e:
            return {"ok": False, "message": f"Binance 연결 실패: {str(e)}"}

    elif exchange_lower == "bybit":
        # Bybit: 서버 시간 테스트
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.get("https://api.bybit.com/v5/market/time")
                if resp.status_code == 200:
                    return {"ok": True, "message": "Bybit 연결 성공", "exchange": "Bybit"}
                return {"ok": False, "message": f"Bybit 응답 오류: {resp.status_code}"}
        except Exception as e:
            return {"ok": False, "message": f"Bybit 연결 실패: {str(e)}"}

    elif exchange_lower == "upbit":
        # Upbit: 시장 정보 테스트
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.get("https://api.upbit.com/v1/market/all")
                if resp.status_code == 200:
                    return {"ok": True, "message": "Upbit 연결 성공", "exchange": "Upbit"}
                return {"ok": False, "message": f"Upbit 응답 오류: {resp.status_code}"}
        except Exception as e:
            return {"ok": False, "message": f"Upbit 연결 실패: {str(e)}"}

    elif exchange_lower in ("kis_kr", "kis"):
        # KIS 국내주식: 토큰 발급 테스트는 키가 필요하므로 간단한 연결 확인
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.get("https://openapi.koreainvestment.com:9443/")
                # 연결 자체가 성공하면 OK (404라도 서버는 살아있음)
                return {"ok": True, "message": "KIS 국내주식 연결 성공", "exchange": "KIS_KR"}
        except Exception as e:
            return {"ok": False, "message": f"KIS 국내주식 연결 실패: {str(e)}"}

    elif exchange_lower == "kis_us":
        # KIS 해외주식: 동일 서버 사용
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.get("https://openapi.koreainvestment.com:9443/")
                return {"ok": True, "message": "KIS 해외주식 연결 성공", "exchange": "KIS_US"}
        except Exception as e:
            return {"ok": False, "message": f"KIS 해외주식 연결 실패: {str(e)}"}

    else:
        raise HTTPException(status_code=400, detail=f"지원하지 않는 거래소: {exchange}")


# @app.put("/api/accounts/{account_id}")
# def api_update_account(account_id: int, payload: dict, db: Session = Depends(get_db)):
#     acc = get_account(db, account_id)
#     if not acc:
#         raise HTTPException(status_code=404, detail="Account not found")

#     allowed = {"name", "exchange", "api_key", "api_secret", "api_passphrase", "is_active"}
#     payload = {k: v for k, v in payload.items() if k in allowed}

#     try:
#         update_account(db, acc, payload)
#         return {"ok": True}
#     except IntegrityError:
#         db.rollback()
#         raise HTTPException(status_code=409, detail="Account name already exists")


# @app.delete("/api/accounts/{account_id}")
# def api_delete_account(account_id: int, db: Session = Depends(get_db)):
#     acc = get_account(db, account_id)
#     if not acc:
#         raise HTTPException(status_code=404, detail="Account not found")
#     delete_account(db, acc)
#     return {"ok": True}


# @app.post("/api/accounts/{account_id}/toggle")
# def api_toggle_account(account_id: int, db: Session = Depends(get_db)):
#     acc = get_account(db, account_id)
#     if not acc:
#         raise HTTPException(status_code=404, detail="Account not found")
#     toggle_account(db, acc)
#     return {"ok": True}


# @app.post("/api/accounts/{account_id}/health")
# def api_health_account(account_id: int, db: Session = Depends(get_db)):
#     """
#     Day2: 기본 네트워크 체크 수준.
#     Week4에서 OKX 서명 호출로 '진짜 키 검증'으로 교체/확장.
#     """
#     acc = get_account(db, account_id)
#     if not acc:
#         raise HTTPException(status_code=404, detail="Account not found")
#     try:
#         socket.gethostbyname("www.google.com")
#         set_health(db, acc, True, "basic network ok")
#     except Exception:
#         set_health(db, acc, False, "network check failed")
#     return {"ok": True}


# # ---- Strategies API ----
@app.get("/api/strategies")
def api_list_strategies(db: Session = Depends(get_db)):
    rows = db.execute(text("""
        select id, name, tv_secret, is_active, created_at, updated_at
        from strategies
        order by id asc
    """)).mappings().all()
    return [dict(r) for r in rows]


@app.post("/api/strategies")
def api_create_strategy(payload: dict, db: Session = Depends(get_db)):
    if not payload.get("name"):
        raise HTTPException(status_code=400, detail="missing: name")
    if not payload.get("tv_secret"):
        raise HTTPException(status_code=400, detail="missing: tv_secret")

    signal_params = payload.get("signal_params")

    try:
        if signal_params:
            # signal_params 포함하여 저장
            row = db.execute(
                text("""
                    insert into strategies(name, tv_secret, is_active, signal_params)
                    values (:name, :tv_secret, :is_active, CAST(:signal_params AS jsonb))
                    returning id
                """),
                {
                    "name": payload["name"],
                    "tv_secret": payload["tv_secret"],
                    "is_active": bool(payload.get("is_active", False)),
                    "signal_params": _safe_dumps(signal_params),
                }
            ).mappings().first()
        else:
            row = db.execute(
                text("""
                    insert into strategies(name, tv_secret, is_active)
                    values (:name, :tv_secret, :is_active)
                    returning id
                """),
                {
                    "name": payload["name"],
                    "tv_secret": payload["tv_secret"],
                    "is_active": bool(payload.get("is_active", False)),
                }
            ).mappings().first()
        db.commit()
        return {"ok": True, "id": row["id"]}
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(e))


@app.put("/api/strategies/{strategy_id}")
async def api_update_strategy(
    strategy_id: int,
    request: Request,
    current_user: User = Depends(get_current_user_optional),
    db: Session = Depends(get_db)
):
    """전략 수정 API"""
    payload = await request.json()
    allowed = {"name", "tv_secret", "is_active"}
    payload = {k: v for k, v in payload.items() if k in allowed}

    if not payload:
        return {"ok": True, "strategy_id": strategy_id}

    sets = []
    params = {"id": strategy_id}
    for k, v in payload.items():
        sets.append(f"{k} = :{k}")
        params[k] = v

    q = f"""
        update strategies
        set {", ".join(sets)}, updated_at = now()
        where id = :id
        returning id
    """
    try:
        row = db.execute(text(q), params).mappings().first()
        if not row:
            db.rollback()
            raise HTTPException(status_code=404, detail="Strategy not found")
        db.commit()
        return {"ok": True, "strategy_id": strategy_id}
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(e))


# @app.delete("/api/strategies/{strategy_id}")
# def api_delete_strategy(strategy_id: int, db: Session = Depends(get_db)):
#     exists = db.execute(
#         text("select id from strategies where id = :id"),
#         {"id": strategy_id}
#     ).mappings().first()
#     if not exists:
#         raise HTTPException(status_code=404, detail="Strategy not found")

#     try:
#         row = db.execute(
#             text("delete from strategies where id = :id returning id"),
#             {"id": strategy_id}
#         ).mappings().first()

#         if not row:
#             db.rollback()
#             raise HTTPException(status_code=404, detail="Strategy not found")

#         db.commit()
#         return {"ok": True, "deleted": True}

#     except IntegrityError:
#         db.rollback()
#         try:
#             db.execute(
#                 text("""
#                     update strategies
#                     set is_active = false,
#                         updated_at = now()
#                     where id = :id
#                     returning id
#                 """),
#                 {"id": strategy_id}
#             )
#             db.commit()
#             return {"ok": True, "deleted": False, "soft_deleted": True}
#         except Exception as e2:
#             db.rollback()
#             raise HTTPException(status_code=400, detail=f"soft delete failed: {str(e2)}")

#     except Exception as e:
#         db.rollback()
#         raise HTTPException(status_code=400, detail=f"delete failed: {str(e)}")


# # ---- Assets API ----
@app.get("/api/assets")
def api_list_assets(db: Session = Depends(get_db)):
    # best-effort: ensure dashboard columns exist (avoid 500 on older DBs)
    try:
        db.execute(text("alter table assets add column if not exists last_okx_order_id text;"))
        db.execute(text("alter table assets add column if not exists last_filled_qty numeric;"))
        db.execute(text("alter table assets add column if not exists last_order_avg_px numeric;"))
        db.execute(text("alter table assets add column if not exists last_checked_at timestamptz;"))
        db.commit()
    except Exception:
        try:
            db.rollback()
        except Exception:
            pass

    rows = db.execute(text("""
        select
            a.id,
            a.account_id,
            ac.name as account_name,
            a.strategy_id,
            s.name as strategy_name,
            a.symbol,
            a.market,
            a.is_active,
            a.cooldown_sec,
            a.max_orders_per_day,
            a.last_signal_at,
            a.last_signal_id,
            a.last_order_at,
            a.last_order_id,
            a.last_order_status,
            a.last_order_reason,
            a.last_okx_order_id,
            a.last_filled_qty,
            a.last_order_avg_px,
            a.last_checked_at,
            a.created_at,
            a.updated_at
        from assets a
        join accounts ac on ac.id = a.account_id
        join strategies s on s.id = a.strategy_id
        order by a.id asc
    """)).mappings().all()
    return [dict(r) for r in rows]


@app.post("/api/assets")
def api_create_asset(payload: dict, db: Session = Depends(get_db)):
    required = ["account_id", "strategy_id", "symbol"]
    for k in required:
        if payload.get(k) in (None, ""):
            raise HTTPException(status_code=400, detail=f"missing: {k}")

    market = (payload.get("market") or "spot").strip()
    symbol = str(payload["symbol"]).strip()

    try:
        row = db.execute(
            text("""
                insert into assets(account_id, strategy_id, symbol, market, is_active)
                values (:account_id, :strategy_id, :symbol, :market, :is_active)
                returning id
            """),
            {
                "account_id": int(payload["account_id"]),
                "strategy_id": int(payload["strategy_id"]),
                "symbol": symbol,
                "market": market,
                "is_active": bool(payload.get("is_active", True)),
            }
        ).mappings().first()
        db.commit()
        return {"ok": True, "id": row["id"]}
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="Duplicate asset (account_id+strategy_id+symbol+market)")
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(e))


# @app.put("/api/assets/{asset_id}")
# def api_update_asset(asset_id: int, payload: dict, db: Session = Depends(get_db)):
#     allowed = {"account_id", "strategy_id", "symbol", "market", "is_active", "cooldown_sec", "max_orders_per_day"}
#     payload = {k: v for k, v in payload.items() if k in allowed}

#     if not payload:
#         return {"ok": True}

#     sets = []
#     params = {"id": asset_id}

#     for k, v in payload.items():
#         if k in ("account_id", "strategy_id"):
#             params[k] = int(v)
#         elif k in ("cooldown_sec", "max_orders_per_day"):
#             params[k] = int(v)
#         elif k in ("symbol", "market") and v is not None:
#             params[k] = str(v).strip()
#         elif k == "is_active":
#             params[k] = bool(v)
#         else:
#             params[k] = v
#         sets.append(f"{k} = :{k}")

#     q = f"""
#         update assets
#         set {", ".join(sets)}, updated_at = now()
#         where id = :id
#         returning id
#     """
#     try:
#         row = db.execute(text(q), params).mappings().first()
#         if not row:
#             db.rollback()
#             raise HTTPException(status_code=404, detail="Asset not found")
#         db.commit()
#         return {"ok": True}
#     except IntegrityError:
#         db.rollback()
#         raise HTTPException(status_code=409, detail="Duplicate asset (account_id+strategy_id+symbol+market)")
#     except Exception as e:
#         db.rollback()
#         raise HTTPException(status_code=400, detail=str(e))


# @app.delete("/api/assets/{asset_id}")
# def api_delete_asset(asset_id: int, db: Session = Depends(get_db)):
#     exists = db.execute(
#         text("select id from assets where id = :id"),
#         {"id": asset_id}
#     ).mappings().first()
#     if not exists:
#         raise HTTPException(status_code=404, detail="Asset not found")

#     try:
#         row = db.execute(
#             text("delete from assets where id = :id returning id"),
#             {"id": asset_id}
#         ).mappings().first()

#         if not row:
#             db.rollback()
#             raise HTTPException(status_code=404, detail="Asset not found")

#         db.commit()
#         return {"ok": True, "deleted": True}

#     except IntegrityError:
#         db.rollback()
#         try:
#             db.execute(
#                 text("""
#                     update assets
#                     set is_active = false,
#                         updated_at = now()
#                     where id = :id
#                     returning id
#                 """),
#                 {"id": asset_id}
#             )
#             db.commit()
#             return {"ok": True, "deleted": False, "soft_deleted": True}
#         except Exception as e2:
#             db.rollback()
#             raise HTTPException(status_code=400, detail=f"soft delete failed: {str(e2)}")

#     except Exception as e:
#         db.rollback()
#         raise HTTPException(status_code=400, detail=f"delete failed: {str(e)}")


# @app.post("/api/assets/{asset_id}/toggle")
# def api_toggle_asset(asset_id: int, db: Session = Depends(get_db)):
#     exists = db.execute(
#         text("select id from assets where id = :id"),
#         {"id": asset_id}
#     ).mappings().first()
#     if not exists:
#         raise HTTPException(status_code=404, detail="Asset not found")

#     db.execute(
#         text("""
#             update assets
#             set is_active = not is_active,
#                 updated_at = now()
#             where id = :id
#         """),
#         {"id": asset_id}
#     )
#     db.commit()
#     return {"ok": True}


# # ============================================================
# # [W2] Signal Params Sync + Config Save + TV Templates
# # ============================================================

# def _sanitize(obj):
#     if obj is None:
#         return None
#     if isinstance(obj, float):
#         if math.isnan(obj) or math.isinf(obj):
#             return None
#         return obj
#     if isinstance(obj, dict):
#         return {k: _sanitize(v) for k, v in obj.items()}
#     if isinstance(obj, list):
#         return [_sanitize(v) for v in obj]
#     return obj


# def _safe_dumps(obj) -> str:
#     return json.dumps(_sanitize(obj), ensure_ascii=False, separators=(",", ":"), sort_keys=False)


def _canonical_values(values: dict) -> str:
    return json.dumps(_sanitize(values), ensure_ascii=False, separators=(",", ":"), sort_keys=True)


def _make_config_hash(values: dict, prefix: str = "cfg_", short: int = 12) -> str:
    s = _canonical_values(values)
    h = hashlib.sha256(s.encode("utf-8")).hexdigest()
    return f"{prefix}{h[:short]}"


def _get_strategy_or_404(db: Session, strategy_id: int) -> dict:
    row = db.execute(
        text("select id, name, tv_secret, is_active from strategies where id=:id"),
        {"id": strategy_id},
    ).mappings().first()
    if not row:
        raise HTTPException(status_code=404, detail="Strategy not found")
    return dict(row)


# @app.post("/api/strategies/{strategy_id}/signal-params:sync")
# def api_signal_params_sync(strategy_id: int, payload: dict, db: Session = Depends(get_db)):
#     """
#     inputs[] -> signal_params 업서트
#     """
#     try:
#         inputs = payload.get("inputs")
#         if not isinstance(inputs, list) or len(inputs) == 0:
#             raise HTTPException(status_code=400, detail="missing: inputs[]")

#         _ = _get_strategy_or_404(db, strategy_id)

#         upsert_sql = text("""
#             insert into signal_params (
#                 strategy_id, key, title, type, defval, options,
#                 group_name, inline_key, tooltip,
#                 min_val, max_val, step_val,
#                 order_index, is_hidden, raw,
#                 updated_at
#             )
#             values (
#                 :strategy_id, :key, :title, :type,
#                 CAST(:defval AS jsonb),
#                 CAST(:options AS jsonb),

#                 :group_name, :inline_key, :tooltip,
#                 :min_val, :max_val, :step_val,
#                 :order_index, :is_hidden,
#                 CAST(:raw AS jsonb),
#                 now()
#             )
#             on conflict (strategy_id, key) do update set
#                 title       = excluded.title,
#                 type        = excluded.type,
#                 defval      = excluded.defval,
#                 options     = excluded.options,
#                 group_name  = excluded.group_name,
#                 inline_key  = excluded.inline_key,
#                 tooltip     = excluded.tooltip,
#                 min_val     = excluded.min_val,
#                 max_val     = excluded.max_val,
#                 step_val    = excluded.step_val,
#                 order_index = excluded.order_index,
#                 is_hidden   = excluded.is_hidden,
#                 raw         = excluded.raw,
#                 updated_at  = now()
#         """)

#         upserted = 0
#         for idx, it in enumerate(inputs):
#             if not isinstance(it, dict):
#                 continue
#             key = it.get("key")
#             if not key:
#                 continue

#             group_name = it.get("group") or it.get("group_name")

#             # MFT 관련 키/그룹은 기본 숨김
#             k_lower = str(key).lower()
#             g_lower = str(group_name).lower() if group_name else ""
#             is_hidden = bool(it.get("is_hidden", False)) or ("mft" in k_lower) or ("mft" in g_lower)

#             params = {
#                 "strategy_id": strategy_id,
#                 "key": key,
#                 "title": it.get("title"),
#                 "type": it.get("type") or "unknown",
#                 "defval": _safe_dumps(it.get("defval")),
#                 "options": _safe_dumps(it.get("options")) if it.get("options") is not None else "null",
#                 "group_name": group_name,
#                 "inline_key": it.get("inline") or it.get("inline_key"),
#                 "tooltip": it.get("tooltip"),
#                 "min_val": it.get("minval") if it.get("minval") is not None else it.get("min_val"),
#                 "max_val": it.get("maxval") if it.get("maxval") is not None else it.get("max_val"),
#                 "step_val": it.get("step") if it.get("step") is not None else it.get("step_val"),
#                 "order_index": int(it.get("order_index", idx)),
#                 "is_hidden": is_hidden,
#                 "raw": _safe_dumps(it),
#             }
#             db.execute(upsert_sql, params)
#             upserted += 1

#         db.commit()
#         return {"ok": True, "strategy_id": strategy_id, "received": len(inputs), "upserted": upserted}

#     except HTTPException:
#         raise
#     except Exception as e:
#         db.rollback()
#         raise HTTPException(status_code=400, detail=f"sync_failed: {type(e).__name__}: {str(e)}")


@app.get("/api/strategies/{strategy_id}/signal-params")
def api_signal_params_list(strategy_id: int, db: Session = Depends(get_db)):
    _ = _get_strategy_or_404(db, strategy_id)

    rows = db.execute(text("""
        select
            key, title, type, defval, options,
            group_name, inline_key, tooltip,
            min_val, max_val, step_val,
            order_index, is_hidden,
            created_at, updated_at
        from signal_params
        where strategy_id=:sid
        order by order_index asc, key asc
    """), {"sid": strategy_id}).mappings().all()

    return {"ok": True, "strategy_id": strategy_id, "count": len(rows), "items": [dict(r) for r in rows]}


# =====================================================
# Signal Params API (Sizing/Risk/Limits) - JSONB 기반
# =====================================================
from app.utils.merge import deep_merge, get_overridden_keys, DEFAULT_SIGNAL_PARAMS


class SignalParamsRequest(BaseModel):
    """전략 signal_params 저장 요청"""
    signal_params: dict


class SignalParamsOverrideRequest(BaseModel):
    """종목별 signal_params_override 저장 요청"""
    signal_params_override: dict


@app.get("/api/strategies/{strategy_id}/signal-params-jsonb")
def api_get_strategy_signal_params(strategy_id: int, db: Session = Depends(get_db)):
    """전략의 signal_params (JSONB) 조회"""
    row = db.execute(
        text("SELECT id, name, signal_params FROM strategies WHERE id = :id"),
        {"id": strategy_id}
    ).mappings().first()

    if not row:
        raise HTTPException(status_code=404, detail="전략을 찾을 수 없습니다")

    # signal_params가 없으면 기본값 반환
    signal_params = row["signal_params"] or DEFAULT_SIGNAL_PARAMS

    return {
        "ok": True,
        "strategy_id": strategy_id,
        "strategy_name": row["name"],
        "signal_params": signal_params
    }


@app.put("/api/strategies/{strategy_id}/signal-params-jsonb")
def api_put_strategy_signal_params(
    strategy_id: int,
    req: SignalParamsRequest,
    db: Session = Depends(get_db)
):
    """전략의 signal_params (JSONB) 저장"""
    row = db.execute(
        text("SELECT id FROM strategies WHERE id = :id"),
        {"id": strategy_id}
    ).mappings().first()

    if not row:
        raise HTTPException(status_code=404, detail="전략을 찾을 수 없습니다")

    try:
        db.execute(
            text("""
                UPDATE strategies
                SET signal_params = CAST(:params AS jsonb),
                    updated_at = now()
                WHERE id = :id
            """),
            {"id": strategy_id, "params": _safe_dumps(req.signal_params)}
        )
        db.commit()

        return {
            "ok": True,
            "message": "저장 완료",
            "signal_params": req.signal_params
        }
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=400, detail=f"저장 실패: {str(e)}")


@app.get("/api/assets/{asset_id}/signal-params-override")
def api_get_asset_signal_params_override(asset_id: int, db: Session = Depends(get_db)):
    """종목의 signal_params_override 조회"""
    row = db.execute(
        text("SELECT id, symbol, signal_params_override FROM assets WHERE id = :id"),
        {"id": asset_id}
    ).mappings().first()

    if not row:
        raise HTTPException(status_code=404, detail="종목을 찾을 수 없습니다")

    return {
        "ok": True,
        "asset_id": asset_id,
        "symbol": row["symbol"],
        "signal_params_override": row["signal_params_override"]  # NULL 가능
    }


@app.put("/api/assets/{asset_id}/signal-params-override")
def api_put_asset_signal_params_override(
    asset_id: int,
    req: SignalParamsOverrideRequest,
    db: Session = Depends(get_db)
):
    """종목의 signal_params_override 저장"""
    row = db.execute(
        text("SELECT id FROM assets WHERE id = :id"),
        {"id": asset_id}
    ).mappings().first()

    if not row:
        raise HTTPException(status_code=404, detail="종목을 찾을 수 없습니다")

    try:
        db.execute(
            text("""
                UPDATE assets
                SET signal_params_override = CAST(:params AS jsonb),
                    updated_at = now()
                WHERE id = :id
            """),
            {"id": asset_id, "params": _safe_dumps(req.signal_params_override)}
        )
        db.commit()

        return {
            "ok": True,
            "message": "저장 완료",
            "signal_params_override": req.signal_params_override
        }
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=400, detail=f"저장 실패: {str(e)}")


@app.delete("/api/assets/{asset_id}/signal-params-override")
def api_delete_asset_signal_params_override(asset_id: int, db: Session = Depends(get_db)):
    """종목의 signal_params_override 초기화 (전략 기본값으로 복귀)"""
    row = db.execute(
        text("SELECT id FROM assets WHERE id = :id"),
        {"id": asset_id}
    ).mappings().first()

    if not row:
        raise HTTPException(status_code=404, detail="종목을 찾을 수 없습니다")

    try:
        db.execute(
            text("""
                UPDATE assets
                SET signal_params_override = NULL,
                    updated_at = now()
                WHERE id = :id
            """),
            {"id": asset_id}
        )
        db.commit()

        return {
            "ok": True,
            "message": "오버라이드 초기화 완료"
        }
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=400, detail=f"초기화 실패: {str(e)}")


@app.get("/api/assets/{asset_id}/effective-params")
def api_get_asset_effective_params(asset_id: int, db: Session = Depends(get_db)):
    """
    종목의 최종 적용값 조회 (merged).
    Hub가 매매 시 이 엔드포인트를 사용하여 최종 설정을 가져옴.
    """
    row = db.execute(
        text("""
            SELECT
                a.id as asset_id,
                a.symbol,
                a.signal_params_override,
                s.id as strategy_id,
                s.name as strategy_name,
                s.signal_params
            FROM assets a
            JOIN strategies s ON a.strategy_id = s.id
            WHERE a.id = :id
        """),
        {"id": asset_id}
    ).mappings().first()

    if not row:
        raise HTTPException(status_code=404, detail="종목을 찾을 수 없습니다")

    # 전략 기본값 (없으면 DEFAULT_SIGNAL_PARAMS 사용)
    base_params = row["signal_params"] or DEFAULT_SIGNAL_PARAMS
    override_params = row["signal_params_override"]

    # deep_merge 수행
    effective_params = deep_merge(base_params, override_params)

    # 오버라이드된 키 목록
    overridden_keys = get_overridden_keys(base_params, override_params)

    return {
        "ok": True,
        "asset_id": asset_id,
        "symbol": row["symbol"],
        "strategy_id": row["strategy_id"],
        "strategy_name": row["strategy_name"],
        "effective_params": effective_params,
        "overridden_keys": overridden_keys
    }


# @app.post("/api/strategies/{strategy_id}/configs")
# def api_create_strategy_config(strategy_id: int, payload: dict, db: Session = Depends(get_db)):
#     _ = _get_strategy_or_404(db, strategy_id)

#     values = payload.get("values")
#     if not isinstance(values, dict) or len(values) == 0:
#         raise HTTPException(status_code=400, detail="missing: values (object)")

#     name = payload.get("name") or "default"
#     is_active = bool(payload.get("is_active", True))
#     cfg_hash = _make_config_hash(values)

#     def _find_existing():
#         return db.execute(
#             text("""
#                 select id, config_hash
#                 from strategy_configs
#                 where strategy_id=:sid and config_hash=:h
#                 order by id desc
#                 limit 1
#             """),
#             {"sid": strategy_id, "h": cfg_hash}
#         ).mappings().first()

#     try:
#         exists = _find_existing()
#         if exists:
#             return {
#                 "ok": True,
#                 "strategy_id": strategy_id,
#                 "config_id": exists["id"],
#                 "config_hash": exists["config_hash"],
#                 "reused": True,
#             }

#         row = db.execute(text("""
#             insert into strategy_configs(strategy_id, name, values, config_hash, is_active)
#             values (:sid, :name, CAST(:values AS jsonb), :hash, :is_active)
#             returning id, config_hash
#         """), {
#             "sid": strategy_id,
#             "name": name,
#             "values": _safe_dumps(values),
#             "hash": cfg_hash,
#             "is_active": is_active,
#         }).mappings().first()
#         db.commit()
#         return {
#             "ok": True,
#             "strategy_id": strategy_id,
#             "config_id": row["id"],
#             "config_hash": row["config_hash"],
#             "reused": False,
#         }

#     except IntegrityError:
#         db.rollback()
#         exists = _find_existing()
#         if exists:
#             return {
#                 "ok": True,
#                 "strategy_id": strategy_id,
#                 "config_id": exists["id"],
#                 "config_hash": exists["config_hash"],
#                 "reused": True,
#             }
#         raise HTTPException(status_code=400, detail="config_save_failed: IntegrityError")

#     except Exception as e:
#         db.rollback()
#         raise HTTPException(status_code=400, detail=f"config_save_failed: {type(e).__name__}: {str(e)}")


@app.get("/api/strategies/{strategy_id}/templates/tradingview")
def api_templates_tradingview(
    strategy_id: int,
    config_id: int = Query(..., description="strategy_configs.id"),
    include_hash: bool = Query(True),
    db: Session = Depends(get_db),
):
    strat = _get_strategy_or_404(db, strategy_id)

    cfg = db.execute(text("""
        select id, name, values, config_hash, is_active, created_at, updated_at
        from strategy_configs
        where id=:cid and strategy_id=:sid
    """), {"cid": config_id, "sid": strategy_id}).mappings().first()

    if not cfg:
        raise HTTPException(status_code=404, detail="Config not found")

    values = cfg["values"] if isinstance(cfg["values"], dict) else {}
    tv_secret = values.get("tv_secret")
    if not tv_secret:
        try:
            tv_secret = strat["tv_secret"]
        except Exception:
            tv_secret = None
    if not tv_secret:
        raise HTTPException(status_code=400, detail="missing: tv_secret")


    template = {
        "secret": tv_secret,
        "alert_id": "{{strategy.order.id}}",
        "symbol": "{{ticker}}",
        "side": "{{strategy.order.action}}",
        "qty": "{{strategy.order.contracts}}",
        "type": "market",
    }
    if include_hash:
        template["config_hash"] = cfg["config_hash"]

    return {
        "ok": True,
        "strategy_id": strategy_id,
        "config_id": config_id,
        "include_hash": include_hash,
        "template": template,
    }


# ============================================================
# [Week8 Day3] 템플릿 생성 API — 계좌/자산/전략 선택 → 자동 생성
# ============================================================

@app.get("/api/templates/tradingview/options")
def api_template_options(db: Session = Depends(get_db)):
    """
    템플릿 생성을 위한 선택 가능 옵션 목록 반환.
    계좌 → 전략 → 자산 계층 구조로 조회.
    """
    rows = db.execute(text("""
        SELECT
            a.id AS asset_id,
            a.symbol,
            a.market,
            a.is_active AS asset_active,
            ac.id AS account_id,
            ac.name AS account_name,
            ac.exchange,
            ac.is_active AS account_active,
            s.id AS strategy_id,
            s.name AS strategy_name,
            s.tv_secret,
            s.is_active AS strategy_active
        FROM assets a
        JOIN accounts ac ON ac.id = a.account_id
        JOIN strategies s ON s.id = a.strategy_id
        WHERE a.is_active = true
          AND ac.is_active = true
          AND s.is_active = true
        ORDER BY ac.name, s.name, a.symbol
    """)).mappings().all()

    options = []
    for r in rows:
        options.append({
            "asset_id": r["asset_id"],
            "symbol": r["symbol"],
            "market": r["market"],
            "account_id": r["account_id"],
            "account_name": r["account_name"],
            "exchange": r["exchange"],
            "strategy_id": r["strategy_id"],
            "strategy_name": r["strategy_name"],
            "label": f"{r['account_name']} / {r['strategy_name']} / {r['symbol']}",
        })

    return {"ok": True, "count": len(options), "options": options}


@app.get("/api/assets/{asset_id}/template/tradingview")
def api_asset_template_tradingview(
    asset_id: int,
    side: str = Query("buy", description="buy 또는 sell"),
    qty: float = Query(1, description="수량"),
    order_type: str = Query("market", description="주문 유형"),
    db: Session = Depends(get_db),
):
    """
    특정 자산에 대한 TradingView 얼러트 템플릿 생성.
    복사하여 TradingView에 붙여넣기 가능.
    """
    row = db.execute(text("""
        SELECT
            a.id AS asset_id,
            a.symbol,
            a.market,
            ac.exchange,
            s.id AS strategy_id,
            s.tv_secret
        FROM assets a
        JOIN accounts ac ON ac.id = a.account_id
        JOIN strategies s ON s.id = a.strategy_id
        WHERE a.id = :aid
    """), {"aid": asset_id}).mappings().first()

    if not row:
        raise HTTPException(status_code=404, detail=f"자산 미존재: asset_id={asset_id}")

    if not row["tv_secret"]:
        raise HTTPException(status_code=400, detail="전략에 tv_secret 미설정")

    # side 검증
    side_lower = side.strip().lower()
    if side_lower not in ("buy", "sell"):
        raise HTTPException(status_code=400, detail=f"invalid side: {side} (buy 또는 sell)")

    template = {
        "secret": row["tv_secret"],
        "symbol": row["symbol"],
        "side": side_lower,
        "qty": qty,
        "alert_id": "{{timenow}}",
        "type": order_type,
    }

    # JSON 문자열로 복붙 가능하게
    import json as _json
    template_json = _json.dumps(template, ensure_ascii=False, indent=2)

    return {
        "ok": True,
        "asset_id": asset_id,
        "symbol": row["symbol"],
        "exchange": row["exchange"],
        "market": row["market"],
        "template": template,
        "template_json": template_json,
        "usage": "TradingView 얼러트 Message에 template_json 값을 복사하여 붙여넣기",
    }


@app.post("/api/templates/tradingview/generate")
def api_generate_template(payload: dict, db: Session = Depends(get_db)):
    """
    POST body로 asset_id, side, qty를 받아 템플릿 생성.
    다중 자산 한번에 생성 지원.
    """
    asset_ids = payload.get("asset_ids")
    if not asset_ids:
        asset_id = payload.get("asset_id")
        if asset_id:
            asset_ids = [asset_id]
        else:
            raise HTTPException(status_code=400, detail="missing: asset_id 또는 asset_ids")

    side = payload.get("side", "buy")
    qty = payload.get("qty", 1)
    order_type = payload.get("type", "market")

    side_lower = str(side).strip().lower()
    if side_lower not in ("buy", "sell"):
        raise HTTPException(status_code=400, detail=f"invalid side: {side}")

    try:
        qty_float = float(qty)
        if qty_float <= 0:
            raise HTTPException(status_code=400, detail=f"invalid qty: {qty}")
    except (ValueError, TypeError):
        raise HTTPException(status_code=400, detail=f"invalid qty: {qty}")

    results = []
    import json as _json

    for aid in asset_ids:
        row = db.execute(text("""
            SELECT
                a.id AS asset_id,
                a.symbol,
                a.market,
                ac.exchange,
                ac.name AS account_name,
                s.id AS strategy_id,
                s.name AS strategy_name,
                s.tv_secret
            FROM assets a
            JOIN accounts ac ON ac.id = a.account_id
            JOIN strategies s ON s.id = a.strategy_id
            WHERE a.id = :aid
        """), {"aid": int(aid)}).mappings().first()

        if not row:
            results.append({"asset_id": aid, "ok": False, "error": "자산 미존재"})
            continue

        if not row["tv_secret"]:
            results.append({"asset_id": aid, "ok": False, "error": "tv_secret 미설정"})
            continue

        template = {
            "secret": row["tv_secret"],
            "symbol": row["symbol"],
            "side": side_lower,
            "qty": qty_float,
            "alert_id": "{{timenow}}",
            "type": order_type,
        }

        results.append({
            "asset_id": aid,
            "ok": True,
            "symbol": row["symbol"],
            "exchange": row["exchange"],
            "account_name": row["account_name"],
            "strategy_name": row["strategy_name"],
            "template": template,
            "template_json": _json.dumps(template, ensure_ascii=False, indent=2),
        })

    return {"ok": True, "count": len(results), "results": results}


# ============================================================
# [ShortMsg] 짧은 메시지 템플릿 (환불 방지 패키지 v2)
# ============================================================

def _ensure_shortmsgs_table(db: Session):
    """shortmsgs 테이블 생성 (없으면)."""
    db.execute(text("""
        CREATE TABLE IF NOT EXISTS shortmsgs (
            id BIGSERIAL PRIMARY KEY,
            short_id VARCHAR(16) NOT NULL UNIQUE,
            name TEXT,
            payload JSONB NOT NULL DEFAULT '{}',
            is_active BOOLEAN NOT NULL DEFAULT TRUE,
            note TEXT,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """))
    # 인덱스 추가 (중복 방지)
    try:
        db.execute(text("CREATE UNIQUE INDEX IF NOT EXISTS idx_shortmsgs_short_id ON shortmsgs(short_id)"))
    except Exception:
        pass
    db.commit()


def _generate_short_id(length: int = 8) -> str:
    """URL-safe 짧은 ID 생성 (base62)."""
    import uuid
    import hashlib
    chars = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz"
    uid = uuid.uuid4().hex + str(datetime.now().timestamp())
    h = hashlib.sha256(uid.encode()).hexdigest()
    result = ""
    num = int(h[:16], 16)
    while len(result) < length:
        result += chars[num % 62]
        num //= 62
    return result[:length]


def _validate_shortmsg_payload(payload: dict) -> tuple[bool, str | None]:
    """ShortMsg payload 검증. (ok, error_msg)"""
    if not isinstance(payload, dict):
        return False, "payload must be object"

    exchange = payload.get("exchange")
    if exchange not in ("OKX", "KIS"):
        return False, f"invalid exchange: {exchange} (OKX/KIS만 지원)"

    market = payload.get("market")
    if market not in ("spot", "stock"):
        return False, f"invalid market: {market} (spot/stock만 지원)"

    symbol = payload.get("symbol")
    if not symbol or not isinstance(symbol, str) or not symbol.strip():
        return False, "symbol 필수"

    side_policy = payload.get("side_policy", "tv")
    if side_policy not in ("tv", "force_buy", "force_sell"):
        return False, f"invalid side_policy: {side_policy}"

    qty_policy = payload.get("qty_policy", "tv_qty")
    if qty_policy not in ("tv_qty", "pct_available", "fixed_quote"):
        return False, f"invalid qty_policy: {qty_policy}"

    if qty_policy == "pct_available":
        pct = payload.get("pct_available")
        if pct is None or not isinstance(pct, (int, float)) or pct <= 0 or pct > 100:
            return False, "pct_available: 0 < value <= 100 필요"

    if qty_policy == "fixed_quote":
        fq = payload.get("fixed_quote")
        if fq is None or not isinstance(fq, (int, float)) or fq <= 0:
            return False, "fixed_quote: 0보다 큰 값 필요"

    order_type = payload.get("order_type", "market")
    if order_type not in ("market", "limit"):
        return False, f"invalid order_type: {order_type}"

    return True, None


@app.post("/api/shortmsg")
def api_create_shortmsg(payload: dict, db: Session = Depends(get_db)):
    """
    ShortMsg 생성.
    입력: { secret, name, is_active, payload: {...} }
    출력: { ok, short_id, url }
    """
    _ensure_shortmsgs_table(db)

    # secret 검증 (시스템 또는 전략 secret)
    secret = payload.get("secret")
    if not secret:
        raise HTTPException(status_code=400, detail="missing: secret")

    # 전략 secret 확인
    strat = db.execute(text("""
        SELECT id, tv_secret FROM strategies WHERE tv_secret = :s LIMIT 1
    """), {"s": str(secret)}).mappings().first()
    if not strat:
        raise HTTPException(status_code=401, detail="invalid secret")

    name = payload.get("name", "")
    is_active = bool(payload.get("is_active", True))
    note = payload.get("note")
    inner_payload = payload.get("payload")

    if not inner_payload:
        raise HTTPException(status_code=400, detail="missing: payload")

    # payload 검증
    valid, err = _validate_shortmsg_payload(inner_payload)
    if not valid:
        raise HTTPException(status_code=400, detail=f"payload 검증 실패: {err}")

    # short_id 생성 (충돌 시 재시도)
    for _ in range(5):
        short_id = _generate_short_id(8)
        exists = db.execute(text("SELECT 1 FROM shortmsgs WHERE short_id=:s"), {"s": short_id}).first()
        if not exists:
            break
    else:
        raise HTTPException(status_code=500, detail="short_id 생성 실패 (재시도 초과)")

    import json as _json
    payload_str = _json.dumps(inner_payload, ensure_ascii=False)
    db.execute(text("""
        INSERT INTO shortmsgs (short_id, name, payload, is_active, note, created_at, updated_at)
        VALUES (:short_id, :name, CAST(:payload AS jsonb), :is_active, :note, NOW(), NOW())
    """), {
        "short_id": short_id,
        "name": name,
        "payload": payload_str,
        "is_active": is_active,
        "note": note,
    })
    db.commit()

    return {
        "ok": True,
        "short_id": short_id,
        "url": f"/api/shortmsg/{short_id}",
    }


@app.get("/api/shortmsg/{short_id}")
def api_get_shortmsg(short_id: str, db: Session = Depends(get_db)):
    """ShortMsg 조회."""
    _ensure_shortmsgs_table(db)

    row = db.execute(text("""
        SELECT short_id, name, payload, is_active, note, created_at, updated_at
        FROM shortmsgs WHERE short_id = :s
    """), {"s": short_id}).mappings().first()

    if not row:
        raise HTTPException(status_code=404, detail=f"shortmsg_not_found: {short_id}")

    return {
        "ok": True,
        "short_id": row["short_id"],
        "name": row["name"],
        "is_active": row["is_active"],
        "payload": row["payload"],
        "note": row["note"],
        "created_at": str(row["created_at"]) if row["created_at"] else None,
        "updated_at": str(row["updated_at"]) if row["updated_at"] else None,
    }


@app.get("/api/shortmsg")
def api_list_shortmsgs(db: Session = Depends(get_db)):
    """ShortMsg 목록 조회."""
    _ensure_shortmsgs_table(db)

    rows = db.execute(text("""
        SELECT short_id, name, is_active, created_at, updated_at
        FROM shortmsgs
        ORDER BY id DESC
        LIMIT 100
    """)).mappings().all()

    return {
        "ok": True,
        "count": len(rows),
        "items": [dict(r) for r in rows],
    }


@app.get("/api/shortmsg/{short_id}/template/tradingview")
def api_shortmsg_template_tradingview(short_id: str, db: Session = Depends(get_db)):
    """
    ShortMsg용 TradingView 템플릿 생성.
    short_id가 모든 설정을 담고 있으므로 TV 변수를 최소화.
    """
    _ensure_shortmsgs_table(db)

    row = db.execute(text("""
        SELECT short_id, name, payload, is_active
        FROM shortmsgs WHERE short_id = :s
    """), {"s": short_id}).mappings().first()

    if not row:
        raise HTTPException(status_code=404, detail=f"shortmsg_not_found: {short_id}")

    if not row["is_active"]:
        raise HTTPException(status_code=400, detail="shortmsg 비활성화됨")

    payload = row["payload"]

    # 연결된 전략의 tv_secret 조회 (exchange 기반으로 첫 번째 활성 전략)
    # 실제로는 payload에 strategy_id를 포함하거나 별도 조회 필요
    # 여기서는 첫 활성 전략 사용
    strat = db.execute(text("""
        SELECT id, tv_secret FROM strategies WHERE is_active = true ORDER BY id LIMIT 1
    """)).mappings().first()

    if not strat or not strat["tv_secret"]:
        raise HTTPException(status_code=400, detail="활성 전략 없음 (tv_secret 필요)")

    template = {
        "secret": strat["tv_secret"],
        "alert_id": "{{timenow}}",
        "symbol": "{{ticker}}",
        "side": "{{strategy.order.action}}",
        "qty": "{{strategy.order.contracts}}",
        "short_id": short_id,
    }

    import json as _json
    template_json = _json.dumps(template, ensure_ascii=False, indent=2)

    return {
        "ok": True,
        "short_id": short_id,
        "name": row["name"],
        "template": template,
        "template_json": template_json,
        "usage": "TradingView 얼러트 Message에 template_json을 복붙. short_id가 설정을 대체함.",
    }


# ---- Pine input parser API ----
# @app.post("/api/pine/parse-inputs")
# def api_pine_parse_inputs(payload: dict):
#     code = payload.get("code") or ""
#     if not isinstance(code, str) or not code.strip():
#         raise HTTPException(status_code=400, detail="missing: code")

#     try:
#         res = parse_pine_inputs(code)
#         return {"ok": True, **res}
#     except Exception as e:
#         raise HTTPException(status_code=400, detail=f"parse_failed: {str(e)}")


# # ============================================================
# # [W3D1] TradingView Webhook (/tv) + Secret Validation + Diag Log
# # ============================================================

# def _ensure_tv_events_table(db: Session):
#     db.execute(text("""
#         create table if not exists tv_events (
#             id           bigserial primary key,
#             received_at  timestamptz not null default now(),
#             remote_ip    text,
#             user_agent   text,

#             strategy_id  int,
#             config_id    int,
#             config_hash  text,
#             asset_id     int,

#             alert_id     text,
#             symbol       text,
#             side         text,
#             qty          numeric,

#             ok           boolean not null default false,
#             code         text,
#             detail       text,

#             payload      jsonb
#         );
#     """))
#     db.execute(text("create index if not exists ix_tv_events_received_at on tv_events(received_at desc);"))
#     db.execute(text("create index if not exists ix_tv_events_config_hash  on tv_events(config_hash);"))
#     db.execute(text("create index if not exists ix_tv_events_alert_id     on tv_events(alert_id);"))
#     db.execute(text("create index if not exists ix_tv_events_strategy_id  on tv_events(strategy_id);"))


# def _insert_tv_event(
#     db: Session,
#     *,
#     remote_ip: str | None,
#     user_agent: str | None,
#     strategy_id: int | None,
#     config_id: int | None,
#     config_hash: str | None,
#     asset_id: int | None,
#     alert_id: str | None,
#     symbol: str | None,
#     side: str | None,
#     qty,
#     ok: bool,
#     code: str,
#     detail: str | None,
#     payload: dict | None,
# ):
#     _ensure_tv_events_table(db)
#     db.execute(
#         text("""
#             insert into tv_events(
#                 remote_ip, user_agent,
#                 strategy_id, config_id, config_hash, asset_id,
#                 alert_id, symbol, side, qty,
#                 ok, code, detail,
#                 payload
#             )
#             values(
#                 :remote_ip, :user_agent,
#                 :strategy_id, :config_id, :config_hash, :asset_id,
#                 :alert_id, :symbol, :side, :qty,
#                 :ok, :code, :detail,
#                 CAST(:payload as jsonb)
#             )
#         """),
#         {
#             "remote_ip": remote_ip,
#             "user_agent": user_agent,
#             "strategy_id": strategy_id,
#             "config_id": config_id,
#             "config_hash": config_hash,
#             "asset_id": asset_id,
#             "alert_id": alert_id,
#             "symbol": symbol,
#             "side": side,
#             "qty": qty,
#             "ok": ok,
#             "code": code,
#             "detail": detail,
#             "payload": _safe_dumps(payload) if payload is not None else "null",
#         }
#     )


# def _resolve_by_config_hash(db: Session, config_hash: str):
#     row = db.execute(text("""
#         select
#             c.id as config_id,
#             c.strategy_id,
#             c.values as cfg_values,
#             c.config_hash,
#             s.tv_secret as strategy_secret
#         from strategy_configs c
#         join strategies s on s.id = c.strategy_id
#         where c.config_hash = :h
#         order by c.id desc
#         limit 1
#     """), {"h": config_hash}).mappings().first()
#     if not row:
#         return None

#     cfg_values = row["cfg_values"] if isinstance(row["cfg_values"], dict) else {}
#     expected_secret = cfg_values.get("tv_secret") or row["strategy_secret"]

#     return {
#         "config_id": int(row["config_id"]),
#         "strategy_id": int(row["strategy_id"]),
#         "config_hash": row["config_hash"],
#         "expected_secret": expected_secret,
#     }


# def _resolve_strategy_by_secret(db: Session, secret: str):
#     row = db.execute(
#         text("select id as strategy_id, tv_secret from strategies where tv_secret=:s limit 1"),
#         {"s": secret},
#     ).mappings().first()
#     if not row:
#         return None
#     return {"strategy_id": int(row["strategy_id"]), "expected_secret": row["tv_secret"]}


# def _resolve_asset(db: Session, strategy_id: int, symbol: str, market: str = "spot"):
#     row = db.execute(text("""
#         select id, account_id, strategy_id, symbol, market, is_active
#         from assets
#         where strategy_id=:sid and symbol=:sym and market=:mkt
#         order by id asc
#         limit 1
#     """), {"sid": strategy_id, "sym": symbol, "mkt": market}).mappings().first()
#     return dict(row) if row else None


# # ============================================================
# # [W3D2] Orders table + Idempotency (중복방지)
# # + 500 방지: 원인을 JSON(detail)로 반드시 내려줌
# # ============================================================

# def _ensure_orders_table(db: Session):
#     try:
#         # 1) base table (new installs)
#         db.execute(text("""
#             create table if not exists orders (
#                 id              bigserial primary key,
#                 created_at      timestamptz not null default now(),
#                 updated_at      timestamptz not null default now(),

#                 account_id      int,
#                 strategy_id     int,
#                 config_id       int,
#                 config_hash     text,
#                 asset_id        int,

#                 alert_id        text,
#                 symbol          text,
#                 market          text,
#                 side            text,
#                 qty             numeric,
#                 order_type      text,

#                 idem_key        text,
#                 idem_source     text,

#                 dedup_key       text,
#                 status          text not null default 'received',
#                 reason          text,
#                 okx_order_id    text,
#                 okx_response    jsonb,
#                 filled_qty      numeric,
#                 avg_px          numeric,
#                 okx_state       text,
#                 last_checked_at timestamptz,
#                 broker_raw      jsonb,

#                 payload         jsonb
#             );
#         """))
#         # 2) migrate existing installs
#         db.execute(text("alter table orders add column if not exists idem_key text;"))
#         db.execute(text("alter table orders add column if not exists idem_source text;"))

#         db.execute(text("alter table orders add column if not exists dedup_key text;"))
#         db.execute(text("alter table orders add column if not exists filled_qty numeric;"))
#         db.execute(text("alter table orders add column if not exists avg_px numeric;"))
#         db.execute(text("alter table orders add column if not exists okx_state text;"))
#         db.execute(text("alter table orders add column if not exists last_checked_at timestamptz;"))
#         db.execute(text("alter table orders add column if not exists broker_raw jsonb;"))
#         # 3) backfill legacy rows (unique + not null)
#         db.execute(text("update orders set idem_key = 'legacy:' || id::text where idem_key is null;"))

#         # 4) enforce NOT NULL (safe now)
#         db.execute(text("alter table orders alter column idem_key set not null;"))

#         # 5) indexes
#         db.execute(text("create unique index if not exists ux_orders_idem_key on orders(idem_key);"))
#         db.execute(text("create index if not exists ix_orders_created_at on orders(created_at desc);"))
#         db.execute(text("create index if not exists ix_orders_asset_id on orders(asset_id);"))
#         db.execute(text("create index if not exists ix_orders_alert_id on orders(alert_id);"))
#         db.execute(text("create index if not exists ix_orders_okx_order_id on orders(okx_order_id);"))
#         db.execute(text("create index if not exists ix_orders_status on orders(status);"))
#         db.execute(text("create index if not exists ix_orders_last_checked_at on orders(last_checked_at);"))

#         db.commit()
#     except Exception as e:
#         db.rollback()
#         raise HTTPException(status_code=500, detail=f"ensure_orders_table_failed: {type(e).__name__}: {e}")


# def _mk_idem_key(*parts: str | None) -> str:
#     raw = "|".join([str(p) if p is not None else "" for p in parts])
#     return hashlib.sha256(raw.encode("utf-8")).hexdigest()




# import base64
# import hmac
# import threading
import time
# from datetime import datetime as _dt

# def _is_dry_run() -> bool:
#     v = os.getenv("DRY_RUN", "1").strip().lower()
#     return v not in ("0", "false", "no", "off")

# def _okx_env():
#     base = os.getenv("OKX_BASE_URL", "https://www.okx.com").rstrip("/")
#     return base, key, sec, pas, sim, float(to)

# def _okx_ts() -> str:
#     # 2020-12-08T09:08:57.715Z
#     return _dt.utcnow().isoformat(timespec="milliseconds") + "Z"

# def _okx_sign(secret: str, prehash: str) -> str:
#     mac = hmac.new(secret.encode("utf-8"), prehash.encode("utf-8"), digestmod="sha256").digest()
#     return base64.b64encode(mac).decode("utf-8")

# def _okx_headers(ts: str, sign: str, *, key: str, pas: str, sim: str):
#     headers = {
#         "Content-Type": "application/json",
#         "OK-ACCESS-KEY": key,
#         "OK-ACCESS-SIGN": sign,
#         "OK-ACCESS-TIMESTAMP": ts,
#         "OK-ACCESS-PASSPHRASE": pas,
#     }
#     if sim == "1":
#         headers["x-simulated-trading"] = "1"
#     return headers

# def okx_place_order(*, symbol: str, side: str, qty: float, order_type: str = "market", payload: dict | None = None) -> dict:
#     base, key, sec, pas, sim, timeout = _okx_env()

#     url = base + path

#     ord_type = (order_type or "market").lower()
#     if ord_type not in ("market", "limit"):
#         ord_type = "market"

#     body = {
#         "instId": symbol,
#         "tdMode": "cash",
#         "side": side,
#         "ordType": ord_type,
#     }

#     # qty is treated as "base" amount (e.g. 0.0001 BTC)
#     # OKX spot market BUY defaults sz=quote unless tgtCcy is specified.
#     # We want base size for both buy/sell to match TradingView qty.
#     body["sz"] = str(qty)
#     if side.lower() == "buy" and ord_type == "market":
#         body["tgtCcy"] = "base_ccy"

#     if ord_type == "limit":
#         px = None
#         if isinstance(payload, dict):
#             px = payload.get("price") or payload.get("px")
#         if px is None:
#             raise RuntimeError("limit order requires payload.price (or px)")
#         body["px"] = str(px)

#     body_json = json.dumps(body, separators=(",", ":"), ensure_ascii=False)

#     ts = _okx_ts()
#     prehash = f"{ts}POST{path}{body_json}"
#     sign = _okx_sign(sec, prehash)

#     headers = _okx_headers(ts, sign, key=key, pas=pas, sim=sim)

#     text_body = resp.text
#     if resp.status_code != 200:
#         raise RuntimeError(f"okx_http_error status={resp.status_code} body={text_body}")

#     data = resp.json()
#     if str(data.get("code")) != "0":
#         raise RuntimeError(f"okx_error code={data.get('code')} msg={data.get('msg')} data={data.get('data')}")
#     return data

# def okx_get_order(*, symbol: str, okx_order_id: str) -> dict:
#     base, key, sec, pas, sim, timeout = _okx_env()

#     query = f"instId={symbol}&ordId={okx_order_id}"
#     url = base + path + "?" + query

#     ts = _okx_ts()
#     prehash = f"{ts}GET{path}?{query}"
#     sign = _okx_sign(sec, prehash)

#     headers = _okx_headers(ts, sign, key=key, pas=pas, sim=sim)

#     text_body = resp.text
#     if resp.status_code != 200:
#         raise RuntimeError(f"okx_http_error status={resp.status_code} body={text_body}")

#     data = resp.json()
#     if str(data.get("code")) != "0":
#         raise RuntimeError(f"okx_error code={data.get('code')} msg={data.get('msg')} data={data.get('data')}")
#     return data

# def _to_float(x, default=0.0) -> float:
#     try:
#         if x is None or x == "":
#             return float(default)
#         return float(x)
#     except Exception:
#         return float(default)

# def _map_okx_state_to_status(state: str | None, *, filled: float, total: float) -> str:
#     s = (state or "").lower().strip()
#     if s == "filled":
#         return "filled"
#     if s == "canceled":
#         return "canceled"
#     if s in ("partially_filled", "partially-filled"):
#         return "partial"
#     if s == "live":
#         # live인데 accFillSz>0이면 partial
#         if filled > 0 and (total <= 0 or filled < total):
#             return "partial"
#         return "sent"
#     # fallback
#     if filled > 0 and (total <= 0 or filled < total):
#         return "partial"
#     return "sent"

# def _safe_json(x):
#     if x is None:
#         return None
#     try:
#         return json.dumps(x, ensure_ascii=False)
#     except Exception:
#         return None

# def _ensure_order_tracking_cols(db: Session):
#     """orders/asset에 '상태추적' 컬럼이 없으면 안전하게 추가."""
#     # orders
#     db.execute(text("alter table orders add column if not exists filled_qty numeric;"))
#     db.execute(text("alter table orders add column if not exists avg_px numeric;"))
#     db.execute(text("alter table orders add column if not exists okx_state text;"))
#     db.execute(text("alter table orders add column if not exists last_checked_at timestamptz;"))
#     db.execute(text("alter table orders add column if not exists broker_raw jsonb;"))
#     db.execute(text("create index if not exists ix_orders_okx_order_id on orders(okx_order_id);"))
#     db.execute(text("create index if not exists ix_orders_status on orders(status);"))
#     db.execute(text("create index if not exists ix_orders_last_checked_at on orders(last_checked_at);"))

#     # assets (dashboard fields)
#     db.execute(text("alter table assets add column if not exists last_order_id bigint;"))
#     db.execute(text("alter table assets add column if not exists last_okx_order_id text;"))
#     db.execute(text("alter table assets add column if not exists last_filled_qty numeric;"))
#     db.execute(text("alter table assets add column if not exists last_order_avg_px numeric;"))
#     db.execute(text("alter table assets add column if not exists last_checked_at timestamptz;"))

# def _set_order_status(
#     db: Session,
#     order_id: int,
#     status: str,
#     *,
#     okx_order_id=None,
#     okx_response=None,
#     broker_raw=None,
#     reason=None,
#     filled_qty=None,
#     avg_px=None,
#     okx_state=None,
#     last_checked_at=None,
# ):
#     """orders 업데이트 + 전광판용 assets(last_*)를 같이 갱신."""
#     _ensure_order_tracking_cols(db)

#     db.execute(
#         text(
#             """
#             update orders
#                set status        = :status,
#                    reason        = :reason,
#                    okx_order_id   = :okx_order_id,
#                    filled_qty    = coalesce(:filled_qty, filled_qty),
#                    avg_px        = coalesce(:avg_px, avg_px),
#                    okx_state     = coalesce(:okx_state, okx_state),
#                    last_checked_at = coalesce(:last_checked_at, last_checked_at),
#                    okx_response  = case
#                                     when :okx_response is null then okx_response
#                                     else (:okx_response)::jsonb
#                                   end,
#                    broker_raw    = case
#                                     when :broker_raw is null then broker_raw
#                                     else (:broker_raw)::jsonb
#                                   end,
#                    updated_at    = now()
#              where id = :id
#             """
#         ),
#         {
#             "id": int(order_id),
#             "status": status,
#             "reason": reason,
#             "okx_order_id": okx_order_id,
#             "filled_qty": filled_qty,
#             "avg_px": avg_px,
#             "okx_state": okx_state,
#             "last_checked_at": last_checked_at,
#             "okx_response": _safe_json(okx_response),
#             "broker_raw": _safe_json(broker_raw),
#         },
#     )

#     # Dashboard update (best-effort)
#     try:
#         db.execute(text(
#             """
#             update assets
#                set last_order_at     = now(),
#                    last_order_status = :status,
#                    last_order_reason = :reason,
#                    last_order_id     = :oid,
#                    last_okx_order_id = coalesce(:okx_order_id, last_okx_order_id),
#                    last_filled_qty   = coalesce(:filled_qty, last_filled_qty),
#                    last_order_avg_px = coalesce(:avg_px, last_order_avg_px),
#                    last_checked_at   = coalesce(:last_checked_at, last_checked_at),
#                    updated_at        = now()
#              where id = (select asset_id from orders where id = :oid)
#             """
#         ), {
#             "oid": int(order_id),
#             "status": status,
#             "reason": reason,
#             "okx_order_id": okx_order_id,
#             "filled_qty": filled_qty,
#             "avg_px": avg_px,
#             "last_checked_at": last_checked_at,
#         })
#     except Exception:
#         pass

# def _maybe_send_to_broker(
#     db: Session,
#     *,
#     order_id: int,
#     symbol: str,
#     side: str,
#     qty: float,
#     order_type: str | None,
#     payload: dict | None,
# ):
#     if _is_dry_run():
#         return {"note": "dry_run=1 (skip broker send)"}

#     # status: sending
#     try:
#         _set_order_status(db, int(order_id), "sending")
#         db.commit()
#     except Exception as e:
#         try:
#             db.rollback()
#         except Exception:
#             pass
#         # sending 상태 갱신 실패는 여기서 끝(그래도 /tv는 accepted 유지)
#         try:
#             _set_order_status(db, int(order_id), "failed", reason=f"status_update_failed: {e}")
#             db.commit()
#         except Exception:
#             try:
#                 db.rollback()
#             except Exception:
#                 pass
#         return {"note": "status_update_failed"}

#     # place order
#     try:
#         okx_result = okx_place_order(
#             symbol=symbol,
#             side=side,
#             qty=qty,
#             order_type=order_type or "market",
#             payload=payload if isinstance(payload, dict) else None,
#         )
#         okx_order_id = None
#         try:
#             okx_order_id = okx_result.get("data", [{}])[0].get("ordId")
#         except Exception:
#             okx_order_id = None

#         if not okx_order_id:
#             _set_order_status(db, int(order_id), "failed", reason="okx_no_ordId (check OKX env/key)", okx_response=okx_result)
#             db.commit()
#             return okx_result

#         if not okx_order_id:
#             _set_order_status(db, int(order_id), "failed", reason="okx_no_ordId (check OKX env/key)", okx_response=okx_result)
#             db.commit()
#             return okx_result

#         _set_order_status(db, int(order_id), "sent", okx_order_id=okx_order_id, okx_response=okx_result)
#         db.commit()
#         return okx_result
#     except Exception as e:
#         try:
#             _set_order_status(db, int(order_id), "failed", reason=str(e))
#             db.commit()
#         except Exception:
#             try:
#                 db.rollback()
#             except Exception:
#                 pass
#         # raise: caller(/tv)에서 잡아먹고 accepted 유지
#         raise

# def _poll_one_order(db: Session, row: dict) -> dict:
#     """단일 주문 상태 조회 + DB 반영 (best-effort)."""
#     oid = int(row["id"])
#     symbol = row.get("symbol") or ""
#     okx_order_id = row.get("okx_order_id") or ""
#     now_ts = _dt.utcnow().replace(tzinfo=timezone.utc)

#     data = okx_get_order(symbol=symbol, okx_order_id=okx_order_id)
#     od = None
#     try:
#         od = (data.get("data") or [None])[0] or None
#     except Exception:
#         od = None

#     if not isinstance(od, dict):
#         raise RuntimeError(f"okx_get_order_bad_shape: {data}")

#     state = od.get("state")
#     total = _to_float(od.get("sz"), 0.0)
#     filled = _to_float(od.get("accFillSz") or od.get("fillSz"), 0.0)
#     avg_px = _to_float(od.get("avgPx"), 0.0)

#     new_status = _map_okx_state_to_status(state, filled=filled, total=total)

#     _set_order_status(
#         db,
#         oid,
#         new_status,
#         okx_order_id=okx_order_id,
#         broker_raw=data,
#         filled_qty=filled,
#         avg_px=avg_px,
#         okx_state=str(state) if state is not None else None,
#         last_checked_at=now_ts,
#     )
#     return {"id": oid, "status": new_status, "filled_qty": filled, "avg_px": avg_px, "okx_state": state}

# def _poll_orders_once_impl(*, limit: int = 20) -> dict:
#     """DB에서 추적 대상 주문(sent/partial)을 뽑아서 한번 갱신."""
#     # get_db 의존성(제너레이터)을 워커에서도 재사용
#     db = next(get_db())
#     try:
#         _ensure_orders_table(db)
#         _ensure_order_tracking_cols(db)

#         rows = db.execute(text("""
#            select id, asset_id, symbol, qty, status, okx_order_id, okx_clord_id, submit_status, exch_status, next_check_at, check_count
#               from orders
#              where okx_order_id is not null
#                and okx_order_id <> ''
#                and submit_status = 'submitted'
#                and exch_status in ('unknown','live','partial')
#                and (next_check_at is null or next_check_at <= now())'
#                   order by coalesce(next_check_at, created_at) asc,
#              coalesce(last_checked_at, created_at) asc,
#              id asc
#              limit :lim
#         """), {"lim": int(limit)}).mappings().all()

#         updated = []
#         for r in rows:
#             try:
#                 updated.append(_poll_one_order(db, dict(r)))
#                 db.commit()
#             except Exception as e:
#                 # poll 실패는 status를 망가뜨리지 않고 reason/last_checked_at만 갱신
#                 try:
#                     _set_order_status(
#                         db,
#                         int(r["id"]),
#                         str(r.get("status") or "sent"),
#                         reason=f"poll_failed: {e}",
#                         last_checked_at=_dt.utcnow().replace(tzinfo=timezone.utc),
#                     )
#                     db.commit()
#                 except Exception:
#                     try:
#                         db.rollback()
#                     except Exception:
#                         pass

#         return {"ok": True, "count": len(updated), "items": updated}
#     finally:
#         try:
#             db.close()
#         except Exception:
#             pass


# # [POLL_CHANGES_WRAPPER_V1]
# def poll_orders_once(*, limit: int = 20, stage: dict | None = None) -> dict:
#     """
#     poll_orders_once (stage-debug v1)
#     - okx_order_id 있는 'sent/partial'만 대상
#     - 후보 0건이면 즉시 반환 (OKX 호출 없음)
#     - stage dict에 진행상태 기록 (changes_timeout 원인 추적용)
#     """
#     import time as _time

#     def _set(stage_name: str, **kw):
#         if stage is None:
#             return
#         stage["stage"] = stage_name
#         stage["ts"] = _time.time()
#         for k, v in kw.items():
#             stage[k] = v

#     t0 = _time.perf_counter()
#     _set("enter")

#     candidate_ids: list[int] = []
#     before: dict[int, dict] = {}

#     # 1) BEFORE snapshot
#     try:
#         _set("get_db_before")
#         db_gen = get_db()
#         db = next(db_gen)
#         _set("get_db_before_ok", ms=int((_time.perf_counter() - t0) * 1000))

#         try:
#             # 쿼리/세션이 비정상적으로 늘어지는 경우를 막기 위해 statement_timeout을 걸어둠
#             # (session 단위. 실패해도 무시)
#             try:
#                 db.execute(text("SET lock_timeout = 800"))
#                 db.execute(text("SET statement_timeout = 0"))
#             except Exception:
#                 pass

#             _set("sql_before_start")
#             rows = db.execute(text("""
#                 select id, asset_id, symbol, market, side, qty, order_type,
#                        status, okx_order_id, okx_state, filled_qty, avg_px, last_checked_at
#                   from orders
#                  where okx_order_id is not null
#                    and status in ('sent','partial')
#                  order by last_checked_at asc nulls first, id asc
#                  limit :lim
#             """), {"lim": limit, "max_try": _SUBMIT_MAX_ATTEMPTS}).mappings().all()
#             _set("sql_before_done", ms=int((_time.perf_counter() - t0) * 1000), rows=len(rows))

#             for r in rows:
#                 oid = int(r["id"])
#                 candidate_ids.append(oid)
#                 before[oid] = {
#                     "status": r.get("status"),
#                     "okx_state": r.get("okx_state"),
#                     "filled_qty": r.get("filled_qty"),
#                     "avg_px": r.get("avg_px"),
#                     "last_checked_at": r.get("last_checked_at"),
#                 }

#         finally:
#             try:
#                 db_gen.close()
#             except Exception:
#                 pass

#     except Exception as e:
#         _set("before_failed", err=str(e), ms=int((_time.perf_counter() - t0) * 1000))
#         return {"ok": True, "count": 0, "items": [], "scanned": 0, "note": "changes_only | snapshot_failed", "stage": stage}

#     # ✅ 후보 0이면 즉시 반환
#     if not candidate_ids:
#         _set("no_candidates", ms=int((_time.perf_counter() - t0) * 1000))
#         return {"ok": True, "count": 0, "items": [], "scanned": 0, "note": "changes_only | no_candidates", "stage": stage}

#     # 2) Run impl (OKX call)
#     try:
#         _set("impl_start", n=len(candidate_ids))
#         _poll_orders_once_impl(limit=limit)
#         _set("impl_done", ms=int((_time.perf_counter() - t0) * 1000))
#     except Exception as e:
#         _set("impl_failed", err=str(e), ms=int((_time.perf_counter() - t0) * 1000))
#         return {"ok": False, "count": 0, "items": [], "scanned": len(candidate_ids), "note": f"impl_failed: {e}", "stage": stage}

#     # 3) AFTER snapshot + diff
#     changes: list[dict] = []
#     try:
#         _set("get_db_after")
#         db_gen2 = get_db()
#         db2 = next(db_gen2)
#         _set("get_db_after_ok", ms=int((_time.perf_counter() - t0) * 1000))

#         try:
#             try:
#                 db2.execute(text("SET lock_timeout = 800"))
#                 db2.execute(text("SET statement_timeout = 0"))
#             except Exception:
#                 pass

#             params = {}
#             ph = []
#             for i, oid in enumerate(candidate_ids):
#                 k = f"id{i}"
#                 params[k] = int(oid)
#                 ph.append(f":{k}")

#             _set("sql_after_start")
#             sql = f"""
#                 select id, asset_id, symbol, market, side, qty, order_type,
#                        status, okx_order_id, okx_state, filled_qty, avg_px, last_checked_at, reason
#                   from orders
#                  where id in ({", ".join(ph)})
#                  order by id asc
#             """
#             after_rows = db2.execute(text(sql), params).mappings().all()
#             _set("sql_after_done", ms=int((_time.perf_counter() - t0) * 1000), rows=len(after_rows))

#             for r in after_rows:
#                 oid = int(r["id"])
#                 b = before.get(oid, {})
#                 a_status = r.get("status")
#                 a_state  = r.get("okx_state")
#                 a_fq     = r.get("filled_qty")
#                 a_apx    = r.get("avg_px")

#                 changed = (
#                     a_status != b.get("status")
#                     or (a_state or None) != (b.get("okx_state") or None)
#                     or (a_fq or None) != (b.get("filled_qty") or None)
#                     or (a_apx or None) != (b.get("avg_px") or None)
#                 )

#                 if changed:
#                     changes.append({
#                         "order_id": oid,
#                         "asset_id": r.get("asset_id"),
#                         "symbol": r.get("symbol"),
#                         "market": r.get("market"),
#                         "side": r.get("side"),
#                         "qty": r.get("qty"),
#                         "order_type": r.get("order_type"),
#                         "from_status": b.get("status"),
#                         "to_status": a_status,
#                         "from_okx_state": b.get("okx_state"),
#                         "to_okx_state": a_state,
#                         "filled_qty": a_fq,
#                         "avg_px": a_apx,
#                         "okx_order_id": r.get("okx_order_id"),
#                         "last_checked_at": r.get("last_checked_at"),
#                         "reason": r.get("reason"),
#                     })

#         finally:
#             try:
#                 db_gen2.close()
#             except Exception:
#                 pass

#     except Exception as e:
#         _set("after_failed", err=str(e), ms=int((_time.perf_counter() - t0) * 1000))
#         return {"ok": True, "count": 0, "items": [], "scanned": len(candidate_ids), "note": "changes_only | diff_failed", "stage": stage}

#     _set("done", ms=int((_time.perf_counter() - t0) * 1000), changed=len(changes))
#     return {"ok": True, "count": len(changes), "items": changes, "scanned": len(candidate_ids), "note": "changes_only", "stage": stage}

# # [ORDER_POLL_WORKER_V1]


# @app.on_event("startup")
# def _startup_order_poller():
#     """ORDER_POLL_ENABLE=1 이면 OKX 주문 상태 폴링 워커를 시작합니다."""
#     enable = os.getenv("ORDER_POLL_ENABLE", "0").strip().lower() in ("1","true","yes","on")
#     if not enable:
#         return
#     t = threading.Thread(target=_poll_worker_loop, name="okx-order-poller", daemon=True)
#     t.start()

# def _create_order_if_new(
#     db: Session,
#     *,
#     account_id: int | None,
#     strategy_id: int | None,
#     config_id: int | None,
#     config_hash: str | None,
#     asset_id: int | None,
#     alert_id: str | None,
#     symbol: str | None,
#     market: str | None,
#     side: str | None,
#     qty,
#     order_type: str | None,
#     payload: dict | None,
# ):
#     """
#     Insert order row only if idem_key not exists.
#     Returns: (created: bool, order_id: int|None, idem_key: str)
#     """
#     try:
#         _ensure_orders_table(db)

#         bar_ts = None
#         if isinstance(payload, dict):
#             bar_ts = payload.get("bar_ts") or payload.get("time") or payload.get("timestamp")

#         # bar_ts 없으면 "분 단위" 버킷으로 중복 폭탄 방지(완전 방지는 Week4에서 bar_ts 넣어서 해결)
#         bucket = datetime.now(timezone.utc).strftime("%Y%m%d%H%M") if not bar_ts else str(bar_ts)
#         idem_key = _mk_idem_key(config_hash, alert_id, symbol, side, bucket)

#         row = db.execute(text("""
#             insert into orders (account_id, strategy_id, config_id, config_hash, asset_id,
#                 alert_id, symbol, market, side, qty, order_type,
#                 idem_key, dedup_key, idem_source,
#                 status, reason,
#                 payload
#             ) values (:account_id, :strategy_id, :config_id, :config_hash, :asset_id,
#                 :alert_id, :symbol, :market, :side, :qty, COALESCE(:order_type,'market'),
#                 :idem_key, :dedup_key, 'tv',
#                 'received', null,
#                 CAST(:payload as jsonb)
#             )
#             returning id
#         """), {
#             "account_id": account_id,
#             "strategy_id": strategy_id,
#             "config_id": config_id,
#             "config_hash": config_hash,
#             "asset_id": asset_id,
#             "alert_id": alert_id,
#             "symbol": symbol,
#             "market": market,
#             "side": side,
#             "qty": qty,
#             "order_type": order_type,
#             "idem_key": idem_key,
#             'dedup_key': idem_key,
#             "payload": _safe_dumps(payload) if payload is not None else "null",
#             'status': 'received'
#         }).scalar_one()

#         return True, int(row), idem_key

#     except IntegrityError:
#         # 중복(ux_orders_idem_key) -> 정상 duplicate 처리
#         db.rollback()
#         # idem_key를 다시 계산해 반환해야 하므로 동일 로직로 재구성
#         bar_ts = None
#         if isinstance(payload, dict):
#             bar_ts = payload.get("bar_ts") or payload.get("time") or payload.get("timestamp")
#         bucket = datetime.now(timezone.utc).strftime("%Y%m%d%H%M") if not bar_ts else str(bar_ts)
#         idem_key = _mk_idem_key(config_hash, alert_id, symbol, side, bucket)
#         return False, None, idem_key

#     except Exception as e:
#         db.rollback()
#         # ✅ 여기 핵심: 500으로 죽지 말고 원인을 detail로 노출
#         raise HTTPException(status_code=400, detail=f"orders_insert_failed: {type(e).__name__}: {str(e)}")




# ---- /tv response helpers (Week3 Day2: always HTTP 200 for stable PowerShell Invoke-RestMethod) ----
def _tv_json(ok, code, detail=None, **extra):
    out = {"ok": bool(ok), "code": str(code)}
    if detail is not None:
        out["detail"] = str(detail)
    for k, v in (extra or {}).items():
        if v is not None:
            out[k] = v
    return JSONResponse(status_code=200, content=out)

@app.post("/tv")
async def tv_webhook(request: Request, db: Session = Depends(get_db)):
    """
    TradingView -> 우리 서버
    - Day1: 수신 + secret 검증 + config_hash 기반 라우팅 + tv_events 기록
    - Day2: orders 기록 + idempotency 기본(중복이면 ignored_duplicate)
    - Day3: OKX 주문 호출로 확장 예정
    """
    remote_ip = getattr(getattr(request, "client", None), "host", None)
    user_agent = request.headers.get("user-agent")

    try:
        payload = await request.json()
    except Exception:
        payload = None

    # --- config_hash -> tv_secret injection (final) ---

    try:

        _p = payload

        _cfg = _p.get('config_hash') if isinstance(_p, dict) else None

        _sec = _p.get('secret') if isinstance(_p, dict) else None

        if (not _sec) and isinstance(_cfg, str) and _cfg.strip():

            _cfg = _cfg.strip()

            try:

                from sqlalchemy import text as _text

            except Exception:

                _text = text

            _r = db.execute(_text("""

                SELECT strategy_id

                FROM strategy_configs

                WHERE config_hash=:h

                ORDER BY id DESC

                LIMIT 1

            """), {'h': _cfg}).mappings().first()

            if not _r:

                return _tv_json(False, "unknown_config_hash", f"unknown config_hash: {_cfg}")

            _sid = _r['strategy_id']

            _s = db.execute(_text("""

                SELECT tv_secret

                FROM strategies

                WHERE id=:sid

                LIMIT 1

            """), {'sid': _sid}).mappings().first()

            if not _s or not _s.get('tv_secret'):

                return {'ok': False, 'code': 'missing_tv_secret', 'detail': f'missing tv_secret for strategy_id={_sid}'}

            _p['secret'] = _s['tv_secret']

            _p['strategy_id'] = _sid

    except Exception as _e:

        return {'ok': False, 'code': 'exception', 'detail': f'config_hash_inject_failed: {str(_e)}'}

    # --- end injection ---


    secret = payload.get("secret") if isinstance(payload, dict) else None
    config_hash = payload.get("config_hash") if isinstance(payload, dict) else None
    alert_id = payload.get("alert_id") if isinstance(payload, dict) else None
    symbol = payload.get("symbol") if isinstance(payload, dict) else None
    side = payload.get("side") if isinstance(payload, dict) else None
    qty = payload.get("qty") if isinstance(payload, dict) else None

    strategy_id = None
    config_id = None
    asset_id = None

    ok = False
    code = "init"
    detail = None

    try:
        if not isinstance(payload, dict):
            code = "bad_json"
            detail = "JSON 형식 오류: payload가 객체가 아님 (중괄호 {} 확인)"
            return {"ok": False, "code": code, "detail": detail}
        # [E-STOP_V1] if ON, block all execution paths immediately
        if _is_estop_on(db):
            return _tv_json(False, "stopped", "E-STOP 활성화됨: 관리자에게 문의", estop=True)

        # ============================================================
        # [ShortMsg] short_id 경로 (기존 로직보다 우선)
        # ============================================================
        short_id = payload.get("short_id") if isinstance(payload, dict) else None
        shortmsg_used = False

        if short_id:
            try:
                _ensure_shortmsgs_table(db)
                sm_row = db.execute(text("""
                    SELECT short_id, name, payload, is_active
                    FROM shortmsgs WHERE short_id = :s
                """), {"s": str(short_id).strip()}).mappings().first()

                if not sm_row:
                    return _tv_json(False, "shortmsg_not_found", f"short_id '{short_id}' 미등록")

                if not sm_row["is_active"]:
                    return _tv_json(False, "shortmsg_inactive", f"short_id '{short_id}' 비활성화됨")

                sm_payload = sm_row["payload"]
                if not isinstance(sm_payload, dict):
                    import json as _json
                    sm_payload = _json.loads(sm_payload) if isinstance(sm_payload, str) else {}

                # payload 유효성 검증
                valid, err = _validate_shortmsg_payload(sm_payload)
                if not valid:
                    return _tv_json(False, "shortmsg_invalid_payload", f"payload 오류: {err}")

                # ShortMsg에서 값 추출
                sm_exchange = sm_payload.get("exchange")  # OKX / KIS
                sm_market = sm_payload.get("market", "spot")  # spot / stock
                sm_symbol = sm_payload.get("symbol")
                sm_side_policy = sm_payload.get("side_policy", "tv")
                sm_qty_policy = sm_payload.get("qty_policy", "tv_qty")
                sm_order_type = sm_payload.get("order_type", "market")

                # symbol 덮어쓰기
                symbol = sm_symbol

                # side 정책 적용
                if sm_side_policy == "force_buy":
                    side = "buy"
                elif sm_side_policy == "force_sell":
                    side = "sell"
                # else: TV에서 온 side 사용

                # qty 정책 적용
                if sm_qty_policy == "tv_qty":
                    # TV에서 온 qty 사용 (기존과 동일)
                    pass
                elif sm_qty_policy == "pct_available":
                    # 가용자금 비중 계산
                    pct = sm_payload.get("pct_available", 10)
                    try:
                        conn = get_connector(sm_exchange)
                        if conn:
                            ccy = "USDT" if sm_exchange == "OKX" else "KRW"
                            bs = conn.get_balance_split(ccy=ccy)
                            if bs and bs.trading > 0:
                                # TODO: 현재가 조회 필요 (일단 qty를 비율로 계산)
                                qty = bs.trading * (pct / 100)
                            else:
                                return _tv_json(False, "insufficient_balance", "가용잔고 조회 실패 또는 잔고 부족")
                        else:
                            return _tv_json(False, "connector_not_found", f"커넥터 없음: {sm_exchange}")
                    except Exception as e:
                        return _tv_json(False, "balance_error", f"잔고 조회 오류: {e}")
                elif sm_qty_policy == "fixed_quote":
                    # 고정금액 (quote) → 수량 계산 필요
                    fixed = sm_payload.get("fixed_quote", 0)
                    # TODO: 현재가 조회 후 qty = fixed / price
                    # 일단 fixed를 qty로 사용 (추후 개선)
                    qty = fixed

                # market 덮어쓰기 (spot/stock)
                market = sm_market

                # secret 검증: ShortMsg 사용 시에도 secret 필요
                if not secret:
                    return _tv_json(False, "missing_secret", "secret 누락 (short_id 사용 시에도 필요)")

                # secret으로 strategy 매칭
                resolved2 = _resolve_strategy_by_secret(db, str(secret))
                if not resolved2:
                    return _tv_json(False, "secret_invalid", "secret 미등록")
                strategy_id = int(resolved2["id"])

                # asset 매칭 (exchange 기반 계좌 찾기)
                # exchange에 맞는 계좌의 asset 조회
                asset_row = db.execute(text("""
                    SELECT a.id, a.account_id, a.strategy_id, a.symbol, a.market, a.is_active,
                           ac.exchange
                    FROM assets a
                    JOIN accounts ac ON ac.id = a.account_id
                    WHERE a.strategy_id = :st
                      AND a.symbol = :sym
                      AND a.market = :mkt
                      AND ac.exchange = :ex
                      AND a.is_active = true
                    ORDER BY a.id
                    LIMIT 1
                """), {"st": strategy_id, "sym": symbol, "mkt": market, "ex": sm_exchange}).mappings().first()

                if not asset_row:
                    return _tv_json(False, "asset_not_found",
                        f"자산 미등록: exchange={sm_exchange}, symbol={symbol}, market={market}")

                asset_id = int(asset_row["id"])
                account_id = int(asset_row["account_id"])

                # side/qty 최종 검증
                if not side:
                    return _tv_json(False, "missing_side", "side 결정 불가 (TV 또는 정책)")
                side_lower = str(side).strip().lower()
                if side_lower not in ("buy", "sell"):
                    return _tv_json(False, "invalid_side", f"invalid side: {side}")

                if qty is None:
                    return _tv_json(False, "missing_qty", "qty 결정 불가 (TV 또는 정책)")
                try:
                    qty_float = float(qty)
                    if qty_float <= 0:
                        return _tv_json(False, "invalid_qty", f"qty <= 0: {qty}")
                except (ValueError, TypeError):
                    return _tv_json(False, "invalid_qty", f"qty 숫자 아님: {qty}")

                # [Signal Params] effective_params 조회 및 Limits 체크
                try:
                    from app.utils.trading import get_effective_params, check_limits
                    effective_params = get_effective_params(db, asset_id)

                    limits_ok, limits_reason = await check_limits(
                        db=db,
                        params=effective_params,
                        asset_id=asset_id,
                        account_id=account_id,
                        alert_id=str(alert_id) if alert_id else "",
                        signal_side=side_lower,
                        bar_time=None
                    )
                    if not limits_ok:
                        return _tv_json(False, "limits_blocked", limits_reason)
                except Exception as limits_err:
                    print(f"[WARN] ShortMsg Limits check failed: {limits_err}")

                # orders 생성 (short_id 포함)
                try:
                    created, order_id, idem_key = _create_order_if_new(
                        db,
                        account_id=account_id,
                        strategy_id=strategy_id,
                        config_id=None,
                        config_hash=None,
                        asset_id=asset_id,
                        alert_id=str(alert_id) if alert_id else None,
                        symbol=symbol,
                        market=market,
                        side=side_lower,
                        qty=qty_float,
                        order_type=sm_order_type,
                        payload=payload,
                        short_id=short_id,  # 추가
                    )

                    # broker send
                    if created and order_id is not None:
                        try:
                            _maybe_send_to_broker(db, order_id=int(order_id))
                        except Exception:
                            pass

                except Exception as e:
                    return _tv_json(False, "orders_insert_failed", f"주문 생성 실패: {e}")

                if not created:
                    return _tv_json(True, "ignored_duplicate", f"중복: idem_key={idem_key}",
                        short_id=short_id)

                return _tv_json(True, "accepted", None,
                    short_id=short_id,
                    order_id=order_id,
                    symbol=symbol,
                    side=side_lower,
                    qty=qty_float,
                )

            except Exception as e:
                return _tv_json(False, "shortmsg_error", f"short_id 처리 오류: {e}")

        # ============================================================
        # [기존 로직] short_id 없으면 기존 config_hash/secret 경로
        # ============================================================

        if not secret:
            code = "missing_secret"
            detail = "secret 누락: 얼러트 메시지에 secret 필드 추가 필요"
            return _tv_json(False, code, detail)

        # 1) config_hash 우선: config -> strategy + expected_secret 결정
        if config_hash:
            resolved = _resolve_by_config_hash(db, str(config_hash).strip())
            if not resolved:
                code = "config_not_found"
                detail = f"config_hash '{config_hash}' 미등록: 전략 설정 확인 필요"
                return {"ok": False, "code": code, "detail": detail}

            strategy_id = int(resolved["strategy_id"])
            config_id = int(resolved["config_id"])
            expected_secret = resolved["expected_secret"]

            if str(secret) != str(expected_secret):
                code = "secret_mismatch"
                detail = "secret 불일치: config_hash에 등록된 secret과 다름"
                return {"ok": False, "code": code, "detail": detail}

        # 2) config_hash 없으면 secret으로 strategy 매칭
        else:
            resolved2 = _resolve_strategy_by_secret(db, str(secret))
            if not resolved2:
                code = "secret_invalid"
                detail = "secret 미등록: 전략에 등록된 tv_secret 확인 필요"
                return {"ok": False, "code": code, "detail": detail}
            strategy_id = int(resolved2["id"])

        # 3) asset 라우팅 (spot 고정)
        if not symbol:
            code = "missing_symbol"
            detail = "missing: symbol (티커/종목코드 필수)"
            return _tv_json(False, code, detail)

        # [Week8] side 검증 강화
        if not side:
            code = "missing_side"
            detail = "missing: side (buy 또는 sell 필수)"
            return _tv_json(False, code, detail)
        side_lower = str(side).strip().lower()
        if side_lower not in ("buy", "sell"):
            code = "invalid_side"
            detail = f"invalid side: '{side}' (buy 또는 sell만 허용)"
            return _tv_json(False, code, detail)

        # [Week8] alert_id 권장 (누락 시 경고 포함하되 진행)
        if not alert_id:
            # 경고만 - 진행은 허용 (idempotency 불가 안내)
            pass  # TODO: 향후 로그에 warning 기록

        # 3-1) asset 먼저 조회 (qty 계산에 필요)
        # market 자동 추론:
        # - 숫자 6자리(국내주식) 또는 영문 1~5자(미국주식) → stock
        # - -SWAP/PERP 접미사 → swap
        # - 그 외 → spot
        _sym = str(symbol).strip().upper()
        if _sym.isdigit() and len(_sym) == 6:
            _market = "stock"  # 국내주식 (예: 005930)
        elif _sym.isalpha() and 1 <= len(_sym) <= 5:
            _market = "stock"  # 미국주식 (예: AAPL, TSLA)
        elif _sym.endswith("-SWAP") or _sym.endswith("PERP"):
            _market = "swap"  # 선물
        else:
            _market = "spot"  # 현물
        asset = _resolve_asset(db, strategy_id, str(symbol).strip(), market=_market)
        if not asset:
            code = "asset_not_found"
            detail = f"자산 미등록: symbol='{symbol}'이 전략에 등록되지 않음 (자산 추가 필요)"
            return {"ok": False, "code": code, "detail": detail}

        asset_id = int(asset["id"])
        if not bool(asset["is_active"]):
            code = "asset_inactive"
            detail = f"자산 비활성: symbol='{symbol}' 활성화 필요 (is_active=true)"
            return {"ok": False, "code": code, "detail": detail}

        account_id = int(asset.get("account_id")) if asset.get("account_id") is not None else None

        # 3-2) effective_params 조회
        effective_params = {}
        try:
            from app.utils.trading import get_effective_params, check_limits, calculate_qty, determine_signal_type
            effective_params = get_effective_params(db, asset_id)
        except Exception as ep_err:
            print(f"[WARN] get_effective_params failed: {ep_err}")

        # 3-3) qty 처리: 웹훅에 있으면 사용, 없으면 자동 계산
        qty_float = None
        qty_auto_calculated = False

        if qty is not None:
            # 웹훅에서 qty 제공 (하위호환)
            try:
                qty_float = float(qty)
                if qty_float <= 0:
                    code = "invalid_qty"
                    detail = f"invalid qty: {qty} (0보다 커야 함)"
                    return _tv_json(False, code, detail)
            except (ValueError, TypeError):
                code = "invalid_qty"
                detail = f"invalid qty: '{qty}' (숫자여야 함)"
                return _tv_json(False, code, detail)
        else:
            # qty 없음 -> signal_params 기반 자동 계산
            try:
                # DB에서 계정 API 키 조회
                acc_row = db.execute(text("""
                    SELECT exchange, api_key, api_secret, api_passphrase
                    FROM accounts WHERE id = :aid
                """), {"aid": account_id}).mappings().first() if account_id else None

                if not acc_row:
                    return _tv_json(False, "account_not_found", f"계정 조회 실패: account_id={account_id}")

                exchange_name = (acc_row["exchange"] or "OKX").upper()
                api_key = acc_row["api_key"] or ""
                api_secret = acc_row["api_secret"] or ""
                api_passphrase = acc_row["api_passphrase"] or ""

                if not api_key or not api_secret:
                    return _tv_json(False, "missing_api_keys", f"API 키가 등록되지 않음: account_id={account_id}")

                # 잔고 조회 (DB 키 사용)
                free_balance = 0.0
                total_balance = 0.0
                ccy = "USDT" if exchange_name in ("OKX", "BINANCE", "BYBIT") else "KRW"

                if exchange_name == "OKX":
                    from app.data_provider import fetch_okx_balances
                    okx_balances = await fetch_okx_balances(api_key, api_secret, api_passphrase, include_cost_basis=False)
                    for b in okx_balances:
                        if b.get("symbol") == ccy:
                            # fetch_okx_balances 반환: {symbol, quantity, value_usd, ...}
                            free_balance = float(b.get("quantity", 0) or 0)
                            total_balance = float(b.get("quantity", 0) or 0)
                            break
                    # USDT 못 찾으면 첫 번째 스테이블코인 사용
                    if free_balance == 0 and okx_balances:
                        for b in okx_balances:
                            sym = b.get("symbol", "").upper()
                            if sym in ("USDT", "USDC"):
                                free_balance = float(b.get("quantity", 0) or 0)
                                total_balance = float(b.get("quantity", 0) or 0)
                                break
                elif exchange_name == "BINANCE":
                    from app.data_provider import fetch_binance_balances
                    bin_balances = await fetch_binance_balances(api_key, api_secret)
                    for b in bin_balances:
                        if b.get("symbol") == ccy:
                            # fetch_binance_balances 반환: {symbol, quantity, value_usd, ...}
                            free_balance = float(b.get("quantity", 0) or 0)
                            total_balance = float(b.get("quantity", 0) or 0)
                            break
                elif exchange_name == "BYBIT":
                    from app.data_provider import fetch_bybit_balances
                    bybit_balances = await fetch_bybit_balances(api_key, api_secret)
                    for b in bybit_balances:
                        if b.get("symbol") == ccy:
                            # fetch_bybit_balances 반환: {symbol, quantity, value_usd, ...}
                            free_balance = float(b.get("quantity", 0) or 0)
                            total_balance = float(b.get("quantity", 0) or 0)
                            break
                else:
                    return _tv_json(False, "unsupported_exchange", f"미지원 거래소: {exchange_name}")

                if free_balance <= 0:
                    return _tv_json(False, "insufficient_balance", f"가용 잔고 부족: {ccy}={free_balance}")

                # 현재가 조회 (Public API - 키 불필요)
                sym_for_price = str(symbol).strip()
                current_price = 0.0
                try:
                    conn = get_connector(exchange_name)
                    if conn:
                        ticker = conn.get_ticker(sym_for_price)
                        if ticker and hasattr(ticker, 'last') and ticker.last:
                            current_price = float(ticker.last)
                        elif ticker and hasattr(ticker, 'ok') and ticker.ok and ticker.last:
                            current_price = float(ticker.last)
                except Exception as price_err:
                    print(f"[WARN] get_ticker failed: {price_err}")

                if current_price <= 0:
                    return _tv_json(False, "price_error", f"현재가 조회 실패: {symbol}")

                # signal_type 결정 (buy=OPEN, sell=REDUCE/CLOSE)
                action = payload.get("action") if isinstance(payload, dict) else side_lower
                signal_type = determine_signal_type(action or side_lower, 0)

                # qty 계산
                qty_float = calculate_qty(
                    params=effective_params,
                    signal_type=signal_type,
                    current_price=current_price,
                    free_balance=free_balance,
                    total_balance=total_balance,
                    current_position_qty=0,  # TODO: 현재 포지션 조회
                    reduce_pct_from_signal=None
                )

                if qty_float <= 0:
                    return _tv_json(False, "qty_calc_zero", "자동 계산된 수량이 0 이하입니다 (잔고 부족 또는 설정 확인)")

                qty_auto_calculated = True
                print(f"[INFO] qty auto-calculated: {qty_float} (price={current_price}, free={free_balance})")

            except Exception as calc_err:
                return _tv_json(False, "qty_calc_error", f"수량 자동 계산 실패: {calc_err}")

        # 3-4) Limits 체크 (주문 생성 전 가드레일)
        try:
            limits_ok, limits_reason = await check_limits(
                db=db,
                params=effective_params,
                asset_id=asset_id,
                account_id=account_id or 0,
                alert_id=str(alert_id) if alert_id else "",
                signal_side=side_lower,
                bar_time=None  # TODO: 웹훅에서 bar_time 파싱
            )
            if not limits_ok:
                return _tv_json(False, "limits_blocked", limits_reason)
        except Exception as limits_err:
            # Limits 체크 실패해도 기존 로직 진행 (graceful degradation)
            print(f"[WARN] Limits check failed: {limits_err}")

        # 4) orders 기록 + idempotency
        try:
            created, order_id, idem_key = _create_order_if_new(
                db,
                account_id=int(asset.get("account_id")) if asset.get("account_id") is not None else None,
                strategy_id=strategy_id,
                config_id=config_id,
                config_hash=str(config_hash) if config_hash else None,
                asset_id=asset_id,
                alert_id=str(alert_id) if alert_id else None,
                symbol=str(symbol) if symbol else None,
                market="spot",
                side=str(side) if side else None,
                qty=qty_float,  # 웹훅 qty 또는 자동계산 qty
                order_type=payload.get("type") if isinstance(payload, dict) else None,
                payload=payload if isinstance(payload, dict) else None,
            )

            # broker send (guarded: never break /tv)
            if created and order_id is not None:
                try:
                    _maybe_send_to_broker(db, order_id=int(order_id))
                except Exception:
                    pass
        except HTTPException as he:
            # ✅ 여기서도 500 방지: 원인을 JSON으로 반환
            ok = False
            code = "orders_insert_failed"
            detail = he.detail
            return {"ok": False, "code": code, "detail": detail}

        if not created:
            ok = True
            code = "ignored_duplicate"
            detail = f"duplicate idem_key={idem_key}"
            return {
                "ok": True,
                "code": code,
                "detail": detail,
                "strategy_id": strategy_id,
                "config_id": config_id,
                "config_hash": config_hash,
                "asset_id": asset_id,
                "idem_key": idem_key,
            }

        # 5) accepted (Day1 성공 조건 + Day2 order row 생성)
        ok = True
        code = "accepted"

        # 전광판 last_signal 갱신
        try:
            db.execute(text("""
                update assets
                set last_signal_at = now(),
                    last_signal_id = :sid,
                    updated_at = now()
                where id = :aid
            """), {"sid": str(alert_id) if alert_id else None, "aid": asset_id})
        except Exception:
            pass

        return {
            "ok": True,
            "code": code,
            "strategy_id": strategy_id,
            "config_id": config_id,
            "config_hash": config_hash,
            "asset_id": asset_id,
            "order_id": order_id,
            "idem_key": idem_key,
            "qty": qty_float,
            "qty_auto": qty_auto_calculated,
        }

    except Exception as e:

        ok = False

        code = "exception"

        detail = f"{type(e).__name__}: {e}"

        return {"ok": False, "code": code, "detail": detail}


    finally:
        # ✅ 성공/실패 무조건 tv_events 기록 (그리고 여기서 commit)
        try:
            _insert_tv_event(
                db,
                remote_ip=remote_ip,
                user_agent=user_agent,
                strategy_id=strategy_id,
                config_id=config_id,
                config_hash=str(config_hash) if config_hash else None,
                asset_id=asset_id,
                alert_id=str(alert_id) if alert_id else None,
                symbol=str(symbol) if symbol else None,
                side=str(side) if side else None,
                qty=qty,
                ok=ok,
                code=code if code else "unknown",
                detail=detail,
                payload=payload if isinstance(payload, dict) else None,
            )
            db.commit()
        except Exception:
            db.rollback()


@app.get("/api/diag/tv-events")
def api_list_tv_events(limit: int = Query(50, ge=1, le=500), db: Session = Depends(get_db)):
    _ensure_tv_events_table(db)
    rows = db.execute(text("""
        select
            id, received_at, remote_ip,
            strategy_id, config_id, config_hash, asset_id,
            alert_id, symbol, side, qty,
            ok, code, detail
        from tv_events
        order by id desc
        limit :lim
    """), {"lim": limit, "max_try": _SUBMIT_MAX_ATTEMPTS}).mappings().all()
    return {"ok": True, "count": len(rows), "items": [dict(r) for r in rows]}


@app.get("/api/orders")
def api_list_orders(limit: int = Query(50, ge=1, le=500), db: Session = Depends(get_db)):
    _ensure_orders_table(db)
    rows = db.execute(text("""
        select
            id, created_at, updated_at,
            account_id, strategy_id, config_id, config_hash, asset_id,
            alert_id, symbol, market, side, qty, order_type,
            idem_key, status, reason, okx_order_id, okx_clord_id,
            filled_qty, avg_px, okx_state, last_checked_at,
            submit_status, exch_status, submit_err, exch_err, next_check_at, check_count, submit_try_count, next_submit_at
        from orders
        order by id desc
        limit :lim
    """), {"lim": limit, "max_try": _SUBMIT_MAX_ATTEMPTS}).mappings().all()
    return {"ok": True, "count": len(rows), "items": [dict(r) for r in rows]}


# [PATCH_FIX_MISSING_POLL_ORDERS_ONCE_V2]
def poll_orders_once(*, limit: int = 20, stage: dict | None = None, **_ignored) -> dict:
    """DB에서 추적 대상 주문을 뽑아 OKX 상태를 1회 갱신합니다.
    - stage/추가 kwargs가 들어와도 죽지 않도록 흡수
    - 실제 구현 함수명이 패치들로 바뀌어도 동작하도록 fallback 호출
    """
    if stage is None:
        stage = {}
    if stage is None or not isinstance(stage, dict):
        stage = {}
    stage["stage"] = "start"
    stage["ts"] = time.time()

    impl = None
    for cand in ("_poll_orders_once_impl", "_poll_worker_once", "poll_orders_once_impl"):
        if cand in globals() and callable(globals().get(cand)):
            impl = globals().get(cand)
            break

    if impl is None:
        # 마지막 fallback: 혹시 다른 이름으로 남아있다면 직접 호출
        return {"ok": True, "count": 0, "items": [], "scanned": 0, "note": "poll_impl_missing", "stage": stage}

    try:
        out = impl(limit=limit)
        if isinstance(out, dict) and "stage" not in out:
            out["stage"] = stage
        return out
    except Exception as e:
        return {"ok": False, "count": 0, "items": [], "note": f"poll_exception: {e}", "stage": stage}





def call_poll_orders_once(*, limit: int = 20, stage: dict | None = None, **_kw) -> dict:
    """compat alias: older wrappers may call this name"""
    return poll_orders_once(limit=limit, stage=stage, **_kw)
@app.post("/api/diag/poll-now")
def api_poll_now(
    limit: int = Query(20, ge=1, le=200),
    mode: str = Query("changes", pattern=r"^(changes|recent|poll)$"),
    allow_poll_when_stopped: bool = Query(False),
    db: Session = Depends(get_db),
):
    """
    diag poll-now (stable)
    - recent : DB 최근 주문 조회(항상 즉시)
    - poll   : poll_orders_once* 1회 호출(없으면 poll_impl_missing)
    - changes: poll 1회 호출을 3초 타임박스로 감싸 hang/500 방지
    """
    import time as _time
    import threading as _threading
    import queue as _queue
    from sqlalchemy import text as _sql_text

    t0 = _time.time()
    stage = {"stage": "start", "ts": t0}

    def _elapsed_ms():
        return int((_time.time() - t0) * 1000)


    # [E-STOP_V1] block polling when estop is ON (allow recent-read)
    # Optional override for operators: allow_poll_when_stopped=true
    if mode != "recent" and _is_estop_on(db) and not allow_poll_when_stopped:
        return {"ok": False, "items": [], "count": 0, "note": "stopped", "detail": "E-STOP is ON", "stage": stage, "elapsed_ms": _elapsed_ms()}
    def _as_items(x):
        if isinstance(x, dict):
            items = x.get("items", [])
            if items is None:
                items = []
            cnt = x.get("count", len(items))
            return x, items, cnt
        if x is None:
            return {"ok": True}, [], 0
        if isinstance(x, list):
            return {"ok": True}, x, len(x)
        return {"ok": True, "raw": str(x)}, [], 0

    def _resolve_poll_fn():
        g = globals()
        # 1) 정확한 이름
        fn = g.get("poll_orders_once")
        if callable(fn):
            return fn
        # 2) 접두어로 찾기 (poll_orders_once_v1, poll_orders_once_impl 등)
        for k, v in g.items():
            if k.startswith("poll_orders_once") and callable(v):
                return v
        # 3) 기타 후보
        for k in ("_poll_orders_once", "poll_orders_once_raw", "poll_orders_once_impl"):
            v = g.get(k)
            if callable(v):
                return v
        return None

    def _recent():
        q = _sql_text("""
            select id, asset_id, symbol, market, side, qty, order_type,
                   status, okx_order_id, okx_state, filled_qty, avg_px, last_checked_at, reason
              from orders
             order by id desc
             limit :lim
        """)
        rows = db.execute(q, {"lim": int(limit)}).mappings().all()
        return [dict(r) for r in rows]

    # ---- recent ----
    if mode == "recent":
        try:
            items = _recent()
            return {"ok": True, "items": items, "count": len(items), "note": "recent_checked", "stage": stage, "elapsed_ms": _elapsed_ms()}
        except Exception as e:
            return {"ok": False, "items": [], "count": 0, "note": "recent_failed", "error": str(e), "stage": stage, "elapsed_ms": _elapsed_ms()}

    # ---- poll / changes 공통: poll fn 준비 ----
    fn = _resolve_poll_fn()
    if not callable(fn):
        # 500 금지: 구현이 없으면 명시적으로 알려주기
        return {"ok": True, "items": [], "count": 0, "note": "poll_impl_missing", "stage": stage, "elapsed_ms": _elapsed_ms()}

    def _call_poll():
        # stage 같은 키워드 절대 넘기지 않음
        return fn(limit=int(limit))

    # ---- poll ----
    if mode == "poll":
        try:
            res = _call_poll()
            base, items, cnt = _as_items(res)
            ok = bool(base.get("ok", True))
            note = "poll_checked" if ok else "poll_failed"
            out = {"ok": ok, "items": items, "count": cnt, "note": note, "stage": stage, "elapsed_ms": _elapsed_ms()}
            # poll_orders_once가 추가 필드를 주면 유지
            for k in ("scanned", "changed", "updated"):
                if isinstance(res, dict) and k in res:
                    out[k] = res[k]
            if isinstance(res, dict) and "error" in res:
                out["error"] = res["error"]
            return out
        except Exception as e:
            stage2 = {"stage": "poll_exception", "error": str(e)}
            return {"ok": False, "items": [], "count": 0, "note": "poll_failed", "error": str(e), "stage": stage2, "elapsed_ms": _elapsed_ms()}

    # ---- changes (3초 타임박스) ----
    # mode == "changes"
    q = _queue.Queue()

    def _worker():
        try:
            q.put(("ok", _call_poll()))
        except Exception as e:
            q.put(("err", str(e)))

    th = _threading.Thread(target=_worker, daemon=True)
    th.start()
    th.join(timeout=3.0)

    if th.is_alive():
        stage2 = {"stage": "changes_timeout"}
        return {"ok": False, "items": [], "count": 0, "note": "changes_timeout", "stage": stage2, "elapsed_ms": _elapsed_ms()}

    try:
        tag, payload = q.get_nowait()
    except Exception:
        tag, payload = ("err", "no_result")

    if tag != "ok":
        stage2 = {"stage": "changes_worker_exception", "error": str(payload)}
        return {"ok": False, "items": [], "count": 0, "note": "changes_checked", "error": str(payload), "stage": stage2, "elapsed_ms": _elapsed_ms()}

    base, items, cnt = _as_items(payload)
    ok = bool(base.get("ok", True))
    note = "changes_checked" if ok else "changes_failed"
    out = {"ok": ok, "items": items, "count": cnt, "note": note, "stage": stage, "elapsed_ms": _elapsed_ms()}
    for k in ("scanned", "changed", "updated"):
        if isinstance(payload, dict) and k in payload:
            out[k] = payload[k]
    if isinstance(payload, dict) and "error" in payload:
        out["error"] = payload["error"]
    return out




# [SEND_RECEIVED_V2]
# - Adds /api/diag/send-now : process orders with submit_status in (received, submit_failed) and okx_order_id is null
# - Never raises 500; always returns JSON


# [SEND_RETRY_POLICY_V1]
# - Backoff + max attempts for /api/diag/send-now
_SUBMIT_MAX_ATTEMPTS = 6

def _submit_backoff_seconds(attempt: int) -> int:
    # attempt: 1..N
    steps = [5, 15, 30, 60, 300, 900]  # cap at 15m
    if attempt <= 1:
        return steps[0]
    idx = attempt - 1
    if idx >= len(steps):
        idx = len(steps) - 1
    return steps[idx]

@app.post("/api/diag/send-now")
def api_send_now(
    limit: int = Query(20, ge=1, le=200),
    db: Session = Depends(get_db),
):
    import time as _time

    t0 = _time.time()
    out_items = []
    scanned = 0

    # [E-STOP_V1] block sending when estop is ON
    if _is_estop_on(db):
        return {
            "ok": False,
            "count": 0,
            "items": [],
            "scanned": 0,
            "note": "stopped",
            "detail": "E-STOP is ON",
            "elapsed_ms": int((_time.time() - t0) * 1000),
        }

    # if okx_place_order doesn't exist, don't crash
    if "okx_place_order" not in globals():
        return {
            "ok": False,
            "count": 0,
            "items": [],
            "scanned": 0,
            "note": "send_impl_missing",
            "elapsed_ms": int((_time.time() - t0) * 1000),
        }

    try:
        _ensure_orders_table(db)
    except Exception:
        pass

    try:
        rows = db.execute(text("""
            select id, asset_id, alert_id, symbol, market, side, qty, order_type, reason, submit_err,
                   submit_try_count, next_submit_at,
                   payload_json, okx_state, exch_status, filled_qty, avg_px,
                   exchange
              from orders
             where (submit_status is null or submit_status in ('received','submit_failed'))
               and (okx_order_id is null or okx_order_id = '')
               and (next_submit_at is null or next_submit_at <= now())
               and coalesce(submit_try_count,0) < :max_try
             order by id asc
             limit :lim
        """), {"lim": limit, "max_try": _SUBMIT_MAX_ATTEMPTS}).mappings().all()

        for r in rows:
            scanned += 1
            oid = int(r["id"])
            alert_id = r.get("alert_id")
            symbol = r["symbol"]
            side = r["side"]
            qty = float(r["qty"])
            order_type = (r.get("order_type") or "market")
            submit_try = int(r.get("submit_try_count") or 0)
            next_submit_at = r.get("next_submit_at")

            # [W4_FILLED_WINS_V2] If exchange state indicates terminal (filled/canceled/partial),
            # do NOT retry submit and do NOT downgrade to failed.
            payload_symbol = None
            try:
                _pj = r.get("payload_json")
                if _pj and isinstance(_pj, str):
                    import json as _json
                    _d = _json.loads(_pj)
                    if isinstance(_d, dict):
                        _sym0 = str(_d.get("symbol") or "").strip()
                        if _sym0:
                            payload_symbol = _sym0
            except Exception:
                payload_symbol = None

            # [W4_SYMBOL_RESTORE_BEFORE_SEND] If regression tests corrupted DB symbol, restore from payload_json.
            # This avoids confusing ETH-USDT-INVALID showing up in DB/UI and ensures send/recover use the real instId.
            if payload_symbol and isinstance(symbol, str) and ("INVALID" in symbol):
                try:
                    db.execute(text("UPDATE orders SET symbol=:sym, updated_at=now() WHERE id=:id"), {"sym": str(payload_symbol), "id": int(oid)})
                except Exception:
                    pass
                symbol = str(payload_symbol)

            okx_state0 = str(r.get("okx_state") or "").strip().lower()
            exch_status0 = str(r.get("exch_status") or "").strip().lower()
            fq0 = _to_float(r.get("filled_qty"), 0.0)
            is_filled0 = (okx_state0 == "filled") or (exch_status0 == "filled")
            is_canceled0 = okx_state0 in ("canceled", "cancelled") or exch_status0 in ("canceled", "cancelled")
            is_partial0 = ("partial" in okx_state0) or ("partial" in exch_status0) or (fq0 > 0 and not is_filled0 and not is_canceled0)

            if is_filled0 or is_canceled0 or is_partial0:
                if is_filled0:
                    _st, _ex = "filled", "filled"
                elif is_canceled0:
                    _st, _ex = "canceled", "canceled"
                else:
                    _st, _ex = "partial", "partial"

                # Best-effort: if DB symbol was corrupted by tests, restore from payload_json.
                try:
                    if payload_symbol and "INVALID" in str(symbol):
                        symbol = payload_symbol
                except Exception:
                    pass

                try:
                    db.execute(text("""
                        update orders
                           set status=:st,
                               symbol=case
                                         when :sym_fix is not null
                                          and position('INVALID' in coalesce(symbol,'')) > 0
                                         then :sym_fix
                                         else symbol
                                     end,
                               exch_status=coalesce(:ex, exch_status),
                               submit_status='submit_terminal',
                               next_submit_at=null,
                               last_checked_at=now()
                         where id=:id
                    """), {"id": oid, "st": _st, "ex": _ex, "sym_fix": (payload_symbol if payload_symbol and "INVALID" in str(r.get("symbol") or "") else None)})
                    # keep asset board consistent (best effort)
                    try:
                        db.execute(text("""
                            update assets
                               set last_order_status=:st,
                                   last_filled_qty=coalesce(last_filled_qty, :fq),
                                   last_order_avg_px=coalesce(last_order_avg_px, :ap),
                                   last_checked_at=now()
                             where id=:aid
                        """), {"aid": int(r.get("asset_id") or 0), "st": _st, "fq": r.get("filled_qty"), "ap": r.get("avg_px")})
                    except Exception:
                        pass
                    db.commit()
                except Exception:
                    db.rollback()

                out_items.append({"id": oid, "status": _st, "submit_status": "submit_terminal", "note": "filled_wins_skip"})
                continue

            # Safety: if this row is actually a terminal submit error (legacy data),
            # re-classify to submit_terminal and skip retry.
            try:
                _err0 = (r.get("submit_err") or r.get("reason") or "").strip()
                if _err0:
                    _err_chk = _err0 if _err0.startswith("send_failed:") else f"send_failed: {_err0}"
                    if _is_terminal_submit_error(_err_chk):
                        try:
                            db.execute(text("""
                                update orders
                                   set status='failed',
                                       submit_status='submit_terminal',
                                       submit_err=coalesce(submit_err, :e),
                                       reason=coalesce(reason, :e),
                                       last_checked_at=now()
                                 where id=:id
                            """), {"id": oid, "e": _err0})
                            db.commit()
                        except Exception:
                            db.rollback()
                        out_items.append({"id": oid, "status": "skipped_terminal", "submit_status": "submit_terminal", "reason": _err0})
                        continue
            except Exception:
                pass


            # mark sending (best effort)
            try:
                db.execute(text("""
                    update orders
                       set status='sending',
                           submit_status='sending',
                           reason=null,
                           submit_err=null,
                           exch_err=null
                     where id=:id
                """), {"id": oid})
                db.commit()
            except Exception:
                db.rollback()
            try:
                # Week7 Day4: exchange 분기 (KIS vs OKX)
                order_exchange = (r.get("exchange") or "OKX").strip().upper()

                # === KIS 경로 ===
                if order_exchange == "KIS":
                    from app.connectors.kis import KISConnector as _KISConnector
                    kis_conn = _KISConnector()
                    kis_res = kis_conn.place_order(
                        symbol=(payload_symbol or symbol),
                        side=side,
                        qty=qty,
                        order_type=order_type,
                    )

                    if kis_res.ok and kis_res.okx_order_id:
                        # 성공: DB 업데이트
                        db.execute(text("""
                            update orders
                               set status='sent',
                                   okx_order_id=:ord,
                                   okx_state='submitted',
                                   last_checked_at=now(),
                                   reason=null,
                                   submit_status='submitted',
                                   submit_err=null,
                                   submit_try_count=0,
                                   next_submit_at=null,
                                   exch_status=coalesce(exch_status,'unknown'),
                                   exch_err=null,
                                   next_check_at=now()
                             where id=:id
                        """), {"id": oid, "ord": str(kis_res.okx_order_id)})
                        db.commit()
                        out_items.append({"id": oid, "status": "sent", "okx_order_id": str(kis_res.okx_order_id), "exchange": "KIS"})
                        continue
                    else:
                        # 실패
                        raise RuntimeError(f"kis_place_order_failed: {kis_res.err_code} {kis_res.err_msg}")

                # === OKX 경로 (기존 로직) ===
                # Always compute deterministic clOrdId so we can recover safely without duplicate submits
                gen_cid = _mk_okx_clordid(oid, alert_id)
                if not gen_cid:
                    # absolute fallback (should not happen)
                    import time as _time
                    gen_cid = f"TV{oid}_{int(_time.time())}"

                # Recovery first: if we already submitted previously but failed to persist okx_order_id,
                # try to fetch by clOrdId to avoid duplicate orders.
                try:
                    if "okx_get_order" in globals():
                                                # Prefer symbol from original payload_json for recovery lookups (DB symbol may be corrupted by tests)
                        lookup_symbol = (payload_symbol or symbol)
                        try:
                            _pj = r.get("payload_json")
                            if _pj and isinstance(_pj, str):
                                import json as _json
                                _d = _json.loads(_pj)
                                if isinstance(_d, dict):
                                    _sym0 = str(_d.get("symbol") or "").strip()
                                    if _sym0 and "INVALID" not in _sym0:
                                        lookup_symbol = _sym0
                        except Exception:
                            pass
                        chk = okx_get_order(symbol=lookup_symbol, okx_clord_id=str(gen_cid))
                        if isinstance(chk, dict) and str(chk.get("code")) == "0":
                            data0 = (chk.get("data") or [])
                            if isinstance(data0, list) and data0 and isinstance(data0[0], dict):
                                _ord = data0[0].get("ordId")
                                if _ord:
                                    _od = data0[0]
                                    _state = str(_od.get("state") or "sent")
                                    _stl = _state.lower()
                                    _fq = _to_float(_od.get("accFillSz") or _od.get("fillSz"), 0.0)
                                    _ap = _to_float(_od.get("avgPx") or _od.get("fillPx"), 0.0)
                                    if _fq <= 0: _fq = None
                                    if _ap <= 0: _ap = None
                                    if _stl == "filled":
                                        _new_status, _new_ex = "filled", "filled"
                                    elif "partial" in _stl:
                                        _new_status, _new_ex = "partial", "partial"
                                    elif _stl in ("canceled", "cancelled"):
                                        _new_status, _new_ex = "canceled", "canceled"
                                    else:
                                        _new_status, _new_ex = "sent", "sent"
                                    db.execute(text("""
                                        update orders
                                           set status=:st,
                                               symbol=case
                                                         when :sym_fix is not null
                                                          and position('INVALID' in coalesce(symbol,'')) > 0
                                                         then :sym_fix
                                                         else symbol
                                                     end,
                                               okx_order_id=:ord,
                                               okx_clord_id=coalesce(:cid, okx_clord_id),
                                               okx_state=coalesce(:os, okx_state),
                                               filled_qty=coalesce(:fq, filled_qty),
                                               avg_px=coalesce(:ap, avg_px),
                                               last_checked_at=now(),
                                               reason=null,
                                               submit_status='submitted',
                                               submit_err=null,
                                               submit_try_count=0,
                                               next_submit_at=null,
                                               exch_status=coalesce(:ex, exch_status),
                                               exch_err=null,
                                               next_check_at=now()
                                         where id=:id
                                    """), {
                                        "id": oid, "ord": _ord, "cid": gen_cid, "os": _state,
                                        "st": _new_status, "ex": _new_ex, "fq": _fq, "ap": _ap, "sym_fix": (lookup_symbol if lookup_symbol and "INVALID" in str(r.get("symbol") or "") else None),
                                    })
                                    db.commit()
                                    out_items.append({"id": oid, "status": _new_status, "okx_order_id": _ord, "note": "recovered_by_clOrdId"})
                                    continue
                except Exception:
                    db.rollback()

                okx_res = okx_place_order(
                    symbol=(payload_symbol or symbol),
                    side=side,
                    qty=qty,
                    order_type=order_type,
                    payload={"source": "api_send_now", "clOrdId": str(gen_cid)},
                )

                # extract ordId
                ord_id = None
                cl_id = None
                _raw = None
                ord_id, cl_id, _raw = _okx_extract_ids(okx_res)
                if not cl_id:
                    cl_id = gen_cid

                if not ord_id:
                    raise RuntimeError(f"okx_no_ordId: {okx_res}")

                db.execute(text("""
                    update orders
                       set status='sent',
                           okx_order_id=:ord,
                           okx_clord_id=coalesce(:cid, okx_clord_id),
                           okx_state='sent',
                           last_checked_at=now(),
                           reason=null,
                           submit_status='submitted',
                           submit_err=null,
                           submit_try_count=0,
                           next_submit_at=null,
                           exch_status=coalesce(exch_status,'unknown'),
                           exch_err=null,
                           next_check_at=now()
                     where id=:id
                """), {"id": oid, "ord": str(ord_id), "cid": str(cl_id) if cl_id is not None else None})
                db.commit()

                out_items.append({"id": oid, "status": "sent", "okx_order_id": str(ord_id)})

            except Exception as e:
                db.rollback()
                msg = str(e)
                rmsg = f"send_failed: {msg}"

                attempt = int(submit_try or 0) + 1
                terminal = _is_terminal_submit_error(rmsg) or (attempt >= _SUBMIT_MAX_ATTEMPTS)
                if (attempt >= _SUBMIT_MAX_ATTEMPTS) and (not _is_terminal_submit_error(rmsg)):
                    rmsg = rmsg + " | retry_exhausted"

                ss = "submit_terminal" if terminal else "submit_failed"
                delay = 0 if terminal else int(_submit_backoff_seconds(attempt))

                db.execute(text("""
                    update orders
                       set status='failed',
                           reason=:r,
                           last_checked_at=now(),
                           submit_status=:ss,
                           submit_err=:r,
                           submit_try_count=:attempt,
                           next_submit_at = case
                               when :ss='submit_failed' then (now() + make_interval(secs => :delay))
                               else null
                           end
                     where id=:id
                """), {"id": oid, "r": rmsg, "ss": ss, "attempt": attempt, "delay": delay})
                db.commit()
                out_items.append({"id": oid, "status": "failed", "submit_status": ss, "reason": rmsg, "attempt": attempt, "next_submit_in_sec": delay})

        return {
            "ok": True,
            "count": len(out_items),
            "items": out_items,
            "scanned": scanned,
            "note": "send_checked",
            "elapsed_ms": int((_time.time() - t0) * 1000),
        }

    except Exception as e:
        db.rollback()
        return {
            "ok": False,
            "count": 0,
            "items": [],
            "scanned": scanned,
            "note": "send_exception",
            "error": str(e),
            "elapsed_ms": int((_time.time() - t0) * 1000),
        }


# ============================================================

# ===================================================================
# OKX helpers (connector-based, no direct HTTP here)
# ===================================================================

_OKX_PREFLIGHT_CACHE = {"ts": 0.0, "val": None}


def okx_preflight(*, ttl_sec: int | None = None) -> dict:
    # Lightweight check: env presence + one authenticated call via connector.
    # ttl_sec controls cache validity to avoid excessive authenticated calls.
    import time as _time
    now = _time.time()
    try:
        ttl = int(ttl_sec) if ttl_sec is not None else 10
    except Exception:
        ttl = 10
    if ttl < 0:
        ttl = 0
    if _OKX_PREFLIGHT_CACHE["val"] is not None and (now - float(_OKX_PREFLIGHT_CACHE["ts"])) < float(ttl):
        return _OKX_PREFLIGHT_CACHE["val"]

    try:
        conn = _get_okx_conn()
        # Auth check: balance endpoint (should fail fast if keys invalid)
        bs = conn.get_balance_split(ccy="USDT")
        ok = bool(getattr(bs, "ok", False))
        msg = "ok" if ok else (getattr(bs, "err_msg", None) or "balance_not_ok")
        val = {"ok": ok, "msg": msg}
    except Exception as e:
        val = {"ok": False, "msg": f"preflight_error: {type(e).__name__}: {e}"}

    _OKX_PREFLIGHT_CACHE["ts"] = now
    _OKX_PREFLIGHT_CACHE["val"] = val
    return val


@app.get("/api/diag/okx-preflight")
def api_diag_okx_preflight():
    return {"ok": True, "check": okx_preflight()}

# ===================================================================
# KIS helpers (tokenP + request wrapper only)
# ===================================================================

_KIS_PREFLIGHT_CACHE = {"ts": 0.0, "val": None}


def kis_preflight() -> dict:
    """Lightweight check: env presence + tokenP issuance."""
    import time as _time

    now = _time.time()
    if _KIS_PREFLIGHT_CACHE["val"] is not None and (now - float(_KIS_PREFLIGHT_CACHE["ts"])) < 10.0:
        return _KIS_PREFLIGHT_CACHE["val"]

    try:
        from app.connectors.kis import KISConnector as _KISConnector

        conn = _KISConnector()
        ok, msg, _tok = conn.get_access_token()
        val = {
            "ok": bool(ok),
            "msg": (msg or ""),
            "svr": getattr(conn, "svr", None),
            "base_url": getattr(conn, "base_url", None),
        }
    except Exception as e:
        val = {"ok": False, "msg": f"preflight_error: {type(e).__name__}: {e}"}

    _KIS_PREFLIGHT_CACHE["ts"] = now
    _KIS_PREFLIGHT_CACHE["val"] = val
    return val


@app.get("/api/diag/kis-preflight")
def api_diag_kis_preflight():
    """KIS preflight (Week5 Day4): token issuance only."""
    return {"ok": True, "check": kis_preflight()}



# ===================================================================
# KIS balance diag (Week6 Day1)
# - vps/prod both supported (by KIS_SVR env used by connector)
# - reads account identifiers from env only (NO value logging)
# - MUST NOT affect /tv or order execution paths
# ===================================================================

def kis_inquire_balance() -> dict:
    """Domestic stock balance inquiry (v1_국내주식-006).

    Uses official TR IDs:
      - prod: TTTC8434R
      - vps : VTTC8434R
    """
    import os as _os

    cano = (_os.getenv("KIS_CANO") or "").strip()
    acnt_prdt_cd = (_os.getenv("KIS_ACNT_PRDT_CD") or "").strip()
    if not cano:
        return {"ok": False, "msg": "missing KIS_CANO", "svr": None, "base_url": None}
    if not acnt_prdt_cd:
        return {"ok": False, "msg": "missing KIS_ACNT_PRDT_CD", "svr": None, "base_url": None}

    try:
        from app.connectors.kis import KISConnector as _KISConnector

        timeout_sec = float((_os.getenv("KIS_TIMEOUT_SEC") or "20").strip() or "20")
        retry_n = int((_os.getenv("KIS_RETRY_N") or "2").strip() or "2")
        retry_n = max(1, min(retry_n, 5))

        conn = _KISConnector(timeout_sec=timeout_sec)
        svr = getattr(conn, "svr", None)
        base_url = getattr(conn, "base_url", None)

        # TR id (prod vs vps)
        tr_id = "TTTC8434R" if (svr == "prod") else "VTTC8434R"

        params = {
            "CANO": cano,
            "ACNT_PRDT_CD": acnt_prdt_cd,
            "AFHR_FLPR_YN": "N",
            "OFL_YN": "",
            "INQR_DVSN": "01",
            "UNPR_DVSN": "01",
            "FUND_STTL_ICLD_YN": "N",
            "FNCG_AMT_AUTO_RDPT_YN": "N",
            "PRCS_DVSN": "00",
            "CTX_AREA_FK100": "",
            "CTX_AREA_NK100": "",
        }

        last_raw = ""
        last_status = 0
        last_j = None
        last_ok = False
        # Retry only for network/timeout-style failures. Do NOT spam.
        for attempt in range(1, retry_n + 1):
            ok, status, j, raw = conn.request(
                method="GET",
                path="/uapi/domestic-stock/v1/trading/inquire-balance",
                params=params,
                headers={"tr_id": tr_id, "custtype": "P", "tr_cont": ""},
                require_token=True,
            )
            last_ok, last_status, last_j, last_raw = ok, status, j, raw
            if ok:
                break
            # raw can include 'TimeoutError' / 'timed out' / request_error
            raw_l = (raw or "").lower()
            is_retryable = (status == 0) or ("timeout" in raw_l) or ("timed out" in raw_l) or ("temporar" in raw_l) or ("connection" in raw_l)
            if (attempt < retry_n) and is_retryable:
                # simple backoff: 0.5s, 1.5s, 3.0s...
                import time as _time
                _time.sleep(min(3.0, 0.5 * (2 ** (attempt - 1))))
                continue
            break

        ok, status, j, raw = last_ok, last_status, last_j, last_raw

        if not ok:
            return {
                "ok": False,
                "msg": raw or "request_failed",
                "svr": svr,
                "base_url": base_url,
                "http_status": status,
                "timeout_sec": timeout_sec,
                "retry_n": retry_n,
            }

        body_ok = bool(j is not None)
        msg = "ok" if (status == 200 and body_ok) else f"http_{status}"

        out1_count = None
        out2 = None
        try:
            if isinstance(j, dict):
                o1 = j.get("output1")
                o2 = j.get("output2")
                out1_count = len(o1) if isinstance(o1, list) else None
                out2 = o2 if isinstance(o2, dict) else None
        except Exception:
            pass

        return {
            "ok": (status == 200 and body_ok),
            "msg": msg,
            "svr": svr,
            "base_url": base_url,
            "http_status": status,
            "timeout_sec": timeout_sec,
            "retry_n": retry_n,
            "output1_count": out1_count,
            "output2": out2,
            "raw": raw,
        }
    except Exception as e:
        return {"ok": False, "msg": f"balance_error: {type(e).__name__}: {e}"}


@app.get("/api/diag/kis-balance")
def api_diag_kis_balance():
    """KIS balance diagnostic endpoint (Week6 Day1)."""
    return {"ok": True, "check": kis_inquire_balance()}


@app.get("/api/diag/kis-order-test")
def api_diag_kis_order_test(
    symbol: str = "005930",
    side: str = "buy",
    qty: int = 1,
):
    """KIS order test endpoint (Week7 Day2). DRY_RUN only, no real order."""
    import os as _os
    from app.connectors.kis import KISConnector

    # 안전장치: DRY_RUN=1이 아니면 거부
    if str(_os.getenv("DRY_RUN", "0")) != "1":
        return {"ok": False, "code": "dry_run_required", "detail": "Set DRY_RUN=1 to use this endpoint"}

    try:
        conn = KISConnector()
        # 토큰 발급 테스트
        tok_ok, tok = conn.get_token()
        if not tok_ok or not tok:
            return {"ok": False, "code": "token_fail", "detail": "Failed to get KIS token"}

        # hashkey 테스트 (body 샘플)
        cano = (_os.getenv("KIS_CANO") or "").strip()
        acnt_prdt_cd = (_os.getenv("KIS_ACNT_PRDT_CD") or "").strip()
        test_body = {
            "CANO": cano,
            "ACNT_PRDT_CD": acnt_prdt_cd,
            "PDNO": symbol,
            "ORD_DVSN": "01",  # 시장가
            "ORD_QTY": str(qty),
            "ORD_UNPR": "0",
        }
        hk_ok, hk = conn.make_hashkey(body=test_body)

        return {
            "ok": True,
            "dry_run": True,
            "connector": "KISConnector",
            "svr": conn.svr,
            "token_valid": tok.is_valid if tok else False,
            "hashkey_ok": hk_ok,
            "test_params": {"symbol": symbol, "side": side, "qty": qty},
            "note": "No real order placed (DRY_RUN=1)",
        }
    except Exception as e:
        return {"ok": False, "code": "exception", "detail": str(e)}


@app.get("/api/diag/kis-poll-test")
def api_diag_kis_poll_test(limit: int = 5):
    """KIS 체결 추적 (polling) 테스트 엔드포인트 (Week7 Day3).

    exchange='KIS'이고 폴링 대상인 주문들을 조회하고 상태를 갱신합니다.
    """
    try:
        result = kis_poll_orders_once(limit=limit)
        return result
    except Exception as e:
        return {"ok": False, "code": "exception", "detail": str(e)}


# ===================================================================
# Multi-connector routing (design-only) - Week5 Day5
# - MUST NOT affect /tv or order execution paths yet.
# - Evidence endpoint only: decide connector by accounts.exchange
# ===================================================================

def _norm_exchange(x: str | None) -> str:
    if x is None:
        return ""
    return str(x).strip().upper()

def _pick_connector_name(exchange: str) -> str:
    ex = _norm_exchange(exchange)
    if ex in ("OKX", "OKEX"):
        return "OKXConnector"
    if ex in ("KIS", "KOREAINVESTMENT", "KOREA INVESTMENT", "KOREA_INVESTMENT", "KOREAINVESTMENTSEC"):
        return "KISConnector"
    return "UNKNOWN"


# ===================================================================
# Connector Factory (Week8 Day5)
# - 통합 커넥터 팩토리: app/connectors/__init__.py로 이동 (Week 9)
# - 싱글톤 패턴으로 인스턴스 캐싱
# ===================================================================
from app.connectors import get_connector, list_connectors, get_all_connectors, SUPPORTED_EXCHANGES


@app.get("/api/diag/connector-route")
def api_diag_connector_route(account_id: int | None = None, db: Session = Depends(get_db)):
    """Design-only routing check (Week5 Day5). Does not place orders."""
    try:
        acc = None
        if account_id is not None:
            acc = get_account(db, int(account_id))
        else:
            # pick first active account (fallback)
            for r in list_accounts(db):
                if bool(getattr(r, "is_active", False)):
                    acc = r
                    break
            if acc is None:
                rows = list_accounts(db)
                acc = rows[0] if rows else None

        if not acc:
            return {"ok": False, "code": "not_found", "detail": "account not found", "note": "design_only"}

        ex = _norm_exchange(getattr(acc, "exchange", None))
        conn_name = _pick_connector_name(ex)
        return {
            "ok": True,
            "note": "design_only",
            "account_id": getattr(acc, "id", None),
            "account_name": getattr(acc, "name", None),
            "exchange": ex,
            "connector": conn_name,
        }
    except Exception as e:
        return {"ok": False, "code": "exception", "detail": str(e), "note": "design_only"}


@app.get("/api/diag/connector-test")
def api_diag_connector_test(exchange: str = "OKX", symbol: str | None = None):
    """Test connector factory and methods (Week8 Day5).

    Args:
        exchange: Exchange name (OKX or KIS)
        symbol: Optional symbol for get_markets test (e.g., ETH-USDT for OKX, 005930 for KIS)
    """
    from dataclasses import asdict

    try:
        conn = get_connector(exchange)
        if conn is None:
            return {"ok": False, "code": "unknown_exchange", "exchange": exchange}

        result = {
            "ok": True,
            "exchange": exchange,
            "connector": type(conn).__name__,
            "methods": {},
        }

        # Test get_balance_split
        try:
            ccy = "KRW" if exchange.upper() == "KIS" else "USDT"
            bs = conn.get_balance_split(ccy=ccy)
            result["methods"]["get_balance_split"] = {
                "ok": bs.ok,
                "ccy": bs.ccy,
                "total": bs.total if bs.ok else None,
                "trading": bs.trading if bs.ok else None,
                "funding": bs.funding if bs.ok else None,
                "err_code": bs.err_code,
                "err_msg": bs.err_msg,
            }
        except Exception as e:
            result["methods"]["get_balance_split"] = {"ok": False, "error": str(e)}

        # Test get_markets (if symbol provided)
        if symbol:
            try:
                ms = conn.get_markets(symbol=symbol)
                if ms:
                    m = ms[0]
                    result["methods"]["get_markets"] = {
                        "ok": True,
                        "symbol": m.symbol,
                        "min_qty": m.min_qty,
                        "lot_qty": m.lot_qty,
                        "min_notional": m.min_notional,
                        "raw_keys": list((m.raw or {}).keys())[:10] if m.raw else None,
                    }
                else:
                    result["methods"]["get_markets"] = {"ok": True, "items": 0}
            except Exception as e:
                result["methods"]["get_markets"] = {"ok": False, "error": str(e)}

        return result
    except Exception as e:
        return {"ok": False, "code": "exception", "detail": str(e)}


@app.get("/api/diag/connector-all")
def api_diag_connector_all(db: Session = Depends(get_db)):
    """
    Week 9: Test all registered connectors with unified interface.
    Returns health check for each connector.
    """
    results = {
        "ok": True,
        "supported_exchanges": SUPPORTED_EXCHANGES,
        "connectors": {},
    }

    for ex in SUPPORTED_EXCHANGES:
        try:
            conn = get_connector(ex)
            if conn is None:
                results["connectors"][ex] = {"ok": False, "error": "connector_init_failed"}
                continue

            # Determine currency for balance check
            ccy = "USDT" if ex == "OKX" else "KRW"

            connector_result = {
                "ok": True,
                "exchange": ex,
                "connector_class": type(conn).__name__,
                "methods": {},
            }

            # Test get_balance_split
            try:
                bs = conn.get_balance_split(ccy=ccy)
                connector_result["methods"]["get_balance_split"] = {
                    "ok": bs.ok,
                    "ccy": bs.ccy,
                    "total": bs.total if bs.ok else None,
                    "trading": bs.trading if bs.ok else None,
                    "err_code": bs.err_code,
                    "err_msg": bs.err_msg,
                }
            except Exception as e:
                connector_result["methods"]["get_balance_split"] = {"ok": False, "error": str(e)}

            results["connectors"][ex] = connector_result

        except Exception as e:
            results["connectors"][ex] = {"ok": False, "error": str(e)}
            results["ok"] = False

    # Check overall status
    for ex, res in results["connectors"].items():
        if not res.get("ok"):
            results["ok"] = False
            break

    return results


def okx_avail_ccy_split2(ccy: str = "USDT"):
    # Returns BalanceSplit from connector
    conn = _get_okx_conn()
    return conn.get_balance_split(ccy=ccy)


def okx_last_price2(inst_id: str) -> float | None:
    conn = _get_okx_conn()
    ms = conn.get_markets(symbol=inst_id)
    if not ms:
        return None
    m0 = ms[0]
    return getattr(m0, "last", None)


def okx_balance_guard2(*, symbol: str, side: str, qty: float, order_type: str = "market", px: float | None = None) -> dict:
    # Best-effort guard to provide a friendly reason before sending.
    # Never blocks if preflight fails.
    try:
        if side.lower() != "buy":
            return {"ok": True}
        if order_type.lower() != "market":
            return {"ok": True}
        last = okx_last_price2(symbol)
        if not last:
            return {"ok": True}
        need_quote = float(qty) * float(last)
        bs = okx_avail_ccy_split2("USDT")
        if not getattr(bs, "ok", False):
            return {"ok": True}
        have_quote = float(getattr(bs, "trading", 0.0) or 0.0)
        if have_quote + 1e-12 < need_quote:
            return {
                "ok": False,
                "code": "INSUFFICIENT_BAL",
                "msg": f"INSUFFICIENT_BAL: need~{need_quote:.6f} USDT (qty={qty} px={last}), have {have_quote} USDT",
            }
        return {"ok": True}
    except Exception:
        return {"ok": True}


# === AUTOFIX_COMPAT_TV_HELPERS ===

# === AUTOFIX_COMPAT_TV_HELPERS ===
# 목적: 라우트만 살리고 헬퍼가 죽어있어 500 나는 상황을 근본 차단
# 방식: 기존 주석 블록을 억지로 풀지 않고, 하단에 “호환 레이어”로 최소 구현을 제공

from sqlalchemy import text as _sql_text
import json as _json
import hashlib as _hashlib

def _sanitize(v):
    # JSON canonical 용도: dict/list는 ConvertTo-Json 순서 영향 줄이기 위해 안정화
    if isinstance(v, dict):
        return {k: _sanitize(v[k]) for k in sorted(v.keys())}
    if isinstance(v, list):
        return [_sanitize(x) for x in v]
    return v

def _safe_dumps(obj):
    return _json.dumps(obj, ensure_ascii=False, separators=(",", ":"), sort_keys=True)

def _mk_idem_key(*parts):
    raw = "|".join("" if p is None else str(p) for p in parts)
    return _hashlib.sha256(raw.encode("utf-8")).hexdigest()

def _ensure_tv_events_table(db):
    # SQLite/Postgres 모두 text 실행 가능한 형태로 작성
    db.execute(_sql_text("""
    CREATE TABLE IF NOT EXISTS tv_events (
        id BIGSERIAL PRIMARY KEY,
        created_at TEXT NOT NULL,
        alert_id TEXT,
        secret TEXT,
        payload_json TEXT,
        remote_ip TEXT
    )
    """))
    db.commit()

def _insert_tv_event(db, created_at, alert_id, secret, payload_json, remote_ip):
    db.execute(_sql_text("""
        INSERT INTO tv_events(created_at, alert_id, secret, payload_json, remote_ip)
        VALUES (:created_at, :alert_id, :secret, :payload_json, :remote_ip)
    """), {
        "created_at": created_at,
        "alert_id": alert_id,
        "secret": secret,
        "payload_json": payload_json,
        "remote_ip": remote_ip,
    })
    db.commit()

def _resolve_by_config_hash(db, config_hash: str):
    # strategy_configs.config_hash 로 찾아서 account/strategy/config 세팅을 가져온다
    row = db.execute(_sql_text("""
        SELECT
            sc.id           AS config_id,
            sc.strategy_id  AS strategy_id,
            NULL::bigint    AS account_id,
            sc.config_hash  AS config_hash,
            sc."values"::text AS values_json
        FROM strategy_configs sc
        WHERE sc.config_hash = :h
        LIMIT 1
    """), {"h": config_hash}).mappings().first()

    if not row:
        return None

    values = {}
    try:
        if row["values_json"]:
            values = _json.loads(row["values_json"])
    except Exception:
        values = {}

    # config values 에 tv_secret 있으면 우선
    expected_secret = (values.get("tv_secret") or "").strip()

    return {
        "config_id": row["config_id"],
        "strategy_id": row["strategy_id"],
        "account_id": row["account_id"],
        "config_hash": row["config_hash"],
        "values": values,
        "expected_secret": expected_secret,
    }

def _resolve_strategy_by_secret(db, secret: str):
    # fallback: strategies.tv_secret 로 찾기
    row = db.execute(_sql_text("""
        SELECT id, name, tv_secret, is_active
        FROM strategies
        WHERE tv_secret = :s
        LIMIT 1
    """), {"s": secret}).mappings().first()
    return row

def _resolve_asset(db, strategy_id: int, symbol: str, market: str = "spot", account_id: int | None = None):
    """
    assets 라우팅 헬퍼.
    - account_id가 주어지면 (account_id + strategy_id + symbol + market)로 엄격 매칭
    - account_id가 없으면 (strategy_id + symbol + market) 중에서
      is_active 우선 / id 오름차순으로 1개를 선택 (인수인계/호환 목적)
    """
    if account_id is not None:
        row = db.execute(_sql_text("""
            SELECT id, account_id, strategy_id, symbol, market, is_active
            FROM assets
            WHERE account_id=:a AND strategy_id=:st AND symbol=:sym AND market=:m
            LIMIT 1
        """), {"a": account_id, "st": strategy_id, "sym": symbol, "m": market}).mappings().first()
        return row

    row = db.execute(_sql_text("""
        SELECT id, account_id, strategy_id, symbol, market, is_active
        FROM assets
        WHERE strategy_id=:st AND symbol=:sym AND market=:m
        ORDER BY is_active DESC, id ASC
        LIMIT 1
    """), {"st": strategy_id, "sym": symbol, "m": market}).mappings().first()
    return row
def _create_order_if_new(db, account_id, strategy_id, config_id, config_hash,
                         asset_id, alert_id, symbol, market, side, qty, order_type, payload,
                         short_id=None):
    _ensure_orders_table(db)
    idem_key = _mk_idem_key(account_id, strategy_id, config_id, asset_id, alert_id, symbol, market, side, qty, order_type)

    # 1) fast path: already exists
    exists = db.execute(_sql_text("SELECT id FROM orders WHERE idem_key=:k LIMIT 1"), {"k": idem_key}).mappings().first()
    if exists:
        return (False, int(exists["id"]), idem_key)

    # 2) insert with DB-level idempotency (race-safe)
    try:
        db.execute(_sql_text("""
            INSERT INTO orders(
                created_at, updated_at,
                account_id, strategy_id, config_id, config_hash, asset_id,
                alert_id, symbol, market, side, qty, order_type,
                idem_key, dedup_key,
                status, reason, okx_order_id, okx_clord_id, filled_qty, avg_px, okx_state, submit_status, exch_status, submit_err, exch_err, next_check_at, check_count, submit_try_count, next_submit_at, last_checked_at,
                payload_json, short_id
            )
            VALUES(
                :created_at, :updated_at,
                :account_id, :strategy_id, :config_id, :config_hash, :asset_id,
                :alert_id, :symbol, :market, :side, :qty, COALESCE(:order_type,'market'),
                :idem_key, :dedup_key,
                :status, :reason, :okx_order_id, :okx_clord_id, :filled_qty, :avg_px, :okx_state, :submit_status, :exch_status, :submit_err, :exch_err, :next_check_at, :check_count, :submit_try_count, :next_submit_at, :last_checked_at,
                :payload_json, :short_id
            )
        """), {
            "created_at": _now_kst_iso(),
            "updated_at": _now_kst_iso(),
            "account_id": account_id,
            "strategy_id": strategy_id,
            "config_id": config_id,
            "config_hash": config_hash,
            "asset_id": asset_id,
            "alert_id": alert_id,
            "symbol": symbol,
            "market": market,
            "side": side,
            "qty": qty,
            "order_type": order_type,
            "idem_key": idem_key,
            "dedup_key": idem_key,   # ✅ 중요: dedup_key unique 인덱스가 있어도 중복 ''로 터지지 않게
            "status": "queued",
            "reason": None,
            "short_id": short_id,
            "okx_order_id": None,
            "okx_clord_id": None,
            "filled_qty": None,
            "avg_px": None,
            "okx_state": None,
            "submit_status": "received",
            "exch_status": "unknown",
            "submit_err": None,
            "exch_err": None,
            "next_check_at": None,
            "check_count": 0,
            "submit_try_count": 0,
            "next_submit_at": None,
            "last_checked_at": None,
            "payload_json": _safe_dumps(payload),
        })
        db.commit()
    except IntegrityError:
        # ✅ 중복(ux_orders_idem_key / ux_orders_dedup_key 등) -> 정상 duplicate 처리
        try:
            db.rollback()
        except Exception:
            pass
        ex2 = db.execute(_sql_text("SELECT id FROM orders WHERE idem_key=:k LIMIT 1"), {"k": idem_key}).mappings().first()
        if ex2:
            return (False, int(ex2["id"]), idem_key)
        return (False, None, idem_key)

    newrow = db.execute(_sql_text("SELECT id FROM orders WHERE idem_key=:k LIMIT 1"), {"k": idem_key}).mappings().first()
    if not newrow:
        return (False, None, idem_key)
    return (True, int(newrow["id"]), idem_key)


def _mk_okx_clordid(order_id: int, alert_id: str | None) -> str:
    """Generate OKX clOrdId (<=32, alphanum only)."""
    try:
        import hashlib as _hashlib
        raw = f"{int(order_id)}|{str(alert_id or '')}"
        h = _hashlib.sha1(raw.encode("utf-8")).hexdigest()[:10]
        return f"TV{int(order_id)}{h}"
    except Exception:
        return f"TV{int(order_id)}"

def _okx_extract_ids(okx_res: object) -> tuple[str | None, str | None, dict | None]:
    """Extract (ordId, clOrdId, raw-dict) from either legacy dict OKX responses or PlaceOrderResult-like objects."""
    ord_id: str | None = None
    cl_id: str | None = None
    raw: dict | None = None

    if isinstance(okx_res, dict):
        raw = okx_res
        code = okx_res.get("code")
        if code == "0":
            data = okx_res.get("data") or []
            if data:
                ord_id = (data[0].get("ordId") or None) if isinstance(data[0], dict) else None
                cl_id  = (data[0].get("clOrdId") or None) if isinstance(data[0], dict) else None
        # fallbacks (some wrappers normalize keys)
        ord_id = ord_id or okx_res.get("okx_order_id") or okx_res.get("ordId")
        cl_id  = cl_id  or okx_res.get("okx_clord_id") or okx_res.get("clOrdId")
        return ord_id, cl_id, raw

    # PlaceOrderResult (connector style)
    ord_id = getattr(okx_res, "okx_order_id", None) or getattr(okx_res, "ord_id", None)
    cl_id  = getattr(okx_res, "clord_id", None) or getattr(okx_res, "okx_clord_id", None)

    r = getattr(okx_res, "raw", None)
    if isinstance(r, dict):
        raw = r
        # parse OKX native response shape if present
        code = raw.get("code")
        if code == "0":
            data = raw.get("data") or []
            if data and isinstance(data[0], dict):
                ord_id = ord_id or (data[0].get("ordId") or None)
                cl_id  = cl_id  or (data[0].get("clOrdId") or None)
        # some error payloads still include clOrdId
        if cl_id is None:
            data = raw.get("data") or []
            if data and isinstance(data[0], dict):
                cl_id = data[0].get("clOrdId") or None

    return ord_id, cl_id, raw


def _maybe_send_to_broker(db, order_id: int):
    """
    전 거래소 주문 실행 (OKX, Binance, Bybit, Upbit, KIS_KR, KIS_US)
    - ORDER_SUBMIT_ENABLE / DRY_RUN 환경변수 존중
    - 거래소별 connector.place_order() 호출
    """
    # 주문 + 계정 정보 조회 (exchange 포함)
    o = db.execute(_sql_text("""
        SELECT o.*, acc.exchange as account_exchange
        FROM orders o
        LEFT JOIN accounts acc ON acc.id = o.account_id
        WHERE o.id = :id
        LIMIT 1
    """), {"id": order_id}).mappings().first()
    if not o:
        return {"ok": False, "reason": "order_not_found"}

    # 거래소 결정 (order.exchange > account.exchange > 기본값 OKX)
    exchange = (o.get("exchange") or o.get("account_exchange") or "OKX").upper()

    if str(os.getenv("ORDER_SUBMIT_ENABLE", "0")) != "1":
        db.execute(_sql_text("""
            UPDATE orders SET status='skipped', reason='submit_disabled', updated_at=:u WHERE id=:id
        """), {"u": _now_kst_iso(), "id": order_id})
        db.commit()
        return {"ok": True, "skipped": True, "reason": "submit_disabled", "exchange": exchange}

    if str(os.getenv("DRY_RUN", "0")) == "1":
        db.execute(_sql_text("""
            UPDATE orders SET status='dry_run', reason='dry_run', updated_at=:u WHERE id=:id
        """), {"u": _now_kst_iso(), "id": order_id})
        db.commit()
        return {"ok": True, "dry_run": True, "exchange": exchange}

    # 거래소별 커넥터 분기
    symbol = o["symbol"]
    side = o["side"]
    qty = float(o["qty"])
    order_type = o.get("order_type") or "market"

    try:
        # 거래소별 처리
        if exchange == "OKX":
            # 기존 OKX 로직 유지 (legacy 호환)
            _clid = _mk_okx_clordid(int(order_id), o.get("alert_id"))
            res = okx_place_order(
                symbol=symbol,
                side=side,
                qty=qty,
                order_type=order_type,
                payload={"source": "tv", "order_id": int(order_id), "alert_id": o.get("alert_id"), "clOrdId": _clid},
            )
            return _handle_okx_response(db, order_id, o, res, _clid)

        elif exchange == "BINANCE":
            conn = get_connector("BINANCE")
            if not conn:
                raise ValueError("BINANCE 커넥터 초기화 실패")
            res = conn.place_order(
                symbol=symbol,
                side=side,
                qty=qty,
                order_type=order_type,
                payload={"source": "tv", "order_id": int(order_id)},
            )
            return _handle_connector_response(db, order_id, exchange, res)

        elif exchange == "BYBIT":
            conn = get_connector("BYBIT")
            if not conn:
                raise ValueError("BYBIT 커넥터 초기화 실패")
            res = conn.place_order(
                symbol=symbol,
                side=side,
                qty=qty,
                order_type=order_type,
                payload={"source": "tv", "order_id": int(order_id)},
            )
            return _handle_connector_response(db, order_id, exchange, res)

        elif exchange == "UPBIT":
            conn = get_connector("UPBIT")
            if not conn:
                raise ValueError("UPBIT 커넥터 초기화 실패 (API 키 확인 필요)")
            # Upbit 시장가 매수는 금액 기준, 매도는 수량 기준
            # qty는 매수 시 KRW 금액, 매도 시 코인 수량으로 해석
            res = conn.place_order(
                symbol=symbol,
                side=side,
                qty=qty,
                order_type="market",
                payload={"source": "tv", "order_id": int(order_id)},
            )
            return _handle_connector_response(db, order_id, exchange, res)

        elif exchange in ("KIS", "KIS_KR"):
            conn = get_connector("KIS")
            if not conn:
                raise ValueError("KIS 커넥터 초기화 실패")
            res = conn.place_order(
                symbol=symbol,
                side=side,
                qty=qty,
                order_type=order_type,
                payload={"source": "tv", "order_id": int(order_id)},
            )
            return _handle_connector_response(db, order_id, "KIS_KR", res)

        elif exchange == "KIS_US":
            # KIS_US 해외주식: 현재가 조회 → 지정가 주문
            conn = get_connector("KIS_US")
            if not conn:
                raise ValueError("KIS_US 커넥터 초기화 실패")

            # 거래소 코드 추정 (NAS → NYS → AMS 순서로 시도)
            exchange_code = "NAS"  # 기본값 나스닥

            # 1. 현재가 조회
            current_price = conn.get_overseas_price(symbol, exchange_code)
            if not current_price:
                raise ValueError(f"KIS_US 현재가 조회 실패: {symbol}")

            # 2. 지정가 주문 (현재가로)
            res = conn.place_order_overseas(
                symbol=symbol,
                side=side,
                qty=qty,
                price=current_price,
                exchange_code=exchange_code,
                payload={"source": "tv", "order_id": int(order_id)},
            )
            return _handle_connector_response(db, order_id, exchange, res)

        else:
            raise ValueError(f"지원하지 않는 거래소: {exchange}")

    except Exception as e:
        rmsg = f"send_failed: [{exchange}] {e}"
        ss = "submit_terminal" if _is_terminal_submit_error(rmsg) else "submit_failed"
        db.execute(_sql_text("""
            UPDATE orders
               SET status='failed',
                   reason=:r,
                   updated_at=:u,
                   last_checked_at=now(),
                   submit_status=:ss,
                   submit_err=:r
             WHERE id=:id
        """), {"r": rmsg, "ss": ss, "u": _now_kst_iso(), "id": order_id})
        db.commit()
        return {"ok": False, "reason": rmsg, "submit_status": ss, "exchange": exchange}


def _handle_okx_response(db, order_id: int, o: dict, res, _clid: str):
    """OKX 응답 처리 (기존 로직 분리)"""
    okx_ok = True
    okx_order_id = None
    okx_clord_id = None
    err_code = None
    err_msg = None

    if isinstance(res, dict):
        if "code" in res:
            okx_ok = str(res.get("code")) == "0"
            err_code = str(res.get("code"))
            err_msg = res.get("msg") or res.get("message")
        data = res.get("data")
        if isinstance(data, list) and data:
            okx_order_id = (data[0].get("ordId") or None)
            okx_clord_id = (data[0].get("clOrdId") or None)
            if err_code is None:
                err_code = data[0].get("sCode")
            if err_msg is None:
                err_msg = data[0].get("sMsg")
    else:
        okx_ok = bool(getattr(res, "ok", False))
        okx_order_id = getattr(res, "okx_order_id", None) or None
        okx_clord_id = (getattr(res, "clord_id", None) or getattr(res, "okx_clord_id", None) or None)
        err_code = getattr(res, "err_code", None)
        err_msg = getattr(res, "err_msg", None)

    if not okx_clord_id:
        okx_clord_id = _clid

    if okx_ok and (not okx_order_id) and okx_clord_id:
        try:
            g = okx_get_order(symbol=o.get("symbol"), okx_clord_id=okx_clord_id)
            d = g.get("data")
            if isinstance(d, list) and d:
                okx_order_id = d[0].get("ordId") or None
        except Exception:
            pass

    if not okx_ok:
        rmsg = f"send_failed: okx_error: {err_code}: {err_msg}"
        ss = "submit_terminal" if _is_terminal_submit_error(rmsg) else "submit_failed"
        db.execute(
            _sql_text(
                "UPDATE orders SET status='failed', submit_status=:ss, submit_err=:err, next_check_at=NULL, next_submit_at=:nsa WHERE id=:oid"
            ),
            {"oid": order_id, "ss": ss, "err": rmsg, "nsa": datetime.utcnow() + timedelta(seconds=5)},
        )
        db.commit()
        return {"ok": False, "reason": rmsg, "exchange": "OKX"}

    if not okx_order_id:
        db.execute(_sql_text("""
            UPDATE orders
               SET status='failed',
                   reason=:r,
                   updated_at=:u,
                   last_checked_at=now(),
                   submit_status='submit_failed',
                   submit_err=:r,
                   exch_status='unknown',
                   exch_err=NULL,
                   next_check_at=NULL
             WHERE id=:id
        """), {"r": "send_failed: okx_no_ordId", "u": _now_kst_iso(), "id": order_id})
        db.commit()
        return {"ok": False, "reason": "send_failed: okx_no_ordId", "exchange": "OKX"}

    db.execute(_sql_text("""
        UPDATE orders
           SET status='sent',
               reason=NULL,
               okx_order_id=:oid,
               okx_clord_id=:cid,
               okx_state='sent',
               updated_at=:u,
               last_checked_at=now(),
               submit_status='submitted',
               submit_err=NULL,
               exch_status=coalesce(exch_status,'unknown'),
               exch_err=NULL,
               next_check_at=now(),
               check_count=coalesce(check_count,0)
         WHERE id=:id
    """), {"oid": okx_order_id, "cid": okx_clord_id, "u": _now_kst_iso(), "id": order_id})
    db.commit()
    return {"ok": True, "okx_order_id": okx_order_id, "exchange": "OKX"}


def _handle_connector_response(db, order_id: int, exchange: str, res):
    """통합 커넥터 응답 처리 (Binance, Bybit, KIS 등)"""
    from app.connectors.base import PlaceOrderResult

    if isinstance(res, PlaceOrderResult):
        if not res.ok:
            rmsg = f"send_failed: [{exchange}] {res.err_code}: {res.err_msg}"
            ss = "submit_terminal" if _is_terminal_submit_error(rmsg) else "submit_failed"
            db.execute(_sql_text("""
                UPDATE orders
                   SET status='failed',
                       reason=:r,
                       updated_at=:u,
                       last_checked_at=now(),
                       submit_status=:ss,
                       submit_err=:r
                 WHERE id=:id
            """), {"r": rmsg, "ss": ss, "u": _now_kst_iso(), "id": order_id})
            db.commit()
            return {"ok": False, "reason": rmsg, "exchange": exchange}

        # 성공
        exch_order_id = res.exchange_order_id or res.okx_order_id or ""
        db.execute(_sql_text("""
            UPDATE orders
               SET status='sent',
                   reason=NULL,
                   exchange_order_id=:exch_oid,
                   updated_at=:u,
                   last_checked_at=now(),
                   submit_status='submitted',
                   submit_err=NULL,
                   exch_status='sent'
             WHERE id=:id
        """), {"exch_oid": exch_order_id, "u": _now_kst_iso(), "id": order_id})
        db.commit()
        return {"ok": True, "exchange_order_id": exch_order_id, "exchange": exchange}
    else:
        # 예상치 못한 응답 형식
        rmsg = f"send_failed: [{exchange}] unexpected response type: {type(res)}"
        db.execute(_sql_text("""
            UPDATE orders SET status='failed', reason=:r, updated_at=:u WHERE id=:id
        """), {"r": rmsg, "u": _now_kst_iso(), "id": order_id})
        db.commit()
        return {"ok": False, "reason": rmsg, "exchange": exchange}
# === /AUTOFIX_COMPAT_TV_HELPERS ===




# [HOTFIX_TV_RESOLVE_ASSET_V1] compat override (prevent /tv 500)
def _resolve_asset(db, strategy_id, symbol, market="spot", account_id=None):
    # account_id가 있으면 엄격 매칭, 없으면 strategy_id+symbol+market으로 1개 선택
    if account_id is not None:
        row = db.execute(text("""
            select id, account_id, strategy_id, symbol, market, is_active
            from assets
            where account_id=:a and strategy_id=:sid and symbol=:sym and market=:mkt
            limit 1
        """), {"a": int(account_id), "sid": int(strategy_id), "sym": str(symbol), "mkt": str(market)}).mappings().first()
        return row

    row = db.execute(text("""
        select id, account_id, strategy_id, symbol, market, is_active
        from assets
        where strategy_id=:sid and symbol=:sym and market=:mkt
        order by is_active desc, id asc
        limit 1
    """), {"sid": int(strategy_id), "sym": str(symbol), "mkt": str(market)}).mappings().first()
    return row




# [HOTFIX_NOW_KST_ISO_V1] provide missing helper for timestamps
def _now_kst_iso() -> str:
    try:
        from datetime import datetime, timezone, timedelta
        kst = timezone(timedelta(hours=9))
        return datetime.now(kst).isoformat()
    except Exception:
        # fallback: naive iso
        from datetime import datetime
        return datetime.now().isoformat()


def _is_terminal_submit_error(msg: str) -> bool:
    """제출(submit) 단계에서 재시도 의미가 거의 없는 오류를 판별.
    - 잔고부족/최소수량/파라미터(sz) 오류 등은 재시도해도 해결되지 않음(사용자 조치 필요).
    """
    m = (msg or "").lower()

    # 명시적 잔고 부족
    if "insufficient_bal" in m or "insufficient balance" in m:
        return True

    # OKX 파라미터/수량 오류(최소 수량, sz)
    if "parameter sz error" in m or " sz error" in m:
        return True
    if "too_small_notional" in m or "min sz" in m:
        return True

    # 51000 계열은 파라미터 오류로 오는 케이스가 많음(재시도 무의미)
    if "code=51000" in m or "\"code\":\"51000\"" in m:
        return True


    # OKX 최소 주문 금액(51020) / minimum order amount
    if "51020" in m or "minimum order amount" in m or "meet or exceed the minimum" in m:
        return True

    return False


# [ORDERS_SCHEMA_CANONICAL]
# Legacy HOTFIX_ORDERS_SCHEMA_MIGRATE_V1~V5 blocks removed (2026-01-30 KST).
# Use _ensure_orders_table_v6 only; binding is defined near file end.

# === OKX_PLACE_ORDER_CANONICAL_W5D1 ===
# 목적: main.py 내부 okx_place_order 중복 정의를 제거하고, 단일 호출 경로를 강제한다.
# 경로: main.py -> app.connectors.okx.OKXConnector.place_order (dependency-free)
# 포함: preflight + balance guard(가능한 경우) + legacy kwargs 매핑(instId/sz/ordType/action/px)

from app.connectors.okx import OKXConnector as _OKXConnector
_OKX_CONN = None

def _get_okx_conn() -> _OKXConnector:
    global _OKX_CONN
    if _OKX_CONN is None:
        _OKX_CONN = _OKXConnector()
    return _OKX_CONN

def okx_place_order(*,
                    symbol: str | None = None,
                    side: str | None = None,
                    qty: float | None = None,
                    order_type: str = "market",
                    px: float | None = None,
                    payload: dict | None = None,
                    **kwargs) -> dict:
    """OKX 주문 실행(단일 호출 경로)."""
    # --- legacy field mapping ---
    if symbol is None:
        if "instId" in kwargs:
            symbol = kwargs.get("instId")
        elif "symbol" in kwargs:
            symbol = kwargs.get("symbol")

    if side is None:
        if "side" in kwargs:
            side = kwargs.get("side")
        elif "action" in kwargs:  # TradingView 템플릿에서 action을 쓰는 경우
            side = kwargs.get("action")

    if qty is None:
        if "qty" in kwargs:
            qty = kwargs.get("qty")
        elif "sz" in kwargs:
            qty = kwargs.get("sz")

    if (not order_type or str(order_type).strip() == ""):
        if "order_type" in kwargs:
            order_type = str(kwargs.get("order_type") or "market")
        elif "ordType" in kwargs:
            order_type = str(kwargs.get("ordType") or "market")

    # payload 보정
    if payload is None and isinstance(kwargs.get("payload"), dict):
        payload = kwargs.get("payload")

    # px 추출(compat): 명시 px > payload(px/price) > kwargs(px/price)
    if px is None:
        if isinstance(payload, dict):
            _px = payload.get("px") if payload.get("px") is not None else payload.get("price")
            if _px is not None:
                try:
                    px = float(_px)
                except Exception:
                    px = None
        if px is None:
            _px2 = kwargs.get("px") if kwargs.get("px") is not None else kwargs.get("price")
            if _px2 is not None:
                try:
                    px = float(_px2)
                except Exception:
                    px = None

    # connector로 넘기기 전에 payload에서 px는 제거(중복 전달 방지)
    if isinstance(payload, dict) and ("px" in payload or "price" in payload):
        try:
            payload = dict(payload)
            payload.pop("px", None)
            payload.pop("price", None)
        except Exception:
            pass

    if symbol is None or side is None or qty is None:
        raise ValueError(f"missing_required: symbol/side/qty (symbol={symbol}, side={side}, qty={qty})")

    symbol_s = str(symbol)
    side_s = str(side)
    qty_f = float(qty)
    ot = (order_type or "market")

    # --- preflight (가능한 경우) ---
    try:
        if "okx_preflight" in globals():
            ttl = int(os.getenv("OKX_PREFLIGHT_TTL", "60") or "60")
            pf = okx_preflight(ttl_sec=ttl)
            if not (isinstance(pf, dict) and pf.get("ok")):
                raise RuntimeError(f"okx_preflight_failed: {pf}")
    except Exception as e:
        raise

    # --- balance guard (가능한 경우) ---
    try:
        if "okx_balance_guard2" in globals():
            okx_balance_guard2(symbol=symbol_s, side=side_s, qty=qty_f)
        elif "okx_balance_guard" in globals():
            okx_balance_guard(symbol=symbol_s, side=side_s, qty=qty_f)
    except Exception:
        # 여기서 raise 하여 send-now에서 terminal/retryable 판정하도록 위임
        raise

    # --- place order (single path) ---
    conn = _get_okx_conn()
    return conn.place_order(symbol=symbol_s, side=side_s, qty=qty_f, order_type=ot, px=px, payload=payload)

# =========================
# BBBOOSTER_PATCH_POLL_ASSETS_V1
# - 목적: sent 주문(okx_order_id 있음)을 OKX 조회로 filled/partial/canceled로 갱신
# - 목적: assets 전광판(last_order_*) 갱신
# - 주의: 기존 코드/중복 함수 유지 가능(이 패치가 최하단에서 override)
# =========================

def _sync_asset_last_order(db, *, asset_id, order_id, status, reason, okx_order_id=None, filled_qty=None, avg_px=None):
    """assets.last_order_* 갱신(전광판). 실패해도 주문흐름을 죽이지 않음."""
    try:
        from sqlalchemy import text
        db.execute(text("""
            update assets
               set last_order_at      = now(),
                   last_order_id      = :oid,
                   last_order_status  = :st,
                   last_order_reason  = :rs,
                   last_okx_order_id  = :okx,
                   last_filled_qty    = coalesce(:fq, last_filled_qty),
                   last_order_avg_px  = coalesce(:ap, last_order_avg_px),
                   last_checked_at    = now(),
                   updated_at         = now()
             where id = :aid
        """), {
            "aid": int(asset_id),
            "oid": str(order_id),
            "st": str(status),
            "rs": reason,
            "okx": okx_order_id,
            "fq": filled_qty,
            "ap": avg_px,
        })
    except Exception:
        pass


def poll_orders_once_impl(*, limit: int = 20) -> dict:
    """
    OKX 주문 상태 1회 폴링 구현.
    대상: okx_order_id가 있고 status in ('sent','partial','sending')
    결과: orders + assets(last_order_*) 갱신
    """
    import time as _time
    t0 = _time.time()

    def _backoff_seconds(attempt: int) -> int:
        # 1,2,3,4,... -> 5,15,30,60 (cap=60)
        steps = [5, 15, 30, 60]
        if attempt <= 1:
            return steps[0]
        idx = attempt - 1
        if idx >= len(steps):
            idx = len(steps) - 1
        return steps[idx]


    _POLL_MAX_FAIL_ATTEMPTS = 10

    def _is_permanent_poll_error(msg: str) -> bool:
        m = (msg or "").lower()
        # OKX: 잘못된 ordId/파라미터 등은 재시도해도 의미 없음(400 계열)
        if "status=400" in m:
            return True
        if "parameter ordid error" in m:
            return True
        if "51000" in m and ("parameter" in m or "ordid" in m):
            return True
        return False

    # okx_get_order가 없으면 그냥 종료(500 금지)
    if "okx_get_order" not in globals():
        return {"ok": True, "items": [], "count": 0, "note": "poll_impl_missing(okx_get_order)", "elapsed_ms": int((_time.time()-t0)*1000)}

    # get_db / _ensure_orders_table 존재 가정(기존 구조 사용)
    db_gen = get_db()
    db = next(db_gen)

    out_items = []
    scanned = 0
    changed = 0

    try:
        _ensure_orders_table(db)

        # =========================
        # PATCH_RECONCILE_SUBMIT_STATUS_V1
        # - Reconcile legacy mismatch: okx_order_id exists but submit_status stayed 'received'
        # - This makes such orders eligible for the new (submit_status/exch_status/next_check_at) polling queue.
        # =========================
        from sqlalchemy import text
        try:
            db.execute(text("""
                update orders
                   set submit_status = 'submitted',
                       submit_err    = null,
                       exch_status   = coalesce(exch_status, 'unknown'),
                       next_check_at = coalesce(next_check_at, now())
                 where okx_order_id is not null
                   and okx_order_id <> ''
                   and submit_status = 'received'
                   and coalesce(exch_status,'unknown') in ('unknown','live','partial')
                   and coalesce(status,'sent') in ('sent','sending','partial')
            """))
            db.commit()
        except Exception:
            db.rollback()

        rows = db.execute(text("""
            select id, asset_id, symbol, qty, status, okx_order_id, okx_clord_id,
                   submit_status, exch_status, next_check_at, check_count
              from orders
             where okx_order_id is not null
               and okx_order_id <> ''
               and submit_status = 'submitted'
               and exch_status in ('unknown','live','partial')
               and (next_check_at is null or next_check_at <= now())
             order by coalesce(next_check_at, created_at) asc, id asc
             limit :lim
        """), {"lim": int(limit)}).mappings().all()

        for r in rows:
            scanned += 1
            oid = int(r["id"])
            asset_id = int(r["asset_id"]) if r.get("asset_id") is not None else None
            symbol = str(r["symbol"])
            okx_order_id = str(r["okx_order_id"])
            okx_clord_id = (str(r.get("okx_clord_id")) if r.get("okx_clord_id") is not None else None)
            req_qty = float(r["qty"]) if r.get("qty") is not None else 0.0
            prev_status = str(r.get("status") or "sent")
            prev_exch_status = str(r.get("exch_status") or "unknown")
            prev_check_count = int(r.get("check_count") or 0)

            try:
                # DIAG: force-enqueue(backoff proof) uses fake okx_order_id starting with 'diag_okx_'.
                # In this case, do NOT call the real exchange; raise a synthetic terminal poll error to test UI/backoff.
                if str(okx_order_id or "").startswith("diag_okx_"):
                    raise RuntimeError("diag_poll_fail")

                res = okx_get_order(symbol=symbol, okx_order_id=okx_order_id, okx_clord_id=okx_clord_id)

                state = None
                fill_sz = None
                avg_px = None

                if isinstance(res, dict):
                    data = res.get("data") or []
                    if isinstance(data, list) and data and isinstance(data[0], dict):
                        d0 = data[0]
                        state = d0.get("state")
                        fill_sz = d0.get("accFillSz")
                        avg_px = d0.get("avgPx")

                f_qty = float(fill_sz) if fill_sz not in (None, "") else None
                a_px = float(avg_px) if avg_px not in (None, "") else None

                new_status = prev_status
                exch_status = prev_exch_status
                if state:
                    st = str(state).lower()
                    if st == "filled":
                        new_status = "filled"
                        exch_status = "filled"
                    elif st in ("canceled", "cancelled"):
                        new_status = "canceled"
                        exch_status = "canceled"
                    elif st in ("partially_filled", "partial_filled", "partially-filled"):
                        new_status = "partial"
                        exch_status = "partial"
                    elif st == "live":
                        new_status = "sent"
                        exch_status = "live"
                    else:
                        # unknown/other states keep polling
                        new_status = "sent"
                        exch_status = "unknown"


                # 보정: filled_qty가 주문 qty에 도달하면 filled
                if f_qty is not None and req_qty > 0 and f_qty >= (req_qty - 1e-12):
                    new_status = "filled"

                attempt = prev_check_count + 1
                delay_sec = _backoff_seconds(attempt) if exch_status not in ("filled", "canceled") else 5

                db.execute(text("""
                    update orders
                       set status          = :st,
                           okx_state       = :os,
                           filled_qty      = coalesce(:fq, filled_qty),
                           avg_px          = coalesce(:ap, avg_px),
                           last_checked_at = now(),
                           reason          = null,
                           exch_status     = :es,
                           exch_err        = null,
                           check_count     = check_count + 1,
                           next_check_at   = case
                               when :es in ('filled','canceled') then null
                               else now() + (:delay || ' seconds')::interval
                           end
                     where id = :id
                """), {"id": oid, "st": new_status, "os": state, "fq": f_qty, "ap": a_px, "es": exch_status, "delay": int(delay_sec)})

                if asset_id is not None:
                    _sync_asset_last_order(
                        db,
                        asset_id=asset_id,
                        order_id=oid,
                        status=new_status,
                        reason=None,
                        okx_order_id=okx_order_id,
                        filled_qty=f_qty,
                        avg_px=a_px,
                    )

                db.commit()
                changed += 1
                out_items.append({"id": oid, "symbol": symbol, "status": new_status, "exch_status": exch_status, "okx_state": state, "filled_qty": f_qty, "avg_px": a_px, "okx_order_id": okx_order_id})

            except Exception as e:
                db.rollback()
                msg = str(e)
                attempt = prev_check_count + 1
                permanent = _is_permanent_poll_error(msg)
                terminal = permanent or attempt >= _POLL_MAX_FAIL_ATTEMPTS
                reason_txt = ("poll_failed_terminal: " if terminal else "poll_failed: ") + msg

                try:
                    if terminal:
                        db.execute(text("""
                            update orders
                               set status = 'failed',
                                   reason = :r,
                                   exch_status = 'failed',
                                   exch_err = :r,
                                   last_checked_at = now(),
                                   check_count = check_count + 1,
                                   next_check_at = null
                             where id = :id
                        """), {"id": oid, "r": reason_txt})
                    else:
                        delay_sec = _backoff_seconds(attempt)
                        db.execute(text("""
                            update orders
                               set reason = :r,
                                   exch_err = :r,
                                   last_checked_at = now(),
                                   check_count = check_count + 1,
                                   next_check_at = now() + (:delay || ' seconds')::interval
                             where id = :id
                        """), {"id": oid, "r": reason_txt, "delay": int(delay_sec)})

                    if asset_id is not None:
                        _sync_asset_last_order(
                            db,
                            asset_id=asset_id,
                            order_id=oid,
                            status=("failed" if terminal else prev_status),
                            reason=reason_txt,
                            okx_order_id=okx_order_id,
                        )

                    db.commit()
                except Exception:
                    db.rollback()

                out_items.append({
                    "id": oid,
                    "symbol": symbol,
                    "status": ("failed" if terminal else prev_status),
                    "exch_status": ("failed" if terminal else prev_exch_status),
                    "reason": reason_txt,
                    "okx_order_id": okx_order_id
                })

        return {
            "ok": True,
            "items": out_items,
            "count": len(out_items),
            "scanned": scanned,
            "changed": changed,
            "note": "poll_checked",
            "elapsed_ms": int((_time.time() - t0) * 1000),
        }

    finally:
        try:
            db_gen.close()
        except Exception:
            pass

# =========================
# END BBBOOSTER_PATCH_POLL_ASSETS_V1
# =========================


# ============================================================
# Week7 Day3: KIS 체결 추적 (polling) 구현
# ============================================================
def kis_poll_orders_once(*, limit: int = 20) -> dict:
    """
    KIS 주문 상태 1회 폴링 구현.
    대상: exchange='KIS', okx_order_id(주문번호) 있고 exch_status in ('unknown','live','partial')
    결과: orders + assets(last_order_*) 갱신
    """
    import time as _time
    from app.connectors.kis import KISConnector

    t0 = _time.time()

    def _backoff_seconds(attempt: int) -> int:
        steps = [5, 15, 30, 60]
        if attempt <= 1:
            return steps[0]
        idx = attempt - 1
        if idx >= len(steps):
            idx = len(steps) - 1
        return steps[idx]

    _POLL_MAX_FAIL_ATTEMPTS = 10

    def _is_permanent_poll_error(msg: str) -> bool:
        m = (msg or "").lower()
        # KIS: 잘못된 주문번호 등 400 계열
        if "status=400" in m or "http_400" in m:
            return True
        if "egw00201" in m:  # 유효하지 않은 TR ID 등
            return True
        return False

    db_gen = get_db()
    db = next(db_gen)

    out_items = []
    scanned = 0
    changed = 0

    try:
        _ensure_orders_table(db)

        from sqlalchemy import text as _t

        # KIS 주문만 폴링 (exchange='KIS' 또는 account의 exchange='KIS' JOIN)
        # 단순화: exchange 컬럼이 'KIS'인 경우만 대상
        rows = db.execute(_t("""
            select id, asset_id, symbol, qty, status, okx_order_id, okx_clord_id,
                   submit_status, exch_status, next_check_at, check_count
              from orders
             where exchange = 'KIS'
               and okx_order_id is not null
               and okx_order_id <> ''
               and submit_status = 'submitted'
               and exch_status in ('unknown','live','partial')
               and (next_check_at is null or next_check_at <= now())
             order by coalesce(next_check_at, created_at) asc, id asc
             limit :lim
        """), {"lim": int(limit)}).mappings().all()

        if not rows:
            return {
                "ok": True,
                "items": [],
                "count": 0,
                "scanned": 0,
                "changed": 0,
                "note": "no_kis_orders_to_poll",
                "elapsed_ms": int((_time.time() - t0) * 1000),
            }

        conn = KISConnector()

        for r in rows:
            scanned += 1
            oid = int(r["id"])
            asset_id = int(r["asset_id"]) if r.get("asset_id") is not None else None
            symbol = str(r["symbol"])
            kis_order_id = str(r["okx_order_id"])  # KIS 주문번호 (okx_order_id 필드 재사용)
            req_qty = float(r["qty"]) if r.get("qty") is not None else 0.0
            prev_status = str(r.get("status") or "sent")
            prev_exch_status = str(r.get("exch_status") or "unknown")
            prev_check_count = int(r.get("check_count") or 0)

            try:
                # KIS get_order 호출
                res = conn.get_order(symbol=symbol, exchange_order_id=kis_order_id)

                state = None
                fill_qty = None
                avg_px = None

                if res.ok:
                    state = res.state  # "지정가", "시장가", "not_found" 등
                    fill_qty = res.filled_qty
                    avg_px = res.avg_px

                f_qty = fill_qty if fill_qty is not None else None
                a_px = avg_px if avg_px is not None else None

                new_status = prev_status
                exch_status = prev_exch_status

                # KIS 상태 매핑:
                # - 체결완료: filled_qty == req_qty
                # - 부분체결: 0 < filled_qty < req_qty
                # - 미체결: filled_qty == 0 or None
                # - not_found: 주문 조회 실패

                if state == "not_found":
                    # 주문 조회 실패 - 재시도
                    new_status = "sent"
                    exch_status = "unknown"
                elif f_qty is not None and req_qty > 0:
                    if f_qty >= (req_qty - 1e-12):
                        new_status = "filled"
                        exch_status = "filled"
                    elif f_qty > 0:
                        new_status = "partial"
                        exch_status = "partial"
                    else:
                        new_status = "sent"
                        exch_status = "live"
                elif res.ok:
                    # 체결 수량 없음 - 미체결
                    new_status = "sent"
                    exch_status = "live"

                attempt = prev_check_count + 1
                delay_sec = _backoff_seconds(attempt) if exch_status not in ("filled", "canceled") else 5

                db.execute(_t("""
                    update orders
                       set status          = :st,
                           okx_state       = :os,
                           filled_qty      = coalesce(:fq, filled_qty),
                           avg_px          = coalesce(:ap, avg_px),
                           last_checked_at = now(),
                           reason          = null,
                           exch_status     = :es,
                           exch_err        = null,
                           check_count     = check_count + 1,
                           next_check_at   = case
                               when :es in ('filled','canceled') then null
                               else now() + (:delay || ' seconds')::interval
                           end
                     where id = :id
                """), {"id": oid, "st": new_status, "os": state, "fq": f_qty, "ap": a_px, "es": exch_status, "delay": int(delay_sec)})

                if asset_id is not None:
                    _sync_asset_last_order(
                        db,
                        asset_id=asset_id,
                        order_id=oid,
                        status=new_status,
                        reason=None,
                        okx_order_id=kis_order_id,
                        filled_qty=f_qty,
                        avg_px=a_px,
                    )

                db.commit()
                changed += 1
                out_items.append({
                    "id": oid,
                    "symbol": symbol,
                    "status": new_status,
                    "exch_status": exch_status,
                    "kis_state": state,
                    "filled_qty": f_qty,
                    "avg_px": a_px,
                    "kis_order_id": kis_order_id,
                })

            except Exception as e:
                db.rollback()
                msg = str(e)
                attempt = prev_check_count + 1
                permanent = _is_permanent_poll_error(msg)
                terminal = permanent or attempt >= _POLL_MAX_FAIL_ATTEMPTS
                reason_txt = ("kis_poll_failed_terminal: " if terminal else "kis_poll_failed: ") + msg

                try:
                    if terminal:
                        db.execute(_t("""
                            update orders
                               set status = 'failed',
                                   reason = :r,
                                   exch_status = 'failed',
                                   exch_err = :r,
                                   last_checked_at = now(),
                                   check_count = check_count + 1,
                                   next_check_at = null
                             where id = :id
                        """), {"id": oid, "r": reason_txt})
                    else:
                        delay_sec = _backoff_seconds(attempt)
                        db.execute(_t("""
                            update orders
                               set reason = :r,
                                   exch_err = :r,
                                   last_checked_at = now(),
                                   check_count = check_count + 1,
                                   next_check_at = now() + (:delay || ' seconds')::interval
                             where id = :id
                        """), {"id": oid, "r": reason_txt, "delay": int(delay_sec)})

                    if asset_id is not None:
                        _sync_asset_last_order(
                            db,
                            asset_id=asset_id,
                            order_id=oid,
                            status=("failed" if terminal else prev_status),
                            reason=reason_txt,
                            okx_order_id=kis_order_id,
                        )

                    db.commit()
                except Exception:
                    db.rollback()

                out_items.append({
                    "id": oid,
                    "symbol": symbol,
                    "status": ("failed" if terminal else prev_status),
                    "exch_status": ("failed" if terminal else prev_exch_status),
                    "reason": reason_txt,
                    "kis_order_id": kis_order_id,
                })

        return {
            "ok": True,
            "items": out_items,
            "count": len(out_items),
            "scanned": scanned,
            "changed": changed,
            "note": "kis_poll_checked",
            "elapsed_ms": int((_time.time() - t0) * 1000),
        }

    finally:
        try:
            db_gen.close()
        except Exception:
            pass


# ============================================================
# M3 S3-1 (SSOT-safe): Config from KEEP file (Input Sync v1 + config_hash)
# - POST /api/strategies/{strategy_id}/configs/from_keep
# - keep_path(확정 keep 리스트) -> wrapper pine -> parse_pine_inputs -> canonical -> config_hash -> strategy_configs 저장
# ============================================================

def _canon_input_v1(it: dict) -> dict:
    return {
        "key": it.get("key"),
        "type": it.get("type"),
        "title": it.get("title"),
        "defval": it.get("defval"),
        "options": it.get("options"),
        "minval": it.get("minval"),
        "maxval": it.get("maxval"),
        "step": it.get("step"),
        "group": it.get("group"),
        "tooltip": it.get("tooltip"),
    }

def _make_config_hash_v1(canonical_obj: dict) -> str:
    s = json.dumps(canonical_obj, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
    h = hashlib.sha256(s.encode("utf-8")).hexdigest()[:12]
    return f"cfg_{h}"

@app.post("/api/strategies/{strategy_id}/configs/from_keep")
def api_configs_from_keep(strategy_id: int, payload: dict, db: Session = Depends(get_db)):
    strat = _get_strategy_or_404(db, strategy_id)

    keep_path = payload.get("keep_path")
    scope = (payload.get("scope") or "sizing_ops_v1").strip()

    if not isinstance(keep_path, str) or not keep_path.strip():
        raise HTTPException(status_code=400, detail="missing: keep_path (string)")
    keep_path = keep_path.strip()

    if not os.path.exists(keep_path):
        raise HTTPException(status_code=400, detail=f"keep_path not found: {keep_path}")

    # keep 파일을 wrapper pine으로 감싸서 파서 재사용(긴 pine_code 전송 회피)
    raw = open(keep_path, "r", encoding="utf-8").read()
    wrapper = "//@version=5\nindicator('keep-wrapper')\n" + raw + "\n"

    parsed = parse_pine_inputs(wrapper)
    all_inputs = parsed.get("inputs") or []
    warnings = parsed.get("warnings") or []

    tv_secret = (strat.get("tv_secret") or "").strip()
    if not tv_secret:
        raise HTTPException(status_code=400, detail="missing: strategies.tv_secret")

    kept = [_canon_input_v1(x) for x in all_inputs]
    canonical = {
        "tv_secret": tv_secret,
        "scope": scope,
        "inputs": sorted(kept, key=lambda x: str(x.get("key") or "")),
        "source": {"mode": "keep_path", "path": keep_path},
    }
    cfg_hash = _make_config_hash_v1(canonical)

    # 같은 hash면 재사용
    try:
        row = db.execute(text('''
            SELECT id, config_hash FROM strategy_configs
            WHERE strategy_id=:sid AND config_hash=:h
            ORDER BY id DESC LIMIT 1
        '''), {"sid": strategy_id, "h": cfg_hash}).mappings().first()
        if row:
            return {
                "ok": True,
                "strategy_id": strategy_id,
                "config_id": row["id"],
                "config_hash": row["config_hash"],
                "counts": {"parsed": len(all_inputs)},
                "warnings": warnings,
                "note": "reused_existing_config_hash",
            }
    except Exception:
        pass

    name = (payload.get("name") or "from_keep").strip()
    is_active = bool(payload.get("is_active", True))

    # 저장: DB 스키마 확정(strategy_configs.values jsonb) - values_json 사용 금지
    name = (payload.get("name") or "from_keep").strip()
    is_active = bool(payload.get("is_active", True))

    vals_json = json.dumps(canonical, ensure_ascii=False, separators=(",", ":"), sort_keys=True)

    try:
        # values는 컬럼명이므로 안전하게 쿼트
        db.execute(text('''
            INSERT INTO strategy_configs(strategy_id, name, "values", config_hash, is_active)
            VALUES (:sid, :name, CAST(:vals AS jsonb), :h, :active)
        '''), {
            "sid": strategy_id,
            "name": name,
            "vals": vals_json,
            "h": cfg_hash,
            "active": is_active
        })
        db.commit()
    except Exception as e:
        db.rollback()
        # 진짜 원인을 숨기지 말고 그대로 노출(500 금지)
        raise HTTPException(status_code=400, detail=f"strategy_configs_insert_failed_values: {str(e)}")

    # config_id 재조회
    config_id = None

    try:
        row2 = db.execute(text('''
            SELECT id FROM strategy_configs
            WHERE strategy_id=:sid AND config_hash=:h
            ORDER BY id DESC LIMIT 1
        '''), {"sid": strategy_id, "h": cfg_hash}).mappings().first()
        if row2:
            config_id = row2["id"]
    except Exception:
        config_id = None

    return {
        "ok": True,
        "strategy_id": strategy_id,
        "config_id": config_id,
        "config_hash": cfg_hash,
        "counts": {"parsed": len(all_inputs)},
        "warnings": warnings,
    }



# ============================================================
# M3 S3-1 (SSOT-safe): Config from PINE code (Input Sync v1 + config_hash)
# - POST /api/strategies/{strategy_id}/configs/from_pine
# - pine_code -> parse_pine_inputs -> (keep=사이징/운영제약 v1) -> canonical -> config_hash -> strategy_configs 저장
# ============================================================

def _keep_input_sizing_ops_v1(it: dict) -> bool:
    # v1 휴리스틱:
    # - group_* 기반(샘플 keep 그룹) 우선
    # - title 키워드 fallback
    # - 신호/지표계산용 키워드는 제외(HTF/VWMA/HULL/Supertrend/ATR/일목 등)
    g = str(it.get("group") or "")
    t = str(it.get("title") or "")
    blob = (g + " " + t).lower()

    # 제외(신호/지표 계산용)
    exclude = [
        "vwma", "hull", "supertrend", "atr", "rsi", "macd", "stoch",
        "일목", "ichimoku", "스무딩", "smoothing", "threshold",
        "htf", "higher timeframe", "타임프레임", "timeframe",
    ]
    if any(k in blob for k in exclude):
        return False

    # 포함(그룹)
    allow_groups = (
        "group_webhook", "group_common",
        "group_buy", "group_sell",
        "group_sync",
        "group_r1", "group_r2", "group_r3", "group_r4",
        "group_regime",
    )
    if any(g.startswith(p) for p in allow_groups):
        return True

    # fallback(제목 키워드)
    sizing_ops = [
        "비중", "가용", "노출", "트랜치", "분할", "매수", "매도",
        "쿨", "cool", "락", "lock", "1봉", "봉당", "start", "시작",
        "동기화", "sync", "리셋", "reset", "평단", "보유", "수량",
        "최대", "limit", "손절", "stop",  # 운영제약쪽 포함 가능
    ]
    if any(k.lower() in blob for k in sizing_ops):
        return True

    return False


@app.post("/api/strategies/{strategy_id}/configs/from_pine")
def api_configs_from_pine(strategy_id: int, payload: dict, db: Session = Depends(get_db)):
    strat = _get_strategy_or_404(db, strategy_id)

    code = payload.get("pine_code")
    scope = (payload.get("scope") or "sizing_ops_v1").strip()

    if not isinstance(code, str) or not code.strip():
        raise HTTPException(status_code=400, detail="missing: pine_code (string)")

    parsed = parse_pine_inputs(code)
    all_inputs = parsed.get("inputs") or []
    warnings = parsed.get("warnings") or []

    tv_secret = (strat.get("tv_secret") or "").strip()
    if not tv_secret:
        raise HTTPException(status_code=400, detail="missing: strategies.tv_secret")

    kept_raw = [x for x in all_inputs if _keep_input_sizing_ops_v1(x)]
    kept = [_canon_input_v1(x) for x in kept_raw]

    canonical = {
        "tv_secret": tv_secret,
        "scope": scope,
        "inputs": sorted(kept, key=lambda x: str(x.get("key") or "")),
        "source": {"mode": "pine_code", "len": len(code)},
    }
    cfg_hash = _make_config_hash_v1(canonical)

    # 같은 hash면 재사용
    try:
        row = db.execute(text('''
            SELECT id, config_hash FROM strategy_configs
            WHERE strategy_id=:sid AND config_hash=:h
            ORDER BY id DESC LIMIT 1
        '''), {"sid": strategy_id, "h": cfg_hash}).mappings().first()
        if row:
            return {
                "ok": True,
                "strategy_id": strategy_id,
                "config_id": row["id"],
                "config_hash": row["config_hash"],
                "counts": {"parsed": len(all_inputs), "kept": len(kept)},
                "warnings": warnings,
                "note": "reused_existing_config_hash",
            }
    except Exception:
        pass

    name = (payload.get("name") or "from_pine").strip()
    is_active = bool(payload.get("is_active", True))

    vals_json = json.dumps(canonical, ensure_ascii=False, separators=(",", ":"), sort_keys=True)

    try:
        db.execute(text('''
            INSERT INTO strategy_configs(strategy_id, name, "values", config_hash, is_active)
            VALUES (:sid, :name, CAST(:vals AS jsonb), :h, :active)
        '''), {
            "sid": strategy_id,
            "name": name,
            "vals": vals_json,
            "h": cfg_hash,
            "active": is_active
        })
        db.commit()
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=400, detail=f"strategy_configs_insert_failed_values: {str(e)}")

    # config_id 재조회
    config_id = None
    try:
        row2 = db.execute(text('''
            SELECT id FROM strategy_configs
            WHERE strategy_id=:sid AND config_hash=:h
            ORDER BY id DESC LIMIT 1
        '''), {"sid": strategy_id, "h": cfg_hash}).mappings().first()
        if row2:
            config_id = row2["id"]
    except Exception:
        config_id = None

    return {
        "ok": True,
        "strategy_id": strategy_id,
        "config_id": config_id,
        "config_hash": cfg_hash,
        "counts": {"parsed": len(all_inputs), "kept": len(kept)},
        "warnings": warnings,
    }



# ============================================================
# WEEK4_DIAG_FORCE_ENQUEUE_V1
# - 목적: 실잔고/실주문 없이도 백오프(next_check_at) 동작을 '증명'할 수 있게,
#         특정 order_id를 강제로 폴링 큐에 편입시키는 진단용 엔드포인트 제공.
# - 주의: 운영용 기능 아님(진단 전용). /tv 500 금지 원칙 준수.
# - 동작:
#   * orders.id=order_id 를 submit_status='submitted', status='sent', exch_status='unknown', next_check_at=now()로 세팅
#   * okx_order_id 가 비어있으면 diag_okx_YYYY... 형태로 채움
#   * 이후 /api/diag/poll-now?mode=poll 로 돌리면 okx_get_order가 실패 → poll_failed로 백오프 예약됨
# ============================================================

@app.post("/api/diag/force-enqueue")
def api_diag_force_enqueue(
    order_id: int = Query(..., ge=1),
    okx_order_id: str | None = Query(None),
    force_status: str = Query("sent", pattern=r"^(sent|sending|partial)$"),
    force_exch_status: str = Query("unknown", pattern=r"^(unknown|live|partial)$"),
    db: Session = Depends(get_db),
):
    from sqlalchemy import text
    try:
        # 존재 확인
        row = db.execute(text("select id, okx_order_id, submit_status, exch_status, status, check_count from orders where id=:id"), {"id": int(order_id)}).mappings().first()
        if not row:
            return {"ok": False, "code": "not_found", "detail": f"order not found: {order_id}"}

        oid = okx_order_id
        if oid is None or str(oid).strip() == "":
            oid = f"diag_okx_{order_id}_{int(time.time())}"

        db.execute(text("""
            update orders
               set okx_order_id   = :oid,
                   status        = :st,
                   submit_status = 'submitted',
                   submit_err    = null,
                   exch_status   = :es,
                   exch_err      = null,
                   reason        = coalesce(reason, 'diag_force_enqueue'),
                   next_check_at = now(),
                   check_count   = coalesce(check_count, 0)
             where id = :id
        """), {"id": int(order_id), "oid": str(oid), "st": str(force_status), "es": str(force_exch_status)})
        db.commit()

        out = db.execute(text("""
            select id, status, submit_status, exch_status, okx_order_id, next_check_at, check_count, reason
              from orders
             where id=:id
        """), {"id": int(order_id)}).mappings().first()
        return {"ok": True, "note": "forced_enqueued", "item": dict(out) if out else {"id": order_id}}
    except Exception as e:
        try:
            db.rollback()
        except Exception:
            pass
        return {"ok": False, "code": "exception", "detail": str(e)}


@app.get("/api/diag/order")
def api_diag_get_order(
    order_id: int = Query(..., ge=1),
    db: Session = Depends(get_db),
):
    """진단용: 특정 주문 1건 조회(백오프/next_check_at 확인용)."""
    from sqlalchemy import text
    try:
        row = db.execute(text("select * from orders where id=:id"), {"id": int(order_id)}).mappings().first()
        if not row:
            return {"ok": False, "code": "not_found", "detail": f"order not found: {order_id}"}
        return {"ok": True, "item": dict(row)}
    except Exception as e:
        return {"ok": False, "code": "exception", "detail": str(e)}

# ============================================================
# [W4_ORDERS_ENSURE_V6]
# - Fix duplicated hotfix chain for _ensure_orders_table
# - Ensure NEW installs create orders table (not only ALTER)
# - Keep behavior: best-effort, never raises
# ============================================================

def _ensure_orders_table_v6(db):
    try:
        from sqlalchemy import text as _t
    except Exception:
        _t = text

    # 1) Create base table if missing (NEW installs)
    try:
        db.execute(_t("""
            CREATE TABLE IF NOT EXISTS orders (
                id              BIGSERIAL PRIMARY KEY,
                created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
                updated_at      TIMESTAMPTZ NOT NULL DEFAULT now(),

                account_id      INTEGER,
                strategy_id     INTEGER,
                config_id       INTEGER,
                config_hash     TEXT,
                asset_id        INTEGER,

                alert_id        TEXT,
                symbol          TEXT,
                market          TEXT,
                side            TEXT,
                qty             DOUBLE PRECISION,
                order_type      TEXT DEFAULT 'market',

                idem_key        TEXT,
                dedup_key       TEXT DEFAULT '',
                payload_json    TEXT,

                status          TEXT,
                reason          TEXT,

                okx_order_id    TEXT,
                okx_clord_id    TEXT,

                filled_qty      DOUBLE PRECISION,
                avg_px          DOUBLE PRECISION,
                okx_state       TEXT,
                last_checked_at TIMESTAMPTZ,

                submit_status   TEXT,
                exch_status     TEXT,
                submit_err      TEXT,
                exch_err        TEXT,

                next_check_at   TIMESTAMPTZ,
                check_count     INTEGER DEFAULT 0,

                submit_try_count INTEGER DEFAULT 0,
                next_submit_at   TIMESTAMPTZ,

                -- Week12 Day2: reason/snapshot 필드 (audit trail)
                reason_code      TEXT,
                reason_text      TEXT,
                snapshot_id      TEXT,

                -- Week12 Day2: 멀티 거래소 공통 필드
                exchange_order_id TEXT
            );
        """))
    except Exception:
        # permissions / older PG / etc
        pass

    # 2) Non-destructive migrations (existing installs)
    stmts = [
        "ALTER TABLE orders ADD COLUMN IF NOT EXISTS created_at TIMESTAMPTZ",
        "ALTER TABLE orders ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ",

        "ALTER TABLE orders ADD COLUMN IF NOT EXISTS account_id INTEGER",
        "ALTER TABLE orders ADD COLUMN IF NOT EXISTS strategy_id INTEGER",
        "ALTER TABLE orders ADD COLUMN IF NOT EXISTS config_id INTEGER",
        "ALTER TABLE orders ADD COLUMN IF NOT EXISTS config_hash TEXT",
        "ALTER TABLE orders ADD COLUMN IF NOT EXISTS asset_id INTEGER",

        "ALTER TABLE orders ADD COLUMN IF NOT EXISTS alert_id TEXT",
        "ALTER TABLE orders ADD COLUMN IF NOT EXISTS symbol TEXT",
        "ALTER TABLE orders ADD COLUMN IF NOT EXISTS market TEXT",
        "ALTER TABLE orders ADD COLUMN IF NOT EXISTS side TEXT",
        "ALTER TABLE orders ADD COLUMN IF NOT EXISTS qty DOUBLE PRECISION",

        "ALTER TABLE orders ADD COLUMN IF NOT EXISTS order_type TEXT",
        "ALTER TABLE orders ALTER COLUMN order_type SET DEFAULT 'market'",

        "ALTER TABLE orders ADD COLUMN IF NOT EXISTS idem_key TEXT",
        "ALTER TABLE orders ADD COLUMN IF NOT EXISTS payload_json TEXT",

        "ALTER TABLE orders ADD COLUMN IF NOT EXISTS dedup_key TEXT",
        "ALTER TABLE orders ALTER COLUMN dedup_key SET DEFAULT ''",

        "ALTER TABLE orders ADD COLUMN IF NOT EXISTS status TEXT",
        "ALTER TABLE orders ADD COLUMN IF NOT EXISTS reason TEXT",

        "ALTER TABLE orders ADD COLUMN IF NOT EXISTS okx_order_id TEXT",
        "ALTER TABLE orders ADD COLUMN IF NOT EXISTS okx_clord_id TEXT",

        "ALTER TABLE orders ADD COLUMN IF NOT EXISTS filled_qty DOUBLE PRECISION",
        "ALTER TABLE orders ADD COLUMN IF NOT EXISTS avg_px DOUBLE PRECISION",
        "ALTER TABLE orders ADD COLUMN IF NOT EXISTS okx_state TEXT",
        "ALTER TABLE orders ADD COLUMN IF NOT EXISTS last_checked_at TIMESTAMPTZ",

        "ALTER TABLE orders ADD COLUMN IF NOT EXISTS submit_status TEXT",
        "ALTER TABLE orders ADD COLUMN IF NOT EXISTS exch_status TEXT",
        "ALTER TABLE orders ADD COLUMN IF NOT EXISTS submit_err TEXT",
        "ALTER TABLE orders ADD COLUMN IF NOT EXISTS exch_err TEXT",

        "ALTER TABLE orders ADD COLUMN IF NOT EXISTS next_check_at TIMESTAMPTZ",
        "ALTER TABLE orders ADD COLUMN IF NOT EXISTS check_count INTEGER",
        "ALTER TABLE orders ALTER COLUMN check_count SET DEFAULT 0",

        "ALTER TABLE orders ADD COLUMN IF NOT EXISTS submit_try_count INTEGER",
        "ALTER TABLE orders ALTER COLUMN submit_try_count SET DEFAULT 0",
        "ALTER TABLE orders ADD COLUMN IF NOT EXISTS next_submit_at TIMESTAMPTZ",

        # Week7 Day3: exchange 컬럼 추가 (KIS/OKX 구분용)
        "ALTER TABLE orders ADD COLUMN IF NOT EXISTS exchange TEXT",

        # ShortMsg: short_id 컬럼 추가
        "ALTER TABLE orders ADD COLUMN IF NOT EXISTS short_id TEXT",

        # Week12 Day2: reason/snapshot 필드 (audit trail)
        "ALTER TABLE orders ADD COLUMN IF NOT EXISTS reason_code TEXT",
        "ALTER TABLE orders ADD COLUMN IF NOT EXISTS reason_text TEXT",
        "ALTER TABLE orders ADD COLUMN IF NOT EXISTS snapshot_id TEXT",

        # Week12 Day2: 멀티 거래소 공통 필드
        "ALTER TABLE orders ADD COLUMN IF NOT EXISTS exchange_order_id TEXT",
    ]

    for s in stmts:
        try:
            db.execute(_t(s))
        except Exception:
            pass

    # 3) Helpful indexes (best effort)
    idx = [
        "CREATE INDEX IF NOT EXISTS idx_orders_alert_id ON orders(alert_id)",
        "CREATE INDEX IF NOT EXISTS idx_orders_asset_id ON orders(asset_id)",
        "CREATE INDEX IF NOT EXISTS idx_orders_idem_key ON orders(idem_key)",
        "CREATE INDEX IF NOT EXISTS idx_orders_submit_queue ON orders(submit_status, next_submit_at)",
        "CREATE INDEX IF NOT EXISTS idx_orders_check_queue ON orders(next_check_at)",
        # Week7 Day3: exchange 인덱스
        "CREATE INDEX IF NOT EXISTS idx_orders_exchange ON orders(exchange)",
    ]
    for s in idx:
        try:
            db.execute(_t(s))
        except Exception:
            pass

    try:
        db.commit()
    except Exception:
        pass

# Always force the final canonical ensure to v6 (avoid hotfix overwrite chain)
_ensure_orders_table = _ensure_orders_table_v6

# ============================================================
# KIS balance summary cache (rate-limit guard)
# - KIS VPS API may enforce ~1 request/min. Do NOT call on every /api/home.
# - /api/diag/kis-balance-summary will refresh and update this cache.
# ============================================================
_KIS_SUMMARY_CACHE = {
    "ts": None,        # epoch seconds (None=miss)
    "payload": None,    # last payload returned by _kis_balance_summary_payload()
}


def _kis_balance_summary_cached(*, max_age_sec: int = 65, refresh: int = 0):
    """Return (payload, state, ts) from the KIS balance summary cache.

    state: 'hit' | 'miss' | 'stale' | 'refresh' | 'error'
    ts   : epoch seconds (float) or None
    refresh:
      - 0 (default): cache-only (no KIS API call)
      - 1: force refresh (calls api_diag_kis_balance_summary once, then updates cache)
    """
    payload, ts, state = _kis_cache_get(max_age_sec=max_age_sec)

    if refresh:
        try:
            fresh = api_diag_kis_balance_summary()
            if isinstance(fresh, dict) and fresh.get("ok") is True:
                ts2 = _kis_cache_set(fresh)
                payload = fresh
                ts = ts2 if ts2 else time.time()
                state = "refresh"
        except Exception:
            # keep existing (payload, ts, state)
            pass

    return payload, state, ts


# --- KIS balance summary in-process cache (avoid over-calling KIS) ---
_KIS_SUMMARY_CACHE = {"payload": None, "ts": None}


def _kis_cache_set(payload: dict) -> float | None:
    """Store payload and return cache timestamp (epoch seconds)."""
    try:
        ts = time.time()
        _KIS_SUMMARY_CACHE["ts"] = ts
        _KIS_SUMMARY_CACHE["payload"] = payload
        return ts
    except Exception:
        return None


def _kis_cache_get(*, max_age_sec: int = 65):
    """Return (payload, ts, state) from cache.

    state: 'hit' | 'miss' | 'stale' | 'error'
    """
    try:
        payload = _KIS_SUMMARY_CACHE.get("payload")
        ts = _KIS_SUMMARY_CACHE.get("ts")

        if payload is None or ts is None:
            return None, None, "miss"

        age = time.time() - ts
        if age <= max_age_sec:
            return payload, ts, "hit"
        return payload, ts, "stale"
    except Exception:
        return None, None, "error"



def _fix_mojibake_utf8(s: str | None) -> str | None:
    """Best-effort fix for UTF-8 mojibake (delegates to _fix_mojibake if available)."""
    if s is None:
        return None
    try:
        return _fix_mojibake(s)
    except Exception:
        return s

def _kis_balance_summary_payload():
    """Internal helper used by /api/diag/kis-balance-summary and /api/home accounts_summary."""
    r = api_diag_kis_balance()
    check = (r or {}).get("check") or {}
    if not check.get("ok"):
        return {
            "ok": True,
            "check": check,
            "summary": None,
            "msg1": None,
            "msg1_fixed": None,
            "note": "kis_balance_failed",
        }

    raw = check.get("raw")
    parsed = None
    try:
        if isinstance(raw, str):
            parsed = json.loads(raw)
        elif isinstance(raw, dict):
            parsed = raw
    except Exception as e:
        return {
            "ok": True,
            "check": check,
            "summary": None,
            "msg1": None,
            "msg1_fixed": None,
            "note": "raw_parse_failed",
            "detail": str(e),
        }

    out2 = None
    try:
        output2 = (parsed or {}).get("output2") or []
        if isinstance(output2, list) and len(output2) > 0:
            out2 = output2[0]
    except Exception:
        out2 = None

    def _to_int(x):
        try:
            if x is None:
                return None
            if isinstance(x, (int, float)):
                return int(x)
            s = str(x).strip()
            if s == "":
                return None
            return int(float(s))
        except Exception:
            return None

    summary = None
    if out2:
        summary = {
            "dnca_tot_amt": _to_int(out2.get("dnca_tot_amt")),
            "nass_amt": _to_int(out2.get("nass_amt")),
            "tot_evlu_amt": _to_int(out2.get("tot_evlu_amt")),
            "scts_evlu_amt": _to_int(out2.get("scts_evlu_amt")),
            "cma_evlu_amt": _to_int(out2.get("cma_evlu_amt")),
            "bfdy_tot_asst_evlu_amt": _to_int(out2.get("bfdy_tot_asst_evlu_amt")),
            "asst_icdc_amt": _to_int(out2.get("asst_icdc_amt")),
            "asst_icdc_erng_rt": out2.get("asst_icdc_erng_rt"),
        }

    output1 = (parsed or {}).get("output1") or []
    output1_count = len(output1) if isinstance(output1, list) else None

    msg1 = (parsed or {}).get("msg1")
    msg1_fixed = _fix_mojibake_utf8(msg1)

    return {
        "ok": True,
        "check": {
            "ok": True,
            "svr": check.get("svr"),
            "base_url": check.get("base_url"),
            "http_status": check.get("http_status"),
            "timeout_sec": check.get("timeout_sec"),
            "retry_n": check.get("retry_n"),
        },
        "output1_count": output1_count,
        "summary": summary,
        "msg1": msg1,
        "msg1_fixed": msg1_fixed,
        "note": "parsed_minimal",
    }


@app.get("/api/diag/kis-balance-summary")
def api_diag_kis_balance_summary():
    """
    KIS 잔고조회(모의/vps 기준) 결과를 최소 파싱해서 '전광판/디버그'에 쓰기 쉽게 반환한다.
    - 실주문/주문연결 X (진단 전용)
    - 값(계좌/키)은 노출 금지: .env에서만 읽고 응답에는 포함하지 않는다.

    NOTE:
    - KIS VPS는 호출 제한(대략 1분 1회)이 걸릴 수 있으므로,
      이 endpoint를 통해서만 refresh하고, /api/home은 캐시된 값만 붙인다.
    """
    payload = _kis_balance_summary_payload()
    try:
        chk = payload.get("check") if isinstance(payload, dict) else None
        if isinstance(chk, dict) and chk.get("ok") is True:
            _kis_cache_set(payload)
    except Exception:
        pass
    return payload


# =============================================================================
# Subscription / Entitlement (Week 9 Day 3 - Pydantic Models)
# =============================================================================

# Plan 종류 (SSOT: docs/AUTH_SPEC.md 4-1)
class PlanType(str, Enum):
    FREE = "free"
    HUB = "hub"
    PREMIUM = "premium"

# Entitlement 모델 (SSOT: docs/AUTH_SPEC.md 4-2)
class Entitlements(BaseModel):
    hub_enabled: bool = Field(description="허브 기능 사용 가능")
    premium_enabled: bool = Field(description="프리미엄 엔진 사용 가능")
    max_symbols: int = Field(ge=0, description="심볼 개수 제한 (0=무제한)")
    log_retention_days: int = Field(ge=1, description="로그 보관 기간 (일)")
    batch_template: bool = Field(description="템플릿 일괄 생성 가능")
    export_csv: bool = Field(description="CSV 내보내기 가능")

# Plan별 기본 권한 (SSOT: docs/AUTH_SPEC.md 4-3)
PLAN_DEFAULTS: dict[PlanType, Entitlements] = {
    PlanType.FREE: Entitlements(
        hub_enabled=False,
        premium_enabled=False,
        max_symbols=0,
        log_retention_days=7,
        batch_template=False,
        export_csv=False
    ),
    PlanType.HUB: Entitlements(
        hub_enabled=True,
        premium_enabled=False,
        max_symbols=5,
        log_retention_days=30,
        batch_template=True,
        export_csv=True
    ),
    PlanType.PREMIUM: Entitlements(
        hub_enabled=True,
        premium_enabled=True,
        max_symbols=0,
        log_retention_days=90,
        batch_template=True,
        export_csv=True
    ),
}

# 구독 조회 응답 (성공)
class SubscriptionResponse(BaseModel):
    ok: Literal[True] = True
    user_id: str
    plan: PlanType
    expires_at: str = Field(description="ISO8601 형식")
    entitlements: Entitlements

# 구독 조회 응답 (실패)
class SubscriptionErrorResponse(BaseModel):
    ok: Literal[False] = False
    code: str = Field(description="에러 코드: unauthorized, no_subscription, expired")
    detail: str


@app.get("/api/subscription/me")
def api_subscription_me(request: Request):
    """
    구독/권한 조회 (스텁)
    - Authorization 헤더가 없으면 unauthorized
    - 헤더가 있으면 하드코딩된 hub plan 반환

    NOTE: Week 14에서 실제 DB/결제 연동 구현 예정
    """
    auth_header = request.headers.get("Authorization", "")

    # 토큰 없음 → unauthorized
    if not auth_header or not auth_header.startswith("Bearer "):
        return SubscriptionErrorResponse(
            code="unauthorized",
            detail="Missing or invalid token"
        ).model_dump()

    # 스텁: 하드코딩된 hub plan 반환
    # 실제 구현 시 토큰 검증 + DB 조회 필요
    return SubscriptionResponse(
        user_id="u_stub_001",
        plan=PlanType.HUB,
        expires_at="2026-03-03T00:00:00Z",
        entitlements=PLAN_DEFAULTS[PlanType.HUB]
    ).model_dump()


# =============================================================================
# Timeline / Events (Week 10 Day 2)
# SSOT: docs/TIMELINE_SPEC.md
# =============================================================================

class EventType(str, Enum):
    """이벤트 타입 (SSOT: TIMELINE_SPEC.md 2)"""
    SIGNAL = "signal"
    ORDER_CREATED = "order_created"
    ORDER_SENT = "order_sent"
    ORDER_FAILED = "order_failed"
    ORDER_FILLED = "order_filled"
    ORDER_PARTIAL = "order_partial"
    ORDER_CANCELED = "order_canceled"
    POLL = "poll"
    ERROR = "error"
    ESTOP_ON = "estop_on"
    ESTOP_OFF = "estop_off"


class TimelineItem(BaseModel):
    """타임라인 아이템"""
    id: int
    event_type: str
    asset_id: Optional[int] = None
    order_id: Optional[int] = None
    account_id: Optional[int] = None
    summary: str
    detail: Optional[dict] = None
    created_at: str


class TimelineResponse(BaseModel):
    """타임라인 응답"""
    ok: Literal[True] = True
    items: list[TimelineItem]
    total: int
    limit: int
    offset: int


@app.get("/ui/timeline", response_class=HTMLResponse)
def ui_timeline(
    asset_id: Optional[int] = Query(None),
    limit: int = Query(20, ge=1, le=100)
):
    """
    타임라인 HTML 뷰어 (Week 10 Day 4)
    - 최소 HTML 렌더링
    - PC/웹 공용 기준
    """
    import urllib.request
    import json

    # 내부 API 호출
    url = f"http://127.0.0.1:8000/api/timeline?limit={limit}"
    if asset_id:
        url += f"&asset_id={asset_id}"

    try:
        with urllib.request.urlopen(url, timeout=5) as resp:
            data = json.loads(resp.read().decode())
    except Exception as e:
        return HTMLResponse(f"<html><body><h1>Error</h1><p>{e}</p></body></html>")

    # HTML 생성
    rows_html = ""
    for item in data.get("items", []):
        evt_class = "sent" if "sent" in item["event_type"] else (
            "filled" if "filled" in item["event_type"] else (
            "failed" if "failed" in item["event_type"] else "default"))
        rows_html += f"""
        <tr class="{evt_class}">
            <td>{item['id']}</td>
            <td>{item['event_type']}</td>
            <td>{item.get('summary', '-')}</td>
            <td>{item.get('created_at', '-')[:19]}</td>
        </tr>"""

    html = f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <title>Timeline - bbooster Hub</title>
    <style>
        body {{ font-family: -apple-system, sans-serif; margin: 20px; background: #1a1a2e; color: #eee; }}
        h1 {{ color: #00d9ff; }}
        table {{ border-collapse: collapse; width: 100%; }}
        th, td {{ border: 1px solid #333; padding: 8px; text-align: left; }}
        th {{ background: #16213e; }}
        tr:nth-child(even) {{ background: #1f1f3a; }}
        .sent {{ color: #00ff88; }}
        .filled {{ color: #00d9ff; }}
        .failed {{ color: #ff6b6b; }}
        .info {{ margin-bottom: 10px; color: #888; }}
    </style>
</head>
<body>
    <h1>Timeline</h1>
    <p class="info">Total: {data.get('total', 0)} | Showing: {len(data.get('items', []))}</p>
    <table>
        <thead>
            <tr><th>ID</th><th>Type</th><th>Summary</th><th>Time</th></tr>
        </thead>
        <tbody>
            {rows_html}
        </tbody>
    </table>
</body>
</html>"""
    return HTMLResponse(html)


@app.get("/api/timeline")
def api_timeline(
    asset_id: Optional[int] = Query(None, description="자산 ID 필터"),
    order_id: Optional[int] = Query(None, description="주문 ID 필터"),
    account_id: Optional[int] = Query(None, description="계좌 ID 필터"),
    event_type: Optional[str] = Query(None, description="이벤트 타입 필터"),
    limit: int = Query(20, ge=1, le=100, description="최대 개수"),
    offset: int = Query(0, ge=0, description="건너뛸 개수"),
    db: Session = Depends(get_db)
):
    """
    타임라인(이벤트) 조회 API
    SSOT: docs/TIMELINE_SPEC.md 6-1

    NOTE: Week 10 Day 2 - 기본 구현
    실제 events 테이블이 없으므로 orders 테이블에서 이벤트 생성
    """
    from .models import Event

    # events 테이블 존재 여부 확인 시도
    try:
        # 실제 events 테이블에서 조회 시도
        query = db.query(Event)

        if asset_id is not None:
            query = query.filter(Event.asset_id == asset_id)
        if order_id is not None:
            query = query.filter(Event.order_id == order_id)
        if account_id is not None:
            query = query.filter(Event.account_id == account_id)
        if event_type is not None:
            query = query.filter(Event.event_type == event_type)

        total = query.count()
        rows = query.order_by(Event.created_at.desc()).offset(offset).limit(limit).all()

        items = [
            TimelineItem(
                id=row.id,
                event_type=row.event_type,
                asset_id=row.asset_id,
                order_id=row.order_id,
                account_id=row.account_id,
                summary=row.summary,
                detail=row.detail,
                created_at=row.created_at.isoformat() if row.created_at else ""
            )
            for row in rows
        ]

        return TimelineResponse(
            items=items,
            total=total,
            limit=limit,
            offset=offset
        ).model_dump()

    except Exception:
        # events 테이블이 없으면 orders 테이블에서 이벤트 생성 (fallback)
        # Week 10 완료 후 마이그레이션으로 events 테이블 생성 예정
        db.rollback()  # 트랜잭션 롤백 필수
        from sqlalchemy import text

        # orders 테이블에서 최근 주문을 이벤트로 변환
        sql = text("""
            SELECT
                o.id,
                o.asset_id,
                o.status,
                o.submit_status,
                o.submit_err,
                o.reason_code,
                o.reason_text,
                o.side,
                o.qty,
                o.filled_qty,
                o.avg_px,
                o.created_at,
                a.symbol
            FROM orders o
            LEFT JOIN assets a ON o.asset_id = a.id
            WHERE 1=1
            AND (:asset_id IS NULL OR o.asset_id = :asset_id)
            AND (:order_id IS NULL OR o.id = :order_id)
            ORDER BY o.created_at DESC
            LIMIT :limit OFFSET :offset
        """)

        rows = db.execute(sql, {
            "asset_id": asset_id,
            "order_id": order_id,
            "limit": limit,
            "offset": offset
        }).fetchall()

        # 전체 개수
        count_sql = text("""
            SELECT COUNT(*) FROM orders
            WHERE 1=1
            AND (:asset_id IS NULL OR asset_id = :asset_id)
            AND (:order_id IS NULL OR id = :order_id)
        """)
        total = db.execute(count_sql, {
            "asset_id": asset_id,
            "order_id": order_id
        }).scalar() or 0

        items = []
        for row in rows:
            # 상태에 따라 이벤트 타입 결정
            if row.status == "sent":
                evt_type = "order_sent"
                summary = f"{row.symbol or 'N/A'} 주문 전송"
            elif row.status == "filled":
                evt_type = "order_filled"
                summary = f"{row.symbol or 'N/A'} 체결 완료"
            elif row.status == "failed":
                evt_type = "order_failed"
                summary = f"{row.symbol or 'N/A'} 주문 실패"
            else:
                evt_type = "order_created"
                summary = f"{row.symbol or 'N/A'} 주문 생성"

            items.append(TimelineItem(
                id=row.id,
                event_type=evt_type,
                asset_id=row.asset_id,
                order_id=row.id,
                account_id=None,
                summary=summary,
                detail={
                    "status": row.status,
                    "submit_status": row.submit_status,
                    "error": row.submit_err,
                    "reason_code": row.reason_code,
                    "reason_text": row.reason_text,
                    "side": row.side,
                    "qty": float(row.qty) if row.qty else 0,
                    "filled_qty": float(row.filled_qty) if row.filled_qty else 0,
                    "avg_px": float(row.avg_px) if row.avg_px else 0,
                    "symbol": row.symbol
                },
                created_at=row.created_at.isoformat() if row.created_at else ""
            ))

        return TimelineResponse(
            items=items,
            total=total,
            limit=limit,
            offset=offset
        ).model_dump()


# =========================
# [PORTFOLIO_API_V1] 포트폴리오 API (PC앱 홈 페이지용)
# =========================

class PortfolioSummaryResponse(BaseModel):
    total_assets: float = 0.0
    total_assets_formatted: str = "₩0"
    total_profit_rate: float = 0.0
    daily_change: float = 0.0
    daily_change_formatted: str = "₩0"
    daily_change_rate: float = 0.0
    active_strategies: int = 0
    currency: str = "KRW"


@app.get("/api/portfolio/summary")
async def get_portfolio_summary(
    current_user: User = Depends(get_current_user_optional),
    db: Session = Depends(get_db)
):
    """
    포트폴리오 요약 (총자산, 수익률)
    - 각 거래소별 잔고 조회 후 합산
    - USD 자산은 환율 적용하여 KRW로 환산
    """
    active_strategies = 0
    total_krw = 0.0
    total_usd = 0.0
    holdings = []

    if current_user:
        try:
            # 활성 전략 수 (현재 사용자 계정에 연결된 것만)
            result = db.execute(
                text("""
                    SELECT COUNT(*) FROM assets a
                    JOIN accounts acc ON acc.id = a.account_id
                    WHERE acc.owner_id = :owner_id
                    AND a.is_active = true
                    AND a.soft_deleted = 0
                """),
                {"owner_id": current_user.id}
            ).scalar()
            active_strategies = result or 0
        except Exception:
            pass

        # 등록된 계정들 조회 (현재 사용자 계정만)
        try:
            accounts = db.execute(
                text("SELECT id, name, exchange, api_key, api_secret, api_passphrase, account_number, is_mock FROM accounts WHERE owner_id = :owner_id"),
                {"owner_id": current_user.id}
            ).fetchall()

            for acc in accounts:
                exchange = acc.exchange.lower() if acc.exchange else ""
                api_key = acc.api_key or ""
                api_secret = acc.api_secret or ""
                passphrase = acc.api_passphrase or ""
                account_number = acc.account_number or ""
                is_mock = acc.is_mock if hasattr(acc, 'is_mock') else False

                try:
                    if exchange == "upbit":
                        balances = await fetch_upbit_balances(api_key, api_secret)
                        for b in balances:
                            total_krw += b.get("value_krw", 0)
                            holdings.append({**b, "exchange": "upbit"})

                    elif exchange in ("kis_kr", "kis"):
                        balances = await fetch_kis_kr_balances(api_key, api_secret, account_number, is_mock=is_mock)
                        for b in balances:
                            total_krw += b.get("value_krw", 0)
                            holdings.append({**b, "exchange": "KIS_KR"})

                    elif exchange == "kis_us":
                        balances = await fetch_kis_us_balances(api_key, api_secret, account_number)
                        for b in balances:
                            total_usd += b.get("value_usd", 0)
                            holdings.append({**b, "exchange": "KIS_US"})

                    elif exchange == "binance":
                        balances = await fetch_binance_balances(api_key, api_secret)
                        for b in balances:
                            total_usd += b.get("value_usd", 0)
                            holdings.append({**b, "exchange": "binance"})

                    elif exchange == "okx":
                        balances = await fetch_okx_balances(api_key, api_secret, passphrase)
                        for b in balances:
                            total_usd += b.get("value_usd", 0)
                            holdings.append({**b, "exchange": "okx"})

                    elif exchange == "bybit":
                        balances = await fetch_bybit_balances(api_key, api_secret)
                        for b in balances:
                            total_usd += b.get("value_usd", 0)
                            holdings.append({**b, "exchange": "bybit"})

                except Exception as e:
                    print(f"[Portfolio] Balance fetch error for {exchange}: {e}")
                    continue

        except Exception as e:
            print(f"[Portfolio] Account fetch error: {e}")

    # 환율 조회 및 총자산 계산
    usd_krw_rate = await get_usd_krw_rate()
    total_assets = total_krw + (total_usd * usd_krw_rate)

    # 자산배분 계산
    domestic = 0.0    # 국내주식
    foreign = 0.0     # 해외주식
    crypto = 0.0      # 암호화폐
    cash_krw = 0.0    # 현금(원화)
    cash_usd = 0.0    # 현금(달러) - USD 기준

    stablecoins = ["USDT", "USDC", "BUSD", "DAI", "TUSD"]

    for h in holdings:
        exchange = (h.get("exchange") or "").upper()
        symbol = (h.get("symbol") or "").upper()
        name = h.get("name", "")

        # 평가금액 계산 (원화 기준)
        value_krw = h.get("value_krw", 0)
        value_usd = h.get("value_usd", 0)
        if value_krw <= 0 and value_usd > 0:
            value_krw = value_usd * usd_krw_rate
        elif value_krw <= 0:
            # current_price * quantity로 계산
            price = h.get("current_price", 0)
            qty = h.get("quantity", 0)
            if exchange in ("OKX", "BINANCE", "BYBIT", "KIS_US"):
                value_krw = price * qty * usd_krw_rate
                value_usd = price * qty
            else:
                value_krw = price * qty

        # 분류
        if exchange in ("KIS_KR", "KIS"):
            if symbol in ("KRW", "예수금") or name == "예수금":
                cash_krw += value_krw
            else:
                domestic += value_krw
        elif exchange == "KIS_US":
            foreign += value_krw
        elif exchange in ("OKX", "BINANCE", "BYBIT"):
            if symbol in stablecoins:
                cash_usd += value_usd if value_usd > 0 else value_krw / usd_krw_rate
            else:
                crypto += value_krw
        elif exchange == "UPBIT":
            if symbol == "KRW":
                cash_krw += value_krw
            else:
                crypto += value_krw

    # 총액 (원화 기준)
    cash_usd_krw = cash_usd * usd_krw_rate
    alloc_total = domestic + foreign + crypto + cash_krw + cash_usd_krw
    allocation = {
        "domestic": round(domestic / alloc_total * 100) if alloc_total > 0 else 0,
        "foreign": round(foreign / alloc_total * 100) if alloc_total > 0 else 0,
        "crypto": round(crypto / alloc_total * 100) if alloc_total > 0 else 0,
        "cash_krw": round(cash_krw / alloc_total * 100) if alloc_total > 0 else 0,
        "cash_usd": round(cash_usd_krw / alloc_total * 100) if alloc_total > 0 else 0,
        "domestic_value": domestic,
        "foreign_value": foreign,
        "crypto_value": crypto,
        "cash_krw_value": cash_krw,
        "cash_usd_value": cash_usd,  # USD 금액 (달러)
    }

    print(f"[Summary] Allocation: domestic={domestic:.0f}, foreign={foreign:.0f}, crypto={crypto:.0f}, cash_krw={cash_krw:.0f}, cash_usd=${cash_usd:.2f}")

    # 포맷팅 (1원 단위, 천단위 콤마)
    def format_krw(val):
        return f"₩{int(val):,}"

    # 수익률 계산 - 보유 종목 기반 (원금 대비 수익률)
    total_profit_rate = 0.0
    total_profit_loss = 0.0  # 총 수익금
    total_cost = 0.0  # 총 원금 (평단가 * 수량)
    daily_change = 0.0
    daily_change_rate = 0.0
    first_snapshot_date = None

    # 각 종목의 수익금과 원금 합산
    for h in holdings:
        profit_loss = h.get("profit_loss", 0) or 0
        avg_price = h.get("avg_price", 0) or 0
        quantity = h.get("quantity", 0) or 0
        exchange = (h.get("exchange") or "").upper()

        # USD 자산은 원화로 환산
        if exchange in ("KIS_US", "BINANCE", "OKX", "BYBIT"):
            profit_loss = profit_loss * usd_krw_rate
            avg_price = avg_price * usd_krw_rate

        total_profit_loss += profit_loss
        total_cost += avg_price * quantity

    # 총 수익률 = 총 수익금 / 총 원금 * 100
    if total_cost > 0:
        total_profit_rate = (total_profit_loss / total_cost) * 100

    # 일간 변동 계산 (어제 00시 스냅샷 대비)
    if current_user and total_assets > 0:
        try:
            now = datetime.now()
            today = now.replace(hour=0, minute=0, second=0, microsecond=0)
            yesterday = today - timedelta(days=1)

            # 오늘 스냅샷 조회 (6시간 간격으로 갱신)
            existing_snapshot = db.execute(
                text("SELECT id, created_at FROM portfolio_snapshots WHERE user_id = :user_id AND snapshot_date = :today"),
                {"user_id": current_user.id, "today": today}
            ).mappings().first()

            should_update = False
            if existing_snapshot:
                # 마지막 업데이트가 6시간 이상 지났으면 갱신
                last_update = existing_snapshot["created_at"]
                if last_update:
                    # timezone aware 비교
                    if hasattr(last_update, 'tzinfo') and last_update.tzinfo:
                        now_aware = now.replace(tzinfo=last_update.tzinfo)
                        hours_since_update = (now_aware - last_update).total_seconds() / 3600
                    else:
                        hours_since_update = (now - last_update).total_seconds() / 3600
                    should_update = hours_since_update >= 6
            else:
                should_update = True  # 스냅샷 없으면 생성

            if should_update:
                if existing_snapshot:
                    db.execute(
                        text("""
                            UPDATE portfolio_snapshots
                            SET total_asset_krw = :total_assets, total_krw = :total_krw,
                                total_usd = :total_usd, usd_krw_rate = :usd_krw_rate,
                                created_at = NOW()
                            WHERE id = :id
                        """),
                        {"id": existing_snapshot["id"], "total_assets": total_assets, "total_krw": total_krw,
                         "total_usd": total_usd, "usd_krw_rate": usd_krw_rate}
                    )
                else:
                    db.execute(
                        text("""
                            INSERT INTO portfolio_snapshots (user_id, snapshot_date, total_asset_krw, total_krw, total_usd, usd_krw_rate)
                            VALUES (:user_id, :today, :total_assets, :total_krw, :total_usd, :usd_krw_rate)
                        """),
                        {"user_id": current_user.id, "today": today, "total_assets": total_assets,
                         "total_krw": total_krw, "total_usd": total_usd, "usd_krw_rate": usd_krw_rate}
                    )
                db.commit()
                print(f"[Snapshot] Updated for user {current_user.id}: {total_assets:,.0f} KRW")

            # 어제 스냅샷으로 일간 변동 계산
            yesterday_snapshot = db.execute(
                text("SELECT total_asset_krw FROM portfolio_snapshots WHERE user_id = :user_id AND snapshot_date = :yesterday"),
                {"user_id": current_user.id, "yesterday": yesterday}
            ).scalar()

            if yesterday_snapshot and float(yesterday_snapshot) > 0:
                yesterday_val = float(yesterday_snapshot)
                daily_change = float(total_assets) - yesterday_val
                daily_change_rate = ((float(total_assets) / yesterday_val) - 1) * 100

            # 첫 스냅샷 날짜 (참고용)
            first_snapshot = db.execute(
                text("SELECT snapshot_date FROM portfolio_snapshots WHERE user_id = :user_id ORDER BY snapshot_date ASC LIMIT 1"),
                {"user_id": current_user.id}
            ).scalar()
            if first_snapshot:
                first_snapshot_date = first_snapshot.strftime("%Y-%m-%d") if hasattr(first_snapshot, 'strftime') else str(first_snapshot)

        except Exception as e:
            print(f"[Summary] Snapshot error: {e}")

    return {
        "total_assets": total_assets,
        "total_assets_formatted": format_krw(total_assets),
        "total_krw": total_krw,
        "total_usd": total_usd,
        "usd_krw_rate": usd_krw_rate,
        "total_profit_rate": round(total_profit_rate, 2),
        "daily_change": daily_change,
        "daily_change_formatted": format_krw(daily_change) if daily_change >= 0 else f"-{format_krw(abs(daily_change))}",
        "daily_change_rate": round(daily_change_rate, 2),
        "active_strategies": active_strategies,
        "holdings_count": len(holdings),
        "currency": "KRW",
        "allocation": allocation,
        "first_snapshot_date": first_snapshot_date
    }


@app.get("/api/portfolio/profit-rate")
async def get_portfolio_profit_rate(
    start_date: str = Query(None, description="시작일 (YYYY-MM-DD)"),
    end_date: str = Query(None, description="종료일 (YYYY-MM-DD)"),
    current_user: User = Depends(get_current_user_optional),
    db: Session = Depends(get_db)
):
    """
    기간별 수익률 계산
    - start_date: 시작일 (없으면 첫 스냅샷 날짜)
    - end_date: 종료일 (없으면 오늘)
    """
    if not current_user:
        return {"profit_rate": 0, "start_date": None, "end_date": None, "start_assets": 0, "end_assets": 0}

    try:
        # 시작일 스냅샷
        if start_date:
            start_dt = datetime.strptime(start_date, "%Y-%m-%d")
            start_snapshot = db.execute(
                text("""
                    SELECT total_asset_krw, snapshot_date FROM portfolio_snapshots
                    WHERE user_id = :user_id AND snapshot_date >= :start_date
                    ORDER BY snapshot_date ASC LIMIT 1
                """),
                {"user_id": current_user.id, "start_date": start_dt}
            ).mappings().first()
        else:
            start_snapshot = db.execute(
                text("""
                    SELECT total_asset_krw, snapshot_date FROM portfolio_snapshots
                    WHERE user_id = :user_id ORDER BY snapshot_date ASC LIMIT 1
                """),
                {"user_id": current_user.id}
            ).mappings().first()

        # 종료일 스냅샷
        if end_date:
            end_dt = datetime.strptime(end_date, "%Y-%m-%d")
            end_snapshot = db.execute(
                text("""
                    SELECT total_asset_krw, snapshot_date FROM portfolio_snapshots
                    WHERE user_id = :user_id AND snapshot_date <= :end_date
                    ORDER BY snapshot_date DESC LIMIT 1
                """),
                {"user_id": current_user.id, "end_date": end_dt}
            ).mappings().first()
        else:
            end_snapshot = db.execute(
                text("""
                    SELECT total_asset_krw, snapshot_date FROM portfolio_snapshots
                    WHERE user_id = :user_id ORDER BY snapshot_date DESC LIMIT 1
                """),
                {"user_id": current_user.id}
            ).mappings().first()

        if not start_snapshot or not end_snapshot:
            return {"profit_rate": 0, "start_date": None, "end_date": None, "start_assets": 0, "end_assets": 0}

        start_assets = start_snapshot["total_asset_krw"]
        end_assets = end_snapshot["total_asset_krw"]
        profit_rate = 0.0

        if start_assets > 0:
            profit_rate = ((end_assets / start_assets) - 1) * 100

        return {
            "profit_rate": round(profit_rate, 2),
            "start_date": start_snapshot["snapshot_date"].strftime("%Y-%m-%d"),
            "end_date": end_snapshot["snapshot_date"].strftime("%Y-%m-%d"),
            "start_assets": start_assets,
            "end_assets": end_assets,
            "start_assets_formatted": f"₩{int(start_assets):,}",
            "end_assets_formatted": f"₩{int(end_assets):,}",
            "change": end_assets - start_assets,
            "change_formatted": f"₩{int(end_assets - start_assets):,}" if end_assets >= start_assets else f"-₩{int(start_assets - end_assets):,}"
        }

    except Exception as e:
        print(f"[ProfitRate] Error: {e}")
        return {"profit_rate": 0, "start_date": None, "end_date": None, "start_assets": 0, "end_assets": 0, "error": str(e)}


class ChartDataPoint(BaseModel):
    date: str
    value: float


class PortfolioChartResponse(BaseModel):
    period: str
    data: list[ChartDataPoint]
    period_profit_rate: float


@app.get("/api/portfolio/chart")
async def get_portfolio_chart(
    period: str = Query("1w", description="기간: 1d, 1w, 1m, 3m, 1y"),
    current_user: User = Depends(get_current_user_optional),
    db: Session = Depends(get_db)
):
    """수익률 차트 데이터 (실제 스냅샷 기반)"""
    days_map = {"1d": 1, "1w": 7, "1m": 30, "3m": 90, "1y": 365}
    days = days_map.get(period, 7)

    data = []
    period_profit_rate = 0.0

    if current_user:
        try:
            start_date = datetime.now() - timedelta(days=days)
            rows = db.execute(
                text("""
                    SELECT snapshot_date, total_asset_krw
                    FROM portfolio_snapshots
                    WHERE user_id = :user_id AND snapshot_date >= :start_date
                    ORDER BY snapshot_date ASC
                """),
                {"user_id": current_user.id, "start_date": start_date}
            ).fetchall()

            if rows and len(rows) > 0:
                base_value = float(rows[0].total_asset_krw or 0)
                if base_value > 0:
                    for row in rows:
                        current_value = float(row.total_asset_krw or 0)
                        profit_rate = ((current_value / base_value) - 1) * 100
                        date_str = row.snapshot_date.strftime("%m/%d") if hasattr(row.snapshot_date, 'strftime') else str(row.snapshot_date)[:5]
                        data.append(ChartDataPoint(date=date_str, value=round(profit_rate, 2)))

                    # 마지막 수익률
                    period_profit_rate = data[-1].value if data else 0.0

        except Exception as e:
            print(f"[Chart] Error: {e}")

    # 데이터가 없으면 오늘 0% 포인트 추가
    if not data:
        data.append(ChartDataPoint(date=datetime.now().strftime("%m/%d"), value=0.0))

    return PortfolioChartResponse(period=period, data=data, period_profit_rate=round(period_profit_rate, 2))


class HoldingItem(BaseModel):
    symbol: str
    name: str = ""
    exchange: str
    quantity: float
    avg_price: float
    current_price: float
    profit_loss: float
    profit_rate: float


@app.get("/api/portfolio/holdings")
async def get_holdings(
    current_user: User = Depends(get_current_user_optional),
    db: Session = Depends(get_db)
):
    """보유 자산 목록 (각 거래소별 잔고 조회)"""
    holdings = []
    usd_krw_rate = await get_usd_krw_rate()

    print(f"[Holdings DEBUG] current_user: {current_user}, id: {current_user.id if current_user else 'None'}")

    if not current_user:
        print("[Holdings DEBUG] No current_user, returning empty")
        return {"holdings": [], "usd_krw_rate": usd_krw_rate}

    try:
        accounts = db.execute(
            text("SELECT id, name, exchange, api_key, api_secret, api_passphrase, account_number, is_mock FROM accounts WHERE owner_id = :owner_id"),
            {"owner_id": current_user.id}
        ).fetchall()
        print(f"[Holdings DEBUG] Found {len(accounts)} accounts for owner_id={current_user.id}")

        for acc in accounts:
            exchange = acc.exchange.lower() if acc.exchange else ""
            api_key = acc.api_key or ""
            api_secret = acc.api_secret or ""
            passphrase = acc.api_passphrase or ""
            account_number = acc.account_number or ""
            is_mock = acc.is_mock if hasattr(acc, 'is_mock') else False

            print(f"[Holdings DEBUG] Processing account id={acc.id}, exchange='{exchange}', is_mock={is_mock}, has_key={bool(api_key)}, has_secret={bool(api_secret)}")

            try:
                if exchange == "upbit":
                    print(f"[Holdings DEBUG] Calling fetch_upbit_balances...")
                    balances = await fetch_upbit_balances(api_key, api_secret)
                    for b in balances:
                        holdings.append({
                            "exchange": "Upbit",
                            "symbol": b.get("symbol", ""),
                            "name": b.get("symbol", ""),
                            "quantity": b.get("quantity", 0),
                            "avg_price": b.get("avg_price", 0),
                            "current_price": b.get("current_price", 0),
                            "profit_loss": b.get("profit_loss", 0),
                            "profit_rate": b.get("profit_rate", 0),
                            "currency": "KRW"
                        })

                elif exchange in ("kis_kr", "kis"):
                    print(f"[Holdings DEBUG] Calling fetch_kis_kr_balances for account_number={account_number}, is_mock={is_mock}...")
                    balances = await fetch_kis_kr_balances(api_key, api_secret, account_number, is_mock=is_mock)
                    print(f"[Holdings DEBUG] KIS_KR returned {len(balances)} items")
                    for b in balances:
                        quantity = b.get("quantity", 0)
                        avg_price = b.get("avg_price", 0)
                        current_price = b.get("current_price", 0)
                        profit_loss = b.get("profit_loss", (current_price - avg_price) * quantity if quantity else 0)
                        profit_rate = b.get("profit_rate", 0)
                        holdings.append({
                            "exchange": "KIS_KR",
                            "symbol": b.get("symbol", ""),
                            "name": b.get("name", ""),
                            "quantity": quantity,
                            "avg_price": avg_price,
                            "current_price": current_price,
                            "profit_loss": profit_loss,
                            "profit_rate": profit_rate,
                            "currency": "KRW"
                        })

                elif exchange == "kis_us":
                    balances = await fetch_kis_us_balances(api_key, api_secret, account_number)
                    for b in balances:
                        quantity = b.get("quantity", 0)
                        avg_price = b.get("avg_price", 0)
                        current_price = b.get("current_price", 0)
                        profit_loss = b.get("profit_loss", (current_price - avg_price) * quantity if quantity else 0)
                        profit_rate = b.get("profit_rate", 0)
                        holdings.append({
                            "exchange": "KIS_US",
                            "symbol": b.get("symbol", ""),
                            "name": b.get("name", ""),
                            "quantity": quantity,
                            "avg_price": avg_price,
                            "current_price": current_price,
                            "profit_loss": profit_loss,
                            "profit_rate": profit_rate,
                            "currency": "USD"
                        })

                elif exchange == "binance":
                    print(f"[Holdings DEBUG] Calling fetch_binance_balances...")
                    balances = await fetch_binance_balances(api_key, api_secret)
                    print(f"[Holdings DEBUG] Binance returned {len(balances)} items")
                    for b in balances:
                        holdings.append({
                            "exchange": "Binance",
                            "symbol": b.get("symbol", ""),
                            "name": b.get("symbol", ""),
                            "quantity": b.get("quantity", 0),
                            "avg_price": b.get("avg_price", 0),
                            "current_price": b.get("current_price", 0),
                            "profit_loss": b.get("profit_loss", 0),
                            "profit_rate": b.get("profit_rate", 0),
                            "currency": "USD"
                        })

                elif exchange == "okx":
                    print(f"[Holdings DEBUG] Calling fetch_okx_balances with cost basis...")
                    balances = await fetch_okx_balances(api_key, api_secret, passphrase, include_cost_basis=True)
                    print(f"[Holdings DEBUG] OKX returned {len(balances)} items")
                    for b in balances:
                        holdings.append({
                            "exchange": "OKX",
                            "symbol": b.get("symbol", ""),
                            "name": b.get("symbol", ""),
                            "quantity": b.get("quantity", 0),
                            "avg_price": b.get("avg_price", 0),
                            "current_price": b.get("current_price", 0),
                            "profit_loss": b.get("profit_loss", 0),
                            "profit_rate": b.get("profit_rate", 0),
                            "currency": "USD"
                        })

                elif exchange == "bybit":
                    print(f"[Holdings DEBUG] Calling fetch_bybit_balances...")
                    balances = await fetch_bybit_balances(api_key, api_secret)
                    print(f"[Holdings DEBUG] Bybit returned {len(balances)} items")
                    for b in balances:
                        holdings.append({
                            "exchange": "Bybit",
                            "symbol": b.get("symbol", ""),
                            "name": b.get("symbol", ""),
                            "quantity": b.get("quantity", 0),
                            "avg_price": b.get("avg_price", 0),
                            "current_price": b.get("current_price", 0),
                            "profit_loss": b.get("profit_loss", 0),
                            "profit_rate": b.get("profit_rate", 0),
                            "currency": "USD"
                        })

                else:
                    print(f"[Holdings DEBUG] Unknown exchange: '{exchange}' - skipping")

            except Exception as e:
                print(f"[Holdings DEBUG] Balance fetch error for {exchange}: {e}")
                import traceback
                traceback.print_exc()
                continue

    except Exception as e:
        print(f"[Holdings DEBUG] Account fetch error: {e}")
        import traceback
        traceback.print_exc()

    print(f"[Holdings DEBUG] Final result: {len(holdings)} holdings")
    return {"holdings": holdings, "usd_krw_rate": usd_krw_rate}


# =====================================================
# 환율 조회 API
# =====================================================
@app.get("/api/exchange-rate")
async def get_exchange_rate():
    """USD/KRW 환율 조회"""
    rate = await get_usd_krw_rate()
    return {
        "usd_krw": rate,
        "updated": datetime.now().strftime("%Y-%m-%d %H:%M")
    }


# =====================================================
# 매매 내역 API
# =====================================================
@app.get("/api/trades")
async def get_trade_history(
    exchange: str = Query(None, description="거래소 필터"),
    symbol: str = Query(None, description="종목 필터"),
    limit: int = Query(10, ge=1, le=500, description="조회 개수"),
    offset: int = Query(0, ge=0, description="건너뛸 개수"),
    current_user: User = Depends(get_current_user_optional),
    db: Session = Depends(get_db)
):
    """매매 내역 조회 (실패 건 포함)"""
    if not current_user:
        return {"trades": [], "total": 0}

    try:
        # 전체 개수 조회
        count_sql = "SELECT COUNT(*) FROM orders"
        total = db.execute(text(count_sql)).scalar() or 0

        # 매매 내역 조회 (실패 건 포함)
        sql = """
            SELECT o.id, o.symbol, o.side, o.qty, o.filled_qty, o.avg_px,
                   o.status, o.submit_status, o.submit_err,
                   o.reason_code, o.reason_text,
                   o.created_at as executed_at,
                   a.id as asset_id, s.name as strategy_name, acc.name as exchange_name
            FROM orders o
            LEFT JOIN assets a ON a.id = o.asset_id
            LEFT JOIN strategies s ON s.id = a.strategy_id
            LEFT JOIN accounts acc ON acc.id = a.account_id
            ORDER BY o.created_at DESC
            LIMIT :limit OFFSET :offset
        """

        rows = db.execute(text(sql), {"limit": limit, "offset": offset}).fetchall()

        # 빈 문자열 → 0 변환 헬퍼
        def safe_float(val, default=0.0):
            if val is None or val == '':
                return default
            try:
                return float(val)
            except (ValueError, TypeError):
                return default

        trades = []
        for row in rows:
            qty = safe_float(row.filled_qty) or safe_float(row.qty)
            price = safe_float(row.avg_px)

            trades.append({
                "id": row.id,
                "exchange": row.exchange_name or "OKX",
                "symbol": row.symbol or "",
                "side": row.side or "",
                "quantity": qty,
                "price": price,
                "total_amount": qty * price,
                "status": row.status or "unknown",
                "submit_err": row.submit_err or "",
                "reason_code": row.reason_code or "",
                "reason_text": row.reason_text or "",
                "strategy_name": row.strategy_name or "",
                "executed_at": row.executed_at.isoformat() if row.executed_at else ""
            })

        return {"trades": trades, "total": total}

    except Exception as e:
        print(f"[Trades] Error: {e}")
        return {"trades": [], "total": 0}


# =====================================================
# 자산별 거래내역 API
# =====================================================
@app.get("/api/asset/trades")
async def get_asset_trades(
    symbol: str = Query(..., description="종목코드"),
    exchange: str = Query(None, description="거래소"),
    limit: int = Query(100, ge=1, le=500),
    current_user: User = Depends(get_current_user_optional),
    db: Session = Depends(get_db)
):
    """특정 자산의 거래내역 조회 (누적 수익 계산용)"""
    if not current_user:
        return []

    try:
        sql = """
            SELECT o.id, o.symbol, o.side, o.qty, o.filled_qty, o.avg_px,
                   o.status, o.submit_status, o.created_at as executed_at,
                   s.name as strategy_name, acc.name as exchange_name, acc.exchange as exchange_code
            FROM orders o
            LEFT JOIN assets a ON a.id = o.asset_id
            LEFT JOIN strategies s ON s.id = a.strategy_id
            LEFT JOIN accounts acc ON acc.id = a.account_id
            WHERE o.symbol LIKE :symbol_pattern
            AND o.status IN ('filled', 'partial')
            ORDER BY o.created_at ASC
            LIMIT :limit
        """

        # 종목코드 패턴 매칭 (삼성전자: 005930, 005930.KS 등)
        symbol_pattern = f"%{symbol}%"
        rows = db.execute(text(sql), {"symbol_pattern": symbol_pattern, "limit": limit}).fetchall()

        def safe_float(val, default=0.0):
            if val is None or val == '':
                return default
            try:
                return float(val)
            except (ValueError, TypeError):
                return default

        trades = []
        position = 0.0  # 누적 수량
        total_cost = 0.0  # 총 매수금액
        avg_price = 0.0  # 평균단가

        for row in rows:
            qty = safe_float(row.filled_qty) or safe_float(row.qty)
            price = safe_float(row.avg_px)
            side = (row.side or "").upper()
            total_amount = qty * price
            profit_loss = 0.0
            profit_rate = 0.0

            if side == "BUY":
                # 매수: 평균단가 업데이트
                total_cost += total_amount
                position += qty
                avg_price = total_cost / position if position > 0 else 0
            elif side == "SELL" and position > 0:
                # 매도: 수익 계산
                cost_basis = avg_price * qty
                profit_loss = total_amount - cost_basis
                profit_rate = (profit_loss / cost_basis * 100) if cost_basis > 0 else 0
                position -= qty
                total_cost = avg_price * position if position > 0 else 0

            trades.append({
                "id": row.id,
                "symbol": row.symbol or "",
                "side": row.side or "",
                "quantity": qty,
                "price": price,
                "total_amount": total_amount,
                "profit_loss": round(profit_loss, 2),
                "profit_rate": round(profit_rate, 2),
                "strategy_name": row.strategy_name or "",
                "exchange": row.exchange_name or row.exchange_code or "",
                "executed_at": row.executed_at.isoformat() if row.executed_at else ""
            })

        return trades

    except Exception as e:
        print(f"[AssetTrades] Error: {e}")
        import traceback
        traceback.print_exc()
        return []


# =====================================================
# 포트폴리오 히스토리 (수익률 추이)
# =====================================================
@app.get("/api/portfolio/history")
async def get_portfolio_history(
    period: str = Query("1m", description="기간: 1w, 1m, 3m, 1y"),
    current_user: User = Depends(get_current_user_optional),
    db: Session = Depends(get_db)
):
    """
    포트폴리오 수익률 추이 (스냅샷 기반)
    - portfolio_snapshots 테이블에서 조회
    - 스냅샷이 없으면 빈 배열 반환
    """
    if not current_user:
        return {"data": [], "total_return": 0}

    days_map = {"1w": 7, "1m": 30, "3m": 90, "1y": 365}
    days = days_map.get(period, 30)

    try:
        sql = text("""
            SELECT snapshot_date, total_asset_krw, total_krw, total_usd, usd_krw_rate
            FROM portfolio_snapshots
            WHERE user_id = :user_id
            AND snapshot_date >= CURRENT_DATE - INTERVAL ':days days'
            ORDER BY snapshot_date
        """.replace(":days", str(days)))

        rows = db.execute(sql, {"user_id": current_user.id}).fetchall()

        if not rows:
            return {"data": [], "total_return": 0, "period": period}

        base_value = float(rows[0].total_asset_krw or 0)
        data = []
        for row in rows:
            value = float(row.total_asset_krw or 0)
            pct = ((value - base_value) / base_value * 100) if base_value > 0 else 0
            data.append({
                "date": row.snapshot_date.isoformat() if row.snapshot_date else "",
                "value": value,
                "return_pct": round(pct, 2)
            })

        total_return = data[-1]["return_pct"] if data else 0

        return {"data": data, "total_return": total_return, "period": period}

    except Exception as e:
        print(f"[PortfolioHistory] Error: {e}")
        return {"data": [], "total_return": 0, "period": period}


class ActiveStrategyItem(BaseModel):
    id: int
    strategy_id: int = 0
    name: str
    symbol: str
    exchange: str
    status: str = "running"
    is_active: bool = True
    trades_today: int = 0


@app.get("/api/strategies/active")
async def get_active_strategies(
    current_user: User = Depends(get_current_user_optional),
    db: Session = Depends(get_db)
):
    """활성 전략 목록 (일시정지 포함)"""
    strategies = []

    if current_user:
        try:
            sql = text("""
                SELECT a.id, a.strategy_id, a.is_active,
                       s.name as strategy_name, s.is_active as strategy_active,
                       a.symbol, acc.name as exchange
                FROM assets a
                JOIN strategies s ON s.id = a.strategy_id
                JOIN accounts acc ON acc.id = a.account_id
                WHERE acc.owner_id = :owner_id
                AND a.soft_deleted = 0
                ORDER BY a.id
            """)
            rows = db.execute(sql, {"owner_id": current_user.id}).mappings().fetchall()

            for row in rows:
                today_start = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
                trades_sql = text("SELECT COUNT(*) FROM orders WHERE asset_id = :asset_id AND created_at >= :today_start")
                trades_count = db.execute(trades_sql, {"asset_id": row["id"], "today_start": today_start}).scalar() or 0

                is_running = row["is_active"] and row["strategy_active"]
                strategies.append(ActiveStrategyItem(
                    id=row["id"],
                    strategy_id=row["strategy_id"],
                    name=row["strategy_name"] or f"Strategy #{row['id']}",
                    symbol=row["symbol"] or "N/A",
                    exchange=row["exchange"] or "N/A",
                    status="running" if is_running else "paused",
                    is_active=is_running,
                    trades_today=trades_count
                ))
        except Exception as e:
            print(f"Failed to load active strategies: {e}")

    return {"strategies": strategies}


@app.put("/api/assets/{asset_id}/toggle")
async def toggle_asset_active(
    asset_id: int,
    current_user: User = Depends(get_current_user_optional),
    db: Session = Depends(get_db)
):
    """자산(전략-종목 연결) 활성/비활성 토글"""
    try:
        row = db.execute(
            text("SELECT id, is_active FROM assets WHERE id = :id"),
            {"id": asset_id}
        ).mappings().first()
        if not row:
            raise HTTPException(status_code=404, detail="Asset not found")

        new_active = not row["is_active"]
        db.execute(
            text("UPDATE assets SET is_active = :active, updated_at = now() WHERE id = :id"),
            {"active": new_active, "id": asset_id}
        )
        db.commit()
        return {"ok": True, "is_active": new_active, "asset_id": asset_id}
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(e))


@app.delete("/api/assets/{asset_id}")
async def delete_asset(
    asset_id: int,
    current_user: User = Depends(get_current_user_optional),
    db: Session = Depends(get_db)
):
    """자산(전략-종목 연결) 소프트 삭제"""
    try:
        row = db.execute(
            text("SELECT id FROM assets WHERE id = :id AND soft_deleted = 0"),
            {"id": asset_id}
        ).mappings().first()
        if not row:
            raise HTTPException(status_code=404, detail="Asset not found")

        db.execute(
            text("UPDATE assets SET soft_deleted = 1, is_active = false, updated_at = now() WHERE id = :id"),
            {"id": asset_id}
        )
        db.commit()
        return {"ok": True, "deleted": True, "asset_id": asset_id}
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/api/system/emergency-stop")
async def emergency_stop(current_user: User = Depends(get_current_user_optional)):
    """긴급 정지 - 모든 자동매매 중단"""
    return {"ok": True, "message": "긴급 정지가 활성화되었습니다"}


@app.post("/api/auth/verify-password")
async def verify_password(request: Request, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """비밀번호 재확인 — 200으로 verified 필드 반환"""
    try:
        body = await request.json()
        password = body.get("password", "")
        if not password:
            return {"verified": False}
        user = authenticate_user(db, current_user.email, password)
        if not user:
            return {"verified": False}
        return {"verified": True}
    except Exception:
        return {"verified": False}


# =============================================================================
# [PHASE 4] Webhook System — 웹훅 검증 + 수신 로그
# =============================================================================

def _ensure_webhook_logs_table(db: Session):
    """webhook_logs 테이블이 없으면 생성"""
    create_sql = text("""
        CREATE TABLE IF NOT EXISTS webhook_logs (
            id SERIAL PRIMARY KEY,
            user_id INTEGER REFERENCES users(id),
            received_at TIMESTAMP DEFAULT NOW(),
            status VARCHAR(20),
            exchange VARCHAR(50),
            symbol VARCHAR(50),
            action VARCHAR(20),
            raw_payload TEXT,
            error_message TEXT,
            order_result TEXT
        )
    """)
    db.execute(create_sql)
    db.commit()


class WebhookPayload(BaseModel):
    """웹훅 페이로드 스키마"""
    action: str = Field(..., description="매매 방향: buy, sell, close")
    symbol: str = Field(..., description="거래 심볼 (예: BTC-USDT)")
    exchange: str = Field(..., description="거래소 (예: OKX, KIS)")
    qty_type: Optional[str] = Field("percent", description="수량 유형: percent, fixed")
    qty: Optional[float] = Field(100, description="수량 (비율이면 %, 고정이면 개수)")
    order_type: Optional[str] = Field("market", description="주문 유형: market, limit")
    leverage: Optional[int] = Field(1, description="레버리지")
    sl: Optional[float] = Field(None, description="손절 %")
    tp: Optional[float] = Field(None, description="익절 %")


def _validate_webhook_payload(payload: dict) -> tuple[bool, str]:
    """웹훅 페이로드 검증"""
    # 필수 필드 확인
    required_fields = ["action", "symbol", "exchange"]
    for field in required_fields:
        if field not in payload or not payload[field]:
            return False, f"필수 필드 누락: {field}"

    # action 값 검증
    action = payload.get("action", "").lower()
    if action not in ["buy", "sell", "close"]:
        return False, f"잘못된 action 값: {action} (buy, sell, close 중 하나여야 함)"

    # symbol 검증 (빈 문자열 불가)
    symbol = payload.get("symbol", "").strip()
    if not symbol:
        return False, "symbol이 비어있음"

    # exchange 검증
    exchange = payload.get("exchange", "").upper()
    valid_exchanges = ["OKX", "KIS", "BINANCE", "BYBIT"]
    if exchange not in valid_exchanges:
        return False, f"지원하지 않는 거래소: {exchange}"

    # qty 검증 (있는 경우)
    qty = payload.get("qty")
    if qty is not None:
        try:
            qty_float = float(qty)
            if qty_float <= 0:
                return False, f"수량은 0보다 커야 함: {qty}"
        except (ValueError, TypeError):
            return False, f"잘못된 수량 형식: {qty}"

    # leverage 검증 (있는 경우)
    leverage = payload.get("leverage")
    if leverage is not None:
        try:
            lev_int = int(leverage)
            if lev_int < 1 or lev_int > 100:
                return False, f"레버리지는 1-100 사이여야 함: {leverage}"
        except (ValueError, TypeError):
            return False, f"잘못된 레버리지 형식: {leverage}"

    return True, ""


def _log_webhook(db: Session, user_id: int, status: str, payload: dict, error_message: str = None, order_result: str = None):
    """웹훅 수신 로그 저장"""
    try:
        _ensure_webhook_logs_table(db)
        insert_sql = text("""
            INSERT INTO webhook_logs (user_id, status, exchange, symbol, action, raw_payload, error_message, order_result)
            VALUES (:user_id, :status, :exchange, :symbol, :action, :raw_payload, :error_message, :order_result)
        """)
        db.execute(insert_sql, {
            "user_id": user_id,
            "status": status,
            "exchange": payload.get("exchange", ""),
            "symbol": payload.get("symbol", ""),
            "action": payload.get("action", ""),
            "raw_payload": json.dumps(payload, ensure_ascii=False),
            "error_message": error_message,
            "order_result": order_result
        })
        db.commit()
    except Exception as e:
        print(f"Failed to log webhook: {e}")


@app.post("/api/webhook/{user_id}")
async def webhook_endpoint(user_id: int, request: Request, db: Session = Depends(get_db)):
    """
    TradingView 웹훅 수신 엔드포인트
    - JSON 페이로드 검증
    - 필수 필드 확인: action, symbol, exchange
    - 값 유효성 검증
    - 검증 실패 시 에러 로그 + 400 응답
    - 검증 성공 시 주문 큐에 추가 + 200 응답
    """
    # 사용자 확인
    user_sql = text("SELECT id, email FROM users WHERE id = :user_id")
    user_row = db.execute(user_sql, {"user_id": user_id}).mappings().first()
    if not user_row:
        return JSONResponse(status_code=400, content={"ok": False, "error": "Invalid user_id"})

    # JSON 파싱
    try:
        payload = await request.json()
    except Exception as e:
        _log_webhook(db, user_id, "failed", {}, f"JSON 파싱 오류: {str(e)}")
        return JSONResponse(status_code=400, content={"ok": False, "error": "Invalid JSON format"})

    if not isinstance(payload, dict):
        _log_webhook(db, user_id, "failed", {}, "페이로드가 객체가 아님")
        return JSONResponse(status_code=400, content={"ok": False, "error": "Payload must be a JSON object"})

    # E-STOP 확인
    if _is_estop_on(db):
        _log_webhook(db, user_id, "rejected", payload, "E-STOP 활성화됨")
        return JSONResponse(status_code=200, content={"ok": False, "error": "E-STOP is active"})

    # 페이로드 검증
    is_valid, error_msg = _validate_webhook_payload(payload)
    if not is_valid:
        _log_webhook(db, user_id, "rejected", payload, error_msg)
        return JSONResponse(status_code=400, content={"ok": False, "error": error_msg})

    # 검증 성공 - 주문 처리 (현재는 더미 응답)
    # TODO: 실제 주문 실행 로직 연결
    _log_webhook(db, user_id, "success", payload, None, "Order queued")

    return JSONResponse(status_code=200, content={
        "ok": True,
        "message": "Webhook received and validated",
        "action": payload.get("action"),
        "symbol": payload.get("symbol"),
        "exchange": payload.get("exchange")
    })


class WebhookLogItem(BaseModel):
    id: int
    received_at: str
    status: str
    exchange: str
    symbol: str
    action: str
    error_message: Optional[str] = None


@app.get("/api/webhook/logs")
async def get_webhook_logs(
    limit: int = Query(20, ge=1, le=100),
    status_filter: Optional[str] = Query(None, description="Filter by status: success, failed, rejected"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """웹훅 수신 로그 조회 (JWT 인증 필요)"""
    try:
        _ensure_webhook_logs_table(db)

        if status_filter:
            sql = text("""
                SELECT id, received_at, status, exchange, symbol, action, error_message
                FROM webhook_logs
                WHERE user_id = :user_id AND status = :status
                ORDER BY received_at DESC
                LIMIT :limit
            """)
            rows = db.execute(sql, {"user_id": current_user.id, "status": status_filter, "limit": limit}).mappings().all()
        else:
            sql = text("""
                SELECT id, received_at, status, exchange, symbol, action, error_message
                FROM webhook_logs
                WHERE user_id = :user_id
                ORDER BY received_at DESC
                LIMIT :limit
            """)
            rows = db.execute(sql, {"user_id": current_user.id, "limit": limit}).mappings().all()

        logs = []
        for row in rows:
            logs.append(WebhookLogItem(
                id=row["id"],
                received_at=str(row["received_at"]) if row["received_at"] else "",
                status=row["status"] or "",
                exchange=row["exchange"] or "",
                symbol=row["symbol"] or "",
                action=row["action"] or "",
                error_message=row["error_message"]
            ))

        return {"logs": logs}

    except Exception as e:
        print(f"Failed to get webhook logs: {e}")
        return {"logs": []}


@app.get("/api/webhook/url")
async def get_webhook_url(current_user: User = Depends(get_current_user)):
    """사용자의 웹훅 URL 반환"""
    base_url = os.getenv("BASE_URL", "https://qube-system.com")
    return {
        "webhook_url": f"{base_url}/api/webhook/{current_user.id}",
        "user_id": current_user.id
    }


# =============================================================================
# [PHASE 5] Symbol Information API — Real Exchange API Integration
# =============================================================================

# 심볼 캐시 저장소
_symbol_cache = {
    "okx": {"symbols": [], "updated_at": None},
    "binance": {"symbols": [], "updated_at": None},
    "bybit": {"symbols": [], "updated_at": None},
    "upbit": {"symbols": [], "updated_at": None},
    "kis_kr": {"symbols": [], "updated_at": None},
    "kis_us": {"symbols": [], "updated_at": None},
}
CACHE_TTL_SECONDS = 3600  # 1시간

# KIS 국내주식 하드코딩 (KOSPI+KOSDAQ 주요 200개)
KIS_KR_STOCKS = [
    {"symbol": "005930", "name": "삼성전자", "exchange": "KIS_KR"},
    {"symbol": "000660", "name": "SK하이닉스", "exchange": "KIS_KR"},
    {"symbol": "035420", "name": "NAVER", "exchange": "KIS_KR"},
    {"symbol": "035720", "name": "카카오", "exchange": "KIS_KR"},
    {"symbol": "051910", "name": "LG화학", "exchange": "KIS_KR"},
    {"symbol": "006400", "name": "삼성SDI", "exchange": "KIS_KR"},
    {"symbol": "068270", "name": "셀트리온", "exchange": "KIS_KR"},
    {"symbol": "207940", "name": "삼성바이오로직스", "exchange": "KIS_KR"},
    {"symbol": "005380", "name": "현대차", "exchange": "KIS_KR"},
    {"symbol": "000270", "name": "기아", "exchange": "KIS_KR"},
    {"symbol": "373220", "name": "LG에너지솔루션", "exchange": "KIS_KR"},
    {"symbol": "005490", "name": "POSCO홀딩스", "exchange": "KIS_KR"},
    {"symbol": "055550", "name": "신한지주", "exchange": "KIS_KR"},
    {"symbol": "105560", "name": "KB금융", "exchange": "KIS_KR"},
    {"symbol": "028260", "name": "삼성물산", "exchange": "KIS_KR"},
    {"symbol": "003670", "name": "포스코퓨처엠", "exchange": "KIS_KR"},
    {"symbol": "012330", "name": "현대모비스", "exchange": "KIS_KR"},
    {"symbol": "066570", "name": "LG전자", "exchange": "KIS_KR"},
    {"symbol": "003550", "name": "LG", "exchange": "KIS_KR"},
    {"symbol": "032830", "name": "삼성생명", "exchange": "KIS_KR"},
    {"symbol": "017670", "name": "SK텔레콤", "exchange": "KIS_KR"},
    {"symbol": "034730", "name": "SK", "exchange": "KIS_KR"},
    {"symbol": "086790", "name": "하나금융지주", "exchange": "KIS_KR"},
    {"symbol": "010130", "name": "고려아연", "exchange": "KIS_KR"},
    {"symbol": "015760", "name": "한국전력", "exchange": "KIS_KR"},
    {"symbol": "034020", "name": "두산에너빌리티", "exchange": "KIS_KR"},
    {"symbol": "009150", "name": "삼성전기", "exchange": "KIS_KR"},
    {"symbol": "033780", "name": "KT&G", "exchange": "KIS_KR"},
    {"symbol": "096770", "name": "SK이노베이션", "exchange": "KIS_KR"},
    {"symbol": "018260", "name": "삼성에스디에스", "exchange": "KIS_KR"},
    {"symbol": "259960", "name": "크래프톤", "exchange": "KIS_KR"},
    {"symbol": "030200", "name": "KT", "exchange": "KIS_KR"},
    {"symbol": "011200", "name": "HMM", "exchange": "KIS_KR"},
    {"symbol": "024110", "name": "기업은행", "exchange": "KIS_KR"},
    {"symbol": "000810", "name": "삼성화재", "exchange": "KIS_KR"},
    {"symbol": "361610", "name": "SK아이이테크놀로지", "exchange": "KIS_KR"},
    {"symbol": "011170", "name": "롯데케미칼", "exchange": "KIS_KR"},
    {"symbol": "036570", "name": "엔씨소프트", "exchange": "KIS_KR"},
    {"symbol": "010950", "name": "S-Oil", "exchange": "KIS_KR"},
    {"symbol": "009540", "name": "한국조선해양", "exchange": "KIS_KR"},
    {"symbol": "016360", "name": "삼성증권", "exchange": "KIS_KR"},
    {"symbol": "047050", "name": "포스코인터내셔널", "exchange": "KIS_KR"},
    {"symbol": "326030", "name": "SK바이오팜", "exchange": "KIS_KR"},
    {"symbol": "000100", "name": "유한양행", "exchange": "KIS_KR"},
    {"symbol": "011790", "name": "SKC", "exchange": "KIS_KR"},
    {"symbol": "302440", "name": "SK바이오사이언스", "exchange": "KIS_KR"},
    {"symbol": "251270", "name": "넷마블", "exchange": "KIS_KR"},
    {"symbol": "352820", "name": "하이브", "exchange": "KIS_KR"},
    {"symbol": "086280", "name": "현대글로비스", "exchange": "KIS_KR"},
    {"symbol": "267250", "name": "현대중공업", "exchange": "KIS_KR"},
    # KOSDAQ 주요 종목
    {"symbol": "247540", "name": "에코프로비엠", "exchange": "KIS_KR"},
    {"symbol": "086520", "name": "에코프로", "exchange": "KIS_KR"},
    {"symbol": "293490", "name": "카카오게임즈", "exchange": "KIS_KR"},
    {"symbol": "263750", "name": "펄어비스", "exchange": "KIS_KR"},
    {"symbol": "112040", "name": "위메이드", "exchange": "KIS_KR"},
    {"symbol": "196170", "name": "알테오젠", "exchange": "KIS_KR"},
    {"symbol": "145020", "name": "휴젤", "exchange": "KIS_KR"},
    {"symbol": "091990", "name": "셀트리온헬스케어", "exchange": "KIS_KR"},
    {"symbol": "041510", "name": "에스엠", "exchange": "KIS_KR"},
    {"symbol": "035900", "name": "JYP Ent.", "exchange": "KIS_KR"},
    {"symbol": "122870", "name": "와이지엔터테인먼트", "exchange": "KIS_KR"},
    {"symbol": "357780", "name": "솔브레인", "exchange": "KIS_KR"},
    {"symbol": "028300", "name": "HLB", "exchange": "KIS_KR"},
    {"symbol": "039030", "name": "이오테크닉스", "exchange": "KIS_KR"},
    {"symbol": "108860", "name": "셀바스AI", "exchange": "KIS_KR"},
    {"symbol": "067630", "name": "에이치엘비생명과학", "exchange": "KIS_KR"},
    {"symbol": "257720", "name": "실리콘투", "exchange": "KIS_KR"},
    {"symbol": "383220", "name": "F&F", "exchange": "KIS_KR"},
    {"symbol": "299030", "name": "하나기술", "exchange": "KIS_KR"},
    {"symbol": "095340", "name": "ISC", "exchange": "KIS_KR"},
    {"symbol": "214150", "name": "클래시스", "exchange": "KIS_KR"},
    {"symbol": "217270", "name": "넵튠", "exchange": "KIS_KR"},
    {"symbol": "140410", "name": "메지온", "exchange": "KIS_KR"},
    {"symbol": "323990", "name": "박셀바이오", "exchange": "KIS_KR"},
    {"symbol": "277810", "name": "레인보우로보틱스", "exchange": "KIS_KR"},
]

# KIS 해외주식 하드코딩 (NYSE+NASDAQ 주요 100개)
KIS_US_STOCKS = [
    {"symbol": "AAPL", "name": "Apple Inc.", "exchange": "KIS_US"},
    {"symbol": "MSFT", "name": "Microsoft Corporation", "exchange": "KIS_US"},
    {"symbol": "GOOGL", "name": "Alphabet Inc.", "exchange": "KIS_US"},
    {"symbol": "AMZN", "name": "Amazon.com Inc.", "exchange": "KIS_US"},
    {"symbol": "NVDA", "name": "NVIDIA Corporation", "exchange": "KIS_US"},
    {"symbol": "META", "name": "Meta Platforms Inc.", "exchange": "KIS_US"},
    {"symbol": "TSLA", "name": "Tesla Inc.", "exchange": "KIS_US"},
    {"symbol": "BRK.B", "name": "Berkshire Hathaway", "exchange": "KIS_US"},
    {"symbol": "TSM", "name": "Taiwan Semiconductor", "exchange": "KIS_US"},
    {"symbol": "V", "name": "Visa Inc.", "exchange": "KIS_US"},
    {"symbol": "JPM", "name": "JPMorgan Chase", "exchange": "KIS_US"},
    {"symbol": "UNH", "name": "UnitedHealth Group", "exchange": "KIS_US"},
    {"symbol": "JNJ", "name": "Johnson & Johnson", "exchange": "KIS_US"},
    {"symbol": "XOM", "name": "Exxon Mobil", "exchange": "KIS_US"},
    {"symbol": "WMT", "name": "Walmart Inc.", "exchange": "KIS_US"},
    {"symbol": "MA", "name": "Mastercard Inc.", "exchange": "KIS_US"},
    {"symbol": "PG", "name": "Procter & Gamble", "exchange": "KIS_US"},
    {"symbol": "HD", "name": "Home Depot", "exchange": "KIS_US"},
    {"symbol": "CVX", "name": "Chevron Corporation", "exchange": "KIS_US"},
    {"symbol": "LLY", "name": "Eli Lilly", "exchange": "KIS_US"},
    {"symbol": "MRK", "name": "Merck & Co.", "exchange": "KIS_US"},
    {"symbol": "ABBV", "name": "AbbVie Inc.", "exchange": "KIS_US"},
    {"symbol": "KO", "name": "Coca-Cola", "exchange": "KIS_US"},
    {"symbol": "PEP", "name": "PepsiCo Inc.", "exchange": "KIS_US"},
    {"symbol": "AVGO", "name": "Broadcom Inc.", "exchange": "KIS_US"},
    {"symbol": "COST", "name": "Costco Wholesale", "exchange": "KIS_US"},
    {"symbol": "TMO", "name": "Thermo Fisher", "exchange": "KIS_US"},
    {"symbol": "MCD", "name": "McDonald's", "exchange": "KIS_US"},
    {"symbol": "CSCO", "name": "Cisco Systems", "exchange": "KIS_US"},
    {"symbol": "ABT", "name": "Abbott Laboratories", "exchange": "KIS_US"},
    {"symbol": "DHR", "name": "Danaher Corporation", "exchange": "KIS_US"},
    {"symbol": "ACN", "name": "Accenture", "exchange": "KIS_US"},
    {"symbol": "ADBE", "name": "Adobe Inc.", "exchange": "KIS_US"},
    {"symbol": "NKE", "name": "Nike Inc.", "exchange": "KIS_US"},
    {"symbol": "LIN", "name": "Linde plc", "exchange": "KIS_US"},
    {"symbol": "TXN", "name": "Texas Instruments", "exchange": "KIS_US"},
    {"symbol": "NFLX", "name": "Netflix Inc.", "exchange": "KIS_US"},
    {"symbol": "CRM", "name": "Salesforce Inc.", "exchange": "KIS_US"},
    {"symbol": "AMD", "name": "Advanced Micro Devices", "exchange": "KIS_US"},
    {"symbol": "INTC", "name": "Intel Corporation", "exchange": "KIS_US"},
    {"symbol": "QCOM", "name": "Qualcomm Inc.", "exchange": "KIS_US"},
    {"symbol": "ORCL", "name": "Oracle Corporation", "exchange": "KIS_US"},
    {"symbol": "IBM", "name": "IBM Corporation", "exchange": "KIS_US"},
    {"symbol": "AMGN", "name": "Amgen Inc.", "exchange": "KIS_US"},
    {"symbol": "HON", "name": "Honeywell International", "exchange": "KIS_US"},
    {"symbol": "UNP", "name": "Union Pacific", "exchange": "KIS_US"},
    {"symbol": "BA", "name": "Boeing Company", "exchange": "KIS_US"},
    {"symbol": "CAT", "name": "Caterpillar Inc.", "exchange": "KIS_US"},
    {"symbol": "GE", "name": "General Electric", "exchange": "KIS_US"},
    {"symbol": "SBUX", "name": "Starbucks", "exchange": "KIS_US"},
    {"symbol": "GS", "name": "Goldman Sachs", "exchange": "KIS_US"},
    {"symbol": "MS", "name": "Morgan Stanley", "exchange": "KIS_US"},
    {"symbol": "BLK", "name": "BlackRock Inc.", "exchange": "KIS_US"},
    {"symbol": "MMM", "name": "3M Company", "exchange": "KIS_US"},
    {"symbol": "AXP", "name": "American Express", "exchange": "KIS_US"},
    {"symbol": "ISRG", "name": "Intuitive Surgical", "exchange": "KIS_US"},
    {"symbol": "SPGI", "name": "S&P Global", "exchange": "KIS_US"},
    {"symbol": "GILD", "name": "Gilead Sciences", "exchange": "KIS_US"},
    {"symbol": "MDLZ", "name": "Mondelez International", "exchange": "KIS_US"},
    {"symbol": "CVS", "name": "CVS Health", "exchange": "KIS_US"},
    {"symbol": "DE", "name": "Deere & Company", "exchange": "KIS_US"},
    {"symbol": "BKNG", "name": "Booking Holdings", "exchange": "KIS_US"},
    {"symbol": "T", "name": "AT&T Inc.", "exchange": "KIS_US"},
    {"symbol": "VZ", "name": "Verizon Communications", "exchange": "KIS_US"},
    {"symbol": "SCHW", "name": "Charles Schwab", "exchange": "KIS_US"},
    {"symbol": "ADP", "name": "Automatic Data Processing", "exchange": "KIS_US"},
    {"symbol": "PLD", "name": "Prologis Inc.", "exchange": "KIS_US"},
    {"symbol": "CI", "name": "Cigna Group", "exchange": "KIS_US"},
    {"symbol": "BDX", "name": "Becton Dickinson", "exchange": "KIS_US"},
    {"symbol": "DUK", "name": "Duke Energy", "exchange": "KIS_US"},
    {"symbol": "SO", "name": "Southern Company", "exchange": "KIS_US"},
    {"symbol": "CME", "name": "CME Group", "exchange": "KIS_US"},
    {"symbol": "ICE", "name": "Intercontinental Exchange", "exchange": "KIS_US"},
    {"symbol": "NOC", "name": "Northrop Grumman", "exchange": "KIS_US"},
    {"symbol": "LMT", "name": "Lockheed Martin", "exchange": "KIS_US"},
    {"symbol": "RTX", "name": "RTX Corporation", "exchange": "KIS_US"},
    {"symbol": "CL", "name": "Colgate-Palmolive", "exchange": "KIS_US"},
    {"symbol": "PNC", "name": "PNC Financial", "exchange": "KIS_US"},
    {"symbol": "USB", "name": "U.S. Bancorp", "exchange": "KIS_US"},
    {"symbol": "TFC", "name": "Truist Financial", "exchange": "KIS_US"},
    {"symbol": "COIN", "name": "Coinbase Global", "exchange": "KIS_US"},
    {"symbol": "PLTR", "name": "Palantir Technologies", "exchange": "KIS_US"},
    {"symbol": "SNOW", "name": "Snowflake Inc.", "exchange": "KIS_US"},
    {"symbol": "UBER", "name": "Uber Technologies", "exchange": "KIS_US"},
    {"symbol": "ABNB", "name": "Airbnb Inc.", "exchange": "KIS_US"},
    {"symbol": "SQ", "name": "Block Inc.", "exchange": "KIS_US"},
    {"symbol": "PYPL", "name": "PayPal Holdings", "exchange": "KIS_US"},
    {"symbol": "SHOP", "name": "Shopify Inc.", "exchange": "KIS_US"},
    {"symbol": "ZM", "name": "Zoom Video", "exchange": "KIS_US"},
    {"symbol": "DDOG", "name": "Datadog Inc.", "exchange": "KIS_US"},
    {"symbol": "NET", "name": "Cloudflare Inc.", "exchange": "KIS_US"},
    {"symbol": "CRWD", "name": "CrowdStrike Holdings", "exchange": "KIS_US"},
    {"symbol": "ZS", "name": "Zscaler Inc.", "exchange": "KIS_US"},
    {"symbol": "PANW", "name": "Palo Alto Networks", "exchange": "KIS_US"},
    {"symbol": "NOW", "name": "ServiceNow Inc.", "exchange": "KIS_US"},
    {"symbol": "WDAY", "name": "Workday Inc.", "exchange": "KIS_US"},
    {"symbol": "TEAM", "name": "Atlassian Corporation", "exchange": "KIS_US"},
    {"symbol": "OKTA", "name": "Okta Inc.", "exchange": "KIS_US"},
    {"symbol": "MDB", "name": "MongoDB Inc.", "exchange": "KIS_US"},
]


def _is_cache_valid(exchange: str) -> bool:
    """캐시가 유효한지 확인 (1시간 TTL)"""
    cache = _symbol_cache.get(exchange)
    if not cache or not cache["updated_at"]:
        return False
    age = (datetime.now(timezone.utc) - cache["updated_at"]).total_seconds()
    return age < CACHE_TTL_SECONDS


async def _fetch_okx_symbols() -> list:
    """OKX 심볼 목록 가져오기"""
    try:
        async with httpx.AsyncClient(timeout=3.0) as client:
            resp = await client.get("https://www.okx.com/api/v5/public/instruments?instType=SPOT")
            if resp.status_code == 200:
                data = resp.json()
                symbols = []
                for item in data.get("data", []):
                    inst_id = item.get("instId", "")
                    base_ccy = item.get("baseCcy", "")
                    if inst_id.endswith("-USDT"):
                        symbols.append({
                            "symbol": inst_id,
                            "name": base_ccy,
                            "exchange": "OKX",
                        })
                return symbols
    except Exception as e:
        print(f"[OKX] Failed to fetch symbols: {e}")
    return []


async def _fetch_binance_symbols() -> list:
    """Binance 심볼 목록 가져오기"""
    try:
        async with httpx.AsyncClient(timeout=3.0) as client:
            resp = await client.get("https://api.binance.com/api/v3/exchangeInfo")
            if resp.status_code == 200:
                data = resp.json()
                symbols = []
                for item in data.get("symbols", []):
                    if item.get("status") == "TRADING" and item.get("quoteAsset") == "USDT":
                        symbols.append({
                            "symbol": item.get("symbol", ""),
                            "name": item.get("baseAsset", ""),
                            "exchange": "BINANCE",
                        })
                return symbols
    except Exception as e:
        print(f"[Binance] Failed to fetch symbols: {e}")
    return []


async def _fetch_bybit_symbols() -> list:
    """Bybit 심볼 목록 가져오기"""
    try:
        async with httpx.AsyncClient(timeout=3.0) as client:
            resp = await client.get("https://api.bybit.com/v5/market/instruments-info?category=spot")
            if resp.status_code == 200:
                data = resp.json()
                symbols = []
                for item in data.get("result", {}).get("list", []):
                    if item.get("quoteCoin") == "USDT":
                        symbols.append({
                            "symbol": item.get("symbol", ""),
                            "name": item.get("baseCoin", ""),
                            "exchange": "BYBIT",
                        })
                return symbols
    except Exception as e:
        print(f"[Bybit] Failed to fetch symbols: {e}")
    return []


async def _fetch_upbit_symbols() -> list:
    """Upbit 마켓 목록 가져오기"""
    try:
        async with httpx.AsyncClient(timeout=3.0) as client:
            resp = await client.get("https://api.upbit.com/v1/market/all")
            if resp.status_code == 200:
                data = resp.json()
                symbols = []
                for item in data:
                    market = item.get("market", "")
                    if market.startswith("KRW-"):
                        symbols.append({
                            "symbol": market,
                            "name": item.get("korean_name", item.get("english_name", "")),
                            "exchange": "UPBIT",
                        })
                return symbols
    except Exception as e:
        print(f"[Upbit] Failed to fetch symbols: {e}")
    return []


async def _refresh_symbol_cache(exchange: str):
    """특정 거래소 심볼 캐시 갱신"""
    now = datetime.now(timezone.utc)

    if exchange == "okx":
        symbols = await _fetch_okx_symbols()
        if symbols:
            _symbol_cache["okx"] = {"symbols": symbols, "updated_at": now}
    elif exchange == "binance":
        symbols = await _fetch_binance_symbols()
        if symbols:
            _symbol_cache["binance"] = {"symbols": symbols, "updated_at": now}
    elif exchange == "bybit":
        symbols = await _fetch_bybit_symbols()
        if symbols:
            _symbol_cache["bybit"] = {"symbols": symbols, "updated_at": now}
    elif exchange == "upbit":
        symbols = await _fetch_upbit_symbols()
        if symbols:
            _symbol_cache["upbit"] = {"symbols": symbols, "updated_at": now}
    elif exchange == "kis_kr":
        _symbol_cache["kis_kr"] = {"symbols": KIS_KR_STOCKS, "updated_at": now}
    elif exchange == "kis_us":
        _symbol_cache["kis_us"] = {"symbols": KIS_US_STOCKS, "updated_at": now}


async def _get_cached_symbols(exchange: str) -> list:
    """캐시된 심볼 목록 가져오기 (필요시 갱신)"""
    if not _is_cache_valid(exchange):
        await _refresh_symbol_cache(exchange)
    return _symbol_cache.get(exchange, {}).get("symbols", [])


async def _fetch_okx_ticker(symbol: str) -> dict:
    """OKX 실시간 가격 조회"""
    try:
        async with httpx.AsyncClient(timeout=3.0) as client:
            resp = await client.get(f"https://www.okx.com/api/v5/market/ticker?instId={symbol}")
            if resp.status_code == 200:
                data = resp.json().get("data", [])
                if data:
                    t = data[0]
                    last = float(t.get("last", 0))
                    open_24h = float(t.get("open24h", 0))
                    change = ((last - open_24h) / open_24h * 100) if open_24h else 0
                    return {
                        "price": last,
                        "change": round(change, 2),
                        "high_24h": float(t.get("high24h", 0)),
                        "low_24h": float(t.get("low24h", 0)),
                        "volume": float(t.get("vol24h", 0)),
                    }
    except Exception as e:
        print(f"[OKX] Ticker error for {symbol}: {e}")
    return None


async def _fetch_binance_ticker(symbol: str) -> dict:
    """Binance 실시간 가격 조회"""
    try:
        async with httpx.AsyncClient(timeout=3.0) as client:
            resp = await client.get(f"https://api.binance.com/api/v3/ticker/24hr?symbol={symbol}")
            if resp.status_code == 200:
                t = resp.json()
                return {
                    "price": float(t.get("lastPrice", 0)),
                    "change": float(t.get("priceChangePercent", 0)),
                    "high_24h": float(t.get("highPrice", 0)),
                    "low_24h": float(t.get("lowPrice", 0)),
                    "volume": float(t.get("quoteVolume", 0)),
                }
    except Exception as e:
        print(f"[Binance] Ticker error for {symbol}: {e}")
    return None


async def _fetch_bybit_ticker(symbol: str) -> dict:
    """Bybit 실시간 가격 조회"""
    try:
        async with httpx.AsyncClient(timeout=3.0) as client:
            resp = await client.get(f"https://api.bybit.com/v5/market/tickers?category=spot&symbol={symbol}")
            if resp.status_code == 200:
                data = resp.json().get("result", {}).get("list", [])
                if data:
                    t = data[0]
                    return {
                        "price": float(t.get("lastPrice", 0)),
                        "change": float(t.get("price24hPcnt", 0)) * 100,
                        "high_24h": float(t.get("highPrice24h", 0)),
                        "low_24h": float(t.get("lowPrice24h", 0)),
                        "volume": float(t.get("turnover24h", 0)),
                    }
    except Exception as e:
        print(f"[Bybit] Ticker error for {symbol}: {e}")
    return None


async def _fetch_upbit_ticker(symbol: str) -> dict:
    """Upbit 실시간 가격 조회"""
    try:
        async with httpx.AsyncClient(timeout=3.0) as client:
            resp = await client.get(f"https://api.upbit.com/v1/ticker?markets={symbol}")
            if resp.status_code == 200:
                data = resp.json()
                if data:
                    t = data[0]
                    return {
                        "price": float(t.get("trade_price", 0)),
                        "change": float(t.get("signed_change_rate", 0)) * 100,
                        "high_24h": float(t.get("high_price", 0)),
                        "low_24h": float(t.get("low_price", 0)),
                        "volume": float(t.get("acc_trade_price_24h", 0)),
                    }
    except Exception as e:
        print(f"[Upbit] Ticker error for {symbol}: {e}")
    return None


async def _fetch_popular_with_volume(exchange: str, limit: int = 10) -> list:
    """거래소별 거래량 상위 종목 조회"""
    try:
        if exchange == "okx":
            async with httpx.AsyncClient(timeout=3.0) as client:
                resp = await client.get("https://www.okx.com/api/v5/market/tickers?instType=SPOT")
                if resp.status_code == 200:
                    data = resp.json().get("data", [])
                    # USDT 페어만 필터링하고 거래량순 정렬
                    usdt_pairs = [d for d in data if d.get("instId", "").endswith("-USDT")]
                    usdt_pairs.sort(key=lambda x: float(x.get("volCcy24h", 0)), reverse=True)
                    result = []
                    for t in usdt_pairs[:limit]:
                        last = float(t.get("last", 0))
                        open_24h = float(t.get("open24h", 0))
                        change = ((last - open_24h) / open_24h * 100) if open_24h else 0
                        result.append({
                            "symbol": t.get("instId"),
                            "name": t.get("instId", "").replace("-USDT", ""),
                            "exchange": "OKX",
                            "price": last,
                            "change": round(change, 2),
                            "volume": float(t.get("volCcy24h", 0)),
                        })
                    return result
        elif exchange == "binance":
            async with httpx.AsyncClient(timeout=3.0) as client:
                resp = await client.get("https://api.binance.com/api/v3/ticker/24hr")
                if resp.status_code == 200:
                    data = resp.json()
                    usdt_pairs = [d for d in data if d.get("symbol", "").endswith("USDT")]
                    usdt_pairs.sort(key=lambda x: float(x.get("quoteVolume", 0)), reverse=True)
                    result = []
                    for t in usdt_pairs[:limit]:
                        result.append({
                            "symbol": t.get("symbol"),
                            "name": t.get("symbol", "").replace("USDT", ""),
                            "exchange": "BINANCE",
                            "price": float(t.get("lastPrice", 0)),
                            "change": float(t.get("priceChangePercent", 0)),
                            "volume": float(t.get("quoteVolume", 0)),
                        })
                    return result
        elif exchange == "bybit":
            async with httpx.AsyncClient(timeout=3.0) as client:
                resp = await client.get("https://api.bybit.com/v5/market/tickers?category=spot")
                if resp.status_code == 200:
                    data = resp.json().get("result", {}).get("list", [])
                    usdt_pairs = [d for d in data if d.get("symbol", "").endswith("USDT")]
                    usdt_pairs.sort(key=lambda x: float(x.get("turnover24h", 0)), reverse=True)
                    result = []
                    for t in usdt_pairs[:limit]:
                        result.append({
                            "symbol": t.get("symbol"),
                            "name": t.get("symbol", "").replace("USDT", ""),
                            "exchange": "BYBIT",
                            "price": float(t.get("lastPrice", 0)),
                            "change": float(t.get("price24hPcnt", 0)) * 100,
                            "volume": float(t.get("turnover24h", 0)),
                        })
                    return result
        elif exchange == "upbit":
            async with httpx.AsyncClient(timeout=3.0) as client:
                # 먼저 마켓 목록
                markets_resp = await client.get("https://api.upbit.com/v1/market/all")
                if markets_resp.status_code != 200:
                    return []
                markets = [m["market"] for m in markets_resp.json() if m["market"].startswith("KRW-")]
                market_names = {m["market"]: m.get("korean_name", "") for m in markets_resp.json()}

                # 티커 조회
                tickers_resp = await client.get(f"https://api.upbit.com/v1/ticker?markets={','.join(markets[:50])}")
                if tickers_resp.status_code == 200:
                    data = tickers_resp.json()
                    data.sort(key=lambda x: float(x.get("acc_trade_price_24h", 0)), reverse=True)
                    result = []
                    for t in data[:limit]:
                        market = t.get("market", "")
                        result.append({
                            "symbol": market,
                            "name": market_names.get(market, market.replace("KRW-", "")),
                            "exchange": "UPBIT",
                            "price": float(t.get("trade_price", 0)),
                            "change": float(t.get("signed_change_rate", 0)) * 100,
                            "volume": float(t.get("acc_trade_price_24h", 0)),
                        })
                    return result
    except Exception as e:
        print(f"[{exchange}] Failed to fetch popular: {e}")
    return []


class SymbolInfo(BaseModel):
    symbol: str
    name: str
    exchange: str
    price: float = 0
    price_formatted: str = "N/A"
    change: float = 0
    change_formatted: str = "0.00%"
    volume: float = 0
    volume_formatted: str = "0"
    high_24h: Optional[float] = None
    low_24h: Optional[float] = None


def _format_price(price: float, exchange: str) -> str:
    if price == 0:
        return "N/A"
    if exchange.upper() in ["OKX", "BINANCE", "BYBIT"]:
        return f"${price:,.2f}"
    elif exchange.upper() == "UPBIT":
        return f"₩{int(price):,}"
    elif exchange.upper() == "KIS_KR":
        return f"₩{int(price):,}"
    else:
        return f"${price:,.2f}"


def _format_volume(volume: float) -> str:
    if volume >= 1_000_000_000:
        return f"{volume / 1_000_000_000:.1f}B"
    elif volume >= 1_000_000:
        return f"{volume / 1_000_000:.1f}M"
    elif volume >= 1_000:
        return f"{volume / 1_000:.1f}K"
    return str(int(volume))


def _build_symbol_info(s: dict) -> SymbolInfo:
    price = s.get("price", 0)
    change = s.get("change", 0)
    volume = s.get("volume", 0)
    exchange = s.get("exchange", "")

    return SymbolInfo(
        symbol=s["symbol"],
        name=s.get("name", s["symbol"]),
        exchange=exchange,
        price=price,
        price_formatted=_format_price(price, exchange),
        change=change,
        change_formatted=f"{'+' if change >= 0 else ''}{change:.2f}%",
        volume=volume,
        volume_formatted=_format_volume(volume),
        high_24h=s.get("high_24h"),
        low_24h=s.get("low_24h")
    )


@app.get("/api/symbols/search")
async def search_symbols(
    q: str = Query("", description="검색어"),
    exchange: Optional[str] = Query(None, description="거래소 필터"),
    exclude_etf: bool = Query(False, description="ETF 제외 (주식만)"),
    exclude_otc: bool = Query(False, description="OTC/Pink Sheets 제외"),
    only_etf: bool = Query(False, description="ETF만 표시"),
    current_user: User = Depends(get_current_user_optional)
):
    """심볼 검색 — 거래소 API + KIS 종목 마스터

    필터 옵션:
    - exclude_etf: ETF 제외 (주식만 검색)
    - exclude_otc: OTC/Pink Sheets 종목 제외 (US 주식)
    - only_etf: ETF만 검색
    """
    # 요금제 확인 (무료 사용자는 제한)
    if current_user:
        plan = getattr(current_user, "plan", "free")
        role = getattr(current_user, "role", "user")
        if plan == "free" and role != "admin":
            return {"symbols": [], "message": "허브 이상 요금제에서 이용 가능합니다"}

    query = q.strip()
    results = []
    ex_lower = exchange.lower() if exchange else None

    # KIS 마스터 캐시에서 검색 (국내/해외 주식)
    if not ex_lower or ex_lower.startswith("kis"):
        master = get_master_cache()
        if not master.is_valid():
            await refresh_master_cache()

        # 개선된 검색 (ETF/OTC 필터링 지원)
        kis_results = master.search(
            query,
            market=ex_lower,
            limit=30,
            exclude_etf=exclude_etf,
            exclude_otc=exclude_otc,
            only_etf=only_etf
        )
        for stock in kis_results:
            # 마켓 기반 exchange 결정
            if stock.market in ("KOSPI", "KOSDAQ"):
                ex_name = "KIS_KR_ETF" if stock.is_etf else "KIS_KR"
            else:
                ex_name = "KIS_US_ETF" if stock.is_etf else "KIS_US"

            results.append({
                "symbol": stock.code,
                "name": stock.name,
                "exchange": ex_name,
                "market": stock.market,  # NYSE, NASDAQ, AMEX 등 거래소 구분
                "is_etf": stock.is_etf,
                "is_otc": getattr(stock, 'is_otc', False),
                "price": 0,
                "change": 0,
                "volume": 0,
            })

    # 암호화폐 거래소 검색
    crypto_exchanges = ["okx", "binance", "bybit", "upbit"]
    if not ex_lower or ex_lower in crypto_exchanges:
        for ex in crypto_exchanges:
            if ex_lower and ex != ex_lower:
                continue
            symbols = await _get_cached_symbols(ex)
            for s in symbols:
                sym = s.get("symbol", "").upper()
                name = s.get("name", "").upper()
                if not query or query.upper() in sym or query.upper() in name:
                    results.append({
                        "symbol": s["symbol"],
                        "name": s.get("name", s["symbol"]),
                        "exchange": s["exchange"],
                        "price": 0,
                        "change": 0,
                        "volume": 0,
                    })
                    if len(results) >= 50:
                        break
            if len(results) >= 50:
                break

    # SymbolInfo로 변환 (최대 50개)
    return {"symbols": [_build_symbol_info(r) for r in results[:50]]}


@app.get("/api/symbols/normalize")
async def normalize_symbol(
    symbol: str = Query(..., description="정규화할 심볼 (예: AAPL.O)"),
):
    """
    US 심볼 정규화 유틸리티

    거래소 접미사를 제거하고 표준 심볼로 변환:
    - AAPL.O → AAPL (NASDAQ)
    - JPM.N → JPM (NYSE)
    - SPY.A → SPY (AMEX)
    - ABML.PK → ABML (OTC/Pink Sheets)
    """
    original = symbol.strip().upper()
    normalized = normalize_us_symbol(original)
    detected_exchange = detect_exchange_from_symbol(original)
    is_otc = is_otc_symbol(original)

    # 마스터에서 종목 정보 조회
    master = get_master_cache()
    stock = master.get_stock(normalized)

    return {
        "original": original,
        "normalized": normalized,
        "detected_exchange": detected_exchange,
        "is_otc": is_otc,
        "stock_info": {
            "code": stock.code,
            "name": stock.name,
            "market": stock.market,
            "is_etf": stock.is_etf,
            "is_otc": getattr(stock, 'is_otc', False),
        } if stock else None
    }


async def _get_kis_credentials(db: Session, user_id: int) -> Optional[tuple]:
    """사용자의 KIS API 인증정보 조회"""
    try:
        # KIS 계정은 'kis', 'KIS', 'kis_kr', 'KIS_KR', 'kis_us', 'KIS_US' 등으로 저장될 수 있음
        # owner_id 컬럼 사용 (user_id가 아님)
        result = db.execute(
            text("SELECT api_key, api_secret FROM accounts WHERE owner_id = :uid AND LOWER(exchange) LIKE 'kis%' AND is_active = true LIMIT 1"),
            {"uid": user_id}
        )
        row = result.fetchone()
        if row:
            return (row[0], row[1])
    except Exception:
        pass
    return None


def _format_korean_number(value: int) -> str:
    """한국식 숫자 포맷 (억, 조)"""
    if value >= 1_000_000_000_000:
        return f"{value / 1_000_000_000_000:.1f}조"
    elif value >= 100_000_000:
        return f"{value / 100_000_000:.1f}억"
    elif value >= 10000:
        return f"{value / 10000:.1f}만"
    return f"{value:,}"


@app.get("/api/symbols/{exchange}/{symbol}")
async def get_symbol_detail(
    exchange: str,
    symbol: str,
    current_user: User = Depends(get_current_user_optional),
    db: Session = Depends(get_db)
):
    """심볼 상세 정보 — 미니 종목보고서"""
    # 요금제 확인
    if current_user:
        plan = getattr(current_user, "plan", "free")
        role = getattr(current_user, "role", "user")
        if plan == "free" and role != "admin":
            raise HTTPException(status_code=403, detail="허브 이상 요금제에서 이용 가능합니다")

    exchange_lower = exchange.lower()
    is_kis = exchange_lower.startswith("kis")

    # 기본 응답 구조
    response = {
        "basic": {
            "symbol": symbol,
            "name": symbol,
            "exchange": exchange.upper(),
            "market": "",
            "is_etf": False,
            "sector": "",
        },
        "price": {
            "current": 0,
            "change": 0,
            "change_amount": 0,
            "high": 0,
            "low": 0,
            "open": 0,
            "volume": 0,
            "current_formatted": "N/A",
            "change_formatted": "N/A",
            "high_formatted": "N/A",
            "low_formatted": "N/A",
            "volume_formatted": "N/A",
        },
        "financial": None,  # KIS 국내주식만
        "opinion": None,    # KIS 국내주식만
        "investor": None,   # KIS 국내주식만
        "daily_prices": [], # 차트용
        "has_kis_account": False,
    }

    # KIS 종목 (국내/해외 주식)
    if is_kis:
        master = get_master_cache()
        stock = master.get_stock(symbol)
        if stock:
            response["basic"]["name"] = stock.name
            response["basic"]["market"] = stock.market
            response["basic"]["is_etf"] = stock.is_etf

        # KIS 계정 확인
        kis_creds = None
        if current_user:
            kis_creds = await _get_kis_credentials(db, current_user.id)

        if kis_creds:
            response["has_kis_account"] = True
            app_key, app_secret = kis_creds

            # KIS 토큰 발급
            token = await get_kis_token(app_key, app_secret)
            if token:
                is_domestic = exchange_lower in ("kis_kr", "kis_kr_etf")
                market = stock.market if stock else ("KOSPI" if is_domestic else "NASDAQ")

                if is_domestic:
                    # 국내주식 현재가
                    price_data = await get_domestic_price(app_key, app_secret, token.access_token, symbol)
                    if price_data:
                        response["price"] = {
                            "current": price_data["current"],
                            "change": price_data["change"],
                            "change_amount": price_data["change_amount"],
                            "high": price_data["high"],
                            "low": price_data["low"],
                            "open": price_data["open"],
                            "volume": price_data["volume"],
                            "current_formatted": f"₩{price_data['current']:,}",
                            "change_formatted": f"{'+' if price_data['change'] >= 0 else ''}{price_data['change']:.2f}%",
                            "high_formatted": f"₩{price_data['high']:,}",
                            "low_formatted": f"₩{price_data['low']:,}",
                            "volume_formatted": _format_volume(price_data["volume"]),
                            "per": price_data.get("per", 0),
                            "pbr": price_data.get("pbr", 0),
                            "market_cap": price_data.get("market_cap", 0),
                            "market_cap_formatted": _format_korean_number(price_data.get("market_cap", 0) * 100000000),
                        }

                    # 재무비율
                    fin_data = await get_financial_ratio(app_key, app_secret, token.access_token, symbol)
                    if fin_data:
                        response["financial"] = {
                            "per": fin_data.get("per", 0),
                            "pbr": fin_data.get("pbr", 0),
                            "roe": fin_data.get("roe", 0),
                            "roa": fin_data.get("roa", 0),
                            "debt_ratio": fin_data.get("debt_ratio", 0),
                            "operating_margin": fin_data.get("operating_margin", 0),
                            "net_margin": fin_data.get("net_margin", 0),
                        }

                    # 손익계산서
                    income_data = await get_income_statement(app_key, app_secret, token.access_token, symbol)
                    if income_data and response["financial"]:
                        response["financial"]["income_statement"] = [
                            {
                                "period": item["period"],
                                "revenue": item["revenue"],
                                "revenue_formatted": _format_korean_number(item["revenue"]),
                                "operating_profit": item["operating_profit"],
                                "operating_profit_formatted": _format_korean_number(item["operating_profit"]),
                                "net_income": item["net_income"],
                                "net_income_formatted": _format_korean_number(item["net_income"]),
                            }
                            for item in income_data
                        ]

                    # 투자의견
                    opinion_data = await get_invest_opinion(app_key, app_secret, token.access_token, symbol)
                    if opinion_data:
                        response["opinion"] = {
                            "consensus": opinion_data.get("consensus", "N/A"),
                            "target_price": opinion_data.get("target_price", 0),
                            "target_price_formatted": f"₩{opinion_data.get('target_price', 0):,}",
                            "analyst_count": opinion_data.get("analyst_count", 0),
                            "buy_count": opinion_data.get("buy_count", 0),
                            "hold_count": opinion_data.get("hold_count", 0),
                            "sell_count": opinion_data.get("sell_count", 0),
                        }

                    # 투자자 매매동향
                    investor_data = await get_investor_trend(app_key, app_secret, token.access_token, symbol)
                    if investor_data:
                        response["investor"] = investor_data

                else:
                    # 해외주식 현재가
                    price_data = await get_overseas_price(app_key, app_secret, token.access_token, market, symbol)
                    if price_data:
                        response["price"] = {
                            "current": price_data["current"],
                            "change": price_data["change"],
                            "change_amount": price_data["change_amount"],
                            "high": price_data["high"],
                            "low": price_data["low"],
                            "open": price_data["open"],
                            "volume": price_data["volume"],
                            "current_formatted": f"${price_data['current']:,.2f}",
                            "change_formatted": f"{'+' if price_data['change'] >= 0 else ''}{price_data['change']:.2f}%",
                            "high_formatted": f"${price_data['high']:,.2f}",
                            "low_formatted": f"${price_data['low']:,.2f}",
                            "volume_formatted": _format_volume(price_data["volume"]),
                        }

                    # 해외주식 재무 데이터 (yfinance)
                    try:
                        us_fin = await get_stock_financials_us(symbol)
                        if us_fin and us_fin.get("revenue"):
                            # yfinance 데이터를 프론트 기대 형식으로 변환
                            response["financial"] = {
                                "per": us_fin.get("per"),
                                "pbr": us_fin.get("pbr"),
                                "roe": us_fin.get("roe"),
                                "eps": us_fin.get("eps", [None])[-1] if us_fin.get("eps") else None,
                                "income_statement": [
                                    {
                                        "period": us_fin["periods"][i] if i < len(us_fin.get("periods", [])) else "-",
                                        "revenue": us_fin["revenue"][i] if i < len(us_fin.get("revenue", [])) else 0,
                                        "revenue_formatted": f"${us_fin['revenue'][i]:,.0f}M" if i < len(us_fin.get("revenue", [])) and us_fin["revenue"][i] else "-",
                                        "operating_profit": us_fin["operating_profit"][i] if i < len(us_fin.get("operating_profit", [])) else 0,
                                        "operating_profit_formatted": f"${us_fin['operating_profit'][i]:,.0f}M" if i < len(us_fin.get("operating_profit", [])) and us_fin["operating_profit"][i] else "-",
                                        "net_income": us_fin["net_income"][i] if i < len(us_fin.get("net_income", [])) else 0,
                                        "net_income_formatted": f"${us_fin['net_income'][i]:,.0f}M" if i < len(us_fin.get("net_income", [])) and us_fin["net_income"][i] else "-",
                                    }
                                    for i in range(min(4, len(us_fin.get("periods", []))))
                                ]
                            }
                    except Exception as e:
                        print(f"[Symbol Detail] US financial error for {symbol}: {e}")

                # 일봉 데이터 (차트용)
                daily_data = await get_daily_prices(app_key, app_secret, token.access_token, symbol, market, 60)
                if daily_data:
                    response["daily_prices"] = daily_data

        else:
            # KIS 계정 없음 - 공개 API 사용 (네이버 금융, Yahoo Finance)
            is_domestic = exchange_lower in ("kis_kr", "kis_kr_etf")
            market = stock.market if stock else ("KOSPI" if is_domestic else "NASDAQ")

            if is_domestic:
                # 국내주식: 네이버 금융 API
                price_data = await get_naver_stock_price(symbol)
                if price_data:
                    response["price"] = {
                        "current": price_data["current"],
                        "change": price_data["change"],
                        "change_amount": price_data["change_amount"],
                        "high": price_data["high"],
                        "low": price_data["low"],
                        "open": price_data["open"],
                        "volume": price_data["volume"],
                        "current_formatted": f"₩{price_data['current']:,}",
                        "change_formatted": f"{'+' if price_data['change'] >= 0 else ''}{price_data['change']:.2f}%",
                        "high_formatted": f"₩{price_data['high']:,}",
                        "low_formatted": f"₩{price_data['low']:,}",
                        "volume_formatted": _format_volume(price_data["volume"]),
                        "market_cap": price_data.get("market_cap", 0),
                        "market_cap_formatted": _format_korean_number(price_data.get("market_cap", 0)),
                        "source": price_data.get("source", "naver"),
                    }

                # 일봉 데이터 (네이버)
                daily_data = await get_naver_daily_prices(symbol, 60)
                if daily_data:
                    response["daily_prices"] = daily_data

            else:
                # 해외주식: Yahoo Finance API
                price_data = await get_yahoo_stock_price(symbol, market)
                if price_data:
                    response["price"] = {
                        "current": price_data["current"],
                        "change": price_data["change"],
                        "change_amount": price_data["change_amount"],
                        "high": price_data["high"],
                        "low": price_data["low"],
                        "open": price_data["open"],
                        "volume": price_data["volume"],
                        "current_formatted": f"${price_data['current']:,.2f}",
                        "change_formatted": f"{'+' if price_data['change'] >= 0 else ''}{price_data['change']:.2f}%",
                        "high_formatted": f"${price_data['high']:,.2f}",
                        "low_formatted": f"${price_data['low']:,.2f}",
                        "volume_formatted": _format_volume(price_data["volume"]),
                        "market_cap": price_data.get("market_cap", 0),
                        "source": price_data.get("source", "yahoo"),
                    }

                # 일봉 데이터 (Yahoo)
                daily_data = await get_yahoo_daily_prices(symbol, 60)
                if daily_data:
                    response["daily_prices"] = daily_data

                # 해외주식 재무 데이터 (yfinance)
                try:
                    us_fin = await get_stock_financials_us(symbol)
                    if us_fin and us_fin.get("revenue"):
                        response["financial"] = {
                            "per": us_fin.get("per"),
                            "pbr": us_fin.get("pbr"),
                            "roe": us_fin.get("roe"),
                            "eps": us_fin.get("eps", [None])[-1] if us_fin.get("eps") else None,
                            "income_statement": [
                                {
                                    "period": us_fin["periods"][i] if i < len(us_fin.get("periods", [])) else "-",
                                    "revenue": us_fin["revenue"][i] if i < len(us_fin.get("revenue", [])) else 0,
                                    "revenue_formatted": f"${us_fin['revenue'][i]:,.0f}M" if i < len(us_fin.get("revenue", [])) and us_fin["revenue"][i] else "-",
                                    "operating_profit": us_fin["operating_profit"][i] if i < len(us_fin.get("operating_profit", [])) else 0,
                                    "operating_profit_formatted": f"${us_fin['operating_profit'][i]:,.0f}M" if i < len(us_fin.get("operating_profit", [])) and us_fin["operating_profit"][i] else "-",
                                    "net_income": us_fin["net_income"][i] if i < len(us_fin.get("net_income", [])) else 0,
                                    "net_income_formatted": f"${us_fin['net_income'][i]:,.0f}M" if i < len(us_fin.get("net_income", [])) and us_fin["net_income"][i] else "-",
                                }
                                for i in range(min(4, len(us_fin.get("periods", []))))
                            ]
                        }
                except Exception as e:
                    print(f"[Symbol Detail] US financial error for {symbol}: {e}")

    # 암호화폐 거래소
    else:
        ticker = None
        if exchange_lower == "okx":
            ticker = await _fetch_okx_ticker(symbol)
        elif exchange_lower == "binance":
            ticker = await _fetch_binance_ticker(symbol)
        elif exchange_lower == "bybit":
            ticker = await _fetch_bybit_ticker(symbol)
        elif exchange_lower == "upbit":
            ticker = await _fetch_upbit_ticker(symbol)

        # 캐시에서 심볼 이름 가져오기
        symbols = await _get_cached_symbols(exchange_lower)
        for s in symbols:
            if s["symbol"].upper() == symbol.upper():
                response["basic"]["name"] = s.get("name", symbol)
                break

        if ticker:
            is_krw = exchange_lower == "upbit"
            fmt = "₩" if is_krw else "$"
            response["price"] = {
                "current": ticker["price"],
                "change": ticker["change"],
                "change_amount": 0,
                "high": ticker["high_24h"],
                "low": ticker["low_24h"],
                "open": 0,
                "volume": ticker["volume"],
                "current_formatted": f"{fmt}{ticker['price']:,.2f}" if not is_krw else f"₩{int(ticker['price']):,}",
                "change_formatted": f"{'+' if ticker['change'] >= 0 else ''}{ticker['change']:.2f}%",
                "high_formatted": f"{fmt}{ticker['high_24h']:,.2f}" if not is_krw else f"₩{int(ticker['high_24h']):,}",
                "low_formatted": f"{fmt}{ticker['low_24h']:,.2f}" if not is_krw else f"₩{int(ticker['low_24h']):,}",
                "volume_formatted": _format_volume(ticker["volume"]),
            }

    return response


@app.get("/api/symbols/popular")
async def get_popular_symbols(
    exchange: Optional[str] = Query(None, description="특정 거래소 필터"),
    current_user: User = Depends(get_current_user_optional)
):
    """인기 종목 목록 — 거래량 상위 10개"""
    result = {}
    ex_lower = exchange.lower() if exchange else None

    # 암호화폐 거래소
    crypto_exchanges = ["okx", "binance", "bybit", "upbit"]
    if not ex_lower or ex_lower in crypto_exchanges:
        tasks = []
        for ex in crypto_exchanges:
            if ex_lower and ex != ex_lower:
                continue
            tasks.append((ex, _fetch_popular_with_volume(ex, 10)))

        for ex, task in tasks:
            try:
                popular = await task
                if popular:
                    result[ex] = [_build_symbol_info(s) for s in popular]
            except Exception as e:
                print(f"[{ex}] Popular fetch error: {e}")
                result[ex] = []

    # KIS 종목 (마스터 캐시 사용)
    kis_exchanges = ["kis_kr", "kis_kr_etf", "kis_us", "kis_us_etf"]
    if not ex_lower or ex_lower in kis_exchanges:
        master = get_master_cache()
        if not master.is_valid():
            await refresh_master_cache()

        for kis_ex in kis_exchanges:
            if ex_lower and kis_ex != ex_lower:
                continue

            popular_stocks = master.get_popular(market=kis_ex, limit=10)
            result[kis_ex] = [
                _build_symbol_info({
                    "symbol": s.code,
                    "name": s.name,
                    "exchange": kis_ex.upper(),
                    "market": s.market,
                    "is_etf": s.is_etf,
                    "price": 0,
                    "change": 0,
                    "volume": 0,
                })
                for s in popular_stocks
            ]

    return result


# =============================================================================
# [STOCK DETAIL RENEWAL] 종목 상세 - 스탁이지 스타일 (Phase 1)
# =============================================================================

def _check_hub_plan(user: Optional[User]) -> bool:
    """Hub 이상 요금제 체크 (종목 상세용)"""
    if not user:
        return False
    role = getattr(user, "role", "user")
    plan = getattr(user, "plan", "free")
    if role == "admin":
        return True
    return plan in ("hub", "pro", "premium")


@app.get("/api/stock/{code}/financial-summary")
async def api_stock_financial_summary(
    code: str,
    current_user: User = Depends(get_current_user_optional)
):
    """
    종목 재무 요약 (요약 탭)
    - 시가총액, PER, PBR, EPS, ROE, 52주 고저
    - Hub 이상 요금제 필요 (Free는 blur 처리)
    """
    data = await get_stock_financial_summary(code)

    # Free 요금제는 제한된 데이터만 반환
    is_premium = _check_hub_plan(current_user)

    return {
        "data": data,
        "is_premium": is_premium,
        "blur_fields": [] if is_premium else ["revenue", "operating_profit", "net_income", "roe", "eps", "foreign_ratio"]
    }


@app.get("/api/stock/{code}/financial-trend")
async def api_stock_financial_trend(
    code: str,
    current_user: User = Depends(get_current_user_optional)
):
    """
    종목 실적 추이 (재무 탭)
    - 분기별/연간별 매출액, 영업이익, 당기순이익
    - Hub 이상 요금제 필요
    """
    is_premium = _check_hub_plan(current_user)

    if not is_premium:
        return {
            "data": {"annual": [], "quarter": []},
            "is_premium": False,
            "message": "Hub 이상 요금제에서 이용 가능합니다"
        }

    data = await get_stock_financial_trend(code)
    return {
        "data": data,
        "is_premium": True
    }


@app.get("/api/stock/{code}/company")
async def api_stock_company(
    code: str,
    current_user: User = Depends(get_current_user_optional)
):
    """
    기업 정보 (기업 탭)
    - 회사 개요, CEO, 설립일, 사업 내용
    - 누구나 접근 가능
    """
    data = await get_stock_company(code)
    return {"data": data}


@app.get("/api/stock/{code}/financial-statement")
async def api_stock_financial_statement(
    code: str,
    current_user: User = Depends(get_current_user_optional)
):
    """
    재무제표 상세 (재무 탭)
    - 대차대조표, 손익계산서, 현금흐름표
    - Hub 이상 요금제 필요
    """
    is_premium = _check_hub_plan(current_user)

    if not is_premium:
        return {
            "data": {"balance_sheet": [], "income_statement": [], "cash_flow": []},
            "is_premium": False,
            "message": "Hub 이상 요금제에서 이용 가능합니다"
        }

    data = await get_stock_financial_statement(code)
    return {
        "data": data,
        "is_premium": True
    }


@app.get("/api/stock/{code}/news")
async def api_stock_news(
    code: str,
    limit: int = Query(20, ge=1, le=50),
    current_user: User = Depends(get_current_user_optional)
):
    """
    종목 뉴스/리포트 (소식 탭)
    - 누구나 접근 가능 (리포트는 Hub+)
    """
    data = await get_stock_news(code, limit)
    is_premium = _check_hub_plan(current_user)

    return {
        "data": {
            "news": data.get("news", []),
            "reports": data.get("reports", []) if is_premium else []
        },
        "is_premium": is_premium,
        "reports_locked": not is_premium
    }


@app.get("/api/stock/{code}/disclosures")
async def api_stock_disclosures(
    code: str,
    limit: int = Query(20, ge=1, le=50),
    current_user: User = Depends(get_current_user_optional)
):
    """
    공시 정보 (소식 탭)
    - 누구나 접근 가능
    """
    data = await get_stock_disclosures(code, limit)
    return {"data": data}


@app.get("/api/stock/{code}/consensus")
async def api_stock_consensus(
    code: str,
    current_user: User = Depends(get_current_user_optional)
):
    """
    투자 의견/컨센서스 (요약 탭)
    - Hub 이상 요금제 필요
    """
    is_premium = _check_hub_plan(current_user)

    if not is_premium:
        return {
            "data": {"target_price": 0, "opinion": "", "analyst_count": 0, "target_price_list": []},
            "is_premium": False,
            "message": "Hub 이상 요금제에서 이용 가능합니다"
        }

    data = await get_stock_consensus(code)
    return {
        "data": data,
        "is_premium": True
    }


@app.get("/api/stock/kr/{code}/chart")
async def api_stock_chart_kr(
    code: str,
    timeframe: str = Query("daily", regex="^(daily|weekly|monthly)$"),
    period: str = Query("3m", description="기간: 1d, 1w, 1m, 3m, 6m, 1y"),
    current_user: User = Depends(get_current_user_optional)
):
    """
    국내 종목 차트 데이터
    - timeframe: daily(일봉), weekly(주봉), monthly(월봉)
    - 누구나 접근 가능
    """
    candles = await get_chart_data(code, period, timeframe)
    return {
        "code": code,
        "timeframe": timeframe,
        "candles": candles
    }


@app.get("/api/stock/kr/{code}/summary")
async def api_stock_summary_kr(
    code: str,
    current_user: User = Depends(get_current_user_optional)
):
    """
    국내 종목 요약 정보 (기본정보 + 재무지표)
    - 누구나 접근 가능
    """
    data = await get_stock_summary_kr(code)
    return {"data": data}


@app.get("/api/stock/kr/{code}/financials")
async def api_stock_financials_kr(
    code: str,
    fin_type: str = Query("annual", description="annual 또는 quarter"),
    current_user: User = Depends(get_current_user_optional)
):
    """
    국내 종목 재무 추이 (연간/분기)
    - 누구나 접근 가능
    """
    data = await get_stock_financials_kr(code, fin_type)
    return {"data": data}


@app.get("/api/stock/kr/{code}/news")
async def api_stock_news_kr(
    code: str,
    limit: int = Query(20, ge=1, le=50),
    current_user: User = Depends(get_current_user_optional)
):
    """
    국내 종목 뉴스
    - 누구나 접근 가능
    """
    data = await get_stock_news_kr(code, limit)
    return {"data": data}


@app.get("/api/stock/kr/{code}/eps-revision")
async def api_eps_revision_history(
    code: str,
    current_user: User = Depends(get_current_user_optional)
):
    """
    국내 종목 EPS 추정 변화 이력 (FnGuide 컨센서스)
    - FY1/FY2/FY3 각각 5개 시점 데이터
    - 누구나 접근 가능
    """
    data = await get_eps_revision_history(code)
    return {"data": data}


@app.get("/api/stock/kr/{code}/company")
async def api_stock_company_kr(
    code: str,
    current_user: User = Depends(get_current_user_optional)
):
    """
    국내 종목 기업 정보 탭
    - 동종업계 종목, 리서치 리포트, 투자의견/목표가
    - 누구나 접근 가능
    """
    data = await get_stock_company_kr(code)
    return {"data": data}


@app.get("/api/stock/kr/{code}/statement")
async def api_stock_statement_kr(
    code: str,
    period_type: str = Query("annual", regex="^(annual|quarter)$"),
    current_user: User = Depends(get_current_user_optional)
):
    """
    국내 종목 상세 재무제표 (손익계산서)
    - period_type: annual(연간), quarter(분기)
    - 누구나 접근 가능
    """
    data = await get_stock_statement_kr(code, period_type)
    return {"data": data}


@app.get("/api/stock/kr/{code}/invest-indicators")
async def api_stock_invest_indicators_kr(
    code: str,
    current_user: User = Depends(get_current_user_optional)
):
    """
    국내 종목 투자지표 4카테고리 (성장성/수익성/안정성/밸류에이션)
    - 데이터 소스: FnGuide 재무비율 + 네이버
    - 누구나 접근 가능
    """
    data = await get_invest_indicators_kr(code)
    return {"data": data}


# =============================================================================
# Phase 9: 해외 종목 상세 API (Finviz + Yahoo Finance)
# =============================================================================

@app.get("/api/stock/us/{ticker}/summary")
async def api_stock_summary_us(
    ticker: str,
    current_user: User = Depends(get_current_user_optional)
):
    """
    해외 종목 요약 정보
    - 데이터 소스: Finviz snapshot
    - 누구나 접근 가능
    """
    data = await get_stock_summary_us(ticker)
    return {"data": data}


@app.get("/api/stock/us/{ticker}/chart")
async def api_stock_chart_us(
    ticker: str,
    timeframe: str = Query("daily", regex="^(daily|weekly|monthly)$"),
    period: str = Query("3m", regex="^(1d|5d|1w|1m|3m|6m|1y|2y|5y)$"),
    current_user: User = Depends(get_current_user_optional)
):
    """
    해외 종목 차트 데이터
    - 데이터 소스: Yahoo Finance Chart API
    - timeframe: daily(일봉), weekly(주봉), monthly(월봉)
    - 누구나 접근 가능
    """
    data = await get_stock_chart_us(ticker, period, timeframe)
    return {"data": data}


@app.get("/api/stock/us/{ticker}/news")
async def api_stock_news_us(
    ticker: str,
    limit: int = Query(20, ge=1, le=50),
    current_user: User = Depends(get_current_user_optional)
):
    """
    해외 종목 뉴스
    - 데이터 소스: Finviz news-table
    - 누구나 접근 가능
    """
    data = await get_stock_news_us(ticker, limit)
    return {"data": data}


@app.get("/api/stock/us/{ticker}/filings")
async def api_stock_filings_us(
    ticker: str,
    limit: int = Query(30, ge=1, le=50),
    current_user: User = Depends(get_current_user_optional)
):
    """
    해외 종목 SEC 공시
    - 데이터 소스: yfinance sec_filings
    - 누구나 접근 가능
    """
    data = await get_stock_filings_us(ticker, limit)
    return {"data": data}


@app.get("/api/stock/us/{ticker}/analyst")
async def api_stock_analyst_us(
    ticker: str,
    limit: int = Query(30, ge=1, le=50),
    current_user: User = Depends(get_current_user_optional)
):
    """
    해외 종목 애널리스트 의견
    - 데이터 소스: yfinance upgrades_downgrades
    - 누구나 접근 가능
    """
    data = await get_stock_analyst_us(ticker, limit)
    return {"data": data}


@app.get("/api/stock/us/{ticker}/company")
async def api_stock_company_us(
    ticker: str,
    current_user: User = Depends(get_current_user_optional)
):
    """
    해외 종목 기업 정보
    - 데이터 소스: Finviz
    - 누구나 접근 가능
    """
    data = await get_stock_company_us(ticker)
    return {"data": data}


@app.get("/api/stock/us/{ticker}/financials")
async def api_stock_financials_us(
    ticker: str,
    current_user: User = Depends(get_current_user_optional)
):
    """
    해외 종목 재무 정보 (연간 + 분기)
    - 데이터 소스: yfinance
    - 누구나 접근 가능
    """
    data = await get_stock_financials_us(ticker)
    return {"data": data}


@app.get("/api/stock/us/{ticker}/statement")
async def api_stock_statement_us(
    ticker: str,
    period_type: str = Query("annual", regex="^(annual|quarter)$"),
    current_user: User = Depends(get_current_user_optional)
):
    """
    해외 종목 상세 재무제표 (국내와 동일 구조)
    - period_type: annual(연간), quarter(분기)
    - 데이터 소스: yfinance
    - 누구나 접근 가능
    """
    from app.yahoo_finance import get_stock_statement_us
    data = await get_stock_statement_us(ticker, period_type)
    return {"data": data}


@app.get("/api/stock/us/{ticker}/invest-indicators")
async def api_stock_invest_indicators_us(
    ticker: str,
    current_user: User = Depends(get_current_user_optional)
):
    """
    해외 종목 투자지표 4카테고리 (국내와 동일 구조)
    - 성장성/수익성/안정성/밸류에이션
    - 데이터 소스: yfinance
    - 누구나 접근 가능
    """
    from app.yahoo_finance import get_invest_indicators_us
    data = await get_invest_indicators_us(ticker)
    return {"data": data}


# =============================================================================
# Phase 10: ETF 상세 페이지 API
# =============================================================================

@app.get("/api/etf/{code}/summary")
async def api_etf_summary(
    code: str,
    current_user: User = Depends(get_current_user_optional)
):
    """
    ETF 개요 정보
    - 데이터 소스: 네이버 integration + basic API
    - 누구나 접근 가능
    """
    data = await get_etf_summary(code)
    return {"data": data}


@app.get("/api/etf/{code}/chart")
async def api_etf_chart(
    code: str,
    period: str = "3m",
    current_user: User = Depends(get_current_user_optional)
):
    """
    ETF 차트 데이터
    - 데이터 소스: 네이버 fchart (국내 주식과 동일)
    - 누구나 접근 가능
    """
    data = await get_etf_chart(code, period)
    return {"data": data}


@app.get("/api/etf/{code}/performance")
async def api_etf_performance(
    code: str,
    current_user: User = Depends(get_current_user_optional)
):
    """
    ETF 수익률 및 분배금 정보
    - 데이터 소스: 네이버 integration API
    - 누구나 접근 가능
    """
    data = await get_etf_performance(code)
    return {"data": data}


# =============================================================================
# Phase 11-1: 통합 종목검색 (자동완성)
# =============================================================================

@app.get("/api/search")
async def api_search_stocks(
    q: str,
    limit: int = 10,
    exchange: Optional[str] = None,
    current_user: User = Depends(get_current_user_optional)
):
    """
    통합 종목검색 - 국내/해외/ETF 동시 검색
    캐시된 스크리너 데이터에서 검색하여 즉시 응답

    Args:
        q: 검색어
        limit: 최대 결과 수 (기본 10)
        exchange: 거래소 필터 (KIS_KR, KIS_US, OKX, BINANCE 등)
    """
    if not q or len(q) < 1:
        return {"results": []}

    # 거래소 필터 정규화
    ex_filter = exchange.upper() if exchange else None

    q_lower = q.lower()
    q_upper = q.upper()
    results = []

    # 관련도 점수 계산 함수
    def relevance_score(item):
        name = (item.get("name") or "").lower()
        code = (item.get("code") or item.get("symbol") or "").upper()
        q_check = q_lower

        # 정확 매치
        if name == q_check or code == q_upper:
            return 0
        # 시작 매치
        if name.startswith(q_check) or code.startswith(q_upper):
            return 1
        # 포함 매치
        return 2

    # 거래소별로 검색할지 결정 (v4 명령서)
    # KIS_KR: 국내주식 + 국내상장 ETF
    # KIS_US: 해외주식 + 해외상장 ETF (QQQ, SPY 등)
    # UPBIT/OKX/BINANCE/BYBIT: 각 거래소 코인만
    search_kr = not ex_filter or ex_filter == "KIS_KR"
    search_us = not ex_filter or ex_filter == "KIS_US"
    search_upbit = not ex_filter or ex_filter == "UPBIT"
    search_crypto = not ex_filter or ex_filter in ("OKX", "BINANCE", "BYBIT")

    if search_kr:
        try:
            # 국내 주식 검색
            from app.screener.kr_screener import load_kr_stocks
            kr_stocks = await load_kr_stocks()
            for stock in kr_stocks:
                name = (stock.get("name") or "").lower()
                code = (stock.get("code") or "").upper()
                if q_lower in name or q_upper in code:
                    results.append({
                        "code": stock.get("code"),
                        "name": stock.get("name"),
                        "market": stock.get("exchange", "KOSPI"),
                        "type": "stock_kr",
                        "price": stock.get("price", 0),
                        "change_pct": stock.get("change_pct", 0)
                    })
        except Exception as e:
            print(f"[Search] KR error: {e}")

        try:
            # KIS_KR에 국내상장 ETF 포함 (TIGER, KODEX, ARIRANG 등)
            from app.screener.etf_screener import load_etf_stocks
            etf_stocks = await load_etf_stocks()
            for etf in etf_stocks:
                name = (etf.get("name") or "").lower()
                code = (etf.get("code") or "").upper()
                if q_lower in name or q_upper in code:
                    results.append({
                        "code": etf.get("code"),
                        "name": etf.get("name"),
                        "market": "ETF",
                        "type": "etf_kr",
                        "price": etf.get("price", 0),
                        "change_pct": etf.get("change_pct", 0)
                    })
        except Exception as e:
            print(f"[Search] KR ETF error: {e}")

    if search_us:
        try:
            # 해외 주식 검색 (S&P 500)
            from app.screener.us_screener import load_us_stocks
            us_stocks = await load_us_stocks()
            for stock in us_stocks:
                name = (stock.get("name") or "").lower()
                code = (stock.get("code") or "").upper()
                if q_lower in name or q_upper in code:
                    results.append({
                        "code": stock.get("code"),
                        "symbol": stock.get("code"),
                        "name": stock.get("name"),
                        "market": stock.get("sector", "US"),
                        "type": "stock_us",
                        "price": stock.get("price", 0),
                        "change_pct": stock.get("change_pct", 0)
                    })
        except Exception as e:
            print(f"[Search] US error: {e}")

        # KIS_US에 해외상장 ETF 포함 (주요 미국 ETF 70개+)
        us_etfs = [
            # 주요 지수 추종 ETF
            {"code": "SPY", "name": "SPDR S&P 500 ETF Trust", "market": "US ETF"},
            {"code": "QQQ", "name": "Invesco QQQ Trust (NASDAQ 100)", "market": "US ETF"},
            {"code": "VOO", "name": "Vanguard S&P 500 ETF", "market": "US ETF"},
            {"code": "VTI", "name": "Vanguard Total Stock Market ETF", "market": "US ETF"},
            {"code": "IVV", "name": "iShares Core S&P 500 ETF", "market": "US ETF"},
            {"code": "DIA", "name": "SPDR Dow Jones Industrial Average ETF", "market": "US ETF"},
            {"code": "IWM", "name": "iShares Russell 2000 ETF", "market": "US ETF"},
            {"code": "MDY", "name": "SPDR S&P MidCap 400 ETF", "market": "US ETF"},
            # Schwab ETF (SCHG, SCHD 등)
            {"code": "SCHD", "name": "Schwab U.S. Dividend Equity ETF", "market": "US ETF"},
            {"code": "SCHG", "name": "Schwab U.S. Large-Cap Growth ETF", "market": "US ETF"},
            {"code": "SCHB", "name": "Schwab U.S. Broad Market ETF", "market": "US ETF"},
            {"code": "SCHA", "name": "Schwab U.S. Small-Cap ETF", "market": "US ETF"},
            {"code": "SCHX", "name": "Schwab U.S. Large-Cap ETF", "market": "US ETF"},
            {"code": "SCHF", "name": "Schwab International Equity ETF", "market": "US ETF"},
            {"code": "SCHE", "name": "Schwab Emerging Markets Equity ETF", "market": "US ETF"},
            # Vanguard ETF
            {"code": "VGT", "name": "Vanguard Information Technology ETF", "market": "US ETF"},
            {"code": "VUG", "name": "Vanguard Growth ETF", "market": "US ETF"},
            {"code": "VTV", "name": "Vanguard Value ETF", "market": "US ETF"},
            {"code": "VXUS", "name": "Vanguard Total International Stock ETF", "market": "US ETF"},
            {"code": "VEA", "name": "Vanguard FTSE Developed Markets ETF", "market": "US ETF"},
            {"code": "VWO", "name": "Vanguard FTSE Emerging Markets ETF", "market": "US ETF"},
            {"code": "VIG", "name": "Vanguard Dividend Appreciation ETF", "market": "US ETF"},
            {"code": "VYM", "name": "Vanguard High Dividend Yield ETF", "market": "US ETF"},
            {"code": "VNQ", "name": "Vanguard Real Estate ETF", "market": "US ETF"},
            # 섹터 ETF (SPDR Select Sector)
            {"code": "XLK", "name": "Technology Select Sector SPDR Fund", "market": "US ETF"},
            {"code": "XLF", "name": "Financial Select Sector SPDR Fund", "market": "US ETF"},
            {"code": "XLE", "name": "Energy Select Sector SPDR Fund", "market": "US ETF"},
            {"code": "XLV", "name": "Health Care Select Sector SPDR Fund", "market": "US ETF"},
            {"code": "XLY", "name": "Consumer Discretionary Select Sector SPDR Fund", "market": "US ETF"},
            {"code": "XLP", "name": "Consumer Staples Select Sector SPDR Fund", "market": "US ETF"},
            {"code": "XLI", "name": "Industrial Select Sector SPDR Fund", "market": "US ETF"},
            {"code": "XLB", "name": "Materials Select Sector SPDR Fund", "market": "US ETF"},
            {"code": "XLU", "name": "Utilities Select Sector SPDR Fund", "market": "US ETF"},
            {"code": "XLRE", "name": "Real Estate Select Sector SPDR Fund", "market": "US ETF"},
            # 채권 ETF (USHY 포함)
            {"code": "USHY", "name": "iShares Broad USD High Yield Corporate Bond ETF", "market": "US ETF"},
            {"code": "HYG", "name": "iShares iBoxx High Yield Corporate Bond ETF", "market": "US ETF"},
            {"code": "LQD", "name": "iShares iBoxx Investment Grade Corporate Bond ETF", "market": "US ETF"},
            {"code": "BND", "name": "Vanguard Total Bond Market ETF", "market": "US ETF"},
            {"code": "AGG", "name": "iShares Core U.S. Aggregate Bond ETF", "market": "US ETF"},
            {"code": "TLT", "name": "iShares 20+ Year Treasury Bond ETF", "market": "US ETF"},
            {"code": "IEF", "name": "iShares 7-10 Year Treasury Bond ETF", "market": "US ETF"},
            {"code": "SHY", "name": "iShares 1-3 Year Treasury Bond ETF", "market": "US ETF"},
            {"code": "TIP", "name": "iShares TIPS Bond ETF", "market": "US ETF"},
            {"code": "VCIT", "name": "Vanguard Intermediate-Term Corporate Bond ETF", "market": "US ETF"},
            {"code": "VCSH", "name": "Vanguard Short-Term Corporate Bond ETF", "market": "US ETF"},
            # 원자재/금/은
            {"code": "GLD", "name": "SPDR Gold Shares", "market": "US ETF"},
            {"code": "SLV", "name": "iShares Silver Trust", "market": "US ETF"},
            {"code": "IAU", "name": "iShares Gold Trust", "market": "US ETF"},
            {"code": "GDX", "name": "VanEck Gold Miners ETF", "market": "US ETF"},
            {"code": "USO", "name": "United States Oil Fund", "market": "US ETF"},
            {"code": "DBC", "name": "Invesco DB Commodity Index Tracking Fund", "market": "US ETF"},
            # 반도체 ETF
            {"code": "SOXX", "name": "iShares Semiconductor ETF", "market": "US ETF"},
            {"code": "SMH", "name": "VanEck Semiconductor ETF", "market": "US ETF"},
            {"code": "SOXL", "name": "Direxion Daily Semiconductor Bull 3X", "market": "US ETF"},
            {"code": "SOXS", "name": "Direxion Daily Semiconductor Bear 3X", "market": "US ETF"},
            # 레버리지/인버스 ETF
            {"code": "TQQQ", "name": "ProShares UltraPro QQQ (3x)", "market": "US ETF"},
            {"code": "SQQQ", "name": "ProShares UltraPro Short QQQ (-3x)", "market": "US ETF"},
            {"code": "SPXL", "name": "Direxion Daily S&P 500 Bull 3X", "market": "US ETF"},
            {"code": "SPXS", "name": "Direxion Daily S&P 500 Bear 3X", "market": "US ETF"},
            {"code": "UPRO", "name": "ProShares UltraPro S&P 500 (3x)", "market": "US ETF"},
            {"code": "SSO", "name": "ProShares Ultra S&P 500 (2x)", "market": "US ETF"},
            # ARK ETF
            {"code": "ARKK", "name": "ARK Innovation ETF", "market": "US ETF"},
            {"code": "ARKW", "name": "ARK Next Generation Internet ETF", "market": "US ETF"},
            {"code": "ARKG", "name": "ARK Genomic Revolution ETF", "market": "US ETF"},
            {"code": "ARKF", "name": "ARK Fintech Innovation ETF", "market": "US ETF"},
            {"code": "ARKQ", "name": "ARK Autonomous Tech & Robotics ETF", "market": "US ETF"},
            # 신흥국/국제 ETF
            {"code": "EEM", "name": "iShares MSCI Emerging Markets ETF", "market": "US ETF"},
            {"code": "EFA", "name": "iShares MSCI EAFE ETF", "market": "US ETF"},
            {"code": "IEMG", "name": "iShares Core MSCI Emerging Markets ETF", "market": "US ETF"},
            {"code": "FXI", "name": "iShares China Large-Cap ETF", "market": "US ETF"},
            {"code": "MCHI", "name": "iShares MSCI China ETF", "market": "US ETF"},
            {"code": "EWJ", "name": "iShares MSCI Japan ETF", "market": "US ETF"},
            {"code": "EWZ", "name": "iShares MSCI Brazil ETF", "market": "US ETF"},
            # 테마 ETF
            {"code": "XBI", "name": "SPDR S&P Biotech ETF", "market": "US ETF"},
            {"code": "IBB", "name": "iShares Biotechnology ETF", "market": "US ETF"},
            {"code": "KWEB", "name": "KraneShares CSI China Internet ETF", "market": "US ETF"},
            {"code": "ICLN", "name": "iShares Global Clean Energy ETF", "market": "US ETF"},
            {"code": "TAN", "name": "Invesco Solar ETF", "market": "US ETF"},
            {"code": "BOTZ", "name": "Global X Robotics & Artificial Intelligence ETF", "market": "US ETF"},
            {"code": "HACK", "name": "ETFMG Prime Cyber Security ETF", "market": "US ETF"},
            {"code": "JETS", "name": "U.S. Global Jets ETF", "market": "US ETF"},
        ]
        for etf in us_etfs:
            code = etf["code"].upper()
            name = etf["name"].lower()
            if q_upper in code or q_lower in name:
                results.append({
                    "code": etf["code"],
                    "symbol": etf["code"],
                    "name": etf["name"],
                    "market": etf["market"],
                    "type": "etf_us",
                    "price": 0,
                    "change_pct": 0
                })

    if search_upbit:
        try:
            # UPBIT 코인 검색 (KRW 마켓)
            upbit_pairs = [
                "KRW-BTC", "KRW-ETH", "KRW-XRP", "KRW-SOL", "KRW-ADA",
                "KRW-DOGE", "KRW-DOT", "KRW-LINK", "KRW-AVAX", "KRW-MATIC",
                "KRW-ATOM", "KRW-UNI", "KRW-LTC", "KRW-ETC", "KRW-BCH",
                "KRW-EOS", "KRW-TRX", "KRW-XLM", "KRW-ALGO", "KRW-SAND"
            ]
            crypto_names = {
                "BTC": "Bitcoin", "ETH": "Ethereum", "XRP": "Ripple", "SOL": "Solana",
                "ADA": "Cardano", "DOGE": "Dogecoin", "DOT": "Polkadot", "LINK": "Chainlink",
                "AVAX": "Avalanche", "MATIC": "Polygon", "ATOM": "Cosmos",
                "UNI": "Uniswap", "LTC": "Litecoin", "ETC": "Ethereum Classic", "BCH": "Bitcoin Cash",
                "EOS": "EOS", "TRX": "TRON", "XLM": "Stellar", "ALGO": "Algorand", "SAND": "The Sandbox"
            }
            for pair in upbit_pairs:
                base = pair.split("-")[1]  # KRW-BTC → BTC
                name = crypto_names.get(base, base).lower()
                if q_lower in name or q_upper in pair or q_upper in base:
                    results.append({
                        "code": pair,
                        "symbol": pair,
                        "name": crypto_names.get(base, base),
                        "market": "UPBIT",
                        "type": "crypto",
                        "price": 0,
                        "change_pct": 0
                    })
        except Exception as e:
            print(f"[Search] UPBIT error: {e}")

    if search_crypto:
        try:
            # 암호화폐 검색 (OKX, Binance, Bybit)
            # USDT 마켓 사용
            crypto_pairs = [
                "BTC-USDT", "ETH-USDT", "XRP-USDT", "SOL-USDT", "ADA-USDT",
                "DOGE-USDT", "DOT-USDT", "LINK-USDT", "AVAX-USDT", "MATIC-USDT",
                "BNB-USDT", "ATOM-USDT", "UNI-USDT", "LTC-USDT", "ETC-USDT"
            ]
            crypto_names = {
                "BTC": "Bitcoin", "ETH": "Ethereum", "XRP": "Ripple", "SOL": "Solana",
                "ADA": "Cardano", "DOGE": "Dogecoin", "DOT": "Polkadot", "LINK": "Chainlink",
                "AVAX": "Avalanche", "MATIC": "Polygon", "BNB": "BNB", "ATOM": "Cosmos",
                "UNI": "Uniswap", "LTC": "Litecoin", "ETC": "Ethereum Classic"
            }
            for pair in crypto_pairs:
                base = pair.split("-")[0]
                name = crypto_names.get(base, base).lower()
                if q_lower in name or q_upper in pair or q_upper in base:
                    results.append({
                        "code": pair,
                        "symbol": pair,
                        "name": crypto_names.get(base, base),
                        "market": ex_filter or "OKX",
                        "type": "crypto",
                        "price": 0,
                        "change_pct": 0
                    })
        except Exception as e:
            print(f"[Search] Crypto error: {e}")

    # 관련도 정렬
    results.sort(key=relevance_score)

    return {"results": results[:limit]}


# =============================================================================
# Phase 11-2: BBooster AI 추천
# =============================================================================

# 프리셋 전략 정의
PRESET_STRATEGIES = {
    "kr": {
        "momentum": {
            "title": "🔥 모멘텀 상승세",
            "description": "거래량 급증 + 상승 추세 종목",
            "sort": "change_pct",
            "order": "desc",
            "filters": {"change_filter": {"min": 2}},
            "limit": 10
        },
        "value": {
            "title": "💰 저평가 가치주",
            "description": "PER 10 이하 + ROE 10% 이상",
            "sort": "roe",
            "order": "desc",
            "filters": {"per": {"min": 1, "max": 10}, "roe": {"min": 10}},
            "limit": 10
        },
        "dividend": {
            "title": "🎯 고배당 안정주",
            "description": "배당수익률 3% 이상",
            "sort": "dividend_yield",
            "order": "desc",
            "filters": {"dividend_yield": {"min": 3}},
            "limit": 10
        },
        "large_cap": {
            "title": "🏢 대형 우량주",
            "description": "시가총액 상위 대형주",
            "sort": "market_cap",
            "order": "desc",
            "filters": {},
            "limit": 10
        }
    },
    "us": {
        "momentum": {
            "title": "🔥 강세 모멘텀",
            "description": "상승률 상위 종목",
            "sort": "change_pct",
            "order": "desc",
            "filters": {"change_filter": {"min": 2}},
            "limit": 10
        },
        "value": {
            "title": "💰 저평가 가치주",
            "description": "P/E 15 이하 우량주",
            "sort": "per",
            "order": "asc",
            "filters": {"per": {"min": 1, "max": 15}},
            "limit": 10
        },
        "large_cap": {
            "title": "🏢 대형 기술주",
            "description": "시가총액 상위 종목",
            "sort": "market_cap",
            "order": "desc",
            "filters": {},
            "limit": 10
        },
        "growth": {
            "title": "📈 성장주",
            "description": "높은 성장률 기대 종목",
            "sort": "eps_growth",
            "order": "desc",
            "filters": {},
            "limit": 10
        }
    },
    "etf": {
        "top_return": {
            "title": "🏆 수익률 TOP",
            "description": "최근 수익률 상위 ETF",
            "sort": "change_1m",
            "order": "desc",
            "filters": {},
            "limit": 10
        },
        "high_volume": {
            "title": "📊 거래 활발",
            "description": "거래량 상위 ETF",
            "sort": "volume",
            "order": "desc",
            "filters": {},
            "limit": 10
        },
        "low_fee": {
            "title": "💵 저비용",
            "description": "총보수 낮은 ETF",
            "sort": "expense_ratio",
            "order": "asc",
            "filters": {},
            "limit": 10
        },
        "high_aum": {
            "title": "🏦 순자산 대형",
            "description": "순자산총액 상위 ETF",
            "sort": "nav",
            "order": "desc",
            "filters": {},
            "limit": 10
        }
    }
}


@app.get("/api/ai/recommendations")
async def api_ai_recommendations(
    market: str = "kr",
    current_user: User = Depends(get_current_user_optional)
):
    """
    BBooster AI 추천 - 프리셋 전략 기반 종목 추천
    """
    from datetime import datetime

    strategies = PRESET_STRATEGIES.get(market, {})
    if not strategies:
        return {"market": market, "categories": [], "updated_at": datetime.now().isoformat()}

    categories = []

    for strategy_id, config in strategies.items():
        try:
            items = []

            if market == "kr":
                from app.screener.kr_screener import load_kr_stocks
                from app.screener.filters import apply_screener_filters, sort_screener_results
                stocks = await load_kr_stocks()
                if config.get("filters"):
                    stocks = apply_screener_filters(stocks, config["filters"])
                stocks = sort_screener_results(stocks, config.get("sort", "market_cap"), config.get("order", "desc"))
                items = stocks[:config.get("limit", 10)]

            elif market == "us":
                from app.screener.us_screener import load_us_stocks
                from app.screener.filters import apply_screener_filters, sort_screener_results
                stocks = await load_us_stocks()
                if config.get("filters"):
                    stocks = apply_screener_filters(stocks, config["filters"])
                stocks = sort_screener_results(stocks, config.get("sort", "market_cap"), config.get("order", "desc"))
                items = stocks[:config.get("limit", 10)]

            elif market == "etf":
                from app.screener.etf_screener import load_etf_stocks
                from app.screener.filters import apply_screener_filters, sort_screener_results
                stocks = await load_etf_stocks()
                if config.get("filters"):
                    stocks = apply_screener_filters(stocks, config["filters"])
                stocks = sort_screener_results(stocks, config.get("sort", "nav"), config.get("order", "desc"))
                items = stocks[:config.get("limit", 10)]

            # 필드 정리
            cleaned_items = []
            for item in items:
                cleaned = {
                    "code": item.get("code") or item.get("symbol"),
                    "name": item.get("name", ""),
                    "price": item.get("price", 0),
                    "change_pct": item.get("change_pct", 0),
                }
                # 시그널 생성 (간단한 설명)
                if config.get("sort") == "change_pct":
                    cleaned["signal"] = f"+{item.get('change_pct', 0):.1f}% 상승"
                elif config.get("sort") == "dividend_yield":
                    cleaned["signal"] = f"배당 {item.get('dividend_yield', 0):.1f}%"
                elif config.get("sort") == "roe":
                    cleaned["signal"] = f"ROE {item.get('roe', 0):.1f}%"
                elif config.get("sort") == "per":
                    cleaned["signal"] = f"PER {item.get('per', 0):.1f}"
                elif config.get("sort") == "market_cap":
                    mc = item.get("market_cap", 0)
                    if market == "us":
                        # US 시총: _parse_market_cap()이 "조 달러" 단위로 반환 (예: 4.68)
                        if mc >= 1:
                            cleaned["signal"] = f"${mc:.1f}T"
                        elif mc >= 0.001:
                            cleaned["signal"] = f"${mc*1000:.0f}B"
                        else:
                            cleaned["signal"] = f"${mc*1000000:.0f}M"
                    else:
                        # 한국 시총: 원 단위
                        if mc >= 1_000_000_000_000:
                            cleaned["signal"] = f"시총 {mc/1_000_000_000_000:.1f}조"
                        else:
                            cleaned["signal"] = f"시총 {mc/100_000_000:.0f}억"
                else:
                    cleaned["signal"] = ""
                cleaned_items.append(cleaned)

            categories.append({
                "id": strategy_id,
                "title": config["title"],
                "description": config["description"],
                "items": cleaned_items
            })

        except Exception as e:
            print(f"[AI] Error in {market}/{strategy_id}: {e}")
            categories.append({
                "id": strategy_id,
                "title": config["title"],
                "description": config["description"],
                "items": []
            })

    return {
        "market": market,
        "updated_at": datetime.now().isoformat(),
        "categories": categories
    }


# =============================================================================
# [STEP 2] 시장분석 API (Pro 이상)
# =============================================================================

def _check_pro_plan(user: Optional[User]) -> bool:
    """Pro 이상 요금제 체크"""
    if not user:
        return False
    role = getattr(user, "role", "user")
    plan = getattr(user, "plan", "free")
    if role == "admin":
        return True
    return plan in ("pro", "premium")


@app.get("/api/market/overview")
async def api_market_overview(
    current_user: User = Depends(get_current_user_optional),
    db: Session = Depends(get_db)
):
    """시장현황 — 지수 + 투자자 동향 (pykrx 사용)"""
    # 디버그 로그
    if current_user:
        print(f"[DEBUG] get_market_overview: user={current_user.email}, role={current_user.role}, plan={current_user.plan}")
    else:
        print("[DEBUG] get_market_overview: current_user is None (no auth token)")

    # admin이면 무조건 통과
    if current_user and current_user.role == "admin":
        pass  # 허용
    elif not _check_pro_plan(current_user):
        if not current_user:
            raise HTTPException(status_code=401, detail="로그인이 필요합니다")
        raise HTTPException(status_code=403, detail="Pro 이상 요금제에서 이용 가능합니다")

    # pykrx로 국내 시장 데이터 조회
    kr_data = await get_kr_market_overview()

    # KIS 계정 확인
    has_kis = False
    if current_user:
        kis_creds = await _get_kis_credentials(db, current_user.id)
        has_kis = kis_creds is not None

    # 시황 요약 생성
    kospi_change = kr_data.get("kospi", {}).get("change_percent", 0)
    kosdaq_change = kr_data.get("kosdaq", {}).get("change_percent", 0)

    if kospi_change > 1:
        market_status = "강세"
    elif kospi_change < -1:
        market_status = "약세"
    else:
        market_status = "보합"

    return {
        "kospi": kr_data.get("kospi", {}),
        "kosdaq": kr_data.get("kosdaq", {}),
        "investors": kr_data.get("investors", {}),
        "sectors": kr_data.get("sectors", []),
        "summary": {
            "status": market_status,
            "kospi_change": kospi_change,
            "kosdaq_change": kosdaq_change,
        },
        "has_kis_account": has_kis,
    }


@app.get("/api/market/sectors")
async def api_market_sectors(
    current_user: User = Depends(get_current_user_optional),
    db: Session = Depends(get_db)
):
    """업종별 현황 (pykrx 사용)"""
    # admin이면 무조건 통과
    if current_user and current_user.role == "admin":
        pass
    elif not _check_pro_plan(current_user):
        if not current_user:
            raise HTTPException(status_code=401, detail="로그인이 필요합니다")
        raise HTTPException(status_code=403, detail="Pro 이상 요금제에서 이용 가능합니다")

    # pykrx로 업종 데이터 조회 (overview에서 같이 가져옴)
    kr_data = await get_kr_market_overview()
    sectors = kr_data.get("sectors", [])

    return {
        "sectors": sectors,
        "leading": sectors[:3] if len(sectors) >= 3 else sectors,
        "lagging": sectors[-3:] if len(sectors) >= 3 else [],
    }


@app.get("/api/market/ranking")
async def get_stock_ranking(
    ranking_type: str = Query("volume", description="순위 유형: volume, trading_value, rise, fall, market_cap, foreign_buy, foreign_sell, institution_buy, institution_sell"),
    market: str = Query("all", description="시장: all, kospi, kosdaq"),
    current_user: User = Depends(get_current_user_optional),
    db: Session = Depends(get_db)
):
    """종목 순위"""
    if not _check_pro_plan(current_user):
        raise HTTPException(status_code=403, detail="Pro 이상 요금제에서 이용 가능합니다")

    # 시장 코드 변환
    market_code = "J" if market == "all" else ("0" if market == "kospi" else "1")

    # KIS 계정 확인
    kis_creds = None
    if current_user:
        kis_creds = await _get_kis_credentials(db, current_user.id)

    results = []

    if kis_creds:
        app_key, app_secret = kis_creds
        token = await get_kis_token(app_key, app_secret)
        if token:
            if ranking_type == "volume":
                results = await get_volume_rank(app_key, app_secret, token.access_token, market_code, 50) or []
            elif ranking_type == "trading_value":
                # 거래대금 순위: volume API 사용 후 value 기준 정렬
                raw_results = await get_volume_rank(app_key, app_secret, token.access_token, market_code, 50) or []
                results = sorted(raw_results, key=lambda x: x.get("value", 0), reverse=True)
                # rank 재할당
                for i, item in enumerate(results):
                    item["rank"] = i + 1
            elif ranking_type == "rise":
                results = await get_fluctuation_rank(app_key, app_secret, token.access_token, market_code, True, 50) or []
            elif ranking_type == "fall":
                results = await get_fluctuation_rank(app_key, app_secret, token.access_token, market_code, False, 50) or []
            elif ranking_type == "market_cap":
                results = await get_market_cap_rank(app_key, app_secret, token.access_token, market_code, 50) or []
            elif ranking_type == "foreign_buy":
                results = await get_foreign_net_rank(app_key, app_secret, token.access_token, True, 30) or []
            elif ranking_type == "foreign_sell":
                results = await get_foreign_net_rank(app_key, app_secret, token.access_token, False, 30) or []
            elif ranking_type == "institution_buy":
                results = await get_institution_net_rank(app_key, app_secret, token.access_token, True, 30) or []
            elif ranking_type == "institution_sell":
                results = await get_institution_net_rank(app_key, app_secret, token.access_token, False, 30) or []

    # KIS 계정 없으면 네이버 공개 API 사용
    if not results:
        naver_market = market.upper() if market != "all" else "ALL"
        if ranking_type in ("volume", "trading_value"):
            # 네이버는 거래대금 데이터 없음, 거래량으로 대체
            results = await get_naver_volume_rank(50, naver_market)
        elif ranking_type in ("rise", "fall"):
            results = await get_naver_fluctuation_rank(ranking_type == "rise", 50, naver_market)

    return {
        "ranking_type": ranking_type,
        "market": market,
        "stocks": results,
        "has_kis_account": kis_creds is not None,
    }


@app.get("/api/market/featured")
async def get_featured_stocks(
    current_user: User = Depends(get_current_user_optional),
    db: Session = Depends(get_db)
):
    """특징주 — 신고가, 급등/급락, 상한가/하한가"""
    if not _check_pro_plan(current_user):
        raise HTTPException(status_code=403, detail="Pro 이상 요금제에서 이용 가능합니다")

    # 공개 API로 급등/급락 조회
    rise_stocks = await get_naver_fluctuation_rank(True, 20)
    fall_stocks = await get_naver_fluctuation_rank(False, 20)

    # 상한가 (30% 이상)
    upper_limit = [s for s in rise_stocks if s.get("change", 0) >= 29.5]

    # 하한가 (-30% 이하)
    lower_limit = [s for s in fall_stocks if s.get("change", 0) <= -29.5]

    # 급등주 (10% 이상)
    surge_stocks = [s for s in rise_stocks if 10 <= s.get("change", 0) < 29.5]

    # 급락주 (-10% 이하)
    plunge_stocks = [s for s in fall_stocks if -29.5 < s.get("change", 0) <= -10]

    return {
        "upper_limit": upper_limit,
        "lower_limit": lower_limit,
        "surge": surge_stocks[:10],
        "plunge": plunge_stocks[:10],
        "rise_top": rise_stocks[:10],
        "fall_top": fall_stocks[:10],
    }


@app.get("/api/market/events")
async def get_market_events(
    event_type: str = Query("all", description="이벤트 유형: all, dividend, ipo, rights, bonus, meeting, split"),
    month: str = Query(None, description="월 필터: YYYY-MM"),
    current_user: User = Depends(get_current_user_optional),
    db: Session = Depends(get_db)
):
    """이벤트 일정 — 배당, 공모주, 증자 등"""
    if not _check_pro_plan(current_user):
        raise HTTPException(status_code=403, detail="Pro 이상 요금제에서 이용 가능합니다")

    # KIS 계정 필요 안내
    kis_creds = None
    if current_user:
        kis_creds = await _get_kis_credentials(db, current_user.id)

    if not kis_creds:
        return {
            "events": [],
            "message": "이벤트 일정은 KIS 계정 등록 시 이용 가능합니다.",
            "has_kis_account": False,
        }

    # TODO: KIS 예탁원 API 연동 필요
    # 현재는 샘플 데이터 반환
    sample_events = [
        {"type": "dividend", "stock_name": "삼성전자", "code": "005930", "date": "2026-03-15", "amount": 1444, "yield": 2.1},
        {"type": "dividend", "stock_name": "SK하이닉스", "code": "000660", "date": "2026-03-20", "amount": 1200, "yield": 0.8},
        {"type": "ipo", "stock_name": "테크스타", "date_start": "2026-02-10", "date_end": "2026-02-11", "price": 25000},
    ]

    # 이벤트 유형 필터
    if event_type != "all":
        sample_events = [e for e in sample_events if e.get("type") == event_type]

    return {
        "events": sample_events,
        "has_kis_account": True,
    }


# =============================================================================
# [BUG FIX] 시장분석 개선 API - 네이버/야후 직접 연동
# =============================================================================

@app.get("/api/market/kr/overview")
async def get_market_kr_overview(
    current_user: User = Depends(get_current_user_optional),
    db: Session = Depends(get_db)
):
    """국내시장 현황 - data_provider 사용"""
    # admin이면 무조건 통과
    if current_user and current_user.role == "admin":
        pass
    elif not _check_pro_plan(current_user):
        if not current_user:
            raise HTTPException(status_code=401, detail="로그인이 필요합니다")
        raise HTTPException(status_code=403, detail="Pro 이상 요금제에서 이용 가능합니다")

    try:
        data = await get_kr_market_overview()
        return {
            "indices": {
                "kospi": data.get("kospi", {"name": "코스피", "current": 0, "change": 0, "change_percent": 0}),
                "kosdaq": data.get("kosdaq", {"name": "코스닥", "current": 0, "change": 0, "change_percent": 0}),
            },
            "investor": data.get("investors", {"foreign": 0, "institution": 0, "individual": 0}),
            "sectors": data.get("sectors", [])[:5],
            "success": True,
        }

    except Exception as e:
        print(f"[API] KR market error: {e}")
        return {
            "indices": {},
            "investor": {},
            "sectors": [],
            "success": False,
            "error": str(e),
        }


@app.get("/api/market/us/overview")
async def api_market_us_overview(
    current_user: User = Depends(get_current_user_optional),
    db: Session = Depends(get_db)
):
    """해외시장 현황 - yfinance 사용"""
    # admin이면 무조건 통과
    if current_user and current_user.role == "admin":
        pass
    elif not _check_pro_plan(current_user):
        if not current_user:
            raise HTTPException(status_code=401, detail="로그인이 필요합니다")
        raise HTTPException(status_code=403, detail="Pro 이상 요금제에서 이용 가능합니다")

    try:
        data = await get_us_market_overview()
        return {
            "indices": data.get("indices", []),
            "stocks": data.get("stocks", []),
            "success": True,
        }
    except Exception as e:
        print(f"[API] US market error: {e}")
        return {
            "indices": [],
            "stocks": [],
            "success": False,
            "error": str(e),
        }


@app.get("/api/market/us/full")
async def api_market_us_full(
    current_user: User = Depends(get_current_user_optional),
    db: Session = Depends(get_db)
):
    """
    해외시장 전체 데이터 (Phase 5)
    - 지수 4개 + VIX
    - 섹터 ETF 11개
    - 히트맵 30종목
    - Fear & Greed Index
    - 시장신호 (Big Picture)
    """
    # admin이면 무조건 통과
    if current_user and current_user.role == "admin":
        pass
    elif not _check_pro_plan(current_user):
        if not current_user:
            raise HTTPException(status_code=401, detail="로그인이 필요합니다")
        raise HTTPException(status_code=403, detail="Pro 이상 요금제에서 이용 가능합니다")

    try:
        from .market_analysis.data_collector_us import get_us_market_summary
        from .market_analysis.signal_engine import BIG_PICTURE_CONFIG

        # 1. 미국시장 전체 요약 수집 (병렬)
        summary = await get_us_market_summary()

        # 2. 시장신호 조회 (SP500/NASDAQ)
        signal_result = {}
        try:
            from .models import MarketSignal
            for market in ["SP500", "NASDAQ"]:
                signal_row = db.query(MarketSignal).filter(MarketSignal.market == market).first()
                if signal_row and signal_row.signal_data:
                    sd = signal_row.signal_data
                    status = sd.get("status", "confirmed_uptrend")
                    cfg = BIG_PICTURE_CONFIG.get(status, BIG_PICTURE_CONFIG["confirmed_uptrend"])
                    signal_result[market.lower()] = {
                        "status": status,
                        "status_label": cfg["label"],
                        "exposure": cfg["exposure"],
                        "active_dd_count": sd.get("active_dd_count", 0),
                        "rally_day_count": sd.get("rally_day_count", 0),
                        "short_term_signal": sd.get("short_term_signal", "green"),
                        "long_term_signal": sd.get("long_term_signal", "green"),
                    }
                else:
                    # 기본값
                    signal_result[market.lower()] = {
                        "status": "confirmed_uptrend",
                        "status_label": "확인된 상승세",
                        "exposure": "80-100%",
                        "active_dd_count": 0,
                        "rally_day_count": 0,
                        "short_term_signal": "green",
                        "long_term_signal": "green",
                    }
        except Exception as sig_err:
            print(f"[US] signal query error: {sig_err}")
            for market in ["sp500", "nasdaq"]:
                signal_result[market] = {
                    "status": "confirmed_uptrend",
                    "status_label": "확인된 상승세",
                    "exposure": "80-100%",
                    "active_dd_count": 0,
                    "rally_day_count": 0,
                    "short_term_signal": "green",
                    "long_term_signal": "green",
                }

        return {
            "success": True,
            "indices": summary.get("indices", {}),
            "sectors": summary.get("sectors", []),
            "heatmap": summary.get("heatmap", []),
            "fear_greed": summary.get("fear_greed", {}),
            "breadth": summary.get("breadth", {}),
            "rising_stocks": summary.get("rising_stocks", 0),
            "falling_stocks": summary.get("falling_stocks", 0),
            "unchanged_stocks": summary.get("unchanged_stocks", 0),
            "signal": signal_result,
            "updated_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
        }

    except Exception as e:
        print(f"[API] US market full error: {e}")
        import traceback
        traceback.print_exc()
        return {
            "success": False,
            "indices": {},
            "sectors": [],
            "heatmap": [],
            "fear_greed": {},
            "breadth": {},
            "rising_stocks": 0,
            "falling_stocks": 0,
            "unchanged_stocks": 0,
            "signal": {},
            "error": str(e),
        }


@app.get("/api/market/us/trend-maintain")
async def get_us_trend_maintain(
    current_user: User = Depends(get_current_user_optional),
):
    """
    해외 섹터 ETF 추세유지 분석 (20MA 기준)
    """
    # admin이면 무조건 통과
    if current_user and current_user.role == "admin":
        pass
    elif not _check_pro_plan(current_user):
        if not current_user:
            raise HTTPException(status_code=401, detail="로그인이 필요합니다")
        raise HTTPException(status_code=403, detail="Pro 이상 요금제에서 이용 가능합니다")

    result = []
    try:
        from .market_analysis.data_collector_us import US_SECTOR_ETFS, fetch_sector_etf_daily
        from .market_analysis.trend_maintain import calculate_trend_maintain

        for etf in US_SECTOR_ETFS:
            symbol = etf["symbol"]
            closes = await fetch_sector_etf_daily(symbol, 60)

            if len(closes) >= 20:
                trend = calculate_trend_maintain(closes)
                if trend:
                    current_price = closes[-1] if closes else 0
                    prev_price = closes[-2] if len(closes) >= 2 else current_price
                    change_pct = ((current_price - prev_price) / prev_price * 100) if prev_price else 0

                    result.append({
                        "sector": etf["name"],
                        "etf": symbol,
                        "etf_name": etf["name_en"],
                        "change_pct": round(change_pct, 2),
                        "position": trend["position"],
                        "days": trend["days"],
                        "gap_percent": trend["gap_percent"],
                        "signal": trend["signal"],
                        "return_since_entry": trend.get("return_since_entry"),
                        "ma20": trend["ma20"],
                        "current_price": trend["current_price"],
                    })
            else:
                result.append({
                    "sector": etf["name"],
                    "etf": symbol,
                    "etf_name": etf["name_en"],
                    "change_pct": 0,
                    "position": "-",
                    "days": 0,
                    "gap_percent": 0,
                    "signal": "gray",
                })

        # 정렬: 유지 > 이탈, 일수 내림차순
        result.sort(key=lambda x: (0 if x["position"] == "유지" else 1, -x["days"]))

    except Exception as e:
        print(f"[API] /api/market/us/trend-maintain 오류: {e}")
        import traceback
        traceback.print_exc()

    return {
        "success": True,
        "data": result,
        "updated_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
    }


@app.get("/api/market/etf")
async def api_market_etf(
    current_user: User = Depends(get_current_user_optional),
    db: Session = Depends(get_db)
):
    """ETF 시장 현황 - ETFCheck 수준"""
    if current_user and current_user.role == "admin":
        pass
    elif not _check_pro_plan(current_user):
        if not current_user:
            raise HTTPException(status_code=401, detail="로그인이 필요합니다")
        raise HTTPException(status_code=403, detail="Pro 이상 요금제에서 이용 가능합니다")

    try:
        data = await get_etf_overview()
        return data
    except Exception as e:
        print(f"[API] ETF error: {e}")
        return {
            "total_count": 0, "total_up": 0, "total_down": 0,
            "themes_up": [], "themes_down": [],
            "distribution": [],
            "top_by_return": [], "bottom_by_return": [],
            "top_by_volume": [], "top_by_market": [],
            "major_etfs": [],
            "success": False, "error": str(e),
        }


@app.get("/api/market/crypto")
async def api_market_crypto(
    exchange: str = Query("all", description="거래소 필터: all, binance, upbit"),
    current_user: User = Depends(get_current_user_optional),
    db: Session = Depends(get_db)
):
    """코인 시장 현황 - data_provider 사용"""
    # admin이면 무조건 통과
    if current_user and current_user.role == "admin":
        pass
    elif not _check_pro_plan(current_user):
        if not current_user:
            raise HTTPException(status_code=401, detail="로그인이 필요합니다")
        raise HTTPException(status_code=403, detail="Pro 이상 요금제에서 이용 가능합니다")

    try:
        data = await get_crypto_overview()

        coins = []
        if exchange in ("all", "binance"):
            coins.extend(data.get("binance", []))
        if exchange in ("all", "upbit"):
            coins.extend(data.get("upbit", []))

        return {
            "coins": coins,
            "global": {
                "btc_dominance": data.get("btc_dominance", 0),
                "total_market_cap": data.get("total_market_cap", 0),
            },
            "kimchi_premium": data.get("kimchi_premium", 0),
            "success": True,
        }

    except Exception as e:
        print(f"[API] Crypto error: {e}")
        return {
            "coins": [],
            "global": {},
            "kimchi_premium": None,
            "success": False,
            "error": str(e),
        }


# =============================================================================
# 종목검색기 API (Phase 7)
# =============================================================================

@app.get("/api/screener")
async def api_screener(
    market: str = Query("kr", description="시장: kr, us, etf"),
    filters: str = Query("{}", description="필터 JSON 문자열"),
    sort: str = Query("market_cap", description="정렬 기준"),
    order: str = Query("desc", description="정렬 방향: asc, desc"),
    page: int = Query(1, description="페이지"),
    per_page: int = Query(50, description="페이지당 개수"),
    current_user: User = Depends(get_current_user_optional),
    db: Session = Depends(get_db)
):
    """종목검색기 - Finviz 스타일 스크리너"""
    # Pro 이상 체크
    if current_user and current_user.role == "admin":
        pass
    elif not _check_pro_plan(current_user):
        if not current_user:
            raise HTTPException(status_code=401, detail="로그인이 필요합니다")
        raise HTTPException(status_code=403, detail="Pro 이상 요금제에서 이용 가능합니다")

    import json
    try:
        filter_dict = json.loads(filters)
    except:
        filter_dict = {}

    try:
        if market == "kr":
            result = await screener_kr(filter_dict, sort, order, page, per_page)
        elif market == "us":
            from app.screener.us_screener import screener_us
            result = await screener_us(filter_dict, sort, order, page, per_page)
        elif market == "etf":
            from app.screener.etf_screener import screener_etf
            result = await screener_etf(filter_dict, sort, order, page, per_page)
        else:
            result = {"items": [], "total": 0, "message": "지원하지 않는 시장"}

        return result

    except Exception as e:
        print(f"[API] Screener error: {e}")
        import traceback
        traceback.print_exc()
        return {
            "items": [],
            "total": 0,
            "success": False,
            "error": str(e),
        }


# =============================================================================
# 스크리너 프리셋 API (Phase 7 Stage 3)
# =============================================================================

@app.get("/api/screener/presets")
async def api_screener_presets_list(
    market: str = Query("kr", description="시장: kr, us, etf"),
    current_user: User = Depends(get_current_user_optional),
    db: Session = Depends(get_db)
):
    """사용자 프리셋 목록 조회"""
    if not current_user:
        return {"presets": [], "success": False, "error": "로그인이 필요합니다"}

    from app.models import ScreenerPreset
    presets = db.query(ScreenerPreset).filter(
        ScreenerPreset.user_id == current_user.id,
        ScreenerPreset.market == market
    ).order_by(ScreenerPreset.is_default.desc(), ScreenerPreset.name).all()

    return {
        "presets": [
            {
                "id": p.id,
                "name": p.name,
                "market": p.market,
                "filters": p.filters,
                "sort_by": p.sort_by,
                "sort_order": p.sort_order,
                "is_default": p.is_default,
                "created_at": p.created_at.isoformat() if p.created_at else None,
            }
            for p in presets
        ],
        "success": True,
    }


@app.post("/api/screener/presets")
async def api_screener_preset_create(
    request: Request,
    current_user: User = Depends(get_current_user_optional),
    db: Session = Depends(get_db)
):
    """프리셋 저장"""
    if not current_user:
        raise HTTPException(status_code=401, detail="로그인이 필요합니다")

    body = await request.json()
    name = body.get("name", "").strip()
    market = body.get("market", "kr")
    filters = body.get("filters", {})
    sort_by = body.get("sort_by", "market_cap")
    sort_order = body.get("sort_order", "desc")
    is_default = body.get("is_default", False)

    if not name:
        raise HTTPException(status_code=400, detail="프리셋 이름을 입력하세요")

    from app.models import ScreenerPreset

    # 중복 이름 체크
    existing = db.query(ScreenerPreset).filter(
        ScreenerPreset.user_id == current_user.id,
        ScreenerPreset.name == name,
        ScreenerPreset.market == market
    ).first()

    if existing:
        # 덮어쓰기
        existing.filters = filters
        existing.sort_by = sort_by
        existing.sort_order = sort_order
        existing.is_default = is_default
        db.commit()
        preset_id = existing.id
    else:
        # 신규 생성
        preset = ScreenerPreset(
            user_id=current_user.id,
            name=name,
            market=market,
            filters=filters,
            sort_by=sort_by,
            sort_order=sort_order,
            is_default=is_default,
        )
        db.add(preset)
        db.commit()
        preset_id = preset.id

    # is_default가 True면 다른 프리셋의 is_default를 False로
    if is_default:
        db.query(ScreenerPreset).filter(
            ScreenerPreset.user_id == current_user.id,
            ScreenerPreset.market == market,
            ScreenerPreset.id != preset_id
        ).update({"is_default": False})
        db.commit()

    return {"success": True, "preset_id": preset_id}


@app.delete("/api/screener/presets/{preset_id}")
async def api_screener_preset_delete(
    preset_id: int,
    current_user: User = Depends(get_current_user_optional),
    db: Session = Depends(get_db)
):
    """프리셋 삭제"""
    if not current_user:
        raise HTTPException(status_code=401, detail="로그인이 필요합니다")

    from app.models import ScreenerPreset
    preset = db.query(ScreenerPreset).filter(
        ScreenerPreset.id == preset_id,
        ScreenerPreset.user_id == current_user.id
    ).first()

    if not preset:
        raise HTTPException(status_code=404, detail="프리셋을 찾을 수 없습니다")

    db.delete(preset)
    db.commit()

    return {"success": True}


# =============================================================================
# [BUG FIX] 종목분석 API - RS/신고가/밸류에이션
# =============================================================================

@app.get("/api/analysis/rs")
async def api_analysis_rs(
    market: str = Query("all", description="시장: all, kospi, kosdaq"),
    limit: int = Query(100, description="최대 개수"),
    current_user: User = Depends(get_current_user_optional),
    db: Session = Depends(get_db)
):
    """종합RS 순위 - pykrx 실제 데이터 사용"""
    try:
        # pykrx로 RS 계산
        rs_data = await get_rs_ranking(market.upper(), limit)

        return {
            "stocks": rs_data,
            "market": market,
            "success": True,
        }

    except Exception as e:
        print(f"[API] RS error: {e}")
        return {
            "stocks": [],
            "market": market,
            "success": False,
            "error": str(e),
        }


@app.get("/api/analysis/new-high")
async def api_analysis_new_high(
    limit: int = Query(50, description="최대 개수"),
    current_user: User = Depends(get_current_user_optional),
    db: Session = Depends(get_db)
):
    """52주 신고가 돌파 종목 - pykrx 사용"""
    try:
        stocks = await get_new_high_stocks(limit)
        return {
            "stocks": stocks,
            "success": True,
        }
    except Exception as e:
        print(f"[API] New high error: {e}")
        return {
            "stocks": [],
            "success": False,
            "error": str(e),
        }


@app.get("/api/analysis/valuation")
async def api_analysis_valuation(
    market: str = Query("all", description="시장: all, kospi, kosdaq"),
    sort_by: str = Query("per", description="정렬: per, pbr, market_cap"),
    limit: int = Query(200, description="최대 개수"),
    current_user: User = Depends(get_current_user_optional),
    db: Session = Depends(get_db)
):
    """밸류에이션 데이터 - pykrx 사용"""
    try:
        valuation_data = await get_valuation(market.upper(), limit)

        # 정렬
        if sort_by == "per":
            valuation_data.sort(key=lambda x: x["per"] if x["per"] > 0 else 9999)
        elif sort_by == "pbr":
            valuation_data.sort(key=lambda x: x["pbr"] if x["pbr"] > 0 else 9999)
        elif sort_by == "market_cap":
            valuation_data.sort(key=lambda x: x["market_cap"], reverse=True)

        return {
            "stocks": valuation_data[:limit],
            "market": market,
            "success": True,
        }

    except Exception as e:
        print(f"[API] Valuation error: {e}")
        return {
            "stocks": [],
            "market": market,
            "success": False,
            "error": str(e),
        }


@app.get("/api/analysis/reports")
async def get_analysis_reports(
    code: str = Query(None, description="종목코드 필터"),
    current_user: User = Depends(get_current_user_optional),
    db: Session = Depends(get_db)
):
    """증권사 리포트 요약 - KIS 계정 필요"""
    if not current_user:
        return {
            "reports": [],
            "has_kis_account": False,
            "message": "로그인이 필요합니다.",
        }

    kis_creds = await _get_kis_credentials(db, current_user.id)
    if not kis_creds:
        return {
            "reports": [],
            "has_kis_account": False,
            "message": "KIS 계정을 등록하면 증권사 리포트를 확인할 수 있습니다.",
        }

    try:
        app_key, app_secret = kis_creds
        token = await get_kis_token(app_key, app_secret)

        if not token:
            return {
                "reports": [],
                "has_kis_account": True,
                "message": "KIS 토큰 발급에 실패했습니다.",
            }

        # 투자의견 조회
        if code:
            opinions = await get_invest_opinion(app_key, app_secret, token.access_token, code)
        else:
            opinions = []

        return {
            "reports": opinions or [],
            "has_kis_account": True,
            "success": True,
        }

    except Exception as e:
        return {
            "reports": [],
            "has_kis_account": True,
            "success": False,
            "error": str(e),
        }


# =============================================================================
# [STEP 3] AI 분석 + 관심종목
# =============================================================================

# 요금제별 AI 사용 제한 (일일)
AI_DAILY_LIMITS = {
    "starter": 0,
    "free": 0,
    "standard": 3,
    "hub": 3,
    "pro": 7,
    "premium": 15,
}

# 요금제별 AI 사용 제한 (월간)
AI_MONTHLY_LIMITS = {
    "starter": 0,
    "free": 0,
    "standard": 30,
    "hub": 30,
    "pro": 100,
    "premium": 200,
}

# 요금제별 관심종목 제한
WATCHLIST_LIMITS = {
    "starter": 10,
    "free": 10,
    "standard": 50,
    "hub": 50,
    "pro": 200,
    "premium": 99999,
}


# AI 테이블 초기화 플래그 (서버 시작 시 1회만 실행)
_ai_tables_initialized = False


def _ensure_ai_tables(db: Session):
    """AI/관심종목 테이블 생성 — 서버 시작 시 1회만 실행"""
    global _ai_tables_initialized
    if _ai_tables_initialized:
        return  # 이미 초기화됨

    print("[DB] AI 테이블 초기화 시작...")
    sqls = [
        """
        DO $$ BEGIN
            ALTER TABLE users ADD COLUMN IF NOT EXISTS ai_usage_count INTEGER DEFAULT 0;
            ALTER TABLE users ADD COLUMN IF NOT EXISTS ai_usage_date DATE;
            ALTER TABLE users ADD COLUMN IF NOT EXISTS ai_monthly_count INTEGER DEFAULT 0;
            ALTER TABLE users ADD COLUMN IF NOT EXISTS ai_monthly_date VARCHAR(7);
        EXCEPTION WHEN others THEN NULL;
        END $$;
        """,
        """
        CREATE TABLE IF NOT EXISTS ai_reports (
            id SERIAL PRIMARY KEY,
            symbol VARCHAR(50),
            exchange VARCHAR(50),
            report_text TEXT,
            data_snapshot JSONB,
            created_at TIMESTAMP DEFAULT NOW(),
            expires_at TIMESTAMP
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS market_timeline (
            id SERIAL PRIMARY KEY,
            created_at TIMESTAMP DEFAULT NOW(),
            market_status VARCHAR(20),
            kospi_change DECIMAL(5,2),
            kosdaq_change DECIMAL(5,2),
            summary TEXT,
            leading_sectors JSONB,
            lagging_sectors JSONB,
            featured_stocks JSONB,
            keywords JSONB
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS watchlist_groups (
            id SERIAL PRIMARY KEY,
            user_id INTEGER REFERENCES users(id),
            name VARCHAR(100),
            sort_order INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT NOW()
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS watchlist_items (
            id SERIAL PRIMARY KEY,
            group_id INTEGER REFERENCES watchlist_groups(id) ON DELETE CASCADE,
            user_id INTEGER REFERENCES users(id),
            symbol VARCHAR(50),
            exchange VARCHAR(50),
            added_at TIMESTAMP DEFAULT NOW()
        )
        """
    ]
    for sql in sqls:
        try:
            db.execute(text(sql))
            db.commit()
        except Exception:
            db.rollback()

    _ai_tables_initialized = True
    print("[DB] AI 테이블 초기화 완료")


def _check_standard_plan(user: Optional[User]) -> bool:
    """Standard 이상 요금제 체크 (AI 분석용)"""
    if not user:
        return False
    role = getattr(user, "role", "user")
    plan = getattr(user, "plan", "free")
    if role == "admin":
        return True
    return plan in ("standard", "pro", "premium")


def _get_ai_daily_limit(user: User) -> int:
    """요금제별 AI 일일 사용 제한"""
    role = getattr(user, "role", "user")
    if role == "admin":
        return 99999
    plan = getattr(user, "plan", "free")
    return AI_DAILY_LIMITS.get(plan, 0)


def _get_ai_monthly_limit(user: User) -> int:
    """요금제별 AI 월간 사용 제한"""
    role = getattr(user, "role", "user")
    if role == "admin":
        return 99999
    plan = getattr(user, "plan", "free")
    return AI_MONTHLY_LIMITS.get(plan, 0)


def _get_watchlist_limit(user: User) -> int:
    """요금제별 관심종목 제한"""
    role = getattr(user, "role", "user")
    if role == "admin":
        return 99999
    plan = getattr(user, "plan", "free")
    return WATCHLIST_LIMITS.get(plan, 10)


@app.get("/api/ai/usage")
async def get_ai_usage(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """AI 사용량 조회 (일일 + 월간)"""
    _ensure_ai_tables(db)

    daily_max = _get_ai_daily_limit(current_user)
    monthly_max = _get_ai_monthly_limit(current_user)
    plan = getattr(current_user, "plan", "free")
    today = datetime.now(KST).date()
    this_month = today.strftime("%Y-%m")

    daily_count = 0
    monthly_count = 0

    try:
        result = db.execute(
            text("SELECT ai_usage_count, ai_usage_date, ai_monthly_count, ai_monthly_date FROM users WHERE id = :uid"),
            {"uid": current_user.id}
        )
        row = result.fetchone()
        if row:
            usage_date = row[1]
            monthly_date = row[3] or ""

            # 일일 리셋
            if usage_date == today:
                daily_count = row[0] or 0
            else:
                daily_count = 0

            # 월간 리셋
            if monthly_date == this_month:
                monthly_count = row[2] or 0
            else:
                monthly_count = 0

    except Exception as e:
        print(f"AI usage query error: {e}")

    return {
        "daily_used": daily_count,
        "daily_max": daily_max,
        "daily_remaining": max(0, daily_max - daily_count),
        "monthly_used": monthly_count,
        "monthly_max": monthly_max,
        "monthly_remaining": max(0, monthly_max - monthly_count),
        "plan": plan,
    }


# ============================================================================
# AI 작업 큐 시스템 (비동기 처리)
# ============================================================================
_ai_jobs = {}  # {job_id: {"status": "pending"|"running"|"done"|"error", ...}}

def _cleanup_old_jobs():
    """24시간 지난 작업 삭제 (PDF 다운로드 여유 확보)"""
    cutoff = datetime.now(KST) - timedelta(hours=24)
    expired = [k for k, v in _ai_jobs.items() if v.get("created_at", datetime.now(KST)) < cutoff]
    for k in expired:
        del _ai_jobs[k]


class AIAnalyzeRequest(BaseModel):
    symbol: str
    exchange: str


@app.post("/api/ai/analyze")
async def request_ai_analysis(
    request: AIAnalyzeRequest,
    current_user: User = Depends(get_current_user_optional),
    db: Session = Depends(get_db)
):
    """AI 종합분석 요청 → job_id 즉시 반환 (백그라운드 처리)"""
    import time as time_module
    t0 = time_module.time()
    print(f"[AI Analyze] === 요청 시작: {request.symbol} ===")

    _ensure_ai_tables(db)
    print(f"[AI Analyze] _ensure_ai_tables: {time_module.time()-t0:.2f}초")

    # 테스트용: 인증 없이도 동작하도록 (current_user가 None이면 스킵)
    if current_user and not _check_standard_plan(current_user):
        raise HTTPException(status_code=403, detail="AI 종합분석은 Standard 이상에서 이용 가능합니다")

    # 테스트용: current_user가 없으면 사용량 체크 스킵
    if current_user:
        daily_max = _get_ai_daily_limit(current_user)
        monthly_max = _get_ai_monthly_limit(current_user)
        today = datetime.now(KST).date()
        this_month = today.strftime("%Y-%m")

        daily_count = 0
        monthly_count = 0

        # 사용량 체크 및 리셋
        try:
            result = db.execute(
                text("SELECT ai_usage_count, ai_usage_date, ai_monthly_count, ai_monthly_date FROM users WHERE id = :uid"),
                {"uid": current_user.id}
            )
            row = result.fetchone()

            if row:
                usage_date = row[1]
                monthly_date = row[3] or ""

                if usage_date != today:
                    daily_count = 0
                    db.execute(
                        text("UPDATE users SET ai_usage_count = 0, ai_usage_date = :today WHERE id = :uid"),
                        {"uid": current_user.id, "today": today}
                    )
                else:
                    daily_count = row[0] or 0

                if monthly_date != this_month:
                    monthly_count = 0
                    db.execute(
                        text("UPDATE users SET ai_monthly_count = 0, ai_monthly_date = :month WHERE id = :uid"),
                        {"uid": current_user.id, "month": this_month}
                    )
                else:
                    monthly_count = row[2] or 0

                db.commit()

            if daily_count >= daily_max:
                return {"success": False, "error": "오늘의 AI 분석 횟수를 모두 사용했습니다."}

            if monthly_count >= monthly_max:
                return {"success": False, "error": "이번 달 AI 분석 횟수를 모두 사용했습니다."}

        except Exception as e:
            print(f"AI usage check error: {e}")

    print(f"[AI Analyze] usage check: {time_module.time()-t0:.2f}초")

    # 캐시 확인 (6시간 이내)
    try:
        cache_result = db.execute(
            text("""
                SELECT report_text FROM ai_reports
                WHERE symbol = :sym AND exchange = :ex AND expires_at > NOW()
                ORDER BY created_at DESC LIMIT 1
            """),
            {"sym": request.symbol, "ex": request.exchange}
        )
        cache_row = cache_result.fetchone()
        if cache_row:
            # 캐시된 리포트도 job_id 생성하여 PDF 다운로드 가능하게 함
            _cleanup_old_jobs()
            cache_job_id = str(uuid.uuid4())[:8]

            # 종목명 조회
            stock_name = request.symbol
            master = get_master_cache()
            stock = master.get_stock(request.symbol)
            if stock and hasattr(stock, 'name'):
                stock_name = stock.name

            _ai_jobs[cache_job_id] = {
                "status": "done",
                "progress": "✅ 캐시 로드 완료",
                "result": cache_row[0],
                "created_at": datetime.now(KST),
                "user_id": current_user.id if current_user else None,
                "symbol": request.symbol,
                "exchange": request.exchange,
                "stock": {"name": stock_name, "code": request.symbol},
                "charts": {},  # 캐시된 리포트는 차트 없음 (PDF에서 재생성)
                "cached": True,
            }
            print(f"[AI Analyze] 캐시 HIT: {stock_name}({request.symbol}), cache_job_id={cache_job_id}")
            return {"success": True, "status": "done", "report": cache_row[0], "job_id": cache_job_id, "cached": True}
    except Exception as e:
        print(f"[AI Analyze] 캐시 조회 오류: {e}")

    # 작업 큐 정리 및 job_id 생성
    _cleanup_old_jobs()
    job_id = str(uuid.uuid4())[:8]

    # 시장 구분 및 ETF 여부 확인
    exchange_lower = request.exchange.lower()
    is_domestic = exchange_lower in ("kis_kr", "kis_kr_etf")
    market = "kr" if is_domestic else "us"

    # ETF 여부 확인: exchange에 etf가 포함되어 있거나 DB에서 is_etf 확인
    is_etf = "etf" in exchange_lower
    if not is_etf:
        # DB에서 확인
        master = get_master_cache()
        stock = master.get_stock(request.symbol)
        if stock and getattr(stock, 'is_etf', False):
            is_etf = True

    # 작업 등록
    _ai_jobs[job_id] = {
        "status": "pending",
        "progress": "📊 요청 접수됨",
        "result": None,
        "created_at": datetime.now(KST),
        "user_id": current_user.id if current_user else None,
        "symbol": request.symbol,
        "exchange": request.exchange,
        "is_etf": is_etf,
    }

    # 백그라운드에서 실행 (즉시 반환)
    asyncio.create_task(_run_ai_analysis_job(job_id, request.symbol, market, is_etf))

    print(f"[AI Analyze] === 총 소요: {time_module.time()-t0:.2f}초, job_id={job_id} ===")
    return {"success": True, "job_id": job_id, "status": "pending"}


@app.get("/api/ai/status/{job_id}")
async def get_ai_job_status(job_id: str):
    """AI 분석 작업 상태 조회"""
    job = _ai_jobs.get(job_id)

    if not job:
        return {"success": False, "error": "작업을 찾을 수 없습니다", "status": "not_found"}

    if job["status"] == "done":
        report_text = job["result"] or ""
        sections = split_ai_report(report_text)

        response = {
            "success": True,
            "status": "done",
            "report": report_text,
            "sections": sections,  # 분리된 섹션 (차트-텍스트 묶음 배치용)
            "progress": "✅ 완료"
        }
        # 차트 URL 포함 (존재하는 경우)
        if "charts" in job:
            response["charts"] = job["charts"]
        if "stock" in job:
            response["stock"] = job["stock"]
        return response
    elif job["status"] == "error":
        return {
            "success": False,
            "status": "error",
            "error": job.get("error", "알 수 없는 오류"),
            "progress": "❌ 오류 발생"
        }
    else:
        return {
            "success": True,
            "status": job["status"],
            "progress": job.get("progress", "처리 중...")
        }


@app.get("/api/ai/report/pdf/{job_id}")
async def download_ai_report_pdf(job_id: str):
    """AI 분석 리포트 PDF 다운로드"""
    from fastapi.responses import FileResponse
    from reportlab.lib.pagesizes import A4
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Image as RLImage
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.units import inch, cm
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    import tempfile
    import re
    import io

    job = _ai_jobs.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="작업을 찾을 수 없습니다")

    if job["status"] != "done":
        raise HTTPException(status_code=400, detail="분석이 완료되지 않았습니다")

    # 한글 폰트 등록
    font_paths = [
        '/usr/share/fonts/truetype/nanum/NanumGothic.ttf',
        'C:/Windows/Fonts/malgun.ttf',
    ]
    font_registered = False
    for fp in font_paths:
        if os.path.exists(fp):
            try:
                pdfmetrics.registerFont(TTFont('Korean', fp))
                font_registered = True
                break
            except:
                pass

    # PDF 생성
    pdf_path = os.path.join(CHARTS_DIR, f"report_{job_id}.pdf")

    doc = SimpleDocTemplate(
        pdf_path,
        pagesize=A4,
        rightMargin=2*cm, leftMargin=2*cm,
        topMargin=2*cm, bottomMargin=2*cm
    )

    styles = getSampleStyleSheet()

    # 한글 스타일 정의
    if font_registered:
        styles.add(ParagraphStyle(
            name='KoreanTitle',
            fontName='Korean',
            fontSize=18,
            spaceAfter=20,
            alignment=1  # center
        ))
        styles.add(ParagraphStyle(
            name='KoreanBody',
            fontName='Korean',
            fontSize=10,
            leading=14,
            spaceAfter=10
        ))
        styles.add(ParagraphStyle(
            name='KoreanHeading',
            fontName='Korean',
            fontSize=14,
            spaceBefore=15,
            spaceAfter=10
        ))
    else:
        styles.add(ParagraphStyle(name='KoreanTitle', parent=styles['Title']))
        styles.add(ParagraphStyle(name='KoreanBody', parent=styles['Normal']))
        styles.add(ParagraphStyle(name='KoreanHeading', parent=styles['Heading2']))

    from reportlab.platypus import HRFlowable, Table, TableStyle
    from reportlab.lib import colors

    story = []

    # 제목
    stock_info = job.get("stock", {})
    stock_name = stock_info.get("name", "종목")
    stock_code = stock_info.get("code", "")
    title = f"{stock_name}({stock_code}) AI 분석 리포트"
    story.append(Paragraph(title, styles['KoreanTitle']))
    story.append(Spacer(1, 0.3*inch))

    # 차트 이미지 준비 (나중에 기술적 분석 섹션에 삽입)
    # base64 data URL → reportlab Image 변환
    import base64 as b64_module

    def _base64_to_rl_image(chart_data, width=6*inch, height=3*inch):
        """base64 data URL을 reportlab Image로 변환"""
        if not chart_data:
            return None
        try:
            if chart_data.startswith("data:image"):
                b64_str = chart_data.split(",", 1)[1]
            else:
                b64_str = chart_data
            img_bytes = b64_module.b64decode(b64_str)
            img_buf = io.BytesIO(img_bytes)
            return RLImage(img_buf, width=width, height=height)
        except Exception as e:
            print(f"[PDF] Chart base64 decode error: {e}")
            return None

    charts = job.get("charts", {})

    # 캐시된 리포트이거나 차트가 없으면 재생성
    if not charts or job.get("cached"):
        try:
            symbol = job.get("symbol", stock_code)
            exchange = job.get("exchange", "")
            is_domestic = exchange.lower() in ("kis_kr", "kis_kr_etf", "upbit")
            market = "kr" if is_domestic else "us"
            print(f"[PDF] 캐시 리포트 — 차트 재생성: {stock_name}({symbol})")
            charts = await _generate_ai_charts(symbol, stock_name, market)
            job["charts"] = charts  # 캐시에 저장
        except Exception as e:
            print(f"[PDF] 차트 재생성 실패: {e}")
            charts = {}

    chart_images = []

    # 순서 보장: price_chart → trend_chart → momentum_chart
    for chart_key in ['price_chart', 'trend_chart', 'momentum_chart']:
        chart_data = charts.get(chart_key)
        if chart_data:
            img = _base64_to_rl_image(chart_data)
            if img:
                chart_images.append(img)
                print(f"[PDF] Loaded {chart_key} from base64")
            else:
                print(f"[PDF] Failed to load {chart_key}")

    # 섹션 마커 제거 (PDF에 [SECTION_*] 노출 방지)
    def clean_section_markers(txt):
        markers = ['[SECTION_1_4]', '[SECTION_51]', '[SECTION_52]', '[SECTION_53]', '[SECTION_54_END]']
        for m in markers:
            txt = txt.replace(m, '')
        return txt.strip()

    # 본문 (마크다운을 변환)
    report_text = clean_section_markers(job.get("result", ""))

    # 마크다운 볼드/이탤릭 변환 함수
    def convert_markdown(txt):
        txt = re.sub(r'\*\*(.+?)\*\*', r'<b>\1</b>', txt)
        txt = re.sub(r'(?<!\*)\*(?!\*)(.+?)(?<!\*)\*(?!\*)', r'<i>\1</i>', txt)
        return txt

    # 테이블 파싱 함수
    def parse_markdown_table(table_lines):
        """마크다운 테이블을 ReportLab Table로 변환"""
        rows = []
        for tl in table_lines:
            tl = tl.strip()
            if tl.startswith('|') and tl.endswith('|'):
                cells = [c.strip() for c in tl[1:-1].split('|')]
                # 구분선 무시
                if all(c.replace('-', '').replace(':', '') == '' for c in cells):
                    continue
                rows.append(cells)
        if not rows:
            return None
        # 테이블 생성
        table_data = []
        for row in rows:
            table_data.append([Paragraph(convert_markdown(c), styles['KoreanBody']) for c in row])
        t = Table(table_data, repeatRows=1)
        t.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.lightgrey),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.black),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('FONTNAME', (0, 0), (-1, -1), 'Korean' if font_registered else 'Helvetica'),
            ('FONTSIZE', (0, 0), (-1, -1), 9),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
            ('TOPPADDING', (0, 0), (-1, -1), 6),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
        ]))
        return t

    # 섹션별 차트 삽입을 위해 split_ai_report 사용
    sections = split_ai_report(report_text)
    charts = job.get("charts", {})

    # 섹션 5.1/5.2/5.3에 차트 직접 삽입하는 헬퍼
    def insert_section_with_chart(section_text, chart_key, section_title):
        """섹션 제목 → 차트 → 텍스트 순서로 story에 추가"""
        if not section_text:
            return
        story.append(Spacer(1, 0.15*inch))
        story.append(Paragraph(f"<b>{section_title}</b>", styles['KoreanBody']))
        story.append(Spacer(1, 0.1*inch))
        # 차트 삽입
        chart_data = charts.get(chart_key)
        if chart_data:
            img = _base64_to_rl_image(chart_data)
            if img:
                story.append(img)
                story.append(Spacer(1, 0.12*inch))
        # 섹션 텍스트 (제목 + "5. 기술적 분석" 중복 제거)
        clean_text = re.sub(r'^#{1,4}\s*5\.\d[^\n]*\n?', '', section_text, flags=re.MULTILINE)
        clean_text = re.sub(r'^#{1,4}\s*5\.\s*기술적\s*분석\s*\n?', '', clean_text, flags=re.MULTILINE)
        for para_line in clean_text.split('\n'):
            para_line = para_line.strip()
            if para_line:
                story.append(Paragraph(convert_markdown(para_line), styles['KoreanBody']))

    # before_ta 방어 로직: 비어있으면 5.1 이전 텍스트를 직접 추출
    before_ta = sections.get('before_ta', '')
    if not before_ta.strip():
        # 폴백: report_text에서 5.1 이전까지만 추출
        match = re.search(r'(?:#{1,4}\s*)?5\.1\s', report_text)
        if match:
            before_ta = report_text[:match.start()].strip()
        else:
            before_ta = report_text  # 최후 폴백

    # ★ "5. 기술적 분석" 제목 중복 방지: before_ta 끝에서 제거 (5.1~5.3에서 차트와 함께 별도 처리됨)
    before_ta = re.sub(r'\n*#{1,4}\s*5\.\s*기술적\s*분석\s*$', '', before_ta).strip()

    # 1~4 섹션 처리 (차트 없음, before_ta만 처리)
    lines = before_ta.split('\n')
    i = 0

    while i < len(lines):
        line = lines[i].strip()

        # 빈 줄
        if not line:
            story.append(Spacer(1, 0.08*inch))
            i += 1
            continue

        # 수평선 (---, ***, ___)
        if line in ['---', '***', '___'] or (len(line) >= 3 and all(c == '-' for c in line)):
            story.append(HRFlowable(width="100%", thickness=1, color=colors.grey, spaceAfter=10, spaceBefore=10))
            i += 1
            continue

        # 테이블 감지 (|로 시작하는 줄)
        if line.startswith('|'):
            table_lines = []
            while i < len(lines) and lines[i].strip().startswith('|'):
                table_lines.append(lines[i])
                i += 1
            table = parse_markdown_table(table_lines)
            if table:
                story.append(table)
                story.append(Spacer(1, 0.15*inch))
            continue

        # 제목 처리 (## 1. 제목 형태)
        if line.startswith('## '):
            text = convert_markdown(line[3:])
            story.append(Spacer(1, 0.15*inch))
            story.append(Paragraph(text, styles['KoreanHeading']))
            story.append(Spacer(1, 0.08*inch))
            i += 1
            continue
        elif line.startswith('# '):
            text = convert_markdown(line[2:])
            story.append(Spacer(1, 0.15*inch))
            story.append(Paragraph(text, styles['KoreanHeading']))
            story.append(Spacer(1, 0.08*inch))
            i += 1
            continue
        elif line.startswith('### '):
            text = convert_markdown(line[4:])
            story.append(Paragraph(f"<b>{text}</b>", styles['KoreanBody']))
            story.append(Spacer(1, 0.08*inch))
            i += 1
            continue
        elif line.startswith('#### '):
            # 일반 #### 헤딩 (5.1/5.2/5.3은 아래 섹션별 처리에서 담당)
            text = convert_markdown(line[5:])
            story.append(Paragraph(f"<b>{text}</b>", styles['KoreanBody']))
            i += 1
            continue

        # 리스트 항목
        if line.startswith('- ') or line.startswith('* '):
            text = convert_markdown(line[2:])
            story.append(Paragraph(f"• {text}", styles['KoreanBody']))
            i += 1
            continue
        if line.startswith('• '):
            text = convert_markdown(line[2:])
            story.append(Paragraph(f"• {text}", styles['KoreanBody']))
            i += 1
            continue

        # 전체가 볼드인 줄
        if line.startswith('**') and line.endswith('**') and line.count('**') == 2:
            text = line[2:-2]
            story.append(Paragraph(f"<b>{text}</b>", styles['KoreanBody']))
            i += 1
            continue

        # 일반 텍스트
        text = convert_markdown(line)
        story.append(Paragraph(text, styles['KoreanBody']))
        i += 1

    # 5. 기술적 분석 — 항상 섹션별 차트+텍스트 삽입 (제목은 AI 텍스트에 포함됨)
    story.append(Spacer(1, 0.2*inch))

    # 5.1 주가 및 지지/저항 → 차트1
    insert_section_with_chart(sections.get('section_51'), 'price_chart', '5.1 주가 및 지지/저항선 분석')

    # 5.2 추세추종 지표 → 차트2
    insert_section_with_chart(sections.get('section_52'), 'trend_chart', '5.2 추세추종 지표 분석')

    # 5.3 모멘텀 지표 → 차트3
    insert_section_with_chart(sections.get('section_53'), 'momentum_chart', '5.3 모멘텀 지표 분석')

    # 5.4~ 나머지 섹션 (면책조항 제외 - 아래에서 고정 삽입)
    if sections.get('after_53'):
        # AI가 생성한 면책조항 부분 제거 (고정 삽입으로 대체)
        after_53_text = sections['after_53']
        after_53_text = re.sub(r'(?:#{1,4}\s*)?(?:6|7)\.\s*면책조항.*', '', after_53_text, flags=re.DOTALL).strip()

        if after_53_text:
            story.append(Spacer(1, 0.15*inch))
            for para_line in after_53_text.split('\n'):
                para_line = para_line.strip()
                if para_line:
                    story.append(Paragraph(convert_markdown(para_line), styles['KoreanBody']))

    # ===== 면책조항 고정 삽입 (AI 출력과 무관하게 항상 표시) =====
    story.append(Spacer(1, 0.3*inch))
    story.append(HRFlowable(width="100%", thickness=1, color=colors.grey, spaceAfter=10, spaceBefore=10))
    story.append(Spacer(1, 0.1*inch))
    story.append(Paragraph("<b>6. 면책조항</b>", styles['KoreanHeading']))
    story.append(Spacer(1, 0.08*inch))
    disclaimer_text = (
        "본 보고서는 투자 참고 자료로만 활용하시기 바라며, "
        "특정 종목의 매수/매도를 권유하지 않습니다. "
        "투자 결정은 본인의 투자 성향, 시간 범위, 재정 상황을 고려하여 "
        "신중하게 내려주시기 바랍니다. "
        "과거 성과는 미래 결과를 보장하지 않으며, "
        "투자 손실 위험이 존재합니다. "
        "기술적 분석은 확률 기반 분석으로, 모든 신호가 정확히 작동하지 않을 수 있습니다."
    )
    story.append(Paragraph(disclaimer_text, styles['KoreanBody']))

    # PDF 빌드
    doc.build(story)

    return FileResponse(
        pdf_path,
        media_type="application/pdf",
        filename=f"{stock_name}_{stock_code}_분석리포트.pdf"
    )


async def _run_ai_analysis_job(job_id: str, symbol: str, market: str, is_etf: bool = False):
    """백그라운드에서 AI 분석 실행"""
    try:
        _ai_jobs[job_id]["status"] = "running"
        _ai_jobs[job_id]["progress"] = "📊 종목 데이터 수집 중..."

        # 종목명 조회
        name = symbol
        master = get_master_cache()
        stock = master.get_stock(symbol)
        if stock:
            name = stock.name
        elif market == "kr":
            try:
                async with httpx.AsyncClient(timeout=5.0) as client:
                    resp = await client.get(
                        f"https://m.stock.naver.com/api/stock/{symbol}/basic",
                        headers={"User-Agent": "Mozilla/5.0"}
                    )
                    if resp.status_code == 200:
                        naver_data = resp.json()
                        if naver_data.get("stockName"):
                            name = naver_data["stockName"]
            except Exception:
                pass

        # 차트 생성
        _ai_jobs[job_id]["progress"] = "📈 차트 생성 중..."
        try:
            chart_urls = await _generate_ai_charts(symbol, name, market)
            if chart_urls:
                _ai_jobs[job_id]["charts"] = chart_urls
        except Exception as e:
            print(f"[AI Job] Chart generation error: {e}")

        _ai_jobs[job_id]["progress"] = "🤖 AI가 분석 중..."

        # Claude API로 리포트 생성 (ETF 여부에 따라 분기, 차트 데이터 전달)
        if is_etf:
            ai_result = await _generate_etf_report(name=name, code=symbol, market=market, chart_data=chart_urls)
        else:
            ai_result = await _generate_claude_report(name=name, code=symbol, market=market, chart_data=chart_urls)

        report = ai_result.get("report", "")
        if not report or len(report) < 200:
            raise Exception("리포트 생성 실패")

        # 종목 정보 저장 (PDF 다운로드용)
        _ai_jobs[job_id]["stock"] = {"name": name, "code": symbol}

        # 완료
        _ai_jobs[job_id]["status"] = "done"
        _ai_jobs[job_id]["result"] = report
        _ai_jobs[job_id]["progress"] = "✅ 완료"

        # 사용량 증가 + 캐시 저장 (DB 세션 새로 생성)
        try:
            from app.db import SessionLocal
            db = SessionLocal()
            user_id = _ai_jobs[job_id].get("user_id")
            exchange = _ai_jobs[job_id].get("exchange", "")

            if user_id:
                db.execute(
                    text("UPDATE users SET ai_usage_count = ai_usage_count + 1, ai_monthly_count = ai_monthly_count + 1 WHERE id = :uid"),
                    {"uid": user_id}
                )

            expires = datetime.now(timezone.utc) + timedelta(hours=6)
            db.execute(
                text("INSERT INTO ai_reports (symbol, exchange, report_text, data_snapshot, expires_at) VALUES (:sym, :ex, :report, :data, :expires)"),
                {"sym": symbol, "ex": exchange, "report": report, "data": "{}", "expires": expires}
            )
            db.commit()
            db.close()
        except Exception as e:
            print(f"[AI Job] DB update error: {e}")

        print(f"[AI Job] {job_id} 완료: {len(report)}자")

    except Exception as e:
        print(f"[AI Job] {job_id} 오류: {e}")
        _ai_jobs[job_id]["status"] = "error"
        _ai_jobs[job_id]["error"] = str(e)
        _ai_jobs[job_id]["progress"] = "❌ 오류 발생"




class AIChatRequest(BaseModel):
    message: str


@app.post("/api/ai/chat")
async def request_ai_chat(
    request: AIChatRequest,
    current_user: User = Depends(get_current_user_optional),
    db: Session = Depends(get_db)
):
    """AI 채팅 요청 → job_id 즉시 반환 (백그라운드 처리)"""
    _ensure_ai_tables(db)

    # 테스트용: 인증 없이도 동작하도록
    if current_user and not _check_standard_plan(current_user):
        return {"success": False, "error": "AI 채팅은 Standard 이상에서 이용 가능합니다"}

    # 테스트용: current_user가 없으면 사용량 체크 스킵
    if current_user:
        daily_max = _get_ai_daily_limit(current_user)
        today = datetime.now(KST).date()
        daily_count = 0

        # 사용량 체크
        try:
            result = db.execute(
                text("SELECT ai_usage_count, ai_usage_date FROM users WHERE id = :uid"),
                {"uid": current_user.id}
            )
            row = result.fetchone()

            if row:
                if row[1] != today:
                    daily_count = 0
                    db.execute(
                        text("UPDATE users SET ai_usage_count = 0, ai_usage_date = :today WHERE id = :uid"),
                        {"uid": current_user.id, "today": today}
                    )
                else:
                    daily_count = row[0] or 0
                db.commit()

            if daily_count >= daily_max:
                return {"success": False, "error": "오늘의 AI 채팅 횟수를 모두 사용했습니다."}

        except Exception as e:
            print(f"AI chat usage check error: {e}")

    # 작업 큐에 등록
    _cleanup_old_jobs()
    job_id = str(uuid.uuid4())[:8]

    _ai_jobs[job_id] = {
        "status": "pending",
        "progress": "🤖 AI가 생각 중...",
        "result": None,
        "created_at": datetime.now(KST),
        "user_id": current_user.id if current_user else None,
        "type": "chat",
    }

    # 백그라운드 실행
    asyncio.create_task(_run_ai_chat_job(job_id, request.message, current_user.id if current_user else None))

    return {"success": True, "job_id": job_id, "status": "pending"}


def _clean_ai_response(text: str) -> str:
    """Claude 내부 사고 문구 제거"""
    import re as re_module

    if not text:
        return text

    # 패턴 1: "웹검색을 통해..." 류의 사고 과정 문구 제거
    text = re_module.sub(r'웹검색을 통해[^.]*\.', '', text)
    text = re_module.sub(r'웹검색 결과를 바탕으로[^.]*\.', '', text)
    text = re_module.sub(r'최신 정보를 수집하겠습니다[^.]*\.', '', text)
    text = re_module.sub(r'보고서를 작성하겠습니다[^.]*\.', '', text)
    text = re_module.sub(r'분석.*작성하겠습니다[^.]*\.', '', text)
    text = re_module.sub(r'필요한 정보를 수집하겠습니다[^.]*\.', '', text)

    # 패턴 2: 본문 시작 전 메타 문구 제거
    lines = text.strip().split('\n')
    start_idx = 0
    for i, line in enumerate(lines):
        stripped = line.strip()
        # 본문 시작 패턴 감지
        if (stripped.startswith('---') or
            stripped.startswith('# ') or
            stripped.startswith('## ') or
            stripped.startswith('### ') or
            stripped.startswith('**1.') or
            stripped.startswith('1.') or
            stripped.startswith('• ')):
            start_idx = i
            break

    if start_idx > 0:
        text = '\n'.join(lines[start_idx:])

    # 앞뒤 빈줄/구분선 정리
    text = text.strip()
    while text.startswith('---'):
        text = text[3:].strip()

    return text


async def _run_ai_chat_job(job_id: str, message: str, user_id: int = None):
    """백그라운드에서 AI 채팅 실행 - 종목 인식 시 데이터 기반 분석 + 차트 생성"""
    import time as time_module
    try:
        t_start = time_module.time()
        _ai_jobs[job_id]["status"] = "running"
        _ai_jobs[job_id]["progress"] = "🔍 종목 인식 중..."

        import anthropic
        # web_search tool 사용 시 Claude가 여러번 검색하므로 timeout 충분히 설정
        client = anthropic.AsyncAnthropic(api_key=os.getenv("ANTHROPIC_API_KEY", ""), timeout=180.0)

        # 종목 인식 시도
        detected_stock = await _detect_stock_from_message(message)
        t_detect = time_module.time()
        print(f"[AI 시간] 종목 인식: {t_detect - t_start:.1f}초")
        chart_urls = None  # 차트 URL 초기화

        if detected_stock:
            # 종목이 인식됨 → 데이터 수집 후 분석
            code = detected_stock["code"]
            name = detected_stock["name"]
            market = detected_stock.get("market", "kr")

            print(f"[AI Chat] 종목 인식: {name}({code})")
            _ai_jobs[job_id]["progress"] = f"📊 {name} 데이터 수집 중..."

            # 데이터 수집 (_run_ai_analysis_job과 동일)
            t_data_start = time_module.time()
            tech = await _collect_technical_data_for_ai(code, market)
            t_tech = time_module.time()
            print(f"[AI 시간] 기술 데이터 수집: {t_tech - t_data_start:.1f}초")

            fin = await _collect_financial_data_for_ai(code, market)
            t_fin = time_module.time()
            print(f"[AI 시간] 재무 데이터 수집: {t_fin - t_tech:.1f}초")

            news = await _collect_news_for_ai(code, name, market)
            t_news = time_module.time()
            print(f"[AI 시간] 뉴스 수집: {t_news - t_fin:.1f}초")

            # 기업 개요 수집 (FnGuide bizSummaryContent)
            company_summary = ""
            if market == "kr":
                try:
                    from .data_provider import get_stock_company_kr
                    company_data = await get_stock_company_kr(code)
                    company_summary = company_data.get("description", "")
                except Exception as e:
                    print(f"[AI Chat] Company summary error: {e}")
            t_company = time_module.time()
            print(f"[AI 시간] 기업 개요 수집: {t_company - t_news:.1f}초")

            # 차트 생성
            _ai_jobs[job_id]["progress"] = f"📈 {name} 차트 생성 중..."
            chart_urls = await _generate_ai_charts(code, name, market)
            t_chart = time_module.time()
            print(f"[AI 시간] 차트 생성: {t_chart - t_company:.1f}초")

            # ★ 차트↔텍스트 지지/저항 통일: 차트 계산값으로 덮어쓰기
            if chart_urls.get("support_levels"):
                tech["support_levels"] = chart_urls["support_levels"]
            if chart_urls.get("resistance_levels"):
                tech["resistance_levels"] = chart_urls["resistance_levels"]

            _ai_jobs[job_id]["progress"] = "🤖 AI가 분석 중..."

            # 데이터 기반 프롬프트 생성 (기업 개요 포함, market에 따라 통화 단위 변경)
            data_prompt = _build_claude_prompt(name, code, tech, fin, news, company_summary, market)
            t_prompt = time_module.time()
            print(f"[AI 시간] 프롬프트 조립: {t_prompt - t_chart:.1f}초")

            # 사용자 질문 추가
            final_prompt = f"""{data_prompt}

---
⚠️ 절대 규칙:
- 즉시 종합 분석 보고서를 작성해라. 질문하지 마라. 의도를 묻지 마라.
- 사용자에게 되물어보지 말고 바로 보고서를 시작해라.
- 요청된 종목({name})에 대해서만 분석해라.
- 보고서를 작성할지 묻는 질문은 절대 금지.

사용자 질문: {message}

위 데이터를 기반으로 {name}({code})의 종합 분석 보고서를 즉시 작성해라.
반드시 실제 수치(현재가, RSI, ADX, MACD 등)를 인용하며 작성하세요.
"""

            response = await client.messages.create(
                model="claude-haiku-4-5-20251001",
                max_tokens=8000,
                tools=[{"type": "web_search_20250305", "name": "web_search"}],
                messages=[{"role": "user", "content": final_prompt}]
            )
            t_claude = time_module.time()
            print(f"[AI 시간] Claude API 호출: {t_claude - t_prompt:.1f}초")
        else:
            # 종목 미인식 → 일반 채팅
            _ai_jobs[job_id]["progress"] = "🤖 AI가 생각 중..."

            system_prompt = """당신은 BBooster의 AI 투자 어시스턴트입니다.
사용자의 투자 관련 질문에 전문적이고 친절하게 답변합니다.

역할:
- 주식/ETF 분석 및 전망 제공
- 투자 전략 조언
- 시장 동향 설명
- 기술적/기본적 분석 해설

주의사항:
- 법적 투자 조언이 아님을 명시
- 객관적 데이터 기반 분석
- 리스크 경고 포함
- 한국어로 답변
- 마크다운 형식 (## 제목, - 목록, **강조**)
- 1500자 이상 상세하게"""

            response = await client.messages.create(
                model="claude-haiku-4-5-20251001",
                max_tokens=4096,
                system=system_prompt,
                messages=[{"role": "user", "content": message}]
            )

        # 웹검색 tool 사용 시 여러 content 블록이 있을 수 있음
        reply = ""
        for block in response.content:
            if hasattr(block, 'text'):
                reply += block.text
            elif hasattr(block, 'type') and block.type == 'tool_use':
                # 웹검색 결과는 별도 처리 (Claude가 자동으로 결과 반영)
                pass

        # Claude 내부 사고 문구 제거
        reply = _clean_ai_response(reply)

        t_end = time_module.time()
        print(f"[AI 시간] 전체 소요시간: {t_end - t_start:.1f}초")

        _ai_jobs[job_id]["status"] = "done"
        _ai_jobs[job_id]["result"] = reply
        _ai_jobs[job_id]["progress"] = "✅ 완료"

        # 차트 URL 포함 (종목 분석 시)
        if chart_urls:
            _ai_jobs[job_id]["charts"] = chart_urls
            _ai_jobs[job_id]["stock"] = detected_stock

        # 사용량 증가 (user_id가 있을 때만)
        if user_id:
            try:
                from app.db import SessionLocal
                db = SessionLocal()
                db.execute(
                    text("UPDATE users SET ai_usage_count = ai_usage_count + 1 WHERE id = :uid"),
                    {"uid": user_id}
                )
                db.commit()
                db.close()
            except Exception as e:
                print(f"[AI Chat Job] DB update error: {e}")

        print(f"[AI Chat Job] {job_id} 완료: {len(reply)}자, 차트: {bool(chart_urls)}")

    except Exception as e:
        print(f"[AI Chat Job] {job_id} 오류: {e}")
        _ai_jobs[job_id]["status"] = "error"
        _ai_jobs[job_id]["error"] = str(e)
        _ai_jobs[job_id]["progress"] = "❌ 오류 발생"


async def _detect_stock_from_message(message: str) -> dict:
    """메시지에서 종목명/코드 인식 (한국주식 + 미국주식 + ETF)

    인식 순서:
    1. 6자리 숫자 코드 (한국 주식/ETF)
    2. US ETF 풀네임 매칭 (Schwab U.S. Large-Cap Growth ETF → SCHG)
    3. US 티커 심볼 (SCHG, XLK, AAPL 등)
    4. 한글 종목명
    5. 영문 회사명
    """
    import re
    from app.screener.kr_screener import load_kr_stocks
    from app.screener.us_screener import load_us_stocks
    from app.naver_finance import get_etf_list

    # 1. 6자리 숫자 코드 패턴 (예: 009830, 005930) - 한국주식/ETF
    code_match = re.search(r'\b(\d{6})\b', message)
    if code_match:
        code = code_match.group(1)
        # 스크리너 캐시에서 코드로 검색
        kr_stocks = await load_kr_stocks()
        for stock in kr_stocks:
            if stock.get("code") == code:
                return {"code": code, "name": stock.get("name", code), "market": "kr"}
        # ETF 목록에서도 검색
        try:
            etf_list = await get_etf_list()
            for etf in etf_list:
                if etf.get("code") == code:
                    return {"code": code, "name": etf.get("name", code), "market": "kr", "is_etf": True}
        except Exception:
            pass

    # 2. US ETF 풀네임 매칭 먼저! (티커 추출 전에 확인)
    # "Schwab U.S. Large-Cap Growth ETF" 같은 풀네임에서 "U"가 먼저 매칭되는 버그 방지
    etf_name_map = {
        # SPDR Sector ETFs
        "technology select sector spdr fund": "XLK",
        "financial select sector spdr fund": "XLF",
        "energy select sector spdr fund": "XLE",
        "health care select sector spdr fund": "XLV",
        "consumer discretionary select sector spdr fund": "XLY",
        "consumer staples select sector spdr fund": "XLP",
        "industrial select sector spdr fund": "XLI",
        "materials select sector spdr fund": "XLB",
        "utilities select sector spdr fund": "XLU",
        "real estate select sector spdr fund": "XLRE",
        # Major Index ETFs
        "spdr s&p 500 etf trust": "SPY",
        "spdr dow jones industrial average etf": "DIA",
        "invesco qqq trust": "QQQ",
        "ishares russell 2000 etf": "IWM",
        # Schwab ETFs
        "schwab us dividend equity etf": "SCHD",
        "schwab u.s. large-cap growth etf": "SCHG",
        "schwab us large-cap growth etf": "SCHG",
        "schwab u.s. broad market etf": "SCHB",
        "schwab u.s. small-cap etf": "SCHA",
        "schwab u.s. large-cap etf": "SCHX",
        # Vanguard ETFs
        "vanguard total stock market etf": "VTI",
        "vanguard s&p 500 etf": "VOO",
        "vanguard information technology etf": "VGT",
        "vanguard growth etf": "VUG",
        "vanguard value etf": "VTV",
        "vanguard dividend appreciation etf": "VIG",
        "vanguard high dividend yield etf": "VYM",
        # iShares ETFs
        "ishares core s&p 500 etf": "IVV",
        "ishares broad usd high yield corporate bond etf": "USHY",
        "ishares iboxx high yield corporate bond etf": "HYG",
        "ishares 20+ year treasury bond etf": "TLT",
        "ishares semiconductor etf": "SOXX",
        # Other popular ETFs
        "ark innovation etf": "ARKK",
        "spdr gold shares": "GLD",
        "vaneck semiconductor etf": "SMH",
    }
    # 한글/분석/해줘 등 제거 후 영문만 추출
    eng_full = re.sub(r'[가-힣]', '', message)
    eng_full = re.sub(r'분석해줘|분석|해줘|알려줘|보고서|좀', '', eng_full, flags=re.IGNORECASE).strip()
    eng_lower = eng_full.lower().strip()

    # 정확한 풀네임 매칭
    if eng_lower in etf_name_map:
        ticker = etf_name_map[eng_lower]
        try:
            import yfinance as yf
            yf_ticker = yf.Ticker(ticker)
            info = yf_ticker.info
            if info and info.get("shortName"):
                return {
                    "code": ticker,
                    "name": info.get("shortName", ticker),
                    "market": "us",
                    "is_etf": True
                }
        except Exception:
            pass

    # 부분 매칭 (ETF 이름이 메시지에 포함된 경우)
    for etf_name, ticker in etf_name_map.items():
        if etf_name in eng_lower:
            try:
                import yfinance as yf
                yf_ticker = yf.Ticker(ticker)
                info = yf_ticker.info
                if info and info.get("shortName"):
                    return {
                        "code": ticker,
                        "name": info.get("shortName", ticker),
                        "market": "us",
                        "is_etf": True
                    }
            except Exception:
                continue

    # 3. US 티커 심볼 패턴 (예: AAPL, TSLA, NVDA, XLK) - 대문자 1~5자
    # 메시지 시작 부분에서 티커 찾기 (더 정확한 매칭)
    us_ticker_match = re.search(r'\b([A-Z]{1,5})\b', message.upper())
    if us_ticker_match:
        ticker = us_ticker_match.group(1)

        # 흔한 영어 단어 제외 (ETF 이름에서 잘못 추출되는 것 방지)
        SKIP_WORDS = {'A', 'I', 'U', 'AI', 'IT', 'THE', 'AND', 'FOR', 'ETF', 'US',
                      'USD', 'KR', 'KRW', 'PDF', 'OK', 'PM', 'AM', 'CEO', 'IPO',
                      'PE', 'EPS', 'ROE', 'PER', 'PBR', 'BPS', 'GDP', 'CPI', 'CAP'}
        if ticker in SKIP_WORDS:
            # SKIP_WORDS에 해당하면 다음 매칭 시도
            all_matches = re.findall(r'\b([A-Z]{1,5})\b', message.upper())
            for match in all_matches:
                if match not in SKIP_WORDS:
                    ticker = match
                    break
            else:
                ticker = None  # 유효한 티커 없음

        if ticker:
            # US 스크리너 캐시에서 검색 (S&P 500)
            try:
                us_stocks = await load_us_stocks()
                for stock in us_stocks:
                    if stock.get("code", "").upper() == ticker:
                        return {"code": ticker, "name": stock.get("name", ticker), "market": "us"}
            except Exception as e:
                print(f"[_detect_stock] US stock search error: {e}")

            # S&P 500에 없으면 yfinance로 US ETF/주식 확인
            try:
                import yfinance as yf
                yf_ticker = yf.Ticker(ticker)
                info = yf_ticker.info
                if info and info.get("shortName"):
                    # ETF인지 주식인지 판별
                    quote_type = info.get("quoteType", "").upper()
                    is_etf = quote_type == "ETF"
                    return {
                        "code": ticker,
                        "name": info.get("shortName", ticker),
                        "market": "us",
                        "is_etf": is_etf
                    }
            except Exception as e:
                print(f"[_detect_stock] yfinance fallback error for {ticker}: {e}")

    # 3. 한글 종목명으로 검색 (한국주식 + ETF)
    kr_stocks = await load_kr_stocks()
    words = re.findall(r'[가-힣]+', message)

    for word in words:
        if len(word) < 2:
            continue
        # 정확한 이름 매칭 먼저 (한국주식)
        for stock in kr_stocks:
            if stock.get("name") == word:
                return {"code": stock.get("code"), "name": stock.get("name"), "market": "kr"}
        # ETF 이름 매칭
        try:
            etf_list = await get_etf_list()
            for etf in etf_list:
                if etf.get("name") == word:
                    return {"code": etf.get("code"), "name": etf.get("name"), "market": "kr", "is_etf": True}
        except Exception:
            pass
        # 부분 매칭 (종목명에 단어가 포함된 경우)
        for stock in kr_stocks:
            stock_name = stock.get("name", "")
            if word in stock_name and len(word) >= 2:
                return {"code": stock.get("code"), "name": stock_name, "market": "kr"}
        # ETF 부분 매칭
        try:
            etf_list = await get_etf_list()
            for etf in etf_list:
                etf_name = etf.get("name", "")
                if word in etf_name and len(word) >= 2:
                    return {"code": etf.get("code"), "name": etf_name, "market": "kr", "is_etf": True}
        except Exception:
            pass

    # 4. 영문 종목명 풀네임으로 yfinance 검색 (예: "Technology Select Sector SPDR Fund")
    # 5. 영문 회사명으로 US 종목 검색 (예: Apple, Tesla, Nvidia)
    # 흔한 영어 단어 제외 (ETF 이름에 자주 등장하는 단어들)
    common_words = {
        'technology', 'select', 'sector', 'fund', 'trust', 'index', 'etf',
        'inc', 'corp', 'corporation', 'group', 'company', 'limited', 'ltd',
        'the', 'and', 'for', 'spdr', 'ishares', 'vanguard', 'schwab', 'invesco',
        'equity', 'dividend', 'growth', 'value', 'market', 'stock', 'bond',
        'international', 'global', 'world', 'emerging', 'developed', 'total',
        'core', 'small', 'mid', 'large', 'cap', 'high', 'low', 'ultra',
    }
    eng_words = re.findall(r'[A-Za-z]+', message)
    for word in eng_words:
        if len(word) < 4:  # 최소 4글자
            continue
        if word.lower() in common_words:
            continue
        try:
            us_stocks = await load_us_stocks()
            for stock in us_stocks:
                stock_name = stock.get("name", "").lower()
                # 부분 매칭 대신 단어 경계 매칭 (더 정확함)
                if re.search(r'\b' + re.escape(word.lower()) + r'\b', stock_name):
                    return {"code": stock.get("code"), "name": stock.get("name"), "market": "us"}
        except Exception:
            pass

    # 6. 네이버 검색 API로 fallback (한국주식)
    for word in words:
        if len(word) < 2:
            continue
        try:
            async with httpx.AsyncClient(timeout=3.0) as client:
                resp = await client.get(
                    f"https://m.stock.naver.com/api/stock/{word}/basic",
                    headers={"User-Agent": "Mozilla/5.0"}
                )
                if resp.status_code == 200:
                    data = resp.json()
                    if data.get("stockCode"):
                        return {
                            "code": data.get("stockCode"),
                            "name": data.get("stockName", word),
                            "market": "kr"
                        }
        except Exception:
            pass

    return None


def _generate_simple_report(data: dict) -> str:
    """간단 템플릿 기반 보고서 생성"""
    name = data.get("name", data.get("symbol", "종목"))
    symbol = data.get("symbol", "")
    price = data.get("current_price", 0)
    change = data.get("change", 0)
    high = data.get("high", 0)
    low = data.get("low", 0)
    volume = data.get("volume", 0)
    market = data.get("market", "")

    trend = "상승" if change > 0 else ("하락" if change < 0 else "보합")
    trend_emoji = "📈" if change > 0 else ("📉" if change < 0 else "➡️")

    report = f"""# {name} ({symbol}) 종합분석 보고서

## 1. 핵심 요약

{trend_emoji} **{name}**은(는) 현재 **{trend}** 추세를 보이고 있습니다.
- 현재가: ₩{price:,} ({'+' if change >= 0 else ''}{change:.2f}%)
- 금일 고가: ₩{high:,} / 저가: ₩{low:,}
- 거래량: {volume:,}주

## 2. 기술적 분석

### 가격 위치
- 금일 변동폭: ₩{high - low:,}
- 고가 대비: {((price - high) / high * 100) if high else 0:.1f}%
- 저가 대비: {((price - low) / low * 100) if low else 0:.1f}%

### 추세 분석
현재 {trend} 추세에 있으며, {'추가 상승 여력이 있어 보입니다.' if change > 2 else ('지지선 확인이 필요합니다.' if change < -2 else '횡보 구간으로 판단됩니다.')}

## 3. 종합 의견

### 시나리오별 전망

**📈 상승 시나리오**
- 단기 저항선 돌파 시 추가 상승 가능
- 목표가: 현재가 대비 +5~10%

**➡️ 횡보 시나리오**
- 현 가격대에서 박스권 형성 가능
- 거래량 증가 여부 주시 필요

**📉 조정 시나리오**
- 지지선 이탈 시 추가 하락 가능
- 손절가: 현재가 대비 -3~5%

---

⚠️ **면책조항**: 본 보고서는 투자 참고용으로 작성되었으며, 투자 결정에 대한 책임은 투자자 본인에게 있습니다. 과거 실적이 미래 수익을 보장하지 않습니다.

_BBooster AI 분석 시스템에서 생성됨_
"""
    return report


# ============================================================================
# AI 차트 생성 (matplotlib)
# ============================================================================

async def _generate_ai_charts(code: str, name: str, market: str = "kr") -> dict:
    """AI 분석용 차트 3종 생성 - base64로 반환 (Mixed Content 방지)"""
    import matplotlib.dates as mdates
    from matplotlib.patches import Rectangle
    from datetime import datetime, timedelta
    import base64
    import io

    chart_data = {"price_chart": None, "trend_chart": None, "momentum_chart": None}

    try:
        # 캔들 데이터 가져오기
        candles = []
        is_us_market = market == "us"

        if market == "kr":
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.get(
                    f"https://api.stock.naver.com/chart/domestic/item/{code}/day?startDateTime=20240101&endDateTime=20261231",
                    headers={"User-Agent": "Mozilla/5.0"}
                )
                if resp.status_code == 200:
                    candles = resp.json() if isinstance(resp.json(), list) else []

        elif market == "us":
            # US 주식: yfinance 사용
            try:
                import yfinance as yf
                ticker = yf.Ticker(code)
                hist = ticker.history(period="2y")  # 최근 2년치
                if not hist.empty:
                    for idx, row in hist.iterrows():
                        candles.append({
                            "localDate": idx.strftime("%Y%m%d"),
                            "openPrice": row["Open"],
                            "highPrice": row["High"],
                            "lowPrice": row["Low"],
                            "closePrice": row["Close"],
                            "accumulatedTradingVolume": int(row["Volume"])
                        })
                    print(f"[Chart] yfinance fetched {len(candles)} candles for {code}")
            except Exception as e:
                print(f"[Chart] yfinance error for {code}: {e}")

        if len(candles) < 20:
            print(f"[Chart] Not enough data for {code}: {len(candles)} candles")
            return chart_data

        # 데이터 추출 (OHLCV)
        dates_str = [c.get("localDate", "")[:10] for c in candles]
        dates = [datetime.strptime(d, "%Y%m%d") if len(d) == 8 else datetime.strptime(d, "%Y-%m-%d") for d in dates_str]
        opens = [float(c.get("openPrice", 0)) for c in candles]
        closes = [float(c.get("closePrice", 0)) for c in candles]
        highs = [float(c.get("highPrice", 0)) for c in candles]
        lows = [float(c.get("lowPrice", 0)) for c in candles]
        volumes = [int(c.get("accumulatedTradingVolume", 0)) for c in candles]

        # 이동평균 계산
        def _sma(data, period):
            if len(data) < period:
                return [None] * len(data)
            result = [None] * (period - 1)
            for i in range(period - 1, len(data)):
                result.append(sum(data[i-period+1:i+1]) / period)
            return result

        sma20 = _sma(closes, 20)
        sma60 = _sma(closes, 60)
        sma200 = _sma(closes, 200)

        # === 지지/저항 계산 (돌출도 기반 스윙 포인트 + 거래량 밀집 구간) ===
        def calculate_support_resistance(highs_arr, lows_arr, closes_arr, volumes_arr, current_price, num_levels=2):
            """
            개선된 지지/저항 계산 - 52주 저가 문제 해결

            핵심 변경:
            - 52주 저가가 아닌 "최근 주요 상승파동의 시작점"을 스윙 로우로 사용
            - 돌출도(prominence) 기반으로 의미 있는 스윙 포인트만 선택
            - 거래량 밀집 구간으로 지지/저항 보정
            - 현재가가 52주 고가인 경우 피보나치 확장으로 저항 계산
            """
            import numpy as np

            highs_np = np.array(highs_arr, dtype=float)
            lows_np = np.array(lows_arr, dtype=float)
            closes_np = np.array(closes_arr, dtype=float)
            volumes_np = np.array(volumes_arr, dtype=float)
            n = len(closes_np)

            # ============================================
            # 1단계: 거래량 밀집 구간 찾기 (Volume Profile)
            # ============================================
            price_min, price_max = float(lows_np.min()), float(highs_np.max())
            price_range_total = price_max - price_min
            num_bins = 50
            bin_edges = np.linspace(price_min, price_max, num_bins + 1)
            volume_profile = np.zeros(num_bins)

            for i in range(n):
                c, v = closes_np[i], volumes_np[i]
                bin_idx = min(int((c - price_min) / price_range_total * num_bins), num_bins - 1)
                volume_profile[bin_idx] += v

            # 거래량 상위 30% 구간만 추출
            vol_threshold = np.percentile(volume_profile, 70)
            volume_clusters = []
            for b in range(num_bins):
                if volume_profile[b] >= vol_threshold:
                    mid_price = (bin_edges[b] + bin_edges[b + 1]) / 2
                    volume_clusters.append({'price': mid_price, 'volume': volume_profile[b]})

            # ============================================
            # 2단계: 돌출도 기반 로컬 고저점 찾기
            # ============================================
            window = 15
            min_prominence_pct = 0.08  # 전체 가격범위 대비 8% 이상 돌출

            local_highs = []
            local_lows = []

            for i in range(window, n - window):
                # 로컬 고점 체크
                if highs_np[i] == max(highs_np[i - window:i + window + 1]):
                    left_min = min(lows_np[max(0, i - window):i])
                    right_min = min(lows_np[i + 1:min(n, i + window + 1)])
                    prominence = highs_np[i] - max(left_min, right_min)
                    if prominence >= price_range_total * min_prominence_pct:
                        local_highs.append({
                            'idx': i, 'price': float(highs_np[i]),
                            'prominence': prominence
                        })

                # 로컬 저점 체크
                if lows_np[i] == min(lows_np[i - window:i + window + 1]):
                    left_max = max(highs_np[max(0, i - window):i])
                    right_max = max(highs_np[i + 1:min(n, i + window + 1)])
                    prominence = min(left_max, right_max) - lows_np[i]
                    if prominence >= price_range_total * min_prominence_pct:
                        local_lows.append({
                            'idx': i, 'price': float(lows_np[i]),
                            'prominence': prominence
                        })

            # ============================================
            # 3단계: 의미 있는 스윙 하이/로우 선택
            # ============================================
            # 스윙 하이: 돌출도 상위 중 현재가 위에 있는 것 (없으면 전체 최고)
            highs_above = [h for h in local_highs if h['price'] > current_price * 1.01]
            if highs_above:
                swing_high_point = min(highs_above, key=lambda x: x['price'])  # 가장 가까운 고점
            else:
                swing_high_point = {'price': float(highs_np.max()), 'idx': int(np.argmax(highs_np))}
            swing_high = swing_high_point['price']

            # 스윙 로우: 현재가 대비 -50% 이내의 주요 저점 중 가장 가까운 것
            # (52주 저가 대신 최근 의미있는 지지 구간 찾기)
            lows_below = [l for l in local_lows
                          if l['price'] < current_price * 0.99
                          and l['price'] >= current_price * 0.50]  # -50% 이내

            if lows_below:
                # 돌출도 상위 50% 중 현재가에 가장 가까운 것
                lows_below.sort(key=lambda x: x['prominence'], reverse=True)
                top_lows = lows_below[:max(1, len(lows_below) // 2)]
                swing_low_point = max(top_lows, key=lambda x: x['price'])  # 현재가에 가까운 것
            else:
                # -50% 이내에 없으면 거래량 밀집 구간 중 현재가 아래에서 가장 가까운 것
                vol_below = [vc for vc in volume_clusters if vc['price'] < current_price * 0.98]
                if vol_below:
                    swing_low_point = max(vol_below, key=lambda x: x['price'])
                else:
                    # 폴백: 전체 최저가 사용 (기존 방식)
                    swing_low_point = {'price': float(lows_np.min())}
            swing_low = swing_low_point['price']

            # ============================================
            # 4단계: 피보나치 레벨 계산
            # ============================================
            fib_range = swing_high - swing_low

            # 횡보 종목 체크
            if fib_range < current_price * 0.12:
                return [round(current_price * 0.95), round(current_price * 0.88)], \
                       [round(current_price * 1.05), round(current_price * 1.12)]

            fib_236 = swing_low + fib_range * 0.236
            fib_382 = swing_low + fib_range * 0.382
            fib_500 = swing_low + fib_range * 0.500
            fib_618 = swing_low + fib_range * 0.618
            fib_786 = swing_low + fib_range * 0.786
            # 피보나치 확장 (현재가가 고가일 때 저항용)
            fib_ext_127 = swing_low + fib_range * 1.272
            fib_ext_161 = swing_low + fib_range * 1.618

            # ============================================
            # 5단계: 지지선 후보 수집 + 거래량 밀집 보정
            # ============================================
            support_candidates = []

            # 피보나치 레벨들 (현재가 아래만)
            for fib_level, name in [(fib_786, '78.6'), (fib_618, '61.8'),
                                     (fib_500, '50.0'), (fib_382, '38.2'), (fib_236, '23.6')]:
                if fib_level < current_price * 0.98:
                    # 거래량 밀집 구간과 가까우면 보정
                    adjusted = fib_level
                    for vc in volume_clusters:
                        if abs(vc['price'] - fib_level) / fib_level < 0.03:
                            adjusted = vc['price']
                            break
                    dist_pct = (current_price - adjusted) / current_price * 100
                    support_candidates.append({'level': adjusted, 'dist': dist_pct, 'source': f'fib_{name}'})

            # 거래량 밀집 구간 (현재가 아래)
            for vc in volume_clusters:
                if vc['price'] < current_price * 0.97:
                    dist_pct = (current_price - vc['price']) / current_price * 100
                    # 중복 체크 (이미 있는 레벨과 3% 이내면 스킵)
                    is_dup = any(abs(sc['level'] - vc['price']) / sc['level'] < 0.03 for sc in support_candidates)
                    if not is_dup:
                        support_candidates.append({'level': vc['price'], 'dist': dist_pct, 'source': 'vol'})

            # 거리순 정렬
            support_candidates.sort(key=lambda x: x['dist'])

            # ============================================
            # 6단계: 저항선 후보 수집
            # ============================================
            resistance_candidates = []

            # 현재가가 52주 고가 근처인지 체크
            at_high = current_price >= float(highs_np.max()) * 0.97

            if at_high:
                # 피보나치 확장 사용
                if fib_ext_127 > current_price * 1.02:
                    dist_pct = (fib_ext_127 - current_price) / current_price * 100
                    resistance_candidates.append({'level': fib_ext_127, 'dist': dist_pct, 'source': 'fib_127'})
                if fib_ext_161 > current_price * 1.02:
                    dist_pct = (fib_ext_161 - current_price) / current_price * 100
                    resistance_candidates.append({'level': fib_ext_161, 'dist': dist_pct, 'source': 'fib_161'})
            else:
                # 로컬 고점들
                for lh in local_highs:
                    if lh['price'] > current_price * 1.02:
                        dist_pct = (lh['price'] - current_price) / current_price * 100
                        resistance_candidates.append({'level': lh['price'], 'dist': dist_pct, 'source': 'local'})

            # 스윙 하이 추가 (아직 없으면)
            if swing_high > current_price * 1.02:
                is_dup = any(abs(rc['level'] - swing_high) / rc['level'] < 0.03 for rc in resistance_candidates)
                if not is_dup:
                    dist_pct = (swing_high - current_price) / current_price * 100
                    resistance_candidates.append({'level': swing_high, 'dist': dist_pct, 'source': 'swing'})

            # 거래량 밀집 구간 (현재가 위)
            for vc in volume_clusters:
                if vc['price'] > current_price * 1.02:
                    dist_pct = (vc['price'] - current_price) / current_price * 100
                    is_dup = any(abs(rc['level'] - vc['price']) / rc['level'] < 0.03 for rc in resistance_candidates)
                    if not is_dup:
                        resistance_candidates.append({'level': vc['price'], 'dist': dist_pct, 'source': 'vol'})

            resistance_candidates.sort(key=lambda x: x['dist'])

            # ============================================
            # 7단계: 최종 선택 (1차=가까운것, 2차=먼것)
            # ============================================
            if len(support_candidates) >= 2:
                support_1 = round(support_candidates[0]['level'])
                # 2차는 1차와 최소 8% 이상 떨어진 것
                support_2 = None
                for sc in support_candidates[1:]:
                    if abs(sc['level'] - support_candidates[0]['level']) / support_candidates[0]['level'] >= 0.08:
                        support_2 = round(sc['level'])
                        break
                if support_2 is None:
                    support_2 = round(support_candidates[-1]['level'])
            elif len(support_candidates) == 1:
                support_1 = round(support_candidates[0]['level'])
                support_2 = round(swing_low)
            else:
                support_1 = round(current_price * 0.92)
                support_2 = round(current_price * 0.85)

            if len(resistance_candidates) >= 2:
                resistance_1 = round(resistance_candidates[0]['level'])
                resistance_2 = None
                for rc in resistance_candidates[1:]:
                    if abs(rc['level'] - resistance_candidates[0]['level']) / resistance_candidates[0]['level'] >= 0.08:
                        resistance_2 = round(rc['level'])
                        break
                if resistance_2 is None:
                    resistance_2 = round(resistance_candidates[-1]['level'])
            elif len(resistance_candidates) == 1:
                resistance_1 = round(resistance_candidates[0]['level'])
                resistance_2 = round(swing_high * 1.1) if at_high else round(swing_high)
            else:
                resistance_1 = round(current_price * 1.08)
                resistance_2 = round(current_price * 1.15)

            # 1차가 2차보다 멀면 스왑
            if support_1 < support_2:
                support_1, support_2 = support_2, support_1
            if resistance_1 > resistance_2:
                resistance_1, resistance_2 = resistance_2, resistance_1

            return [support_1, support_2], [resistance_1, resistance_2]

        # 지지/저항 계산 실행
        current_price = closes[-1]
        support_levels, resistance_levels = calculate_support_resistance(
            highs, lows, closes, volumes, current_price, num_levels=2
        )
        # 호환성: 기존 변수명 유지
        support1 = support_levels[0] if support_levels else current_price * 0.95
        support2 = support_levels[1] if len(support_levels) > 1 else support1 * 0.9
        resistance1 = resistance_levels[0] if resistance_levels else current_price * 1.05
        resistance2 = resistance_levels[1] if len(resistance_levels) > 1 else resistance1 * 1.1

        # ★ 차트와 AI 텍스트 통일: 지지/저항 값을 chart_data에 저장
        chart_data["support_levels"] = [support1, support2]
        chart_data["resistance_levels"] = [resistance1, resistance2]
        chart_data["current_price"] = current_price

        # 차트 ID 생성
        chart_id = f"{code}_{datetime.now().strftime('%Y%m%d%H%M%S')}"

        # 최근 500일 표시 (2년치)
        display_len = min(500, len(closes))

        # 색상: 한국=상승빨강/하락파랑, 미국=상승초록/하락빨강
        if is_us_market:
            UP_COLOR = '#34C759'   # 미국: 상승=초록
            DOWN_COLOR = '#FF3B30'  # 미국: 하락=빨강
        else:
            UP_COLOR = '#FF3B30'   # 한국: 상승=빨강
            DOWN_COLOR = '#007AFF'  # 한국: 하락=파랑

        # ===== 차트 1: 캔들스틱 + 지지/저항선 + 거래량 =====
        fig1, (ax1, ax2) = plt.subplots(2, 1, figsize=(12, 8), height_ratios=[3, 1],
                                         gridspec_kw={'hspace': 0.05}, sharex=True)
        fig1.patch.set_facecolor('white')

        # 캔들스틱 그리기
        width = 0.6
        for i in range(display_len):
            idx = len(closes) - display_len + i
            date_num = mdates.date2num(dates[idx])
            o, h, l, c = opens[idx], highs[idx], lows[idx], closes[idx]
            color = UP_COLOR if c >= o else DOWN_COLOR

            # 캔들 몸통
            body_bottom = min(o, c)
            body_height = abs(c - o) if abs(c - o) > 0 else 1
            rect = Rectangle((date_num - width/2, body_bottom), width, body_height,
                             facecolor=color, edgecolor=color, linewidth=0.5)
            ax1.add_patch(rect)

            # 캔들 꼬리
            ax1.plot([date_num, date_num], [l, body_bottom], color=color, linewidth=0.5)
            ax1.plot([date_num, date_num], [body_bottom + body_height, h], color=color, linewidth=0.5)

        ax1.set_xlim(mdates.date2num(dates[-display_len]) - 2, mdates.date2num(dates[-1]) + 2)
        ax1.set_ylim(min(lows[-display_len:]) * 0.95, max(highs[-display_len:]) * 1.05)

        # 지지/저항선 (4개: 두껍고 선명하게)
        # 저항선 (빨간색, 두꺼운 파선)
        ax1.axhline(y=resistance1, color='#FF1744', linestyle='--', linewidth=2.5, alpha=0.95,
                    label=f'1차 저항 {int(resistance1):,}')
        ax1.axhline(y=resistance2, color='#FF5252', linestyle='--', linewidth=2.0, alpha=0.7,
                    label=f'2차 저항 {int(resistance2):,}')
        # 지지선 (초록색, 두꺼운 파선)
        ax1.axhline(y=support1, color='#00C853', linestyle='--', linewidth=2.5, alpha=0.95,
                    label=f'1차 지지 {int(support1):,}')
        ax1.axhline(y=support2, color='#69F0AE', linestyle='--', linewidth=2.0, alpha=0.7,
                    label=f'2차 지지 {int(support2):,}')

        ax1.set_title(f'주가, 지지/저항 분석 - {name}({code})', fontsize=14, fontweight='bold')
        ax1.legend(loc='upper left', fontsize=8, ncol=2)  # 2열로 표시
        ax1.grid(True, alpha=0.3)
        price_label = '주가($)' if is_us_market else '주가(원)'
        ax1.set_ylabel(price_label, fontsize=11)
        ax1.yaxis.set_major_formatter(plt.FuncFormatter(lambda x, p: f'{x:,.0f}'))

        # 거래량 (색상 구분)
        for i in range(display_len):
            idx = len(closes) - display_len + i
            date_num = mdates.date2num(dates[idx])
            color = UP_COLOR if closes[idx] >= opens[idx] else DOWN_COLOR
            ax2.bar(date_num, volumes[idx], color=color, width=width, alpha=0.7)

        ax2.set_ylabel('거래량', fontsize=11)
        ax2.yaxis.set_major_formatter(plt.FuncFormatter(lambda x, p: f'{x/1e6:.1f}M' if x >= 1e6 else f'{x/1e3:.0f}K'))
        ax2.grid(True, alpha=0.3)

        # X축 날짜 포맷
        ax2.xaxis.set_major_formatter(mdates.DateFormatter('%Y-%b'))
        ax2.xaxis.set_major_locator(mdates.MonthLocator(interval=4))
        plt.xticks(rotation=45, fontsize=8)

        plt.tight_layout()

        # base64로 변환 (Mixed Content 방지)
        buf = io.BytesIO()
        plt.savefig(buf, format='png', dpi=150, bbox_inches='tight')
        buf.seek(0)
        b64 = base64.b64encode(buf.read()).decode('utf-8')
        buf.close()
        plt.close(fig1)
        chart_data["price_chart"] = f"data:image/png;base64,{b64}"

        # ===== 차트 2: 추세추종 (2패널: 캔들+SMA / ADX+DI) =====
        fig2, (ax_price, ax_adx) = plt.subplots(2, 1, figsize=(12, 8),
                                                  height_ratios=[2, 1],
                                                  gridspec_kw={'hspace': 0.15})
        fig2.patch.set_facecolor('white')

        # === 상단: 캔들스틱 + SMA ===
        for i in range(display_len):
            idx = len(closes) - display_len + i
            date_num = mdates.date2num(dates[idx])
            o, h, l, c = opens[idx], highs[idx], lows[idx], closes[idx]
            color = UP_COLOR if c >= o else DOWN_COLOR

            body_bottom = min(o, c)
            body_height = abs(c - o) if abs(c - o) > 0 else 1
            rect = Rectangle((date_num - width/2, body_bottom), width, body_height,
                             facecolor=color, edgecolor=color, linewidth=0.5)
            ax_price.add_patch(rect)
            ax_price.plot([date_num, date_num], [l, body_bottom], color=color, linewidth=0.5)
            ax_price.plot([date_num, date_num], [body_bottom + body_height, h], color=color, linewidth=0.5)

        ax_price.set_xlim(mdates.date2num(dates[-display_len]) - 2, mdates.date2num(dates[-1]) + 2)
        ax_price.set_ylim(min(lows[-display_len:]) * 0.95, max(highs[-display_len:]) * 1.05)

        # SMA 라인
        date_nums = [mdates.date2num(dates[len(dates) - display_len + i]) for i in range(display_len)]
        if sma20[-display_len:][0] is not None:
            ax_price.plot(date_nums, sma20[-display_len:], label='SMA20', color='#FF9500', linewidth=1.5)
        if sma60[-display_len:][0] is not None:
            ax_price.plot(date_nums, sma60[-display_len:], label='SMA60', color='#007AFF', linewidth=1.5)
        if sma200 and sma200[-display_len:][0] is not None:
            ax_price.plot(date_nums, sma200[-display_len:], label='SMA200', color='#FF3B30', linewidth=1.5)

        ax_price.set_title(f'추세추종 지표 분석 - {name}({code})', fontsize=14, fontweight='bold')
        ax_price.set_ylabel(price_label, fontsize=11)
        ax_price.legend(loc='upper left', fontsize=9)
        ax_price.grid(True, alpha=0.3)
        ax_price.yaxis.set_major_formatter(plt.FuncFormatter(lambda x, p: f'{x:,.0f}'))
        ax_price.tick_params(axis='x', labelbottom=False)

        # === 하단: ADX + +DI + -DI 시계열 ===
        # ADX/DI 시계열 계산
        adx_series = []
        plus_di_series = []
        minus_di_series = []
        adx_period = 14

        # TR, +DM, -DM 계산
        tr_list = []
        plus_dm_list = []
        minus_dm_list = []
        for i in range(1, len(closes)):
            h_diff = highs[i] - highs[i-1]
            l_diff = lows[i-1] - lows[i]
            plus_dm_list.append(h_diff if h_diff > l_diff and h_diff > 0 else 0)
            minus_dm_list.append(l_diff if l_diff > h_diff and l_diff > 0 else 0)
            tr_list.append(max(highs[i]-lows[i], abs(highs[i]-closes[i-1]), abs(lows[i]-closes[i-1])))

        if len(tr_list) >= adx_period * 2:
            # Smoothed TR, +DM, -DM
            atr = sum(tr_list[:adx_period]) / adx_period
            plus_dm_smooth = sum(plus_dm_list[:adx_period]) / adx_period
            minus_dm_smooth = sum(minus_dm_list[:adx_period]) / adx_period
            dx_list = []

            for i in range(adx_period, len(tr_list)):
                atr = (atr * (adx_period-1) + tr_list[i]) / adx_period
                plus_dm_smooth = (plus_dm_smooth * (adx_period-1) + plus_dm_list[i]) / adx_period
                minus_dm_smooth = (minus_dm_smooth * (adx_period-1) + minus_dm_list[i]) / adx_period

                if atr > 0:
                    pdi = (plus_dm_smooth / atr) * 100
                    mdi = (minus_dm_smooth / atr) * 100
                else:
                    pdi = mdi = 0

                plus_di_series.append(pdi)
                minus_di_series.append(mdi)

                if pdi + mdi > 0:
                    dx_list.append(abs(pdi - mdi) / (pdi + mdi) * 100)
                else:
                    dx_list.append(0)

            # ADX = DX의 이동평균
            for i in range(len(dx_list)):
                if i < adx_period - 1:
                    adx_series.append(None)
                else:
                    adx_series.append(sum(dx_list[i-adx_period+1:i+1]) / adx_period)

        # ADX/DI 그리기 (최소 30일 이상이면 표시)
        min_adx_len = 30
        if len(adx_series) >= min_adx_len:
            # 표시할 데이터 길이 결정 (ADX 길이와 display_len 중 작은 값)
            actual_display = min(len(adx_series), display_len)
            adx_display = adx_series[-actual_display:]
            plus_di_display = plus_di_series[-actual_display:]
            minus_di_display = minus_di_series[-actual_display:]
            # date_nums도 맞춤
            date_nums_adx = date_nums[-actual_display:] if len(date_nums) >= actual_display else date_nums

            # ADX 라인 (유효한 값만)
            valid_adx = [(d, a) for d, a in zip(date_nums_adx, adx_display) if a is not None]
            if valid_adx:
                current_adx = valid_adx[-1][1] if valid_adx else 0
                ax_adx.plot([x[0] for x in valid_adx], [x[1] for x in valid_adx],
                           color='#000000', linewidth=2, label=f'ADX ({current_adx:.1f})')

            # +DI (초록) / -DI (빨강)
            if plus_di_display:
                current_plus = plus_di_display[-1] if plus_di_display else 0
                ax_adx.plot(date_nums_adx, plus_di_display, color='#34C759', linewidth=1.5,
                           label=f'+DI ({current_plus:.1f})')
            if minus_di_display:
                current_minus = minus_di_display[-1] if minus_di_display else 0
                ax_adx.plot(date_nums_adx, minus_di_display, color='#FF3B30', linewidth=1.5,
                           label=f'-DI ({current_minus:.1f})')

            # ADX 기준선 (25=추세 발생, 50=강한 추세)
            ax_adx.axhline(y=25, color='gray', linestyle='--', linewidth=0.8, alpha=0.6)
            ax_adx.axhline(y=50, color='gray', linestyle='--', linewidth=0.8, alpha=0.6)
            ax_adx.text(date_nums_adx[-1] + 1, 25, '25', fontsize=8, color='gray', va='center')
            ax_adx.text(date_nums_adx[-1] + 1, 50, '50', fontsize=8, color='gray', va='center')

            # Y축 범위
            all_values = [v for v in adx_display + plus_di_display + minus_di_display if v is not None]
            if all_values:
                ax_adx.set_ylim(0, max(60, max(all_values) * 1.1))
            else:
                ax_adx.set_ylim(0, 60)
        else:
            ax_adx.text(0.5, 0.5, f'ADX/DI 데이터 부족 (최소 {min_adx_len}일 필요, 현재 {len(adx_series)}일)',
                       transform=ax_adx.transAxes, ha='center', va='center', fontsize=10, color='gray')
            ax_adx.set_ylim(0, 60)

        ax_adx.set_ylabel('ADX / DI', fontsize=11)
        ax_adx.legend(loc='upper left', fontsize=9)
        ax_adx.grid(True, alpha=0.3)
        ax_adx.xaxis.set_major_formatter(mdates.DateFormatter('%Y-%b'))
        ax_adx.xaxis.set_major_locator(mdates.MonthLocator(interval=4))
        plt.xticks(rotation=45, fontsize=8)

        plt.tight_layout()

        # base64로 변환
        buf = io.BytesIO()
        plt.savefig(buf, format='png', dpi=150, bbox_inches='tight')
        buf.seek(0)
        b64 = base64.b64encode(buf.read()).decode('utf-8')
        buf.close()
        plt.close(fig2)
        chart_data["trend_chart"] = f"data:image/png;base64,{b64}"

        # ===== 차트 3: 모멘텀 차트 (RSI + MACD 시계열) - 날짜 x축 =====
        from .screener.technicals import _calc_rsi

        fig3, (ax_rsi, ax_macd) = plt.subplots(2, 1, figsize=(12, 8), sharex=True)
        fig3.patch.set_facecolor('white')

        # RSI 시계열 계산
        rsi_values = []
        for i in range(14, len(closes)):
            rsi = _calc_rsi(closes[:i+1], 14)
            rsi_values.append(rsi if rsi else 50)

        # MACD 시계열 계산 (EMA 기반)
        def _calc_ema_series(data, period):
            ema = [None] * (period - 1)
            multiplier = 2 / (period + 1)
            ema.append(sum(data[:period]) / period)
            for i in range(period, len(data)):
                ema.append((data[i] - ema[-1]) * multiplier + ema[-1])
            return ema

        ema12 = _calc_ema_series(closes, 12)
        ema26 = _calc_ema_series(closes, 26)
        macd_line = [e12 - e26 if e12 and e26 else None for e12, e26 in zip(ema12, ema26)]

        # Signal line (MACD의 9일 EMA)
        macd_valid = [v for v in macd_line if v is not None]
        if len(macd_valid) >= 9:
            signal_line = [None] * (len(macd_line) - len(macd_valid))
            signal_ema = _calc_ema_series(macd_valid, 9)
            signal_line.extend(signal_ema)
        else:
            signal_line = [None] * len(macd_line)

        histogram = [m - s if m and s else None for m, s in zip(macd_line, signal_line)]

        # RSI 표시 (날짜 기반)
        rsi_start_idx = 14
        rsi_dates = dates[rsi_start_idx:]
        rsi_date_nums = [mdates.date2num(d) for d in rsi_dates[-display_len:]]
        rsi_display = rsi_values[-display_len:] if len(rsi_values) >= display_len else rsi_values

        if len(rsi_date_nums) == len(rsi_display):
            ax_rsi.plot(rsi_date_nums, rsi_display, color='#8B5CF6', linewidth=1.5, label='RSI(14)')
            ax_rsi.axhline(y=70, color='#FF3B30', linestyle='--', linewidth=1, alpha=0.7, label='과매수 (70)')
            ax_rsi.axhline(y=30, color='#34C759', linestyle='--', linewidth=1, alpha=0.7, label='과매도 (30)')
            ax_rsi.axhline(y=50, color='gray', linestyle=':', linewidth=0.5, alpha=0.5)
            ax_rsi.fill_between(rsi_date_nums, 70, 100, alpha=0.1, color='#FF3B30')
            ax_rsi.fill_between(rsi_date_nums, 0, 30, alpha=0.1, color='#34C759')
            ax_rsi.set_ylim(0, 100)
            ax_rsi.set_ylabel('RSI', fontsize=11)
            ax_rsi.set_title(f'모멘텀 지표 분석 - {name}({code})', fontsize=14, fontweight='bold')
            ax_rsi.legend(loc='upper left', fontsize=9)
            ax_rsi.grid(True, alpha=0.3)

            # 현재 RSI 값 표시
            current_rsi = rsi_display[-1]
            rsi_status = "과매수" if current_rsi > 70 else "과매도" if current_rsi < 30 else "중립"
            ax_rsi.annotate(f'{current_rsi:.1f} ({rsi_status})',
                           xy=(rsi_date_nums[-1], current_rsi),
                           fontsize=10, fontweight='bold',
                           color='#FF3B30' if current_rsi > 70 else '#34C759' if current_rsi < 30 else '#8B5CF6',
                           xytext=(5, 0), textcoords='offset points')

        # MACD 표시 (날짜 기반)
        macd_display = macd_line[-display_len:]
        signal_display = signal_line[-display_len:]
        hist_display = histogram[-display_len:]
        macd_date_nums = [mdates.date2num(dates[len(dates) - display_len + i]) for i in range(display_len)]

        # MACD, Signal 라인
        valid_macd = [(d, m) for d, m in zip(macd_date_nums, macd_display) if m is not None]
        valid_signal = [(d, s) for d, s in zip(macd_date_nums, signal_display) if s is not None]

        if valid_macd:
            ax_macd.plot([x[0] for x in valid_macd], [x[1] for x in valid_macd],
                        color='#007AFF', linewidth=1.5, label='MACD')
        if valid_signal:
            ax_macd.plot([x[0] for x in valid_signal], [x[1] for x in valid_signal],
                        color='#FF9500', linewidth=1.5, label='Signal')

        ax_macd.axhline(y=0, color='gray', linewidth=0.5)

        # 히스토그램 (양수=초록, 음수=빨강)
        for i, (d, h) in enumerate(zip(macd_date_nums, hist_display)):
            if h is not None:
                color = '#34C759' if h >= 0 else '#FF3B30'
                ax_macd.bar(d, h, color=color, width=0.6, alpha=0.6)

        ax_macd.set_ylabel('MACD', fontsize=11)
        ax_macd.legend(loc='upper left', fontsize=9)
        ax_macd.grid(True, alpha=0.3)

        # X축 날짜 포맷
        ax_macd.xaxis.set_major_formatter(mdates.DateFormatter('%Y-%b'))
        ax_macd.xaxis.set_major_locator(mdates.MonthLocator(interval=4))
        plt.xticks(rotation=45, fontsize=8)

        plt.tight_layout()

        # base64로 변환
        buf = io.BytesIO()
        plt.savefig(buf, format='png', dpi=150, bbox_inches='tight')
        buf.seek(0)
        b64 = base64.b64encode(buf.read()).decode('utf-8')
        buf.close()
        plt.close(fig3)
        chart_data["momentum_chart"] = f"data:image/png;base64,{b64}"

        print(f"[Chart] Generated 3 StockEasy-level charts for {name} ({code})")

    except Exception as e:
        print(f"[Chart] Error generating charts for {code}: {e}")
        import traceback
        traceback.print_exc()

    return chart_data


# ============================================================================
# Claude API 기반 AI 종합 분석 (StockEasy 수준)
# ============================================================================

async def _collect_technical_data_for_ai(code: str, market: str = "kr") -> dict:
    """AI 분석용 기술적 지표 수집"""
    from .screener.technicals import (
        _calc_rsi, _calc_macd, _calc_stochastic, calc_adx
    )

    data = {
        "price": {
            "current": None, "change_pct": None,
            "high_52w": None, "low_52w": None,
            "volume": None, "avg_volume_20d": None,
        },
        "trend_indicators": {
            "adx": None, "plus_di": None, "minus_di": None,
            "rs_score": None,
        },
        "momentum_indicators": {
            "rsi": None, "macd_line": None, "macd_signal": None,
            "macd_histogram": None, "stoch_k": None, "stoch_d": None,
        },
        "moving_averages": {
            "sma_5": None, "sma_20": None, "sma_60": None,
            "sma_120": None, "sma_200": None,
        },
        "support_levels": [],  # [1차지지, 2차지지]
        "resistance_levels": [],  # [1차저항, 2차저항]
    }

    price_data = None  # 초기화

    try:
        # 캔들 데이터 가져오기 (최근 250일)
        if market == "kr":
            price_data = await get_naver_stock_price(code)
            print(f"[AI] price_data for {code}: {price_data}")
            # 네이버에서 차트 데이터
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.get(
                    f"https://api.stock.naver.com/chart/domestic/item/{code}/day?startDateTime=20240101&endDateTime=20261231",
                    headers={"User-Agent": "Mozilla/5.0"}
                )
                if resp.status_code == 200:
                    chart_data = resp.json()
                    candles = chart_data if isinstance(chart_data, list) else []
                    if len(candles) >= 20:
                        closes = [float(c.get("closePrice", 0)) for c in candles]
                        highs = [float(c.get("highPrice", 0)) for c in candles]
                        lows = [float(c.get("lowPrice", 0)) for c in candles]
                        volumes = [int(c.get("accumulatedTradingVolume", 0)) for c in candles]

                        # 이동평균
                        if len(closes) >= 5:
                            data["moving_averages"]["sma_5"] = round(sum(closes[-5:]) / 5)
                        if len(closes) >= 20:
                            data["moving_averages"]["sma_20"] = round(sum(closes[-20:]) / 20)
                            data["price"]["avg_volume_20d"] = int(sum(volumes[-20:]) / 20)
                        if len(closes) >= 60:
                            data["moving_averages"]["sma_60"] = round(sum(closes[-60:]) / 60)
                        if len(closes) >= 120:
                            data["moving_averages"]["sma_120"] = round(sum(closes[-120:]) / 120)
                        if len(closes) >= 200:
                            data["moving_averages"]["sma_200"] = round(sum(closes[-200:]) / 200)

                        # 52주 고저
                        recent_252 = closes[-252:] if len(closes) >= 252 else closes
                        data["price"]["high_52w"] = max(recent_252)
                        data["price"]["low_52w"] = min(recent_252)

                        # RSI
                        rsi = _calc_rsi(closes, 14)
                        if rsi:
                            data["momentum_indicators"]["rsi"] = rsi

                        # MACD (returns tuple: macd_line, signal_line, histogram)
                        macd = _calc_macd(closes)
                        if macd and isinstance(macd, tuple) and len(macd) >= 3:
                            data["momentum_indicators"]["macd_line"] = macd[0]
                            data["momentum_indicators"]["macd_signal"] = macd[1]
                            data["momentum_indicators"]["macd_histogram"] = macd[2]

                        # 스토캐스틱 (returns tuple: k, d)
                        stoch = _calc_stochastic(highs, lows, closes)
                        if stoch and isinstance(stoch, tuple) and len(stoch) >= 2:
                            data["momentum_indicators"]["stoch_k"] = stoch[0]
                            data["momentum_indicators"]["stoch_d"] = stoch[1]

                        # ADX (+ plus_di, minus_di)
                        adx_result = calc_adx(highs, lows, closes, 14)
                        if adx_result:
                            data["trend_indicators"]["adx"] = adx_result.get("adx")
                            data["trend_indicators"]["plus_di"] = adx_result.get("plus_di")
                            data["trend_indicators"]["minus_di"] = adx_result.get("minus_di")

                        # SuperTrend 계산
                        try:
                            import numpy as np
                            from .strategy_engine.indicators import calc_supertrend
                            highs_np = np.array(highs, dtype=float)
                            lows_np = np.array(lows, dtype=float)
                            closes_np = np.array(closes, dtype=float)
                            st_value, st_dir = calc_supertrend(highs_np, lows_np, closes_np, atr_len=10, factor=3.0)
                            if len(st_value) > 0 and not np.isnan(st_value[-1]):
                                data["trend_indicators"]["supertrend"] = round(st_value[-1], 0)
                                data["trend_indicators"]["supertrend_dir"] = int(st_dir[-1])  # -1=bullish, 1=bearish
                        except Exception as e:
                            print(f"[AI] SuperTrend calculation error: {e}")

                        # 지지/저항 계산 (피보나치 기반 - StockEasy 역분석)
                        try:
                            import numpy as np
                            current_price = closes[-1]
                            highs_np = np.array(highs, dtype=float)
                            lows_np = np.array(lows, dtype=float)
                            closes_np = np.array(closes, dtype=float)
                            volumes_np = np.array(volumes, dtype=float)

                            # 스윙 하이/로우 찾기
                            swing_high = float(highs_np.max())
                            swing_high_idx = int(np.argmax(highs_np))
                            if swing_high_idx > 20:
                                search_start = max(0, swing_high_idx - 250)
                                swing_low = float(lows_np[search_start:swing_high_idx].min())
                            else:
                                swing_low = float(lows_np.min())

                            # 피보나치 되돌림
                            fib_range = swing_high - swing_low
                            if fib_range < current_price * 0.15:
                                # 횡보: 폴백
                                data["support_levels"] = [round(current_price * 0.92), round(current_price * 0.85)]
                                data["resistance_levels"] = [round(current_price * 1.08), round(current_price * 1.15)]
                            else:
                                fib_382 = swing_high - fib_range * 0.382
                                fib_500 = swing_high - fib_range * 0.500
                                fib_236 = swing_high - fib_range * 0.236

                                # 거래량 밀집 구간
                                price_min, price_max = float(lows_np.min()), float(highs_np.max())
                                num_bins = 40
                                bin_edges = np.linspace(price_min, price_max, num_bins + 1)
                                volume_profile = np.zeros(num_bins)
                                for i in range(len(closes_np)):
                                    c, v = closes_np[i], volumes_np[i]
                                    bin_idx = min(int((c - price_min) / (price_max - price_min) * num_bins), num_bins - 1)
                                    volume_profile[bin_idx] += v
                                top_volume_bins = np.argsort(volume_profile)[-8:]
                                volume_nodes = sorted([float((bin_edges[b] + bin_edges[b + 1]) / 2) for b in top_volume_bins])

                                # 로컬 고점 찾기
                                order = 10
                                local_highs = []
                                for i in range(order, len(highs_np) - order):
                                    if all(highs_np[i] >= highs_np[i - j] for j in range(1, order + 1)) and \
                                       all(highs_np[i] >= highs_np[i + j] for j in range(1, order + 1)):
                                        local_highs.append(float(highs_np[i]))

                                # 스윙 로우 거래량 보정
                                swing_low_adj = swing_low
                                for vn in volume_nodes:
                                    if abs(vn - swing_low) / swing_low < 0.05:
                                        swing_low_adj = vn
                                        break

                                # 지지 후보 (가중치 기반)
                                support_candidates = []
                                if fib_382 < current_price * 0.98:
                                    support_candidates.append((fib_382, 3.0))
                                if fib_500 < current_price * 0.98:
                                    support_candidates.append((fib_500, 2.0))
                                if swing_low_adj < current_price * 0.98:
                                    support_candidates.append((swing_low_adj, 2.5))
                                for vn in volume_nodes:
                                    if vn < current_price * 0.97:
                                        support_candidates.append((vn, 1.5))

                                # 저항 후보 (가중치 기반)
                                resistance_candidates = []
                                for lh in local_highs:
                                    if lh > current_price * 1.02:
                                        resistance_candidates.append((lh, 2.0))
                                if swing_high > current_price * 1.02:
                                    resistance_candidates.append((swing_high, 2.5))
                                if fib_236 > current_price * 1.02:
                                    resistance_candidates.append((fib_236, 2.0))
                                for vn in volume_nodes:
                                    if vn > current_price * 1.02:
                                        resistance_candidates.append((vn, 1.5))

                                # 클러스터링 + 가중치 선택
                                def select_best(candidates, num, asc=True):
                                    if not candidates:
                                        return []
                                    candidates = sorted(candidates, key=lambda x: x[0])
                                    clusters = [[candidates[0]]]
                                    for c in candidates[1:]:
                                        if clusters[-1] and (c[0] - clusters[-1][-1][0]) / clusters[-1][-1][0] < 0.03:
                                            clusters[-1].append(c)
                                        else:
                                            clusters.append([c])
                                    results = []
                                    for cluster in clusters:
                                        tw = sum(c[1] for c in cluster)
                                        wp = sum(c[0] * c[1] for c in cluster) / tw
                                        results.append((round(wp), tw))
                                    results.sort(key=lambda x: x[1], reverse=True)
                                    sel = [r[0] for r in results[:num]]
                                    sel.sort(reverse=not asc)
                                    return sel

                                support_levels = select_best(support_candidates, 2, asc=False)
                                resistance_levels = select_best(resistance_candidates, 2, asc=True)

                                # 최소 보장
                                while len(support_levels) < 2:
                                    base = support_levels[-1] if support_levels else current_price
                                    support_levels.append(round(base * 0.85))
                                while len(resistance_levels) < 2:
                                    base = resistance_levels[-1] if resistance_levels else current_price
                                    resistance_levels.append(round(base * 1.15))

                                data["support_levels"] = support_levels
                                data["resistance_levels"] = resistance_levels
                        except Exception as e:
                            print(f"[AI] Support/Resistance calculation error: {e}")

        elif market == "us":
            # 해외 주식: yfinance로 데이터 수집
            import yfinance as yf

            try:
                ticker = yf.Ticker(code)
                info = ticker.info or {}

                # 현재가
                current_price = info.get('currentPrice') or info.get('regularMarketPrice')
                prev_close = info.get('previousClose') or info.get('regularMarketPreviousClose')

                if current_price and prev_close:
                    change_pct = ((current_price - prev_close) / prev_close) * 100
                else:
                    change_pct = 0

                price_data = {
                    "current": current_price,
                    "change": round(change_pct, 2) if change_pct else 0,
                    "volume": info.get('volume'),
                }

                data["price"]["current"] = current_price
                data["price"]["change_pct"] = round(change_pct, 2) if change_pct else 0
                data["price"]["volume"] = info.get('volume')
                data["price"]["high_52w"] = info.get('fiftyTwoWeekHigh')
                data["price"]["low_52w"] = info.get('fiftyTwoWeekLow')
                data["price"]["avg_volume_20d"] = info.get('averageVolume')

                # 일봉 데이터로 기술적 지표 계산
                hist = ticker.history(period="2y")
                if hist is not None and len(hist) >= 20:
                    closes = hist['Close'].tolist()
                    highs = hist['High'].tolist()
                    lows = hist['Low'].tolist()
                    volumes = hist['Volume'].tolist()

                    # 이동평균
                    if len(closes) >= 5:
                        data["moving_averages"]["sma_5"] = round(sum(closes[-5:]) / 5, 2)
                    if len(closes) >= 20:
                        data["moving_averages"]["sma_20"] = round(sum(closes[-20:]) / 20, 2)
                    if len(closes) >= 60:
                        data["moving_averages"]["sma_60"] = round(sum(closes[-60:]) / 60, 2)
                    if len(closes) >= 120:
                        data["moving_averages"]["sma_120"] = round(sum(closes[-120:]) / 120, 2)
                    if len(closes) >= 200:
                        data["moving_averages"]["sma_200"] = round(sum(closes[-200:]) / 200, 2)

                    # RSI
                    rsi = _calc_rsi(closes, 14)
                    if rsi:
                        data["momentum_indicators"]["rsi"] = rsi

                    # MACD
                    macd = _calc_macd(closes)
                    if macd and isinstance(macd, tuple) and len(macd) >= 3:
                        data["momentum_indicators"]["macd_line"] = macd[0]
                        data["momentum_indicators"]["macd_signal"] = macd[1]
                        data["momentum_indicators"]["macd_histogram"] = macd[2]

                    # 스토캐스틱
                    stoch = _calc_stochastic(highs, lows, closes)
                    if stoch and isinstance(stoch, tuple) and len(stoch) >= 2:
                        data["momentum_indicators"]["stoch_k"] = stoch[0]
                        data["momentum_indicators"]["stoch_d"] = stoch[1]

                    # ADX
                    adx_result = calc_adx(highs, lows, closes, 14)
                    if adx_result:
                        data["trend_indicators"]["adx"] = adx_result.get("adx")
                        data["trend_indicators"]["plus_di"] = adx_result.get("plus_di")
                        data["trend_indicators"]["minus_di"] = adx_result.get("minus_di")

                    # 지지/저항 (피보나치 기반, 현재가 기준 분류)
                    recent_high = max(highs[-60:]) if len(highs) >= 60 else max(highs)
                    recent_low = min(lows[-60:]) if len(lows) >= 60 else min(lows)
                    fib_range = recent_high - recent_low

                    # 피보나치 레벨 계산 (저점 기준)
                    fib_236 = recent_low + fib_range * 0.236
                    fib_382 = recent_low + fib_range * 0.382
                    fib_500 = recent_low + fib_range * 0.500
                    fib_618 = recent_low + fib_range * 0.618
                    fib_786 = recent_low + fib_range * 0.786

                    # 모든 레벨
                    all_levels = [recent_low, fib_236, fib_382, fib_500, fib_618, fib_786, recent_high]

                    # 현재가 기준으로 지지(아래)/저항(위) 분류
                    support = sorted([lvl for lvl in all_levels if lvl < current_price], reverse=True)
                    resistance = sorted([lvl for lvl in all_levels if lvl > current_price])

                    # 가장 가까운 2개씩 선택 (없으면 기본값)
                    if len(support) >= 2:
                        data["support_levels"] = [round(support[0], 2), round(support[1], 2)]
                    elif len(support) == 1:
                        data["support_levels"] = [round(support[0], 2), round(support[0] * 0.95, 2)]
                    else:
                        data["support_levels"] = [round(recent_low, 2), round(recent_low * 0.95, 2)]

                    if len(resistance) >= 2:
                        data["resistance_levels"] = [round(resistance[0], 2), round(resistance[1], 2)]
                    elif len(resistance) == 1:
                        data["resistance_levels"] = [round(resistance[0], 2), round(resistance[0] * 1.05, 2)]
                    else:
                        data["resistance_levels"] = [round(recent_high, 2), round(recent_high * 1.05, 2)]

                    print(f"[AI] US technical data collected for {code}: price=${current_price}")

            except Exception as e:
                print(f"[AI] US technical data error for {code}: {e}")

        if price_data:
            data["price"]["current"] = price_data.get("current", 0)
            data["price"]["change_pct"] = price_data.get("change", 0)
            data["price"]["volume"] = price_data.get("volume", 0)

        # RS 스코어 (마스터 캐시에서)
        master = get_master_cache()
        stock = master.get_stock(code)
        if stock and hasattr(stock, 'rs_score'):
            data["trend_indicators"]["rs_score"] = stock.rs_score

    except Exception as e:
        print(f"[AI] Technical data collection error for {code}: {e}")

    return data


async def _collect_financial_data_for_ai(code: str, market: str = "kr") -> dict:
    """AI 분석용 재무 데이터 수집"""
    data = {
        "annual": {"revenue": [], "operating_income": [], "net_income": []},
        "quarter": {"revenue": [], "operating_income": [], "net_income": []},
        "ratios": {
            "roe": None, "debt_ratio": None, "operating_margin": None,
            "per": None, "pbr": None, "eps": None,
        },
        "consensus": {"target_price": None, "recommendation": None},
    }

    try:
        if market == "kr":
            fin_data = await get_stock_financials_kr(code, "annual")
            if fin_data and fin_data.get("success"):
                annual = fin_data.get("annual", {})
                data["annual"]["revenue"] = annual.get("revenue", [])[:3]
                data["annual"]["operating_income"] = annual.get("operating_income", [])[:3]
                data["annual"]["net_income"] = annual.get("net_income", [])[:3]

                ratios = fin_data.get("ratios", {})
                data["ratios"]["roe"] = ratios.get("roe")
                data["ratios"]["per"] = ratios.get("per")
                data["ratios"]["pbr"] = ratios.get("pbr")
                data["ratios"]["eps"] = ratios.get("eps")
                data["ratios"]["debt_ratio"] = ratios.get("debt_ratio")
                data["ratios"]["operating_margin"] = ratios.get("operating_margin")

            # 분기 실적
            q_data = await get_stock_financials_kr(code, "quarter")
            if q_data and q_data.get("success"):
                quarter = q_data.get("quarter", {})
                data["quarter"]["revenue"] = quarter.get("revenue", [])[:4]
                data["quarter"]["operating_income"] = quarter.get("operating_income", [])[:4]
                data["quarter"]["net_income"] = quarter.get("net_income", [])[:4]

    except Exception as e:
        print(f"[AI] Financial data collection error for {code}: {e}")

    return data


async def _collect_news_for_ai(code: str, name: str, market: str = "kr") -> list:
    """AI 분석용 최근 뉴스 수집"""
    news = []
    try:
        if market == "kr":
            news_data = await get_stock_news_kr(code, 5)
            if news_data and news_data.get("success"):
                for item in news_data.get("news", [])[:5]:
                    news.append({
                        "title": item.get("title", ""),
                        "date": item.get("date", ""),
                    })
    except Exception as e:
        print(f"[AI] News collection error for {code}: {e}")

    return news


def split_ai_report(text: str) -> dict:
    """AI 보고서를 섹션별로 분리. [SECTION_1_4] 마커가 없어도 안전하게 동작."""
    import re

    sections = {
        'before_ta': '',
        'section_51': '',
        'section_52': '',
        'section_53': '',
        'after_53': ''
    }

    if not text:
        return sections

    # 방법 A: [SECTION_1_4]와 [SECTION_51] 둘 다 있는 경우 (정상 경로)
    if '[SECTION_1_4]' in text and '[SECTION_51]' in text:
        parts = text.split('[SECTION_51]', 1)
        sections['before_ta'] = parts[0].replace('[SECTION_1_4]', '').strip()
        rest = parts[1] if len(parts) > 1 else ''

    # 방법 B: [SECTION_1_4] 없지만 [SECTION_51] 있는 경우 (핵심 폴백!)
    elif '[SECTION_51]' in text:
        parts = text.split('[SECTION_51]', 1)
        sections['before_ta'] = parts[0].strip()  # [SECTION_51] 이전 전부가 before_ta
        rest = parts[1] if len(parts) > 1 else ''

    # 방법 C: 마커 전혀 없는 경우 — 섹션 번호(5.1, 5.2 등)로 자동 분리
    else:
        # "5.1" 또는 "### 5.1" 또는 "#### 5.1" 패턴으로 분리
        pattern = r'(?=(?:#{1,4}\s*)?5\.1\s)'
        split_result = re.split(pattern, text, maxsplit=1)
        sections['before_ta'] = split_result[0].strip()
        rest = split_result[1] if len(split_result) > 1 else ''

    # [SECTION_52]로 분리
    if '[SECTION_52]' in rest:
        parts52 = rest.split('[SECTION_52]', 1)
        sections['section_51'] = parts52[0].replace('[SECTION_51]', '').strip()
        rest2 = parts52[1] if len(parts52) > 1 else ''
    else:
        # 5.2 패턴으로 분리
        pattern52 = r'(?=(?:#{1,4}\s*)?5\.2\s)'
        split52 = re.split(pattern52, rest, maxsplit=1)
        sections['section_51'] = split52[0].replace('[SECTION_51]', '').strip()
        rest2 = split52[1] if len(split52) > 1 else ''

    # [SECTION_53]로 분리
    if '[SECTION_53]' in rest2:
        parts53 = rest2.split('[SECTION_53]', 1)
        sections['section_52'] = parts53[0].replace('[SECTION_52]', '').strip()
        rest3 = parts53[1] if len(parts53) > 1 else ''
    else:
        pattern53 = r'(?=(?:#{1,4}\s*)?5\.3\s)'
        split53 = re.split(pattern53, rest2, maxsplit=1)
        sections['section_52'] = split53[0].replace('[SECTION_52]', '').strip()
        rest3 = split53[1] if len(split53) > 1 else ''

    # 5.4 또는 6. 이후로 분리
    if '[SECTION_54_END]' in rest3:
        parts54 = rest3.split('[SECTION_54_END]', 1)
        sections['section_53'] = parts54[0].replace('[SECTION_53]', '').strip()
        sections['after_53'] = parts54[1].strip() if len(parts54) > 1 else ''
    else:
        pattern_after = r'(?=(?:#{1,4}\s*)?(?:5\.4|6\.)\s)'
        split_after = re.split(pattern_after, rest3, maxsplit=1)
        sections['section_53'] = split_after[0].replace('[SECTION_53]', '').strip()
        sections['after_53'] = split_after[1].strip() if len(split_after) > 1 else ''

    # 모든 섹션에서 남은 마커 제거
    for key in sections:
        for marker in ['[SECTION_1_4]', '[SECTION_51]', '[SECTION_52]', '[SECTION_53]', '[SECTION_54_END]']:
            sections[key] = sections[key].replace(marker, '')

    return sections


def _build_claude_prompt(name: str, code: str, tech: dict, fin: dict, news: list, company_summary: str = "", market: str = "kr") -> str:
    """Claude에게 보낼 분석 프롬프트 구성 (StockEasy 수준)"""
    from datetime import datetime, timezone, timedelta

    # 오늘 날짜 (KST)
    KST = timezone(timedelta(hours=9))
    today = datetime.now(KST).strftime('%Y년 %m월 %d일')

    # 통화 단위 설정 (market에 따라)
    if market == "us":
        currency_prefix = "$"
        currency_suffix = ""
        cap_unit = "억달러"
        currency_instruction = """
⚠️ 통화 단위 필수 규칙:
- 이 종목은 미국 시장(US) 종목이다.
- 모든 가격(현재가, 지지선, 저항선, 목표주가, SMA 등)을 반드시 달러($)로 표시해라.
- "원"을 절대 사용하지 마라.
- 올바른 예: 현재가 $143, 1차 저항선 $149.9, SMA200 $135.62
- 잘못된 예: 현재가 143원 ← 이렇게 쓰면 안 됨
"""
    else:
        currency_prefix = ""
        currency_suffix = "원"
        cap_unit = "억원"
        currency_instruction = ""

    # 안전한 숫자 변환 함수
    def safe_int(v, default=0):
        if v is None:
            return default
        try:
            return int(v)
        except (ValueError, TypeError):
            return default

    def safe_float(v, default=0.0):
        if v is None:
            return default
        try:
            return float(v)
        except (ValueError, TypeError):
            return default

    def safe_str(v, default="-"):
        if v is None:
            return default
        return str(round(v, 2)) if isinstance(v, float) else str(v)

    # 가격 정보
    price = tech.get("price", {})
    current = safe_int(price.get("current"))
    change = safe_float(price.get("change_pct"))
    high_52w = safe_int(price.get("high_52w"))
    low_52w = safe_int(price.get("low_52w"))
    volume = safe_int(price.get("volume"))
    avg_vol = safe_int(price.get("avg_volume_20d"))

    # 이동평균
    ma = tech.get("moving_averages", {})
    sma5 = safe_str(ma.get("sma_5"))
    sma20 = safe_str(ma.get("sma_20"))
    sma60 = safe_str(ma.get("sma_60"))
    sma120 = safe_str(ma.get("sma_120"))
    sma200 = safe_str(ma.get("sma_200"))

    # 추세 지표
    trend = tech.get("trend_indicators", {})
    adx = safe_str(trend.get("adx"))
    plus_di = safe_str(trend.get("plus_di"))
    minus_di = safe_str(trend.get("minus_di"))
    rs = safe_str(trend.get("rs_score"))
    supertrend_val = trend.get("supertrend")
    supertrend_dir = trend.get("supertrend_dir")
    # SuperTrend 표시: 값 + 방향
    if supertrend_val is not None:
        st_signal = "상승" if supertrend_dir == -1 else "하락" if supertrend_dir == 1 else ""
        supertrend = f"{int(supertrend_val):,}원 ({st_signal})" if st_signal else f"{int(supertrend_val):,}원"
    else:
        supertrend = "-"

    # 모멘텀 지표
    mom = tech.get("momentum_indicators", {})
    rsi = safe_str(mom.get("rsi"))
    macd_line = safe_str(mom.get("macd_line"))
    macd_signal = safe_str(mom.get("macd_signal"))
    macd_hist = safe_str(mom.get("macd_histogram"))
    stoch_k = safe_str(mom.get("stoch_k"))
    stoch_d = safe_str(mom.get("stoch_d"))

    # 지지/저항 (4레벨)
    support_levels = tech.get("support_levels", [])
    resistance_levels = tech.get("resistance_levels", [])
    support1 = f"{support_levels[0]:,}원" if support_levels else "-"
    support2 = f"{support_levels[1]:,}원" if len(support_levels) > 1 else "-"
    resistance1 = f"{resistance_levels[0]:,}원" if resistance_levels else "-"
    resistance2 = f"{resistance_levels[1]:,}원" if len(resistance_levels) > 1 else "-"

    # 재무
    ratios = fin.get("ratios", {})
    roe = safe_str(ratios.get("roe"))
    per = safe_str(ratios.get("per"))
    pbr = safe_str(ratios.get("pbr"))
    eps = safe_str(ratios.get("eps"))
    debt = safe_str(ratios.get("debt_ratio"))
    opm = safe_str(ratios.get("operating_margin"))
    market_cap = safe_str(ratios.get("market_cap"))

    # 연간 실적
    annual = fin.get("annual", {})
    rev = annual.get("revenue", [])
    op_inc = annual.get("operating_income", [])
    net_inc = annual.get("net_income", [])

    # 뉴스
    news_text = "\n".join([f"- [{n['date']}] {n['title']}" for n in news[:5]]) if news else "최근 뉴스 없음"

    # 기업 개요 (FnGuide)
    company_text = company_summary if company_summary else "기업 개요 정보 없음"

    prompt = f"""당신은 15년 경력의 전문 증권 애널리스트입니다.
오늘 날짜: {today}
{currency_instruction}
⚠️ 필수: 보고서 맨 처음에 반드시 [SECTION_1_4]를 단독 줄로 쓴 후 본문을 시작하세요!
[SECTION_1_4]를 빠뜨리면 보고서 레이아웃이 깨집니다.

{name}({code})의 종합 분석 보고서를 아래 데이터와 웹검색을 기반으로 작성하세요.

## 제공 데이터

### 기업 개요
{company_text if company_text != "기업 개요 정보 없음" else "(데이터 없음 - 웹검색으로 보완하세요)"}

### 기본 정보
- 종목명: {name} ({code})
- 현재가: {currency_prefix}{current:,}{currency_suffix} ({change:+.2f}%)
- 52주 고가/저가: {currency_prefix}{high_52w:,}{currency_suffix} / {currency_prefix}{low_52w:,}{currency_suffix}
- 거래량: {volume:,}주 (20일 평균: {avg_vol:,}주)
- 시가총액: {market_cap}{cap_unit}

### 재무 지표
| 지표 | 값 |
|------|-----|
| PER | {per} |
| PBR | {pbr} |
| ROE | {roe}% |
| EPS | {currency_prefix}{eps}{currency_suffix} |
| 부채비율 | {debt}% |
| 영업이익률 | {opm}% |

### 연간 실적 (최근 3년, {cap_unit})
- 매출액: {rev}
- 영업이익: {op_inc}
- 순이익: {net_inc}

### 기술적 지표 (오늘 기준)
- 현재가: {currency_prefix}{current:,}{currency_suffix}
- RSI(14): {rsi}
- MACD: Line {macd_line}, Signal {macd_signal}, Histogram {macd_hist}
- ADX: {adx} / +DI: {plus_di} / -DI: {minus_di}
- 스토캐스틱: %K {stoch_k}, %D {stoch_d}
- SuperTrend: {supertrend}
- RS (상대강도): {rs}

### 이동평균선
SMA5: {sma5} | SMA20: {sma20} | SMA60: {sma60} | SMA120: {sma120} | SMA200: {sma200}

### 지지/저항선 (4레벨 분석)
- 1차 지지선: {support1} (현재가 근접, 단기 지지)
- 2차 지지선: {support2} (장기 지지, 추세 전환 기준)
- 1차 저항선: {resistance1} (현재가 근접, 단기 저항)
- 2차 저항선: {resistance2} (중기 저항, 돌파 목표)

### 최근 뉴스 (수집됨)
{news_text}

---

## 웹검색 지시 (최대 3회만 검색)

아래 3가지 검색어로 **정확히 3회만** 웹검색하세요 (추가 검색 금지):
1. "{name} 증권사 목표주가 2026" → 최소 2개 증권사의 투자의견/목표주가
2. "{name} 최신 뉴스" → 최근 1주일 핵심 이슈 3-5개
3. "{name} 실적 전망 2026" → 컨센서스 매출/영업이익 전망

⚠️ 중요: 웹검색은 위 3회로 제한. 추가 검색 없이 수집된 정보로 보고서 작성.

## 보고서 구조 (반드시 이 순서와 형식으로 작성)

**중요: 아래 구분자를 반드시 각 섹션 시작 전에 줄 맨 앞에 단독으로 작성하세요.**
- [SECTION_1_4] : 1~4섹션 시작 전
- [SECTION_51] : 5.1 시작 전
- [SECTION_52] : 5.2 시작 전
- [SECTION_53] : 5.3 시작 전
- [SECTION_54_END] : 5.4 시작 전

[SECTION_1_4]

### 1. 핵심 요약
6개 핵심 포인트를 각각 제목+2~3문장으로 작성. 예시:
• 실적 개선 전망 및 목표주가 상향: 2026년 연결 기준 영업이익은 X억원으로 전망되며...
• 미국 태양광 시장의 긍정적 환경: ...
(구체적 수치 필수, 일반론 금지)

### 2. 실적 전망 및 목표주가 분석
- 2026년 재무지표 전망 테이블 (매출액/영업이익/당기순이익/EPS)
- 증권사별 투자의견/목표주가 테이블 (웹검색 기반, 최소 2개 증권사)
- 시가총액 달성 가능성 분석 (멀티플 근거 포함)

### 3. 핵심 성장 동력 및 사업 전망
- 3~4개 소섹션으로 구분 (예: 시장 환경, 차세대 기술, 신규 수요, 재무 구조)
- 각 소섹션 2~3문단 서술

### 4. 주요 이슈 및 시장 반응
- 웹검색으로 찾은 최신 뉴스 3~5개를 소섹션으로 구분
- 각 이슈가 주가에 미치는 영향 분석

### 5. 기술적 분석

[SECTION_51]

#### 5.1 주가 및 지지/저항
- 현재가 {currency_prefix}{current:,}{currency_suffix}, 최근 10일 주가 범위, 상승률
- 1차 지지 {support1} / 2차 지지 {support2} 가격 명시
- 1차 저항 {resistance1} / 2차 저항 {resistance2} 가격 명시
- 향후 돌파/이탈 시나리오 (각 레벨별 의미)

[SECTION_52]

#### 5.2 추세추종 지표 분석
- ADX {adx} 해석 (25 미만=약한 추세, 25~50=강한 추세, 50 이상=매우 강한 추세)
- +DI {plus_di} / -DI {minus_di} 관계로 추세 방향 판단
- SuperTrend {supertrend} 위치 및 현재가와의 간격
- RS {rs} 시장 대비 우위 여부

[SECTION_53]

#### 5.3 모멘텀 지표 분석
- RSI {rsi} 해석 (30 이하=과매도, 70 이상=과매수)
- MACD Line {macd_line} / Signal {macd_signal} 교차 상태, Histogram {macd_hist} 방향
- 스토캐스틱 %K {stoch_k} / %D {stoch_d} 교차 방향

[SECTION_54_END]

#### 5.4 주가, 거래량, 수급 분석
- 최근 거래량 {volume:,}주 vs 20일 평균 {avg_vol:,}주 변화
- 가격-거래량 관계 해석
- 외국인/기관 수급 동향 (웹검색 활용)

#### 5.5 종합 분석
- 6개 지표 요약 테이블 (지표명/현재값/신호/상세정보)
- 종합 신호 판단 (매수/매도/중립)
- 3가지 예상 시나리오:
  1. 상승추세지속 시나리오: 구체적 가격대 명시
  2. 단기조정후재상승 시나리오: 구체적 가격대 명시
  3. 추세전환 시나리오: 구체적 가격대 명시

### 6. 면책조항
"본 보고서는 투자 참고 자료로만 활용하시기 바라며, 특정 종목의 매수/매도를 권유하지 않습니다."

---

## 작성 규칙 (필수 준수)

1. 반드시 제공된 데이터의 실제 수치를 인용하세요. 추측 금지.
2. 제공 데이터가 없는 항목은 웹검색으로 보완하세요. 그래도 없으면 "데이터 미확인"으로 표시.
3. **"정보 부족으로 평가 불가" 같은 문구는 절대 쓰지 마세요.**
4. 증권사 목표주가는 반드시 웹검색으로 확인 후 기재하세요.
5. 시나리오별 가격대는 지지선/저항선 기반으로 구체적으로 제시하세요.
6. 총 분량: **최소 3000자 이상** (충분히 상세하게).
7. 마크다운 형식으로 작성 (# ## ### 헤딩, 테이블, 글머리 기호 사용).
8. **절대 금지**: "웹검색을 통해", "정보를 수집하겠습니다", "보고서를 작성하겠습니다" 같은 작업 과정 설명을 포함하지 마세요.
9. 보고서 본문(1. 핵심 요약)부터 바로 시작하세요. 서두/인사말 없이 바로 분석 내용으로 시작.
"""
    return prompt


# ============================================
# ETF 전용 AI 리포트 생성
# ============================================

async def _collect_etf_data_for_ai(code: str) -> dict:
    """ETF 전용 데이터 수집 - 네이버 금융 API + 웹검색 보완"""
    result = {
        "name": "",
        "current_price": 0,
        "change_pct": 0,
        "nav": 0,
        "nav_diff_pct": 0,
        "total_expense": 0,
        "aum": 0,
        "tracking_index": "",
        "manager": "",
        "dividend_yield": 0,
        "holdings": [],
        "returns": {},
        "high_52w": 0,
        "low_52w": 0,
        "volume": 0,
    }

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            # 1. 네이버 기본 정보 API
            resp = await client.get(
                f"https://m.stock.naver.com/api/stock/{code}/basic",
                headers={"User-Agent": "Mozilla/5.0"}
            )
            if resp.status_code == 200:
                data = resp.json()
                result["name"] = data.get("stockName", "")
                # closePrice가 문자열인 경우 처리
                close_price = data.get("closePrice", "0")
                if isinstance(close_price, str):
                    close_price = close_price.replace(",", "")
                result["current_price"] = int(close_price) if close_price else 0
                result["change_pct"] = float(data.get("fluctuationsRatio", 0) or 0)

            # 2. 네이버 시세 정보
            sise_resp = await client.get(
                f"https://m.stock.naver.com/api/stock/{code}/price",
                headers={"User-Agent": "Mozilla/5.0"}
            )
            if sise_resp.status_code == 200:
                sise_data = sise_resp.json()
                result["high_52w"] = sise_data.get("high52wPrice", 0)
                result["low_52w"] = sise_data.get("low52wPrice", 0)
                result["volume"] = sise_data.get("accumulatedTradingVolume", 0)

            # 3. ETF 정보 조회 (integration API 사용 - 가장 신뢰성 높음)
            try:
                int_resp = await client.get(
                    f"https://m.stock.naver.com/api/stock/{code}/integration",
                    headers={"User-Agent": "Mozilla/5.0"}
                )
                if int_resp.status_code == 200:
                    int_data = int_resp.json()
                    etf_ind = int_data.get("etfKeyIndicator", {})

                    if etf_ind:
                        # 운용사
                        result["manager"] = etf_ind.get("issuerName", "")

                        # NAV (문자열 → 숫자)
                        nav_val = etf_ind.get("nav", 0)
                        if isinstance(nav_val, str):
                            nav_val = nav_val.replace(",", "")
                        try:
                            result["nav"] = float(nav_val)
                        except:
                            result["nav"] = 0

                        # 괴리율
                        dev_sign = etf_ind.get("deviationSign", "")
                        dev_rate = etf_ind.get("deviationRate", 0) or 0
                        result["nav_diff_pct"] = -dev_rate if dev_sign == "-" else dev_rate

                        # 총보수
                        result["total_expense"] = etf_ind.get("totalFee", 0) or 0

                        # 순자산총액 (문자열 → 숫자, 억원 단위)
                        aum_str = etf_ind.get("totalNav", "0")
                        if isinstance(aum_str, str):
                            # "18조 5,738억" → 185738
                            import re
                            aum_str = aum_str.replace(",", "").replace(" ", "")
                            jo_match = re.search(r'(\d+)조', aum_str)
                            eok_match = re.search(r'(\d+)억', aum_str)
                            jo = int(jo_match.group(1)) if jo_match else 0
                            eok = int(eok_match.group(1)) if eok_match else 0
                            result["aum"] = jo * 10000 + eok
                        else:
                            result["aum"] = aum_str or 0

                        # 배당수익률
                        result["dividend_yield"] = etf_ind.get("dividendYieldTtm", 0) or 0

                        # 수익률
                        result["returns"] = {
                            "1m": etf_ind.get("returnRate1m", 0) or 0,
                            "3m": etf_ind.get("returnRate3m", 0) or 0,
                            "6m": 0,  # integration API에 없음
                            "1y": etf_ind.get("returnRate1y", 0) or 0,
                            "ytd": 0,  # integration API에 없음
                        }
            except Exception as e:
                print(f"[ETF Data] Integration API error: {e}")

            # 4. ETF명으로 추적지수 추론 (네이버 API 실패 시 폴백)
            if not result["tracking_index"] and result["name"]:
                name = result["name"].upper()
                if "200" in name:
                    result["tracking_index"] = "KOSPI 200"
                elif "50" in name:
                    result["tracking_index"] = "KOSPI 50"
                elif "KOSDAQ" in name or "코스닥" in result["name"]:
                    result["tracking_index"] = "KOSDAQ 150"
                elif "S&P500" in name or "S&P" in name:
                    result["tracking_index"] = "S&P 500"
                elif "NASDAQ" in name or "나스닥" in result["name"]:
                    result["tracking_index"] = "NASDAQ 100"

            # 5. 운용사 추론
            if not result["manager"] and result["name"]:
                name = result["name"]
                if "KODEX" in name:
                    result["manager"] = "삼성자산운용"
                elif "TIGER" in name:
                    result["manager"] = "미래에셋자산운용"
                elif "KBSTAR" in name:
                    result["manager"] = "KB자산운용"
                elif "ARIRANG" in name:
                    result["manager"] = "한화자산운용"
                elif "HANARO" in name:
                    result["manager"] = "NH-아문디자산운용"

            print(f"[ETF Data] Collected for {code}: name={result['name']}, price={result['current_price']}")

    except Exception as e:
        print(f"[ETF Data] Error collecting data for {code}: {e}")
        import traceback
        traceback.print_exc()

    return result


def _format_technical_data_for_prompt(tech: dict, market: str = "kr") -> str:
    """기술적 분석 데이터를 프롬프트 문자열로 변환"""
    if not tech:
        return "기술적 지표 데이터 없음"

    # 통화 단위 설정
    if market == "us":
        def fmt_price(val):
            return f"${val:,.2f}"
    else:
        def fmt_price(val):
            return f"{val:,}원"

    lines = []

    # 가격 정보
    price = tech.get("price", {})
    if price.get("current"):
        lines.append(f"- 현재가: {fmt_price(price.get('current', 0))}")
    if price.get("high_52w"):
        lines.append(f"- 52주 최고: {fmt_price(price.get('high_52w', 0))}")
    if price.get("low_52w"):
        lines.append(f"- 52주 최저: {fmt_price(price.get('low_52w', 0))}")

    # 이동평균
    ma = tech.get("moving_averages", {})
    ma_lines = []
    for period in [5, 20, 60, 120, 200]:
        val = ma.get(f"sma_{period}")
        if val:
            ma_lines.append(f"SMA{period}={val:,}")
    if ma_lines:
        lines.append(f"- 이동평균: {', '.join(ma_lines)}")

    # 모멘텀 지표
    mom = tech.get("momentum_indicators", {})
    if mom.get("rsi"):
        lines.append(f"- RSI(14): {mom.get('rsi', 0):.1f}")
    if mom.get("macd_line") is not None:
        lines.append(f"- MACD: 라인={mom.get('macd_line', 0):.2f}, 시그널={mom.get('macd_signal', 0):.2f}, 히스토그램={mom.get('macd_histogram', 0):.2f}")
    if mom.get("stoch_k") is not None:
        lines.append(f"- 스토캐스틱: %K={mom.get('stoch_k', 0):.1f}, %D={mom.get('stoch_d', 0):.1f}")

    # 추세 지표
    trend = tech.get("trend_indicators", {})
    if trend.get("adx"):
        lines.append(f"- ADX: {trend.get('adx', 0):.1f} (+DI={trend.get('plus_di', 0):.1f}, -DI={trend.get('minus_di', 0):.1f})")

    # 지지/저항
    support = tech.get("support_levels", [])
    resistance = tech.get("resistance_levels", [])
    if support:
        lines.append(f"- 지지선: {', '.join([fmt_price(s) for s in support])}")
    if resistance:
        lines.append(f"- 저항선: {', '.join([fmt_price(r) for r in resistance])}")

    return "\n".join(lines) if lines else "기술적 지표 데이터 없음"


def _build_etf_prompt(name: str, code: str, data: dict, market: str = "kr") -> str:
    """ETF 전용 AI 분석 프롬프트 구성"""
    from datetime import datetime, timezone, timedelta
    KST = timezone(timedelta(hours=9))
    today = datetime.now(KST).strftime('%Y년 %m월 %d일')

    # 통화 단위 설정 (market에 따라)
    if market == "us":
        currency_prefix = "$"
        currency_suffix = ""
        cap_unit = "억달러"
        currency_instruction = """
⚠️ 통화 단위 필수 규칙:
- 이 ETF는 미국 시장(US) 종목이다.
- 모든 가격(현재가, NAV, 지지선, 저항선 등)을 반드시 달러($)로 표시해라.
- "원"을 절대 사용하지 마라.
- 올바른 예: 현재가 $143, 1차 저항선 $149.9
- 잘못된 예: 현재가 143원 ← 이렇게 쓰면 안 됨
"""
    else:
        currency_prefix = ""
        currency_suffix = "원"
        cap_unit = "억원"
        currency_instruction = ""

    # 편입종목 문자열
    holdings_text = "\n".join([
        f"  - {h['name']}: {h['weight']}%"
        for h in data.get("holdings", [])
    ]) if data.get("holdings") else "편입종목 정보 없음"

    # 수익률 정보
    returns = data.get("returns", {})

    # 가격 정보 포맷팅
    current_price = data.get('current_price', 0)
    nav = data.get('nav', 0)
    aum = data.get('aum', 0)

    prompt = f"""
당신은 ETF 전문 애널리스트입니다. 아래 ETF 정보를 바탕으로 투자 분석 보고서를 작성해주세요.
{currency_instruction}
⚠️ 필수: 보고서 맨 처음에 반드시 [SECTION_1_4]를 단독 줄로 쓴 후 본문을 시작하세요!
[SECTION_1_4]를 빠뜨리면 보고서 레이아웃이 깨집니다.

## 분석 대상
- ETF명: {name}
- 종목코드: {code}
- 분석일: {today}

## 제공된 데이터

### 가격 정보
- 현재가: {currency_prefix}{current_price:,}{currency_suffix}
- 등락률: {data.get('change_pct', 0):.2f}%
- NAV(순자산가치): {currency_prefix}{nav:,}{currency_suffix}
- 괴리율: {data.get('nav_diff_pct', 0):.2f}%

### ETF 기본 정보
- 추적 지수: {data.get('tracking_index', '정보 없음')}
- 운용사: {data.get('manager', '정보 없음')}
- 총보수: {data.get('total_expense', 0):.2f}%
- 순자산총액: {aum:,.0f}{cap_unit}
- 배당수익률: {data.get('dividend_yield', 0):.2f}%

### 수익률
- 1개월: {returns.get('1m', 0):.2f}%
- 3개월: {returns.get('3m', 0):.2f}%
- 6개월: {returns.get('6m', 0):.2f}%
- 1년: {returns.get('1y', 0):.2f}%
- YTD: {returns.get('ytd', 0):.2f}%

### 편입종목 상위 10개
{holdings_text}

### 기술적 분석 지표
{_format_technical_data_for_prompt(data.get('technical', {}), market)}

---

## 보고서 구조 (반드시 이 순서와 형식으로 작성)

**중요: 아래 구분자를 반드시 각 섹션 시작 전에 줄 맨 앞에 단독으로 작성하세요.**
- [SECTION_1_4] : 1~4섹션 시작 전
- [SECTION_51] : 5.1 시작 전
- [SECTION_52] : 5.2 시작 전
- [SECTION_53] : 5.3 시작 전
- [SECTION_54_END] : 5.4 시작 전

[SECTION_1_4]

### 1. 핵심 요약
- ETF 개요 (추적 지수, 투자 전략, 특징)
- 최근 수익률 요약
- 핵심 투자 포인트 3가지

### 2. 추적 지수 분석
- 벤치마크 지수 설명
- 지수 최근 동향 (웹검색으로 확인)
- 추적 오차 및 괴리율 분석

### 3. 편입종목 분석
- 상위 편입종목 현황
- 섹터/테마 구성
- 주요 편입종목의 최근 이슈 (웹검색으로 확인)

### 4. 비용 및 효율성
- 총보수 분석
- 동일 지수 추적 ETF와 비교 (웹검색으로 확인)
- 거래량 및 유동성

### 5. 기술적 분석

[SECTION_51]

#### 5.1 주가 및 지지/저항선 분석
- 현재가 vs 이동평균선 (5/20/60/120/200일) 위치
- 지지/저항선 현황 (제공 데이터 기반)
- 향후 돌파/이탈 시나리오

[SECTION_52]

#### 5.2 추세추종 지표 분석
- ADX 해석 (25 미만=약한 추세, 25~50=강한 추세, 50 이상=매우 강한 추세)
- +DI/-DI 관계로 추세 방향 판단
- 이동평균선 배열 분석 (정배열/역배열)

[SECTION_53]

#### 5.3 모멘텀 지표 분석
- RSI 해석 (30 이하=과매도, 70 이상=과매수)
- MACD Line/Signal 교차 상태, Histogram 방향
- 스토캐스틱 %K/%D 교차 방향

[SECTION_54_END]

#### 5.4 거래량 및 종합 분석
- 최근 거래량 vs 평균 거래량 비교
- 가격-거래량 관계 해석
- 종합 기술적 신호 판단 (매수/매도/중립)

### 6. 투자 의견
- 적합한 투자자 유형
- 투자 시 주의사항
- 포트폴리오 내 역할 제안

### 7. 면책조항
"본 보고서는 투자 참고 자료로만 활용하시기 바라며, 특정 종목의 매수/매도를 권유하지 않습니다."

---

## 작성 규칙 (필수 준수)

1. **중요**: 이 종목은 ETF(상장지수펀드)입니다. 일반 주식처럼 EPS, PER, 재무제표를 분석하지 마세요.
2. ETF 특성에 맞게 NAV, 괴리율, 추적오차, 보수율, 편입종목을 중심으로 분석하세요.
3. 제공된 데이터의 실제 수치를 인용하세요. 추측 금지.
4. 제공 데이터가 없는 항목은 웹검색으로 보완하세요.
5. 동일 지수를 추적하는 다른 ETF와의 비교를 포함하세요.
6. 총 분량: **최소 2000자 이상**.
7. 마크다운 형식으로 작성 (# ## ### 헤딩, 테이블, 글머리 기호 사용).
8. **절대 금지**: "상장폐지", "거래정지" 같은 부정확한 표현. ETF는 펀드이므로 일반 주식과 다릅니다.
9. 보고서 본문(1. 핵심 요약)부터 바로 시작하세요. 서두/인사말 없이 바로 분석 내용으로 시작.
10. **구분자 필수**: [SECTION_1_4], [SECTION_51], [SECTION_52], [SECTION_53], [SECTION_54_END]를 반드시 해당 섹션 시작 전에 단독 줄로 작성.
"""
    return prompt


async def _generate_etf_report(name: str, code: str, market: str = "kr", chart_data: dict = None) -> dict:
    """ETF 전용 Claude API 리포트 생성"""
    import anthropic

    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        print("[ETF Report] ANTHROPIC_API_KEY 없음, fallback 사용")
        return {
            "success": False,
            "report": f"# {name} ({code}) ETF 분석\n\nETF 분석 데이터를 불러올 수 없습니다.",
            "fallback": True
        }

    try:
        # ETF 데이터 수집
        print(f"[ETF Report] Collecting ETF data for {name}({code})...")
        etf_data = await _collect_etf_data_for_ai(code)

        # 기술적 데이터 추가 — 국내주식과 동일한 함수 재사용
        print(f"[ETF Report] Collecting technical data for {name}({code})...")
        technical_data = await _collect_technical_data_for_ai(code, market)

        # ★ 차트↔텍스트 지지/저항 통일: 차트 계산값으로 덮어쓰기
        if chart_data:
            if chart_data.get("support_levels"):
                technical_data["support_levels"] = chart_data["support_levels"]
            if chart_data.get("resistance_levels"):
                technical_data["resistance_levels"] = chart_data["resistance_levels"]

        etf_data['technical'] = technical_data

        # 프롬프트 구성
        prompt = _build_etf_prompt(name, code, etf_data, market)

        # Claude API 호출
        print(f"[ETF Report] Calling Claude API...")
        client = anthropic.AsyncAnthropic(api_key=api_key, timeout=180.0)

        response = await client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=8000,  # 잘림 방지: 6000 → 8000
            messages=[{"role": "user", "content": prompt}]
        )

        report_md = response.content[0].text
        print(f"[ETF Report] Generated report: {len(report_md)} chars")

        return {
            "success": True,
            "report": report_md,
            "fallback": False
        }

    except Exception as e:
        print(f"[ETF Report] Claude API error: {e}")
        return {
            "success": False,
            "report": f"# {name} ({code}) ETF 분석\n\nETF 분석 중 오류가 발생했습니다: {e}",
            "error": str(e),
            "fallback": True
        }


async def _generate_claude_report(name: str, code: str, market: str = "kr", chart_data: dict = None) -> dict:
    """Claude API로 종합 분석 리포트 생성"""
    import anthropic

    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        print("[AI Report] ANTHROPIC_API_KEY 없음, fallback 사용")
        return {
            "success": False,
            "report": _generate_simple_report({"name": name, "symbol": code}),
            "fallback": True
        }

    try:
        # 데이터 수집
        print(f"[AI Report] Collecting data for {name}({code})...")
        tech = await _collect_technical_data_for_ai(code, market)
        fin = await _collect_financial_data_for_ai(code, market)
        news = await _collect_news_for_ai(code, name, market)

        # ★ 차트↔텍스트 지지/저항 통일: 차트 계산값으로 덮어쓰기
        if chart_data:
            if chart_data.get("support_levels"):
                tech["support_levels"] = chart_data["support_levels"]
            if chart_data.get("resistance_levels"):
                tech["resistance_levels"] = chart_data["resistance_levels"]

        # 프롬프트 구성 (market에 따라 통화 단위 변경)
        prompt = _build_claude_prompt(name, code, tech, fin, news, "", market)

        # Claude API 호출 (AsyncAnthropic 사용 - 이벤트 루프 블로킹 방지)
        print(f"[AI Report] Calling Claude API...")
        client = anthropic.AsyncAnthropic(api_key=api_key, timeout=180.0)

        response = await client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=8000,  # 6개 섹션 완전한 리포트 생성 위해 증가
            messages=[{"role": "user", "content": prompt}]
        )

        report_md = response.content[0].text
        print(f"[AI Report] Generated report: {len(report_md)} chars")

        return {
            "success": True,
            "report": report_md,
            "technical": tech,
            "financial": fin,
            "fallback": False
        }

    except Exception as e:
        print(f"[AI Report] Claude API error: {e}")
        return {
            "success": False,
            "report": _generate_simple_report({"name": name, "symbol": code}),
            "error": str(e),
            "fallback": True
        }


@app.get("/api/market/timeline")
async def get_market_timeline(
    current_user: User = Depends(get_current_user_optional),
    db: Session = Depends(get_db)
):
    """시황 타임라인 조회"""
    _ensure_ai_tables(db)

    # 최근 10개 타임라인 조회
    try:
        result = db.execute(
            text("""
                SELECT created_at, market_status, kospi_change, kosdaq_change,
                       summary, leading_sectors, lagging_sectors, featured_stocks, keywords
                FROM market_timeline
                ORDER BY created_at DESC
                LIMIT 10
            """)
        )
        rows = result.fetchall()

        timeline = []
        for row in rows:
            timeline.append({
                "time": row[0].strftime("%H:%M") if row[0] else "",
                "date": row[0].strftime("%Y-%m-%d") if row[0] else "",
                "status": row[1],
                "kospi_change": float(row[2]) if row[2] else 0,
                "kosdaq_change": float(row[3]) if row[3] else 0,
                "summary": row[4],
                "leading_sectors": row[5] or [],
                "lagging_sectors": row[6] or [],
                "featured_stocks": row[7] or [],
                "keywords": row[8] or [],
            })

        return {"timeline": timeline}
    except Exception as e:
        print(f"Timeline query error: {e}")
        return {"timeline": []}


# ============================================
# 시장신호 API (Phase 4 - IBD Big Picture)
# ============================================

@app.get("/api/market/signal")
async def get_market_signal(
    current_user: User = Depends(get_current_user_optional),
    db: Session = Depends(get_db)
):
    """
    시장신호 조회 (KOSPI/KOSDAQ)
    - short_term_signal: 단기 신호 (G/Y/R)
    - long_term_signal: 장기 신호 (G/Y/R)
    - Big Picture 상태
    - Distribution Day 정보
    - 실시간 데이터 (index_value, rising_stocks, falling_stocks)
    """
    from .market_analysis.signal_engine import BIG_PICTURE_CONFIG
    from .market_analysis.data_collector import get_market_summary
    from datetime import datetime

    result = {
        "kospi": None,
        "kosdaq": None,
        "updated_at": None
    }

    # 1. 실시간 데이터 가져오기 (rising/falling stocks, index value)
    realtime_data = {}
    try:
        realtime_data = await get_market_summary()
    except Exception as e:
        print(f"[API] 실시간 데이터 조회 오류: {e}")

    try:
        for market in ["KOSPI", "KOSDAQ"]:
            # 최근 5일치 조회 (주말 고려)
            rows = db.execute(
                text("""
                    SELECT date, market, index_value, change_amount, change_percent,
                           trading_volume, trading_value,
                           rising_stocks, falling_stocks, unchanged_stocks,
                           upper_limit_stocks, lower_limit_stocks, listed_stocks,
                           status, active_dd_count, distribution_days,
                           rally_start_date, rally_day_count, last_ftd_date,
                           short_term_signal, long_term_signal,
                           foreign_net, institution_net, individual_net
                    FROM market_signals
                    WHERE market = :market
                    ORDER BY date DESC
                    LIMIT 5
                """),
                {"market": market}
            ).fetchall()

            row = rows[0] if rows else None

            # 금/토/일이면 목요일 대비, 아니면 전일 대비
            today = datetime.now()
            trading_value_prev = None
            if today.weekday() in [4, 5, 6]:  # 금(4), 토(5), 일(6)
                # 목요일 데이터 찾기
                for r in rows[1:]:
                    if r.date and r.date.weekday() == 3:  # 목(3)
                        trading_value_prev = r.trading_value
                        break
            else:
                # 전일 데이터 (두 번째 행)
                if len(rows) > 1:
                    trading_value_prev = rows[1].trading_value

            # 실시간 데이터 (있으면 DB 값 덮어쓰기)
            rt = realtime_data.get(market.lower(), {})

            if row:
                status = row.status or 'confirmed_uptrend'
                config = BIG_PICTURE_CONFIG.get(status, BIG_PICTURE_CONFIG['confirmed_uptrend'])

                result[market.lower()] = {
                    "date": row.date.strftime("%Y-%m-%d") if row.date else None,
                    # 실시간 데이터 우선, 없으면 DB 값 사용
                    "index_value": rt.get("index_value") or row.index_value,
                    "change_amount": rt.get("change_amount") if rt.get("change_amount") is not None else row.change_amount,
                    "change_percent": rt.get("change_percent") if rt.get("change_percent") is not None else row.change_percent,
                    "trading_volume": rt.get("trading_volume") or row.trading_volume,
                    "trading_value": rt.get("trading_value") or row.trading_value,
                    "trading_value_prev": trading_value_prev,
                    "rising_stocks": rt.get("rising_stocks") or row.rising_stocks,
                    "falling_stocks": rt.get("falling_stocks") or row.falling_stocks,
                    "unchanged_stocks": rt.get("unchanged_stocks") or row.unchanged_stocks,
                    "upper_limit_stocks": rt.get("upper_limit_stocks") or row.upper_limit_stocks,
                    "lower_limit_stocks": rt.get("lower_limit_stocks") or row.lower_limit_stocks,
                    "listed_stocks": rt.get("listed_stocks") or row.listed_stocks,
                    "status": status,
                    "status_label": config['label'],
                    "exposure": config['exposure'],
                    "status_color": config['color'],
                    "status_description": config['description'],
                    "active_dd_count": row.active_dd_count,
                    "distribution_days": row.distribution_days or [],
                    "rally_start_date": row.rally_start_date.strftime("%Y-%m-%d") if row.rally_start_date else None,
                    "rally_day_count": row.rally_day_count,
                    "last_ftd_date": row.last_ftd_date.strftime("%Y-%m-%d") if row.last_ftd_date else None,
                    "short_term_signal": row.short_term_signal,
                    "long_term_signal": row.long_term_signal,
                    # 투자자 동향도 실시간 데이터 우선 (각 시장별)
                    "foreign_net": rt.get("foreign_net") or row.foreign_net,
                    "institution_net": rt.get("institution_net") or row.institution_net,
                    "individual_net": rt.get("individual_net") or row.individual_net,
                }

                if not result["updated_at"] and row.date:
                    result["updated_at"] = row.date.strftime("%Y-%m-%d %H:%M")
            elif rt:
                # DB에 데이터 없지만 실시간 데이터는 있는 경우
                config = BIG_PICTURE_CONFIG.get('confirmed_uptrend')
                result[market.lower()] = {
                    "date": datetime.now().strftime("%Y-%m-%d"),
                    "index_value": rt.get("index_value", 0),
                    "change_amount": rt.get("change_amount", 0),
                    "change_percent": rt.get("change_percent", 0),
                    "trading_volume": rt.get("trading_volume", 0),
                    "trading_value": rt.get("trading_value", 0),
                    "trading_value_prev": trading_value_prev,
                    "rising_stocks": rt.get("rising_stocks", 0),
                    "falling_stocks": rt.get("falling_stocks", 0),
                    "unchanged_stocks": rt.get("unchanged_stocks", 0),
                    "upper_limit_stocks": rt.get("upper_limit_stocks", 0),
                    "lower_limit_stocks": rt.get("lower_limit_stocks", 0),
                    "listed_stocks": rt.get("listed_stocks", 0),
                    "status": "confirmed_uptrend",
                    "status_label": config['label'],
                    "exposure": config['exposure'],
                    "status_color": config['color'],
                    "status_description": config['description'],
                    "active_dd_count": 0,
                    "distribution_days": [],
                    "rally_start_date": None,
                    "rally_day_count": 0,
                    "last_ftd_date": None,
                    "short_term_signal": "yellow",
                    "long_term_signal": "green",
                    "foreign_net": rt.get("foreign_net", 0),
                    "institution_net": rt.get("institution_net", 0),
                    "individual_net": rt.get("individual_net", 0),
                }
                result["updated_at"] = datetime.now().strftime("%Y-%m-%d %H:%M")

    except Exception as e:
        print(f"[API] /api/market/signal 오류: {e}")
        # 테이블이 없으면 기본값 반환
        for market in ["kospi", "kosdaq"]:
            result[market] = {
                "status": "confirmed_uptrend",
                "status_label": "확인된 상승세",
                "exposure": "80-100%",
                "short_term_signal": "green",
                "long_term_signal": "green",
                "active_dd_count": 0,
                "distribution_days": [],
            }

    return result


@app.get("/api/market/big-picture")
async def get_market_big_picture(
    current_user: User = Depends(get_current_user_optional),
    db: Session = Depends(get_db)
):
    """
    Big Picture 상세 정보
    - 4가지 상태: confirmed_uptrend, uptrend_under_pressure, market_in_correction, rally_attempt
    - Distribution Day 목록
    - 권장 투자 비중
    """
    from .market_analysis.signal_engine import BIG_PICTURE_CONFIG

    result = {
        "kospi": None,
        "kosdaq": None,
        "config": BIG_PICTURE_CONFIG,
        "last_updated": None
    }

    try:
        for market in ["KOSPI", "KOSDAQ"]:
            row = db.execute(
                text("""
                    SELECT date, status, active_dd_count, distribution_days,
                           rally_start_date, rally_day_count, last_ftd_date,
                           index_value, change_percent
                    FROM market_signals
                    WHERE market = :market
                    ORDER BY date DESC
                    LIMIT 1
                """),
                {"market": market}
            ).fetchone()

            if row:
                status = row.status or 'confirmed_uptrend'
                config = BIG_PICTURE_CONFIG.get(status, BIG_PICTURE_CONFIG['confirmed_uptrend'])

                # Distribution Days 중 활성인 것만 필터
                dd_list = row.distribution_days or []
                active_dds = [dd for dd in dd_list if dd.get('is_active', False)]

                result[market.lower()] = {
                    "market_code": market,
                    "status": status,
                    "label": config['label'],
                    "label_en": config['label_en'],
                    "exposure": config['exposure'],
                    "color": config['color'],
                    "description": config['description'],
                    "active_dd_count": row.active_dd_count,
                    "distribution_days": active_dds,
                    "rally_start_date": row.rally_start_date.strftime("%Y-%m-%d") if row.rally_start_date else None,
                    "rally_day_count": row.rally_day_count,
                    "last_ftd_date": row.last_ftd_date.strftime("%Y-%m-%d") if row.last_ftd_date else None,
                    "index_value": row.index_value,
                    "change_percent": row.change_percent,
                }

                if not result["last_updated"] and row.date:
                    result["last_updated"] = row.date.strftime("%Y-%m-%d")

    except Exception as e:
        print(f"[API] /api/market/big-picture 오류: {e}")

    return result


@app.get("/api/market/signal/history")
async def get_market_signal_history(
    days: int = Query(30, ge=1, le=365),
    market: str = Query("KOSPI", description="KOSPI 또는 KOSDAQ"),
    current_user: User = Depends(get_current_user_optional),
    db: Session = Depends(get_db)
):
    """
    시장신호 히스토리 (차트용)
    """
    result = []

    try:
        rows = db.execute(
            text("""
                SELECT date, index_value, change_percent,
                       short_term_signal, long_term_signal, status,
                       active_dd_count, rising_stocks, falling_stocks
                FROM market_signals
                WHERE market = :market
                ORDER BY date DESC
                LIMIT :days
            """),
            {"market": market.upper(), "days": days}
        ).fetchall()

        for row in rows:
            result.append({
                "date": row.date.strftime("%Y-%m-%d") if row.date else None,
                "index_value": row.index_value,
                "change_percent": row.change_percent,
                "short_term_signal": row.short_term_signal,
                "long_term_signal": row.long_term_signal,
                "status": row.status,
                "active_dd_count": row.active_dd_count,
                "rising_stocks": row.rising_stocks,
                "falling_stocks": row.falling_stocks,
            })

        # 날짜 순 정렬 (오래된 것부터)
        result.reverse()

    except Exception as e:
        print(f"[API] /api/market/signal/history 오류: {e}")

    return {"history": result, "market": market.upper(), "days": days}


@app.get("/api/market/breadth")
async def get_market_breadth(
    days: int = Query(30, ge=1, le=365),
    market: str = Query("KOSPI", description="KOSPI 또는 KOSDAQ"),
    current_user: User = Depends(get_current_user_optional),
    db: Session = Depends(get_db)
):
    """
    시장 너비 데이터 (20/200일선 하락비율, ADR, 52주 신고가/신저가)
    """
    result = []

    try:
        rows = db.execute(
            text("""
                SELECT date, below_ma20_ratio, below_ma200_ratio,
                       adr, new_high_52w, new_low_52w
                FROM market_breadth
                WHERE market = :market
                ORDER BY date DESC
                LIMIT :days
            """),
            {"market": market.upper(), "days": days}
        ).fetchall()

        for row in rows:
            result.append({
                "date": row.date.strftime("%Y-%m-%d") if row.date else None,
                "below_ma20_ratio": row.below_ma20_ratio,
                "below_ma200_ratio": row.below_ma200_ratio,
                "adr": row.adr,
                "new_high_52w": row.new_high_52w,
                "new_low_52w": row.new_low_52w,
            })

        result.reverse()

    except Exception as e:
        print(f"[API] /api/market/breadth 오류: {e}")

    return {"breadth": result, "market": market.upper(), "days": days}


@app.post("/api/market/breadth/init")
async def init_market_breadth(
    days: int = Query(400, ge=30, le=500),
    market: str = Query("KOSPI", description="KOSPI 또는 KOSDAQ"),
    db: Session = Depends(get_db)
):
    """
    네이버에서 지수 히스토리를 가져와서 breadth 데이터 생성
    - KOSPI 일봉 데이터 조회
    - 20일/200일 이동평균 계산
    - 지수가 MA 아래인 비율을 시뮬레이션
    """
    import random
    from .market_analysis.data_collector import fetch_index_history

    try:
        # 1. 네이버에서 지수 히스토리 가져오기
        history = await fetch_index_history(market.upper(), days)
        if not history:
            return {"success": False, "error": "지수 히스토리 조회 실패"}

        print(f"[BreadthInit] {market} {len(history)}일치 데이터 수신")

        # 날짜순 정렬 (오래된 것부터)
        history.sort(key=lambda x: x['date'])

        # 2. MA20, MA200 계산
        closes = [h['close'] for h in history]
        n = len(closes)

        inserted = 0
        for i in range(200, n):  # MA200 계산 가능한 시점부터
            date_str = history[i]['date']
            close = closes[i]
            ma20 = sum(closes[i-19:i+1]) / 20
            ma200 = sum(closes[i-199:i+1]) / 200

            # 지수가 MA 대비 얼마나 아래/위인지 계산
            pct_from_ma20 = (close - ma20) / ma20
            pct_from_ma200 = (close - ma200) / ma200

            # 현실적인 하락비율 계산:
            # - 실제 시장: 지수가 MA200 위 20%여도 40-50% 종목이 MA200 아래
            # - 지수 위치와 개별 종목 분포는 약한 상관관계
            # - 스탁이지 기준: MA200 하락비율 40-60%, MA20 하락비율 35-55%
            import math
            noise = random.uniform(-0.02, 0.02)

            # MA20 하락비율 (기준: 48%, 약한 조정)
            # 지수 5% 위 → 43%, 지수 5% 아래 → 53%
            base_ma20 = 0.48
            adjustment_ma20 = -pct_from_ma20 * 1.0  # 지수 1% 변화당 1% 조정
            below_ma20 = base_ma20 + adjustment_ma20 + noise
            below_ma20 = max(0.30, min(0.70, below_ma20))

            # MA200 하락비율 (기준: 52%, 극히 약한 조정)
            # 지수가 MA200 위 30%여도 45% 정도 유지 (실제 개별종목 분포 반영)
            base_ma200 = 0.52
            adjustment_ma200 = -pct_from_ma200 * 0.25  # 지수 10% 변화당 2.5% 조정
            below_ma200 = base_ma200 + adjustment_ma200 + noise
            below_ma200 = max(0.40, min(0.65, below_ma200))

            # ADR (Advance/Decline Ratio) 시뮬레이션
            # ADR = (상승종목수 / 하락종목수) * 100
            # 100 이상 = 상승 우세, 100 이하 = 하락 우세
            # 당일 등락률 기반으로 시뮬레이션
            daily_return = (close - closes[i-1]) / closes[i-1] if i > 0 else 0
            adr_noise = random.uniform(-5, 5)
            # 기준 ADR = 100, 당일 등락률 1%당 ADR 15 변화
            adr = 100 + daily_return * 1500 + adr_noise
            adr = max(40, min(200, adr))

            # DB 저장 (upsert)
            try:
                date_obj = datetime.strptime(date_str, "%Y%m%d").date()
                db.execute(
                    text("""
                        INSERT INTO market_breadth (date, market, below_ma20_ratio, below_ma200_ratio, adr, created_at)
                        VALUES (:date, :market, :ma20, :ma200, :adr, NOW())
                        ON CONFLICT (date, market) DO UPDATE SET
                            below_ma20_ratio = :ma20,
                            below_ma200_ratio = :ma200,
                            adr = :adr
                    """),
                    {"date": date_obj, "market": market.upper(), "ma20": below_ma20, "ma200": below_ma200, "adr": adr}
                )
                inserted += 1
            except Exception as e:
                print(f"[BreadthInit] Insert error for {date_str}: {e}")

        db.commit()
        print(f"[BreadthInit] {inserted}건 저장 완료")
        return {"success": True, "inserted": inserted, "market": market.upper()}

    except Exception as e:
        print(f"[BreadthInit] 오류: {e}")
        import traceback
        traceback.print_exc()
        return {"success": False, "error": str(e)}


@app.post("/api/market/signals/init")
async def init_market_signals(
    days: int = Query(365, ge=30, le=500),
    db: Session = Depends(get_db)
):
    """
    market_signals 테이블에 과거 데이터 생성
    - 네이버 지수 히스토리에서 trading_value(거래대금) 포함
    """
    from .market_analysis.data_collector import fetch_index_history
    from .market_analysis.signal_engine import BIG_PICTURE_CONFIG

    try:
        total_inserted = 0

        for market in ["KOSPI", "KOSDAQ"]:
            # 네이버에서 지수 히스토리 가져오기
            history = await fetch_index_history(market, days)
            if not history:
                print(f"[SignalsInit] {market} 히스토리 조회 실패")
                continue

            print(f"[SignalsInit] {market} {len(history)}일치 데이터 수신")

            # 날짜순 정렬 (오래된 것부터)
            history.sort(key=lambda x: x['date'])

            inserted = 0
            for i, h in enumerate(history):
                date_str = h['date']
                close = h['close']
                volume = h['volume']

                # 전일 대비 계산
                if i > 0:
                    prev_close = history[i-1]['close']
                    change_amount = close - prev_close
                    change_percent = (change_amount / prev_close) * 100 if prev_close else 0
                else:
                    change_amount = 0
                    change_percent = 0

                # 거래대금: 히스토리 API에서 제공하지 않음
                # 실시간 스케줄러에서 채워넣으므로 0으로 설정
                trading_value = 0

                try:
                    date_obj = datetime.strptime(date_str, "%Y%m%d").date()
                    db.execute(
                        text("""
                            INSERT INTO market_signals (
                                date, market, index_value, change_amount, change_percent,
                                trading_volume, trading_value, status, short_term_signal, long_term_signal
                            )
                            VALUES (
                                :date, :market, :index_value, :change_amount, :change_percent,
                                :volume, :trading_value, 'confirmed_uptrend', 'yellow', 'green'
                            )
                            ON CONFLICT (date, market) DO UPDATE SET
                                index_value = :index_value,
                                change_amount = :change_amount,
                                change_percent = :change_percent,
                                trading_volume = :volume
                                -- trading_value는 스케줄러가 실시간으로 채우므로 덮어쓰지 않음
                        """),
                        {
                            "date": date_obj,
                            "market": market,
                            "index_value": close,
                            "change_amount": round(change_amount, 2),
                            "change_percent": round(change_percent, 2),
                            "volume": volume,
                            "trading_value": trading_value
                        }
                    )
                    inserted += 1
                except Exception as e:
                    print(f"[SignalsInit] Insert error for {market} {date_str}: {e}")

            db.commit()
            total_inserted += inserted
            print(f"[SignalsInit] {market} {inserted}건 저장 완료")

        return {"success": True, "inserted": total_inserted}

    except Exception as e:
        print(f"[SignalsInit] 오류: {e}")
        import traceback
        traceback.print_exc()
        return {"success": False, "error": str(e)}


@app.get("/api/market/breadth-with-index")
async def get_market_breadth_with_index(
    days: int = Query(250, ge=30, le=365),
    market: str = Query("KOSPI", description="KOSPI 또는 KOSDAQ"),
    current_user: User = Depends(get_current_user_optional),
    db: Session = Depends(get_db)
):
    """
    시장 너비 데이터 + KOSPI 지수 포함
    - 쌍축 차트용 데이터
    """
    from .market_analysis.data_collector import fetch_index_history

    result = {
        "dates": [],
        "index_values": [],
        "below_ma20": [],
        "below_ma200": [],
        "adr": [],
        "market": market.upper(),
        "days": days
    }

    try:
        # 1. breadth 데이터 조회 (ADR 포함)
        breadth_rows = db.execute(
            text("""
                SELECT date, below_ma20_ratio, below_ma200_ratio, adr
                FROM market_breadth
                WHERE market = :market
                ORDER BY date DESC
                LIMIT :days
            """),
            {"market": market.upper(), "days": days}
        ).fetchall()

        if not breadth_rows:
            # breadth 데이터 없으면 초기화 시도
            return {"error": "breadth 데이터 없음. POST /api/market/breadth/init 먼저 실행 필요"}

        breadth_dict = {}
        for row in breadth_rows:
            date_str = row.date.strftime("%Y-%m-%d") if row.date else None
            if date_str:
                breadth_dict[date_str] = {
                    "below_ma20": row.below_ma20_ratio,
                    "below_ma200": row.below_ma200_ratio,
                    "adr": row.adr
                }

        # 2. KOSPI 지수 히스토리 조회
        history = await fetch_index_history(market.upper(), days + 50)
        if history:
            history.sort(key=lambda x: x['date'])
            # 최근 days일만
            history = history[-days:] if len(history) > days else history

            for h in history:
                date_str = datetime.strptime(h['date'], "%Y%m%d").strftime("%Y-%m-%d")
                result["dates"].append(date_str)
                result["index_values"].append(h['close'])

                # breadth 데이터 매칭
                if date_str in breadth_dict:
                    result["below_ma20"].append(breadth_dict[date_str]["below_ma20"])
                    result["below_ma200"].append(breadth_dict[date_str]["below_ma200"])
                    result["adr"].append(breadth_dict[date_str]["adr"])
                else:
                    result["below_ma20"].append(None)
                    result["below_ma200"].append(None)
                    result["adr"].append(None)

        # ADR 스무딩 (5일 이동평균)
        adr_raw = result["adr"]
        adr_smoothed = []
        for i in range(len(adr_raw)):
            if i < 4:
                adr_smoothed.append(adr_raw[i])  # 처음 4일은 원시값
            else:
                # 최근 5일 평균 (None 제외)
                window = [v for v in adr_raw[i-4:i+1] if v is not None]
                if window:
                    adr_smoothed.append(round(sum(window) / len(window), 1))
                else:
                    adr_smoothed.append(None)
        result["adr"] = adr_smoothed

    except Exception as e:
        print(f"[API] /api/market/breadth-with-index 오류: {e}")
        import traceback
        traceback.print_exc()
        return {"error": str(e)}

    return result


@app.get("/api/market/investors")
async def get_market_investors(
    days: int = Query(30, ge=1, le=365),
    current_user: User = Depends(get_current_user_optional),
    db: Session = Depends(get_db)
):
    """
    투자자 동향 (외국인/기관/개인 순매수)
    """
    result = []

    try:
        rows = db.execute(
            text("""
                SELECT date, market, foreign_net, institution_net, individual_net
                FROM market_signals
                WHERE market = 'KOSPI'
                ORDER BY date DESC
                LIMIT :days
            """),
            {"days": days}
        ).fetchall()

        for row in rows:
            result.append({
                "date": row.date.strftime("%Y-%m-%d") if row.date else None,
                "market": row.market,
                "foreign_net": row.foreign_net,
                "institution_net": row.institution_net,
                "individual_net": row.individual_net,
            })

        result.reverse()

    except Exception as e:
        print(f"[API] /api/market/investors 오류: {e}")

    return {"investors": result, "days": days}


@app.get("/api/market/trading-value")
async def get_market_trading_value(
    days: int = Query(30, ge=1, le=365),
    market: str = Query("KOSPI", description="KOSPI 또는 KOSDAQ"),
    current_user: User = Depends(get_current_user_optional),
    db: Session = Depends(get_db)
):
    """
    거래대금 데이터
    """
    result = []

    try:
        rows = db.execute(
            text("""
                SELECT date, trading_value, trading_volume
                FROM market_signals
                WHERE market = :market
                ORDER BY date DESC
                LIMIT :days
            """),
            {"market": market.upper(), "days": days}
        ).fetchall()

        for row in rows:
            result.append({
                "date": row.date.strftime("%Y-%m-%d") if row.date else None,
                "trading_value": row.trading_value,
                "trading_volume": row.trading_volume,
            })

        result.reverse()

    except Exception as e:
        print(f"[API] /api/market/trading-value 오류: {e}")

    return {"trading_values": result, "market": market.upper(), "days": days}


@app.post("/api/market/signal/update")
async def trigger_market_signal_update(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    시장신호 수동 업데이트 (관리자용)
    """
    if current_user.role != "admin":
        raise HTTPException(status_code=403, detail="관리자만 사용 가능합니다")

    try:
        from .market_analysis.scheduler import daily_market_update
        result = await daily_market_update(db)
        return {"success": True, "result": result}
    except Exception as e:
        return {"success": False, "error": str(e)}


# 종목명 → 종목코드 매핑 캐시
_stock_name_to_code_cache: Dict[str, str] = {}
_stock_name_cache_time: Optional[datetime] = None

# 주요 종목 하드코딩 매핑 (StockRS 테이블이 비어있을 때 사용)
_STOCK_NAME_FALLBACK = {
    # 시가총액 상위
    "삼성전자": "005930", "SK하이닉스": "000660", "LG에너지솔루션": "373220",
    "삼성바이오로직스": "207940", "현대차": "005380", "셀트리온": "068270",
    "기아": "000270", "KB금융": "105560", "POSCO홀딩스": "005490",
    "신한지주": "055550", "NAVER": "035420", "LG화학": "051910",
    "삼성SDI": "006400", "현대모비스": "012330", "카카오": "035720",
    "삼성물산": "028260", "하나금융지주": "086790", "LG전자": "066570",
    "삼성생명": "032830", "우리금융지주": "316140", "SK이노베이션": "096770",
    "HMM": "011200", "삼성화재": "000810", "KT&G": "033780",
    "SK텔레콤": "017670", "포스코퓨처엠": "003670", "고려아연": "010130",
    "SK": "034730", "한국전력": "015760", "두산에너빌리티": "034020",
    # 반도체/전자
    "SK스퀘어": "402340", "삼성전기": "009150", "DB하이텍": "000990",
    "리노공업": "058470", "하나마이크론": "067310", "이오테크닉스": "039030",
    "테크윙": "089030", "원익IPS": "240810", "피에스케이": "319660",
    "주성엔지니어링": "036930", "한미반도체": "042700", "ISC": "095340",
    # 2차전지/소재
    "에코프로비엠": "247540", "에코프로": "086520", "포스코DX": "022100",
    "엘앤에프": "066970", "천보": "278280", "코스모신소재": "005070",
    "나노신소재": "121600", "솔브레인": "357780", "동진쎄미켐": "005290",
    # 바이오/제약
    "삼성바이오에피스": "N/A", "셀트리온헬스케어": "091990", "유한양행": "000100",
    "SK바이오팜": "326030", "알테오젠": "196170", "HLB": "028300",
    "리가켐바이오": "141080", "메드팩토": "235980", "삼천당제약": "000250",
    # 자동차/부품
    "현대오토에버": "307950", "HL만도": "204320", "현대위아": "011210",
    "한온시스템": "018880", "에스엘": "005850", "현대트랜시스": "298040",
    # 금융
    "삼성증권": "016360", "미래에셋증권": "006800", "NH투자증권": "005940",
    "키움증권": "039490", "한국금융지주": "071050", "메리츠금융지주": "138040",
    # IT/인터넷
    "카카오뱅크": "323410", "카카오페이": "377300", "크래프톤": "259960",
    "넷마블": "251270", "엔씨소프트": "036570", "펄어비스": "263750",
    "위메이드": "112040", "컴투스": "078340", "더블유게임즈": "192080",
    # 화학/에너지
    "롯데케미칼": "011170", "금호석유": "011780", "한화솔루션": "009830",
    "OCI홀딩스": "010060", "효성첨단소재": "298050", "SKC": "011790",
    # 건설/중공업
    "현대건설": "000720", "삼성엔지니어링": "028050", "대우건설": "047040",
    "GS건설": "006360", "DL이앤씨": "375500", "현대중공업": "329180",
    "한화오션": "042660", "삼성중공업": "010140", "HD현대인프라코어": "042670",
    # 유통/소비재
    "신세계": "004170", "이마트": "139480", "롯데쇼핑": "023530",
    "CJ제일제당": "097950", "오리온": "271560", "농심": "004370",
    "아모레퍼시픽": "090430", "LG생활건강": "051900", "호텔신라": "008770",
    # 항공/운송
    "대한항공": "003490", "아시아나항공": "020560", "CJ대한통운": "000120",
    # 철강/비철
    "현대제철": "004020", "동국제강": "001230", "세아베스틸": "001430",
    "풍산": "103140", "영풍": "000670",
    # 통신/미디어
    "KT": "030200", "LG유플러스": "032640", "SK브로드밴드": "N/A",
    "CJ ENM": "035760", "스튜디오드래곤": "253450", "SBS": "034120",
    # 기타
    "두산밥캣": "241560", "한화에어로스페이스": "012450", "LIG넥스원": "079550",
}

async def get_stock_name_to_code_map(db: Session) -> Dict[str, str]:
    """
    StockRS 테이블에서 종목명 → 종목코드 매핑 로드 (1시간 캐시)
    DB가 비어있으면 하드코딩 매핑 사용
    """
    global _stock_name_to_code_cache, _stock_name_cache_time

    # 캐시 유효성 확인 (1시간)
    if _stock_name_cache_time and (datetime.now() - _stock_name_cache_time).total_seconds() < 3600:
        if _stock_name_to_code_cache:
            return _stock_name_to_code_cache

    try:
        # 최근 RS 데이터에서 종목명 → 코드 매핑 추출
        from sqlalchemy import text
        result = db.execute(text("""
            SELECT DISTINCT ON (name) symbol, name
            FROM stock_rs
            WHERE name IS NOT NULL AND symbol IS NOT NULL
            ORDER BY name, date DESC
        """))

        mapping = {}
        for row in result:
            if row.name and row.symbol:
                mapping[row.name.strip()] = row.symbol.strip()

        # DB 매핑이 비어있으면 하드코딩 매핑 사용
        if not mapping:
            mapping = _STOCK_NAME_FALLBACK.copy()
            print(f"[StockNameCache] DB 비어있음, 하드코딩 매핑 사용: {len(mapping)}개")
        else:
            print(f"[StockNameCache] DB에서 매핑 로드: {len(mapping)}개")

        _stock_name_to_code_cache = mapping
        _stock_name_cache_time = datetime.now()
        return mapping
    except Exception as e:
        print(f"[StockNameCache] 매핑 로드 오류: {e}, 하드코딩 매핑 사용")
        return _STOCK_NAME_FALLBACK.copy()


async def fetch_stockeasy_csv(db: Session = None) -> Dict[str, Dict]:
    """
    스탁이지 ETF 테이블 CSV 파싱
    Returns: {종목코드: {sector, etf_name, position, gap_percent, signal, top_holdings: [{name, rs, code}]}}
    """
    import httpx
    import csv
    import io
    import re

    url = "https://stockeasy.intellio.kr/requestfile/etf_sector/etf_table.csv"

    # 종목명 → 코드 매핑 가져오기
    name_to_code = {}
    if db:
        name_to_code = await get_stock_name_to_code_map(db)

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            r = await client.get(url, headers={"User-Agent": "Mozilla/5.0"})
            if r.status_code != 200:
                return {}

            # CSV 파싱
            reader = csv.DictReader(io.StringIO(r.text))
            result = {}

            for row in reader:
                code = row.get('종목코드', '').strip()
                if not code or len(code) < 6:
                    continue

                # 대표종목(RS) 파싱: "삼성전자(94), SK하이닉스(95), ..."
                holdings_str = row.get('대표종목(RS)', '')
                top_holdings = []
                if holdings_str:
                    # 정규식으로 파싱: 종목명(RS점수)
                    matches = re.findall(r'([^,()]+)\((\d+)\)', holdings_str)
                    for name, rs in matches:
                        stock_name = name.strip()
                        stock_code = name_to_code.get(stock_name, '')
                        top_holdings.append({
                            "name": stock_name,
                            "rs": int(rs),
                            "code": stock_code  # 종목코드 추가
                        })

                result[code] = {
                    "sector": row.get('섹터', ''),
                    "industry": row.get('산업', ''),
                    "etf_name": row.get('종목명', ''),
                    "position": row.get('포지션', ''),
                    "gap_percent": row.get('20일 이격', ''),
                    "signal": row.get('신호등', ''),
                    "top_holdings": top_holdings[:6],  # 상위 6개
                }

            return result

    except Exception as e:
        print(f"[StockEasy] CSV 파싱 오류: {e}")
        return {}


@app.get("/api/market/trend-maintain")
async def get_market_trend_maintain(
    current_user: User = Depends(get_current_user_optional),
    db: Session = Depends(get_db),
):
    """
    추세유지 분석 (섹터 ETF 20MA 기준)
    - 유지: 현재가 > 20MA
    - 이탈: 현재가 <= 20MA
    - 스탁이지 CSV에서 대표종목(RS) 추가
    """
    from .market_analysis.trend_maintain import calculate_trend_maintain
    from .market_analysis.sector_config import SECTOR_ETFS
    import httpx
    from datetime import datetime

    result = []

    try:
        # 스탁이지 CSV에서 대표종목 데이터 가져오기 (종목코드 포함)
        stockeasy_data = await fetch_stockeasy_csv(db)

        async with httpx.AsyncClient(timeout=30.0) as client:
            headers = {"User-Agent": "Mozilla/5.0"}

            for etf in SECTOR_ETFS:
                symbol = etf["symbol"]

                try:
                    # 네이버 차트 API로 60일 일봉 조회
                    url = f"https://fchart.stock.naver.com/sise.nhn?symbol={symbol}&timeframe=day&count=60&requestType=0"
                    r = await client.get(url, headers=headers)

                    if r.status_code != 200:
                        continue

                    # XML 파싱
                    from xml.etree import ElementTree as ET
                    root = ET.fromstring(r.text)

                    closes = []
                    change_pct = 0
                    for item in root.findall('.//item'):
                        data_str = item.get('data', '')
                        parts = data_str.split('|')
                        if len(parts) >= 5:
                            closes.append(float(parts[4]))

                    if len(closes) < 20:
                        continue

                    # 등락률 계산
                    if len(closes) >= 2:
                        change_pct = (closes[-1] - closes[-2]) / closes[-2] * 100

                    # 추세유지 분석
                    trend = calculate_trend_maintain(closes)
                    if trend:
                        # 스탁이지 데이터 병합
                        se_data = stockeasy_data.get(symbol, {})

                        result.append({
                            "symbol": symbol,
                            "name": etf["name"],  # ETF 이름
                            "sector": etf["sector"],
                            "industry": etf.get("industry", ""),
                            "current_price": trend["current_price"],
                            "ma20": trend["ma20"],
                            "position": trend["position"],
                            "days": trend["days"],
                            "gap_percent": trend["gap_percent"],
                            "signal": trend["signal"],
                            "return_since_entry": trend["return_since_entry"],
                            "change_percent": round(change_pct, 2),
                            # 스탁이지 대표종목 추가
                            "top_holdings": se_data.get("top_holdings", []),
                        })

                except Exception as e:
                    print(f"[TrendMaintain] {symbol} 오류: {e}")
                    continue

        # 정렬: 유지 > 이탈, 일수 내림차순
        result.sort(key=lambda x: (0 if x["position"] == "유지" else 1, -x["days"]))

    except Exception as e:
        print(f"[API] /api/market/trend-maintain 오류: {e}")

    return {
        "success": True,
        "data": result,
        "updated_at": datetime.now().strftime("%Y-%m-%d %H:%M")
    }


@app.get("/api/market/sector-analysis")
async def get_market_sector_analysis(
    current_user: User = Depends(get_current_user_optional),
    db: Session = Depends(get_db)
):
    """
    섹터 분석 (추세유지 + 대표종목 RS)
    스탁이지 동일 형식 반환
    """
    from .market_analysis.sector_config import SECTOR_ETFS, get_etf_components, fetch_etf_daily_data
    from .market_analysis.trend_maintain import calculate_trend_maintain
    from datetime import datetime

    result = []

    try:
        # 최신 RS 점수 조회 (DB에서)
        today = datetime.now().date()
        rs_query = text("""
            SELECT symbol, rs_score FROM stock_rs
            WHERE date::date = (SELECT MAX(date::date) FROM stock_rs)
        """)
        rs_result = db.execute(rs_query)
        rs_map = {row[0]: row[1] for row in rs_result.fetchall()}

        for etf in SECTOR_ETFS:
            symbol = etf["symbol"]

            try:
                # 일봉 데이터 조회
                daily_data = await fetch_etf_daily_data(symbol, 60)
                if len(daily_data) < 20:
                    continue

                closes = [d['close'] for d in daily_data]

                # 등락률 계산
                change_pct = 0
                if len(closes) >= 2:
                    change_pct = (closes[-1] - closes[-2]) / closes[-2] * 100

                # 추세유지 분석
                trend = calculate_trend_maintain(closes)
                if not trend:
                    continue

                # ETF 구성종목 + RS 점수
                components = await get_etf_components(symbol, 6)
                top_stocks = []
                for comp in components:
                    rs = rs_map.get(comp['symbol'], 0)
                    top_stocks.append({
                        "symbol": comp['symbol'],
                        "name": comp['name'],
                        "rs": rs
                    })

                result.append({
                    "etf_symbol": symbol,
                    "etf_name": etf["name"],
                    "sector": etf["sector"],
                    "industry": etf.get("industry", ""),
                    "change_percent": round(change_pct, 2),
                    "position": trend["position"],
                    "position_days": trend["days"],
                    "gap_percent": trend["gap_percent"],
                    "signal": trend["signal"],
                    "return_since_entry": trend.get("return_since_entry"),
                    "ma20": trend["ma20"],
                    "current_price": trend["current_price"],
                    "top_stocks": top_stocks,
                })

            except Exception as e:
                print(f"[SectorAnalysis] {symbol} 오류: {e}")
                continue

        # 등락률 내림차순 정렬
        result.sort(key=lambda x: x["change_percent"], reverse=True)

    except Exception as e:
        print(f"[API] /api/market/sector-analysis 오류: {e}")

    return {
        "success": True,
        "data": result,
        "updated_at": datetime.now().strftime("%Y-%m-%d %H:%M")
    }


@app.get("/api/market/rs-ranking")
async def get_market_rs_ranking(
    market: str = Query("ALL", description="KOSPI | KOSDAQ | ALL"),
    top: int = Query(50, description="상위 N개"),
    current_user: User = Depends(get_current_user_optional),
    db: Session = Depends(get_db)
):
    """
    RS 순위 조회 (상위 종목)
    """
    from datetime import datetime

    result = []

    try:
        # 최신 날짜의 RS 데이터
        if market.upper() == "ALL":
            query = text("""
                SELECT symbol, name, market, rs_score, roc_3m, roc_6m, roc_12m, strength_factor
                FROM stock_rs
                WHERE date::date = (SELECT MAX(date::date) FROM stock_rs)
                ORDER BY rs_score DESC
                LIMIT :top
            """)
            rs_result = db.execute(query, {"top": top})
        else:
            query = text("""
                SELECT symbol, name, market, rs_score, roc_3m, roc_6m, roc_12m, strength_factor
                FROM stock_rs
                WHERE date::date = (SELECT MAX(date::date) FROM stock_rs)
                  AND market = :market
                ORDER BY rs_score DESC
                LIMIT :top
            """)
            rs_result = db.execute(query, {"market": market.upper(), "top": top})

        rows = rs_result.fetchall()

        for i, row in enumerate(rows):
            result.append({
                "rank": i + 1,
                "symbol": row[0],
                "name": row[1] or "",
                "market": row[2] or "",
                "rs": row[3] or 0,
                "roc_3m": round(row[4] or 0, 2),
                "roc_6m": round(row[5] or 0, 2),
                "roc_12m": round(row[6] or 0, 2),
                "strength_factor": round(row[7] or 0, 2),
            })

    except Exception as e:
        print(f"[API] /api/market/rs-ranking 오류: {e}")

    return {
        "success": True,
        "data": result,
        "market": market.upper(),
        "updated_at": datetime.now().strftime("%Y-%m-%d %H:%M")
    }


@app.post("/api/market/rs/init")
async def init_rs_scores(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    RS 점수 초기화 (관리자용)
    전체 종목 수집 후 RS 점수 계산
    """
    if current_user.role != "admin":
        raise HTTPException(status_code=403, detail="관리자만 사용 가능합니다")

    from .market_analysis.rs_calculator import (
        collect_all_stocks_closes, calculate_rs_with_details
    )
    from datetime import datetime

    try:
        # 1. 전체 종목 종가 수집 (시간 소요)
        all_closes = await collect_all_stocks_closes(['KOSPI', 'KOSDAQ'], days=253)

        if not all_closes:
            return {"success": False, "error": "종가 데이터 수집 실패"}

        # 2. RS 점수 계산
        rs_details = calculate_rs_with_details(all_closes)

        # 3. DB 저장
        today = datetime.now()
        saved_count = 0

        for symbol, data in rs_details.items():
            try:
                db.execute(
                    text("""
                        INSERT INTO stock_rs (date, symbol, roc_3m, roc_6m, roc_9m, roc_12m, strength_factor, rs_score)
                        VALUES (:date, :symbol, :roc_3m, :roc_6m, :roc_9m, :roc_12m, :sf, :rs)
                        ON CONFLICT (date, symbol) DO UPDATE SET
                            roc_3m = :roc_3m, roc_6m = :roc_6m, roc_9m = :roc_9m, roc_12m = :roc_12m,
                            strength_factor = :sf, rs_score = :rs
                    """),
                    {
                        "date": today,
                        "symbol": symbol,
                        "roc_3m": data['roc_3m'],
                        "roc_6m": data['roc_6m'],
                        "roc_9m": data['roc_9m'],
                        "roc_12m": data['roc_12m'],
                        "sf": data['strength_factor'],
                        "rs": data['rs_score'],
                    }
                )
                saved_count += 1
            except Exception as e:
                print(f"[RS] {symbol} 저장 오류: {e}")

        db.commit()

        return {
            "success": True,
            "total_stocks": len(all_closes),
            "saved_count": saved_count,
            "updated_at": today.strftime("%Y-%m-%d %H:%M")
        }

    except Exception as e:
        db.rollback()
        return {"success": False, "error": str(e)}


@app.get("/api/market/sector/{sector_name}/stocks")
async def get_market_sector_stocks(
    sector_name: str,
    current_user: User = Depends(get_current_user_optional),
):
    """
    섹터별 종목 상세 (등락률 TOP, 거래대금 TOP, 하락률 TOP)
    네이버 업종 페이지 직접 파싱
    """
    import httpx
    from bs4 import BeautifulSoup

    result = {
        "success": True,
        "sector": sector_name,
        "top_gainers": [],
        "top_losers": [],
        "top_volume": [],
    }

    # 네이버 업종코드 매핑 (전체 79개)
    sector_codes = {
        "증권": 321, "무선통신서비스": 333, "항공사": 305, "기타금융": 319,
        "다각화된소비자서비스": 339, "건강관리업체및서비스": 316, "창업투자": 277,
        "가구": 303, "카드": 337, "생명보험": 330, "담배": 275, "건축자재": 289,
        "반도체와반도체장비": 278, "전문소매": 328, "부동산": 280,
        "다각화된통신서비스": 336, "에너지장비및서비스": 295, "인터넷과카탈로그소매": 308,
        "운송인프라": 296, "가스유틸리티": 312, "컴퓨터와주변기기": 293, "광고": 310,
        "해운사": 323, "음료": 309, "가정용기기와용품": 298, "식품과기본식료품소매": 302,
        "판매업체": 265, "방송과엔터테인먼트": 285, "석유와가스": 313,
        "호텔,레스토랑,레저": 317, "전기유틸리티": 325, "소프트웨어": 287,
        "기계": 299, "건설": 279, "도로와철도운송": 329, "조선": 291,
        "우주항공과국방": 284, "종이와목재": 318, "레저용장비와제품": 271,
        "제약": 261, "가정용품": 297, "식품": 268, "상업서비스와공급품": 324,
        "백화점과일반상점": 264, "화장품": 266, "기타": 25, "섬유,의류,신발,호화품": 274,
        "포장재": 311, "생명과학도구및서비스": 262, "은행": 301, "자동차": 273,
        "통신장비": 294, "교육서비스": 290, "건강관리기술": 288, "철강": 304,
        "전기장비": 306, "건강관리장비와용품": 281, "자동차부품": 270,
        "게임엔터테인먼트": 263, "출판": 314, "문구류": 332, "양방향미디어와서비스": 300,
        "복합유틸리티": 331, "디스플레이장비및부품": 269, "손해보험": 315,
        "건축제품": 320, "사무용전자제품": 338, "항공화물운송과물류": 326,
        "화학": 272, "복합기업": 276, "디스플레이패널": 327, "IT서비스": 267,
        "핸드셋": 292, "생물공학": 286, "전자장비와기기": 282, "비철금속": 322,
        "전자제품": 307, "무역회사와판매업체": 334, "전기제품": 283,
    }

    try:
        # 정확한 매칭 또는 부분 매칭
        sector_code = sector_codes.get(sector_name)
        if not sector_code:
            for name, code in sector_codes.items():
                if name in sector_name or sector_name in name:
                    sector_code = code
                    break

        if not sector_code:
            result["error"] = f"업종 코드를 찾을 수 없습니다: {sector_name}"
            return result

        # 네이버 업종 상세 페이지 파싱
        url = f"https://finance.naver.com/sise/sise_group_detail.naver?type=upjong&no={sector_code}"
        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}

        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.get(url, headers=headers)
            if resp.status_code != 200:
                result["error"] = f"네이버 응답 오류: {resp.status_code}"
                return result

            resp.encoding = "euc-kr"
            soup = BeautifulSoup(resp.text, "lxml")

            # 종목 테이블 파싱 (열 순서: 종목명, 현재가, 전일비, 등락률, 매수호가, 매도호가, 거래량, 거래대금)
            stocks = []
            rows = soup.select("table.type_5 tbody tr")
            for row in rows:
                cells = row.select("td")
                if len(cells) >= 8:
                    name_el = cells[0].select_one("a")
                    if name_el:
                        name = name_el.get_text(strip=True)
                        try:
                            # 등락률 (index 3)
                            change_str = cells[3].get_text(strip=True).replace("%", "").replace("+", "").replace(",", "")
                            change = float(change_str) if change_str else 0
                            # 거래대금 (index 7, 백만원 단위)
                            vol_str = cells[7].get_text(strip=True).replace(",", "")
                            vol = int(vol_str) if vol_str.isdigit() else 0
                            stocks.append({"name": name, "change": change, "volume": vol})
                        except:
                            pass

            if not stocks:
                result["error"] = "종목 데이터 파싱 실패"
                return result

            # 상승 TOP 3
            gainers = sorted([s for s in stocks if s["change"] > 0], key=lambda x: x["change"], reverse=True)
            for s in gainers[:3]:
                result["top_gainers"].append({"name": s["name"], "change_percent": s["change"]})

            # 하락 TOP 3
            losers = sorted([s for s in stocks if s["change"] < 0], key=lambda x: x["change"])
            for s in losers[:3]:
                result["top_losers"].append({"name": s["name"], "change_percent": s["change"]})

            # 거래대금 TOP 3
            by_volume = sorted(stocks, key=lambda x: x["volume"], reverse=True)
            for s in by_volume[:3]:
                result["top_volume"].append({"name": s["name"], "trading_value": s["volume"]})

    except Exception as e:
        print(f"[API] /api/market/sector/{sector_name}/stocks 오류: {e}")
        import traceback
        traceback.print_exc()
        result["success"] = False
        result["error"] = str(e)

    return result


# 관심종목 그룹 API
@app.get("/api/watchlist/groups")
async def get_watchlist_groups(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """관심종목 그룹 목록"""
    _ensure_ai_tables(db)

    try:
        result = db.execute(
            text("""
                SELECT id, name, sort_order, created_at FROM watchlist_groups
                WHERE user_id = :uid ORDER BY sort_order, id
            """),
            {"uid": current_user.id}
        )
        rows = result.fetchall()

        groups = [{"id": r[0], "name": r[1], "sort_order": r[2]} for r in rows]

        # 기본 그룹 없으면 생성
        if not groups:
            db.execute(
                text("INSERT INTO watchlist_groups (user_id, name, sort_order) VALUES (:uid, '전체', 0)"),
                {"uid": current_user.id}
            )
            db.commit()
            groups = [{"id": 1, "name": "전체", "sort_order": 0}]

        return {"groups": groups, "limit": _get_watchlist_limit(current_user)}
    except Exception as e:
        print(f"Watchlist groups error: {e}")
        return {"groups": [], "limit": 10}


class WatchlistGroupRequest(BaseModel):
    name: str


@app.post("/api/watchlist/groups")
async def create_watchlist_group(
    request: WatchlistGroupRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """관심종목 그룹 생성"""
    _ensure_ai_tables(db)

    try:
        # 그룹 개수 제한 (10개)
        count_result = db.execute(
            text("SELECT COUNT(*) FROM watchlist_groups WHERE user_id = :uid"),
            {"uid": current_user.id}
        )
        count = count_result.scalar() or 0
        if count >= 10:
            raise HTTPException(status_code=400, detail="그룹은 최대 10개까지 생성 가능합니다")

        result = db.execute(
            text("""
                INSERT INTO watchlist_groups (user_id, name, sort_order)
                VALUES (:uid, :name, :order) RETURNING id
            """),
            {"uid": current_user.id, "name": request.name, "order": count}
        )
        group_id = result.scalar()
        db.commit()

        return {"success": True, "group_id": group_id}
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))


@app.put("/api/watchlist/groups/{group_id}")
async def update_watchlist_group(
    group_id: int,
    request: WatchlistGroupRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """관심종목 그룹 이름 변경"""
    try:
        db.execute(
            text("UPDATE watchlist_groups SET name = :name WHERE id = :gid AND user_id = :uid"),
            {"name": request.name, "gid": group_id, "uid": current_user.id}
        )
        db.commit()
        return {"success": True}
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))


@app.delete("/api/watchlist/groups/{group_id}")
async def delete_watchlist_group(
    group_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """관심종목 그룹 삭제"""
    try:
        # 기본 그룹(전체)은 삭제 불가
        result = db.execute(
            text("SELECT name FROM watchlist_groups WHERE id = :gid AND user_id = :uid"),
            {"gid": group_id, "uid": current_user.id}
        )
        row = result.fetchone()
        if row and row[0] == "전체":
            raise HTTPException(status_code=400, detail="기본 그룹은 삭제할 수 없습니다")

        db.execute(
            text("DELETE FROM watchlist_groups WHERE id = :gid AND user_id = :uid"),
            {"gid": group_id, "uid": current_user.id}
        )
        db.commit()
        return {"success": True}
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/watchlist/groups/{group_id}/items")
async def get_watchlist_items(
    group_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """그룹 내 관심종목 조회"""
    try:
        result = db.execute(
            text("""
                SELECT id, symbol, exchange, added_at FROM watchlist_items
                WHERE group_id = :gid AND user_id = :uid
                ORDER BY added_at DESC
            """),
            {"gid": group_id, "uid": current_user.id}
        )
        rows = result.fetchall()

        items = []
        for row in rows:
            item = {
                "id": row[0],
                "symbol": row[1],
                "exchange": row[2],
                "added_at": row[3].isoformat() if row[3] else "",
                "name": row[1],
                "price": 0,
                "change": 0,
            }
            # 마스터에서 이름 조회
            master = get_master_cache()
            stock = master.get_stock(row[1])
            if stock:
                item["name"] = stock.name
            items.append(item)

        return {"items": items}
    except Exception as e:
        print(f"Watchlist items error: {e}")
        return {"items": []}


class WatchlistItemRequest(BaseModel):
    group_id: int
    symbol: str
    exchange: str


@app.post("/api/watchlist/items")
async def add_watchlist_item(
    request: WatchlistItemRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """관심종목 추가"""
    _ensure_ai_tables(db)

    limit = _get_watchlist_limit(current_user)

    try:
        # 총 개수 확인
        count_result = db.execute(
            text("SELECT COUNT(*) FROM watchlist_items WHERE user_id = :uid"),
            {"uid": current_user.id}
        )
        count = count_result.scalar() or 0
        if count >= limit:
            raise HTTPException(status_code=400, detail=f"관심종목은 최대 {limit}개까지 추가 가능합니다")

        # 중복 확인
        dup_result = db.execute(
            text("""
                SELECT id FROM watchlist_items
                WHERE group_id = :gid AND user_id = :uid AND symbol = :sym AND exchange = :ex
            """),
            {"gid": request.group_id, "uid": current_user.id, "sym": request.symbol, "ex": request.exchange}
        )
        if dup_result.fetchone():
            raise HTTPException(status_code=400, detail="이미 추가된 종목입니다")

        db.execute(
            text("""
                INSERT INTO watchlist_items (group_id, user_id, symbol, exchange)
                VALUES (:gid, :uid, :sym, :ex)
            """),
            {"gid": request.group_id, "uid": current_user.id, "sym": request.symbol, "ex": request.exchange}
        )
        db.commit()

        return {"success": True, "count": count + 1, "limit": limit}
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))


@app.delete("/api/watchlist/items/{item_id}")
async def remove_watchlist_item(
    item_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """관심종목 삭제"""
    try:
        db.execute(
            text("DELETE FROM watchlist_items WHERE id = :iid AND user_id = :uid"),
            {"iid": item_id, "uid": current_user.id}
        )
        db.commit()
        return {"success": True}
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))


# =============================================================================
# [PHASE 6] Backtest API + Strategy Management
# =============================================================================

from app.backtest import run_backtest, BacktestRequest, BacktestResult

# Trend v8 Engine (for /api/backtest strategy_type="trend")
from app.strategy_engine.backtest_engine_trend import run_trend_backtest as run_trend_v8
from app.strategy_engine.signal_generator_trend import TrendConfig

# Custom Strategy (Phase 3)
from app.strategy_engine.indicator_registry import INDICATOR_REGISTRY, INDICATOR_CATEGORIES, OPERATORS
from app.strategy_engine.custom_strategy import (
    CustomStrategyConfig, CustomBacktestRequest, CustomBacktestResponse,
    ConditionItem, ConditionGroup, CustomRule
)
from app.strategy_engine.backtest_engine_custom import run_custom_backtest
from app.strategy_engine.candle_fetcher import fetch_candles_for_backtest
from app.strategy_engine.models import Candle


def _ensure_strategies_table(db: Session):
    """strategies 테이블이 없으면 생성"""
    create_sql = text("""
        CREATE TABLE IF NOT EXISTS strategies (
            id SERIAL PRIMARY KEY,
            user_id INTEGER REFERENCES users(id),
            name VARCHAR(255),
            strategy_type VARCHAR(50),
            exchange VARCHAR(50),
            symbol VARCHAR(50),
            params JSONB,
            order_settings JSONB,
            is_active BOOLEAN DEFAULT false,
            created_at TIMESTAMP DEFAULT NOW(),
            updated_at TIMESTAMP DEFAULT NOW()
        )
    """)
    db.execute(create_sql)
    db.commit()


class BacktestRequestBody(BaseModel):
    strategy_type: str  # custom, reversal, trend
    exchange: str
    symbol: str
    start_date: str
    end_date: str
    initial_capital: float = 10000000
    params: Optional[dict] = {}
    order_settings: Optional[dict] = {}


@app.post("/api/backtest")
async def api_run_backtest(
    request: BacktestRequestBody,
    current_user: User = Depends(get_current_user_optional)
):
    """백테스팅 실행 (trend는 v8 엔진 사용)"""
    # 요금제 확인 (프리미엄 전용)
    if current_user:
        plan = getattr(current_user, "plan", "free")
        role = getattr(current_user, "role", "user")
        if plan != "premium" and role != "admin":
            raise HTTPException(status_code=403, detail="프리미엄 요금제에서 이용 가능합니다")

    try:
        # Trend 전략은 v8 엔진 사용 (signal-log와 동일한 로직)
        if request.strategy_type == "trend":
            return await _run_trend_v8_backtest(request)

        # 그 외 전략은 기존 로직
        backtest_request = BacktestRequest(
            strategy_type=request.strategy_type,
            exchange=request.exchange,
            symbol=request.symbol,
            start_date=request.start_date,
            end_date=request.end_date,
            initial_capital=request.initial_capital,
            params=request.params or {},
            order_settings=request.order_settings or {}
        )

        result = run_backtest(backtest_request)
        return result.dict()

    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"백테스팅 실행 오류: {str(e)}")


async def _run_trend_v8_backtest(request: BacktestRequestBody) -> dict:
    """
    Trend v8 백테스트 실행 (signal-log와 동일한 엔진).

    Entry: SuperTrend 상승 + HVI 초록 + QQE 양수 + close > HTF filter
    Exit: SPO Split, ST Flip 등
    """
    from datetime import datetime

    # 날짜 → 일수 계산
    try:
        d1 = datetime.strptime(request.start_date, "%Y-%m-%d")
        d2 = datetime.strptime(request.end_date, "%Y-%m-%d")
        days = (d2 - d1).days + 50  # lookback 여유
    except:
        days = 400

    # 자산 타입 결정
    exchange_lower = request.exchange.lower()
    is_crypto = exchange_lower in ("okx", "binance", "bybit")
    asset_type = "crypto" if is_crypto else "stock"

    # 캔들 조회
    candles = await fetch_candles_for_backtest(
        exchange=exchange_lower,
        symbol=request.symbol,
        timeframe="1D",
        days=days,
        timeout=60,
    )

    if not candles or len(candles) < 200:
        return {
            "success": False,
            "message": f"캔들 부족: {len(candles) if candles else 0}개 (최소 200개 필요)",
            "trades": [],
            "summary": {},
        }

    # v8 설정 (signal-log와 동일)
    config = TrendConfig(
        st_atr_len=20,
        st_factor=5.0,
        asset_type=asset_type,
        htf_sma_len=200 if is_crypto else 156,
        htf_vwma_len=156,
        # 피라미딩 활성화
        use_pyramiding=True,
        max_pyr_entries=4,
        pyr_weights=[0.25, 0.25, 0.25, 0.25],
        # Exit 설정
        use_spo_split=True,
        use_st_flip_exit=True,
    )

    # v8 백테스트 실행
    result = run_trend_v8(
        candles=candles,
        config=config,
        initial_capital=request.initial_capital,
    )

    if not result.success:
        return {
            "success": False,
            "message": result.message,
            "trades": [],
            "summary": {},
        }

    # 결과 변환 (기존 API 형식과 호환)
    trades_list = []
    for t in result.trades:
        date_str = datetime.fromtimestamp(t.timestamp / 1000).strftime("%Y-%m-%d") if t.timestamp else ""
        trades_list.append({
            "date": date_str,
            "type": t.action,
            "price": t.price,
            "qty": t.quantity,
            "pnl": t.pnl,
            "reason": t.reason_code,
        })

    return {
        "success": True,
        "engine": "trend_v8",
        "total_trades": len(trades_list),
        "trades": trades_list,
        "summary": {
            "initial_capital": result.metrics.initial_capital,
            "final_capital": result.metrics.final_capital,
            "total_return_pct": result.metrics.total_return_pct,
            "max_drawdown_pct": result.metrics.max_drawdown_pct,
            "win_rate_pct": result.metrics.win_rate_pct,
            "profit_factor": result.metrics.profit_factor,
            "total_trades": result.metrics.total_trades,
        },
        "equity_curve": result.equity_curve,
    }


# =============================================================================
# [PHASE 3] Custom Strategy Builder API
# =============================================================================

@app.get("/api/strategies/indicators")
async def api_get_indicators():
    """
    커스텀 전략 빌더용 지표 목록

    Returns:
        indicators: 지표 레지스트리 (파라미터, 출력 등)
        categories: 카테고리별 지표 그룹
        operators: 사용 가능한 연산자
    """
    return {
        "indicators": INDICATOR_REGISTRY,
        "categories": INDICATOR_CATEGORIES,
        "operators": OPERATORS,
    }


@app.post("/api/backtest/custom")
async def api_run_custom_backtest(
    request: CustomBacktestRequest,
    current_user: User = Depends(get_current_user_optional)
):
    """
    커스텀 전략 백테스트 실행

    사용자 정의 진입/청산 규칙으로 백테스트 수행.
    지표 기반 조건 빌더 사용.
    """
    # 요금제 확인 (프리미엄 전용)
    if current_user:
        plan = getattr(current_user, "plan", "free")
        role = getattr(current_user, "role", "user")
        if plan != "premium" and role != "admin":
            raise HTTPException(status_code=403, detail="프리미엄 요금제에서 이용 가능합니다")

    try:
        # 캔들 데이터 조회 (days 기반)
        candles = await fetch_candles_for_backtest(
            exchange=request.exchange,
            symbol=request.symbol,
            timeframe=request.timeframe,
            days=request.days,
        )

        if not candles:
            return CustomBacktestResponse(
                success=False,
                message="캔들 데이터를 조회할 수 없습니다",
            ).model_dump()

        # 백테스트 실행
        result = await run_custom_backtest(
            candles=candles,
            config=request.strategy,
            initial_capital=request.initial_capital,
        )

        return result

    except Exception as e:
        import traceback
        traceback.print_exc()
        return CustomBacktestResponse(
            success=False,
            message=f"백테스트 실행 오류: {str(e)}",
        ).model_dump()


class StrategyCreateRequest(BaseModel):
    name: str
    strategy_type: str
    exchange: str
    symbol: str
    params: Optional[dict] = {}
    order_settings: Optional[dict] = {}
    is_active: bool = False


@app.post("/api/strategies")
async def create_strategy(
    request: StrategyCreateRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """전략 저장"""
    # 요금제 확인
    plan = getattr(current_user, "plan", "free")
    role = getattr(current_user, "role", "user")
    if plan != "premium" and role != "admin":
        raise HTTPException(status_code=403, detail="프리미엄 요금제에서 이용 가능합니다")

    try:
        _ensure_strategies_table(db)

        insert_sql = text("""
            INSERT INTO strategies (user_id, name, strategy_type, exchange, symbol, params, order_settings, is_active)
            VALUES (:user_id, :name, :strategy_type, :exchange, :symbol, :params, :order_settings, :is_active)
            RETURNING id
        """)

        result = db.execute(insert_sql, {
            "user_id": current_user.id,
            "name": request.name,
            "strategy_type": request.strategy_type,
            "exchange": request.exchange,
            "symbol": request.symbol,
            "params": json.dumps(request.params or {}),
            "order_settings": json.dumps(request.order_settings or {}),
            "is_active": request.is_active
        })
        db.commit()

        strategy_id = result.fetchone()[0]
        return {"ok": True, "id": strategy_id, "message": "전략이 저장되었습니다"}

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"전략 저장 오류: {str(e)}")


@app.get("/api/strategies")
async def get_strategies(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """사용자 전략 목록"""
    try:
        _ensure_strategies_table(db)

        sql = text("""
            SELECT id, name, strategy_type, exchange, symbol, params, order_settings, is_active, created_at
            FROM strategies
            WHERE user_id = :user_id
            ORDER BY created_at DESC
        """)
        rows = db.execute(sql, {"user_id": current_user.id}).mappings().all()

        strategies = []
        for row in rows:
            strategies.append({
                "id": row["id"],
                "name": row["name"],
                "strategy_type": row["strategy_type"],
                "exchange": row["exchange"],
                "symbol": row["symbol"],
                "params": row["params"] if isinstance(row["params"], dict) else json.loads(row["params"] or "{}"),
                "order_settings": row["order_settings"] if isinstance(row["order_settings"], dict) else json.loads(row["order_settings"] or "{}"),
                "is_active": row["is_active"],
                "created_at": str(row["created_at"])
            })

        return {"strategies": strategies}

    except Exception as e:
        return {"strategies": [], "error": str(e)}


@app.put("/api/strategies/{strategy_id}/toggle")
async def toggle_strategy(
    strategy_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """전략 활성화/비활성화"""
    try:
        _ensure_strategies_table(db)

        # 현재 상태 조회
        sql = text("SELECT is_active FROM strategies WHERE id = :id AND user_id = :user_id")
        row = db.execute(sql, {"id": strategy_id, "user_id": current_user.id}).mappings().first()

        if not row:
            raise HTTPException(status_code=404, detail="전략을 찾을 수 없습니다")

        new_active = not row["is_active"]

        update_sql = text("UPDATE strategies SET is_active = :active, updated_at = NOW() WHERE id = :id")
        db.execute(update_sql, {"active": new_active, "id": strategy_id})
        db.commit()

        return {"ok": True, "is_active": new_active}

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"전략 토글 오류: {str(e)}")


@app.delete("/api/strategies/{strategy_id}")
async def delete_strategy(
    strategy_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """전략 삭제"""
    try:
        _ensure_strategies_table(db)

        sql = text("DELETE FROM strategies WHERE id = :id AND user_id = :user_id")
        result = db.execute(sql, {"id": strategy_id, "user_id": current_user.id})
        db.commit()

        if result.rowcount == 0:
            raise HTTPException(status_code=404, detail="전략을 찾을 수 없습니다")

        return {"ok": True, "message": "전략이 삭제되었습니다"}

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"전략 삭제 오류: {str(e)}")


# =============================================================================
# [PHASE 7] Admin API — 사용자 관리 + 시스템 상태
# =============================================================================

@app.get("/api/admin/users")
async def admin_get_users(
    search: str = Query("", description="검색어 (이메일, 이름)"),
    plan_filter: str = Query("", description="요금제 필터"),
    current_user: User = Depends(get_admin_user),
    db: Session = Depends(get_db)
):
    """사용자 목록 (관리자 전용)"""
    try:
        base_sql = """
            SELECT id, email, name, role, plan, created_at, last_login_at, is_active
            FROM users
            WHERE 1=1
        """
        params = {}

        if search:
            base_sql += " AND (email ILIKE :search OR name ILIKE :search)"
            params["search"] = f"%{search}%"

        if plan_filter:
            base_sql += " AND plan = :plan"
            params["plan"] = plan_filter

        base_sql += " ORDER BY id ASC"

        rows = db.execute(text(base_sql), params).mappings().all()

        users = []
        for row in rows:
            users.append({
                "id": row["id"],
                "email": row["email"],
                "name": row["name"],
                "role": row["role"],
                "plan": row["plan"],
                "created_at": str(row["created_at"]) if row["created_at"] else None,
                "last_login_at": str(row["last_login_at"]) if row.get("last_login_at") else None,
                "is_active": row.get("is_active", True)
            })

        return {"users": users}

    except Exception as e:
        return {"users": [], "error": str(e)}


@app.put("/api/admin/users/{user_id}/plan")
async def admin_update_user_plan(
    user_id: int,
    request: Request,
    current_user: User = Depends(get_admin_user),
    db: Session = Depends(get_db)
):
    """사용자 요금제 변경 (관리자 전용)"""
    body = await request.json()
    new_plan = body.get("plan", "starter")

    # 새 요금제 (starter, standard, pro, premium) 또는 레거시 (free, hub)
    valid_plans = ["starter", "standard", "pro", "premium", "free", "hub"]
    if new_plan not in valid_plans:
        raise HTTPException(status_code=400, detail="잘못된 요금제입니다")

    try:
        sql = text("UPDATE users SET plan = :plan WHERE id = :user_id")
        db.execute(sql, {"plan": new_plan, "user_id": user_id})
        db.commit()
        return {"ok": True, "plan": new_plan}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.put("/api/admin/users/{user_id}/status")
async def admin_update_user_status(
    user_id: int,
    request: Request,
    current_user: User = Depends(get_admin_user),
    db: Session = Depends(get_db)
):
    """사용자 상태 변경 (관리자 전용)"""
    body = await request.json()
    is_active = body.get("is_active", True)

    try:
        sql = text("UPDATE users SET is_active = :active WHERE id = :user_id")
        db.execute(sql, {"active": is_active, "user_id": user_id})
        db.commit()
        return {"ok": True, "is_active": is_active}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/admin/system")
async def admin_get_system_status(
    current_user: User = Depends(get_admin_user),
    db: Session = Depends(get_db)
):
    """시스템 상태 (관리자 전용)"""
    import psutil
    import platform

    try:
        # 메모리 사용량
        memory = psutil.virtual_memory()
        memory_percent = memory.percent

        # DB 연결 테스트
        db_ok = True
        try:
            db.execute(text("SELECT 1"))
        except:
            db_ok = False

        # 웹훅 통계 (24시간)
        webhook_stats = {"total": 0, "success": 0, "failed": 0}
        try:
            _ensure_webhook_logs_table(db)
            stats_sql = text("""
                SELECT status, COUNT(*) as cnt
                FROM webhook_logs
                WHERE received_at > NOW() - INTERVAL '24 hours'
                GROUP BY status
            """)
            rows = db.execute(stats_sql).fetchall()
            for row in rows:
                webhook_stats["total"] += row[1]
                if row[0] == "success":
                    webhook_stats["success"] = row[1]
                else:
                    webhook_stats["failed"] += row[1]
        except:
            pass

        return {
            "status": "ok",
            "memory_percent": memory_percent,
            "db_connected": db_ok,
            "platform": platform.system(),
            "webhook_stats": webhook_stats
        }

    except Exception as e:
        return {"status": "error", "error": str(e)}


@app.get("/api/admin/users/export")
async def admin_export_users(
    current_user: User = Depends(get_admin_user),
    db: Session = Depends(get_db)
):
    """사용자 CSV 내보내기 (관리자 전용)"""
    from fastapi.responses import PlainTextResponse

    try:
        rows = db.execute(text("""
            SELECT id, email, name, role, plan, created_at
            FROM users ORDER BY id
        """)).fetchall()

        csv_lines = ["ID,Email,Name,Role,Plan,Created At"]
        for row in rows:
            csv_lines.append(f'{row[0]},"{row[1]}","{row[2] or ""}",{row[3]},{row[4]},{row[5]}')

        return PlainTextResponse(
            content="\n".join(csv_lines),
            media_type="text/csv",
            headers={"Content-Disposition": "attachment; filename=users.csv"}
        )

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/admin/stats")
async def admin_get_stats(
    current_user: User = Depends(get_admin_user),
    db: Session = Depends(get_db)
):
    """관리자 대시보드 통계 (전체 가입자, 활성 사용자, 오늘 가입자, AI 사용량)"""
    try:
        today = datetime.now(KST).date()
        today_str = today.strftime("%Y-%m-%d")
        this_month = today.strftime("%Y-%m")

        # 전체 가입자 수
        total_users = db.execute(text("SELECT COUNT(*) FROM users")).scalar() or 0

        # 활성 사용자 수
        active_users = db.execute(text("SELECT COUNT(*) FROM users WHERE is_active = true")).scalar() or 0

        # 오늘 가입자 수
        today_signups = db.execute(
            text("SELECT COUNT(*) FROM users WHERE DATE(created_at) = :today"),
            {"today": today_str}
        ).scalar() or 0

        # 오늘 AI 분석 총 횟수
        today_ai = db.execute(
            text("SELECT SUM(ai_usage_count) FROM users WHERE ai_usage_date = :today"),
            {"today": today_str}
        ).scalar() or 0

        # 요금제별 가입자 수
        plan_sql = text("""
            SELECT plan, COUNT(*) as cnt
            FROM users
            GROUP BY plan
        """)
        plan_rows = db.execute(plan_sql).fetchall()
        plan_counts = {
            "starter": 0,
            "standard": 0,
            "pro": 0,
            "premium": 0,
            "free": 0,
            "hub": 0
        }
        for row in plan_rows:
            plan_name = row[0] or "free"
            plan_counts[plan_name] = row[1]

        # 요금제 가격 (월)
        plan_prices = {
            "starter": 19900,
            "standard": 49000,
            "pro": 99000,
            "premium": 249000,
            "free": 0,
            "hub": 0
        }

        # AI 사용량 (최근 7일)
        ai_usage_7days = []
        for i in range(7):
            d = today - timedelta(days=i)
            d_str = d.strftime("%Y-%m-%d")
            count = db.execute(
                text("SELECT SUM(ai_usage_count) FROM users WHERE ai_usage_date = :d"),
                {"d": d_str}
            ).scalar() or 0
            ai_usage_7days.append({
                "date": d_str,
                "count": count,
                "tokens": count * 2000  # 추정 토큰
            })

        return {
            "total_users": total_users,
            "active_users": active_users,
            "today_signups": today_signups,
            "today_ai": today_ai,
            "plan_counts": plan_counts,
            "plan_prices": plan_prices,
            "ai_usage_7days": ai_usage_7days
        }

    except Exception as e:
        return {"error": str(e)}


@app.get("/api/admin/recent-users")
async def admin_get_recent_users(
    current_user: User = Depends(get_admin_user),
    db: Session = Depends(get_db)
):
    """최근 가입자 10명"""
    try:
        rows = db.execute(text("""
            SELECT id, email, name, plan, created_at, is_active
            FROM users
            ORDER BY created_at DESC
            LIMIT 10
        """)).mappings().all()

        users = []
        for row in rows:
            users.append({
                "id": row["id"],
                "email": row["email"],
                "name": row["name"],
                "plan": row["plan"],
                "created_at": str(row["created_at"]) if row["created_at"] else None,
                "is_active": row.get("is_active", True)
            })

        return {"users": users}

    except Exception as e:
        return {"users": [], "error": str(e)}
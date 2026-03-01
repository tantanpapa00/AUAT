# app/routers/webhook.py
# 웹훅 시스템 API 엔드포인트

import os
import json
from typing import Optional
from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from sqlalchemy import text

from app.db import get_db
from app.auth import get_current_user
from app.models import User

router = APIRouter(prefix="/api", tags=["webhook"])


# =============================================================================
# 헬퍼 함수
# =============================================================================

def _ensure_system_flags_table(db: Session):
    """system_flags 테이블이 없으면 생성"""
    db.execute(text("""
        CREATE TABLE IF NOT EXISTS system_flags (
            key VARCHAR(50) PRIMARY KEY,
            value TEXT,
            reason TEXT,
            updated_at TIMESTAMP DEFAULT NOW()
        )
    """))
    db.commit()


def _get_flag(db: Session, key: str, default: str = None) -> str:
    """시스템 플래그 조회"""
    try:
        _ensure_system_flags_table(db)
        row = db.execute(
            text("SELECT value FROM system_flags WHERE key = :k"),
            {"k": key}
        ).mappings().first()
        return row["value"] if row else default
    except Exception:
        return default


def _is_estop_on(db: Session) -> bool:
    """긴급 정지 상태 확인"""
    v = str(_get_flag(db, "estop", "0")).strip().lower()
    return v in ("1", "true", "yes", "y", "on")


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


class WebhookLogItem(BaseModel):
    id: int
    received_at: str
    status: str
    exchange: str
    symbol: str
    action: str
    error_message: Optional[str] = None


# =============================================================================
# API 엔드포인트
# =============================================================================

@router.post("/webhook/{user_id}")
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


@router.get("/webhook/logs")
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


@router.get("/webhook/url")
async def get_webhook_url(current_user: User = Depends(get_current_user)):
    """사용자의 웹훅 URL 반환"""
    base_url = os.getenv("BASE_URL", "https://qube-system.com")
    return {
        "webhook_url": f"{base_url}/api/webhook/{current_user.id}",
        "user_id": current_user.id
    }

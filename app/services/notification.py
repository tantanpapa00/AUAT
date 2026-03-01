"""
BBooster 알림 시스템
- 내부 이벤트 발행/구독
- WebSocket 전송
- FCM 푸시 발송 (향후)
- DB 저장
"""
import asyncio
import json
from datetime import datetime, timezone
from typing import Optional, Callable, List, Tuple, Any
from enum import Enum


class NotificationType(str, Enum):
    """알림 유형"""
    ORDER_FILLED = "order_filled"       # 주문 체결
    ORDER_FAILED = "order_failed"       # 주문 실패
    SIGNAL_RECEIVED = "signal_received" # 시그널 수신
    SIGNAL_SKIPPED = "signal_skipped"   # 시그널 스킵 (조건 미충족)
    REPORT_DONE = "report_done"         # AI 리포트 생성 완료
    REPORT_FAILED = "report_failed"     # AI 리포트 실패
    SYSTEM_ALERT = "system_alert"       # 시스템 알림 (에러, 점검 등)
    PRICE_ALERT = "price_alert"         # 가격 알림 (향후)


class NotificationEvent:
    """알림 이벤트 객체"""

    def __init__(
        self,
        user_id: int,
        event_type: NotificationType,
        title: str,
        message: str,
        data: Optional[dict] = None
    ):
        self.user_id = user_id
        self.event_type = event_type
        self.title = title
        self.message = message
        self.data = data or {}
        self.created_at = datetime.now(timezone.utc).isoformat()

    def to_dict(self) -> dict:
        return {
            "user_id": self.user_id,
            "type": self.event_type.value,
            "title": self.title,
            "message": self.message,
            "data": self.data,
            "created_at": self.created_at
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False)


class NotificationManager:
    """
    싱글톤 이벤트 매니저.
    이벤트 발행 시 등록된 모든 핸들러에게 전달한다.
    """

    def __init__(self):
        self._handlers: List[Tuple[Callable, Optional[Callable]]] = []

    def register(self, handler: Callable, filter_fn: Optional[Callable] = None):
        """
        핸들러 등록.
        filter_fn이 있으면 조건 맞는 이벤트만 전달.
        """
        self._handlers.append((handler, filter_fn))
        print(f"[NOTIFY] 핸들러 등록: {handler.__name__}")

    def unregister(self, handler: Callable):
        """핸들러 제거."""
        self._handlers = [(h, f) for h, f in self._handlers if h != handler]

    async def publish(self, event: NotificationEvent):
        """이벤트 발행 → 모든 핸들러에게 전달."""
        print(f"[NOTIFY] 발행: user={event.user_id}, type={event.event_type.value}, title={event.title}")

        for handler, filter_fn in self._handlers:
            try:
                if filter_fn is None or filter_fn(event):
                    if asyncio.iscoroutinefunction(handler):
                        await handler(event)
                    else:
                        handler(event)
            except Exception as e:
                print(f"[NOTIFY] 핸들러 에러 ({handler.__name__}): {e}")

    @property
    def handler_count(self) -> int:
        return len(self._handlers)


# 글로벌 싱글톤
notification_manager = NotificationManager()


# =============================================================================
# DB 저장 핸들러 (알림 히스토리)
# =============================================================================

async def save_notification_to_db(event: NotificationEvent):
    """알림 이벤트 → DB 저장."""
    try:
        from sqlalchemy import text
        from app.db import get_db

        # DB 세션 가져오기
        db = next(get_db())
        try:
            # notifications 테이블 확인/생성
            db.execute(text("""
                CREATE TABLE IF NOT EXISTS notifications (
                    id SERIAL PRIMARY KEY,
                    user_id INTEGER NOT NULL,
                    type VARCHAR(50) NOT NULL,
                    title VARCHAR(200) NOT NULL,
                    message TEXT NOT NULL,
                    data JSONB DEFAULT '{}',
                    is_read BOOLEAN DEFAULT FALSE,
                    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
                )
            """))

            # 인덱스 생성 (없으면)
            db.execute(text("""
                CREATE INDEX IF NOT EXISTS idx_notifications_user_id ON notifications(user_id)
            """))
            db.execute(text("""
                CREATE INDEX IF NOT EXISTS idx_notifications_created_at ON notifications(created_at DESC)
            """))

            # 알림 저장
            db.execute(text("""
                INSERT INTO notifications (user_id, type, title, message, data)
                VALUES (:user_id, :type, :title, :message, :data)
            """), {
                "user_id": event.user_id,
                "type": event.event_type.value,
                "title": event.title,
                "message": event.message,
                "data": json.dumps(event.data, ensure_ascii=False)
            })
            db.commit()
        finally:
            db.close()

    except Exception as e:
        print(f"[NOTIFY] DB 저장 실패: {e}")


# DB 핸들러 등록
notification_manager.register(save_notification_to_db)

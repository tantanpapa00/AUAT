"""
알림 API 엔드포인트.
- 알림 목록 조회
- 알림 읽음 처리
- 알림 삭제
"""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import text
from typing import Optional, List
from pydantic import BaseModel
from datetime import datetime

from app.db import get_db
from app.auth import get_current_user
from app.models import User

router = APIRouter(prefix="/api/notifications", tags=["notifications"])


class NotificationItem(BaseModel):
    """알림 항목"""
    id: int
    type: str
    title: str
    message: str
    data: dict
    is_read: bool
    created_at: datetime


class NotificationListResponse(BaseModel):
    """알림 목록 응답"""
    success: bool = True
    data: List[NotificationItem]
    total: int
    unread_count: int


@router.get("", response_model=NotificationListResponse)
async def get_notifications(
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    unread_only: bool = Query(default=False),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    알림 목록 조회.
    - limit: 최대 조회 개수 (기본 50, 최대 200)
    - offset: 조회 시작 위치
    - unread_only: 읽지 않은 알림만 조회
    """
    try:
        # 읽지 않은 알림 수 조회
        unread_result = db.execute(text("""
            SELECT COUNT(*) FROM notifications
            WHERE user_id = :user_id AND is_read = FALSE
        """), {"user_id": current_user.id})
        unread_count = unread_result.scalar() or 0

        # 전체 알림 수 조회
        where_clause = "WHERE user_id = :user_id"
        if unread_only:
            where_clause += " AND is_read = FALSE"

        total_result = db.execute(text(f"""
            SELECT COUNT(*) FROM notifications {where_clause}
        """), {"user_id": current_user.id})
        total = total_result.scalar() or 0

        # 알림 목록 조회
        result = db.execute(text(f"""
            SELECT id, type, title, message, data, is_read, created_at
            FROM notifications
            {where_clause}
            ORDER BY created_at DESC
            LIMIT :limit OFFSET :offset
        """), {
            "user_id": current_user.id,
            "limit": limit,
            "offset": offset
        })

        notifications = []
        for row in result:
            import json
            data_dict = {}
            if row.data:
                try:
                    data_dict = json.loads(row.data) if isinstance(row.data, str) else row.data
                except:
                    pass

            notifications.append(NotificationItem(
                id=row.id,
                type=row.type,
                title=row.title,
                message=row.message,
                data=data_dict,
                is_read=row.is_read,
                created_at=row.created_at
            ))

        return NotificationListResponse(
            data=notifications,
            total=total,
            unread_count=unread_count
        )

    except Exception as e:
        print(f"[NOTIFY API] 목록 조회 실패: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{notification_id}/read")
async def mark_notification_read(
    notification_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """알림 읽음 처리."""
    try:
        result = db.execute(text("""
            UPDATE notifications
            SET is_read = TRUE
            WHERE id = :id AND user_id = :user_id
            RETURNING id
        """), {
            "id": notification_id,
            "user_id": current_user.id
        })
        db.commit()

        if result.rowcount == 0:
            raise HTTPException(status_code=404, detail="알림을 찾을 수 없습니다")

        return {"success": True, "message": "읽음 처리 완료"}

    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/read-all")
async def mark_all_notifications_read(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """모든 알림 읽음 처리."""
    try:
        db.execute(text("""
            UPDATE notifications
            SET is_read = TRUE
            WHERE user_id = :user_id AND is_read = FALSE
        """), {"user_id": current_user.id})
        db.commit()

        return {"success": True, "message": "모든 알림 읽음 처리 완료"}

    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/{notification_id}")
async def delete_notification(
    notification_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """알림 삭제."""
    try:
        result = db.execute(text("""
            DELETE FROM notifications
            WHERE id = :id AND user_id = :user_id
            RETURNING id
        """), {
            "id": notification_id,
            "user_id": current_user.id
        })
        db.commit()

        if result.rowcount == 0:
            raise HTTPException(status_code=404, detail="알림을 찾을 수 없습니다")

        return {"success": True, "message": "알림 삭제 완료"}

    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("")
async def delete_all_notifications(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """모든 알림 삭제."""
    try:
        db.execute(text("""
            DELETE FROM notifications
            WHERE user_id = :user_id
        """), {"user_id": current_user.id})
        db.commit()

        return {"success": True, "message": "모든 알림 삭제 완료"}

    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))

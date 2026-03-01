# app/routers/admin.py
# 관리자 전용 API 엔드포인트

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import PlainTextResponse
from sqlalchemy.orm import Session
from sqlalchemy import text
from datetime import datetime, timedelta, timezone

from app.db import get_db
from app.auth import get_admin_user
from app.models import User

# KST timezone
KST = timezone(timedelta(hours=9))

router = APIRouter(prefix="/api/admin", tags=["admin"])


@router.get("/users")
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


@router.put("/users/{user_id}/role")
async def admin_update_user_role(
    user_id: int,
    request: Request,
    current_user: User = Depends(get_admin_user),
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


@router.put("/users/{user_id}/plan")
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


@router.put("/users/{user_id}/status")
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


@router.get("/system")
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


@router.get("/users/export")
async def admin_export_users(
    current_user: User = Depends(get_admin_user),
    db: Session = Depends(get_db)
):
    """사용자 CSV 내보내기 (관리자 전용)"""
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


@router.get("/stats")
async def admin_get_stats(
    current_user: User = Depends(get_admin_user),
    db: Session = Depends(get_db)
):
    """관리자 대시보드 통계 (전체 가입자, 활성 사용자, 오늘 가입자, AI 사용량)"""
    try:
        today = datetime.now(KST).date()
        today_str = today.strftime("%Y-%m-%d")

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


@router.get("/recent-users")
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

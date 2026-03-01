# app/routers/watchlist.py
# 관심종목 API 엔드포인트

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import text
from pydantic import BaseModel

from app.db import get_db
from app.auth import get_current_user
from app.models import User
from app.kis_api import get_master_cache
from app.utils.plan_limits import get_watchlist_limit
from app.utils.db_init import ensure_ai_tables

router = APIRouter(prefix="/api/watchlist", tags=["watchlist"])


class WatchlistGroupRequest(BaseModel):
    name: str


class WatchlistItemRequest(BaseModel):
    group_id: int
    symbol: str
    exchange: str
    name: str = ""  # 종목명 (선택)
    memo: str = ""  # 메모 (선택)


@router.get("/groups")
async def get_watchlist_groups(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """관심종목 그룹 목록"""
    ensure_ai_tables(db)

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

        return {"groups": groups, "limit": get_watchlist_limit(current_user)}
    except Exception as e:
        print(f"Watchlist groups error: {e}")
        return {"groups": [], "limit": 10}


@router.post("/groups")
async def create_watchlist_group(
    request: WatchlistGroupRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """관심종목 그룹 생성"""
    ensure_ai_tables(db)

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


@router.put("/groups/{group_id}")
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


@router.delete("/groups/{group_id}")
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


@router.get("/groups/{group_id}/items")
async def get_watchlist_items(
    group_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """그룹 내 관심종목 조회 (시세 데이터 보강)"""
    try:
        result = db.execute(
            text("""
                SELECT id, symbol, exchange, added_at, name, memo FROM watchlist_items
                WHERE group_id = :gid AND user_id = :uid
                ORDER BY added_at DESC
            """),
            {"gid": group_id, "uid": current_user.id}
        )
        rows = result.fetchall()

        # 스크리너 캐시에서 시세 데이터 가져오기
        from app.screener.kr_screener import load_kr_stocks
        kr_stocks = await load_kr_stocks()
        kr_stock_map = {s.get("code"): s for s in kr_stocks}

        items = []
        for row in rows:
            symbol = row[1]
            exchange = row[2]
            db_name = row[4] or ""
            db_memo = row[5] or ""

            item = {
                "id": row[0],
                "symbol": symbol,
                "exchange": exchange,
                "added_at": row[3].isoformat() if row[3] else "",
                "name": db_name or symbol,
                "memo": db_memo,
                "price": 0,
                "change_pct": 0,
                "volume": 0,
            }

            # 시세 데이터 보강
            if exchange in ["kis_kr", "KIS_KR", "kospi", "kosdaq"]:
                stock_data = kr_stock_map.get(symbol)
                if stock_data:
                    item["name"] = db_name or stock_data.get("name", symbol)
                    item["price"] = stock_data.get("price", 0)
                    item["change_pct"] = stock_data.get("change_pct", 0)
                    item["volume"] = stock_data.get("volume", 0)
                else:
                    # 마스터에서 이름만 조회
                    master = get_master_cache()
                    stock = master.get_stock(symbol)
                    if stock:
                        item["name"] = db_name or stock.name

            items.append(item)

        return {"items": items}
    except Exception as e:
        print(f"Watchlist items error: {e}")
        import traceback
        traceback.print_exc()
        return {"items": []}


@router.post("/items")
async def add_watchlist_item(
    request: WatchlistItemRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """관심종목 추가"""
    ensure_ai_tables(db)

    limit = get_watchlist_limit(current_user)

    try:
        # 그룹 존재 확인 및 자동 생성
        group_result = db.execute(
            text("SELECT id FROM watchlist_groups WHERE id = :gid AND user_id = :uid"),
            {"gid": request.group_id, "uid": current_user.id}
        )
        if not group_result.fetchone():
            # 기본 그룹이 없으면 자동 생성
            db.execute(
                text("""
                    INSERT INTO watchlist_groups (id, user_id, name, sort_order)
                    VALUES (:gid, :uid, '기본', 0)
                    ON CONFLICT (id) DO NOTHING
                """),
                {"gid": request.group_id, "uid": current_user.id}
            )
            db.commit()

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
                INSERT INTO watchlist_items (group_id, user_id, symbol, exchange, name, memo)
                VALUES (:gid, :uid, :sym, :ex, :name, :memo)
            """),
            {"gid": request.group_id, "uid": current_user.id, "sym": request.symbol,
             "ex": request.exchange, "name": request.name, "memo": request.memo}
        )
        db.commit()

        return {"success": True, "count": count + 1, "limit": limit}
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/items/{item_id}")
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

from pathlib import Path

TARGET = Path(r"C:\autobot\app\main.py")
src = TARGET.read_text(encoding="utf-8")

# 이미 정의돼있으면 아무 것도 안 함(중복 방지)
if "def _get_strategy_or_404" in src:
    print("SKIP: _get_strategy_or_404 already exists")
    raise SystemExit(0)

# FastAPI HTTPException이 있어야 함
if "from fastapi import" not in src or "HTTPException" not in src:
    print("WARN: HTTPException import not found in fastapi import line. (existing code should already have it)")

helper = r'''

# ------------------------------
# helper: get strategy or 404
# - must exist for template routes
# ------------------------------
def _get_strategy_or_404(db, strategy_id: int):
    try:
        from sqlalchemy import text
        row = db.execute(text("SELECT * FROM strategies WHERE id=:id AND soft_deleted=FALSE"), {"id": strategy_id}).mappings().first()
        if not row:
            raise HTTPException(status_code=404, detail="strategy_not_found")
        return row
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"strategy_lookup_failed: {e}")

'''

# 삽입 위치: 템플릿 라우트(api_templates_tradingview) 정의 '위'가 안전
anchor = "def api_templates_tradingview"
idx = src.find(anchor)
if idx < 0:
    raise SystemExit("PATCH_FAIL: anchor not found: def api_templates_tradingview")

# anchor 바로 위에 helper 삽입
src2 = src[:idx] + helper + "\n" + src[idx:]
TARGET.write_text(src2, encoding="utf-8")
print("PATCH_OK: inserted _get_strategy_or_404 before api_templates_tradingview")

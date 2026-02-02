from sqlalchemy import text
def get_session():
    try:
        from app.db import SessionLocal
        db = SessionLocal()
        return db, db.close
    except Exception:
        from app.db import get_db
        gen = get_db()
        db = next(gen)
        return db, gen.close

db, closer = get_session()
try:
    cols = db.execute(text("""
        select column_name
        from information_schema.columns
        where table_name='orders'
    """)).fetchall()
    cols = {c[0] for c in cols}
    need = ["status","okx_order_id","okx_response","reason","reason_code","reason_msg"]
    print("MISSING:", [x for x in need if x not in cols])
finally:
    try: closer()
    except Exception: pass

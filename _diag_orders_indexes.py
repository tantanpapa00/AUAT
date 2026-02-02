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
    rows = db.execute(text("""
        select indexname, indexdef
        from pg_indexes
        where tablename='orders'
        order by indexname
    """)).fetchall()
    print("== orders indexes ==")
    for r in rows:
        print(r)
finally:
    try: closer()
    except Exception: pass

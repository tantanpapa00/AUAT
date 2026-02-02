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
        SELECT
          column_name,
          data_type,
          is_nullable,
          COALESCE(column_default,'') AS column_default
        FROM information_schema.columns
        WHERE table_name='orders'
        ORDER BY ordinal_position
    """)).fetchall()

    print("== orders columns ==")
    for r in rows:
        print(r)

    cnt = db.execute(text("select count(*) from orders")).scalar()
    print("orders_count =", cnt)
finally:
    try: closer()
    except Exception: pass

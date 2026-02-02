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
    db.execute(text("ALTER TABLE orders ALTER COLUMN status SET DEFAULT 'received';"))
    db.execute(text("UPDATE orders SET status='received' WHERE status IS NULL OR status='';"))
    db.commit()
    print("OK: status default repaired")
finally:
    try: closer()
    except Exception: pass

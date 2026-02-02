from sqlalchemy.orm import Session
from sqlalchemy import select
from datetime import datetime, timezone
from .models import Account

def list_accounts(db: Session):
    return db.execute(select(Account).order_by(Account.id.asc())).scalars().all()

def get_account(db: Session, account_id: int):
    return db.get(Account, account_id)

def create_account(db: Session, payload: dict):
    acc = Account(**payload)
    db.add(acc)
    db.commit()
    db.refresh(acc)
    return acc

def update_account(db: Session, acc: Account, payload: dict):
    for k, v in payload.items():
        setattr(acc, k, v)
    db.commit()
    db.refresh(acc)
    return acc

def delete_account(db: Session, acc: Account):
    db.delete(acc)
    db.commit()

def toggle_account(db: Session, acc: Account):
    acc.is_active = not acc.is_active
    db.commit()
    db.refresh(acc)
    return acc

def set_health(db: Session, acc: Account, ok: bool, msg: str):
    acc.last_health_ok = ok
    acc.last_health_msg = msg
    acc.last_health_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(acc)
    return acc

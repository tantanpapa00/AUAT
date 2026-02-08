from sqlalchemy.orm import Session
from sqlalchemy import select
from datetime import datetime, timezone
from .models import Account

# Account 모델의 유효한 컬럼 목록
ACCOUNT_VALID_COLUMNS = {
    'name', 'exchange', 'api_key', 'api_secret',
    'api_passphrase', 'account_number', 'is_active'
}

# 거래소별 필수/선택 필드 정의
EXCHANGE_FIELDS = {
    'okx': {
        'required': ['api_key', 'api_secret', 'api_passphrase'],
        'optional': ['account_number']
    },
    'binance': {
        'required': ['api_key', 'api_secret'],
        'optional': ['api_passphrase', 'account_number']
    },
    'bybit': {
        'required': ['api_key', 'api_secret'],
        'optional': ['api_passphrase', 'account_number']
    },
    'upbit': {
        'required': ['api_key', 'api_secret'],  # access_key → api_key로 매핑됨
        'optional': ['api_passphrase', 'account_number']
    },
    'kis_kr': {
        'required': ['api_key', 'api_secret', 'account_number'],  # app_key, app_secret → api_key, api_secret
        'optional': ['api_passphrase']
    },
    'kis_us': {
        'required': ['api_key', 'api_secret', 'account_number'],
        'optional': ['api_passphrase']
    },
    'kis': {  # 일반 KIS
        'required': ['api_key', 'api_secret', 'account_number'],
        'optional': ['api_passphrase']
    },
}


def list_accounts(db: Session):
    return db.execute(select(Account).order_by(Account.id.asc())).scalars().all()

def get_account(db: Session, account_id: int):
    return db.get(Account, account_id)

def validate_exchange_fields(exchange: str, payload: dict) -> tuple[bool, str]:
    """
    거래소별 필수 필드 검증
    Returns: (is_valid, error_message)
    """
    exchange_lower = exchange.lower()
    if exchange_lower not in EXCHANGE_FIELDS:
        # 알 수 없는 거래소는 기본 검증 (api_key, api_secret 필수)
        if not payload.get('api_key') or not payload.get('api_secret'):
            return False, f"api_key와 api_secret은 필수입니다"
        return True, ""

    config = EXCHANGE_FIELDS[exchange_lower]
    missing = []
    for field in config['required']:
        if not payload.get(field):
            missing.append(field)

    if missing:
        return False, f"필수 필드 누락: {', '.join(missing)}"
    return True, ""

def filter_account_payload(payload: dict) -> dict:
    """
    payload에서 Account 모델에 유효한 컬럼만 추출
    """
    return {k: v for k, v in payload.items() if k in ACCOUNT_VALID_COLUMNS}

def create_account(db: Session, payload: dict):
    # 유효한 컬럼만 필터링
    filtered_payload = filter_account_payload(payload)
    acc = Account(**filtered_payload)
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

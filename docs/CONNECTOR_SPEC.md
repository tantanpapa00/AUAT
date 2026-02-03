# CONNECTOR_SPEC.md (SSOT)
- Last updated: 2026-02-04 KST
- Owner: 기훈(작가님)
- Status: Week 13 Day 1

> NOTE: 이 파일은 거래소 커넥터 인터페이스의 '진실(SSOT)'입니다.

---

# 1) 지원 거래소

| Exchange | 타입 | 마켓 | 상태 | 비고 |
|----------|------|------|------|------|
| OKX | 암호화폐 | Spot | DONE | Week 4 완료 |
| KIS | 증권사 | Stock | DONE | Week 7 완료 |
| Binance | 암호화폐 | Spot | DONE | Week 12 Day 3 |
| Bybit | 암호화폐 | Spot | DONE | Week 12 Day 4 |
| Upbit | 암호화폐 | Spot (KRW/USDT) | DONE | Week 13 Day 1 |

> **원칙**: 선물(Futures)/레버리지 전면 미지원. Spot만 지원.

---

# 2) 커넥터 인터페이스

## 2-1) 공통 타입 (base.py)

```python
# 이미 구현됨 - app/connectors/base.py

Side = Literal["buy", "sell"]
OrderType = Literal["market", "limit"]

@dataclass(frozen=True)
class PlaceOrderResult:
    ok: bool
    exchange: str
    symbol: str
    side: Side
    qty: float
    order_type: OrderType
    exchange_order_id: Optional[str] = None  # 공통 필드
    clord_id: Optional[str] = None
    state: Optional[str] = None
    avg_px: Optional[float] = None
    filled_qty: Optional[float] = None
    raw: Optional[Dict[str, Any]] = None
    err_code: Optional[str] = None
    err_msg: Optional[str] = None

@dataclass(frozen=True)
class OrderResult:
    ok: bool
    exchange: str
    symbol: str
    exchange_order_id: Optional[str] = None
    clord_id: Optional[str] = None
    state: Optional[str] = None
    avg_px: Optional[float] = None
    filled_qty: Optional[float] = None
    raw: Optional[Dict[str, Any]] = None
    err_code: Optional[str] = None
    err_msg: Optional[str] = None

@dataclass(frozen=True)
class BalanceSplit:
    ok: bool
    exchange: str
    ccy: str
    total: float
    trading: float
    funding: float
    raw: Optional[Dict[str, Any]] = None
    err_code: Optional[str] = None
    err_msg: Optional[str] = None
```

## 2-2) Connector Protocol

```python
class Connector(Protocol):
    exchange: str  # "OKX", "KIS", "BINANCE", "BYBIT", "UPBIT"

    def place_order(
        self,
        *,
        symbol: str,
        side: Side,
        qty: float,
        order_type: OrderType = "market",
        px: Optional[float] = None,
        payload: Optional[Dict[str, Any]] = None,
    ) -> PlaceOrderResult:
        ...

    def get_order(
        self,
        *,
        symbol: str,
        exchange_order_id: Optional[str] = None,
        clord_id: Optional[str] = None,
    ) -> OrderResult:
        ...

    def get_balance_split(self, *, ccy: str = "USDT") -> BalanceSplit:
        ...

    def get_markets(self, *, symbol: Optional[str] = None) -> List[MarketInfo]:
        ...
```

---

# 3) 라우팅 정책

## 3-1) 라우팅 기준

```
account.exchange → Connector 선택
```

| account.exchange | Connector Class | 비고 |
|------------------|-----------------|------|
| OKX | OKXConnector | 기존 |
| KIS | KISConnector | 기존 |
| BINANCE | BinanceConnector | TODO |
| BYBIT | BybitConnector | TODO |
| UPBIT | UpbitConnector | TODO |

## 3-2) 팩토리 함수

```python
# app/connectors/__init__.py

SUPPORTED_EXCHANGES = ["OKX", "KIS", "BINANCE", "BYBIT", "UPBIT"]

def get_connector(exchange: str) -> Optional[Connector]:
    ex = _norm_exchange(exchange)
    if ex == "OKX":
        from .okx import OKXConnector
        return OKXConnector()
    elif ex == "KIS":
        from .kis import KISConnector
        return KISConnector()
    elif ex == "BINANCE":
        from .binance import BinanceConnector
        return BinanceConnector()
    elif ex == "BYBIT":
        from .bybit import BybitConnector
        return BybitConnector()
    elif ex == "UPBIT":
        from .upbit import UpbitConnector
        return UpbitConnector()
    return None
```

## 3-3) Exchange 정규화

```python
def _norm_exchange(exchange: str | None) -> str:
    if not exchange:
        return ""
    ex = str(exchange).strip().upper()
    # Aliases
    aliases = {
        "OKEX": "OKX",
        "KOREAINVESTMENT": "KIS",
        "KOREA INVESTMENT": "KIS",
        "BINANCE.COM": "BINANCE",
        "BYBIT.COM": "BYBIT",
        "UPBIT.COM": "UPBIT",
    }
    return aliases.get(ex, ex)
```

---

# 4) 주문 상태 표준

## 4-1) 공통 상태 (state)

| 상태 | 의미 | OKX | Binance | Bybit | Upbit | KIS |
|------|------|-----|---------|-------|-------|-----|
| `sent` | 주문 전송됨 | live | NEW | New | wait | 접수 |
| `partial` | 부분 체결 | partially_filled | PARTIALLY_FILLED | PartiallyFilled | - | 일부체결 |
| `filled` | 전체 체결 | filled | FILLED | Filled | done | 전량체결 |
| `canceled` | 취소됨 | canceled | CANCELED | Cancelled | cancel | 취소 |
| `failed` | 실패 | - | REJECTED | Rejected | error | 거부 |
| `expired` | 만료됨 | - | EXPIRED | - | - | - |

## 4-2) 내부 상태 플로우

```
pending → sent → [partial →] filled
                       ↓
                   canceled
                       ↓
                    failed
```

## 4-3) 상태 매핑 함수 (각 커넥터에서 구현)

```python
def _normalize_state(exchange_state: str) -> str:
    """거래소별 상태를 공통 상태로 변환"""
    # OKX
    if exchange_state in ("live",):
        return "sent"
    if exchange_state in ("partially_filled",):
        return "partial"
    if exchange_state in ("filled",):
        return "filled"
    if exchange_state in ("canceled",):
        return "canceled"
    return "unknown"
```

## 4-4) reason/snapshot 필드 표준 (Week12 Day2)

> **원칙**: 모든 주문 상태 변경은 `reason_code`, `reason_text`, `snapshot_id`를 기록해야 함.

### 필드 정의

| 필드 | 타입 | 용도 | 예시 |
|------|------|------|------|
| `reason_code` | TEXT | 표준화된 사유 코드 (기계용) | `signal_buy`, `estop`, `insufficient_balance` |
| `reason_text` | TEXT | 사람이 읽을 수 있는 설명 | `TradingView buy signal received` |
| `snapshot_id` | TEXT | 스냅샷 참조 ID (선택) | `snap_20260204_123456` |

### 표준 reason_code 목록

| 코드 | 의미 | 사용 위치 |
|------|------|-----------|
| `signal_buy` | 매수 시그널 | order_created |
| `signal_sell` | 매도 시그널 | order_created |
| `estop` | E-STOP 발동 | order_failed |
| `dry_run` | DRY_RUN 모드 | order_created |
| `insufficient_balance` | 잔고 부족 | order_failed |
| `symbol_not_found` | 심볼 없음 | order_failed |
| `api_error` | API 오류 | order_failed |
| `network_error` | 네트워크 오류 | order_failed |
| `exchange_error` | 거래소 오류 | order_failed |
| `rate_limit` | API 제한 초과 | order_failed |
| `timeout` | 타임아웃 | order_failed |
| `user_cancel` | 사용자 취소 | order_canceled |
| `auto_cancel` | 자동 취소 | order_canceled |
| `filled` | 체결 완료 | order_filled |
| `partial_filled` | 부분 체결 | order_partial |

### 사용 예시

```python
# 주문 생성 시
order.reason_code = "signal_buy"
order.reason_text = f"TradingView signal: {alert_id}"
order.snapshot_id = f"snap_{timestamp}"

# 실패 시
order.reason_code = "estop"
order.reason_text = "E-STOP activated by user"
```

### 이벤트(Event) 연동

Event 모델에서도 동일한 필드 사용:
- `reason_code`: 이벤트 발생 원인 코드
- `reason_text`: 이벤트 설명
- `snapshot_id`: 관련 스냅샷 참조

---

# 5) 심볼 정규화

## 5-1) 내부 표준 포맷

```
{BASE}-{QUOTE}
```

예시:
- `BTC-USDT` (암호화폐)
- `ETH-USDT` (암호화폐)
- `BTC-KRW` (Upbit)
- `005930` (KIS, 종목코드)

## 5-2) 거래소별 변환

| 거래소 | 내부 포맷 | 거래소 포맷 | 변환 함수 |
|--------|-----------|-------------|-----------|
| OKX | `BTC-USDT` | `BTC-USDT` | 동일 |
| Binance | `BTC-USDT` | `BTCUSDT` | 하이픈 제거 |
| Bybit | `BTC-USDT` | `BTCUSDT` | 하이픈 제거 |
| Upbit | `BTC-KRW` | `KRW-BTC` | 순서 반전 |
| KIS | `005930` | `005930` | 동일 |

## 5-3) 심볼 변환 함수

```python
def to_exchange_symbol(internal: str, exchange: str) -> str:
    """내부 심볼 → 거래소 심볼"""
    ex = exchange.upper()
    if ex in ("BINANCE", "BYBIT"):
        return internal.replace("-", "")
    if ex == "UPBIT":
        parts = internal.split("-")
        if len(parts) == 2:
            return f"{parts[1]}-{parts[0]}"  # BTC-KRW → KRW-BTC
    return internal

def from_exchange_symbol(external: str, exchange: str) -> str:
    """거래소 심볼 → 내부 심볼"""
    ex = exchange.upper()
    if ex == "UPBIT":
        parts = external.split("-")
        if len(parts) == 2:
            return f"{parts[1]}-{parts[0]}"  # KRW-BTC → BTC-KRW
    # Binance/Bybit: 단순 연결 → 하이픈 삽입 필요 (마켓 정보 필요)
    return external
```

---

# 6) 환경변수 정책

## 6-1) 공통 패턴

```
{EXCHANGE}_API_KEY
{EXCHANGE}_API_SECRET
{EXCHANGE}_PASSPHRASE (optional)
{EXCHANGE}_BASE_URL (optional)
{EXCHANGE}_SIMULATED (optional, 0/1)
```

## 6-2) 거래소별 환경변수

| 환경변수 | OKX | Binance | Bybit | Upbit | KIS |
|----------|-----|---------|-------|-------|-----|
| API_KEY | O | O | O | O | APP_KEY |
| API_SECRET | O | O | O | O | APP_SECRET |
| PASSPHRASE | O | - | - | - | - |
| BASE_URL | O | O | O | O | SVR |
| SIMULATED | O | O (testnet) | O (testnet) | - | O |
| CANO | - | - | - | - | O |
| ACNT_PRDT_CD | - | - | - | - | O |

## 6-3) 예시 (.env)

```bash
# OKX
OKX_API_KEY=xxx
OKX_API_SECRET=xxx
OKX_API_PASSPHRASE=xxx
OKX_BASE_URL=https://www.okx.com
OKX_SIMULATED=0

# Binance
BINANCE_API_KEY=xxx
BINANCE_API_SECRET=xxx
BINANCE_BASE_URL=https://api.binance.com
BINANCE_SIMULATED=0

# Bybit
BYBIT_API_KEY=xxx
BYBIT_API_SECRET=xxx
BYBIT_BASE_URL=https://api.bybit.com
BYBIT_SIMULATED=0

# Upbit
UPBIT_API_KEY=xxx
UPBIT_API_SECRET=xxx
UPBIT_BASE_URL=https://api.upbit.com

# KIS
KIS_APP_KEY=xxx
KIS_APP_SECRET=xxx
KIS_CANO=xxx
KIS_ACNT_PRDT_CD=01
KIS_SVR=vps
KIS_SIMULATED=0
```

---

# 7) 진단 엔드포인트

## 7-1) 단일 커넥터 테스트

```
GET /api/diag/connector-test?exchange={EXCHANGE}
```

Response:
```json
{
  "ok": true,
  "exchange": "BINANCE",
  "connector": "BinanceConnector",
  "balance": {
    "ok": true,
    "ccy": "USDT",
    "trading": 100.5
  }
}
```

## 7-2) 전체 커넥터 목록

```
GET /api/diag/connector-all
```

Response:
```json
{
  "ok": true,
  "connectors": [
    {"exchange": "OKX", "ok": true, "trading": 197.72},
    {"exchange": "BINANCE", "ok": true, "trading": 100.50},
    {"exchange": "BYBIT", "ok": true, "trading": 50.00},
    {"exchange": "UPBIT", "ok": true, "trading": 1000000},
    {"exchange": "KIS", "ok": true, "trading": 10000000}
  ]
}
```

---

# 8) 회귀 스크립트

## 8-1) 각 거래소별 스크립트

| 스크립트 | 거래소 | 검증 항목 |
|----------|--------|-----------|
| `week4_regression.ps1` | OKX | place_order, get_order, recover |
| `kis_regression.ps1` | KIS | preflight, balance, place_order |
| `binance_regression.ps1` | Binance | preflight, balance, place_order |
| `bybit_regression.ps1` | Bybit | preflight, balance, place_order |
| `upbit_regression.ps1` | Upbit | preflight, balance, place_order |

## 8-2) 통합 회귀 체크 항목

1. `/api/diag/connector-test?exchange={EXCHANGE}` → `ok: true`
2. `/api/diag/connector-all` → 모든 커넥터 `ok: true`
3. 주문 테스트 (DRY_RUN=1 또는 최소 수량)
4. 잔고 조회

---

# 9) 에러 코드 표준

## 9-1) 공통 에러 코드

| 코드 | 의미 | HTTP |
|------|------|------|
| `connector_not_found` | 커넥터 없음 | 400 |
| `api_key_invalid` | API 키 오류 | 401 |
| `insufficient_balance` | 잔고 부족 | 400 |
| `symbol_not_found` | 심볼 없음 | 400 |
| `order_failed` | 주문 실패 | 400 |
| `rate_limit` | API 제한 초과 | 429 |
| `network_error` | 네트워크 오류 | 503 |
| `exchange_error` | 거래소 오류 | 502 |

## 9-2) 에러 응답 포맷

```json
{
  "ok": false,
  "code": "insufficient_balance",
  "detail": "USDT 잔고 부족: 필요=100, 보유=50",
  "exchange": "BINANCE",
  "raw": { ... }
}
```

---

# 10) Upbit 마켓 정책 (Week13 Day1)

## 10-1) 지원 마켓

| 마켓 | Quote Currency | 예시 심볼 | 비고 |
|------|----------------|-----------|------|
| KRW 마켓 | KRW (원화) | BTC-KRW, ETH-KRW | 주력 마켓, 한국 원화 거래 |
| BTC 마켓 | BTC | ETH-BTC, XRP-BTC | 비트코인 기준 거래 |
| USDT 마켓 | USDT | BTC-USDT, ETH-USDT | 글로벌 스테이블코인 |

> **원칙**: 모든 마켓 지원. KRW 마켓이 주력이나 USDT 마켓도 동일 인터페이스.

## 10-2) 심볼 변환 규칙

```
내부 포맷: {BASE}-{QUOTE}  →  Upbit: {QUOTE}-{BASE}

BTC-KRW   →  KRW-BTC
ETH-USDT  →  USDT-ETH
XRP-BTC   →  BTC-XRP
```

## 10-3) 시장가 주문 특성

| 주문 타입 | Side | qty 의미 | 비고 |
|-----------|------|----------|------|
| Market BUY | bid | Quote 금액 (KRW) | 예: qty=100000 → 10만원어치 매수 |
| Market SELL | ask | Base 수량 (코인) | 예: qty=0.01 → 0.01 BTC 매도 |
| Limit | 양쪽 | Base 수량 (코인) | 지정가는 항상 코인 수량 |

> **주의**: 시장가 매수는 원화 금액, 매도는 코인 수량. 다른 거래소와 다름.

## 10-4) 인증 방식

- JWT (JSON Web Token) 사용
- HMAC SHA256 서명
- Query Hash: SHA512 (쿼리 파라미터 해시)

```python
# JWT Payload
{
    "access_key": "...",
    "nonce": "uuid",
    "query_hash": "sha512(query_string)",
    "query_hash_alg": "SHA512"
}
```

## 10-5) 환경변수

| 변수 | 설명 | 예시 |
|------|------|------|
| `UPBIT_ACCESS_KEY` | Open API Access Key | `xxx-xxx-xxx` |
| `UPBIT_SECRET_KEY` | Open API Secret Key | `xxx-xxx-xxx` |
| `UPBIT_BASE_URL` | API Base URL (선택) | `https://api.upbit.com` |
| `UPBIT_TIMEOUT_SEC` | 타임아웃 (선택) | `10` |

## 10-6) 기본 통화

- **get_balance_split()**: `ccy` 기본값 = `KRW` (다른 거래소는 USDT)
- 원화 잔고 조회가 가장 일반적인 사용 패턴

## 10-7) 주문 상태 매핑

| Upbit 상태 | 내부 상태 | 의미 |
|------------|-----------|------|
| `wait` | `sent` | 체결 대기 |
| `watch` | `sent` | 예약주문 대기 |
| `done` | `filled` | 전체 체결 |
| `cancel` | `canceled` | 취소됨 |

---

# 11) 구현 계획 (v5 일정)

| Week | Day | 작업 | 상태 |
|------|-----|------|------|
| 12 | 1 | 공통 인터페이스/라우팅 정책 확정 | DONE (spec) |
| 12 | 2 | 주문 상태/이벤트 표준 재점검 + reason/snapshot 필드 | DONE |
| 12 | 3 | Binance Spot 최소 구현 | DONE |
| 12 | 4 | Bybit Spot 최소 구현 | DONE |
| 12 | 5 | 회귀 스크립트 생성 | DONE |
| 13 | 1 | Upbit Spot 최소 구현 + KRW/USDT 마켓 정책 | DONE |
| 13 | 2 | 심볼 정규화 룰 확정 | TODO |
| 13 | 3 | upbit_regression.ps1 생성 | TODO |

---

# 12) 참조

- app/connectors/base.py (기존 인터페이스)
- app/connectors/__init__.py (팩토리)
- docs/PROJECT_STATUS.md (일정)
- [Binance API](https://binance-docs.github.io/apidocs/spot/en/)
- [Bybit API](https://bybit-exchange.github.io/docs/v5/intro)
- [Upbit API](https://docs.upbit.com/)

---

[END OF CONNECTOR_SPEC]

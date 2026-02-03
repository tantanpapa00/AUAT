# Connector Interface (Week 9)

> 이 문서는 bbooster Hub의 커넥터 인터페이스 명세입니다.
> 새 거래소 추가 시 이 인터페이스를 구현하세요.

---

## 1. 지원 거래소

| Exchange | Connector Class | 통화 | 비고 |
|----------|-----------------|------|------|
| OKX | `OKXConnector` | USDT | 현물 (Spot) |
| KIS | `KISConnector` | KRW | 국내/해외 주식 |

---

## 2. 커넥터 Protocol

모든 커넥터는 `app/connectors/base.py`의 `Connector` Protocol을 구현합니다.

```python
class Connector(Protocol):
    exchange: str

    def place_order(
        self,
        *,
        symbol: str,
        side: Literal["buy", "sell"],
        qty: float,
        order_type: Literal["market", "limit"] = "market",
        px: Optional[float] = None,
        payload: Optional[Dict[str, Any]] = None,
    ) -> PlaceOrderResult: ...

    def get_order(
        self,
        *,
        symbol: str,
        exchange_order_id: Optional[str] = None,
        clord_id: Optional[str] = None,
    ) -> OrderResult: ...

    def get_balance_split(self, *, ccy: str = "USDT") -> BalanceSplit: ...

    def get_markets(self, *, symbol: Optional[str] = None) -> List[MarketInfo]: ...
```

---

## 3. 데이터 클래스

### PlaceOrderResult
```python
@dataclass(frozen=True)
class PlaceOrderResult:
    ok: bool
    exchange: str
    symbol: str
    side: Side
    qty: float
    order_type: OrderType
    exchange_order_id: Optional[str] = None  # 공통 주문 ID
    clord_id: Optional[str] = None
    state: Optional[str] = None
    avg_px: Optional[float] = None
    filled_qty: Optional[float] = None
    raw: Optional[Dict[str, Any]] = None
    err_code: Optional[str] = None
    err_msg: Optional[str] = None
```

### OrderResult
```python
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
```

### BalanceSplit
```python
@dataclass(frozen=True)
class BalanceSplit:
    ok: bool
    exchange: str
    ccy: str
    total: float      # 총 자산
    trading: float    # 거래 가능
    funding: float    # 펀딩 계정
    raw: Optional[Dict[str, Any]] = None
    err_code: Optional[str] = None
    err_msg: Optional[str] = None
```

### MarketInfo
```python
@dataclass(frozen=True)
class MarketInfo:
    exchange: str
    symbol: str
    min_qty: Optional[float] = None     # 최소 주문 수량
    lot_qty: Optional[float] = None     # 주문 단위
    min_notional: Optional[float] = None  # 최소 주문 금액
    raw: Optional[Dict[str, Any]] = None
```

---

## 4. 커넥터 팩토리

```python
from app.connectors import get_connector, list_connectors, get_all_connectors

# 단일 커넥터 조회
conn = get_connector("OKX")
conn = get_connector("KIS")

# 지원 거래소 목록
exchanges = list_connectors()  # ["OKX", "KIS"]

# 모든 커넥터 조회
all_conns = get_all_connectors()  # {"OKX": OKXConnector, "KIS": KISConnector}
```

---

## 5. 테스트 엔드포인트

| Method | Path | 설명 |
|--------|------|------|
| GET | `/api/diag/connector-test?exchange=OKX` | 단일 커넥터 테스트 |
| GET | `/api/diag/connector-all` | 모든 커넥터 일괄 테스트 |
| GET | `/api/diag/connector-route?account_id=1` | 계좌 기반 라우팅 확인 |

---

## 6. 새 커넥터 추가 방법

1. `app/connectors/새거래소.py` 생성
2. `Connector` Protocol 구현
3. `app/connectors/__init__.py`에 등록:
   ```python
   SUPPORTED_EXCHANGES = ["OKX", "KIS", "새거래소"]

   def get_connector(exchange: str):
       ...
       elif ex == "새거래소":
           from .새거래소 import 새거래소Connector
           conn = 새거래소Connector()
   ```
4. 회귀 테스트 실행: `scripts/connector_regression.ps1`

---

## 7. 회귀 테스트

```powershell
# 커넥터 회귀 테스트
powershell -ExecutionPolicy Bypass -File scripts\connector_regression.ps1
```

### PASS 기준
- 모든 지원 커넥터 초기화 성공
- `get_balance_split` 정상 응답 (rate-limit은 SKIP)
- `/api/diag/connector-all` returns `ok=true`

---

[END OF CONNECTOR DOC]

# TradingView 얼러트 설정 Wizard (초보자용)

> 이 문서는 TradingView 얼러트를 bbooster Hub에 연결하는 과정을 단계별로 안내합니다.
> 스크린샷 없이 텍스트로만 설명하므로, 각 단계를 순서대로 따라하세요.

---

## 체크리스트 (시작 전 확인)

시작하기 전에 아래 항목을 모두 확인하세요:

- [ ] TradingView 계정 (Pro 이상 권장, 무료는 webhook 제한)
- [ ] bbooster Hub 서버 주소 (예: `http://your-server:8000`)
- [ ] 계좌(Account) 등록 완료
- [ ] 전략(Strategy) 등록 완료 + `tv_secret` 설정됨
- [ ] 자산(Asset) 등록 완료 + `is_active=true`

---

## Phase 1: 사전 준비 (Hub 설정)

### Step 1.1: 계좌 확인
```
GET /api/accounts
```
- 사용할 계좌가 목록에 있는지 확인
- `is_active: true` 인지 확인
- 없으면 계좌 먼저 등록

### Step 1.2: 전략 확인
```
GET /api/strategies
```
- 사용할 전략이 목록에 있는지 확인
- `tv_secret` 값이 설정되어 있는지 확인 (비어있으면 안됨)
- 없으면 전략 먼저 등록

### Step 1.3: 자산 확인
```
GET /api/assets
```
- 거래할 심볼이 등록되어 있는지 확인
- `is_active: true` 인지 확인
- 없으면 자산 먼저 등록:
  - `account_id`: 계좌 ID
  - `strategy_id`: 전략 ID
  - `symbol`: 티커 (예: `BTC-USDT`, `005930`, `AAPL`)
  - `market`: `spot`

---

## Phase 2: 템플릿 생성

### Step 2.1: 옵션 목록 확인
```
GET /api/templates/tradingview/options
```
- 활성화된 자산 목록이 표시됨
- 사용할 자산의 `asset_id` 확인

### Step 2.2: 템플릿 생성
```
GET /api/assets/{asset_id}/template/tradingview?side=buy&qty=1
```
- `asset_id`: Step 2.1에서 확인한 ID
- `side`: `buy` 또는 `sell`
- `qty`: 거래 수량

### Step 2.3: 템플릿 복사
응답의 `template_json` 값을 복사합니다:
```json
{
  "secret": "your-secret-here",
  "symbol": "BTC-USDT",
  "side": "buy",
  "qty": 1,
  "alert_id": "{{timenow}}",
  "type": "market"
}
```

---

## Phase 3: TradingView 설정

### Step 3.1: 차트 열기
1. TradingView 접속
2. 거래할 심볼의 차트 열기
3. 원하는 지표/전략 적용

### Step 3.2: 얼러트 생성
1. 차트 우측 상단 "알림" 아이콘 클릭 (종 모양)
2. "알림 추가" 또는 "Create Alert" 클릭

### Step 3.3: 조건 설정
- **Condition**: 원하는 조건 선택
  - 예: "RSI가 30 아래로 교차" → 매수 신호
  - 예: "RSI가 70 위로 교차" → 매도 신호

### Step 3.4: Webhook 설정
1. "Notifications" 탭 클릭
2. "Webhook URL" 체크박스 활성화
3. URL 입력:
   ```
   http://YOUR_SERVER:8000/tv
   ```

### Step 3.5: Message 설정
1. "Message" 필드에 Step 2.3에서 복사한 JSON 붙여넣기
2. 주의: JSON 형식 그대로 붙여넣기 (수정 X)

### Step 3.6: 저장
1. 알림 이름 설정 (선택)
2. "Create" 버튼 클릭

---

## Phase 4: 테스트

### Step 4.1: 테스트 전송
1. 생성된 얼러트 우클릭
2. "Test this alert" 클릭
3. Hub 서버 로그 확인

### Step 4.2: 응답 확인
성공 시:
```json
{"ok": true, "code": "accepted", "order_id": 123}
```

실패 시:
```json
{"ok": false, "code": "에러코드", "detail": "해결방법 안내"}
```

### Step 4.3: 문제 해결
에러 발생 시 `detail` 메시지를 확인하고 해결:
- `missing_secret` → secret 필드 추가
- `missing_symbol` → symbol 필드 추가
- `missing_side` → side 필드 추가 (buy/sell)
- `missing_qty` → qty 필드 추가
- `asset_not_found` → 자산 등록 필요
- `secret_invalid` → tv_secret 값 확인

---

## 최종 체크리스트 (설정 완료 후)

- [ ] 테스트 전송 성공 (`ok: true`)
- [ ] 주문이 정상 생성됨 (`order_id` 반환)
- [ ] 실제 조건 발생 시 얼러트 트리거 확인
- [ ] 거래소에서 주문 체결 확인 (실거래 시)

---

## 자주 묻는 질문 (FAQ)

### Q1: Webhook이 작동하지 않아요
- TradingView 플랜 확인 (무료 플랜은 제한 있음)
- 서버 URL이 외부에서 접근 가능한지 확인
- 방화벽/포트 설정 확인

### Q2: "bad_json" 에러가 나요
- JSON 형식 확인 (쉼표, 따옴표, 중괄호)
- TradingView에서 Message 필드에 그대로 붙여넣었는지 확인

### Q3: "asset_not_found" 에러가 나요
- `/api/assets`에서 해당 심볼이 등록되어 있는지 확인
- `symbol` 값이 정확히 일치하는지 확인 (대소문자 구분)
- `is_active: true`인지 확인

### Q4: 중복 주문이 걱정돼요
- `alert_id: "{{timenow}}"` 사용 시 자동 중복 방지
- 같은 `alert_id`로 재전송하면 `ignored_duplicate` 반환

### Q5: 매수/매도 두 개 다 설정하고 싶어요
- 얼러트 2개 생성 (매수용, 매도용)
- 각각 다른 조건 + 다른 `side` 값 사용

---

## 빠른 참조

| 항목 | 값 |
|------|-----|
| Webhook URL | `http://YOUR_SERVER:8000/tv` |
| Method | POST (자동) |
| Content-Type | application/json (자동) |
| 필수 필드 | secret, symbol, side, qty |
| 권장 필드 | alert_id (중복방지) |

---

[END OF WIZARD]

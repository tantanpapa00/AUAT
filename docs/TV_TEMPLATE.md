# TradingView Alert Template (표준 템플릿)

> **목적**: TradingView 얼러트 메시지를 bbooster Hub `/tv` 엔드포인트로 전송하기 위한 표준 JSON 템플릿
> **적용 대상**: OKX(현물), KIS(국내주식/해외주식) 공용

---

## 1. 필수 필드

| 필드 | 타입 | 설명 | 예시 |
|------|------|------|------|
| `secret` | string | 전략 인증 시크릿 (또는 config_hash 사용) | `"abc123secret"` |
| `symbol` | string | 티커/심볼 | `"BTC-USDT"`, `"005930"`, `"AAPL"` |
| `side` | string | 매수/매도 | `"buy"` 또는 `"sell"` |
| `qty` | number/string | 수량 | `0.1`, `"10"` |
| `alert_id` | string | 중복 방지용 고유 ID | `"{{timenow}}"` |

## 2. 선택 필드

| 필드 | 타입 | 설명 | 기본값 |
|------|------|------|--------|
| `config_hash` | string | 전략 설정 해시 (secret 대신 사용 가능) | - |
| `type` | string | 주문 유형 | `"market"` |
| `price` | number | 지정가 (type=limit일 때) | - |

---

## 3. 복붙 예시 (Copy-Paste Examples)

### 3.1 OKX 현물 (Crypto Spot)

**매수 (Buy)**
```json
{
  "secret": "YOUR_TV_SECRET",
  "symbol": "BTC-USDT",
  "side": "buy",
  "qty": 0.001,
  "alert_id": "{{timenow}}",
  "type": "market"
}
```

**매도 (Sell)**
```json
{
  "secret": "YOUR_TV_SECRET",
  "symbol": "ETH-USDT",
  "side": "sell",
  "qty": 0.01,
  "alert_id": "{{timenow}}",
  "type": "market"
}
```

---

### 3.2 KIS 국내주식 (Domestic Stock)

> **심볼 형식**: 6자리 종목코드 (예: 삼성전자 = `005930`)

**매수 (Buy)**
```json
{
  "secret": "YOUR_TV_SECRET",
  "symbol": "005930",
  "side": "buy",
  "qty": 1,
  "alert_id": "{{timenow}}",
  "type": "market"
}
```

**매도 (Sell)**
```json
{
  "secret": "YOUR_TV_SECRET",
  "symbol": "005930",
  "side": "sell",
  "qty": 1,
  "alert_id": "{{timenow}}",
  "type": "market"
}
```

---

### 3.3 KIS 해외주식 (Overseas Stock)

> **심볼 형식**: 티커 (예: Apple = `AAPL`, Tesla = `TSLA`)

**매수 (Buy)**
```json
{
  "secret": "YOUR_TV_SECRET",
  "symbol": "AAPL",
  "side": "buy",
  "qty": 1,
  "alert_id": "{{timenow}}",
  "type": "market"
}
```

**매도 (Sell)**
```json
{
  "secret": "YOUR_TV_SECRET",
  "symbol": "TSLA",
  "side": "sell",
  "qty": 1,
  "alert_id": "{{timenow}}",
  "type": "market"
}
```

---

### 3.4 config_hash 사용 예시

> `config_hash`를 사용하면 `secret`을 DB에서 자동 조회합니다.

```json
{
  "config_hash": "YOUR_CONFIG_HASH",
  "symbol": "BTC-USDT",
  "side": "buy",
  "qty": 0.001,
  "alert_id": "{{timenow}}"
}
```

---

## 4. TradingView 설정 방법

### Step 1: 얼러트 생성
1. TradingView 차트에서 원하는 조건 설정
2. "Create Alert" 클릭

### Step 2: Webhook URL 설정
- **URL**: `http://YOUR_SERVER:8000/tv`
- **Method**: POST (자동)

### Step 3: Message 입력
위 복붙 예시 중 하나를 복사하여 붙여넣기
- `YOUR_TV_SECRET` → 실제 시크릿으로 변경
- `symbol` → 거래할 심볼로 변경
- `qty` → 거래 수량으로 변경

### Step 4: 테스트
얼러트 저장 후 "Test" 버튼으로 테스트 전송

---

## 4.5 템플릿 자동 생성 API (권장)

수동으로 템플릿을 작성하는 대신 API를 사용하면 자동으로 생성됩니다.

### 옵션 목록 조회
```bash
GET /api/templates/tradingview/options
```

**응답 예시:**
```json
{
  "ok": true,
  "count": 2,
  "options": [
    {
      "asset_id": 1,
      "symbol": "BTC-USDT",
      "exchange": "OKX",
      "account_name": "OKX-Main",
      "strategy_name": "Scalping",
      "label": "OKX-Main / Scalping / BTC-USDT"
    }
  ]
}
```

### 자산별 템플릿 생성
```bash
GET /api/assets/{asset_id}/template/tradingview?side=buy&qty=0.001
```

**응답 예시:**
```json
{
  "ok": true,
  "asset_id": 1,
  "symbol": "BTC-USDT",
  "exchange": "OKX",
  "template_json": "{\n  \"secret\": \"abc123\",\n  \"symbol\": \"BTC-USDT\",\n  ...}"
}
```

→ `template_json` 값을 TradingView Message에 붙여넣기

### 다중 자산 일괄 생성
```bash
POST /api/templates/tradingview/generate
Content-Type: application/json

{
  "asset_ids": [1, 2, 3],
  "side": "buy",
  "qty": 1
}
```

---

## 5. 에러 코드 안내 (환불 방지 패키지)

> **Tip**: 에러 발생 시 `detail` 필드에 구체적인 해결 방법이 표시됩니다.

| 코드 | 설명 | 해결방법 |
|------|------|----------|
| `bad_json` | JSON 형식 오류 | 중괄호 `{}`, 쉼표, 따옴표 확인 |
| `missing_secret` | secret 누락 | `"secret": "..."` 추가 |
| `secret_invalid` | secret 미등록 | 전략의 tv_secret 값 확인 |
| `secret_mismatch` | secret 불일치 | config_hash에 등록된 secret 확인 |
| `config_not_found` | config_hash 미등록 | 전략 설정 확인 |
| `missing_symbol` | symbol 누락 | `"symbol": "..."` 추가 |
| `missing_side` | side 누락 | `"side": "buy"` 또는 `"sell"` 추가 |
| `invalid_side` | side 값 오류 | `buy` 또는 `sell`만 허용 |
| `missing_qty` | qty 누락 | `"qty": 1` 추가 |
| `invalid_qty` | qty 값 오류 | 0보다 큰 숫자 입력 |
| `asset_not_found` | 자산 미등록 | 해당 심볼을 전략에 추가 |
| `asset_inactive` | 자산 비활성 | 자산 is_active 활성화 |
| `ignored_duplicate` | 중복 요청 (정상) | alert_id 변경 또는 무시 |
| `stopped` | E-STOP 활성화 | 관리자에게 E-STOP 해제 요청 |

---

## 6. 주의사항

1. **시크릿 보안**: `secret` 값은 절대 공개하지 마세요
2. **alert_id**: `{{timenow}}`를 사용하면 TradingView가 자동으로 타임스탬프 생성
3. **수량 단위**:
   - OKX: 코인 수량 (예: 0.001 BTC)
   - KIS 국내: 주 수량 (정수)
   - KIS 해외: 주 수량 (정수)
4. **시장가 주문**: `type: "market"`이 기본 (생략 가능)
5. **선물 미지원**: 현물/주식만 지원 (Futures 불가)

---

[END OF TEMPLATE DOC]

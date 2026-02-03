# TIMELINE_SPEC.md (SSOT)
- Last updated: 2026-02-03 KST
- Owner: 기훈(작가님)
- Status: DRAFT (Week 10 Day 1)

> NOTE: 이 파일은 타임라인/이벤트 스키마의 '진실(SSOT)'입니다.

---

# 1) 개요

## 목적
- 주문/신호/체결/에러 등 주요 이벤트를 시간순으로 기록
- 사이트/PC/앱에서 공통으로 조회 가능한 타임라인 제공
- 차트 마커, 성과 분석, 디버깅용 기초 데이터

## 참조
- PRODUCT_SPEC.md 1-9 (UI 범위)
- PROJECT_STATUS.md Week 10

---

# 2) 이벤트 타입

| event_type | 설명 | 예시 |
|------------|------|------|
| `signal` | TradingView 신호 수신 | /tv webhook 도착 |
| `order_created` | 주문 생성 | DB에 order 레코드 생성 |
| `order_sent` | 주문 전송 완료 | OKX/KIS 주문 API 성공 |
| `order_failed` | 주문 전송 실패 | API 오류, 잔고 부족 등 |
| `order_filled` | 체결 완료 | 전량 체결 확인 |
| `order_partial` | 부분 체결 | 일부 수량만 체결 |
| `order_canceled` | 주문 취소 | 사용자 취소 또는 시스템 취소 |
| `poll` | 체결 조회 | poll-now 실행 |
| `error` | 시스템 에러 | 예외 발생, 연결 오류 등 |
| `estop_on` | E-STOP 활성화 | 긴급 정지 ON |
| `estop_off` | E-STOP 비활성화 | 긴급 정지 OFF |

---

# 3) 이벤트 스키마 (DB 테이블)

## 3-1) events 테이블

```sql
CREATE TABLE events (
    id              BIGSERIAL PRIMARY KEY,
    event_type      TEXT NOT NULL,           -- signal, order_created, order_sent, ...
    asset_id        BIGINT,                  -- FK to assets (nullable for system events)
    order_id        BIGINT,                  -- FK to orders (nullable)
    account_id      BIGINT,                  -- FK to accounts (nullable)

    -- 이벤트 상세
    summary         TEXT NOT NULL,           -- 짧은 요약 (UI 표시용)
    detail          JSONB,                   -- 상세 데이터 (flexible)

    -- 메타
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    -- 인덱스용
    CONSTRAINT fk_asset FOREIGN KEY (asset_id) REFERENCES assets(id),
    CONSTRAINT fk_order FOREIGN KEY (order_id) REFERENCES orders(id),
    CONSTRAINT fk_account FOREIGN KEY (account_id) REFERENCES accounts(id)
);

CREATE INDEX idx_events_asset_id ON events(asset_id);
CREATE INDEX idx_events_order_id ON events(order_id);
CREATE INDEX idx_events_created_at ON events(created_at DESC);
CREATE INDEX idx_events_type ON events(event_type);
```

## 3-2) 필드 설명

| 필드 | 타입 | 필수 | 설명 |
|------|------|------|------|
| id | BIGINT | O | PK, auto-increment |
| event_type | TEXT | O | 이벤트 종류 (enum) |
| asset_id | BIGINT | X | 관련 자산 ID |
| order_id | BIGINT | X | 관련 주문 ID |
| account_id | BIGINT | X | 관련 계좌 ID |
| summary | TEXT | O | 짧은 요약 (50자 이내 권장) |
| detail | JSONB | X | 상세 데이터 (유연) |
| created_at | TIMESTAMPTZ | O | 이벤트 발생 시각 |

---

# 4) detail JSONB 예시

## 4-1) signal 이벤트
```json
{
  "alert_id": "tv-123",
  "symbol": "ETH-USDT",
  "side": "buy",
  "qty": 0.01,
  "source": "tradingview"
}
```

## 4-2) order_sent 이벤트
```json
{
  "exchange": "OKX",
  "okx_order_id": "3274817031181656064",
  "clord_id": "TV191abc123",
  "side": "buy",
  "qty": 0.01,
  "price": null,
  "order_type": "market"
}
```

## 4-3) order_failed 이벤트
```json
{
  "exchange": "OKX",
  "error_code": "INSUFFICIENT_BAL",
  "error_msg": "need~0.125 USDT, have 0.00008 USDT",
  "retry_count": 0
}
```

## 4-4) order_filled 이벤트
```json
{
  "exchange": "OKX",
  "okx_order_id": "3274817031181656064",
  "filled_qty": 0.01,
  "avg_px": 2650.5,
  "fee": 0.00001
}
```

## 4-5) error 이벤트
```json
{
  "error_type": "network",
  "error_msg": "Connection timeout",
  "endpoint": "/api/diag/send-now",
  "stack_trace": "..."
}
```

---

# 5) 저장 방식

## 5-1) DB 저장 (기본)
- 모든 이벤트는 events 테이블에 저장
- log_retention_days에 따라 오래된 이벤트 삭제 (Plan별)
- 조회: GET /api/timeline?asset_id=...&limit=...

## 5-2) 로그 파일 (백업)
- 선택적으로 파일에도 기록 (logs/events.jsonl)
- 형식: JSONL (한 줄에 한 이벤트)
- 로테이션: 일별 또는 크기별

## 5-3) 실시간 알림 (향후)
- WebSocket 또는 SSE로 실시간 푸시 (Week 12+ 고려)

---

# 6) API 엔드포인트

## 6-1) GET /api/timeline

### 요청
```
GET /api/timeline?asset_id=3&limit=20&offset=0&event_type=order_sent
```

### 파라미터
| 파라미터 | 타입 | 필수 | 기본값 | 설명 |
|----------|------|------|--------|------|
| asset_id | int | X | - | 자산 ID 필터 |
| order_id | int | X | - | 주문 ID 필터 |
| account_id | int | X | - | 계좌 ID 필터 |
| event_type | string | X | - | 이벤트 타입 필터 |
| limit | int | X | 20 | 최대 개수 (max 100) |
| offset | int | X | 0 | 건너뛸 개수 |

### 응답
```json
{
  "ok": true,
  "items": [
    {
      "id": 123,
      "event_type": "order_sent",
      "asset_id": 3,
      "order_id": 191,
      "account_id": 1,
      "summary": "ETH-USDT 매수 주문 전송",
      "detail": {"okx_order_id": "327..."},
      "created_at": "2026-02-03T15:19:12+09:00"
    }
  ],
  "total": 45,
  "limit": 20,
  "offset": 0
}
```

---

# 7) 구현 계획

| Day | 작업 | 상태 |
|-----|------|------|
| Day 1 | 스키마 확정 (이 문서) | DONE |
| Day 2 | GET /api/timeline 구현 | TODO |
| Day 3 | /api/home에 최근 이벤트 추가 | TODO |
| Day 4 | UI 타임라인 렌더링 | TODO |
| Day 5 | 회귀 테스트 | TODO |

---

[END OF TIMELINE_SPEC]

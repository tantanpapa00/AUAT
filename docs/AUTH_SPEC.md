# AUTH_SPEC.md (SSOT)
- Last updated: 2026-02-03 KST
- Owner: 기훈(작가님)
- Status: FIXED (Week 9 Day 3 - Pydantic 모델 확정)

> NOTE: 이 파일은 Auth/구독/권한 스펙의 '진실(SSOT)'입니다.
> 구현 시 반드시 이 문서와 일치해야 합니다.

---

# 1) 개요

## 목적
- 사이트(서버)가 구독/권한 상태의 '정본'
- PC/앱은 토큰으로 서버에 조회하여 entitlement(권한) 동기화
- 권한 변경(업/다운그레이드/만료/환불) 시 즉시 반영

## 참조
- PRODUCT_SPEC.md 1-8 (구독/권한/동기화 원칙)

---

# 2) 인증 플로우

## 2-1) 로그인

### 엔드포인트
```
POST /api/auth/login
```

### 요청
```json
{
  "email": "user@example.com",
  "password": "********"
}
```

### 응답 (성공)
```json
{
  "ok": true,
  "access_token": "eyJhbGciOiJIUzI1NiIs...",
  "token_type": "bearer",
  "expires_in": 3600
}
```

### 응답 (실패)
```json
{
  "ok": false,
  "code": "invalid_credentials",
  "detail": "Invalid email or password"
}
```

## 2-2) 토큰 갱신 (선택)

### 엔드포인트
```
POST /api/auth/refresh
```

### 요청
```
Authorization: Bearer <access_token>
```

### 응답
```json
{
  "ok": true,
  "access_token": "eyJhbGciOiJIUzI1NiIs...",
  "expires_in": 3600
}
```

---

# 3) 구독 조회

## 3-1) /api/subscription/me

### 엔드포인트
```
GET /api/subscription/me
```

### 요청
```
Authorization: Bearer <access_token>
```

### 응답 (성공)
```json
{
  "ok": true,
  "user_id": "u_abc123",
  "plan": "hub",
  "expires_at": "2026-03-03T00:00:00Z",
  "entitlements": {
    "hub_enabled": true,
    "premium_enabled": false,
    "max_symbols": 5,
    "log_retention_days": 30,
    "batch_template": false,
    "export_csv": true
  }
}
```

### 응답 (미인증)
```json
{
  "ok": false,
  "code": "unauthorized",
  "detail": "Missing or invalid token"
}
```

### 응답 (구독 없음/만료)
```json
{
  "ok": false,
  "code": "no_subscription",
  "detail": "No active subscription"
}
```

---

# 4) Plan/Entitlement 정의

## 4-1) Plan 종류

| Plan | 설명 |
|------|------|
| `free` | 무료 (기능 제한) |
| `hub` | 허브형 (TradingView 브릿지) |
| `premium` | 프리미엄형 (신호판단 엔진 포함) |

## 4-2) Entitlement 필드

| 필드 | 타입 | 설명 |
|------|------|------|
| `hub_enabled` | boolean | 허브 기능 사용 가능 |
| `premium_enabled` | boolean | 프리미엄 엔진 사용 가능 |
| `max_symbols` | integer | 심볼 개수 제한 (0=무제한) |
| `log_retention_days` | integer | 로그 보관 기간 (일) |
| `batch_template` | boolean | 템플릿 일괄 생성 가능 |
| `export_csv` | boolean | CSV 내보내기 가능 |

## 4-3) Plan별 기본 권한

| Plan | hub_enabled | premium_enabled | max_symbols | log_retention_days | batch_template | export_csv |
|------|-------------|-----------------|-------------|-------------------|----------------|------------|
| free | false | false | 0 | 7 | false | false |
| hub | true | false | 5 | 30 | true | true |
| premium | true | true | 0 | 90 | true | true |

---

# 5) PC/앱 동기화 플로우 (Week 9 Day 4 확정)

## 5-1) 실행 시 동기화 (공통)

```
┌─────────────────────────────────────────────────────────────┐
│ 1. PC/앱 실행                                                │
│    ↓                                                        │
│ 2. 로컬 저장된 access_token 확인                             │
│    ├─ 없음 → 로그인 화면 표시                                │
│    └─ 있음 → 3단계로                                        │
│    ↓                                                        │
│ 3. GET /api/subscription/me 호출                            │
│    ↓                                                        │
│ 4. 응답 처리                                                 │
│    ├─ ok=true → entitlements 적용 → 메인 화면               │
│    ├─ code=unauthorized → 토큰 삭제 → 로그인 화면            │
│    ├─ code=no_subscription → 기능 잠금 → 구독 안내          │
│    └─ 네트워크 오류 → 오프라인 모드 (아래 5-4 참조)          │
└─────────────────────────────────────────────────────────────┘
```

## 5-2) 토큰 만료 처리

```
┌─────────────────────────────────────────────────────────────┐
│ 1. API 호출 → 401 Unauthorized 수신                         │
│    ↓                                                        │
│ 2. refresh_token 확인                                        │
│    ├─ 없음 → 로그인 화면                                     │
│    └─ 있음 → POST /api/auth/refresh                         │
│    ↓                                                        │
│ 3. refresh 응답 처리                                         │
│    ├─ ok=true → 새 access_token 저장 → 원래 API 재시도       │
│    └─ ok=false → 모든 토큰 삭제 → 로그인 화면                │
└─────────────────────────────────────────────────────────────┘
```

## 5-3) 주기적 동기화

| 플랫폼 | 주기 | 조건 |
|--------|------|------|
| PC | 30분 | 앱 포그라운드 상태 |
| 앱 | 15분 | 앱 포그라운드 상태 |

```
1. 타이머 발동 → GET /api/subscription/me
2. 응답에서 entitlements 비교
   ├─ 변경 없음 → 무시
   └─ 변경 있음 → UI 업데이트 + 알림 표시
3. 권한 축소 시 (다운그레이드/만료)
   └─ 즉시 해당 기능 잠금 + 안내 메시지
```

## 5-4) 오프라인 모드 (PC 전용)

> 앱은 오프라인 모드 미지원 (관측 중심이므로 서버 연결 필수)

```
┌─────────────────────────────────────────────────────────────┐
│ 조건: 네트워크 오류 + 로컬에 캐시된 entitlements 존재        │
│                                                             │
│ 동작:                                                       │
│ 1. 캐시된 entitlements 적용 (읽기 전용 모드)                 │
│ 2. 주문 기능 비활성화 (send-now, /tv 차단)                   │
│ 3. 상태바에 "오프라인" 표시                                  │
│ 4. 30초마다 연결 재시도                                      │
│ 5. 연결 복구 시 → 서버 entitlements로 갱신                   │
└─────────────────────────────────────────────────────────────┘
```

## 5-5) 기능 잠금/해제 매핑

| entitlement | 잠금 시 동작 (PC) | 잠금 시 동작 (앱) |
|-------------|-------------------|-------------------|
| hub_enabled=false | /tv 차단, 템플릿 생성 비활성화 | 대시보드만 표시 |
| premium_enabled=false | 프리미엄 설정 숨김 | 프리미엄 탭 숨김 |
| max_symbols 초과 | 신규 심볼 추가 차단, 안내 표시 | 신규 추가 버튼 비활성화 |
| batch_template=false | 일괄 생성 버튼 비활성화 | N/A (앱에서 미지원) |
| export_csv=false | 내보내기 버튼 비활성화 | N/A (앱에서 미지원) |

## 5-6) 에러 메시지 (사용자 표시용)

| code | 메시지 (한글) | 액션 버튼 |
|------|---------------|-----------|
| unauthorized | 로그인이 필요합니다 | [로그인] |
| no_subscription | 구독이 필요합니다 | [구독하기] |
| expired | 구독이 만료되었습니다 | [갱신하기] |
| network_error | 서버에 연결할 수 없습니다 | [재시도] |

## 5-7) 로컬 저장 (보안)

| 항목 | PC 저장 위치 | 앱 저장 위치 | 암호화 |
|------|-------------|-------------|--------|
| access_token | OS 자격증명 관리자 | Keychain/Keystore | 필수 |
| refresh_token | OS 자격증명 관리자 | Keychain/Keystore | 필수 |
| entitlements (캐시) | 앱 설정 파일 | 앱 설정 파일 | 선택 |
| user_id | 앱 설정 파일 | 앱 설정 파일 | 불필요 |

> **절대 금지**: 토큰 값을 로그/콘솔/파일에 출력하지 않음

---

# 6) 보안 고려사항

- access_token은 로컬 암호화 저장 (값 로그 금지)
- HTTPS 필수
- 토큰 만료 시간: 1시간 (조정 가능)
- refresh_token: 7일 (선택 구현)

---

# 7) 구현 상태 (Week 9 Day 3)

## Pydantic 모델 (app/main.py)
```python
class PlanType(str, Enum):
    FREE = "free"
    HUB = "hub"
    PREMIUM = "premium"

class Entitlements(BaseModel):
    hub_enabled: bool
    premium_enabled: bool
    max_symbols: int  # 0=무제한
    log_retention_days: int
    batch_template: bool
    export_csv: bool

class SubscriptionResponse(BaseModel):
    ok: Literal[True] = True
    user_id: str
    plan: PlanType
    expires_at: str
    entitlements: Entitlements

class SubscriptionErrorResponse(BaseModel):
    ok: Literal[False] = False
    code: str  # unauthorized, no_subscription, expired
    detail: str
```

## Plan별 기본값 (PLAN_DEFAULTS)
| Plan | hub_enabled | premium_enabled | max_symbols | log_retention_days | batch_template | export_csv |
|------|-------------|-----------------|-------------|-------------------|----------------|------------|
| free | false | false | 0 | 7 | false | false |
| hub | true | false | 5 | 30 | true | true |
| premium | true | true | 0 | 90 | true | true |

## 엔드포인트 상태
- `/api/subscription/me`: 스텁 구현 (Pydantic 모델 사용)
- `/api/auth/login`: TODO (Week 14)
- `/api/auth/refresh`: TODO (Week 14)

## 스텁 동작
- Authorization 헤더 없음 → SubscriptionErrorResponse(code="unauthorized")
- Authorization 헤더 있음 → SubscriptionResponse(plan="hub", entitlements=PLAN_DEFAULTS[HUB])

---

[END OF AUTH_SPEC]

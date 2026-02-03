# AUTH_SPEC.md (SSOT)
- Last updated: 2026-02-03 KST
- Owner: 기훈(작가님)
- Status: DRAFT (Week 9 Day 2)

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

# 5) PC/앱 동기화 플로우

## 5-1) 실행 시 동기화

```
1. PC/앱 실행
2. 로컬 저장된 access_token 확인
3. GET /api/subscription/me 호출
4. 응답에 따라:
   - ok=true → entitlements 적용
   - ok=false, code=unauthorized → 재로그인 유도
   - ok=false, code=no_subscription → 기능 잠금 + 구독 안내
```

## 5-2) 토큰 만료 처리

```
1. API 호출 시 401 응답 수신
2. refresh 토큰이 있으면 → POST /api/auth/refresh
3. refresh도 실패하면 → 재로그인 유도
```

## 5-3) 주기적 동기화 (선택)

- 앱 실행 중 N분마다 /api/subscription/me 조회
- 권한 변경(업/다운그레이드/만료) 즉시 반영

---

# 6) 보안 고려사항

- access_token은 로컬 암호화 저장 (값 로그 금지)
- HTTPS 필수
- 토큰 만료 시간: 1시간 (조정 가능)
- refresh_token: 7일 (선택 구현)

---

# 7) 스텁 구현 (Week 9 Day 2)

## 현재 상태
- `/api/subscription/me`: 스텁 구현 (하드코딩된 응답)
- `/api/auth/login`: TODO (Week 14)
- `/api/auth/refresh`: TODO (Week 14)

## 스텁 동작
- Authorization 헤더 없음 → ok=false, code=unauthorized
- Authorization 헤더 있음 → 하드코딩된 hub plan 반환

---

[END OF AUTH_SPEC]

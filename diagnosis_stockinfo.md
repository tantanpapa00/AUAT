# 종목정보 AI분석 타임아웃 진단

작성일: 2026-02-25

---

## 1. 호출 경로 추적 결과

### 1.1 AI 분석 버튼 위치 (2곳)

| 버튼 | 파일:라인 | HTML ID | 용도 |
|------|----------|---------|------|
| 메인 AI 분석 | main.js:4791 | `btn-ai-analysis` | 종목 상세 페이지 상단 🤖 버튼 |
| 종목정보 모달 AI 분석 | main.js:13232 | `btn-ai-analysis-modal` | stock-detail-modal 푸터 버튼 |

### 1.2 호출 방식 비교

| 항목 | 메인 AI분석 (line 4791) | 종목정보 AI분석 (line 13232) |
|------|------------------------|---------------------------|
| **호출 함수** | `invoke('request_ai_analysis', ...)` | `invoke('request_ai_analysis', ...)` |
| **호출 방식** | Job Queue (POST → job_id → 폴링) | Job Queue (POST → job_id → 폴링) |
| **폴링 함수** | `pollAiJobResult()` | `pollAiJobResult2()` |
| **폴링 간격** | 2초 | 2초 |
| **최대 대기** | 120초 | 120초 |
| **Tauri timeout** | 60초 (POST) / 10초 (폴링) | 60초 (POST) / 10초 (폴링) |

**결론: 두 버튼 모두 동일한 호출 패턴을 사용함**

---

## 2. 코드 경로 상세

### 2.1 프론트엔드 → Tauri

```
[main.js:4816 / 13257]
invoke('request_ai_analysis', { accessToken, symbol, exchange })
    ↓
[commands.rs:3145] request_ai_analysis()
    ↓
POST http://76.13.180.30/api/ai/analyze
timeout: 60초 (line 3163)
```

### 2.2 Tauri → 백엔드

```
[commands.rs:3151]
POST http://76.13.180.30/api/ai/analyze
    ↓
[main.py:12269] request_ai_analysis()
    ↓
1. _ensure_ai_tables(db)        ← DDL 5개 실행 (line 12280)
2. 사용량 체크 쿼리             ← SELECT + UPDATE (lines 12298-12327)
3. 캐시 확인 쿼리               ← SELECT (lines 12341-12354)
4. asyncio.create_task()        ← 백그라운드 작업 생성 (line 12376)
5. return {"job_id": ...}       ← 즉시 반환 (line 12379)
```

### 2.3 폴링

```
[main.js:4861 / 13302]
invoke('check_ai_status', { jobId })
    ↓
[commands.rs:3182] check_ai_status()
    ↓
GET http://76.13.180.30/api/ai/status/{job_id}
timeout: 10초 (line 3190)
    ↓
[main.py:12382] get_ai_job_status()
    ↓
return _ai_jobs[job_id]  ← 메모리에서 즉시 조회
```

---

## 3. 타임아웃 발생 가능 지점

### 3.1 타임아웃 체인

| 지점 | 타임아웃 | 파일:라인 | 가능성 |
|------|---------|----------|--------|
| Tauri POST | 60초 | commands.rs:3163 | **높음** |
| Tauri GET (폴링) | 10초 | commands.rs:3190 | 낮음 |
| 클라이언트 폴링 루프 | 120초 | main.js:4857, 13298 | 중간 |
| Claude API | 180초 | main.py:12893, 14260 | 낮음 |

### 3.2 에러 메시지 분석

```
error sending request for url (http://76.13.180.30/api/ai/analyze): operation timed out
```

이 에러는 **Tauri reqwest에서 발생** (commands.rs:3166):
```rust
.map_err(|e| format!("네트워크 오류: {}", e))?
```

→ **POST 요청이 60초 타임아웃에 걸림**

---

## 4. 원인 분석

### 4.1 POST가 60초 걸리는 이유

백엔드 `/api/ai/analyze` 엔드포인트는 **즉시 반환하도록 설계됨** (< 1초).
그러나 다음 상황에서 지연 가능:

| 원인 | 증상 | 확인 방법 |
|------|------|----------|
| **DB 연결 지연** | `_ensure_ai_tables()` 에서 멈춤 | 서버 로그 `[AI Analyze] _ensure_ai_tables: XX초` |
| **DB 커넥션 풀 고갈** | 요청이 대기열에서 대기 | `docker exec bbooster-db psql -c "SELECT * FROM pg_stat_activity;"` |
| **네트워크 불안정** | 요청이 서버에 도달 안 함 | 서버 로그에 요청 기록 없음 |
| **서버 다운** | 응답 없음 | `curl http://76.13.180.30/api/health` |

### 4.2 서버 로그 확인 (필수)

```bash
# SSH 접속
ssh -i ~/.ssh/bbooster_vps root@76.13.180.30

# AI 분석 로그 실시간 모니터링
docker logs -f bbooster-app 2>&1 | grep -E "\[AI Analyze\]"

# 또는 최근 로그
docker logs bbooster-app --tail 50 | grep -E "\[AI Analyze\]"
```

**정상 로그 예시**:
```
[AI Analyze] === 요청 시작: 005930 ===
[AI Analyze] _ensure_ai_tables: 0.02초
[AI Analyze] usage check: 0.15초
[AI Analyze] === 총 소요: 0.23초, job_id=a1b2c3d4 ===
```

**문제 로그 예시**:
```
[AI Analyze] === 요청 시작: 005930 ===
[AI Analyze] _ensure_ai_tables: 45.23초  ← DB 지연
```

또는 로그 자체가 없으면 → 요청이 서버에 도달하지 않음

---

## 5. 결론

### 5.1 진단 결과

| 항목 | 상태 |
|------|------|
| 프론트엔드 호출 방식 | ✅ 정상 (Job Queue 패턴) |
| Tauri invoke | ✅ 동일한 함수 사용 |
| 백엔드 엔드포인트 | ✅ 즉시 반환 설계 |
| **타임아웃 발생 지점** | ⚠️ Tauri POST 60초 |

### 5.2 추정 원인 (확인 필요)

1. **DB 연결 문제**: PostgreSQL 커넥션 풀 고갈 또는 지연
2. **네트워크 문제**: VPS 연결 불안정
3. **서버 과부하**: Docker 컨테이너 리소스 부족

### 5.3 확인 필요 사항

```bash
# 1. 서버 상태 확인
curl -w "\n응답시간: %{time_total}초\n" http://76.13.180.30/api/health

# 2. AI 분석 POST 직접 테스트
curl -w "\n응답시간: %{time_total}초\n" \
  -X POST http://76.13.180.30/api/ai/analyze \
  -H "Content-Type: application/json" \
  -d '{"symbol":"005930","exchange":"KIS_KR"}'

# 3. DB 연결 상태
docker exec bbooster-db psql -U bbooster -c "SELECT count(*) FROM pg_stat_activity;"

# 4. Docker 리소스
docker stats --no-stream
```

---

## 6. 수정 방향 (수정하지 말 것 - 참고용)

| 우선순위 | 수정 내용 | 파일:라인 |
|---------|----------|----------|
| 1 | 서버 로그 확인하여 정확한 병목 지점 파악 | VPS |
| 2 | `_ensure_ai_tables()` 첫 요청 시에만 실행하도록 변경 | main.py:12280 |
| 3 | DB 커넥션 풀 설정 확인/증가 | database.py |
| 4 | Tauri POST timeout 증가 (60 → 120초) | commands.rs:3163 |

---

## 7. 요약

**문제**: 종목정보 AI분석 버튼 클릭 시 `operation timed out` 에러

**발견사항**:
- 메인 AI분석과 종목정보 AI분석은 **완전히 동일한 코드 경로** 사용
- 두 버튼 모두 Job Queue 패턴으로 정상 구현됨
- 타임아웃은 Tauri POST 60초에서 발생

**근본 원인**:
- 백엔드 POST 응답이 60초 이상 걸림 (정상 시 < 1초)
- **서버 로그 확인이 필수** - 어느 단계에서 지연되는지 파악 필요

**다음 단계**:
1. VPS에서 `docker logs bbooster-app` 확인
2. `[AI Analyze]` 로그에서 각 단계별 소요시간 확인
3. 병목 지점 파악 후 수정 계획 수립

---

## 8. 실제 원인 확정 (2026-02-25 진단 완료)

### 8.1 근본 원인: PostgreSQL idle in transaction 블로킹

**서버 로그 분석:**
```
[AI Analyze] === 요청 시작: 034020 ===
(이후 로그 없음 → _ensure_ai_tables()에서 블로킹)
```

**DB 상태 확인:**
```sql
SELECT pid, state, query, duration FROM pg_stat_activity;

pid   | state               | query                                      | duration
57019 | idle in transaction | SELECT users... WHERE id=1                 | 25:50
57027 | active (대기중)      | ALTER TABLE users ADD COLUMN IF NOT EXISTS | 25:49
```

### 8.2 블로킹 메커니즘

```
이전 요청 → SELECT users (트랜잭션 시작)
         ↓
         트랜잭션 미커밋 (idle in transaction 25분+)
         ↓
AI 분석 요청 → _ensure_ai_tables()
             ↓
             ALTER TABLE users ADD COLUMN... (테이블 락 필요)
             ↓
             락 대기 (무한 대기) → 60초 후 Tauri 타임아웃
```

### 8.3 해결

```bash
# 블로킹 커넥션 강제 종료
SELECT pg_terminate_backend(57019);

# 결과: AI 분석 즉시 정상 작동
[AI Report] Generated report: 4401 chars
[AI Job] 5f52def1 완료: 4401자
```

### 8.4 재발 방지 권장 (수정 필요)

| 우선순위 | 수정 내용 | 파일:라인 |
|---------|----------|----------|
| **1 (필수)** | `_ensure_ai_tables()` 를 서버 시작 시 1회만 실행 | main.py:12280 |
| **2 (권장)** | SQLAlchemy 세션 autocommit 또는 커넥션 타임아웃 설정 | database.py |
| **3 (권장)** | PostgreSQL `idle_in_transaction_session_timeout` 설정 | docker-compose.yml |

**PostgreSQL 설정 예시:**
```sql
-- 5분 후 idle in transaction 자동 종료
ALTER SYSTEM SET idle_in_transaction_session_timeout = '5min';
SELECT pg_reload_conf();
```

### 8.5 최종 결론

- **원인**: DB 트랜잭션 미커밋으로 인한 테이블 락 블로킹
- **해결**: 블로킹 커넥션 강제 종료로 즉시 해결
- **재발 방지**: `_ensure_ai_tables()` 최적화 + DB 타임아웃 설정 필요

# AI 종합분석 타임아웃 진단 보고서

작성일: 2026-02-25

---

## 1. 타임아웃 체인 분석

### 1.1 전체 타임아웃 체인 (End-to-End)

| 구간 | 설정값 | 파일:라인 | 비고 |
|------|--------|-----------|------|
| **Tauri POST** `/api/ai/analyze` | 60초 | commands.rs:3163 | job_id 요청 |
| **Tauri GET** `/api/ai/status/{job_id}` | 10초 | commands.rs:3190 | 폴링 |
| **nginx → uvicorn** | 300초 | /etc/nginx/sites-enabled/* | proxy_read_timeout |
| **uvicorn** | 무제한 | Dockerfile:42 | timeout 미설정 |
| **Claude API (chat)** | 180초 | main.py:12893 | web_search 사용 |
| **Claude API (report)** | 180초 | main.py:14260 | report 생성 |

### 1.2 클라이언트 폴링 설정

| 항목 | 설정값 | 파일:라인 |
|------|--------|-----------|
| 폴링 간격 | 2초 | main.js:4858 |
| 최대 대기시간 | 120초 | main.js:4853, 4839 |
| 최대 폴링 횟수 | ~60회 | 120초 / 2초 |

---

## 2. 아키텍처 분석

### 2.1 요청 흐름 (Job Queue 패턴)

```
[PC App] ─POST→ [/api/ai/analyze] ──→ job_id 즉시 반환 (≈0.5초)
                      │
                      └──→ asyncio.create_task(_run_ai_analysis_job)
                                    │
                                    ├─ 종목 데이터 수집 (~5초)
                                    ├─ Claude API 호출 (~30-120초)
                                    └─ 결과 저장, _ai_jobs[job_id] 업데이트

[PC App] ─GET (2초마다)→ [/api/ai/status/{job_id}] → {status, progress, report}
```

### 2.2 핵심 발견

**POST `/api/ai/analyze` 엔드포인트 (main.py:12269-12379)**:
- 즉시 job_id를 반환하도록 설계됨 (비동기 처리)
- `asyncio.create_task()`로 백그라운드 실행
- **이론상 1초 이내 응답 가능**

**POST 전 수행되는 동기 작업 (타임아웃 가능성 있음)**:
1. `_ensure_ai_tables(db)` - DB 테이블 확인/생성 (line 12280)
2. 사용량 조회 쿼리 (lines 12298-12327)
3. 캐시 확인 쿼리 (lines 12341-12354)

### 2.3 타이밍 로그 (기존 추가됨)

```python
# main.py:12277-12338
t0 = time_module.time()
print(f"[AI Analyze] === 요청 시작: {request.symbol} ===")
_ensure_ai_tables(db)
print(f"[AI Analyze] _ensure_ai_tables: {time_module.time()-t0:.2f}초")
# ...
print(f"[AI Analyze] usage check: {time_module.time()-t0:.2f}초")
# ...
print(f"[AI Analyze] === 총 소요: {time_module.time()-t0:.2f}초, job_id={job_id} ===")
```

---

## 3. 잠재적 원인 분석

### 3.1 가능한 타임아웃 지점

| 지점 | 가능성 | 설명 |
|------|--------|------|
| **POST 요청 자체** | 낮음 | Job Queue 패턴으로 즉시 반환 설계 |
| **DB 연결 지연** | 중간 | `_ensure_ai_tables()` 또는 usage check 쿼리 지연 |
| **네트워크 지연** | 중간 | VPS 연결 불안정 |
| **Claude API 지연** | 높음 | web_search tool 사용 시 30-120초 소요 가능 |

### 3.2 web_search tool 영향

**main.py:12963**:
```python
tools=[{"type": "web_search_20250305", "name": "web_search"}]
```

- web_search 사용 시 Claude가 여러 번 검색 수행
- **응답 시간 30-120초로 크게 증가**
- 현재 timeout=180초로 설정되어 있어 Claude API 자체는 문제 없음

### 3.3 실제 타임아웃 발생 시나리오

1. **Tauri POST 60초 타임아웃**:
   - DB 연결 지연으로 job_id 반환 전 타임아웃
   - 가능성: 낮음 (DB 쿼리는 보통 1초 이내)

2. **클라이언트 폴링 120초 초과**:
   - Claude API 응답이 120초 넘게 걸릴 때
   - 가능성: 중간 (web_search 사용 시)

3. **Claude API 180초 타임아웃**:
   - 매우 복잡한 분석 요청 시
   - 가능성: 낮음 (대부분 60초 이내 완료)

---

## 4. 서버 로그 확인 방법

### 4.1 VPS 로그 확인 명령어

```bash
# SSH 접속
ssh -i ~/.ssh/bbooster_vps root@76.13.180.30

# 최근 AI 관련 로그
docker logs bbooster-app --tail 100 | grep -E "\[AI"

# 타이밍 로그 확인
docker logs bbooster-app --tail 200 | grep -E "AI Analyze|AI 시간"

# 에러 확인
docker logs bbooster-app --tail 100 | grep -i "error\|timeout\|exception"
```

### 4.2 기대 출력 예시 (정상)

```
[AI Analyze] === 요청 시작: 005930 ===
[AI Analyze] _ensure_ai_tables: 0.02초
[AI Analyze] usage check: 0.15초
[AI Analyze] === 총 소요: 0.23초, job_id=a1b2c3d4 ===
[AI Report] Collecting data for 삼성전자(005930)...
[AI 시간] 기술 데이터 수집: 2.3초
[AI 시간] 재무 데이터 수집: 1.1초
[AI 시간] 뉴스 수집: 1.5초
[AI Report] Calling Claude API...
[AI Report] Generated report: 3500 chars
[AI Job] a1b2c3d4 완료: 3500자
```

### 4.3 기대 출력 예시 (문제 발생 시)

```
[AI Analyze] === 요청 시작: 005930 ===
[AI Analyze] _ensure_ai_tables: 45.23초   ← DB 연결 문제
...
[AI Report] Claude API error: APITimeoutError: Request timed out.  ← Claude 타임아웃
```

---

## 5. 결론 및 권장 수정 방향

### 5.1 현재 상태 요약

| 항목 | 상태 | 판정 |
|------|------|------|
| Tauri POST timeout | 60초 | ✅ 충분 (job_id 반환은 1초 이내) |
| Tauri GET timeout | 10초 | ✅ 충분 (상태 조회는 1초 이내) |
| 클라이언트 폴링 | 120초 | ⚠️ web_search 시 부족할 수 있음 |
| Claude API timeout | 180초 | ✅ 충분 |
| nginx timeout | 300초 | ✅ 충분 |

### 5.2 권장 수정 사항 (우선순위순)

1. **클라이언트 폴링 대기시간 증가** (선택사항)
   - 현재: 120초
   - 권장: 180초 (Claude API timeout과 동일)
   - 파일: `pc-app/ui/src/main.js:4853, 4839`

2. **서버 로그 확인 필수**
   - 실제 타임아웃 발생 시 로그 분석으로 정확한 병목 파악
   - 특히 `_ensure_ai_tables`와 DB 쿼리 소요시간 확인

3. **web_search 비활성화 테스트** (원인 규명용)
   - 임시로 web_search tool 제거하여 응답시간 비교
   - `main.py:12963` 라인 주석 처리

### 5.3 최종 판단

**현재 코드상 명백한 타임아웃 원인 없음.**

타임아웃이 실제로 발생한다면:
1. 서버 로그 확인하여 정확한 병목 지점 파악 필요
2. DB 연결 상태 확인 (PostgreSQL 커넥션 풀)
3. 네트워크 상태 확인 (VPS ↔ Anthropic API)

---

## 6. 추가 진단 명령어

```bash
# 1. PostgreSQL 연결 상태
docker exec bbooster-db psql -U bbooster -c "SELECT count(*) FROM pg_stat_activity;"

# 2. API 응답시간 테스트 (curl)
curl -w "\n시간: %{time_total}초\n" -X POST \
  -H "Content-Type: application/json" \
  -d '{"symbol":"005930","exchange":"KIS_KR"}' \
  https://qube-system.com/api/ai/analyze

# 3. Claude API 직접 테스트 (Python)
python -c "
import anthropic
import time
t0 = time.time()
client = anthropic.Anthropic()
resp = client.messages.create(
    model='claude-haiku-4-5-20251001',
    max_tokens=100,
    messages=[{'role':'user','content':'Hello'}]
)
print(f'응답시간: {time.time()-t0:.2f}초')
"
```

---

**진단 완료. 수정 필요 시 서버 로그 확인 후 정확한 병목 지점 파악이 선행되어야 함.**

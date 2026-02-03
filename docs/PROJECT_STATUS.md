# PROJECT_STATUS.md (SSOT)
- Last updated: 2026-02-03 KST
- Owner: 기훈(작가님)

> NOTE: 이 파일이 '진실(SSOT)'입니다. 채팅은 인터페이스일 뿐.
> 변경 시 반드시 근거(파일/코드/PS 실측 출력)를 docs/APPENDIX_LOG.md에 남기고 커밋합니다.

---

# 0) 절대 규칙 (SSOT / 절대 위반 금지)
1) 진행상태/완료여부 판단 기준은 "docs/PROJECT_STATUS.md(=이 문서)"만. (채팅 아님)
2) 운영 루틴 고정: stop → syntax → run → /tv test (이 순서 외 금지)
3) Hub 원칙: 신호판단/추천/스크리닝/자동선정 X
4) /tv는 500 금지. 예외는 반드시 `ok=false` + `code=exception` + `detail` 포함으로만 반환.
5) 작업 시작 전 docs/AI_RULES.md 필독 + 레포 파일 구조 확인
   - 스코프 제외(절대 건드리지 않음): SMC 전략/SMC 파일, MFT 캔들 관련 파일/로직

---

# 1) 제품 방향
- 마케팅/소개 = 웹, 대시보드 = 웹(로그인), 계좌/API키/설정 = 프로그램(PC)/앱
- 보안: 출금 권한 없는 키 + 2차인증 + E-STOP(웹/프로그램/앱 3곳)
- 증권사: KIS만 (키움 제외)

---

# 2) 개발 환경
- 작업 폴더: C:\Users\pc\새 폴더\AUAT
- 서버: FastAPI(Uvicorn) http://127.0.0.1:8000
- Swagger: http://127.0.0.1:8000/docs

## 운영 루틴
- STOP: scripts/stop.ps1 또는 Ctrl+C
- SYNTAX: `python -m compileall app`
- RUN: scripts/run.ps1 또는 `python -m uvicorn app.main:app --reload --port 8000`

---

# 3) 파일 구조
- app/main.py: FastAPI 엔드포인트 (핵심)
- app/connectors/: OKX, KIS 커넥터
- scripts/: run.ps1, stop.ps1, week4_regression.ps1, kis_regression.ps1
- docs/: PROJECT_STATUS.md(SSOT), AI_RULES.md, APPENDIX_LOG.md

---

# 4) 환경변수 키 (값 노출 금지)
- DATABASE_URL, DRY_RUN, ORDER_SUBMIT_ENABLE, ORDER_POLL_ENABLE
- OKX_*: API_KEY, API_SECRET, API_PASSPHRASE, BASE_URL, SIMULATED
- KIS_*: APP_KEY, APP_SECRET, CANO, ACNT_PRDT_CD, SVR, SIMULATED

---

# 5) 핵심 엔드포인트
| Method | Path | Description |
|--------|------|-------------|
| POST | /tv | TradingView webhook (500 금지) |
| GET | /api/home | 전광판 요약 |
| POST | /api/diag/send-now | 주문 전송 |
| POST | /api/diag/poll-now | 체결 조회 |
| GET | /api/diag/kis-preflight | KIS 연결 체크 |
| GET | /api/diag/kis-balance | KIS 잔고 |
| GET | /api/diag/connector-test | 커넥터 테스트 (Week7) |

---

# 6) 개발 일정 (12주)

## 원칙
- Day 단위 체크리스트가 SSOT의 "현재 위치"를 만든다. (완료/미완료는 API 실측/파일 증거로만)
- OKX Week4 회귀 게이트(week4_regression.ps1 -FailOnContradiction PASS)를 절대 깨지 않는다.
- KIS(한투)는 12주 계획 안에 Day 단위로 포함한다.
- Hub 원칙(신호판단/추천/스크리닝/자동선정 X) 위반하는 기능은 일정에 넣지 않는다.
- 선물(Futures)은 전면 미지원(설계/구현/QA 범위에서 제외).

## Week 1: DONE
Day 1~5: (기존 SSOT 동일, 삭제 없음)

## Week 2: DONE
Day 1~5: (기존 SSOT 동일, 삭제 없음)

## Week 3: DONE
Day 1~5: (기존 SSOT 동일, 삭제 없음)

## Week 4: DONE (2026-01-30 KST 실측)
Day 1~5: (기존 SSOT 동일, 삭제 없음)

## Week 5: 커넥터 표준화(OKX 정리) + KIS 착수(스켈레톤) — DONE (2026-02-02 KST)
Day 1: 커넥터 공통 인터페이스 정의(PlaceOrder/GetOrder/Balance/Markets) + 결과 타입 명세
Day 2: OKX 호출 경로 "단일화" 고정(중복 def 방지 원칙 문서화) + 회귀 게이트 유지
Day 3: main.py OKX 관련 "직접호출 흔적 제거/정리" (connector-only) + week4_regression PASS 유지
Day 4: KIS 커넥터 스켈레톤 생성(인증/토큰/요청 래퍼 틀) + .env 키 목록만 추가(값 금지)
Day 5: "다중 커넥터 선택" 최소 라우팅(계좌 exchange 필드 기반) 설계만(실주문 X) + 문서/grep 증거 남김

## Week 6: KIS 기본 실측(잔고/토큰/드라이런) + DB 매핑 초안 — DONE (2026-02-02 KST)
Day 1: KIS 잔고 조회 실측 + 추가 환경변수 문서화
Day 2: KIS 토큰 갱신/만료 핸들링 검증
Day 3: 드라이런(DRY_RUN) 플래그 KIS 경로 적용 확인
Day 4: DB 매핑 초안 (orders 테이블 KIS 컬럼 검토) — KIS 필요: kis_order_no/kis_order_date/kis_state
Day 5: KIS 실측 회귀 테스트 작성 + 문서화 (scripts/kis_regression.ps1 PASS)

## Week 7: KIS 주문/조회/체결추적 최소("MVP 루프") + "주식(국내/해외) 표준화" — DONE (2026-02-03 KST)
Day 1: KIS place_order/get_order 구현
Day 2: KIS 주문 테스트 엔드포인트 추가(국내/해외 공통) + 심볼 정규화 규칙 확정(6자리/티커)
Day 3: KIS 체결 추적(polling) 구현 + 상태맵(kis_state→internal status) 고정
Day 4: main.py에 KIS 경로 연결(send-now/poll-now 최소 루프) + 전광판 last_* 반영
Day 5: KIS MVP 회귀 테스트(PowerShell) + 문서화(실측 원문 APPENDIX에 누적)
- 추가: exchange_order_id 공통 필드, KIS get_balance_split/get_markets, Connector 팩토리 (2026-02-03)

## Week 8: 얼러트 메시지 "환불 방지 패키지"(기본/고급 모드) — IN PROGRESS
Day 1: 표준 TradingView 템플릿 1종(현물/주식 공용) 확정 + docs에 "복붙 예시" 추가 — DONE (2026-02-03)
- 생성: docs/TV_TEMPLATE.md (OKX/KIS 공용 복붙 예시 포함)
Day 2: /tv payload 검증 강화(필수필드/심볼/마켓/계좌 매칭) + 에러코드 표준화(환불 방지) — DONE (2026-02-03)
- 추가: missing_side, invalid_side, missing_qty, invalid_qty 검증
- 개선: 모든 에러 메시지 한글화 + 해결방법 안내
Day 3: "템플릿 생성 API"(templates/tradingview 확장) — 계좌/자산/전략 선택하면 자동 생성 — DONE (2026-02-03)
- GET /api/templates/tradingview/options (옵션 목록)
- GET /api/assets/{asset_id}/template/tradingview (자산별 생성)
- POST /api/templates/tradingview/generate (다중 일괄 생성)
Day 4: (선택) 간단 Wizard 문서(스크린샷 없이 텍스트 기준) + 체크리스트(초보자용)
Day 5: 회귀 스크립트 1개 추가(tv_template_regression.ps1) + PASS 기준 정의

## Week 9: Upbit Spot 착수(필요 시) + 멀티 커넥터 공통화 — TODO
Day 1~5: (OKX/KIS 구조 유지하면서 Upbit spot은 "필요 시"만)

## Week 10: 운영/관측/장애대응(M11) — TODO
Day 1~5: (기존 SSOT 동일, 삭제 없음)

## Week 11: 보안/키관리/2차인증 설계 고정 — TODO
Day 1~5: (기존 SSOT 동일, 삭제 없음)

## Week 12: 정리/리팩토링 최소 + 릴리즈 패키징/문서 — TODO
Day 1~5: (기존 SSOT 동일, 삭제 없음)

---

# 7) NEXT ACTION (3개)
1) Week8 Day4 착수: (선택) 간단 Wizard 문서 + 체크리스트
2) 회귀 게이트 유지 (week4_regression + kis_regression)
3) 작업 전 docs/AI_RULES.md 필독

---

[END OF SSOT]

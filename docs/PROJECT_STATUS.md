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

---

# 6) 개발 일정 (12주)

## Week 1~7: DONE
- OKX 주문/체결 루프, KIS MVP (place_order, get_order, polling, routing)

## Week 8: 멀티 커넥터 공통화 — DONE
- Day1: 공통 인터페이스 정의 (DONE)
- Day2: exchange_order_id 공통 필드 추가 (DONE)
- Day3: KIS get_balance_split 구현 (DONE)
- Day4: KIS get_markets 구현 (DONE)
- Day5: Connector 팩토리 + 테스트 엔드포인트 (DONE)

## Week 9~12: TODO
- 구독/쿼터, 운영/관측, 보안/키관리, 릴리즈

---

# 7) NEXT ACTION (3개)
1) Week9 착수: 구독/쿼터 또는 운영/관측
2) 회귀 게이트 유지 (week4_regression + kis_regression)
3) 작업 전 docs/AI_RULES.md 필독

---

[END OF SSOT]

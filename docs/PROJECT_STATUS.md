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
- **상세 제품 아키텍처**: [docs/PRODUCT_SPEC.md](PRODUCT_SPEC.md) (사이트/PC/앱 역할, 허브형/프리미엄형, 구독/권한)

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

# 6) 개발 일정 (16주, v2)

## 게이트(절대)
- **Gate-OKX**: scripts/week4_regression.ps1 -FailOnContradiction PASS 유지(깨지면 즉시 원복)
- **Gate-TV**: scripts/tv_template_regression.ps1 PASS 유지
- **Gate-E-STOP**: E-STOP ON에서 send-now 차단 실측 유지

## 원칙
- 완료/미완료는 PS 실측/파일/코드근거로만 판정. 주차 숫자보다 모듈 게이트 우선.
- Hub 원칙(신호판단/추천/스크리닝/자동선정 X) 위반하는 기능은 일정에 넣지 않는다.
- 선물(Futures)은 전면 미지원(설계/구현/QA 범위에서 제외).

## Week 1~4: DONE (DB+UI 기본/OKX 루프/회귀 게이트 정착)
- 증거: APPENDIX(week4_regression PASS), /tv accepted, poll-now filled, recover PASS

## Week 5~6: DONE (OKX 커넥터 단일화 + KIS 착수/실측/회귀 기반)
- 증거: KIS diag/home refresh_kis timestamp, kis_regression PASS 등

## Week 7: DONE (KIS place_order/get_order 골격 + 라우팅 최소)
- 증거: APPENDIX_LOG.md 실측 원문

## Week 8: DONE (환불 방지 패키지 v1 + ShortMsg)
- 포함: TV_TEMPLATE.md, /tv 검증 강화, 템플릿 생성 API, TV_WIZARD.md, tv_template_regression.ps1, ShortMsg
- 증거: APPENDIX_LOG.md 2026-02-03 원문(회귀 PASS, connector-test OK)

## Week 9: 3종 제품 아키텍처 고정 + 구독/권한 뼈대 — DONE
Day 1: SSOT에 3종 역할/범위(사이트/PC/앱) + 허브/프리미엄 경계 확정 — DONE (2026-02-03)
- 생성: docs/PRODUCT_SPEC.md (1-6 ~ 1-9)
- 커넥터 팩토리 모듈화: app/connectors/__init__.py, scripts/connector_regression.ps1
Day 2: 서버에 Auth 토큰 스펙(초안) + /api/subscription/me(스텁) 설계 — DONE (2026-02-03)
- 생성: docs/AUTH_SPEC.md (Plan/Entitlement 정의, 동기화 플로우)
- 구현: /api/subscription/me 스텁 엔드포인트
Day 3: Plan/Entitlement 모델 확정 + 서버 응답형식 고정 — DONE (2026-02-03)
- Pydantic 모델: PlanType, Entitlements, SubscriptionResponse, SubscriptionErrorResponse
- PLAN_DEFAULTS: free/hub/premium 기본 권한값 확정
Day 4: PC/앱 "실행 시 구독 동기화" 플로우 문서화 — DONE (2026-02-03)
- AUTH_SPEC.md 5) 섹션 확장: 실행 시 동기화, 토큰 만료, 주기적 동기화, 오프라인 모드
- 기능 잠금/해제 매핑, 에러 메시지, 로컬 저장 보안 가이드
Day 5: 회귀: Gate-OKX/Gate-TV/Gate-E-STOP 전부 PASS — DONE (2026-02-03)
- Gate-OKX: week4_regression.ps1 PASS
- Gate-TV: tv_template_regression.ps1 PASS
- Gate-E-STOP: E-STOP ON 시 send-now 차단 확인

## Week 10: 종합 UI v1(공통 데이터) — 타임라인/마커/성과 최소 — DONE
Day 1: 이벤트(타임라인) 스키마 확정 + DB/로그 저장 방식 결정 — DONE (2026-02-03)
- 생성: docs/TIMELINE_SPEC.md (이벤트 타입, 스키마, API 스펙)
- 구현: app/models.py Event 모델 추가
Day 2: GET /api/timeline 구현 + PS 실측 — DONE (2026-02-03)
- 구현: /api/timeline 엔드포인트 (asset_id, order_id, limit, offset 필터)
- Fallback: events 테이블 없으면 orders 테이블에서 이벤트 생성
Day 3: /api/home에 최근 이벤트 요약 5개 추가 — DONE (2026-02-03)
- 구현: recent_events 필드 추가
Day 4: 타임라인 HTML 뷰어 — DONE (2026-02-03)
- 구현: /ui/timeline 엔드포인트 (최소 HTML 렌더링)
Day 5: 회귀 게이트 전체 PASS — DONE (2026-02-03)
- Gate-OKX: PASS, Gate-TV: PASS, timeline: PASS

## Week 11: PC 프로그램(설정 본체) v1 — 키/계좌/전략/템플릿/로그 — IN PROGRESS
Day 1: PC 앱 기술선정 고정 + 빌드/런 구조 문서화 — DONE (2026-02-03)
- 선정: Tauri (Rust + Web, 가벼움, 보안 우수)
- 생성: docs/PC_APP_SPEC.md (아키텍처, 디렉토리 구조, 빌드/런, 보안)
Day 2: 계좌/키 등록 UI + 로컬 암호화 저장 — DONE (2026-02-03)
- PC_APP_SPEC.md 7) Day 2 상세: UI 구성, Tauri 커맨드 (Rust), 보안 체크리스트
Day 3: PC: 템플릿 생성(assets/template, batch generate, shortmsg template) UI 연결 — DONE (2026-02-03)
- 구현: PC_APP_SPEC.md 8) Day 3 상세 (UI 구성, API 연동, Tauri 커맨드, 워크플로우)
Day 4: PC: 시스템 설정(E-STOP, DRY_RUN, submit/poll enable) UI 연결
Day 5: 회귀: PC 조작 후 서버 API 상태 변화 실측 로그 누적

## Week 12: 앱(모바일) v1 — 관측/알림/E-STOP — TODO
Day 1: 앱 기술선정 고정(Flutter/ReactNative 중 1) + 인증/토큰 저장 정책 문서화
Day 2: 앱: 대시보드(계좌/자산/주문 상태 요약) 읽기 전용 화면
Day 3: 앱: E-STOP ON/OFF 버튼 + 실측(차단 동작 확인)
Day 4: 앱: 알림 설계(푸시/로컬) "어떤 이벤트에 알림을 보낼지" 확정
Day 5: 회귀: 앱 경유 E-STOP 동작 + Gate-OKX/Gate-TV PASS

## Week 13: 프리미엄 엔진 v0(신호판단 포함) — TODO
> 단, 종목추천/자동선정/스크리너 금지 준수
Day 1: 프리미엄 엔진 경계 정의(입력: 사용자 지정 asset, 출력: signal event) + 정책 문서화
Day 2: 엔진 파라미터 스키마(프리미엄 설정) + 저장/버전/검증 규칙
Day 3: 엔진 → 주문 파이프라인 연결("signal 생성"만, sizing/guard는 Hub 규칙 유지)
Day 4: 회귀: 프리미엄 엔진 OFF/ON 전환 시 동작 차이 실측
Day 5: 리스크: 오주문 방지/과도 신호 방지(쿨다운/일일제한) 기본 가드 적용

## Week 14: 결제/구독 연동 v1 — 사이트 정본, PC/앱 entitlement 동기화 실구현 — TODO
Day 1: 결제 프로바이더(Stripe/토스 등) 1개 선정 + 최소 플로우 문서화
Day 2: /api/subscription/me 실구현 + 만료/업그레이드 반영
Day 3: PC/앱: 실행 시 entitlement fetch + 기능 잠금/해제 적용
Day 4: 환불/만료/다운그레이드 시나리오 테스트(PS 실측 + UI 반영)
Day 5: 회귀: 기존 Gate + entitlement 시나리오 PASS

## Week 15: 운영/관측/장애대응 v1 — 로그/리커버리/CS 대응 — TODO
Day 1: 에러코드 카탈로그 정리(/tv 포함) + "환불 방지" 문구 고정
Day 2: 주문/체결 상태모델 통합 점검(OKX/KIS) + terminal/retryable 규칙 확정
Day 3: 리커버리(runbook) 문서화 + scripts 정리
Day 4: 관리자/CS용 조회 API(읽기 전용) 최소 추가
Day 5: 회귀 + 장애 시나리오 리허설(네트워크/키오류/잔고부족)

## Week 16: 릴리즈 패키징/문서/법적고지 최종 — "출시 가능한 1.0" — TODO
Day 1: 설치/업데이트/다운로드(사이트) 플로우 정리
Day 2: 온보딩 문서(PC 기준) + 앱 관측 가이드
Day 3: 약관/면책/리스크 고지 문서 확정(사이트 반영)
Day 4: 최종 회귀(OKX/KIS/TV/ShortMsg/구독/E-STOP) 전체 PASS
Day 5: SSOT/APPENDIX 정리(증거 누락 없게), 릴리즈 태그 준비

---

# 7) NEXT ACTION (3개)
1) Week 11 Day 4: 시스템 설정(E-STOP, DRY_RUN, submit/poll enable) UI 연결
2) 회귀 게이트 유지 (Gate-OKX + Gate-TV + Gate-E-STOP)
3) 작업 전 docs/AI_RULES.md + docs/PC_APP_SPEC.md 필독

---

[END OF SSOT]

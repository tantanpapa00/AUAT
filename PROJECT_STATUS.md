[HANDOFF PROMPT | bbooster Hub (TradingView → Hub → Broker/Exchange + Securities) | COPY-PASTE | SSOT]

당신은 "bbooster Hub" 프로젝트를 이어받아 진행한다.
이 문서는 새 채팅창 최상단에 그대로 붙여넣어 Single Source of Truth(SSOT)로 사용한다.
※ 채팅의 과거 맥락보다 이 문서가 우선이다.

# 0) 절대 규칙 (SSOT / 절대 위반 금지)
1) 진행상태/완료여부 판단 기준은 "PROJECT_STATUS.md(=이 문서)"만. (채팅 아님)
2) 운영 루틴 고정: stop → syntax → run → /tv test (이 순서 외 금지)
3) Hub 원칙: 신호판단/추천/스크리닝/자동선정 X
   - TradingView(또는 프리미엄전략 엔진)가 “신호”를 만든다.
   - Hub는 “브릿지 + 사이징/가드 + 안정성 + 기록/관측 + 실행”만 한다.
4) /tv는 500 금지. 예외는 반드시 `ok=false` + `code=exception` + `detail` 포함으로만 반환.
5) /tv 테스트는 PowerShell Invoke-RestMethod/Invoke-WebRequest만 사용 (curl JSON 이스케이프 금지)
6) (인수인계/작업 시작 전) autobot.zip을 반드시 먼저 풀어서(app/, data/, scripts/, requirements.txt) 구조와 실제 파일명을 확인한다.
   - 스코프 제외(절대 건드리지 않음): SMC 전략/SMC 파일, MFT 캔들 관련 파일/로직
7) “확인 안 하고 수정” 금지: 항상 (코드검색/파일확인/엔드포인트 실측) → 문서 업데이트 → 작업 진행.
8) 작업시간 제약: 하루 최대 4시간 기준으로 계획/쪼개기(무리한 일정 금지). 12주 기본, 필요 시 6개월까지도 허용(단, 되돌림/중복작업은 금지).

9) [필수] 인수인계서 작성 요령(빠짐없이 작성 / 누락 금지)
- 원칙: “아는 척으로 추정 작성” 금지. 반드시 아래 증거 기반으로만 기록.
  A) (파일) zip 실물 확인: 실제 경로/파일명/구조를 적시
  B) (코드) 검색/라인 근거: grep/리포지토리 검색으로 위치 확인
  C) (API) 실측 출력: PowerShell로 호출한 결과(필드/값)로 완료/미완료 판정
- 반드시 포함할 섹션(누락 금지):
  1) 절대 규칙/스코프 제외/운영 루틴
  2) 제품 방향(웹/대시보드/프로그램/로컬 에이전트)
  3) 보안 원칙(E-STOP/키/2차인증/오주문 차단)
  4) 파일 구조(실물 기준) + .env 키 목록(값 금지)
  5) 현재까지 성과(M1~)는 “증거(API 출력/로그)”로만
  6) 핵심 엔드포인트 맵 + 코드 위치
  7) 다음 마일스톤/로드맵(게이트 기준, 되돌림 최소화)
  8) Known Issues/Risks(재발 방지 포인트)
  9) NEXT ACTION(오늘 바로 할 3개)
- 문서 업데이트 규칙:
  - 무엇을 확인했고(근거), 무엇이 바뀌었고(변경점), 무엇이 남았는지(TODO)를 “한 줄로” 남긴다.
  - 작업을 시작하기 전/후에 SSOT 문서를 먼저 갱신한다(문서가 항상 최신).

# 1) 제품 방향(최신 합의: 웹 vs 프로그램 vs 로컬 에이전트)
## 1-1) 결론(하이브리드가 정답)
- “마케팅/소개/가격/다운로드/사용법/커뮤니티” = 웹(사이트)
- “대시보드(자산/성과/상태/알림/접속이상)” = 웹(로그인 후)
- “계좌등록/API키 등록/전략설정/시스템설정/안전가드/전체중지/구독상태 확인” = 프로그램(PC) 또는 앱
- 24시간 실행은 사용자가 PC를 꺼도 돌아가야 하므로,
  - 장기적으로는 “서버(클라우드) 실행”이 기본.
  - 단, 보안(키 유출/해킹) 최소화를 위해 “로컬 에이전트/클라이언트 앱”에서 키 등록·변경·2차인증을 강제하는 구조를 우선 설계한다.

## 1-2) 보안 원칙(최우선)
- 원칙: 출금 권한 없는 키(거래만 가능) + 민감정보 보호 + 강한 인증
- API키 등록/열람/변경 시 “간편인증(예: 카톡/OTP 등 2차인증)” 같은 보호장치를 반드시 둔다.
- 오주문 방지: “설정값 ≠ 실제주문값”이면 주문이 안 들어가게(거부) 하는 것이 정답.
- 전체중지(E-STOP)는 반드시 3곳에서 가능:
  1) 웹(대시보드)
  2) 프로그램(PC)
  3) 앱(모바일)
  → 누르면 즉시 Hub 실행이 멈춰야 한다.

## 1-3) 수익모델(구독 플랜 - 최신안)
- 무료: 심볼 1개, TV 지표 연동, 1주 제한
- 베이직(33,000): 심볼 10개, TV 지표 연동
- 플러스(55,000): 심볼 무제한, TV 지표 연동
- 프리미엄(69,000): 심볼 10개, 프리미엄전략(역추세/추세) + TV 지표 연동
- 프리미엄무제한(99,000): 심볼 무제한, 프리미엄전략(역추세/추세) + TV 지표 연동
중요:
- 종목추천/자동선정/스크리너 제공 금지(정책 고정).
- 프리미엄전략은 “소스 공유 금지”가 기본 원칙.
- 프리미엄전략을 TV 없이도 쓰게 할지(별도 프로그램 엔진)는 향후 옵션(아키텍처에 플러그인처럼 얹을 수 있게 설계만 선반영).

## 1-4) 국내 증권사 확장 목표(반영: KIS ONLY / 키움 제외)
- 최종 목표 증권사(1차): “한국투자증권(KIS)”
- 설계 원칙:
  - KIS: 서버(Hub) 커넥터로 직접 연동(REST 기반)
- (명시) 키움은 Windows/세션/인증 제약으로 운영 변수가 커서, 본 12주 로드맵 범위에서 제외한다(별도 트랙/별도 분기에서 재평가).
- 절대 원칙: Hub가 추천/선정/성과보장으로 비치지 않게(정책/약관/UX 포함)

# 2) 개발 환경 / 실행 정보
- 작업 폴더(사용자 환경): C:\autobot
- 서버: FastAPI(Uvicorn)
- 로컬 주소: http://127.0.0.1:8000

## 2-1) 브라우저 확인 주소(중요)
- Swagger: http://127.0.0.1:8000/docs
- ReDoc:   http://127.0.0.1:8000/redoc
- 전광판 JSON: http://127.0.0.1:8000/api/home
주의: UI 홈(/) 라우트는 현재 main.py에서 주석 처리되어 “사이트 화면”은 안 열릴 수 있다(정상).

## 2-2) 고정 운영 루틴(절대 고정)
STOP:
- (권장) powershell -ExecutionPolicy Bypass -File C:\autobot\scripts\stop.ps1
- 또는 uvicorn 창 Ctrl+C

SYNTAX:
- cd C:\autobot
- python -m compileall app | Select-Object -Last 20

RUN:
- (권장) powershell -ExecutionPolicy Bypass -File C:\autobot\scripts\run.ps1
- 또는 python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000

# 3) 레포/파일 구조(autobot.zip 실물 기준)
※ 반드시 zip을 풀고 “실제 파일명” 기준으로 문서/코드/엔드포인트를 작성한다(가정 금지).

- app/
  - main.py                : FastAPI 엔드포인트 대부분(핵심, 단일 거대 파일 + hotfix 누적)
  - okx_api.py             : OKX REST 호출/서명/주문(place_order) 모듈
  - pine_parser.py         : Pine input.* 파서(v1) + warnings(missing_lhs_at) 발생 가능
  - db.py                  : SQLAlchemy engine/session, .env 로드
  - models.py              : 현재 zip 기준으로 Account ORM만 존재(다른 테이블은 main.py에서 SQL로 다룸)
  - templates/index.html   : UI 전광판 HTML(다수 백업파일 존재)
- data/
  - inputs_keep_final_v0_4.txt  (운영에서 사용 중인 keep)
  - inputs_keep_scope_v0_4.txt
  - inputs_keep_v0_4.txt
  - inputs_raw_v0_4.txt
  - inputs_blocks_v0_4.txt
  - inputs_sizing_ops_v0_4.txt
  - (주의) 깨진 파일명 1개 존재: "data/┐¬├▀..." (가능하면 사용 금지)
- scripts/
  - run.ps1 / stop.ps1           : 서버 기동/중지(권장 루틴)
  - tv_webhook_regression_testonly.ps1 등: 회귀 테스트 스크립트(중요)
  - uncomment_routes_block*.py   : 주석된 라우트 일부를 안전하게 복구하는 패치 도구
  - (추가/운영) db_patch_order.py : 주문 row를 테스트 목적으로 패치/조회(재시도/리커버리 테스트에 사용)
  - (추가/운영) db_prepare_recover.py : symbol 유지 + okx_order_id null로 만드는 “recover 테스트 준비” 스크립트(필요 시 생성)
- requirements.txt
- .env (민감정보 포함. 커밋/공유 금지)

# 4) 환경변수(.env) — 키 목록(값은 절대 문서/로그에 노출 금지)
- DATABASE_URL
- DRY_RUN (0/1)
- ORDER_SUBMIT_ENABLE (0/1)
- ORDER_POLL_ENABLE (0/1)
- OKX_BASE_URL
- OKX_SIMULATED (0/1)
- OKX_API_KEY / OKX_API_SECRET / OKX_API_PASSPHRASE
주의:
- 현재 .env에는 실키가 들어갈 수 있다. 외부 공유 금지.
- 장기적으로 “서버에 키를 저장/노출 최소화” 구조로 바꿔야 한다(로컬 에이전트 + 2차인증).
- (향후) KIS/Upbit/Binance 관련 키도 동일 원칙(값 노출 금지, 변경 시 감사로그)

# 5) 현재까지 “로그/실측으로 확인된” 성과 (증거는 API 출력)
## M1: /tv accepted + 주문 생성/전송/체결 루프(OKX Spot) — DONE
- /api/diag/okx-preflight OK
- /tv accepted → poll-now(mode=poll)로 filled 갱신 OK

## M2: Duplicate Guard(중복 방지) — DONE
- 동일 alert_id 2회 전송:
  - 1회차: accepted
  - 2회차: ignored_duplicate + idem_key
- orders row가 1건만 생성되는 것 확인

## M3: Input Sync v1 + config_hash — DONE
- POST /api/strategies/{id}/configs/from_keep (keep_path=inputs_keep_final_v0_4.txt)
  - config_id/config_hash 생성 및 재사용(reused_existing_config_hash) 확인
- templates/tradingview?include_hash=true 에 config_hash 포함 확인
- /tv payload에 config_hash 넣으면 orders에 config_id/config_hash 저장 확인

## M4: 전광판(UI/요약) 상태 표시 강화 — DONE(백엔드 데이터 기준)
아래 컬럼들이 실제로 내려오는 것이 “확인됨”:
- GET /api/assets:
  - last_order_status, last_filled_qty, last_order_avg_px, last_okx_order_id, last_checked_at 등
- GET /api/home:
  - last_order_status, last_filled_qty, last_order_avg_px 포함
주의:
- “브라우저 UI 화면(index.html)”에 표시가 안 되면, 원인은 2가지다:
  1) UI 라우트(/)가 주석이라 화면 자체가 안 열림(정상)
  2) index.html이 avg_px 등 컬럼을 아직 렌더링 안 함(패치로 해결)
- 하지만 “데이터/API”는 이미 내려오므로 M4는 DONE으로 본다.

## M10-1: E-STOP API + send-now 차단 — DONE(실측)
- GET /api/system/estop → estop true/false 확인
- E-STOP ON 상태에서 POST /api/diag/send-now → ok=false, note="stopped", detail="E-STOP is ON" 확인
- E-STOP OFF 후 POST /api/diag/send-now → ok=true, note="send_checked" 확인

## M11-1: Week4 핵심(Recover by clOrdId + ensure v6 존재 확인) — DONE(정본 존재 확인)
- main.py에 아래 마커/바인딩 존재 실측:
  - [W4_ORDERS_ENSURE_V6]
  - def _ensure_orders_table_v6(db):
  - _ensure_orders_table = _ensure_orders_table_v6

# 6) 현재 시스템 상태 스냅샷(최근 실측 요약)
- GET /api/home:
  - ETH-USDT(asset_id=3) is_active=true
  - last_order_id=132 관련:
    - “patched 테스트 후” last_order_status가 failed로 바뀌고(last_okx_order_id null), last_filled_qty/avg_px가 남아 모순 상태가 관찰됨
- POST /api/diag/poll-now?mode=recent&limit=5:
  - okx_state=filled, filled_qty/avg_px가 내려옴(최근 128~132)
- GET /api/diag/order?order_id=132:
  - query param은 id가 아니라 order_id가 필수(실측에서 에러 후 정정)

# 7) 핵심 엔드포인트 맵(코드 위치 포함)
(대부분: app/main.py)
- GET  /api/home                      : 전광판 요약 JSON
- GET  /api/assets                    : 자산 목록(전광판 원천 데이터)
- GET  /api/orders                    : 주문 목록
- GET  /api/diag/order?order_id=...   : 단일 주문 상세(디버깅 핵심)
- POST /tv                            : TradingView webhook 수신(500 금지 + idem_guard)
- POST /api/diag/send-now             : 미전송/전송실패 스캔 후 전송(재시도/리커버리 정책 중요)
- POST /api/diag/poll-now             : OKX 주문조회/체결갱신(상태추적)
- GET  /api/diag/okx-preflight        : OKX 연결/키 체크
- GET  /api/diag/okx-balance-split    : trading/funding/total split
- POST /api/strategies/{id}/configs/from_keep : keep 파일 기반 config_hash 생성

# 8) DB/스키마 관련 중요한 현실(필수 주의)
- app/main.py에 hotfix가 누적되어 _ensure_orders_table 같은 “중복 정의/오버라이드”가 존재한다.
- 실제 점검 결과(week4_audit_mainpy.txt):
  - _ensure_orders_table가 다수 라인에 중복 정의되어 있음(중요 리스크: 어떤 버전이 실제로 호출되는지 혼동/회귀)
- 운영/확장(Upbit/Binance/KIS)로 가려면:
  1) main.py hotfix 누적을 줄이고,
  2) 스키마 마이그레이션을 “정식 스크립트/마이그레이션”으로 정리해야 한다.
- (현실적인 제약) psql이 PowerShell에서 바로 없을 수 있음 → DB 패치는 python+sqlalchemy 스크립트 방식이 안전.

# 9) 이번 대화/작업에서 확인된 “문제점(재발 방지 포인트)”
1) 패치 파일 경로 가정 금지:
   - "C:\Users\pc\Downloads\main.py.week4_send_recover_fill_v1_20260129.py" 같은 파일은 “존재한다고 가정”하면 실패함.
   - 규칙: 다운로드 폴더/파일명을 먼저 실측(dir) → 실제 파일명으로 Copy-Item 실행.
2) PowerShell에서 python -c 인라인 멀티라인/따옴표가 자주 깨짐:
   - 해결: scripts/에 짧은 .py 파일로 저장 후 실행(db_prepare_recover.py 같은 방식).
3) ConvertTo-Json -Depth 상한:
   - PowerShell 기본 제한으로 Depth 100 초과 시 오류 발생 → 필요 필드만 뽑거나 Depth를 현실적으로 설정.
4) 상태 정합성 버그(핵심):
   - okx_state/exch_status=filled 이력(filled_qty/avg_px 존재)인데, orders.status=failed / submit_status=submit_failed로 남는 모순 상태가 관찰됨.
   - 특히 “symbol을 일부러 INVALID로 깨는 테스트”에서 send-now가 PRICE_UNAVAILABLE로 failed 처리하며, 동시에 poll 결과는 okx_state=filled 흔적이 남음.
   - 결론: “filled wins(체결이 확인되면 status=filled가 우선)” 규칙/정리 로직이 필요.
5) Recover 로직이 symbol에 의존하면 테스트/운영이 깨짐:
   - recover는 (okx_clord_id / payload_json / alert_id / dedup_key) 중심으로 복구되어야 안전.

# 10-A) 개발 일정(고정) — 8주(주5일, 1~2시간/일) “Day 단위 SSOT”
원칙: Day 단위 체크리스트가 SSOT의 “현재 위치”를 만든다. (완료/미완료는 API 실측/파일 증거로만)

## Week 1: 뼈대(DB + UI 4메뉴) 완성 — DONE(실측 기반)
Day 1: DB 스키마 확정(accounts/strategies/assets/orders/snapshots)
Day 2: API등록 화면(CRUD) + 연결상태/활성 토글
Day 3: 전략설정 화면 골격(신규/수정/삭제)
Day 4: 자산등록 화면 골격(계좌×심볼×전략 선택)
Day 5: 홈(전광판) 표 + 활성/비활성 + last_signal/last_order 컬럼 표시
✅ 완료 기준: “등록 3종 + 전광판 목록” 동작
증거: GET /api/home, /api/accounts, /api/strategies, /api/assets 응답 OK

## Week 2: Input Sync v1(처음부터) + config_hash — DONE
Day 1: Pine input.* 파서(v1) 구현(지원 타입)
Day 2: keep 파일 → config 생성(from_keep) + config_hash
Day 3: 템플릿(tradingview) 생성 + include_hash
Day 4: /tv payload에서 config_hash 받아 orders에 저장
Day 5: 동기화 회귀(keep 재적용 시 재사용) + 경고(warnings) 정리
✅ 완료 기준: from_keep로 config_hash 생성/재사용 + /tv에서 config_hash 저장
증거: POST /api/strategies/{id}/configs/from_keep, GET templates/tradingview?include_hash=true, orders에 config_hash 저장

## Week 3: 안정성(중복방지/가드/재시도 정책 초안) — DONE(현재까지 확인된 범위)
Day 1: /tv 500 금지 가드 + exception 포맷 고정
Day 2: Duplicate Guard(동일 alert_id 재전송 시 ignored_duplicate)
Day 3: send-now 재시도/backoff 도입(기본)
Day 4: poll-now 상태갱신 루프(최근/변경/폴링 모드)
Day 5: 전광판에 last_order_status/filled_qty/avg_px/okx_order_id 반영(백엔드 데이터)
✅ 완료 기준: duplicate 방지 + send/poll 루프 + 전광판 데이터 필드 확인
증거: /api/home, /api/diag/send-now, /api/diag/poll-now 실측

## Week 4: “Recover + 상태정합성 + main.py 중복정리(최소)” — IN PROGRESS (오늘의 포커스)
Day 1: Recover 로직(OKX clOrdId 기반) — symbol 의존 제거
Day 2: 상태정합성 룰 “filled wins” (exch_status/okx_state=filled면 status=failed로 덮지 않기)
Day 3: main.py 중복 정의 정리(특히 _ensure_orders_table) + canonical 고정
Day 4: 회귀 테스트 스크립트 정비(PS 기준) + 감사 로그(week4_audit_*)
Day 5: 릴리즈 패치 워크플로 고정(Downloads 가정 금지, 실존 파일명 기반)
✅ 완료 기준: order_id=132 같은 “okx_state filled인데 status failed” 모순 재현 불가 + recover가 안정 동작
증거: /api/diag/order, /api/home, send-now/poll-now 실측 + audit 파일

## Week 5~8: (확장 트랙) 커넥터 표준화 + 구독 게이트 + KIS MVP
- Week 5: 커넥터 공통 인터페이스(PlaceOrder/GetOrder/Balance/Markets) + OKX 래핑
- Week 6: DB/스키마 최소 정식화(마이그레이션 스크립트/인덱스/상태모델 문서)
- Week 7: 관측/장애대응(실패 원인 분리, 1분 내 파악)
- Week 8: 구독(결제X) 기능게이트/쿼터 서버 강제 + 운영 체크리스트

# 10-B) 현재 위치(오늘 기준) — 2026-01-29 KST
- 현재 주차/일차: Week 4 (Recover/정합성/중복정리)
- 현상(실측):
  - order_id=132를 테스트로 “symbol을 INVALID로 바꿔 실패 유도”하면 send-now가 PRICE_UNAVAILABLE로 failed 처리함.
  - 동시에 okx_state/exch_status=filled + filled_qty/avg_px 흔적이 남아 “status=failed” 모순 상태가 발생함.
  - /api/diag/send-now가 일시적으로 recovered_by_clOrdId 형태로 okx_order_id를 복구시키는 동작도 관찰됨(회귀/정합성 검사에 포함).
- 즉시 해결 목표(Week4 Day1~Day2):
  1) recover가 symbol에 의존하지 않게(원본 payload_json 또는 okx_clord_id 기반)
  2) filled wins 룰로 status 정합성 고정
  3) “재시도(retryable) vs 종료(terminal)” 분류를 명확히 해서 무한 재시도 방지(예: INSUFFICIENT_BAL은 terminal)

# 11) 지금부터의 “다음 마일스톤 재정의”(키움 제외 버전)
(되돌림 최소화를 위해 게이트 중심)

## M5: 제품 아키텍처 분리(웹/대시보드 vs 프로그램/로컬에이전트) — TODO
- 웹: 소개/가격/다운로드/사용법/커뮤니티 + 로그인 대시보드(읽기 중심)
- 프로그램/앱: 계좌등록/키등록/전략설정/시스템설정/안전가드/전체중지
- 서버(Hub): 실행/기록/관측/가드/주문 처리(절대 추천/스크리닝 X)

## M6: 인증/권한/구독 게이트(최소) — TODO  (중요: 결제 구현이 아님)
- 구독 플랜별 심볼 수 제한/기능 제한(프리미엄전략 접근 등)
- 키 등록/열람/변경은 2차인증(간편인증/OTP 등) 필수(설계부터 박기)
- 무료 1주 제한 등 “기간 제한”도 서버에서 강제(우회 불가)

## M7: 멀티 거래소 커넥터(OKX/Upbit/Binance) — TODO
- 공통 인터페이스(PlaceOrder/GetOrder/Balance/Markets)
- 거래소별 rate limit / 오류코드 / 최소명목/최소수량 정책 흡수
- “출금 불가 키” 안내/검증 로직 포함

## M8: 증권사 커넥터(한국투자증권 KIS) — TODO
- 서버 커넥터로 주문/조회/체결추적/잔고가 가능해야 함
- 인증/토큰/갱신/시장시간/주문유형 차이를 커넥터에서 흡수
- 보안/법적/운영 리스크 때문에 설계/검증을 더 촘촘히

## M10: 전체중지(E-STOP) 3채널 구현(웹/프로그램/앱) — TODO
- 누르면 즉시 Hub가 주문/폴링/전송을 중지해야 함(우선순위 매우 높음)
- “중지 상태”는 /tv 수신 처리, send-now, poll-now 모두에 강제 적용

## M11: 관측/장애대응/운영도구 — TODO
- 장애/로그/알림(예: 접속이상, 주문실패 급증, 레이트리밋 등)
- 공지/업데이트(버전/릴리즈노트/필수패치 안내) 운영 체계

# 12) 즉시 실행 가능한 검증 커맨드(복붙용 / PowerShell)
$base="http://127.0.0.1:8000"

# (A) 전광판 데이터(핵심)
Invoke-RestMethod -Method Get -Uri "$base/api/home" | ConvertTo-Json -Depth 50
Invoke-RestMethod -Method Get -Uri "$base/api/assets?limit=50" | ConvertTo-Json -Depth 50

# (B) E-STOP
Invoke-RestMethod -Method Get -Uri "$base/api/system/estop" | ConvertTo-Json -Depth 10
@{ estop=$true;  reason="manual stop" } | ConvertTo-Json | %{
  Invoke-RestMethod -Method Post -Uri "$base/api/system/estop" -ContentType "application/json" -Body $_
}
Invoke-RestMethod -Method Post -Uri "$base/api/diag/send-now?limit=5" | ConvertTo-Json -Depth 30
@{ estop=$false; reason="resume" } | ConvertTo-Json | %{
  Invoke-RestMethod -Method Post -Uri "$base/api/system/estop" -ContentType "application/json" -Body $_
}

# (C) /tv + 중복방지(M2)
$aid="dup-test-" + (Get-Date -Format "yyyyMMdd-HHmmss")
$payload=@{ secret="dummy2"; alert_id=$aid; symbol="ETH-USDT"; side="buy"; qty=0.0001; type="market" } | ConvertTo-Json
Invoke-RestMethod -Method Post -Uri "$base/tv" -ContentType "application/json" -Body $payload
Invoke-RestMethod -Method Post -Uri "$base/tv" -ContentType "application/json" -Body $payload

# (D) poll-now (체결 갱신)
Invoke-RestMethod -Method Post -Uri "$base/api/diag/poll-now?mode=poll&limit=20" -TimeoutSec 15 | ConvertTo-Json -Depth 30

# (E) 단일 주문 디버깅
Invoke-RestMethod -Method Get -Uri "$base/api/diag/order?order_id=132" | ConvertTo-Json -Depth 80

# 13) Known Issues / Risks (반드시 기억)
1) main.py hotfix 누적(중복 함수 정의/래퍼)이 많아 유지보수 리스크 큼:
   - 특히 _ensure_orders_table 중복 정의가 다수 존재(감사 로그로 확인됨).
2) 상태 정합성(중요):
   - okx_state/exch_status=filled 이면서도 status=failed로 남는 모순이 발생 가능.
   - 반드시 “filled wins” 룰을 넣고, poll 결과를 status에 반영하는 우선순위를 고정해야 함.
3) retry 정책:
   - INSUFFICIENT_BAL 같은 실패는 terminal로 종결되어야 함(무한 재시도 금지).
   - PRICE_UNAVAILABLE/NETWORK/5xx는 retryable 후보지만 백오프/최대횟수 필요.
4) PowerShell/python -c 인라인은 깨지기 쉬움:
   - DB 패치/준비는 scripts/*.py 파일로 고정하여 재현성 확보.
5) 패치 워크플로:
   - Downloads 경로/파일명 “가정” 금지. 항상 dir로 실제 파일 확인 후 Copy-Item.
6) (키움 제외 사유) 키움은 Windows/세션/인증 제약으로 운영 변수가 커서, 본 12주 범위에서 제외.

# 14) 오늘의 감사/증거 파일(로컬 생성)
- C:\autobot\data\week4_audit_mainpy.txt  : main.py 중복 정의/라우트 후보 라인 수집
- C:\autobot\data\week4_audit_routes.txt  : @app.get/post 데코레이터 라인 수집

# 15) NEXT ACTION (딱 3개만, 오늘 바로)
1) “autobot.zip 실물 점검”부터:
   - zip 풀기 → app/data/scripts/requirements.txt 실제 파일명/중복/깨진 파일 확인 → SSOT 섹션 3을 실물 기준으로 보강
2) Week4 Day1~Day2(핵심 버그) 해결:
   - recover가 symbol에 의존하지 않도록 정리(OKX clOrdId/payload_json 기반)
   - filled wins 룰을 적용해 “filled인데 failed” 모순 제거(전광판/주문 상세가 일관되게)
3) main.py 중복 정의 최소 정리(전면 리팩토링 금지):
   - _ensure_orders_table canonical 1개로 고정(현 v6 바인딩 유지/검증)
   - 회귀 테스트(PS)로 send-now/poll-now/tv + estop + duplicate 전부 통과 확인

[2026-01-29 KST] DONE(E-STOP Regression):
- GET /api/system/estop → estop true/false 실측
- E-STOP ON → POST /api/diag/send-now → ok=false note=stopped detail="E-STOP is ON" 실측
- E-STOP OFF → POST /api/diag/send-now → ok=true note=send_checked 실측

[2026-01-29 KST] DONE(ensure v6 존재 확인):
- main.py에서 W4_ORDERS_ENSURE_V6 / def _ensure_orders_table_v6 / _ensure_orders_table 바인딩 존재 실측

[2026-01-29 KST] IN PROGRESS(Week4 Recover/정합성):
- order_id=132 패치 테스트에서 okx_state filled 흔적과 status failed가 공존하는 모순 관찰 → “filled wins” 및 recover(symbol 비의존) 필요

[END OF SSOT]

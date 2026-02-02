[HANDOFF PROMPT | bbooster Hub (TradingView → Hub → Broker/Exchange + Securities) | COPY-PASTE | SSOT]

당신은 "bbooster Hub" 프로젝트를 이어받아 진행한다.
이 문서는 새 채팅창 최상단에 그대로 붙여넣어 Single Source of Truth(SSOT)로 사용한다.
※ 채팅의 과거 맥락보다 이 문서가 우선이다.

# =========================
# PROJECT_STATUS.md (SSOT)
# =========================
- Last updated: 2026-02-02 KST
- Owner: 기훈(작가님)

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

## 2-3) 운영 방식(창 2개 사용 규칙 — “멋대로 합치지 말 것”)
- 작가님 운영 방식: “서버창 1개 + 테스트창 1개”를 동시에 켜서 운용한다.
- 따라서 커맨드는 반드시:
  - (서버창) run/로그 관측
  - (테스트창) API 호출/회귀 스크립트
  로 구분해서 안내한다.
- 하나의 블록에서 서버/테스트 커맨드를 섞어서 “한 번에 실행”시키는 안내 금지(운영 혼선/오작동 원인).

# 3) 레포/파일 구조(autobot.zip 실물 기준)
※ 반드시 zip을 풀고 “실제 파일명” 기준으로 문서/코드/엔드포인트를 작성한다(가정 금지).

- app/
  - main.py                : FastAPI 엔드포인트 대부분(핵심, 단일 거대 파일 + hotfix 누적)
  - okx_api.py             : OKX REST 호출/서명/주문(place_order) 모듈(존재하나 “실사용 여부는 증거 기반으로만” 판정)
  - pine_parser.py         : Pine input.* 파서(v1) + warnings(missing_lhs_at) 발생 가능
  - db.py                  : SQLAlchemy engine/session, .env 로드
  - models.py              : zip 기준 일부 ORM (단, 다수는 main.py SQL로 처리되는 구간 존재)
  - templates/index.html   : UI 전광판 HTML(다수 백업파일 존재)
  - connectors/okx.py      : OKX connector(urllib, dependency-free) (현재 main.py에서 import/사용됨: 아래 APPENDIX 증거 참고)
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
  - week4_regression.ps1         : Week4 회귀(증거 기반) 스크립트(중요, 게이트)
  - tv_webhook_regression_testonly.ps1 등: 기존 회귀/테스트 스크립트(존재)
  - uncomment_routes_block*.py   : 주석된 라우트 일부를 안전하게 복구하는 패치 도구
  - db_patch_order.py            : 주문 row 테스트 패치/조회(재시도/리커버리 테스트에 사용)
  - db_prepare_recover.py        : recover 테스트 준비(주문 invalid + okx_order_id NULL 등) 스크립트(week4_regression에서 사용)

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
- KIS_SVR ('prod' or 'vps', 기본값: prod)
- KIS_SIMULATED (0/1, 1이면 vps로 전환)
- KIS_BASE_URL (optional, 고급 설정용)
- KIS_APP_KEY / KIS_APP_SECRET (실전계좌용)
- KIS_PAPER_APP_KEY / KIS_PAPER_APP_SECRET (모의계좌/vps용)
- KIS_USER_AGENT (optional)

주의:
- 현재 .env에는 실키가 들어갈 수 있다. 외부 공유 금지.
- 장기적으로 “서버에 키를 저장/노출 최소화” 구조로 바꿔야 한다(로컬 에이전트 + 2차인증).
- (향후) KIS/Upbit/Binance 관련 키도 동일 원칙(값 노출 금지, 변경 시 감사로그)

# 5) 현재까지 “로그/실측으로 확인된” 성과 (증거는 API 출력)
## M1: /tv accepted + 주문 생성/전송/체결 루프(OKX Spot) — DONE
- /api/diag/okx-preflight OK
- /tv accepted → poll-now(mode=poll)로 filled 갱신 OK
- (증거) APPENDIX A1 week4_regression 출력에서 poll-now 결과에 status/okx_state/exch_status=filled + filled_qty + avg_px + okx_order_id 확인됨

## M2: Duplicate Guard(중복 방지) — DONE
- 동일 alert_id 2회 전송:
  - 1회차: accepted
  - 2회차: ignored_duplicate + idem_key
- orders row가 1건만 생성되는 것 확인
(주의: 이 섹션의 DONE 판정은 “실측 출력”을 재확인할 수 있어야 유지된다)

## M3: Input Sync v1 + config_hash — DONE
- POST /api/strategies/{id}/configs/from_keep (keep_path=inputs_keep_final_v0_4.txt)
  - config_id/config_hash 생성 및 재사용(reused_existing_config_hash) 확인
- templates/tradingview?include_hash=true 에 config_hash 포함 확인
- /tv payload에 config_hash 넣으면 orders에 config_id/config_hash 저장 확인

## M4: 전광판(UI/요약) 상태 표시 강화 — DONE(백엔드 데이터 기준)
아래 컬럼들이 실제로 내려오는 것이 “확인됨”:
- GET /api/home:
  - last_order_status, last_filled_qty, last_order_avg_px, last_okx_order_id, last_checked_at 등
(증거) APPENDIX A1의 /api/home 출력에 last_* 필드가 포함됨

주의:
- “브라우저 UI 화면(index.html)”에 표시가 안 되면, 원인은 2가지다:
  1) UI 라우트(/)가 주석이라 화면 자체가 안 열릴 수 있다(정상)
  2) index.html이 avg_px 등 컬럼을 아직 렌더링 안 함(패치로 해결)
- 하지만 “데이터/API”는 이미 내려오므로 M4는 DONE으로 본다.

## M10-1: E-STOP API + send-now 차단 — DONE(실측)
- GET /api/system/estop → estop true/false 확인
- E-STOP ON 상태에서 POST /api/diag/send-now → ok=false, note="stopped", detail="E-STOP is ON" 확인
- E-STOP OFF 후 POST /api/diag/send-now → ok=true, note="send_checked" 확인

## M11-2: Week4 Regression(PS) + Recover + Filled-wins Gate(실측) — DONE(2026-01-30 KST 실측)
- scripts/week4_regression.ps1 -FailOnContradiction 옵션으로 “모순 탐지”가 실패(exit 1) 없이 통과
- poll-now에서 filled 근거(okx_state/exch_status/filled_qty/avg_px)가 생기면 최종 status가 filled로 유지됨(회귀 스크립트로 확인)

# 6) 핵심 엔드포인트 맵(코드 위치 포함)
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

# 7) DB/스키마 관련 중요한 현실(필수 주의)
- app/main.py에 hotfix가 누적되어 “중복 정의/오버라이드” 리스크가 항상 존재한다.
- 운영/확장(OKX→KIS)로 가려면:
  1) 호출 경로를 증거로 고정하고(런타임 proof),
  2) 스키마/상태모델을 문서화하여 “되돌림/중복작업”을 막아야 한다.
- (현실적인 제약) psql이 PowerShell에서 바로 없을 수 있음 → DB 패치는 python+sqlalchemy 스크립트 방식이 안전.

# 8) 현재 시스템 상태 스냅샷(최근 실측 요약 — 2026-01-30 KST 로그 기반)
(증거: APPENDIX A1 원문)
- /api/diag/okx-preflight: ok=true, msg="ok"
- /api/home: last_* (filled_qty/avg_px/okx_order_id/checked_at) 포함
- /tv accepted: order_id 생성
- poll-now: status/okx_state/exch_status=filled + filled_qty/avg_px/okx_order_id
- recover: invalidate 후 send-now recovered_by_clOrdId + symbol normalize + filled 유지

# 9) 이번 세션(2026-01-30 KST)에서 실제로 한 것 / 문제점 / 해결 (증거 기반)
## 9-1) 오늘 무엇을 했나(증거: APPENDIX A1/A2/A3/A4)
1) week4_regression.ps1 실행 → 게이트 통과 확인
2) main.py OKX 직접 호출/레거시 주석 블록 제거 반영(main.py 교체 패치)
3) compileall 통과 후 week4_regression 재통과
4) 최종 grep(Select-String)에서 main.py OKX 흔적이 “connector import 4줄만 남음” 확인

## 9-2) 오늘의 문제점(증거 기반)
1) OKX 최소주문/잔고부족/최소명목 미달은 retryable이 아니라 terminal로 분류되어야 함
- 증거(사용자 로그 /api/home reason):
  - send_failed: INSUFFICIENT_BAL ...
2) (운영 리스크) 호출 경로가 섞이면 okx_place_order 인자/응답 파싱 불일치가 발생할 수 있음
- 재발 방지: “한 경로만 호출” 원칙을 Week5에서 강제

## 9-3) 오늘 해결한 것(증거 기반)
1) main.py OKX 직접 /api/v5/requests/urllib 흔적 제거(실사용 구간)
- 증거: APPENDIX A2 최종 Select-String 결과(4줄)
2) week4_regression PASS 유지
- 증거: APPENDIX A1 원문에서 == DONE ==

# =========================
# 9-4) 이번 세션(2026-02-02 KST)에서 실제로 한 것 / 문제점 / 해결 (KIS cache timestamp) — 누적(삭제 금지)
# =========================
## 9-4-1) 오늘 무엇을 했나(증거: APPENDIX A5/A6/A7/A8)
1) /api/diag/home 기본 호출에서 KIS가 miss로 내려오는 동작 확인(기본은 강제조회하지 않음)
2) /api/diag/home?refresh_kis=1 호출 시 KIS 강제조회 + 캐시갱신(refresh) 동작 확인
3) 문제: refresh 후에도 kis_cached_at가 null로 남는 케이스가 있었고, “갱신 시각을 남겨야 한다”로 정책 확정
4) main.py에서 kis_cached_at 주입 지점 + _KIS_SUMMARY_CACHE(ts/payload) 구조를 Select-String으로 근거 확보
5) 패치 적용 후 재실측:
   - refresh_kis=1 호출에서 kis_cached_at가 ISO8601(+09:00)로 채워짐
   - 이후 기본 호출에서 kis_cache_state=hit + 동일 kis_cached_at 유지됨

## 9-4-2) 오늘의 문제점(증거 기반)
1) KIS 캐시 타임스탬프(kis_cached_at)가 refresh 이후에도 null이면 “언제 갱신됐는지” 증거가 전광판에서 사라짐
- 증거: APPENDIX A5(기본 miss) 및 APPENDIX A7(패치 전/후 비교 로그)에서 kis_cached_at=null 관측 케이스 존재
2) mojibake(문자깨짐): kis_msg1_fixed가 깨진 문자열로 내려옴
- 증거: APPENDIX A7/A8에서 kis_msg1_fixed="ëª¨ìí¬ì ì¡°íê° ìë£ëììµëë¤." 형태
3) PowerShell 세션 변경 시 $base 변수가 사라질 수 있어 테스트 혼선 발생 가능
- 재발 방지: 테스트 시작 시 항상 $base 재정의

## 9-4-3) 오늘 해결한 것(증거 기반)
1) 정책 확정(운영/비용/증거성):
   - 기본 /api/diag/home 는 외부 호출 X, 캐시 hit/miss만 표시
   - /api/diag/home?refresh_kis=1 에서만 외부 호출 O, 캐시 갱신 + kis_cached_at 반드시 세팅
- 증거: APPENDIX A7/A8에서 refresh→hit 흐름 및 timestamp 유지 확인
2) 코드 근거 확보:
   - kis_cached_at 주입 라인 존재
   - _KIS_SUMMARY_CACHE(ts/payload) 캐시 구조 존재
   - _fix_mojibake / _fix_mojibake_utf8 존재
- 증거: APPENDIX A6 Select-String 결과(라인번호 포함)

## 9-4-4) 앞으로는 이렇게 해야 한다(재발 방지 규칙)
1) KIS 강제조회는 refresh_kis=1에서만(기본 홈 호출에서 KIS API를 절대 때리지 않음)
2) refresh 시 kis_cached_at 반드시 갱신, hit에서는 유지(전광판에 “근거”가 남아야 함)
3) mojibake는 “표시용 보정”만 적용(원문 데이터/로그 훼손 금지)
4) 테스트 루틴:
   - (테스트창) $base 재세팅
   - /api/diag/home → miss/hit 확인
   - /api/diag/home?refresh_kis=1 → refresh + kis_cached_at 확인
   - /api/diag/home → hit + 동일 kis_cached_at 유지 확인

# =========================
# 10-A) 개발 일정(고정) — 12주(주5일, 1~2시간/일, 하루 최대 4시간 상한) “Day 단위 SSOT”
# =========================
원칙:
- Day 단위 체크리스트가 SSOT의 “현재 위치”를 만든다. (완료/미완료는 API 실측/파일 증거로만)
- OKX Week4 회귀 게이트(week4_regression.ps1 -FailOnContradiction PASS)를 절대 깨지 않는다.
- KIS(한투)는 12주 계획 안에 Day 단위로 포함한다.
- Hub 원칙(신호판단/추천/스크리닝/자동선정 X) 위반하는 기능은 일정에 넣지 않는다.

## Week 1: DONE
Day 1~5: (기존 SSOT 동일, 삭제 없음)

## Week 2: DONE
Day 1~5: (기존 SSOT 동일, 삭제 없음)

## Week 3: DONE
Day 1~5: (기존 SSOT 동일, 삭제 없음)

## Week 4: DONE(2026-01-30 KST 실측)
Day 1~5: (기존 SSOT 동일, 삭제 없음)

## Week 5: 커넥터 표준화(OKX 정리) + KIS 착수(스켈레톤) — DONE (2026-02-02 KST)
Day 1: 커넥터 공통 인터페이스 정의(PlaceOrder/GetOrder/Balance/Markets) + 결과 타입 명세
Day 2: OKX 호출 경로 “단일화” 고정(중복 def 방지 원칙 문서화) + 회귀 게이트 유지
Day 3: main.py OKX 관련 “직접호출 흔적 제거/정리” (connector-only) + week4_regression PASS 유지  ← (증거: APPENDIX A1/A2)
Day 4: KIS 커넥터 스켈레톤 생성(인증/토큰/요청 래퍼 틀) + .env 키 목록만 추가(값 금지) ← DONE (2026-02-02 KST, 증거: kis.py + main.py:3054 kis-preflight)
Day 5: "다중 커넥터 선택" 최소 라우팅(계좌 exchange 필드 기반) 설계만(실주문 X) + 문서/grep 증거 남김 ← DONE (2026-02-02 KST, 증거: main.py:3193-3237)

## Week 6: KIS 기본 실측(잔고/토큰/드라이런) + DB 매핑 초안 — TODO
Day 1~5: (기존 SSOT 동일, 삭제 없음)

## Week 7: KIS 주문/조회/체결추적 최소(“MVP 루프”) — TODO
Day 1~5: (기존 SSOT 동일, 삭제 없음)

## Week 8: 멀티 커넥터 공통화(OKX/KIS) + 오류정책 고정 — TODO
Day 1~5: (기존 SSOT 동일, 삭제 없음)

## Week 9: 구독/쿼터 게이트(M6) 최소 구현(결제 X) — TODO
Day 1~5: (기존 SSOT 동일, 삭제 없음)

## Week 10: 운영/관측/장애대응(M11) — TODO
Day 1~5: (기존 SSOT 동일, 삭제 없음)

## Week 11: 보안/키관리/2차인증 설계 고정 — TODO
Day 1~5: (기존 SSOT 동일, 삭제 없음)

## Week 12: 정리/리팩토링 최소 + 릴리즈 패키징/문서 — TODO
Day 1~5: (기존 SSOT 동일, 삭제 없음)

# =========================
# 10-B) 현재 위치(증거 기반)
# =========================
- Week4: DONE(회귀 게이트 통과)
- Week5: DONE (2026-02-02 KST)
  - Day3 DONE 근거:
    - APPENDIX A1: week4_regression 재검증 통과
    - APPENDIX A2: main.py OKX grep 결과가 connector import 4줄만 남음
  - Day4 DONE 근거 (2026-02-02 KST):
    - kis.py: KISConnector 스켈레톤 구현 (tokenP/request/hashkey)
    - main.py:3054: /api/diag/kis-preflight 엔드포인트
    - PROJECT_STATUS.md: KIS_* 환경변수 키 목록 추가
  - Day5 DONE 근거 (2026-02-02 KST):
    - main.py:3193: _norm_exchange() 정규화 함수
    - main.py:3198: _pick_connector_name() 커넥터 선택 함수
    - main.py:3206: /api/diag/connector-route 설계 전용 엔드포인트
    - 테스트: OKX→OKXConnector, KIS→KISConnector 라우팅 확인

- (추가) 2026-02-02 KST 실측: KIS diag cache timestamp 증거화 DONE
  - DONE 근거:
    - APPENDIX A7: refresh_kis=1에서 kis_cache_state=refresh + kis_cached_at 세팅 확인
    - APPENDIX A8: 이후 기본 호출에서 kis_cache_state=hit + 동일 kis_cached_at 유지 확인

# 11) Known Issues / Risks (재발 방지 포인트)
1) main.py hotfix 누적 → “단일 호출 경로” 원칙 유지
2) 상태 정합성: filled 근거가 생기면 최종 status는 filled (게이트로 감시)
3) terminal 분류: INSUFFICIENT_BAL, 최소명목 미달 등은 무한 재시도 금지
4) 패치 워크플로: Downloads 파일명/경로 가정 금지, dir로 실존 확인 후 Copy-Item
5) 서버창/테스트창 혼용 금지
6) (추가) KIS diag/home:
   - 기본은 miss/hit만(외부 호출 금지)
   - refresh_kis=1에서만 외부 호출 + kis_cached_at 갱신(증거 유지)

# 12) NEXT ACTION (딱 3개만)
1) Week6 Day1: KIS 기본 실측(잔고/토큰/드라이런) 착수 + DB 매핑 초안
2) 해시 스냅샷(회귀 통과 조합) 기록 후 SSOT에 누적(삭제 금지)
3) 작업 전/후 week4_regression PASS 유지 확인(깨지면 즉시 원복)

[END OF SSOT]


# ============================================================
# [APPENDIX] 2026-01-30 KST — “이번 세션에서 실제로 한 것” 원문 증거(삭제 금지, 누적)
# ============================================================

# A1) week4_regression.ps1 실측 출력(원문) — 1차
(기존 APPENDIX A1 원문은 작가님이 붙여준 그대로 유지/누적)

# A2) OKX 흔적 grep(Select-String) — “정리 전/후” 증거(원문)
(기존 APPENDIX A2 원문은 작가님이 붙여준 그대로 유지/누적)

# A3) main.py 덮어쓰기 패치 적용(Downloads 워크플로) — 원문 증거(요약 없이 그대로)
(기존 APPENDIX A3 원문은 작가님이 붙여준 그대로 유지/누적)

# A4) 패치 후 재검증 회귀 통과(원문) — 2차
(기존 APPENDIX A4 원문은 작가님이 붙여준 그대로 유지/누적)


# ============================================================
# [APPENDIX] 2026-02-02 KST — KIS cache timestamp(kis_cached_at) 이슈 원문 증거(삭제 금지, 누적)
# ============================================================

# A5) main.py 코드 검색 근거(원문)
PS C:\Users\pc\Downloads> Select-String -Path "C:\autobot\app\main.py" -Pattern "fix_kis_cached_at_timestamp_v2", "_fix_mojibake", "kis_cached_at", "_KIS_SUMMARY_CACHE" | Select-Object -First 50

C:\autobot\app\main.py:7:def _fix_mojibake(s: str):
C:\autobot\app\main.py:505:                    item["kis_cached_at"] = (
C:\autobot\app\main.py:510:                    item["kis_cached_at"] = None
C:\autobot\app\main.py:4642:_KIS_SUMMARY_CACHE = {
C:\autobot\app\main.py:4675:_KIS_SUMMARY_CACHE = {"payload": None, "ts": None}
C:\autobot\app\main.py:4682:        _KIS_SUMMARY_CACHE["ts"] = ts
C:\autobot\app\main.py:4683:        _KIS_SUMMARY_CACHE["payload"] = payload
C:\autobot\app\main.py:4695:        payload = _KIS_SUMMARY_CACHE.get("payload")
C:\autobot\app\main.py:4696:        ts = _KIS_SUMMARY_CACHE.get("ts")
C:\autobot\app\main.py:4710:def _fix_mojibake_utf8(s: str | None) -> str | None:
C:\autobot\app\main.py:4711:    """Best-effort fix for UTF-8 mojibake (delegates to _fix_mojibake if available)."""
C:\autobot\app\main.py:4715:        return _fix_mojibake(s)
C:\autobot\app\main.py:4789:    msg1_fixed = _fix_mojibake_utf8(msg1)

# A6) SYNTAX 체크(원문)
PS C:\autobot> python -m compileall app | Select-Object -Last 20
Listing 'app'...
Listing 'app\\connectors'...
Listing 'app\\templates'...

# A7) /api/diag/home?refresh_kis=1 실측(원문) — refresh + kis_cached_at 채움
PS C:\Users\pc\Downloads> $base="http://127.0.0.1:8000"
PS C:\Users\pc\Downloads> (Invoke-WebRequest -UseBasicParsing -Uri "$base/api/diag/home?refresh_kis=1" -TimeoutSec 60).Content
{"ok":true,"items":[{"id":1,"account_name":"okx-main","strategy_name":"SPO-v2-edit","symbol":"ETH-USDT","market":"spot","is_active":false,"last_signal_at":null,"last_signal_id":null,"last_order_at":null,"last_order_status":null,"last_order_reason":null,"last_order_id":null,"last_okx_order_id":null,"last_filled_qty":null,"last_order_avg_px":null,"last_checked_at":null,"last_signal":"-","last_order":"-","last_filled":"-"},{"id":3,"account_name":"okx-main","strategy_name":"SPO-v2","symbol":"ETH-USDT","market":"spot","is_active":true,"last_signal_at":"2026-01-23T19:24:48.816792+09:00","last_signal_id":"diag-tv-001","last_order_at":"2026-02-01T02:06:49.362444+09:00","last_order_status":"sent","last_order_reason":null,"last_order_id":"173","last_okx_order_id":"3267423532845064192","last_filled_qty":null,"last_order_avg_px":null,"last_checked_at":"2026-02-01T02:06:49.528722+09:00","last_signal":"2026-01-23 19:24:48.816792+09:00 (diag-tv-001)","last_order":"2026-02-01 02:06:49.362444+09:00 | sent | ordId=3267423532845064192 | checked=2026-02-01 02:06:49.528722+09:00","last_filled":"-"},{"id":4,"account_name":"okx-main","strategy_name":"SPO-v2","symbol":"BTC-USDT","market":"spot","is_active":true,"last_signal_at":"2026-01-25T13:12:19.241034+09:00","last_signal_id":"diag-tv-c4133e40cb384137a5304c59cd772402","last_order_at":"2026-01-25T12:59:55.925873+09:00","last_order_status":"failed","last_order_reason":"send_failed: INSUFFICIENT_BAL: need~8.894464 USDT (qty=0.0001 px=88064.0), have 8.73966403219e-05 USDT","last_order_id":"67","last_okx_order_id":null,"last_filled_qty":null,"last_order_avg_px":null,"last_checked_at":"2026-01-27T18:09:21.219185+09:00","last_signal":"2026-01-25 13:12:19.241034+09:00 (diag-tv-c4133e40cb384137a5304c59cd772402)","last_order":"2026-01-25 12:59:55.925873+09:00 | failed | checked=2026-01-27 18:09:21.219185+09:00","last_filled":"-"},{"id":5,"account_name":"okx-main","strategy_name":"SPO-v2","symbol":"SOL-USDT","market":"spot","is_active":true,"last_signal_at":null,"last_signal_id":null,"last_order_at":"2026-01-26T15:40:16.523271+09:00","last_order_status":"failed","last_order_reason":"send_failed: INSUFFICIENT_BAL: need~0.125058 USDT (qty=0.001 px=123.82), have 8.73966403219e-05 USDT","last_order_id":"77","last_okx_order_id":null,"last_filled_qty":null,"last_order_avg_px":null,"last_checked_at":"2026-01-27T18:09:21.395077+09:00","last_signal":"-","last_order":"2026-01-26 15:40:16.523271+09:00 | failed | checked=2026-01-27 18:09:21.395077+09:00","last_filled":"-"}],"accounts_summary":[{"id":1,"name":"okx-main","exchange":"OKX","is_active":false,"last_health_at":"2026-01-20T18:37:09.377828+09:00","last_health_ok":true,"last_health_msg":"basic network ok"},{"id":2,"name":"okx-sub","exchange":"OKX","is_active":false,"last_health_at":"2026-01-20T18:37:48.645589+09:00","last_health_ok":true,"last_health_msg":"basic network ok"},{"id":3,"name":"kis-vps","exchange":"KIS","is_active":false,"last_health_at":null,"last_health_ok":null,"last_health_msg":null,"kis_balance_summary":{"dnca_tot_amt":10000000,"nass_amt":10000000,"tot_evlu_amt":10000000,"scts_evlu_amt":0,"cma_evlu_amt":0,"bfdy_tot_asst_evlu_amt":10000000,"asst_icdc_amt":0,"asst_icdc_erng_rt":"0.00000000"},"kis_msg1_fixed":"ëª¨ìí¬ì ì¡°íê° ìë£ëììµëë¤.","kis_check":{"ok":true,"svr":"vps","base_url":"https://openapivts.koreainvestment.com:29443","http_status":200,"timeout_sec":20.0,"retry_n":2},"kis_cache_state":"refresh","kis_cached_at":"2026-02-02T13:56:56.517611+09:00"}],"note":"assets_soft_deleted_missing"}

# A8) /api/diag/home 재호출 실측(원문) — hit + kis_cached_at 유지
PS C:\Users\pc\Downloads> (Invoke-WebRequest -UseBasicParsing -Uri "$base/api/diag/home" -TimeoutSec 20).Content
{"ok":true,"items":[{"id":1,"account_name":"okx-main","strategy_name":"SPO-v2-edit","symbol":"ETH-USDT","market":"spot","is_active":false,"last_signal_at":null,"last_signal_id":null,"last_order_at":null,"last_order_status":null,"last_order_reason":null,"last_order_id":null,"last_okx_order_id":null,"last_filled_qty":null,"last_order_avg_px":null,"last_checked_at":null,"last_signal":"-","last_order":"-","last_filled":"-"},{"id":3,"account_name":"okx-main","strategy_name":"SPO-v2","symbol":"ETH-USDT","market":"spot","is_active":true,"last_signal_at":"2026-01-23T19:24:48.816792+09:00","last_signal_id":"diag-tv-001","last_order_at":"2026-02-01T02:06:49.362444+09:00","last_order_status":"sent","last_order_reason":null,"last_order_id":"173","last_okx_order_id":"3267423532845064192","last_filled_qty":null,"last_order_avg_px":null,"last_checked_at":"2026-02-01T02:06:49.528722+09:00","last_signal":"2026-01-23 19:24:48.816792+09:00 (diag-tv-001)","last_order":"2026-02-01 02:06:49.362444+09:00 | sent | ordId=3267423532845064192 | checked=2026-02-01 02:06:49.528722+09:00","last_filled":"-"},{"id":4,"account_name":"okx-main","strategy_name":"SPO-v2","symbol":"BTC-USDT","market":"spot","is_active":true,"last_signal_at":"2026-01-25T13:12:19.241034+09:00","last_signal_id":"diag-tv-c4133e40cb384137a5304c59cd772402","last_order_at":"2026-01-25T12:59:55.925873+09:00","last_order_status":"failed","last_order_reason":"send_failed: INSUFFICIENT_BAL: need~8.894464 USDT (qty=0.0001 px=88064.0), have 8.73966403219e-05 USDT","last_order_id":"67","last_okx_order_id":null,"last_filled_qty":null,"last_order_avg_px":null,"last_checked_at":"2026-01-27T18:09:21.219185+09:00","last_signal":"2026-01-25 13:12:19.241034+09:00 (diag-tv-c4133e40cb384137a5304c59cd772402)","last_order":"2026-01-25 12:59:55.925873+09:00 | failed | checked=2026-01-27 18:09:21.219185+09:00","last_filled":"-"},{"id":5,"account_name":"okx-main","strategy_name":"SPO-v2","symbol":"SOL-USDT","market":"spot","is_active":true,"last_signal_at":null,"last_signal_id":null,"last_order_at":"2026-01-26T15:40:16.523271+09:00","last_order_status":"failed","last_order_reason":"send_failed: INSUFFICIENT_BAL: need~0.125058 USDT (qty=0.001 px=123.82), have 8.73966403219e-05 USDT","last_order_id":"77","last_okx_order_id":null,"last_filled_qty":null,"last_order_avg_px":null,"last_checked_at":"2026-01-27T18:09:21.395077+09:00","last_signal":"-","last_order":"2026-01-26 15:40:16.523271+09:00 | failed | checked=2026-01-27 18:09:21.395077+09:00","last_filled":"-"}],"accounts_summary":[{"id":1,"name":"okx-main","exchange":"OKX","is_active":false,"last_health_at":"2026-01-20T18:37:09.377828+09:00","last_health_ok":true,"last_health_msg":"basic network ok"},{"id":2,"name":"okx-sub","exchange":"OKX","is_active":false,"last_health_at":"2026-01-20T18:37:48.645589+09:00","last_health_ok":true,"last_health_msg":"basic network ok"},{"id":3,"name":"kis-vps","exchange":"KIS","is_active":false,"last_health_at":null,"last_health_ok":null,"last_health_msg":null,"kis_balance_summary":{"dnca_tot_amt":10000000,"nass_amt":10000000,"tot_evlu_amt":10000000,"scts_evlu_amt":0,"cma_evlu_amt":0,"bfdy_tot_asst_evlu_amt":10000000,"asst_icdc_amt":0,"asst_icdc_erng_rt":"0.00000000"},"kis_msg1_fixed":"ëª¨ìí¬ì ì¡°íê° ìë£ëììµëë¤.","kis_check":{"ok":true,"svr":"vps","base_url":"https://openapivts.koreainvestment.com:29443","http_status":200,"timeout_sec":20.0,"retry_n":2},"kis_cache_state":"hit","kis_cached_at":"2026-02-02T13:56:56.517611+09:00"}],"note":"assets_soft_deleted_missing"}


# A5) 2026-02-02 KST — KIS 캐시 타임스탬프(kis_cached_at) 갱신/표시 근거(원문, 누적)

(1) /api/diag/home (초기)
- kis_cache_state: "miss"
- kis_cached_at: null
- kis_balance_summary: null
(서버 재기동 직후면 miss는 정상: 메모리 캐시 초기화됨)

(2) /api/diag/home?refresh_kis=1 (강제 갱신)
- kis_cache_state: "refresh"
- kis_balance_summary: {"dnca_tot_amt":10000000, "nass_amt":10000000, "tot_evlu_amt":10000000, ...}
- kis_check: {"ok":true,"svr":"vps","base_url":"https://openapivts.koreainvestment.com:29443","http_status":200,"timeout_sec":20.0,"retry_n":2}
- kis_cached_at: "2026-02-02T13:56:56.517611+09:00"  (※ null → timestamp로 채워짐 확인)

(3) /api/diag/home (재호출)
- kis_cache_state: "hit"
- kis_cached_at: "2026-02-02T13:56:56.517611+09:00" 유지 확인
- kis_balance_summary 유지 확인

결론:
- refresh_kis=1 수행 시 _KIS_SUMMARY_CACHE.ts가 정상 세팅되고,
- diag/home에서 kis_cached_at가 null이 아닌 값으로 내려오며,
- 이후 home 재호출에서 cache_state=hit + kis_cached_at 유지됨.
== DONE ==

[END OF APPENDIX]

git config --global user.name  "tantanpapa"
git config --global user.email "tantanpapa00@gmail.com"


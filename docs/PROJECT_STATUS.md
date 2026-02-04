# PROJECT_STATUS.md (SSOT)
- Last updated: 2026-02-04 KST
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
- app/connectors/: OKX, KIS, Binance, Bybit, Upbit 커넥터
- scripts/: run.ps1, stop.ps1, week4_regression.ps1, kis_regression.ps1
- docs/: PROJECT_STATUS.md(SSOT), AI_RULES.md, APPENDIX_LOG.md

---

# 4) 환경변수 키 (값 노출 금지)
- DATABASE_URL, DRY_RUN, ORDER_SUBMIT_ENABLE, ORDER_POLL_ENABLE
- OKX_*: API_KEY, API_SECRET, API_PASSPHRASE, BASE_URL, SIMULATED
- KIS_*: APP_KEY, APP_SECRET, CANO, ACNT_PRDT_CD, SVR, SIMULATED
- BINANCE_*: API_KEY, API_SECRET, BASE_URL, SIMULATED
- BYBIT_*: API_KEY, API_SECRET, BASE_URL, SIMULATED
- UPBIT_*: ACCESS_KEY, SECRET_KEY, BASE_URL

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

# 6) 개발 일정 (18주, v5) — 순서/의존관계 재정렬(거래소→프리미엄→앱→커스텀→라이센스→릴리즈)

## 공통 고정(반드시)
- 차트는 TradingView embed(WebView) 방식(A) 1순위. 우리는 차트 개발하지 않는다.
- 근거 표시는 우리 UI(타임라인 패널): reason_code/reason_text/snapshot_id 필수.
- Premium/Custom 권장 TF: 15분봉 이상(1~5분봉은 슬리피지/체결괴리 경고).
- Custom은 복잡도 제한 + Rule Lint(OK/WARN/BLOCK) 필수.
- 거래소는 Spot만 지원. 선물(Futures)/레버리지 전면 미지원.

## 게이트(절대)
- **Gate-OKX**: scripts/week4_regression.ps1 -FailOnContradiction PASS 유지(깨지면 즉시 원복)
- **Gate-TV**: scripts/tv_template_regression.ps1 PASS 유지
- **Gate-E-STOP**: E-STOP ON에서 send-now 차단 실측 유지
- **Gate-BINANCE**: scripts/binance_regression.ps1 PASS 유지(Week 12~13에 생성)
- **Gate-BYBIT**: scripts/bybit_regression.ps1 PASS 유지(Week 12~13에 생성)
- **Gate-UPBIT**: scripts/upbit_regression.ps1 PASS 유지(Week 13에 생성)

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

## Week 11: PC 프로그램(설정 본체) v1 — 키/계좌/전략/템플릿/로그 — DONE
Day 1: PC 앱 기술선정 고정 + 빌드/런 구조 문서화 — DONE (2026-02-03)
- 선정: Tauri (Rust + Web, 가벼움, 보안 우수)
- 생성: docs/PC_APP_SPEC.md (아키텍처, 디렉토리 구조, 빌드/런, 보안)
Day 2: 계좌/키 등록 UI + 로컬 암호화 저장 — DONE (2026-02-03)
- PC_APP_SPEC.md 7) Day 2 상세: UI 구성, Tauri 커맨드 (Rust), 보안 체크리스트
Day 3: PC: 템플릿 생성(assets/template, batch generate, shortmsg template) UI 연결 — DONE (2026-02-03)
- 구현: PC_APP_SPEC.md 8) Day 3 상세 (UI 구성, API 연동, Tauri 커맨드, 워크플로우)
Day 4: PC: 시스템 설정(E-STOP, DRY_RUN, submit/poll enable) UI 연결 — DONE (2026-02-03)
- 구현: PC_APP_SPEC.md 9) Day 4 상세 (E-STOP 제어, 시스템 상태 표시, 서버 연결, Tauri 커맨드)
Day 5: 회귀: PC 조작 후 서버 API 상태 변화 실측 로그 누적 — DONE (2026-02-03)
- 증거: APPENDIX_LOG.md 2026-02-03 회귀 게이트 전체 PASS
- Gate-TV: PASS, Gate-E-STOP: PASS, Gate-OKX: PASS, Connector: PASS

## Week 12: 거래소 확장 v1 — Binance/Bybit (Spot) + 공통 표준 먼저 — DONE
Day 1: Spot 커넥터 공통 인터페이스/라우팅 정책 확정(account.exchange 기반) — DONE (2026-02-03)
- 생성: docs/CONNECTOR_SPEC.md (인터페이스, 라우팅, 상태 표준, 심볼 정규화, 환경변수)
Day 2: 공통 주문 상태/이벤트 표준 재점검 + reason/snapshot 필드 자리 확보 — DONE (2026-02-04)
- 추가: orders 테이블에 reason_code, reason_text, snapshot_id, exchange_order_id 컬럼
- 추가: Event 모델에 reason_code, reason_text, snapshot_id 컬럼
- 문서화: CONNECTOR_SPEC.md §4-4 reason/snapshot 필드 표준
Day 3: Binance Spot 최소 구현(place_order/get_order/balance) + /api/diag/connector-test 실측 — DONE (2026-02-04)
- 생성: app/connectors/binance.py (BinanceConnector)
- 실측: /api/diag/connector-test?exchange=BINANCE → ok:true, trading:2.77 USDT
Day 4: Bybit Spot 최소 구현(place_order/get_order/balance) + /api/diag/connector-test 실측 — DONE (2026-02-04)
- 생성: app/connectors/bybit.py (BybitConnector)
- 커넥터 로드 확인 (API 키 없어서 balance 조회 실패, 구현은 완료)
Day 5: 회귀 스크립트 생성 + 전체 게이트 검증 — DONE (2026-02-04)
- 생성: scripts/binance_regression.ps1, scripts/bybit_regression.ps1
- Gate-BINANCE: PASS (connector load + balance 2.77 USDT)
- Gate-BYBIT: PASS (connector load, API 키 미설정으로 balance 실패는 예상대로)
- Gate-OKX: PASS (order_id=197, okx_order_id=3276734354947792896)
- Gate-TV: PASS

## Week 13: 거래소 확장 v2 — Upbit (Spot) + 심볼/마켓 정책 확정 — DONE
Day 1: Upbit Spot 최소 구현(place_order/get_order/balance) + 마켓(KRW/USDT) 정책 문서화 — DONE (2026-02-04)
- 생성: app/connectors/upbit.py (UpbitConnector)
- JWT 인증 (HMAC SHA256 + Query Hash SHA512)
- 심볼 변환: BTC-KRW → KRW-BTC (Upbit은 QUOTE-BASE 형식)
- 마켓 정책: KRW/USDT/BTC 마켓 모두 지원 (CONNECTOR_SPEC.md §10)
- 시장가 매수 특성: qty = 원화 금액 (다른 거래소와 다름)
- 실측: connector load OK, get_markets() 689개 마켓 (KRW:237, USDT:170, BTC:282)
- IP 미인증으로 balance 실패 (예상됨 - API 키 IP 화이트리스트 필요)
Day 2: 심볼 정규화 룰 확정(내부 표준 symbol 포맷, 거래소별 변환 테이블) — DONE (2026-02-04)
- 생성: app/connectors/symbols.py (중앙화된 심볼 정규화 모듈)
- 내부 표준: {BASE}-{QUOTE} 대문자 (BTC-USDT)
- 함수: to_exchange_symbol(), from_exchange_symbol(), validate_symbol(), parse_tv_ticker()
- KNOWN_QUOTES: 역변환용 quote 통화 목록 (USDT, KRW, BTC 등)
- 문서화: CONNECTOR_SPEC.md §5 전면 확장 (규칙, 변환 테이블, 엣지 케이스)
Day 3: 회귀 스크립트 생성: scripts/upbit_regression.ps1 + Gate-UPBIT PASS 기준 고정 — DONE (2026-02-04)
- 생성: scripts/upbit_regression.ps1
- Gate-UPBIT: PASS (connector load OK, balance는 IP 화이트리스트 필요)
- 테스트: connector-test, connector-all, symbol normalization
Day 4: 이벤트/타임라인에서 exchange별 표기 통일(OKX/Binance/Bybit/Upbit) — DONE (2026-02-04)
- TimelineItem에 exchange 필드 추가
- /api/timeline: exchange 정보 포함 (accounts 조인)
- /ui/timeline: Exchange 컬럼 추가
- ShortMsg 검증: 5개 거래소 모두 허용 (OKX/KIS/BINANCE/BYBIT/UPBIT)
- connector-test: 통화 기본값 개선 (KIS/UPBIT=KRW, 나머지=USDT)
Day 5: 통합 회귀: Gate-OKX/Gate-TV/Gate-E-STOP + Gate-BINANCE/Gate-BYBIT/Gate-UPBIT PASS — DONE (2026-02-04)
- Gate-OKX: PASS (order_id=198)
- Gate-TV: PASS (Errors=0)
- Gate-BINANCE: PASS (connector + balance OK)
- Gate-BYBIT: PASS (connector OK, API 키 미설정)
- Gate-UPBIT: PASS (connector OK, IP 화이트리스트 필요)
- 지원 거래소: ["OKX", "KIS", "BINANCE", "BYBIT", "UPBIT"]

## Week 14: 프리미엄 엔진 v0 — 추세/역추세 "지표 점검" + 커스텀(룰 실행 계약) + 근거 표준화 — TODO
> 종목추천/자동선정/스크리너 금지 준수
> Premium은 신호(결과) 생성만, Hub는 실행/가드/기록만 담당(역할 중복 금지)
> 차트는 TradingView embed(A) + 근거는 타임라인 패널로만 표시

### (중요) 프리미엄 전략 타입(고정)
- Premium 전략 타입: 1) 역추세  2) 추세  3) 커스텀(Rule Builder)
- 돌파/스캘핑 같은 구체 프리셋은 "커스텀"으로 흡수한다.
- 본 Week 14는 "커스텀 UI/빌더 완성"이 아니라, 커스텀을 포함한 Premium 계약(입출력/근거/가드)을 고정한다.
  - 커스텀 빌더(UI/AST 편집/복잡도 제한/Lint) 구현은 별도 주차(예: Week 16)에서 완성한다.

### (중요) 추세/역추세의 정본 소스 위치
- 역추세매매/추세매매 로직(또는 기준)은 scripts/ 폴더 내 파일이 정본이다.
- Week 14 산출물 문서(docs/PREMIUM_SIGNALS.md)는 "새 로직 창작"이 아니라,
  scripts 내 정본 로직을 제품 스펙으로 '요약/매핑'하는 문서다.
- scripts 로직 변경은 별도 이슈로 분리(회귀/실측/PASS 동반). docs는 매핑/설명/계약만 수정한다.

### 목표(Week 14 완료 기준)
- 추세/역추세/커스텀을 포함한 Premium 입력/출력 계약이 확정되어 있고(문서+모델),
- Premium ON에서만 signal_event가 생성되며,
- signal_event마다 reason_code/reason_text/snapshot_id가 저장되고,
- PC/앱은 TradingView 차트 embed(A) + 우리 타임라인 패널에서 "근거"를 확인 가능해야 한다.
- 슬리피지/체결괴리로 인해 15분봉 이상 사용 권장(1~5분봉은 강한 경고) 정책이 적용되어 있어야 한다.

### 금지(재확인)
- 종목추천/자동선정/스크리닝/리밸런싱 자동 구성 금지
- 프리미엄 엔진 내부 로직/소스 노출 금지(불펌 방지)
- 선물(Futures)/레버리지/파생상품 전면 미지원

### 공통 데이터 계약(반드시 고정)
- Premium 출력은 "signal_event"로만 표현한다.
- signal_event 필수 필드:
  - asset_id, symbol, exchange, market(spot), side(entry/exit), ts
  - premium_mode(trend/mr/custom), params_version
  - reason_code, reason_text, snapshot_id
  - tf(타임프레임), price_hint(선택)
- snapshot_id는 "근거 재현"용 최소 스냅샷(OHLCV 범위/계산 결과 요약/주문 시점)을 가리킨다.
- UI(웹/PC/앱)는 차트 위 오버레이가 아니라 타임라인 패널로 근거를 표시한다(A안).

### 커스텀(Rule Builder) v1 — Week 14에서 '계약'으로 고정(구현 완성은 별도 주차)
- 커스텀 지원 인디케이터(제한): MA(SMA/EMA/WMA), BollingerBands, RSI, MACD, CCI, Ichimoku
- 규칙 저장 포맷은 문자열이 아니라 안전한 AST(JSON 트리)로 저장/검증한다.
- 복잡도 제한(필수, v1 고정):
  - max_depth = 3
  - max_leaf_total = 12 (Entry 8 / Exit 4 권장)
  - max_leaf_per_group = 6
  - max_or_groups = 2, max_leaf_per_or_group = 4
  - 같은 레벨에서 AND/OR 혼합 금지(혼합은 그룹 중첩으로만 허용)
  - 초과 시 저장/실행 불가(code=rule_complexity_exceeded)
- Rule Lint(필수, v1 고정): OK/WARN/BLOCK 등급
  - WARN: 희소/상충 가능성 높음(기본 저장 허용 + 강한 경고 UI)
  - BLOCK: 거의 불가능/오해 유발/위험(기본 저장 불가, 고급 사용자 우회 토글은 premium 권한에서만)
  - 예: "BB 상단 돌파 AND RSI<30"은 희소/상충 경고(WARN 또는 BLOCK 후보)
- Exit 옵션(v1 고정): 1) 신호청산 2) %TP/SL 3) Trailing%
- 우선순위(권장 고정): 리스크(손절/강제) > 익절 > 신호청산
- TF 정책(고정): 15분봉 이상 권장, 1~5분봉은 슬리피지/체결괴리 경고(필수)

Day 1: 추세/역추세/커스텀 신호 정의서 + reason_code 표준 확정 — DONE (2026-02-04)
- 입력 소스(정본): scripts/추세매매.txt, scripts/역추세매매 현물 v0.4.txt
- 산출 문서: docs/PREMIUM_SIGNALS.md (신규 생성)
  - Trend: Entry(ST+HVI+QQE+VWMA), Exit(HardSL/TP1/SPO/STFlip)
  - MR: 4국면 엔진(R1~R4), OSC 기반 Entry/Exit, 분할 매수/매도
  - Custom: 지원 인디케이터 6종, 복잡도 제한, Rule Lint, Exit 옵션
  - reason_code: TREND_*, MR_*, CUSTOM_* 표준 목록
  - TF 정책: 15분봉 이상 권장, 1~5분봉 슬리피지 경고
  - snapshot_id 규격 정의
- 완료 증거: 커밋 + APPENDIX_LOG.md 기록

Day 2: Premium 입력/출력 스키마 확정(계약 고정) — DONE (2026-02-04)
- 문서: docs/PREMIUM_ENGINE_SPEC.md (신규 생성)
  - 역할 분리: Premium(신호 생성) vs Hub(실행/가드/기록)
  - signal_event 스키마: 필수/선택 필드 정의
  - SignalSnapshot 스키마: OHLCV + indicators
  - DB 테이블: signal_events, signal_snapshots
  - API 엔드포인트: /api/premium/signals, /api/premium/snapshots
  - 환경변수: PREMIUM_ENABLED, PREMIUM_DAILY_LIMIT 등
- 모델: app/models.py에 SignalEvent, SignalSnapshot 클래스 추가
- 완료 증거: 커밋

Day 3: Premium 이벤트 생성 파이프라인 최소 구현 + 실측
- 정책: Premium OFF면 signal_event 생성 금지, ON이면 생성
- 구현: trend/mr는 scripts 정본을 기준으로 최소 이벤트 생성 가능하게
- custom은 "AST 입력이 존재하면 엔진이 평가→이벤트 생성"까지의 파이프라인 골격만 확인(빌더 UI는 별도 주차)
- 실측: PS로 이벤트 생성/조회 확인(/api/timeline 또는 전용 endpoint)
- 완료 증거: APPENDIX에 PS 원문(요청/응답) + Gate-TV PASS 유지

Day 4: 과다 신호/단기봉 경고 가드 정책 확정 + 실측
- 정책(초안 고정):
  - 과다 신호 방지: 1봉 1회(또는 최소 쿨다운) / 일일 제한 (기본값)
  - TF<15m 경고 배너(차단은 옵션)
- 실측: 과다 신호 조건에서 이벤트가 제한되는지 확인(또는 경고 표시)
- 완료 증거: APPENDIX에 PS 원문 + 정책 문서 업데이트

Day 5: 회귀(통합) — Premium ON/OFF 차이 실측 + Gate 유지
- Premium OFF/ON 전환 실측(OFF=이벤트 없음, ON=이벤트 생성)
- Gate-TV/Gate-OKX/Gate-E-STOP 유지(PASS)
- 완료 증거: APPENDIX에 회귀 스크립트 실행 원문 + PASS 로그 누적

## Week 15: 앱(모바일) v1 — "근거 확인" 중심(프리미엄 반영 포함) — TODO
Day 1: 앱 기술선정 고정(Flutter/ReactNative 중 1) + 인증/토큰 저장 정책 확정
Day 2: 앱: 대시보드(계좌/자산/주문 요약) + 타임라인(근거 패널) 읽기전용
Day 3: 앱: E-STOP ON/OFF + 실측(차단 동작 확인) + Gate-E-STOP 유지
Day 4: 앱: TradingView 차트 embed(WebView) 화면 추가(심볼/TF 이동 링크 포함)
Day 5: 회귀: 앱 경유 E-STOP + 프리미엄 이벤트 표시 실측 + Gate-OKX/Gate-TV PASS

## Week 16: 커스텀 Rule Builder v1 — 역추세/추세를 "사용자 조립"으로 확장 — TODO
Day 1: 지원 인디케이터 확정(제한): MA(SMA/EMA/WMA), Bollinger, RSI, MACD, CCI, Ichimoku
Day 2: 규칙 저장 포맷: 문자열 금지 → AST(JSON 트리)로 확정 + 서버 validation 구현
Day 3: 복잡도 제한 구현(깊이/leaf/OR 제한) + 실패 코드 고정(rule_complexity_exceeded)
Day 4: Rule Lint 구현(OK/WARN/BLOCK) + 희소/상충 조건 경고(예: BB 상단돌파 AND RSI<30)
Day 5: 회귀: Custom 룰 생성/검증/실행(이벤트 생성) + Gate-TV PASS

## Week 17: 보안/라이센스/구독 연동 v1 — 불펌/오남용 방지 "잠금" 완성 — TODO
Day 1: Entitlement 적용 범위 확정(Advanced Custom, Premium 엔진, 위험 기능) + 오프라인 정책 확정
Day 2: /api/subscription/me 실구현(만료/업그레이드/다운그레이드 반영)
Day 3: PC/앱: 실행 시 entitlement fetch + 기능 잠금/해제 적용(오프라인 제한 포함)
Day 4: 보안 점검: 민감정보 마스킹(로그/응답), 소스/로직 노출 금지 규칙 강제
Day 5: 회귀: Gate 전부 + entitlement 시나리오 PASS(환불/만료/다운그레이드 포함)

## Week 18: 릴리즈/운영/문서 최종 — "출시 가능한 1.0" — TODO
Day 1: 온보딩 문서(PC 기준) + 앱 근거 확인 가이드 + 15m 권장 고지 문구 고정
Day 2: 에러코드 카탈로그(/tv 포함) + 환불 방지 문구/경고 문구 고정
Day 3: runbook(운영/장애대응) + scripts 정리 + 관리자 조회(읽기) 최소
Day 4: 최종 통합 회귀: OKX/KIS/Binance/Bybit/Upbit + TV/ShortMsg/구독/E-STOP/Premium/Custom 전체 PASS
Day 5: SSOT/APPENDIX 증거 최종 정리 + 릴리즈 태그(1.0) 준비

---

# 7) NEXT ACTION (3개) — v5
1) Week 13 Day 1: Upbit Spot 최소 구현 + 마켓(KRW/USDT) 정책 문서화
2) Week 13 Day 2: 심볼 정규화 룰 확정
3) Week 13 Day 3: upbit_regression.ps1 생성 + Gate-UPBIT PASS 기준 고정

---

[END OF SSOT]

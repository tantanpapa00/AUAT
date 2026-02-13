# FINISH_SSOT.md (완성품 전용 SSOT / COPY-PASTE)
- Last updated: 2026-02-11 KST
- Owner: 기훈(작가님)

> 이 문서는 "완성품(외관+내관+도로+조경)" 제작만을 위한 SSOT이다.
> 기존 히스토리/주차 기록은 docs/PROJECT_STATUS.md에 보관하고, 본 문서는 앞으로의 작업만 다룬다.
> 변경 시 반드시 근거(파일/코드/PS 실측 출력)를 docs/APPENDIX_LOG.md에 누적하고 커밋한다.

---

# 0) 절대 규칙(완성품 공정에서도 그대로)
1) 운영 루틴 고정: stop → syntax → run → /tv test (이 순서 외 금지)
2) Hub 원칙: 신호판단/추천/스크리닝/자동선정 X
3) /tv는 500 금지. 예외는 `ok=false` + `code=exception` + `detail` 포함으로만 반환.
4) 차트는 TradingView embed(WebView). 차트 개발하지 않는다.
5) 스코프 제외(절대 건드리지 않음): SMC 전략/SMC 파일, MFT 캔들 관련 파일/로직
6) Gate(절대): Gate-OKX / Gate-TV / Gate-E-STOP / Gate-BINANCE / Gate-BYBIT / Gate-UPBIT 는 항상 PASS 유지.
   - 깨지면 즉시 원복하고 APPENDIX_LOG.md에 원인/조치/재실측을 남긴다.

---

# 1) 현재 상태(완성품 공정 관점 요약)
- 서버 코어(FastAPI) + 핵심 엔드포인트(/tv, /api/home, /api/timeline, diag send/poll 등) 기반은 존재.
- Spot 거래소/증권사 커넥터(OKX/KIS/BINANCE/BYBIT/UPBIT) 기반은 존재.
- 제품 스펙 문서(역할 분리/권한/PC앱/모바일앱)는 docs/PRODUCT_SPEC.md, AUTH_SPEC.md, PC_APP_SPEC.md, MOBILE_APP_SPEC.md에 존재.
- 지금부터 목표는 "사용자 설치/실행/사용/업데이트/지원"이 가능한 완성품으로 마감하는 것.

---

# 2) 완성품 목표(Definition of Done)
완성품(베타 기준)은 아래 7개를 모두 만족해야 한다.

(1) 브랜드 패키지
- 아이콘 전용(B안): 텍스트 제거/미니멀 버전(다크/라이트/단색)
- Windows .ico / favicon / Android adaptive icon 세트 완료

(2) 공식 사이트(랜딩) v0.1
- 소개 / 다운로드(PC, APK) / 설치가이드 / 릴리즈노트 / FAQ / Legal(면책/약관/개인정보) / SHA-256 해시 표기

(3) PC 설치형(.exe) v1
- 설치 → 바탕화면 아이콘 → 더블클릭 → 서버 실행 + 대시보드 자동 오픈
- 로그 보기 / 진단 리포트 export(zip) / 언인스톨 동작

(4) 트레이(Tray) v1
- 상태(정상/주의/오류) 표시
- 시작/중지/로그열기/진단내보내기/E-STOP 토글/업데이트 확인(최소 스텁)

(5) Android APK v0.1(중간 단계)
- "설치 가능"이 목표(PlayStore 아님)
- v0.1은 WebView 래핑 또는 관측/알림/E-STOP 중심(키/복잡 설정 금지)

(6) UI/대시보드 개선 v1
- 상태등 + 마지막 수신/전송/체결 시각
- 주문 타임라인(received→sent→filled/partial/failed) 가시화
- 에러는 사람말 + 해결 가이드

(7) QA/지원 루프 고정
- 스모크 테스트 10개(정상5/실패5) 문서화 + 가능하면 스크립트화
- 진단 리포트(zip 1파일)로 "안돼요" 대응 가능

---

# 3) 공정 순서(외관/내관/도로/조경 병렬, 주간 게이트로 통제)
- 병렬 트랙: BRAND / SITE / PC_INSTALLER / TRAY / ANDROID / UI / QA
- 단, "배포(외부 공개)"는 DoD(위 7개) 통과 후에만 진행한다.
- 내부 확인(작가님 점검)은 매주 Gate + 스모크 PASS로 판정한다.

---

# 4) 일정(완성품 제작 6주 플랜, 주 5일 기준)
## Week A (브랜드+사이트 뼈대+PC 설치형 착수) — IN PROGRESS
- BRAND:
  - [x] 엠블럼 확인: bbooster_emblem.png (로켓+차트+BBooster 텍스트)
  - [x] brand/BRAND_SPEC.md 생성: 컬러 팔레트, 아이콘 세트 정의
  - [x] brand/original/ 에 원본 복사
  - [x] 아이콘 3종 생성 (Pillow): icon-dark.png, icon-light.png, icon-mono.png
  - [x] .ico / favicon 생성: icon.ico (multi-size), favicon.ico
  - [x] Tauri 아이콘: 32x32, 128x128, 256x256, 128x128@2x, icon.png
  - [x] scripts/generate_icons.py 스크립트
- SITE v0.1:
  - [x] Home/Download/Guide/Release/FAQ/Legal 페이지 골격 생성
  - [x] 다운로드 항목에 SHA-256 표기 자리 마련
  - [x] CSS 스타일시트 생성
  - [x] 엠블럼 site/assets/에 복사
- PC_INSTALLER 착수:
  - [x] Tauri 프로젝트 구조 생성 (pc-app/)
  - [x] Cargo.toml + tauri.conf.json 설정
  - [x] Rust 백엔드: main.rs + commands.rs
    - 서버 시작/정지
    - 시스템 트레이 메뉴
    - E-STOP 제어
    - 진단 리포트 export
    - API 키 암호화 저장 (keyring)
  - [x] 프론트엔드: HTML + CSS + JS (Vite)
  - [x] README.md (빌드 가이드)
  - [ ] 실제 빌드 테스트 (Rust 환경 필요)
  - [ ] 아이콘 파일 배치

## Week B (PC 설치형 v1 + 진단/로그/언인스톨) — IN PROGRESS
- PC_INSTALLER v1:
  - [x] Tauri 프로젝트 구조 (Week A에서 완료)
  - [ ] 실제 빌드 테스트
  - [ ] 설치/실행/언인스톨 완주
  - [ ] 로그 보기(폴더 오픈) + 진단 export(zip) 버튼 연결
- QA:
  - [x] docs/QA_SMOKE.md 생성: 스모크 10개 정의
  - [x] scripts/smoke_test.ps1 생성
  - [x] 스모크 테스트 실행: 10/10 PASS
    - SMOKE-01: Health Check - PASS
    - SMOKE-02: /tv Webhook - PASS (secret 필드로 수정)
    - SMOKE-03: E-STOP Toggle - PASS (JSON body로 수정)
    - SMOKE-04: Timeline - PASS
    - SMOKE-05: Connector - PASS
    - SMOKE-06: Missing Secret - PASS
    - SMOKE-07: Invalid Secret - PASS
    - SMOKE-08: Invalid Side - PASS
    - SMOKE-09: E-STOP Block - PASS
    - SMOKE-10: 404 Endpoint - PASS
  - [x] Gate 스크립트 PASS 실측 기록(APPENDIX_LOG 누적)

## Week C (트레이 v1 + UI/대시보드 개선 v1) — IN PROGRESS
- TRAY v1:
  - [x] 상태표시 + 시작/중지/로그/진단/E-STOP 메뉴 (main.rs에 구현 완료, 빌드 필요)
- UI v1:
  - [x] 상태등(LED 스타일) 추가
  - [x] 마지막 수신/전송/체결 시각 표시 (status-overview 패널)
  - [x] 주문 타임라인(received→sent→filled/partial/failed) 가시화
  - [x] 오류 메시지 사람말 + 해결 가이드 연결 (ERROR_GUIDES)

## Week D (Android APK v0.1 "설치 가능" + E-STOP/관측 최소) — IN PROGRESS
- ANDROID v0.1:
  - [x] Flutter 프로젝트 구조 생성 (mobile-app/)
  - [x] 홈 화면 (서버 상태 + 최근 주문)
  - [x] E-STOP 제어 버튼
  - [x] 설정 화면 (서버 URL)
  - [x] 상태 카드, 이벤트 리스트 위젯
  - [ ] 실제 빌드 테스트 (Flutter 환경 필요)
- SITE:
  - [x] APK 설치 가이드 상세화 (Android 버전별 안내)
  - [x] info-box, warning-box 스타일 추가

## Week E (업데이트/릴리즈 체계 + FAQ/지원 강화) — TODO
- PC:
  - 업데이트 정책(설정/DB/로그 경로 분리, 백업/롤백 원칙) 문서화
- SITE:
  - FAQ/트러블슈팅 20개로 확장
  - 릴리즈 노트 운영 규칙 고정

## Week F (베타 릴리즈 후보 패키징 + 최종 점검) — TODO
- 전체:
  - DoD 7개 체크리스트 100% 통과
  - Gate + 스모크 전부 PASS
  - 사이트 다운로드 링크 실제 파일 연결 + SHA-256 실제값 게시
  - "외부 배포(공개)" 여부는 이 시점에 결정

---

# 4.5) 일일 진행 로그 (Daily Progress)

## Day 6 (2026-02-06) — DONE ✅
- **대시보드 + PC앱 업그레이드**
  - [x] 웹사이트 홈페이지 + 로그인/회원가입 분리
  - [x] 대시보드 개편
  - [x] 구독 플랜 페이지
  - [x] 관리자 대시보드 개선
  - [x] 템플릿 생성 마법사 형식 UI 개선
- Commit: `ccc6373`, `7b6db4e`, `bbcf813`

## Day 7 (2026-02-07) — DONE ✅
- **STEP B: 종목분석 개편**
  - [x] RS(상대강도) 분석 기능
  - [x] 52주 신고가 분석
  - [x] 밸류에이션 분석 (PER/PBR)
  - [x] TradingView Lightweight Charts 캔들차트 구현
  - [x] 검색 자동완성 개선 (4개 위치)

- **10개 버그 수정**
  - [x] 종목 자동완성 + 선택 검증 (웹훅 템플릿/백테스트/전략/포트폴리오)
  - [x] 종목 상세 모달 [object Object] 수정
  - [x] 시장분석 KR/US/ETF/Crypto 데이터 로딩 문제
  - [x] 종목분석 RS/52주신고가/밸류에이션 수정
  - [x] Admin/일반 사용자 구분 표시
  - [x] ETF 페이지 StockEasy 수준 개선
  - [x] 마스터 데이터 재시도 로직 (5초/10초/30초 간격)
  - [x] 전체 API 타임아웃 + 에러 처리 (10초)
  - [x] 네이버 금융 스크래핑 모듈 추가 (app/naver_finance.py)
  - [x] Yahoo Finance 모듈 추가 (app/yahoo_finance.py)

- **새로운 파일**
  - `app/naver_finance.py` — 네이버 금융 웹 스크래핑 (KOSPI/KOSDAQ/ETF/RS분석)
  - `app/yahoo_finance.py` — Yahoo Finance API 연동 (미국지수/종목/암호화폐)

- **새로운 API 엔드포인트**
  - `GET /api/market/etf` — ETF 목록 (섹터별 분류)
  - `GET /api/market/crypto` — 암호화폐 시세
  - `GET /api/analysis/rs` — 상대강도(RS) 분석
  - `GET /api/analysis/new-high` — 52주 신고가 종목
  - `GET /api/analysis/valuation` — 밸류에이션 분석

- **Tauri 커맨드 추가**
  - `get_market_etf`, `get_market_crypto`
  - `get_analysis_rs`, `get_analysis_new_high`, `get_analysis_valuation`

- Commits: `30000d6` (STEP B), `63339d4` (10 bug fixes)

## Day 8 (2026-02-07) — DONE ✅
- **긴급 버그 수정 5가지**
  - [x] kis_api.py: `search_symbols()` 함수 추가
  - [x] naver_finance.py: 네이버 모바일 API 기반 재작성
    - HTML 파싱(BeautifulSoup) → JSON API
    - `_safe_int`, `_safe_float` 안전한 타입 변환
    - 모든 함수 try/except + 기본값 반환
  - [x] PC앱 자동완성 4곳 적용
    - TV Connect Step 2: asset-search-input
    - Premium Strategy: custom/reversal/trend-symbol
    - Watchlist: 종목 추가 모달
  - [x] 종목명 파싱 오류 수정
    - `_clean_stock_name()` 함수 추가
    - "삼성화재    ST100210025000" → "삼성화재"
  - [x] 섹터 데이터 수정
    - `get_sector_ranking()` API 변경
    - `/api/stocks/up?menu=UPJONG` → `/api/index/KOSPI/all`
    - 개별종목 → 업종지수 정상 반환

- **의존성 추가**
  - [x] itsdangerous==2.1.2

- **API 경로 확인 (모두 일치)**
  - `/api/market/overview` ✓
  - `/api/market/sectors` ✓
  - `/api/market/etf` ✓
  - `/api/market/crypto` ✓
  - `/api/analysis/rs` ✓
  - `/api/analysis/new-high` ✓
  - `/api/analysis/valuation` ✓

- Commits: `a257c8b`, `9583e50`, `3502355`

## Day 12 (2026-02-07) — DONE ✅
- **KRX API 차단 우회 — 네이버 모바일 API 적용**
  - [x] data_provider.py 전면 재작성
    - pykrx 제거 (VPS 해외서버에서 KRX 차단)
    - 네이버 모바일 API로 전환 (해외서버에서 정상 작동)
  - [x] 지수 데이터: `m.stock.naver.com/api/index/KOSPI/basic`
  - [x] 시가총액 상위: `m.stock.naver.com/api/stocks/marketValue/KOSPI`
  - [x] RS 계산: `api.stock.naver.com/chart/domestic/item/{code}` 차트 데이터 기반
  - [x] 투자자동향: `m.stock.naver.com/api/index/KOSPI/investor`
  - [x] 업종별: `m.stock.naver.com/api/index/KOSPI/sectors`
  - [x] ETF: `m.stock.naver.com/api/stocks/marketValue/ETF`
  - [x] 개별종목: `m.stock.naver.com/api/stock/{code}/basic`

- **프론트엔드 버그 수정**
  - [x] `safeSetText()`, `safeSetHTML()`, `safeSetVisible()` 함수 추가 (DOM null 방지)
  - [x] 종목 상세 UI 안전한 DOM 접근으로 수정
  - [x] 모든 검색 input에 `autocomplete="off"` 적용
    - user-search, stock-us-search, stock-etf-search, stock-crypto-search

- **VPS 배포 및 테스트**
  - [x] 배포: `docker compose up -d --build`
  - [x] API 테스트 결과:
    - `/api/health` ✅ `{"ok":true,"status":"running"}`
    - `/api/analysis/rs` ✅ 실제 네이버 데이터 50개 종목 반환
    - `/api/analysis/new-high` ✅ 52주 신고가 종목
    - `/api/analysis/valuation` ✅ 밸류에이션 데이터
    - `/api/symbols/popular` ✅ OKX 코인 실시간 데이터

- **API 응답 샘플 (RS 순위)**
  ```json
  {"stocks":[
    {"code":"005935","name":"삼성전자우","market":"KOSPI","price":112400,"change":-0.97,"rs_total":75},
    {"code":"373220","name":"LG에너지솔루션","market":"KOSPI","price":385000,"change":-2.53,"rs_total":72},
    {"code":"015760","name":"한국전력","market":"KOSPI","price":60700,"change":-1.94,"rs_total":72}
  ],"market":"kospi","success":true}
  ```

- Commit: `958cba4`, `e15357e`

## Day 12 Update (2026-02-07) — DONE ✅
- **8개 버그 수정 완료**
  - [x] 버그 1: 국내시장 API admin 체크 + data_provider 사용으로 변경
  - [x] 버그 4: 코인에 exchange 필드 추가 (binance/upbit)
  - [x] 버그 5: 52주 신고가 — integration API로 실제 52주 고가 조회
  - [x] 버그 6: 밸류에이션 — integration API로 PER/PBR 조회
  - [x] 버그 8: RS 백분위 계산 개선 — fchart API 사용, 200개 종목 기반

- **data_provider.py 개선**
  - `fchart.stock.naver.com` 일봉 API 사용 (분봉 문제 해결)
  - `m.stock.naver.com/api/stock/{code}/integration` API로 52주 고가/PER/PBR 조회
  - RS 백분위 계산: 전체 종목 수익률 기반 순위 할당 (1위=99점)
  - 캐싱 시간 1시간으로 조정 (API 호출 최적화)

- **main.py 개선**
  - `/api/market/kr/overview`: admin 체크 추가, data_provider 사용

- **VPS 배포 및 테스트 결과**
  - RS API: 1위 미래에셋증권 RS:98, 삼성전자 RS:79 (기간별 차별화)
  - 52주 신고가: 우리금융지주 -0.46%, 기업은행 -0.65% (실제 거리 계산)
  - 밸류에이션: 한국전력 PER:4.73/PBR:0.84, 기업은행 PER:6.79/PBR:0.52

- **API 응답 샘플 (개선된 RS 순위)**
  ```json
  {"stocks":[
    {"code":"006800","name":"미래에셋증권","market":"KOSPI","price":48000,"rs_total":98,"rs_1m":99,"rs_3m":98,"rs_6m":97},
    {"code":"010130","name":"고려아연","market":"KOSPI","price":1641000,"rs_total":94,"rs_1m":97,"rs_3m":93,"rs_6m":92},
    {"code":"005930","name":"삼성전자","market":"KOSPI","price":158600,"rs_total":79,"rs_1m":59,"rs_3m":91,"rs_6m":95}
  ],"market":"kospi","success":true}
  ```

- **API 응답 샘플 (밸류에이션 PER/PBR)**
  ```json
  {"stocks":[
    {"code":"015760","name":"한국전력","price":60700,"per":4.73,"pbr":0.84,"market_cap":389672,"market":"KOSPI"},
    {"code":"024110","name":"기업은행","price":23000,"per":6.79,"pbr":0.52,"market_cap":183408,"market":"KOSPI"}
  ],"market":"all","success":true}
  ```

- Commits: `18a940c`, `992ec00`

## Day 15 (2026-02-10) — DONE ✅
- **백테스트 신호 계산 벡터화 최적화**
  - [x] 지표 계산 벡터화 (indicators.py)
    - `calc_wma`: for loop → np.convolve
    - `calc_stdev`: for loop → cumsum 기반 E[X²]-E[X]² 공식
    - `calc_highest/calc_lowest`: for loop → sliding_window_view + np.max/np.min
    - `calc_vwma`: for loop → cumsum 기반 rolling sum
    - `calc_atr`: 벡터화된 True Range 계산
  - [x] SPO 오실레이터 사전 계산 (backtest_engine.py)
    - `precompute_spo_arrays()`: 전체 시리즈 SPO 한 번에 계산
    - `precompute_signal_arrays()`: sig_up_raw/sig_dn_raw 배열 벡터화
    - `precompute_htf_arrays()`: VWMA50/200, HMA, Supertrend, Ichimoku 사전 계산
    - `get_htf_indicators_at_index()`: 사전 계산된 배열에서 인덱스로 접근
    - `get_osc_data_at_index()`: 사전 계산된 배열에서 인덱스로 접근
  - [x] 메인 루프 최적화
    - 기존: 매 바마다 지표 재계산 (O(n²))
    - 개선: 사전 계산 후 인덱스 접근 (O(n))

- **성능 측정 결과**
  | 조건 | 개선 전 | 개선 후 | 배수 |
  |------|---------|---------|------|
  | 4h 365d (2190 bars) | 20.6s | 0.07s | 294x |
  | 1h 365d (8760 bars) | - | 0.25s | - |
  | 15m 365d (35040 bars) | - | 1.0s | - |

- **검증**
  - 거래 횟수 동일 (16 trades) - 로직 정확성 확인
  - 캔들 DB 캐시 HIT 시 0.1초 이내
  - 목표 달성: 4h 365d < 5s ✅, 1h 365d < 10s ✅

- **Tauri PC 앱 빌드**
  - [x] `cargo tauri build` 성공
  - [x] MSI 설치 패키지 생성: `BBooster_1.0.0_x64_en-US.msi`
  - [x] NSIS 설치 프로그램 생성: `BBooster_1.0.0_x64-setup.exe`
  - Rust 컴파일 경고 15개 (dead_code, unused) - 정상 작동에 영향 없음

- **수정된 파일**
  - `app/strategy_engine/backtest_engine.py` — 벡터화 사전 계산 함수 추가
  - `app/strategy_engine/indicators.py` — 지표 함수 벡터화

- Commit: `8c960e9`

## Day 18 (2026-02-13) — DONE ✅
- **추세매매 PineScript v8 정합성 검증**
  - [x] HTF 필터 크립토/주식 분리 (SMA vs VWMA)
  - [x] Supertrend 기본값 20/5.0 통일
  - [x] signal_generator_trend.py PineScript v8 완전 재작성
  - [x] reason_code 변경 (TREND_ENTRY_FULL → TREND_ENTRY)

- **추세매매 백테스트 3가지 문제 수정**
  - [x] 문제 1 (SPO OFF 무시): JS invoke snake_case로 변경
  - [x] 문제 2 (느린 로딩 48초→7초): KIS HTF 캔들 스킵
  - [x] 문제 3 (날짜 '25'): tickMarkFormatter + localization 추가

- **KIS 토큰 캐싱 추가**
  - [x] 403 "1분당 1회 제한" 에러 해결
  - [x] kis_api.py: get_kis_token() 캐싱
  - [x] candle_fetcher.py: kis_api.py 캐시 재사용

- **수정된 파일**
  - `app/strategy_engine/signal_generator_trend.py` — v8 로직 재작성
  - `app/strategy_engine/backtest_engine_trend.py` — precompute_sma 추가
  - `app/premium_routes.py` — htf_sma_len, asset_type, KIS HTF 스킵
  - `pc-app/ui/src/main.js` — snake_case invoke, 날짜 포맷
  - `app/kis_api.py` — 토큰 캐싱
  - `app/strategy_engine/candle_fetcher.py` — 토큰 캐시 공유

- **테스트**: pytest 341 passed
- **VPS 배포**: docker compose up -d --build 완료

- Commits: `4501fcb`, `33522c1`, `bf2bf4d`, `96ff487`, `9385063`, `adc6fcf`

## Day 16 (2026-02-11) — DONE ✅
- **백테스트 UI TradingView 스타일 동기화**
  - [x] 에퀴티 커브 Y축 퍼센트(%) 표시로 변경
  - [x] 0% 기준선 추가 (손익분기점)
  - [x] Chart.js segment 컬러링 (수익=초록, 손실=빨강)
  - [x] 툴팁에 금액 + 퍼센트 동시 표시

- **화폐단위 자동 결정 시스템**
  - [x] `getMrCurrency(exchange, symbol)` 함수 추가
    - KIS_KR, UPBIT → KRW (원)
    - KIS_US → USD ($)
    - USDT/USDC/BTC 페어 자동 감지
  - [x] `formatMrAmount(value, currency)` 함수 추가
    - KRW: 1,234,567원
    - USD: $1,234.56
    - USDT/USDC/BTC: 1,234.56 USDT
  - [x] 만원/억 단위 축약 제거 (정확한 금액 표시)

- **수익지수(Profit Factor) ∞ 처리**
  - [x] `formatProfitFactor()` 함수 추가
  - [x] 문자열 "Infinity" 처리
  - [x] Number 변환 후 >= 999 → ∞ 표시
  - [x] null/undefined → '--' 표시

- **거래소 드롭다운 개선**
  - [x] `EXCHANGE_DISPLAY` 객체로 한글명 매핑
    - OKX → OKX
    - BINANCE → 바이낸스
    - BYBIT → 바이비트
    - UPBIT → 업비트
    - KIS_KR → 한투증권(국내)
    - KIS_US → 한투증권(해외)
  - [x] index.html 드롭다운에 KIS_KR/KIS_US 옵션 추가

- **백엔드 수정**
  - [x] `MRBacktestResponse`에 `symbol` 필드 추가 (화폐단위 결정용)

- **PC 앱 빌드**
  - [x] npm run build (프론트엔드)
  - [x] cargo tauri build (설치 패키지)
  - [x] 4개 타임프레임 테스트 (1D/4h/1h/30m) 완료

- **수정된 파일**
  - `app/premium_routes.py` — symbol 필드 추가
  - `pc-app/ui/src/main.js` — 화폐단위/∞처리/거래소명 함수
  - `pc-app/ui/index.html` — 거래소 드롭다운 옵션

- Commits: `53f3519`, `02daa30`, `04db84e`

---

# 5) 매주 승인(작가님 체크 포인트)
- Gate(OKX/TV/E-STOP/BINANCE/BYBIT/UPBIT) PASS?
- 스모크 10개 PASS?
- PC 설치형: 설치→아이콘→실행→대시보드→진단 export까지 막힘 없는가?
- 사이트: 다운로드/가이드/릴리즈/FAQ/Legal이 갖춰졌는가?
- 앱: 최소 "설치 가능 + 관측/E-STOP" 방향을 지켰는가(키/복잡설정 금지)?

---

# 6) 작업 지시 원칙(Claude Code 위임용)
- 각 트랙은 PR 단위로 쪼개고, PR에는 반드시:
  1) 변경 파일 목록
  2) 실행/빌드 방법
  3) PS 실측 결과
  4) Gate/스모크 결과
  를 포함한다.

---

# 7) 브랜드 자산
- 엠블럼 원본: bbooster_emblem.png (AUAT 루트)

---

[END OF FINISH_SSOT]

# FINISH_SSOT.md (완성품 전용 SSOT / COPY-PASTE)
- Last updated: 2026-02-07 KST
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

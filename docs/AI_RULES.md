# AI_RULES — bbooster Hub (MUST FOLLOW)

## 0) Absolute Rules (NON-NEGOTIABLE)
1) Do NOT modify anything related to SMC strategy/files or MFT candle files/logic.
2) Fixed routine only: stop → syntax → run → /tv test. Do not propose alternative sequences.
3) /tv must never return HTTP 500. Any exception must return: ok=false + code=exception + detail (with actionable message).
4) No assumptions. If not proven by file/grep/API output, mark as TODO and cite where to verify.
5) Always show touched files:
   - touched files (planned) BEFORE changes
   - touched files (actual) AFTER changes

## 1) SSOT & Evidence (Token-saving)
- Source of truth is repo docs (NOT chat):
  - docs/PROJECT_STATUS.md = SSOT-SLIM (keep short)
  - docs/APPENDIX_LOG.md   = raw PowerShell outputs (append-only, no summaries)
  - docs/SSOT_HEADER.md    = chat copy-paste header (<= 20 lines)
- Chat should only paste docs/SSOT_HEADER.md (and optionally commit hash). Never paste long logs in chat.

## 2) Gates (Quality)
- Syntax gate: python -m compileall app
- OKX regression gate: scripts/week4_regression.ps1 -FailOnContradiction
- KIS regression gate: scripts/kis_regression.ps1
- If gates fail: stop and revert (do not "push through").

## 3) Scope Policy (Product)
- TradingView makes signals. Hub only bridges + sizing/guards + stability + logs/observability + execution.
- No recommendations/selection/screener/auto-picking features.
- Futures are not supported (coin futures / domestic futures / overseas futures).

## 4) Security Principles
- Secret required for /tv (unless diag-only endpoints explicitly exempt).
- Keys must not be printed. Never include .env values in logs/docs.
- E-STOP must block execution paths immediately.

## 5) Evidence Logging Rule
- All PowerShell outputs used as proof must be appended to docs/APPENDIX_LOG.md with:
  - timestamp (KST)
  - command
  - raw output block
- Do not rewrite or summarize raw evidence inside APPENDIX_LOG.md.

## 6) Repo-based Workflow
- Working directory: C:\Users\pc\새 폴더\AUAT
- Work directly with repo files (git clone or local).
- Always verify file structure from repo before making changes.
- Before starting work: read docs/AI_RULES.md + docs/PROJECT_STATUS.md.

## 7) 일괄 적용 원칙 (NON-NEGOTIABLE)
1) 모든 코드 수정은 전 거래소(OKX/Binance/Bybit/Upbit/KIS_KR/KIS_US) 일괄 적용.
   - 한 거래소만 수정하고 나머지 미적용 금지.
   - 캔들 조회, 백테스트, 주문실행, 잔고조회 등 모든 기능 해당.
2) candle_preloader.py에 등록된 프리로딩 대상은 전 거래소 주요 종목 포함:
   - BINANCE: BTCUSDT, ETHUSDT, SOLUSDT, XRPUSDT, BNBUSDT
   - OKX: BTC-USDT, ETH-USDT, SOL-USDT
   - BYBIT: BTCUSDT, ETHUSDT
   - KIS_KR: 005930(삼성전자), 000660(SK하이닉스) — 일봉만 (분봉은 당일만 가능)
   - KIS_US: AAPL, TSLA — 일봉만
3) 커밋 전 반드시:
   a. 문법 검증: python -c "import ast; ast.parse(open('파일').read())"
   b. 전 거래소 테스트 (최소 curl로 API 응답 확인)
   c. 기존 테스트 통과: python -m pytest tests/ -x -q

## 7-A) 캔들 DB 축적 정책 (CANDLE_CACHE)
BBooster 서버는 캔들 데이터를 PostgreSQL candles 테이블에 축적한다.
이는 서비스의 핵심 자산이며, 사용자가 많을수록 모든 사용자가 빨라지는 구조다.

**축적 방식 (3가지):**
1) 프리로딩 (candle_preloader.py): 서버 시작 시 + 1시간마다 주요 종목 자동 저장
2) 사용자 요청 캐싱: 백테스트 요청 시 DB에 없으면 거래소 API 조회 → DB 저장 → 두 번째부터 즉시
3) 증분 갱신: DB 마지막 캔들이 오래되면 최신분만 추가 조회

**속도 차이:**
- DB 캐시 HIT: 0.1초 이내
- DB 캐시 MISS (첫 요청): 거래소 API 조회 5~15초 → 이후 HIT

**용량 추정:**
- 종목 1만개 × 일봉 1000일 = 1000만행 ≈ 1~2GB (PostgreSQL에서 가벼운 수준)
- VPS 디스크 압박 없음

**데이터 관리 정책:**
- 3년(1095일) 이상 된 캔들은 자동 삭제 (cron 또는 서버 시작 시)
- 삭제 쿼리: DELETE FROM candles WHERE timestamp < NOW() - INTERVAL '3 years'
- 프리로딩 대상 종목 캔들은 삭제 대상에서 제외 가능 (선택)

**KIS 캔들 제한사항:**
- 일봉/주봉/월봉: 조회 가능 → 백테스트 + 프리로딩 가능
- 분봉: 당일 1분봉만, 30건씩 → 과거 분봉 백테스트 불가
- KIS 백테스트는 일봉 기준으로만 지원

**전 거래소 캔들 조회 API:**
| 거래소 | 일봉 | 분봉 | 1회 조회 한도 | 비고 |
|--------|------|------|-------------|------|
| Binance | ✅ | ✅ (1m~1w) | 1000개 | 제한 없음 |
| OKX | ✅ | ✅ (1m~1w) | 100개 | VPS IP 429 주의 |
| Bybit | ✅ | ✅ (1m~1w) | 200개 | |
| Upbit | ✅ | ✅ (1m~1w) | 200개 | 원화마켓 |
| KIS_KR | ✅ | 당일1분봉만 | 30개 | 분봉 과거조회 불가 |
| KIS_US | ✅ | 당일1분봉만 | 30개 | 분봉 과거조회 불가 |

## 8) 문제 해결 프로세스 (NON-NEGOTIABLE)
문제 발생 시 아래 순서 준수:
1) 점검: 로그 확인 (docker logs, grep error)
2) 원인 규명: 에러 메시지 + 코드 추적
3) 여러 변수 테스트: 다른 거래소/종목/타임프레임으로 재현
4) 수정 후 검증: 동일 조건 + 다른 조건 모두 테스트
5) 커밋

절대 금지:
- 원인 미파악 상태에서 커밋
- 한 거래소만 테스트하고 커밋
- "이미 완료됨" 스킵

## 9) 백테스트 결과 기준 (트레이딩뷰 동일)
백테스트 결과는 트레이딩뷰 전략 리포트와 동일한 구조:
- 상단 카드 5개: 총손익(금액+%), 최대자본감소(금액+%), 총거래횟수, 수익성거래(% + n/n), 수익지수
- 수익률 테이블: 전체/매수/매도 3열, 행: 순손익, 총수익, 총손실, 수익지수, 수수료, 기대수익
- 자본 차트: Y축 수익률(%), 수익구간 초록/손실구간 빨강, 초기자본 기준선
- 거래 내역: 수익금+수익률 둘 다 표시
- 수수료 계산 포함 (기본 0.1%)
- 미실현 손익 포함 (백테스트 종료 시 보유 포지션)

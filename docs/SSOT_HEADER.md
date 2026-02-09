# 큐브시스템 (QUBE System) — BBooster Hub
- Company: 큐브시스템 (QUBE System)
- Repo: C:\Users\pc\새 폴더\AUAT
- VPS: 76.13.180.30 (https://qube-system.com)
- SSOT: docs/FINISH_SSOT.md, docs/PROJECT_STATUS.md
- Rules: docs/AI_RULES.md (MUST read first)

## Current Status (2026-02-09)
- Week A~D: DONE (브랜드/사이트/PC앱/Android APK 기반)
- Day 6: DONE (대시보드 개편 + 구독 플랜)
- Day 7: DONE (종목분석 개편 + 10 버그 수정)
- Day 8: DONE (종목검색/네이버API/자동완성/파싱 수정)
- Day 9: DONE (긴급 수정 + 보유자산 + 계정관리 + 전략설정 v2 UI)
- Day 10: DONE (홈 대시보드 개선 - 거래내역 + 활성전략 관리)
- Day 11: DONE (역추세매매 프리미엄 엔진 Phase 1 - 지표 파이썬 재구현)
- Day 12: DONE (역추세매매 프리미엄 엔진 Phase 2 - 시세/실행 모듈)

## Quick Commands
- Syntax: `python -m compileall app`
- Gates: `week4_regression.ps1`, `tv_template_regression.ps1`
- Server: `docker compose up -d` (VPS)
- PC App: `cd pc-app && cargo tauri dev`

## Day 9 Fixes (2026-02-08)

### 긴급 수정 3건
1. **이용약관 RTF 한글 깨짐** - 유니코드 이스케이프 변환 (`\uXXXXX?`)
2. **수익률 소수점 깨짐** - `toFixed(2)` 적용 (차트 Y축 + 데이터)
3. **보유자산 빈 배열** - `accounts.user_id` → `accounts.owner_id` 수정

### 보유자산 표시 개선 5건
1. **BTC 누락** - OKX 필터 완화 (`eq > 0.01` → `cashBal > 0`)
2. **현재가 $0.00** - OKX Ticker API 추가 (`/api/v5/market/ticker`)
3. **평균단가 없음** - 프론트에서 `-` 표시 (0 대신)
4. **헤더 줄바꿈** - `white-space: nowrap` 적용
5. **거래소 필터** - 드롭다운 추가 (전체/OKX/Binance/Bybit/Upbit/KIS)

### 계정 관리 수정
- **삭제 버튼 에러** - `data-exchange` 속성 누락 수정
- **is_mock 필드** - KIS 모의투자 지원 (`accounts.is_mock` 컬럼 추가)
- **테스트 계정 정리** - `test-okx-temp`, `test-kis-temp` 삭제

### 전 거래소 평균단가/평가손익/수익률 구현
| 거래소 | 잔고 | 현재가 | 평균단가 | 통화 |
|--------|------|--------|----------|------|
| OKX | `/api/v5/account/balance` | `/api/v5/market/ticker` | fills-history 이동평균 | USD |
| Binance | `/api/v3/account` | `/api/v3/ticker/price` | myTrades 이동평균 | USD |
| Bybit | `/v5/account/wallet-balance` | `/v5/market/tickers` | execution/list 이동평균 | USD |
| Upbit | `/v1/accounts` (avg_buy_price 제공) | `/v1/ticker` | API 직접 제공 | KRW |
| KIS 국내 | 잔고 API (pchs_avg_pric 제공) | - | API 직접 제공 | KRW |
| KIS 해외 | 해외잔고 API | - | avg_unpr3 제공 | USD |

- **이동평균법** - 매수: `(기존총액 + 매수금액) / (기존수량 + 매수수량)`, 매도: 수량만 감소
- **프론트엔드** - currency 필드 기반 ₩/$ 자동 표시

### 보유자산 Allocation + UI 개선
1. **5-카테고리 Allocation** - cash → cash_krw/cash_usd 분리
   - cash_krw: 국내 예수금 (KIS 예수금)
   - cash_usd: USD 스테이블코인 (OKX/Binance/Bybit USDT/USDC/BUSD/DAI/TUSD)
   - domestic: 국내주식
   - overseas: 해외주식
   - crypto: 암호화폐

2. **총자산 1원 단위 표시** - 만/억 포맷 → 1원 단위 (₩10,477,147)

3. **평가액 컬럼 앰버 색상** - #F59E0B, font-weight: 600

### 커밋 목록
- `1df2e32` fix: 긴급 수정 3건 - RTF/수익률/보유자산
- `6aad6a7` fix: accounts 테이블 컬럼명 수정 (user_id → owner_id)
- `0c7fc9c` fix: KIS 모의투자 is_mock 필드 지원 추가
- `98e4ffa` fix: 계정 삭제 버튼에 data-exchange 속성 추가
- `98759ec` feat: 보유자산 표시 개선 5건
- `4b499f7` feat: OKX 보유자산 평균단가/평가손익/수익률 구현
- `0993868` feat: 전 거래소 평균단가/평가손익/수익률 구현
- `5758628` style: 평가액 컬럼 앰버 색상 적용 (#F59E0B)
- `7482588` fix: allocation 분류 로직 수정 + 디버그 로그 정리

### 전략설정 (Sizing/Risk/Limits) 기능 추가
**아키텍처**: `strategies.signal_params` (JSONB) + `assets.signal_params_override` (JSONB)
Hub 로직: `effective = deep_merge(strategies.signal_params, assets.signal_params_override)`

**Phase 1: DB + 유틸리티**
- `scripts/migrate_signal_params.sql`: DB 마이그레이션
- `app/utils/merge.py`: deep_merge (object 재귀, array 통째 교체, null 무시)
- `app/utils/validation.py`: validate_effective_params 검증

**Phase 2: API 엔드포인트**
- `GET/PUT /api/strategies/{id}/signal-params-jsonb`
- `GET/PUT/DELETE /api/assets/{id}/signal-params-override`
- `GET /api/assets/{id}/effective-params`

**Phase 3: PC앱 UI**
- TV Connect Step 3: 사이징/리스크/리밋 3개 카드
- collectSignalParams(), loadSignalParamsToUI() 함수

**Phase 4: Hub 매매 로직**
- `app/utils/trading.py`: check_limits, calculate_qty, get_effective_params
- `/tv` 웹훅: effective_params 조회 + Limits 체크
- Limits 항목: 중복방지, 쿨다운, 1봉1회, 일일한도, 포지션한도

**Phase 5: v2 UI 개편** (2026-02-09)
- Sizing 3개 모드: `balance_pct` / `fixed_amount` / `fixed_qty`
- Currency 드롭다운: KRW / USD / USDT / USDC
- Limits v2 구조: `{enabled: bool, value: number}` 객체
- 용어 변경: "TV신호 기반" → "신호 대기", "거래소 브라켓" → "자동 손절/익절"
- 조건부 필드 표시 (mode별, enabled별)
- 도움말 아이콘 (ℹ️) 각 필드
- Step 4 템플릿 간소화 (설정은 서버 저장)

**v2 DEFAULT_SIGNAL_PARAMS 구조:**
```python
{
    "sizing": {
        "mode": "balance_pct",  # balance_pct / fixed_amount / fixed_qty
        "value": 30,
        "base": "free",
        "currency": "USDT",
        "reduce": {"mode": "full", "default_pct": 100}
    },
    "limits": {
        "daily_max_trades": {"enabled": False, "value": 0},
        "daily_max_notional": {"enabled": False, "value": 0},
        "max_open_positions": {"enabled": False, "value": 0}
    },
    "meta": {"version": 2}
}
```

**커밋**
- `f2da45a` feat: 전략설정 (Sizing/Risk/Limits) Phase 1-3 구현
- `4c119f7` feat: 전략설정 Phase 4 - Hub 매매 로직 통합
- `001ca81` feat: 전략설정 v2 - PC앱 UI 개편 + 백엔드 구조 업데이트

### PC앱 템플릿 생성 + /tv 웹훅 자동 수량 계산 (2026-02-09)

**문제 1: PC앱 "템플릿 생성" 버튼이 서버에 저장 안 됨**
- 원인: JavaScript에서 fetch() 직접 호출 → Tauri 아키텍처 위반
- 해결: Rust commands 추가 + JS에서 invoke() 호출로 변경

**Tauri 아키텍처:**
```
JavaScript (main.js) → invoke() → Rust commands (commands.rs) → HTTP API (서버)
```

**추가된 Rust Commands (`pc-app/src-tauri/src/commands.rs`):**
```rust
#[tauri::command]
pub async fn create_strategy_with_params(
    access_token: String, name: String, tv_secret: String,
    signal_params: serde_json::Value,
) -> Result<serde_json::Value, String>

#[tauri::command]
pub async fn save_signal_params(
    access_token: String, strategy_id: i64,
    signal_params: serde_json::Value,
) -> Result<serde_json::Value, String>

#[tauri::command]
pub async fn create_asset(
    access_token: String, account_id: i64, strategy_id: i64,
    symbol: String, market: String,
) -> Result<serde_json::Value, String>
```

**문제 2: /tv 웹훅 자동 수량 계산 안 됨**
- 원인: get_connector()가 빈 환경변수에서 API 키 읽음
- 해결: DB accounts 테이블에서 API 키 조회 + data_provider 함수 사용

**추가된 커넥터 메서드:**
- `get_ticker(symbol: str) -> TickerInfo` - 현재가 조회 (Public API)
- 구현: OKX, Binance, Bybit, KIS 전 커넥터

**TickerInfo 데이터클래스 (`app/connectors/base.py`):**
```python
@dataclass(frozen=True)
class TickerInfo:
    ok: bool
    exchange: str
    symbol: str
    last: Optional[float] = None
    bid: Optional[float] = None
    ask: Optional[float] = None
    high24h: Optional[float] = None
    low24h: Optional[float] = None
    vol24h: Optional[float] = None
```

**/tv 웹훅 자동 수량 계산 흐름:**
1. DB에서 계정 API 키 조회 (`accounts` 테이블)
2. data_provider로 잔고 조회 (fetch_okx_balances 등)
3. get_ticker로 현재가 조회 (Public API)
4. effective_params 기반 수량 계산
5. 주문 실행

**잔고 파싱 키 수정:**
- 수정 전: `b.get("available", 0)`, `b.get("free", 0)`, `b.get("total", 0)`
- 수정 후: `b.get("quantity", 0)` - data_provider 반환 구조에 맞춤

**커밋:**
- `c4196cf` fix: /tv 잔고 파싱 키 수정 (quantity 사용)

## Day 10: 홈 대시보드 개선 (2026-02-09)

### 웹 대시보드 (dashboard.html)
1. **거래내역 섹션** - offset 파라미터, 실패주문 포함, total count
2. **활성전략 관리** - paused 포함 (soft_deleted=0), toggle/delete 버튼
3. **타임라인 확장** - reason_code, reason_text, side, qty, filled_qty, avg_px

**API 변경:**
- `GET /api/trades` - offset, limit, include_failed, total 반환
- `GET /api/strategies/active` - paused 포함 조회
- `PUT /api/assets/{id}/toggle` - 전략 일시정지/재개
- `DELETE /api/assets/{id}` - 전략 삭제

### PC앱 대시보드 (Tauri invoke)
1. **거래내역 테이블** - 최근 10건, 페이지네이션, 상태별 색상
2. **활성전략 테이블** - 전략명/종목/거래소/오늘거래/상태/액션
3. **Toggle/Delete 버튼** - Rust commands 연동

**Tauri 아키텍처:**
```
JavaScript (main.js) → invoke() → Rust commands (commands.rs) → HTTP API
```

**추가된 Rust Commands:**
```rust
#[tauri::command]
pub async fn toggle_asset(access_token: String, asset_id: i64) -> Result<serde_json::Value, String>

#[tauri::command]
pub async fn delete_asset(access_token: String, asset_id: i64) -> Result<serde_json::Value, String>
```

### 해결한 이슈
1. **CSS 충돌** - 중복 .strategy-card 정의 제거
2. **이모지 깨짐** - ⏸▶🗑 → 정지/재개/삭제 텍스트로 변경
3. **Tauri 파라미터** - camelCase (assetId) → snake_case (asset_id) 자동 변환
4. **Vite 모듈 스코프** - `window.toggleAsset`, `window.deleteAsset` 등록
5. **레이아웃** - grid-column: 1/-1 (전체 너비), 위아래 배치

**커밋:**
- `34f87c0` feat: 홈 대시보드 개선 - 거래내역 + 활성전략 관리
- `366e19c` feat: PC앱 홈 대시보드 개선 - 거래내역 + 활성전략 관리
- `e4c05d8` fix: PC앱 활성전략 카드 레이아웃 수정
- `3ad21b7` fix: PC앱 홈 활성전략 테이블 형태로 변경 + 디버깅 로그
- `96215bb` fix: PC앱 홈 레이아웃 위아래 배치 + 버튼 텍스트 변경
- `fda77a6` fix: toggleAsset/deleteAsset window에 등록 (Vite 모듈 스코프)

## Day 11: 역추세매매 프리미엄 엔진 Phase 1 (2026-02-09)

### 엔진 코어 구현 (파인스크립트 1:1 재구현)
**정본 소스**: `scripts/역추세매매 현물 v0.4.txt`

**신규 파일**:
```
app/strategy_engine/
├── __init__.py          # 모듈 초기화
├── presets.py           # OSC_PRESETS, HTF_DEFAULTS
├── models.py            # Candle, SignalResult, MRConfig
├── indicators.py        # SPO, VWMA, HMA, Ichimoku, Supertrend
├── regime_detector.py   # 4국면 판별 (R1~R4)
└── signal_generator.py  # 매수/매도 신호 생성
```

**지표 구현 (indicators.py)**:
- `smoother_f(src, length)` - EMA 변형 (PineScript smoother_F)
- `calc_spo(close, ...)` - Smooth Price Oscillator (normalized_osc, BB bands)
- `calc_vwma(close, volume, length)` - Volume Weighted Moving Average
- `calc_hma(close, length)` - Hull Moving Average
- `calc_ichimoku(high, low, ...)` - 일목균형표 (tenkan, kijun, senkouA/B)
- `calc_supertrend(high, low, close, atr_len, factor)` - Supertrend

**4국면 엔진 (regime_detector.py)**:
| 국면 | 조건 | 매수 정책 | 매도 정책 |
|------|------|-----------|-----------|
| R1 | 정배열 + ST상승 | 눌림 1회 트리거 | 확대 (1.3x) |
| R2 | 정배열 + ST하락 | 금지 (0x) | 확대 (1.6x) |
| R3 | 역배열 + ST상승 | 돌파 1회 트리거 | 일반 (1.3x) |
| R4 | 역배열 + ST하락 | 확대 (1.2x) | 축소 (0.7x) |

**신호 생성 (signal_generator.py)**:
- OSC 매수: `sig_up_raw = osc < -threshold AND crossover`
- OSC 매도: `sig_dn_raw = osc > threshold AND crossunder`
- R1 눌림: HULL 하락 시 armed → osc_trigger 시 1회 fire
- R3 돌파: senkouB 상향돌파 시 1회 fire
- 익절 게이트: `close >= avg * (1 + min_profit + fee_buffer)`

**테스트 (47개 PASS)**:
- `tests/test_indicators.py` - 지표 계산 테스트 (24개)
- `tests/test_signal_generator.py` - 신호 생성 테스트 (23개)

**커밋**:
- `96e3983` feat: 역추세매매(MR) 프리미엄 엔진 Phase 1 - 지표 파이썬 재구현

## Day 12: 역추세매매 프리미엄 엔진 Phase 2 (2026-02-09)

### 시세 + 실행 모듈 구현

**신규 파일**:
```
app/strategy_engine/
├── candle_fetcher.py    # 거래소 OHLCV 조회 + 메모리 캐시
├── position_manager.py  # 트랜치 기반 포지션 계산
└── hub_integration.py   # 시그널 → 주문 실행 브릿지

scripts/
└── migrate_premium_tables.sql  # DB 마이그레이션
```

**candle_fetcher.py** - 거래소 OHLCV 조회:
- OKX, Binance, Bybit, Upbit 지원
- `CandleData` 데이터클래스 (numpy 배열)
- `CandleCache` 메모리 캐시 (싱글톤)
- `fetch_candles_from_exchange()` 비동기 조회

**position_manager.py** - 트랜치 기반 포지션 계산:
- A-type 공식: `spend = available * cash_use_pct * tranche_pct`
- `calculate_buy_quantity()` - 매수 수량 계산
- `calculate_sell_quantity()` - 매도 수량 계산
- `update_position_after_fill()` - 체결 후 포지션 업데이트 (이동평균)
- `get_effective_tranche_stage()` - 트랜치 순환/정지 처리

**hub_integration.py** - 시그널 → 주문 브릿지:
- `SignalEvent` - 허브용 시그널 이벤트 스키마
- `SignalSnapshot` - 감사 추적용 스냅샷
- `process_asset()` - 자산 처리 메인 진입점
- `signal_to_order_request()` - 시그널 → 주문 요청 변환

**DB 마이그레이션 (migrate_premium_tables.sql)**:
| 테이블 | 용도 |
|--------|------|
| premium_configs | 프리미엄 엔진 설정 |
| strategy_states | 전략 상태 (buy_stage, sell_stage 등) |
| candles | 캔들 데이터 캐시 |
| signal_events | 시그널 이벤트 기록 |
| signal_snapshots | 시그널 스냅샷 (감사 추적) |

**테스트 (60개 추가, 총 107개 PASS)**:
- `tests/test_candle_fetcher.py` - 캔들 조회/캐시 테스트 (15개)
- `tests/test_position_manager.py` - 포지션 계산 테스트 (28개)
- `tests/test_hub_integration.py` - 허브 연동 테스트 (17개)

**커밋**:
- `ea1d8a2` feat: 역추세매매(MR) 프리미엄 엔진 Phase 2 - 시세/실행 모듈

## Day 8 Fixes
- 종목명 쓰레기 데이터 제거 (`_clean_stock_name`)
- 섹터 데이터 수정 (업종 지수 기반)
- itsdangerous==2.1.2 추가

## Scope Exclusions
- SMC strategy/files, MFT candle, Futures

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
- Day 12: DONE (역추세매매 프리미엄 엔진 Phase 2~5 - 시세/실행/스케줄러/API/UI/백테스트)
- Day 13: DONE (역추세매매 프리미엄 엔진 Phase 6 - 라이브 테스트 준비)
- Day 14: DONE (추세매매 프리미엄 엔진 - HVI/QQE/백테스트/API)

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

## 역추세매매(MR) 프리미엄 엔진 - 전체 요약

### Phase 요약 (MR 엔진)
| Phase | 내용 | 파일 수 | 테스트 |
|-------|------|--------|--------|
| Phase 1 | 지표 파이썬 재구현 (SPO/HMA/Ichimoku/Supertrend) | 6개 | 47개 |
| Phase 2 | 시세/실행 모듈 (Candle/Position/Hub) | 4개 | +60개 |
| Phase 3 | 스케줄러 + FastAPI | 2개 | +58개 |
| Phase 4 | PC앱 UI (Rust 13개 + JS) | - | - |
| Phase 5 | 백테스트 엔진 | 1개 | +20개 |
| Phase 6 | 라이브 테스트 준비 (DRY-RUN) | 1개 | +31개 |
| **MR 소계** | - | **14개** | **216개** |

### Phase 요약 (Trend 엔진)
| Phase | 내용 | 파일 | 테스트 |
|-------|------|------|--------|
| Phase 1 | 지표 추가 (RSI/HVI/QQE) | indicators.py | +22개 |
| Phase 2 | 신호 생성기 | signal_generator_trend.py | +20개 |
| Phase 3 | 백테스트 엔진 | backtest_engine_trend.py | +27개 |
| Phase 4 | DB + Hub 확장 | migrate_trend_tables.sql, hub_integration.py | - |
| Phase 5 | API + Rust | premium_routes.py, commands.rs | - |
| **Trend 소계** | - | **5개** | **69개** |

### 전체 현황
| 엔진 | 테스트 | 비고 |
|------|--------|------|
| MR (역추세매매) | 216개 | 4국면 매매 |
| Trend (추세매매) | 69개 | HVI+QQE+VWMA |
| **총합** | **285개** | - |

### 파일 구조 (MR + Trend 통합)
```
app/strategy_engine/
├── __init__.py              # 모듈 초기화
├── presets.py               # OSC_PRESETS, HTF_DEFAULTS
├── models.py                # Candle, SignalResult, MRConfig, StrategyState
├── indicators.py            # SPO, VWMA, HMA, Ichimoku, Supertrend, RSI, HVI, QQE
├── regime_detector.py       # 4국면 판별 (R1~R4)
├── signal_generator.py      # MR 매수/매도 신호 생성
├── signal_generator_trend.py # Trend 매수/매도 신호 생성
├── candle_fetcher.py        # 거래소 OHLCV 조회 + 캐시
├── position_manager.py      # 트랜치 기반 포지션 계산
├── hub_integration.py       # 시그널 → 주문 브릿지 (MR + Trend)
├── scheduler.py             # 봉 확정 주기 스케줄러
├── backtest_engine.py       # MR 백테스트 엔진
└── backtest_engine_trend.py # Trend 백테스트 엔진

app/premium_routes.py        # FastAPI 프리미엄 API (/backtest/mr, /backtest/trend)

scripts/
├── migrate_premium_tables.sql  # MR DB 마이그레이션
├── migrate_trend_tables.sql    # Trend DB 마이그레이션
└── validate_live.py            # 라이브 검증 스크립트
```

### 아키텍처 (MR + Trend)
```
┌─────────────────────────────────────────────────────────────┐
│                       PC앱 (Tauri)                          │
│  MR 엔진 탭 │ Trend 엔진 탭 │ 백테스트 UI │ 시그널 모니터링 │
└────────────────────────┬────────────────────────────────────┘
                         │ Rust Commands (15개)
                         ▼
┌─────────────────────────────────────────────────────────────┐
│                FastAPI (premium_routes.py)                  │
│  /configs │ /scheduler │ /backtest/mr │ /backtest/trend     │
└────────────────────────┬────────────────────────────────────┘
                         ▼
┌─────────────────────────────────────────────────────────────┐
│                     Strategy Engine                         │
│  ┌────────────┐  ┌────────────┐  ┌────────────────────────┐ │
│  │ Indicators │  │MR Signal   │  │ Trend Signal           │ │
│  │SPO/HMA/RSI │  │Generator   │  │ Generator              │ │
│  │HVI/QQE/ST  │  │(4국면매매) │  │(HVI+QQE+VWMA)          │ │
│  └─────┬──────┘  └─────┬──────┘  └──────────┬─────────────┘ │
│        │               │                     │              │
│        ▼               ▼                     ▼              │
│  ┌────────────┐  ┌────────────┐  ┌────────────────────────┐ │
│  │  Candle    │  │  Position  │  │    Hub Integration     │ │
│  │  Fetcher   │  │  Manager   │  │ process_asset_mr/trend │ │
│  └─────┬──────┘  └────────────┘  └──────────┬─────────────┘ │
│        │                                     │              │
│        ▼                                     ▼              │
│  ┌────────────┐  ┌────────────┐  ┌────────────────────────┐ │
│  │ Scheduler  │  │ Backtest   │  │ Backtest Trend         │ │
│  │ (DRY-RUN)  │  │ Engine MR  │  │ Engine                 │ │
│  └─────┬──────┘  └────────────┘  └────────────────────────┘ │
└────────┼────────────────────────────────────────────────────┘
         ▼
┌──────────────┐            ┌──────────────────────────────────┐
│ 거래소 API   │            │ PostgreSQL                       │
│OKX/Binance/..│            │premium_configs (strategy_type)   │
└──────────────┘            └──────────────────────────────────┘
```

### 4국면 매매 정책
| 국면 | 조건 | 매수 | 매도 |
|------|------|------|------|
| R1 | 정배열+ST상승 | 눌림 1회 (1.0x) | 확대 (1.3x) |
| R2 | 정배열+ST하락 | 금지 (0x) | 확대 (1.6x) |
| R3 | 역배열+ST상승 | 돌파 1회 (1.0x) | 일반 (1.3x) |
| R4 | 역배열+ST하락 | 확대 (1.2x) | 축소 (0.7x) |

### 테스트 현황 (285개 PASS)
| 파일 | 테스트 수 | 비고 |
|------|----------|------|
| test_indicators.py | 24 | MR 지표 |
| test_indicators_trend.py | 22 | Trend 지표 (HVI/QQE) |
| test_signal_generator.py | 23 | MR 신호 |
| test_signal_generator_trend.py | 20 | Trend 신호 |
| test_candle_fetcher.py | 15 | 시세 조회 |
| test_position_manager.py | 28 | 포지션 계산 |
| test_hub_integration.py | 17 | 허브 연동 |
| test_scheduler.py | 52 | 스케줄러 |
| test_premium_routes.py | 22 | API |
| test_backtest_engine.py | 20 | MR 백테스트 |
| test_backtest_trend.py | 27 | Trend 백테스트 |
| test_integration.py | 15 | 통합 |

### 라이브 검증 사용법
```bash
# 페이퍼 트레이딩 (기본)
python scripts/validate_live.py --symbol BTC-USDT --duration 1h

# 실거래 모드
python scripts/validate_live.py --symbol BTC-USDT --duration 1h --live
```

---

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

### Phase 3: 스케줄러 + API (2026-02-09)

**신규 파일**:
```
app/
├── premium_routes.py    # FastAPI 프리미엄 엔드포인트

app/strategy_engine/
└── scheduler.py         # 봉 확정 주기 실행
```

**scheduler.py** - 봉 확정 주기 스케줄러:
- `PremiumScheduler` - 다중 자산 스케줄링 클래스
- 타임프레임별 봉 마감 시간 계산 (`get_next_bar_close_time`)
- 자산 등록/해제, 활성화/비활성화
- 에러 카운트 기반 자동 비활성화 (max_consecutive_errors)
- 배치 처리 지원 (max_concurrent_assets)

**premium_routes.py** - FastAPI 프리미엄 API:
| 엔드포인트 | 설명 |
|------------|------|
| `GET/POST /api/premium/configs` | 프리미엄 설정 목록/생성 |
| `GET/PUT/DELETE /api/premium/configs/{asset_id}` | 설정 조회/수정/삭제 |
| `GET /api/premium/states/{asset_id}` | 전략 상태 조회 |
| `POST /api/premium/states/{asset_id}/reset` | 상태 리셋 |
| `GET/POST /api/premium/scheduler/status` | 스케줄러 상태/시작 |
| `POST /api/premium/scheduler/stop/pause/resume` | 스케줄러 제어 |
| `POST /api/premium/scheduler/register/{asset_id}` | 자산 등록 |
| `POST /api/premium/signal/trigger` | 수동 시그널 트리거 |
| `GET /api/premium/signals` | 시그널 이벤트 목록 |

**테스트 (58개 추가, 총 165개 PASS)**:
- `tests/test_scheduler.py` - 스케줄러 테스트 (36개)
- `tests/test_premium_routes.py` - API 모델 테스트 (22개)

**커밋**:
- `76aa6cf` feat: 역추세매매(MR) 프리미엄 엔진 Phase 3 - 스케줄러 + API

### Phase 4: PC앱 UI (2026-02-09)

**Rust Commands** (`pc-app/src-tauri/src/commands.rs`):
```rust
// Premium Strategy API (13개)
get_premium_configs       // 전체 설정 조회
get_premium_config        // 개별 설정 조회
create_premium_config     // 설정 생성
update_premium_config     // 설정 수정
delete_premium_config     // 설정 삭제
get_strategy_state        // 전략 상태 조회
reset_strategy_state      // 전략 상태 초기화
get_scheduler_status      // 스케줄러 상태
start_scheduler           // 스케줄러 시작
stop_scheduler_premium    // 스케줄러 중지
register_to_scheduler     // 종목 등록
trigger_signal            // 수동 시그널
get_signal_events         // 시그널 이벤트 조회
```

**PC앱 UI** (`pc-app/ui/index.html` + `src/main.js`):
- MR 엔진 탭 추가 (프리미엄 전략 → MR 엔진)
- 스케줄러 상태 표시 (running/stopped/paused)
- 등록 종목 테이블 (심볼/TF/프리셋/매수단계/매도단계/상태)
- 종목 추가 폼 (오실레이터 프리셋, 단계, 필터 설정)
- 최근 시그널 목록 (매수/매도/시간/사유코드)

**JavaScript 함수**:
- `loadMrEngineTab()` - MR 탭 초기화
- `loadMrSchedulerStatus()` - 스케줄러 상태 갱신
- `loadMrConfigs()` - 설정 목록 렌더링
- `loadMrSignals()` - 시그널 이벤트 렌더링
- `triggerMrSignal(assetId)` - 수동 시그널 트리거
- `deleteMrConfig(assetId)` - 설정 삭제

**CSS 스타일** (`pc-app/ui/src/style.css`):
- `.mr-scheduler-status` - 스케줄러 상태 박스
- `.scheduler-state.state-*` - 상태별 색상
- `.configs-table` - 설정 테이블
- `.signal-item.signal-buy/sell` - 시그널 카드

### Phase 5: 백테스트 (2026-02-09)

**신규 파일**:
- `app/strategy_engine/backtest_engine.py` - MR 전략 백테스트 엔진
- `tests/test_backtest_engine.py` - 백테스트 테스트 (20개)

**백테스트 엔진 핵심 클래스**:
```python
@dataclass
class BacktestMetrics:
    total_return_pct: float  # 총 수익률
    cagr_pct: float          # 연환산 수익률
    max_drawdown_pct: float  # 최대 낙폭
    sharpe_ratio: float      # 샤프 비율
    win_rate_pct: float      # 승률
    total_trades: int        # 총 거래 수
    profit_factor: float     # 이익비율

def run_mr_backtest(candles, config, initial_capital) -> BacktestResult
def generate_sample_candles(days, base_price) -> List[Candle]
```

**API 엔드포인트**:
- `POST /api/premium/backtest/mr` - MR 백테스트 실행

**Rust Command**:
```rust
#[tauri::command]
pub async fn run_mr_backtest(
    access_token, exchange, symbol, timeframe,
    days, initial_capital, osc_preset, ...
) -> Result<serde_json::Value, String>
```

**PC앱 UI** (`pc-app/ui/index.html`):
- MR 엔진 탭 백테스트 섹션
- 메트릭 카드 6개 (수익률/CAGR/MDD/샤프/승률/거래수)
- 자산 추이 차트 (Chart.js)

**JavaScript 함수**:
- `runMrBacktest()` - 백테스트 실행
- `displayMrBacktestResult()` - 결과 표시
- `drawMrBacktestChart()` - 차트 그리기

**커밋**:
- `826a479` feat: 역추세매매(MR) 프리미엄 엔진 Phase 5 - 백테스트

### Phase 6: 라이브 테스트 준비 (2026-02-09)

**스케줄러 개선** (`app/strategy_engine/scheduler.py`):
```python
@dataclass
class SchedulerConfig:
    dry_run: bool = True      # 페이퍼 트레이딩 모드
    log_signals: bool = True  # 시그널 로깅

@dataclass
class ProcessingStats:
    total_processed: int      # 처리된 자산 수
    total_signals: int        # 생성된 시그널 수
    total_buy_signals: int    # 매수 시그널 수
    total_sell_signals: int   # 매도 시그널 수
    total_errors: int         # 에러 수
    start_time: datetime      # 시작 시간

@dataclass
class SignalLog:
    timestamp, asset_id, symbol, exchange
    action, reason_code, dry_run, executed
```

**신규 메서드**:
- `scheduler.is_dry_run` - DRY-RUN 모드 확인
- `scheduler.set_dry_run(enabled)` - DRY-RUN 모드 전환
- `scheduler.reset_stats()` - 통계 초기화
- `scheduler.get_recent_signals(limit)` - 최근 시그널 조회
- `scheduler.stats` - 처리 통계 (ProcessingStats)
- `scheduler.signal_history` - 시그널 히스토리 (List[SignalLog])

**라이브 검증 스크립트** (`scripts/validate_live.py`):
```bash
# 사용법
python scripts/validate_live.py --symbol BTC-USDT --exchange okx --duration 1h
python scripts/validate_live.py --config config.json --duration 24h --dry-run
python scripts/validate_live.py --live  # 실거래 모드

# 출력
validation_result.json    # 검증 결과
validation_signals.jsonl  # 시그널 로그
validate_live.log        # 실행 로그
```

**검증 결과 (ValidationResult)**:
- duration_seconds: 검증 소요 시간
- total_checks: 처리된 체크 수
- signals_generated: 생성된 시그널 수
- buy_signals / sell_signals: 매수/매도 시그널 수
- errors: 에러 발생 수
- success: 성공 여부

**통합 테스트** (`tests/test_integration.py` - 15개):
- `TestSignalIdGeneration` - 시그널 ID 생성
- `TestProcessAssetIntegration` - 자산 처리 통합
- `TestSignalToOrderIntegration` - 시그널 → 주문 변환
- `TestSchedulerIntegration` - 스케줄러 라이프사이클
- `TestFullPipelineIntegration` - 전체 파이프라인 테스트
- `TestSignalEventStructure` - 시그널 이벤트 구조
- `TestPositionTracking` - 포지션 트래킹

**스케줄러 테스트 추가** (`tests/test_scheduler.py` - 16개 추가, 총 52개):
- `TestDryRunMode` - DRY-RUN 모드 테스트 (4개)
- `TestSchedulerStats` - 처리 통계 테스트 (5개)
- `TestSignalLogging` - 시그널 로깅 테스트 (4개)
- `TestStatusWithStats` - 상태 + 통계 테스트 (3개)

**테스트 현황**: 총 216개 PASS (전체 strategy_engine 테스트)

## Day 14: 추세매매(Trend) 프리미엄 엔진 (2026-02-09)

### 개요
**정본 소스**: Stock Trend Auto v7 (PineScript)

**Entry 조건** (4가지 모두 충족):
1. Supertrend 상승 (st_dir < 0 = bullish)
2. HVI 초록 (g_enabled = True)
3. QQE 양수 (primary_rsi > 50)
4. close > HTF VWMA(156)

**Exit 우선순위**:
1. Hard SL: entry_close <= entry_price * (1 - hard_sl_pct/100)
2. TP1: exit_close >= entry_price * (1 + tp1_pct/100)
3. SPO Split: SPO signal_dn 발생 시 분할 매도
4. ST Flip: Supertrend 하락 전환 시 전량 청산

### Phase 요약
| Phase | 내용 | 파일 | 테스트 |
|-------|------|------|--------|
| Phase 1 | 지표 추가 (RSI, HVI, QQE MOD) | indicators.py | +22개 |
| Phase 2 | 신호 생성기 (TrendConfig/State) | signal_generator_trend.py | +20개 |
| Phase 3 | 백테스트 엔진 | backtest_engine_trend.py | +27개 |
| Phase 4 | DB 마이그레이션 + Hub 확장 | migrate_trend_tables.sql, hub_integration.py | - |
| Phase 5 | API 엔드포인트 + Rust 명령어 | premium_routes.py, commands.rs | - |
| Phase 6 | 테스트 작성 및 검증 | test_*_trend.py | 69개 |
| **총합** | - | **8개** | **69개** |

### 파일 구조
```
app/strategy_engine/
├── signal_generator_trend.py  # TrendConfig, TrendState, generate_trend_signal
├── backtest_engine_trend.py   # run_trend_backtest
├── hub_integration.py         # process_asset_trend (수정)
├── indicators.py              # calc_rsi, calc_hvi, calc_qqe_mod (추가)

app/
├── premium_routes.py          # /backtest/trend 엔드포인트 (수정)

scripts/
├── migrate_trend_tables.sql   # DB 마이그레이션

pc-app/src-tauri/src/
├── commands.rs                # run_trend_backtest (추가)
├── main.rs                    # 명령어 등록 (수정)

tests/
├── test_indicators_trend.py   # HVI, QQE, VWMA 테스트 (22개)
├── test_signal_generator_trend.py  # Entry/Exit 로직 테스트 (20개)
├── test_backtest_trend.py     # 백테스트 엔진 테스트 (27개)
```

### 지표 구현 (indicators.py 추가)

**calc_rsi(close, length)** - Relative Strength Index:
```python
# RSI = 100 - 100/(1 + RS)
# RS = Avg Gain / Avg Loss (Wilder smoothing)
```

**calc_hvi(high, low, close, volume, length, divisor)** - Historical Volatility Indicator:
```python
# LazyBear's HVI
# Returns: {'g_enabled', 'r_enabled', 'gr_enabled'}
# g_enabled: 초록 = 상승 추세
# r_enabled: 빨강 = 하락 추세
```

**calc_qqe_mod(close, rsi_length, rsi_smoothing, qqe_factor)** - QQE MOD:
```python
# Quantitative Qualitative Estimation
# Returns: {'primary_rsi', 'qqe_line', 'is_positive', 'trend_dir'}
# is_positive: RSI smoothed > 50
```

### TrendConfig 설정 (signal_generator_trend.py)
```python
@dataclass
class TrendConfig:
    # 타임프레임
    entry_tf: str = "1D"      # 매수 판단 타임프레임
    exit_tf: str = "1D"       # 매도 판단 타임프레임
    htf_tf: str = "1W"        # HTF VWMA 기준 타임프레임

    # Entry 지표
    st_atr_len: int = 10
    st_factor: float = 3.0
    hvi_length: int = 200
    hvi_divisor: float = 3.6
    qqe_rsi_length: int = 6
    qqe_rsi_smoothing: int = 5
    qqe_factor: float = 3.0
    htf_vwma_len: int = 156

    # Exit 조건
    hard_sl_pct: float = 7.0          # 하드 손절 %
    tp1_pct: float = 21.0             # TP1 목표 %
    tp1_sell_pct: float = 50.0        # TP1 매도 비율 %
    use_spo_split: bool = True        # SPO 분할매도
    use_st_flip_exit: bool = True     # ST 전환 청산

    # SPO Split 분할매도
    sell_tranches: List[float] = [10.0, 20.0, 30.0, 5.0, 2.5, 1.0]
    max_sell_tranches: int = 6
    after_max_sell: str = "cycle"     # extend/cycle/stop

    # 익절 게이트
    use_profit_gate: bool = True
    min_profit_pct: float = 0.10
    fee_buffer_pct: float = 0.20
```

### TrendState 상태 (signal_generator_trend.py)
```python
@dataclass
class TrendState:
    in_position: bool = False
    entry_price: float = 0.0
    entry_ts: int = 0
    position_qty: float = 0.0
    highest_since_entry: float = 0.0
    tp1_triggered: bool = False        # TP1 발동 여부
    sell_stage: int = 0                # SPO 분할매도 차수
    last_st_dir: int = 0               # 마지막 ST 방향
```

### Reason Codes
| 코드 | 설명 |
|------|------|
| TREND_ENTRY_FULL | 추세매매 진입 (4조건 충족) |
| TREND_EXIT_HARD_SL | 하드 손절 발동 (전량 청산) |
| TREND_EXIT_TP1 | 목표 익절 TP1 도달 (비율 청산) |
| TREND_EXIT_SPO_SPLIT | SPO 분할매도 (SELL1~6) |
| TREND_EXIT_ST_FLIP | Supertrend 전환 (전량 청산) |

### API 엔드포인트
**POST /api/premium/backtest/trend** - 추세매매 백테스트:
```json
// Request
{
  "exchange": "okx",
  "symbol": "BTC-USDT",
  "entry_tf": "1D",
  "exit_tf": "1D",
  "htf_tf": "1W",
  "days": 365,
  "initial_capital": 10000000,
  "hard_sl_pct": 7.0,
  "tp1_pct": 21.0,
  ...
}

// Response
{
  "success": true,
  "message": "추세매매 백테스트 완료: 400봉, 12거래",
  "metrics": {
    "total_return_pct": 45.2,
    "cagr_pct": 38.5,
    "max_drawdown_pct": -12.3,
    "sharpe_ratio": 1.8,
    "win_rate_pct": 75.0,
    ...
  },
  "equity_curve": [...],
  "trades": [...],
  "signals_count": 24
}
```

### Rust Command (commands.rs)
```rust
#[tauri::command]
pub async fn run_trend_backtest(
    access_token: String,
    exchange: String,
    symbol: String,
    entry_tf: Option<String>,
    exit_tf: Option<String>,
    htf_tf: Option<String>,
    days: Option<i32>,
    initial_capital: Option<f64>,
    // Entry 지표
    st_atr_len: Option<i32>,
    hvi_length: Option<i32>,
    qqe_rsi_length: Option<i32>,
    // Exit 조건
    hard_sl_pct: Option<f64>,
    tp1_pct: Option<f64>,
    use_spo_split: Option<bool>,
    ...
) -> Result<serde_json::Value, String>
```

### DB 마이그레이션 (migrate_trend_tables.sql)

**premium_configs 테이블 추가 컬럼**:
| 컬럼 | 타입 | 설명 |
|------|------|------|
| strategy_type | VARCHAR(20) | mr/trend 구분 |
| trend_entry_tf | VARCHAR(10) | 매수 타임프레임 |
| trend_exit_tf | VARCHAR(10) | 매도 타임프레임 |
| trend_htf_tf | VARCHAR(10) | HTF VWMA 타임프레임 |
| trend_st_* | various | Entry Supertrend 설정 |
| trend_hvi_* | various | HVI 설정 |
| trend_qqe_* | various | QQE 설정 |
| trend_exit_* | various | Exit 지표 설정 |
| trend_hard_sl_pct | FLOAT | 하드 손절 % |
| trend_tp1_pct | FLOAT | TP1 목표 % |
| trend_sell_tranches | JSONB | 분할매도 비율 |

**strategy_states 테이블 추가 컬럼**:
| 컬럼 | 타입 | 설명 |
|------|------|------|
| trend_in_position | BOOLEAN | 포지션 보유 여부 |
| trend_entry_price | FLOAT | 진입가 |
| trend_tp1_triggered | BOOLEAN | TP1 발동 여부 |
| trend_sell_stage | INTEGER | 분할매도 차수 |

### 테스트 현황 (69개 PASS)
| 파일 | 테스트 수 |
|------|----------|
| test_indicators_trend.py | 22 |
| test_signal_generator_trend.py | 20 |
| test_backtest_trend.py | 27 |

### 전체 테스트 현황
```
285 passed (MR 216개 + Trend 69개)
```

## Day 8 Fixes
- 종목명 쓰레기 데이터 제거 (`_clean_stock_name`)
- 섹터 데이터 수정 (업종 지수 기반)
- itsdangerous==2.1.2 추가

## Scope Exclusions
- SMC strategy/files, MFT candle, Futures

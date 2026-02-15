# 큐브시스템 (QUBE System) — BBooster Hub
- Company: 큐브시스템 (QUBE System)
- Repo: C:\Users\pc\새 폴더\AUAT
- VPS: 76.13.180.30 (https://qube-system.com)
- SSOT: docs/FINISH_SSOT.md, docs/PROJECT_STATUS.md
- Rules: docs/AI_RULES.md (MUST read first)

---

## 전체 Phase 진행 현황

| Phase | 항목 | 상태 | Day |
|-------|------|------|-----|
| Phase 1 | 역추세매매(MR) 완성 | ✅ DONE | Day 6~16 |
| Phase 2 | 추세매매(Trend) 완성 | ✅ DONE | Day 17~18 |
| Phase 3 | 커스텀 전략 | ✅ DONE | Day 19~20 |
| Phase 3.5 | 실전 거래 엔진 (KIS 주문 타이밍) | ✅ DONE | Day 21 |
| **Phase 4** | **시장분석 — 국내** | 🔄 진행중 | **Day 22~** |
| Phase 5 | 시장분석 — 해외 | 대기 | - |
| Phase 6 | 시장분석 — ETF | 대기 | - |
| Phase 7 | 시장분석 — 코인 | 대기 | - |
| Phase 8 | 종목분석 상세 | 대기 | - |
| Phase 9 | 모바일 앱 완성 | 대기 | - |
| Phase 10 | 호환 점검 | 대기 | - |

---

## Phase 3.5: 실전 거래 엔진 (Day 21~)

**목표**: KIS_KR/KIS_US 실전 매매를 위한 주문 타이밍 설정 UI 및 실행 로직

### KIS_KR (국내주식) 주문 설계

```
┌─ KIS_KR 주문 설정 ──────────────────────────────┐
│                                                   │
│  주문 방식: [▼ 드롭다운]                         │
│    ├ 정규장 마감 전                               │
│    ├ 넥스트트레이드 마감 전                       │
│    └ 다음날 시가                                  │
│                                                   │
│  주문 타이밍: 마감 [30] 초 전                     │
│  (다음날 시가 선택 시 비활성화)                   │
│                                                   │
│  주문 유형: 시장가 (ⓘ)                           │
│                                                   │
└───────────────────────────────────────────────────┘
```

| 주문 방식 | 신호 판단 시점 | 주문 실행 시점 | 비고 |
|----------|---------------|---------------|------|
| 정규장 마감 전 | 15:20 - N초 전 | 15:20 - N초 전 | 동시호가(15:20) 전 체결 |
| 넥스트트레이드 마감 전 | 20:00 - N초 전 | 20:00 - N초 전 | 넥스트트레이드 지원 종목만 |
| 다음날 시가 | 당일 종가 확정 후 | 다음날 09:00 | 갭 리스크 있음 |

### KIS_US (해외주식) 주문 설계

```
┌─ KIS_US 주문 설정 ──────────────────────────────────┐
│                                                      │
│  종가마감 신호: 마감 [2] 분 전 (ⓘ)                  │
│                                                      │
│  주문 유형: 지정가 (ⓘ)                              │
│  └ "해외주식은 KIS API에서 시장가 미지원"            │
│                                                      │
│  슬리피지: [3] 틱 (ⓘ)                               │
│  └ 매수: 현재가 + N틱 / 매도: 현재가 - N틱          │
│                                                      │
└──────────────────────────────────────────────────────┘
```

| 단계 | 시점 | 동작 |
|------|------|------|
| 1. 신호 판단 | 06:00 - N분 전 | 현재가를 종가로 간주, 시그널 계산 |
| 2. 현재가 조회 | 시그널 발생 즉시 | KIS API로 현재가 조회 |
| 3. 지정가 계산 | 즉시 | 매수: +N틱 / 매도: -N틱 |
| 4. 주문 실행 | 즉시 | 계산된 지정가로 주문 |
| 5. 체결 확인 | 마감까지 | 미체결 시 처리 방법 결정 필요 |

### 코인 (OKX/BINANCE/BYBIT/UPBIT)

- 별도 설정 팝업 없음
- 24시간 거래, 시장가 즉시 실행
- 시그널 발생 → 즉시 시장가 주문

### 공통 사항

- 모든 설정값은 사용자 설정 화면에서 변경 가능
- ⓘ 툴팁으로 초보 사용자 이해 지원
- 백테스트에는 영향 없음 (실전 거래 전용)

### Day 21 작업 계획

- [x] KIS_KR 주문 설정 팝업 UI ✅
- [x] KIS_US 주문 설정 팝업 UI ✅
- [ ] 주문 타이밍 설정 저장 로직 (DB/API)
- [ ] 스케줄러 연동 (마감 N초/분 전 트리거)

### Day 22 작업 계획

- [ ] KIS_KR 시장가 주문 실행 로직
- [ ] KIS_US 지정가 주문 실행 로직 (슬리피지 적용)
- [ ] 미체결 주문 처리 로직
- [ ] 실전 테스트 (모의투자)

---

## 완료 히스토리

### Current Status (2026-02-15)
- Week A~D: DONE (브랜드/사이트/PC앱/Android APK 기반)
- Day 6~14: DONE (대시보드/종목분석/계정관리/전략설정/MR엔진/Trend엔진)
- Day 15: DONE (백테스트 벡터화 최적화 20초→0.3초)
- Day 16: DONE (트레이딩뷰 백테스트 동일화 + UI 개편)
- Day 17: DONE (추세매매 최종 종합 업그레이드)
- Day 18: DONE (추세매매 검증 + 전 거래소 백테스트)
- Day 19: DONE (커스텀 전략 조건 빌더 Phase 3)
- Day 20: DONE (커스텀 백테스트 Tauri invoke + 프리셋 파라미터 입력칸)
- Day 21: DONE (KIS 주문 설정 UI Phase 3.5)
- Day 22: DONE (시장분석 Phase 4 - 투자자순매수/거래대금 전일대비)

## Day 22 완료사항 (2026-02-15)

### 시장분석 개선 (Phase 4)

**작업 내용**: 투자자별 순매수 데이터 수정 + 거래대금 전일대비 구현

### 1. 투자자별 순매수 데이터 수정

**문제**: 네이버 HTML 구조 변경으로 파싱 실패 (KOSPI/KOSDAQ 동일 값 표시)

**해결**: `data_collector.py` - `get_investor_trend_from_naver()` 함수 수정

| 항목 | 기존 | 수정 후 |
|------|------|---------|
| 파싱 대상 | `<a>` 태그 | `<dd class="dd">` 태그 |
| URL | `/sise/` (메인) | `/sise/sise_index.naver?code=KOSPI` (지수별) |
| 데이터 저장 | KOSPI만 저장 | KOSPI/KOSDAQ 각각 저장 |

**수정 파일**:
- `app/market_analysis/data_collector.py`: 파싱 로직 전면 수정
- `app/main.py`: 시장별 투자자 데이터 반환 (`rt.get("foreign_net")`)

**검증 결과**:
```
KOSPI:  외국인 -9,220억 / 기관 +831억 / 개인 +7,141억
KOSDAQ: 외국인 -2,414억 / 기관 -3,381억 / 개인 +6,220억
```

### 2. 거래대금 전일대비 구현

**문제**: `trading_value_prev`가 프론트엔드 객체에 누락

**해결**:

| 파일 | 수정 내용 |
|------|-----------|
| `app/main.py` | 금/토/일 → 목요일 대비 로직 추가 (`LIMIT 5` + weekday 체크) |
| `app/main.py` | `POST /api/market/signals/init` 엔드포인트 추가 |
| `pc-app/ui/src/main.js` | kospi/kosdaq 객체에 `trading_value_prev` 필드 추가 |

**금/토/일 전일대비 로직**:
```python
if today.weekday() in [4, 5, 6]:  # 금(4), 토(5), 일(6)
    # 목요일(weekday=3) 데이터 찾기
    for r in rows[1:]:
        if r.date and r.date.weekday() == 3:
            trading_value_prev = r.trading_value
            break
else:
    # 일반 전일 데이터
    trading_value_prev = rows[1].trading_value
```

**검증 결과**:
```
KOSPI:  30.8조 / 목(2/12) 27.8조 → +10.8%
KOSDAQ: 11.3조 / 목(2/12) 10.2조 → +10.8%
```

### 3. 수정 파일 목록

| 파일 | 변경 |
|------|------|
| `app/main.py` | 투자자 데이터 시장별 분리, 거래대금 전일대비 로직, init 엔드포인트 |
| `app/market_analysis/data_collector.py` | 네이버 투자자 파싱 수정, 시장별 데이터 저장 |
| `pc-app/ui/src/main.js` | `trading_value_prev` 필드 추가 |

### 4. 검증 및 배포

| 항목 | 결과 |
|------|------|
| Python 문법 검증 | ✅ passed |
| npm run build | ✅ passed |
| cargo tauri build | ✅ passed |
| VPS 배포 | ✅ 완료 |
| API 검증 | ✅ 네이버 데이터와 일치 |

---

## Day 21 진행사항 (2026-02-14)

### KIS 주문 설정 모달 UI 구현 (Phase 3.5)

**목표**: KIS_KR/KIS_US 거래소 선택 시 주문 타이밍 설정 팝업 표시

### 1. 구현 완료

| 항목 | 상태 | 설명 |
|------|------|------|
| KIS_KR 주문 설정 모달 | ✅ | 주문방식/타이밍/주문유형 |
| KIS_US 주문 설정 모달 | ✅ | 종가마감신호/주문유형/슬리피지 |
| 툴팁 CSS 스타일 | ✅ | ⓘ 아이콘 hover 시 설명 표시 |
| 거래소 change 이벤트 | ✅ | 3개 탭 모두 KIS 감지 연결 |
| 탭 순서 변경 | ✅ | 전략현황→역추세→추세→커스텀 |
| 커스텀 로딩 UI | ✅ | MR/Trend와 동일 스타일 |

### 2. 수정 파일 (3개)

| 파일 | 변경 내용 |
|------|-----------|
| `pc-app/ui/index.html` | KIS_KR/KIS_US 모달 HTML 추가 (+93줄), 탭 순서 변경, 로딩 UI 개선 |
| `pc-app/ui/src/main.js` | KIS 모달 핸들러 함수 추가 (+104줄), 거래소 change 이벤트 연결 |
| `pc-app/ui/src/style.css` | 툴팁 CSS 스타일 추가 (+64줄) |

### 3. KIS_KR 모달 구성

```
┌─ KIS_KR 주문 설정 ────────────────────────┐
│ 주문 방식: [정규장 마감 전 ▼]              │
│   - 정규장 마감 전                          │
│   - 넥스트트레이드 마감 전                  │
│   - 다음날 시가                             │
│                                             │
│ 주문 타이밍: 마감 [30] 초 전                │
│   (다음날 시가 선택 시 숨김)                │
│                                             │
│ 주문 유형: 시장가 ⓘ                        │
│                                             │
│              [취소]  [확인]                 │
└─────────────────────────────────────────────┘
```

### 4. KIS_US 모달 구성

```
┌─ KIS_US 주문 설정 ────────────────────────┐
│ 종가마감 신호: 마감 [2] 분 전 ⓘ           │
│                                             │
│ 주문 유형: 지정가 (API 제한) ⓘ            │
│                                             │
│ 슬리피지: [3] 틱 ⓘ                         │
│                                             │
│              [취소]  [확인]                 │
└─────────────────────────────────────────────┘
```

### 5. 검증 및 배포

| 항목 | 결과 |
|------|------|
| pytest 341 tests | ✅ passed |
| npm run build | ✅ passed |
| cargo tauri build | ✅ passed (5m 25s) |
| VPS 배포 | ✅ 완료 |

**커밋**: `3f797d4`

### 6. 남은 작업

- [ ] 주문 타이밍 설정 DB 저장 로직
- [ ] 스케줄러 연동 (마감 N초/분 전 트리거)
- [ ] KIS_KR 시장가 주문 실행 로직
- [ ] KIS_US 지정가 주문 실행 로직 (슬리피지 적용)

---

### 홈 화면 개선 (Phase 3.6)

**목표**: 누적수익률/일간변동 정상화, 수익률차트 제거, 보유자산 거래내역 모달

### 1. 구현 완료

| 항목 | 상태 | 설명 |
|------|------|------|
| 수익률추이 그래프 제거 | ✅ | 홈 화면에서 차트 섹션 삭제 |
| 보유자산 클릭 → 거래내역 모달 | ✅ | 전략명/타입/날짜/수량/금액/수익금/수익률/누적 표시 |
| 누적수익률 (보유종목 기반) | ✅ | 총 수익금 / 총 원금 × 100 |
| 일간변동 (스냅샷 기반) | ✅ | 어제 00:00 스냅샷 대비 현재 자산 변동 |
| 원화(예수금) 표시 수정 | ✅ | KIS API output2 리스트/딕셔너리 양쪽 처리 |

### 2. 수정 파일 (5개)

| 파일 | 변경 내용 |
|------|-----------|
| `app/main.py` | 자산별 거래내역 API 추가 (`/api/asset/trades`) |
| `app/data_provider.py` | KIS output2 형식 처리 개선 (예수금 조회) |
| `pc-app/ui/index.html` | 수익률차트 제거, 자산 거래내역 모달 추가 |
| `pc-app/ui/src/main.js` | loadPortfolioChart 제거, showAssetTradesModal 추가 |
| `pc-app/src-tauri/src/commands.rs` | get_asset_trades 명령어 추가 |

### 3. 누적수익률 계산 방식

```python
# app/main.py 라인 7990-8015
for h in holdings:
    total_profit_loss += profit_loss  # 수익금 합계
    total_cost += avg_price * quantity  # 원금 합계

total_profit_rate = (total_profit_loss / total_cost) * 100
```

### 4. 일간변동 계산 방식

```python
# app/main.py 라인 8017-8078
today = now.replace(hour=0, minute=0, second=0, microsecond=0)
yesterday = today - timedelta(days=1)

# 어제 00:00 스냅샷 조회
yesterday_snapshot = db.execute(
    text("SELECT total_asset_krw FROM portfolio_snapshots WHERE user_id = :user_id AND snapshot_date = :yesterday"),
    {"user_id": current_user.id, "yesterday": yesterday}
).scalar()

daily_change = total_assets - yesterday_snapshot
daily_change_rate = ((total_assets / yesterday_snapshot) - 1) * 100
```

- 스냅샷 갱신: 6시간마다 (과도한 DB 업데이트 방지)

### 5. 보유자산 거래내역 모달

```
┌─ 삼성전자 거래내역 ─ KIS_KR ──────────────────────────┐
│ 전략명 │ 타입 │ 날짜 │ 수량 │ 금액 │ 수익금 │ 수익률 │ 누적 │
│ MR전략 │ 매수 │ 02/10 │ 10 │ ₩830,000 │ - │ - │ - │
│ MR전략 │ 매도 │ 02/14 │ 10 │ ₩850,000 │ +₩20,000 │ +2.4% │ +₩20,000 │
└────────────────────────────────────────────────────────┘
```

### 6. 검증 및 배포

| 항목 | 결과 |
|------|------|
| Python 문법 검증 | ✅ main.py, data_provider.py |
| npm run build | ✅ passed |
| cargo tauri build | ✅ passed |
| VPS 배포 | ✅ 완료 |

**커밋**: `358e770`

---

## Day 20 완료사항 (2026-02-14)

### 프리셋 파라미터 입력칸 완성

**핵심 수정**: 프리셋 선택 시 파라미터 편집 가능하게 개선

| 프리셋 유형 | 표시 예시 |
|------------|----------|
| 동일 지표 비교 (골든크로스) | 단기 기간: [20]  장기 기간: [50] |
| 다른 지표 비교 (PRICE vs SMA) | SMA 기간: [20] |
| 고정값 비교 (RSI < 30) | 기간: [14]  과매도 기준: [30] |

**수정 내용**:
- 동일 지표 비교 시 "단기/장기" 라벨로 양쪽 파라미터 표시
- 다른 지표 비교 시 비교 지표명 + 파라미터 표시
- 프리셋 라벨에서 고정값 제거 (골든크로스 20↑50 → 골든크로스)
- ICHIMOKU 프리셋에 chikou_offset 파라미터 추가

**커밋**: `6a41ae4`, `e9feab9`

---

### 커스텀 백테스트 Tauri invoke 지원 + 교차검증

**핵심 수정**: PC앱 커스텀 백테스트 "Failed to fetch" 오류 해결

### 1. 수정 파일 (3개)

| 파일 | 변경 내용 |
|------|-----------|
| `pc-app/src-tauri/src/commands.rs` | `run_custom_backtest` 명령 추가 (45줄) |
| `pc-app/src-tauri/src/main.rs` | 명령 등록 추가 |
| `pc-app/ui/src/main.js` | `fetch` → `invoke` 전환 |

### 2. 신규 파일 (1개)

| 파일 | 용도 |
|------|------|
| `tests/run_custom_16tests.py` | 16개 커스텀 + 4개 MR/Trend 테스트 스크립트 |

### 3. 원인 및 해결

**문제**: 커스텀 백테스트에서 JavaScript `fetch` 직접 사용 → Tauri WebView에서 CORS/네트워크 오류

**해결**: MR/Trend 백테스트와 동일하게 `invoke('run_custom_backtest', ...)` 사용

### 4. 검증 결과

| 테스트 유형 | 결과 |
|------------|------|
| pytest 341 tests | ✅ passed |
| Custom 16 strategies | ✅ 16/16 |
| MR/Trend 4 tests | ✅ 4/4 |
| **Total** | **20/20** |

### 5. 배포

- Git commit: `4d3be41`
- VPS: 배포 완료

---

## Day 19 완료사항 (2026-02-13)

### 커스텀 전략 조건 빌더 Phase 3 완료

**구현 범위**: 사용자 정의 트레이딩 전략 + UI 조건 빌더 + 백테스트 엔진

### 1. 신규 파일 (4개)

| 파일 | 용도 |
|------|------|
| `app/strategy_engine/indicator_registry.py` | 14개 지표 메타데이터 정의 (프론트엔드 동적 UI 생성용) |
| `app/strategy_engine/custom_strategy.py` | Pydantic 모델 (ConditionItem, ConditionGroup, CustomRule 등) |
| `app/strategy_engine/condition_evaluator.py` | 조건 평가 엔진 (compute_indicator, evaluate_condition, evaluate_rule) |
| `app/strategy_engine/backtest_engine_custom.py` | 커스텀 전략 백테스트 엔진 |

### 2. 수정 파일 (5개)

| 파일 | 변경 내용 |
|------|-----------|
| `app/strategy_engine/indicators.py` | MACD, Stochastic, CCI, ADX, Bollinger Bands 추가 |
| `app/premium_routes.py` | `/indicators`, `/backtest/custom` 엔드포인트 추가 |
| `pc-app/ui/index.html` | 커스텀 탭 조건 빌더 UI 구조 |
| `pc-app/ui/src/main.js` | 735줄 추가 (조건 빌더 + 백테스트 로직) |
| `pc-app/ui/src/style.css` | 329줄 추가 (조건 빌더 스타일링) |

### 3. 지표 레지스트리 (14개 지표)

**이동평균 (6개)**:
- SMA (단순이동평균)
- EMA (지수이동평균)
- WMA (가중이동평균)
- HMA (헐이동평균)
- VWMA (거래량가중이동평균)
- BB (볼린저 밴드) - upper/middle/lower

**오실레이터 (4개)**:
- RSI (상대강도지수)
- MACD - macd/signal/histogram
- STOCH (스토캐스틱) - k/d
- CCI (상품채널지수)

**추세 (2개)**:
- ADX (평균방향지수) - adx/plus_di/minus_di
- SUPERTREND - direction/value

**변동성 (1개)**:
- ATR (평균진폭)

**가격 (1개)**:
- PRICE - open/high/low/close/volume

### 4. 연산자 목록

| 연산자 | 설명 |
|--------|------|
| > | 초과 |
| < | 미만 |
| >= | 이상 |
| <= | 이하 |
| == | 같음 |
| cross_above | 상향돌파 (골든크로스) |
| cross_below | 하향돌파 (데드크로스) |

### 5. API 엔드포인트

**GET /api/premium/indicators**:
```json
{
  "success": true,
  "indicators": { /* INDICATOR_REGISTRY */ },
  "operators": [ /* OPERATORS */ ]
}
```

**POST /api/premium/backtest/custom**:
```json
// Request
{
  "exchange": "OKX",
  "symbol": "BTC-USDT",
  "timeframe": "1D",
  "days": 365,
  "initial_capital": 10000000,
  "strategy": {
    "name": "내 전략",
    "entry_rules": { "groups": [...] },
    "exit_rules": { "groups": [...] },
    "stop_loss_pct": 5.0,
    "take_profit_pct": 10.0,
    "commission_pct": 0.015
  }
}

// Response
{
  "success": true,
  "message": "커스텀 백테스트 완료",
  "metrics": { /* TradingView 동일 포맷 */ },
  "trades": [...],
  "equity_curve": [...],
  "candles": [...]
}
```

### 6. 조건 빌더 데이터 구조

**ConditionItem** (단일 조건):
```python
{
  "indicator": "RSI",           # 좌측 지표
  "output": "value",            # 출력값
  "params": {"period": 14},     # 파라미터
  "operator": "<",              # 연산자
  "compare_type": "value",      # value | indicator
  "compare_value": 30           # 고정값 비교
}
```

**ConditionGroup** (조건 그룹):
```python
{
  "conditions": [ConditionItem, ...],
  "logic": "AND"  # AND | OR
}
```

**CustomRule** (진입/청산 규칙):
```python
{
  "groups": [ConditionGroup, ...]  # 그룹 간 OR 연결
}
```

### 7. 프론트엔드 함수

| 함수 | 용도 |
|------|------|
| `loadCustomExchangeDropdown()` | 6개 거래소 드롭다운 로드 |
| `initCustomConditionBuilder()` | 지표 레지스트리 로드 + UI 초기화 |
| `addConditionGroup(type)` | 조건 그룹 추가 (entry/exit) |
| `addCondition(groupId)` | 그룹에 조건 행 추가 |
| `removeCondition(condId)` | 조건 삭제 |
| `removeConditionGroup(groupId)` | 그룹 삭제 |
| `collectConditions(type)` | UI에서 조건 수집 |
| `runCustomBacktest()` | 백테스트 실행 |
| `displayCustomBacktestResult()` | 결과 표시 (MR/Trend 동일 포맷) |

### 8. 조건 평가 로직

**compute_indicator()**: 지표명 → 계산 함수 라우팅
```python
if indicator == "RSI":
    return calc_rsi(closes, params.get("period", 14))
if indicator == "MACD":
    result = calc_macd(closes, fast, slow, signal)
    return result.get(output, result["macd"])
# ...
```

**evaluate_condition()**: 단일 조건 평가 (bar_idx 기준)
```python
# cross_above 로직
prev_left <= prev_right AND left_val > curr_right

# cross_below 로직
prev_left >= prev_right AND left_val < curr_right
```

**evaluate_rule()**: 규칙 평가 (그룹 OR, 조건 AND/OR)
```python
for group in rule.groups:
    if group.logic == "AND":
        if all(evaluate_condition(c) for c in group.conditions):
            return True
    else:  # OR
        if any(evaluate_condition(c) for c in group.conditions):
            return True
return False
```

### 9. 백테스트 결과 포맷

**5카드 메트릭** (TradingView 동일):
- 총손익 (total_return_pct)
- 최대자본감소 (max_drawdown_pct)
- 총거래횟수 (total_trades)
- 수익성거래% (win_rate_pct)
- 수익지수 (profit_factor)

**수익률 테이블**: 전체/매수/매도 3열

**캔들차트**: SMA 20/50/200 + 매매 마커

**거래내역**: 수익금 + 수익률 표시

### 10. 테스트 결과

**API 테스트**:
```bash
# GET /indicators
curl https://qube-system.com/api/premium/indicators
# → 14개 지표 + 7개 연산자 반환 확인

# POST /backtest/custom (RSI < 30 진입, RSI > 70 청산)
curl -X POST https://qube-system.com/api/premium/backtest/custom \
  -H "Content-Type: application/json" \
  -d '{"exchange":"OKX","symbol":"BTC-USDT","timeframe":"1D","days":365,...}'
# → 백테스트 결과 정상 반환
```

**빌드 테스트**:
- npm run build: ✅ 953ms 완료 (C:\AUAT\pc-app\ui)
- VPS 배포: ✅ docker compose up -d --build

### 11. 커밋

```
cfc91f3 feat: 커스텀 전략 조건 빌더 + 13개 기술지표 + 백테스트 엔진
```

**변경 통계**: 9 files changed, 2691 insertions(+), 76 deletions(-)

### 12. 6개 거래소 지원

커스텀 전략 탭에서 전 거래소 백테스트 가능:
| 거래소 | 일봉 | 분봉 | 주봉 |
|--------|------|------|------|
| OKX | ✅ | ✅ | ✅ |
| BINANCE | ✅ | ✅ | ✅ |
| BYBIT | ✅ | ✅ | ✅ |
| UPBIT | ✅ | ✅ | ✅ |
| KIS_KR | ✅ | ❌ (당일만) | ✅ |
| KIS_US | ✅ | ❌ (당일만) | ✅ |

## Day 18 진행사항 (2026-02-13)

### 8. 신호 일치 검증 완료 (2026-02-13 최신)

**백테스트 ↔ 실시간 신호 동일성 확인:**
| 전략 | 함수 | 일치 |
|------|------|------|
| MR | generate_mr_signal() | ✅ 동일 함수 사용 |
| Trend | generate_trend_signal() | ✅ 동일 함수 사용 |

**수정된 버그:**
1. `backtest_engine_trend.py`: 최종 포지션 정산 시 `qty_to_close` 저장
   - 기존: `pnl = position.remove(qty); proceeds = position.quantity * price` (qty=0)
   - 수정: `qty_to_close = position.quantity; pnl = position.remove(qty_to_close); proceeds = qty_to_close * price`

**신규 디버그 API:**
- `POST /api/premium/debug/trend-indicators` - ST, HVI, QQE, HTF VWMA 봉별 확인

### 9. 전 거래소 종합 백테스트 (2026-02-13 15:41 완료)

**테스트 개요:**
- **총 테스트**: 580건 (성공 570, 실패 10)
- **기간**: 365일 (1년)
- **거래소**: 6개 (OKX, BINANCE, BYBIT, UPBIT, KIS_KR, KIS_US)
- **심볼**: 58개 (거래소당 9~10개)
- **전략 변형**: MR 5개 + Trend 5개 = 10개

**전략별 평균 수익률:**
| 전략 | 평균 수익률 | 평균 MDD | 테스트 수 |
|------|------------|----------|----------|
| MR (역추세) | -1.23% | -1.55% | 285건 |
| Trend (추세) | +3.94% | -4.13% | 285건 |

**거래소별 평균 수익률:**
| 거래소 | 평균 수익률 | 평균 MDD | 테스트 수 |
|--------|------------|----------|----------|
| OKX | -1.65% | -1.91% | 90건 |
| BINANCE | -1.47% | -1.79% | 100건 |
| BYBIT | -1.58% | -1.88% | 90건 |
| UPBIT | -2.00% | -2.29% | 90건 |
| **KIS_KR** | **+13.48%** | -4.58% | 100건 |
| KIS_US | +0.43% | -4.34% | 100건 |

**상위 10 수익률 (전부 추세매매/국내주식):**
| 순위 | 종목 | 전략 변형 | 수익률 | MDD |
|------|------|----------|--------|-----|
| 1 | SK하이닉스 (000660) | Trend default | +104.11% | -12.44% |
| 2-3 | SK하이닉스 (000660) | tight_sl/loose_sl | +104.11% | -12.44% |
| 4-6 | 삼성전자 (005930) | default/tight_sl/loose_sl | +79.54% | -10.82% |
| 7 | SK하이닉스 (000660) | fast_st | +72.09% | -12.27% |
| 8 | 삼성전자 (005930) | fast_st | +68.47% | -9.91% |
| 9 | SK하이닉스 (000660) | no_pyramid | +65.45% | -8.32% |
| 10-12 | 현대차 (005380) | default/tight_sl/loose_sl | +65.00% | -10.47% |

**결론:**
- 추세매매(Trend)가 역추세매매(MR)보다 평균 5% 이상 우수
- 국내주식(KIS_KR)이 암호화폐 대비 압도적 성과 (+13.48% vs -1.5%~-2%)
- 해외주식(KIS_US)도 양의 수익률 (+0.43%)
- OKX MATIC-USDT 심볼 미지원으로 10건 실패

**결과 파일:**
- JSON: `backtest_results_20260213_151820.json`
- CSV: `backtest_results_20260213_151820.csv`
- 스크립트: `tests/comprehensive_backtest.py`

### 1. HTF 필터 크립토/주식 분리 (Major Fix)
**문제**: 백테스트 엔진이 항상 VWMA 사용, 하지만 PineScript v8은:
- **크립토**: 일봉 SMA(200)
- **주식**: 주봉 VWMA(156)

**수정 파일**:
| 파일 | 변경 내용 |
|------|-----------|
| `signal_generator_trend.py` | `htf_sma_len: int = 200` 추가 |
| `backtest_engine_trend.py` | `precompute_sma()` 추가 + asset_type별 분기 |
| `premium_routes.py` | `htf_sma_len`, `asset_type` 파라미터 추가 |

### 2. Supertrend 기본값 20/5.0 통일 (작가님 확정)
**배경**: 10/3.0 (PineScript 기본값)으로 변경했다가 작가님 확정값 20/5.0으로 복원

**수정 파일**:
- `presets.py`, `signal_generator_trend.py`, `debug_trend_indicators.py`
- `test_signal_generator_trend.py` (검증 테스트)

### 3. signal_generator_trend.py PineScript v8 완전 재작성 (Major Refactor)

**핵심 변경사항**:

| 항목 | 변경 전 | 변경 후 |
|------|---------|---------|
| reason_code (1차 진입) | `TREND_ENTRY_FULL` | `TREND_ENTRY` |
| reason_code (피라미딩) | `TREND_ENTRY_PYR` | `TREND_PYR{n}` (예: TREND_PYR2) |
| barstate.isconfirmed | 미지원 | `is_bar_confirmed` 파라미터 추가 |
| N봉 신고가 계산 | 현재봉 포함 | 현재봉 제외 (high[1]부터 N봉) |
| 로직 순서 | EXIT→ENTRY | EXIT→PYR→ENTRY |

**PineScript v8 핵심 로직 일치**:
```python
# PineScript: highestN = ta.highest(high[1], pyrHighLen)
# high[1] = 직전봉, 현재봉 제외
pyr_high_threshold = np.max(entry_high[-(config.pyr_high_len + 1):-1])

# PineScript: canPyramid = position_size > 0 AND pyrCount < maxPyrEntries
#             AND pyrBreakout AND cooldown AND stBull AND htfOk
can_pyramid = cooldown_ok and breakout_ok and st_bullish and htf_ok
```

**reason_text 간소화**:
- "추세매매 진입: ST상승+HVI초록+QQE양수+HTF VWMA 상위" → "ENTRY: ST+HVI+QQE+HTF"
- "목표익절(TP1): +21% 도달, 50% 청산" → "TP1: +21% (50%)"
- "SPO 분할매도: SELL1 실행 (5%)" → "SPO S1 (5%)"

### 4. 테스트 업데이트
- `test_signal_generator_trend.py`: reason_code 변경 반영
- 35개 테스트 전체 통과

### 5. 테스트 결과
- ✅ 341 tests passed
- ✅ Frontend build OK
- ✅ debug_trend_indicators.py 정상 동작 (20/5.0)

### 6. 추세매매 백테스트 3가지 문제 수정 (2026-02-13)

**문제 1: SPO OFF 설정 무시**
- **원인**: JS에서 camelCase (`useSpoSplit`) → Rust는 snake_case (`use_spo_split`) 기대
- **수정**: main.js invoke 파라미터 전부 snake_case로 변경
- **파일**: `pc-app/ui/src/main.js` line ~8429

**문제 2: 백테스트 로딩 48초 → 7초**
- **원인**: KIS 1W (주봉) HTF 캔들 조회가 36초 소요
- **수정**: KIS 거래소는 HTF 캔들 스킵 (signal_tf만 사용)
- **파일**: `app/premium_routes.py`

**문제 3: 캔들 날짜 '25' 표시**
- **원인**: lightweight-charts 기본 날짜 포맷
- **수정**: tickMarkFormatter + localization 추가
- **파일**: `pc-app/ui/src/main.js` line ~7887

### 7. KIS 토큰 캐싱 추가 (2026-02-13)

**문제**: "KIS 토큰 발급 실패" 403 에러
- **원인**: "1분당 1회 제한" - candle_fetcher.py와 kis_api.py가 별도 캐시 사용
- **수정**:
  - `kis_api.py`: get_kis_token()에 app_key 기반 캐시 추가
  - `candle_fetcher.py`: kis_api.py 캐시 재사용
- **결과**: 중복 토큰 발급 방지, 403 에러 해결

### 5. 테스트 결과
- ✅ 341 tests passed
- ✅ Frontend build OK
- ✅ VPS 배포 완료

### 커밋
- `9385063` fix: JS invoke snake_case + KIS HTF 스킵 + 날짜 포맷
- `adc6fcf` fix: KIS 토큰 캐싱 추가 (1분당 1회 제한 회피)

### 남은 작업
- [ ] PineScript Data Window와 봉별 값 비교 (정합성 최종 검증)
- [ ] 다중 심볼 테스트 (삼성전자, SK하이닉스, AAPL, BTC-USDT)
- [ ] PC앱 빌드 및 최종 검증

## Day 17 완료사항 (2026-02-12)
- v8 엔진 로직 완료 (피라미딩/ATR손절/ST Exit Mode)
- 추세매매 UI 전면 재설계 (MR 동일 구조)
- TF 구조: signal_tf + exit_tf + htf_tf 3개
- ST 기본값: 20/5.0 확정
- 실제 캔들 백테스트 연동 완료
- smoother_f NaN 전파 버그 수정 (indicators.py)
- 이모지 제거, 글자크기 MR 동일화
- 거래소 6개 드롭다운 완료
- Rust recursion_limit 512 증가 (serde_json 매크로 확장 한계)
- **MR 백테스트 custom 프리셋 버그 수정** (osc_smooth_len/osc_threshold 무시 문제)
- **추세매매 백테스트에 MR 동일 구조 적용:**
  - 프리로드 단계 추가 (preload_candles)
  - 로딩 UI 추가 (스피너 + 메시지)
  - 버튼 상태 관리 (disabled + 텍스트 변경)
  - 콘솔 로깅 + 에러 처리 humanizeMrError
- KIS_KR 백테스트 정상 동작 확인 (SK하이닉스 1000일 → 2거래)
- **백테스트 캔들차트 추가 (TradingView Lightweight Charts):**
  - MR/Trend 백테스트 응답에 candles 필드 추가
  - 캔들차트 컨테이너 및 createBacktestCandleChart 함수 구현
  - 거래 마커(매수/매도) 표시 지원
- **KIS 마스터 캐시 개선:**
  - refresh_master_cache 에러 로깅 개선
  - 미국 주식/ETF fallback 목록 대폭 확장 (SPY, QQQ, TQQQ 등)
  - /api/debug/master-cache 디버그 엔드포인트 추가
- 테스트: pytest 341 passed
- PC앱 빌드: BBooster_1.0.0_x64-setup.exe

### 커밋
- 431d870 fix: Rust recursion_limit 증가
- 654cdc2 fix: MR 백테스트 custom 프리셋 파라미터 적용 안되는 버그 수정
- e4aa7d0 feat: 추세매매 백테스트에 MR 동일 구조 적용
- 594437f feat: 백테스트 캔들차트 추가 + KIS 마스터 캐시 개선
- 0a2a1d8 perf: 추세매매 백테스트 벡터화 최적화 (20~50배 속도 향상)
- 581373a fix: KIS_US 해외주식/ETF 검색 수정
- 3492b8b fix: US fallback 종목 대폭 확장 (SCHD, PLTR 등 200+ 종목)
- 7adec5b fix: 종목 자동완성 거래소별 필터링 (전 탭 동일 적용)
- 76f0314 fix: 백테스트 캔들 데이터 접근 TypeError 수정
- e194d63 fix: lightweight-charts v3.8.0 다운그레이드 + ES 모듈 통일
- 9faa8a0 docs: SSOT 캔들차트 검증 결과 추가
- 41f2c3b fix: 최소봉수 동적계산 + 캔들차트 방어코드 강화
- e881357 feat: 캔들차트 위치 변경(맨 위) + SMA 20/50/200일선 추가

### 캔들차트 위치 변경 + 이동평균선 (2026-02-13)
- **캔들차트 위치**: 5카드 위로 이동 (MR/Trend 공통)
- **이동평균선 추가**:
  - 20일선: 노란색 (#FBBF24)
  - 50일선: 주황색 (#F97316)
  - 200일선: 파란색 (#3B82F6)
- **calcSMA 함수 구현**: 봉수 체크 후 라인 추가
- **24개 교차 테스트 전부 통과**:
  - MR 8건 + Trend 10건 + 추가 6건

### 최소봉수 동적계산 + 백테스트 안정화 (최종)
**문제**: 300봉 하드코딩 → KIS 365일 백테스트 실패
**수정**:
- MR: preset1=300봉, preset2=250봉, custom=150봉 (동적)
- Trend: max(HVI+50, VWMA+20, SPO+30, 피라미딩+20, ST*3, 100)

**15개 자체 테스트 전부 통과**:
| # | 전략 | 거래소 | 종목 | TF | 기간 | 거래수 | 상태 |
|---|------|--------|------|-----|------|--------|------|
| 1 | MR | OKX | BTC | 1h | 365일 | 83 | OK |
| 2 | MR | BINANCE | BTC | 1h | 365일 | 84 | OK |
| 3 | MR | KIS_KR | 삼성 | 1D | 365일 | 1 | OK |
| 4 | MR | KIS_KR | 삼성 | 1D | 730일 | 6 | OK |
| 5 | MR | KIS_US | AAPL | 1D | 365일 | 0 | OK |
| 6 | MR | KIS_US | AAPL | 1D | 730일 | 3 | OK |
| 7 | Trend | OKX | BTC | 1D | 365일 | 0 | OK |
| 8 | Trend | OKX | BTC | 1D | 730일 | 3 | OK |
| 9 | Trend | BINANCE | BTC | 1D | 730일 | 3 | OK |
| 10 | Trend | KIS_KR | 삼성 | 1D | 365일 | 6 | OK |
| 11 | Trend | KIS_KR | 삼성 | 1D | 730일 | 21 | OK |
| 12 | Trend | KIS_KR | 삼성 | 1D | 1000일 | 63 | OK |
| 13 | Trend | KIS_US | AAPL | 1D | 365일 | 2 | OK |
| 14 | Trend | KIS_US | AAPL | 1D | 730일 | 5 | OK |
| 15 | Trend | KIS_US | AAPL | 1D | 1000일 | 27 | OK |

**캔들차트 방어코드 강화**:
- try-catch 에러 처리 추가
- Array.isArray 타입 체크 추가
- trades 빈배열 초기화

### 캔들차트 구현 검증 완료 (최종)
- **lightweight-charts v3.8.0**: `addCandlestickSeries` API 호환 확인
- **ES 모듈 통일**: `import { createChart, ColorType, CrosshairMode }`
- **백엔드 candles 데이터**: MR/Trend 모두 정상 반환
  - 형식: `{time, open, high, low, close, volume}`
  - Candle 객체 접근: `c.ts, c.o, c.h, c.l, c.c, c.v`
- **프론트 함수 검증**:
  - `createBacktestCandleChart()`: null/빈배열 방어 코드 있음
  - `displayMrBacktestResult()` line 8008, `displayTrendBacktestResult()` line 8536 호출
  - HTML 컨테이너: `mr-candle-chart`, `trend-candle-chart` 존재
- **종목 필터링**: 4개 탭 전부 `setExchange()` 연결 확인

### 빌드 및 배포 완료
- **PC앱 빌드**: `BBooster_1.0.0_x64-setup.exe`
  - 원본: `C:\Users\pc\새 폴더\AUAT\pc-app\src-tauri\target\release\bundle\nsis\`
  - 복사: `C:\AUAT\pc-app\src-tauri\target\release\bundle\nsis\`
- **VPS 배포**: `docker compose up -d --build` 완료
  - 상태: `Uvicorn running on http://0.0.0.0:8000`

### 종목 자동완성 거래소 필터링 (4개 탭 전부 적용)
- **문제**: KIS_US 선택 후 "ko" 검색 → 국내 KODEX ETF 나옴
- **원인**: exchange 파라미터가 자동완성에 전달 안 됨
- **수정**:
  - createSymbolAutocomplete에 setExchange() 메서드 추가
  - TV Connect: Step 2 진입 시 selectedExchange.exchange로 필터
  - 커스텀/역추세/추세: 거래소 드롭다운 change 이벤트 연동
- **필터링 규칙**:
  - OKX/BINANCE/BYBIT/UPBIT → 해당 거래소 코인만
  - KIS_KR → KOSPI/KOSDAQ만
  - KIS_US → NYSE/NASDAQ/AMEX만

### 백테스트 TypeError 수정
- **문제**: MR/Trend 백테스트 실행 시 TypeError 발생
- **원인**: Candle 객체를 dict처럼 접근 (`c["timestamp"]`)
- **수정**: `c.ts`, `c.o`, `c.h`, `c.l`, `c.c`, `c.v`로 변경

### 6개 거래소 API 점검 결과
| 거래소 | 심볼검색 | Trend 730일 | MR 365일 |
|--------|---------|-------------|----------|
| OKX | ✅ | ✅ 3거래 | ✅ 83거래 (1h) |
| BINANCE | ✅ | ✅ 3거래 | ✅ 354거래 (30m) |
| BYBIT | ✅ | ✅ 3거래 | ✅ 360거래 (30m) |
| UPBIT | ✅ | ✅ 0거래 | ✅ 59거래 (1h) |
| KIS_KR | ✅ | ✅ 44거래 | ✅ 6거래 (1D) |
| KIS_US | ✅ | ✅ 5거래 | ✅ 3거래 (1D) |

- OKX/UPBIT 30분봉 730일(35,040봉) → API 타임아웃 (네트워크 제한)
- KIS는 일봉/주봉/월봉만 지원 (분봉 미지원)

### KIS_US 해외주식/ETF 검색 수정
- 해외 마스터 파싱 개선 (탭 구분자 처리)
- US fallback 항상 병합 (_get_us_fallback_stocks)
- **대폭 확장: 200+ 미국 주식/ETF**
  - 기술주: AAPL, MSFT, GOOGL, PLTR, SNOW, NET, CRWD, ARM, SMCI
  - 배당 ETF: SCHD, VYM, JEPI, JEPQ, QYLD, XYLD, RYLD
  - 레버리지 ETF: TQQQ, SQQQ, SOXL, SOXS, FNGU, FNGD, LABU, LABD
  - 섹터/테마 ETF: XLK, XLF, XLE, XLV, ARKK, BOTZ, KWEB, VNQ

### 추세매매 벡터화 최적화
- 기존: 매 봉마다 지표 재계산 → O(N × lookback × 지표수) = 15~30초
- 변경: 사전 계산 후 인덱스 조회 → O(N) = 0.5~1초
- 대상 지표: Supertrend, HVI, QQE, VWMA, SPO, ATR
- 테스트: 33 passed in 1.34s

### 내일 이어서 할 것
- PC앱 빌드 및 캔들차트/속도 테스트
- Phase 3 커스텀전략 시작

## Day 16 완료사항 (2026-02-11)
- 백테스트 트레이딩뷰 동일화:
  - 상단 5카드 (총손익/최대자본감소/총거래횟수/수익성거래/수익지수)
  - 수익률 테이블 3열 (전체/매수/매도)
  - 차트 Y축 수익률(%), 0% 기준선
  - 거래내역 수익금+수익률 컬럼
  - 수수료 0.1% 포함, 미실현 손익 계산
- 화폐단위 개편:
  - getMrCurrency(): exchange+symbol 기반 결정 (USDT/USDC/KRW/USD)
  - formatMrAmount(): 만원/억 축약 제거, 원본 금액 표시
  - 차트 툴팁 만원/억 완전 제거
- 수익지수 ∞ 처리 (profit_factor >= 999)
- 거래소 한글화:
  - 드롭다운: 바이낸스/바이비트/업비트/한투증권(국내)/한투증권(해외)
  - index.html에 KIS_KR/KIS_US 옵션 추가
- 테스트: pytest 285 passed
- PC앱 빌드: BBooster_1.0.0_x64-setup.exe

## 남은 버그/미완성
| # | 문제 | 상태 |
|---|------|------|
| 1 | KIS_KR 캔들 조회 | ✅ 완료 |
| 2 | KIS_US 캔들 조회 | ✅ 완료 |
| 3 | OKX VPS IP 429 차단 | ⚠️ |
| 4 | 샤프지수 미표시 | ❌ |

## Phase 1 로드맵 (역추세매매 완성)
- P0: 백테스트 UI 마무리 (1일) - 대부분 완료
- P1: 전 거래소 캔들 + 백테스트 (2~3일)
- P2: 모의거래 테스트 (2일)
- P3: 완성 선언 (0.5일)

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
341 passed (MR 216개 + Trend 70개 + 파인비교/무결성 55개)
```

## Day 15: 백테스트 벡터화 최적화 (2026-02-10)

### 문제
- 백테스트 시그널 계산이 너무 느림 (2000봉 이상에서 20초+)
- 매 봉마다 지표 재계산 (for 루프 O(n²) 복잡도)
- 타임아웃 발생 (1h 365일 = 8760봉)

### 해결: 벡터화 사전 계산

**backtest_engine.py 추가 함수**:
```python
def precompute_spo_arrays(closes, preset) -> Dict[str, np.ndarray]
    # 전체 시리즈에서 SPO 지표 한 번만 계산
    # normalized_osc, upper_band, lower_band, basis, line_short, line_long

def precompute_signal_arrays(normalized_osc, threshold) -> Dict[str, np.ndarray]
    # sig_up_raw, sig_dn_raw 배열 사전 계산 (벡터화)

def precompute_htf_arrays(htf_closes, htf_highs, htf_lows, htf_volumes) -> Dict[str, np.ndarray]
    # VWMA50, VWMA200, HMA, Supertrend, Ichimoku 한 번에 계산

def get_htf_indicators_at_index(htf_arrays, idx) -> HTFIndicators
    # 사전 계산된 배열에서 인덱스로 HTFIndicators 추출

def get_osc_data_at_index(spo_arrays, sig_arrays, closes, idx) -> OscillatorData
    # 사전 계산된 배열에서 인덱스로 OscillatorData 추출
```

**indicators.py 벡터화 최적화**:
| 함수 | 기존 | 최적화 |
|------|------|--------|
| calc_wma | for 루프 | np.convolve |
| calc_stdev | for 루프 + np.std | cumsum 기반 (E[X²]-E[X]²) |
| calc_highest | for 루프 | sliding_window_view + np.max |
| calc_lowest | for 루프 | sliding_window_view + np.min |
| calc_vwma | for 루프 | cumsum 기반 rolling sum |
| calc_atr | for 루프 (TR) | 벡터화 True Range 계산 |

### 성능 결과
| 타임프레임 | 봉 수 | 최적화 전 | 최적화 후 | 목표 | 개선율 |
|-----------|------|----------|----------|------|--------|
| 4h 365일 | 2,190 | 20.6초 | **0.07초** | <5초 ✓ | 294x |
| 1h 365일 | 8,760 | ~80초 | **0.30초** | <10초 ✓ | 267x |

### 알고리즘 복잡도
- **기존**: O(n × lookback × indicator_cost) ≈ O(n²)
- **최적화**: O(n × indicator_cost) ≈ O(n)

### 커밋
- `cc68791` perf: 백테스트 시그널 계산 벡터화 최적화 (20초→0.3초)

### PC앱 빌드
- MSI: `pc-app\src-tauri\target\release\bundle\msi\BBooster_1.0.0_x64_en-US.msi`
- NSIS: `pc-app\src-tauri\target\release\bundle\nsis\BBooster_1.0.0_x64-setup.exe`

---

## Day 8 Fixes
- 종목명 쓰레기 데이터 제거 (`_clean_stock_name`)
- 섹터 데이터 수정 (업종 지수 기반)
- itsdangerous==2.1.2 추가

## Scope Exclusions
- SMC strategy/files, MFT candle, Futures

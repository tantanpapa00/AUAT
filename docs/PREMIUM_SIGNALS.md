# PREMIUM_SIGNALS.md (SSOT)
- Last updated: 2026-02-04 KST
- Owner: 기훈(작가님)
- Status: Week 14 Day 1

> NOTE: 이 파일은 Premium 신호 정의의 '진실(SSOT)'입니다.
> 상세 로직은 scripts/ 폴더가 정본이며, 이 문서는 요약/매핑 문서입니다.

---

# 1) 정본 소스 위치

| 전략 | 정본 파일 | 비고 |
|------|-----------|------|
| 추세매매 (Trend) | `scripts/추세매매.txt` | 주식 전용 |
| 역추세매매 (Mean-Reversion) | `scripts/역추세매매 현물 v0.4.txt` | 현물 (암호화폐) |
| 커스텀 (Custom) | (없음 - 사용자 정의) | AST 기반 규칙 |

> **원칙**: scripts 로직 변경은 별도 이슈로 분리. docs는 매핑/설명/계약만 수정.

---

# 2) Premium 전략 타입

| 타입 | 코드 | 설명 |
|------|------|------|
| 추세매매 | `trend` | 추세 방향 확인 후 진입, 추세 전환 시 청산 |
| 역추세매매 | `mr` | 과매도/과매수 구간에서 평균 회귀 기대 |
| 커스텀 | `custom` | 사용자 정의 규칙 (AST 기반) |

---

# 3) 추세매매 (Trend) 신호 정의

## 3-1) 정본 소스
`scripts/추세매매.txt` (Stock Trend Auto v7)

## 3-2) Entry 조건 요약

```
BUY = Supertrend 상승 AND HVI 초록 AND QQE 양수 AND close > HTF VWMA156
```

| 조건 | 지표 | 설명 |
|------|------|------|
| S | Supertrend | direction < 0 (상승추세, 초록) |
| H | HVI (LazyBear) | g_enabled = true (초록 히스토그램) |
| Q | QQE MOD | primaryRSI > 50 (또는 선택 옵션) |
| W | HTF VWMA156 | close > 주봉 VWMA(156) |

## 3-3) Exit 조건 요약

| 우선순위 | 조건 | 설명 |
|----------|------|------|
| 1 | Hard SL | -X% 전량 손절 (기본: -7%) |
| 2 | TP1 | +X% 도달 시 Y% 우선 매도 (기본: +21% → 50% 매도) |
| 3 | SPO Split | SPO signal_dn 발생 시 분할 매도 (SELL1~6) |
| 4 | ST Flip | Supertrend 하락 전환 시 전량 청산 |

## 3-4) reason_code (Trend)

| 코드 | 의미 | 발생 시점 |
|------|------|-----------|
| `TREND_ENTRY_FULL` | 4가지 조건 모두 충족 진입 | Entry |
| `TREND_EXIT_HARD_SL` | 하드 손절 (-X%) | Exit |
| `TREND_EXIT_TP1` | 목표 수익 도달 분할 청산 | Exit |
| `TREND_EXIT_SPO_SPLIT` | SPO 신호 분할 매도 | Exit |
| `TREND_EXIT_ST_FLIP` | Supertrend 하락 전환 전량 청산 | Exit |

---

# 4) 역추세매매 (Mean-Reversion) 신호 정의

## 4-1) 정본 소스
`scripts/역추세매매 현물 v0.4.txt` (역추세매매 현물 v0.3)

## 4-2) 핵심 지표: Smooth Price Oscillator (SPO)

```python
# SPO 신호
signal_up = normalized_osc < -threshold AND crossover(normalized_osc, normalized_osc[1])
signal_dn = normalized_osc > threshold AND crossover(normalized_osc[1], normalized_osc)
```

## 4-3) 4국면 엔진 (HTF 기반)

| 국면 | 조건 | 매수 정책 | 매도 정책 |
|------|------|-----------|-----------|
| R1 | 정배열 + ST상승 | 눌림 1회 트리거 | 확대 (1.3x) |
| R2 | 정배열 + ST하락 | 금지/극소 (0x) | 확대 (1.6x) |
| R3 | 역배열 + ST상승 | 돌파 1회 트리거 | 일반 (1.3x) |
| R4 | 역배열 + ST하락 | 확대 (1.2x) | 축소 (0.7x) |

- 정배열: HTF VWMA50 >= VWMA200
- 역배열: HTF VWMA50 < VWMA200
- ST상승/하락: HTF Supertrend 방향

## 4-4) Entry 조건 요약

```
BUY = (OSC 신호 AND 하단밴드 조건) OR 눌림 트리거(R1) OR 돌파 트리거(R3)
```

| 국면 | OSC 매수 | 특수 트리거 |
|------|----------|-------------|
| R1 | 허용 | 눌림 1회 (HULL 하락 구간) |
| R2 | 금지 | 없음 |
| R3 | 허용 | 돌파 1회 (선행스팬B 상향돌파) |
| R4 | 허용 | 없음 |

필터:
- 하단 밴드 근처/이하
- 평단가 이하 (국면별 옵션)
- 직전 신호가/체결가보다 낮음 (국면별 옵션)

## 4-5) Exit 조건 요약

```
SELL = OSC signal_dn AND 최소 익절 게이트 충족 AND 분할 비중 > 0
```

| 조건 | 설명 |
|------|------|
| signal_dn | OSC 상단 밴드에서 하락 전환 |
| 익절 게이트 | close >= avg_price * (1 + min_profit_pct + fee_buffer) |
| 분할 매도 | SELL1~6 비중 순차 적용 |
| 교대 매도 | R2에서 기본 활성화 (Alternate 모드) |

## 4-6) reason_code (Mean-Reversion)

| 코드 | 의미 | 발생 시점 |
|------|------|-----------|
| `MR_ENTRY_OSC` | OSC 하단밴드 신호 진입 | Entry |
| `MR_ENTRY_R1_PULLBACK` | R1 눌림 트리거 진입 | Entry |
| `MR_ENTRY_R3_BREAKOUT` | R3 돌파 트리거 진입 | Entry |
| `MR_EXIT_OSC_SPLIT` | OSC 상단밴드 분할 청산 | Exit |
| `MR_EXIT_PROFIT_GATE` | 익절 게이트 미충족 (스킵) | Skip |
| `MR_BLOCKED_R2` | R2 국면 매수 금지 | Block |

---

# 5) 커스텀 (Custom) 신호 정의

## 5-1) 지원 인디케이터 (v1 제한)

| 인디케이터 | 파라미터 | 비고 |
|------------|----------|------|
| MA | period, type(SMA/EMA/WMA) | 이동평균 |
| BollingerBands | period, std_mult | 볼린저밴드 |
| RSI | period | 상대강도지수 |
| MACD | fast, slow, signal | MACD |
| CCI | period | 상품채널지수 |
| Ichimoku | tenkan, kijun, senkou | 일목균형표 |

## 5-2) 복잡도 제한 (v1 고정)

| 항목 | 제한값 | 설명 |
|------|--------|------|
| max_depth | 3 | 최대 중첩 깊이 |
| max_leaf_total | 12 | 전체 조건 노드 수 |
| max_leaf_per_group | 6 | 그룹당 조건 수 |
| max_or_groups | 2 | OR 그룹 수 |
| max_leaf_per_or_group | 4 | OR 그룹당 조건 수 |

> **원칙**: 같은 레벨에서 AND/OR 혼합 금지. 초과 시 `rule_complexity_exceeded` 오류.

## 5-3) Rule Lint 등급

| 등급 | 의미 | 처리 |
|------|------|------|
| OK | 정상 | 저장/실행 허용 |
| WARN | 희소/상충 가능성 | 저장 허용 + 강한 경고 UI |
| BLOCK | 거의 불가능/위험 | 저장 불가 (premium 우회 토글 옵션) |

WARN/BLOCK 예시:
- `BB_UPPER_BREAK AND RSI<30` → 희소/상충 (WARN)
- `RSI>90 AND RSI<10` → 모순 (BLOCK)

## 5-4) Exit 옵션 (v1)

| 옵션 | 설명 |
|------|------|
| 신호청산 | Exit 규칙 신호 발생 시 청산 |
| %TP/SL | 목표 수익률/손절률 도달 시 청산 |
| Trailing% | 고점 대비 X% 하락 시 청산 |

우선순위: 리스크(손절/강제) > 익절 > 신호청산

## 5-5) reason_code (Custom)

| 코드 | 의미 | 발생 시점 |
|------|------|-----------|
| `CUSTOM_ENTRY_RULE` | 커스텀 Entry 규칙 충족 | Entry |
| `CUSTOM_EXIT_RULE` | 커스텀 Exit 규칙 충족 | Exit |
| `CUSTOM_EXIT_TP` | 목표 수익률 도달 | Exit |
| `CUSTOM_EXIT_SL` | 손절률 도달 | Exit |
| `CUSTOM_EXIT_TRAIL` | Trailing 조건 충족 | Exit |
| `CUSTOM_LINT_WARN` | Rule Lint 경고 | Warning |
| `CUSTOM_LINT_BLOCK` | Rule Lint 차단 | Block |

---

# 6) 공통 reason_code

| 코드 | 의미 | 사용 위치 |
|------|------|-----------|
| `SIGNAL_CREATED` | 신호 이벤트 생성됨 | signal_event |
| `SIGNAL_EXECUTED` | 신호 기반 주문 실행됨 | order_event |
| `SIGNAL_SKIPPED` | 신호 스킵됨 (가드/필터) | skip_event |
| `COOLDOWN_ACTIVE` | 쿨다운 중 (과다 신호 방지) | skip_event |
| `DAILY_LIMIT` | 일일 신호 제한 도달 | skip_event |
| `TF_WARNING` | 단기봉 경고 (TF < 15m) | warning |
| `PREMIUM_OFF` | Premium 비활성화 | block |

---

# 7) reason_text 템플릿

## 7-1) Trend

```
# Entry
"추세매매 진입: ST상승+HVI초록+QQE양수+HTF VWMA 상위"

# Exit
"하드손절 발동: -{stop_pct}% 도달"
"목표익절(TP1): +{tp_pct}% 도달, {sell_pct}% 청산"
"SPO 분할매도: SELL{stage} 실행 ({pct}%)"
"추세전환 전량청산: Supertrend 하락"
```

## 7-2) Mean-Reversion

```
# Entry
"역추세 진입: OSC 하단밴드 신호 (R{regime})"
"눌림 매수: R1 HULL 하락구간 1회 트리거"
"돌파 매수: R3 선행스팬B 상향돌파 1회 트리거"

# Exit
"역추세 분할청산: OSC 상단 SELL{stage} ({pct}%)"
"익절게이트 미충족: 최소익절 {min_pct}% 필요"
```

## 7-3) Custom

```
# Entry
"커스텀 진입: {rule_name} 조건 충족"

# Exit
"커스텀 청산: {rule_name} Exit 조건"
"목표익절: +{tp_pct}% 도달"
"손절: -{sl_pct}% 도달"
"Trailing: 고점 대비 -{trail_pct}% 하락"

# Warning
"Rule Lint 경고: {lint_message}"
```

---

# 8) TF(타임프레임) 정책

## 8-1) 권장 타임프레임

| TF | 권장 | 비고 |
|----|------|------|
| 1m, 3m, 5m | 비권장 | 슬리피지/체결괴리 경고 필수 |
| 15m | 권장 | 최소 권장 TF |
| 1h, 4h | 권장 | 안정적 |
| 1D, 1W | 권장 | 장기 전략 |

## 8-2) 단기봉 경고 (TF < 15m)

```
경고 메시지:
"1~5분봉은 슬리피지, 체결괴리, 수수료 손실 위험이 높습니다.
15분봉 이상 사용을 권장합니다."
```

처리:
- 기본: 경고 배너 표시 (거래 허용)
- 옵션: 차단 모드 (premium 설정에서 선택)

---

# 9) snapshot_id 규격

## 9-1) 포맷

```
snap_{asset_id}_{timestamp}_{hash8}
```

예시: `snap_3_1707012345_a1b2c3d4`

## 9-2) 스냅샷 내용 (최소)

```json
{
  "snapshot_id": "snap_3_1707012345_a1b2c3d4",
  "ts": 1707012345000,
  "tf": "1h",
  "asset_id": 3,
  "symbol": "BTC-USDT",
  "exchange": "OKX",
  "premium_mode": "mr",
  "ohlcv": {
    "o": 42000.0,
    "h": 42500.0,
    "l": 41800.0,
    "c": 42200.0,
    "v": 1234.56
  },
  "indicators": {
    "spo_normalized": -1.2,
    "regime": 4,
    "vwma50": 41500.0,
    "vwma200": 40000.0
  },
  "reason_code": "MR_ENTRY_OSC"
}
```

---

# 10) 금지 사항 (재확인)

1. **종목추천/자동선정/스크리닝 금지**: Premium은 신호 생성만 담당
2. **내부 로직 노출 금지**: 불펌 방지 (scripts 폴더는 비공개)
3. **선물/레버리지 미지원**: Spot만 지원
4. **역할 중복 금지**: Premium은 신호만, Hub는 실행/가드/기록만

---

# 11) 참조

- scripts/추세매매.txt (정본)
- scripts/역추세매매 현물 v0.4.txt (정본)
- docs/PROJECT_STATUS.md (일정)
- docs/TIMELINE_SPEC.md (이벤트 스키마)

---

[END OF PREMIUM_SIGNALS]

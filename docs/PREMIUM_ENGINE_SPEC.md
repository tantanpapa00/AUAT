# PREMIUM_ENGINE_SPEC.md (SSOT)
- Last updated: 2026-02-04 KST
- Owner: 기훈(작가님)
- Status: Week 14 Day 2

> NOTE: 이 파일은 Premium 엔진의 입출력 계약(SSOT)입니다.
> 신호 정의는 docs/PREMIUM_SIGNALS.md 참조.

---

# 1) 역할 분리 원칙

## 1-1) Premium 엔진 역할 (신호 생성만)

| 허용 | 금지 |
|------|------|
| 지표 계산 | 주문 실행 |
| 신호 이벤트 생성 | 잔고 조회/변경 |
| reason/snapshot 생성 | 계좌 접근 |
| TF/가드 정책 적용 | 거래소 API 호출 |

## 1-2) Hub 역할 (실행/가드/기록만)

| 허용 | 금지 |
|------|------|
| 주문 실행 (connector) | 신호 판단 |
| 잔고 조회/검증 | 지표 계산 |
| 이벤트 저장 (DB) | 종목 추천/선정 |
| E-STOP/가드 적용 | 전략 로직 실행 |

> **원칙**: 역할 중복 금지. Premium이 생성한 signal_event를 Hub가 실행.

---

# 2) signal_event 스키마 (출력)

## 2-1) 필수 필드

```python
class SignalEvent(BaseModel):
    """Premium 엔진 출력: 신호 이벤트"""

    # 식별
    signal_id: str              # 고유 ID (예: "sig_3_1707012345_abc123")
    asset_id: int               # 자산 ID
    symbol: str                 # 심볼 (예: "BTC-USDT")
    exchange: str               # 거래소 (OKX/BINANCE/BYBIT/UPBIT/KIS)
    market: Literal["spot"]     # 마켓 (spot만 지원)

    # 신호 내용
    side: Literal["entry", "exit"]  # 진입/청산
    action: Literal["buy", "sell"]  # 매수/매도

    # Premium 설정
    premium_mode: Literal["trend", "mr", "custom"]  # 전략 타입
    params_version: str         # 파라미터 버전 (예: "v1.0")

    # 근거 (audit trail)
    reason_code: str            # 표준 코드 (예: "MR_ENTRY_OSC")
    reason_text: str            # 설명 (예: "역추세 진입: OSC 하단밴드 신호")
    snapshot_id: str            # 스냅샷 참조 ID

    # 타임프레임
    tf: str                     # 타임프레임 (예: "1h", "15m")
    tf_warning: Optional[bool] = None  # TF < 15m 경고 여부

    # 가격 힌트 (선택)
    price_hint: Optional[float] = None  # 신호 발생 시점 가격

    # 메타
    ts: int                     # 신호 생성 타임스탬프 (ms)
    created_at: datetime        # 생성 시각
```

## 2-2) 선택 필드 (확장)

```python
class SignalEventExtended(SignalEvent):
    """확장 필드 (커스텀/분할용)"""

    # 분할 매매
    tranche: Optional[int] = None       # 차수 (1, 2, 3...)
    tranche_pct: Optional[float] = None # 비중 (%)

    # 커스텀 규칙
    rule_id: Optional[str] = None       # 커스텀 규칙 ID
    rule_name: Optional[str] = None     # 커스텀 규칙 이름
    lint_grade: Optional[str] = None    # Lint 등급 (OK/WARN/BLOCK)

    # Exit 조건 (커스텀)
    exit_type: Optional[str] = None     # "signal", "tp", "sl", "trail"
    exit_pct: Optional[float] = None    # TP/SL/Trail 퍼센트

    # 국면 (MR)
    regime: Optional[int] = None        # 1, 2, 3, 4
    regime_name: Optional[str] = None   # "R1", "R2", "R3", "R4"
```

---

# 3) Premium 입력 스키마

## 3-1) 기본 입력

```python
class PremiumInput(BaseModel):
    """Premium 엔진 입력"""

    # 대상
    asset_id: int               # 자산 ID
    symbol: str                 # 심볼
    exchange: str               # 거래소

    # 모드
    premium_mode: Literal["trend", "mr", "custom"]
    params_version: str = "v1.0"

    # 타임프레임
    tf: str                     # "1m", "5m", "15m", "1h", "4h", "1D"

    # OHLCV 데이터 (필수)
    ohlcv: List[OHLCVBar]       # 최근 N개 봉

    # 커스텀 규칙 (custom 모드만)
    custom_rule: Optional[CustomRuleAST] = None
```

## 3-2) OHLCV 바

```python
class OHLCVBar(BaseModel):
    """OHLCV 단일 봉"""
    ts: int                     # 타임스탬프 (ms)
    o: float                    # Open
    h: float                    # High
    l: float                    # Low
    c: float                    # Close
    v: float                    # Volume
```

## 3-3) 커스텀 규칙 AST

```python
class CustomRuleAST(BaseModel):
    """커스텀 규칙 AST (JSON 트리)"""
    rule_id: str
    rule_name: str
    version: str = "1.0"

    entry: ConditionGroup       # Entry 조건
    exit: ConditionGroup        # Exit 조건

    # Exit 옵션
    exit_options: ExitOptions

    # 메타
    created_at: datetime
    lint_grade: str = "OK"      # OK/WARN/BLOCK
```

---

# 4) Snapshot 스키마

## 4-1) 스냅샷 모델

```python
class SignalSnapshot(BaseModel):
    """신호 근거 스냅샷"""

    # 식별
    snapshot_id: str            # 예: "snap_3_1707012345_a1b2c3d4"
    signal_id: str              # 연관 신호 ID

    # 대상
    asset_id: int
    symbol: str
    exchange: str

    # 시점
    ts: int                     # 스냅샷 시점 (ms)
    tf: str                     # 타임프레임

    # OHLCV (현재 봉)
    ohlcv: OHLCVBar

    # 지표 값 (모드별)
    indicators: Dict[str, Any]

    # Premium 설정
    premium_mode: str
    params_version: str

    # 근거
    reason_code: str
    reason_text: str

    # 메타
    created_at: datetime
```

## 4-2) indicators 예시

```json
// Trend
{
  "supertrend_dir": -1,
  "hvi_green": true,
  "qqe_positive": true,
  "htf_vwma156": 42000.0,
  "close_above_vwma": true
}

// Mean-Reversion
{
  "spo_normalized": -1.2,
  "lower_band": -1.5,
  "upper_band": 1.5,
  "regime": 4,
  "vwma50": 41500.0,
  "vwma200": 40000.0,
  "st_dir": -1
}

// Custom
{
  "rsi_14": 28.5,
  "bb_lower": 41000.0,
  "bb_upper": 43000.0,
  "macd_hist": -50.0,
  "rule_conditions_met": ["rsi<30", "close<bb_lower"]
}
```

---

# 5) DB 스키마 확장

## 5-1) signal_events 테이블

```sql
CREATE TABLE IF NOT EXISTS signal_events (
    id              BIGSERIAL PRIMARY KEY,
    signal_id       TEXT NOT NULL UNIQUE,
    asset_id        BIGINT REFERENCES assets(id),
    symbol          TEXT NOT NULL,
    exchange        TEXT NOT NULL,
    market          TEXT NOT NULL DEFAULT 'spot',

    side            TEXT NOT NULL,          -- entry/exit
    action          TEXT NOT NULL,          -- buy/sell

    premium_mode    TEXT NOT NULL,          -- trend/mr/custom
    params_version  TEXT NOT NULL,

    reason_code     TEXT NOT NULL,
    reason_text     TEXT,
    snapshot_id     TEXT,

    tf              TEXT NOT NULL,
    tf_warning      BOOLEAN DEFAULT FALSE,
    price_hint      FLOAT,

    -- 확장 필드
    tranche         INT,
    tranche_pct     FLOAT,
    rule_id         TEXT,
    regime          INT,

    ts              BIGINT NOT NULL,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_signal_events_asset ON signal_events(asset_id);
CREATE INDEX idx_signal_events_ts ON signal_events(ts);
CREATE INDEX idx_signal_events_mode ON signal_events(premium_mode);
```

## 5-2) signal_snapshots 테이블

```sql
CREATE TABLE IF NOT EXISTS signal_snapshots (
    id              BIGSERIAL PRIMARY KEY,
    snapshot_id     TEXT NOT NULL UNIQUE,
    signal_id       TEXT REFERENCES signal_events(signal_id),

    asset_id        BIGINT,
    symbol          TEXT NOT NULL,
    exchange        TEXT NOT NULL,

    ts              BIGINT NOT NULL,
    tf              TEXT NOT NULL,

    ohlcv           JSONB NOT NULL,         -- {o, h, l, c, v}
    indicators      JSONB NOT NULL,         -- 지표 값

    premium_mode    TEXT NOT NULL,
    params_version  TEXT NOT NULL,
    reason_code     TEXT NOT NULL,
    reason_text     TEXT,

    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_signal_snapshots_signal ON signal_snapshots(signal_id);
CREATE INDEX idx_signal_snapshots_ts ON signal_snapshots(ts);
```

---

# 6) API 엔드포인트

## 6-1) 신호 조회

```
GET /api/premium/signals
  ?asset_id={id}
  &premium_mode={trend|mr|custom}
  &side={entry|exit}
  &from_ts={timestamp}
  &to_ts={timestamp}
  &limit={n}
```

Response:
```json
{
  "ok": true,
  "signals": [
    {
      "signal_id": "sig_3_1707012345_abc123",
      "asset_id": 3,
      "symbol": "BTC-USDT",
      "exchange": "OKX",
      "side": "entry",
      "action": "buy",
      "premium_mode": "mr",
      "reason_code": "MR_ENTRY_OSC",
      "reason_text": "역추세 진입: OSC 하단밴드 신호 (R4)",
      "snapshot_id": "snap_3_1707012345_a1b2c3d4",
      "tf": "1h",
      "ts": 1707012345000,
      "created_at": "2026-02-04T12:00:00+09:00"
    }
  ],
  "total": 1
}
```

## 6-2) 스냅샷 조회

```
GET /api/premium/snapshots/{snapshot_id}
```

Response:
```json
{
  "ok": true,
  "snapshot": {
    "snapshot_id": "snap_3_1707012345_a1b2c3d4",
    "signal_id": "sig_3_1707012345_abc123",
    "asset_id": 3,
    "symbol": "BTC-USDT",
    "tf": "1h",
    "ohlcv": {"o": 42000, "h": 42500, "l": 41800, "c": 42200, "v": 1234.56},
    "indicators": {
      "spo_normalized": -1.2,
      "regime": 4,
      "vwma50": 41500.0,
      "vwma200": 40000.0
    },
    "reason_code": "MR_ENTRY_OSC",
    "reason_text": "역추세 진입: OSC 하단밴드 신호 (R4)"
  }
}
```

## 6-3) Premium 상태

```
GET /api/premium/status
```

Response:
```json
{
  "ok": true,
  "premium_enabled": true,
  "available_modes": ["trend", "mr", "custom"],
  "active_assets": [
    {"asset_id": 3, "symbol": "BTC-USDT", "premium_mode": "mr"}
  ],
  "signals_today": 5,
  "daily_limit": 100
}
```

---

# 7) Premium 활성화/비활성화

## 7-1) 환경변수

```bash
# Premium 전역 ON/OFF
PREMIUM_ENABLED=1           # 0=OFF, 1=ON

# 모드별 활성화
PREMIUM_TREND_ENABLED=1
PREMIUM_MR_ENABLED=1
PREMIUM_CUSTOM_ENABLED=0    # 커스텀은 별도 활성화

# 가드
PREMIUM_DAILY_LIMIT=100     # 일일 신호 제한
PREMIUM_COOLDOWN_SEC=60     # 신호 간 최소 간격 (초)
PREMIUM_TF_BLOCK_UNDER=0    # 0=경고만, 1=15m 미만 차단
```

## 7-2) 자산별 설정

```sql
-- assets 테이블 확장
ALTER TABLE assets ADD COLUMN premium_mode TEXT DEFAULT NULL;
ALTER TABLE assets ADD COLUMN premium_params JSONB DEFAULT NULL;
ALTER TABLE assets ADD COLUMN premium_enabled BOOLEAN DEFAULT FALSE;
```

---

# 8) Hub 연동 계약

## 8-1) 신호 → 주문 변환

```python
def signal_to_order(signal: SignalEvent) -> Optional[OrderRequest]:
    """
    Premium 신호를 주문 요청으로 변환.
    Hub에서만 호출 가능.
    """
    # Premium OFF면 None
    if not is_premium_enabled():
        return None

    # 가드 체크
    if is_cooldown_active(signal.asset_id):
        log_event("COOLDOWN_ACTIVE", signal)
        return None

    if is_daily_limit_reached(signal.asset_id):
        log_event("DAILY_LIMIT", signal)
        return None

    # E-STOP 체크
    if is_estop_on():
        log_event("ESTOP_BLOCK", signal)
        return None

    # 주문 생성
    return OrderRequest(
        asset_id=signal.asset_id,
        symbol=signal.symbol,
        exchange=signal.exchange,
        side=signal.action,  # buy/sell
        order_type="market",
        # qty는 자산 설정에서 결정
        reason_code=signal.reason_code,
        reason_text=signal.reason_text,
        snapshot_id=signal.snapshot_id,
    )
```

## 8-2) 이벤트 저장 (타임라인 연동)

```python
def save_signal_event(signal: SignalEvent, db: Session):
    """
    신호 이벤트를 DB에 저장하고 타임라인에 추가.
    """
    # signal_events 테이블에 저장
    db_signal = SignalEventModel(**signal.dict())
    db.add(db_signal)

    # events 테이블에도 추가 (타임라인 표시용)
    timeline_event = Event(
        event_type="signal_created",
        asset_id=signal.asset_id,
        summary=f"[{signal.premium_mode.upper()}] {signal.side}: {signal.reason_code}",
        detail=signal.dict(),
        reason_code=signal.reason_code,
        reason_text=signal.reason_text,
        snapshot_id=signal.snapshot_id,
    )
    db.add(timeline_event)

    db.commit()
```

---

# 9) 에러 코드

| 코드 | HTTP | 의미 |
|------|------|------|
| `premium_disabled` | 403 | Premium 비활성화 |
| `invalid_mode` | 400 | 잘못된 premium_mode |
| `asset_not_found` | 404 | 자산 없음 |
| `insufficient_data` | 400 | OHLCV 데이터 부족 |
| `rule_complexity_exceeded` | 400 | 커스텀 규칙 복잡도 초과 |
| `rule_lint_block` | 400 | Rule Lint BLOCK |
| `cooldown_active` | 429 | 쿨다운 중 |
| `daily_limit_reached` | 429 | 일일 제한 도달 |
| `tf_blocked` | 400 | 타임프레임 차단 (TF < 15m) |

---

# 10) 참조

- docs/PREMIUM_SIGNALS.md (신호 정의)
- docs/TIMELINE_SPEC.md (이벤트 스키마)
- docs/PROJECT_STATUS.md (일정)
- app/models.py (DB 모델)

---

[END OF PREMIUM_ENGINE_SPEC]

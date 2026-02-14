# BBooster 마스터 로드맵 v3 — SSOT 통합본
> 작성일: 2026-02-09 | Owner: 기훈(작가님)
> 기반: FINISH_SSOT.md (Week A~D 완료) + PREMIUM_ENGINE_SPEC.md + PREMIUM_SIGNALS.md + PRODUCT_SPEC.md

---

# 0) 현재 상태 요약

## 완료된 것 (Week A~D + Day 6~15)
- ✅ 브랜드/사이트/PC앱 골격/Android APK 기반
- ✅ 거래소 커넥터 (OKX/Binance/Bybit/Upbit/KIS)
- ✅ Hub형 (/tv 웹훅 → 주문 실행) 동작
- ✅ 전략설정 v2 (Sizing/Risk/Limits JSONB)
- ✅ 대시보드 거래내역 + 활성전략 관리 (웹+PC)
- ✅ 시장분석/종목분석 기초 (네이버API, RS, 52주신고가, 밸류에이션)
- ✅ MR 프리미엄 엔진 Phase 1~6 (지표/시세/실행/스케줄러/API/UI/백테스트)
- ✅ Trend 프리미엄 엔진 (HVI/QQE/백테스트/API)
- ✅ 백테스트 벡터화 최적화 (20초→0.3초)
- ✅ 백테스트 캔들 DB 캐싱 (5.8배 속도 향상)
- ✅ 백테스트 UI 기본 (메트릭카드+자산추이차트+거래내역테이블)
- ✅ 토스페이먼츠 웹사이트 심사 준비 (사업자정보/이용약관/개인정보처리방침)

## 남은 큰 작업 10개 (아래 §1~§10)

---

# 1) 역추세매매(MR) 프리미엄 전략 — PC앱 + 모바일앱

## 1-A) 역추세매매 남은 작업 (우선순위순)

### P0: 백테스트 결과 = 트레이딩뷰 전략리포트
- 상단 카드 5개 (총손익/최대자본감소/총거래/수익성거래/수익지수)
- 수익률 테이블 (전체/매수/매도 3열)
- 차트 Y축 수익률(%), 거래별 막대
- 거래 내역에 수익금+수익률 둘 다 표시
- 수수료 0.1% 포함 계산
- 미실현 손익 (종료 시 보유 포지션 평가)

### P1: 전 거래소 일괄 적용
- 캔들 조회: OKX/Binance/Bybit 전부 동작 확인
- 캔들 프리로딩: 전 거래소 주요 종목 등록
- 백테스트: 전 거래소에서 동일 결과 구조
- KIS: 일봉 캔들 조회 구현 (국내/해외 주식)

### P2: 실제 모의 거래 테스트
- OKX 모의투자로 역추세 전략 DRY-RUN
- Binance/Bybit 테스트넷으로 테스트
- KIS 모의투자로 국내주식 테스트
- 설정값(분할매수/매도 비중, 4국면 파라미터)이 실제로 반영되는지 확인

### P3: PC앱 UI 마무리
- 백테스트 결과 화면 완성 (위 P0)
- 전략 설정 → 백테스트 → 결과 확인 → 라이브 전환 플로우

---

## 핵심 목표
파인스크립트 `역추세매매 현물 v0.4`를 **파이썬으로 1:1 재구현**하여
BBooster 서버에서 독립 실행. TradingView 의존 제거.

## 기존 SSOT 연결
- PREMIUM_ENGINE_SPEC.md: signal_event 스키마, 역할 분리 (Premium=신호, Hub=실행)
- PREMIUM_SIGNALS.md §4: MR 신호 정의, reason_code, 4국면 정책
- PRODUCT_SPEC.md 1-7: PC=본체 설정, 앱=간단 조정만

## 아키텍처 (PREMIUM_ENGINE_SPEC 준수)

```
Strategy Engine (Python) ← 신호 생성만 (주문 실행 금지)
├── candle_fetcher.py      — 거래소 OHLCV → candles 테이블
├── indicators.py          — SPO, VWMA, HULL, 일목, Supertrend (내장)
├── regime_detector.py     — 4국면 판별 (HTF 지표 기반)
├── signal_generator.py    — 매수/매도 신호 + 필터 → signal_event 출력
├── presets.py             — 오실레이터/HTF 프리셋 상수
└── models.py              — Candle, Signal 데이터클래스

Hub (기존) ← 실행/가드/기록만
├── position_manager.py    — 트랜치 계산, 자금관리
├── order_executor.py      — 거래소 주문 실행 (기존 connector 재활용)
└── scheduler.py           — 봉 확정 주기 실행
```

## 신규 DB 테이블

### premium_configs (사용자 설정 — PC앱 위저드에서 입력)
```sql
CREATE TABLE IF NOT EXISTS premium_configs (
    id SERIAL PRIMARY KEY,
    asset_id INTEGER UNIQUE REFERENCES assets(id),
    strategy_type VARCHAR(50) NOT NULL DEFAULT 'counter_trend',
    signal_tf VARCHAR(10) NOT NULL DEFAULT '30m',
    htf_tf VARCHAR(10) NOT NULL DEFAULT '1D',
    osc_preset VARCHAR(10) NOT NULL DEFAULT 'preset1',
    cash_use_pct FLOAT NOT NULL DEFAULT 55.0,
    hard_cap_pct FLOAT NOT NULL DEFAULT 100.0,
    min_profit_pct FLOAT NOT NULL DEFAULT 0.10,
    fee_buffer_pct FLOAT NOT NULL DEFAULT 0.20,
    one_trade_per_bar BOOLEAN NOT NULL DEFAULT true,
    buy_tranches JSONB NOT NULL DEFAULT '[5,5,5,5,5,5,5,5,5,5]',
    max_buy_tranches INTEGER NOT NULL DEFAULT 10,
    after_max_buy VARCHAR(10) NOT NULL DEFAULT 'extend',
    sell_tranches JSONB NOT NULL DEFAULT '[10,20,30,5,2.5,1]',
    max_sell_tranches INTEGER NOT NULL DEFAULT 6,
    after_max_sell VARCHAR(10) NOT NULL DEFAULT 'cycle',
    use_4regime BOOLEAN NOT NULL DEFAULT true,
    r1_buy_mult FLOAT DEFAULT 1.0, r1_sell_mult FLOAT DEFAULT 1.3,
    r1_allow_osc_buy BOOLEAN DEFAULT true, r1_pullback_on BOOLEAN DEFAULT true,
    r1_pullback_buy_mult FLOAT DEFAULT 1.0,
    r1_buy1_only BOOLEAN DEFAULT false, r1_sell1_only BOOLEAN DEFAULT false,
    r1_sell_mode VARCHAR(20) DEFAULT 'Normal',
    r1_filt_below_avg BOOLEAN DEFAULT true,
    r1_filt_prev_signal BOOLEAN DEFAULT true, r1_filt_prev_exec BOOLEAN DEFAULT true,
    r2_buy_mult FLOAT DEFAULT 0.0, r2_sell_mult FLOAT DEFAULT 1.6,
    r2_allow_osc_buy BOOLEAN DEFAULT false,
    r2_buy1_only BOOLEAN DEFAULT false, r2_sell1_only BOOLEAN DEFAULT false,
    r2_sell_mode VARCHAR(20) DEFAULT 'Alternate',
    r2_filt_below_avg BOOLEAN DEFAULT false,
    r2_filt_prev_signal BOOLEAN DEFAULT false, r2_filt_prev_exec BOOLEAN DEFAULT false,
    r3_buy_mult FLOAT DEFAULT 1.0, r3_sell_mult FLOAT DEFAULT 1.3,
    r3_allow_osc_buy BOOLEAN DEFAULT true, r3_breakout_on BOOLEAN DEFAULT true,
    r3_breakout_buy_mult FLOAT DEFAULT 1.0,
    r3_buy1_only BOOLEAN DEFAULT true, r3_sell1_only BOOLEAN DEFAULT false,
    r3_sell_mode VARCHAR(20) DEFAULT 'Normal',
    r3_filt_below_avg BOOLEAN DEFAULT false,
    r3_filt_prev_signal BOOLEAN DEFAULT true, r3_filt_prev_exec BOOLEAN DEFAULT true,
    r4_buy_mult FLOAT DEFAULT 1.2, r4_sell_mult FLOAT DEFAULT 0.7,
    r4_allow_osc_buy BOOLEAN DEFAULT true,
    r4_buy1_only BOOLEAN DEFAULT false, r4_sell1_only BOOLEAN DEFAULT false,
    r4_sell_mode VARCHAR(20) DEFAULT 'Normal',
    r4_filt_below_avg BOOLEAN DEFAULT true,
    r4_filt_prev_signal BOOLEAN DEFAULT true, r4_filt_prev_exec BOOLEAN DEFAULT false,
    use_lower_band_buy BOOLEAN DEFAULT true, lower_band_buffer FLOAT DEFAULT 0.0,
    use_add_buy_gap BOOLEAN DEFAULT false, add_buy_gap_pct FLOAT DEFAULT 2.0,
    created_at TIMESTAMP DEFAULT NOW(), updated_at TIMESTAMP DEFAULT NOW()
);
```

### strategy_states (엔진 내부 상태 — 사용자 불필요)
```sql
CREATE TABLE IF NOT EXISTS strategy_states (
    id SERIAL PRIMARY KEY,
    asset_id INTEGER UNIQUE REFERENCES assets(id),
    buy_stage INTEGER DEFAULT 0, sell_stage INTEGER DEFAULT 0,
    last_buy_exec_price FLOAT, last_buy_signal_price FLOAT,
    last_buy_time TIMESTAMP, last_sell_time TIMESTAMP,
    r1_pb_armed BOOLEAN DEFAULT false, r1_pb_used BOOLEAN DEFAULT false,
    r3_break_used BOOLEAN DEFAULT false,
    alt_sell_toggle BOOLEAN DEFAULT false,
    current_regime INTEGER DEFAULT 0,
    last_bar_time TIMESTAMP,
    updated_at TIMESTAMP DEFAULT NOW()
);
```

### candles (시세 캐시)
```sql
CREATE TABLE IF NOT EXISTS candles (
    id SERIAL PRIMARY KEY,
    exchange VARCHAR(20) NOT NULL, symbol VARCHAR(30) NOT NULL,
    timeframe VARCHAR(10) NOT NULL, open_time TIMESTAMP NOT NULL,
    open FLOAT NOT NULL, high FLOAT NOT NULL, low FLOAT NOT NULL,
    close FLOAT NOT NULL, volume FLOAT DEFAULT 0,
    UNIQUE(exchange, symbol, timeframe, open_time)
);
CREATE INDEX IF NOT EXISTS idx_candles_lookup
    ON candles(exchange, symbol, timeframe, open_time DESC);
```

## 오실레이터 프리셋 (내장, UI에서 "설정1/설정2"만 선택)
```python
OSC_PRESETS = {
    "preset1": {"smooth_len": 20, "threshold": 1.0, "std_len": 50, "hma_len": 30, "bb_len": 250, "bb_mult": 2.0},
    "preset2": {"smooth_len": 14, "threshold": 0.7, "std_len": 50, "hma_len": 20, "bb_len": 200, "bb_mult": 1.8},
}
HTF_DEFAULTS = {
    "vwma50_len": 50, "vwma200_len": 200, "hull_len": 100,
    "ichi_tenkan": 9, "ichi_kijun": 26, "ichi_senkou": 52,
    "st_atr_len": 20, "st_factor": 5.0,
}
```

## UI 구현 범위

### PC앱 (Tauri) — 전체 설정
- 프리미엄 전략 목록 페이지
- 4단계 위저드: 기본설정 → 자금관리 → 국면별설정 → 확인/시작
- 실행 모니터링 (현재 국면, 차수, 포지션, 로그)
- Rust commands 추가 (premium API invoke)

### 모바일앱 (Flutter) — 간단 조정만
- 활성 전략 상태 확인 (국면, 포지션)
- 일시정지/재개 버튼
- 국면별 배수 간단 슬라이더 (상세 설정은 PC에서)
- E-STOP

### 웹 대시보드 — 변경 없음
- 기존 포트폴리오/거래내역/활성전략 조회만 유지

## 백테스트 기능
- 과거 시세 데이터로 전략 시뮬레이션
- PC앱에서 결과 차트 (수익률, 승률, MDD) 표시
- 파인스크립트 결과와 비교 검증용

## 개발 Phase

### Phase 1: 엔진 코어 (지표 파이썬 재구현)
1. indicators.py — SPO(smoother_F, 정규화, HMA, 볼린저)
2. indicators.py — VWMA, HULL MA, 일목, Supertrend
3. regime_detector.py — 4국면 판별
4. signal_generator.py — 매수/매도 신호 + 필터 + R1눌림/R3돌파
5. **검증**: 동일 OHLCV 데이터 → 파인스크립트 vs 파이썬 신호 비교 테스트

### Phase 2: 시세 + 실행
6. candle_fetcher.py — 거래소 OHLCV 조회 + DB 캐시
7. position_manager.py — 트랜치 계산
8. Hub 연동: signal_event → signal_to_order → order_executor
9. DB 마이그레이션 (premium_configs, strategy_states, candles)

### Phase 3: 스케줄러 + API
10. scheduler.py — 봉 확정 주기 실행
11. FastAPI 프리미엄 엔드포인트
12. 통합 테스트 (mock 주문)

### Phase 4: PC앱 UI
13. 프리미엄 전략 목록/위저드 (index.html + main.js)
14. Rust commands 추가 (commands.rs)
15. 실행 모니터링 UI

### Phase 5: 백테스트
16. backtest_engine.py — 과거 데이터 시뮬레이션
17. PC앱 백테스트 UI (결과 차트)

### Phase 6: 라이브 테스트
18. 소액 실전 + 파인스크립트 비교 검증
19. 안정화

---

# 2) 추세매매(Trend) 프리미엄 전략 — PC앱 + 모바일앱

## 정본 소스: scripts/추세매매.txt
## Entry: Supertrend + HVI + QQE + HTF VWMA156
## Exit: Hard SL → TP1 → SPO Split → ST Flip
## reason_code: TREND_ENTRY_FULL, TREND_EXIT_HARD_SL 등 (PREMIUM_SIGNALS.md §3)

### 구현 순서
- §1 역추세매매 엔진 완성 후 진행
- indicators.py에 Supertrend/HVI/QQE 추가
- signal_generator_trend.py 별도 생성
- PC앱 위저드에 추세매매 옵션 추가
- 백테스트 기능 공유

---

# 3) 커스텀 전략 — 확인 + 백테스트

## 정본: CUSTOM_RULE_SPEC.md
## AST 기반 Rule Builder (지표 6종, 복잡도 제한, Lint)
## 구현 순서
- §1~§2 완성 후 진행
- 기존 CUSTOM_RULE_SPEC.md 스키마 검증
- indicators.py에서 커스텀 지표 계산 지원
- PC앱 Rule Builder UI
- 백테스트 통합

---

# 4) 시장분석 — 국내시장 (StockEasy 수준)

## 현재 상태: 네이버API 기반 기초 구현됨 (Day 7~12)
## 목표: StockEasy 수준 — 시장신호, 섹터분석, 추세유지

### 세부 항목
- [ ] 시장 신호 대시보드 (KOSPI/KOSDAQ 종합 신호등)
- [ ] 섹터 히트맵 (업종별 상승/하락 시각화)
- [ ] 추세 유지/전환 판단 (이동평균 기반)
- [ ] 투자자 동향 (외국인/기관/개인 매매 추이)
- [ ] 시장 너비 (상승종목 비율, 신고가/신저가 비율)

---

# 5) 시장분석 — 해외시장

### 세부 항목
- [ ] 미국 시장 대시보드 (S&P500, NASDAQ, DJI)
- [ ] 섹터분석 (S&P 섹터별 ETF 기반)
- [ ] 추세 유지/전환
- [ ] 투자자 심리 지표 (VIX, CNN Fear & Greed)
- [ ] Yahoo Finance API 활용

---

# 6) 시장분석 — ETF (ETFCheck 수준)

### 세부 항목
- [ ] 상승테마 / 하락테마 목록
- [ ] 테마별 ETF 수익률 비교
- [ ] 관련 뉴스 (네이버 뉴스 API)

---

# 7) 시장분석 — 코인 (CoinMarketCap 홈 수준)

### 세부 항목
- [ ] 시총 순위 목록 (실시간)
- [ ] 김프(김치 프리미엄) 가격차이
- [ ] 도미넌스 차트 (BTC/ETH/Altcoin)
- [ ] 24h 거래량 상위
- [ ] OKX/Binance/Upbit API 활용

---

# 8) 종목분석 — 상세

### 국내주식
- [ ] 종목검색기 (자동완성 + 필터)
- [ ] RS종합(상대강도) 속도 개선 + StockEasy 수준 UI
- [ ] 52주 신고가 다듬기
- [ ] 밸류에이션 (PER/PBR/PSR/EV-EBITDA) StockEasy 수준
- [ ] 리포트 요약 (네이버 리서치 연동)
- [ ] 개별종목 보고서 (StockEasy 종목 상세 수준)

### 해외주식
- [ ] 종목검색기 (티커 검색)
- [ ] RS종합 (국내주식과 동일 구현)
- [ ] 52주 신고가
- [ ] 밸류에이션 (Yahoo Finance)
- [ ] 리포트 요약 (StockEasy 수준)

### ETF
- [ ] ETF 검색 + 종목 상세 (ETFCheck 수준)
- [ ] 구성종목, 수익률, 배당

### 코인
- [ ] 코인 검색 + 기본 차트

---

# 9) 모바일 앱 만들기

## 현재 상태: Flutter 기반 v0.1 (WebView 래핑, E-STOP)
## 목표
- [ ] 네이티브 UI로 전환 (또는 WebView 고도화)
- [ ] 프리미엄 전략 간단 조정 (배수 슬라이더, 일시정지/재개)
- [ ] 시장분석/종목분석 뷰어
- [ ] 푸시 알림 (거래 체결, 신호 발생)

---

# 10) 호환 점검

- [ ] PC앱: Windows 10/11 64bit 설치→실행→거래 완주
- [ ] 모바일앱: Android 10+ APK 설치→실행→조회 완주
- [ ] 웹: Chrome/Edge/Safari 대시보드 정상 표시
- [ ] 거래소별: OKX/Binance/Bybit/Upbit/KIS 전체 주문 테스트
- [ ] Gate 전체 PASS + 스모크 10개 PASS

---

# 11) 전체 우선순위 요약

| 순번 | 작업 | 의존성 | 난이도 |
|------|------|--------|--------|
| **1** | 역추세매매 엔진 + PC/모바일 + 백테스트 | 없음 | ★★★★★ |
| **2** | 추세매매 엔진 + PC/모바일 + 백테스트 | §1 엔진 기반 | ★★★★ |
| **3** | 커스텀 전략 확인 + 백테스트 | §1~2 엔진 기반 | ★★★ |
| **4** | 시장분석-국내 (StockEasy) | 없음 | ★★★ |
| **5** | 시장분석-해외 | §4 패턴 재활용 | ★★★ |
| **6** | 시장분석-ETF (ETFCheck) | 없음 | ★★ |
| **7** | 시장분석-코인 (CoinMarketCap) | 없음 | ★★ |
| **8** | 종목분석 상세 (국내/해외/ETF/코인) | §4~7 기반 | ★★★★ |
| **9** | 모바일 앱 완성 | §1~8 API 활용 | ★★★ |
| **10** | 호환 점검 | 전체 | ★★ |

---

# 12) 클로드 코드 명령서 — Phase 1 (역추세매매 엔진 코어)

## 작업 지시 (Claude Code에 복사하여 전달)

```
=== BBooster 프리미엄 역추세매매 엔진 Phase 1 ===

[목표]
파인스크립트 "역추세매매 현물 v0.4" (scripts/역추세매매 현물 v0.4.txt)를
파이썬으로 1:1 재구현하여 BBooster 서버에서 독립 실행하는 전략 엔진을 만든다.

[필수 문서 읽기 — 작업 전 반드시 확인]
1. docs/AI_RULES.md (절대 규칙)
2. docs/PREMIUM_ENGINE_SPEC.md (signal_event 스키마, 역할 분리)
3. docs/PREMIUM_SIGNALS.md §4 (MR 신호 정의, reason_code)
4. scripts/역추세매매 현물 v0.4.txt (파인스크립트 정본)

[작업 범위 — Phase 1: 엔진 코어]

1. app/strategy_engine/ 디렉토리 생성

2. app/strategy_engine/presets.py
   - OSC_PRESETS: preset1(기본), preset2(민감)
   - HTF_DEFAULTS: VWMA50/200, HULL100, 일목9/26/52, ST ATR20/5.0

3. app/strategy_engine/models.py
   - Candle(ts, o, h, l, c, v)
   - SignalResult(action, reason_code, reason_text, regime, tranche, snapshot)

4. app/strategy_engine/indicators.py — 파인스크립트와 1:1 매칭
   - smoother_f(src, length) → EMA 변형 (파인스크립트 smoother_F)
   - calc_spo(closes, preset) → normalized_osc, upper_band, lower_band, basis
     - oscillator = line_short - line_long
     - stdev_osc → rolling max → normalized
     - HMA(30) 적용
     - 볼린저밴드(250, mult=2)
   - calc_vwma(close, volume, length) → VWMA
   - calc_hma(close, length) → Hull Moving Average
   - calc_ichimoku(high, low, tenkan_len, kijun_len, senkou_len) → tenkan, kijun, senkouA, senkouB
   - calc_supertrend(high, low, close, atr_len, factor) → st_value, st_direction

5. app/strategy_engine/regime_detector.py
   - detect_regime(htf_indicators, use_4regime) → int (0,1,2,3,4)
   - R1: vwma50 >= vwma200 AND st_dir > 0
   - R2: vwma50 >= vwma200 AND st_dir < 0
   - R3: vwma50 < vwma200 AND st_dir > 0
   - R4: vwma50 < vwma200 AND st_dir < 0

6. app/strategy_engine/signal_generator.py
   - generate_mr_signal(osc_data, regime, config, state) → SignalResult
   - 매수 조건: sig_up_raw = osc < -threshold AND crossover(osc, osc_prev)
   - 매도 조건: sig_dn_raw = osc > threshold AND crossover(osc_prev, osc)
   - 국면별 필터: allow_osc_buy, filt_below_avg, filt_prev_signal, filt_prev_exec
   - R1 눌림 트리거: HULL 하락 시 armed → osc_trigger 시 1회 fire
   - R3 돌파 트리거: close > senkouB 상향돌파 시 1회 fire
   - 교대매도 (Alternate): R2에서 기본 활성화
   - 최소익절 게이트: close >= avg_price * (1 + min_profit_pct + fee_buffer)

[검증 — 반드시 수행]
- tests/test_indicators.py 생성
- tests/test_signal_generator.py 생성
- 동일 OHLCV 샘플 데이터로 파인스크립트 결과와 파이썬 결과 비교
- smoother_f: 최소 100봉 데이터로 오차 < 0.001% 확인
- calc_spo: normalized_osc 값 비교
- signal_generator: 매수/매도 신호 발생 봉 번호 일치 확인

[금지 사항]
- 주문 실행 코드 작성 금지 (Premium 엔진은 신호만)
- 거래소 API 호출 금지 (Phase 2에서)
- 기존 app/main.py 수정 금지 (Phase 3에서)
- SMC/MFT 관련 파일 절대 건드리지 않음

[산출물]
- app/strategy_engine/__init__.py
- app/strategy_engine/presets.py
- app/strategy_engine/models.py
- app/strategy_engine/indicators.py
- app/strategy_engine/regime_detector.py
- app/strategy_engine/signal_generator.py
- tests/test_indicators.py
- tests/test_signal_generator.py

[완료 기준]
- python -m compileall app (문법 에러 없음)
- pytest tests/test_indicators.py — 전부 PASS
- pytest tests/test_signal_generator.py — 전부 PASS
- 파인스크립트 vs 파이썬 신호 비교: 불일치 0건
```

---

---

# 13) 전체 로드맵 (우선순위순)

## Phase 1: 역추세매매 완성
1. 백테스트 = 트레이딩뷰 전략리포트 동일
2. 전 거래소 일괄 적용 (캔들/백테스트/프리로딩)
3. 실제 모의거래 테스트 (OKX/Binance/Bybit/KIS)
4. 설정값이 실제로 반영되는지 확인
*모바일앱은 나중 단계

## Phase 2: 추세매매 완성
- Phase 1과 동일한 과정 반복
*모바일앱은 나중 단계

## Phase 3: 커스텀전략
- 동작 확인 + 백테스트 + 모의거래 테스트

## Phase 3.5: 실전 거래 엔진 (KIS 주문 타이밍)
- KIS_KR: 주문 방식 선택 (정규장 마감 전 / 넥스트트레이드 / 다음날 시가)
- KIS_KR: 주문 타이밍 (마감 N초 전), 시장가 주문
- KIS_US: 종가마감 신호 (마감 N분 전), 지정가 + 슬리피지 N틱
- 코인: 별도 설정 없음, 24시간 시장가 즉시 실행
- 스케줄러 연동 + 실전 모의투자 테스트

## Phase 4: 시장분석 — 국내
- 스탁이지 수준: 시장신호, 섹터, 추세유지

## Phase 5: 시장분석 — 해외
- 국내시장과 동일 수준

## Phase 6: 시장분석 — ETF
- ETFCHECK 수준: 상승/하락 테마, 뉴스

## Phase 7: 시장분석 — 코인
- 코인마켓캡 수준: 김프가, 도미넌스

## Phase 8: 종목분석
- 국내: 종목검색기, RS, 52주신고가, 밸류에이션, 리포트요약, 개별보고서
- 해외: 국내와 동일
- ETF: 검색+종목상세 (ETFCHECK 수준)
- 코인: 검색+기본차트

## Phase 9: 모바일 앱

## Phase 10: 호환 점검

---

[END OF MASTER_ROADMAP_V3]

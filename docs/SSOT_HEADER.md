# 큐브시스템 (QUBE System) — BBooster Hub
- Company: 큐브시스템 (QUBE System)
- Repo: C:\Users\pc\새 폴더\AUAT
- VPS: 76.13.180.30 (https://qube-system.com)
- SSOT: docs/FINISH_SSOT.md, docs/PROJECT_STATUS.md
- Rules: docs/AI_RULES.md (MUST read first)

## Current Status (2026-02-08)
- Week A~D: DONE (브랜드/사이트/PC앱/Android APK 기반)
- Day 6: DONE (대시보드 개편 + 구독 플랜)
- Day 7: DONE (종목분석 개편 + 10 버그 수정)
- Day 8: DONE (종목검색/네이버API/자동완성/파싱 수정)
- Day 9: DONE (긴급 수정 + 보유자산 + 계정관리)

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

**커밋**
- `f2da45a` feat: 전략설정 (Sizing/Risk/Limits) Phase 1-3 구현

## Day 8 Fixes
- 종목명 쓰레기 데이터 제거 (`_clean_stock_name`)
- 섹터 데이터 수정 (업종 지수 기반)
- itsdangerous==2.1.2 추가

## Scope Exclusions
- SMC strategy/files, MFT candle, Futures

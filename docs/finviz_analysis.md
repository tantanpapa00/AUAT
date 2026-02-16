# Finviz 데이터 소스 분석 결과

**분석일:** 2026-02-16
**분석 스크립트:** `tests/test_finviz_scrape.py`

---

## 1. Breadth 데이터 (메인페이지)

### 파싱 가능 여부: O (성공)

### URL
```
https://finviz.com/
```

### HTML 구조
```html
<div class="market-stats" data-boxover="...Advancing / Declining...">
    <div class="market-stats_labels">
        <div class="market-stats_labels_left"><p>Advancing</p><p>62.5% (3485)</p></div>
        <div class="market-stats_labels_right"><p>Declining</p><p>(1849) 33.2%</p></div>
    </div>
</div>
```

### 파싱 방법 (정규식)
```python
import re
import httpx

async def collect_finviz_breadth():
    headers = {"User-Agent": "Mozilla/5.0..."}
    r = await client.get("https://finviz.com/", headers=headers)
    html = r.text

    result = {}

    # Advancing: XX.X% (NNNN)
    adv = re.search(r'Advancing.*?(\d+\.\d+)%\s*\((\d+)\)', html, re.DOTALL)
    if adv:
        result["advancing_pct"] = float(adv.group(1))
        result["advancing_count"] = int(adv.group(2))

    # Declining: (NNNN) XX.X%
    dec = re.search(r'Declining.*?\((\d+)\)\s*(\d+\.\d+)%', html, re.DOTALL)
    if dec:
        result["declining_count"] = int(dec.group(1))
        result["declining_pct"] = float(dec.group(2))

    # New High: XX.X% (NNNN)
    nh = re.search(r'New High.*?(\d+\.\d+)%\s*\((\d+)\)', html, re.DOTALL)
    if nh:
        result["new_high_pct"] = float(nh.group(1))
        result["new_high_count"] = int(nh.group(2))

    # New Low: (NNNN) XX.X%
    nl = re.search(r'New Low.*?\((\d+)\)\s*(\d+\.\d+)%', html, re.DOTALL)
    if nl:
        result["new_low_count"] = int(nl.group(1))
        result["new_low_pct"] = float(nl.group(2))

    # SMA50 Above: XX.X% (NNNN)
    sma50_a = re.search(r'SMA50.*?(\d+\.\d+)%\s*\((\d+)\).*?Below', html, re.DOTALL)
    if sma50_a:
        result["above_sma50_pct"] = float(sma50_a.group(1))
        result["above_sma50_count"] = int(sma50_a.group(2))

    # SMA200 Above: XX.X% (NNNN)
    sma200_a = re.search(r'SMA200.*?(\d+\.\d+)%\s*\((\d+)\).*?Below', html, re.DOTALL)
    if sma200_a:
        result["above_sma200_pct"] = float(sma200_a.group(1))
        result["above_sma200_count"] = int(sma200_a.group(2))

    return result
```

### 가져올 수 있는 항목
- [x] **Advancing / Declining** (종목수 + 비율)
  - 예: Advancing 62.5% (3485), Declining (1849) 33.2%
- [x] **New High / New Low**
  - 예: New High 50.4% (198), New Low (195) 49.6%
- [x] **Above/Below SMA50**
  - 예: Above 48.5% (2697), Below (2865) 51.5%
- [x] **Above/Below SMA200**
  - 예: Above 51.8% (2879), Below (2683) 48.2%

### 참고
- NYSE, NASDAQ, AMEX 전체 종목 기준 (약 5,500개)
- S&P 500 전용 데이터는 별도 제공 안 함
- 실시간 업데이트 (장중)

---

## 2. 히트맵 데이터

### API 존재 여부: O (발견)

### API URL
```
https://finviz.com/api/map_perf.ashx?t=sec        # S&P 500 (503개)
https://finviz.com/api/map_perf.ashx?t=sec_all    # 전체 시장 (5887개)
```

### 응답 형식: JSON
```json
{
  "nodes": {
    "AAPL": 1.23,
    "MSFT": -0.45,
    "NVDA": 2.11,
    ...
  },
  "additional": null,
  "subtype": "d1",
  "version": "...",
  "hash": "..."
}
```

### 제한 사항
- **등락률(%)만 제공** - 섹터, 시가총액 정보 없음
- 섹터/시가총액 정보는 Screener API 필요

### 가져올 수 있는 항목
- [x] **S&P 500 전체 종목 (503개)**
- [x] **티커 심볼**
- [x] **일간 등락률 (%)**
- [ ] 시가총액 (별도 API 필요)
- [ ] 섹터 (별도 API 필요)

---

## 3. Finviz Python 패키지 (finviz.screener)

### Screener 사용 가능 여부: O (성공)

### 설치
```bash
pip install finviz
```

### 코드 예제
```python
from finviz.screener import Screener

# S&P 500 전체 종목 조회 (시가총액 순)
filters = ['idx_sp500']
stock_list = Screener(filters=filters, table='Overview', order='-marketcap')

print(f"종목 수: {len(stock_list)}")  # 503개

for stock in stock_list[:5]:
    print(stock)
```

### 응답 데이터 구조
```python
{
    'No.': '1',
    'Ticker': 'NVDA',
    'Company': 'NVIDIA Corp',
    'Sector': 'Technology',          # 섹터 ✓
    'Industry': 'Semiconductors',
    'Country': 'USA',
    'Market Cap': '4442.28B',        # 시가총액 ✓
    'P/E': '45.28',
    'Price': '182.81',
    'Change': '-2.21%',              # 등락률 ✓
    'Volume': '161,406,714'
}
```

### 가져올 수 있는 항목
- [x] **S&P 500 전체 종목 (503개)**
- [x] **티커, 회사명**
- [x] **섹터 (11개 GICS 섹터)**
- [x] **산업 (Industry)**
- [x] **시가총액**
- [x] **등락률 (%)**
- [x] **P/E, 가격, 거래량**

### 속도/제한
- 503개 종목 조회: **약 10초** (26페이지 크롤링)
- Rate limit: 있음 (과도한 요청 시 차단 가능)
- 권장: 1시간마다 캐싱

---

## 4. 권장 데이터 소스

| 데이터 | 권장 소스 | 이유 |
|--------|----------|------|
| **Breadth** (상승/하락, 신고가/신저가, SMA) | Finviz 메인페이지 | 전체 시장 실시간 데이터, 파싱 안정 |
| **히트맵 등락률** | Finviz API (`map_perf.ashx`) | S&P 500 전체, 실시간, JSON |
| **히트맵 섹터/시가총액** | Finviz Screener | 503개 전체, 섹터/시가총액 포함 |
| **Fear & Greed** | CNN API (기존 유지) | 공식 API, 안정적 |
| **VIX** | Yahoo Finance (기존 유지) | 무료, 빠름 |

---

## 5. 구현 권장 사항

### 5.1 히트맵 개선 (현재 30개 → 503개)

**현재 문제:**
- 30개 종목 하드코딩 (HEATMAP_STOCKS)
- 시가총액 수동 입력

**개선 방안:**
```python
# 1. Finviz Screener로 S&P 500 전체 가져오기
from finviz.screener import Screener

filters = ['idx_sp500']
stocks = Screener(filters=filters, table='Overview', order='-marketcap')

# 2. 히트맵 데이터 변환
heatmap = []
for s in stocks:
    mcap_str = s.get('Market Cap', '0')  # "4442.28B"
    mcap = parse_market_cap(mcap_str)     # 4442.28

    heatmap.append({
        "symbol": s['Ticker'],
        "name": s['Company'],
        "sector": s['Sector'],
        "market_cap": mcap,
        "change_pct": float(s['Change'].replace('%', '')),
    })
```

### 5.2 Breadth 개선

**현재 문제:**
- 30개 샘플로 503개 추정 (정확도 낮음)
- S&P 500 전용 데이터 없음

**개선 방안:**
```python
# Finviz 메인페이지에서 전체 시장 Breadth 사용
# (NYSE + NASDAQ + AMEX 기준, S&P 500 아님)

# 또는 Screener로 S&P 500 상승/하락 계산
advancing = sum(1 for s in stocks if float(s['Change'].replace('%','')) > 0)
declining = sum(1 for s in stocks if float(s['Change'].replace('%','')) < 0)
```

### 5.3 캐싱 전략

```python
# 1시간마다 Screener 데이터 갱신
# 5분마다 map_perf.ashx API로 등락률만 업데이트

import time

CACHE = {
    "stocks": [],           # Screener 데이터 (1시간 캐시)
    "stocks_updated": 0,
    "perf": {},             # API 등락률 (5분 캐시)
    "perf_updated": 0,
}

async def get_heatmap():
    now = time.time()

    # 1시간마다 전체 데이터 갱신
    if now - CACHE["stocks_updated"] > 3600:
        CACHE["stocks"] = await fetch_screener()
        CACHE["stocks_updated"] = now

    # 5분마다 등락률만 갱신
    if now - CACHE["perf_updated"] > 300:
        CACHE["perf"] = await fetch_map_perf()
        CACHE["perf_updated"] = now

    # 병합
    for s in CACHE["stocks"]:
        s["change_pct"] = CACHE["perf"].get(s["symbol"], s["change_pct"])

    return CACHE["stocks"]
```

---

## 6. 테스트 스크립트 실행 결과

```
=== Breadth 파싱 결과 ===
Advancing: 62.5% (3485)
Declining: (1849) 33.2%
New High: 50.4% (198)
New Low: (195) 49.6%
SMA50 Above: 48.5% (2697), Below: (2865) 51.5%
SMA200 Above: 51.8% (2879), Below: (2683) 48.2%

=== 히트맵 API ===
URL: https://finviz.com/api/map_perf.ashx?t=sec
Status: 200
종목 수: 503
샘플: {'CF': 0.531, 'CTVA': 1.241, 'MOS': -0.403, ...}

=== Finviz Screener ===
종목 수: 503
샘플:
  1. NVDA: Technology, 4442.28B, -2.21%
  2. AAPL: Technology, 3755.14B, -2.27%
  3. GOOG: Communication Services, 3699.93B, -1.08%
  4. GOOGL: Communication Services, 3699.93B, -1.06%
  5. MSFT: Technology, 2980.05B, -0.13%
```

---

## 7. 결론

Finviz는 해외시장 분석에 **매우 유용한 데이터 소스**입니다:

1. **Breadth 데이터**: 메인페이지에서 안정적 파싱 가능
2. **히트맵 API**: S&P 500 전체 등락률 실시간 제공
3. **Screener**: 섹터/시가총액 포함 전체 데이터 제공

**다음 단계:**
1. `data_collector_us.py`에 Finviz 통합
2. 30개 하드코딩 → 503개 동적 데이터
3. 캐싱 전략 적용 (1시간/5분)

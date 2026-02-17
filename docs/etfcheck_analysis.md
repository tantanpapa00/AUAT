# ETFCheck 사이트 분석 보고서

> 분석일: 2026-02-17

## 1. ETFCheck API 분석

### 1-1. 기본 정보
- **사이트**: https://www.etfcheck.co.kr/
- **기술 스택**: Vue.js SPA + Axios
- **Base URL**: `https://www.etfcheck.co.kr`

### 1-2. 발견된 API 엔드포인트 (총 150+개)

#### 주요 ETF 데이터 API
| 엔드포인트 | 설명 |
|------------|------|
| `/user/etp/getEtpRankListYield` | 수익률 순위 |
| `/user/etp/getEtpRankListVolume` | 거래량 순위 |
| `/user/etp/getEtpRankListInflow` | 자금유입 순위 |
| `/user/etp/getEtpRankListMarketCap` | 시총 순위 |
| `/user/etp/getEtpRankListCash` | 분배금 순위 |
| `/user/etp/getEtpRankListDisparate` | 괴리율 순위 |
| `/user/etp/getEtpListByCtg` | 테마/카테고리별 목록 |
| `/user/etp/getEtpInfoByCtg` | 카테고리 정보 |
| `/user/etp/getIssueEtp` | 이슈 ETF |
| `/user/etp/getIssueNewItem` | 신규 상장 ETF |

#### 뉴스/리포트 API
| 엔드포인트 | 설명 |
|------------|------|
| `/etc/etp/getNewsList` | 뉴스 목록 |
| `/etc/etp/getNewsTitle` | 뉴스 제목 |
| `/etc/etp/getBreakingNewsList` | 속보 뉴스 |
| `/report/getReport` | 리포트 조회 |
| `/user/etp/getWeeklyReportList` | 주간 리포트 |
| `/user/etp/getMonthlyReportList` | 월간 리포트 |

#### 카테고리/테마 API
| 엔드포인트 | 설명 |
|------------|------|
| `/user/common/getEtpCtgLarge` | 대분류 카테고리 |
| `/user/common/getEtpCtgMiddle` | 중분류 카테고리 |
| `/user/common/getEtpCtgMap` | 카테고리 맵 |
| `/user/etp/getEtpSector` | 섹터 정보 |

#### 종목 상세 API
| 엔드포인트 | 설명 |
|------------|------|
| `/user/etp/getEtpItemInfo` | 종목 기본 정보 |
| `/user/etp/getEtpItemOutline` | 종목 개요 |
| `/user/etp/getEtpItemCash` | 분배금 정보 |
| `/user/etp/getEtpItemDiffInfo` | 괴리율 정보 |
| `/user/etp/getEtpYieldList` | 수익률 이력 |

### 1-3. 카테고리 코드 (data_config.js)

```javascript
// 메인 탭
tabMenu: ["HOT", "레버리지", "인버스", "원자재"]

// 카테고리 코드
ctgCodeInfo: [
    {ctgLargeCode: "", ctgCode: ""},                         // HOT
    {ctgLargeCode: "0301", ctgCode: ["0301002", "0301003"]}, // 레버리지
    {ctgLargeCode: "0301", ctgCode: ["0301004", "0301005", "0301006"]}, // 인버스
    {ctgLargeCode: "0105", ctgCode: ""}                      // 원자재
]

// 원자재 세부 코드
ctgGubunInfo: {
    default: '0105003',
    items: [
        { text: '원유', value: '0105003' },
        { text: '금은', value: '0701010|0701011' },
        { text: '기타', value: 'etc' }
    ]
}
```

### 1-4. API 접근성 문제
- **인증 필요**: ETFCheck API는 세션 쿠키/토큰 인증 필요
- **직접 호출 불가**: curl로 직접 호출 시 빈 응답 반환
- **CORS 제한**: 외부 도메인에서 호출 시 차단

---

## 2. 대안 데이터 소스: 네이버 금융 ETF API

### 2-1. API 정보
- **엔드포인트**: `https://finance.naver.com/api/sise/etfItemList.nhn`
- **인증**: 불필요 (공개 API)
- **응답 형식**: JSON

### 2-2. 요청 파라미터
| 파라미터 | 설명 | 값 |
|----------|------|-----|
| `etfType` | ETF 유형 | 0-7 (아래 참조) |
| `targetColumn` | 정렬 기준 | market_sum, change_rate, quant 등 |
| `sortOrder` | 정렬 순서 | asc, desc |

### 2-3. ETF 유형 코드 (etfTabCode)
| 코드 | 한글명 | ETF 수 |
|------|--------|--------|
| 0 | 전체 | 1,070개 |
| 1 | 국내 시장지수 | 90개 |
| 2 | 국내 업종/테마 | 288개 |
| 3 | 국내 파생 (레버리지/인버스) | 38개 |
| 4 | 해외 주식 | 364개 |
| 5 | 원자재 | 21개 |
| 6 | 채권 | 168개 |
| 7 | 기타 | 101개 |

### 2-4. 응답 데이터 구조
```json
{
  "resultCode": "success",
  "result": {
    "etfItemList": [
      {
        "itemcode": "069500",
        "etfTabCode": 1,
        "itemname": "KODEX 200",
        "nowVal": 81860,
        "risefall": "5",
        "changeVal": -115,
        "changeRate": -0.14,
        "nav": 81847,
        "threeMonthEarnRate": 38.7269,
        "quant": 15969201,
        "amonut": 1313103,
        "marketSum": 160691
      }
    ]
  }
}
```

### 2-5. 필드 설명
| 필드 | 설명 | 단위 |
|------|------|------|
| itemcode | 종목코드 | - |
| etfTabCode | ETF 유형 | 1-7 |
| itemname | 종목명 | - |
| nowVal | 현재가 | 원 |
| risefall | 등락 구분 | 2:상승, 5:하락 |
| changeVal | 전일대비 | 원 |
| changeRate | 등락률 | % |
| nav | 순자산가치 | 원 |
| threeMonthEarnRate | 3개월 수익률 | % |
| quant | 거래량 | 주 |
| amonut | 거래대금 | 백만원 |
| marketSum | 시가총액 | 억원 |

---

## 3. 활용 가능한 데이터 항목

### 3-1. BBooster ETF 시장분석 탭 구현 시 활용
| 기능 | 데이터 소스 | API |
|------|------------|-----|
| **수익률 TOP** | 네이버 금융 | etfItemList.nhn (threeMonthEarnRate 정렬) |
| **수익률 BOTTOM** | 네이버 금융 | etfItemList.nhn (threeMonthEarnRate 역순) |
| **거래량 TOP** | 네이버 금융 | etfItemList.nhn (quant 정렬) |
| **시총 TOP** | 네이버 금융 | etfItemList.nhn (marketSum 정렬) |
| **테마별 목록** | 네이버 금융 | etfType 파라미터로 필터링 |
| **레버리지/인버스** | 네이버 금융 | etfType=3 |
| **원자재** | 네이버 금융 | etfType=5 |
| **채권** | 네이버 금융 | etfType=6 |

### 3-2. 3개월 수익률 TOP 10 (실제 데이터)
1. TIGER 반도체TOP10레버리지: +114.14%
2. KODEX 반도체레버리지: +100.83%
3. PLUS 드론&UAM: +93.30%
4. TIGER 200IT레버리지: +87.35%
5. TIGER 레버리지: +85.25%
6. HANARO 200선물레버리지: +85.22%
7. PLUS 200선물레버리지: +85.19%
8. TIGER 200선물레버리지: +85.08%
9. ACE 레버리지: +85.07%
10. RISE 200선물레버리지: +84.78%

### 3-3. 3개월 수익률 BOTTOM 10 (실제 데이터)
1. KODEX 200선물인버스2X: -52.17%
2. RISE 200선물인버스2X: -52.15%
3. TIGER 200선물인버스2X: -52.11%
4. KIWOOM 200선물인버스2X: -52.06%
5. PLUS 200선물인버스2X: -51.35%
6. TIGER 미국AIBig테크TOP4Plus: -36.09%
7. ACE 인버스: -29.64%
8. KODEX 인버스: -29.58%
9. TIGER 인버스: -29.47%
10. HANARO 200선물인버스: -29.23%

---

## 4. 기타 대안 데이터 소스

### 4-1. KRX 데이터시스템
- **URL**: https://data.krx.co.kr/
- **장점**: 공식 데이터, 높은 신뢰성
- **단점**: API 제공 불가, 수동 다운로드만 가능

### 4-2. 공공데이터포털 증권상품시세 API
- **URL**: https://www.data.go.kr/
- **API 예시**:
  - 금융위원회_증권상품시세정보
  - 금융위원회_ETF시세정보
- **장점**: 공식 인증 API
- **단점**: API 키 발급 필요, 호출 제한 있음

### 4-3. 한국거래소 Open API
- **URL**: https://openapi.krx.co.kr/
- **내용**: ETF/ETN 현재가, 등락률, NAV 등
- **장점**: 실시간 데이터
- **단점**: 회원가입 및 API 키 필요

---

## 5. 권장 구현 방안

### Phase 6: ETF 시장분석 구현

1. **1차**: 네이버 금융 ETF API 활용
   - 공개 API, 인증 불필요
   - 모든 국내 ETF 데이터 포함 (1,070개)
   - 3개월 수익률, 거래량, 시총 등 핵심 지표

2. **2차**: ETFCheck 스타일 UI 구현
   - 상승 테마 / 하락 테마 히트맵
   - 테마별 ETF 수익률 비교
   - 레버리지/인버스 섹션

3. **3차**: 추가 데이터 소스 연동 (선택)
   - 공공데이터포털 API (더 상세한 정보 필요시)
   - 네이버 뉴스 API (ETF 관련 뉴스)

### 백엔드 API 설계

```python
# app/etf_routes.py

@router.get("/api/etf/ranking")
async def get_etf_ranking(
    etf_type: int = 0,  # 0-7
    sort_by: str = "threeMonthEarnRate",  # marketSum, quant, changeRate
    order: str = "desc",
    limit: int = 20
):
    """네이버 금융 ETF API 프록시"""
    pass

@router.get("/api/etf/themes")
async def get_etf_by_theme():
    """테마별 ETF 그룹핑"""
    pass
```

---

## 6. 결론

| 항목 | ETFCheck | 네이버 금융 |
|------|----------|------------|
| **API 접근성** | 인증 필요 (사용 불가) | 공개 API (사용 가능) |
| **데이터 범위** | 국내/해외 ETF | 국내 ETF만 |
| **ETF 수** | - | 1,070개 |
| **제공 정보** | 테마, 분배금, 상세 분석 | 기본 시세, 3개월 수익률 |
| **업데이트** | 실시간 | 장중 실시간 |

**권장**: 네이버 금융 ETF API를 1차 데이터 소스로 활용하여 ETF 시장분석 기능 구현

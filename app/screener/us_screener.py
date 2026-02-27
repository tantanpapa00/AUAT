"""
해외(미국) 주식 스크리너
Finviz 기반 (v=111 Overview + v=161 Financial)
"""

import asyncio
import httpx
import time as _time
from typing import List, Dict, Any, Optional
from datetime import datetime

from .cache import screener_cache, CACHE_TTL
from .filters import apply_screener_filters, sort_screener_results

# 모듈 레벨 메모리 캐시 (서버 시작 시 워밍업)
_us_stock_cache = None
_us_cache_ts = 0
_US_CACHE_TTL = 3600  # 1시간


async def load_us_stocks():
    """US 종목 목록 — 메모리 캐시 우선 (서버 워밍업용)"""
    global _us_stock_cache, _us_cache_ts
    now = _time.time()

    if _us_stock_cache and now - _us_cache_ts < _US_CACHE_TTL:
        return [s.copy() for s in _us_stock_cache]  # 복사본 반환

    # 캐시 만료 → Finviz에서 새로 로드
    stocks = await fetch_all_us_stocks()
    _us_stock_cache = stocks
    _us_cache_ts = now
    return [s.copy() for s in stocks]

# Finviz 헤더
FINVIZ_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Accept": "text/html,application/xhtml+xml",
}

# Finviz 섹터 한글 변환
FINVIZ_SECTOR_KR = {
    "Technology": "기술",
    "Healthcare": "헬스케어",
    "Financial": "금융",
    "Financials": "금융",
    "Financial Services": "금융",
    "Consumer Cyclical": "임의소비재",
    "Consumer Defensive": "필수소비재",
    "Communication Services": "커뮤니케이션",
    "Industrials": "산업재",
    "Energy": "에너지",
    "Utilities": "유틸리티",
    "Real Estate": "부동산",
    "Basic Materials": "소재",
    "Materials": "소재",
}


async def screener_us(filters: dict, sort: str, order: str, page: int, per_page: int) -> dict:
    """
    미국 주식 스크리너 - Finviz + Yahoo Finance 기반

    [흐름]
    1. S&P 500 종목 목록 가져오기 (메모리 캐시 — 10분)
    2. 필터 적용 (섹터, 시총, 등락률)
    3. 정렬 + 페이지네이션
    """
    t0 = _time.time()

    # 메모리 캐시에서 S&P 500 전종목 데이터 가져오기 (서버 워밍업 후 즉시 반환)
    all_stocks = await load_us_stocks()
    t1 = _time.time()
    print(f"[PERF] US 종목로드: {t1-t0:.2f}초, {len(all_stocks)}개")

    if not all_stocks:
        return {"items": [], "total": 0, "page": page, "per_page": per_page, "message": "데이터를 불러올 수 없습니다"}

    # 필터 적용
    filtered = apply_us_filters(all_stocks, filters)
    t2 = _time.time()
    print(f"[PERF] US 필터: {t2-t1:.2f}초, {len(filtered)}개")

    # 정렬
    filtered = sort_screener_results(filtered, sort, order)

    total = len(filtered)

    # 페이지네이션
    start = (page - 1) * per_page
    end = start + per_page
    items = filtered[start:end]

    t3 = _time.time()
    print(f"[PERF] US 전체: {t3-t0:.2f}초")

    # 시총 문자열 추가 (달러 기준)
    for item in items:
        cap = item.get("market_cap", 0)  # 조 달러 단위
        if cap >= 1:
            item["market_cap_str"] = f"${cap:.1f}T"
        elif cap >= 0.001:
            item["market_cap_str"] = f"${cap * 1000:.0f}B"
        else:
            item["market_cap_str"] = "-"

    return {
        "items": items,
        "total": total,
        "page": page,
        "per_page": per_page,
        "filters_applied": list(filters.keys()),
    }


def apply_us_filters(stocks: List[Dict], filters: dict) -> List[Dict]:
    """US 전용 필터 적용"""
    result = stocks

    # 섹터 필터
    if filters.get("sector"):
        sector = filters["sector"]
        if isinstance(sector, dict):
            sector = sector.get("value", sector)
        result = [s for s in result if s.get("sector") == sector]

    # 시총 필터 (프론트: B$단위, 데이터: 조달러단위)
    if filters.get("market_cap"):
        mc_filter = filters["market_cap"]
        if isinstance(mc_filter, dict):
            min_val = mc_filter.get("min")
            max_val = mc_filter.get("max")
            # B$ → T$ 변환 (200B = 0.2T)
            if min_val is not None:
                min_trillion = min_val / 1000
                result = [s for s in result if s.get("market_cap", 0) >= min_trillion]
            if max_val is not None:
                max_trillion = max_val / 1000
                result = [s for s in result if s.get("market_cap", 0) <= max_trillion]

    # 등락률 필터
    if filters.get("change_pct"):
        cp_filter = filters["change_pct"]
        if isinstance(cp_filter, dict):
            min_val = cp_filter.get("min")
            max_val = cp_filter.get("max")
            if min_val is not None:
                result = [s for s in result if (s.get("change_pct") or 0) >= min_val]
            if max_val is not None:
                result = [s for s in result if (s.get("change_pct") or 0) <= max_val]

    # 재무 필터 (공통 로직 사용)
    financial_filters = {k: v for k, v in filters.items() if k in [
        "per", "pbr", "roe", "roa", "operating_margin", "gross_margin",
        "profit_margin", "debt_ratio", "current_ratio", "dividend_yield",
        "revenue_growth", "earnings_growth", "eps_growth"
    ]}
    if financial_filters:
        result = apply_screener_filters(result, financial_filters)

    return result


async def fetch_all_us_stocks() -> List[Dict]:
    """
    S&P 500 종목 + 실시간 등락률 + 재무 데이터 결합

    1. Finviz v=111 (Overview): 섹터, 시총, 종목명
    2. Finviz v=161 (Financial): ROE, ROA, Debt/Eq, Margins 등
    3. Finviz v=141 (Valuation): PER, PBR
    4. Finviz 히트맵 API: 실시간 등락률
    """
    # 1. 메타데이터 가져오기 (v=111)
    metadata = await fetch_sp500_metadata()

    # 2. 재무 데이터 가져오기 (v=161)
    financials = await fetch_sp500_financials()

    # 3. Valuation 데이터 가져오기 (v=141) - PER, PBR
    valuations = await fetch_sp500_valuation()

    # 4. 실시간 등락률 가져오기
    changes = await fetch_finviz_changes()

    # 5. 결합
    stocks = []
    for symbol, meta in metadata.items():
        change_pct = changes.get(symbol, 0)
        fin = financials.get(symbol, {})
        val = valuations.get(symbol, {})

        stock = {
            "code": symbol,
            "name": meta.get("name", symbol),
            "sector": meta.get("sector", "기타"),
            "market_cap": meta.get("market_cap", 0),  # 조 달러 단위
            "change_pct": change_pct,
            "price": meta.get("price", 0),
            "volume": 0,
            "exchange": "NYSE/NASDAQ",
        }
        # 재무 데이터 병합
        stock.update(fin)
        # Valuation 데이터 병합 (PER, PBR)
        stock.update(val)
        stocks.append(stock)

    print(f"[US Screener] {len(stocks)}개 종목 로드 완료")
    return stocks


async def fetch_sp500_metadata() -> Dict[str, Dict]:
    """
    Finviz Screener 페이지 스크래핑으로 S&P 500 메타데이터 수집
    Returns: {"AAPL": {"sector": "기술", "market_cap": 3.5, "name": "Apple Inc"}, ...}
    """
    from bs4 import BeautifulSoup

    result = {}
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Accept": "text/html,application/xhtml+xml",
    }

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            page = 1
            all_stocks = []

            while True:
                offset = (page - 1) * 20 + 1
                url = f"https://finviz.com/screener.ashx?v=111&f=idx_sp500&o=-marketcap&r={offset}"

                r = await client.get(url, headers=headers)
                if r.status_code != 200:
                    print(f"[Finviz Screener] 페이지 {page} 실패: {r.status_code}")
                    break

                soup = BeautifulSoup(r.text, 'lxml')
                rows = soup.select('table.screener-body-table-nw tr[valign="top"]')
                if not rows:
                    rows = soup.select('tr.styled-row')
                if not rows:
                    break

                for row in rows:
                    cols = row.find_all('td')
                    if len(cols) < 10:
                        continue

                    try:
                        ticker_link = cols[1].find('a')
                        ticker = ticker_link.text.strip() if ticker_link else ""
                        company = cols[2].text.strip()
                        sector_en = cols[3].text.strip()
                        mcap_str = cols[6].text.strip()

                        # cols[8] = Price, cols[9] = Change
                        try:
                            price = float(cols[8].text.strip().replace(',', ''))
                        except (ValueError, IndexError):
                            price = 0

                        try:
                            change_text = cols[9].text.strip().replace('%', '')
                            change_pct = float(change_text)
                        except (ValueError, IndexError):
                            change_pct = 0

                        if ticker:
                            sector_kr = FINVIZ_SECTOR_KR.get(sector_en, sector_en)
                            mcap = _parse_market_cap(mcap_str)
                            all_stocks.append({
                                "symbol": ticker,
                                "name": company,
                                "sector": sector_kr,
                                "market_cap": mcap,
                                "price": price,
                                "change_pct": change_pct,
                            })
                    except Exception:
                        continue

                if len(rows) < 20 or page >= 30:
                    break
                page += 1
                await asyncio.sleep(0.3)  # 요청 간격

            for stock in all_stocks:
                result[stock["symbol"]] = {
                    "sector": stock["sector"],
                    "market_cap": stock["market_cap"],
                    "name": stock["name"],
                    "price": stock.get("price", 0),
                    "change_pct": stock.get("change_pct", 0),
                }

            print(f"[Finviz Screener] S&P 500: {len(result)}개 종목 ({page}페이지)")

    except Exception as e:
        print(f"[Finviz Screener] 오류: {e}")
        import traceback
        traceback.print_exc()

    return result


def _parse_market_cap(mcap_str: str) -> float:
    """시가총액 문자열을 조 달러 단위로 변환 ('4442.28B' → 4.44)"""
    if not mcap_str:
        return 0.01
    mcap_str = mcap_str.strip().upper()
    try:
        if mcap_str.endswith("T"):
            return float(mcap_str[:-1])
        elif mcap_str.endswith("B"):
            return float(mcap_str[:-1]) / 1000
        elif mcap_str.endswith("M"):
            return float(mcap_str[:-1]) / 1000000
        else:
            return float(mcap_str) / 1e12
    except:
        return 0.01


def _parse_finviz_pct(val: str) -> Optional[float]:
    """Finviz % 값 파싱. '10.50%' → 10.50, '-' → None"""
    if not val or val == '-' or val == '':
        return None
    try:
        return float(val.replace('%', '').strip())
    except:
        return None


def _parse_finviz_float(val: str) -> Optional[float]:
    """Finviz 숫자 파싱. '1.50' → 1.50, '-' → None"""
    if not val or val == '-' or val == '':
        return None
    try:
        return float(val.strip())
    except:
        return None


async def fetch_sp500_financials() -> Dict[str, Dict]:
    """
    Finviz Financial 뷰(v=161)에서 재무 데이터 수집
    Returns: {"AAPL": {"roe": 152.02, "roa": 32.56, "debt_ratio": 1.03, ...}, ...}

    v=161 컬럼 순서:
    No., Ticker, Market Cap, Dividend, ROA, ROE, ROI,
    Curr R, Quick R, LTDebt/Eq, Debt/Eq, Gross M, Oper M, Profit M,
    Earnings, Price, Change, Volume
    """
    from bs4 import BeautifulSoup

    result = {}

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            page = 1

            while True:
                offset = (page - 1) * 20 + 1
                url = f"https://finviz.com/screener.ashx?v=161&f=idx_sp500&o=-marketcap&r={offset}"

                r = await client.get(url, headers=FINVIZ_HEADERS)
                if r.status_code != 200:
                    print(f"[Finviz v=161 Financial] 페이지 {page} 실패: {r.status_code}")
                    break

                soup = BeautifulSoup(r.text, 'lxml')
                rows = soup.select('table.screener-body-table-nw tr[valign="top"]')
                if not rows:
                    rows = soup.select('tr.styled-row')
                if not rows:
                    break

                for row in rows:
                    cols = row.find_all('td')
                    if len(cols) < 17:
                        continue

                    try:
                        ticker_link = cols[1].find('a')
                        ticker = ticker_link.text.strip() if ticker_link else ""

                        if ticker:
                            # v=161 컬럼: No, Ticker, MktCap, Div, ROA, ROE, ROI, CurrR, QuickR, LTD/Eq, D/Eq, GrossM, OperM, ProfitM, Earn, Price, Chg, Vol
                            result[ticker] = {
                                "dividend_yield": _parse_finviz_pct(cols[3].text.strip()),
                                "roa": _parse_finviz_pct(cols[4].text.strip()),
                                "roe": _parse_finviz_pct(cols[5].text.strip()),
                                "roi": _parse_finviz_pct(cols[6].text.strip()),
                                "current_ratio": _parse_finviz_float(cols[7].text.strip()),
                                "quick_ratio": _parse_finviz_float(cols[8].text.strip()),
                                "lt_debt_ratio": _parse_finviz_float(cols[9].text.strip()),
                                "debt_ratio": _parse_finviz_float(cols[10].text.strip()),
                                "gross_margin": _parse_finviz_pct(cols[11].text.strip()),
                                "operating_margin": _parse_finviz_pct(cols[12].text.strip()),
                                "profit_margin": _parse_finviz_pct(cols[13].text.strip()),
                            }
                    except Exception:
                        continue

                if len(rows) < 20 or page >= 30:
                    break
                page += 1
                await asyncio.sleep(0.3)  # 요청 간격

            print(f"[Finviz v=161 Financial] S&P 500 재무데이터: {len(result)}개 종목 ({page}페이지)")

    except Exception as e:
        print(f"[Finviz v=161 Financial] 오류: {e}")
        import traceback
        traceback.print_exc()

    return result


async def fetch_sp500_valuation() -> Dict[str, Dict]:
    """
    Finviz Valuation 뷰(v=121)에서 PER, PBR 데이터 수집
    Returns: {"AAPL": {"per": 28.5, "pbr": 45.2}, ...}

    v=121 컬럼 순서:
    No., Ticker, P/E, Fwd P/E, PEG, P/S, P/B, P/C, P/FCF,
    EPS This Y, EPS Next Y, EPS Past 5Y, EPS Next 5Y, Sales Past 5Y, Price, Change, Volume
    """
    from bs4 import BeautifulSoup

    result = {}

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            page = 1

            while True:
                offset = (page - 1) * 20 + 1
                url = f"https://finviz.com/screener.ashx?v=121&f=idx_sp500&o=-marketcap&r={offset}"

                r = await client.get(url, headers=FINVIZ_HEADERS)
                if r.status_code != 200:
                    print(f"[Finviz v=121 Valuation] 페이지 {page} 실패: {r.status_code}")
                    break

                soup = BeautifulSoup(r.text, 'lxml')
                rows = soup.select('table.screener-body-table-nw tr[valign="top"]')
                if not rows:
                    rows = soup.select('tr.styled-row')
                if not rows:
                    break

                for row in rows:
                    cols = row.find_all('td')
                    if len(cols) < 10:
                        continue

                    try:
                        ticker_link = cols[1].find('a')
                        ticker = ticker_link.text.strip() if ticker_link else ""

                        if ticker:
                            # v=121 컬럼: No, Ticker, MktCap, P/E, Fwd P/E, PEG, P/S, P/B, ...
                            result[ticker] = {
                                "per": _parse_finviz_float(cols[3].text.strip()),
                                "pbr": _parse_finviz_float(cols[7].text.strip()),
                            }
                    except Exception:
                        continue

                if len(rows) < 20 or page >= 30:
                    break
                page += 1
                await asyncio.sleep(0.3)

            print(f"[Finviz v=121 Valuation] S&P 500 PER/PBR: {len(result)}개 종목 ({page}페이지)")

    except Exception as e:
        print(f"[Finviz v=121 Valuation] 오류: {e}")
        import traceback
        traceback.print_exc()

    return result


async def fetch_finviz_changes() -> Dict[str, float]:
    """
    Finviz 히트맵 API에서 실시간 등락률 수집
    Returns: {"AAPL": -7.16, "MSFT": -0.75, ...}
    """
    result = {}

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            headers = {"User-Agent": "Mozilla/5.0"}
            r = await client.get(
                "https://finviz.com/api/map_perf.ashx?t=sec",
                headers=headers
            )
            if r.status_code != 200:
                print(f"[Finviz] 히트맵 API 실패: {r.status_code}")
                return result

            data = r.json()

            if isinstance(data, dict):
                if "nodes" in data:
                    result = data["nodes"]
                else:
                    sample_key = next(iter(data), "")
                    if sample_key.isupper() and len(sample_key) <= 5:
                        result = data

            print(f"[Finviz] 등락률: {len(result)}개 종목")

    except Exception as e:
        print(f"[Finviz] 히트맵 오류: {e}")

    return result


# 필터 키 정의 (US 전용) - Finviz v=141/v=161 기반 재무 필터
US_FILTER_KEYS = [
    "sector", "market_cap", "change_pct",
    # Valuation 필터 (Finviz v=141)
    "per", "pbr",
    # 재무 필터 (Finviz v=161)
    "roe", "roa", "roi",
    "operating_margin", "gross_margin", "profit_margin",
    "debt_ratio", "current_ratio", "dividend_yield",
]

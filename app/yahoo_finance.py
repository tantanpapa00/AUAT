"""
Yahoo Finance 데이터 수집 모듈
- 미국 주요 지수 (S&P500, 나스닥, 다우, 러셀)
- 미국 개별 종목 시세
- 미국 종목 차트 데이터
"""

import httpx
from typing import Optional, List, Dict, Any
from datetime import datetime

# 공통 헤더
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
}

# 타임아웃 설정
TIMEOUT = 10.0

# 주요 미국 지수 심볼
US_INDICES = {
    "^GSPC": "S&P 500",
    "^IXIC": "NASDAQ",
    "^DJI": "Dow Jones",
    "^RUT": "Russell 2000",
}

# 시가총액 상위 미국 종목
TOP_US_STOCKS = [
    "AAPL", "MSFT", "GOOGL", "AMZN", "NVDA", "META", "TSLA", "BRK-B",
    "UNH", "XOM", "JPM", "JNJ", "V", "PG", "MA", "HD", "CVX", "MRK",
    "ABBV", "LLY"
]


async def get_us_indices() -> Dict[str, Dict[str, Any]]:
    """미국 주요 지수 (S&P500, 나스닥, 다우, 러셀)"""
    results = {}

    async with httpx.AsyncClient(timeout=TIMEOUT) as client:
        for symbol, name in US_INDICES.items():
            try:
                url = f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}?interval=1d&range=1d"
                resp = await client.get(url, headers=HEADERS)
                data = resp.json()

                if "chart" in data and "result" in data["chart"] and data["chart"]["result"]:
                    result = data["chart"]["result"][0]
                    meta = result.get("meta", {})

                    current = meta.get("regularMarketPrice", 0)
                    prev_close = meta.get("chartPreviousClose", meta.get("previousClose", current))
                    change = current - prev_close
                    change_pct = (change / prev_close * 100) if prev_close else 0

                    results[symbol] = {
                        "name": name,
                        "symbol": symbol,
                        "current": round(current, 2),
                        "change": round(change, 2),
                        "change_percent": round(change_pct, 2),
                    }
                else:
                    results[symbol] = {"name": name, "symbol": symbol, "current": 0, "error": "No data"}

            except Exception as e:
                print(f"[YahooFinance] {symbol} 조회 실패: {e}")
                results[symbol] = {"name": name, "symbol": symbol, "current": 0, "error": str(e)}

    return results


async def get_stock_price_us(symbol: str) -> Dict[str, Any]:
    """미국 개별 종목 시세"""
    try:
        async with httpx.AsyncClient(timeout=TIMEOUT) as client:
            url = f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}?interval=1d&range=5d"
            resp = await client.get(url, headers=HEADERS)
            data = resp.json()

            if "chart" in data and "result" in data["chart"] and data["chart"]["result"]:
                result = data["chart"]["result"][0]
                meta = result.get("meta", {})
                quote = result.get("indicators", {}).get("quote", [{}])[0]

                current = meta.get("regularMarketPrice", 0)
                prev_close = meta.get("chartPreviousClose", meta.get("previousClose", current))
                change = current - prev_close
                change_pct = (change / prev_close * 100) if prev_close else 0

                # 오늘 시가/고가/저가
                opens = quote.get("open", [])
                highs = quote.get("high", [])
                lows = quote.get("low", [])
                volumes = quote.get("volume", [])

                open_price = opens[-1] if opens and opens[-1] else 0
                high = highs[-1] if highs and highs[-1] else 0
                low = lows[-1] if lows and lows[-1] else 0
                volume = volumes[-1] if volumes and volumes[-1] else 0

                # 52주 최고/최저
                high52 = meta.get("fiftyTwoWeekHigh", 0)
                low52 = meta.get("fiftyTwoWeekLow", 0)

                return {
                    "symbol": symbol,
                    "name": meta.get("shortName", symbol),
                    "price": round(current, 2),
                    "change": round(change, 2),
                    "change_percent": round(change_pct, 2),
                    "open": round(open_price, 2) if open_price else 0,
                    "high": round(high, 2) if high else 0,
                    "low": round(low, 2) if low else 0,
                    "volume": int(volume) if volume else 0,
                    "high52": round(high52, 2),
                    "low52": round(low52, 2),
                    "market_cap": meta.get("marketCap", 0),
                    "currency": meta.get("currency", "USD"),
                }
            else:
                return {"symbol": symbol, "name": symbol, "price": 0, "error": "No data"}

    except Exception as e:
        print(f"[YahooFinance] {symbol} 시세 조회 실패: {e}")
        return {"symbol": symbol, "name": symbol, "price": 0, "error": str(e)}


async def get_stock_chart_us(symbol: str, period: str = "1y") -> List[Dict[str, Any]]:
    """미국 종목 차트 데이터"""
    # period: 1d, 5d, 1mo, 3mo, 6mo, 1y, 2y, 5y, max
    # interval: 1m, 2m, 5m, 15m, 30m, 60m, 90m, 1h, 1d, 5d, 1wk, 1mo

    interval_map = {
        "1d": ("1d", "5m"),
        "5d": ("5d", "15m"),
        "1mo": ("1mo", "1d"),
        "3mo": ("3mo", "1d"),
        "1y": ("1y", "1d"),
    }

    range_val, interval = interval_map.get(period, ("1y", "1d"))

    try:
        async with httpx.AsyncClient(timeout=TIMEOUT) as client:
            url = f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}?interval={interval}&range={range_val}"
            resp = await client.get(url, headers=HEADERS)
            data = resp.json()

            if "chart" in data and "result" in data["chart"] and data["chart"]["result"]:
                result = data["chart"]["result"][0]
                timestamps = result.get("timestamp", [])
                quote = result.get("indicators", {}).get("quote", [{}])[0]

                opens = quote.get("open", [])
                highs = quote.get("high", [])
                lows = quote.get("low", [])
                closes = quote.get("close", [])
                volumes = quote.get("volume", [])

                chart_data = []
                for i, ts in enumerate(timestamps):
                    if ts and closes[i]:
                        chart_data.append({
                            "time": ts,
                            "date": datetime.fromtimestamp(ts).strftime("%Y-%m-%d"),
                            "open": round(opens[i], 2) if opens[i] else 0,
                            "high": round(highs[i], 2) if highs[i] else 0,
                            "low": round(lows[i], 2) if lows[i] else 0,
                            "close": round(closes[i], 2) if closes[i] else 0,
                            "volume": int(volumes[i]) if volumes[i] else 0,
                        })

                return chart_data
            else:
                return []

    except Exception as e:
        print(f"[YahooFinance] {symbol} 차트 조회 실패: {e}")
        return []


async def get_top_us_stocks() -> List[Dict[str, Any]]:
    """시가총액 상위 미국 종목 20개 시세"""
    results = []

    async with httpx.AsyncClient(timeout=TIMEOUT) as client:
        for symbol in TOP_US_STOCKS:
            try:
                stock = await get_stock_price_us(symbol)
                if not stock.get("error"):
                    results.append(stock)
            except Exception as e:
                print(f"[YahooFinance] {symbol} 조회 실패: {e}")

    # 시가총액 순 정렬
    results.sort(key=lambda x: x.get("market_cap", 0), reverse=True)
    return results


async def get_crypto_prices() -> List[Dict[str, Any]]:
    """주요 암호화폐 시세 (Yahoo Finance)"""
    symbols = ["BTC-USD", "ETH-USD", "SOL-USD", "XRP-USD", "ADA-USD", "DOGE-USD"]
    results = []

    async with httpx.AsyncClient(timeout=TIMEOUT) as client:
        for symbol in symbols:
            try:
                url = f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}?interval=1d&range=1d"
                resp = await client.get(url, headers=HEADERS)
                data = resp.json()

                if "chart" in data and "result" in data["chart"] and data["chart"]["result"]:
                    result = data["chart"]["result"][0]
                    meta = result.get("meta", {})

                    current = meta.get("regularMarketPrice", 0)
                    prev_close = meta.get("chartPreviousClose", current)
                    change = current - prev_close
                    change_pct = (change / prev_close * 100) if prev_close else 0

                    results.append({
                        "symbol": symbol.replace("-USD", ""),
                        "name": meta.get("shortName", symbol),
                        "price": round(current, 2),
                        "change": round(change, 2),
                        "change_percent": round(change_pct, 2),
                        "volume": meta.get("regularMarketVolume", 0),
                        "market_cap": meta.get("marketCap", 0),
                    })

            except Exception as e:
                print(f"[YahooFinance] {symbol} 조회 실패: {e}")

    return results


# =============================================================================
# Phase 9+: 해외 종목 재무제표 + 투자지표 (국내와 동일 구조)
# =============================================================================

async def get_stock_statement_us(ticker: str, period_type: str = "annual") -> dict:
    """
    해외 종목 상세 재무제표 (국내와 동일 구조)
    period_type: annual(연간), quarter(분기)
    데이터 소스: yfinance
    """
    import yfinance as yf

    result = {
        "code": ticker,
        "period_type": period_type,
        "periods": [],
        "rows": [],
        "health": {
            "score": 0,
            "grade": "C",
            "grade_label": "보통",
            "debt_ratio": None,
            "roe": None,
            "operating_margin": None,
            "current_ratio": None,
        }
    }

    try:
        stock = yf.Ticker(ticker)
        info = stock.info or {}

        # 재무제표 가져오기 (분기/연간)
        if period_type == "quarter":
            income_stmt = stock.quarterly_income_stmt
            balance_sheet = stock.quarterly_balance_sheet
        else:
            income_stmt = stock.income_stmt
            balance_sheet = stock.balance_sheet

        if income_stmt is None or income_stmt.empty:
            return result

        # 기간 목록 (최근 4개)
        periods = []
        for col in income_stmt.columns[:4]:
            if hasattr(col, 'strftime'):
                periods.append(col.strftime('%Y.%m'))
            else:
                periods.append(str(col)[:7])
        result["periods"] = periods

        # 값 추출 헬퍼
        def get_row_values(df, row_names):
            for name in row_names:
                if name in df.index:
                    vals = []
                    for col in df.columns[:4]:
                        try:
                            v = df.loc[name, col]
                            if v is not None and not (hasattr(v, '__float__') and str(v) == 'nan'):
                                vals.append(float(v) / 1_000_000)  # 백만 달러 단위
                            else:
                                vals.append(None)
                        except:
                            vals.append(None)
                    return vals
            return [None] * 4

        # 손익계산서 항목
        revenue = get_row_values(income_stmt, ['Total Revenue', 'Revenue'])
        operating_income = get_row_values(income_stmt, ['Operating Income', 'EBIT'])
        net_income = get_row_values(income_stmt, ['Net Income', 'Net Income Common Stockholders'])
        gross_profit = get_row_values(income_stmt, ['Gross Profit'])

        # 비율 계산
        def calc_margin(numerator, denominator):
            margins = []
            for n, d in zip(numerator, denominator):
                if n is not None and d is not None and d != 0:
                    margins.append(round((n / d) * 100, 1))
                else:
                    margins.append(None)
            return margins

        operating_margin = calc_margin(operating_income, revenue)
        net_margin = calc_margin(net_income, revenue)

        # 재무상태표에서 비율 계산
        debt_ratio = None
        current_ratio = None
        roe = None

        if balance_sheet is not None and not balance_sheet.empty:
            def get_latest(df, row_names):
                for name in row_names:
                    if name in df.index:
                        try:
                            v = df.loc[name, df.columns[0]]
                            if v is not None and str(v) != 'nan':
                                return float(v)
                        except:
                            pass
                return None

            total_debt = get_latest(balance_sheet, ['Total Debt', 'Long Term Debt'])
            total_equity = get_latest(balance_sheet, ['Total Stockholder Equity', 'Stockholders Equity', 'Total Equity Gross Minority Interest'])
            current_assets = get_latest(balance_sheet, ['Current Assets', 'Total Current Assets'])
            current_liabilities = get_latest(balance_sheet, ['Current Liabilities', 'Total Current Liabilities'])

            if total_debt and total_equity and total_equity != 0:
                debt_ratio = round((total_debt / total_equity) * 100, 1)

            if current_assets and current_liabilities and current_liabilities != 0:
                current_ratio = round((current_assets / current_liabilities) * 100, 1)

            # ROE 계산
            latest_net_income = net_income[0] if net_income and net_income[0] else None
            if latest_net_income and total_equity and total_equity != 0:
                roe = round((latest_net_income * 1_000_000 / total_equity) * 100, 1)

        # info에서 가져오기 (yfinance 기본 제공)
        if debt_ratio is None:
            debt_ratio = info.get('debtToEquity')
        if roe is None:
            roe_val = info.get('returnOnEquity')
            if roe_val:
                roe = round(roe_val * 100, 1)
        if current_ratio is None:
            cr_val = info.get('currentRatio')
            if cr_val:
                current_ratio = round(cr_val * 100, 1)

        op_margin_latest = operating_margin[0] if operating_margin and operating_margin[0] else None
        if op_margin_latest is None:
            om_val = info.get('operatingMargins')
            if om_val:
                op_margin_latest = round(om_val * 100, 1)

        # Rows 구성
        result["rows"] = [
            {"label": "매출액", "values": revenue, "unit": "$M"},
            {"label": "영업이익", "values": operating_income, "unit": "$M"},
            {"label": "당기순이익", "values": net_income, "unit": "$M"},
            {"label": "매출총이익", "values": gross_profit, "unit": "$M"},
            {"label": "영업이익률", "values": operating_margin, "unit": "%"},
            {"label": "순이익률", "values": net_margin, "unit": "%"},
        ]

        # 건전성 데이터
        result["health"]["debt_ratio"] = debt_ratio
        result["health"]["roe"] = roe
        result["health"]["operating_margin"] = op_margin_latest
        result["health"]["current_ratio"] = current_ratio

        # 건전성 점수 계산 (국내와 동일 로직)
        score = 0

        # 부채비율 (낮을수록 좋음)
        if debt_ratio is not None:
            if debt_ratio < 50: score += 25
            elif debt_ratio < 100: score += 20
            elif debt_ratio < 150: score += 15
            elif debt_ratio < 200: score += 10
            else: score += 5

        # ROE (높을수록 좋음)
        if roe is not None:
            if roe > 15: score += 25
            elif roe > 10: score += 20
            elif roe > 5: score += 15
            elif roe > 0: score += 10
            else: score += 5

        # 영업이익률 (높을수록 좋음)
        if op_margin_latest is not None:
            if op_margin_latest > 20: score += 25
            elif op_margin_latest > 10: score += 20
            elif op_margin_latest > 5: score += 15
            elif op_margin_latest > 0: score += 10
            else: score += 5

        # 유동비율 (높을수록 좋음)
        if current_ratio is not None:
            if current_ratio > 200: score += 25
            elif current_ratio > 150: score += 20
            elif current_ratio > 100: score += 15
            elif current_ratio > 50: score += 10
            else: score += 5

        result["health"]["score"] = score

        # 등급 결정
        if score >= 85:
            result["health"]["grade"] = "A+"
            result["health"]["grade_label"] = "매우우수"
        elif score >= 70:
            result["health"]["grade"] = "A"
            result["health"]["grade_label"] = "우수"
        elif score >= 55:
            result["health"]["grade"] = "B"
            result["health"]["grade_label"] = "양호"
        elif score >= 40:
            result["health"]["grade"] = "C"
            result["health"]["grade_label"] = "보통"
        elif score >= 25:
            result["health"]["grade"] = "D"
            result["health"]["grade_label"] = "주의"
        else:
            result["health"]["grade"] = "F"
            result["health"]["grade_label"] = "위험"

    except Exception as e:
        print(f"[YahooFinance] get_stock_statement_us error for {ticker}: {e}")
        import traceback
        traceback.print_exc()

    return result


async def get_invest_indicators_us(ticker: str) -> dict:
    """
    해외 종목 투자지표 4카테고리 (국내와 동일 구조)
    성장성/수익성/안정성/밸류에이션
    데이터 소스: yfinance
    """
    import yfinance as yf

    result = {
        "code": ticker,
        "growth": {"grade": "C", "grade_label": "보통", "items": {}},
        "profitability": {"grade": "C", "grade_label": "보통", "items": {}},
        "stability": {"grade": "C", "grade_label": "보통", "items": {}},
        "valuation": {"grade": "C", "grade_label": "보통", "items": {}},
    }

    try:
        stock = yf.Ticker(ticker)
        info = stock.info or {}

        # 성장성 지표
        growth_items = {}
        rev_growth = info.get('revenueGrowth')
        if rev_growth:
            growth_items['매출성장률'] = round(rev_growth * 100, 1)
        earn_growth = info.get('earningsGrowth')
        if earn_growth:
            growth_items['이익성장률'] = round(earn_growth * 100, 1)
        eps_growth = info.get('earningsQuarterlyGrowth')
        if eps_growth:
            growth_items['EPS성장률'] = round(eps_growth * 100, 1)

        result["growth"]["items"] = growth_items
        result["growth"]["grade"], result["growth"]["grade_label"] = _calc_growth_grade_us(growth_items)

        # 수익성 지표
        prof_items = {}
        roe = info.get('returnOnEquity')
        if roe:
            prof_items['ROE'] = round(roe * 100, 1)
        roa = info.get('returnOnAssets')
        if roa:
            prof_items['ROA'] = round(roa * 100, 1)
        op_margin = info.get('operatingMargins')
        if op_margin:
            prof_items['영업이익률'] = round(op_margin * 100, 1)
        net_margin = info.get('profitMargins')
        if net_margin:
            prof_items['순이익률'] = round(net_margin * 100, 1)

        result["profitability"]["items"] = prof_items
        result["profitability"]["grade"], result["profitability"]["grade_label"] = _calc_profitability_grade_us(prof_items)

        # 안정성 지표
        stab_items = {}
        debt_equity = info.get('debtToEquity')
        if debt_equity:
            stab_items['부채비율'] = round(debt_equity, 1)
        current_ratio = info.get('currentRatio')
        if current_ratio:
            stab_items['유동비율'] = round(current_ratio * 100, 1)
        quick_ratio = info.get('quickRatio')
        if quick_ratio:
            stab_items['당좌비율'] = round(quick_ratio * 100, 1)

        result["stability"]["items"] = stab_items
        result["stability"]["grade"], result["stability"]["grade_label"] = _calc_stability_grade_us(stab_items)

        # 밸류에이션 지표
        val_items = {}
        per = info.get('trailingPE')
        if per:
            val_items['PER'] = round(per, 1)
        forward_pe = info.get('forwardPE')
        if forward_pe:
            val_items['Forward PER'] = round(forward_pe, 1)
        pbr = info.get('priceToBook')
        if pbr:
            val_items['PBR'] = round(pbr, 2)
        div_yield = info.get('dividendYield')
        if div_yield:
            val_items['배당수익률'] = round(div_yield * 100, 2)

        result["valuation"]["items"] = val_items
        result["valuation"]["grade"], result["valuation"]["grade_label"] = _calc_valuation_grade_us(val_items)

    except Exception as e:
        print(f"[YahooFinance] get_invest_indicators_us error for {ticker}: {e}")
        import traceback
        traceback.print_exc()

    return result


def _calc_growth_grade_us(items: dict) -> tuple:
    """성장성 등급 계산"""
    if not items:
        return "C", "보통"

    score = 0
    count = 0

    rev_growth = items.get('매출성장률')
    if rev_growth is not None:
        count += 1
        if rev_growth > 20: score += 25
        elif rev_growth > 10: score += 20
        elif rev_growth > 5: score += 15
        elif rev_growth > 0: score += 10
        else: score += 5

    earn_growth = items.get('이익성장률') or items.get('EPS성장률')
    if earn_growth is not None:
        count += 1
        if earn_growth > 20: score += 25
        elif earn_growth > 10: score += 20
        elif earn_growth > 5: score += 15
        elif earn_growth > 0: score += 10
        else: score += 5

    if count == 0:
        return "C", "보통"

    avg = score / count
    if avg >= 23: return "A+", "매우우수"
    if avg >= 18: return "A", "우수"
    if avg >= 13: return "B", "양호"
    if avg >= 8: return "C", "보통"
    return "D", "주의"


def _calc_profitability_grade_us(items: dict) -> tuple:
    """수익성 등급 계산"""
    if not items:
        return "C", "보통"

    score = 0
    count = 0

    roe = items.get('ROE')
    if roe is not None:
        count += 1
        if roe > 20: score += 25
        elif roe > 15: score += 20
        elif roe > 10: score += 15
        elif roe > 5: score += 10
        else: score += 5

    op_margin = items.get('영업이익률')
    if op_margin is not None:
        count += 1
        if op_margin > 25: score += 25
        elif op_margin > 15: score += 20
        elif op_margin > 10: score += 15
        elif op_margin > 5: score += 10
        else: score += 5

    if count == 0:
        return "C", "보통"

    avg = score / count
    if avg >= 23: return "A+", "매우우수"
    if avg >= 18: return "A", "우수"
    if avg >= 13: return "B", "양호"
    if avg >= 8: return "C", "보통"
    return "D", "주의"


def _calc_stability_grade_us(items: dict) -> tuple:
    """안정성 등급 계산"""
    if not items:
        return "C", "보통"

    score = 0
    count = 0

    debt = items.get('부채비율')
    if debt is not None:
        count += 1
        if debt < 50: score += 25
        elif debt < 100: score += 20
        elif debt < 150: score += 15
        elif debt < 200: score += 10
        else: score += 5

    current = items.get('유동비율')
    if current is not None:
        count += 1
        if current > 200: score += 25
        elif current > 150: score += 20
        elif current > 100: score += 15
        elif current > 50: score += 10
        else: score += 5

    if count == 0:
        return "C", "보통"

    avg = score / count
    if avg >= 23: return "A+", "매우우수"
    if avg >= 18: return "A", "우수"
    if avg >= 13: return "B", "양호"
    if avg >= 8: return "C", "보통"
    return "D", "주의"


def _calc_valuation_grade_us(items: dict) -> tuple:
    """밸류에이션 등급 계산"""
    if not items:
        return "C", "보통"

    score = 0
    count = 0

    per = items.get('PER')
    if per is not None:
        count += 1
        if per < 10: score += 25
        elif per < 15: score += 20
        elif per < 20: score += 15
        elif per < 30: score += 10
        else: score += 5

    pbr = items.get('PBR')
    if pbr is not None:
        count += 1
        if pbr < 1: score += 25
        elif pbr < 2: score += 20
        elif pbr < 3: score += 15
        elif pbr < 5: score += 10
        else: score += 5

    if count == 0:
        return "C", "보통"

    avg = score / count
    if avg >= 23: return "A+", "매우우수"
    if avg >= 18: return "A", "우수"
    if avg >= 13: return "B", "양호"
    if avg >= 8: return "C", "보통"
    return "D", "주의"

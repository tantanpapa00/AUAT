"""
BBooster 데이터 제공 모듈
pykrx: 국내 주식/ETF/업종/투자자
yfinance: 해외 주식/지수
httpx: 코인 거래소 API
"""
import asyncio
from datetime import datetime, timedelta
from pykrx import stock as krx
import yfinance as yf
import httpx
import traceback

# ===== 캐싱 =====
_cache = {}

def _cached(key, ttl_seconds=3600):
    """캐시에서 데이터 가져오기. 없거나 만료되면 None"""
    if key in _cache:
        data, ts = _cache[key]
        if (datetime.now() - ts).total_seconds() < ttl_seconds:
            return data
    return None

def _set_cache(key, data):
    _cache[key] = (data, datetime.now())

def _get_today():
    """오늘 날짜 YYYYMMDD"""
    return datetime.now().strftime("%Y%m%d")

def _get_date_ago(days):
    """N일 전 날짜"""
    return (datetime.now() - timedelta(days=days)).strftime("%Y%m%d")

# ===== 국내 시장 =====

async def get_kr_market_overview():
    """국내 시장 개요: 지수 + 투자자동향 + 업종 TOP 10"""
    cached = _cached("kr_overview", 300)  # 5분 캐싱
    if cached:
        return cached

    try:
        today = _get_today()
        yesterday = _get_date_ago(1)

        result = await asyncio.to_thread(_fetch_kr_overview, today, yesterday)
        _set_cache("kr_overview", result)
        return result
    except Exception as e:
        print(f"[DataProvider] KR overview error: {e}")
        traceback.print_exc()
        return {"error": str(e), "kospi": {}, "kosdaq": {}, "investors": {}, "sectors": []}

def _fetch_kr_overview(today, yesterday):
    """동기 함수 - pykrx 호출"""
    result = {}

    # 코스피 지수
    try:
        kospi_df = krx.get_index_ohlcv(yesterday, today, "1001")
        if not kospi_df.empty:
            last = kospi_df.iloc[-1]
            prev = kospi_df.iloc[-2] if len(kospi_df) > 1 else last
            result["kospi"] = {
                "name": "코스피",
                "current": float(last["종가"]),
                "change": float(last["종가"] - prev["종가"]) if len(kospi_df) > 1 else 0,
                "change_percent": float(last["등락률"]) if "등락률" in last else 0,
                "volume": int(last["거래량"]) if "거래량" in last else 0
            }
        else:
            result["kospi"] = {"name": "코스피", "current": 0, "change": 0, "change_percent": 0}
    except Exception as e:
        print(f"[DataProvider] KOSPI error: {e}")
        result["kospi"] = {"name": "코스피", "current": 0, "change": 0, "change_percent": 0}

    # 코스닥 지수
    try:
        kosdaq_df = krx.get_index_ohlcv(yesterday, today, "2001")
        if not kosdaq_df.empty:
            last = kosdaq_df.iloc[-1]
            prev = kosdaq_df.iloc[-2] if len(kosdaq_df) > 1 else last
            result["kosdaq"] = {
                "name": "코스닥",
                "current": float(last["종가"]),
                "change": float(last["종가"] - prev["종가"]) if len(kosdaq_df) > 1 else 0,
                "change_percent": float(last["등락률"]) if "등락률" in last else 0,
                "volume": int(last["거래량"]) if "거래량" in last else 0
            }
        else:
            result["kosdaq"] = {"name": "코스닥", "current": 0, "change": 0, "change_percent": 0}
    except Exception as e:
        print(f"[DataProvider] KOSDAQ error: {e}")
        result["kosdaq"] = {"name": "코스닥", "current": 0, "change": 0, "change_percent": 0}

    # 투자자별 매매동향
    try:
        inv_df = krx.get_market_trading_value_by_investor(today, today, "KOSPI")
        if not inv_df.empty:
            result["investors"] = {
                "foreign": int(inv_df.loc["외국인합계"]["순매수"]) if "외국인합계" in inv_df.index else 0,
                "institution": int(inv_df.loc["기관합계"]["순매수"]) if "기관합계" in inv_df.index else 0,
                "individual": int(inv_df.loc["개인"]["순매수"]) if "개인" in inv_df.index else 0
            }
        else:
            result["investors"] = {"foreign": 0, "institution": 0, "individual": 0}
    except Exception as e:
        print(f"[DataProvider] Investor error: {e}")
        result["investors"] = {"foreign": 0, "institution": 0, "individual": 0}

    # 업종별 등락률 TOP 10
    try:
        sector_list = []
        tickers = krx.get_index_ticker_list(today, market="KOSPI")
        for ticker in tickers[:20]:
            try:
                name = krx.get_index_ticker_name(ticker)
                ohlcv = krx.get_index_ohlcv(yesterday, today, ticker)
                if not ohlcv.empty:
                    last = ohlcv.iloc[-1]
                    sector_list.append({
                        "name": name,
                        "change_percent": float(last["등락률"]) if "등락률" in last else 0,
                        "volume": int(last["거래량"]) if "거래량" in last else 0
                    })
            except:
                continue
        sector_list.sort(key=lambda x: x["change_percent"], reverse=True)
        result["sectors"] = sector_list[:10]
    except Exception as e:
        print(f"[DataProvider] Sector error: {e}")
        result["sectors"] = []

    return result

async def get_kr_all_stocks():
    """전종목 시세 (RS/밸류에이션/신고가 계산용)"""
    cached = _cached("kr_all_stocks", 3600)  # 1시간 캐싱
    if cached:
        return cached

    try:
        today = _get_today()
        df = await asyncio.to_thread(krx.get_market_ohlcv, today, market="ALL")
        if df.empty:
            yesterday = _get_date_ago(1)
            df = await asyncio.to_thread(krx.get_market_ohlcv, yesterday, market="ALL")

        stocks = []
        for ticker, row in df.iterrows():
            stocks.append({
                "code": ticker,
                "name": row.get("종목명", ticker),
                "close": int(row.get("종가", 0)),
                "change_percent": float(row.get("등락률", 0)),
                "volume": int(row.get("거래량", 0)),
                "market_cap": int(row.get("시가총액", 0)),
                "open": int(row.get("시가", 0)),
                "high": int(row.get("고가", 0)),
                "low": int(row.get("저가", 0))
            })

        _set_cache("kr_all_stocks", stocks)
        return stocks
    except Exception as e:
        print(f"[DataProvider] All stocks error: {e}")
        traceback.print_exc()
        return []

# ===== RS 순위 =====

async def get_rs_ranking(market="ALL", limit=100):
    """RS 순위 계산"""
    cache_key = f"rs_{market}_{limit}"
    cached = _cached(cache_key, 3600)  # 1시간 캐싱
    if cached:
        return cached

    try:
        result = await asyncio.to_thread(_calc_rs_ranking, market, limit)
        _set_cache(cache_key, result)
        return result
    except Exception as e:
        print(f"[DataProvider] RS error: {e}")
        traceback.print_exc()
        return []

def _calc_rs_ranking(market, limit):
    """RS 계산 (동기)"""
    today = _get_today()
    date_1m = _get_date_ago(30)
    date_3m = _get_date_ago(90)
    date_6m = _get_date_ago(180)

    # 전종목 현재 시세
    mkt = "ALL" if market.upper() == "ALL" else market.upper()
    try:
        today_df = krx.get_market_ohlcv(today, market=mkt)
        if today_df.empty:
            today_df = krx.get_market_ohlcv(_get_date_ago(1), market=mkt)
    except:
        return []

    if today_df.empty:
        return []

    # 과거 시세
    try:
        df_1m = krx.get_market_ohlcv(date_1m, market=mkt)
        df_3m = krx.get_market_ohlcv(date_3m, market=mkt)
        df_6m = krx.get_market_ohlcv(date_6m, market=mkt)
    except:
        return []

    stocks = []
    for ticker in today_df.index:
        try:
            name = today_df.loc[ticker].get("종목명", ticker) if hasattr(today_df.loc[ticker], 'get') else ticker
            close = float(today_df.loc[ticker]["종가"]) if "종가" in today_df.columns else 0
            cap = int(today_df.loc[ticker]["시가총액"]) if "시가총액" in today_df.columns else 0
            change = float(today_df.loc[ticker]["등락률"]) if "등락률" in today_df.columns else 0

            if close == 0 or cap < 200000000000:  # 시총 2000억 미만 제외
                continue

            # 수익률 계산
            ret_1m = 0
            ret_3m = 0
            ret_6m = 0

            if ticker in df_1m.index:
                prev_close = float(df_1m.loc[ticker]["종가"]) if "종가" in df_1m.columns else 0
                if prev_close > 0:
                    ret_1m = ((close / prev_close) - 1) * 100

            if ticker in df_3m.index:
                prev_close = float(df_3m.loc[ticker]["종가"]) if "종가" in df_3m.columns else 0
                if prev_close > 0:
                    ret_3m = ((close / prev_close) - 1) * 100

            if ticker in df_6m.index:
                prev_close = float(df_6m.loc[ticker]["종가"]) if "종가" in df_6m.columns else 0
                if prev_close > 0:
                    ret_6m = ((close / prev_close) - 1) * 100

            stocks.append({
                "code": ticker,
                "name": name,
                "market": "KOSPI" if mkt in ["ALL", "KOSPI"] else "KOSDAQ",
                "price": close,
                "change": change,
                "ret_1m": ret_1m,
                "ret_3m": ret_3m,
                "ret_6m": ret_6m
            })
        except Exception as e:
            continue

    # 각 기간별 백분위 계산
    for period in ["ret_1m", "ret_3m", "ret_6m"]:
        sorted_list = sorted(stocks, key=lambda x: x[period])
        total = len(sorted_list)
        for i, s in enumerate(sorted_list):
            s[f"rs_{period.replace('ret_', '')}"] = int((i / max(total - 1, 1)) * 99) + 1

    # RS 종합 = 가중평균
    for s in stocks:
        s["rs_total"] = int(s.get("rs_1m", 50) * 0.4 + s.get("rs_3m", 50) * 0.3 + s.get("rs_6m", 50) * 0.3)

    stocks.sort(key=lambda x: x["rs_total"], reverse=True)
    return stocks[:limit]

# ===== 52주 신고가 =====

async def get_new_high_stocks(limit=50):
    """52주 신고가 종목"""
    cached = _cached("new_high", 3600)
    if cached:
        return cached

    try:
        result = await asyncio.to_thread(_calc_new_high, limit)
        _set_cache("new_high", result)
        return result
    except Exception as e:
        print(f"[DataProvider] New high error: {e}")
        return []

def _calc_new_high(limit):
    today = _get_today()
    date_1y = _get_date_ago(365)

    try:
        today_df = krx.get_market_ohlcv(today, market="ALL")
        if today_df.empty:
            today_df = krx.get_market_ohlcv(_get_date_ago(1), market="ALL")
    except:
        return []

    if today_df.empty:
        return []

    results = []
    tickers = list(today_df.index)[:500]  # 상위 500개만 (속도)

    for ticker in tickers:
        try:
            name = today_df.loc[ticker].get("종목명", ticker) if hasattr(today_df.loc[ticker], 'get') else ticker
            close = float(today_df.loc[ticker]["종가"]) if "종가" in today_df.columns else 0
            high = float(today_df.loc[ticker]["고가"]) if "고가" in today_df.columns else 0
            cap = int(today_df.loc[ticker]["시가총액"]) if "시가총액" in today_df.columns else 0
            change = float(today_df.loc[ticker]["등락률"]) if "등락률" in today_df.columns else 0

            if close == 0 or cap < 200000000000:
                continue

            # 1년 최고가 가져오기
            year_df = krx.get_market_ohlcv(date_1y, today, ticker)
            if year_df.empty:
                continue

            year_high = float(year_df["고가"].max())

            if high >= year_high * 0.97:  # 52주 최고가의 97% 이상
                results.append({
                    "code": ticker,
                    "name": name,
                    "price": close,
                    "change": change,
                    "high_52w": year_high,
                    "distance": round((close / year_high - 1) * 100, 2),
                    "market_cap": cap
                })
        except:
            continue

    results.sort(key=lambda x: x["distance"], reverse=True)
    return results[:limit]

# ===== 밸류에이션 =====

async def get_valuation(market="ALL", limit=200):
    """PER/PBR 밸류에이션"""
    cache_key = f"valuation_{market}"
    cached = _cached(cache_key, 3600)
    if cached:
        return cached

    try:
        result = await asyncio.to_thread(_fetch_valuation, market, limit)
        _set_cache(cache_key, result)
        return result
    except Exception as e:
        print(f"[DataProvider] Valuation error: {e}")
        return []

def _fetch_valuation(market, limit):
    today = _get_today()
    mkt = "ALL" if market.upper() == "ALL" else market.upper()

    try:
        fund_df = krx.get_market_fundamental(today, market=mkt)
        if fund_df.empty:
            fund_df = krx.get_market_fundamental(_get_date_ago(1), market=mkt)
    except:
        return []

    if fund_df.empty:
        return []

    try:
        cap_df = krx.get_market_cap(today, market=mkt)
        if cap_df.empty:
            cap_df = krx.get_market_cap(_get_date_ago(1), market=mkt)
    except:
        cap_df = None

    results = []
    for ticker in fund_df.index:
        try:
            per = float(fund_df.loc[ticker]["PER"]) if "PER" in fund_df.columns else 0
            pbr = float(fund_df.loc[ticker]["PBR"]) if "PBR" in fund_df.columns else 0
            name = fund_df.loc[ticker].get("종목명", ticker) if hasattr(fund_df.loc[ticker], 'get') else ticker
            close = int(fund_df.loc[ticker]["종가"]) if "종가" in fund_df.columns else 0

            market_cap = 0
            if cap_df is not None and ticker in cap_df.index:
                market_cap = int(cap_df.loc[ticker]["시가총액"]) if "시가총액" in cap_df.columns else 0

            if per == 0 and pbr == 0:
                continue

            results.append({
                "code": ticker,
                "name": str(name),
                "price": close,
                "per": round(per, 2),
                "pbr": round(pbr, 2),
                "market_cap": market_cap,
                "market": market.upper()
            })
        except:
            continue

    results.sort(key=lambda x: x["per"] if x["per"] > 0 else 9999)
    return results[:limit]

# ===== ETF =====

async def get_etf_overview():
    """ETF 전종목 시세 + 섹터 분류"""
    cached = _cached("etf_overview", 1800)  # 30분 캐싱
    if cached:
        return cached

    try:
        result = await asyncio.to_thread(_fetch_etf)
        _set_cache("etf_overview", result)
        return result
    except Exception as e:
        print(f"[DataProvider] ETF error: {e}")
        traceback.print_exc()
        return {"sectors": {}, "all": []}

def _fetch_etf():
    today = _get_today()

    try:
        etf_df = krx.get_etf_ohlcv_by_ticker(today)
        if etf_df.empty:
            etf_df = krx.get_etf_ohlcv_by_ticker(_get_date_ago(1))
    except:
        return {"sectors": {}, "all": []}

    if etf_df.empty:
        return {"sectors": {}, "all": []}

    # 섹터 키워드 매핑
    sector_keywords = {
        "반도체": ["반도체", "필라델피아"],
        "2차전지": ["2차전지", "배터리", "리튬"],
        "AI": ["AI", "인공지능", "소프트웨어", "클라우드"],
        "바이오": ["바이오", "헬스", "제약", "의료"],
        "자동차": ["자동차", "전기차", "모빌리티", "자율주행"],
        "배당": ["배당", "고배당", "월배당"],
        "인버스/레버리지": ["인버스", "곱버스", "레버리지", "2X", "3X"],
        "해외(미국)": ["미국", "S&P", "나스닥", "NASDAQ", "글로벌", "선진국"],
        "원자재": ["금", "골드", "원유", "은", "원자재", "구리"],
        "채권": ["채권", "국채", "회사채", "금리"]
    }

    all_etfs = []
    sectors = {k: [] for k in sector_keywords}
    sectors["기타"] = []

    for ticker, row in etf_df.iterrows():
        name = row.get("종목명", ticker) if hasattr(row, 'get') else str(ticker)
        etf = {
            "code": str(ticker),
            "name": str(name),
            "close": int(row["종가"]) if "종가" in row else 0,
            "change_percent": float(row["등락률"]) if "등락률" in row else 0,
            "volume": int(row["거래량"]) if "거래량" in row else 0,
            "nav": float(row["NAV"]) if "NAV" in row else 0
        }
        all_etfs.append(etf)

        # 섹터 분류
        matched = False
        for sector, keywords in sector_keywords.items():
            if any(kw in str(name) for kw in keywords):
                sectors[sector].append(etf)
                matched = True
                break
        if not matched:
            sectors["기타"].append(etf)

    # 각 섹터 등락률순 정렬
    for sector in sectors:
        sectors[sector].sort(key=lambda x: x["change_percent"], reverse=True)

    return {"sectors": sectors, "all": all_etfs}

# ===== 해외 시장 =====

async def get_us_market_overview():
    """해외 시장 개요 - yfinance"""
    cached = _cached("us_overview", 600)  # 10분 캐싱
    if cached:
        return cached

    try:
        result = await asyncio.to_thread(_fetch_us_overview)
        _set_cache("us_overview", result)
        return result
    except Exception as e:
        print(f"[DataProvider] US overview error: {e}")
        traceback.print_exc()
        return {"indices": [], "stocks": []}

def _fetch_us_overview():
    indices = []
    for symbol, name in [("^GSPC", "S&P 500"), ("^IXIC", "나스닥"), ("^DJI", "다우존스"), ("^RUT", "러셀2000")]:
        try:
            t = yf.Ticker(symbol)
            info = t.fast_info
            last_price = float(info.last_price) if hasattr(info, 'last_price') else 0
            prev_close = float(info.previous_close) if hasattr(info, 'previous_close') else last_price
            indices.append({
                "name": name,
                "current": round(last_price, 2),
                "change": round(last_price - prev_close, 2),
                "change_percent": round((last_price / prev_close - 1) * 100, 2) if prev_close > 0 else 0
            })
        except Exception as e:
            print(f"[DataProvider] US index {symbol} error: {e}")
            indices.append({"name": name, "current": 0, "change": 0, "change_percent": 0})

    # 주요 미국 종목 TOP 20
    top_symbols = ["AAPL", "MSFT", "NVDA", "GOOGL", "AMZN", "META", "TSLA", "BRK-B", "JPM", "V",
                   "UNH", "MA", "HD", "PG", "COST", "ABBV", "CRM", "AVGO", "NFLX", "AMD"]
    stocks = []
    for symbol in top_symbols:
        try:
            t = yf.Ticker(symbol)
            info = t.fast_info
            last_price = float(info.last_price) if hasattr(info, 'last_price') else 0
            prev_close = float(info.previous_close) if hasattr(info, 'previous_close') else last_price
            last_volume = int(info.last_volume) if hasattr(info, 'last_volume') else 0
            stocks.append({
                "symbol": symbol,
                "price": round(last_price, 2),
                "change_percent": round((last_price / prev_close - 1) * 100, 2) if prev_close > 0 else 0,
                "volume": last_volume
            })
        except:
            stocks.append({"symbol": symbol, "price": 0, "change_percent": 0, "volume": 0})

    return {"indices": indices, "stocks": stocks}

# ===== 코인 =====

async def get_crypto_overview():
    """코인 시장 개요"""
    cached = _cached("crypto_overview", 60)  # 1분 캐싱
    if cached:
        return cached

    try:
        result = {}
        async with httpx.AsyncClient(timeout=10) as client:
            # Binance 시세
            try:
                r = await client.get("https://api.binance.com/api/v3/ticker/24hr")
                if r.status_code == 200:
                    data = r.json()
                    main_coins = {s["symbol"]: s for s in data if s["symbol"] in
                                  ["BTCUSDT","ETHUSDT","XRPUSDT","SOLUSDT","DOGEUSDT","ADAUSDT","AVAXUSDT","DOTUSDT","LINKUSDT","MATICUSDT"]}
                    result["binance"] = [{
                        "symbol": k.replace("USDT",""),
                        "price": float(v["lastPrice"]),
                        "change_24h": float(v["priceChangePercent"]),
                        "volume": float(v["quoteVolume"])
                    } for k, v in main_coins.items()]
                else:
                    result["binance"] = []
            except:
                result["binance"] = []

            # Upbit 시세
            try:
                r = await client.get("https://api.upbit.com/v1/ticker?markets=KRW-BTC,KRW-ETH,KRW-XRP,KRW-SOL,KRW-DOGE")
                if r.status_code == 200:
                    data = r.json()
                    result["upbit"] = [{
                        "symbol": d["market"].replace("KRW-",""),
                        "price": float(d["trade_price"]),
                        "change_24h": float(d["signed_change_rate"]) * 100,
                        "volume": float(d["acc_trade_price_24h"])
                    } for d in data]
                else:
                    result["upbit"] = []
            except:
                result["upbit"] = []

            # BTC 도미넌스 (CoinGecko)
            try:
                r = await client.get("https://api.coingecko.com/api/v3/global")
                if r.status_code == 200:
                    data = r.json()["data"]
                    result["btc_dominance"] = round(data["market_cap_percentage"]["btc"], 2)
                    result["total_market_cap"] = int(data["total_market_cap"]["usd"])
                else:
                    result["btc_dominance"] = 0
                    result["total_market_cap"] = 0
            except:
                result["btc_dominance"] = 0
                result["total_market_cap"] = 0

            # 김치 프리미엄 계산
            try:
                if result.get("binance") and result.get("upbit"):
                    btc_usd = next((c["price"] for c in result["binance"] if c["symbol"] == "BTC"), 0)
                    btc_krw = next((c["price"] for c in result["upbit"] if c["symbol"] == "BTC"), 0)
                    if btc_usd > 0:
                        # 환율 가져오기
                        r = await client.get("https://api.exchangerate-api.com/v4/latest/USD")
                        usd_krw = r.json()["rates"]["KRW"] if r.status_code == 200 else 1450
                        result["kimchi_premium"] = round((btc_krw / (btc_usd * usd_krw) - 1) * 100, 2)
                    else:
                        result["kimchi_premium"] = 0
                else:
                    result["kimchi_premium"] = 0
            except:
                result["kimchi_premium"] = 0

        _set_cache("crypto_overview", result)
        return result
    except Exception as e:
        print(f"[DataProvider] Crypto error: {e}")
        return {"binance": [], "upbit": [], "btc_dominance": 0, "total_market_cap": 0, "kimchi_premium": 0}

# ===== 개별 종목 =====

async def get_stock_detail(code):
    """개별 종목 상세"""
    try:
        result = await asyncio.to_thread(_fetch_stock_detail, code)
        return result
    except Exception as e:
        print(f"[DataProvider] Stock detail error: {e}")
        return None

def _fetch_stock_detail(code):
    today = _get_today()
    yesterday = _get_date_ago(7)

    try:
        ohlcv = krx.get_market_ohlcv(yesterday, today, code)
        if ohlcv.empty:
            return None

        last = ohlcv.iloc[-1]
        prev = ohlcv.iloc[-2] if len(ohlcv) > 1 else last

        # 종목명 가져오기
        try:
            name = krx.get_market_ticker_name(code)
        except:
            name = code

        # 펀더멘탈
        try:
            fund = krx.get_market_fundamental(today, today, code)
            per = float(fund.iloc[0]["PER"]) if not fund.empty and "PER" in fund.columns else 0
            pbr = float(fund.iloc[0]["PBR"]) if not fund.empty and "PBR" in fund.columns else 0
        except:
            per, pbr = 0, 0

        return {
            "code": code,
            "name": name,
            "close": int(last["종가"]),
            "open": int(last["시가"]),
            "high": int(last["고가"]),
            "low": int(last["저가"]),
            "volume": int(last["거래량"]),
            "change": int(last["종가"] - prev["종가"]) if len(ohlcv) > 1 else 0,
            "change_percent": float(last["등락률"]) if "등락률" in last else 0,
            "per": round(per, 2),
            "pbr": round(pbr, 2)
        }
    except Exception as e:
        print(f"[DataProvider] Stock detail error for {code}: {e}")
        return None

async def get_chart_data(code, period="3m"):
    """차트 데이터"""
    try:
        result = await asyncio.to_thread(_fetch_chart, code, period)
        return result
    except Exception as e:
        print(f"[DataProvider] Chart error: {e}")
        return []

def _fetch_chart(code, period):
    period_map = {"1d": 1, "1w": 7, "1m": 30, "3m": 90, "6m": 180, "1y": 365}
    days = period_map.get(period, 90)

    start = _get_date_ago(days)
    end = _get_today()

    try:
        df = krx.get_market_ohlcv(start, end, code)
        if df.empty:
            return []

        return [{
            "date": idx.strftime("%Y-%m-%d"),
            "open": int(row["시가"]),
            "high": int(row["고가"]),
            "low": int(row["저가"]),
            "close": int(row["종가"]),
            "volume": int(row["거래량"])
        } for idx, row in df.iterrows()]
    except:
        return []

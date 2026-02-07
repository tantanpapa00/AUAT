"""
BBooster 데이터 제공 모듈
httpx: 네이버증권/야후/코인거래소 API
yfinance: 해외 주식/지수
"""
import asyncio
from datetime import datetime, timedelta
import yfinance as yf
import httpx
import traceback
import json
import re

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

# ===== 국내 시장 (네이버 증권 API) =====

async def get_kr_market_overview():
    """국내 시장 개요: 지수 + 투자자동향"""
    cached = _cached("kr_overview", 300)  # 5분 캐싱
    if cached:
        return cached

    result = {
        "kospi": {"name": "코스피", "current": 0, "change": 0, "change_percent": 0},
        "kosdaq": {"name": "코스닥", "current": 0, "change": 0, "change_percent": 0},
        "investors": {"foreign": 0, "institution": 0, "individual": 0},
        "sectors": []
    }

    try:
        async with httpx.AsyncClient(timeout=10) as client:
            # 코스피 지수
            try:
                r = await client.get("https://api.finance.naver.com/siseJson.naver?symbol=KOSPI&requestType=1&count=1")
                if r.status_code == 200:
                    text = r.text.strip()
                    # Parse the response (네이버 형식)
                    data = _parse_naver_index(text)
                    if data:
                        result["kospi"] = {
                            "name": "코스피",
                            "current": data.get("close", 0),
                            "change": data.get("change", 0),
                            "change_percent": data.get("change_percent", 0),
                            "volume": data.get("volume", 0)
                        }
            except Exception as e:
                print(f"[DataProvider] KOSPI error: {e}")

            # 코스닥 지수
            try:
                r = await client.get("https://api.finance.naver.com/siseJson.naver?symbol=KOSDAQ&requestType=1&count=1")
                if r.status_code == 200:
                    text = r.text.strip()
                    data = _parse_naver_index(text)
                    if data:
                        result["kosdaq"] = {
                            "name": "코스닥",
                            "current": data.get("close", 0),
                            "change": data.get("change", 0),
                            "change_percent": data.get("change_percent", 0),
                            "volume": data.get("volume", 0)
                        }
            except Exception as e:
                print(f"[DataProvider] KOSDAQ error: {e}")

            # 투자자 동향 (샘플 데이터 - 실제 API 필요)
            result["investors"] = _get_sample_investors()

            # 업종 (샘플 데이터)
            result["sectors"] = _get_sample_sectors()

        _set_cache("kr_overview", result)
        return result

    except Exception as e:
        print(f"[DataProvider] KR overview error: {e}")
        traceback.print_exc()
        return result

def _parse_naver_index(text):
    """네이버 지수 응답 파싱"""
    try:
        # 네이버 siseJson 형식 파싱
        # [["날짜","시가","고가","저가","종가","거래량"],[...]]
        lines = text.strip().split('\n')
        if len(lines) >= 2:
            # 마지막 유효한 라인 사용
            for line in reversed(lines[1:]):
                line = line.strip().rstrip(',')
                if line.startswith('[') and line.endswith(']'):
                    data = json.loads(line)
                    if len(data) >= 5:
                        return {
                            "close": float(data[4]) if data[4] else 0,
                            "change": 0,  # 별도 계산 필요
                            "change_percent": 0,
                            "volume": int(data[5]) if len(data) > 5 and data[5] else 0
                        }
    except:
        pass
    return None

def _get_sample_investors():
    """투자자 동향 샘플 데이터"""
    import random
    return {
        "foreign": random.randint(-500000000000, 500000000000),
        "institution": random.randint(-300000000000, 300000000000),
        "individual": random.randint(-400000000000, 400000000000)
    }

def _get_sample_sectors():
    """업종 샘플 데이터"""
    import random
    sectors = ["반도체", "2차전지", "바이오", "자동차", "금융", "건설", "철강", "화학", "IT", "통신"]
    return [
        {"name": s, "change_percent": round(random.uniform(-3, 5), 2), "volume": random.randint(1000000, 100000000)}
        for s in sectors
    ]

# ===== RS 순위 =====

async def get_rs_ranking(market="ALL", limit=100):
    """RS 순위 - 샘플 데이터 (실제 구현 시 일봉 데이터 필요)"""
    cache_key = f"rs_{market}_{limit}"
    cached = _cached(cache_key, 3600)
    if cached:
        return cached

    import random

    # 샘플 종목 리스트
    sample_stocks = [
        ("005930", "삼성전자"), ("000660", "SK하이닉스"), ("373220", "LG에너지솔루션"),
        ("207940", "삼성바이오로직스"), ("005380", "현대차"), ("000270", "기아"),
        ("068270", "셀트리온"), ("035420", "NAVER"), ("051910", "LG화학"),
        ("006400", "삼성SDI"), ("035720", "카카오"), ("028260", "삼성물산"),
        ("105560", "KB금융"), ("055550", "신한지주"), ("003670", "포스코퓨처엠"),
        ("012330", "현대모비스"), ("066570", "LG전자"), ("003550", "LG"),
        ("096770", "SK이노베이션"), ("034730", "SK"), ("015760", "한국전력"),
        ("017670", "SK텔레콤"), ("033780", "KT&G"), ("030200", "KT"),
        ("018260", "삼성에스디에스"), ("032830", "삼성생명"), ("086790", "하나금융지주")
    ]

    stocks = []
    for code, name in sample_stocks[:limit]:
        rs_1m = random.randint(30, 99)
        rs_3m = random.randint(30, 99)
        rs_6m = random.randint(30, 99)
        rs_total = int(rs_1m * 0.4 + rs_3m * 0.3 + rs_6m * 0.3)

        stocks.append({
            "code": code,
            "name": name,
            "market": "KOSPI" if market.upper() in ["ALL", "KOSPI"] else "KOSDAQ",
            "price": random.randint(10000, 500000),
            "change": round(random.uniform(-5, 8), 2),
            "rs_total": rs_total,
            "rs_1m": rs_1m,
            "rs_3m": rs_3m,
            "rs_6m": rs_6m
        })

    stocks.sort(key=lambda x: x["rs_total"], reverse=True)
    _set_cache(cache_key, stocks)
    return stocks

# ===== 52주 신고가 =====

async def get_new_high_stocks(limit=50):
    """52주 신고가 종목 - 샘플 데이터"""
    cached = _cached("new_high", 3600)
    if cached:
        return cached

    import random

    sample_stocks = [
        ("005930", "삼성전자"), ("000660", "SK하이닉스"), ("373220", "LG에너지솔루션"),
        ("207940", "삼성바이오로직스"), ("005380", "현대차"), ("000270", "기아"),
        ("068270", "셀트리온"), ("035420", "NAVER"), ("051910", "LG화학")
    ]

    results = []
    for code, name in sample_stocks[:limit]:
        price = random.randint(50000, 500000)
        high_52w = int(price * random.uniform(0.98, 1.05))
        results.append({
            "code": code,
            "name": name,
            "price": price,
            "change": round(random.uniform(0, 10), 2),
            "high_52w": high_52w,
            "distance": round((price / high_52w - 1) * 100, 2),
            "market_cap": random.randint(1000000000000, 500000000000000)
        })

    results.sort(key=lambda x: x["distance"], reverse=True)
    _set_cache("new_high", results)
    return results

# ===== 밸류에이션 =====

async def get_valuation(market="ALL", limit=200):
    """PER/PBR 밸류에이션 - 샘플 데이터"""
    cache_key = f"valuation_{market}"
    cached = _cached(cache_key, 3600)
    if cached:
        return cached

    import random

    sample_stocks = [
        ("005930", "삼성전자"), ("000660", "SK하이닉스"), ("373220", "LG에너지솔루션"),
        ("207940", "삼성바이오로직스"), ("005380", "현대차"), ("000270", "기아"),
        ("068270", "셀트리온"), ("035420", "NAVER"), ("051910", "LG화학"),
        ("006400", "삼성SDI"), ("035720", "카카오"), ("028260", "삼성물산"),
        ("105560", "KB금융"), ("055550", "신한지주"), ("003670", "포스코퓨처엠")
    ]

    results = []
    for code, name in sample_stocks[:limit]:
        per = round(random.uniform(5, 50), 2)
        pbr = round(random.uniform(0.5, 5), 2)
        results.append({
            "code": code,
            "name": name,
            "price": random.randint(10000, 500000),
            "per": per if per > 0 else 0,
            "pbr": pbr,
            "market_cap": random.randint(1000000000000, 500000000000000),
            "market": market.upper() if market.upper() != "ALL" else "KOSPI"
        })

    results.sort(key=lambda x: x["per"] if x["per"] > 0 else 9999)
    _set_cache(cache_key, results)
    return results

# ===== ETF =====

async def get_etf_overview():
    """ETF 전종목 시세 + 섹터 분류 - 샘플 데이터"""
    cached = _cached("etf_overview", 1800)
    if cached:
        return cached

    import random

    # 섹터별 샘플 ETF
    sector_etfs = {
        "반도체": [
            {"code": "091160", "name": "KODEX 반도체", "close": 45000, "change_percent": 2.5, "volume": 1500000, "nav": 45100},
            {"code": "091170", "name": "KODEX 반도체레버리지", "close": 15000, "change_percent": 5.0, "volume": 2000000, "nav": 15050},
        ],
        "2차전지": [
            {"code": "305720", "name": "KODEX 2차전지산업", "close": 18000, "change_percent": -1.2, "volume": 800000, "nav": 17950},
            {"code": "394660", "name": "TIGER 2차전지TOP10", "close": 12000, "change_percent": -0.8, "volume": 500000, "nav": 11980},
        ],
        "AI": [
            {"code": "418660", "name": "KODEX AI소프트웨어", "close": 15500, "change_percent": 3.2, "volume": 600000, "nav": 15550},
        ],
        "바이오": [
            {"code": "143860", "name": "KODEX 헬스케어", "close": 32000, "change_percent": 0.5, "volume": 300000, "nav": 32050},
        ],
        "배당": [
            {"code": "210780", "name": "TIGER 코스피고배당", "close": 11500, "change_percent": 0.2, "volume": 400000, "nav": 11510},
        ],
        "해외(미국)": [
            {"code": "360750", "name": "TIGER 미국S&P500", "close": 18000, "change_percent": 1.0, "volume": 700000, "nav": 18020},
            {"code": "133690", "name": "TIGER 미국나스닥100", "close": 95000, "change_percent": 1.5, "volume": 900000, "nav": 95100},
        ],
    }

    all_etfs = []
    for sector, etfs in sector_etfs.items():
        for etf in etfs:
            etf["change_percent"] = round(random.uniform(-3, 5), 2)
            all_etfs.append(etf)

    _set_cache("etf_overview", {"sectors": sector_etfs, "all": all_etfs})
    return {"sectors": sector_etfs, "all": all_etfs}

# ===== 해외 시장 =====

async def get_us_market_overview():
    """해외 시장 개요 - yfinance"""
    cached = _cached("us_overview", 600)
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
    cached = _cached("crypto_overview", 60)
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
            except Exception as e:
                print(f"[DataProvider] Binance error: {e}")
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
            except Exception as e:
                print(f"[DataProvider] Upbit error: {e}")
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
    """개별 종목 상세 - 샘플 데이터"""
    import random

    # 종목명 매핑
    stock_names = {
        "005930": "삼성전자", "000660": "SK하이닉스", "373220": "LG에너지솔루션",
        "207940": "삼성바이오로직스", "005380": "현대차", "000270": "기아",
        "068270": "셀트리온", "035420": "NAVER", "051910": "LG화학",
    }

    name = stock_names.get(code, f"종목{code}")
    price = random.randint(10000, 500000)

    return {
        "code": code,
        "name": name,
        "close": price,
        "open": int(price * random.uniform(0.97, 1.03)),
        "high": int(price * random.uniform(1.0, 1.05)),
        "low": int(price * random.uniform(0.95, 1.0)),
        "volume": random.randint(100000, 10000000),
        "change": random.randint(-5000, 10000),
        "change_percent": round(random.uniform(-5, 8), 2),
        "per": round(random.uniform(5, 50), 2),
        "pbr": round(random.uniform(0.5, 5), 2)
    }

async def get_chart_data(code, period="3m"):
    """차트 데이터 - 샘플 데이터"""
    import random
    from datetime import datetime, timedelta

    period_map = {"1d": 1, "1w": 7, "1m": 30, "3m": 90, "6m": 180, "1y": 365}
    days = period_map.get(period, 90)

    base_price = random.randint(10000, 100000)
    data = []

    for i in range(days):
        date = (datetime.now() - timedelta(days=days-i)).strftime("%Y-%m-%d")
        change = random.uniform(-0.03, 0.03)
        base_price = int(base_price * (1 + change))

        data.append({
            "date": date,
            "open": int(base_price * random.uniform(0.98, 1.0)),
            "high": int(base_price * random.uniform(1.0, 1.03)),
            "low": int(base_price * random.uniform(0.97, 1.0)),
            "close": base_price,
            "volume": random.randint(100000, 5000000)
        })

    return data

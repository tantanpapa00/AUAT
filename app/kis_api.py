"""
KIS Open API 연동 모듈
- 종목 마스터 다운로드 및 파싱
- 현재가 시세 조회
- 재무제표 조회 (국내주식)
- 투자의견 조회 (국내주식)
- 투자자 매매동향 조회
- 일봉 데이터 조회 (차트용)
"""

import os
import io
import zipfile
import httpx
import asyncio
from datetime import datetime, timezone, timedelta
from typing import Optional, Dict, List, Any
from dataclasses import dataclass, field

# KIS API 환경 설정
KIS_REAL_URL = "https://openapi.koreainvestment.com:9443"
KIS_MOCK_URL = "https://openapivts.koreainvestment.com:29443"

# 종목 마스터 파일 URL
MASTER_URLS = {
    "kospi": "https://new.real.download.dws.co.kr/common/master/kospi_code.mst.zip",
    "kosdaq": "https://new.real.download.dws.co.kr/common/master/kosdaq_code.mst.zip",
    "nasdaq": "https://new.real.download.dws.co.kr/common/master/nasmst.cod.zip",
    "nyse": "https://new.real.download.dws.co.kr/common/master/nysmst.cod.zip",
    "amex": "https://new.real.download.dws.co.kr/common/master/amsmst.cod.zip",
}


@dataclass
class StockMaster:
    """종목 마스터 정보"""
    code: str
    name: str
    market: str  # KOSPI, KOSDAQ, NYSE, NASDAQ, AMEX
    sector: str = ""
    is_etf: bool = False
    is_etn: bool = False


@dataclass
class KISToken:
    """KIS API 액세스 토큰"""
    access_token: str
    token_type: str
    expires_at: datetime


class KISMasterCache:
    """종목 마스터 캐시"""

    def __init__(self):
        self.stocks: Dict[str, StockMaster] = {}  # code -> StockMaster
        self.last_updated: Optional[datetime] = None
        self._lock = asyncio.Lock()

    def is_valid(self) -> bool:
        """캐시가 유효한지 확인 (1일)"""
        if not self.last_updated:
            return False
        age = (datetime.now(timezone.utc) - self.last_updated).total_seconds()
        return age < 86400  # 24시간

    def get_stock(self, code: str) -> Optional[StockMaster]:
        """종목 코드로 조회"""
        return self.stocks.get(code.upper())

    def search(self, query: str, market: Optional[str] = None, limit: int = 50) -> List[StockMaster]:
        """종목 검색"""
        query_upper = query.upper()
        results = []

        for stock in self.stocks.values():
            # 마켓 필터
            if market:
                market_upper = market.upper()
                if market_upper == "KIS_KR":
                    if stock.market not in ("KOSPI", "KOSDAQ"):
                        continue
                elif market_upper == "KIS_KR_ETF":
                    if stock.market not in ("KOSPI", "KOSDAQ") or not stock.is_etf:
                        continue
                elif market_upper == "KIS_US":
                    if stock.market not in ("NYSE", "NASDAQ", "AMEX"):
                        continue
                elif market_upper == "KIS_US_ETF":
                    if stock.market not in ("NYSE", "NASDAQ", "AMEX") or not stock.is_etf:
                        continue
                elif market_upper not in (stock.market, "ALL"):
                    continue

            # 검색어 매칭
            if not query or query_upper in stock.code.upper() or query_upper in stock.name.upper():
                results.append(stock)
                if len(results) >= limit:
                    break

        return results

    def get_popular(self, market: Optional[str] = None, limit: int = 10) -> List[StockMaster]:
        """인기 종목 (하드코딩된 주요 종목)"""
        # 시가총액 상위 종목 하드코딩
        popular_codes = {
            "KOSPI": ["005930", "000660", "005380", "000270", "051910", "006400", "035420", "035720", "068270", "207940"],
            "KOSDAQ": ["247540", "086520", "293490", "263750", "196170", "145020", "091990", "041510", "035900", "122870"],
            "NYSE": ["BRK.B", "JPM", "V", "JNJ", "WMT", "PG", "MA", "UNH", "HD", "BAC"],
            "NASDAQ": ["AAPL", "MSFT", "GOOGL", "AMZN", "NVDA", "META", "TSLA", "AVGO", "COST", "NFLX"],
            "AMEX": ["SPY", "QQQ", "IWM", "DIA", "VTI", "VOO", "GLD", "SLV", "XLF", "XLE"],
        }

        results = []

        if market:
            market_upper = market.upper()
            if market_upper == "KIS_KR":
                target_markets = ["KOSPI", "KOSDAQ"]
            elif market_upper == "KIS_US":
                target_markets = ["NYSE", "NASDAQ", "AMEX"]
            else:
                target_markets = [market_upper]
        else:
            target_markets = list(popular_codes.keys())

        for mkt in target_markets:
            codes = popular_codes.get(mkt, [])
            for code in codes[:limit]:
                stock = self.stocks.get(code)
                if stock:
                    results.append(stock)

        return results[:limit]


# 전역 캐시
_master_cache = KISMasterCache()
_token_cache: Dict[str, KISToken] = {}  # user_id -> token


def _parse_kospi_kosdaq_master(content: bytes, market: str) -> Dict[str, StockMaster]:
    """KOSPI/KOSDAQ 종목 마스터 파싱"""
    stocks = {}
    try:
        # EUC-KR 인코딩
        lines = content.decode('euc-kr', errors='replace').splitlines()
        for line in lines:
            if len(line) < 32:
                continue
            try:
                # 고정 폭 형식: 종목코드(9) + 표준코드(12) + 한글명(50) + ...
                code = line[0:9].strip()
                if not code or not code.isdigit():
                    # 코드가 숫자가 아니면 건너뛰기 (헤더 등)
                    continue
                # 실제 마스터 형식에 따라 조정 필요
                # 간단히 종목코드 6자리 + 종목명 파싱
                code = code[:6] if len(code) >= 6 else code
                name = line[21:71].strip() if len(line) > 71 else line[21:].strip()

                # ETF 여부 (종목코드로 추정: 1로 시작하면 ETF가 많음)
                is_etf = code.startswith("1") or code.startswith("3") or "ETF" in name.upper()

                stocks[code] = StockMaster(
                    code=code,
                    name=name,
                    market=market,
                    is_etf=is_etf
                )
            except Exception:
                continue
    except Exception as e:
        print(f"[KIS] Master parse error ({market}): {e}")

    return stocks


def _parse_overseas_master(content: bytes, market: str) -> Dict[str, StockMaster]:
    """해외 종목 마스터 파싱 (NYSE, NASDAQ, AMEX)"""
    stocks = {}
    try:
        # 해외 마스터는 | 구분자 또는 고정폭
        lines = content.decode('utf-8', errors='replace').splitlines()
        for line in lines:
            if not line.strip():
                continue
            try:
                # 형식에 따라 파싱 (예: 종목코드|종목명|...)
                if '|' in line:
                    parts = line.split('|')
                    if len(parts) >= 2:
                        code = parts[0].strip()
                        name = parts[1].strip()
                        is_etf = "ETF" in name.upper() or len(parts) > 5 and "ETF" in parts[5].upper()
                        stocks[code] = StockMaster(
                            code=code,
                            name=name,
                            market=market,
                            is_etf=is_etf
                        )
                else:
                    # 고정폭 형식 추정
                    if len(line) >= 20:
                        code = line[0:12].strip()
                        name = line[12:62].strip() if len(line) > 62 else line[12:].strip()
                        if code and name:
                            is_etf = "ETF" in name.upper()
                            stocks[code] = StockMaster(
                                code=code,
                                name=name,
                                market=market,
                                is_etf=is_etf
                            )
            except Exception:
                continue
    except Exception as e:
        print(f"[KIS] Overseas master parse error ({market}): {e}")

    return stocks


async def download_and_parse_master(market: str, url: str) -> Dict[str, StockMaster]:
    """마스터 파일 다운로드 및 파싱"""
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.get(url)
            if resp.status_code != 200:
                print(f"[KIS] Master download failed ({market}): {resp.status_code}")
                return {}

            # ZIP 압축 해제
            with zipfile.ZipFile(io.BytesIO(resp.content)) as zf:
                for name in zf.namelist():
                    content = zf.read(name)
                    if market in ("kospi", "kosdaq"):
                        return _parse_kospi_kosdaq_master(content, market.upper())
                    else:
                        return _parse_overseas_master(content, market.upper())
    except Exception as e:
        print(f"[KIS] Master download error ({market}): {e}")

    return {}


async def refresh_master_cache():
    """종목 마스터 캐시 갱신"""
    async with _master_cache._lock:
        if _master_cache.is_valid():
            return  # 아직 유효함

        print("[KIS] Refreshing master cache...")
        all_stocks = {}

        # 병렬 다운로드
        tasks = []
        for market, url in MASTER_URLS.items():
            tasks.append(download_and_parse_master(market, url))

        results = await asyncio.gather(*tasks, return_exceptions=True)

        for result in results:
            if isinstance(result, dict):
                all_stocks.update(result)

        # 다운로드 실패 시 하드코딩 폴백
        if len(all_stocks) < 100:
            print("[KIS] Using fallback hardcoded stocks")
            all_stocks.update(_get_fallback_stocks())

        _master_cache.stocks = all_stocks
        _master_cache.last_updated = datetime.now(timezone.utc)
        print(f"[KIS] Master cache updated: {len(all_stocks)} stocks")


def _get_fallback_stocks() -> Dict[str, StockMaster]:
    """폴백 하드코딩 종목 (다운로드 실패 시)"""
    fallback = {}

    # KOSPI 주요 종목
    kospi = [
        ("005930", "삼성전자"), ("000660", "SK하이닉스"), ("005380", "현대차"),
        ("000270", "기아"), ("051910", "LG화학"), ("006400", "삼성SDI"),
        ("035420", "NAVER"), ("035720", "카카오"), ("068270", "셀트리온"),
        ("207940", "삼성바이오로직스"), ("373220", "LG에너지솔루션"), ("005490", "POSCO홀딩스"),
        ("055550", "신한지주"), ("105560", "KB금융"), ("028260", "삼성물산"),
        ("003670", "포스코퓨처엠"), ("012330", "현대모비스"), ("066570", "LG전자"),
        ("032830", "삼성생명"), ("017670", "SK텔레콤"), ("034730", "SK"),
        ("086790", "하나금융지주"), ("015760", "한국전력"), ("009150", "삼성전기"),
    ]
    for code, name in kospi:
        fallback[code] = StockMaster(code=code, name=name, market="KOSPI")

    # KOSDAQ 주요 종목
    kosdaq = [
        ("247540", "에코프로비엠"), ("086520", "에코프로"), ("293490", "카카오게임즈"),
        ("263750", "펄어비스"), ("196170", "알테오젠"), ("145020", "휴젤"),
        ("091990", "셀트리온헬스케어"), ("041510", "에스엠"), ("035900", "JYP Ent."),
        ("122870", "와이지엔터테인먼트"), ("357780", "솔브레인"), ("028300", "HLB"),
    ]
    for code, name in kosdaq:
        fallback[code] = StockMaster(code=code, name=name, market="KOSDAQ")

    # NYSE 주요 종목
    nyse = [
        ("BRK.B", "Berkshire Hathaway"), ("JPM", "JPMorgan Chase"), ("V", "Visa"),
        ("JNJ", "Johnson & Johnson"), ("WMT", "Walmart"), ("PG", "Procter & Gamble"),
        ("MA", "Mastercard"), ("UNH", "UnitedHealth"), ("HD", "Home Depot"),
        ("BAC", "Bank of America"), ("XOM", "Exxon Mobil"), ("CVX", "Chevron"),
    ]
    for code, name in nyse:
        fallback[code] = StockMaster(code=code, name=name, market="NYSE")

    # NASDAQ 주요 종목
    nasdaq = [
        ("AAPL", "Apple"), ("MSFT", "Microsoft"), ("GOOGL", "Alphabet"),
        ("AMZN", "Amazon"), ("NVDA", "NVIDIA"), ("META", "Meta"),
        ("TSLA", "Tesla"), ("AVGO", "Broadcom"), ("COST", "Costco"),
        ("NFLX", "Netflix"), ("AMD", "AMD"), ("INTC", "Intel"),
        ("QCOM", "Qualcomm"), ("ADBE", "Adobe"), ("CRM", "Salesforce"),
    ]
    for code, name in nasdaq:
        fallback[code] = StockMaster(code=code, name=name, market="NASDAQ")

    # ETF
    etfs = [
        ("069500", "KODEX 200", "KOSPI"), ("229200", "KODEX 코스닥150", "KOSDAQ"),
        ("SPY", "SPDR S&P 500 ETF", "NYSE"), ("QQQ", "Invesco QQQ", "NASDAQ"),
        ("IWM", "iShares Russell 2000", "NYSE"), ("DIA", "SPDR Dow Jones", "NYSE"),
    ]
    for code, name, market in etfs:
        fallback[code] = StockMaster(code=code, name=name, market=market, is_etf=True)

    return fallback


def get_master_cache() -> KISMasterCache:
    """마스터 캐시 반환"""
    return _master_cache


async def search_symbols(query: str, exchange: str = None, category: str = None) -> list:
    """종목 마스터 캐시에서 종목 검색 (공개 API)"""
    cache = get_master_cache()

    # 캐시가 유효하지 않으면 갱신
    if not cache.is_valid():
        await refresh_master_cache()

    results = []
    query_lower = query.lower() if query else ""

    for key, stock in cache.stocks.items():
        # 종목명 또는 종목코드에 query 포함
        if not query_lower or query_lower in stock.name.lower() or query_lower in stock.code.lower():
            # exchange 필터
            if exchange and exchange.lower() != 'all':
                ex_lower = exchange.lower()
                # KIS_KR → KOSPI/KOSDAQ, KIS_US → NYSE/NASDAQ/AMEX
                if ex_lower == 'kis_kr':
                    if stock.market not in ('KOSPI', 'KOSDAQ'):
                        continue
                elif ex_lower == 'kis_kr_etf':
                    if stock.market not in ('KOSPI', 'KOSDAQ') or not stock.is_etf:
                        continue
                elif ex_lower == 'kis_us':
                    if stock.market not in ('NYSE', 'NASDAQ', 'AMEX'):
                        continue
                elif ex_lower == 'kis_us_etf':
                    if stock.market not in ('NYSE', 'NASDAQ', 'AMEX') or not stock.is_etf:
                        continue
                elif stock.market.lower() != ex_lower:
                    continue

            # category 필터 (stock/etf)
            if category and category.lower() != 'all':
                if category.lower() == 'etf' and not stock.is_etf:
                    continue
                elif category.lower() == 'stock' and stock.is_etf:
                    continue

            results.append({
                "code": stock.code,
                "name": stock.name,
                "market": stock.market,
                "exchange": stock.market.lower(),
                "is_etf": stock.is_etf,
            })

        if len(results) >= 50:
            break

    return results


# =====================================================
# KIS API 호출 함수들
# =====================================================

async def get_kis_token(app_key: str, app_secret: str, is_mock: bool = False) -> Optional[KISToken]:
    """KIS API 액세스 토큰 발급"""
    base_url = KIS_MOCK_URL if is_mock else KIS_REAL_URL
    url = f"{base_url}/oauth2/tokenP"

    body = {
        "grant_type": "client_credentials",
        "appkey": app_key,
        "appsecret": app_secret
    }

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(url, json=body)
            if resp.status_code == 200:
                data = resp.json()
                expires_in = int(data.get("expires_in", 86400))
                return KISToken(
                    access_token=data.get("access_token", ""),
                    token_type=data.get("token_type", "Bearer"),
                    expires_at=datetime.now(timezone.utc) + timedelta(seconds=expires_in)
                )
    except Exception as e:
        print(f"[KIS] Token error: {e}")

    return None


async def get_domestic_price(
    app_key: str,
    app_secret: str,
    access_token: str,
    stock_code: str,
    is_mock: bool = False
) -> Optional[Dict[str, Any]]:
    """국내주식 현재가 조회"""
    base_url = KIS_MOCK_URL if is_mock else KIS_REAL_URL
    url = f"{base_url}/uapi/domestic-stock/v1/quotations/inquire-price"

    headers = {
        "Content-Type": "application/json; charset=utf-8",
        "authorization": f"Bearer {access_token}",
        "appkey": app_key,
        "appsecret": app_secret,
        "tr_id": "FHKST01010100",  # 주식현재가 시세
    }

    params = {
        "FID_COND_MRKT_DIV_CODE": "J",  # 주식
        "FID_INPUT_ISCD": stock_code,
    }

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(url, headers=headers, params=params)
            if resp.status_code == 200:
                data = resp.json()
                if data.get("rt_cd") == "0":
                    output = data.get("output", {})
                    return {
                        "current": int(output.get("stck_prpr", 0)),
                        "change": float(output.get("prdy_ctrt", 0)),
                        "change_amount": int(output.get("prdy_vrss", 0)),
                        "high": int(output.get("stck_hgpr", 0)),
                        "low": int(output.get("stck_lwpr", 0)),
                        "open": int(output.get("stck_oprc", 0)),
                        "volume": int(output.get("acml_vol", 0)),
                        "value": int(output.get("acml_tr_pbmn", 0)),
                        "per": float(output.get("per", 0)),
                        "pbr": float(output.get("pbr", 0)),
                        "eps": float(output.get("eps", 0)),
                        "bps": float(output.get("bps", 0)),
                        "market_cap": int(output.get("hts_avls", 0)),
                    }
    except Exception as e:
        print(f"[KIS] Domestic price error: {e}")

    return None


async def get_overseas_price(
    app_key: str,
    app_secret: str,
    access_token: str,
    exchange: str,  # NYSE, NASDAQ, AMEX
    stock_code: str,
    is_mock: bool = False
) -> Optional[Dict[str, Any]]:
    """해외주식 현재가 조회"""
    base_url = KIS_MOCK_URL if is_mock else KIS_REAL_URL
    url = f"{base_url}/uapi/overseas-price/v1/quotations/price"

    # 거래소 코드 매핑
    excd_map = {
        "NYSE": "NYS",
        "NASDAQ": "NAS",
        "AMEX": "AMS",
    }
    excd = excd_map.get(exchange.upper(), "NAS")

    headers = {
        "Content-Type": "application/json; charset=utf-8",
        "authorization": f"Bearer {access_token}",
        "appkey": app_key,
        "appsecret": app_secret,
        "tr_id": "HHDFS00000300",  # 해외주식현재가
    }

    params = {
        "AUTH": "",
        "EXCD": excd,
        "SYMB": stock_code,
    }

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(url, headers=headers, params=params)
            if resp.status_code == 200:
                data = resp.json()
                if data.get("rt_cd") == "0":
                    output = data.get("output", {})
                    return {
                        "current": float(output.get("last", 0)),
                        "change": float(output.get("rate", 0)),
                        "change_amount": float(output.get("diff", 0)),
                        "high": float(output.get("high", 0)),
                        "low": float(output.get("low", 0)),
                        "open": float(output.get("open", 0)),
                        "volume": int(output.get("tvol", 0)),
                        "value": float(output.get("tamt", 0)),
                    }
    except Exception as e:
        print(f"[KIS] Overseas price error: {e}")

    return None


async def get_financial_ratio(
    app_key: str,
    app_secret: str,
    access_token: str,
    stock_code: str,
    is_mock: bool = False
) -> Optional[Dict[str, Any]]:
    """국내주식 재무비율 조회"""
    base_url = KIS_MOCK_URL if is_mock else KIS_REAL_URL
    url = f"{base_url}/uapi/domestic-stock/v1/finance/financial-ratio"

    headers = {
        "Content-Type": "application/json; charset=utf-8",
        "authorization": f"Bearer {access_token}",
        "appkey": app_key,
        "appsecret": app_secret,
        "tr_id": "FHKST66430100",
    }

    params = {
        "FID_DIV_CLS_CODE": "0",
        "fid_cond_mrkt_div_code": "J",
        "fid_input_iscd": stock_code,
    }

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(url, headers=headers, params=params)
            if resp.status_code == 200:
                data = resp.json()
                if data.get("rt_cd") == "0":
                    output = data.get("output", [])
                    if output:
                        latest = output[0]
                        return {
                            "per": float(latest.get("per", 0)),
                            "pbr": float(latest.get("pbr", 0)),
                            "roe": float(latest.get("roe", 0)),
                            "roa": float(latest.get("roa", 0)),
                            "debt_ratio": float(latest.get("lblt_rate", 0)),
                            "operating_margin": float(latest.get("bsop_prfi_inrt", 0)),
                            "net_margin": float(latest.get("ntin_inrt", 0)),
                        }
    except Exception as e:
        print(f"[KIS] Financial ratio error: {e}")

    return None


async def get_income_statement(
    app_key: str,
    app_secret: str,
    access_token: str,
    stock_code: str,
    is_mock: bool = False
) -> Optional[List[Dict[str, Any]]]:
    """국내주식 손익계산서 조회 (최근 4분기)"""
    base_url = KIS_MOCK_URL if is_mock else KIS_REAL_URL
    url = f"{base_url}/uapi/domestic-stock/v1/finance/income-statement"

    headers = {
        "Content-Type": "application/json; charset=utf-8",
        "authorization": f"Bearer {access_token}",
        "appkey": app_key,
        "appsecret": app_secret,
        "tr_id": "FHKST66430200",
    }

    params = {
        "FID_DIV_CLS_CODE": "1",  # 분기
        "fid_cond_mrkt_div_code": "J",
        "fid_input_iscd": stock_code,
    }

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(url, headers=headers, params=params)
            if resp.status_code == 200:
                data = resp.json()
                if data.get("rt_cd") == "0":
                    output = data.get("output", [])
                    results = []
                    for item in output[:4]:
                        results.append({
                            "period": item.get("stac_yymm", ""),
                            "revenue": int(item.get("sale_account", 0)),
                            "operating_profit": int(item.get("bsop_prti", 0)),
                            "net_income": int(item.get("thtr_ntin", 0)),
                        })
                    return results
    except Exception as e:
        print(f"[KIS] Income statement error: {e}")

    return None


async def get_invest_opinion(
    app_key: str,
    app_secret: str,
    access_token: str,
    stock_code: str,
    is_mock: bool = False
) -> Optional[Dict[str, Any]]:
    """국내주식 투자의견 조회"""
    base_url = KIS_MOCK_URL if is_mock else KIS_REAL_URL
    url = f"{base_url}/uapi/domestic-stock/v1/quotations/invest-opinion"

    headers = {
        "Content-Type": "application/json; charset=utf-8",
        "authorization": f"Bearer {access_token}",
        "appkey": app_key,
        "appsecret": app_secret,
        "tr_id": "FHKST663300C0",
    }

    params = {
        "FID_COND_MRKT_DIV_CODE": "J",
        "FID_INPUT_ISCD": stock_code,
    }

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(url, headers=headers, params=params)
            if resp.status_code == 200:
                data = resp.json()
                if data.get("rt_cd") == "0":
                    output = data.get("output", [])
                    if output:
                        # 최근 의견들 집계
                        buy = 0
                        hold = 0
                        sell = 0
                        target_prices = []

                        for item in output[:20]:
                            opinion = item.get("invt_opnn", "")
                            if "매수" in opinion or "Buy" in opinion.upper():
                                buy += 1
                            elif "중립" in opinion or "Hold" in opinion.upper():
                                hold += 1
                            elif "매도" in opinion or "Sell" in opinion.upper():
                                sell += 1

                            tp = int(item.get("stck_prpr", 0))
                            if tp > 0:
                                target_prices.append(tp)

                        total = buy + hold + sell
                        consensus = "매수" if buy > hold and buy > sell else ("중립" if hold >= buy and hold >= sell else "매도")
                        avg_target = sum(target_prices) / len(target_prices) if target_prices else 0

                        return {
                            "consensus": consensus,
                            "target_price": int(avg_target),
                            "analyst_count": total,
                            "buy_count": buy,
                            "hold_count": hold,
                            "sell_count": sell,
                        }
    except Exception as e:
        print(f"[KIS] Invest opinion error: {e}")

    return None


async def get_investor_trend(
    app_key: str,
    app_secret: str,
    access_token: str,
    stock_code: str,
    is_mock: bool = False
) -> Optional[List[Dict[str, Any]]]:
    """국내주식 투자자 매매동향 (최근 5일)"""
    base_url = KIS_MOCK_URL if is_mock else KIS_REAL_URL
    url = f"{base_url}/uapi/domestic-stock/v1/quotations/inquire-investor"

    headers = {
        "Content-Type": "application/json; charset=utf-8",
        "authorization": f"Bearer {access_token}",
        "appkey": app_key,
        "appsecret": app_secret,
        "tr_id": "FHKST01010900",
    }

    params = {
        "FID_COND_MRKT_DIV_CODE": "J",
        "FID_INPUT_ISCD": stock_code,
    }

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(url, headers=headers, params=params)
            if resp.status_code == 200:
                data = resp.json()
                if data.get("rt_cd") == "0":
                    output = data.get("output", [])
                    results = []
                    for item in output[:5]:
                        results.append({
                            "date": item.get("stck_bsop_date", ""),
                            "foreign_net": int(item.get("frgn_ntby_qty", 0)),
                            "institution_net": int(item.get("orgn_ntby_qty", 0)),
                            "individual_net": int(item.get("prsn_ntby_qty", 0)),
                        })
                    return results
    except Exception as e:
        print(f"[KIS] Investor trend error: {e}")

    return None


async def get_daily_prices(
    app_key: str,
    app_secret: str,
    access_token: str,
    stock_code: str,
    market: str,  # KOSPI, KOSDAQ, NYSE, NASDAQ, AMEX
    days: int = 60,
    is_mock: bool = False
) -> Optional[List[Dict[str, Any]]]:
    """일봉 데이터 조회"""
    base_url = KIS_MOCK_URL if is_mock else KIS_REAL_URL

    if market in ("KOSPI", "KOSDAQ"):
        # 국내주식
        url = f"{base_url}/uapi/domestic-stock/v1/quotations/inquire-daily-itemchartprice"
        headers = {
            "Content-Type": "application/json; charset=utf-8",
            "authorization": f"Bearer {access_token}",
            "appkey": app_key,
            "appsecret": app_secret,
            "tr_id": "FHKST03010100",
        }

        end_date = datetime.now().strftime("%Y%m%d")
        start_date = (datetime.now() - timedelta(days=days + 30)).strftime("%Y%m%d")

        params = {
            "FID_COND_MRKT_DIV_CODE": "J",
            "FID_INPUT_ISCD": stock_code,
            "FID_INPUT_DATE_1": start_date,
            "FID_INPUT_DATE_2": end_date,
            "FID_PERIOD_DIV_CODE": "D",
            "FID_ORG_ADJ_PRC": "0",
        }
    else:
        # 해외주식
        url = f"{base_url}/uapi/overseas-price/v1/quotations/dailyprice"
        excd_map = {"NYSE": "NYS", "NASDAQ": "NAS", "AMEX": "AMS"}

        headers = {
            "Content-Type": "application/json; charset=utf-8",
            "authorization": f"Bearer {access_token}",
            "appkey": app_key,
            "appsecret": app_secret,
            "tr_id": "HHDFS76240000",
        }

        params = {
            "AUTH": "",
            "EXCD": excd_map.get(market, "NAS"),
            "SYMB": stock_code,
            "GUBN": "0",  # 일
            "BYMD": "",
            "MODP": "1",
        }

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(url, headers=headers, params=params)
            if resp.status_code == 200:
                data = resp.json()
                if data.get("rt_cd") == "0":
                    output = data.get("output2", data.get("output", []))
                    results = []

                    for item in output[:days]:
                        if market in ("KOSPI", "KOSDAQ"):
                            results.append({
                                "date": item.get("stck_bsop_date", ""),
                                "open": int(item.get("stck_oprc", 0)),
                                "high": int(item.get("stck_hgpr", 0)),
                                "low": int(item.get("stck_lwpr", 0)),
                                "close": int(item.get("stck_clpr", 0)),
                                "volume": int(item.get("acml_vol", 0)),
                            })
                        else:
                            results.append({
                                "date": item.get("xymd", ""),
                                "open": float(item.get("open", 0)),
                                "high": float(item.get("high", 0)),
                                "low": float(item.get("low", 0)),
                                "close": float(item.get("clos", 0)),
                                "volume": int(item.get("tvol", 0)),
                            })

                    return results
    except Exception as e:
        print(f"[KIS] Daily prices error: {e}")

    return None


# =====================================================
# 공개 API (KIS 계정 없이도 사용 가능)
# =====================================================

async def get_naver_stock_price(stock_code: str) -> Optional[Dict[str, Any]]:
    """네이버 금융에서 국내주식 시세 조회 (공개 API)"""
    # 네이버 금융 시세 API
    url = f"https://m.stock.naver.com/api/stock/{stock_code}/basic"

    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(url, headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
            })
            if resp.status_code == 200:
                data = resp.json()

                # 현재가 정보 추출
                current = int(data.get("closePrice", "0").replace(",", ""))
                change_amount = int(data.get("compareToPreviousClosePrice", "0").replace(",", ""))
                change_rate = float(data.get("fluctuationsRatio", "0"))
                high = int(data.get("highPrice", "0").replace(",", ""))
                low = int(data.get("lowPrice", "0").replace(",", ""))
                open_price = int(data.get("openPrice", "0").replace(",", ""))
                volume = int(data.get("accumulatedTradingVolume", "0").replace(",", ""))
                market_cap = int(data.get("marketValue", "0").replace(",", ""))

                return {
                    "current": current,
                    "change": change_rate,
                    "change_amount": change_amount,
                    "high": high,
                    "low": low,
                    "open": open_price,
                    "volume": volume,
                    "market_cap": market_cap,
                    "source": "naver"
                }
    except Exception as e:
        print(f"[Naver] Price error for {stock_code}: {e}")

    # 폴백: KRX API 시도
    return await get_krx_stock_price(stock_code)


async def get_krx_stock_price(stock_code: str) -> Optional[Dict[str, Any]]:
    """KRX에서 국내주식 시세 조회 (폴백)"""
    # KRX 시세 데이터
    url = "http://data.krx.co.kr/comm/bldAttendant/getJsonData.cmd"

    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            # KRX API 호출
            resp = await client.post(url, data={
                "bld": "dbms/MDC/STAT/standard/MDCSTAT01501",
                "isuCd": stock_code,
                "isuCd2": stock_code,
                "strtDd": datetime.now().strftime("%Y%m%d"),
                "endDd": datetime.now().strftime("%Y%m%d"),
            }, headers={
                "User-Agent": "Mozilla/5.0",
                "Content-Type": "application/x-www-form-urlencoded"
            })

            if resp.status_code == 200:
                data = resp.json()
                items = data.get("OutBlock_1", [])
                if items:
                    item = items[0]
                    return {
                        "current": int(item.get("TDD_CLSPRC", "0").replace(",", "")),
                        "change": float(item.get("FLUC_RT", "0").replace(",", "")),
                        "change_amount": int(item.get("CMPPREVDD_PRC", "0").replace(",", "")),
                        "high": int(item.get("TDD_HGPRC", "0").replace(",", "")),
                        "low": int(item.get("TDD_LWPRC", "0").replace(",", "")),
                        "open": int(item.get("TDD_OPNPRC", "0").replace(",", "")),
                        "volume": int(item.get("ACC_TRDVOL", "0").replace(",", "")),
                        "market_cap": 0,
                        "source": "krx"
                    }
    except Exception as e:
        print(f"[KRX] Price error for {stock_code}: {e}")

    return None


async def get_yahoo_stock_price(symbol: str, exchange: str = "NASDAQ") -> Optional[Dict[str, Any]]:
    """Yahoo Finance에서 해외주식 시세 조회 (공개 API)"""
    # Yahoo Finance v8 API
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}"

    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(url, params={
                "interval": "1d",
                "range": "1d"
            }, headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
            })

            if resp.status_code == 200:
                data = resp.json()
                result = data.get("chart", {}).get("result", [])

                if result:
                    meta = result[0].get("meta", {})
                    indicators = result[0].get("indicators", {})
                    quote = indicators.get("quote", [{}])[0]

                    current = meta.get("regularMarketPrice", 0)
                    prev_close = meta.get("previousClose", current)
                    change_amount = current - prev_close
                    change_rate = (change_amount / prev_close * 100) if prev_close else 0

                    # 오늘 데이터
                    high_list = quote.get("high", [])
                    low_list = quote.get("low", [])
                    open_list = quote.get("open", [])
                    volume_list = quote.get("volume", [])

                    return {
                        "current": current,
                        "change": round(change_rate, 2),
                        "change_amount": round(change_amount, 2),
                        "high": high_list[-1] if high_list else current,
                        "low": low_list[-1] if low_list else current,
                        "open": open_list[-1] if open_list else current,
                        "volume": volume_list[-1] if volume_list else 0,
                        "market_cap": meta.get("marketCap", 0),
                        "source": "yahoo"
                    }
    except Exception as e:
        print(f"[Yahoo] Price error for {symbol}: {e}")

    return None


async def get_yahoo_daily_prices(symbol: str, days: int = 60) -> Optional[List[Dict[str, Any]]]:
    """Yahoo Finance에서 일봉 데이터 조회"""
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}"

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(url, params={
                "interval": "1d",
                "range": "3mo"  # 약 60 거래일
            }, headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
            })

            if resp.status_code == 200:
                data = resp.json()
                result = data.get("chart", {}).get("result", [])

                if result:
                    timestamps = result[0].get("timestamp", [])
                    indicators = result[0].get("indicators", {})
                    quote = indicators.get("quote", [{}])[0]

                    opens = quote.get("open", [])
                    highs = quote.get("high", [])
                    lows = quote.get("low", [])
                    closes = quote.get("close", [])
                    volumes = quote.get("volume", [])

                    results = []
                    for i in range(min(len(timestamps), days)):
                        idx = len(timestamps) - days + i
                        if idx >= 0 and idx < len(timestamps):
                            dt = datetime.fromtimestamp(timestamps[idx])
                            results.append({
                                "date": dt.strftime("%Y%m%d"),
                                "open": opens[idx] if idx < len(opens) and opens[idx] else 0,
                                "high": highs[idx] if idx < len(highs) and highs[idx] else 0,
                                "low": lows[idx] if idx < len(lows) and lows[idx] else 0,
                                "close": closes[idx] if idx < len(closes) and closes[idx] else 0,
                                "volume": volumes[idx] if idx < len(volumes) and volumes[idx] else 0,
                            })

                    return results[-days:] if len(results) > days else results
    except Exception as e:
        print(f"[Yahoo] Daily prices error for {symbol}: {e}")

    return None


async def get_naver_daily_prices(stock_code: str, days: int = 60) -> Optional[List[Dict[str, Any]]]:
    """네이버 금융에서 국내주식 일봉 데이터 조회"""
    url = f"https://m.stock.naver.com/api/stock/{stock_code}/price"

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(url, params={
                "pageSize": days,
                "page": 1
            }, headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
            })

            if resp.status_code == 200:
                data = resp.json()
                items = data if isinstance(data, list) else data.get("priceInfos", [])

                results = []
                for item in items[:days]:
                    results.append({
                        "date": item.get("localDate", "").replace("-", ""),
                        "open": int(item.get("openPrice", "0").replace(",", "") if isinstance(item.get("openPrice"), str) else item.get("openPrice", 0)),
                        "high": int(item.get("highPrice", "0").replace(",", "") if isinstance(item.get("highPrice"), str) else item.get("highPrice", 0)),
                        "low": int(item.get("lowPrice", "0").replace(",", "") if isinstance(item.get("lowPrice"), str) else item.get("lowPrice", 0)),
                        "close": int(item.get("closePrice", "0").replace(",", "") if isinstance(item.get("closePrice"), str) else item.get("closePrice", 0)),
                        "volume": int(item.get("accumulatedTradingVolume", "0").replace(",", "") if isinstance(item.get("accumulatedTradingVolume"), str) else item.get("accumulatedTradingVolume", 0)),
                    })

                # 날짜 순 정렬 (오래된 것부터)
                results.reverse()
                return results
    except Exception as e:
        print(f"[Naver] Daily prices error for {stock_code}: {e}")

    return None


# =====================================================
# 시장분석 API (STEP 2)
# =====================================================

# 업종 코드 매핑
SECTOR_CODES = {
    "0001": "코스피",
    "1001": "코스닥",
    "0002": "대형주",
    "0003": "중형주",
    "0004": "소형주",
    "0005": "음식료업",
    "0006": "섬유의복",
    "0007": "종이목재",
    "0008": "화학",
    "0009": "의약품",
    "0010": "비금속광물",
    "0011": "철강금속",
    "0012": "기계",
    "0013": "전기전자",
    "0014": "의료정밀",
    "0015": "운수장비",
    "0016": "유통업",
    "0017": "전기가스업",
    "0018": "건설업",
    "0019": "운수창고",
    "0020": "통신업",
    "0021": "금융업",
    "0022": "은행",
    "0024": "증권",
    "0025": "보험",
    "0026": "서비스업",
    "0027": "제조업",
}


async def get_index_price(
    app_key: str,
    app_secret: str,
    access_token: str,
    index_code: str = "0001",  # 코스피
    is_mock: bool = False
) -> Optional[Dict[str, Any]]:
    """업종별 현재지수 조회"""
    base_url = KIS_MOCK_URL if is_mock else KIS_REAL_URL
    url = f"{base_url}/uapi/domestic-stock/v1/quotations/inquire-index-price"

    headers = {
        "Content-Type": "application/json; charset=utf-8",
        "authorization": f"Bearer {access_token}",
        "appkey": app_key,
        "appsecret": app_secret,
        "tr_id": "FHPUP02100000",
    }

    params = {
        "FID_COND_MRKT_DIV_CODE": "U",
        "FID_INPUT_ISCD": index_code,
    }

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(url, headers=headers, params=params)
            if resp.status_code == 200:
                data = resp.json()
                if data.get("rt_cd") == "0":
                    output = data.get("output", {})
                    return {
                        "index_code": index_code,
                        "name": SECTOR_CODES.get(index_code, ""),
                        "current": float(output.get("bstp_nmix_prpr", 0)),
                        "change": float(output.get("bstp_nmix_prdy_ctrt", 0)),
                        "change_amount": float(output.get("bstp_nmix_prdy_vrss", 0)),
                        "high": float(output.get("bstp_nmix_hgpr", 0)),
                        "low": float(output.get("bstp_nmix_lwpr", 0)),
                        "volume": int(output.get("acml_vol", 0)),
                        "value": int(output.get("acml_tr_pbmn", 0)),
                    }
    except Exception as e:
        print(f"[KIS] Index price error: {e}")

    return None


async def get_volume_rank(
    app_key: str,
    app_secret: str,
    access_token: str,
    market: str = "J",  # J: 전체, 0: 코스피, 1: 코스닥
    limit: int = 30,
    is_mock: bool = False
) -> Optional[List[Dict[str, Any]]]:
    """거래량 순위 조회"""
    base_url = KIS_MOCK_URL if is_mock else KIS_REAL_URL
    url = f"{base_url}/uapi/domestic-stock/v1/quotations/volume-rank"

    headers = {
        "Content-Type": "application/json; charset=utf-8",
        "authorization": f"Bearer {access_token}",
        "appkey": app_key,
        "appsecret": app_secret,
        "tr_id": "FHPST01710000",
    }

    params = {
        "FID_COND_MRKT_DIV_CODE": market,
        "FID_COND_SCR_DIV_CODE": "20101",
        "FID_INPUT_ISCD": "0000",
        "FID_DIV_CLS_CODE": "0",
        "FID_BLNG_CLS_CODE": "0",
        "FID_TRGT_CLS_CODE": "111111111",
        "FID_TRGT_EXLS_CLS_CODE": "000000",
        "FID_INPUT_PRICE_1": "",
        "FID_INPUT_PRICE_2": "",
        "FID_VOL_CNT": "",
        "FID_INPUT_DATE_1": "",
    }

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(url, headers=headers, params=params)
            if resp.status_code == 200:
                data = resp.json()
                if data.get("rt_cd") == "0":
                    output = data.get("output", [])
                    results = []
                    for item in output[:limit]:
                        results.append({
                            "rank": int(item.get("data_rank", 0)),
                            "code": item.get("stck_shrn_iscd", ""),
                            "name": item.get("hts_kor_isnm", ""),
                            "current": int(item.get("stck_prpr", 0)),
                            "change": float(item.get("prdy_ctrt", 0)),
                            "change_amount": int(item.get("prdy_vrss", 0)),
                            "volume": int(item.get("acml_vol", 0)),
                            "value": int(item.get("acml_tr_pbmn", 0)),
                            "market_cap": int(item.get("stck_avls", 0)),
                        })
                    return results
    except Exception as e:
        print(f"[KIS] Volume rank error: {e}")

    return None


async def get_fluctuation_rank(
    app_key: str,
    app_secret: str,
    access_token: str,
    market: str = "J",
    is_rise: bool = True,  # True: 상승률, False: 하락률
    limit: int = 30,
    is_mock: bool = False
) -> Optional[List[Dict[str, Any]]]:
    """등락률 순위 조회"""
    base_url = KIS_MOCK_URL if is_mock else KIS_REAL_URL
    url = f"{base_url}/uapi/domestic-stock/v1/ranking/fluctuation"

    headers = {
        "Content-Type": "application/json; charset=utf-8",
        "authorization": f"Bearer {access_token}",
        "appkey": app_key,
        "appsecret": app_secret,
        "tr_id": "FHPST01700000",
    }

    params = {
        "fid_cond_mrkt_div_code": market,
        "fid_cond_scr_div_code": "20170",
        "fid_input_iscd": "0000",
        "fid_rank_sort_cls_code": "0" if is_rise else "1",
        "fid_input_cnt_1": "0",
        "fid_prc_cls_code": "0",
        "fid_input_price_1": "",
        "fid_input_price_2": "",
        "fid_vol_cnt": "",
        "fid_trgt_cls_code": "0",
        "fid_trgt_exls_cls_code": "0",
        "fid_div_cls_code": "0",
        "fid_rsfl_rate1": "",
        "fid_rsfl_rate2": "",
    }

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(url, headers=headers, params=params)
            if resp.status_code == 200:
                data = resp.json()
                if data.get("rt_cd") == "0":
                    output = data.get("output", [])
                    results = []
                    for i, item in enumerate(output[:limit]):
                        results.append({
                            "rank": i + 1,
                            "code": item.get("stck_shrn_iscd", ""),
                            "name": item.get("hts_kor_isnm", ""),
                            "current": int(item.get("stck_prpr", 0)),
                            "change": float(item.get("prdy_ctrt", 0)),
                            "change_amount": int(item.get("prdy_vrss", 0)),
                            "volume": int(item.get("acml_vol", 0)),
                        })
                    return results
    except Exception as e:
        print(f"[KIS] Fluctuation rank error: {e}")

    return None


async def get_investor_daily(
    app_key: str,
    app_secret: str,
    access_token: str,
    market: str = "0001",  # 코스피
    is_mock: bool = False
) -> Optional[Dict[str, Any]]:
    """투자자별 매매동향 (일별)"""
    base_url = KIS_MOCK_URL if is_mock else KIS_REAL_URL
    url = f"{base_url}/uapi/domestic-stock/v1/quotations/inquire-daily-trade"

    headers = {
        "Content-Type": "application/json; charset=utf-8",
        "authorization": f"Bearer {access_token}",
        "appkey": app_key,
        "appsecret": app_secret,
        "tr_id": "FHPTJ04400000",
    }

    params = {
        "FID_COND_MRKT_DIV_CODE": "J",
        "FID_INPUT_ISCD": market,
        "FID_INPUT_DATE_1": datetime.now().strftime("%Y%m%d"),
        "FID_INPUT_DATE_2": datetime.now().strftime("%Y%m%d"),
    }

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(url, headers=headers, params=params)
            if resp.status_code == 200:
                data = resp.json()
                if data.get("rt_cd") == "0":
                    output = data.get("output", [])
                    if output:
                        item = output[0]
                        return {
                            "date": item.get("stck_bsop_date", ""),
                            "foreign_buy": int(item.get("frgn_pure_buy_qty", 0)),
                            "foreign_sell": int(item.get("frgn_pure_sll_qty", 0)),
                            "foreign_net": int(item.get("frgn_ntby_qty", 0)),
                            "institution_buy": int(item.get("orgn_pure_buy_qty", 0)),
                            "institution_sell": int(item.get("orgn_pure_sll_qty", 0)),
                            "institution_net": int(item.get("orgn_ntby_qty", 0)),
                            "individual_net": int(item.get("prsn_ntby_qty", 0)),
                        }
    except Exception as e:
        print(f"[KIS] Investor daily error: {e}")

    return None


async def get_market_cap_rank(
    app_key: str,
    app_secret: str,
    access_token: str,
    market: str = "J",
    limit: int = 50,
    is_mock: bool = False
) -> Optional[List[Dict[str, Any]]]:
    """시가총액 순위 조회"""
    base_url = KIS_MOCK_URL if is_mock else KIS_REAL_URL
    url = f"{base_url}/uapi/domestic-stock/v1/ranking/market-cap"

    headers = {
        "Content-Type": "application/json; charset=utf-8",
        "authorization": f"Bearer {access_token}",
        "appkey": app_key,
        "appsecret": app_secret,
        "tr_id": "FHPST01740000",
    }

    params = {
        "fid_cond_mrkt_div_code": market,
        "fid_cond_scr_div_code": "20174",
        "fid_input_iscd": "0000",
        "fid_div_cls_code": "0",
        "fid_trgt_cls_code": "0",
        "fid_trgt_exls_cls_code": "0",
        "fid_input_price_1": "",
        "fid_input_price_2": "",
        "fid_vol_cnt": "",
    }

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(url, headers=headers, params=params)
            if resp.status_code == 200:
                data = resp.json()
                if data.get("rt_cd") == "0":
                    output = data.get("output", [])
                    results = []
                    for i, item in enumerate(output[:limit]):
                        results.append({
                            "rank": i + 1,
                            "code": item.get("mksc_shrn_iscd", ""),
                            "name": item.get("hts_kor_isnm", ""),
                            "current": int(item.get("stck_prpr", 0)),
                            "change": float(item.get("prdy_ctrt", 0)),
                            "market_cap": int(item.get("stck_avls", 0)),
                            "per": float(item.get("per", 0) or 0),
                        })
                    return results
    except Exception as e:
        print(f"[KIS] Market cap rank error: {e}")

    return None


async def get_foreign_net_rank(
    app_key: str,
    app_secret: str,
    access_token: str,
    is_buy: bool = True,  # True: 순매수, False: 순매도
    limit: int = 30,
    is_mock: bool = False
) -> Optional[List[Dict[str, Any]]]:
    """외인 순매수/순매도 순위"""
    base_url = KIS_MOCK_URL if is_mock else KIS_REAL_URL
    url = f"{base_url}/uapi/domestic-stock/v1/quotations/foreign-institution-total"

    headers = {
        "Content-Type": "application/json; charset=utf-8",
        "authorization": f"Bearer {access_token}",
        "appkey": app_key,
        "appsecret": app_secret,
        "tr_id": "FHPTJ04010000",
    }

    params = {
        "FID_COND_MRKT_DIV_CODE": "V",
        "FID_COND_SCR_DIV_CODE": "16449",
        "FID_INPUT_ISCD": "0000",
        "FID_DIV_CLS_CODE": "1" if is_buy else "2",  # 1: 순매수, 2: 순매도
        "FID_RANK_SORT_CLS_CODE": "0",
        "FID_ETC_CLS_CODE": "",
        "FID_INPUT_DATE_1": datetime.now().strftime("%Y%m%d"),
        "FID_INPUT_DATE_2": datetime.now().strftime("%Y%m%d"),
    }

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(url, headers=headers, params=params)
            if resp.status_code == 200:
                data = resp.json()
                if data.get("rt_cd") == "0":
                    output = data.get("output", [])
                    results = []
                    for i, item in enumerate(output[:limit]):
                        results.append({
                            "rank": i + 1,
                            "code": item.get("stck_shrn_iscd", ""),
                            "name": item.get("hts_kor_isnm", ""),
                            "current": int(item.get("stck_prpr", 0)),
                            "change": float(item.get("prdy_ctrt", 0)),
                            "foreign_net_qty": int(item.get("frgn_ntby_qty", 0)),
                            "foreign_net_amt": int(item.get("frgn_ntby_tr_pbmn", 0)),
                        })
                    return results
    except Exception as e:
        print(f"[KIS] Foreign net rank error: {e}")

    return None


async def get_institution_net_rank(
    app_key: str,
    app_secret: str,
    access_token: str,
    is_buy: bool = True,
    limit: int = 30,
    is_mock: bool = False
) -> Optional[List[Dict[str, Any]]]:
    """기관 순매수/순매도 순위"""
    base_url = KIS_MOCK_URL if is_mock else KIS_REAL_URL
    url = f"{base_url}/uapi/domestic-stock/v1/quotations/foreign-institution-total"

    headers = {
        "Content-Type": "application/json; charset=utf-8",
        "authorization": f"Bearer {access_token}",
        "appkey": app_key,
        "appsecret": app_secret,
        "tr_id": "FHPTJ04010000",
    }

    params = {
        "FID_COND_MRKT_DIV_CODE": "V",
        "FID_COND_SCR_DIV_CODE": "16449",
        "FID_INPUT_ISCD": "0001",
        "FID_DIV_CLS_CODE": "1" if is_buy else "2",
        "FID_RANK_SORT_CLS_CODE": "1",  # 기관
        "FID_ETC_CLS_CODE": "",
        "FID_INPUT_DATE_1": datetime.now().strftime("%Y%m%d"),
        "FID_INPUT_DATE_2": datetime.now().strftime("%Y%m%d"),
    }

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(url, headers=headers, params=params)
            if resp.status_code == 200:
                data = resp.json()
                if data.get("rt_cd") == "0":
                    output = data.get("output", [])
                    results = []
                    for i, item in enumerate(output[:limit]):
                        results.append({
                            "rank": i + 1,
                            "code": item.get("stck_shrn_iscd", ""),
                            "name": item.get("hts_kor_isnm", ""),
                            "current": int(item.get("stck_prpr", 0)),
                            "change": float(item.get("prdy_ctrt", 0)),
                            "institution_net_qty": int(item.get("orgn_ntby_qty", 0)),
                            "institution_net_amt": int(item.get("orgn_ntby_tr_pbmn", 0)),
                        })
                    return results
    except Exception as e:
        print(f"[KIS] Institution net rank error: {e}")

    return None


# 공개 API로 지수 데이터 가져오기 (네이버 금융)
async def get_naver_index() -> Dict[str, Any]:
    """네이버 금융에서 주요 지수 조회 (공개)"""
    indices = {}

    # 코스피
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(
                "https://m.stock.naver.com/api/index/KOSPI/basic",
                headers={"User-Agent": "Mozilla/5.0"}
            )
            if resp.status_code == 200:
                data = resp.json()
                indices["kospi"] = {
                    "name": "코스피",
                    "current": float(data.get("closePrice", "0").replace(",", "")),
                    "change": float(data.get("fluctuationsRatio", 0)),
                    "change_amount": float(data.get("compareToPreviousClosePrice", "0").replace(",", "")),
                }
    except Exception as e:
        print(f"[Naver] KOSPI index error: {e}")

    # 코스닥
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(
                "https://m.stock.naver.com/api/index/KOSDAQ/basic",
                headers={"User-Agent": "Mozilla/5.0"}
            )
            if resp.status_code == 200:
                data = resp.json()
                indices["kosdaq"] = {
                    "name": "코스닥",
                    "current": float(data.get("closePrice", "0").replace(",", "")),
                    "change": float(data.get("fluctuationsRatio", 0)),
                    "change_amount": float(data.get("compareToPreviousClosePrice", "0").replace(",", "")),
                }
    except Exception as e:
        print(f"[Naver] KOSDAQ index error: {e}")

    return indices


async def get_yahoo_index() -> Dict[str, Any]:
    """Yahoo Finance에서 해외 지수 조회 (공개)"""
    indices = {}
    symbols = {
        "nasdaq": ("^IXIC", "나스닥"),
        "sp500": ("^GSPC", "S&P 500"),
        "dow": ("^DJI", "다우존스"),
    }

    for key, (symbol, name) in symbols.items():
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                resp = await client.get(
                    f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}",
                    params={"interval": "1d", "range": "1d"},
                    headers={"User-Agent": "Mozilla/5.0"}
                )
                if resp.status_code == 200:
                    data = resp.json()
                    result = data.get("chart", {}).get("result", [])
                    if result:
                        meta = result[0].get("meta", {})
                        current = meta.get("regularMarketPrice", 0)
                        prev = meta.get("previousClose", current)
                        change = ((current - prev) / prev * 100) if prev else 0

                        indices[key] = {
                            "name": name,
                            "current": round(current, 2),
                            "change": round(change, 2),
                            "change_amount": round(current - prev, 2),
                        }
        except Exception as e:
            print(f"[Yahoo] {key} index error: {e}")

    return indices


async def get_naver_sector_list() -> List[Dict[str, Any]]:
    """네이버 금융에서 업종별 현황 (공개)"""
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(
                "https://m.stock.naver.com/api/index/KOSPI/all",
                headers={"User-Agent": "Mozilla/5.0"}
            )
            if resp.status_code == 200:
                data = resp.json()
                sectors = data.get("sectors", [])
                results = []
                for sector in sectors:
                    results.append({
                        "code": sector.get("code", ""),
                        "name": sector.get("sectorName", ""),
                        "current": float(sector.get("closePrice", "0").replace(",", "")),
                        "change": float(sector.get("fluctuationsRatio", 0)),
                        "volume": int(sector.get("accumulatedTradingVolume", "0").replace(",", "") if sector.get("accumulatedTradingVolume") else 0),
                    })
                return results
    except Exception as e:
        print(f"[Naver] Sector list error: {e}")

    return []


async def get_naver_volume_rank(limit: int = 50) -> List[Dict[str, Any]]:
    """네이버 금융에서 거래량 순위 (공개)"""
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(
                "https://m.stock.naver.com/api/stocks/volume/KOSPI?page=1&pageSize=50",
                headers={"User-Agent": "Mozilla/5.0"}
            )
            if resp.status_code == 200:
                data = resp.json()
                stocks = data.get("stocks", [])
                results = []
                for i, stock in enumerate(stocks[:limit]):
                    results.append({
                        "rank": i + 1,
                        "code": stock.get("itemCode", ""),
                        "name": stock.get("stockName", ""),
                        "current": int(stock.get("closePrice", "0").replace(",", "")),
                        "change": float(stock.get("fluctuationsRatio", 0)),
                        "volume": int(stock.get("accumulatedTradingVolume", "0").replace(",", "")),
                    })
                return results
    except Exception as e:
        print(f"[Naver] Volume rank error: {e}")

    return []


async def get_naver_fluctuation_rank(is_rise: bool = True, limit: int = 50) -> List[Dict[str, Any]]:
    """네이버 금융에서 등락률 순위 (공개)"""
    try:
        endpoint = "rise" if is_rise else "fall"
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(
                f"https://m.stock.naver.com/api/stocks/{endpoint}/KOSPI?page=1&pageSize=50",
                headers={"User-Agent": "Mozilla/5.0"}
            )
            if resp.status_code == 200:
                data = resp.json()
                stocks = data.get("stocks", [])
                results = []
                for i, stock in enumerate(stocks[:limit]):
                    results.append({
                        "rank": i + 1,
                        "code": stock.get("itemCode", ""),
                        "name": stock.get("stockName", ""),
                        "current": int(stock.get("closePrice", "0").replace(",", "")),
                        "change": float(stock.get("fluctuationsRatio", 0)),
                        "volume": int(stock.get("accumulatedTradingVolume", "0").replace(",", "") if stock.get("accumulatedTradingVolume") else 0),
                    })
                return results
    except Exception as e:
        print(f"[Naver] Fluctuation rank error: {e}")

    return []

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

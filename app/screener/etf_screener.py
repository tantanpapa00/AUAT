"""
ETF 스크리너 (국내 상장 ETF)
네이버 금융 기반
"""

import asyncio
import httpx
from typing import List, Dict, Any, Optional
from datetime import datetime

from .cache import screener_cache, CACHE_TTL
from .filters import sort_screener_results


async def screener_etf(filters: dict, sort: str, order: str, page: int, per_page: int) -> dict:
    """
    국내 ETF 스크리너

    [흐름]
    1. 네이버 금융에서 ETF 전체 목록 (캐시 10분)
    2. 필터 적용 (운용사, 카테고리, 순자산, 등락률)
    3. 정렬 + 페이지네이션
    """
    # 캐시에서 ETF 전종목 데이터 가져오기
    all_etfs = await screener_cache.get_or_fetch(
        key="etf_all_stocks",
        ttl_seconds=CACHE_TTL.get("etf_all_stocks", 600),  # 10분
        fetch_fn=fetch_all_etfs
    )

    if not all_etfs:
        return {"items": [], "total": 0, "page": page, "per_page": per_page, "message": "데이터를 불러올 수 없습니다"}

    # 필터 적용
    filtered = apply_etf_filters(all_etfs, filters)

    # 정렬
    filtered = sort_etf_results(filtered, sort, order)

    total = len(filtered)

    # 페이지네이션
    start = (page - 1) * per_page
    end = start + per_page
    items = filtered[start:end]

    # 순자산 문자열 추가
    for item in items:
        nav = item.get("nav", 0)  # 억원 단위
        if nav >= 10000:
            item["nav_str"] = f"{nav / 10000:.1f}조"
        elif nav >= 1:
            item["nav_str"] = f"{int(nav)}억"
        else:
            item["nav_str"] = "-"

    return {
        "items": items,
        "total": total,
        "page": page,
        "per_page": per_page,
        "filters_applied": list(filters.keys()),
    }


def apply_etf_filters(etfs: List[Dict], filters: dict) -> List[Dict]:
    """ETF 전용 필터 적용"""
    result = etfs

    # 운용사 필터
    if filters.get("issuer"):
        issuer = filters["issuer"]
        if isinstance(issuer, dict):
            issuer = issuer.get("value", issuer)
        result = [e for e in result if e.get("issuer") == issuer]

    # 카테고리 필터
    if filters.get("category"):
        cat = filters["category"]
        if isinstance(cat, dict):
            cat = cat.get("value", cat)
        result = [e for e in result if e.get("category") == cat]

    # 순자산 필터 (억원 단위)
    if filters.get("nav"):
        nav_filter = filters["nav"]
        if isinstance(nav_filter, dict):
            min_val = nav_filter.get("min", 0)
            max_val = nav_filter.get("max")
            result = [e for e in result if e.get("nav", 0) >= min_val]
            if max_val:
                result = [e for e in result if e.get("nav", 0) <= max_val]

    # 등락률 필터
    if filters.get("change_pct"):
        cp_filter = filters["change_pct"]
        if isinstance(cp_filter, dict):
            min_val = cp_filter.get("min")
            max_val = cp_filter.get("max")
            if min_val is not None:
                result = [e for e in result if (e.get("change_pct") or 0) >= min_val]
            if max_val is not None:
                result = [e for e in result if (e.get("change_pct") or 0) <= max_val]

    return result


def sort_etf_results(etfs: List[Dict], sort: str, order: str) -> List[Dict]:
    """ETF 정렬"""
    reverse = order.lower() == "desc"

    sort_keys = {
        "nav": lambda x: x.get("nav") or 0,
        "price": lambda x: x.get("price") or 0,
        "change_pct": lambda x: x.get("change_pct") or 0,
        "volume": lambda x: x.get("volume") or 0,
        "name": lambda x: x.get("name") or "",
        "code": lambda x: x.get("code") or "",
        "issuer": lambda x: x.get("issuer") or "",
    }

    key_fn = sort_keys.get(sort, sort_keys["nav"])

    try:
        return sorted(etfs, key=key_fn, reverse=reverse)
    except Exception:
        return etfs


async def fetch_all_etfs() -> List[Dict]:
    """
    네이버 금융에서 ETF 전체 목록 가져오기
    https://finance.naver.com/api/sise/etfItemList.naver
    """
    all_etfs = []
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Referer": "https://finance.naver.com/"
    }

    try:
        async with httpx.AsyncClient(timeout=30, headers=headers) as client:
            # 네이버 금융 ETF API
            url = "https://finance.naver.com/api/sise/etfItemList.naver"
            resp = await client.get(url)

            if resp.status_code != 200:
                print(f"[ETF Screener] API 오류: {resp.status_code}")
                return all_etfs

            data = resp.json()
            result = data.get("result", {})
            stocks = result.get("etfItemList", [])

            if not stocks:
                print("[ETF Screener] etfItemList가 비어있음")
                return all_etfs

            for s in stocks:
                try:
                    # 네이버 금융 ETF API 필드명
                    # itemcode, itemname, nowVal, changeRate, quant, nav, marketSum
                    code = s.get("itemcode", "")
                    name = s.get("itemname", "")
                    price = _parse_price(s.get("nowVal", 0))
                    change_pct = _parse_float(s.get("changeRate", 0))
                    volume = _parse_int(s.get("quant", 0))
                    nav = _parse_float(s.get("nav", 0))  # 순자산
                    market_sum = _parse_float(s.get("marketSum", 0))  # 시가총액 (억원)

                    issuer = _extract_issuer(name)
                    category = _extract_category(name)

                    all_etfs.append({
                        "code": code,
                        "name": name,
                        "price": price,
                        "change_pct": change_pct,
                        "volume": volume,
                        "nav": market_sum,  # 시가총액을 nav로 사용 (억원)
                        "issuer": issuer,
                        "category": category,
                        "exchange": "ETF",
                    })
                except Exception as e:
                    continue

    except Exception as e:
        print(f"[ETF Screener] 오류: {e}")
        import traceback
        traceback.print_exc()

    print(f"[ETF Screener] {len(all_etfs)}개 ETF 로드 완료")
    return all_etfs


def _extract_issuer(name: str) -> str:
    """ETF 이름에서 운용사 추출"""
    issuers = {
        "KODEX": "삼성자산운용",
        "TIGER": "미래에셋자산운용",
        "KBSTAR": "KB자산운용",
        "ACE": "한국투자신탁운용",
        "ARIRANG": "한화자산운용",
        "KOSEF": "키움투자자산운용",
        "SOL": "신한자산운용",
        "HANARO": "NH-Amundi자산운용",
        "TIMEFOLIO": "타임폴리오자산운용",
        "KINDEX": "한국투자신탁운용",
    }

    name_upper = name.upper()
    for prefix, issuer in issuers.items():
        if name_upper.startswith(prefix):
            return issuer
    return "기타"


def _extract_category(name: str) -> str:
    """ETF 이름에서 카테고리 추출"""
    categories = {
        "200": "인덱스",
        "나스닥": "해외",
        "S&P": "해외",
        "미국": "해외",
        "중국": "해외",
        "일본": "해외",
        "인도": "해외",
        "반도체": "섹터",
        "2차전지": "섹터",
        "바이오": "섹터",
        "헬스케어": "섹터",
        "금융": "섹터",
        "에너지": "섹터",
        "레버리지": "레버리지/인버스",
        "인버스": "레버리지/인버스",
        "곱버스": "레버리지/인버스",
        "금": "원자재",
        "은": "원자재",
        "원유": "원자재",
        "달러": "통화",
        "채권": "채권",
        "국채": "채권",
        "회사채": "채권",
        "배당": "테마",
        "ESG": "테마",
    }

    for keyword, category in categories.items():
        if keyword in name:
            return category
    return "기타"


def _parse_float(val) -> float:
    """문자열을 float로 변환"""
    if val is None:
        return 0.0
    if isinstance(val, (int, float)):
        return float(val)
    try:
        cleaned = str(val).replace(",", "").replace(" ", "").strip()
        if not cleaned or cleaned == "-":
            return 0.0
        return float(cleaned)
    except (ValueError, TypeError):
        return 0.0


def _parse_price(val) -> int:
    """문자열을 int 가격으로 변환"""
    if val is None:
        return 0
    if isinstance(val, (int, float)):
        return int(val)
    try:
        cleaned = str(val).replace(",", "").replace(" ", "").strip()
        if not cleaned or cleaned == "-":
            return 0
        return int(float(cleaned))
    except (ValueError, TypeError):
        return 0


def _parse_int(val) -> int:
    """문자열을 int로 변환"""
    if val is None:
        return 0
    if isinstance(val, (int, float)):
        return int(val)
    try:
        cleaned = str(val).replace(",", "").replace(" ", "").strip()
        if not cleaned or cleaned == "-":
            return 0
        return int(float(cleaned))
    except (ValueError, TypeError):
        return 0


# 필터 키 정의 (ETF 전용)
ETF_FILTER_KEYS = [
    "issuer", "category", "nav", "change_pct"
]

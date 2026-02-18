"""
스크리너 필터 함수 모음
"""

from typing import List, Dict, Any


def apply_screener_filters(stocks: List[Dict], filters: Dict) -> List[Dict]:
    """필터 적용 메인 함수"""
    result = stocks

    # === 기본정보 필터 ===
    # 거래소 필터
    if filters.get("exchange"):
        exchange = filters["exchange"].upper()
        result = [s for s in result if s.get("exchange", "").upper() == exchange]

    # 업종 필터
    if filters.get("sector"):
        sector = filters["sector"]
        result = [s for s in result if s.get("sector") == sector]

    # 시가총액 필터
    if filters.get("market_cap"):
        cap_filter = filters["market_cap"]
        if cap_filter == "mega":  # 10조 이상
            result = [s for s in result if (s.get("market_cap") or 0) >= 10_000_000_000_000]
        elif cap_filter == "large":  # 1조~10조
            result = [s for s in result if 1_000_000_000_000 <= (s.get("market_cap") or 0) < 10_000_000_000_000]
        elif cap_filter == "mid":  # 5천억~1조
            result = [s for s in result if 500_000_000_000 <= (s.get("market_cap") or 0) < 1_000_000_000_000]
        elif cap_filter == "small":  # 1천억~5천억
            result = [s for s in result if 100_000_000_000 <= (s.get("market_cap") or 0) < 500_000_000_000]
        elif cap_filter == "micro":  # 1천억 미만
            result = [s for s in result if (s.get("market_cap") or 0) < 100_000_000_000]

    # 현재가 범위
    if filters.get("price_min"):
        result = [s for s in result if (s.get("price") or 0) >= filters["price_min"]]
    if filters.get("price_max"):
        result = [s for s in result if (s.get("price") or 0) <= filters["price_max"]]

    # 거래량 필터
    if filters.get("volume_min"):
        result = [s for s in result if (s.get("volume") or 0) >= filters["volume_min"]]

    # === 재무지표 필터 ===
    if filters.get("per"):
        result = _filter_by_range(result, "per", filters["per"])

    if filters.get("pbr"):
        result = _filter_by_range(result, "pbr", filters["pbr"])

    if filters.get("roe"):
        result = _filter_by_range(result, "roe", filters["roe"])

    if filters.get("operating_margin"):
        result = _filter_by_range(result, "operating_margin", filters["operating_margin"])

    if filters.get("debt_ratio"):
        result = _filter_by_range(result, "debt_ratio", filters["debt_ratio"])

    if filters.get("dividend_yield"):
        result = _filter_by_range(result, "dividend_yield", filters["dividend_yield"])

    # === 기술적지표 필터 ===
    # 등락률 필터
    if filters.get("change_filter"):
        result = _filter_by_change(result, filters["change_filter"])

    # 52주 고가 대비 필터
    if filters.get("w52_high"):
        result = _filter_by_52w(result, filters["w52_high"])

    # 거래량 급증 필터
    if filters.get("volume_surge"):
        threshold = float(filters["volume_surge"])
        result = [s for s in result if (s.get("volume_surge") or 0) >= threshold]

    # 이동평균선 필터
    if filters.get("sma20"):
        result = _filter_by_sma(result, "sma20", filters["sma20"])

    if filters.get("sma60"):
        result = _filter_by_sma(result, "sma60", filters["sma60"])

    if filters.get("sma120"):
        result = _filter_by_sma(result, "sma120", filters["sma120"])

    return result


def _filter_by_range(stocks: List[Dict], field: str, value: str) -> List[Dict]:
    """
    범위 필터 통합 파서
    지원 포맷:
    - "0~10"      → 0 <= x < 10
    - "10+"       → x >= 10
    - "10 이상"   → x >= 10
    - "loss"      → x < 0
    - "적자"      → x < 0
    """
    if not value:
        return stocks

    value = value.strip()

    # 적자/역성장
    if value in ("loss", "적자", "역성장"):
        return [s for s in stocks if s.get(field) is not None and s.get(field) < 0]

    # "N+" 또는 "N 이상" 또는 "N%+"
    if value.endswith("+") or "이상" in value:
        num_str = value.replace("+", "").replace("이상", "").replace("%", "").strip()
        try:
            threshold = float(num_str)
            return [s for s in stocks if s.get(field) is not None and s.get(field) >= threshold]
        except ValueError:
            return stocks

    # "A~B" 범위
    if "~" in value:
        parts = value.replace("%", "").split("~")
        try:
            lo = float(parts[0].strip())
            hi_str = parts[1].strip().replace("+", "")
            hi = float(hi_str) if hi_str else float("inf")
            return [s for s in stocks if s.get(field) is not None and lo <= s.get(field) < hi]
        except (ValueError, IndexError):
            return stocks

    # 단일 숫자 (배수 등)
    try:
        threshold = float(value)
        return [s for s in stocks if s.get(field) is not None and s.get(field) >= threshold]
    except ValueError:
        return stocks


def _filter_by_change(stocks: List[Dict], value: str) -> List[Dict]:
    """등락률 필터"""
    if not value:
        return stocks

    # up3, up5, up10, down3, down5, down10
    if value == "up3":
        return [s for s in stocks if (s.get("change_pct") or 0) >= 3]
    elif value == "up5":
        return [s for s in stocks if (s.get("change_pct") or 0) >= 5]
    elif value == "up10":
        return [s for s in stocks if (s.get("change_pct") or 0) >= 10]
    elif value == "down3":
        return [s for s in stocks if (s.get("change_pct") or 0) <= -3]
    elif value == "down5":
        return [s for s in stocks if (s.get("change_pct") or 0) <= -5]
    elif value == "down10":
        return [s for s in stocks if (s.get("change_pct") or 0) <= -10]

    # +3, -3 형식
    if value.startswith("+"):
        try:
            threshold = float(value[1:])
            return [s for s in stocks if (s.get("change_pct") or 0) >= threshold]
        except ValueError:
            pass
    elif value.startswith("-"):
        try:
            threshold = float(value)
            return [s for s in stocks if (s.get("change_pct") or 0) <= threshold]
        except ValueError:
            pass

    return stocks


def _filter_by_52w(stocks: List[Dict], value: str) -> List[Dict]:
    """52주 고가 대비 필터 (비율)"""
    if not value:
        return stocks

    # w52_high_pct: (52주고가 - 현재가) / 52주고가 = 0 ~ 1
    if value == "0~5":
        return [s for s in stocks if s.get("w52_high_pct") is not None and 0 <= s["w52_high_pct"] < 0.05]
    elif value == "5~10":
        return [s for s in stocks if s.get("w52_high_pct") is not None and 0.05 <= s["w52_high_pct"] < 0.10]
    elif value == "10~20":
        return [s for s in stocks if s.get("w52_high_pct") is not None and 0.10 <= s["w52_high_pct"] < 0.20]
    elif value == "20+":
        return [s for s in stocks if s.get("w52_high_pct") is not None and s["w52_high_pct"] >= 0.20]

    return stocks


def _filter_by_sma(stocks: List[Dict], sma_field: str, value: str) -> List[Dict]:
    """이동평균선 필터"""
    if not value:
        return stocks

    if value == "above":
        return [s for s in stocks if s.get(sma_field) and s.get("price") and s["price"] > s[sma_field]]
    elif value == "below":
        return [s for s in stocks if s.get(sma_field) and s.get("price") and s["price"] < s[sma_field]]
    elif value == "near":
        # ±2% 이내
        return [s for s in stocks if s.get(sma_field) and s.get("price") and abs(s["price"] - s[sma_field]) / s[sma_field] <= 0.02]

    return stocks


def sort_screener_results(stocks: List[Dict], sort: str, order: str) -> List[Dict]:
    """정렬"""
    reverse = order.lower() == "desc"

    sort_keys = {
        "market_cap": lambda x: x.get("market_cap") or 0,
        "price": lambda x: x.get("price") or 0,
        "change_pct": lambda x: x.get("change_pct") or 0,
        "volume": lambda x: x.get("volume") or 0,
        "per": lambda x: x.get("per") or 9999,
        "pbr": lambda x: x.get("pbr") or 9999,
        "roe": lambda x: x.get("roe") or -9999,
        "w52_high_pct": lambda x: x.get("w52_high_pct") or 9999,
        "dividend_yield": lambda x: x.get("dividend_yield") or 0,
        "name": lambda x: x.get("name") or "",
        "code": lambda x: x.get("code") or "",
    }

    key_fn = sort_keys.get(sort, sort_keys["market_cap"])

    try:
        return sorted(stocks, key=key_fn, reverse=reverse)
    except Exception:
        return stocks

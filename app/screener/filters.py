"""
스크리너 필터 함수 모음
기본정보 + 재무지표 + 기술적지표 필터 지원
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
        try:
            price_min = float(filters["price_min"])
            result = [s for s in result if (s.get("price") or 0) >= price_min]
        except (ValueError, TypeError):
            pass
    if filters.get("price_max"):
        try:
            price_max = float(filters["price_max"])
            result = [s for s in result if (s.get("price") or 0) <= price_max]
        except (ValueError, TypeError):
            pass

    # 거래량 필터
    if filters.get("volume_min"):
        try:
            vol_min = int(filters["volume_min"])
            result = [s for s in result if (s.get("volume") or 0) >= vol_min]
        except (ValueError, TypeError):
            pass

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
    # 등락률 필터 (change_filter 또는 change)
    if filters.get("change_filter"):
        result = _filter_by_change(result, filters["change_filter"])
    if filters.get("change"):
        result = _filter_by_change(result, filters["change"])

    # 52주 고가 대비 필터
    if filters.get("w52_high"):
        result = _filter_by_52w_high(result, filters["w52_high"])

    # 52주 저가 대비 필터
    if filters.get("w52_low"):
        result = _filter_by_52w_low(result, filters["w52_low"])

    # 거래량 급증 필터
    if filters.get("volume_surge"):
        try:
            threshold = float(filters["volume_surge"])
            result = [s for s in result if (s.get("volume_surge") or 0) >= threshold]
        except (ValueError, TypeError):
            pass

    # 이동평균선 필터 (SSOT 기준: 20/50/200일)
    if filters.get("sma20"):
        result = _filter_by_sma_position(result, "sma20_position", filters["sma20"])

    if filters.get("sma50"):
        result = _filter_by_sma_position(result, "sma50_position", filters["sma50"])

    if filters.get("sma200"):
        result = _filter_by_sma_position(result, "sma200_position", filters["sma200"])

    # 레거시 지원 (sma60 → sma50, sma120 → sma200)
    if filters.get("sma60"):
        result = _filter_by_sma_position(result, "sma50_position", filters["sma60"])
    if filters.get("sma120"):
        result = _filter_by_sma_position(result, "sma200_position", filters["sma120"])

    # 이평선 교차 필터
    if filters.get("sma_cross"):
        cross_val = filters["sma_cross"]
        if cross_val == "golden":
            result = [s for s in result if s.get("sma_cross") == "golden"]
        elif cross_val == "dead":
            result = [s for s in result if s.get("sma_cross") == "dead"]

    # RSI 필터
    if filters.get("rsi"):
        result = _filter_by_rsi(result, filters["rsi"])

    # 볼린저밴드 필터
    if filters.get("bollinger"):
        bb_val = filters["bollinger"]
        if bb_val == "upper":
            result = [s for s in result if s.get("bb_position") == "upper"]
        elif bb_val == "lower":
            result = [s for s in result if s.get("bb_position") == "lower"]
        elif bb_val == "middle":
            result = [s for s in result if s.get("bb_position") == "middle"]

    # MACD 필터
    if filters.get("macd"):
        macd_val = filters["macd"]
        if macd_val == "buy":
            result = [s for s in result if s.get("macd_cross") == "buy"]
        elif macd_val == "sell":
            result = [s for s in result if s.get("macd_cross") == "sell"]

    # 스토캐스틱 필터
    if filters.get("stochastic"):
        result = _filter_by_stochastic(result, filters["stochastic"])

    # ATR 필터 (변동성)
    if filters.get("atr"):
        result = _filter_by_atr(result, filters["atr"])

    # 기간 수익률 필터
    if filters.get("period_return"):
        result = _filter_by_period_return(result, filters["period_return"])

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

    value = str(value).strip()

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

    value = str(value).strip()

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


def _filter_by_52w_high(stocks: List[Dict], value: str) -> List[Dict]:
    """52주 고가 대비 필터 (w52_high_pct: 음수 = 고가 대비 하락)"""
    if not value:
        return stocks

    # w52_high_pct: (현재가 - 52주고가) / 52주고가 * 100 = 음수~0
    # 예: -5% = 52주고가 대비 5% 하락
    if value == "0~5":
        return [s for s in stocks if s.get("w52_high_pct") is not None and -5 <= s["w52_high_pct"] <= 0]
    elif value == "5~10":
        return [s for s in stocks if s.get("w52_high_pct") is not None and -10 <= s["w52_high_pct"] < -5]
    elif value == "10~20":
        return [s for s in stocks if s.get("w52_high_pct") is not None and -20 <= s["w52_high_pct"] < -10]
    elif value == "20+":
        return [s for s in stocks if s.get("w52_high_pct") is not None and s["w52_high_pct"] < -20]

    return stocks


def _filter_by_52w_low(stocks: List[Dict], value: str) -> List[Dict]:
    """52주 저가 대비 필터 (w52_low_pct: 양수 = 저가 대비 상승)"""
    if not value:
        return stocks

    # w52_low_pct: (현재가 - 52주저가) / 52주저가 * 100 = 0~양수
    if value == "0~5":
        return [s for s in stocks if s.get("w52_low_pct") is not None and 0 <= s["w52_low_pct"] < 5]
    elif value == "5~10":
        return [s for s in stocks if s.get("w52_low_pct") is not None and 5 <= s["w52_low_pct"] < 10]
    elif value == "10~20":
        return [s for s in stocks if s.get("w52_low_pct") is not None and 10 <= s["w52_low_pct"] < 20]
    elif value == "20+":
        return [s for s in stocks if s.get("w52_low_pct") is not None and s["w52_low_pct"] >= 20]

    return stocks


def _filter_by_sma_position(stocks: List[Dict], position_field: str, value: str) -> List[Dict]:
    """이동평균선 위치 필터"""
    if not value:
        return stocks

    if value == "above":
        return [s for s in stocks if s.get(position_field) == "above"]
    elif value == "below":
        return [s for s in stocks if s.get(position_field) == "below"]
    elif value == "near":
        return [s for s in stocks if s.get(position_field) == "near"]

    return stocks


def _filter_by_rsi(stocks: List[Dict], value: str) -> List[Dict]:
    """RSI 필터"""
    if not value:
        return stocks

    # 과매수(70+), 과매도(30-), 중립(30~70)
    if value in ("overbought", "과매수", "70+"):
        return [s for s in stocks if s.get("rsi") is not None and s["rsi"] >= 70]
    elif value in ("oversold", "과매도", "30-"):
        return [s for s in stocks if s.get("rsi") is not None and s["rsi"] <= 30]
    elif value in ("neutral", "중립", "30~70"):
        return [s for s in stocks if s.get("rsi") is not None and 30 < s["rsi"] < 70]

    return stocks


def _filter_by_stochastic(stocks: List[Dict], value: str) -> List[Dict]:
    """스토캐스틱 필터"""
    if not value:
        return stocks

    # 과매수(80+), 과매도(20-)
    if value in ("overbought", "과매수", "80+"):
        return [s for s in stocks if s.get("stoch_k") is not None and s["stoch_k"] >= 80]
    elif value in ("oversold", "과매도", "20-"):
        return [s for s in stocks if s.get("stoch_k") is not None and s["stoch_k"] <= 20]

    return stocks


def _filter_by_atr(stocks: List[Dict], value: str) -> List[Dict]:
    """ATR(변동성) 필터 - 현재가 대비 ATR 비율"""
    if not value:
        return stocks

    # ATR/현재가 비율로 변동성 판단
    # 고변동: 3%+, 중변동: 1.5~3%, 저변동: 1.5% 미만
    if value in ("high", "고변동"):
        return [s for s in stocks if s.get("atr") and s.get("price") and (s["atr"] / s["price"] * 100) >= 3]
    elif value in ("medium", "중변동"):
        return [s for s in stocks if s.get("atr") and s.get("price") and 1.5 <= (s["atr"] / s["price"] * 100) < 3]
    elif value in ("low", "저변동"):
        return [s for s in stocks if s.get("atr") and s.get("price") and (s["atr"] / s["price"] * 100) < 1.5]

    return stocks


def _filter_by_period_return(stocks: List[Dict], value: str) -> List[Dict]:
    """기간 수익률 필터"""
    if not value:
        return stocks

    # 1주+10%, 1개월+20%, 3개월+30%
    if value == "1w+10":
        return [s for s in stocks if s.get("period_return_1w") is not None and s["period_return_1w"] >= 10]
    elif value == "1m+20":
        return [s for s in stocks if s.get("period_return_1m") is not None and s["period_return_1m"] >= 20]
    elif value == "3m+30":
        return [s for s in stocks if s.get("period_return_3m") is not None and s["period_return_3m"] >= 30]
    elif value == "1w-10":
        return [s for s in stocks if s.get("period_return_1w") is not None and s["period_return_1w"] <= -10]
    elif value == "1m-20":
        return [s for s in stocks if s.get("period_return_1m") is not None and s["period_return_1m"] <= -20]

    return stocks


def sort_screener_results(stocks: List[Dict], sort: str, order: str) -> List[Dict]:
    """정렬"""
    reverse = order.lower() == "desc"

    sort_keys = {
        # 기본
        "market_cap": lambda x: x.get("market_cap") or 0,
        "price": lambda x: x.get("price") or 0,
        "change_pct": lambda x: x.get("change_pct") or 0,
        "volume": lambda x: x.get("volume") or 0,
        "name": lambda x: x.get("name") or "",
        "code": lambda x: x.get("code") or "",
        # 재무
        "per": lambda x: x.get("per") or 9999,
        "pbr": lambda x: x.get("pbr") or 9999,
        "roe": lambda x: x.get("roe") or -9999,
        "dividend_yield": lambda x: x.get("dividend_yield") or 0,
        # 52주
        "w52_high_pct": lambda x: x.get("w52_high_pct") or -9999,
        "w52_low_pct": lambda x: x.get("w52_low_pct") or 0,
        # 기술적
        "rsi": lambda x: x.get("rsi") or 50,
        "volume_surge": lambda x: x.get("volume_surge") or 0,
        "sma20": lambda x: x.get("sma20") or 0,
        "sma50": lambda x: x.get("sma50") or 0,
        "sma200": lambda x: x.get("sma200") or 0,
        "atr": lambda x: x.get("atr") or 0,
        # 기간 수익률
        "period_return_1w": lambda x: x.get("period_return_1w") or 0,
        "period_return_1m": lambda x: x.get("period_return_1m") or 0,
        "period_return_3m": lambda x: x.get("period_return_3m") or 0,
    }

    key_fn = sort_keys.get(sort, sort_keys["market_cap"])

    try:
        return sorted(stocks, key=key_fn, reverse=reverse)
    except Exception:
        return stocks

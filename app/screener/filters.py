"""
스크리너 필터 함수 모음
기본정보 + 재무지표 + 기술적지표 필터 지원

필터 포맷 V2:
- 레거시: {"rsi": "70+"}
- V2: {"rsi": {"min": 70, "max": null, "params": {"period": 7}}}
"""

from typing import List, Dict, Any, Union, Tuple


def _parse_filter_v2(value: Any) -> Tuple[float, float, Dict]:
    """
    V2 필터 파서 - min/max/params 추출

    반환: (min_val, max_val, params)
    - min_val: 최소값 (None이면 제한 없음)
    - max_val: 최대값 (None이면 제한 없음)
    - params: 파라미터 딕셔너리
    """
    if value is None:
        return None, None, {}

    # V2 포맷: {"min": 70, "max": null, "params": {...}}
    if isinstance(value, dict):
        min_val = value.get('min')
        max_val = value.get('max')
        params = value.get('params', {})
        return min_val, max_val, params

    # 레거시 문자열 포맷
    value = str(value).strip()

    # 적자/역성장
    if value in ("loss", "적자", "역성장"):
        return None, 0, {}

    # "N+" 또는 "N 이상"
    if value.endswith("+") or "이상" in value:
        num_str = value.replace("+", "").replace("이상", "").replace("%", "").strip()
        try:
            return float(num_str), None, {}
        except ValueError:
            return None, None, {}

    # "A~B" 범위
    if "~" in value:
        parts = value.replace("%", "").split("~")
        try:
            lo = float(parts[0].strip())
            hi_str = parts[1].strip().replace("+", "")
            hi = float(hi_str) if hi_str else None
            return lo, hi, {}
        except (ValueError, IndexError):
            return None, None, {}

    # 단일 숫자
    try:
        return float(value), None, {}
    except ValueError:
        return None, None, {}


def _filter_by_minmax(stocks: List[Dict], field: str, min_val: float, max_val: float) -> List[Dict]:
    """min/max 범위 필터"""
    result = []
    for s in stocks:
        val = s.get(field)
        if val is None:
            continue
        if min_val is not None and val < min_val:
            continue
        if max_val is not None and val > max_val:
            continue
        result.append(s)
    return result


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

    # === 재무지표 필터 (V2 포맷 지원) ===
    # PER
    if filters.get("per"):
        min_val, max_val, _ = _parse_filter_v2(filters["per"])
        if min_val is not None or max_val is not None:
            result = _filter_by_minmax(result, "per", min_val, max_val)
        else:
            result = _filter_by_range(result, "per", filters["per"])

    # PBR
    if filters.get("pbr"):
        min_val, max_val, _ = _parse_filter_v2(filters["pbr"])
        if min_val is not None or max_val is not None:
            result = _filter_by_minmax(result, "pbr", min_val, max_val)
        else:
            result = _filter_by_range(result, "pbr", filters["pbr"])

    # ROE
    if filters.get("roe"):
        min_val, max_val, _ = _parse_filter_v2(filters["roe"])
        if min_val is not None or max_val is not None:
            result = _filter_by_minmax(result, "roe", min_val, max_val)
        else:
            result = _filter_by_range(result, "roe", filters["roe"])

    # 영업이익률
    if filters.get("operating_margin"):
        min_val, max_val, _ = _parse_filter_v2(filters["operating_margin"])
        if min_val is not None or max_val is not None:
            result = _filter_by_minmax(result, "operating_margin", min_val, max_val)
        else:
            result = _filter_by_range(result, "operating_margin", filters["operating_margin"])

    # 부채비율
    if filters.get("debt_ratio"):
        min_val, max_val, _ = _parse_filter_v2(filters["debt_ratio"])
        if min_val is not None or max_val is not None:
            result = _filter_by_minmax(result, "debt_ratio", min_val, max_val)
        else:
            result = _filter_by_range(result, "debt_ratio", filters["debt_ratio"])

    # 배당수익률
    if filters.get("dividend_yield"):
        min_val, max_val, _ = _parse_filter_v2(filters["dividend_yield"])
        if min_val is not None or max_val is not None:
            result = _filter_by_minmax(result, "dividend_yield", min_val, max_val)
        else:
            result = _filter_by_range(result, "dividend_yield", filters["dividend_yield"])

    # 추가 재무지표 (V2)
    for field in ["psr", "roa", "net_margin", "current_ratio", "quick_ratio",
                  "reserve_ratio", "eps_growth", "bps", "sales_growth", "op_growth",
                  "payout_ratio", "foreign_ratio"]:
        if filters.get(field):
            min_val, max_val, _ = _parse_filter_v2(filters[field])
            if min_val is not None or max_val is not None:
                result = _filter_by_minmax(result, field, min_val, max_val)

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

    # 동적 이동평균선 필터 (V2: sma_SMA_20, sma_EMA_7 등)
    for key, value in filters.items():
        if key.startswith("sma_") and "_" in key[4:]:
            # 예: sma_SMA_20, sma_EMA_7, sma_WMA_50
            position_key = f"{key}_position"
            if isinstance(value, dict):
                condition = value.get("condition", value.get("value", ""))
            else:
                condition = value
            if condition == "above":
                result = [s for s in result if s.get(position_key) == "above"]
            elif condition == "below":
                result = [s for s in result if s.get(position_key) == "below"]
            elif condition == "near":
                result = [s for s in result if s.get(position_key) == "near"]

    # 이평선 교차 필터 (V2 포맷 지원)
    if filters.get("sma_cross"):
        cross_filter = filters["sma_cross"]
        if isinstance(cross_filter, dict):
            # V2: {"short_type": "SMA", "short_period": 20, "long_type": "SMA", "long_period": 50, "condition": "golden"}
            cross_val = cross_filter.get("condition", "")
        else:
            cross_val = cross_filter
        if cross_val == "golden":
            result = [s for s in result if s.get("sma_cross") == "golden"]
        elif cross_val == "dead":
            result = [s for s in result if s.get("sma_cross") == "dead"]

    # RSI 필터 (V2 포맷 지원)
    if filters.get("rsi"):
        min_val, max_val, params = _parse_filter_v2(filters["rsi"])
        if min_val is not None or max_val is not None:
            # V2: params에 period가 있으면 해당 기간 RSI 값 사용
            # 현재는 기본 RSI(14) 필드만 사용
            result = _filter_by_minmax(result, "rsi", min_val, max_val)
        else:
            result = _filter_by_rsi(result, filters["rsi"])

    # 볼린저밴드 필터 (V2 포맷 지원)
    if filters.get("bollinger"):
        bb_filter = filters["bollinger"]
        if isinstance(bb_filter, dict):
            # V2: {"condition": "upper", "params": {"period": 20, "mult": 2}}
            bb_condition = bb_filter.get("condition", bb_filter.get("value", ""))
        else:
            bb_condition = bb_filter
        if bb_condition == "upper":
            result = [s for s in result if s.get("bb_position") == "upper"]
        elif bb_condition == "lower":
            result = [s for s in result if s.get("bb_position") == "lower"]
        elif bb_condition == "middle":
            result = [s for s in result if s.get("bb_position") == "middle"]

    # MACD 필터 (V2 포맷 지원)
    if filters.get("macd"):
        macd_filter = filters["macd"]
        if isinstance(macd_filter, dict):
            # V2: {"condition": "buy", "params": {"fast": 12, "slow": 26, "signal": 9}}
            macd_condition = macd_filter.get("condition", macd_filter.get("value", ""))
        else:
            macd_condition = macd_filter
        if macd_condition == "buy":
            result = [s for s in result if s.get("macd_cross") == "buy"]
        elif macd_condition == "sell":
            result = [s for s in result if s.get("macd_cross") == "sell"]

    # 스토캐스틱 필터 (V2 포맷 지원)
    if filters.get("stochastic"):
        stoch_filter = filters["stochastic"]
        if isinstance(stoch_filter, dict):
            # V2: {"min": 80, "max": null} 또는 {"condition": "overbought"}
            min_val = stoch_filter.get("min")
            max_val = stoch_filter.get("max")
            if min_val is not None or max_val is not None:
                result = _filter_by_minmax(result, "stoch_k", min_val, max_val)
            else:
                condition = stoch_filter.get("condition", "")
                result = _filter_by_stochastic(result, condition)
        else:
            result = _filter_by_stochastic(result, stoch_filter)

    # ATR 필터 (변동성) (V2 포맷 지원)
    if filters.get("atr"):
        atr_filter = filters["atr"]
        if isinstance(atr_filter, dict):
            # V2: {"condition": "high"} 또는 min/max
            min_val = atr_filter.get("min")
            max_val = atr_filter.get("max")
            if min_val is not None or max_val is not None:
                # ATR % (ATR / price * 100)
                filtered = []
                for s in result:
                    atr = s.get("atr")
                    price = s.get("price")
                    if atr and price:
                        atr_pct = atr / price * 100
                        if min_val is not None and atr_pct < min_val:
                            continue
                        if max_val is not None and atr_pct > max_val:
                            continue
                        filtered.append(s)
                result = filtered
            else:
                condition = atr_filter.get("condition", "")
                result = _filter_by_atr(result, condition)
        else:
            result = _filter_by_atr(result, atr_filter)

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
        "nav": lambda x: x.get("nav") or 0,  # ETF 순자산
        "price": lambda x: x.get("price") or 0,
        "change_pct": lambda x: x.get("change_pct") or 0,
        "volume": lambda x: x.get("volume") or 0,
        "name": lambda x: x.get("name") or "",
        "code": lambda x: x.get("code") or "",
        "sector": lambda x: x.get("sector") or "",  # US 섹터
        "issuer": lambda x: x.get("issuer") or "",  # ETF 운용사
        "category": lambda x: x.get("category") or "",  # ETF 카테고리
        # 재무 (기본)
        "per": lambda x: x.get("per") or 9999,
        "pbr": lambda x: x.get("pbr") or 9999,
        "roe": lambda x: x.get("roe") or -9999,
        "roa": lambda x: x.get("roa") or -9999,
        "dividend_yield": lambda x: x.get("dividend_yield") or 0,
        # 재무 (추가)
        "eps_growth": lambda x: x.get("eps_growth") or 0,
        "bps": lambda x: x.get("bps") or 0,
        "debt_ratio": lambda x: x.get("debt_ratio") or 9999,
        "current_ratio": lambda x: x.get("current_ratio") or 0,
        "operating_margin": lambda x: x.get("operating_margin") or -9999,
        "net_margin": lambda x: x.get("net_margin") or -9999,
        "sales_growth": lambda x: x.get("sales_growth") or -9999,
        "op_growth": lambda x: x.get("op_growth") or -9999,
        "foreign_ratio": lambda x: x.get("foreign_ratio") or 0,
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

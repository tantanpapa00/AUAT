# app/strategy_engine/indicator_registry.py
"""
Indicator Registry for Custom Strategy Builder.

Defines available indicators, their parameters, and outputs.
Frontend uses this to dynamically render the condition builder UI.
"""

INDICATOR_REGISTRY = {
    # === 이동평균 (Moving Averages) ===
    "SMA": {
        "name": "단순이동평균 (SMA)",
        "category": "이동평균",
        "params": [
            {"key": "period", "label": "기간", "default": 20, "min": 2, "max": 500, "type": "int"}
        ],
        "outputs": ["value"],
        "func": "calc_sma",
    },
    "EMA": {
        "name": "지수이동평균 (EMA)",
        "category": "이동평균",
        "params": [
            {"key": "period", "label": "기간", "default": 20, "min": 2, "max": 500, "type": "int"}
        ],
        "outputs": ["value"],
        "func": "calc_ema",
    },
    "WMA": {
        "name": "가중이동평균 (WMA)",
        "category": "이동평균",
        "params": [
            {"key": "period", "label": "기간", "default": 20, "min": 2, "max": 500, "type": "int"}
        ],
        "outputs": ["value"],
        "func": "calc_wma",
    },
    "HMA": {
        "name": "헐이동평균 (HMA)",
        "category": "이동평균",
        "params": [
            {"key": "period", "label": "기간", "default": 20, "min": 2, "max": 500, "type": "int"}
        ],
        "outputs": ["value"],
        "func": "calc_hma",
    },
    "VWMA": {
        "name": "거래량가중이동평균 (VWMA)",
        "category": "이동평균",
        "params": [
            {"key": "period", "label": "기간", "default": 20, "min": 2, "max": 500, "type": "int"}
        ],
        "outputs": ["value"],
        "func": "calc_vwma",
    },
    "BB": {
        "name": "볼린저 밴드",
        "category": "이동평균",
        "params": [
            {"key": "period", "label": "기간", "default": 20, "min": 2, "max": 500, "type": "int"},
            {"key": "std_mult", "label": "표준편차 배수", "default": 2.0, "min": 0.1, "max": 5.0, "type": "float"},
        ],
        "outputs": ["upper", "middle", "lower"],
        "func": "calc_bollinger_bands",
    },

    # === 모멘텀/오실레이터 (Momentum/Oscillators) ===
    "RSI": {
        "name": "RSI (상대강도지수)",
        "category": "오실레이터",
        "params": [
            {"key": "period", "label": "기간", "default": 14, "min": 2, "max": 100, "type": "int"}
        ],
        "outputs": ["value"],
        "func": "calc_rsi",
    },
    "MACD": {
        "name": "MACD",
        "category": "오실레이터",
        "params": [
            {"key": "fast_length", "label": "단기", "default": 12, "min": 2, "max": 100, "type": "int"},
            {"key": "slow_length", "label": "장기", "default": 26, "min": 2, "max": 200, "type": "int"},
            {"key": "signal_length", "label": "시그널", "default": 9, "min": 2, "max": 50, "type": "int"},
        ],
        "outputs": ["macd", "signal", "histogram"],
        "func": "calc_macd",
    },
    "STOCH": {
        "name": "스토캐스틱",
        "category": "오실레이터",
        "params": [
            {"key": "k_period", "label": "K 기간", "default": 14, "min": 2, "max": 100, "type": "int"},
            {"key": "d_period", "label": "D 기간", "default": 3, "min": 2, "max": 50, "type": "int"},
            {"key": "slowing", "label": "슬로잉", "default": 3, "min": 1, "max": 10, "type": "int"},
        ],
        "outputs": ["k", "d"],
        "func": "calc_stochastic",
    },
    "CCI": {
        "name": "CCI (상품채널지수)",
        "category": "오실레이터",
        "params": [
            {"key": "period", "label": "기간", "default": 20, "min": 2, "max": 100, "type": "int"}
        ],
        "outputs": ["value"],
        "func": "calc_cci",
    },

    # === 추세 (Trend) ===
    "ADX": {
        "name": "ADX (평균방향지수)",
        "category": "추세",
        "params": [
            {"key": "period", "label": "기간", "default": 14, "min": 2, "max": 100, "type": "int"}
        ],
        "outputs": ["adx", "plus_di", "minus_di"],
        "func": "calc_adx",
    },
    "SUPERTREND": {
        "name": "슈퍼트렌드",
        "category": "추세",
        "params": [
            {"key": "atr_len", "label": "ATR 길이", "default": 20, "min": 2, "max": 100, "type": "int"},
            {"key": "factor", "label": "팩터", "default": 5.0, "min": 0.1, "max": 10.0, "type": "float"},
        ],
        "outputs": ["direction", "value"],
        "func": "calc_supertrend",
    },

    # === 변동성 (Volatility) ===
    "ATR": {
        "name": "ATR (평균진폭)",
        "category": "변동성",
        "params": [
            {"key": "period", "label": "기간", "default": 14, "min": 2, "max": 100, "type": "int"}
        ],
        "outputs": ["value"],
        "func": "calc_atr",
    },

    # === 가격 (Price) ===
    "PRICE": {
        "name": "가격",
        "category": "가격",
        "params": [],
        "outputs": ["open", "high", "low", "close", "volume"],
        "func": None,
    },
}

# 카테고리별 지표 그룹화
INDICATOR_CATEGORIES = {
    "이동평균": ["SMA", "EMA", "WMA", "HMA", "VWMA", "BB"],
    "오실레이터": ["RSI", "MACD", "STOCH", "CCI"],
    "추세": ["ADX", "SUPERTREND"],
    "변동성": ["ATR"],
    "가격": ["PRICE"],
}

# 연산자 목록
OPERATORS = [
    {"value": ">", "label": ">"},
    {"value": "<", "label": "<"},
    {"value": ">=", "label": ">="},
    {"value": "<=", "label": "<="},
    {"value": "==", "label": "=="},
    {"value": "cross_above", "label": "상향돌파 (골든크로스)"},
    {"value": "cross_below", "label": "하향돌파 (데드크로스)"},
]

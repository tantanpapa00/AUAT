"""
기술적 지표 계산 모듈
네이버 일봉 데이터 기반
"""
import numpy as np
from typing import List, Optional, Dict, Any


def compute_all_technicals(candles: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    일봉 데이터로 전체 기술적 지표 계산

    candles: [{"localDate": "20260218", "closePrice": 181200, "highPrice": 182000,
               "lowPrice": 180000, "accumulatedTradingVolume": 3345000}, ...]

    반환:
    {
        "rsi": 55.3,
        "sma20": 178500, "sma50": 175000, "sma200": 170000,
        "bb_upper": 185000, "bb_middle": 178500, "bb_lower": 172000,
        "bb_position": "middle",
        "macd": 1200, "macd_signal": 800, "macd_histogram": 400,
        "macd_cross": "buy",
        "stoch_k": 65.0, "stoch_d": 60.0,
        "atr": 3500,
        "volume_surge": 1.5,
        "sma20_position": "above",
        "sma50_position": "below",
        "sma200_position": "above",
        "sma_cross": "golden",
        "w52_high_pct": -5.5,
        "w52_low_pct": 25.3,
        "period_return_1w": 2.5,
        "period_return_1m": -3.2,
        "period_return_3m": 15.0,
    }
    """
    if not candles or len(candles) < 20:
        return {}

    # 네이버 API 필드명 매핑
    closes = [c.get('closePrice') or c.get('close') for c in candles if c.get('closePrice') or c.get('close')]
    highs = [c.get('highPrice') or c.get('high') for c in candles if c.get('highPrice') or c.get('high')]
    lows = [c.get('lowPrice') or c.get('low') for c in candles if c.get('lowPrice') or c.get('low')]
    volumes = [c.get('accumulatedTradingVolume') or c.get('volume') for c in candles
               if c.get('accumulatedTradingVolume') or c.get('volume')]

    if len(closes) < 20:
        return {}

    result = {}
    current_price = closes[-1]

    # RSI(14)
    result['rsi'] = _calc_rsi(closes, 14)

    # SMA (20, 50, 200)
    result['sma20'] = _calc_sma(closes, 20)
    result['sma50'] = _calc_sma(closes, 50)
    result['sma200'] = _calc_sma(closes, 200)

    # SMA 포지션 (현재가 대비)
    for period, key in [(20, 'sma20'), (50, 'sma50'), (200, 'sma200')]:
        sma_val = result.get(key)
        if sma_val and current_price:
            pct = (current_price - sma_val) / sma_val
            if pct > 0.02:
                result[f'{key}_position'] = 'above'
            elif pct < -0.02:
                result[f'{key}_position'] = 'below'
            else:
                result[f'{key}_position'] = 'near'

    # 이평선 교차 (20일 vs 50일)
    if result.get('sma20') and result.get('sma50') and len(closes) > 51:
        prev_sma20 = _calc_sma(closes[:-1], 20)
        prev_sma50 = _calc_sma(closes[:-1], 50)
        if prev_sma20 and prev_sma50:
            if result['sma20'] > result['sma50'] and prev_sma20 <= prev_sma50:
                result['sma_cross'] = 'golden'
            elif result['sma20'] < result['sma50'] and prev_sma20 >= prev_sma50:
                result['sma_cross'] = 'dead'
            else:
                result['sma_cross'] = 'none'

    # 볼린저밴드 (20일, 2σ)
    bb = _calc_bollinger(closes, 20, 2.0)
    if bb:
        result['bb_upper'] = bb[0]
        result['bb_middle'] = bb[1]
        result['bb_lower'] = bb[2]
        if current_price >= bb[0]:
            result['bb_position'] = 'upper'
        elif current_price <= bb[2]:
            result['bb_position'] = 'lower'
        else:
            result['bb_position'] = 'middle'

    # MACD (12, 26, 9)
    macd = _calc_macd(closes, 12, 26, 9)
    if macd:
        result['macd'] = macd[0]
        result['macd_signal'] = macd[1]
        result['macd_histogram'] = macd[2]
        if macd[0] is not None and macd[1] is not None:
            result['macd_cross'] = 'buy' if macd[0] > macd[1] else 'sell'

    # 스토캐스틱 (14, 3, 3)
    if len(highs) >= 14 and len(lows) >= 14:
        stoch = _calc_stochastic(highs, lows, closes, 14, 3)
        if stoch:
            result['stoch_k'] = stoch[0]
            result['stoch_d'] = stoch[1]

    # ATR (14)
    if len(highs) >= 15:
        result['atr'] = _calc_atr(highs, lows, closes, 14)

    # 거래량 급증 (당일 / 20일 평균)
    if len(volumes) >= 21:
        avg_vol = np.mean(volumes[-21:-1])
        if avg_vol > 0:
            result['volume_surge'] = round(volumes[-1] / avg_vol, 2)

    # 52주 고가/저가 대비
    period_252 = min(len(highs), 252)
    if period_252 >= 20:
        w52_high = max(highs[-period_252:])
        w52_low = min(lows[-period_252:])
        if w52_high > 0:
            result['w52_high_pct'] = round((current_price - w52_high) / w52_high * 100, 2)
        if w52_low > 0:
            result['w52_low_pct'] = round((current_price - w52_low) / w52_low * 100, 2)
        result['w52_high'] = w52_high
        result['w52_low'] = w52_low

    # 기간 수익률
    if len(closes) >= 6:
        result['period_return_1w'] = round((closes[-1] - closes[-6]) / closes[-6] * 100, 2)
    if len(closes) >= 23:
        result['period_return_1m'] = round((closes[-1] - closes[-23]) / closes[-23] * 100, 2)
    if len(closes) >= 66:
        result['period_return_3m'] = round((closes[-1] - closes[-66]) / closes[-66] * 100, 2)

    return result


def _calc_rsi(closes: list, period: int = 14) -> Optional[float]:
    """RSI 계산"""
    if len(closes) < period + 1:
        return None
    deltas = np.diff(closes[-period-1:])
    gains = np.where(deltas > 0, deltas, 0)
    losses = np.where(deltas < 0, -deltas, 0)
    avg_gain = np.mean(gains)
    avg_loss = np.mean(losses)
    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return round(100 - (100 / (1 + rs)), 2)


def _calc_sma(closes: list, period: int) -> Optional[float]:
    """단순이동평균"""
    if len(closes) < period:
        return None
    return round(np.mean(closes[-period:]), 2)


def _calc_bollinger(closes: list, period: int = 20, mult: float = 2.0):
    """볼린저밴드 (upper, middle, lower)"""
    if len(closes) < period:
        return None
    data = closes[-period:]
    sma = np.mean(data)
    std = np.std(data)
    return (round(sma + mult * std, 2), round(sma, 2), round(sma - mult * std, 2))


def _calc_macd(closes: list, fast=12, slow=26, signal=9):
    """MACD (macd_line, signal_line, histogram)"""
    if len(closes) < slow + signal:
        return None
    arr = np.array(closes, dtype=float)
    ema_fast = _ema(arr, fast)
    ema_slow = _ema(arr, slow)
    macd_line = ema_fast[-len(ema_slow):] - ema_slow
    if len(macd_line) < signal:
        return None
    signal_line = _ema(macd_line, signal)
    return (
        round(float(macd_line[-1]), 2),
        round(float(signal_line[-1]), 2),
        round(float(macd_line[-1] - signal_line[-1]), 2)
    )


def _ema(data, period):
    """지수이동평균"""
    arr = np.array(data, dtype=float)
    alpha = 2 / (period + 1)
    result = np.zeros_like(arr)
    result[0] = arr[0]
    for i in range(1, len(arr)):
        result[i] = alpha * arr[i] + (1 - alpha) * result[i - 1]
    return result


def _calc_stochastic(highs, lows, closes, k_period=14, d_period=3):
    """스토캐스틱 %K, %D"""
    if len(closes) < k_period:
        return None

    # %K 계산
    k_values = []
    for i in range(k_period - 1, len(closes)):
        h = max(highs[i - k_period + 1:i + 1])
        l = min(lows[i - k_period + 1:i + 1])
        if h == l:
            k_values.append(50.0)
        else:
            k_values.append(((closes[i] - l) / (h - l)) * 100)

    if len(k_values) < d_period:
        return None

    # %D (K의 단순이동평균)
    d_value = np.mean(k_values[-d_period:])

    return (round(k_values[-1], 2), round(d_value, 2))


def _calc_atr(highs, lows, closes, period=14) -> Optional[float]:
    """ATR (Average True Range)"""
    if len(highs) < period + 1:
        return None
    trs = []
    for i in range(-period, 0):
        tr = max(
            highs[i] - lows[i],
            abs(highs[i] - closes[i - 1]),
            abs(lows[i] - closes[i - 1])
        )
        trs.append(tr)
    return round(np.mean(trs), 2)

"""
기술적 지표 계산 모듈
네이버 일봉 데이터 기반
"""
import numpy as np
from typing import List, Optional, Dict, Any


def compute_all_technicals(candles: List[Dict[str, Any]], params: Dict[str, Any] = None) -> Dict[str, Any]:
    """
    일봉 데이터로 전체 기술적 지표 계산 (동적 파라미터 지원)

    candles: [{"localDate": "20260218", "closePrice": 181200, "highPrice": 182000,
               "lowPrice": 180000, "accumulatedTradingVolume": 3345000}, ...]

    params: 동적 파라미터 (프론트엔드에서 전달)
    {
        "rsi": {"period": 14},
        "macd": {"fast": 12, "slow": 26, "signal": 9},
        "bollinger": {"period": 20, "mult": 2.0},
        "stochastic": {"k_period": 14, "d_period": 3},
        "atr": {"period": 14},
        "sma": [{"type": "SMA", "period": 20}, {"type": "EMA", "period": 50}]
    }

    반환:
    {
        "rsi": 55.3, "rsi_period": 14,
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
        # 동적 이평선 (프론트엔드 요청시)
        "sma_SMA_20": 178500, "sma_SMA_20_position": "above",
        "sma_EMA_50": 175000, "sma_EMA_50_position": "below",
    }
    """
    params = params or {}
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

    # RSI (동적 기간 지원)
    rsi_period = params.get('rsi', {}).get('period', 14)
    result['rsi'] = _calc_rsi(closes, rsi_period)
    result['rsi_period'] = rsi_period

    # SMA (20, 50, 200) - 기본 이평선
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

    # 동적 이평선 계산 (프론트엔드 요청시)
    # params['sma'] = [{"type": "SMA", "period": 20}, {"type": "EMA", "period": 7}]
    dynamic_sma_list = params.get('sma', [])
    for sma_config in dynamic_sma_list:
        ma_type = sma_config.get('type', 'SMA').upper()
        period = int(sma_config.get('period', 20))
        if period > len(closes):
            continue

        key = f"sma_{ma_type}_{period}"
        if ma_type == 'SMA':
            ma_value = _calc_sma(closes, period)
        elif ma_type == 'EMA':
            ema_arr = _ema(closes, period)
            ma_value = round(float(ema_arr[-1]), 2) if len(ema_arr) > 0 else None
        elif ma_type == 'WMA':
            ma_value = _calc_wma(closes, period)
        else:
            ma_value = _calc_sma(closes, period)

        result[key] = ma_value

        # 동적 이평선 포지션
        if ma_value and current_price:
            pct = (current_price - ma_value) / ma_value
            if pct > 0.02:
                result[f'{key}_position'] = 'above'
            elif pct < -0.02:
                result[f'{key}_position'] = 'below'
            else:
                result[f'{key}_position'] = 'near'

    # 이평선 교차 (20일 vs 50일) - lookback 5일 내 교차 감지
    if result.get('sma20') and result.get('sma50') and len(closes) > 55:
        lookback = 5  # 최근 5일 내 교차 감지
        result['sma_cross'] = 'none'

        for offset in range(lookback):
            if offset >= len(closes) - 51:
                break

            # 현재 위치에서 SMA 계산
            idx = len(closes) - offset
            sma20_now = _calc_sma(closes[:idx], 20)
            sma50_now = _calc_sma(closes[:idx], 50)
            sma20_prev = _calc_sma(closes[:idx-1], 20) if idx > 21 else None
            sma50_prev = _calc_sma(closes[:idx-1], 50) if idx > 51 else None

            if sma20_now and sma50_now and sma20_prev and sma50_prev:
                if sma20_now > sma50_now and sma20_prev <= sma50_prev:
                    result['sma_cross'] = 'golden'
                    result['sma_cross_days_ago'] = offset
                    break
                elif sma20_now < sma50_now and sma20_prev >= sma50_prev:
                    result['sma_cross'] = 'dead'
                    result['sma_cross_days_ago'] = offset
                    break

    # 볼린저밴드 (동적 파라미터 지원)
    bb_params = params.get('bollinger', {})
    bb_period = bb_params.get('period', 20)
    bb_mult = bb_params.get('mult', 2.0)
    bb = _calc_bollinger(closes, bb_period, bb_mult)
    if bb:
        result['bb_upper'] = bb[0]
        result['bb_middle'] = bb[1]
        result['bb_lower'] = bb[2]
        result['bb_period'] = bb_period
        result['bb_mult'] = bb_mult
        if current_price >= bb[0]:
            result['bb_position'] = 'upper'
        elif current_price <= bb[2]:
            result['bb_position'] = 'lower'
        else:
            result['bb_position'] = 'middle'

    # MACD (동적 파라미터 지원)
    macd_params = params.get('macd', {})
    macd_fast = macd_params.get('fast', 12)
    macd_slow = macd_params.get('slow', 26)
    macd_signal_period = macd_params.get('signal', 9)
    macd = _calc_macd(closes, macd_fast, macd_slow, macd_signal_period)
    if macd:
        result['macd'] = macd[0]
        result['macd_signal'] = macd[1]
        result['macd_histogram'] = macd[2]
        result['macd_params'] = {'fast': macd_fast, 'slow': macd_slow, 'signal': macd_signal_period}
        if macd[0] is not None and macd[1] is not None:
            result['macd_cross'] = 'buy' if macd[0] > macd[1] else 'sell'

    # 스토캐스틱 (동적 파라미터 지원)
    stoch_params = params.get('stochastic', {})
    stoch_k_period = stoch_params.get('k_period', 14)
    stoch_d_period = stoch_params.get('d_period', 3)
    if len(highs) >= stoch_k_period and len(lows) >= stoch_k_period:
        stoch = _calc_stochastic(highs, lows, closes, stoch_k_period, stoch_d_period)
        if stoch:
            result['stoch_k'] = stoch[0]
            result['stoch_d'] = stoch[1]
            result['stoch_params'] = {'k_period': stoch_k_period, 'd_period': stoch_d_period}

    # ATR (동적 파라미터 지원)
    atr_params = params.get('atr', {})
    atr_period = atr_params.get('period', 14)
    if len(highs) >= atr_period + 1:
        result['atr'] = _calc_atr(highs, lows, closes, atr_period)
        result['atr_period'] = atr_period

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

    # 일목균형표 (동적 파라미터 지원)
    ichimoku_params = params.get('ichimoku', {})
    tenkan = ichimoku_params.get('tenkan', 9)
    kijun = ichimoku_params.get('kijun', 26)
    senkou_b_period = ichimoku_params.get('senkou_b', 52)
    ichimoku_result = calc_ichimoku(highs, lows, closes, tenkan, kijun, senkou_b_period)
    result.update(ichimoku_result)

    # Stochastic RSI (동적 파라미터 지원)
    stoch_rsi_params = params.get('stoch_rsi', {})
    stoch_rsi_result = calc_stoch_rsi(
        closes,
        rsi_period=stoch_rsi_params.get('rsi_period', 14),
        stoch_period=stoch_rsi_params.get('stoch_period', 14),
        k_period=stoch_rsi_params.get('k_period', 3),
        d_period=stoch_rsi_params.get('d_period', 3)
    )
    result.update(stoch_rsi_result)

    # ADX (동적 파라미터 지원)
    adx_params = params.get('adx', {})
    adx_result = calc_adx(highs, lows, closes, period=adx_params.get('period', 14))
    result.update(adx_result)

    # CCI (동적 파라미터 지원)
    cci_params = params.get('cci', {})
    cci_result = calc_cci(highs, lows, closes, period=cci_params.get('period', 20))
    result.update(cci_result)

    # Williams %R (동적 파라미터 지원)
    wr_params = params.get('williams_r', {})
    wr_result = calc_williams_r(highs, lows, closes, period=wr_params.get('period', 14))
    result.update(wr_result)

    return result


def _calc_rsi(closes: list, period: int = 14) -> Optional[float]:
    """
    RSI 계산 - TradingView 동일 방식 (Wilder's Smoothing/RMA)

    Wilder's smoothing: alpha = 1/period (일반 EMA는 2/(period+1))
    첫 번째 평균은 SMA, 이후 RMA로 스무딩
    """
    if len(closes) < period + 1:
        return None

    # 전체 변화량 계산 (충분한 데이터 사용)
    data_len = min(len(closes), period * 3)  # 최소 period*3 봉 사용
    deltas = np.diff(closes[-data_len:])
    gains = np.where(deltas > 0, deltas, 0)
    losses = np.where(deltas < 0, -deltas, 0)

    # 첫 번째 평균 (SMA)
    avg_gain = np.mean(gains[:period])
    avg_loss = np.mean(losses[:period])

    # Wilder's smoothing (RMA) 적용
    alpha = 1.0 / period
    for i in range(period, len(gains)):
        avg_gain = alpha * gains[i] + (1 - alpha) * avg_gain
        avg_loss = alpha * losses[i] + (1 - alpha) * avg_loss

    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return round(100 - (100 / (1 + rs)), 2)


def _calc_sma(closes: list, period: int) -> Optional[float]:
    """단순이동평균"""
    if len(closes) < period:
        return None
    return round(np.mean(closes[-period:]), 2)


def _calc_wma(closes: list, period: int) -> Optional[float]:
    """가중이동평균 (Weighted Moving Average)"""
    if len(closes) < period:
        return None
    data = closes[-period:]
    weights = np.arange(1, period + 1)
    return round(np.sum(data * weights) / np.sum(weights), 2)


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


def calc_ichimoku(highs, lows, closes, tenkan=9, kijun=26, senkou_b=52) -> Dict[str, Any]:
    """
    일목균형표 계산
    - 전환선(Tenkan): (9일 최고 + 9일 최저) / 2
    - 기준선(Kijun): (26일 최고 + 26일 최저) / 2
    - 선행스팬A: (전환선 + 기준선) / 2, 26일 앞으로 표시
    - 선행스팬B: (52일 최고 + 52일 최저) / 2, 26일 앞으로 표시
    """
    n = len(closes)
    if n < senkou_b + kijun:
        return {}

    i = n - 1  # 현재 봉

    # 전환선 (tenkan-sen)
    tenkan_val = (max(highs[max(0, i-tenkan+1):i+1]) + min(lows[max(0, i-tenkan+1):i+1])) / 2

    # 기준선 (kijun-sen)
    kijun_val = (max(highs[max(0, i-kijun+1):i+1]) + min(lows[max(0, i-kijun+1):i+1])) / 2

    # 선행스팬 A, B (26봉 전 기준)
    j = i - kijun
    if j >= max(tenkan, kijun):
        t_prev = (max(highs[max(0, j-tenkan+1):j+1]) + min(lows[max(0, j-tenkan+1):j+1])) / 2
        k_prev = (max(highs[max(0, j-kijun+1):j+1]) + min(lows[max(0, j-kijun+1):j+1])) / 2
        senkou_a = (t_prev + k_prev) / 2
    else:
        senkou_a = (tenkan_val + kijun_val) / 2

    if j >= senkou_b:
        senkou_b_val = (max(highs[max(0, j-senkou_b+1):j+1]) + min(lows[max(0, j-senkou_b+1):j+1])) / 2
    else:
        senkou_b_val = (max(highs[max(0, i-senkou_b+1):i+1]) + min(lows[max(0, i-senkou_b+1):i+1])) / 2

    # 구름 위치 판단
    cloud_top = max(senkou_a, senkou_b_val)
    cloud_bottom = min(senkou_a, senkou_b_val)
    current_price = closes[-1]

    if current_price > cloud_top:
        cloud_pos = 'above_cloud'
    elif current_price < cloud_bottom:
        cloud_pos = 'below_cloud'
    else:
        cloud_pos = 'in_cloud'

    # 전환선/기준선 관계
    if tenkan_val > kijun_val:
        tk_cross = 'tenkan_above_kijun'
    elif tenkan_val < kijun_val:
        tk_cross = 'tenkan_below_kijun'
    else:
        tk_cross = 'equal'

    return {
        'ichimoku_tenkan': round(tenkan_val, 2),
        'ichimoku_kijun': round(kijun_val, 2),
        'ichimoku_senkou_a': round(senkou_a, 2),
        'ichimoku_senkou_b': round(senkou_b_val, 2),
        'ichimoku_cloud': cloud_pos,
        'ichimoku_tk_cross': tk_cross,
    }


def calc_stoch_rsi(closes, rsi_period=14, stoch_period=14, k_period=3, d_period=3) -> Dict[str, Any]:
    """
    Stochastic RSI 계산 - TradingView 동일 방식

    내부 RSI도 Wilder's smoothing 사용
    """
    if len(closes) < rsi_period + stoch_period + 10:
        return {'stoch_rsi': None}

    # RSI 시계열 계산 (Wilder's smoothing)
    deltas = np.diff(closes)
    gains = np.where(deltas > 0, deltas, 0)
    losses = np.where(deltas < 0, -deltas, 0)

    # 첫 번째 평균 (SMA)
    avg_gain = np.mean(gains[:rsi_period])
    avg_loss = np.mean(losses[:rsi_period])

    rsi_values = []
    alpha = 1.0 / rsi_period

    for i in range(rsi_period, len(gains)):
        avg_gain = alpha * gains[i] + (1 - alpha) * avg_gain
        avg_loss = alpha * losses[i] + (1 - alpha) * avg_loss

        if avg_loss == 0:
            rsi_values.append(100.0)
        else:
            rs = avg_gain / avg_loss
            rsi_values.append(100 - (100 / (1 + rs)))

    if len(rsi_values) < stoch_period:
        return {'stoch_rsi': None}

    # Stochastic 적용 (최근 stoch_period 구간의 RSI 기준)
    recent_rsi = rsi_values[-stoch_period:]
    rsi_high = max(recent_rsi)
    rsi_low = min(recent_rsi)

    if rsi_high == rsi_low:
        stoch_rsi = 50
    else:
        stoch_rsi = ((rsi_values[-1] - rsi_low) / (rsi_high - rsi_low)) * 100

    return {'stoch_rsi': round(stoch_rsi, 2)}


def calc_adx(highs, lows, closes, period=14) -> Dict[str, Any]:
    """ADX (Average Directional Index) 계산"""
    n = len(closes)
    if n < period * 2:
        return {'adx': None}

    plus_dm = []
    minus_dm = []
    tr_list = []

    for i in range(1, n):
        h_diff = highs[i] - highs[i-1]
        l_diff = lows[i-1] - lows[i]

        plus_dm.append(h_diff if h_diff > l_diff and h_diff > 0 else 0)
        minus_dm.append(l_diff if l_diff > h_diff and l_diff > 0 else 0)
        tr_list.append(max(highs[i]-lows[i], abs(highs[i]-closes[i-1]), abs(lows[i]-closes[i-1])))

    if len(tr_list) < period:
        return {'adx': None}

    # Smoothed averages
    atr = sum(tr_list[:period]) / period
    plus_di_sum = sum(plus_dm[:period]) / period
    minus_di_sum = sum(minus_dm[:period]) / period

    dx_list = []
    for i in range(period, len(tr_list)):
        atr = (atr * (period-1) + tr_list[i]) / period
        plus_di_sum = (plus_di_sum * (period-1) + plus_dm[i]) / period
        minus_di_sum = (minus_di_sum * (period-1) + minus_dm[i]) / period

        if atr == 0:
            continue
        pdi = (plus_di_sum / atr) * 100
        mdi = (minus_di_sum / atr) * 100

        if pdi + mdi == 0:
            dx_list.append(0)
        else:
            dx_list.append(abs(pdi - mdi) / (pdi + mdi) * 100)

    if len(dx_list) < period:
        return {'adx': None}

    adx = sum(dx_list[-period:]) / period
    return {'adx': round(adx, 2)}


def calc_cci(highs, lows, closes, period=20) -> Dict[str, Any]:
    """CCI (Commodity Channel Index) 계산"""
    n = len(closes)
    if n < period:
        return {'cci': None}

    tp_list = [(highs[i]+lows[i]+closes[i])/3 for i in range(n)]
    tp_recent = tp_list[-period:]
    tp_sma = sum(tp_recent) / period
    mean_dev = sum(abs(tp - tp_sma) for tp in tp_recent) / period

    if mean_dev == 0:
        return {'cci': 0}

    cci = (tp_list[-1] - tp_sma) / (0.015 * mean_dev)
    return {'cci': round(cci, 2)}


def calc_williams_r(highs, lows, closes, period=14) -> Dict[str, Any]:
    """Williams %R 계산"""
    n = len(closes)
    if n < period:
        return {'williams_r': None}

    highest = max(highs[-period:])
    lowest = min(lows[-period:])

    if highest == lowest:
        return {'williams_r': -50}

    wr = ((highest - closes[-1]) / (highest - lowest)) * -100
    return {'williams_r': round(wr, 2)}

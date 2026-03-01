# app/routers/ai_report_charts.py
# AI 분석용 차트 생성 모듈

import os
import io
import base64
from datetime import datetime, timedelta
from typing import Dict, Any

import httpx
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from matplotlib.patches import Rectangle

# Static directory
STATIC_DIR = "/app/static"
CHARTS_DIR = os.path.join(STATIC_DIR, "charts")


async def generate_ai_charts(code: str, name: str, market: str = "kr") -> dict:
    """AI 분석용 차트 3종 생성 - base64로 반환 (Mixed Content 방지)"""
    chart_data = {"price_chart": None, "trend_chart": None, "momentum_chart": None}

    try:
        candles = []
        is_us_market = market == "us"

        if market == "kr":
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.get(
                    f"https://api.stock.naver.com/chart/domestic/item/{code}/day?startDateTime=20240101&endDateTime=20261231",
                    headers={"User-Agent": "Mozilla/5.0"}
                )
                if resp.status_code == 200:
                    candles = resp.json() if isinstance(resp.json(), list) else []

        elif market == "us":
            try:
                import yfinance as yf
                ticker = yf.Ticker(code)
                hist = ticker.history(period="2y")
                if not hist.empty:
                    for idx, row in hist.iterrows():
                        candles.append({
                            "localDate": idx.strftime("%Y%m%d"),
                            "openPrice": row["Open"],
                            "highPrice": row["High"],
                            "lowPrice": row["Low"],
                            "closePrice": row["Close"],
                            "accumulatedTradingVolume": int(row["Volume"])
                        })
                    print(f"[Chart] yfinance fetched {len(candles)} candles for {code}")
            except Exception as e:
                print(f"[Chart] yfinance error for {code}: {e}")

        if len(candles) < 20:
            print(f"[Chart] Not enough data for {code}: {len(candles)} candles")
            return chart_data

        # 데이터 추출
        dates_str = [c.get("localDate", "")[:10] for c in candles]
        dates = [datetime.strptime(d, "%Y%m%d") if len(d) == 8 else datetime.strptime(d, "%Y-%m-%d") for d in dates_str]
        opens = [float(c.get("openPrice", 0)) for c in candles]
        closes = [float(c.get("closePrice", 0)) for c in candles]
        highs = [float(c.get("highPrice", 0)) for c in candles]
        lows = [float(c.get("lowPrice", 0)) for c in candles]
        volumes = [int(c.get("accumulatedTradingVolume", 0)) for c in candles]

        # 이동평균 계산
        def _sma(data, period):
            if len(data) < period:
                return [None] * len(data)
            result = [None] * (period - 1)
            for i in range(period - 1, len(data)):
                result.append(sum(data[i-period+1:i+1]) / period)
            return result

        sma20 = _sma(closes, 20)
        sma60 = _sma(closes, 60)
        sma200 = _sma(closes, 200)

        # 지지/저항 계산
        support_levels, resistance_levels = _calculate_support_resistance(
            highs, lows, closes, volumes, closes[-1], num_levels=2
        )

        support1 = support_levels[0] if support_levels else closes[-1] * 0.95
        support2 = support_levels[1] if len(support_levels) > 1 else support1 * 0.9
        resistance1 = resistance_levels[0] if resistance_levels else closes[-1] * 1.05
        resistance2 = resistance_levels[1] if len(resistance_levels) > 1 else resistance1 * 1.1

        chart_data["support_levels"] = [support1, support2]
        chart_data["resistance_levels"] = [resistance1, resistance2]
        chart_data["current_price"] = closes[-1]

        display_len = min(500, len(closes))

        if is_us_market:
            UP_COLOR = '#34C759'
            DOWN_COLOR = '#FF3B30'
        else:
            UP_COLOR = '#FF3B30'
            DOWN_COLOR = '#007AFF'

        # ===== 차트 1: 캔들스틱 + 지지/저항선 + 거래량 =====
        fig1, (ax1, ax2) = plt.subplots(2, 1, figsize=(12, 8), height_ratios=[3, 1],
                                         gridspec_kw={'hspace': 0.05}, sharex=True)
        fig1.patch.set_facecolor('white')

        width = 0.6
        for i in range(display_len):
            idx = len(closes) - display_len + i
            date_num = mdates.date2num(dates[idx])
            o, h, l, c = opens[idx], highs[idx], lows[idx], closes[idx]
            color = UP_COLOR if c >= o else DOWN_COLOR

            body_bottom = min(o, c)
            body_height = abs(c - o) if abs(c - o) > 0 else 1
            rect = Rectangle((date_num - width/2, body_bottom), width, body_height,
                             facecolor=color, edgecolor=color, linewidth=0.5)
            ax1.add_patch(rect)
            ax1.plot([date_num, date_num], [l, body_bottom], color=color, linewidth=0.5)
            ax1.plot([date_num, date_num], [body_bottom + body_height, h], color=color, linewidth=0.5)

        ax1.set_xlim(mdates.date2num(dates[-display_len]) - 2, mdates.date2num(dates[-1]) + 2)
        ax1.set_ylim(min(lows[-display_len:]) * 0.95, max(highs[-display_len:]) * 1.05)

        ax1.axhline(y=resistance1, color='#FF1744', linestyle='--', linewidth=2.5, alpha=0.95,
                    label=f'1차 저항 {int(resistance1):,}')
        ax1.axhline(y=resistance2, color='#FF5252', linestyle='--', linewidth=2.0, alpha=0.7,
                    label=f'2차 저항 {int(resistance2):,}')
        ax1.axhline(y=support1, color='#00C853', linestyle='--', linewidth=2.5, alpha=0.95,
                    label=f'1차 지지 {int(support1):,}')
        ax1.axhline(y=support2, color='#69F0AE', linestyle='--', linewidth=2.0, alpha=0.7,
                    label=f'2차 지지 {int(support2):,}')

        ax1.set_title(f'주가, 지지/저항 분석 - {name}({code})', fontsize=14, fontweight='bold')
        ax1.legend(loc='upper left', fontsize=8, ncol=2)
        ax1.grid(True, alpha=0.3)
        price_label = '주가($)' if is_us_market else '주가(원)'
        ax1.set_ylabel(price_label, fontsize=11)
        ax1.yaxis.set_major_formatter(plt.FuncFormatter(lambda x, p: f'{x:,.0f}'))

        for i in range(display_len):
            idx = len(closes) - display_len + i
            date_num = mdates.date2num(dates[idx])
            color = UP_COLOR if closes[idx] >= opens[idx] else DOWN_COLOR
            ax2.bar(date_num, volumes[idx], color=color, width=width, alpha=0.7)

        ax2.set_ylabel('거래량', fontsize=11)
        ax2.yaxis.set_major_formatter(plt.FuncFormatter(lambda x, p: f'{x/1e6:.1f}M' if x >= 1e6 else f'{x/1e3:.0f}K'))
        ax2.grid(True, alpha=0.3)
        ax2.xaxis.set_major_formatter(mdates.DateFormatter('%Y-%b'))
        ax2.xaxis.set_major_locator(mdates.MonthLocator(interval=4))
        plt.xticks(rotation=45, fontsize=8)
        plt.tight_layout()

        buf = io.BytesIO()
        plt.savefig(buf, format='png', dpi=150, bbox_inches='tight')
        buf.seek(0)
        b64 = base64.b64encode(buf.read()).decode('utf-8')
        buf.close()
        plt.close(fig1)
        chart_data["price_chart"] = f"data:image/png;base64,{b64}"

        # ===== 차트 2: 추세추종 =====
        fig2, (ax_price, ax_adx) = plt.subplots(2, 1, figsize=(12, 8),
                                                  height_ratios=[2, 1],
                                                  gridspec_kw={'hspace': 0.15})
        fig2.patch.set_facecolor('white')

        for i in range(display_len):
            idx = len(closes) - display_len + i
            date_num = mdates.date2num(dates[idx])
            o, h, l, c = opens[idx], highs[idx], lows[idx], closes[idx]
            color = UP_COLOR if c >= o else DOWN_COLOR

            body_bottom = min(o, c)
            body_height = abs(c - o) if abs(c - o) > 0 else 1
            rect = Rectangle((date_num - width/2, body_bottom), width, body_height,
                             facecolor=color, edgecolor=color, linewidth=0.5)
            ax_price.add_patch(rect)
            ax_price.plot([date_num, date_num], [l, body_bottom], color=color, linewidth=0.5)
            ax_price.plot([date_num, date_num], [body_bottom + body_height, h], color=color, linewidth=0.5)

        ax_price.set_xlim(mdates.date2num(dates[-display_len]) - 2, mdates.date2num(dates[-1]) + 2)
        ax_price.set_ylim(min(lows[-display_len:]) * 0.95, max(highs[-display_len:]) * 1.05)

        date_nums = [mdates.date2num(dates[len(dates) - display_len + i]) for i in range(display_len)]
        if sma20[-display_len:][0] is not None:
            ax_price.plot(date_nums, sma20[-display_len:], label='SMA20', color='#FF9500', linewidth=1.5)
        if sma60[-display_len:][0] is not None:
            ax_price.plot(date_nums, sma60[-display_len:], label='SMA60', color='#007AFF', linewidth=1.5)
        if sma200 and sma200[-display_len:][0] is not None:
            ax_price.plot(date_nums, sma200[-display_len:], label='SMA200', color='#FF3B30', linewidth=1.5)

        ax_price.set_title(f'추세추종 지표 분석 - {name}({code})', fontsize=14, fontweight='bold')
        ax_price.set_ylabel(price_label, fontsize=11)
        ax_price.legend(loc='upper left', fontsize=9)
        ax_price.grid(True, alpha=0.3)
        ax_price.yaxis.set_major_formatter(plt.FuncFormatter(lambda x, p: f'{x:,.0f}'))
        ax_price.tick_params(axis='x', labelbottom=False)

        # ADX/DI 계산
        adx_series, plus_di_series, minus_di_series = _calculate_adx_series(highs, lows, closes)

        min_adx_len = 30
        if len(adx_series) >= min_adx_len:
            actual_display = min(len(adx_series), display_len)
            adx_display = adx_series[-actual_display:]
            plus_di_display = plus_di_series[-actual_display:]
            minus_di_display = minus_di_series[-actual_display:]
            date_nums_adx = date_nums[-actual_display:] if len(date_nums) >= actual_display else date_nums

            valid_adx = [(d, a) for d, a in zip(date_nums_adx, adx_display) if a is not None]
            if valid_adx:
                current_adx = valid_adx[-1][1] if valid_adx else 0
                ax_adx.plot([x[0] for x in valid_adx], [x[1] for x in valid_adx],
                           color='#000000', linewidth=2, label=f'ADX ({current_adx:.1f})')

            if plus_di_display:
                current_plus = plus_di_display[-1] if plus_di_display else 0
                ax_adx.plot(date_nums_adx, plus_di_display, color='#34C759', linewidth=1.5,
                           label=f'+DI ({current_plus:.1f})')
            if minus_di_display:
                current_minus = minus_di_display[-1] if minus_di_display else 0
                ax_adx.plot(date_nums_adx, minus_di_display, color='#FF3B30', linewidth=1.5,
                           label=f'-DI ({current_minus:.1f})')

            ax_adx.axhline(y=25, color='gray', linestyle='--', linewidth=0.8, alpha=0.6)
            ax_adx.axhline(y=50, color='gray', linestyle='--', linewidth=0.8, alpha=0.6)
            ax_adx.text(date_nums_adx[-1] + 1, 25, '25', fontsize=8, color='gray', va='center')
            ax_adx.text(date_nums_adx[-1] + 1, 50, '50', fontsize=8, color='gray', va='center')

            all_values = [v for v in adx_display + plus_di_display + minus_di_display if v is not None]
            if all_values:
                ax_adx.set_ylim(0, max(60, max(all_values) * 1.1))
            else:
                ax_adx.set_ylim(0, 60)
        else:
            ax_adx.text(0.5, 0.5, f'ADX/DI 데이터 부족 (최소 {min_adx_len}일 필요)',
                       transform=ax_adx.transAxes, ha='center', va='center', fontsize=10, color='gray')
            ax_adx.set_ylim(0, 60)

        ax_adx.set_ylabel('ADX / DI', fontsize=11)
        ax_adx.legend(loc='upper left', fontsize=9)
        ax_adx.grid(True, alpha=0.3)
        ax_adx.xaxis.set_major_formatter(mdates.DateFormatter('%Y-%b'))
        ax_adx.xaxis.set_major_locator(mdates.MonthLocator(interval=4))
        plt.xticks(rotation=45, fontsize=8)
        plt.tight_layout()

        buf = io.BytesIO()
        plt.savefig(buf, format='png', dpi=150, bbox_inches='tight')
        buf.seek(0)
        b64 = base64.b64encode(buf.read()).decode('utf-8')
        buf.close()
        plt.close(fig2)
        chart_data["trend_chart"] = f"data:image/png;base64,{b64}"

        # ===== 차트 3: 모멘텀 (RSI + MACD) =====
        fig3, (ax_rsi, ax_macd) = plt.subplots(2, 1, figsize=(12, 8), sharex=True)
        fig3.patch.set_facecolor('white')

        rsi_values = _calculate_rsi_series(closes, 14)
        macd_line, signal_line, histogram = _calculate_macd_series(closes)

        rsi_start_idx = 14
        rsi_dates = dates[rsi_start_idx:]
        rsi_date_nums = [mdates.date2num(d) for d in rsi_dates[-display_len:]]
        rsi_display = rsi_values[-display_len:] if len(rsi_values) >= display_len else rsi_values

        if len(rsi_date_nums) == len(rsi_display):
            ax_rsi.plot(rsi_date_nums, rsi_display, color='#8B5CF6', linewidth=1.5, label='RSI(14)')
            ax_rsi.axhline(y=70, color='#FF3B30', linestyle='--', linewidth=1, alpha=0.7, label='과매수 (70)')
            ax_rsi.axhline(y=30, color='#34C759', linestyle='--', linewidth=1, alpha=0.7, label='과매도 (30)')
            ax_rsi.axhline(y=50, color='gray', linestyle=':', linewidth=0.5, alpha=0.5)
            ax_rsi.fill_between(rsi_date_nums, 70, 100, alpha=0.1, color='#FF3B30')
            ax_rsi.fill_between(rsi_date_nums, 0, 30, alpha=0.1, color='#34C759')
            ax_rsi.set_ylim(0, 100)
            ax_rsi.set_ylabel('RSI', fontsize=11)
            ax_rsi.set_title(f'모멘텀 지표 분석 - {name}({code})', fontsize=14, fontweight='bold')
            ax_rsi.legend(loc='upper left', fontsize=9)
            ax_rsi.grid(True, alpha=0.3)

            current_rsi = rsi_display[-1]
            rsi_status = "과매수" if current_rsi > 70 else "과매도" if current_rsi < 30 else "중립"
            ax_rsi.annotate(f'{current_rsi:.1f} ({rsi_status})',
                           xy=(rsi_date_nums[-1], current_rsi),
                           fontsize=10, fontweight='bold',
                           color='#FF3B30' if current_rsi > 70 else '#34C759' if current_rsi < 30 else '#8B5CF6',
                           xytext=(5, 0), textcoords='offset points')

        macd_display = macd_line[-display_len:]
        signal_display = signal_line[-display_len:]
        hist_display = histogram[-display_len:]
        macd_date_nums = [mdates.date2num(dates[len(dates) - display_len + i]) for i in range(display_len)]

        valid_macd = [(d, m) for d, m in zip(macd_date_nums, macd_display) if m is not None]
        valid_signal = [(d, s) for d, s in zip(macd_date_nums, signal_display) if s is not None]

        if valid_macd:
            ax_macd.plot([x[0] for x in valid_macd], [x[1] for x in valid_macd],
                        color='#007AFF', linewidth=1.5, label='MACD')
        if valid_signal:
            ax_macd.plot([x[0] for x in valid_signal], [x[1] for x in valid_signal],
                        color='#FF9500', linewidth=1.5, label='Signal')

        ax_macd.axhline(y=0, color='gray', linewidth=0.5)

        for i, (d, h) in enumerate(zip(macd_date_nums, hist_display)):
            if h is not None:
                color = '#34C759' if h >= 0 else '#FF3B30'
                ax_macd.bar(d, h, color=color, width=0.6, alpha=0.6)

        ax_macd.set_ylabel('MACD', fontsize=11)
        ax_macd.legend(loc='upper left', fontsize=9)
        ax_macd.grid(True, alpha=0.3)
        ax_macd.xaxis.set_major_formatter(mdates.DateFormatter('%Y-%b'))
        ax_macd.xaxis.set_major_locator(mdates.MonthLocator(interval=4))
        plt.xticks(rotation=45, fontsize=8)
        plt.tight_layout()

        buf = io.BytesIO()
        plt.savefig(buf, format='png', dpi=150, bbox_inches='tight')
        buf.seek(0)
        b64 = base64.b64encode(buf.read()).decode('utf-8')
        buf.close()
        plt.close(fig3)
        chart_data["momentum_chart"] = f"data:image/png;base64,{b64}"

        print(f"[Chart] Generated 3 charts for {name} ({code})")

    except Exception as e:
        print(f"[Chart] Error generating charts for {code}: {e}")
        import traceback
        traceback.print_exc()

    return chart_data


def _calculate_support_resistance(highs_arr, lows_arr, closes_arr, volumes_arr, current_price, num_levels=2):
    """지지/저항 계산 (피보나치 + 거래량 밀집)"""
    import numpy as np

    highs_np = np.array(highs_arr, dtype=float)
    lows_np = np.array(lows_arr, dtype=float)
    closes_np = np.array(closes_arr, dtype=float)
    volumes_np = np.array(volumes_arr, dtype=float)
    n = len(closes_np)

    price_min, price_max = float(lows_np.min()), float(highs_np.max())
    price_range_total = price_max - price_min
    num_bins = 50
    bin_edges = np.linspace(price_min, price_max, num_bins + 1)
    volume_profile = np.zeros(num_bins)

    for i in range(n):
        c, v = closes_np[i], volumes_np[i]
        bin_idx = min(int((c - price_min) / price_range_total * num_bins), num_bins - 1)
        volume_profile[bin_idx] += v

    vol_threshold = np.percentile(volume_profile, 70)
    volume_clusters = []
    for b in range(num_bins):
        if volume_profile[b] >= vol_threshold:
            mid_price = (bin_edges[b] + bin_edges[b + 1]) / 2
            volume_clusters.append({'price': mid_price, 'volume': volume_profile[b]})

    window = 15
    min_prominence_pct = 0.08
    local_highs = []
    local_lows = []

    for i in range(window, n - window):
        if highs_np[i] == max(highs_np[i - window:i + window + 1]):
            left_min = min(lows_np[max(0, i - window):i])
            right_min = min(lows_np[i + 1:min(n, i + window + 1)])
            prominence = highs_np[i] - max(left_min, right_min)
            if prominence >= price_range_total * min_prominence_pct:
                local_highs.append({'idx': i, 'price': float(highs_np[i]), 'prominence': prominence})

        if lows_np[i] == min(lows_np[i - window:i + window + 1]):
            left_max = max(highs_np[max(0, i - window):i])
            right_max = max(highs_np[i + 1:min(n, i + window + 1)])
            prominence = min(left_max, right_max) - lows_np[i]
            if prominence >= price_range_total * min_prominence_pct:
                local_lows.append({'idx': i, 'price': float(lows_np[i]), 'prominence': prominence})

    highs_above = [h for h in local_highs if h['price'] > current_price * 1.01]
    if highs_above:
        swing_high_point = min(highs_above, key=lambda x: x['price'])
    else:
        swing_high_point = {'price': float(highs_np.max()), 'idx': int(np.argmax(highs_np))}
    swing_high = swing_high_point['price']

    lows_below = [l for l in local_lows
                  if l['price'] < current_price * 0.99
                  and l['price'] >= current_price * 0.50]

    if lows_below:
        lows_below.sort(key=lambda x: x['prominence'], reverse=True)
        top_lows = lows_below[:max(1, len(lows_below) // 2)]
        swing_low_point = max(top_lows, key=lambda x: x['price'])
    else:
        vol_below = [vc for vc in volume_clusters if vc['price'] < current_price * 0.98]
        if vol_below:
            swing_low_point = max(vol_below, key=lambda x: x['price'])
        else:
            swing_low_point = {'price': float(lows_np.min())}
    swing_low = swing_low_point['price']

    fib_range = swing_high - swing_low

    if fib_range < current_price * 0.12:
        return [round(current_price * 0.95), round(current_price * 0.88)], \
               [round(current_price * 1.05), round(current_price * 1.12)]

    fib_236 = swing_low + fib_range * 0.236
    fib_382 = swing_low + fib_range * 0.382
    fib_500 = swing_low + fib_range * 0.500
    fib_618 = swing_low + fib_range * 0.618
    fib_786 = swing_low + fib_range * 0.786
    fib_ext_127 = swing_low + fib_range * 1.272
    fib_ext_161 = swing_low + fib_range * 1.618

    support_candidates = []
    for fib_level, name in [(fib_786, '78.6'), (fib_618, '61.8'),
                             (fib_500, '50.0'), (fib_382, '38.2'), (fib_236, '23.6')]:
        if fib_level < current_price * 0.98:
            adjusted = fib_level
            for vc in volume_clusters:
                if abs(vc['price'] - fib_level) / fib_level < 0.03:
                    adjusted = vc['price']
                    break
            dist_pct = (current_price - adjusted) / current_price * 100
            support_candidates.append({'level': adjusted, 'dist': dist_pct, 'source': f'fib_{name}'})

    for vc in volume_clusters:
        if vc['price'] < current_price * 0.97:
            dist_pct = (current_price - vc['price']) / current_price * 100
            is_dup = any(abs(sc['level'] - vc['price']) / sc['level'] < 0.03 for sc in support_candidates)
            if not is_dup:
                support_candidates.append({'level': vc['price'], 'dist': dist_pct, 'source': 'vol'})

    support_candidates.sort(key=lambda x: x['dist'])

    resistance_candidates = []
    at_high = current_price >= float(highs_np.max()) * 0.97

    if at_high:
        if fib_ext_127 > current_price * 1.02:
            dist_pct = (fib_ext_127 - current_price) / current_price * 100
            resistance_candidates.append({'level': fib_ext_127, 'dist': dist_pct, 'source': 'fib_127'})
        if fib_ext_161 > current_price * 1.02:
            dist_pct = (fib_ext_161 - current_price) / current_price * 100
            resistance_candidates.append({'level': fib_ext_161, 'dist': dist_pct, 'source': 'fib_161'})
    else:
        for lh in local_highs:
            if lh['price'] > current_price * 1.02:
                dist_pct = (lh['price'] - current_price) / current_price * 100
                resistance_candidates.append({'level': lh['price'], 'dist': dist_pct, 'source': 'local'})

    if swing_high > current_price * 1.02:
        is_dup = any(abs(rc['level'] - swing_high) / rc['level'] < 0.03 for rc in resistance_candidates)
        if not is_dup:
            dist_pct = (swing_high - current_price) / current_price * 100
            resistance_candidates.append({'level': swing_high, 'dist': dist_pct, 'source': 'swing'})

    for vc in volume_clusters:
        if vc['price'] > current_price * 1.02:
            dist_pct = (vc['price'] - current_price) / current_price * 100
            is_dup = any(abs(rc['level'] - vc['price']) / rc['level'] < 0.03 for rc in resistance_candidates)
            if not is_dup:
                resistance_candidates.append({'level': vc['price'], 'dist': dist_pct, 'source': 'vol'})

    resistance_candidates.sort(key=lambda x: x['dist'])

    if len(support_candidates) >= 2:
        support_1 = round(support_candidates[0]['level'])
        support_2 = None
        for sc in support_candidates[1:]:
            if abs(sc['level'] - support_candidates[0]['level']) / support_candidates[0]['level'] >= 0.08:
                support_2 = round(sc['level'])
                break
        if support_2 is None:
            support_2 = round(support_candidates[-1]['level'])
    elif len(support_candidates) == 1:
        support_1 = round(support_candidates[0]['level'])
        support_2 = round(swing_low)
    else:
        support_1 = round(current_price * 0.92)
        support_2 = round(current_price * 0.85)

    if len(resistance_candidates) >= 2:
        resistance_1 = round(resistance_candidates[0]['level'])
        resistance_2 = None
        for rc in resistance_candidates[1:]:
            if abs(rc['level'] - resistance_candidates[0]['level']) / resistance_candidates[0]['level'] >= 0.08:
                resistance_2 = round(rc['level'])
                break
        if resistance_2 is None:
            resistance_2 = round(resistance_candidates[-1]['level'])
    elif len(resistance_candidates) == 1:
        resistance_1 = round(resistance_candidates[0]['level'])
        resistance_2 = round(swing_high * 1.1) if at_high else round(swing_high)
    else:
        resistance_1 = round(current_price * 1.08)
        resistance_2 = round(current_price * 1.15)

    if support_1 < support_2:
        support_1, support_2 = support_2, support_1
    if resistance_1 > resistance_2:
        resistance_1, resistance_2 = resistance_2, resistance_1

    return [support_1, support_2], [resistance_1, resistance_2]


def _calculate_adx_series(highs, lows, closes):
    """ADX/DI 시계열 계산"""
    adx_series = []
    plus_di_series = []
    minus_di_series = []
    adx_period = 14

    tr_list = []
    plus_dm_list = []
    minus_dm_list = []

    for i in range(1, len(closes)):
        h_diff = highs[i] - highs[i-1]
        l_diff = lows[i-1] - lows[i]
        plus_dm_list.append(h_diff if h_diff > l_diff and h_diff > 0 else 0)
        minus_dm_list.append(l_diff if l_diff > h_diff and l_diff > 0 else 0)
        tr_list.append(max(highs[i]-lows[i], abs(highs[i]-closes[i-1]), abs(lows[i]-closes[i-1])))

    if len(tr_list) >= adx_period * 2:
        atr = sum(tr_list[:adx_period]) / adx_period
        plus_dm_smooth = sum(plus_dm_list[:adx_period]) / adx_period
        minus_dm_smooth = sum(minus_dm_list[:adx_period]) / adx_period
        dx_list = []

        for i in range(adx_period, len(tr_list)):
            atr = (atr * (adx_period-1) + tr_list[i]) / adx_period
            plus_dm_smooth = (plus_dm_smooth * (adx_period-1) + plus_dm_list[i]) / adx_period
            minus_dm_smooth = (minus_dm_smooth * (adx_period-1) + minus_dm_list[i]) / adx_period

            if atr > 0:
                pdi = (plus_dm_smooth / atr) * 100
                mdi = (minus_dm_smooth / atr) * 100
            else:
                pdi = mdi = 0

            plus_di_series.append(pdi)
            minus_di_series.append(mdi)

            if pdi + mdi > 0:
                dx_list.append(abs(pdi - mdi) / (pdi + mdi) * 100)
            else:
                dx_list.append(0)

        for i in range(len(dx_list)):
            if i < adx_period - 1:
                adx_series.append(None)
            else:
                adx_series.append(sum(dx_list[i-adx_period+1:i+1]) / adx_period)

    return adx_series, plus_di_series, minus_di_series


def _calculate_rsi_series(closes, period=14):
    """RSI 시계열 계산"""
    rsi_values = []
    for i in range(period, len(closes)):
        gains = []
        losses = []
        for j in range(i - period + 1, i + 1):
            change = closes[j] - closes[j - 1]
            if change > 0:
                gains.append(change)
                losses.append(0)
            else:
                gains.append(0)
                losses.append(abs(change))

        avg_gain = sum(gains) / period
        avg_loss = sum(losses) / period

        if avg_loss == 0:
            rsi_values.append(100)
        else:
            rs = avg_gain / avg_loss
            rsi_values.append(100 - (100 / (1 + rs)))

    return rsi_values


def _calculate_macd_series(closes):
    """MACD 시계열 계산"""
    def _calc_ema_series(data, period):
        ema = [None] * (period - 1)
        multiplier = 2 / (period + 1)
        ema.append(sum(data[:period]) / period)
        for i in range(period, len(data)):
            ema.append((data[i] - ema[-1]) * multiplier + ema[-1])
        return ema

    ema12 = _calc_ema_series(closes, 12)
    ema26 = _calc_ema_series(closes, 26)
    macd_line = [e12 - e26 if e12 and e26 else None for e12, e26 in zip(ema12, ema26)]

    macd_valid = [v for v in macd_line if v is not None]
    if len(macd_valid) >= 9:
        signal_line = [None] * (len(macd_line) - len(macd_valid))
        signal_ema = _calc_ema_series(macd_valid, 9)
        signal_line.extend(signal_ema)
    else:
        signal_line = [None] * len(macd_line)

    histogram = [m - s if m and s else None for m, s in zip(macd_line, signal_line)]

    return macd_line, signal_line, histogram

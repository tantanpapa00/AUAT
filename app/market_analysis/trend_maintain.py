"""
추세유지 분석 모듈 (20MA 기준)
"""
import numpy as np
from typing import List, Dict, Optional
from datetime import date

# 섹터 ETF 설정은 sector_config에서 가져옴
from .sector_config import SECTOR_ETFS


def calculate_trend_maintain(daily_closes: List[float], lang: str = "kr") -> Optional[Dict]:
    """
    추세유지 판단:
    1. 20일 이동평균(MA20) 계산
    2. 현재가가 MA20 위에 연속 몇 일 유지되는지 계산
    3. 5일 이상 유지 = "유지 N일" (green)
    4. MA20 아래 = "이탈 N일" (red)

    Args:
        daily_closes: 일별 종가 리스트 (오래된 것 먼저)
        lang: 언어 설정 ('kr' = 한글, 'en' = 영문)

    Returns:
        {
            "position": "유지" | "이탈" (kr) or "Holding" | "Below" (en),
            "days": 연속 유지/이탈 일수,
            "gap_percent": 20일 이격도 %,
            "signal": "green" | "yellow" | "red",
            "return_since_entry": 유지 시작 후 수익률 %,
            "ma20": 20일 이동평균,
            "current_price": 현재가,
        }
    """
    if len(daily_closes) < 20:
        return None

    ma20 = float(np.mean(daily_closes[-20:]))
    current = float(daily_closes[-1])
    gap_pct = (current - ma20) / ma20 * 100

    # 연속 유지/이탈 일수 계산
    days = 0
    is_above = current > ma20

    for i in range(len(daily_closes) - 1, 19, -1):
        ma = float(np.mean(daily_closes[i-20:i]))
        if is_above and daily_closes[i] > ma:
            days += 1
        elif not is_above and daily_closes[i] <= ma:
            days += 1
        else:
            break

    # lang에 따라 position 텍스트 결정
    if lang == "en":
        position = "Holding" if is_above else "Below"
    else:
        position = "유지" if is_above else "이탈"

    # 신호등
    if is_above and days >= 5:
        signal = "green"
    elif is_above and days < 5:
        signal = "yellow"
    else:
        signal = "red"

    # 유지 시작점 수익률
    entry_idx = -(days + 1) if days < len(daily_closes) - 20 else -len(daily_closes) + 20
    entry_price = daily_closes[entry_idx] if is_above and abs(entry_idx) < len(daily_closes) else 0
    return_pct = (current - entry_price) / entry_price * 100 if entry_price > 0 else 0

    return {
        "position": position,
        "days": days,
        "gap_percent": round(gap_pct, 1),
        "signal": signal,
        "return_since_entry": round(return_pct, 1) if is_above else None,
        "ma20": round(ma20, 2),
        "current_price": round(current, 2),
    }

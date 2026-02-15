"""
추세유지 분석 모듈 (20MA 기준)
"""
import numpy as np
from typing import List, Dict, Optional
from datetime import date


# 섹터 대표 ETF 목록
SECTOR_ETFS = [
    {"symbol": "069500", "name": "KODEX 200", "sector": "마켓"},
    {"symbol": "229200", "name": "KODEX 코스닥150", "sector": "마켓"},
    {"symbol": "091170", "name": "KODEX 은행", "sector": "금융"},
    {"symbol": "091180", "name": "KODEX 증권", "sector": "증권"},
    {"symbol": "140700", "name": "KODEX 보험", "sector": "보험"},
    {"symbol": "266360", "name": "KODEX 자동차", "sector": "자동차"},
    {"symbol": "091160", "name": "KODEX 반도체", "sector": "반도체"},
    {"symbol": "117460", "name": "KODEX 에너지화학", "sector": "에너지"},
    {"symbol": "117680", "name": "KODEX 철강", "sector": "철강"},
    {"symbol": "117700", "name": "KODEX 건설", "sector": "건설"},
    {"symbol": "266370", "name": "KODEX 바이오", "sector": "바이오"},
    {"symbol": "091220", "name": "KODEX 미디어&엔터", "sector": "미디어"},
    {"symbol": "098560", "name": "KODEX 운송", "sector": "운송"},
]


def calculate_trend_maintain(daily_closes: List[float]) -> Optional[Dict]:
    """
    추세유지 판단:
    1. 20일 이동평균(MA20) 계산
    2. 현재가가 MA20 위에 연속 몇 일 유지되는지 계산
    3. 5일 이상 유지 = "유지 N일" (green)
    4. MA20 아래 = "이탈 N일" (red)

    Args:
        daily_closes: 일별 종가 리스트 (오래된 것 먼저)

    Returns:
        {
            "position": "유지" | "이탈",
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

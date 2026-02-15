"""
시장신호 알고리즘 엔진 (IBD Big Picture 기반)

Distribution Day (DD): 하락 + 거래량 증가
Follow-Through Day (FTD): Rally 4일 후 + 1.25% 상승 + 거래량 증가
Big Picture Status: confirmed_uptrend | uptrend_under_pressure | market_in_correction | rally_attempt
"""

from datetime import datetime, date, timedelta
from typing import Dict, List, Any, Optional
from dataclasses import dataclass


@dataclass
class MarketData:
    """일별 시장 데이터"""
    date: date
    market: str  # KOSPI | KOSDAQ
    index_value: float
    change_amount: float
    change_percent: float
    trading_volume: int
    trading_value: int
    rising_stocks: int
    falling_stocks: int
    unchanged_stocks: int
    upper_limit_stocks: int
    lower_limit_stocks: int
    listed_stocks: int
    foreign_net: int = 0
    institution_net: int = 0
    individual_net: int = 0


@dataclass
class PrevSignal:
    """이전 시장신호"""
    status: str
    distribution_days: List[Dict]
    active_dd_count: int
    rally_start_date: Optional[date]
    rally_day_count: int
    last_ftd_date: Optional[date]


# ============================================
# Distribution Day (DD) 감지
# ============================================
def detect_distribution_day(today: MarketData, yesterday: MarketData) -> bool:
    """
    DD 조건:
    1. 지수 하락 (change_percent < 0)
    2. 거래량 증가 (today.volume > yesterday.volume)

    Returns: True/False
    """
    if today.change_percent < 0 and today.trading_volume > yesterday.trading_volume:
        return True
    return False


# ============================================
# Distribution Day 만료 처리
# ============================================
def expire_distribution_days(
    distribution_days: List[Dict],
    today_date: date,
    today_index_value: float
) -> tuple:
    """
    DD 만료 조건:
    1. 25일 경과 → is_active = False
    2. DD 발생일 대비 6% 이상 상승 → is_active = False

    Args:
        distribution_days: [{date, change_percent, volume, prev_volume, index_value, is_active}]
        today_date: 오늘 날짜
        today_index_value: 오늘 지수 종가

    Returns: (갱신된 distribution_days, active_dd_count)
    """
    if not distribution_days:
        return [], 0

    for dd in distribution_days:
        if not dd.get('is_active', False):
            continue

        # 날짜 파싱
        dd_date = dd.get('date')
        if isinstance(dd_date, str):
            dd_date = datetime.fromisoformat(dd_date.replace('Z', '+00:00')).date()
        elif isinstance(dd_date, datetime):
            dd_date = dd_date.date()

        # 25일 경과 만료
        if today_date and dd_date:
            days_elapsed = (today_date - dd_date).days
            if days_elapsed >= 25:
                dd['is_active'] = False
                dd['expired_reason'] = '25일 경과'
                continue

        # 6% 상승 만료
        dd_index = dd.get('index_value', 0)
        if dd_index and dd_index > 0 and today_index_value:
            gain_pct = (today_index_value - dd_index) / dd_index * 100
            if gain_pct >= 6.0:
                dd['is_active'] = False
                dd['expired_reason'] = f'6% 상승 ({gain_pct:.1f}%)'

    active_count = sum(1 for dd in distribution_days if dd.get('is_active', False))
    return distribution_days, active_count


# ============================================
# Follow-Through Day (FTD) 감지
# ============================================
def detect_follow_through_day(
    today: MarketData,
    yesterday: MarketData,
    rally_day_count: int
) -> bool:
    """
    FTD 조건:
    1. Rally 시작일로부터 4일 이후 (rally_day_count >= 4)
    2. 지수 +1.25% 이상 상승
    3. 거래량 > 전일 거래량

    Returns: True/False
    """
    if rally_day_count >= 4:
        if today.change_percent >= 1.25 and today.trading_volume > yesterday.trading_volume:
            return True
    return False


# ============================================
# Rally Day 감지 (바닥 반등 시작)
# ============================================
def detect_rally_day(today: MarketData, yesterday: MarketData) -> bool:
    """
    Rally 시작 조건:
    - 하락 추세 중 첫 양봉 (지수 상승)

    Returns: True/False
    """
    if today.change_percent > 0:
        return True
    return False


# ============================================
# Big Picture 상태 전환
# ============================================
def update_big_picture_status(
    prev_status: str,
    active_dd_count: int,
    ftd_detected: bool,
    rally_detected: bool,
    rally_day_count: int
) -> str:
    """
    상태 전환 로직:

    confirmed_uptrend (DD 0~2)
        ↓ DD 3개 이상
    uptrend_under_pressure (DD 3~4)
        ↓ DD 5개 이상 또는 급락
    market_in_correction
        ↓ Rally Day 시작
    rally_attempt
        ↓ FTD 발생
    confirmed_uptrend

    Returns: new_status
    """
    if prev_status == 'confirmed_uptrend':
        if active_dd_count >= 3:
            return 'uptrend_under_pressure'
        return 'confirmed_uptrend'

    elif prev_status == 'uptrend_under_pressure':
        if active_dd_count >= 5:
            return 'market_in_correction'
        if active_dd_count < 3:
            return 'confirmed_uptrend'
        return 'uptrend_under_pressure'

    elif prev_status == 'market_in_correction':
        if rally_detected:
            return 'rally_attempt'
        return 'market_in_correction'

    elif prev_status == 'rally_attempt':
        if ftd_detected:
            return 'confirmed_uptrend'
        # Rally 실패 조건: 연속 하락 또는 Rally 저점 이탈 시
        # TODO: Rally 실패 조건 추가 필요
        return 'rally_attempt'

    return prev_status


# ============================================
# 단기 신호 계산
# ============================================
def calc_short_term_signal(today: MarketData, big_picture_status: str = None) -> str:
    """
    단기 신호 (Big Picture 상태 기반 - 스탁이지 방식):

    green:  confirmed_uptrend 또는 uptrend_under_pressure
    yellow: rally_attempt
    red:    market_in_correction

    스탁이지와 동일한 로직: Big Picture 상태에 따라 신호 결정

    Returns: 'green' | 'yellow' | 'red'
    """
    # Big Picture 상태 기반 신호 결정 (스탁이지 방식)
    if big_picture_status in ('confirmed_uptrend', 'uptrend_under_pressure'):
        return 'green'
    elif big_picture_status == 'rally_attempt':
        return 'yellow'
    elif big_picture_status == 'market_in_correction':
        return 'red'

    # Big Picture 상태가 없으면 일일 데이터 기반 (fallback)
    total = today.rising_stocks + today.falling_stocks
    if total == 0:
        return 'yellow'

    rising_ratio = today.rising_stocks / total

    if rising_ratio > 0.55 and today.change_percent > 0:
        return 'green'
    elif rising_ratio < 0.40 and today.change_percent < -1.0:
        return 'red'
    else:
        return 'yellow'


# ============================================
# 장기 신호 계산
# ============================================
def calc_long_term_signal(big_picture_status: str) -> str:
    """
    장기 신호 (Big Picture 상태 기반):

    green:  confirmed_uptrend
    yellow: uptrend_under_pressure | rally_attempt
    red:    market_in_correction

    Returns: 'green' | 'yellow' | 'red'
    """
    if big_picture_status == 'confirmed_uptrend':
        return 'green'
    elif big_picture_status in ('uptrend_under_pressure', 'rally_attempt'):
        return 'yellow'
    elif big_picture_status == 'market_in_correction':
        return 'red'
    return 'yellow'


# ============================================
# 메인 업데이트 함수
# ============================================
def update_market_signal(
    market: str,
    today_data: MarketData,
    yesterday_data: MarketData,
    prev_signal: PrevSignal
) -> Dict[str, Any]:
    """
    매일 실행:
    1. DD 감지
    2. DD 만료 처리
    3. FTD / Rally 감지
    4. Big Picture 상태 전환
    5. 단기/장기 신호 계산

    Returns: 새로운 시장신호 dict
    """
    # 1. Distribution Day 감지
    is_dd = detect_distribution_day(today_data, yesterday_data)

    distribution_days = list(prev_signal.distribution_days) if prev_signal.distribution_days else []

    if is_dd:
        distribution_days.append({
            'date': today_data.date.isoformat() if isinstance(today_data.date, date) else str(today_data.date),
            'change_percent': today_data.change_percent,
            'volume': today_data.trading_volume,
            'prev_volume': yesterday_data.trading_volume,
            'index_value': today_data.index_value,
            'is_active': True
        })

    # 2. DD 만료 처리
    today_date_obj = today_data.date if isinstance(today_data.date, date) else datetime.fromisoformat(str(today_data.date)).date()
    distribution_days, active_dd_count = expire_distribution_days(
        distribution_days, today_date_obj, today_data.index_value
    )

    # 3. Rally / FTD 감지
    rally_detected = False
    ftd_detected = False
    rally_day_count = prev_signal.rally_day_count or 0
    rally_start_date = prev_signal.rally_start_date
    last_ftd_date = prev_signal.last_ftd_date

    if prev_signal.status == 'market_in_correction':
        rally_detected = detect_rally_day(today_data, yesterday_data)
        if rally_detected:
            rally_day_count = 1
            rally_start_date = today_date_obj
    elif prev_signal.status == 'rally_attempt':
        # Rally 진행 중
        if today_data.change_percent > 0:
            rally_day_count += 1
        ftd_detected = detect_follow_through_day(today_data, yesterday_data, rally_day_count)

    # 4. Big Picture 상태 전환
    new_status = update_big_picture_status(
        prev_signal.status, active_dd_count, ftd_detected, rally_detected, rally_day_count
    )

    # FTD 발생 시 DD 초기화
    if ftd_detected and new_status == 'confirmed_uptrend':
        distribution_days = []
        active_dd_count = 0
        rally_day_count = 0
        last_ftd_date = today_date_obj

    # 5. 단기/장기 신호 계산 (Big Picture 상태 기반)
    short_term = calc_short_term_signal(today_data, new_status)
    long_term = calc_long_term_signal(new_status)

    # 6. 결과 반환
    return {
        'date': today_data.date,
        'market': market,
        'index_value': today_data.index_value,
        'change_amount': today_data.change_amount,
        'change_percent': today_data.change_percent,
        'trading_volume': today_data.trading_volume,
        'trading_value': today_data.trading_value,
        'rising_stocks': today_data.rising_stocks,
        'falling_stocks': today_data.falling_stocks,
        'unchanged_stocks': today_data.unchanged_stocks,
        'upper_limit_stocks': today_data.upper_limit_stocks,
        'lower_limit_stocks': today_data.lower_limit_stocks,
        'listed_stocks': today_data.listed_stocks,
        'status': new_status,
        'active_dd_count': active_dd_count,
        'distribution_days': distribution_days,
        'rally_start_date': rally_start_date,
        'rally_day_count': rally_day_count,
        'last_ftd_date': last_ftd_date,
        'short_term_signal': short_term,
        'long_term_signal': long_term,
        'foreign_net': today_data.foreign_net,
        'institution_net': today_data.institution_net,
        'individual_net': today_data.individual_net,
    }


# ============================================
# Big Picture 설정 (UI용)
# ============================================
BIG_PICTURE_CONFIG = {
    'confirmed_uptrend': {
        'label': '확인된 상승세',
        'label_en': 'Confirmed Uptrend',
        'exposure': '80-100%',
        'color': '#22c55e',  # green
        'description': '시장이 상승 추세에 있습니다. 적극적 매수 가능.'
    },
    'uptrend_under_pressure': {
        'label': '상승 둔화',
        'label_en': 'Uptrend Under Pressure',
        'exposure': '40-60%',
        'color': '#fde047',  # yellow
        'description': 'Distribution Day가 누적되고 있습니다. 신규 매수 자제.'
    },
    'market_in_correction': {
        'label': '조정 국면',
        'label_en': 'Market in Correction',
        'exposure': '0-20%',
        'color': '#ef4444',  # red
        'description': '시장이 조정 중입니다. 현금 비중 확대 권장.'
    },
    'rally_attempt': {
        'label': '반등 시도',
        'label_en': 'Rally Attempt',
        'exposure': '20-40%',
        'color': '#3b82f6',  # blue
        'description': '바닥에서 반등을 시도하고 있습니다. FTD 확인 필요.'
    }
}

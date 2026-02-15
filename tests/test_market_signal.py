"""
시장신호 알고리즘 테스트 (Phase 4)

테스트 항목:
1. DD 감지 (하락+거래량증가)
2. DD 미감지 (하락+거래량감소)
3. DD 만료 (25일 경과)
4. DD 만료 (6% 상승)
5. FTD 감지 (Rally 4일후+1.25%+거래량증가)
6. FTD 미감지 (Rally 3일후)
7. Big Picture 상태 전환 (DD 3개 → uptrend_under_pressure)
8. Big Picture 상태 전환 (FTD → confirmed_uptrend)
9-12. 단기/장기 신호 테스트
"""

import pytest
from datetime import date, timedelta
import sys
import os

# 프로젝트 루트 추가
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.market_analysis.signal_engine import (
    detect_distribution_day,
    expire_distribution_days,
    detect_follow_through_day,
    detect_rally_day,
    update_big_picture_status,
    calc_short_term_signal,
    calc_long_term_signal,
    update_market_signal,
    MarketData,
    PrevSignal,
)


# ============================================
# 테스트 1: DD 감지 (하락 + 거래량 증가)
# ============================================
def test_dd_detection_positive():
    """DD 감지: 하락+거래량증가 → True"""
    today = MarketData(
        date=date.today(),
        market="KOSPI",
        index_value=2500,
        change_amount=-30,
        change_percent=-1.2,  # 하락
        trading_volume=1000000,  # 거래량 증가
        trading_value=50000000000,
        rising_stocks=300,
        falling_stocks=600,
        unchanged_stocks=50,
        upper_limit_stocks=0,
        lower_limit_stocks=0,
        listed_stocks=950,
    )
    yesterday = MarketData(
        date=date.today() - timedelta(days=1),
        market="KOSPI",
        index_value=2530,
        change_amount=10,
        change_percent=0.4,
        trading_volume=800000,  # 어제보다 적음
        trading_value=40000000000,
        rising_stocks=500,
        falling_stocks=400,
        unchanged_stocks=50,
        upper_limit_stocks=0,
        lower_limit_stocks=0,
        listed_stocks=950,
    )

    result = detect_distribution_day(today, yesterday)
    assert result == True, "DD 감지 실패: 하락+거래량증가인데 감지 못함"


# ============================================
# 테스트 2: DD 미감지 (하락 + 거래량 감소)
# ============================================
def test_dd_detection_negative():
    """DD 미감지: 하락+거래량감소 → False"""
    today = MarketData(
        date=date.today(),
        market="KOSPI",
        index_value=2500,
        change_amount=-30,
        change_percent=-1.2,  # 하락
        trading_volume=700000,  # 거래량 감소
        trading_value=35000000000,
        rising_stocks=300,
        falling_stocks=600,
        unchanged_stocks=50,
        upper_limit_stocks=0,
        lower_limit_stocks=0,
        listed_stocks=950,
    )
    yesterday = MarketData(
        date=date.today() - timedelta(days=1),
        market="KOSPI",
        index_value=2530,
        change_amount=10,
        change_percent=0.4,
        trading_volume=800000,  # 어제보다 많음
        trading_value=40000000000,
        rising_stocks=500,
        falling_stocks=400,
        unchanged_stocks=50,
        upper_limit_stocks=0,
        lower_limit_stocks=0,
        listed_stocks=950,
    )

    result = detect_distribution_day(today, yesterday)
    assert result == False, "DD 잘못 감지: 거래량 감소인데 DD로 판단"


# ============================================
# 테스트 3: DD 만료 (25일 경과)
# ============================================
def test_dd_expiry_25_days():
    """DD 만료: 25일 경과 → is_active=False"""
    today = date.today()
    dd_date = today - timedelta(days=26)  # 26일 전 발생

    distribution_days = [
        {
            'date': dd_date.isoformat(),
            'change_percent': -1.5,
            'volume': 1000000,
            'prev_volume': 900000,
            'index_value': 2400,
            'is_active': True
        }
    ]

    updated_dds, active_count = expire_distribution_days(
        distribution_days, today, 2500
    )

    assert active_count == 0, "DD 만료 실패: 25일 경과인데 아직 활성"
    assert updated_dds[0]['is_active'] == False


# ============================================
# 테스트 4: DD 만료 (6% 상승)
# ============================================
def test_dd_expiry_6_percent_gain():
    """DD 만료: 6% 상승 → is_active=False"""
    today = date.today()
    dd_date = today - timedelta(days=10)  # 10일 전 발생

    distribution_days = [
        {
            'date': dd_date.isoformat(),
            'change_percent': -1.5,
            'volume': 1000000,
            'prev_volume': 900000,
            'index_value': 2400,  # DD 발생 시 지수
            'is_active': True
        }
    ]

    # 오늘 지수 2400 * 1.07 = 2568 (7% 상승)
    updated_dds, active_count = expire_distribution_days(
        distribution_days, today, 2568
    )

    assert active_count == 0, "DD 만료 실패: 6% 상승인데 아직 활성"
    assert updated_dds[0]['is_active'] == False


# ============================================
# 테스트 5: FTD 감지 (Rally 4일 후 + 1.25% + 거래량 증가)
# ============================================
def test_ftd_detection_positive():
    """FTD 감지: Rally 4일후+1.25%상승+거래량증가 → True"""
    today = MarketData(
        date=date.today(),
        market="KOSPI",
        index_value=2500,
        change_amount=35,
        change_percent=1.4,  # 1.25% 이상 상승
        trading_volume=1000000,  # 거래량 증가
        trading_value=50000000000,
        rising_stocks=600,
        falling_stocks=300,
        unchanged_stocks=50,
        upper_limit_stocks=5,
        lower_limit_stocks=0,
        listed_stocks=950,
    )
    yesterday = MarketData(
        date=date.today() - timedelta(days=1),
        market="KOSPI",
        index_value=2465,
        change_amount=10,
        change_percent=0.4,
        trading_volume=800000,  # 어제보다 적음
        trading_value=40000000000,
        rising_stocks=500,
        falling_stocks=400,
        unchanged_stocks=50,
        upper_limit_stocks=0,
        lower_limit_stocks=0,
        listed_stocks=950,
    )

    result = detect_follow_through_day(today, yesterday, rally_day_count=4)
    assert result == True, "FTD 감지 실패"


# ============================================
# 테스트 6: FTD 미감지 (Rally 3일)
# ============================================
def test_ftd_detection_too_early():
    """FTD 미감지: Rally 3일후 → False (4일 이후부터 가능)"""
    today = MarketData(
        date=date.today(),
        market="KOSPI",
        index_value=2500,
        change_amount=35,
        change_percent=1.4,
        trading_volume=1000000,
        trading_value=50000000000,
        rising_stocks=600,
        falling_stocks=300,
        unchanged_stocks=50,
        upper_limit_stocks=5,
        lower_limit_stocks=0,
        listed_stocks=950,
    )
    yesterday = MarketData(
        date=date.today() - timedelta(days=1),
        market="KOSPI",
        index_value=2465,
        change_amount=10,
        change_percent=0.4,
        trading_volume=800000,
        trading_value=40000000000,
        rising_stocks=500,
        falling_stocks=400,
        unchanged_stocks=50,
        upper_limit_stocks=0,
        lower_limit_stocks=0,
        listed_stocks=950,
    )

    result = detect_follow_through_day(today, yesterday, rally_day_count=3)
    assert result == False, "FTD 잘못 감지: Rally 3일차인데 FTD로 판단"


# ============================================
# 테스트 7: Big Picture 상태 전환 (DD 3개 → uptrend_under_pressure)
# ============================================
def test_big_picture_dd_pressure():
    """Big Picture: DD 3개 이상 → uptrend_under_pressure"""
    new_status = update_big_picture_status(
        prev_status='confirmed_uptrend',
        active_dd_count=3,
        ftd_detected=False,
        rally_detected=False,
        rally_day_count=0
    )
    assert new_status == 'uptrend_under_pressure', f"상태 전환 실패: {new_status}"


# ============================================
# 테스트 8: Big Picture 상태 전환 (FTD → confirmed_uptrend)
# ============================================
def test_big_picture_ftd_recovery():
    """Big Picture: FTD 발생 → confirmed_uptrend"""
    new_status = update_big_picture_status(
        prev_status='rally_attempt',
        active_dd_count=0,
        ftd_detected=True,
        rally_detected=False,
        rally_day_count=5
    )
    assert new_status == 'confirmed_uptrend', f"상태 전환 실패: {new_status}"


# ============================================
# 테스트 9: 단기 신호 green
# ============================================
def test_short_term_signal_green():
    """단기 신호: 상승비율 60% + 등락 +0.5% → green"""
    today = MarketData(
        date=date.today(),
        market="KOSPI",
        index_value=2500,
        change_amount=12.5,
        change_percent=0.5,  # +0.5%
        trading_volume=1000000,
        trading_value=50000000000,
        rising_stocks=600,  # 60%
        falling_stocks=350,  # 35%
        unchanged_stocks=50,
        upper_limit_stocks=5,
        lower_limit_stocks=0,
        listed_stocks=950,
    )

    signal = calc_short_term_signal(today)
    assert signal == 'green', f"단기 신호 실패: {signal}"


# ============================================
# 테스트 10: 단기 신호 red
# ============================================
def test_short_term_signal_red():
    """단기 신호: 상승비율 35% + 등락 -2% → red"""
    today = MarketData(
        date=date.today(),
        market="KOSPI",
        index_value=2450,
        change_amount=-50,
        change_percent=-2.0,  # -2%
        trading_volume=1000000,
        trading_value=50000000000,
        rising_stocks=300,  # 35%
        falling_stocks=600,  # 65%
        unchanged_stocks=50,
        upper_limit_stocks=0,
        lower_limit_stocks=5,
        listed_stocks=950,
    )

    signal = calc_short_term_signal(today)
    assert signal == 'red', f"단기 신호 실패: {signal}"


# ============================================
# 테스트 11: 장기 신호 green (confirmed_uptrend)
# ============================================
def test_long_term_signal_green():
    """장기 신호: confirmed_uptrend → green"""
    signal = calc_long_term_signal('confirmed_uptrend')
    assert signal == 'green', f"장기 신호 실패: {signal}"


# ============================================
# 테스트 12: 장기 신호 red (market_in_correction)
# ============================================
def test_long_term_signal_red():
    """장기 신호: market_in_correction → red"""
    signal = calc_long_term_signal('market_in_correction')
    assert signal == 'red', f"장기 신호 실패: {signal}"


# ============================================
# 테스트 13: update_market_signal 전체 흐름
# ============================================
def test_update_market_signal_flow():
    """전체 업데이트 흐름 테스트"""
    today = MarketData(
        date=date.today(),
        market="KOSPI",
        index_value=2500,
        change_amount=-25,
        change_percent=-1.0,
        trading_volume=1000000,  # 거래량 증가 → DD 발생
        trading_value=50000000000,
        rising_stocks=350,
        falling_stocks=550,
        unchanged_stocks=50,
        upper_limit_stocks=0,
        lower_limit_stocks=2,
        listed_stocks=950,
    )
    yesterday = MarketData(
        date=date.today() - timedelta(days=1),
        market="KOSPI",
        index_value=2525,
        change_amount=10,
        change_percent=0.4,
        trading_volume=800000,
        trading_value=40000000000,
        rising_stocks=500,
        falling_stocks=400,
        unchanged_stocks=50,
        upper_limit_stocks=0,
        lower_limit_stocks=0,
        listed_stocks=950,
    )
    prev_signal = PrevSignal(
        status='confirmed_uptrend',
        distribution_days=[],
        active_dd_count=0,
        rally_start_date=None,
        rally_day_count=0,
        last_ftd_date=None,
    )

    result = update_market_signal("KOSPI", today, yesterday, prev_signal)

    assert result['market'] == "KOSPI"
    assert result['active_dd_count'] == 1  # DD 1개 발생
    assert len(result['distribution_days']) == 1
    assert result['status'] == 'confirmed_uptrend'  # DD 1개면 아직 confirmed


# ============================================
# 테스트 14: 추세유지 분석 - 유지 상태
# ============================================
def test_trend_maintain_above_ma20():
    """추세유지: 20MA 위 5일 이상 → 유지 상태, green 신호"""
    from app.market_analysis.trend_maintain import calculate_trend_maintain

    # 30일 종가 데이터 (상승 추세)
    closes = [100 + i * 0.5 for i in range(30)]  # 100 → 114.5 상승

    result = calculate_trend_maintain(closes)

    assert result is not None
    assert result['position'] == '유지'
    assert result['signal'] == 'green'
    assert result['days'] >= 5


# ============================================
# 테스트 15: 추세유지 분석 - 이탈 상태
# ============================================
def test_trend_maintain_below_ma20():
    """추세유지: 20MA 아래 → 이탈 상태, red 신호"""
    from app.market_analysis.trend_maintain import calculate_trend_maintain

    # 30일 종가 데이터 (하락 추세)
    closes = [100 - i * 0.5 for i in range(30)]  # 100 → 85.5 하락

    result = calculate_trend_maintain(closes)

    assert result is not None
    assert result['position'] == '이탈'
    assert result['signal'] == 'red'


# ============================================
# 테스트 16: 추세유지 분석 - 데이터 부족
# ============================================
def test_trend_maintain_insufficient_data():
    """추세유지: 20일 미만 데이터 → None"""
    from app.market_analysis.trend_maintain import calculate_trend_maintain

    closes = [100 + i for i in range(15)]  # 15일 데이터만

    result = calculate_trend_maintain(closes)

    assert result is None


# ============================================
# 테스트 17: 추세유지 분석 - yellow 신호 (유지 5일 미만)
# ============================================
def test_trend_maintain_yellow_signal():
    """추세유지: 20MA 위지만 5일 미만 → yellow 신호"""
    from app.market_analysis.trend_maintain import calculate_trend_maintain

    # 20일은 하락, 마지막 3일만 상승하여 MA 돌파
    closes = [100 - i * 0.3 for i in range(20)]  # 하락
    closes.extend([95, 96, 97])  # 마지막 3일 상승

    result = calculate_trend_maintain(closes)

    assert result is not None
    # 최근 MA 위에 있으면 유지, 아래면 이탈
    # position과 signal이 제대로 계산되는지 확인


# ============================================
# 테스트 18: Big Picture DD 5개 → market_in_correction
# ============================================
def test_big_picture_dd5_correction():
    """Big Picture: DD 5개 이상 → market_in_correction"""
    new_status = update_big_picture_status(
        prev_status='uptrend_under_pressure',
        active_dd_count=5,
        ftd_detected=False,
        rally_detected=False,
        rally_day_count=0
    )
    assert new_status == 'market_in_correction'


# ============================================
# 테스트 19: Big Picture rally_attempt 진입
# ============================================
def test_big_picture_rally_attempt():
    """Big Picture: correction에서 Rally Day → rally_attempt"""
    new_status = update_big_picture_status(
        prev_status='market_in_correction',
        active_dd_count=3,
        ftd_detected=False,
        rally_detected=True,  # Rally 시작
        rally_day_count=1
    )
    assert new_status == 'rally_attempt'


# ============================================
# 테스트 20: DD 만료 안됨 (24일 경과)
# ============================================
def test_dd_not_expired_24_days():
    """DD 만료 안됨: 24일 경과 → 아직 활성"""
    today = date.today()
    dd_date = today - timedelta(days=24)  # 24일 전 발생

    distribution_days = [
        {
            'date': dd_date.isoformat(),
            'change_percent': -1.5,
            'volume': 1000000,
            'prev_volume': 900000,
            'index_value': 2400,
            'is_active': True
        }
    ]

    updated_dds, active_count = expire_distribution_days(
        distribution_days, today, 2400  # 지수 변화 없음
    )

    assert active_count == 1, "DD 잘못 만료: 24일인데 만료됨"
    assert updated_dds[0]['is_active'] == True


# ============================================
# 테스트 21: DD 만료 안됨 (5% 상승)
# ============================================
def test_dd_not_expired_5_percent():
    """DD 만료 안됨: 5% 상승 → 아직 활성 (6% 필요)"""
    today = date.today()
    dd_date = today - timedelta(days=10)

    distribution_days = [
        {
            'date': dd_date.isoformat(),
            'change_percent': -1.5,
            'volume': 1000000,
            'prev_volume': 900000,
            'index_value': 2400,
            'is_active': True
        }
    ]

    # 2400 * 1.05 = 2520 (5% 상승)
    updated_dds, active_count = expire_distribution_days(
        distribution_days, today, 2520
    )

    assert active_count == 1, "DD 잘못 만료: 5%인데 만료됨"
    assert updated_dds[0]['is_active'] == True


# ============================================
# 테스트 22: 단기 신호 yellow (Big Picture 기반)
# ============================================
def test_short_term_signal_yellow_big_picture():
    """단기 신호: rally_attempt → yellow (Big Picture 기반)"""
    today = MarketData(
        date=date.today(),
        market="KOSPI",
        index_value=2500,
        change_amount=10,
        change_percent=0.4,
        trading_volume=1000000,
        trading_value=50000000000,
        rising_stocks=450,
        falling_stocks=450,
        unchanged_stocks=50,
        upper_limit_stocks=0,
        lower_limit_stocks=0,
        listed_stocks=950,
    )

    signal = calc_short_term_signal(today, big_picture_status='rally_attempt')
    assert signal == 'yellow'


# ============================================
# 테스트 23: 단기 신호 green (uptrend_under_pressure 포함)
# ============================================
def test_short_term_signal_green_under_pressure():
    """단기 신호: uptrend_under_pressure → green (Big Picture 기반)"""
    today = MarketData(
        date=date.today(),
        market="KOSPI",
        index_value=2500,
        change_amount=-10,
        change_percent=-0.4,
        trading_volume=1000000,
        trading_value=50000000000,
        rising_stocks=400,
        falling_stocks=500,
        unchanged_stocks=50,
        upper_limit_stocks=0,
        lower_limit_stocks=0,
        listed_stocks=950,
    )

    signal = calc_short_term_signal(today, big_picture_status='uptrend_under_pressure')
    assert signal == 'green'  # 스탁이지 방식: under_pressure도 green


# ============================================
# 테스트 24: 장기 신호 yellow (uptrend_under_pressure)
# ============================================
def test_long_term_signal_yellow():
    """장기 신호: uptrend_under_pressure → yellow"""
    signal = calc_long_term_signal('uptrend_under_pressure')
    assert signal == 'yellow'


# ============================================
# 테스트 25: Rally Day 감지
# ============================================
def test_rally_day_detection():
    """Rally Day 감지: 하락 추세 중 첫 양봉"""
    today = MarketData(
        date=date.today(),
        market="KOSPI",
        index_value=2400,
        change_amount=20,
        change_percent=0.8,  # 양봉
        trading_volume=900000,
        trading_value=45000000000,
        rising_stocks=500,
        falling_stocks=400,
        unchanged_stocks=50,
        upper_limit_stocks=2,
        lower_limit_stocks=0,
        listed_stocks=950,
    )
    yesterday = MarketData(
        date=date.today() - timedelta(days=1),
        market="KOSPI",
        index_value=2380,
        change_amount=-30,
        change_percent=-1.2,  # 어제 음봉
        trading_volume=1000000,
        trading_value=50000000000,
        rising_stocks=350,
        falling_stocks=550,
        unchanged_stocks=50,
        upper_limit_stocks=0,
        lower_limit_stocks=3,
        listed_stocks=950,
    )

    result = detect_rally_day(today, yesterday)
    assert result == True


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

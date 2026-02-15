"""
시장신호 스케줄러

- 매일 장 마감 후 (16:00) 시장신호 업데이트
- 주말/공휴일 스킵
"""

import asyncio
from datetime import datetime, date, timedelta
from typing import Optional
from sqlalchemy.orm import Session
from sqlalchemy import text

from .signal_engine import MarketData, PrevSignal, update_market_signal
from .data_collector import collect_daily_market_data


async def daily_market_update(db: Session) -> dict:
    """
    매일 실행:
    1. 네이버 API에서 당일 데이터 수집
    2. signal_engine으로 DD/FTD/Big Picture 계산
    3. DB 저장

    Returns: {kospi: {...}, kosdaq: {...}}
    """
    result = {"kospi": None, "kosdaq": None, "errors": []}

    today = datetime.now()

    # 주말 체크 (토=5, 일=6)
    if today.weekday() >= 5:
        result["errors"].append("주말은 업데이트하지 않습니다.")
        return result

    for market in ['KOSPI', 'KOSDAQ']:
        try:
            # 1. 오늘 데이터 수집
            today_data = await collect_daily_market_data(market)
            if not today_data:
                result["errors"].append(f"{market} 데이터 수집 실패")
                continue

            # 2. 어제 데이터 조회 (DB)
            yesterday_data = await get_yesterday_from_db(db, market)

            # 3. 이전 신호 조회 (DB)
            prev_signal = await get_latest_signal_from_db(db, market)

            # 4. 신호 계산
            new_signal = update_market_signal(market, today_data, yesterday_data, prev_signal)

            # 5. DB 저장
            await save_signal_to_db(db, new_signal)

            result[market.lower()] = new_signal

        except Exception as e:
            result["errors"].append(f"{market} 업데이트 오류: {str(e)}")

    return result


async def get_yesterday_from_db(db: Session, market: str) -> MarketData:
    """DB에서 어제 데이터 조회"""
    try:
        sql = text("""
            SELECT * FROM market_signals
            WHERE market = :market
            ORDER BY date DESC
            LIMIT 1
        """)
        row = db.execute(sql, {"market": market}).fetchone()

        if row:
            return MarketData(
                date=row.date.date() if hasattr(row.date, 'date') else row.date,
                market=row.market,
                index_value=row.index_value or 0,
                change_amount=row.change_amount or 0,
                change_percent=row.change_percent or 0,
                trading_volume=row.trading_volume or 0,
                trading_value=row.trading_value or 0,
                rising_stocks=row.rising_stocks or 0,
                falling_stocks=row.falling_stocks or 0,
                unchanged_stocks=row.unchanged_stocks or 0,
                upper_limit_stocks=row.upper_limit_stocks or 0,
                lower_limit_stocks=row.lower_limit_stocks or 0,
                listed_stocks=row.listed_stocks or 0,
                foreign_net=row.foreign_net or 0,
                institution_net=row.institution_net or 0,
                individual_net=row.individual_net or 0,
            )
    except Exception as e:
        print(f"[Scheduler] 어제 데이터 조회 오류: {e}")

    # 데이터 없으면 기본값
    return MarketData(
        date=date.today() - timedelta(days=1),
        market=market,
        index_value=0,
        change_amount=0,
        change_percent=0,
        trading_volume=0,
        trading_value=0,
        rising_stocks=0,
        falling_stocks=0,
        unchanged_stocks=0,
        upper_limit_stocks=0,
        lower_limit_stocks=0,
        listed_stocks=0,
    )


async def get_latest_signal_from_db(db: Session, market: str) -> PrevSignal:
    """DB에서 최신 시장신호 조회"""
    try:
        sql = text("""
            SELECT status, distribution_days, active_dd_count,
                   rally_start_date, rally_day_count, last_ftd_date
            FROM market_signals
            WHERE market = :market
            ORDER BY date DESC
            LIMIT 1
        """)
        row = db.execute(sql, {"market": market}).fetchone()

        if row:
            return PrevSignal(
                status=row.status or 'confirmed_uptrend',
                distribution_days=row.distribution_days or [],
                active_dd_count=row.active_dd_count or 0,
                rally_start_date=row.rally_start_date,
                rally_day_count=row.rally_day_count or 0,
                last_ftd_date=row.last_ftd_date,
            )
    except Exception as e:
        print(f"[Scheduler] 이전 신호 조회 오류: {e}")

    # 데이터 없으면 기본값 (최초 실행)
    return PrevSignal(
        status='confirmed_uptrend',
        distribution_days=[],
        active_dd_count=0,
        rally_start_date=None,
        rally_day_count=0,
        last_ftd_date=None,
    )


async def save_signal_to_db(db: Session, signal: dict):
    """DB에 시장신호 저장 (UPSERT)"""
    try:
        sql = text("""
            INSERT INTO market_signals (
                date, market, index_value, change_amount, change_percent,
                trading_volume, trading_value,
                rising_stocks, falling_stocks, unchanged_stocks,
                upper_limit_stocks, lower_limit_stocks, listed_stocks,
                status, active_dd_count, distribution_days,
                rally_start_date, rally_day_count, last_ftd_date,
                short_term_signal, long_term_signal,
                foreign_net, institution_net, individual_net
            ) VALUES (
                :date, :market, :index_value, :change_amount, :change_percent,
                :trading_volume, :trading_value,
                :rising_stocks, :falling_stocks, :unchanged_stocks,
                :upper_limit_stocks, :lower_limit_stocks, :listed_stocks,
                :status, :active_dd_count, :distribution_days::jsonb,
                :rally_start_date, :rally_day_count, :last_ftd_date,
                :short_term_signal, :long_term_signal,
                :foreign_net, :institution_net, :individual_net
            )
            ON CONFLICT (date, market)
            DO UPDATE SET
                index_value = EXCLUDED.index_value,
                change_amount = EXCLUDED.change_amount,
                change_percent = EXCLUDED.change_percent,
                trading_volume = EXCLUDED.trading_volume,
                trading_value = EXCLUDED.trading_value,
                rising_stocks = EXCLUDED.rising_stocks,
                falling_stocks = EXCLUDED.falling_stocks,
                unchanged_stocks = EXCLUDED.unchanged_stocks,
                upper_limit_stocks = EXCLUDED.upper_limit_stocks,
                lower_limit_stocks = EXCLUDED.lower_limit_stocks,
                listed_stocks = EXCLUDED.listed_stocks,
                status = EXCLUDED.status,
                active_dd_count = EXCLUDED.active_dd_count,
                distribution_days = EXCLUDED.distribution_days,
                rally_start_date = EXCLUDED.rally_start_date,
                rally_day_count = EXCLUDED.rally_day_count,
                last_ftd_date = EXCLUDED.last_ftd_date,
                short_term_signal = EXCLUDED.short_term_signal,
                long_term_signal = EXCLUDED.long_term_signal,
                foreign_net = EXCLUDED.foreign_net,
                institution_net = EXCLUDED.institution_net,
                individual_net = EXCLUDED.individual_net
        """)

        import json
        params = {
            **signal,
            'distribution_days': json.dumps(signal.get('distribution_days', []))
        }
        db.execute(sql, params)
        db.commit()

    except Exception as e:
        db.rollback()
        print(f"[Scheduler] DB 저장 오류: {e}")
        raise


async def initialize_market_data(db: Session, days: int = 30):
    """
    과거 데이터 초기화 (최초 실행 시)

    Note: 과거 데이터가 필요한 경우 별도 스크립트로 실행 권장
    """
    print(f"[Scheduler] 과거 {days}일 데이터 초기화 시작...")

    # 현재는 오늘 데이터만 수집
    result = await daily_market_update(db)

    print(f"[Scheduler] 초기화 완료: {result}")
    return result

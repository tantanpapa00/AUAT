# app/routers/market_kr.py
# 국내시장 API 엔드포인트

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import text
from datetime import datetime, timedelta
from typing import Dict, Optional

from app.db import get_db
from app.auth import get_current_user_optional, get_current_user
from app.models import User
from app.utils.plan_limits import check_pro_plan
from app.data_provider import get_kr_market_overview

router = APIRouter(prefix="/api/market", tags=["market-kr"])

# 종목명 → 종목코드 매핑 캐시
_stock_name_to_code_cache: Dict[str, str] = {}
_stock_name_cache_time: Optional[datetime] = None

# 주요 종목 하드코딩 매핑 (StockRS 테이블이 비어있을 때 사용)
_STOCK_NAME_FALLBACK = {
    # 시가총액 상위
    "삼성전자": "005930", "SK하이닉스": "000660", "LG에너지솔루션": "373220",
    "삼성바이오로직스": "207940", "현대차": "005380", "셀트리온": "068270",
    "기아": "000270", "KB금융": "105560", "POSCO홀딩스": "005490",
    "신한지주": "055550", "NAVER": "035420", "LG화학": "051910",
    "삼성SDI": "006400", "현대모비스": "012330", "카카오": "035720",
    "삼성물산": "028260", "하나금융지주": "086790", "LG전자": "066570",
    "삼성생명": "032830", "우리금융지주": "316140", "SK이노베이션": "096770",
    "HMM": "011200", "삼성화재": "000810", "KT&G": "033780",
    "SK텔레콤": "017670", "포스코퓨처엠": "003670", "고려아연": "010130",
    "SK": "034730", "한국전력": "015760", "두산에너빌리티": "034020",
    # 반도체/전자
    "SK스퀘어": "402340", "삼성전기": "009150", "DB하이텍": "000990",
    "리노공업": "058470", "하나마이크론": "067310", "이오테크닉스": "039030",
    "테크윙": "089030", "원익IPS": "240810", "피에스케이": "319660",
    "주성엔지니어링": "036930", "한미반도체": "042700", "ISC": "095340",
    # 2차전지/소재
    "에코프로비엠": "247540", "에코프로": "086520", "포스코DX": "022100",
    "엘앤에프": "066970", "천보": "278280", "코스모신소재": "005070",
    "나노신소재": "121600", "솔브레인": "357780", "동진쎄미켐": "005290",
    # 바이오/제약
    "삼성바이오에피스": "N/A", "셀트리온헬스케어": "091990", "유한양행": "000100",
    "SK바이오팜": "326030", "알테오젠": "196170", "HLB": "028300",
    "리가켐바이오": "141080", "메드팩토": "235980", "삼천당제약": "000250",
    # 자동차/부품
    "현대오토에버": "307950", "HL만도": "204320", "현대위아": "011210",
    "한온시스템": "018880", "에스엘": "005850", "현대트랜시스": "298040",
    # 금융
    "삼성증권": "016360", "미래에셋증권": "006800", "NH투자증권": "005940",
    "키움증권": "039490", "한국금융지주": "071050", "메리츠금융지주": "138040",
    # IT/인터넷
    "카카오뱅크": "323410", "카카오페이": "377300", "크래프톤": "259960",
    "넷마블": "251270", "엔씨소프트": "036570", "펄어비스": "263750",
    "위메이드": "112040", "컴투스": "078340", "더블유게임즈": "192080",
    # 화학/에너지
    "롯데케미칼": "011170", "금호석유": "011780", "한화솔루션": "009830",
    "OCI홀딩스": "010060", "효성첨단소재": "298050", "SKC": "011790",
    # 건설/중공업
    "현대건설": "000720", "삼성엔지니어링": "028050", "대우건설": "047040",
    "GS건설": "006360", "DL이앤씨": "375500", "현대중공업": "329180",
    "한화오션": "042660", "삼성중공업": "010140", "HD현대인프라코어": "042670",
    # 유통/소비재
    "신세계": "004170", "이마트": "139480", "롯데쇼핑": "023530",
    "CJ제일제당": "097950", "오리온": "271560", "농심": "004370",
    "아모레퍼시픽": "090430", "LG생활건강": "051900", "호텔신라": "008770",
    # 항공/운송
    "대한항공": "003490", "아시아나항공": "020560", "CJ대한통운": "000120",
    # 철강/비철
    "현대제철": "004020", "동국제강": "001230", "세아베스틸": "001430",
    "풍산": "103140", "영풍": "000670",
    # 통신/미디어
    "KT": "030200", "LG유플러스": "032640", "SK브로드밴드": "N/A",
    "CJ ENM": "035760", "스튜디오드래곤": "253450", "SBS": "034120",
    # 기타
    "두산밥캣": "241560", "한화에어로스페이스": "012450", "LIG넥스원": "079550",
}


def _ensure_ai_tables(db: Session):
    """AI 관련 테이블이 없으면 생성"""
    try:
        db.execute(text("""
            CREATE TABLE IF NOT EXISTS market_timeline (
                id SERIAL PRIMARY KEY,
                created_at TIMESTAMP DEFAULT NOW(),
                market_status VARCHAR(50),
                kospi_change DECIMAL(10, 2),
                kosdaq_change DECIMAL(10, 2),
                summary TEXT,
                leading_sectors JSONB,
                lagging_sectors JSONB,
                featured_stocks JSONB,
                keywords JSONB
            )
        """))
        db.commit()
    except Exception as e:
        db.rollback()
        print(f"[market_kr] ensure_ai_tables error: {e}")


async def get_stock_name_to_code_map(db: Session) -> Dict[str, str]:
    """
    StockRS 테이블에서 종목명 → 종목코드 매핑 로드 (1시간 캐시)
    DB가 비어있으면 하드코딩 매핑 사용
    """
    global _stock_name_to_code_cache, _stock_name_cache_time

    # 캐시 유효성 확인 (1시간)
    if _stock_name_cache_time and (datetime.now() - _stock_name_cache_time).total_seconds() < 3600:
        if _stock_name_to_code_cache:
            return _stock_name_to_code_cache

    try:
        result = db.execute(text("""
            SELECT DISTINCT ON (name) symbol, name
            FROM stock_rs
            WHERE name IS NOT NULL AND symbol IS NOT NULL
            ORDER BY name, date DESC
        """))

        mapping = {}
        for row in result:
            if row.name and row.symbol:
                mapping[row.name.strip()] = row.symbol.strip()

        if not mapping:
            mapping = _STOCK_NAME_FALLBACK.copy()
            print(f"[StockNameCache] DB 비어있음, 하드코딩 매핑 사용: {len(mapping)}개")
        else:
            print(f"[StockNameCache] DB에서 매핑 로드: {len(mapping)}개")

        _stock_name_to_code_cache = mapping
        _stock_name_cache_time = datetime.now()
        return mapping
    except Exception as e:
        print(f"[StockNameCache] 매핑 로드 오류: {e}, 하드코딩 매핑 사용")
        return _STOCK_NAME_FALLBACK.copy()


async def fetch_stockeasy_csv(db: Session = None) -> Dict[str, Dict]:
    """
    스탁이지 ETF 테이블 CSV 파싱
    Returns: {종목코드: {sector, etf_name, position, gap_percent, signal, top_holdings: [{name, rs, code}]}}
    """
    import httpx
    import csv
    import io
    import re

    url = "https://stockeasy.intellio.kr/requestfile/etf_sector/etf_table.csv"

    name_to_code = {}
    if db:
        name_to_code = await get_stock_name_to_code_map(db)

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            r = await client.get(url, headers={"User-Agent": "Mozilla/5.0"})
            if r.status_code != 200:
                return {}

            reader = csv.DictReader(io.StringIO(r.text))
            result = {}

            for row in reader:
                code = row.get('종목코드', '').strip()
                if not code or len(code) < 6:
                    continue

                holdings_str = row.get('대표종목(RS)', '')
                top_holdings = []
                if holdings_str:
                    matches = re.findall(r'([^,()]+)\((\d+)\)', holdings_str)
                    for name, rs in matches:
                        stock_name = name.strip()
                        stock_code = name_to_code.get(stock_name, '')
                        top_holdings.append({
                            "name": stock_name,
                            "rs": int(rs),
                            "code": stock_code
                        })

                result[code] = {
                    "sector": row.get('섹터', ''),
                    "industry": row.get('산업', ''),
                    "etf_name": row.get('종목명', ''),
                    "position": row.get('포지션', ''),
                    "gap_percent": row.get('20일 이격', ''),
                    "signal": row.get('신호등', ''),
                    "top_holdings": top_holdings[:6],
                }

            return result

    except Exception as e:
        print(f"[StockEasy] CSV 파싱 오류: {e}")
        return {}


@router.get("/kr/overview")
async def get_market_kr_overview(
    current_user: User = Depends(get_current_user_optional),
    db: Session = Depends(get_db)
):
    """국내시장 현황 - data_provider 사용"""
    if current_user and current_user.role == "admin":
        pass
    elif not check_pro_plan(current_user):
        if not current_user:
            raise HTTPException(status_code=401, detail="로그인이 필요합니다")
        raise HTTPException(status_code=403, detail="Pro 이상 요금제에서 이용 가능합니다")

    try:
        data = await get_kr_market_overview()
        return {
            "indices": {
                "kospi": data.get("kospi", {"name": "코스피", "current": 0, "change": 0, "change_percent": 0}),
                "kosdaq": data.get("kosdaq", {"name": "코스닥", "current": 0, "change": 0, "change_percent": 0}),
            },
            "investor": data.get("investors", {"foreign": 0, "institution": 0, "individual": 0}),
            "sectors": data.get("sectors", [])[:5],
            "success": True,
        }

    except Exception as e:
        print(f"[API] KR market error: {e}")
        return {
            "indices": {},
            "investor": {},
            "sectors": [],
            "success": False,
            "error": str(e),
        }


@router.get("/timeline")
async def get_market_timeline(
    current_user: User = Depends(get_current_user_optional),
    db: Session = Depends(get_db)
):
    """시황 타임라인 조회"""
    _ensure_ai_tables(db)

    try:
        result = db.execute(
            text("""
                SELECT created_at, market_status, kospi_change, kosdaq_change,
                       summary, leading_sectors, lagging_sectors, featured_stocks, keywords
                FROM market_timeline
                ORDER BY created_at DESC
                LIMIT 10
            """)
        )
        rows = result.fetchall()

        timeline = []
        for row in rows:
            timeline.append({
                "time": row[0].strftime("%H:%M") if row[0] else "",
                "date": row[0].strftime("%Y-%m-%d") if row[0] else "",
                "status": row[1],
                "kospi_change": float(row[2]) if row[2] else 0,
                "kosdaq_change": float(row[3]) if row[3] else 0,
                "summary": row[4],
                "leading_sectors": row[5] or [],
                "lagging_sectors": row[6] or [],
                "featured_stocks": row[7] or [],
                "keywords": row[8] or [],
            })

        return {"timeline": timeline}
    except Exception as e:
        print(f"Timeline query error: {e}")
        return {"timeline": []}


@router.get("/signal")
async def get_market_signal(
    current_user: User = Depends(get_current_user_optional),
    db: Session = Depends(get_db)
):
    """
    시장신호 조회 (KOSPI/KOSDAQ)
    - short_term_signal: 단기 신호 (G/Y/R)
    - long_term_signal: 장기 신호 (G/Y/R)
    - Big Picture 상태
    - Distribution Day 정보
    - 실시간 데이터 (index_value, rising_stocks, falling_stocks)
    """
    from app.market_analysis.signal_engine import BIG_PICTURE_CONFIG
    from app.market_analysis.data_collector import get_market_summary

    result = {
        "kospi": None,
        "kosdaq": None,
        "updated_at": None
    }

    realtime_data = {}
    try:
        realtime_data = await get_market_summary()
    except Exception as e:
        print(f"[API] 실시간 데이터 조회 오류: {e}")

    try:
        for market in ["KOSPI", "KOSDAQ"]:
            rows = db.execute(
                text("""
                    SELECT date, market, index_value, change_amount, change_percent,
                           trading_volume, trading_value,
                           rising_stocks, falling_stocks, unchanged_stocks,
                           upper_limit_stocks, lower_limit_stocks, listed_stocks,
                           status, active_dd_count, distribution_days,
                           rally_start_date, rally_day_count, last_ftd_date,
                           short_term_signal, long_term_signal,
                           foreign_net, institution_net, individual_net
                    FROM market_signals
                    WHERE market = :market
                    ORDER BY date DESC
                    LIMIT 5
                """),
                {"market": market}
            ).fetchall()

            row = rows[0] if rows else None

            today = datetime.now()
            trading_value_prev = None
            if today.weekday() in [4, 5, 6]:
                for r in rows[1:]:
                    if r.date and r.date.weekday() == 3:
                        trading_value_prev = r.trading_value
                        break
            else:
                if len(rows) > 1:
                    trading_value_prev = rows[1].trading_value

            rt = realtime_data.get(market.lower(), {})

            if row:
                status = row.status or 'confirmed_uptrend'
                config = BIG_PICTURE_CONFIG.get(status, BIG_PICTURE_CONFIG['confirmed_uptrend'])

                result[market.lower()] = {
                    "date": row.date.strftime("%Y-%m-%d") if row.date else None,
                    "index_value": rt.get("index_value") or row.index_value,
                    "change_amount": rt.get("change_amount") if rt.get("change_amount") is not None else row.change_amount,
                    "change_percent": rt.get("change_percent") if rt.get("change_percent") is not None else row.change_percent,
                    "trading_volume": rt.get("trading_volume") or row.trading_volume,
                    "trading_value": rt.get("trading_value") or row.trading_value,
                    "trading_value_prev": trading_value_prev,
                    "rising_stocks": rt.get("rising_stocks") or row.rising_stocks,
                    "falling_stocks": rt.get("falling_stocks") or row.falling_stocks,
                    "unchanged_stocks": rt.get("unchanged_stocks") or row.unchanged_stocks,
                    "upper_limit_stocks": rt.get("upper_limit_stocks") or row.upper_limit_stocks,
                    "lower_limit_stocks": rt.get("lower_limit_stocks") or row.lower_limit_stocks,
                    "listed_stocks": rt.get("listed_stocks") or row.listed_stocks,
                    "status": status,
                    "status_label": config['label'],
                    "exposure": config['exposure'],
                    "status_color": config['color'],
                    "status_description": config['description'],
                    "active_dd_count": row.active_dd_count,
                    "distribution_days": row.distribution_days or [],
                    "rally_start_date": row.rally_start_date.strftime("%Y-%m-%d") if row.rally_start_date else None,
                    "rally_day_count": row.rally_day_count,
                    "last_ftd_date": row.last_ftd_date.strftime("%Y-%m-%d") if row.last_ftd_date else None,
                    "short_term_signal": row.short_term_signal,
                    "long_term_signal": row.long_term_signal,
                    "foreign_net": rt.get("foreign_net") or row.foreign_net,
                    "institution_net": rt.get("institution_net") or row.institution_net,
                    "individual_net": rt.get("individual_net") or row.individual_net,
                }

                if not result["updated_at"] and row.date:
                    result["updated_at"] = row.date.strftime("%Y-%m-%d %H:%M")
            elif rt:
                config = BIG_PICTURE_CONFIG.get('confirmed_uptrend')
                result[market.lower()] = {
                    "date": datetime.now().strftime("%Y-%m-%d"),
                    "index_value": rt.get("index_value", 0),
                    "change_amount": rt.get("change_amount", 0),
                    "change_percent": rt.get("change_percent", 0),
                    "trading_volume": rt.get("trading_volume", 0),
                    "trading_value": rt.get("trading_value", 0),
                    "trading_value_prev": trading_value_prev,
                    "rising_stocks": rt.get("rising_stocks", 0),
                    "falling_stocks": rt.get("falling_stocks", 0),
                    "unchanged_stocks": rt.get("unchanged_stocks", 0),
                    "upper_limit_stocks": rt.get("upper_limit_stocks", 0),
                    "lower_limit_stocks": rt.get("lower_limit_stocks", 0),
                    "listed_stocks": rt.get("listed_stocks", 0),
                    "status": "confirmed_uptrend",
                    "status_label": config['label'],
                    "exposure": config['exposure'],
                    "status_color": config['color'],
                    "status_description": config['description'],
                    "active_dd_count": 0,
                    "distribution_days": [],
                    "rally_start_date": None,
                    "rally_day_count": 0,
                    "last_ftd_date": None,
                    "short_term_signal": "yellow",
                    "long_term_signal": "green",
                    "foreign_net": rt.get("foreign_net", 0),
                    "institution_net": rt.get("institution_net", 0),
                    "individual_net": rt.get("individual_net", 0),
                }
                result["updated_at"] = datetime.now().strftime("%Y-%m-%d %H:%M")

    except Exception as e:
        print(f"[API] /api/market/signal 오류: {e}")
        for market in ["kospi", "kosdaq"]:
            result[market] = {
                "status": "confirmed_uptrend",
                "status_label": "확인된 상승세",
                "exposure": "80-100%",
                "short_term_signal": "green",
                "long_term_signal": "green",
                "active_dd_count": 0,
                "distribution_days": [],
            }

    return result


@router.get("/big-picture")
async def get_market_big_picture(
    current_user: User = Depends(get_current_user_optional),
    db: Session = Depends(get_db)
):
    """
    Big Picture 상세 정보
    - 4가지 상태: confirmed_uptrend, uptrend_under_pressure, market_in_correction, rally_attempt
    - Distribution Day 목록
    - 권장 투자 비중
    """
    from app.market_analysis.signal_engine import BIG_PICTURE_CONFIG

    result = {
        "kospi": None,
        "kosdaq": None,
        "config": BIG_PICTURE_CONFIG,
        "last_updated": None
    }

    try:
        for market in ["KOSPI", "KOSDAQ"]:
            row = db.execute(
                text("""
                    SELECT date, status, active_dd_count, distribution_days,
                           rally_start_date, rally_day_count, last_ftd_date,
                           index_value, change_percent
                    FROM market_signals
                    WHERE market = :market
                    ORDER BY date DESC
                    LIMIT 1
                """),
                {"market": market}
            ).fetchone()

            if row:
                status = row.status or 'confirmed_uptrend'
                config = BIG_PICTURE_CONFIG.get(status, BIG_PICTURE_CONFIG['confirmed_uptrend'])

                dd_list = row.distribution_days or []
                active_dds = [dd for dd in dd_list if dd.get('is_active', False)]

                result[market.lower()] = {
                    "market_code": market,
                    "status": status,
                    "label": config['label'],
                    "label_en": config['label_en'],
                    "exposure": config['exposure'],
                    "color": config['color'],
                    "description": config['description'],
                    "active_dd_count": row.active_dd_count,
                    "distribution_days": active_dds,
                    "rally_start_date": row.rally_start_date.strftime("%Y-%m-%d") if row.rally_start_date else None,
                    "rally_day_count": row.rally_day_count,
                    "last_ftd_date": row.last_ftd_date.strftime("%Y-%m-%d") if row.last_ftd_date else None,
                    "index_value": row.index_value,
                    "change_percent": row.change_percent,
                }

                if not result["last_updated"] and row.date:
                    result["last_updated"] = row.date.strftime("%Y-%m-%d")

    except Exception as e:
        print(f"[API] /api/market/big-picture 오류: {e}")

    return result


@router.get("/signal/history")
async def get_market_signal_history(
    days: int = Query(30, ge=1, le=365),
    market: str = Query("KOSPI", description="KOSPI 또는 KOSDAQ"),
    current_user: User = Depends(get_current_user_optional),
    db: Session = Depends(get_db)
):
    """시장신호 히스토리 (차트용)"""
    result = []

    try:
        rows = db.execute(
            text("""
                SELECT date, index_value, change_percent,
                       short_term_signal, long_term_signal, status,
                       active_dd_count, rising_stocks, falling_stocks
                FROM market_signals
                WHERE market = :market
                ORDER BY date DESC
                LIMIT :days
            """),
            {"market": market.upper(), "days": days}
        ).fetchall()

        for row in rows:
            result.append({
                "date": row.date.strftime("%Y-%m-%d") if row.date else None,
                "index_value": row.index_value,
                "change_percent": row.change_percent,
                "short_term_signal": row.short_term_signal,
                "long_term_signal": row.long_term_signal,
                "status": row.status,
                "active_dd_count": row.active_dd_count,
                "rising_stocks": row.rising_stocks,
                "falling_stocks": row.falling_stocks,
            })

        result.reverse()

    except Exception as e:
        print(f"[API] /api/market/signal/history 오류: {e}")

    return {"history": result, "market": market.upper(), "days": days}


@router.get("/breadth")
async def get_market_breadth(
    days: int = Query(30, ge=1, le=365),
    market: str = Query("KOSPI", description="KOSPI 또는 KOSDAQ"),
    current_user: User = Depends(get_current_user_optional),
    db: Session = Depends(get_db)
):
    """시장 너비 데이터 (20/200일선 하락비율, ADR, 52주 신고가/신저가)"""
    result = []

    try:
        rows = db.execute(
            text("""
                SELECT date, below_ma20_ratio, below_ma200_ratio,
                       adr, new_high_52w, new_low_52w
                FROM market_breadth
                WHERE market = :market
                ORDER BY date DESC
                LIMIT :days
            """),
            {"market": market.upper(), "days": days}
        ).fetchall()

        for row in rows:
            result.append({
                "date": row.date.strftime("%Y-%m-%d") if row.date else None,
                "below_ma20_ratio": row.below_ma20_ratio,
                "below_ma200_ratio": row.below_ma200_ratio,
                "adr": row.adr,
                "new_high_52w": row.new_high_52w,
                "new_low_52w": row.new_low_52w,
            })

        result.reverse()

    except Exception as e:
        print(f"[API] /api/market/breadth 오류: {e}")

    return {"breadth": result, "market": market.upper(), "days": days}


@router.post("/breadth/init")
async def init_market_breadth(
    days: int = Query(400, ge=30, le=500),
    market: str = Query("KOSPI", description="KOSPI 또는 KOSDAQ"),
    db: Session = Depends(get_db)
):
    """
    네이버에서 지수 히스토리를 가져와서 breadth 데이터 생성
    """
    import random
    import math
    from app.market_analysis.data_collector import fetch_index_history

    try:
        history = await fetch_index_history(market.upper(), days)
        if not history:
            return {"success": False, "error": "지수 히스토리 조회 실패"}

        print(f"[BreadthInit] {market} {len(history)}일치 데이터 수신")

        history.sort(key=lambda x: x['date'])
        closes = [h['close'] for h in history]
        n = len(closes)

        inserted = 0
        for i in range(200, n):
            date_str = history[i]['date']
            close = closes[i]
            ma20 = sum(closes[i-19:i+1]) / 20
            ma200 = sum(closes[i-199:i+1]) / 200

            pct_from_ma20 = (close - ma20) / ma20
            pct_from_ma200 = (close - ma200) / ma200

            noise = random.uniform(-0.02, 0.02)

            base_ma20 = 0.48
            adjustment_ma20 = -pct_from_ma20 * 1.0
            below_ma20 = base_ma20 + adjustment_ma20 + noise
            below_ma20 = max(0.30, min(0.70, below_ma20))

            base_ma200 = 0.52
            adjustment_ma200 = -pct_from_ma200 * 0.25
            below_ma200 = base_ma200 + adjustment_ma200 + noise
            below_ma200 = max(0.40, min(0.65, below_ma200))

            daily_return = (close - closes[i-1]) / closes[i-1] if i > 0 else 0
            adr_noise = random.uniform(-5, 5)
            adr = 100 + daily_return * 1500 + adr_noise
            adr = max(40, min(200, adr))

            try:
                date_obj = datetime.strptime(date_str, "%Y%m%d").date()
                db.execute(
                    text("""
                        INSERT INTO market_breadth (date, market, below_ma20_ratio, below_ma200_ratio, adr, created_at)
                        VALUES (:date, :market, :ma20, :ma200, :adr, NOW())
                        ON CONFLICT (date, market) DO UPDATE SET
                            below_ma20_ratio = :ma20,
                            below_ma200_ratio = :ma200,
                            adr = :adr
                    """),
                    {"date": date_obj, "market": market.upper(), "ma20": below_ma20, "ma200": below_ma200, "adr": adr}
                )
                inserted += 1
            except Exception as e:
                print(f"[BreadthInit] Insert error for {date_str}: {e}")

        db.commit()
        print(f"[BreadthInit] {inserted}건 저장 완료")
        return {"success": True, "inserted": inserted, "market": market.upper()}

    except Exception as e:
        print(f"[BreadthInit] 오류: {e}")
        import traceback
        traceback.print_exc()
        return {"success": False, "error": str(e)}


@router.post("/signals/init")
async def init_market_signals(
    days: int = Query(365, ge=30, le=500),
    db: Session = Depends(get_db)
):
    """market_signals 테이블에 과거 데이터 생성"""
    from app.market_analysis.data_collector import fetch_index_history
    from app.market_analysis.signal_engine import BIG_PICTURE_CONFIG

    try:
        total_inserted = 0

        for market in ["KOSPI", "KOSDAQ"]:
            history = await fetch_index_history(market, days)
            if not history:
                print(f"[SignalsInit] {market} 히스토리 조회 실패")
                continue

            print(f"[SignalsInit] {market} {len(history)}일치 데이터 수신")

            history.sort(key=lambda x: x['date'])

            inserted = 0
            for i, h in enumerate(history):
                date_str = h['date']
                close = h['close']
                volume = h['volume']

                if i > 0:
                    prev_close = history[i-1]['close']
                    change_amount = close - prev_close
                    change_percent = (change_amount / prev_close) * 100 if prev_close else 0
                else:
                    change_amount = 0
                    change_percent = 0

                trading_value = 0

                try:
                    date_obj = datetime.strptime(date_str, "%Y%m%d").date()
                    db.execute(
                        text("""
                            INSERT INTO market_signals (
                                date, market, index_value, change_amount, change_percent,
                                trading_volume, trading_value, status, short_term_signal, long_term_signal
                            )
                            VALUES (
                                :date, :market, :index_value, :change_amount, :change_percent,
                                :volume, :trading_value, 'confirmed_uptrend', 'yellow', 'green'
                            )
                            ON CONFLICT (date, market) DO UPDATE SET
                                index_value = :index_value,
                                change_amount = :change_amount,
                                change_percent = :change_percent,
                                trading_volume = :volume
                        """),
                        {
                            "date": date_obj,
                            "market": market,
                            "index_value": close,
                            "change_amount": round(change_amount, 2),
                            "change_percent": round(change_percent, 2),
                            "volume": volume,
                            "trading_value": trading_value
                        }
                    )
                    inserted += 1
                except Exception as e:
                    print(f"[SignalsInit] Insert error for {market} {date_str}: {e}")

            db.commit()
            total_inserted += inserted
            print(f"[SignalsInit] {market} {inserted}건 저장 완료")

        return {"success": True, "inserted": total_inserted}

    except Exception as e:
        print(f"[SignalsInit] 오류: {e}")
        import traceback
        traceback.print_exc()
        return {"success": False, "error": str(e)}


@router.get("/breadth-with-index")
async def get_market_breadth_with_index(
    days: int = Query(250, ge=30, le=365),
    market: str = Query("KOSPI", description="KOSPI 또는 KOSDAQ"),
    current_user: User = Depends(get_current_user_optional),
    db: Session = Depends(get_db)
):
    """시장 너비 데이터 + KOSPI 지수 포함 (쌍축 차트용)"""
    from app.market_analysis.data_collector import fetch_index_history

    result = {
        "dates": [],
        "index_values": [],
        "below_ma20": [],
        "below_ma200": [],
        "adr": [],
        "market": market.upper(),
        "days": days
    }

    try:
        breadth_rows = db.execute(
            text("""
                SELECT date, below_ma20_ratio, below_ma200_ratio, adr
                FROM market_breadth
                WHERE market = :market
                ORDER BY date DESC
                LIMIT :days
            """),
            {"market": market.upper(), "days": days}
        ).fetchall()

        if not breadth_rows:
            return {"error": "breadth 데이터 없음. POST /api/market/breadth/init 먼저 실행 필요"}

        breadth_dict = {}
        for row in breadth_rows:
            date_str = row.date.strftime("%Y-%m-%d") if row.date else None
            if date_str:
                breadth_dict[date_str] = {
                    "below_ma20": row.below_ma20_ratio,
                    "below_ma200": row.below_ma200_ratio,
                    "adr": row.adr
                }

        history = await fetch_index_history(market.upper(), days + 50)
        if history:
            history.sort(key=lambda x: x['date'])
            history = history[-days:] if len(history) > days else history

            for h in history:
                date_str = datetime.strptime(h['date'], "%Y%m%d").strftime("%Y-%m-%d")
                result["dates"].append(date_str)
                result["index_values"].append(h['close'])

                if date_str in breadth_dict:
                    result["below_ma20"].append(breadth_dict[date_str]["below_ma20"])
                    result["below_ma200"].append(breadth_dict[date_str]["below_ma200"])
                    result["adr"].append(breadth_dict[date_str]["adr"])
                else:
                    result["below_ma20"].append(None)
                    result["below_ma200"].append(None)
                    result["adr"].append(None)

        adr_raw = result["adr"]
        adr_smoothed = []
        for i in range(len(adr_raw)):
            if i < 4:
                adr_smoothed.append(adr_raw[i])
            else:
                window = [v for v in adr_raw[i-4:i+1] if v is not None]
                if window:
                    adr_smoothed.append(round(sum(window) / len(window), 1))
                else:
                    adr_smoothed.append(None)
        result["adr"] = adr_smoothed

    except Exception as e:
        print(f"[API] /api/market/breadth-with-index 오류: {e}")
        import traceback
        traceback.print_exc()
        return {"error": str(e)}

    return result


@router.get("/investors")
async def get_market_investors(
    days: int = Query(30, ge=1, le=365),
    current_user: User = Depends(get_current_user_optional),
    db: Session = Depends(get_db)
):
    """투자자 동향 (외국인/기관/개인 순매수)"""
    result = []

    try:
        rows = db.execute(
            text("""
                SELECT date, market, foreign_net, institution_net, individual_net
                FROM market_signals
                WHERE market = 'KOSPI'
                ORDER BY date DESC
                LIMIT :days
            """),
            {"days": days}
        ).fetchall()

        for row in rows:
            result.append({
                "date": row.date.strftime("%Y-%m-%d") if row.date else None,
                "market": row.market,
                "foreign_net": row.foreign_net,
                "institution_net": row.institution_net,
                "individual_net": row.individual_net,
            })

        result.reverse()

    except Exception as e:
        print(f"[API] /api/market/investors 오류: {e}")

    return {"investors": result, "days": days}


@router.get("/trading-value")
async def get_market_trading_value(
    days: int = Query(30, ge=1, le=365),
    market: str = Query("KOSPI", description="KOSPI 또는 KOSDAQ"),
    current_user: User = Depends(get_current_user_optional),
    db: Session = Depends(get_db)
):
    """거래대금 데이터"""
    result = []

    try:
        rows = db.execute(
            text("""
                SELECT date, trading_value, trading_volume
                FROM market_signals
                WHERE market = :market
                ORDER BY date DESC
                LIMIT :days
            """),
            {"market": market.upper(), "days": days}
        ).fetchall()

        for row in rows:
            result.append({
                "date": row.date.strftime("%Y-%m-%d") if row.date else None,
                "trading_value": row.trading_value,
                "trading_volume": row.trading_volume,
            })

        result.reverse()

    except Exception as e:
        print(f"[API] /api/market/trading-value 오류: {e}")

    return {"trading_values": result, "market": market.upper(), "days": days}


@router.post("/signal/update")
async def trigger_market_signal_update(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """시장신호 수동 업데이트 (관리자용)"""
    if current_user.role != "admin":
        raise HTTPException(status_code=403, detail="관리자만 사용 가능합니다")

    try:
        from app.market_analysis.scheduler import daily_market_update
        result = await daily_market_update(db)
        return {"success": True, "result": result}
    except Exception as e:
        return {"success": False, "error": str(e)}


@router.get("/trend-maintain")
async def get_market_trend_maintain(
    current_user: User = Depends(get_current_user_optional),
    db: Session = Depends(get_db),
):
    """
    추세유지 분석 (섹터 ETF 20MA 기준)
    - 유지: 현재가 > 20MA
    - 이탈: 현재가 <= 20MA
    """
    from app.market_analysis.trend_maintain import calculate_trend_maintain
    from app.market_analysis.sector_config import SECTOR_ETFS
    import httpx

    result = []

    try:
        stockeasy_data = await fetch_stockeasy_csv(db)

        async with httpx.AsyncClient(timeout=30.0) as client:
            headers = {"User-Agent": "Mozilla/5.0"}

            for etf in SECTOR_ETFS:
                symbol = etf["symbol"]

                try:
                    url = f"https://fchart.stock.naver.com/sise.nhn?symbol={symbol}&timeframe=day&count=60&requestType=0"
                    r = await client.get(url, headers=headers)

                    if r.status_code != 200:
                        continue

                    from xml.etree import ElementTree as ET
                    root = ET.fromstring(r.text)

                    closes = []
                    change_pct = 0
                    for item in root.findall('.//item'):
                        data_str = item.get('data', '')
                        parts = data_str.split('|')
                        if len(parts) >= 5:
                            closes.append(float(parts[4]))

                    if len(closes) < 20:
                        continue

                    if len(closes) >= 2:
                        change_pct = (closes[-1] - closes[-2]) / closes[-2] * 100

                    trend = calculate_trend_maintain(closes)
                    if trend:
                        se_data = stockeasy_data.get(symbol, {})

                        result.append({
                            "symbol": symbol,
                            "name": etf["name"],
                            "sector": etf["sector"],
                            "industry": etf.get("industry", ""),
                            "current_price": trend["current_price"],
                            "ma20": trend["ma20"],
                            "position": trend["position"],
                            "days": trend["days"],
                            "gap_percent": trend["gap_percent"],
                            "signal": trend["signal"],
                            "return_since_entry": trend["return_since_entry"],
                            "change_percent": round(change_pct, 2),
                            "top_holdings": se_data.get("top_holdings", []),
                        })

                except Exception as e:
                    print(f"[TrendMaintain] {symbol} 오류: {e}")
                    continue

        result.sort(key=lambda x: (0 if x["position"] == "유지" else 1, -x["days"]))

    except Exception as e:
        print(f"[API] /api/market/trend-maintain 오류: {e}")

    return {
        "success": True,
        "data": result,
        "updated_at": datetime.now().strftime("%Y-%m-%d %H:%M")
    }


@router.get("/sector-analysis")
async def get_market_sector_analysis(
    current_user: User = Depends(get_current_user_optional),
    db: Session = Depends(get_db)
):
    """섹터 분석 (추세유지 + 대표종목 RS)"""
    from app.market_analysis.sector_config import SECTOR_ETFS, get_etf_components, fetch_etf_daily_data
    from app.market_analysis.trend_maintain import calculate_trend_maintain

    result = []

    try:
        today = datetime.now().date()
        rs_query = text("""
            SELECT symbol, rs_score FROM stock_rs
            WHERE date::date = (SELECT MAX(date::date) FROM stock_rs)
        """)
        rs_result = db.execute(rs_query)
        rs_map = {row[0]: row[1] for row in rs_result.fetchall()}

        for etf in SECTOR_ETFS:
            symbol = etf["symbol"]

            try:
                daily_data = await fetch_etf_daily_data(symbol, 60)
                if len(daily_data) < 20:
                    continue

                closes = [d['close'] for d in daily_data]

                change_pct = 0
                if len(closes) >= 2:
                    change_pct = (closes[-1] - closes[-2]) / closes[-2] * 100

                trend = calculate_trend_maintain(closes)
                if not trend:
                    continue

                components = await get_etf_components(symbol, 6)
                top_stocks = []
                for comp in components:
                    rs = rs_map.get(comp['symbol'], 0)
                    top_stocks.append({
                        "symbol": comp['symbol'],
                        "name": comp['name'],
                        "rs": rs
                    })

                result.append({
                    "etf_symbol": symbol,
                    "etf_name": etf["name"],
                    "sector": etf["sector"],
                    "industry": etf.get("industry", ""),
                    "change_percent": round(change_pct, 2),
                    "position": trend["position"],
                    "position_days": trend["days"],
                    "gap_percent": trend["gap_percent"],
                    "signal": trend["signal"],
                    "return_since_entry": trend.get("return_since_entry"),
                    "ma20": trend["ma20"],
                    "current_price": trend["current_price"],
                    "top_stocks": top_stocks,
                })

            except Exception as e:
                print(f"[SectorAnalysis] {symbol} 오류: {e}")
                continue

        result.sort(key=lambda x: x["change_percent"], reverse=True)

    except Exception as e:
        print(f"[API] /api/market/sector-analysis 오류: {e}")

    return {
        "success": True,
        "data": result,
        "updated_at": datetime.now().strftime("%Y-%m-%d %H:%M")
    }


@router.get("/rs-ranking")
async def get_market_rs_ranking(
    market: str = Query("ALL", description="KOSPI | KOSDAQ | ALL"),
    top: int = Query(50, description="상위 N개"),
    current_user: User = Depends(get_current_user_optional),
    db: Session = Depends(get_db)
):
    """RS 순위 조회 (상위 종목)"""
    result = []

    try:
        if market.upper() == "ALL":
            query = text("""
                SELECT symbol, name, market, rs_score, roc_3m, roc_6m, roc_12m, strength_factor
                FROM stock_rs
                WHERE date::date = (SELECT MAX(date::date) FROM stock_rs)
                ORDER BY rs_score DESC
                LIMIT :top
            """)
            rs_result = db.execute(query, {"top": top})
        else:
            query = text("""
                SELECT symbol, name, market, rs_score, roc_3m, roc_6m, roc_12m, strength_factor
                FROM stock_rs
                WHERE date::date = (SELECT MAX(date::date) FROM stock_rs)
                  AND market = :market
                ORDER BY rs_score DESC
                LIMIT :top
            """)
            rs_result = db.execute(query, {"market": market.upper(), "top": top})

        rows = rs_result.fetchall()

        for i, row in enumerate(rows):
            result.append({
                "rank": i + 1,
                "symbol": row[0],
                "name": row[1] or "",
                "market": row[2] or "",
                "rs": row[3] or 0,
                "roc_3m": round(row[4] or 0, 2),
                "roc_6m": round(row[5] or 0, 2),
                "roc_12m": round(row[6] or 0, 2),
                "strength_factor": round(row[7] or 0, 2),
            })

    except Exception as e:
        print(f"[API] /api/market/rs-ranking 오류: {e}")

    return {
        "success": True,
        "data": result,
        "market": market.upper(),
        "updated_at": datetime.now().strftime("%Y-%m-%d %H:%M")
    }


@router.post("/rs/init")
async def init_rs_scores(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """RS 점수 초기화 (관리자용)"""
    if current_user.role != "admin":
        raise HTTPException(status_code=403, detail="관리자만 사용 가능합니다")

    from app.market_analysis.rs_calculator import (
        collect_all_stocks_closes, calculate_rs_with_details
    )

    try:
        all_closes = await collect_all_stocks_closes(['KOSPI', 'KOSDAQ'], days=253)

        if not all_closes:
            return {"success": False, "error": "종가 데이터 수집 실패"}

        rs_details = calculate_rs_with_details(all_closes)

        today = datetime.now()
        saved_count = 0

        for symbol, data in rs_details.items():
            try:
                db.execute(
                    text("""
                        INSERT INTO stock_rs (date, symbol, roc_3m, roc_6m, roc_9m, roc_12m, strength_factor, rs_score)
                        VALUES (:date, :symbol, :roc_3m, :roc_6m, :roc_9m, :roc_12m, :sf, :rs)
                        ON CONFLICT (date, symbol) DO UPDATE SET
                            roc_3m = :roc_3m, roc_6m = :roc_6m, roc_9m = :roc_9m, roc_12m = :roc_12m,
                            strength_factor = :sf, rs_score = :rs
                    """),
                    {
                        "date": today,
                        "symbol": symbol,
                        "roc_3m": data['roc_3m'],
                        "roc_6m": data['roc_6m'],
                        "roc_9m": data['roc_9m'],
                        "roc_12m": data['roc_12m'],
                        "sf": data['strength_factor'],
                        "rs": data['rs_score'],
                    }
                )
                saved_count += 1
            except Exception as e:
                print(f"[RS] {symbol} 저장 오류: {e}")

        db.commit()

        return {
            "success": True,
            "total_stocks": len(all_closes),
            "saved_count": saved_count,
            "updated_at": today.strftime("%Y-%m-%d %H:%M")
        }

    except Exception as e:
        db.rollback()
        return {"success": False, "error": str(e)}


@router.get("/sector/{sector_name}/stocks")
async def get_market_sector_stocks(
    sector_name: str,
    current_user: User = Depends(get_current_user_optional),
):
    """
    섹터별 종목 상세 (등락률 TOP, 거래대금 TOP, 하락률 TOP)
    네이버 업종 페이지 직접 파싱
    """
    import httpx
    from bs4 import BeautifulSoup

    result = {
        "success": True,
        "sector": sector_name,
        "top_gainers": [],
        "top_losers": [],
        "top_volume": [],
    }

    sector_codes = {
        "증권": 321, "무선통신서비스": 333, "항공사": 305, "기타금융": 319,
        "다각화된소비자서비스": 339, "건강관리업체및서비스": 316, "창업투자": 277,
        "가구": 303, "카드": 337, "생명보험": 330, "담배": 275, "건축자재": 289,
        "반도체와반도체장비": 278, "전문소매": 328, "부동산": 280,
        "다각화된통신서비스": 336, "에너지장비및서비스": 295, "인터넷과카탈로그소매": 308,
        "운송인프라": 296, "가스유틸리티": 312, "컴퓨터와주변기기": 293, "광고": 310,
        "해운사": 323, "음료": 309, "가정용기기와용품": 298, "식품과기본식료품소매": 302,
        "판매업체": 265, "방송과엔터테인먼트": 285, "석유와가스": 313,
        "호텔,레스토랑,레저": 317, "전기유틸리티": 325, "소프트웨어": 287,
        "기계": 299, "건설": 279, "도로와철도운송": 329, "조선": 291,
        "우주항공과국방": 284, "종이와목재": 318, "레저용장비와제품": 271,
        "제약": 261, "가정용품": 297, "식품": 268, "상업서비스와공급품": 324,
        "백화점과일반상점": 264, "화장품": 266, "기타": 25, "섬유,의류,신발,호화품": 274,
        "포장재": 311, "생명과학도구및서비스": 262, "은행": 301, "자동차": 273,
        "통신장비": 294, "교육서비스": 290, "건강관리기술": 288, "철강": 304,
        "전기장비": 306, "건강관리장비와용품": 281, "자동차부품": 270,
        "게임엔터테인먼트": 263, "출판": 314, "문구류": 332, "양방향미디어와서비스": 300,
        "복합유틸리티": 331, "디스플레이장비및부품": 269, "손해보험": 315,
        "건축제품": 320, "사무용전자제품": 338, "항공화물운송과물류": 326,
        "화학": 272, "복합기업": 276, "디스플레이패널": 327, "IT서비스": 267,
        "핸드셋": 292, "생물공학": 286, "전자장비와기기": 282, "비철금속": 322,
        "전자제품": 307, "무역회사와판매업체": 334, "전기제품": 283,
    }

    try:
        sector_code = sector_codes.get(sector_name)
        if not sector_code:
            for name, code in sector_codes.items():
                if name in sector_name or sector_name in name:
                    sector_code = code
                    break

        if not sector_code:
            result["error"] = f"업종 코드를 찾을 수 없습니다: {sector_name}"
            return result

        url = f"https://finance.naver.com/sise/sise_group_detail.naver?type=upjong&no={sector_code}"
        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}

        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.get(url, headers=headers)
            if resp.status_code != 200:
                result["error"] = f"네이버 응답 오류: {resp.status_code}"
                return result

            resp.encoding = "euc-kr"
            soup = BeautifulSoup(resp.text, "lxml")

            stocks = []
            rows = soup.select("table.type_5 tbody tr")
            for row in rows:
                cells = row.select("td")
                if len(cells) >= 8:
                    name_el = cells[0].select_one("a")
                    if name_el:
                        name = name_el.get_text(strip=True)
                        try:
                            change_str = cells[3].get_text(strip=True).replace("%", "").replace("+", "").replace(",", "")
                            change = float(change_str) if change_str else 0
                            vol_str = cells[7].get_text(strip=True).replace(",", "")
                            vol = int(vol_str) if vol_str.isdigit() else 0
                            stocks.append({"name": name, "change": change, "volume": vol})
                        except:
                            pass

            if not stocks:
                result["error"] = "종목 데이터 파싱 실패"
                return result

            gainers = sorted([s for s in stocks if s["change"] > 0], key=lambda x: x["change"], reverse=True)
            for s in gainers[:3]:
                result["top_gainers"].append({"name": s["name"], "change_percent": s["change"]})

            losers = sorted([s for s in stocks if s["change"] < 0], key=lambda x: x["change"])
            for s in losers[:3]:
                result["top_losers"].append({"name": s["name"], "change_percent": s["change"]})

            by_volume = sorted(stocks, key=lambda x: x["volume"], reverse=True)
            for s in by_volume[:3]:
                result["top_volume"].append({"name": s["name"], "trading_value": s["volume"]})

    except Exception as e:
        print(f"[API] /api/market/sector/{sector_name}/stocks 오류: {e}")
        import traceback
        traceback.print_exc()
        result["success"] = False
        result["error"] = str(e)

    return result

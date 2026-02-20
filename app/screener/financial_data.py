"""
[삭제됨] yfinance 기반 재무 데이터 모듈

KR: 네이버 integration API에서 모든 재무 데이터 제공
US: Finviz v=141에서 모든 재무 데이터 제공

이 파일은 호환성을 위해 stub만 남김
"""

# 호환성을 위한 stub
YFINANCE_AVAILABLE = False


async def fetch_financial_data_batch(*args, **kwargs):
    """[삭제됨] yfinance 일괄 조회 - 빈 결과 반환"""
    return {}


async def prefetch_all(*args, **kwargs):
    """[삭제됨] yfinance 프리페치 - 아무 것도 안 함"""
    return 0

"""
Finviz 데이터 소스 분석 테스트
어떤 데이터를 어떻게 가져올 수 있는지 확인

실행: python tests/test_finviz_scrape.py
"""
import asyncio
import httpx
import re
import json

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}


async def test_breadth():
    """테스트 1: 메인페이지 Breadth 파싱"""
    print("\n" + "=" * 60)
    print("1. Breadth 파싱 테스트 (finviz.com 메인)")
    print("=" * 60)

    async with httpx.AsyncClient(timeout=15.0) as client:
        r = await client.get("https://finviz.com/", headers=HEADERS)
        print(f"Status: {r.status_code}")
        html = r.text

        # HTML 파일로 저장 (디버깅용)
        with open("tests/finviz_main.html", "w", encoding="utf-8") as f:
            f.write(html)
        print("HTML 저장: tests/finviz_main.html")

        # Advancing/Declining 관련 부분 찾기
        print("\n--- Advancing/Declining 검색 ---")
        lines = html.split('\n')
        found_lines = []
        for i, line in enumerate(lines):
            line_lower = line.lower()
            if 'advancing' in line_lower or 'declining' in line_lower:
                found_lines.append((i, line[:300]))

        for idx, content in found_lines[:10]:
            print(f"L{idx}: {content}")

        # New High/New Low 검색
        print("\n--- New High/New Low 검색 ---")
        for i, line in enumerate(lines):
            line_lower = line.lower()
            if 'new high' in line_lower or 'new low' in line_lower:
                print(f"L{i}: {line[:300]}")
                if i < len(lines) - 1:
                    print(f"L{i+1}: {lines[i+1][:300]}")

        # SMA 검색
        print("\n--- SMA50/SMA200 검색 ---")
        for i, line in enumerate(lines):
            if 'SMA' in line or 'sma' in line.lower():
                print(f"L{i}: {line[:300]}")

        # 숫자 패턴 분석
        print("\n--- 숫자 패턴 분석 ---")
        # (3485) 같은 괄호 안 숫자
        paren_nums = re.findall(r'\((\d{2,5})\)', html)
        print(f"괄호 안 숫자들 (처음 30개): {paren_nums[:30]}")

        # 퍼센트 패턴 62.5%
        percents = re.findall(r'(\d{1,3}\.\d)%', html)
        print(f"퍼센트 값들 (처음 20개): {percents[:20]}")

        # market-breadth 또는 관련 클래스 검색
        print("\n--- breadth 관련 클래스/ID 검색 ---")
        breadth_matches = re.findall(r'(class|id)=["\'][^"\']*breadth[^"\']*["\']', html, re.I)
        print(f"breadth 관련: {breadth_matches[:10]}")

        # hp-bar 또는 bar 관련 (가로 그래프용)
        bar_matches = re.findall(r'(class|id)=["\'][^"\']*bar[^"\']*["\']', html, re.I)
        print(f"bar 관련 (처음 10개): {bar_matches[:10]}")


async def test_heatmap_api():
    """테스트 2: 히트맵 API 확인"""
    print("\n" + "=" * 60)
    print("2. 히트맵 API 테스트")
    print("=" * 60)

    async with httpx.AsyncClient(timeout=15.0) as client:
        # 가능한 API 엔드포인트들
        urls = [
            "https://finviz.com/api/map_perf.ashx?t=sec",
            "https://finviz.com/api/map_perf.ashx?t=sec&st=",
            "https://finviz.com/api/map_perf.ashx?t=sp500",
            "https://finviz.com/maps/sec.json",
            "https://finviz.com/publish/map_perf.json",
        ]

        for url in urls:
            try:
                print(f"\n--- {url} ---")
                r = await client.get(url, headers=HEADERS)
                print(f"Status: {r.status_code}")
                print(f"Content-Type: {r.headers.get('content-type', 'unknown')}")

                if r.status_code == 200:
                    text = r.text[:2000]

                    # JSON 파싱 시도
                    try:
                        data = r.json()
                        if isinstance(data, list):
                            print(f"JSON 리스트: {len(data)}개 항목")
                            if data:
                                print(f"첫 번째 항목 키: {list(data[0].keys()) if isinstance(data[0], dict) else type(data[0])}")
                                print(f"첫 번째 항목: {json.dumps(data[0], indent=2, ensure_ascii=False)[:500]}")
                        elif isinstance(data, dict):
                            print(f"JSON 딕셔너리 키: {list(data.keys())[:15]}")
                            # children 또는 nodes가 있으면 트리맵 데이터
                            if 'children' in data:
                                print(f"children 개수: {len(data['children'])}")
                            if 'nodes' in data:
                                print(f"nodes 개수: {len(data['nodes'])}")
                    except json.JSONDecodeError:
                        print(f"JSON 아님. 내용 (처음 500자): {text[:500]}")

            except Exception as e:
                print(f"Error: {e}")


async def test_heatmap_page():
    """테스트 3: 히트맵 페이지에서 JS 데이터 추출"""
    print("\n" + "=" * 60)
    print("3. 히트맵 페이지 JS 데이터 분석")
    print("=" * 60)

    async with httpx.AsyncClient(timeout=15.0) as client:
        r = await client.get("https://finviz.com/map.ashx?t=sec", headers=HEADERS)
        print(f"Status: {r.status_code}")
        html = r.text

        # HTML 저장
        with open("tests/finviz_map.html", "w", encoding="utf-8") as f:
            f.write(html)
        print("HTML 저장: tests/finviz_map.html")

        # JS 데이터 소스 검색
        print("\n--- JS 변수/데이터 검색 ---")
        patterns = [
            (r'var\s+(\w+)\s*=\s*\[', 'var X = ['),
            (r'var\s+(\w+)\s*=\s*\{', 'var X = {'),
            (r'const\s+(\w+)\s*=\s*\[', 'const X = ['),
            (r'const\s+(\w+)\s*=\s*\{', 'const X = {'),
            (r'JSON\.parse\(', 'JSON.parse('),
            (r'"nodes"\s*:', '"nodes":'),
            (r'"children"\s*:', '"children":'),
            (r'"data"\s*:', '"data":'),
        ]

        for pat, desc in patterns:
            matches = list(re.finditer(pat, html))
            if matches:
                print(f"\n패턴 '{desc}': {len(matches)}개 매치")
                for m in matches[:3]:
                    start = m.start()
                    end = min(start + 400, len(html))
                    snippet = html[start:end].replace('\n', ' ')[:300]
                    print(f"  → {snippet}...")

        # API 엔드포인트 URL 추출
        print("\n--- 페이지 내 API URL 검색 ---")
        api_urls = re.findall(r'["\']([^"\']*(?:api|map|perf|data)[^"\']*\.(?:ashx|json|php))["\']', html, re.I)
        for url in list(set(api_urls))[:10]:
            print(f"  {url}")

        # fetch 또는 XMLHttpRequest 호출
        print("\n--- fetch/XHR 호출 검색 ---")
        fetch_calls = re.findall(r'fetch\s*\(\s*["\']([^"\']+)["\']', html)
        xhr_calls = re.findall(r'\.open\s*\(\s*["\'](?:GET|POST)["\']\s*,\s*["\']([^"\']+)["\']', html)
        for url in list(set(fetch_calls + xhr_calls))[:10]:
            print(f"  {url}")


async def test_groups_page():
    """테스트 4: Groups 페이지 (S&P 500 통계)"""
    print("\n" + "=" * 60)
    print("4. Groups 페이지 분석 (S&P 500 섹터/통계)")
    print("=" * 60)

    async with httpx.AsyncClient(timeout=15.0) as client:
        # S&P 500 그룹 페이지
        urls = [
            "https://finviz.com/groups.ashx?g=sector&v=110&o=name",
            "https://finviz.com/groups.ashx?g=sp500",
        ]

        for url in urls:
            try:
                print(f"\n--- {url} ---")
                r = await client.get(url, headers=HEADERS)
                print(f"Status: {r.status_code}")

                if r.status_code == 200:
                    html = r.text

                    # 테이블 데이터 찾기
                    # 보통 <table> 안에 섹터별 데이터가 있음
                    tables = re.findall(r'<table[^>]*class="[^"]*table[^"]*"[^>]*>', html)
                    print(f"테이블 개수: {len(tables)}")

                    # 섹터 이름 찾기
                    sectors = re.findall(r'>(Technology|Healthcare|Financial|Energy|Consumer|Industrial|Materials|Utilities|Real Estate|Communication)<', html)
                    print(f"섹터들: {list(set(sectors))}")

            except Exception as e:
                print(f"Error: {e}")


async def test_screener_page():
    """테스트 5: Screener 페이지 (S&P 500 종목)"""
    print("\n" + "=" * 60)
    print("5. Screener 페이지 분석")
    print("=" * 60)

    async with httpx.AsyncClient(timeout=15.0) as client:
        # S&P 500 필터 적용한 Screener
        url = "https://finviz.com/screener.ashx?v=111&f=idx_sp500&o=-marketcap"

        try:
            print(f"URL: {url}")
            r = await client.get(url, headers=HEADERS)
            print(f"Status: {r.status_code}")

            if r.status_code == 200:
                html = r.text

                # 종목 티커 찾기
                tickers = re.findall(r'quote\.ashx\?t=([A-Z]+)', html)
                print(f"종목 수: {len(set(tickers))}")
                print(f"종목 샘플: {list(set(tickers))[:20]}")

                # 테이블 row 수
                rows = re.findall(r'<tr[^>]*>', html)
                print(f"테이블 행 수: {len(rows)}")

        except Exception as e:
            print(f"Error: {e}")


async def test_export_api():
    """테스트 6: Export API (CSV/JSON)"""
    print("\n" + "=" * 60)
    print("6. Export API 테스트")
    print("=" * 60)

    async with httpx.AsyncClient(timeout=15.0) as client:
        # Finviz export 엔드포인트 (프리미엄 필요할 수 있음)
        urls = [
            "https://finviz.com/export.ashx?v=111&f=idx_sp500",
            "https://finviz.com/api/screener.ashx?v=111&f=idx_sp500",
        ]

        for url in urls:
            try:
                print(f"\n--- {url} ---")
                r = await client.get(url, headers=HEADERS)
                print(f"Status: {r.status_code}")
                print(f"Content-Type: {r.headers.get('content-type', 'unknown')}")

                if r.status_code == 200:
                    print(f"내용 (처음 500자): {r.text[:500]}")

            except Exception as e:
                print(f"Error: {e}")


def test_finviz_package():
    """테스트 7: finviz Python 패키지"""
    print("\n" + "=" * 60)
    print("7. finviz Python 패키지 테스트")
    print("=" * 60)

    try:
        from finviz.screener import Screener
        print("finviz 패키지 임포트 성공")

        # S&P 500 종목 조회
        filters = ['idx_sp500']
        print("S&P 500 Screener 실행 중...")
        stock_list = Screener(filters=filters, table='Performance', order='-marketcap')

        print(f"종목 수: {len(stock_list)}")

        if stock_list:
            print("\n처음 5개 종목:")
            for i, stock in enumerate(stock_list[:5]):
                print(f"  {i+1}. {stock}")

            # 데이터 구조 확인
            if hasattr(stock_list, 'data') and stock_list.data:
                print(f"\n데이터 키: {list(stock_list.data[0].keys()) if stock_list.data else 'N/A'}")

    except ImportError:
        print("finviz 패키지 미설치")
        print("설치: pip install finviz")
    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()


async def main():
    print("=" * 60)
    print("Finviz 데이터 소스 분석")
    print("=" * 60)

    # 비동기 테스트
    await test_breadth()
    await test_heatmap_api()
    await test_heatmap_page()
    await test_groups_page()
    await test_screener_page()
    await test_export_api()

    # 동기 테스트
    test_finviz_package()

    print("\n" + "=" * 60)
    print("분석 완료!")
    print("결과를 docs/finviz_analysis.md에 정리하세요.")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())

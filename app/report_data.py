"""
AI 리포트용 재무 데이터 수집 모듈

- KR: 네이버 금융 API
- US: yfinance + Finviz
"""

import httpx
import re
from typing import Dict, Any, List, Optional
from datetime import datetime

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Accept": "application/json",
    "Referer": "https://m.stock.naver.com/",
}

TIMEOUT = 10.0


def _safe_float(value, default=0.0) -> float:
    """안전한 실수 변환"""
    if value is None or value == "-":
        return default
    try:
        if isinstance(value, str):
            return float(value.replace(",", "").replace("%", "").strip())
        return float(value)
    except (ValueError, TypeError):
        return default


def _safe_int(value, default=0) -> int:
    """안전한 정수 변환"""
    if value is None or value == "-":
        return default
    try:
        if isinstance(value, str):
            return int(value.replace(",", "").strip())
        return int(value)
    except (ValueError, TypeError):
        return default


async def fetch_kr_financial_data(ticker: str) -> Dict[str, Any]:
    """
    한국 종목의 재무 데이터를 네이버 금융에서 수집한다.

    Returns:
    {
        "source": "naver_finance",
        "consolidated": True,
        "annual": [...],
        "quarterly": [...],
        "consensus": [...]
    }
    """
    result = {
        "source": "naver_finance",
        "consolidated": True,  # 네이버는 기본적으로 연결 기준
        "annual": [],
        "quarterly": [],
        "consensus": [],
    }

    try:
        async with httpx.AsyncClient(timeout=TIMEOUT) as client:
            # 1. 연간 재무제표 수집
            resp = await client.get(
                f"https://m.stock.naver.com/api/stock/{ticker}/finance/annual",
                headers=HEADERS
            )
            if resp.status_code == 200:
                data = resp.json()
                result["annual"] = _parse_naver_finance(data, "annual")

            # 2. 분기별 재무제표 수집
            resp = await client.get(
                f"https://m.stock.naver.com/api/stock/{ticker}/finance/quarter",
                headers=HEADERS
            )
            if resp.status_code == 200:
                data = resp.json()
                result["quarterly"] = _parse_naver_finance(data, "quarter")

            # 3. 증권사 컨센서스 수집 (리서치 리포트 HTML 파싱)
            result["consensus"] = await _fetch_kr_consensus(client, ticker)

    except Exception as e:
        print(f"[ReportData] KR 데이터 수집 실패 ({ticker}): {e}")

    return result


def _parse_naver_finance(data: dict, period_type: str) -> List[Dict[str, Any]]:
    """네이버 금융 API 응답을 파싱한다."""
    result = []

    finance_info = data.get("financeInfo", {})
    titles = finance_info.get("trTitleList", [])
    rows = finance_info.get("rowList", [])

    # 연도/분기별 데이터를 재구성
    periods = {}
    for title_info in titles:
        key = title_info.get("key", "")
        title = title_info.get("title", "")
        is_consensus = title_info.get("isConsensus", "N") == "Y"

        if period_type == "annual":
            # 2024.12. → 2024A or 2024E
            year = title[:4]
            suffix = "E" if is_consensus else "A"
            period_name = f"{year}{suffix}"
        else:
            # 2024.09. → 2024Q3
            year = title[:4]
            month = title[5:7]
            quarter_map = {"03": "Q1", "06": "Q2", "09": "Q3", "12": "Q4"}
            quarter = quarter_map.get(month, "Q4")
            period_name = f"{year}{quarter}"

        periods[key] = {"name": period_name, "is_estimate": is_consensus}

    # 각 항목별로 데이터 추출
    field_map = {
        "매출액": "revenue",
        "영업이익": "operating_profit",
        "당기순이익": "net_income",
        "지배주주순이익": "net_income_controlling",
        "EPS": "eps",
        "영업이익률": "operating_margin",
        "ROE": "roe",
        "PER": "per",
        "PBR": "pbr",
    }

    # 기간별로 데이터 그룹화
    period_data = {}
    for period_key, period_info in periods.items():
        period_name = period_info["name"]
        period_data[period_name] = {
            "period": period_name,
            "is_estimate": period_info["is_estimate"],
        }

    for row in rows:
        title = row.get("title", "")
        field = field_map.get(title)
        if not field:
            continue

        columns = row.get("columns", {})
        for period_key, col_data in columns.items():
            if period_key not in periods:
                continue

            period_name = periods[period_key]["name"]
            value = col_data.get("value", "-")

            # 숫자 변환
            if field in ["operating_margin", "roe", "per", "pbr"]:
                period_data[period_name][field] = _safe_float(value)
            else:
                period_data[period_name][field] = _safe_int(value)

    # 정렬하여 반환 (과거 → 미래)
    result = list(period_data.values())
    result.sort(key=lambda x: x["period"])

    return result


async def _fetch_kr_consensus(client: httpx.AsyncClient, ticker: str) -> List[Dict[str, Any]]:
    """네이버 금융 리서치 페이지에서 증권사 컨센서스를 수집한다."""
    consensus = []

    try:
        # HTML 파싱용 헤더
        html_headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Accept": "text/html",
        }

        # 종목분석 리포트 목록 페이지
        resp = await client.get(
            f"https://finance.naver.com/research/company_list.naver?searchType=itemCode&itemCode={ticker}&page=1",
            headers=html_headers
        )

        if resp.status_code != 200:
            return consensus

        # EUC-KR 디코딩
        try:
            html = resp.content.decode("euc-kr", errors="ignore")
        except:
            html = resp.text

        # 리포트 링크 추출 (최신 5개)
        report_pattern = r'company_read\.naver\?nid=(\d+)'
        report_ids = re.findall(report_pattern, html)[:5]

        # 증권사 추출 (테이블에서)
        # 패턴: <td>종목명</td><td>제목</td><td>증권사</td>
        broker_pattern = r'<td style="padding-left:10">.*?</td>\s*<td>.*?</td>\s*<td>([^<]+)</td>'
        brokers = re.findall(broker_pattern, html, re.DOTALL)[:5]

        # 각 리포트에서 목표가 추출
        for i, nid in enumerate(report_ids[:5]):
            try:
                detail_resp = await client.get(
                    f"https://finance.naver.com/research/company_read.naver?nid={nid}",
                    headers=html_headers
                )
                if detail_resp.status_code != 200:
                    continue

                try:
                    detail_html = detail_resp.content.decode("euc-kr", errors="ignore")
                except:
                    detail_html = detail_resp.text

                # 목표가 추출 (예: 150,000원)
                target_match = re.search(r'([0-9,]+)원', detail_html)
                target_price = _safe_int(target_match.group(1)) if target_match else 0

                # 투자의견 추출
                opinion = "매수"  # 기본값
                if re.search(r'(Buy|매수|Strong Buy|적극매수)', detail_html, re.I):
                    opinion = "매수"
                elif re.search(r'(Hold|보유|중립)', detail_html, re.I):
                    opinion = "중립"
                elif re.search(r'(Sell|매도)', detail_html, re.I):
                    opinion = "매도"

                broker = brokers[i] if i < len(brokers) else ""

                if broker and target_price > 0:
                    consensus.append({
                        "broker": broker.strip(),
                        "opinion": opinion,
                        "target_price": target_price,
                        "reason": "",  # 상세 사유는 추출이 어려움
                    })

            except Exception as e:
                print(f"[ReportData] 리포트 상세 파싱 실패 ({nid}): {e}")
                continue

    except Exception as e:
        print(f"[ReportData] KR 컨센서스 수집 실패 ({ticker}): {e}")

    return consensus


async def fetch_us_financial_data(ticker: str) -> Dict[str, Any]:
    """
    미국 종목의 재무 데이터를 수집한다.
    yfinance 라이브러리 사용.

    Returns: KR과 동일한 구조 (금액 단위: 백만 달러)
    """
    result = {
        "source": "yahoo_finance",
        "consolidated": True,
        "annual": [],
        "quarterly": [],
        "consensus": [],
    }

    try:
        import yfinance as yf

        stock = yf.Ticker(ticker)

        # 연간 재무제표
        income_stmt = stock.income_stmt
        if income_stmt is not None and not income_stmt.empty:
            for col in income_stmt.columns[:4]:  # 최근 4년
                year = col.year if hasattr(col, 'year') else str(col)[:4]

                revenue = income_stmt.loc["Total Revenue", col] if "Total Revenue" in income_stmt.index else 0
                op_income = income_stmt.loc["Operating Income", col] if "Operating Income" in income_stmt.index else 0
                net_income = income_stmt.loc["Net Income", col] if "Net Income" in income_stmt.index else 0

                # 백만 달러 단위로 변환
                revenue_m = int(revenue / 1_000_000) if revenue else 0
                op_income_m = int(op_income / 1_000_000) if op_income else 0
                net_income_m = int(net_income / 1_000_000) if net_income else 0

                op_margin = (op_income_m / revenue_m * 100) if revenue_m > 0 else 0

                result["annual"].append({
                    "period": f"{year}A",
                    "revenue": revenue_m,
                    "operating_profit": op_income_m,
                    "net_income": net_income_m,
                    "operating_margin": round(op_margin, 2),
                    "is_estimate": False,
                })

        # 분기별 재무제표
        quarterly_income = stock.quarterly_income_stmt
        if quarterly_income is not None and not quarterly_income.empty:
            for col in quarterly_income.columns[:8]:  # 최근 8분기
                date = col
                year = date.year if hasattr(date, 'year') else str(date)[:4]
                month = date.month if hasattr(date, 'month') else 12
                quarter = (month - 1) // 3 + 1

                revenue = quarterly_income.loc["Total Revenue", col] if "Total Revenue" in quarterly_income.index else 0
                op_income = quarterly_income.loc["Operating Income", col] if "Operating Income" in quarterly_income.index else 0

                revenue_m = int(revenue / 1_000_000) if revenue else 0
                op_income_m = int(op_income / 1_000_000) if op_income else 0
                op_margin = (op_income_m / revenue_m * 100) if revenue_m > 0 else 0

                result["quarterly"].append({
                    "period": f"{year}Q{quarter}",
                    "revenue": revenue_m,
                    "operating_profit": op_income_m,
                    "operating_margin": round(op_margin, 2),
                    "is_estimate": False,
                })

        # 애널리스트 컨센서스
        recommendations = stock.recommendations
        if recommendations is not None and not recommendations.empty:
            # 최근 추천 정보
            recent = recommendations.tail(5)
            for _, row in recent.iterrows():
                firm = row.get("Firm", "")
                grade = row.get("To Grade", row.get("Action", ""))

                if firm:
                    opinion = "매수"
                    if any(x in str(grade).lower() for x in ["buy", "outperform", "overweight"]):
                        opinion = "매수"
                    elif any(x in str(grade).lower() for x in ["hold", "neutral", "equal"]):
                        opinion = "중립"
                    elif any(x in str(grade).lower() for x in ["sell", "underperform", "underweight"]):
                        opinion = "매도"

                    result["consensus"].append({
                        "broker": firm,
                        "opinion": opinion,
                        "target_price": 0,  # yfinance에서 목표가 직접 제공 안 함
                        "reason": "",
                    })

        # 목표가는 info에서 가져오기
        info = stock.info
        if info:
            target_mean = info.get("targetMeanPrice", 0)

            # 목표가 범위를 consensus에 추가
            if target_mean and result["consensus"]:
                for c in result["consensus"]:
                    if c["target_price"] == 0:
                        c["target_price"] = target_mean

        # 정렬
        result["annual"].sort(key=lambda x: x["period"])
        result["quarterly"].sort(key=lambda x: x["period"])

    except ImportError:
        print("[ReportData] yfinance 미설치. pip install yfinance 필요")
    except Exception as e:
        print(f"[ReportData] US 데이터 수집 실패 ({ticker}): {e}")

    return result


async def fetch_report_data(ticker: str, market: str) -> Dict[str, Any]:
    """
    통합 데이터 수집 함수.

    Args:
        ticker: 종목 코드 (예: "042700", "NVDA")
        market: "KR" 또는 "US"

    Returns:
        수집된 재무 데이터. 실패 시 빈 dict 반환.
    """
    try:
        if market.upper() == "KR":
            data = await fetch_kr_financial_data(ticker)
        elif market.upper() == "US":
            data = await fetch_us_financial_data(ticker)
        else:
            print(f"[ReportData] 지원하지 않는 시장: {market}")
            return {}

        # 데이터 유효성 검증
        if not data.get("annual") or len(data["annual"]) < 2:
            print(f"[ReportData] 불충분한 데이터 ({ticker}): annual {len(data.get('annual', []))}개")
            return {}

        return data

    except Exception as e:
        print(f"[ReportData] 데이터 수집 실패 ({ticker}): {e}")
        return {}


def format_financial_data_for_prompt(data: Dict[str, Any], market: str) -> str:
    """
    수집된 데이터를 AI 프롬프트용 텍스트로 변환한다.
    """
    if not data or not data.get("annual"):
        return ""

    is_kr = market.upper() == "KR"
    currency = "억원" if is_kr else "백만달러"
    eps_unit = "원" if is_kr else "달러"
    price_unit = "원" if is_kr else "달러"

    lines = []
    lines.append("## 📊 서버 제공 재무 데이터 (정확한 연결재무제표 기준)")
    lines.append("⚠️ 아래 데이터는 서버가 공신력 있는 출처에서 수집한 연결재무제표 기준 데이터입니다.")
    lines.append("⚠️ 테이블 작성 시 반드시 아래 숫자를 그대로 사용하세요. 웹검색으로 다른 숫자를 가져오지 마세요.")
    lines.append("")

    # 연간 실적 테이블
    annual = data.get("annual", [])
    if annual:
        lines.append(f"### 연간 실적 (단위: {currency})")

        # 헤더
        periods = [a["period"] for a in annual[-4:]]  # 최근 4년
        lines.append("| 항목 | " + " | ".join(periods) + " |")
        lines.append("|------" + "|------" * len(periods) + "|")

        # 각 행
        for field, label in [
            ("revenue", "매출액"),
            ("operating_profit", "영업이익"),
            ("net_income", "순이익"),
            ("eps", f"EPS({eps_unit})"),
            ("operating_margin", "영업이익률(%)"),
            ("roe", "ROE(%)"),
        ]:
            values = []
            for a in annual[-4:]:
                v = a.get(field)
                if v is None or v == 0:
                    values.append("-")
                elif field in ["operating_margin", "roe"]:
                    values.append(f"{v:.1f}")
                elif field == "eps":
                    values.append(f"{v:,}")
                else:
                    values.append(f"{v:,}")
            lines.append(f"| {label} | " + " | ".join(values) + " |")

        lines.append("")

    # 분기별 실적
    quarterly = data.get("quarterly", [])
    if quarterly:
        lines.append(f"### 분기별 실적 (단위: {currency})")
        lines.append("| 분기 | 매출액 | 영업이익 | 영업이익률 |")
        lines.append("|------|--------|----------|----------|")

        for q in quarterly[-8:]:  # 최근 8분기
            rev = f"{q.get('revenue', 0):,}"
            op = f"{q.get('operating_profit', 0):,}"
            opm = f"{q.get('operating_margin', 0):.1f}%" if q.get('operating_margin') else "-"
            lines.append(f"| {q['period']} | {rev} | {op} | {opm} |")

        lines.append("")

    # 증권사 컨센서스
    consensus = data.get("consensus", [])
    if consensus:
        lines.append("### 증권사 컨센서스")
        lines.append(f"| 증권사명 | 투자의견 | 목표가({price_unit}) |")
        lines.append("|----------|----------|-------------|")

        for c in consensus[:6]:  # 최대 6개
            broker = c.get("broker", "")
            opinion = c.get("opinion", "")
            tp = c.get("target_price", 0)
            tp_str = f"{tp:,}" if tp > 0 else "-"
            lines.append(f"| {broker} | {opinion} | {tp_str} |")

        # 목표가 범위
        prices = [c["target_price"] for c in consensus if c.get("target_price", 0) > 0]
        if prices:
            lines.append(f"\n목표가 범위: {min(prices):,} ~ {max(prices):,} {price_unit}")

        lines.append("")

    return "\n".join(lines)


# 테스트용
if __name__ == "__main__":
    import asyncio

    async def test():
        # KR 테스트
        print("=== KR 테스트 (042700 한미반도체) ===")
        kr_data = await fetch_report_data("042700", "KR")
        print(f"Annual: {len(kr_data.get('annual', []))}개")
        print(f"Quarterly: {len(kr_data.get('quarterly', []))}개")
        print(f"Consensus: {len(kr_data.get('consensus', []))}개")

        prompt_text = format_financial_data_for_prompt(kr_data, "KR")
        print("\n--- 프롬프트용 텍스트 ---")
        print(prompt_text[:2000])

    asyncio.run(test())

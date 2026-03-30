# app/routers/ai_report_engine.py
# AI 분석 엔진 - Claude API 기반 리포트 생성

import os
import re
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, List, Callable, Optional

import httpx
from sqlalchemy import text

from app.db import SessionLocal
from app.data_provider import (
    get_naver_stock_price,
    get_stock_financials_kr,
    get_stock_news_kr,
)
from app.report_data import fetch_report_data, format_financial_data_for_prompt

# KST timezone
KST = timezone(timedelta(hours=9))


async def run_ai_analysis_job(
    job_id: str,
    symbol: str,
    market: str,
    is_etf: bool,
    ai_jobs: Dict[str, Dict[str, Any]],
    get_master_cache: Callable,
    language: str = "kr"
):
    """백그라운드에서 AI 분석 실행"""
    from .ai_report_charts import generate_ai_charts

    is_english = language == "en"

    try:
        ai_jobs[job_id]["status"] = "running"
        ai_jobs[job_id]["progress"] = "Collecting stock data..." if is_english else "종목 데이터 수집 중..."

        # 종목명 조회
        name = symbol
        master = get_master_cache()
        stock = master.get_stock(symbol)
        if stock:
            name = stock.name
        elif market == "kr":
            try:
                async with httpx.AsyncClient(timeout=5.0) as client:
                    resp = await client.get(
                        f"https://m.stock.naver.com/api/stock/{symbol}/basic",
                        headers={"User-Agent": "Mozilla/5.0"}
                    )
                    if resp.status_code == 200:
                        naver_data = resp.json()
                        if naver_data.get("stockName"):
                            name = naver_data["stockName"]
            except Exception:
                pass

        # 차트 생성
        ai_jobs[job_id]["progress"] = "Generating charts..." if is_english else "차트 생성 중..."
        try:
            chart_urls = await generate_ai_charts(symbol, name, market)
            if chart_urls:
                ai_jobs[job_id]["charts"] = chart_urls
        except Exception as e:
            print(f"[AI Job] Chart generation error: {e}")
            chart_urls = {}

        ai_jobs[job_id]["progress"] = "AI is analyzing..." if is_english else "AI가 분석 중..."

        # Claude API로 리포트 생성 (language로 프롬프트 언어 결정)
        if is_etf:
            ai_result = await _generate_etf_report(name=name, code=symbol, market=market, chart_data=chart_urls, language=language)
        else:
            ai_result = await _generate_claude_report(name=name, code=symbol, market=market, chart_data=chart_urls, language=language)

        report = ai_result.get("report", "")
        if not report or len(report) < 200:
            raise Exception("Report generation failed" if is_english else "리포트 생성 실패")

        ai_jobs[job_id]["stock"] = {"name": name, "code": symbol}
        ai_jobs[job_id]["status"] = "done"
        ai_jobs[job_id]["result"] = report
        ai_jobs[job_id]["progress"] = "Done" if is_english else "완료"

        # 사용량 증가 + 캐시 저장
        try:
            db = SessionLocal()
            user_id = ai_jobs[job_id].get("user_id")
            exchange = ai_jobs[job_id].get("exchange", "")

            if user_id:
                db.execute(
                    text("UPDATE users SET ai_usage_count = ai_usage_count + 1, ai_monthly_count = ai_monthly_count + 1 WHERE id = :uid"),
                    {"uid": user_id}
                )

            expires = datetime.now(timezone.utc) + timedelta(hours=6)
            db.execute(
                text("INSERT INTO ai_reports (symbol, exchange, language, report_text, data_snapshot, expires_at) VALUES (:sym, :ex, :lang, :report, :data, :expires)"),
                {"sym": symbol, "ex": exchange, "lang": language, "report": report, "data": "{}", "expires": expires}
            )
            db.commit()
            db.close()
        except Exception as e:
            print(f"[AI Job] DB update error: {e}")

        print(f"[AI Job] {job_id} 완료: {len(report)}자")

    except Exception as e:
        print(f"[AI Job] {job_id} 오류: {e}")
        ai_jobs[job_id]["status"] = "error"
        ai_jobs[job_id]["error"] = str(e)
        ai_jobs[job_id]["progress"] = "Error occurred" if is_english else "오류 발생"


async def run_ai_chat_job(
    job_id: str,
    message: str,
    user_id: Optional[int],
    ai_jobs: Dict[str, Dict[str, Any]],
    get_master_cache: Callable
):
    """백그라운드에서 AI 채팅 실행"""
    import time as time_module
    from .ai_report_charts import generate_ai_charts

    try:
        t_start = time_module.time()
        ai_jobs[job_id]["status"] = "running"
        ai_jobs[job_id]["progress"] = "종목 인식 중..."

        import anthropic
        client = anthropic.AsyncAnthropic(api_key=os.getenv("ANTHROPIC_API_KEY", ""), timeout=180.0)

        detected_stock = await _detect_stock_from_message(message)
        chart_urls = None

        if detected_stock:
            code = detected_stock["code"]
            name = detected_stock["name"]
            market = detected_stock.get("market", "kr")

            print(f"[AI Chat] 종목 인식: {name}({code})")
            ai_jobs[job_id]["progress"] = f"{name} 데이터 수집 중..."

            tech = await _collect_technical_data_for_ai(code, market)
            fin = await _collect_financial_data_for_ai(code, market)
            news = await _collect_news_for_ai(code, name, market)

            company_summary = ""
            if market == "kr":
                try:
                    from app.data_provider import get_stock_company_kr
                    company_data = await get_stock_company_kr(code)
                    company_summary = company_data.get("description", "")
                except Exception as e:
                    print(f"[AI Chat] Company summary error: {e}")

            pre_fetched_data = {}
            try:
                pre_fetched_data = await fetch_report_data(code, market.upper())
            except Exception as e:
                print(f"[AI Chat] Pre-fetch failed: {e}")

            ai_jobs[job_id]["progress"] = f"{name} 차트 생성 중..."
            chart_urls = await generate_ai_charts(code, name, market)

            if chart_urls.get("support_levels"):
                tech["support_levels"] = chart_urls["support_levels"]
            if chart_urls.get("resistance_levels"):
                tech["resistance_levels"] = chart_urls["resistance_levels"]

            ai_jobs[job_id]["progress"] = "AI is analyzing..." if market == "us" else "AI가 분석 중..."

            system_prompt, user_data_prompt = _build_claude_prompt(name, code, tech, fin, news, company_summary, market, pre_fetched_data)

            if market == "us":
                final_user_prompt = f"""{user_data_prompt}

---
Additional Rules:
- Write a comprehensive analysis report immediately. Do not ask questions.
- Analyze only the requested stock ({name}).

User Question: {message}

Write a comprehensive analysis report for {name} ({code}) based on the above data immediately.
"""
            else:
                final_user_prompt = f"""{user_data_prompt}

---
추가 규칙:
- 즉시 종합 분석 보고서를 작성해라. 질문하지 마라.
- 요청된 종목({name})에 대해서만 분석해라.

사용자 질문: {message}

위 데이터를 기반으로 {name}({code})의 종합 분석 보고서를 즉시 작성해라.
"""

            cache_messages = _split_prompt_for_cache(final_user_prompt)

            response = await client.messages.create(
                model="claude-haiku-4-5-20251001",
                max_tokens=16000,
                tools=[{"type": "web_search_20250305", "name": "web_search"}],
                system=[{
                    "type": "text",
                    "text": system_prompt,
                    "cache_control": {"type": "ephemeral"}
                }],
                messages=cache_messages
            )
        else:
            ai_jobs[job_id]["progress"] = "AI가 생각 중..." if not detected_stock or detected_stock.get("market") != "us" else "AI is thinking..."

            # Determine language based on detected market or default to Korean
            is_us_market = detected_stock.get("market") == "us" if detected_stock else False

            if is_us_market:
                system_prompt = """You are BBooster's AI Investment Assistant.
You provide professional and friendly responses to users' investment-related questions.

Role:
- Stock/ETF analysis and forecasts
- Investment strategy advice
- Market trend explanations
- Technical/fundamental analysis guidance

Guidelines:
- Clarify that this is not legal investment advice
- Provide objective, data-based analysis
- Include risk warnings
- Respond in English
- Use markdown format (## headings, - lists, **emphasis**)
- Provide detailed responses (at least 500 words)"""
            else:
                system_prompt = """당신은 BBooster의 AI 투자 어시스턴트입니다.
사용자의 투자 관련 질문에 전문적이고 친절하게 답변합니다.

역할:
- 주식/ETF 분석 및 전망 제공
- 투자 전략 조언
- 시장 동향 설명
- 기술적/기본적 분석 해설

주의사항:
- 법적 투자 조언이 아님을 명시
- 객관적 데이터 기반 분석
- 리스크 경고 포함
- 한국어로 답변
- 마크다운 형식 (## 제목, - 목록, **강조**)
- 1500자 이상 상세하게"""

            response = await client.messages.create(
                model="claude-haiku-4-5-20251001",
                max_tokens=4096,
                system=system_prompt,
                messages=[{"role": "user", "content": message}]
            )

        reply = ""
        for block in response.content:
            if hasattr(block, 'text'):
                reply += block.text

        reply = _clean_ai_response(reply)

        ai_jobs[job_id]["status"] = "done"
        ai_jobs[job_id]["result"] = reply
        ai_jobs[job_id]["progress"] = "완료"

        if chart_urls:
            ai_jobs[job_id]["charts"] = chart_urls
            ai_jobs[job_id]["stock"] = detected_stock

        if user_id:
            try:
                db = SessionLocal()
                db.execute(
                    text("UPDATE users SET ai_usage_count = ai_usage_count + 1 WHERE id = :uid"),
                    {"uid": user_id}
                )
                db.commit()
                db.close()
            except Exception as e:
                print(f"[AI Chat Job] DB update error: {e}")

        print(f"[AI Chat Job] {job_id} 완료: {len(reply)}자")

    except Exception as e:
        print(f"[AI Chat Job] {job_id} 오류: {e}")
        ai_jobs[job_id]["status"] = "error"
        ai_jobs[job_id]["error"] = str(e)
        ai_jobs[job_id]["progress"] = "오류 발생"


def _clean_ai_response(text: str) -> str:
    """Claude 내부 사고 문구 제거"""
    if not text:
        return text

    text = re.sub(r'웹검색을 통해[^.]*\.', '', text)
    text = re.sub(r'웹검색 결과를 바탕으로[^.]*\.', '', text)
    text = re.sub(r'최신 정보를 수집하겠습니다[^.]*\.', '', text)
    text = re.sub(r'보고서를 작성하겠습니다[^.]*\.', '', text)
    text = re.sub(r'분석.*작성하겠습니다[^.]*\.', '', text)
    text = re.sub(r'필요한 정보를 수집하겠습니다[^.]*\.', '', text)

    lines = text.strip().split('\n')
    start_idx = 0
    for i, line in enumerate(lines):
        stripped = line.strip()
        if (stripped.startswith('---') or
            stripped.startswith('# ') or
            stripped.startswith('## ') or
            stripped.startswith('### ') or
            stripped.startswith('**1.') or
            stripped.startswith('1.') or
            stripped.startswith('* ')):
            start_idx = i
            break

    if start_idx > 0:
        text = '\n'.join(lines[start_idx:])

    text = text.strip()
    while text.startswith('---'):
        text = text[3:].strip()

    return text


async def _detect_stock_from_message(message: str) -> Optional[dict]:
    """메시지에서 종목명/코드 인식"""
    from app.screener.kr_screener import load_kr_stocks
    from app.screener.us_screener import load_us_stocks
    from app.naver_finance import get_etf_list

    # 6자리 숫자 코드
    code_match = re.search(r'\b(\d{6})\b', message)
    if code_match:
        code = code_match.group(1)
        kr_stocks = await load_kr_stocks()
        for stock in kr_stocks:
            if stock.get("code") == code:
                return {"code": code, "name": stock.get("name", code), "market": "kr"}
        try:
            etf_list = await get_etf_list()
            for etf in etf_list:
                if etf.get("code") == code:
                    return {"code": code, "name": etf.get("name", code), "market": "kr", "is_etf": True}
        except Exception:
            pass

    # US 티커 심볼
    us_ticker_match = re.search(r'\b([A-Z]{1,5})\b', message.upper())
    if us_ticker_match:
        ticker = us_ticker_match.group(1)
        SKIP_WORDS = {'A', 'I', 'U', 'AI', 'IT', 'THE', 'AND', 'FOR', 'ETF', 'US',
                      'USD', 'KR', 'KRW', 'PDF', 'OK', 'PM', 'AM', 'CEO', 'IPO',
                      'PE', 'EPS', 'ROE', 'PER', 'PBR', 'BPS', 'GDP', 'CPI', 'CAP'}

        if ticker not in SKIP_WORDS:
            try:
                us_stocks = await load_us_stocks()
                for stock in us_stocks:
                    if stock.get("code", "").upper() == ticker:
                        return {"code": ticker, "name": stock.get("name", ticker), "market": "us"}
            except Exception:
                pass

            try:
                import yfinance as yf
                yf_ticker = yf.Ticker(ticker)
                info = yf_ticker.info
                if info and info.get("shortName"):
                    quote_type = info.get("quoteType", "").upper()
                    is_etf = quote_type == "ETF"
                    return {
                        "code": ticker,
                        "name": info.get("shortName", ticker),
                        "market": "us",
                        "is_etf": is_etf
                    }
            except Exception:
                pass

    # 한글 종목명
    kr_stocks = await load_kr_stocks()
    words = re.findall(r'[가-힣]+', message)

    for word in words:
        if len(word) < 2:
            continue
        for stock in kr_stocks:
            if stock.get("name") == word:
                return {"code": stock.get("code"), "name": stock.get("name"), "market": "kr"}

        for stock in kr_stocks:
            stock_name = stock.get("name", "")
            if word in stock_name and len(word) >= 2:
                return {"code": stock.get("code"), "name": stock_name, "market": "kr"}

    return None


async def _collect_technical_data_for_ai(code: str, market: str = "kr") -> dict:
    """AI 분석용 기술적 지표 수집"""
    from app.screener.technicals import _calc_rsi, _calc_macd, _calc_stochastic, calc_adx

    data = {
        "price": {
            "current": None, "change_pct": None,
            "high_52w": None, "low_52w": None,
            "volume": None, "avg_volume_20d": None,
        },
        "trend_indicators": {
            "adx": None, "plus_di": None, "minus_di": None,
            "rs_score": None,
        },
        "momentum_indicators": {
            "rsi": None, "macd_line": None, "macd_signal": None,
            "macd_histogram": None, "stoch_k": None, "stoch_d": None,
        },
        "moving_averages": {
            "sma_5": None, "sma_20": None, "sma_60": None,
            "sma_120": None, "sma_200": None,
        },
        "support_levels": [],
        "resistance_levels": [],
    }

    try:
        if market == "kr":
            price_data = await get_naver_stock_price(code)
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.get(
                    f"https://api.stock.naver.com/chart/domestic/item/{code}/day?startDateTime=20240101&endDateTime=20261231",
                    headers={"User-Agent": "Mozilla/5.0"}
                )
                if resp.status_code == 200:
                    chart_data = resp.json()
                    candles = chart_data if isinstance(chart_data, list) else []
                    if len(candles) >= 20:
                        closes = [float(c.get("closePrice", 0)) for c in candles]
                        highs = [float(c.get("highPrice", 0)) for c in candles]
                        lows = [float(c.get("lowPrice", 0)) for c in candles]
                        volumes = [int(c.get("accumulatedTradingVolume", 0)) for c in candles]

                        if len(closes) >= 5:
                            data["moving_averages"]["sma_5"] = round(sum(closes[-5:]) / 5)
                        if len(closes) >= 20:
                            data["moving_averages"]["sma_20"] = round(sum(closes[-20:]) / 20)
                            data["price"]["avg_volume_20d"] = int(sum(volumes[-20:]) / 20)
                        if len(closes) >= 60:
                            data["moving_averages"]["sma_60"] = round(sum(closes[-60:]) / 60)
                        if len(closes) >= 120:
                            data["moving_averages"]["sma_120"] = round(sum(closes[-120:]) / 120)
                        if len(closes) >= 200:
                            data["moving_averages"]["sma_200"] = round(sum(closes[-200:]) / 200)

                        recent_252 = closes[-252:] if len(closes) >= 252 else closes
                        data["price"]["high_52w"] = max(recent_252)
                        data["price"]["low_52w"] = min(recent_252)

                        rsi = _calc_rsi(closes, 14)
                        if rsi:
                            data["momentum_indicators"]["rsi"] = rsi

                        macd = _calc_macd(closes)
                        if macd and isinstance(macd, tuple) and len(macd) >= 3:
                            data["momentum_indicators"]["macd_line"] = macd[0]
                            data["momentum_indicators"]["macd_signal"] = macd[1]
                            data["momentum_indicators"]["macd_histogram"] = macd[2]

                        stoch = _calc_stochastic(highs, lows, closes)
                        if stoch and isinstance(stoch, tuple) and len(stoch) >= 2:
                            data["momentum_indicators"]["stoch_k"] = stoch[0]
                            data["momentum_indicators"]["stoch_d"] = stoch[1]

                        adx_result = calc_adx(highs, lows, closes, 14)
                        if adx_result:
                            data["trend_indicators"]["adx"] = adx_result.get("adx")
                            data["trend_indicators"]["plus_di"] = adx_result.get("plus_di")
                            data["trend_indicators"]["minus_di"] = adx_result.get("minus_di")

            if price_data:
                data["price"]["current"] = price_data.get("current", 0)
                data["price"]["change_pct"] = price_data.get("change", 0)
                data["price"]["volume"] = price_data.get("volume", 0)

        elif market == "us":
            import yfinance as yf
            from app.screener.technicals import _calc_rsi, _calc_macd, _calc_stochastic, calc_adx

            ticker = yf.Ticker(code)
            info = ticker.info or {}

            current_price = info.get('currentPrice') or info.get('regularMarketPrice')
            prev_close = info.get('previousClose')
            change_pct = ((current_price - prev_close) / prev_close) * 100 if current_price and prev_close else 0

            data["price"]["current"] = current_price
            data["price"]["change_pct"] = round(change_pct, 2)
            data["price"]["volume"] = info.get('volume')
            data["price"]["high_52w"] = info.get('fiftyTwoWeekHigh')
            data["price"]["low_52w"] = info.get('fiftyTwoWeekLow')
            data["price"]["avg_volume_20d"] = info.get('averageVolume')

            hist = ticker.history(period="2y")
            if hist is not None and len(hist) >= 20:
                closes = hist['Close'].tolist()
                highs = hist['High'].tolist()
                lows = hist['Low'].tolist()

                if len(closes) >= 5:
                    data["moving_averages"]["sma_5"] = round(sum(closes[-5:]) / 5, 2)
                if len(closes) >= 20:
                    data["moving_averages"]["sma_20"] = round(sum(closes[-20:]) / 20, 2)
                if len(closes) >= 60:
                    data["moving_averages"]["sma_60"] = round(sum(closes[-60:]) / 60, 2)
                if len(closes) >= 120:
                    data["moving_averages"]["sma_120"] = round(sum(closes[-120:]) / 120, 2)
                if len(closes) >= 200:
                    data["moving_averages"]["sma_200"] = round(sum(closes[-200:]) / 200, 2)

                rsi = _calc_rsi(closes, 14)
                if rsi:
                    data["momentum_indicators"]["rsi"] = rsi

                macd = _calc_macd(closes)
                if macd and isinstance(macd, tuple) and len(macd) >= 3:
                    data["momentum_indicators"]["macd_line"] = macd[0]
                    data["momentum_indicators"]["macd_signal"] = macd[1]
                    data["momentum_indicators"]["macd_histogram"] = macd[2]

                stoch = _calc_stochastic(highs, lows, closes)
                if stoch and isinstance(stoch, tuple) and len(stoch) >= 2:
                    data["momentum_indicators"]["stoch_k"] = stoch[0]
                    data["momentum_indicators"]["stoch_d"] = stoch[1]

                adx_result = calc_adx(highs, lows, closes, 14)
                if adx_result:
                    data["trend_indicators"]["adx"] = adx_result.get("adx")
                    data["trend_indicators"]["plus_di"] = adx_result.get("plus_di")
                    data["trend_indicators"]["minus_di"] = adx_result.get("minus_di")

    except Exception as e:
        print(f"[AI] Technical data collection error for {code}: {e}")

    return data


async def _collect_financial_data_for_ai(code: str, market: str = "kr") -> dict:
    """AI 분석용 재무 데이터 수집"""
    data = {
        "annual": {"revenue": [], "operating_income": [], "net_income": []},
        "quarter": {"revenue": [], "operating_income": [], "net_income": []},
        "ratios": {
            "roe": None, "debt_ratio": None, "operating_margin": None,
            "per": None, "pbr": None, "eps": None, "market_cap": None,
        },
        "consensus": {"target_price": None, "recommendation": None},
    }

    try:
        if market == "kr":
            fin_data = await get_stock_financials_kr(code, "annual")
            if fin_data and fin_data.get("success"):
                annual = fin_data.get("annual", {})
                data["annual"]["revenue"] = annual.get("revenue", [])[:4]
                data["annual"]["operating_income"] = annual.get("operating_income", [])[:4]
                data["annual"]["net_income"] = annual.get("net_income", [])[:4]

                ratios = fin_data.get("ratios", {})
                data["ratios"]["roe"] = ratios.get("roe")
                data["ratios"]["per"] = ratios.get("per")
                data["ratios"]["pbr"] = ratios.get("pbr")
                data["ratios"]["eps"] = ratios.get("eps")
                data["ratios"]["debt_ratio"] = ratios.get("debt_ratio")
                data["ratios"]["operating_margin"] = ratios.get("operating_margin")
                data["ratios"]["market_cap"] = ratios.get("market_cap")

            q_data = await get_stock_financials_kr(code, "quarter")
            if q_data and q_data.get("success"):
                quarter = q_data.get("quarter", {})
                data["quarter"]["revenue"] = quarter.get("revenue", [])[:8]
                data["quarter"]["operating_income"] = quarter.get("operating_income", [])[:8]
                data["quarter"]["net_income"] = quarter.get("net_income", [])[:8]

    except Exception as e:
        print(f"[AI] Financial data collection error for {code}: {e}")

    return data


async def _collect_news_for_ai(code: str, name: str, market: str = "kr") -> list:
    """AI 분석용 최근 뉴스 수집"""
    news = []
    try:
        if market == "kr":
            news_data = await get_stock_news_kr(code, 5)
            if news_data and news_data.get("success"):
                for item in news_data.get("news", [])[:5]:
                    news.append({
                        "title": item.get("title", ""),
                        "date": item.get("date", ""),
                    })
    except Exception as e:
        print(f"[AI] News collection error for {code}: {e}")

    return news


# =============================================================================
# AI Report System Prompt
# =============================================================================
def get_ai_report_system_prompt(market: str = "kr") -> str:
    """market에 따라 적절한 시스템 프롬프트 반환"""
    if market == "us":
        return """You are a professional securities analyst with 15 years of experience.
Write a comprehensive analysis report based on the given data and instructions.
Please respond in English. All analysis, descriptions, and explanations must be written in English.
"""
    else:
        return """당신은 15년 경력의 전문 증권 애널리스트입니다.
주어진 데이터와 지시에 따라 종합 분석 보고서를 작성합니다.
"""


def _split_prompt_for_cache(user_prompt: str) -> list:
    """user_prompt를 캐싱용 content 배열로 변환"""
    MARKERS = [
        "서버 제공 재무 데이터",
        "## 제공 데이터",
        "## Provided Data",  # English marker for US market
    ]

    split_idx = -1
    for marker in MARKERS:
        idx = user_prompt.find(marker)
        if idx > 0:
            split_idx = idx
            break

    if split_idx > 0:
        static_part = user_prompt[:split_idx]
        dynamic_part = user_prompt[split_idx:]

        return [{
            "role": "user",
            "content": [
                {"type": "text", "text": static_part, "cache_control": {"type": "ephemeral"}},
                {"type": "text", "text": dynamic_part}
            ]
        }]
    else:
        return [{"role": "user", "content": user_prompt}]


def _build_claude_prompt(name: str, code: str, tech: dict, fin: dict, news: list, company_summary: str = "", market: str = "kr", pre_fetched_data: dict = None) -> tuple:
    """Claude에게 보낼 분석 프롬프트 구성"""
    is_us = market == "us"

    if is_us:
        today = datetime.now(KST).strftime('%B %d, %Y')
        currency_prefix = "$"
        currency_suffix = ""
        cap_unit = "B"
        currency_instruction = "This is a US market stock. Display all prices in USD ($)."
    else:
        today = datetime.now(KST).strftime('%Y년 %m월 %d일')
        currency_prefix = ""
        currency_suffix = "원"
        cap_unit = "억원"
        currency_instruction = ""

    def safe_int(v, default=0):
        if v is None:
            return default
        try:
            return int(v)
        except (ValueError, TypeError):
            return default

    def safe_float(v, default=0.0):
        if v is None:
            return default
        try:
            return float(v)
        except (ValueError, TypeError):
            return default

    def safe_str(v, default="-"):
        if v is None:
            return default
        return str(round(v, 2)) if isinstance(v, float) else str(v)

    price = tech.get("price", {})
    current = safe_int(price.get("current"))
    change = safe_float(price.get("change_pct"))
    high_52w = safe_int(price.get("high_52w"))
    low_52w = safe_int(price.get("low_52w"))
    volume = safe_int(price.get("volume"))
    avg_vol = safe_int(price.get("avg_volume_20d"))

    ma = tech.get("moving_averages", {})
    sma20 = safe_str(ma.get("sma_20"))
    sma60 = safe_str(ma.get("sma_60"))
    sma200 = safe_str(ma.get("sma_200"))

    trend = tech.get("trend_indicators", {})
    adx = safe_str(trend.get("adx"))
    plus_di = safe_str(trend.get("plus_di"))
    minus_di = safe_str(trend.get("minus_di"))
    rs = safe_str(trend.get("rs_score"))

    mom = tech.get("momentum_indicators", {})
    rsi = safe_str(mom.get("rsi"))
    macd_hist = safe_str(mom.get("macd_histogram"))

    support_levels = tech.get("support_levels", [])
    resistance_levels = tech.get("resistance_levels", [])
    if is_us:
        support1 = f"${support_levels[0]:,.2f}" if support_levels else "-"
        support2 = f"${support_levels[1]:,.2f}" if len(support_levels) > 1 else "-"
        resistance1 = f"${resistance_levels[0]:,.2f}" if resistance_levels else "-"
        resistance2 = f"${resistance_levels[1]:,.2f}" if len(resistance_levels) > 1 else "-"
    else:
        support1 = f"{support_levels[0]:,}원" if support_levels else "-"
        support2 = f"{support_levels[1]:,}원" if len(support_levels) > 1 else "-"
        resistance1 = f"{resistance_levels[0]:,}원" if resistance_levels else "-"
        resistance2 = f"{resistance_levels[1]:,}원" if len(resistance_levels) > 1 else "-"

    ratios = fin.get("ratios", {})
    roe = safe_str(ratios.get("roe"))
    per = safe_str(ratios.get("per"))
    pbr = safe_str(ratios.get("pbr"))
    eps = safe_str(ratios.get("eps"))
    debt = safe_str(ratios.get("debt_ratio"))
    opm = safe_str(ratios.get("operating_margin"))
    market_cap = safe_str(ratios.get("market_cap"))

    if is_us:
        news_text = "\n".join([f"- [{n['date']}] {n['title']}" for n in news[:5]]) if news else "No recent news"
        company_text = company_summary if company_summary else "Company overview not available"
    else:
        news_text = "\n".join([f"- [{n['date']}] {n['title']}" for n in news[:5]]) if news else "최근 뉴스 없음"
        company_text = company_summary if company_summary else "기업 개요 정보 없음"

    pre_fetched_text = ""
    if pre_fetched_data:
        pre_fetched_text = format_financial_data_for_prompt(pre_fetched_data, market)

    if is_us:
        user_prompt = f"""You are a professional securities analyst with 15 years of experience.
Today's Date: {today}
{currency_instruction}

Write a comprehensive analysis report for {name} ({code}) based on the data below.

{pre_fetched_text}

## Provided Data

### Company Overview
{company_text}

### Basic Information
- Stock: {name} ({code})
- Current Price: {currency_prefix}{current:,}{currency_suffix} ({change:+.2f}%)
- 52-Week High/Low: {currency_prefix}{high_52w:,}{currency_suffix} / {currency_prefix}{low_52w:,}{currency_suffix}
- Volume: {volume:,} shares (20-day avg: {avg_vol:,} shares)
- Market Cap: {currency_prefix}{market_cap}{cap_unit}

### Financial Ratios
| Metric | Value |
|--------|-------|
| P/E Ratio | {per} |
| P/B Ratio | {pbr} |
| ROE | {roe}% |
| EPS | {currency_prefix}{eps}{currency_suffix} |
| Debt Ratio | {debt}% |
| Operating Margin | {opm}% |

### Technical Indicators Summary
- RSI(14): {rsi} | MACD Histogram: {macd_hist}
- ADX: {adx} (+DI: {plus_di}, -DI: {minus_di})
- RS (Relative Strength): {rs}
- Support: {support1}, {support2} | Resistance: {resistance1}, {resistance2}
- Moving Averages: SMA20 {sma20}, SMA60 {sma60}, SMA200 {sma200}

### Recent News
{news_text}

---

## Report Structure

1. Executive Summary (Company identity, earnings, valuation, growth drivers, risks, technical signals)
2. Company Analysis (Business overview, market position)
3. Earnings & Valuation Analysis (Annual/quarterly tables)
4. Investment Points (Positive/negative factors)
5. Technical Analysis (Support/resistance, momentum, trend)
6. Investment Strategy (Short-term/mid-long term)
7. Disclaimer

Please write the report. Minimum 1500 words.
"""
    else:
        user_prompt = f"""당신은 15년 경력의 전문 증권 애널리스트입니다.
오늘 날짜: {today}
{currency_instruction}

{name}({code})의 종합 분석 보고서를 아래 데이터 기반으로 작성하세요.

{pre_fetched_text}

## 제공 데이터

### 기업 개요
{company_text}

### 기본 정보
- 종목명: {name} ({code})
- 현재가: {currency_prefix}{current:,}{currency_suffix} ({change:+.2f}%)
- 52주 고가/저가: {currency_prefix}{high_52w:,}{currency_suffix} / {currency_prefix}{low_52w:,}{currency_suffix}
- 거래량: {volume:,}주 (20일 평균: {avg_vol:,}주)
- 시가총액: {market_cap}{cap_unit}

### 재무 지표
| 지표 | 값 |
|------|-----|
| PER | {per} |
| PBR | {pbr} |
| ROE | {roe}% |
| EPS | {currency_prefix}{eps}{currency_suffix} |
| 부채비율 | {debt}% |
| 영업이익률 | {opm}% |

### 기술적 지표 요약
- RSI(14): {rsi} | MACD Histogram: {macd_hist}
- ADX: {adx} (+DI: {plus_di}, -DI: {minus_di})
- RS(상대강도): {rs}
- 지지선: {support1}, {support2} | 저항선: {resistance1}, {resistance2}
- 이동평균: SMA20 {sma20}, SMA60 {sma60}, SMA200 {sma200}

### 최근 뉴스
{news_text}

---

## 보고서 구조

1. 핵심 요약 (기업정체, 실적, 밸류에이션, 성장동력, 리스크, 기술적 신호)
2. 기업 분석 (사업 개요, 시장 포지션)
3. 실적 및 밸류에이션 분석 (연간/분기 테이블)
4. 투자 포인트 (긍정/부정 요인)
5. 기술적 분석 (지지/저항, 모멘텀, 추세)
6. 투자 전략 (단기/중장기)
7. 면책조항

보고서를 작성하세요. 최소 3000자 이상.
"""
    return (get_ai_report_system_prompt(market), user_prompt)


async def _generate_etf_report(name: str, code: str, market: str = "kr", chart_data: dict = None, language: str = "kr") -> dict:
    """ETF 전용 Claude API 리포트 생성"""
    import anthropic

    is_english = language == "en"
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        return {
            "success": False,
            "report": f"# {name} ({code}) ETF Analysis\n\nUnable to load ETF analysis data." if is_english else f"# {name} ({code}) ETF 분석\n\nETF 분석 데이터를 불러올 수 없습니다.",
            "fallback": True
        }

    try:
        # ETF 데이터 수집
        etf_data = await _collect_etf_data_for_ai(code)
        technical_data = await _collect_technical_data_for_ai(code, market)

        if chart_data:
            if chart_data.get("support_levels"):
                technical_data["support_levels"] = chart_data["support_levels"]
            if chart_data.get("resistance_levels"):
                technical_data["resistance_levels"] = chart_data["resistance_levels"]

        etf_data['technical'] = technical_data

        # language로 프롬프트 언어 결정
        prompt_lang = "us" if language == "en" else "kr"
        prompt = _build_etf_prompt(name, code, etf_data, prompt_lang)

        client = anthropic.AsyncAnthropic(api_key=api_key, timeout=180.0)

        response = await client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=16000,
            messages=[{"role": "user", "content": prompt}]
        )

        report_md = response.content[0].text
        report_md = _clean_meta_comments(report_md)

        return {
            "success": True,
            "report": report_md,
            "fallback": False
        }

    except Exception as e:
        print(f"[ETF Report] Claude API error: {e}")
        return {
            "success": False,
            "report": f"# {name} ({code}) ETF 분석\n\nETF 분석 중 오류가 발생했습니다: {e}",
            "error": str(e),
            "fallback": True
        }


async def _collect_etf_data_for_ai(code: str) -> dict:
    """ETF 전용 데이터 수집"""
    result = {
        "name": "",
        "current_price": 0,
        "change_pct": 0,
        "nav": 0,
        "nav_diff_pct": 0,
        "total_expense": 0,
        "aum": 0,
        "tracking_index": "",
        "manager": "",
        "dividend_yield": 0,
        "holdings": [],
        "returns": {},
        "high_52w": 0,
        "low_52w": 0,
        "volume": 0,
    }

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.get(
                f"https://m.stock.naver.com/api/stock/{code}/basic",
                headers={"User-Agent": "Mozilla/5.0"}
            )
            if resp.status_code == 200:
                data = resp.json()
                result["name"] = data.get("stockName", "")
                close_price = data.get("closePrice", "0")
                if isinstance(close_price, str):
                    close_price = close_price.replace(",", "")
                result["current_price"] = int(close_price) if close_price else 0
                result["change_pct"] = float(data.get("fluctuationsRatio", 0) or 0)

    except Exception as e:
        print(f"[ETF Data] Error collecting data for {code}: {e}")

    return result


def _build_etf_prompt(name: str, code: str, data: dict, market: str = "kr") -> str:
    """ETF 전용 AI 분석 프롬프트 구성"""
    is_us = market == "us"

    if is_us:
        today = datetime.now(KST).strftime('%B %d, %Y')
        currency_prefix = "$"
        currency_suffix = ""
        manager_default = "Not available"
    else:
        today = datetime.now(KST).strftime('%Y년 %m월 %d일')
        currency_prefix = ""
        currency_suffix = "원"
        manager_default = "정보 없음"

    current_price = data.get('current_price', 0)
    nav = data.get('nav', 0)

    if is_us:
        prompt = f"""
You are a professional ETF analyst. Write an investment analysis report based on the ETF information below.
Please respond in English. All analysis must be written in English.

## Analysis Target
- ETF Name: {name}
- Ticker: {code}
- Analysis Date: {today}

## Provided Data
- Current Price: {currency_prefix}{current_price:,}{currency_suffix}
- Change: {data.get('change_pct', 0):.2f}%
- NAV: {currency_prefix}{nav:,}{currency_suffix}
- Manager: {data.get('manager', manager_default)}
- Expense Ratio: {data.get('total_expense', 0):.2f}%

---

## Report Structure

1. Executive Summary
2. Tracking Index Analysis
3. Holdings Analysis
4. Cost & Efficiency
5. Technical Analysis
6. Investment Opinion
7. Disclaimer

Minimum 1000 words.
"""
    else:
        prompt = f"""
당신은 ETF 전문 애널리스트입니다. 아래 ETF 정보를 바탕으로 투자 분석 보고서를 작성해주세요.

## 분석 대상
- ETF명: {name}
- 종목코드: {code}
- 분석일: {today}

## 제공된 데이터
- 현재가: {currency_prefix}{current_price:,}{currency_suffix}
- 등락률: {data.get('change_pct', 0):.2f}%
- NAV: {currency_prefix}{nav:,}{currency_suffix}
- 운용사: {data.get('manager', manager_default)}
- 총보수: {data.get('total_expense', 0):.2f}%

---

## 보고서 구조

1. 핵심 요약
2. 추적 지수 분석
3. 편입종목 분석
4. 비용 및 효율성
5. 기술적 분석
6. 투자 의견
7. 면책조항

최소 2000자 이상으로 작성하세요.
"""
    return prompt


def _clean_meta_comments(report_md: str) -> str:
    """AI 응답에서 메타 코멘트 제거 (Remove meta comments from AI response)"""
    meta_patterns = [
        # Korean patterns
        r"이제 보고서를 완성하겠습니다\.?",
        r"분석을 시작하겠습니다\.?",
        r"다음으로 넘어가겠습니다\.?",
        r"이상으로 마치겠습니다\.?",
        r"보고서를 작성하겠습니다\.?",
        # English patterns
        r"I will now complete the report\.?",
        r"Let me start the analysis\.?",
        r"Moving on to the next section\.?",
        r"That concludes the report\.?",
        r"I will write the report\.?",
        r"Let me analyze\.?",
    ]

    cleaned = report_md
    for pattern in meta_patterns:
        cleaned = re.sub(pattern, "", cleaned)

    cleaned = re.sub(r'\n{3,}', '\n\n', cleaned)

    return cleaned.strip()


async def _generate_claude_report(name: str, code: str, market: str = "kr", chart_data: dict = None, language: str = "kr") -> dict:
    """Claude API로 종합 분석 리포트 생성"""
    import anthropic

    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        from .ai_report import _generate_simple_report
        return {
            "success": False,
            "report": _generate_simple_report({"name": name, "symbol": code}),
            "fallback": True
        }

    try:
        tech = await _collect_technical_data_for_ai(code, market)
        fin = await _collect_financial_data_for_ai(code, market)
        news = await _collect_news_for_ai(code, name, market)

        pre_fetched_data = {}
        try:
            pre_fetched_data = await fetch_report_data(code, market.upper())
        except Exception as e:
            print(f"[AI Report] Pre-fetch failed: {e}")

        if chart_data:
            if chart_data.get("support_levels"):
                tech["support_levels"] = chart_data["support_levels"]
            if chart_data.get("resistance_levels"):
                tech["resistance_levels"] = chart_data["resistance_levels"]

        # language 파라미터를 사용하여 프롬프트 언어 결정
        prompt_lang = "us" if language == "en" else "kr"
        system_prompt, user_prompt = _build_claude_prompt(name, code, tech, fin, news, "", prompt_lang, pre_fetched_data)

        client = anthropic.AsyncAnthropic(api_key=api_key, timeout=180.0)
        cache_messages = _split_prompt_for_cache(user_prompt)

        response = await client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=16000,
            system=[{
                "type": "text",
                "text": system_prompt,
                "cache_control": {"type": "ephemeral"}
            }],
            messages=cache_messages
        )

        report_md = response.content[0].text
        report_md = _clean_meta_comments(report_md)

        return {
            "success": True,
            "report": report_md,
            "technical": tech,
            "financial": fin,
            "fallback": False,
        }

    except Exception as e:
        print(f"[AI Report] Claude API error: {e}")
        from .ai_report import _generate_simple_report
        return {
            "success": False,
            "report": _generate_simple_report({"name": name, "symbol": code}),
            "error": str(e),
            "fallback": True
        }

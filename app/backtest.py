"""
BBooster 백테스팅 엔진 (PHASE 6)
- RSI, MACD, SMA, EMA, 볼린저밴드 지표 계산
- 커스텀/역추세/추세 전략 백테스팅
- 성과 지표 계산 (수익률, MDD, 샤프비율, 승률 등)
"""

from typing import List, Dict, Optional, Any
from datetime import datetime, timedelta
from pydantic import BaseModel
import math
import random


# =============================================================================
# 데이터 모델
# =============================================================================

class BacktestRequest(BaseModel):
    strategy_type: str  # custom, reversal, trend
    exchange: str
    symbol: str
    start_date: str
    end_date: str
    initial_capital: float = 10000000
    params: Dict[str, Any] = {}
    order_settings: Dict[str, Any] = {}


class TradeRecord(BaseModel):
    date: str
    type: str  # buy, sell
    price: float
    qty: float
    pnl: Optional[float] = None


class BacktestResult(BaseModel):
    summary: Dict[str, float]
    equity_curve: List[Dict[str, Any]]
    trades: List[TradeRecord]


# =============================================================================
# 더미 가격 데이터 생성
# =============================================================================

def generate_price_data(symbol: str, start_date: str, end_date: str) -> List[Dict[str, Any]]:
    """더미 가격 데이터 생성 (일봉)"""
    random.seed(hash(symbol) % 10000)  # 심볼별 일관된 데이터

    start = datetime.strptime(start_date, "%Y-%m-%d")
    end = datetime.strptime(end_date, "%Y-%m-%d")

    # 초기 가격 설정
    base_prices = {
        "BTC-USDT": 50000,
        "ETH-USDT": 3000,
        "SOL-USDT": 100,
        "005930": 70000,  # 삼성전자
    }
    price = base_prices.get(symbol.upper(), 10000)

    data = []
    current = start

    while current <= end:
        # 랜덤 워크 + 약간의 상승 트렌드
        change = (random.random() - 0.48) * price * 0.03
        price = max(price * 0.5, price + change)  # 최소 50% 유지

        high = price * (1 + random.random() * 0.02)
        low = price * (1 - random.random() * 0.02)
        open_price = price * (1 + (random.random() - 0.5) * 0.01)
        volume = random.randint(1000000, 10000000)

        data.append({
            "date": current.strftime("%Y-%m-%d"),
            "open": open_price,
            "high": high,
            "low": low,
            "close": price,
            "volume": volume
        })

        current += timedelta(days=1)

    return data


# =============================================================================
# 기술적 지표 계산
# =============================================================================

def calculate_sma(prices: List[float], period: int) -> List[Optional[float]]:
    """단순 이동평균 (SMA)"""
    result = [None] * len(prices)
    for i in range(period - 1, len(prices)):
        result[i] = sum(prices[i - period + 1:i + 1]) / period
    return result


def calculate_ema(prices: List[float], period: int) -> List[Optional[float]]:
    """지수 이동평균 (EMA)"""
    result = [None] * len(prices)
    multiplier = 2 / (period + 1)

    # 첫 EMA는 SMA로 계산
    if len(prices) >= period:
        result[period - 1] = sum(prices[:period]) / period

        for i in range(period, len(prices)):
            result[i] = (prices[i] * multiplier) + (result[i - 1] * (1 - multiplier))

    return result


def calculate_rsi(prices: List[float], period: int = 14) -> List[Optional[float]]:
    """상대강도지수 (RSI)"""
    result = [None] * len(prices)

    if len(prices) < period + 1:
        return result

    gains = []
    losses = []

    for i in range(1, len(prices)):
        change = prices[i] - prices[i - 1]
        gains.append(max(change, 0))
        losses.append(max(-change, 0))

    for i in range(period, len(prices)):
        avg_gain = sum(gains[i - period:i]) / period
        avg_loss = sum(losses[i - period:i]) / period

        if avg_loss == 0:
            result[i] = 100
        else:
            rs = avg_gain / avg_loss
            result[i] = 100 - (100 / (1 + rs))

    return result


def calculate_macd(prices: List[float], fast: int = 12, slow: int = 26, signal: int = 9) -> Dict[str, List[Optional[float]]]:
    """MACD"""
    ema_fast = calculate_ema(prices, fast)
    ema_slow = calculate_ema(prices, slow)

    macd_line = [None] * len(prices)
    for i in range(len(prices)):
        if ema_fast[i] is not None and ema_slow[i] is not None:
            macd_line[i] = ema_fast[i] - ema_slow[i]

    # MACD 값만 추출해서 신호선 계산
    valid_macd = [m for m in macd_line if m is not None]
    signal_line = [None] * len(prices)

    if len(valid_macd) >= signal:
        ema_signal = calculate_ema(valid_macd, signal)
        j = 0
        for i in range(len(prices)):
            if macd_line[i] is not None:
                if j < len(ema_signal):
                    signal_line[i] = ema_signal[j]
                j += 1

    return {"macd": macd_line, "signal": signal_line}


def calculate_bollinger_bands(prices: List[float], period: int = 20, std_dev: float = 2.0) -> Dict[str, List[Optional[float]]]:
    """볼린저 밴드"""
    sma = calculate_sma(prices, period)
    upper = [None] * len(prices)
    lower = [None] * len(prices)

    for i in range(period - 1, len(prices)):
        window = prices[i - period + 1:i + 1]
        std = (sum((p - sma[i]) ** 2 for p in window) / period) ** 0.5
        upper[i] = sma[i] + (std_dev * std)
        lower[i] = sma[i] - (std_dev * std)

    return {"middle": sma, "upper": upper, "lower": lower}


# =============================================================================
# 전략 시뮬레이션
# =============================================================================

def run_reversal_strategy(
    price_data: List[Dict],
    rsi_period: int = 14,
    overbought: int = 70,
    oversold: int = 30,
    initial_capital: float = 10000000,
    qty_percent: float = 100,
    stop_loss: Optional[float] = None,
    take_profit: Optional[float] = None
) -> BacktestResult:
    """역추세 전략 (RSI 기반)"""
    prices = [d["close"] for d in price_data]
    rsi = calculate_rsi(prices, rsi_period)

    equity = initial_capital
    position = 0
    entry_price = 0
    trades: List[TradeRecord] = []
    equity_curve = []

    for i, data in enumerate(price_data):
        price = data["close"]
        date = data["date"]

        if rsi[i] is None:
            equity_curve.append({"date": date, "equity": equity})
            continue

        # 포지션이 없을 때
        if position == 0:
            # RSI 과매도 → 매수
            if rsi[i] < oversold:
                qty = (equity * qty_percent / 100) / price
                position = qty
                entry_price = price
                trades.append(TradeRecord(date=date, type="buy", price=price, qty=qty))
        else:
            # 포지션이 있을 때
            current_pnl_pct = (price - entry_price) / entry_price * 100

            # 손절
            if stop_loss and current_pnl_pct <= -stop_loss:
                pnl = (price - entry_price) * position
                equity += pnl
                trades.append(TradeRecord(date=date, type="sell", price=price, qty=position, pnl=pnl))
                position = 0
            # 익절
            elif take_profit and current_pnl_pct >= take_profit:
                pnl = (price - entry_price) * position
                equity += pnl
                trades.append(TradeRecord(date=date, type="sell", price=price, qty=position, pnl=pnl))
                position = 0
            # RSI 과매수 → 매도
            elif rsi[i] > overbought:
                pnl = (price - entry_price) * position
                equity += pnl
                trades.append(TradeRecord(date=date, type="sell", price=price, qty=position, pnl=pnl))
                position = 0

        # 현재 자산 계산
        current_equity = equity + (position * price if position > 0 else 0)
        equity_curve.append({"date": date, "equity": current_equity})

    # 마지막 포지션 정리
    if position > 0:
        last_price = price_data[-1]["close"]
        pnl = (last_price - entry_price) * position
        equity += pnl
        trades.append(TradeRecord(
            date=price_data[-1]["date"],
            type="sell",
            price=last_price,
            qty=position,
            pnl=pnl
        ))

    summary = calculate_performance_metrics(equity_curve, trades, initial_capital)
    return BacktestResult(summary=summary, equity_curve=equity_curve, trades=trades)


def run_trend_strategy(
    price_data: List[Dict],
    short_ma: int = 20,
    long_ma: int = 60,
    initial_capital: float = 10000000,
    qty_percent: float = 100,
    stop_loss: Optional[float] = None,
    take_profit: Optional[float] = None
) -> BacktestResult:
    """추세 전략 (이동평균 크로스)"""
    prices = [d["close"] for d in price_data]
    sma_short = calculate_sma(prices, short_ma)
    sma_long = calculate_sma(prices, long_ma)

    equity = initial_capital
    position = 0
    entry_price = 0
    trades: List[TradeRecord] = []
    equity_curve = []

    for i, data in enumerate(price_data):
        price = data["close"]
        date = data["date"]

        if sma_short[i] is None or sma_long[i] is None:
            equity_curve.append({"date": date, "equity": equity})
            continue

        prev_short = sma_short[i - 1] if i > 0 and sma_short[i - 1] else None
        prev_long = sma_long[i - 1] if i > 0 and sma_long[i - 1] else None

        # 포지션이 없을 때
        if position == 0:
            # 골든 크로스 (단기 > 장기, 이전에는 단기 < 장기)
            if prev_short and prev_long:
                if sma_short[i] > sma_long[i] and prev_short <= prev_long:
                    qty = (equity * qty_percent / 100) / price
                    position = qty
                    entry_price = price
                    trades.append(TradeRecord(date=date, type="buy", price=price, qty=qty))
        else:
            # 포지션이 있을 때
            current_pnl_pct = (price - entry_price) / entry_price * 100

            # 손절
            if stop_loss and current_pnl_pct <= -stop_loss:
                pnl = (price - entry_price) * position
                equity += pnl
                trades.append(TradeRecord(date=date, type="sell", price=price, qty=position, pnl=pnl))
                position = 0
            # 익절
            elif take_profit and current_pnl_pct >= take_profit:
                pnl = (price - entry_price) * position
                equity += pnl
                trades.append(TradeRecord(date=date, type="sell", price=price, qty=position, pnl=pnl))
                position = 0
            # 데드 크로스 → 매도
            elif prev_short and prev_long:
                if sma_short[i] < sma_long[i] and prev_short >= prev_long:
                    pnl = (price - entry_price) * position
                    equity += pnl
                    trades.append(TradeRecord(date=date, type="sell", price=price, qty=position, pnl=pnl))
                    position = 0

        current_equity = equity + (position * price if position > 0 else 0)
        equity_curve.append({"date": date, "equity": current_equity})

    # 마지막 포지션 정리
    if position > 0:
        last_price = price_data[-1]["close"]
        pnl = (last_price - entry_price) * position
        equity += pnl
        trades.append(TradeRecord(
            date=price_data[-1]["date"],
            type="sell",
            price=last_price,
            qty=position,
            pnl=pnl
        ))

    summary = calculate_performance_metrics(equity_curve, trades, initial_capital)
    return BacktestResult(summary=summary, equity_curve=equity_curve, trades=trades)


# =============================================================================
# 성과 지표 계산
# =============================================================================

def calculate_performance_metrics(
    equity_curve: List[Dict],
    trades: List[TradeRecord],
    initial_capital: float
) -> Dict[str, float]:
    """성과 지표 계산"""
    if not equity_curve:
        return {
            "total_return": 0,
            "cagr": 0,
            "max_drawdown": 0,
            "sharpe_ratio": 0,
            "win_rate": 0,
            "total_trades": 0,
            "avg_win": 0,
            "avg_loss": 0
        }

    final_equity = equity_curve[-1]["equity"]
    total_return = (final_equity - initial_capital) / initial_capital * 100

    # CAGR 계산
    years = len(equity_curve) / 365
    if years > 0 and final_equity > 0:
        cagr = ((final_equity / initial_capital) ** (1 / years) - 1) * 100
    else:
        cagr = 0

    # MDD 계산
    max_equity = initial_capital
    max_drawdown = 0
    for point in equity_curve:
        eq = point["equity"]
        max_equity = max(max_equity, eq)
        drawdown = (max_equity - eq) / max_equity * 100
        max_drawdown = max(max_drawdown, drawdown)

    # 샤프 비율 계산 (간략화)
    returns = []
    for i in range(1, len(equity_curve)):
        prev = equity_curve[i - 1]["equity"]
        curr = equity_curve[i]["equity"]
        if prev > 0:
            returns.append((curr - prev) / prev)

    if returns:
        avg_return = sum(returns) / len(returns)
        std_return = (sum((r - avg_return) ** 2 for r in returns) / len(returns)) ** 0.5
        sharpe_ratio = (avg_return / std_return * (252 ** 0.5)) if std_return > 0 else 0
    else:
        sharpe_ratio = 0

    # 승률 및 평균 수익/손실
    sell_trades = [t for t in trades if t.type == "sell" and t.pnl is not None]
    total_trades = len(sell_trades)

    if total_trades > 0:
        wins = [t for t in sell_trades if t.pnl > 0]
        losses = [t for t in sell_trades if t.pnl <= 0]
        win_rate = len(wins) / total_trades * 100

        avg_win = sum(t.pnl for t in wins) / len(wins) if wins else 0
        avg_loss = sum(t.pnl for t in losses) / len(losses) if losses else 0

        # 퍼센트로 변환 (초기 자본 대비)
        avg_win_pct = avg_win / initial_capital * 100
        avg_loss_pct = avg_loss / initial_capital * 100
    else:
        win_rate = 0
        avg_win_pct = 0
        avg_loss_pct = 0

    return {
        "total_return": round(total_return, 2),
        "cagr": round(cagr, 2),
        "max_drawdown": round(-max_drawdown, 2),
        "sharpe_ratio": round(sharpe_ratio, 2),
        "win_rate": round(win_rate, 1),
        "total_trades": total_trades,
        "avg_win": round(avg_win_pct, 2),
        "avg_loss": round(avg_loss_pct, 2)
    }


# =============================================================================
# 메인 백테스팅 함수
# =============================================================================

def run_backtest(request: BacktestRequest) -> BacktestResult:
    """백테스팅 실행"""
    # 가격 데이터 생성
    price_data = generate_price_data(request.symbol, request.start_date, request.end_date)

    if len(price_data) < 30:
        return BacktestResult(
            summary={"error": "데이터 부족", "total_return": 0},
            equity_curve=[],
            trades=[]
        )

    params = request.params or {}
    order_settings = request.order_settings or {}

    qty_percent = order_settings.get("qty_percent", 100)
    stop_loss = order_settings.get("stop_loss")
    take_profit = order_settings.get("take_profit")

    if request.strategy_type == "reversal":
        return run_reversal_strategy(
            price_data,
            rsi_period=params.get("rsi_period", 14),
            overbought=params.get("overbought", 70),
            oversold=params.get("oversold", 30),
            initial_capital=request.initial_capital,
            qty_percent=qty_percent,
            stop_loss=stop_loss,
            take_profit=take_profit
        )

    elif request.strategy_type == "trend":
        return run_trend_strategy(
            price_data,
            short_ma=params.get("short_ma", 20),
            long_ma=params.get("long_ma", 60),
            initial_capital=request.initial_capital,
            qty_percent=qty_percent,
            stop_loss=stop_loss,
            take_profit=take_profit
        )

    else:  # custom - 기본적으로 역추세 전략 사용
        return run_reversal_strategy(
            price_data,
            initial_capital=request.initial_capital,
            qty_percent=qty_percent,
            stop_loss=stop_loss,
            take_profit=take_profit
        )

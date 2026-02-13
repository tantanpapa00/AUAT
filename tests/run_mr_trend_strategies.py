#!/usr/bin/env python
"""
Test MR and Trend Strategy Backtests across all exchanges
"""

import requests
import json
from datetime import datetime

API_MR = "https://qube-system.com/api/premium/backtest/mr"
API_TREND = "https://qube-system.com/api/premium/backtest/trend"

# 거래소별 테스트 (1D만)
TEST_CASES = [
    {"exchange": "OKX", "symbol": "BTC-USDT-SWAP"},
    {"exchange": "BINANCE", "symbol": "BTCUSDT"},
    {"exchange": "BYBIT", "symbol": "BTCUSDT"},
    {"exchange": "UPBIT", "symbol": "KRW-BTC"},
    {"exchange": "KIS_KR", "symbol": "005930"},  # 삼성전자
    {"exchange": "KIS_US", "symbol": "AAPL"},
]


def run_mr_backtest(exchange, symbol):
    """Run MR backtest"""
    payload = {
        "exchange": exchange,
        "symbol": symbol,
        "timeframe": "1D",
        "days": 180,
        "initial_capital": 10000000,
    }
    try:
        resp = requests.post(API_MR, json=payload, timeout=120)
        data = resp.json()
        return {
            "success": data.get("success", False),
            "message": data.get("message"),
            "trades": len(data.get("trades", [])) if data.get("trades") else 0,
            "net_profit_pct": data.get("metrics", {}).get("net_profit_pct", 0),
        }
    except Exception as e:
        return {"success": False, "message": str(e), "trades": 0, "net_profit_pct": 0}


def run_trend_backtest(exchange, symbol):
    """Run Trend backtest"""
    payload = {
        "exchange": exchange,
        "symbol": symbol,
        "timeframe": "1D",
        "days": 180,
        "initial_capital": 10000000,
    }
    try:
        resp = requests.post(API_TREND, json=payload, timeout=120)
        data = resp.json()
        return {
            "success": data.get("success", False),
            "message": data.get("message"),
            "trades": len(data.get("trades", [])) if data.get("trades") else 0,
            "net_profit_pct": data.get("metrics", {}).get("net_profit_pct", 0),
        }
    except Exception as e:
        return {"success": False, "message": str(e), "trades": 0, "net_profit_pct": 0}


def main():
    print("=" * 70)
    print("MR / Trend 전략 백테스트 검증")
    print(f"시작: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 70)

    results = []

    for case in TEST_CASES:
        exchange, symbol = case["exchange"], case["symbol"]

        # MR Test
        print(f"\n[MR] {exchange}/{symbol}")
        mr_result = run_mr_backtest(exchange, symbol)
        if mr_result["success"]:
            print(f"  > SUCCESS | trades: {mr_result['trades']} | return: {mr_result['net_profit_pct']:.2f}%")
        else:
            print(f"  > FAILED | {mr_result['message']}")
        results.append({"strategy": "MR", "exchange": exchange, "symbol": symbol, **mr_result})

        # Trend Test
        print(f"[Trend] {exchange}/{symbol}")
        trend_result = run_trend_backtest(exchange, symbol)
        if trend_result["success"]:
            print(f"  > SUCCESS | trades: {trend_result['trades']} | return: {trend_result['net_profit_pct']:.2f}%")
        else:
            print(f"  > FAILED | {trend_result['message']}")
        results.append({"strategy": "Trend", "exchange": exchange, "symbol": symbol, **trend_result})

    # Summary
    print("\n" + "=" * 70)
    print("SUMMARY")
    print("=" * 70)

    mr_results = [r for r in results if r["strategy"] == "MR"]
    trend_results = [r for r in results if r["strategy"] == "Trend"]

    mr_success = sum(1 for r in mr_results if r["success"])
    trend_success = sum(1 for r in trend_results if r["success"])

    print(f"\nMR Strategy: {mr_success}/{len(mr_results)}")
    print(f"Trend Strategy: {trend_success}/{len(trend_results)}")
    print(f"Total: {mr_success + trend_success}/{len(results)}")

    # Failed tests
    failed = [r for r in results if not r["success"]]
    if failed:
        print("\n[Failed Tests]")
        for r in failed:
            print(f"  - {r['strategy']}/{r['exchange']}/{r['symbol']}: {r['message']}")

    return mr_success + trend_success, len(results) - (mr_success + trend_success)


if __name__ == "__main__":
    main()

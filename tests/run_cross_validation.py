#!/usr/bin/env python
"""
Cross-validation test: 6 strategies x 6 exchanges + MR/Trend = 48 tests
"""

import requests
from datetime import datetime

API_CUSTOM = "https://qube-system.com/api/premium/backtest/custom"
API_MR = "https://qube-system.com/api/premium/backtest/mr"
API_TREND = "https://qube-system.com/api/premium/backtest/trend"

# 6 exchanges with symbols
EXCHANGE_SYMBOLS = {
    "OKX": "BTC-USDT-SWAP",
    "BINANCE": "BTCUSDT",
    "BYBIT": "BTCUSDT",
    "UPBIT": "KRW-BTC",
    "KIS_KR": "005930",  # Samsung
    "KIS_US": "AAPL",
}


def make_condition(indicator, output, params, operator, compare_value):
    """Helper to create a condition item"""
    return {
        "indicator": indicator,
        "output": output,
        "params": params,
        "operator": operator,
        "compare_type": "value",
        "compare_value": compare_value,
    }


def make_strategy(name, entry_conditions, exit_conditions):
    """Helper to create a strategy config"""
    return {
        "name": name,
        "entry_rules": {
            "groups": [{"conditions": entry_conditions, "logic": "AND"}]
        },
        "exit_rules": {
            "groups": [{"conditions": exit_conditions, "logic": "AND"}]
        },
        "position_size_pct": 100.0,
        "commission_pct": 0.015,
    }


# 6 strategies with proper schema
STRATEGIES = {
    "RSI_basic": make_strategy(
        "RSI_basic",
        [make_condition("RSI", "value", {"period": 14}, "<", 40)],
        [make_condition("RSI", "value", {"period": 14}, ">", 60)],
    ),
    "MACD_cross": make_strategy(
        "MACD_cross",
        [make_condition("MACD", "macd", {"fast_length": 12, "slow_length": 26, "signal_length": 9}, ">", 0)],
        [make_condition("MACD", "macd", {"fast_length": 12, "slow_length": 26, "signal_length": 9}, "<", 0)],
    ),
    "BB_band": make_strategy(
        "BB_band",
        [make_condition("BB", "pctb", {"period": 20, "mult": 2.0}, "<", 0.2)],
        [make_condition("BB", "pctb", {"period": 20, "mult": 2.0}, ">", 0.8)],
    ),
    "SMA_trend": make_strategy(
        "SMA_trend",
        [make_condition("SMA", "value", {"period": 20}, "<", 99999999)],
        [make_condition("SMA", "value", {"period": 20}, ">", 0)],
    ),
    "STOCH_oversold": make_strategy(
        "STOCH_oversold",
        [make_condition("STOCH", "k", {"k_period": 14, "d_period": 3, "smooth": 3}, "<", 30)],
        [make_condition("STOCH", "k", {"k_period": 14, "d_period": 3, "smooth": 3}, ">", 70)],
    ),
    "RSI_SMA_combo": make_strategy(
        "RSI_SMA_combo",
        [
            make_condition("RSI", "value", {"period": 14}, "<", 45),
        ],
        [
            make_condition("RSI", "value", {"period": 14}, ">", 55),
        ],
    ),
}


def run_custom_backtest(exchange: str, symbol: str, strategy_name: str, strategy: dict):
    """Execute custom backtest"""
    payload = {
        "exchange": exchange,
        "symbol": symbol,
        "timeframe": "1D",
        "days": 180,
        "initial_capital": 10000000,
        "strategy": strategy,
    }
    try:
        resp = requests.post(API_CUSTOM, json=payload, timeout=120)
        data = resp.json()
        return {
            "success": data.get("success", False),
            "trades": len(data.get("trades", [])) if data.get("trades") else 0,
            "net_profit_pct": data.get("metrics", {}).get("net_profit_pct", 0) if data.get("metrics") else 0,
            "message": data.get("message") or data.get("detail"),
        }
    except Exception as e:
        return {"success": False, "trades": 0, "net_profit_pct": 0, "message": str(e)}


def run_mr_backtest(exchange: str, symbol: str):
    """Execute MR backtest"""
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
            "trades": len(data.get("trades", [])) if data.get("trades") else 0,
            "net_profit_pct": data.get("metrics", {}).get("net_profit_pct", 0) if data.get("metrics") else 0,
            "message": data.get("message"),
        }
    except Exception as e:
        return {"success": False, "trades": 0, "net_profit_pct": 0, "message": str(e)}


def run_trend_backtest(exchange: str, symbol: str):
    """Execute Trend backtest"""
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
            "trades": len(data.get("trades", [])) if data.get("trades") else 0,
            "net_profit_pct": data.get("metrics", {}).get("net_profit_pct", 0) if data.get("metrics") else 0,
            "message": data.get("message"),
        }
    except Exception as e:
        return {"success": False, "trades": 0, "net_profit_pct": 0, "message": str(e)}


def main():
    print("=" * 80)
    print("Cross Validation Test: 6 strategies x 6 exchanges + MR/Trend")
    print(f"Start: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 80)

    results = []

    # PART 1: Custom Strategy Tests (6 strategies x 6 exchanges = 36 tests)
    print("\n[PART 1] Custom Strategy Tests (36)")
    print("-" * 80)

    for exchange, symbol in EXCHANGE_SYMBOLS.items():
        for strat_name, strat_config in STRATEGIES.items():
            result = run_custom_backtest(exchange, symbol, strat_name, strat_config)
            status = "OK" if result["success"] else "FAIL"
            print(f"  [{status:4}] {exchange:10} | {strat_name:15} | trades: {result['trades']:3} | return: {result['net_profit_pct']:+8.2f}%")
            results.append({
                "type": "Custom",
                "exchange": exchange,
                "strategy": strat_name,
                **result,
            })

    # PART 2: MR + Trend Tests (6 exchanges x 2 strategies = 12 tests)
    print("\n[PART 2] MR/Trend Strategy Tests (12)")
    print("-" * 80)

    for exchange, symbol in EXCHANGE_SYMBOLS.items():
        # MR
        mr_result = run_mr_backtest(exchange, symbol)
        status = "OK" if mr_result["success"] else "FAIL"
        print(f"  [{status:4}] {exchange:10} | MR              | trades: {mr_result['trades']:3} | return: {mr_result['net_profit_pct']:+8.2f}%")
        results.append({"type": "MR", "exchange": exchange, "strategy": "MR", **mr_result})

        # Trend
        trend_result = run_trend_backtest(exchange, symbol)
        status = "OK" if trend_result["success"] else "FAIL"
        print(f"  [{status:4}] {exchange:10} | Trend           | trades: {trend_result['trades']:3} | return: {trend_result['net_profit_pct']:+8.2f}%")
        results.append({"type": "Trend", "exchange": exchange, "strategy": "Trend", **trend_result})

    # Summary
    print("\n" + "=" * 80)
    print("SUMMARY")
    print("=" * 80)

    custom_results = [r for r in results if r["type"] == "Custom"]
    mr_results = [r for r in results if r["type"] == "MR"]
    trend_results = [r for r in results if r["type"] == "Trend"]

    custom_success = sum(1 for r in custom_results if r["success"])
    mr_success = sum(1 for r in mr_results if r["success"])
    trend_success = sum(1 for r in trend_results if r["success"])

    print(f"\nCustom Strategies: {custom_success}/{len(custom_results)}")
    print(f"MR Strategy:       {mr_success}/{len(mr_results)}")
    print(f"Trend Strategy:    {trend_success}/{len(trend_results)}")
    print(f"Total:             {custom_success + mr_success + trend_success}/{len(results)}")

    # Failed tests
    failed = [r for r in results if not r["success"]]
    if failed:
        print("\n[Failed Tests]")
        for r in failed:
            msg = str(r.get('message', 'Unknown error'))[:60]
            print(f"  - {r['type']}/{r['exchange']}/{r['strategy']}: {msg}")

    print(f"\nEnd: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

    return custom_success + mr_success + trend_success, len(results) - (custom_success + mr_success + trend_success)


if __name__ == "__main__":
    success, failed = main()
    print(f"\n{'='*80}")
    print(f"Final: {success} passed, {failed} failed")
    print(f"{'='*80}")

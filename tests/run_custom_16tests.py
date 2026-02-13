#!/usr/bin/env python
"""
16 Custom Strategy Tests as specified in the requirements
"""

import requests
from datetime import datetime

API_CUSTOM = "https://qube-system.com/api/premium/backtest/custom"
API_MR = "https://qube-system.com/api/premium/backtest/mr"
API_TREND = "https://qube-system.com/api/premium/backtest/trend"


def make_condition(indicator, output, params, operator, compare_type, compare_value=None,
                   compare_indicator=None, compare_output=None, compare_params=None):
    cond = {
        "indicator": indicator,
        "output": output,
        "params": params,
        "operator": operator,
        "compare_type": compare_type,
    }
    if compare_type == "value":
        cond["compare_value"] = compare_value
    else:
        cond["compare_indicator"] = compare_indicator
        cond["compare_output"] = compare_output
        cond["compare_params"] = compare_params or {}
    return cond


def make_strategy(name, entry_conditions, exit_conditions):
    return {
        "name": name,
        "entry_rules": {"groups": [{"conditions": entry_conditions, "logic": "AND"}]},
        "exit_rules": {"groups": [{"conditions": exit_conditions, "logic": "AND"}]},
        "position_size_pct": 100.0,
        "commission_pct": 0.015,
    }


# 16 Test Cases
TEST_CASES = [
    # 1. RSI basic
    {
        "name": "RSI 역추세",
        "exchange": "OKX", "symbol": "BTC-USDT-SWAP", "days": 365,
        "strategy": make_strategy("RSI",
            [make_condition("RSI", "value", {"period": 14}, "<", "value", 30)],
            [make_condition("RSI", "value", {"period": 14}, ">", "value", 70)]
        )
    },
    # 2. MACD cross
    {
        "name": "MACD 크로스",
        "exchange": "BINANCE", "symbol": "ETHUSDT", "days": 365,
        "strategy": make_strategy("MACD",
            [make_condition("MACD", "macd", {"fast_length": 12, "slow_length": 26, "signal_length": 9},
                           "cross_above", "indicator", compare_indicator="MACD", compare_output="signal",
                           compare_params={"fast_length": 12, "slow_length": 26, "signal_length": 9})],
            [make_condition("MACD", "macd", {"fast_length": 12, "slow_length": 26, "signal_length": 9},
                           "cross_below", "indicator", compare_indicator="MACD", compare_output="signal",
                           compare_params={"fast_length": 12, "slow_length": 26, "signal_length": 9})]
        )
    },
    # 3. BB reversal
    {
        "name": "볼린저 반전",
        "exchange": "BYBIT", "symbol": "BTCUSDT", "days": 365,
        "strategy": make_strategy("BB",
            [make_condition("PRICE", "close", {}, "<", "indicator",
                           compare_indicator="BB", compare_output="lower", compare_params={"period": 20, "std_mult": 2.0})],
            [make_condition("PRICE", "close", {}, ">", "indicator",
                           compare_indicator="BB", compare_output="upper", compare_params={"period": 20, "std_mult": 2.0})]
        )
    },
    # 4. SMA cross
    {
        "name": "SMA 크로스",
        "exchange": "OKX", "symbol": "BTC-USDT-SWAP", "days": 730,
        "strategy": make_strategy("SMA",
            [make_condition("SMA", "value", {"period": 20}, "cross_above", "indicator",
                           compare_indicator="SMA", compare_output="value", compare_params={"period": 50})],
            [make_condition("SMA", "value", {"period": 20}, "cross_below", "indicator",
                           compare_indicator="SMA", compare_output="value", compare_params={"period": 50})]
        )
    },
    # 5. EMA cross
    {
        "name": "EMA 크로스",
        "exchange": "BINANCE", "symbol": "ETHUSDT", "days": 365,
        "strategy": make_strategy("EMA",
            [make_condition("EMA", "value", {"period": 12}, "cross_above", "indicator",
                           compare_indicator="EMA", compare_output="value", compare_params={"period": 26})],
            [make_condition("EMA", "value", {"period": 12}, "cross_below", "indicator",
                           compare_indicator="EMA", compare_output="value", compare_params={"period": 26})]
        )
    },
    # 6. Stochastic
    {
        "name": "스토캐스틱",
        "exchange": "OKX", "symbol": "BTC-USDT-SWAP", "days": 365,
        "strategy": make_strategy("STOCH",
            [make_condition("STOCH", "k", {"k_period": 14, "d_period": 3, "smooth": 3}, "<", "value", 20)],
            [make_condition("STOCH", "k", {"k_period": 14, "d_period": 3, "smooth": 3}, ">", "value", 80)]
        )
    },
    # 7. Supertrend
    {
        "name": "슈퍼트렌드",
        "exchange": "BYBIT", "symbol": "BTCUSDT", "days": 730,
        "strategy": make_strategy("SUPERTREND",
            [make_condition("SUPERTREND", "direction", {"atr_len": 20, "factor": 5.0}, "cross_below", "value", 0)],
            [make_condition("SUPERTREND", "direction", {"atr_len": 20, "factor": 5.0}, "cross_above", "value", 0)]
        )
    },
    # 8. ADX
    {
        "name": "ADX 추세",
        "exchange": "OKX", "symbol": "BTC-USDT-SWAP", "days": 365,
        "strategy": make_strategy("ADX",
            [make_condition("ADX", "adx", {"period": 14}, ">", "value", 25),
             make_condition("ADX", "plus_di", {"period": 14}, ">", "indicator",
                           compare_indicator="ADX", compare_output="minus_di", compare_params={"period": 14})],
            [make_condition("ADX", "adx", {"period": 14}, ">", "value", 25),
             make_condition("ADX", "minus_di", {"period": 14}, ">", "indicator",
                           compare_indicator="ADX", compare_output="plus_di", compare_params={"period": 14})]
        )
    },
    # 9. CCI
    {
        "name": "CCI",
        "exchange": "BINANCE", "symbol": "ETHUSDT", "days": 365,
        "strategy": make_strategy("CCI",
            [make_condition("CCI", "value", {"period": 20}, "<", "value", -100)],
            [make_condition("CCI", "value", {"period": 20}, ">", "value", 100)]
        )
    },
    # 10. Ichimoku
    {
        "name": "일목균형",
        "exchange": "OKX", "symbol": "BTC-USDT-SWAP", "days": 730,
        "strategy": make_strategy("ICHIMOKU",
            [make_condition("PRICE", "close", {}, ">", "indicator",
                           compare_indicator="ICHIMOKU", compare_output="senkou_a",
                           compare_params={"tenkan_len": 9, "kijun_len": 26, "senkou_len": 52}),
             make_condition("ICHIMOKU", "tenkan", {"tenkan_len": 9, "kijun_len": 26, "senkou_len": 52}, ">", "indicator",
                           compare_indicator="ICHIMOKU", compare_output="kijun",
                           compare_params={"tenkan_len": 9, "kijun_len": 26, "senkou_len": 52})],
            [make_condition("PRICE", "close", {}, "<", "indicator",
                           compare_indicator="ICHIMOKU", compare_output="senkou_b",
                           compare_params={"tenkan_len": 9, "kijun_len": 26, "senkou_len": 52})]
        )
    },
    # 11. KIS_KR RSI
    {
        "name": "RSI 역추세 (삼성)",
        "exchange": "KIS_KR", "symbol": "005930", "days": 730,
        "strategy": make_strategy("RSI",
            [make_condition("RSI", "value", {"period": 14}, "<", "value", 35)],
            [make_condition("RSI", "value", {"period": 14}, ">", "value", 65)]
        )
    },
    # 12. KIS_KR SMA
    {
        "name": "SMA 크로스 (SK하이닉스)",
        "exchange": "KIS_KR", "symbol": "000660", "days": 730,
        "strategy": make_strategy("SMA",
            [make_condition("SMA", "value", {"period": 20}, "cross_above", "indicator",
                           compare_indicator="SMA", compare_output="value", compare_params={"period": 60})],
            [make_condition("SMA", "value", {"period": 20}, "cross_below", "indicator",
                           compare_indicator="SMA", compare_output="value", compare_params={"period": 60})]
        )
    },
    # 13. KIS_US MACD
    {
        "name": "MACD 크로스 (AAPL)",
        "exchange": "KIS_US", "symbol": "AAPL", "days": 730,
        "strategy": make_strategy("MACD",
            [make_condition("MACD", "macd", {"fast_length": 12, "slow_length": 26, "signal_length": 9},
                           "cross_above", "indicator", compare_indicator="MACD", compare_output="signal",
                           compare_params={"fast_length": 12, "slow_length": 26, "signal_length": 9})],
            [make_condition("MACD", "macd", {"fast_length": 12, "slow_length": 26, "signal_length": 9},
                           "cross_below", "indicator", compare_indicator="MACD", compare_output="signal",
                           compare_params={"fast_length": 12, "slow_length": 26, "signal_length": 9})]
        )
    },
    # 14. KIS_US BB
    {
        "name": "볼린저 반전 (MSFT)",
        "exchange": "KIS_US", "symbol": "MSFT", "days": 730,
        "strategy": make_strategy("BB",
            [make_condition("PRICE", "close", {}, "<", "indicator",
                           compare_indicator="BB", compare_output="lower", compare_params={"period": 20, "std_mult": 2.0})],
            [make_condition("PRICE", "close", {}, ">", "indicator",
                           compare_indicator="BB", compare_output="upper", compare_params={"period": 20, "std_mult": 2.0})]
        )
    },
    # 15. Composite RSI + SMA
    {
        "name": "복합전략 RSI+SMA",
        "exchange": "OKX", "symbol": "BTC-USDT-SWAP", "days": 365,
        "strategy": make_strategy("RSI+SMA",
            [make_condition("RSI", "value", {"period": 14}, "<", "value", 30),
             make_condition("SMA", "value", {"period": 20}, ">", "indicator",
                           compare_indicator="SMA", compare_output="value", compare_params={"period": 50})],
            [make_condition("RSI", "value", {"period": 14}, ">", "value", 70)]
        )
    },
    # 16. UPBIT composite
    {
        "name": "복합전략 MACD+ADX",
        "exchange": "UPBIT", "symbol": "KRW-BTC", "days": 365,
        "strategy": make_strategy("MACD+ADX",
            [make_condition("MACD", "macd", {"fast_length": 12, "slow_length": 26, "signal_length": 9},
                           "cross_above", "indicator", compare_indicator="MACD", compare_output="signal",
                           compare_params={"fast_length": 12, "slow_length": 26, "signal_length": 9}),
             make_condition("ADX", "adx", {"period": 14}, ">", "value", 25)],
            [make_condition("MACD", "macd", {"fast_length": 12, "slow_length": 26, "signal_length": 9},
                           "cross_below", "indicator", compare_indicator="MACD", compare_output="signal",
                           compare_params={"fast_length": 12, "slow_length": 26, "signal_length": 9})]
        )
    },
]

# MR/Trend tests (17-20)
MR_TREND_TESTS = [
    {"type": "MR", "exchange": "OKX", "symbol": "BTC-USDT-SWAP", "timeframe": "1H", "days": 365},
    {"type": "MR", "exchange": "KIS_KR", "symbol": "005930", "timeframe": "1D", "days": 730},
    {"type": "TREND", "exchange": "OKX", "symbol": "BTC-USDT-SWAP", "timeframe": "1D", "days": 730},
    {"type": "TREND", "exchange": "KIS_KR", "symbol": "005930", "timeframe": "1D", "days": 365},
]


def run_custom_test(test_case):
    payload = {
        "exchange": test_case["exchange"],
        "symbol": test_case["symbol"],
        "timeframe": "1D",
        "days": test_case["days"],
        "initial_capital": 10000000,
        "strategy": test_case["strategy"],
    }
    try:
        resp = requests.post(API_CUSTOM, json=payload, timeout=120)
        data = resp.json()
        return {
            "success": data.get("success", False),
            "trades": len(data.get("trades", [])) if data.get("trades") else 0,
            "return_pct": data.get("metrics", {}).get("net_profit_pct", 0),
            "message": data.get("message"),
        }
    except Exception as e:
        return {"success": False, "trades": 0, "return_pct": 0, "message": str(e)}


def run_mr_trend_test(test):
    api = API_MR if test["type"] == "MR" else API_TREND
    payload = {
        "exchange": test["exchange"],
        "symbol": test["symbol"],
        "timeframe": test["timeframe"],
        "days": test["days"],
        "initial_capital": 10000000,
    }
    try:
        resp = requests.post(api, json=payload, timeout=120)
        data = resp.json()
        return {
            "success": data.get("success", False),
            "trades": len(data.get("trades", [])) if data.get("trades") else 0,
            "return_pct": data.get("metrics", {}).get("net_profit_pct", 0),
            "message": data.get("message"),
        }
    except Exception as e:
        return {"success": False, "trades": 0, "return_pct": 0, "message": str(e)}


def main():
    print("=" * 80)
    print("Custom Strategy 16 Tests + MR/Trend 4 Tests = 20 Total")
    print(f"Start: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 80)

    results = []

    # Custom tests (1-16)
    print("\n[Custom Strategy Tests 1-16]")
    print("-" * 80)
    for i, tc in enumerate(TEST_CASES, 1):
        result = run_custom_test(tc)
        status = "OK" if result["success"] else "FAIL"
        print(f"  #{i:2} [{status:4}] {tc['name']:25} | {tc['exchange']:8} | trades: {result['trades']:3} | return: {result['return_pct']:+8.2f}%")
        results.append({"no": i, "name": tc["name"], "type": "Custom", **result})

    # MR/Trend tests (17-20)
    print("\n[MR/Trend Tests 17-20]")
    print("-" * 80)
    for i, tc in enumerate(MR_TREND_TESTS, 17):
        result = run_mr_trend_test(tc)
        status = "OK" if result["success"] else "FAIL"
        name = f"{tc['type']} {tc['exchange']} {tc['timeframe']}"
        print(f"  #{i:2} [{status:4}] {name:25} | {tc['symbol']:15} | trades: {result['trades']:3} | return: {result['return_pct']:+8.2f}%")
        results.append({"no": i, "name": name, "type": tc["type"], **result})

    # Summary
    print("\n" + "=" * 80)
    print("SUMMARY")
    print("=" * 80)

    passed = sum(1 for r in results if r["success"])
    failed = len(results) - passed

    print(f"\nPassed: {passed}/20")
    print(f"Failed: {failed}/20")

    if failed > 0:
        print("\n[Failed Tests]")
        for r in results:
            if not r["success"]:
                print(f"  #{r['no']} {r['name']}: {r.get('message', 'Unknown')}")

    print(f"\nEnd: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    return passed, failed


if __name__ == "__main__":
    passed, failed = main()
    print(f"\n{'='*80}")
    print(f"Final: {passed} passed, {failed} failed")
    print(f"{'='*80}")

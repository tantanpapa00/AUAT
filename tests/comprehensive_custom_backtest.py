#!/usr/bin/env python
"""
Comprehensive Custom Strategy Backtest Test
- 6 exchanges x multiple symbols x various indicator combinations
- Tests all 15 indicators with different presets
"""

import requests
import json
from datetime import datetime
from typing import List, Dict, Any

API_BASE = "https://qube-system.com/api/premium/backtest/custom"

# 거래소별 테스트 심볼
TEST_CASES = [
    # OKX
    {"exchange": "OKX", "symbol": "BTC-USDT-SWAP", "timeframe": "1D", "days": 180},
    {"exchange": "OKX", "symbol": "ETH-USDT-SWAP", "timeframe": "4H", "days": 90},
    {"exchange": "OKX", "symbol": "SOL-USDT", "timeframe": "1H", "days": 30},

    # Binance
    {"exchange": "BINANCE", "symbol": "BTCUSDT", "timeframe": "1D", "days": 180},
    {"exchange": "BINANCE", "symbol": "ETHUSDT", "timeframe": "4H", "days": 90},
    {"exchange": "BINANCE", "symbol": "SOLUSDT", "timeframe": "1H", "days": 30},

    # Bybit
    {"exchange": "BYBIT", "symbol": "BTCUSDT", "timeframe": "1D", "days": 180},
    {"exchange": "BYBIT", "symbol": "ETHUSDT", "timeframe": "4H", "days": 90},

    # Upbit (KRW)
    {"exchange": "UPBIT", "symbol": "KRW-BTC", "timeframe": "1D", "days": 180},
    {"exchange": "UPBIT", "symbol": "KRW-ETH", "timeframe": "4H", "days": 90},

    # KIS_KR (국내주식)
    {"exchange": "KIS_KR", "symbol": "005930", "timeframe": "1D", "days": 180},  # 삼성전자
    {"exchange": "KIS_KR", "symbol": "000660", "timeframe": "1D", "days": 180},  # SK하이닉스

    # KIS_US (해외주식)
    {"exchange": "KIS_US", "symbol": "AAPL", "timeframe": "1D", "days": 180},
    {"exchange": "KIS_US", "symbol": "NVDA", "timeframe": "1D", "days": 180},
]

# 다양한 전략 프리셋
STRATEGY_PRESETS = {
    "RSI_과매도": {
        "name": "RSI 과매도 전략",
        "entry_rules": {
            "groups": [{
                "logic": "AND",
                "conditions": [{
                    "indicator": "RSI", "output": "value", "params": {"period": 14},
                    "operator": "<", "compare_type": "value", "compare_value": 30
                }]
            }]
        },
        "exit_rules": {
            "groups": [{
                "logic": "AND",
                "conditions": [{
                    "indicator": "RSI", "output": "value", "params": {"period": 14},
                    "operator": ">", "compare_type": "value", "compare_value": 70
                }]
            }]
        }
    },
    "MACD_골든크로스": {
        "name": "MACD 골든크로스 전략",
        "entry_rules": {
            "groups": [{
                "logic": "AND",
                "conditions": [{
                    "indicator": "MACD", "output": "macd",
                    "params": {"fast_length": 12, "slow_length": 26, "signal_length": 9},
                    "operator": "cross_above", "compare_type": "indicator",
                    "compare_indicator": "MACD", "compare_output": "signal",
                    "compare_params": {"fast_length": 12, "slow_length": 26, "signal_length": 9}
                }]
            }]
        },
        "exit_rules": {
            "groups": [{
                "logic": "AND",
                "conditions": [{
                    "indicator": "MACD", "output": "macd",
                    "params": {"fast_length": 12, "slow_length": 26, "signal_length": 9},
                    "operator": "cross_below", "compare_type": "indicator",
                    "compare_indicator": "MACD", "compare_output": "signal",
                    "compare_params": {"fast_length": 12, "slow_length": 26, "signal_length": 9}
                }]
            }]
        }
    },
    "BB_하단터치": {
        "name": "볼린저밴드 하단 터치 전략",
        "entry_rules": {
            "groups": [{
                "logic": "AND",
                "conditions": [{
                    "indicator": "PRICE", "output": "close", "params": {},
                    "operator": "<", "compare_type": "indicator",
                    "compare_indicator": "BB", "compare_output": "lower",
                    "compare_params": {"period": 20, "std_mult": 2.0}
                }]
            }]
        },
        "exit_rules": {
            "groups": [{
                "logic": "AND",
                "conditions": [{
                    "indicator": "PRICE", "output": "close", "params": {},
                    "operator": ">", "compare_type": "indicator",
                    "compare_indicator": "BB", "compare_output": "upper",
                    "compare_params": {"period": 20, "std_mult": 2.0}
                }]
            }]
        }
    },
    "SUPERTREND": {
        "name": "슈퍼트렌드 전략",
        "entry_rules": {
            "groups": [{
                "logic": "AND",
                "conditions": [{
                    "indicator": "SUPERTREND", "output": "direction",
                    "params": {"atr_len": 20, "factor": 5.0},
                    "operator": "cross_below", "compare_type": "value", "compare_value": 0
                }]
            }]
        },
        "exit_rules": {
            "groups": [{
                "logic": "AND",
                "conditions": [{
                    "indicator": "SUPERTREND", "output": "direction",
                    "params": {"atr_len": 20, "factor": 5.0},
                    "operator": "cross_above", "compare_type": "value", "compare_value": 0
                }]
            }]
        }
    },
    "STOCH_골든크로스": {
        "name": "스토캐스틱 골든크로스",
        "entry_rules": {
            "groups": [{
                "logic": "AND",
                "conditions": [
                    {
                        "indicator": "STOCH", "output": "k",
                        "params": {"k_period": 14, "d_period": 3, "slowing": 3},
                        "operator": "<", "compare_type": "value", "compare_value": 20
                    },
                    {
                        "indicator": "STOCH", "output": "k",
                        "params": {"k_period": 14, "d_period": 3, "slowing": 3},
                        "operator": "cross_above", "compare_type": "indicator",
                        "compare_indicator": "STOCH", "compare_output": "d",
                        "compare_params": {"k_period": 14, "d_period": 3, "slowing": 3}
                    }
                ]
            }]
        },
        "exit_rules": {
            "groups": [{
                "logic": "AND",
                "conditions": [{
                    "indicator": "STOCH", "output": "k",
                    "params": {"k_period": 14, "d_period": 3, "slowing": 3},
                    "operator": ">", "compare_type": "value", "compare_value": 80
                }]
            }]
        }
    },
    "이동평균_크로스": {
        "name": "SMA 20/50 크로스",
        "entry_rules": {
            "groups": [{
                "logic": "AND",
                "conditions": [{
                    "indicator": "SMA", "output": "value", "params": {"period": 20},
                    "operator": "cross_above", "compare_type": "indicator",
                    "compare_indicator": "SMA", "compare_output": "value",
                    "compare_params": {"period": 50}
                }]
            }]
        },
        "exit_rules": {
            "groups": [{
                "logic": "AND",
                "conditions": [{
                    "indicator": "SMA", "output": "value", "params": {"period": 20},
                    "operator": "cross_below", "compare_type": "indicator",
                    "compare_indicator": "SMA", "compare_output": "value",
                    "compare_params": {"period": 50}
                }]
            }]
        }
    },
    "ADX_강한추세": {
        "name": "ADX 강한 추세 전략",
        "entry_rules": {
            "groups": [{
                "logic": "AND",
                "conditions": [
                    {
                        "indicator": "ADX", "output": "adx", "params": {"period": 14},
                        "operator": ">", "compare_type": "value", "compare_value": 25
                    },
                    {
                        "indicator": "ADX", "output": "plus_di", "params": {"period": 14},
                        "operator": ">", "compare_type": "indicator",
                        "compare_indicator": "ADX", "compare_output": "minus_di",
                        "compare_params": {"period": 14}
                    }
                ]
            }]
        },
        "exit_rules": {
            "groups": [{
                "logic": "OR",
                "conditions": [
                    {
                        "indicator": "ADX", "output": "adx", "params": {"period": 14},
                        "operator": "<", "compare_type": "value", "compare_value": 20
                    },
                    {
                        "indicator": "ADX", "output": "minus_di", "params": {"period": 14},
                        "operator": ">", "compare_type": "indicator",
                        "compare_indicator": "ADX", "compare_output": "plus_di",
                        "compare_params": {"period": 14}
                    }
                ]
            }]
        }
    },
    "ICHIMOKU_구름위": {
        "name": "일목균형표 구름 위 전략",
        "entry_rules": {
            "groups": [{
                "logic": "AND",
                "conditions": [
                    {
                        "indicator": "PRICE", "output": "close", "params": {},
                        "operator": ">", "compare_type": "indicator",
                        "compare_indicator": "ICHIMOKU", "compare_output": "senkou_a",
                        "compare_params": {"tenkan_len": 9, "kijun_len": 26, "senkou_len": 52}
                    },
                    {
                        "indicator": "ICHIMOKU", "output": "tenkan",
                        "params": {"tenkan_len": 9, "kijun_len": 26, "senkou_len": 52},
                        "operator": "cross_above", "compare_type": "indicator",
                        "compare_indicator": "ICHIMOKU", "compare_output": "kijun",
                        "compare_params": {"tenkan_len": 9, "kijun_len": 26, "senkou_len": 52}
                    }
                ]
            }]
        },
        "exit_rules": {
            "groups": [{
                "logic": "AND",
                "conditions": [{
                    "indicator": "PRICE", "output": "close", "params": {},
                    "operator": "<", "compare_type": "indicator",
                    "compare_indicator": "ICHIMOKU", "compare_output": "senkou_b",
                    "compare_params": {"tenkan_len": 9, "kijun_len": 26, "senkou_len": 52}
                }]
            }]
        }
    },
    "CCI_과매도": {
        "name": "CCI 과매도 전략",
        "entry_rules": {
            "groups": [{
                "logic": "AND",
                "conditions": [{
                    "indicator": "CCI", "output": "value", "params": {"period": 20},
                    "operator": "cross_above", "compare_type": "value", "compare_value": -100
                }]
            }]
        },
        "exit_rules": {
            "groups": [{
                "logic": "AND",
                "conditions": [{
                    "indicator": "CCI", "output": "value", "params": {"period": 20},
                    "operator": ">", "compare_type": "value", "compare_value": 100
                }]
            }]
        }
    },
    "복합_RSI_MACD": {
        "name": "RSI + MACD 복합 전략",
        "entry_rules": {
            "groups": [{
                "logic": "AND",
                "conditions": [
                    {
                        "indicator": "RSI", "output": "value", "params": {"period": 14},
                        "operator": "<", "compare_type": "value", "compare_value": 40
                    },
                    {
                        "indicator": "MACD", "output": "histogram",
                        "params": {"fast_length": 12, "slow_length": 26, "signal_length": 9},
                        "operator": "cross_above", "compare_type": "value", "compare_value": 0
                    }
                ]
            }]
        },
        "exit_rules": {
            "groups": [{
                "logic": "OR",
                "conditions": [
                    {
                        "indicator": "RSI", "output": "value", "params": {"period": 14},
                        "operator": ">", "compare_type": "value", "compare_value": 70
                    },
                    {
                        "indicator": "MACD", "output": "histogram",
                        "params": {"fast_length": 12, "slow_length": 26, "signal_length": 9},
                        "operator": "cross_below", "compare_type": "value", "compare_value": 0
                    }
                ]
            }]
        }
    },
}


def run_backtest(test_case: dict, strategy: dict) -> dict:
    """Run a single backtest"""
    payload = {
        "exchange": test_case["exchange"],
        "symbol": test_case["symbol"],
        "timeframe": test_case["timeframe"],
        "days": test_case["days"],
        "initial_capital": 10000000,
        "strategy": {
            **strategy,
            "position_size_pct": 100,
            "stop_loss_pct": None,
            "take_profit_pct": None,
            "commission_pct": 0.015,
        }
    }

    try:
        resp = requests.post(API_BASE, json=payload, timeout=120)
        data = resp.json()
        return {
            "success": data.get("success", False),
            "message": data.get("message"),
            "metrics": data.get("metrics"),
            "trade_count": len(data.get("trades", [])) if data.get("trades") else 0,
        }
    except Exception as e:
        return {"success": False, "message": str(e), "metrics": None, "trade_count": 0}


def main():
    print("=" * 80)
    print("커스텀 전략 종합 백테스트")
    print(f"시작 시간: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 80)

    results = []
    total_tests = len(TEST_CASES) * len(STRATEGY_PRESETS)
    current = 0

    for test_case in TEST_CASES:
        for strategy_name, strategy in STRATEGY_PRESETS.items():
            current += 1
            test_id = f"{test_case['exchange']}/{test_case['symbol']}/{strategy_name}"
            print(f"\n[{current}/{total_tests}] {test_id}")

            result = run_backtest(test_case, strategy)

            if result["success"]:
                m = result.get("metrics", {})
                print(f"  > SUCCESS | trades: {result['trade_count']} | "
                      f"return: {m.get('net_profit_pct', 0):.2f}% | "
                      f"MDD: {m.get('max_drawdown_pct', 0):.2f}%")
            else:
                print(f"  > FAILED | {result.get('message', 'Unknown error')}")

            results.append({
                "exchange": test_case["exchange"],
                "symbol": test_case["symbol"],
                "timeframe": test_case["timeframe"],
                "strategy": strategy_name,
                **result
            })

    # 결과 요약
    print("\n" + "=" * 80)
    print("SUMMARY")
    print("=" * 80)

    success_count = sum(1 for r in results if r["success"])
    fail_count = len(results) - success_count

    print(f"\nTotal tests: {len(results)}")
    print(f"Success: {success_count} ({100*success_count/len(results):.1f}%)")
    print(f"Failed: {fail_count}")

    # 거래소별 결과
    print("\n[By Exchange]")
    for exchange in ["OKX", "BINANCE", "BYBIT", "UPBIT", "KIS_KR", "KIS_US"]:
        ex_results = [r for r in results if r["exchange"] == exchange]
        ex_success = sum(1 for r in ex_results if r["success"])
        print(f"  {exchange}: {ex_success}/{len(ex_results)}")

    # 전략별 결과
    print("\n[By Strategy]")
    for strategy_name in STRATEGY_PRESETS.keys():
        st_results = [r for r in results if r["strategy"] == strategy_name]
        st_success = sum(1 for r in st_results if r["success"])
        print(f"  {strategy_name}: {st_success}/{len(st_results)}")

    # 실패 목록
    if fail_count > 0:
        print("\n[Failed Tests]")
        for r in results:
            if not r["success"]:
                print(f"  - {r['exchange']}/{r['symbol']}/{r['strategy']}: {r.get('message', 'Unknown')}")

    # JSON으로 저장
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    output_file = f"tests/custom_backtest_results_{timestamp}.json"
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
    print(f"\nResults saved: {output_file}")

    return success_count, fail_count


if __name__ == "__main__":
    main()

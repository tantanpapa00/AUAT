#!/usr/bin/env python3
"""
전 거래소, 다양한 심볼 백테스트 스크립트.
역추세매매(MR) + 추세매매(Trend) 모두 테스트.
"""

import asyncio
import json
import httpx
from datetime import datetime
from typing import Dict, List, Any

BASE_URL = "https://qube-system.com/api/premium"

# 거래소별 테스트 심볼
EXCHANGE_SYMBOLS = {
    "OKX": ["BTC-USDT", "ETH-USDT", "SOL-USDT", "XRP-USDT", "DOGE-USDT"],
    "BINANCE": ["BTCUSDT", "ETHUSDT", "SOLUSDT", "XRPUSDT", "DOGEUSDT"],
    "BYBIT": ["BTCUSDT", "ETHUSDT", "SOLUSDT", "XRPUSDT", "DOGEUSDT"],
    "UPBIT": ["KRW-BTC", "KRW-ETH", "KRW-SOL", "KRW-XRP", "KRW-DOGE"],
    "KIS_KR": ["005930", "000660", "035420", "051910", "006400"],  # 삼성, SK하이닉스, NAVER, LG화학, 삼성SDI
    "KIS_US": ["AAPL", "MSFT", "NVDA", "GOOGL", "AMZN"],
}

# 역추세매매 프리셋 변형
MR_PRESETS = [
    {"name": "preset1", "osc_preset": "preset1", "osc_smooth_len": 20, "osc_threshold": 1.0},
    {"name": "preset2", "osc_preset": "preset2", "osc_smooth_len": 14, "osc_threshold": 0.7},
    {"name": "custom_aggressive", "osc_preset": "custom", "osc_smooth_len": 10, "osc_threshold": 0.8},
]

# 추세매매 프리셋 변형
TREND_PRESETS = [
    {"name": "default", "st_atr_len": 20, "st_factor": 5.0, "hard_sl_pct": 7.0},
    {"name": "tight_sl", "st_atr_len": 20, "st_factor": 5.0, "hard_sl_pct": 5.0},
    {"name": "loose_st", "st_atr_len": 14, "st_factor": 3.0, "hard_sl_pct": 7.0},
]


async def run_mr_backtest(client: httpx.AsyncClient, exchange: str, symbol: str, preset: dict) -> Dict:
    """역추세매매 백테스트 실행."""
    payload = {
        "exchange": exchange,
        "symbol": symbol,
        "timeframe": "1D",
        "htf_tf": "1D",
        "days": 365,
        "initial_capital": 10000000,
        "osc_preset": preset["osc_preset"],
        "osc_smooth_len": preset["osc_smooth_len"],
        "osc_threshold": preset["osc_threshold"],
        "cash_use_pct": 55.0,
        "use_4regime": True,
    }

    try:
        resp = await client.post(f"{BASE_URL}/backtest/mr", json=payload, timeout=120)
        data = resp.json()
        if data.get("success"):
            metrics = data.get("metrics", {})
            return {
                "success": True,
                "exchange": exchange,
                "symbol": symbol,
                "preset": preset["name"],
                "total_profit_pct": metrics.get("total_profit_pct", 0),
                "mdd": metrics.get("max_drawdown_pct", 0),
                "total_trades": metrics.get("total_trades", 0),
                "win_rate": metrics.get("winning_pct", 0),
                "profit_factor": metrics.get("profit_factor", 0),
            }
        else:
            return {
                "success": False,
                "exchange": exchange,
                "symbol": symbol,
                "preset": preset["name"],
                "error": data.get("message", "Unknown error"),
            }
    except Exception as e:
        return {
            "success": False,
            "exchange": exchange,
            "symbol": symbol,
            "preset": preset["name"],
            "error": str(e),
        }


async def run_trend_backtest(client: httpx.AsyncClient, exchange: str, symbol: str, preset: dict) -> Dict:
    """추세매매 백테스트 실행."""
    # KIS는 asset_type=stock, 나머지는 crypto
    asset_type = "stock" if exchange.startswith("KIS") else "crypto"

    payload = {
        "exchange": exchange,
        "symbol": symbol,
        "signal_tf": "1D",
        "exit_tf": "1W",
        "htf_tf": "1W",
        "days": 365,
        "initial_capital": 10000000,
        "st_atr_len": preset["st_atr_len"],
        "st_factor": preset["st_factor"],
        "hard_sl_pct": preset["hard_sl_pct"],
        "asset_type": asset_type,
        "cash_use_pct": 100.0,
        "use_pyramiding": True,
    }

    try:
        resp = await client.post(f"{BASE_URL}/backtest/trend", json=payload, timeout=120)
        data = resp.json()
        if data.get("success"):
            metrics = data.get("metrics", {})
            return {
                "success": True,
                "exchange": exchange,
                "symbol": symbol,
                "preset": preset["name"],
                "total_profit_pct": metrics.get("total_profit_pct", 0),
                "mdd": metrics.get("max_drawdown_pct", 0),
                "total_trades": metrics.get("total_trades", 0),
                "win_rate": metrics.get("winning_pct", 0),
                "profit_factor": metrics.get("profit_factor", 0),
            }
        else:
            return {
                "success": False,
                "exchange": exchange,
                "symbol": symbol,
                "preset": preset["name"],
                "error": data.get("message", "Unknown error"),
            }
    except Exception as e:
        return {
            "success": False,
            "exchange": exchange,
            "symbol": symbol,
            "preset": preset["name"],
            "error": str(e),
        }


async def main():
    print("=" * 80)
    print("전 거래소 다중 심볼 백테스트 시작")
    print(f"시작 시간: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 80)

    mr_results = []
    trend_results = []

    async with httpx.AsyncClient() as client:
        # 1. 역추세매매 테스트
        print("\n[1] 역추세매매(MR) 백테스트")
        print("-" * 60)

        for exchange, symbols in EXCHANGE_SYMBOLS.items():
            for symbol in symbols:
                for preset in MR_PRESETS:
                    print(f"  MR | {exchange:10} | {symbol:15} | {preset['name']:20}", end=" ... ")
                    result = await run_mr_backtest(client, exchange, symbol, preset)
                    mr_results.append(result)

                    if result["success"]:
                        print(f"수익률 {result['total_profit_pct']:+.2f}%, MDD {result['mdd']:.2f}%, 거래 {result['total_trades']}회")
                    else:
                        print(f"실패: {result.get('error', 'Unknown')[:50]}")

        # 2. 추세매매 테스트
        print("\n[2] 추세매매(Trend) 백테스트")
        print("-" * 60)

        for exchange, symbols in EXCHANGE_SYMBOLS.items():
            for symbol in symbols:
                for preset in TREND_PRESETS:
                    print(f"  TR | {exchange:10} | {symbol:15} | {preset['name']:20}", end=" ... ")
                    result = await run_trend_backtest(client, exchange, symbol, preset)
                    trend_results.append(result)

                    if result["success"]:
                        print(f"수익률 {result['total_profit_pct']:+.2f}%, MDD {result['mdd']:.2f}%, 거래 {result['total_trades']}회")
                    else:
                        print(f"실패: {result.get('error', 'Unknown')[:50]}")

    # 결과 요약
    print("\n" + "=" * 80)
    print("백테스트 결과 요약")
    print("=" * 80)

    # MR 결과 요약
    mr_success = [r for r in mr_results if r["success"]]
    mr_fail = [r for r in mr_results if not r["success"]]

    print(f"\n[역추세매매] 성공: {len(mr_success)}, 실패: {len(mr_fail)}")
    if mr_success:
        print("\n  상위 10 수익률:")
        sorted_mr = sorted(mr_success, key=lambda x: x["total_profit_pct"], reverse=True)[:10]
        for i, r in enumerate(sorted_mr, 1):
            print(f"    {i:2}. {r['exchange']:10} {r['symbol']:15} {r['preset']:20} | {r['total_profit_pct']:+8.2f}% | MDD {r['mdd']:6.2f}% | PF {r['profit_factor']:.2f}")

    # Trend 결과 요약
    trend_success = [r for r in trend_results if r["success"]]
    trend_fail = [r for r in trend_results if not r["success"]]

    print(f"\n[추세매매] 성공: {len(trend_success)}, 실패: {len(trend_fail)}")
    if trend_success:
        print("\n  상위 10 수익률:")
        sorted_trend = sorted(trend_success, key=lambda x: x["total_profit_pct"], reverse=True)[:10]
        for i, r in enumerate(sorted_trend, 1):
            print(f"    {i:2}. {r['exchange']:10} {r['symbol']:15} {r['preset']:20} | {r['total_profit_pct']:+8.2f}% | MDD {r['mdd']:6.2f}% | PF {r['profit_factor']:.2f}")

    # 실패 목록
    if mr_fail or trend_fail:
        print("\n  실패 목록:")
        for r in (mr_fail + trend_fail)[:10]:
            print(f"    - {r['exchange']} {r['symbol']} {r['preset']}: {r.get('error', 'Unknown')[:60]}")

    print(f"\n완료 시간: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 80)

    # JSON 파일로 저장
    with open("backtest_results.json", "w", encoding="utf-8") as f:
        json.dump({
            "timestamp": datetime.now().isoformat(),
            "mr_results": mr_results,
            "trend_results": trend_results,
        }, f, ensure_ascii=False, indent=2)
    print("\n결과가 backtest_results.json에 저장되었습니다.")


if __name__ == "__main__":
    asyncio.run(main())

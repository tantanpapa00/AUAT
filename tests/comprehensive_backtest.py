#!/usr/bin/env python3
"""
전 거래소 종합 백테스트 스크립트.
다양한 심볼 + 다양한 파라미터로 테스트하고 결과를 JSON/CSV로 저장.
"""

import asyncio
import json
import csv
import httpx
from datetime import datetime
from typing import Dict, List, Any
import sys

BASE_URL = "https://qube-system.com/api/premium"

# ============================================================================
# 거래소별 심볼 (확장)
# ============================================================================
EXCHANGE_SYMBOLS = {
    "OKX": [
        "BTC-USDT", "ETH-USDT", "SOL-USDT", "XRP-USDT", "DOGE-USDT",
        "ADA-USDT", "AVAX-USDT", "DOT-USDT", "LINK-USDT", "MATIC-USDT",
    ],
    "BINANCE": [
        "BTCUSDT", "ETHUSDT", "SOLUSDT", "XRPUSDT", "DOGEUSDT",
        "ADAUSDT", "AVAXUSDT", "DOTUSDT", "LINKUSDT", "MATICUSDT",
    ],
    "BYBIT": [
        "BTCUSDT", "ETHUSDT", "SOLUSDT", "XRPUSDT", "DOGEUSDT",
        "ADAUSDT", "AVAXUSDT", "DOTUSDT", "LINKUSDT",
    ],
    "UPBIT": [
        "KRW-BTC", "KRW-ETH", "KRW-SOL", "KRW-XRP", "KRW-DOGE",
        "KRW-ADA", "KRW-AVAX", "KRW-DOT", "KRW-LINK",
    ],
    "KIS_KR": [
        "005930",  # 삼성전자
        "000660",  # SK하이닉스
        "035420",  # NAVER
        "051910",  # LG화학
        "006400",  # 삼성SDI
        "035720",  # 카카오
        "068270",  # 셀트리온
        "207940",  # 삼성바이오로직스
        "005380",  # 현대차
        "000270",  # 기아
    ],
    "KIS_US": [
        "AAPL", "MSFT", "NVDA", "GOOGL", "AMZN",
        "META", "TSLA", "AMD", "AVGO", "NFLX",
    ],
}

# ============================================================================
# 전략 파라미터 변형
# ============================================================================
MR_VARIANTS = [
    {"name": "preset1_default", "osc_preset": "preset1", "osc_smooth_len": 20, "osc_threshold": 1.0, "use_4regime": True},
    {"name": "preset2_default", "osc_preset": "preset2", "osc_smooth_len": 14, "osc_threshold": 0.7, "use_4regime": True},
    {"name": "custom_aggressive", "osc_preset": "custom", "osc_smooth_len": 10, "osc_threshold": 0.6, "use_4regime": True},
    {"name": "custom_conservative", "osc_preset": "custom", "osc_smooth_len": 30, "osc_threshold": 1.2, "use_4regime": True},
    {"name": "no_regime", "osc_preset": "preset1", "osc_smooth_len": 20, "osc_threshold": 1.0, "use_4regime": False},
]

TREND_VARIANTS = [
    {"name": "default", "st_atr_len": 20, "st_factor": 5.0, "hard_sl_pct": 7.0, "use_pyramiding": True},
    {"name": "tight_sl", "st_atr_len": 20, "st_factor": 5.0, "hard_sl_pct": 5.0, "use_pyramiding": True},
    {"name": "loose_sl", "st_atr_len": 20, "st_factor": 5.0, "hard_sl_pct": 10.0, "use_pyramiding": True},
    {"name": "fast_st", "st_atr_len": 14, "st_factor": 3.0, "hard_sl_pct": 7.0, "use_pyramiding": True},
    {"name": "no_pyramid", "st_atr_len": 20, "st_factor": 5.0, "hard_sl_pct": 7.0, "use_pyramiding": False},
]

# ============================================================================
# 백테스트 함수
# ============================================================================
async def run_mr_backtest(client: httpx.AsyncClient, exchange: str, symbol: str, variant: dict) -> Dict:
    """역추세매매 백테스트."""
    initial_capital = 10000000 if exchange.startswith("KIS") or exchange == "UPBIT" else 10000

    payload = {
        "exchange": exchange,
        "symbol": symbol,
        "timeframe": "1D",
        "htf_tf": "1D",
        "days": 365,
        "initial_capital": initial_capital,
        "osc_preset": variant["osc_preset"],
        "osc_smooth_len": variant["osc_smooth_len"],
        "osc_threshold": variant["osc_threshold"],
        "use_4regime": variant["use_4regime"],
        "cash_use_pct": 55.0,
    }

    try:
        resp = await client.post(f"{BASE_URL}/backtest/mr", json=payload, timeout=120)
        data = resp.json()
        if data.get("success"):
            m = data.get("metrics", {})
            return {
                "success": True,
                "strategy": "MR",
                "exchange": exchange,
                "symbol": symbol,
                "variant": variant["name"],
                "total_return_pct": round(m.get("total_return_pct", 0), 2),
                "mdd": round(m.get("max_drawdown_pct", 0), 2),
                "total_trades": m.get("total_trades", 0),
                "win_rate": round(m.get("win_rate_pct", 0), 1),
                "profit_factor": round(m.get("profit_factor", 0), 2),
                "cagr": round(m.get("cagr_pct", 0), 2),
            }
        else:
            return {
                "success": False,
                "strategy": "MR",
                "exchange": exchange,
                "symbol": symbol,
                "variant": variant["name"],
                "error": data.get("message", "Unknown")[:100],
            }
    except Exception as e:
        return {
            "success": False,
            "strategy": "MR",
            "exchange": exchange,
            "symbol": symbol,
            "variant": variant["name"],
            "error": str(e)[:100],
        }


async def run_trend_backtest(client: httpx.AsyncClient, exchange: str, symbol: str, variant: dict) -> Dict:
    """추세매매 백테스트."""
    asset_type = "stock" if exchange.startswith("KIS") else "crypto"
    initial_capital = 10000000 if exchange.startswith("KIS") or exchange == "UPBIT" else 10000

    payload = {
        "exchange": exchange,
        "symbol": symbol,
        "signal_tf": "1D",
        "exit_tf": "1W",
        "htf_tf": "1W",
        "days": 365,
        "initial_capital": initial_capital,
        "st_atr_len": variant["st_atr_len"],
        "st_factor": variant["st_factor"],
        "hard_sl_pct": variant["hard_sl_pct"],
        "use_pyramiding": variant["use_pyramiding"],
        "asset_type": asset_type,
        "cash_use_pct": 100.0,
    }

    try:
        resp = await client.post(f"{BASE_URL}/backtest/trend", json=payload, timeout=120)
        data = resp.json()
        if data.get("success"):
            m = data.get("metrics", {})
            return {
                "success": True,
                "strategy": "Trend",
                "exchange": exchange,
                "symbol": symbol,
                "variant": variant["name"],
                "total_return_pct": round(m.get("total_return_pct", 0), 2),
                "mdd": round(m.get("max_drawdown_pct", 0), 2),
                "total_trades": m.get("total_trades", 0),
                "win_rate": round(m.get("win_rate_pct", 0), 1),
                "profit_factor": round(m.get("profit_factor", 0), 2),
                "cagr": round(m.get("cagr_pct", 0), 2),
            }
        else:
            return {
                "success": False,
                "strategy": "Trend",
                "exchange": exchange,
                "symbol": symbol,
                "variant": variant["name"],
                "error": data.get("message", "Unknown")[:100],
            }
    except Exception as e:
        return {
            "success": False,
            "strategy": "Trend",
            "exchange": exchange,
            "symbol": symbol,
            "variant": variant["name"],
            "error": str(e)[:100],
        }


async def main():
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    print("=" * 80)
    print(f"전 거래소 종합 백테스트 시작: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 80)

    all_results = []
    total_tests = 0
    success_count = 0
    fail_count = 0

    async with httpx.AsyncClient() as client:
        # ================================================================
        # 1. 역추세매매 (MR) 테스트
        # ================================================================
        print("\n[1] 역추세매매(MR) 백테스트")
        print("-" * 60)

        for exchange, symbols in EXCHANGE_SYMBOLS.items():
            for symbol in symbols:
                for variant in MR_VARIANTS:
                    total_tests += 1
                    print(f"  MR | {exchange:10} | {symbol:15} | {variant['name']:20}", end=" ... ", flush=True)

                    result = await run_mr_backtest(client, exchange, symbol, variant)
                    all_results.append(result)

                    if result["success"]:
                        success_count += 1
                        print(f"수익률 {result['total_return_pct']:+.2f}%, MDD {result['mdd']:.2f}%, 거래 {result['total_trades']}회")
                    else:
                        fail_count += 1
                        print(f"FAIL: {result.get('error', 'Unknown')[:40]}")

        # ================================================================
        # 2. 추세매매 (Trend) 테스트
        # ================================================================
        print("\n[2] 추세매매(Trend) 백테스트")
        print("-" * 60)

        for exchange, symbols in EXCHANGE_SYMBOLS.items():
            for symbol in symbols:
                for variant in TREND_VARIANTS:
                    total_tests += 1
                    print(f"  TR | {exchange:10} | {symbol:15} | {variant['name']:20}", end=" ... ", flush=True)

                    result = await run_trend_backtest(client, exchange, symbol, variant)
                    all_results.append(result)

                    if result["success"]:
                        success_count += 1
                        print(f"수익률 {result['total_return_pct']:+.2f}%, MDD {result['mdd']:.2f}%, 거래 {result['total_trades']}회")
                    else:
                        fail_count += 1
                        print(f"FAIL: {result.get('error', 'Unknown')[:40]}")

    # ================================================================
    # 결과 요약
    # ================================================================
    print("\n" + "=" * 80)
    print("백테스트 결과 요약")
    print("=" * 80)
    print(f"총 테스트: {total_tests}, 성공: {success_count}, 실패: {fail_count}")

    # 성공한 결과만 필터
    success_results = [r for r in all_results if r["success"]]

    if success_results:
        # 상위 20 수익률
        print("\n[상위 20 수익률]")
        sorted_results = sorted(success_results, key=lambda x: x["total_return_pct"], reverse=True)[:20]
        print(f"{'#':>3} | {'전략':6} | {'거래소':10} | {'종목':15} | {'변형':20} | {'수익률':>10} | {'MDD':>8} | {'거래':>5} | {'PF':>6}")
        print("-" * 100)
        for i, r in enumerate(sorted_results, 1):
            print(f"{i:3} | {r['strategy']:6} | {r['exchange']:10} | {r['symbol']:15} | {r['variant']:20} | {r['total_return_pct']:>+10.2f}% | {r['mdd']:>8.2f}% | {r['total_trades']:>5} | {r['profit_factor']:>6.2f}")

        # 전략별 평균
        print("\n[전략별 평균 수익률]")
        for strategy in ["MR", "Trend"]:
            strat_results = [r for r in success_results if r["strategy"] == strategy]
            if strat_results:
                avg_return = sum(r["total_return_pct"] for r in strat_results) / len(strat_results)
                avg_mdd = sum(r["mdd"] for r in strat_results) / len(strat_results)
                print(f"  {strategy:6}: 평균 수익률 {avg_return:+.2f}%, 평균 MDD {avg_mdd:.2f}%, 테스트 {len(strat_results)}건")

        # 거래소별 평균
        print("\n[거래소별 평균 수익률]")
        for exchange in EXCHANGE_SYMBOLS.keys():
            ex_results = [r for r in success_results if r["exchange"] == exchange]
            if ex_results:
                avg_return = sum(r["total_return_pct"] for r in ex_results) / len(ex_results)
                avg_mdd = sum(r["mdd"] for r in ex_results) / len(ex_results)
                print(f"  {exchange:10}: 평균 수익률 {avg_return:+.2f}%, 평균 MDD {avg_mdd:.2f}%, 테스트 {len(ex_results)}건")

    # ================================================================
    # 결과 저장
    # ================================================================
    # JSON 저장
    json_file = f"backtest_results_{timestamp}.json"
    with open(json_file, "w", encoding="utf-8") as f:
        json.dump({
            "timestamp": datetime.now().isoformat(),
            "summary": {
                "total_tests": total_tests,
                "success_count": success_count,
                "fail_count": fail_count,
            },
            "results": all_results,
        }, f, ensure_ascii=False, indent=2)
    print(f"\nJSON 저장: {json_file}")

    # CSV 저장 (성공 결과만)
    csv_file = f"backtest_results_{timestamp}.csv"
    if success_results:
        with open(csv_file, "w", newline="", encoding="utf-8-sig") as f:
            writer = csv.DictWriter(f, fieldnames=[
                "strategy", "exchange", "symbol", "variant",
                "total_return_pct", "mdd", "total_trades", "win_rate", "profit_factor", "cagr"
            ])
            writer.writeheader()
            for r in success_results:
                writer.writerow({k: v for k, v in r.items() if k in writer.fieldnames})
    print(f"CSV 저장: {csv_file}")

    print(f"\n완료: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 80)


if __name__ == "__main__":
    asyncio.run(main())

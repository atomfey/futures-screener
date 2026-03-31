"""
季節性分析模組
- 計算每個期貨品種歷史同月份的平均漲跌幅
- 統計上漲機率（勝率）
- 輸出 seasonality.json
"""

import json
import sys
from datetime import datetime
from pathlib import Path

import pandas as pd
import yfinance as yf

from futures_list import FUTURES_CONTRACTS

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

SCRIPT_DIR = Path(__file__).parent
OUTPUT_DIR = SCRIPT_DIR.parent / "docs" / "data"
OUTPUT_FILE = OUTPUT_DIR / "seasonality.json"

YEARS_BACK = 10  # 分析過去 10 年


def calc_seasonality(code, info):
    """計算單一期貨的月度季節性統計"""
    yf_symbol = info["yfinance"]
    try:
        ticker = yf.Ticker(yf_symbol)
        df = ticker.history(period=f"{YEARS_BACK}y", interval="1mo")
        if df.empty or len(df) < 12:
            return None

        df = df[["Close"]].copy()
        df.index = pd.to_datetime(df.index).tz_localize(None)
        df["return"] = df["Close"].pct_change() * 100
        df["month"] = df.index.month
        df.dropna(inplace=True)

        monthly_stats = {}
        for month in range(1, 13):
            month_data = df[df["month"] == month]["return"]
            if len(month_data) == 0:
                continue
            monthly_stats[str(month)] = {
                "avg_return": round(float(month_data.mean()), 2),
                "median_return": round(float(month_data.median()), 2),
                "win_rate": round(float((month_data > 0).sum() / len(month_data) * 100), 1),
                "best": round(float(month_data.max()), 2),
                "worst": round(float(month_data.min()), 2),
                "count": int(len(month_data)),
            }

        return {
            "code": code,
            "name": info["name"],
            "category": info["category"],
            "months": monthly_stats,
        }

    except Exception as e:
        print(f"  [ERR] {code}: {e}")
        return None


def run_seasonality():
    """計算所有期貨的季節性分析"""
    print("=" * 60)
    print(f"季節性分析 (過去 {YEARS_BACK} 年)")
    print("=" * 60)

    results = {}
    for code, info in FUTURES_CONTRACTS.items():
        print(f"  分析 {code} ({info['name']})...")
        data = calc_seasonality(code, info)
        if data:
            results[code] = data
            # 顯示當月的季節性
            current_month = str(datetime.now().month)
            if current_month in data["months"]:
                m = data["months"][current_month]
                bias = "+" if m["avg_return"] > 0 else ""
                print(f"    本月平均: {bias}{m['avg_return']}% | 勝率: {m['win_rate']}%")

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump({
            "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "years_analyzed": YEARS_BACK,
            "data": results,
        }, f, ensure_ascii=False, indent=2)

    print(f"\n季節性資料已寫入: {OUTPUT_FILE}")
    return results


if __name__ == "__main__":
    run_seasonality()

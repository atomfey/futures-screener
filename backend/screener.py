"""
期貨篩選器主引擎
- 從 yfinance 抓取期貨 OHLCV 資料
- 計算趨勢跟隨 + 動量排名 + 多時間框架條件
- 綜合評分並輸出 results.json
"""

import json
import os
import sys
from datetime import datetime, timedelta
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed

import numpy as np
import pandas as pd
import yfinance as yf

from futures_list import FUTURES_CONTRACTS, get_next_expiry, get_affordable

# Windows console encoding fix
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")


class NumpyEncoder(json.JSONEncoder):
    """Handle numpy types for JSON serialization"""
    def default(self, obj):
        if isinstance(obj, (np.bool_,)):
            return bool(obj)
        if isinstance(obj, (np.integer,)):
            return int(obj)
        if isinstance(obj, (np.floating,)):
            return float(obj)
        if isinstance(obj, (np.ndarray,)):
            return obj.tolist()
        return super().default(obj)

# ============================================================
# 設定
# ============================================================

ACCOUNT_BALANCE = 7000
RISK_PER_TRADE = 0.02  # 每筆交易風險 2%
DATA_PERIOD = "2y"      # 抓取 2 年歷史資料
DATA_INTERVAL = "1d"    # 日線

SCRIPT_DIR = Path(__file__).parent
OUTPUT_DIR = SCRIPT_DIR.parent / "docs" / "data"
RESULTS_FILE = OUTPUT_DIR / "results.json"
HISTORY_DIR = OUTPUT_DIR / "history"


# ============================================================
# 資料抓取
# ============================================================

def fetch_data(symbol_info):
    """從 yfinance 抓取單一期貨的歷史資料"""
    code, info = symbol_info
    yf_symbol = info["yfinance"]
    try:
        ticker = yf.Ticker(yf_symbol)
        df = ticker.history(period=DATA_PERIOD, interval=DATA_INTERVAL)
        if df.empty or len(df) < 50:
            print(f"  [SKIP] {code} ({yf_symbol}): 資料不足 ({len(df)} bars)")
            return code, None
        # 清理資料
        df = df[["Open", "High", "Low", "Close", "Volume"]].copy()
        df.index = pd.to_datetime(df.index).tz_localize(None)
        df.dropna(inplace=True)
        print(f"  [OK]   {code} ({yf_symbol}): {len(df)} bars")
        return code, df
    except Exception as e:
        print(f"  [ERR]  {code} ({yf_symbol}): {e}")
        return code, None


def fetch_all_data():
    """並行抓取所有期貨資料"""
    print("=" * 60)
    print(f"抓取期貨資料 ({len(FUTURES_CONTRACTS)} 個標的)")
    print("=" * 60)

    data = {}
    items = list(FUTURES_CONTRACTS.items())

    with ThreadPoolExecutor(max_workers=5) as executor:
        futures = {executor.submit(fetch_data, item): item[0] for item in items}
        for future in as_completed(futures):
            code, df = future.result()
            if df is not None:
                data[code] = df

    print(f"\n成功抓取: {len(data)}/{len(FUTURES_CONTRACTS)} 個標的")
    return data


# ============================================================
# 技術指標計算
# ============================================================

def calc_sma(series, period):
    """簡單移動平均"""
    return series.rolling(window=period, min_periods=period).mean()


def calc_ema(series, period):
    """指數移動平均"""
    return series.ewm(span=period, adjust=False).mean()


def calc_atr(df, period=14):
    """Average True Range"""
    high = df["High"]
    low = df["Low"]
    close = df["Close"]
    prev_close = close.shift(1)

    tr1 = high - low
    tr2 = (high - prev_close).abs()
    tr3 = (low - prev_close).abs()
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)

    return tr.rolling(window=period, min_periods=period).mean()


def calc_adx(df, period=14):
    """Average Directional Index"""
    high = df["High"]
    low = df["Low"]
    close = df["Close"]

    plus_dm = high.diff()
    minus_dm = -low.diff()

    plus_dm[plus_dm < 0] = 0
    minus_dm[minus_dm < 0] = 0

    # 當 +DM > -DM 時保留 +DM，否則設為 0
    mask = plus_dm > minus_dm
    plus_dm[~mask] = 0
    minus_dm[mask] = 0

    atr = calc_atr(df, period)

    plus_di = 100 * calc_ema(plus_dm, period) / atr
    minus_di = 100 * calc_ema(minus_dm, period) / atr

    dx = 100 * (plus_di - minus_di).abs() / (plus_di + minus_di).replace(0, np.nan)
    adx = calc_ema(dx, period)

    return adx, plus_di, minus_di


def calc_donchian(df, period=20):
    """Donchian Channel"""
    high_channel = df["High"].rolling(window=period).max()
    low_channel = df["Low"].rolling(window=period).min()
    mid_channel = (high_channel + low_channel) / 2
    return high_channel, low_channel, mid_channel


def calc_roc(series, period):
    """Rate of Change (變動率) %"""
    return ((series / series.shift(period)) - 1) * 100


def calc_rsi(series, period=14):
    """Relative Strength Index"""
    delta = series.diff()
    gain = delta.where(delta > 0, 0.0)
    loss = (-delta).where(delta < 0, 0.0)

    avg_gain = gain.rolling(window=period, min_periods=period).mean()
    avg_loss = loss.rolling(window=period, min_periods=period).mean()

    rs = avg_gain / avg_loss.replace(0, np.nan)
    rsi = 100 - (100 / (1 + rs))
    return rsi


def resample_weekly(df):
    """將日線轉為週線"""
    weekly = df.resample("W").agg({
        "Open": "first",
        "High": "max",
        "Low": "min",
        "Close": "last",
        "Volume": "sum",
    }).dropna()
    return weekly


# ============================================================
# 篩選條件計算
# ============================================================

def analyze_contract(code, df):
    """對單一期貨計算所有篩選條件"""
    info = FUTURES_CONTRACTS[code]
    close = df["Close"]
    latest = close.iloc[-1]

    # 均線
    sma50 = calc_sma(close, 50)
    sma200 = calc_sma(close, 200)
    sma20 = calc_sma(close, 20)

    # ATR
    atr14 = calc_atr(df, 14)

    # ADX
    adx, plus_di, minus_di = calc_adx(df, 14)

    # Donchian Channel
    don_high, don_low, don_mid = calc_donchian(df, 20)

    # ROC
    roc20 = calc_roc(close, 20)
    roc60 = calc_roc(close, 60)

    # RSI
    rsi14 = calc_rsi(close, 14)

    # 取最新值
    latest_sma50 = sma50.iloc[-1] if not pd.isna(sma50.iloc[-1]) else None
    latest_sma200 = sma200.iloc[-1] if not pd.isna(sma200.iloc[-1]) else None
    latest_sma20 = sma20.iloc[-1] if not pd.isna(sma20.iloc[-1]) else None
    latest_atr = atr14.iloc[-1] if not pd.isna(atr14.iloc[-1]) else None
    latest_adx = adx.iloc[-1] if not pd.isna(adx.iloc[-1]) else None
    latest_plus_di = plus_di.iloc[-1] if not pd.isna(plus_di.iloc[-1]) else None
    latest_minus_di = minus_di.iloc[-1] if not pd.isna(minus_di.iloc[-1]) else None
    latest_don_high = don_high.iloc[-1] if not pd.isna(don_high.iloc[-1]) else None
    latest_don_mid = don_mid.iloc[-1] if not pd.isna(don_mid.iloc[-1]) else None
    latest_don_low = don_low.iloc[-1] if not pd.isna(don_low.iloc[-1]) else None
    latest_roc20 = roc20.iloc[-1] if not pd.isna(roc20.iloc[-1]) else None
    latest_roc60 = roc60.iloc[-1] if not pd.isna(roc60.iloc[-1]) else None
    latest_rsi = rsi14.iloc[-1] if not pd.isna(rsi14.iloc[-1]) else None

    # ==========================================
    # 策略一：趨勢跟隨條件
    # ==========================================
    conditions = {}

    # 1. 價格在 50 日均線之上
    conditions["price_above_sma50"] = (
        latest > latest_sma50 if latest_sma50 else False
    )

    # 2. 50 日均線在 200 日均線之上（黃金交叉）
    conditions["sma50_above_sma200"] = (
        latest_sma50 > latest_sma200
        if latest_sma50 and latest_sma200 else False
    )

    # 3. 200 日均線向上
    sma200_20ago = sma200.iloc[-20] if len(sma200) >= 20 and not pd.isna(sma200.iloc[-20]) else None
    conditions["sma200_trending_up"] = (
        latest_sma200 > sma200_20ago
        if latest_sma200 and sma200_20ago else False
    )

    # 4. ADX > 25（趨勢強度足夠）
    conditions["adx_above_25"] = (
        latest_adx > 25 if latest_adx else False
    )

    # 5. 價格在 Donchian 中線之上
    conditions["price_above_donchian_mid"] = (
        latest > latest_don_mid if latest_don_mid else False
    )

    # ==========================================
    # 策略二：動量條件
    # ==========================================

    # 6. ROC 20 > 0 (20日動量正向)
    conditions["roc_20_positive"] = (
        latest_roc20 > 0 if latest_roc20 is not None else False
    )

    # 7. ROC 60 > 0 (60日動量正向)
    conditions["roc_60_positive"] = (
        latest_roc60 > 0 if latest_roc60 is not None else False
    )

    # 8. 突破 20 日最高
    conditions["breakout_high"] = (
        latest >= latest_don_high if latest_don_high else False
    )

    # ==========================================
    # 策略四：多時間框架確認
    # ==========================================

    # 週線趨勢
    try:
        weekly = resample_weekly(df)
        weekly_sma20 = calc_sma(weekly["Close"], 20)
        weekly_latest = weekly["Close"].iloc[-1]
        weekly_sma_val = weekly_sma20.iloc[-1] if not pd.isna(weekly_sma20.iloc[-1]) else None
        weekly_sma_prev = weekly_sma20.iloc[-4] if len(weekly_sma20) >= 4 and not pd.isna(weekly_sma20.iloc[-4]) else None

        # 9. 週線趨勢向上
        conditions["weekly_trend_up"] = (
            weekly_sma_val > weekly_sma_prev
            if weekly_sma_val and weekly_sma_prev else False
        )

        # 10. 多時間框架一致（週線+日線都向上）
        daily_trend_up = conditions["price_above_sma50"] and conditions["sma200_trending_up"]
        conditions["mtf_alignment"] = (
            conditions["weekly_trend_up"] and daily_trend_up
        )
    except Exception:
        conditions["weekly_trend_up"] = False
        conditions["mtf_alignment"] = False

    # ==========================================
    # 計算信號方向
    # ==========================================

    # DI 方向判斷
    bullish_di = latest_plus_di > latest_minus_di if latest_plus_di and latest_minus_di else None

    # ==========================================
    # 綜合評分
    # ==========================================

    # 做多條件計分
    long_conditions = [
        "price_above_sma50", "sma50_above_sma200", "sma200_trending_up",
        "adx_above_25", "price_above_donchian_mid",
        "roc_20_positive", "roc_60_positive", "breakout_high",
        "weekly_trend_up", "mtf_alignment",
    ]

    long_score = sum(1 for c in long_conditions if conditions.get(c, False))

    # 多時間框架一致加分
    if conditions.get("mtf_alignment"):
        long_score += 2

    total_conditions = len(long_conditions)

    # 做空條件（反向計分）
    short_conditions_met = sum(1 for c in [
        "price_above_sma50", "sma50_above_sma200", "sma200_trending_up",
        "roc_20_positive", "roc_60_positive",
    ] if not conditions.get(c, True))

    short_score = short_conditions_met
    if not conditions.get("weekly_trend_up", True):
        short_score += 2

    # 信號判定
    if long_score >= 10:
        signal = "強烈做多"
        signal_en = "STRONG_LONG"
    elif long_score >= 7:
        signal = "做多"
        signal_en = "LONG"
    elif short_score >= 6:
        signal = "做空"
        signal_en = "SHORT"
    elif short_score >= 8:
        signal = "強烈做空"
        signal_en = "STRONG_SHORT"
    else:
        signal = "中性"
        signal_en = "NEUTRAL"

    # ==========================================
    # 風險管理計算
    # ==========================================

    # ATR 止損距離
    stop_distance = latest_atr * 2 if latest_atr else None

    # 建議倉位大小
    max_loss = ACCOUNT_BALANCE * RISK_PER_TRADE
    if stop_distance and info["tick_value"] and info["tick_size"]:
        stop_ticks = stop_distance / info["tick_size"]
        risk_per_contract = stop_ticks * info["tick_value"]
        suggested_contracts = max(1, int(max_loss / risk_per_contract)) if risk_per_contract > 0 else 0
        margin_needed = info["margin"] * suggested_contracts
        can_afford = margin_needed <= ACCOUNT_BALANCE * 0.5
    else:
        risk_per_contract = None
        suggested_contracts = 0
        margin_needed = 0
        can_afford = False

    # 換倉資訊
    expiry_info = get_next_expiry(code)

    # ==========================================
    # 組裝結果
    # ==========================================

    result = {
        "code": code,
        "name": info["name"],
        "name_en": info["name_en"],
        "category": info["category"],
        "exchange": info["exchange"],
        "yfinance": info["yfinance"],
        "tradingview": info["tradingview"],

        # 價格資訊
        "price": round(latest, 4),
        "change_1d": round(float(calc_roc(close, 1).iloc[-1]), 2) if len(close) > 1 else 0,
        "change_5d": round(float(calc_roc(close, 5).iloc[-1]), 2) if len(close) > 5 else 0,
        "change_20d": round(latest_roc20, 2) if latest_roc20 is not None else 0,
        "change_60d": round(latest_roc60, 2) if latest_roc60 is not None else 0,

        # 技術指標
        "sma50": round(latest_sma50, 4) if latest_sma50 else None,
        "sma200": round(latest_sma200, 4) if latest_sma200 else None,
        "atr14": round(latest_atr, 4) if latest_atr else None,
        "adx": round(latest_adx, 2) if latest_adx else None,
        "plus_di": round(latest_plus_di, 2) if latest_plus_di else None,
        "minus_di": round(latest_minus_di, 2) if latest_minus_di else None,
        "rsi14": round(latest_rsi, 2) if latest_rsi else None,
        "donchian_high": round(latest_don_high, 4) if latest_don_high else None,
        "donchian_mid": round(latest_don_mid, 4) if latest_don_mid else None,
        "donchian_low": round(latest_don_low, 4) if latest_don_low else None,

        # 篩選條件
        "conditions": conditions,

        # 評分
        "long_score": long_score,
        "short_score": short_score,
        "total_conditions": total_conditions,
        "signal": signal,
        "signal_en": signal_en,

        # 風險管理
        "margin": info["margin"],
        "multiplier": info["multiplier"],
        "tick_size": info["tick_size"],
        "tick_value": info["tick_value"],
        "stop_distance": round(stop_distance, 4) if stop_distance else None,
        "risk_per_contract": round(risk_per_contract, 2) if risk_per_contract else None,
        "suggested_contracts": suggested_contracts,
        "margin_needed": margin_needed,
        "can_afford": can_afford,

        # 換倉資訊
        "next_expiry": expiry_info["expiry_date"].strftime("%Y-%m-%d") if expiry_info else None,
        "next_rollover": expiry_info["rollover_date"].strftime("%Y-%m-%d") if expiry_info else None,
        "days_to_rollover": expiry_info["days_to_rollover"] if expiry_info else None,
        "contract_month": expiry_info["contract_label"] if expiry_info else None,
    }

    return result


# ============================================================
# 動量排名（跨品種比較）
# ============================================================

def calc_momentum_ranks(results):
    """計算所有期貨的動量排名"""
    if not results:
        return results

    # 用 60 日變動率排名
    roc_values = [(r["code"], r["change_60d"]) for r in results if r["change_60d"] is not None]
    roc_values.sort(key=lambda x: x[1], reverse=True)

    rank_map = {}
    for i, (code, _) in enumerate(roc_values):
        rank_map[code] = {
            "momentum_rank": i + 1,
            "momentum_percentile": round((1 - i / max(len(roc_values) - 1, 1)) * 100, 1),
        }

    for r in results:
        if r["code"] in rank_map:
            r["momentum_rank"] = rank_map[r["code"]]["momentum_rank"]
            r["momentum_percentile"] = rank_map[r["code"]]["momentum_percentile"]
        else:
            r["momentum_rank"] = None
            r["momentum_percentile"] = None

    return results


# ============================================================
# 波動率環境
# ============================================================

def calc_volatility_environment(data):
    """計算各品種的波動率百分位"""
    vol_env = {}
    for code, df in data.items():
        atr = calc_atr(df, 14)
        if atr.dropna().empty:
            continue
        current_atr = atr.iloc[-1]
        # 過去一年的 ATR 百分位
        atr_1y = atr.tail(252)
        percentile = (atr_1y < current_atr).sum() / len(atr_1y) * 100
        vol_env[code] = {
            "current_atr": round(float(current_atr), 4),
            "volatility_percentile": round(float(percentile), 1),
            "volatility_level": (
                "高" if percentile > 75 else
                "中" if percentile > 25 else "低"
            ),
        }
    return vol_env


# ============================================================
# 相關性矩陣
# ============================================================

def calc_correlation_matrix(data):
    """計算所有期貨品種之間的 60 日相關性"""
    closes = {}
    for code, df in data.items():
        closes[code] = df["Close"].tail(60).pct_change().dropna()

    if len(closes) < 2:
        return {}

    close_df = pd.DataFrame(closes)
    corr = close_df.corr()

    # 轉換為可序列化的格式
    result = {}
    for c1 in corr.columns:
        result[c1] = {}
        for c2 in corr.columns:
            val = corr.loc[c1, c2]
            result[c1][c2] = round(float(val), 3) if not pd.isna(val) else None

    return result


# ============================================================
# 主執行
# ============================================================

def run_screening():
    """執行完整篩選流程"""
    start_time = datetime.now()
    print(f"\n期貨篩選器 - {start_time.strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60)

    # 1. 抓取資料
    data = fetch_all_data()
    if not data:
        print("無法抓取任何資料，結束")
        return

    # 2. 分析每個標的
    print("\n" + "=" * 60)
    print("分析篩選條件")
    print("=" * 60)

    results = []
    for code, df in data.items():
        try:
            result = analyze_contract(code, df)
            results.append(result)
            signal_icon = {
                "強烈做多": "++", "做多": "+", "中性": "=",
                "做空": "-", "強烈做空": "--",
            }.get(result["signal"], "=")
            print(f"  {signal_icon} {code:5s} | {result['name']:8s} | "
                  f"分數: {result['long_score']:2d}/{result['total_conditions']} | "
                  f"信號: {result['signal']}")
        except Exception as e:
            print(f"  [ERR] {code}: {e}")

    # 3. 計算動量排名
    results = calc_momentum_ranks(results)

    # 4. 計算波動率環境
    vol_env = calc_volatility_environment(data)
    for r in results:
        if r["code"] in vol_env:
            r.update(vol_env[r["code"]])

    # 5. 計算相關性矩陣
    correlation = calc_correlation_matrix(data)

    # 6. 按做多分數排序
    results.sort(key=lambda x: x["long_score"], reverse=True)

    # 7. 匯出 OHLCV K 線數據（最近 90 根日線）
    ohlcv_data = {}
    for code, df in data.items():
        recent = df.tail(90)
        ohlcv_data[code] = [
            {
                "time": row.Index.strftime("%Y-%m-%d"),
                "open": round(float(row.Open), 6),
                "high": round(float(row.High), 6),
                "low": round(float(row.Low), 6),
                "close": round(float(row.Close), 6),
                "volume": int(row.Volume) if row.Volume else 0,
            }
            for row in recent.itertuples()
        ]
    ohlcv_file = OUTPUT_DIR / "ohlcv.json"
    with open(ohlcv_file, "w", encoding="utf-8") as f:
        json.dump(ohlcv_data, f, ensure_ascii=False, cls=NumpyEncoder)
    print(f"K線數據已寫入: {ohlcv_file}")

    # 8. 輸出結果
    output = {
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "account_balance": ACCOUNT_BALANCE,
        "risk_per_trade": RISK_PER_TRADE,
        "total_contracts": len(results),
        "results": results,
        "correlation_matrix": correlation,
        "categories": sorted(set(r["category"] for r in results)),
    }

    # 確保輸出目錄存在
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    HISTORY_DIR.mkdir(parents=True, exist_ok=True)

    # 寫入最新結果
    with open(RESULTS_FILE, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2, cls=NumpyEncoder)
    print(f"\n結果已寫入: {RESULTS_FILE}")

    # 寫入歷史快照
    today = datetime.now().strftime("%Y-%m-%d")
    history_file = HISTORY_DIR / f"{today}.json"
    with open(history_file, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2, cls=NumpyEncoder)
    print(f"歷史快照: {history_file}")

    # 8. 摘要
    elapsed = (datetime.now() - start_time).total_seconds()
    print("\n" + "=" * 60)
    print(f"篩選完成 (耗時 {elapsed:.1f} 秒)")
    print("=" * 60)

    strong_long = [r for r in results if r["signal"] == "強烈做多"]
    long_list = [r for r in results if r["signal"] == "做多"]
    short_list = [r for r in results if r["signal"] in ("做空", "強烈做空")]

    if strong_long:
        print(f"\n[++] STRONG LONG ({len(strong_long)}):")
        for r in strong_long:
            print(f"   {r['code']} {r['name']} | score {r['long_score']}/{r['total_conditions']} | price {r['price']}")

    if long_list:
        print(f"\n[+] LONG ({len(long_list)}):")
        for r in long_list:
            print(f"   {r['code']} {r['name']} | score {r['long_score']}/{r['total_conditions']} | price {r['price']}")

    if short_list:
        print(f"\n[-] SHORT ({len(short_list)}):")
        for r in short_list:
            print(f"   {r['code']} {r['name']} | score {r['short_score']} | price {r['price']}")

    # rollover alerts
    urgent_rollover = [r for r in results if r.get("days_to_rollover") and r["days_to_rollover"] <= 14]
    if urgent_rollover:
        print(f"\n[!] ROLLOVER ALERT:")
        for r in urgent_rollover:
            print(f"   {r['code']} {r['name']} -> rollover: {r['next_rollover']} ({r['days_to_rollover']} days left)")

    return output


if __name__ == "__main__":
    run_screening()

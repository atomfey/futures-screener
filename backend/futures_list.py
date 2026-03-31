"""
期貨標的池管理
- 所有可交易的期貨合約清單
- 合約規格（乘數、最小跳動、保證金）
- 合約到期日計算
- 換倉日期建議
"""

from datetime import datetime, timedelta
import calendar


# ============================================================
# 期貨標的池定義
# ============================================================

FUTURES_CONTRACTS = {
    # === 微型股指期貨（Micro Index Futures）===
    "MES": {
        "name": "微型標普500",
        "name_en": "Micro E-mini S&P 500",
        "yfinance": "MES=F",
        "exchange": "CME",
        "category": "股指",
        "multiplier": 5,        # 每點 $5
        "tick_size": 0.25,      # 最小跳動
        "tick_value": 1.25,     # 每跳動 $1.25
        "margin": 1500,         # 預估保證金
        "months": [3, 6, 9, 12],  # 季月合約 (H, M, U, Z)
        "tradingview": "CME_MINI:ES1!",
    },
    "MNQ": {
        "name": "微型納斯達克",
        "name_en": "Micro E-mini Nasdaq-100",
        "yfinance": "MNQ=F",
        "exchange": "CME",
        "category": "股指",
        "multiplier": 2,
        "tick_size": 0.25,
        "tick_value": 0.50,
        "margin": 2000,
        "months": [3, 6, 9, 12],
        "tradingview": "CME_MINI:NQ1!",
    },
    "MYM": {
        "name": "微型道瓊",
        "name_en": "Micro E-mini Dow",
        "yfinance": "MYM=F",
        "exchange": "CME",
        "category": "股指",
        "multiplier": 0.50,
        "tick_size": 1.0,
        "tick_value": 0.50,
        "margin": 900,
        "months": [3, 6, 9, 12],
        "tradingview": "CBOT_MINI:YM1!",
    },
    "M2K": {
        "name": "微型羅素2000",
        "name_en": "Micro E-mini Russell 2000",
        "yfinance": "M2K=F",
        "exchange": "CME",
        "category": "股指",
        "multiplier": 5,
        "tick_size": 0.10,
        "tick_value": 0.50,
        "margin": 700,
        "months": [3, 6, 9, 12],
        "tradingview": "CME_MINI:RTY1!",
    },

    # === 微型商品期貨（Micro Commodity Futures）===
    "MGC": {
        "name": "微型黃金",
        "name_en": "Micro Gold",
        "yfinance": "MGC=F",
        "exchange": "COMEX",
        "category": "貴金屬",
        "multiplier": 10,
        "tick_size": 0.10,
        "tick_value": 1.00,
        "margin": 1000,
        "months": list(range(1, 13)),  # 每月都有 (但主要交易偶數月)
        "tradingview": "COMEX:GC1!",
    },
    "MCL": {
        "name": "微型原油",
        "name_en": "Micro WTI Crude Oil",
        "yfinance": "MCL=F",
        "exchange": "NYMEX",
        "category": "能源",
        "multiplier": 100,
        "tick_size": 0.01,
        "tick_value": 1.00,
        "margin": 800,
        "months": list(range(1, 13)),
        "tradingview": "NYMEX:CL1!",
    },

    # === 標準農產品期貨 ===
    "ZC": {
        "name": "玉米",
        "name_en": "Corn",
        "yfinance": "ZC=F",
        "exchange": "CBOT",
        "category": "農產品",
        "multiplier": 50,       # 每蒲式耳 50 倍 (5000蒲式耳/口)
        "tick_size": 0.25,      # 1/4 美分
        "tick_value": 12.50,
        "margin": 1500,
        "months": [3, 5, 7, 9, 12],  # H, K, N, U, Z
        "tradingview": "CBOT:ZC1!",
    },
    "ZW": {
        "name": "小麥",
        "name_en": "Wheat",
        "yfinance": "ZW=F",
        "exchange": "CBOT",
        "category": "農產品",
        "multiplier": 50,
        "tick_size": 0.25,
        "tick_value": 12.50,
        "margin": 1500,
        "months": [3, 5, 7, 9, 12],
        "tradingview": "CBOT:ZW1!",
    },
    "ZS": {
        "name": "大豆",
        "name_en": "Soybeans",
        "yfinance": "ZS=F",
        "exchange": "CBOT",
        "category": "農產品",
        "multiplier": 50,
        "tick_size": 0.25,
        "tick_value": 12.50,
        "margin": 2000,
        "months": [1, 3, 5, 7, 8, 9, 11],  # F, H, K, N, Q, U, X
        "tradingview": "CBOT:ZS1!",
    },

    # === 債券期貨 ===
    "ZN": {
        "name": "10年美國國債",
        "name_en": "10-Year T-Note",
        "yfinance": "ZN=F",
        "exchange": "CBOT",
        "category": "債券",
        "multiplier": 1000,
        "tick_size": 0.015625,  # 1/64
        "tick_value": 15.625,
        "margin": 2000,
        "months": [3, 6, 9, 12],
        "tradingview": "CBOT:ZN1!",
    },

    # === 外匯期貨 ===
    "6E": {
        "name": "歐元",
        "name_en": "Euro FX",
        "yfinance": "6E=F",
        "exchange": "CME",
        "category": "外匯",
        "multiplier": 125000,
        "tick_size": 0.00005,
        "tick_value": 6.25,
        "margin": 2500,
        "months": [3, 6, 9, 12],
        "tradingview": "CME:6E1!",
    },
    "6J": {
        "name": "日圓",
        "name_en": "Japanese Yen",
        "yfinance": "6J=F",
        "exchange": "CME",
        "category": "外匯",
        "multiplier": 12500000,
        "tick_size": 0.0000005,
        "tick_value": 6.25,
        "margin": 3000,
        "months": [3, 6, 9, 12],
        "tradingview": "CME:6J1!",
    },
}

# 合約月份代碼對照
MONTH_CODES = {
    1: "F", 2: "G", 3: "H", 4: "J", 5: "K", 6: "M",
    7: "N", 8: "Q", 9: "U", 10: "V", 11: "X", 12: "Z",
}

MONTH_NAMES_ZH = {
    1: "一月", 2: "二月", 3: "三月", 4: "四月", 5: "五月", 6: "六月",
    7: "七月", 8: "八月", 9: "九月", 10: "十月", 11: "十一月", 12: "十二月",
}


def get_all_symbols():
    """取得所有期貨的 yfinance 代碼"""
    return {code: info["yfinance"] for code, info in FUTURES_CONTRACTS.items()}


def get_by_category(category):
    """按類別篩選期貨"""
    return {
        code: info for code, info in FUTURES_CONTRACTS.items()
        if info["category"] == category
    }


def get_affordable(account_balance=7000, max_margin_pct=0.50):
    """取得在預算內可交易的期貨（預設不超過帳戶50%保證金）"""
    max_margin = account_balance * max_margin_pct
    return {
        code: info for code, info in FUTURES_CONTRACTS.items()
        if info["margin"] <= max_margin
    }


def get_next_expiry(symbol, from_date=None):
    """
    計算下一個合約到期日
    股指期貨：到期月份第三個週五
    農產品/商品：到期月份前一個月的最後營業日（近似）
    """
    if from_date is None:
        from_date = datetime.now()

    contract = FUTURES_CONTRACTS.get(symbol)
    if not contract:
        return None

    months = contract["months"]
    category = contract["category"]

    # 找到下一個合約月份
    for offset in range(0, 15):  # 最多看 15 個月
        check_date = from_date + timedelta(days=offset * 30)
        year = check_date.year
        for m in months:
            if m >= check_date.month or (m < check_date.month and offset > 0):
                target_year = year if m >= check_date.month else year + 1
                expiry = _calc_expiry_date(category, target_year, m)
                if expiry > from_date:
                    return {
                        "symbol": symbol,
                        "contract_month": f"{MONTH_CODES[m]}{str(target_year)[-2:]}",
                        "contract_label": f"{MONTH_NAMES_ZH[m]} {target_year}",
                        "expiry_date": expiry,
                        "rollover_date": expiry - timedelta(days=10),
                        "warning_date": expiry - timedelta(days=14),
                        "days_to_expiry": (expiry - from_date).days,
                        "days_to_rollover": (expiry - timedelta(days=10) - from_date).days,
                    }
    return None


def _calc_expiry_date(category, year, month):
    """計算合約到期日（近似值）"""
    if category == "股指":
        # 股指期貨：到期月份第三個週五
        return _third_friday(year, month)
    elif category in ("農產品", "能源", "貴金屬"):
        # 商品期貨：到期月份前15日左右（近似）
        return datetime(year, month, 15)
    elif category == "債券":
        # 債券：到期月份最後營業日前 7 日
        last_day = calendar.monthrange(year, month)[1]
        return datetime(year, month, last_day) - timedelta(days=7)
    elif category == "外匯":
        # 外匯：到期月份第三個週三前兩個營業日
        third_wed = _nth_weekday(year, month, 2, 3)  # 第三個週三
        return third_wed - timedelta(days=2)
    else:
        return datetime(year, month, 15)


def _third_friday(year, month):
    """取得某月份的第三個週五"""
    return _nth_weekday(year, month, 4, 3)  # 4=Friday, 第3個


def _nth_weekday(year, month, weekday, n):
    """取得某月份第 n 個特定星期幾 (0=Mon, 4=Fri)"""
    first_day = datetime(year, month, 1)
    first_weekday = first_day.weekday()
    if first_weekday <= weekday:
        first_target = first_day + timedelta(days=weekday - first_weekday)
    else:
        first_target = first_day + timedelta(days=7 - first_weekday + weekday)
    return first_target + timedelta(weeks=n - 1)


def get_all_categories():
    """取得所有期貨類別"""
    return sorted(set(info["category"] for info in FUTURES_CONTRACTS.values()))


if __name__ == "__main__":
    print("=" * 60)
    print("期貨標的池")
    print("=" * 60)

    for code, info in FUTURES_CONTRACTS.items():
        expiry = get_next_expiry(code)
        print(f"\n{code} | {info['name']} ({info['name_en']})")
        print(f"  類別: {info['category']} | 保證金: ${info['margin']:,}")
        print(f"  合約乘數: {info['multiplier']} | 每跳: ${info['tick_value']}")
        if expiry:
            print(f"  下一到期: {expiry['contract_label']} ({expiry['expiry_date'].strftime('%Y-%m-%d')})")
            print(f"  建議換倉: {expiry['rollover_date'].strftime('%Y-%m-%d')} (剩 {expiry['days_to_rollover']} 天)")

    print(f"\n\n帳戶 $7,000 可交易:")
    affordable = get_affordable(7000)
    for code, info in affordable.items():
        print(f"  {code} - {info['name']} (保證金 ${info['margin']:,})")

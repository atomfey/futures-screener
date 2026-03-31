"""
經濟日曆模組
- 提供重大經濟數據排程（靜態+動態）
- 標記受影響的期貨品種
- 輸出 calendar.json
"""

import json
import sys
from datetime import datetime, timedelta
from pathlib import Path
from calendar import monthrange

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

SCRIPT_DIR = Path(__file__).parent
OUTPUT_DIR = SCRIPT_DIR.parent / "docs" / "data"
OUTPUT_FILE = OUTPUT_DIR / "calendar.json"


# ============================================================
# 重大經濟數據定義
# ============================================================

ECONOMIC_EVENTS = [
    {
        "name": "非農就業報告 (NFP)",
        "name_en": "Non-Farm Payrolls",
        "frequency": "monthly",
        "schedule": "first_friday",  # 每月第一個週五
        "time": "08:30 ET",
        "impact": "high",
        "affected": ["MES", "MNQ", "MYM", "M2K", "MGC", "ZN", "6E", "6J"],
        "description": "美國就業市場最重要的指標，影響所有市場",
    },
    {
        "name": "消費者物價指數 (CPI)",
        "name_en": "Consumer Price Index",
        "frequency": "monthly",
        "schedule": "mid_month",  # 約每月 10-15 日
        "time": "08:30 ET",
        "impact": "high",
        "affected": ["MES", "MNQ", "MYM", "M2K", "MGC", "ZN", "6E", "6J"],
        "description": "通膨指標，直接影響 Fed 利率決策",
    },
    {
        "name": "聯準會利率決議 (FOMC)",
        "name_en": "FOMC Rate Decision",
        "frequency": "6weeks",
        "schedule": "fomc",
        "time": "14:00 ET",
        "impact": "high",
        "affected": ["MES", "MNQ", "MYM", "M2K", "MGC", "ZN", "6E", "6J"],
        "description": "Fed 利率決策，影響所有金融市場",
    },
    {
        "name": "EIA 原油庫存報告",
        "name_en": "EIA Crude Oil Inventories",
        "frequency": "weekly",
        "schedule": "wednesday",
        "time": "10:30 ET",
        "impact": "high",
        "affected": ["MCL"],
        "description": "美國原油庫存變化，直接影響油價",
    },
    {
        "name": "USDA 農作物供需報告",
        "name_en": "USDA WASDE Report",
        "frequency": "monthly",
        "schedule": "mid_month",
        "time": "12:00 ET",
        "impact": "high",
        "affected": ["ZC", "ZW", "ZS"],
        "description": "美國農業部月度供需報告，影響農產品價格",
    },
    {
        "name": "GDP 國內生產毛額",
        "name_en": "GDP",
        "frequency": "quarterly",
        "schedule": "late_month",
        "time": "08:30 ET",
        "impact": "medium",
        "affected": ["MES", "MNQ", "MYM", "M2K", "ZN"],
        "description": "美國經濟成長率，每季公布",
    },
    {
        "name": "生產者物價指數 (PPI)",
        "name_en": "Producer Price Index",
        "frequency": "monthly",
        "schedule": "mid_month",
        "time": "08:30 ET",
        "impact": "medium",
        "affected": ["MES", "MNQ", "MGC", "ZN"],
        "description": "批發端通膨指標",
    },
    {
        "name": "零售銷售",
        "name_en": "Retail Sales",
        "frequency": "monthly",
        "schedule": "mid_month",
        "time": "08:30 ET",
        "impact": "medium",
        "affected": ["MES", "MNQ", "MYM", "M2K"],
        "description": "消費者支出指標",
    },
]

# 2026 年 FOMC 會議日期 (預估)
FOMC_DATES_2026 = [
    "2026-01-28", "2026-03-18", "2026-05-06", "2026-06-17",
    "2026-07-29", "2026-09-16", "2026-11-04", "2026-12-16",
]


def _first_friday(year, month):
    """取得某月第一個週五"""
    from datetime import date
    for day in range(1, 8):
        d = date(year, month, day)
        if d.weekday() == 4:  # Friday
            return d
    return None


def _next_wednesday(from_date):
    """取得下一個週三"""
    days_ahead = 2 - from_date.weekday()  # Wednesday = 2
    if days_ahead <= 0:
        days_ahead += 7
    return from_date + timedelta(days=days_ahead)


def get_upcoming_events(days_ahead=14):
    """取得未來 N 天的重大經濟事件"""
    today = datetime.now().date()
    end_date = today + timedelta(days=days_ahead)
    events = []

    for event in ECONOMIC_EVENTS:
        schedule = event["schedule"]

        if schedule == "first_friday":
            # 檢查本月和下月的第一個週五
            for m_offset in range(0, 2):
                year = today.year
                month = today.month + m_offset
                if month > 12:
                    month -= 12
                    year += 1
                d = _first_friday(year, month)
                if d and today <= d <= end_date:
                    events.append({**event, "date": d.isoformat()})

        elif schedule == "wednesday":
            # 每週三
            d = _next_wednesday(today)
            while d <= end_date:
                events.append({**event, "date": d.isoformat()})
                d += timedelta(days=7)

        elif schedule == "fomc":
            for date_str in FOMC_DATES_2026:
                from datetime import date
                d = date.fromisoformat(date_str)
                if today <= d <= end_date:
                    events.append({**event, "date": date_str})

        elif schedule == "mid_month":
            for m_offset in range(0, 2):
                year = today.year
                month = today.month + m_offset
                if month > 12:
                    month -= 12
                    year += 1
                from datetime import date
                d = date(year, month, 12)  # 約每月 12 日
                if today <= d <= end_date:
                    events.append({**event, "date": d.isoformat()})

        elif schedule == "late_month":
            for m_offset in range(0, 2):
                year = today.year
                month = today.month + m_offset
                if month > 12:
                    month -= 12
                    year += 1
                from datetime import date
                d = date(year, month, 25)
                if today <= d <= end_date:
                    events.append({**event, "date": d.isoformat()})

    # 排序
    events.sort(key=lambda x: x["date"])

    # 計算剩餘天數
    for e in events:
        from datetime import date
        d = date.fromisoformat(e["date"])
        e["days_until"] = (d - today).days

    return events


def run_calendar():
    """產生經濟日曆 JSON"""
    print("=" * 60)
    print("經濟日曆")
    print("=" * 60)

    events = get_upcoming_events(days_ahead=30)

    print(f"\n未來 30 天重大經濟事件:")
    for e in events:
        impact_icon = {"high": "[!]", "medium": "[*]", "low": "[-]"}.get(e["impact"], "")
        affected = ", ".join(e["affected"][:5])
        print(f"  {impact_icon} {e['date']} | {e['name']} | 影響: {affected}")

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump({
            "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "events": events,
            "all_events_definition": ECONOMIC_EVENTS,
        }, f, ensure_ascii=False, indent=2)

    print(f"\n經濟日曆已寫入: {OUTPUT_FILE}")
    return events


if __name__ == "__main__":
    run_calendar()

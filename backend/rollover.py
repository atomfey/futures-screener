"""
換倉管理模組
- 管理持倉記錄與合約到期日
- 計算換倉時間表
- 產生 Telegram 提醒訊息
- 輸出 positions.json
"""

import json
import sys
from datetime import datetime, timedelta
from pathlib import Path

from futures_list import FUTURES_CONTRACTS, get_next_expiry

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

SCRIPT_DIR = Path(__file__).parent
OUTPUT_DIR = SCRIPT_DIR.parent / "docs" / "data"
POSITIONS_FILE = OUTPUT_DIR / "positions.json"


def load_positions():
    """載入持倉記錄"""
    if POSITIONS_FILE.exists():
        with open(POSITIONS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {"positions": [], "rollover_history": []}


def save_positions(data):
    """儲存持倉記錄"""
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    with open(POSITIONS_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def check_rollover_alerts(positions_data=None):
    """檢查所有持倉的換倉提醒"""
    if positions_data is None:
        positions_data = load_positions()

    alerts = []
    today = datetime.now()

    for pos in positions_data.get("positions", []):
        if pos.get("status") != "open":
            continue

        symbol = pos.get("symbol")
        if not symbol or symbol not in FUTURES_CONTRACTS:
            continue

        expiry_info = get_next_expiry(symbol, today)
        if not expiry_info:
            continue

        days = expiry_info["days_to_rollover"]
        urgency = (
            "critical" if days <= 3 else
            "urgent" if days <= 7 else
            "warning" if days <= 14 else
            "normal"
        )

        if days <= 14:
            message = _format_alert_message(pos, expiry_info, urgency)
            alerts.append({
                "symbol": symbol,
                "name": FUTURES_CONTRACTS[symbol]["name"],
                "urgency": urgency,
                "days_to_rollover": days,
                "expiry_date": expiry_info["expiry_date"].strftime("%Y-%m-%d"),
                "rollover_date": expiry_info["rollover_date"].strftime("%Y-%m-%d"),
                "contract_month": expiry_info["contract_label"],
                "message": message,
                "position": pos,
            })

    alerts.sort(key=lambda x: x["days_to_rollover"])
    return alerts


def _format_alert_message(pos, expiry_info, urgency):
    """產生 Telegram 提醒訊息"""
    symbol = pos["symbol"]
    name = FUTURES_CONTRACTS[symbol]["name"]
    days = expiry_info["days_to_rollover"]

    urgency_emoji = {
        "critical": "🚨🚨🚨",
        "urgent": "⚠️⚠️",
        "warning": "📢",
        "normal": "📋",
    }[urgency]

    urgency_text = {
        "critical": "必須立即換倉！",
        "urgent": "建議本週內完成換倉",
        "warning": "請準備換倉",
        "normal": "正常追蹤中",
    }[urgency]

    msg = f"""{urgency_emoji} 換倉提醒 - {symbol} {name}

{urgency_text}

品種: {symbol} ({name})
合約月份: {expiry_info['contract_label']}
合約到期: {expiry_info['expiry_date'].strftime('%Y-%m-%d')}
建議換倉: {expiry_info['rollover_date'].strftime('%Y-%m-%d')}
剩餘天數: {days} 天

開倉價: {pos.get('entry_price', '-')}
開倉日期: {pos.get('entry_date', '-')}
方向: {'做多' if pos.get('direction') == 'long' else '做空'}
口數: {pos.get('contracts', 1)}

請及時完成換倉操作，避免被強制平倉或交割。"""

    return msg


def get_all_rollover_schedule():
    """取得所有期貨品種的換倉時間表"""
    today = datetime.now()
    schedule = []

    for code, info in FUTURES_CONTRACTS.items():
        expiry = get_next_expiry(code, today)
        if expiry:
            schedule.append({
                "code": code,
                "name": info["name"],
                "category": info["category"],
                "contract_month": expiry["contract_label"],
                "expiry_date": expiry["expiry_date"].strftime("%Y-%m-%d"),
                "rollover_date": expiry["rollover_date"].strftime("%Y-%m-%d"),
                "days_to_expiry": expiry["days_to_expiry"],
                "days_to_rollover": expiry["days_to_rollover"],
            })

    schedule.sort(key=lambda x: x["days_to_rollover"])
    return schedule


def run_rollover_check():
    """執行換倉檢查"""
    print("=" * 60)
    print("換倉管理")
    print("=" * 60)

    # 換倉時間表
    schedule = get_all_rollover_schedule()
    print("\n所有期貨換倉時間表:")
    for s in schedule:
        urgency = (
            "[!!!]" if s["days_to_rollover"] <= 3 else
            "[!!]" if s["days_to_rollover"] <= 7 else
            "[!]" if s["days_to_rollover"] <= 14 else
            "[ok]"
        )
        print(f"  {urgency} {s['code']:5s} {s['name']:10s} | "
              f"到期: {s['expiry_date']} | 換倉: {s['rollover_date']} | "
              f"剩 {s['days_to_rollover']} 天")

    # 檢查持倉的換倉提醒
    alerts = check_rollover_alerts()
    if alerts:
        print(f"\n持倉換倉提醒 ({len(alerts)}):")
        for a in alerts:
            print(f"  [{a['urgency']}] {a['symbol']} {a['name']} - {a['days_to_rollover']} 天")
    else:
        print("\n目前沒有持倉需要換倉提醒")

    return {"schedule": schedule, "alerts": alerts}


if __name__ == "__main__":
    run_rollover_check()

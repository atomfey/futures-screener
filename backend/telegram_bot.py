"""
Telegram 通知模組
- 發送換倉提醒
- 發送每日篩選結果摘要
- 需要設定 TELEGRAM_BOT_TOKEN 和 TELEGRAM_CHAT_ID
"""

import json
import os
import sys
from pathlib import Path

import requests

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

# ============================================================
# 設定
# ============================================================

# 從環境變數讀取（或在此直接設定）
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")

SCRIPT_DIR = Path(__file__).parent
CONFIG_FILE = SCRIPT_DIR / "telegram_config.json"


def load_config():
    """從設定檔載入 Telegram 設定"""
    global TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID
    if CONFIG_FILE.exists():
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            config = json.load(f)
            TELEGRAM_BOT_TOKEN = config.get("bot_token", TELEGRAM_BOT_TOKEN)
            TELEGRAM_CHAT_ID = config.get("chat_id", TELEGRAM_CHAT_ID)


def save_config(bot_token, chat_id):
    """儲存 Telegram 設定"""
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump({
            "bot_token": bot_token,
            "chat_id": chat_id,
        }, f, indent=2)
    print(f"Telegram 設定已儲存到: {CONFIG_FILE}")


def send_message(text, parse_mode="Markdown"):
    """發送 Telegram 訊息"""
    load_config()

    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        print("[Telegram] 未設定 BOT_TOKEN 或 CHAT_ID，跳過發送")
        print(f"[Telegram] 訊息內容預覽:\n{text[:200]}...")
        return False

    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": text,
        "parse_mode": parse_mode,
    }

    try:
        resp = requests.post(url, json=payload, timeout=10)
        if resp.status_code == 200:
            print("[Telegram] 訊息發送成功")
            return True
        else:
            print(f"[Telegram] 發送失敗: {resp.status_code} - {resp.text}")
            return False
    except Exception as e:
        print(f"[Telegram] 發送錯誤: {e}")
        return False


def send_rollover_alerts(alerts):
    """發送換倉提醒"""
    if not alerts:
        return

    for alert in alerts:
        send_message(alert["message"])


def send_daily_summary(results):
    """發送每日篩選結果摘要"""
    if not results:
        return

    data = results if isinstance(results, dict) else {}
    items = data.get("results", [])

    strong_long = [r for r in items if r["signal"] == "強烈做多"]
    long_list = [r for r in items if r["signal"] == "做多"]
    short_list = [r for r in items if r["signal"] in ("做空", "強烈做空")]

    msg = f"""📊 *期貨篩選日報*
_{data.get('generated_at', '')}_

"""

    if strong_long:
        msg += f"🟢🟢 *強烈做多* ({len(strong_long)}):\n"
        for r in strong_long:
            msg += f"  `{r['code']}` {r['name']} | {r['long_score']}/{r['total_conditions']} | {r['price']}\n"
        msg += "\n"

    if long_list:
        msg += f"🟢 *做多* ({len(long_list)}):\n"
        for r in long_list:
            msg += f"  `{r['code']}` {r['name']} | {r['long_score']}/{r['total_conditions']} | {r['price']}\n"
        msg += "\n"

    if short_list:
        msg += f"🔴 *做空* ({len(short_list)}):\n"
        for r in short_list:
            msg += f"  `{r['code']}` {r['name']} | {r['price']}\n"
        msg += "\n"

    # 換倉提醒
    urgent = [r for r in items if r.get("days_to_rollover") and r["days_to_rollover"] <= 14]
    if urgent:
        msg += "⚠️ *換倉提醒:*\n"
        for r in urgent:
            msg += f"  `{r['code']}` {r['name']} → {r['next_rollover']} ({r['days_to_rollover']}天)\n"

    send_message(msg)


def setup_telegram():
    """互動式設定 Telegram Bot"""
    print("=" * 60)
    print("Telegram Bot 設定")
    print("=" * 60)
    print()
    print("步驟 1: 在 Telegram 中搜尋 @BotFather")
    print("步驟 2: 發送 /newbot 建立新機器人")
    print("步驟 3: 複製 Bot Token")
    print("步驟 4: 將 Bot 加入你的群組或私聊")
    print("步驟 5: 取得 Chat ID (可透過 @userinfobot)")
    print()

    token = input("請輸入 Bot Token: ").strip()
    chat_id = input("請輸入 Chat ID: ").strip()

    if token and chat_id:
        save_config(token, chat_id)
        # 測試發送
        TELEGRAM_BOT_TOKEN = token
        TELEGRAM_CHAT_ID = chat_id
        test_msg = "🤖 ASTC 期貨篩選器 Telegram 連接成功！\n換倉提醒和每日篩選結果將透過此頻道推送。"
        send_message(test_msg)
    else:
        print("設定取消")


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "setup":
        setup_telegram()
    else:
        # 測試發送
        load_config()
        send_message("🧪 Telegram 測試訊息 - ASTC 期貨篩選器")

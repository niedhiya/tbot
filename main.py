import time
import os
import requests
from tradingview_ta import TA_Handler, Interval, Exchange

TOKEN = os.environ.get("TELEGRAM_TOKEN")
URL = f"https://api.telegram.org/bot{TOKEN}"

# Daftar ticker yang ingin dipantau
TICKERS = ["BBCA", "BBRI", "TLKM", "UNVR", "ANTM"]

def send_message(chat_id, text):
    url = f"{URL}/sendMessage"
    payload = {"chat_id": chat_id, "text": text}
    requests.post(url, json=payload)

def check_macd_golden_cross(ticker):
    handler = TA_Handler(
        symbol=ticker,
        screener="indonesia",
        exchange="IDX",
        interval=Interval.INTERVAL_1_MINUTE
    )
    analysis = handler.get_analysis()
    macd = analysis.indicators.get("MACD.macd")
    signal = analysis.indicators.get("MACD.signal")
    # Golden Cross: MACD baru saja melintasi signal dari bawah ke atas
    if macd and signal and macd > signal:
        return True
    return False

def main():
    subscribers = set()
    offset = None

    while True:
        # Ambil update Telegram
        updates = requests.get(f"{URL}/getUpdates", params={"offset": offset, "timeout": 100}).json()
        for update in updates.get("result", []):
            message = update.get("message")
            if message:
                chat_id = message["chat"]["id"]
                text = message.get("text", "").lower()
                subscribers.add(chat_id)
                if "/start" in text:
                    send_message(chat_id, "Bot MACD Golden Cross setiap 1 menit aktif. Kamu akan mendapat notifikasi.")
                offset = update["update_id"] + 1

        # Cek MACD setiap 60 detik
        for ticker in TICKERS:
            if check_macd_golden_cross(ticker):
                for chat_id in subscribers:
                    send_message(chat_id, f"📈 MACD Golden Cross terdeteksi di {ticker}!")

        time.sleep(60)

if __name__ == "__main__":
    main()

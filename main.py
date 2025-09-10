import time
import os
import requests
import pandas as pd
import yfinance as yf
import talib

TOKEN = os.environ.get("TELEGRAM_TOKEN")
URL = f"https://api.telegram.org/bot{TOKEN}"

# Load semua ticker IDX dari file XLSX
def load_idx_tickers(file_path="tickers_idx.xlsx"):
    df = pd.read_excel(file_path)
    tickers = df['Code'].astype(str).tolist()  # kolom 'Code' sesuai XLSX IDX
    tickers = [t + ".JK" for t in tickers]    # format Yahoo Finance IDX
    return tickers

def send_message(chat_id, text):
    try:
        requests.post(f"{URL}/sendMessage", json={"chat_id": chat_id, "text": text})
    except Exception as e:
        print(f"Error sending message: {e}")

def check_macd_golden_cross(ticker):
    try:
        df = yf.download(ticker, period="7d", interval="5m")
        if df.empty or len(df) < 26:
            print(f"{ticker}: Not enough data")
            return False
        macd, signal, hist = talib.MACD(df['Close'], fastperiod=12, slowperiod=26, signalperiod=9)
        # Golden Cross: MACD melintasi signal dari bawah ke atas
        if macd.iloc[-2] < signal.iloc[-2] and macd.iloc[-1] > signal.iloc[-1]:
            print(f"{ticker}: Golden Cross detected ✅")
            return True
        else:
            print(f"{ticker}: No Golden Cross")
    except Exception as e:
        print(f"Error {ticker}: {e}")
    return False

def main():
    subscribers = set()

    # Ambil offset awal agar tidak membaca update lama
    try:
        updates = requests.get(f"{URL}/getUpdates", params={"timeout":100}).json()
        if updates["result"]:
            offset = updates["result"][-1]["update_id"] + 1
        else:
            offset = None
    except Exception as e:
        print(f"Error initializing offset: {e}")
        offset = None

    tickers = load_idx_tickers("tickers_idx.xlsx")
    print(f"{len(tickers)} tickers loaded.")

    while True:
        # Ambil update Telegram baru
        try:
            updates = requests.get(f"{URL}/getUpdates", params={"offset": offset, "timeout":100}).json()
            for update in updates.get("result", []):
                print("Update received:", update)
                message = update.get("message")
                if message:
                    chat_id = message["chat"]["id"]
                    text = message.get("text", "").lower()
                    if "/start" in text:
                        send_message(chat_id, "Bot MACD Golden Cross IDX aktif. Kamu akan menerima notifikasi otomatis.")
                        subscribers.add(chat_id)
                    offset = update["update_id"] + 1
        except Exception as e:
            print(f"Error fetching updates: {e}")

        # Screening semua ticker tiap 5 menit
        for ticker in tickers:
            if check_macd_golden_cross(ticker):
                for chat_id in subscribers:
                    send_message(chat_id, f"📈 MACD Golden Cross terdeteksi pada {ticker}!")

        print("Sleeping 5 minutes...")
        time.sleep(300)  # 5 menit

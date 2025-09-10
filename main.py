import time
import os
import requests
import pandas as pd
import pandas_ta as ta
import yfinance as yf

TOKEN = os.environ.get("TELEGRAM_TOKEN")
URL = f"https://api.telegram.org/bot{TOKEN}"

# Load semua ticker IDX dari file XLSX
def load_idx_tickers(file_path="tickers_idx.xlsx"):
    df = pd.read_excel(file_path)
    # Ambil kolom 'Code' atau 'Ticker' sesuai nama kolom di file XLSX IDX
    tickers = df['Code'].astype(str).tolist()
    tickers = [t + ".JK" for t in tickers]  # format Yahoo Finance IDX
    return tickers

def send_message(chat_id, text):
    requests.post(f"{URL}/sendMessage", json={"chat_id": chat_id, "text": text})

def check_macd_golden_cross(ticker):
    try:
        df = yf.download(ticker, period="2d", interval="1m")
        if len(df) < 26:
            return False
        macd = ta.macd(df['Close'])
        df = df.join(macd)
        # Golden Cross: MACD melintasi signal dari bawah ke atas
        if df['MACD_12_26_9'].iloc[-2] < df['MACDs_12_26_9'].iloc[-2] and \
           df['MACD_12_26_9'].iloc[-1] > df['MACDs_12_26_9'].iloc[-1]:
            return True
    except Exception as e:
        print(f"Error {ticker}: {e}")
    return False

def main():
    subscribers = set()
    offset = None
    tickers = load_idx_tickers("tickers_idx.xlsx")

    while True:
        # Ambil update Telegram
        updates = requests.get(f"{URL}/getUpdates", params={"offset": offset, "timeout": 100}).json()
        for update in updates.get("result", []):
            message = update.get("message")
            if message:
                chat_id = message["chat"]["id"]
                text = message.get("text", "").lower()
                if "/start" in text:
                    send_message(chat_id, "Bot MACD Golden Cross IDX aktif. Kamu akan menerima notifikasi otomatis.")
                    subscribers.add(chat_id)
                offset = update["update_id"] + 1

        # Screening semua ticker tiap 1 menit
        for ticker in tickers:
            if check_macd_golden_cross(ticker):
                for chat_id in subscribers:
                    send_message(chat_id, f"📈 MACD Golden Cross terdeteksi pada {ticker}!")

        time.sleep(60)

if __name__ == "__main__":
    main()

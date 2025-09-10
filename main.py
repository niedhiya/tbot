import time
import os
import requests
import pandas as pd
from threading import Thread
from tradingview_ta import TA_Handler, Interval

TOKEN = os.environ.get("TELEGRAM_TOKEN")
URL = f"https://api.telegram.org/bot{TOKEN}"

# Load ticker IDX
def load_idx_tickers(file_path="tickers_idx.xlsx"):
    df = pd.read_excel(file_path)
    tickers = df['Code'].astype(str).tolist()
    return tickers, df.set_index('Code')

tickers_list, tickers_df = load_idx_tickers()

# Telegram helper
def send_message(chat_id, text):
    try:
        requests.post(f"{URL}/sendMessage", json={"chat_id": chat_id, "text": text})
    except Exception as e:
        print(f"Error sending message: {e}")

# TradingView TA
INTERVAL = Interval.INTERVAL_1_DAY  # default daily interval
CACHE_EXPIRY = 60  # detik

ta_cache = {}  # {ticker: {'indicators': ..., 'summary': ...}}

# Ambil TA per ticker
def get_tv_ta(symbol):
    try:
        handler = TA_Handler(symbol=symbol, screener="indonesia", exchange="IDX", interval=INTERVAL)
        analysis = handler.get_analysis()
        return analysis.indicators, analysis.summary
    except Exception as e:
        print(f"[ERROR] Ticker {symbol} gagal diambil: {e}")
        return None, None

# Perulangan /ta_all simpan data
def ta_all_loop(save_to_file=True):
    for t in tickers_list:
        indicators, summary = get_tv_ta(t)
        if indicators:
            ta_cache[t] = {'indicators': indicators, 'summary': summary}
            print(f"TA {t} berhasil diambil.")
        else:
            print(f"TA {t} gagal diambil.")
        time.sleep(1)  # delay supaya tidak overload request

    if save_to_file:
        df_list = []
        for ticker, data in ta_cache.items():
            row = {'Ticker': ticker}
            row.update(data['indicators'])
            row.update({'Summary': data['summary'].get('RECOMMENDATION')})
            df_list.append(row)
        df = pd.DataFrame(df_list)
        df.to_excel("ta_idx_1day.xlsx", index=False)
        print("Semua data TA tersimpan di ta_idx_1day.xlsx")

# Telegram bot untuk /ta_all
subscribers = set()

def auto_check():
    while True:
        # bisa dipakai untuk screener otomatis tiap CACHE_EXPIRY detik
        time.sleep(CACHE_EXPIRY)

# Telegram main loop
def main():
    global INTERVAL, CACHE_EXPIRY
    offset = None
    Thread(target=auto_check, daemon=True).start()
    print("Bot started...")

    while True:
        try:
            updates = requests.get(f"{URL}/getUpdates", params={"offset": offset, "timeout":100}).json()
            for update in updates.get("result", []):
                message = update.get("message")
                if message:
                    chat_id = message["chat"]["id"]
                    text = message.get("text", "").lower()

                    if "/start" in text:
                        send_message(chat_id, "Bot aktif. Perintah:\n/ta <TICKER>\n/ta_all\n/screener\n/set_interval <INTERVAL>\n/set_cache <SECONDS>")
                        subscribers.add(chat_id)

                    elif text.startswith("/ta "):
                        parts = text.split()
                        if len(parts) == 2:
                            symbol = parts[1].upper()
                            indicators, summary = get_tv_ta(symbol)
                            if indicators:
                                msg = f"{symbol} TA:\n"
                                for k,v in indicators.items():
                                    msg += f"{k}: {v}\n"
                                msg += f"Summary: {summary.get('RECOMMENDATION')}"
                                send_message(chat_id, msg)
                            else:
                                send_message(chat_id, f"TA {symbol} tidak tersedia")

                    elif text.startswith("/ta_all"):
                        send_message(chat_id, "Memulai pengambilan TA semua ticker...")
                        ta_all_loop()  # jalankan perulangan dan simpan data
                        send_message(chat_id, "Selesai mengambil TA semua ticker dan tersimpan di ta_idx_1day.xlsx")

                    offset = update["update_id"] + 1
        except Exception as e:
            print(f"Error: {e}")
        time.sleep(5)

if __name__ == "__main__":
    main()

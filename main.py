import time
import os
import requests
import pandas as pd
from tradingview_ta import TA_Handler, Interval

TOKEN = os.environ.get("TELEGRAM_TOKEN")
URL = f"https://api.telegram.org/bot{TOKEN}"

# Load ticker IDX
def load_idx_tickers(file_path="tickers_idx.xlsx"):
    df = pd.read_excel(file_path)
    tickers = df['Code'].astype(str).tolist()
    return tickers, df.set_index('Code')

tickers_list, tickers_df = load_idx_tickers()

INTERVAL = Interval.INTERVAL_1_DAY
CACHE_EXPIRY = 60
ta_cache = {}  # {ticker: {indicators, summary}}

# Telegram helper
def send_message(chat_id, text):
    try:
        requests.post(f"{URL}/sendMessage", json={"chat_id": chat_id, "text": text})
    except Exception as e:
        print(f"Error sending message: {e}")

# TradingView TA dengan retry
def get_tv_ta(symbol, retries=3):
    for i in range(retries):
        try:
            handler = TA_Handler(symbol=symbol, screener="indonesia", exchange="IDX", interval=INTERVAL)
            analysis = handler.get_analysis()
            return analysis.indicators, analysis.summary
        except Exception as e:
            print(f"[ERROR] {symbol} attempt {i+1} failed: {e}")
            time.sleep(1)
    return None, None

# /ta_all dengan log ke Telegram
def ta_all_loop(chat_id):
    log_msgs = []
    for t in tickers_list:
        indicators, summary = get_tv_ta(t)
        if indicators:
            ta_cache[t] = {'indicators': indicators, 'summary': summary}
            msg = f"✅ {t}: TA berhasil diambil. Summary: {summary.get('RECOMMENDATION')}"
        else:
            msg = f"❌ {t}: Gagal diambil"
        log_msgs.append(msg)
        send_message(chat_id, msg)  # kirim tiap ticker agar bisa dibaca real-time
        time.sleep(1)  # delay supaya tidak kena rate limit

    # Simpan ke Excel setelah selesai
    df_list = []
    for ticker, data in ta_cache.items():
        row = {'Ticker': ticker}
        row.update(data['indicators'])
        row.update({'Summary': data['summary'].get('RECOMMENDATION')})
        df_list.append(row)
    df = pd.DataFrame(df_list)
    df.to_excel("ta_idx_1day.xlsx", index=False)
    send_message(chat_id, "✅ Semua TA tersimpan di ta_idx_1day.xlsx")

# Telegram main loop sederhana
def main():
    offset = None
    while True:
        try:
            updates = requests.get(f"{URL}/getUpdates", params={"offset": offset, "timeout":100}).json()
            for update in updates.get("result", []):
                message = update.get("message")
                if message:
                    chat_id = message["chat"]["id"]
                    text = message.get("text","").lower()

                    if "/start" in text:
                        send_message(chat_id, "Bot aktif. Perintah:\n/ta <TICKER>\n/ta_all")

                    elif text.startswith("/ta_all"):
                        send_message(chat_id, "Mulai mengambil TA semua ticker IDX...")
                        ta_all_loop(chat_id)
                        send_message(chat_id, "✅ Selesai semua ticker.")

                    offset = update["update_id"] + 1
        except Exception as e:
            print(f"Error: {e}")
        time.sleep(5)

if __name__ == "__main__":
    main()

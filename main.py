import time
import os
import requests
import pandas as pd
from tradingview_ta import TA_Handler, Interval

TOKEN = os.environ.get("TELEGRAM_TOKEN")
URL = f"https://api.telegram.org/bot{TOKEN}"

INTERVAL = Interval.INTERVAL_1_DAY
CACHE_EXPIRY = 60

ta_cache = {}  # {ticker: {indicators, summary}}

# Ambil list ticker IDX dari TradingView Scanner JSON
def load_idx_tickers_from_tv():
    url = 'https://scanner.tradingview.com/indonesia/scan'
    payload = {
        "filter":[],
        "options":{"lang":"en"},
        "symbols":{"query":{"types":[]}},
        "columns":["name"]
    }
    try:
        r = requests.post(url, json=payload)
        data = r.json()
        tickers = []
        for item in data.get('data', []):
            name = item.get('d', [])[0]  # biasanya kolom pertama adalah symbol
            if name:
                tickers.append(name.replace('IDX:',''))  # hapus prefix IDX jika ada
        return tickers
    except Exception as e:
        print(f"Gagal ambil ticker dari TradingView: {e}")
        return []

tickers_list = load_idx_tickers_from_tv()

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
        send_message(chat_id, msg)
        time.sleep(1)

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
                    text = message.get("text","").lower()+"

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

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
INTERVAL = Interval.INTERVAL_1_MINUTE  # default intraday
CACHE_EXPIRY = 60  # detik

ta_cache = {}  # {ticker: {'time': timestamp, 'data': indicators, 'summary': summary}}

def get_tv_ta(symbol):
    try:
        handler = TA_Handler(symbol=symbol, screener="indonesia", exchange="IDX", interval=INTERVAL)
        analysis = handler.get_analysis()
        return analysis.indicators, analysis.summary
    except Exception as e:
        print(f"TradingView TA error for {symbol}: {e}")
        return None, None

def get_cached_ta(symbol):
    now = time.time()
    if symbol in ta_cache and now - ta_cache[symbol]['time'] < CACHE_EXPIRY:
        return ta_cache[symbol]['data'], ta_cache[symbol]['summary']
    indicators, summary = get_tv_ta(symbol)
    if indicators:
        ta_cache[symbol] = {'time': now, 'data': indicators, 'summary': summary}
    return indicators, summary

# Preload TA semua ticker sesuai interval
def preload_all_ta():
    for t in tickers_list:
        get_cached_ta(t)

# Screener dynamic
screener_filters = {
    'MACD': 'Golden Cross',  # contoh default filter
    'RSI': '<70',
    'Stochastic_K': '<80',
    'Summary': None  # abaikan summary default
}

def run_screener():
    preload_all_ta()  # pastikan semua TA di-cache
    results = []
    for t in tickers_list:
        indicators, summary = get_cached_ta(t)
        if not indicators:
            continue
        passed = True
        for key, condition in screener_filters.items():
            if key in summary and condition is not None:
                if summary[key] != condition:
                    passed = False
            if key in indicators and '<' in condition:
                threshold = float(condition.replace('<',''))
                val = indicators[key]
                if val >= threshold:
                    passed = False
        if passed:
            results.append(t)
    return results

# Background auto-check for screener
subscribers = set()

def auto_check():
    while True:
        screened = run_screener()
        if screened:
            msg = "🔍 Screener IDX (Filter Dinamis):\n" + "\n".join(screened)
            for chat_id in subscribers:
                send_message(chat_id, msg)
        time.sleep(CACHE_EXPIRY)

# Telegram main loop
def main():
    global INTERVAL, CACHE_EXPIRY
    offset = None
    Thread(target=auto_check, daemon=True).start()
    print("Bot started...")

    # preload semua TA sesuai interval saat bot start
    preload_all_ta()

    while True:
        try:
            updates = requests.get(f"{URL}/getUpdates", params={"offset": offset, "timeout":100}).json()
            for update in updates.get("result", []):
                message = update.get("message")
                if message:
                    chat_id = message["chat"]["id"]
                    text = message.get("text", "").lower()

                    if "/start" in text:
                        send_message(chat_id, "Bot aktif. Perintah:\n/ta <TICKER>\n/ta_all\n/screener\n/set_interval <INTERVAL>\n/set_cache <SECONDS>\n/set_filter <KEY>=<VALUE>")
                        subscribers.add(chat_id)

                    elif text.startswith("/ta "):
                        parts = text.split()
                        if len(parts) == 2:
                            symbol = parts[1].upper()
                            indicators, summary = get_cached_ta(symbol)
                            if indicators:
                                msg = f"{symbol} TA:\n"
                                for k,v in indicators.items():
                                    msg += f"{k}: {v}\n"
                                msg += f"Summary: {summary.get('RECOMMENDATION')}"
                                send_message(chat_id, msg)
                            else:
                                send_message(chat_id, f"TA {symbol} tidak tersedia")

                    elif text.startswith("/ta_all"):
                        msg = "TA semua ticker IDX:\n"
                        preload_all_ta()  # update semua TA
                        for t in tickers_list:
                            indicators, summary = get_cached_ta(t)
                            if indicators:
                                msg += f"{t}: Summary {summary.get('RECOMMENDATION')}\n"
                        send_message(chat_id, msg)

                    elif text.startswith("/screener"):
                        screened = run_screener()
                        if screened:
                            msg = "🔍 Screener IDX:\n" + "\n".join(screened)
                        else:
                            msg = "Tidak ada saham memenuhi kriteria saat ini."
                        send_message(chat_id, msg)

                    elif text.startswith("/set_interval"):
                        parts = text.split()
                        if len(parts) == 2:
                            val = parts[1].upper()
                            INTERVAL = getattr(Interval, val, INTERVAL)
                            send_message(chat_id, f"Interval TA diubah ke {INTERVAL}")

                    elif text.startswith("/set_cache"):
                        parts = text.split()
                        if len(parts) == 2:
                            try:
                                CACHE_EXPIRY = int(parts[1])
                                send_message(chat_id, f"Cache expiry diubah ke {CACHE_EXPIRY} detik")
                            except:
                                send_message(chat_id, "Format salah. Gunakan: /set_cache <detik>")

                    elif text.startswith("/set_filter"):
                        parts = text.split()[1:]
                        for p in parts:
                            if '=' in p:
                                k,v = p.split('=',1)
                                screener_filters[k] = v
                        send_message(chat_id, f"Filter screener diperbarui: {screener_filters}")

                    offset = update["update_id"] + 1
        except Exception as e:
            print(f"Error: {e}")
        time.sleep(5)

if __name__ == "__main__":
    main()

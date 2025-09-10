import time
import os
import requests
import threading
from tradingview_ta import TA_Handler, Interval

# ---------------- Config Telegram ----------------
TOKEN = os.environ.get("TELEGRAM_TOKEN")
URL = f"https://api.telegram.org/bot{TOKEN}"
UPDATE_INTERVAL = 600  # 10 menit default
TA_INTERVAL = Interval.INTERVAL_1_HOUR

screener_thread_running = False
last_crossup_results = {}
default_delay = 2
current_delay = default_delay
ta_cache = {}
cache_expiry = 600

# Ambil ticker IDX
def load_idx_tickers_from_tv():
    url = 'https://scanner.tradingview.com/indonesia/scan'
    payload = {"filter":[],"options":{"lang":"en"},"symbols":{"query":{"types":[]}},"columns":["name"]}
    try:
        r = requests.post(url, json=payload)
        data = r.json()
        tickers = [item['d'][0].replace('IDX:', '') for item in data.get('data', []) if item.get('d')]
        return tickers
    except Exception as e:
        print(f"ERROR ambil ticker: {e}")
        return []

tickers_list = load_idx_tickers_from_tv()

# ---------------- Telegram helper ----------------
def send_message(chat_id, text):
    try:
        requests.post(f"{URL}/sendMessage", json={"chat_id": chat_id, "text": text})
    except Exception as e:
        print(f"Error sending message: {e}")

# ---------------- Ambil TA per ticker adaptif ----------------
def get_tv_ta(symbol, retries=5):
    global current_delay
    for attempt in range(retries):
        try:
            cached = ta_cache.get(symbol)
            if cached and time.time() - cached['timestamp'] < cache_expiry:
                return cached['indicators'], cached['summary']

            handler = TA_Handler(symbol=symbol, screener="indonesia", exchange="IDX", interval=TA_INTERVAL)
            analysis = handler.get_analysis()
            ta_cache[symbol] = {
                "indicators": analysis.indicators,
                "summary": analysis.summary,
                "timestamp": time.time()
            }
            time.sleep(current_delay)
            return analysis.indicators, analysis.summary

        except Exception as e:
            err_str = str(e)
            if "429" in err_str:
                current_delay += 1
                print(f"⚠️ {symbol} 429 detected, increasing delay to {current_delay} sec")
            else:
                print(f"{symbol} attempt {attempt+1} failed: {e}")
            time.sleep(current_delay)
    return None, None

# ---------------- Screener EMA5 crossup EMA20 ----------------
def run_screener_ema_crossup(chat_id):
    global last_crossup_results
    batch_size = 10
    any_crossup = False

    for i in range(0, len(tickers_list), batch_size):
        batch = tickers_list[i:i+batch_size]
        for ticker in batch:
            indicators, summary = get_tv_ta(ticker)
            if not indicators:
                continue

            ema5 = indicators.get("EMA5")
            ema20 = indicators.get("EMA20")

            if ema5 is None or ema20 is None:
                continue

            crossup = ema5 > ema20
            if crossup:
                any_crossup = True
                if ticker not in last_crossup_results or not last_crossup_results[ticker]:
                    msg = f"✅ {ticker} EMA5 crossup EMA20!\nEMA5: {ema5}\nEMA20: {ema20}\nSummary: {summary.get('RECOMMENDATION')}"
                    send_message(chat_id, msg)
                    last_crossup_results[ticker] = True
            else:
                if ticker in last_crossup_results and last_crossup_results[ticker]:
                    send_message(chat_id, f"❌ {ticker} keluar dari EMA5 crossup EMA20")
                    last_crossup_results[ticker] = False

            time.sleep(0.5)

    if not any_crossup:
        send_message(chat_id, "⚠️ Screener selesai, tidak ada EMA5 crossup EMA20 saat ini.")

# ---------------- Screener Thread ----------------
def screener_thread(chat_id):
    global screener_thread_running
    while screener_thread_running:
        run_screener_ema_crossup(chat_id)
        time.sleep(UPDATE_INTERVAL)

# ---------------- Telegram Main Loop ----------------
def main():
    global TA_INTERVAL, screener_thread_running
    offset = None
    while True:
        try:
            updates = requests.get(f"{URL}/getUpdates", params={"offset": offset, "timeout":100}).json()
            for update in updates.get("result", []):
                message = update.get("message")
                if message:
                    chat_id = message["chat"]["id"]
                    text = message.get("text", "").lower()

                    if "/start" in text:
                        send_message(chat_id, "Bot EMA crossup aktif.\nPerintah:\n/ta <TICKER>\n/screener_start\n/screener_stop\n/set_interval")

                    elif text.startswith("/ta "):
                        parts = text.split()
                        if len(parts) == 2:
                            symbol = parts[1].upper()
                            indicators, summary = get_tv_ta(symbol)
                            if indicators:
                                msg = f"{symbol} TA (Interval: {TA_INTERVAL}):\n"
                                for k, v in indicators.items():
                                    msg += f"{k}: {v}\n"
                                msg += f"Summary: {summary.get('RECOMMENDATION')}"
                                send_message(chat_id, msg)
                            else:
                                send_message(chat_id, f"TA {symbol} tidak tersedia")

                    elif text.startswith("/screener_start"):
                        if not screener_thread_running:
                            screener_thread_running = True
                            threading.Thread(target=screener_thread, args=(chat_id,), daemon=True).start()
                            send_message(chat_id, f"✅ Screener EMA5 crossup EMA20 realtime dimulai (refresh tiap {UPDATE_INTERVAL//60} menit)")
                        else:
                            send_message(chat_id, "Screener sudah berjalan.")

                    elif text.startswith("/screener_stop"):
                        if screener_thread_running:
                            screener_thread_running = False
                            send_message(chat_id, "🛑 Screener dihentikan.")
                        else:
                            send_message(chat_id, "Screener belum berjalan.")

                    elif text.startswith("/set_interval"):
                        parts = text.split()
                        if len(parts) == 2:
                            interval_str = parts[1].lower()
                            mapping = {
                                "1m": Interval.INTERVAL_1_MINUTE,
                                "5m": Interval.INTERVAL_5_MINUTES,
                                "15m": Interval.INTERVAL_15_MINUTES,
                                "1h": Interval.INTERVAL_1_HOUR,
                                "1d": Interval.INTERVAL_1_DAY
                            }
                            if interval_str in mapping:
                                TA_INTERVAL = mapping[interval_str]
                                send_message(chat_id, f"✅ Interval diperbarui menjadi {interval_str}")
                            else:
                                send_message(chat_id, "Format interval salah. Gunakan: 1m,5m,15m,1h,1d")

                    offset = update["update_id"] + 1
        except Exception as e:
            print(f"Main loop error: {e}")
        time.sleep(5)

if __name__ == "__main__":
    main()

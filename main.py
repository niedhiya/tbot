import time
import os
import requests
import threading
from tradingview_ta import TA_Handler, Interval

# ---------------- Config Telegram ----------------
TOKEN = os.environ.get("TELEGRAM_TOKEN")
URL = f"https://api.telegram.org/bot{TOKEN}"
UPDATE_INTERVAL = 600  # 10 menit
TA_INTERVAL = Interval.INTERVAL_1_HOUR

# Screener control
screener_thread_running = False
last_screener_results = {}
default_delay = 2
current_delay = default_delay

# Filter khusus RSI > 50
criteria = {"RSI": ">50"}

# Cache TA
ta_cache = {}
cache_expiry = 600

# ---------------- Ambil ticker ----------------
def load_idx_tickers_from_tv():
    url = 'https://scanner.tradingview.com/indonesia/scan'
    payload = {"filter":[],"options":{"lang":"en"},"symbols":{"query":{"types":[]}},"columns":["name"]}
    try:
        r = requests.post(url, json=payload)
        data = r.json()
        tickers = []
        for item in data.get('data', []):
            d_values = item.get('d', [])
            if len(d_values) > 0:
                name = d_values[0]
                if name:
                    tickers.append(name.replace('IDX:', ''))
        return tickers
    except Exception as e:
        send_error(f"Gagal ambil ticker: {e}")
        return []

tickers_list = load_idx_tickers_from_tv()

# ---------------- Telegram helper ----------------
def send_message(chat_id, text):
    try:
        requests.post(f"{URL}/sendMessage", json={"chat_id": chat_id, "text": text})
    except Exception as e:
        send_error(f"Error sending message: {e}")

def send_error(text):
    admin_chat_id = os.environ.get("ADMIN_CHAT_ID")
    if admin_chat_id:
        try:
            requests.post(f"{URL}/sendMessage", json={"chat_id": admin_chat_id, "text": f"⚠️ ERROR: {text}"})
        except:
            print(f"ERROR sending error message: {text}")
    print(f"ERROR: {text}")

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

            if current_delay > default_delay:
                current_delay = max(default_delay, current_delay - 0.5)

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

# ---------------- Screener RSI > 50 ----------------
def run_screener_rsi(chat_id):
    global last_screener_results
    batch_size = 10
    any_lolos = False

    for i in range(0, len(tickers_list), batch_size):
        batch = tickers_list[i:i+batch_size]
        for ticker in batch:
            indicators, summary = get_tv_ta(ticker)
            if not indicators:
                continue

            val = indicators.get("RSI")
            match = val is not None and val > 50

            if match:
                any_lolos = True
                if ticker not in last_screener_results or last_screener_results[ticker] != "RSI>50":
                    msg = f"✅ {ticker} RSI>50!\nRSI: {val}\nSummary: {summary.get('RECOMMENDATION')}"
                    send_message(chat_id, msg)
                    last_screener_results[ticker] = "RSI>50"
            else:
                if ticker in last_screener_results:
                    send_message(chat_id, f"❌ {ticker} keluar dari RSI>50")
                    del last_screener_results[ticker]

            time.sleep(0.5)

    if not any_lolos:
        send_message(chat_id, "⚠️ Screener selesai, tidak ada ticker RSI>50 saat ini.")

# ---------------- Screener Thread ----------------
def screener_thread(chat_id):
    global screener_thread_running
    while screener_thread_running:
        run_screener_rsi(chat_id)
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
                        send_message(chat_id, "Bot aktif. Perintah:\n/ta <TICKER>\n/screener_start\n/screener_stop\n/set_interval")

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
                            send_message(chat_id, f"✅ Screener RSI>50 realtime dimulai (refresh tiap {UPDATE_INTERVAL//60} menit)")
                        else:
                            send_message(chat_id, "Screener sudah berjalan.")

                    elif text.startswith("/screener_stop"):
                        if screener_thread_running:
                            screener_thread_running = False
                            send_message(chat_id, "🛑 Screener realtime dihentikan.")
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
                                send_message(chat_id, f"✅ Interval TA diperbarui menjadi {interval_str}")
                            else:
                                send_message(chat_id, "Format interval salah. Gunakan: 1m,5m,15m,1h,1d")

                    offset = update["update_id"] + 1
        except Exception as e:
            send_error(f"Main loop error: {e}")
        time.sleep(5)

if __name__ == "__main__":
    main()

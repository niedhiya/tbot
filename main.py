import time
import os
import requests
import threading
from tradingview_ta import get_multiple_analysis, Interval

# ---------------- Config Telegram ----------------
TOKEN = os.environ.get("TELEGRAM_TOKEN")
URL = f"https://api.telegram.org/bot{TOKEN}"
UPDATE_INTERVAL = 600  # Screener refresh tiap 10 menit
TA_INTERVAL = Interval.INTERVAL_1_HOUR  # Interval 1 jam

screener_thread_running = False
last_crossup_results = {}

DELAY = 10  # 10 detik per batch
batch_size = 10

# ---------------- Ambil ticker IDX ----------------
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

# ---------------- Screener Stochastic crossup ----------------
def run_screener_stochastic_crossup(chat_id):
    global last_crossup_results
    any_crossup = False

    for i in range(0, len(tickers_list), batch_size):
        batch = tickers_list[i:i+batch_size]
        try:
            analyses = get_multiple_analysis(
                screener="indonesia",
                interval=TA_INTERVAL,
                symbols=[f"IDX:{t}" for t in batch]
            )
        except Exception as e:
            print(f"Batch error: {e}")
            time.sleep(DELAY)
            continue

        for symbol_full, data in analyses.items():
            ticker = symbol_full.replace("IDX:", "")
            indicators = data.indicators

            stochastic_k = indicators.get("STOCH.K")
            stochastic_d = indicators.get("STOCH.D")

            if stochastic_k is None or stochastic_d is None:
                continue

            crossup = stochastic_k > stochastic_d

            if crossup:
                any_crossup = True
                if ticker not in last_crossup_results or not last_crossup_results[ticker]:
                    msg = f"✅ {ticker} Stochastic K crossup D\nK: {stochastic_k}\nD: {stochastic_d}"
                    send_message(chat_id, msg)
                    last_crossup_results[ticker] = True
            else:
                if ticker in last_crossup_results and last_crossup_results[ticker]:
                    send_message(chat_id, f"❌ {ticker} keluar dari Stochastic K crossup D")
                    last_crossup_results[ticker] = False

        time.sleep(DELAY)

    if not any_crossup:
        send_message(chat_id, "⚠️ Screener selesai, tidak ada Stochastic crossup saat ini.")

# ---------------- Screener Thread ----------------
def screener_thread(chat_id):
    global screener_thread_running
    while screener_thread_running:
        run_screener_stochastic_crossup(chat_id)
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
                        send_message(chat_id, "Bot Stochastic crossup 1H aktif.\nPerintah:\n/screener_start\n/screener_stop\n/set_interval")

                    elif text.startswith("/screener_start"):
                        if not screener_thread_running:
                            screener_thread_running = True
                            threading.Thread(target=screener_thread, args=(chat_id,), daemon=True).start()
                            send_message(chat_id, "✅ Screener Stochastic crossup 1H realtime dimulai (refresh tiap 10 menit)")
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

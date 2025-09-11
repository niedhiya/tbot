import time
import os
import requests
import threading
from tradingview_ta import get_multiple_analysis, Interval

# ---------------- Telegram & Bot Config ----------------
TOKEN = os.environ.get("TELEGRAM_TOKEN")
URL = f"https://api.telegram.org/bot{TOKEN}"
UPDATE_INTERVAL = 600  # tiap 10 menit
TA_INTERVAL = Interval.INTERVAL_1_HOUR  # default interval
DELAY = 10  # delay antar batch (detik)

screener_thread_running = False
last_screened_results = {}
custom_filters = []

# ---------------- Ambil semua ticker dari TradingView ----------------
def load_idx_tickers_from_tv():
    url = 'https://scanner.tradingview.com/indonesia/scan'
    payload = {"filter":[],"options":{"lang":"en"},"symbols":{"query":{"types":[]}},"columns":["name"]}
    try:
        r = requests.post(url, json=payload)
        data = r.json()
        return [item['d'][0].replace('IDX:', '') for item in data.get('data', []) if item.get('d')]
    except Exception as e:
        print(f"[ERROR] Load ticker: {e}")
        return []

tickers_list = load_idx_tickers_from_tv()

# ---------------- Kirim pesan ke Telegram ----------------
def send_message(chat_id, text):
    try:
        requests.post(f"{URL}/sendMessage", json={"chat_id": chat_id, "text": text})
    except Exception as e:
        print(f"[ERROR] send_message: {e}")

# ---------------- Ambil TA dari TradingView ----------------
def get_tv_batch(tickers):
    try:
        data = get_multiple_analysis(
            screener="indonesia",
            interval=TA_INTERVAL,
            symbols=[f"IDX:{t}" for t in tickers]
        )
        time.sleep(DELAY)
        return data
    except Exception as e:
        print(f"[ERROR] Batch TA: {e}")
        time.sleep(DELAY)
        return {}

# ---------------- Filter kriteria user ----------------
def parse_filter(expr):
    import re
    match = re.match(r"(\w+)([><=]{1,2})([\d\.]+)", expr)
    if match:
        ind, op, val = match.groups()
        return ind.upper(), op, float(val)
    return None

def check_conditions(indicators, filters):
    for ind, op, val in filters:
        i_val = indicators.get(ind)
        if i_val is None:
            return False
        if op == ">" and not (i_val > val): return False
        if op == "<" and not (i_val < val): return False
        if op == ">=" and not (i_val >= val): return False
        if op == "<=" and not (i_val <= val): return False
        if op == "==" and not (i_val == val): return False
    return True

# ---------------- Jalankan Screener ----------------
def run_screener(chat_id):
    global last_screened_results
    if not custom_filters:
        send_message(chat_id, "⚠️ Belum ada filter. Gunakan /set_filter contoh: /set_filter EMA5>EMA20 RSI>50")
        return

    batch_size = 10
    matched_now = {}

    for i in range(0, len(tickers_list), batch_size):
        batch = tickers_list[i:i+batch_size]
        results = get_tv_batch(batch)

        for symbol, result in results.items():
            ticker = symbol.replace("IDX:", "")
            indicators = result.indicators
            passed = check_conditions(indicators, custom_filters)

            if passed:
                matched_now[ticker] = indicators
                if ticker not in last_screened_results or not last_screened_results[ticker]:
                    msg = f"✅ {ticker} lolos filter:"
                    for ind, _, _ in custom_filters:
                        msg += f"\n{ind}: {indicators.get(ind)}"
                    send_message(chat_id, msg)
            else:
                if ticker in last_screened_results and last_screened_results[ticker]:
                    send_message(chat_id, f"❌ {ticker} keluar dari filter")
                    matched_now[ticker] = False

    last_screened_results = {k: True for k in matched_now}

# ---------------- Loop Screener ----------------
def screener_thread(chat_id):
    global screener_thread_running
    while screener_thread_running:
        run_screener(chat_id)
        time.sleep(UPDATE_INTERVAL)

# ---------------- Main Telegram Bot ----------------
def main():
    global TA_INTERVAL, screener_thread_running, custom_filters
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
                        send_message(chat_id,
"""📊 Bot Screener IDX Siap.
Perintah:
/set_filter <indikator>
/set_interval <1m|5m|15m|1h|1d>
/screener_start
/screener_stop""")

                    elif text.startswith("/set_filter"):
                        raw = text.replace("/set_filter", "").strip().upper().split()
                        parsed = [parse_filter(x) for x in raw if parse_filter(x)]
                        custom_filters = parsed
                        send_message(chat_id, f"✅ Filter diset:\n" + "\n".join(raw))

                    elif text.startswith("/set_interval"):
                        parts = text.split()
                        if len(parts) == 2:
                            interval_map = {
                                "1m": Interval.INTERVAL_1_MINUTE,
                                "5m": Interval.INTERVAL_5_MINUTES,
                                "15m": Interval.INTERVAL_15_MINUTES,
                                "1h": Interval.INTERVAL_1_HOUR,
                                "1d": Interval.INTERVAL_1_DAY,
                                "4h": Interval.INTERVAL_4_HOURS,
                                "3h": Interval.INTERVAL_1_HOUR  # fallback (lib belum support 3h)
                            }
                            key = parts[1]
                            if key in interval_map:
                                TA_INTERVAL = interval_map[key]
                                send_message(chat_id, f"✅ Interval diset ke: {key}")
                            else:
                                send_message(chat_id, "⛔ Interval tidak dikenali. Gunakan: 1m, 5m, 15m, 1h, 4h, 1d")

                    elif text.startswith("/screener_start"):
                        if not screener_thread_running:
                            screener_thread_running = True
                            threading.Thread(target=screener_thread, args=(chat_id,), daemon=True).start()
                            send_message(chat_id, "🚀 Screener dimulai!")
                        else:
                            send_message(chat_id, "⚠️ Screener sudah berjalan.")

                    elif text.startswith("/screener_stop"):
                        screener_thread_running = False
                        send_message(chat_id, "🛑 Screener dihentikan.")

                    offset = update["update_id"] + 1
        except Exception as e:
            print(f"[ERROR] Main loop: {e}")
        time.sleep(5)

if __name__ == "__main__":
    main()

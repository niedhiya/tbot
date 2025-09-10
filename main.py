import time
import os
import requests
import threading
from tradingview_ta import TA_Handler, Interval

# ---------------- Telegram Config ----------------
TOKEN = os.environ.get("TELEGRAM_TOKEN")
URL = f"https://api.telegram.org/bot{TOKEN}"

# Interval default dan update
TA_INTERVAL = Interval.INTERVAL_1_MINUTE
UPDATE_INTERVAL = 300  # 5 menit

# Cache TA
ta_cache = {}  # {ticker: {"indicators":..., "summary":..., "timestamp":...}}
cache_expiry = 300  # detik, sesuai UPDATE_INTERVAL

# User-defined filter criteria
criteria = {}  # Tidak ada default, user harus set via /set_criteria

# Thread control
screener_thread_running = False

# ---------------- Ambil ticker dari TradingView ----------------
def load_idx_tickers_from_tv():
    url = 'https://scanner.tradingview.com/indonesia/scan'
    payload = {
        "filter": [],
        "options": {"lang": "en"},
        "symbols": {"query": {"types": []}},
        "columns": ["name"]
    }
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

# ---------------- Ambil TA per ticker ----------------
def get_tv_ta(symbol, retries=3):
    for i in range(retries):
        try:
            # Gunakan cache jika belum expired
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
            return analysis.indicators, analysis.summary
        except Exception as e:
            send_error(f"{symbol} attempt {i+1} failed: {e}")
            time.sleep(2)  # delay lebih panjang untuk menghindari 429
    return None, None

# ---------------- Screener ----------------
def run_screener(chat_id):
    if not criteria:
        send_message(chat_id, "❌ Silakan set kriteria screener terlebih dahulu menggunakan /set_criteria")
        return

    results = []
    batch_size = 10  # batch per 50 ticker
    for i in range(0, len(tickers_list), batch_size):
        batch = tickers_list[i:i+batch_size]
        for ticker in batch:
            indicators, summary = get_tv_ta(ticker)
            if not indicators:
                continue

            # Filter berdasarkan user-defined criteria
            match = True
            for key, condition in criteria.items():
                val = indicators.get(key)
                if val is None:
                    match = False
                    break
                if isinstance(condition, str):
                    if condition.startswith("<") and val >= float(condition[1:]):
                        match = False
                        break
                    elif condition.startswith(">") and val <= float(condition[1:]):
                        match = False
                        break
                    elif condition == "cross_up" and summary.get('RECOMMENDATION') != "BUY":
                        match = False
                        break
                    elif condition == "cross_down" and summary.get('RECOMMENDATION') != "SELL":
                        match = False
                        break
            if match:
                results.append((ticker, summary.get('RECOMMENDATION')))
            time.sleep(2)  # delay antar ticker

    # Kirim hasil screener
    if results:
        msg = f"🔍 Screener IDX (Interval: {TA_INTERVAL}):\n"
        for t, s in results:
            msg += f"{t} → {s}\n"
        send_message(chat_id, msg)
    else:
        send_message(chat_id, "❌ Tidak ada ticker yang lolos kriteria.")

# ---------------- Screener Thread ----------------
def screener_thread(chat_id):
    global screener_thread_running
    while screener_thread_running:
        run_screener(chat_id)
        time.sleep(UPDATE_INTERVAL)

# ---------------- Telegram Main Loop ----------------
def main():
    global TA_INTERVAL, criteria, screener_thread_running
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
                        send_message(chat_id, "Bot aktif. Perintah:\n/ta <TICKER>\n/screener_start\n/screener_stop\n/set_criteria\n/set_interval")

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
                            send_message(chat_id, f"✅ Screener realtime dimulai (refresh tiap {UPDATE_INTERVAL//60} menit)")
                        else:
                            send_message(chat_id, "Screener sudah berjalan.")

                    elif text.startswith("/screener_stop"):
                        if screener_thread_running:
                            screener_thread_running = False
                            send_message(chat_id, "🛑 Screener realtime dihentikan.")
                        else:
                            send_message(chat_id, "Screener belum berjalan.")

                    elif text.startswith("/set_criteria"):
                        parts = text.split()
                        new_criteria = {}
                        for p in parts[1:]:
                            if "=" in p:
                                k, v = p.split("=")
                                new_criteria[k] = v
                        if new_criteria:
                            criteria = new_criteria
                            send_message(chat_id, f"✅ Kriteria screener diperbarui: {criteria}")
                        else:
                            send_message(chat_id, "Format salah. Contoh: /set_criteria MACD=cross_up RSI=<30")

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
                                send_message(chat_id, "Format interval salah. Contoh: /set_interval 1m / 5m / 1d")

                    offset = update["update_id"] + 1
        except Exception as e:
            send_error(f"Main loop error: {e}")
        time.sleep(5)

if __name__ == "__main__":
    main()

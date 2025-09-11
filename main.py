import time
import os
import requests
import threading
import re
from tradingview_ta import TA_Handler, get_multiple_analysis, Interval

# === Telegram Config ===
TOKEN = os.environ.get("TELEGRAM_TOKEN")
URL = f"https://api.telegram.org/bot{TOKEN}"
TA_INTERVAL = Interval.INTERVAL_1_HOUR
UPDATE_INTERVAL = 600  # 10 menit
DELAY = 10

screener_thread_running = False
last_screened_results = {}
custom_filters = []
TA_cache = {}

# === Load all IDX tickers from TradingView ===
def load_idx_tickers_from_tv():
    url = 'https://scanner.tradingview.com/indonesia/scan'
    payload = {"filter":[],"options":{"lang":"en"},"symbols":{"query":{"types":[]}},"columns":["name"]}
    try:
        r = requests.post(url, json=payload, timeout=10)
        if r.status_code != 200:
            print(f"[WARN] HTTP {r.status_code}")
            return []
        data = r.json()
        return [item['d'][0].replace('IDX:', '') for item in data.get('data', []) if item.get('d')]
    except Exception as e:
        print(f"[ERROR] Load ticker: {e}")
        return []

tickers_list = load_idx_tickers_from_tv()

# === Telegram Message ===
def send_message(chat_id, text):
    try:
        requests.post(f"{URL}/sendMessage", json={"chat_id": chat_id, "text": text})
    except Exception as e:
        print(f"[ERROR] send_message: {e}")

# === TA One-by-One (/ta) ===
def get_ta_single(ticker):
    try:
        handler = TA_Handler(
            symbol=f"{ticker}",
            screener="indonesia",
            exchange="IDX",
            interval=TA_INTERVAL
        )
        return handler.get_analysis()
    except Exception as e:
        print(f"[ERROR] get_ta_single: {e}")
        return None

# === Batch TA ===
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
        return {}

# === Filter Parser ===
def parse_filter(expr):
    match = re.match(r"(\S+)\s*(>|<|>=|<=|==|crossup|crossdown)\s*(\S+)", expr)
    if match:
        ind1, op, ind2 = match.groups()
        return ind1, op.lower(), ind2
    return None

def check_conditions(indicators, filters):
    for ind1, op, ind2 in filters:
        val1 = indicators.get(ind1)
        try:
            val2 = float(ind2)
        except:
            val2 = indicators.get(ind2)
        if val1 is None or val2 is None:
            return False
        if op == ">" and not (val1 > val2): return False
        if op == "<" and not (val1 < val2): return False
        if op == ">=" and not (val1 >= val2): return False
        if op == "<=" and not (val1 <= val2): return False
        if op == "==" and not (val1 == val2): return False
        if op == "crossup":
            prev_val1 = indicators.get(f"PREV_{ind1}")
            prev_val2 = indicators.get(f"PREV_{ind2}")
            if prev_val1 is None or prev_val2 is None or not (prev_val1 < prev_val2 and val1 > val2):
                return False
        if op == "crossdown":
            prev_val1 = indicators.get(f"PREV_{ind1}")
            prev_val2 = indicators.get(f"PREV_{ind2}")
            if prev_val1 is None or prev_val2 is None or not (prev_val1 > prev_val2 and val1 < val2):
                return False
    return True

# === Fetch All TA to Cache ===
def fetch_all_ta():
    global TA_cache
    batch_size = 5
    for i in range(0, len(tickers_list), batch_size):
        batch = tickers_list[i:i+batch_size]
        results = get_tv_batch(batch)
        for symbol, result in results.items():
            ticker = symbol.replace("IDX:", "")
            TA_cache[ticker] = result.indicators

# === Screener Core ===
def run_screener_from_cache(chat_id):
    global last_screened_results
    if not custom_filters:
        send_message(chat_id, "⚠️ Belum ada filter. Gunakan /set_filter")
        return
    matched_now = {}
    for ticker, indicators in TA_cache.items():
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

# === Screener Thread ===
def screener_thread(chat_id):
    global screener_thread_running
    fetch_all_ta()
    while screener_thread_running:
        run_screener_from_cache(chat_id)
        time.sleep(UPDATE_INTERVAL)

# === Bot Main ===
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
                    text = message.get("text", "").strip()

                    if "/start" in text.lower():
                        send_message(chat_id,
"""📊 Bot Screener IDX Siap.
Perintah:
/set_filter <filter>
/set_interval <1m|5m|15m|1h|1d>
/screener_start
/screener_stop
/ta <ticker> atau /ta <indikator1> <indikator2> ... <ticker>""")

                    elif text.lower().startswith("/set_filter"):
                        raw_expr = text.replace("/set_filter", "").strip()
                        parsed = parse_filter(raw_expr)
                        if parsed:
                            custom_filters = [parsed]
                            send_message(chat_id, f"✅ Filter diset:\n{raw_expr}")
                        else:
                            send_message(chat_id, "⛔ Format filter salah. Contoh: EMA5 crossup EMA20")

                    elif text.lower().startswith("/set_interval"):
                        parts = text.split()
                        if len(parts) == 2:
                            interval_map = {
                                "1m": Interval.INTERVAL_1_MINUTE,
                                "5m": Interval.INTERVAL_5_MINUTES,
                                "15m": Interval.INTERVAL_15_MINUTES,
                                "1h": Interval.INTERVAL_1_HOUR,
                                "4h": Interval.INTERVAL_4_HOURS,
                                "1d": Interval.INTERVAL_1_DAY
                            }
                            key = parts[1]
                            if key in interval_map:
                                TA_INTERVAL = interval_map[key]
                                send_message(chat_id, f"✅ Interval diset ke: {key}")
                            else:
                                send_message(chat_id, "⛔ Interval tidak dikenali.")

                    elif text.lower().startswith("/screener_start"):
                        if not screener_thread_running:
                            screener_thread_running = True
                            threading.Thread(target=screener_thread, args=(chat_id,), daemon=True).start()
                            send_message(chat_id, "🚀 Screener dimulai!")
                        else:
                            send_message(chat_id, "⚠️ Screener sudah berjalan.")

                    elif text.lower().startswith("/screener_stop"):
                        screener_thread_running = False
                        send_message(chat_id, "🛑 Screener dihentikan.")

                    elif text.lower().startswith("/ta"):
                        parts = text.strip().split()
                        if len(parts) >= 2:
                            ticker = parts[-1].upper()
                            indicators_req = parts[1:-1]  # bisa banyak indikator
                            analysis = get_ta_single(ticker)
                            if analysis:
                                indicators = analysis.indicators
                                if not indicators_req:
                                    msg = f"📊 TA {ticker} ({TA_INTERVAL}):\n"
                                    msg += f"Summary: {analysis.summary.get('RECOMMENDATION')}\n"
                                    for k, v in indicators.items():
                                        msg += f"{k}: {v}\n"
                                    send_message(chat_id, msg[:4096])
                                else:
                                    msg = f"📊 TA {ticker} ({TA_INTERVAL}):\n"
                                    for ind in indicators_req:
                                        value = indicators.get(ind)
                                        if value is not None:
                                            msg += f"{ind}: {value}\n"
                                        else:
                                            available = ", ".join(indicators.keys())
                                            msg += f"⛔ Indikator '{ind}' tidak ditemukan.\n🔎 Indikator tersedia:\n{available}\n"
                                    send_message(chat_id, msg[:4096])
                            else:
                                send_message(chat_id, f"⛔ Data tidak tersedia untuk {ticker}")

                    offset = update["update_id"] + 1
        except Exception as e:
            print(f"[ERROR] Main loop: {e}")
        time.sleep(5)

if __name__ == "__main__":
    main()

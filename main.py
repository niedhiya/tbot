import os
import time
import requests
import threading
from tradingview_ta import get_multiple_analysis, Interval, TA_Handler
from flask import Flask, request

# --- Config ---
TOKEN = os.environ.get("TELEGRAM_TOKEN")
URL = f"https://api.telegram.org/bot{TOKEN}"
UPDATE_INTERVAL = 600
BATCH_DELAY = 10
BATCH_SIZE = 10

TA_INTERVAL = Interval.INTERVAL_1_HOUR
USER_CRITERIA = {}
LAST_RESULTS = {}
screener_thread_running = False

app = Flask(__name__)

def send_message(chat_id, text):
    try:
        requests.post(f"{URL}/sendMessage", json={"chat_id": chat_id, "text": text})
    except Exception as e:
        print("Send message error:", e)

def load_idx_tickers_from_tv():
    url = 'https://scanner.tradingview.com/indonesia/scan'
    payload = {"filter":[],"options":{"lang":"en"},"symbols":{"query":{"types":[]}},"columns":["name"]}
    try:
        r = requests.post(url, json=payload)
        data = r.json()
        return [item['d'][0].replace('IDX:', '') for item in data.get('data', []) if item.get('d')]
    except Exception as e:
        print(f"Ticker error: {e}")
        return []

tickers_list = load_idx_tickers_from_tv()

def eval_criteria(indicators):
    for key, rule in USER_CRITERIA.items():
        val = indicators.get(key)
        if val is None:
            return False
        if rule.startswith(">") and not val > float(rule[1:]):
            return False
        elif rule.startswith("<") and not val < float(rule[1:]):
            return False
        elif rule.startswith("=") and not val == float(rule[1:]):
            return False
    return True

def run_screener(chat_id):
    global LAST_RESULTS
    tickers = tickers_list.copy()
    found = []

    for i in range(0, len(tickers), BATCH_SIZE):
        batch = tickers[i:i + BATCH_SIZE]
        try:
            result = get_multiple_analysis(
                screener="indonesia",
                interval=TA_INTERVAL,
                symbols=[f"IDX:{t}" for t in batch]
            )
        except Exception as e:
            print(f"[ERROR] Batch error: {e}")
            time.sleep(BATCH_DELAY)
            continue

        for symbol, data in result.items():
            ticker = symbol.replace("IDX:", "")
            indicators = data.indicators
            match = eval_criteria(indicators)

            if match:
                found.append(ticker)
                if not LAST_RESULTS.get(ticker, False):
                    msg = f"✅ {ticker} memenuhi kriteria\n" + "\n".join(
                        [f"{k}: {indicators.get(k)}" for k in USER_CRITERIA.keys()]
                    )
                    send_message(chat_id, msg)
                    LAST_RESULTS[ticker] = True
            else:
                if LAST_RESULTS.get(ticker, False):
                    send_message(chat_id, f"❌ {ticker} tidak lagi memenuhi kriteria.")
                    LAST_RESULTS[ticker] = False

        time.sleep(BATCH_DELAY)

    if not found:
        send_message(chat_id, "🔍 Tidak ada saham yang memenuhi kriteria saat ini.")

def screener_loop(chat_id):
    global screener_thread_running
    while screener_thread_running:
        run_screener(chat_id)
        time.sleep(UPDATE_INTERVAL)

def parse_criteria(text):
    try:
        parts = text.replace("/set_criteria", "").strip().split("AND")
        USER_CRITERIA.clear()
        for part in parts:
            part = part.strip()
            if ">" in part:
                k, v = part.split(">")
                USER_CRITERIA[k.strip().upper()] = ">" + v.strip()
            elif "<" in part:
                k, v = part.split("<")
                USER_CRITERIA[k.strip().upper()] = "<" + v.strip()
            elif "=" in part:
                k, v = part.split("=")
                USER_CRITERIA[k.strip().upper()] = "=" + v.strip()
        return True
    except:
        return False

def fetch_ta_for_ticker(ticker):
    try:
        handler = TA_Handler(symbol=ticker, screener="indonesia", exchange="IDX", interval=TA_INTERVAL)
        analysis = handler.get_analysis()
        indicators = analysis.indicators
        lines = [f"{k}: {v}" for k, v in indicators.items()]
        return "\n".join(lines[:20])  # limit output
    except Exception as e:
        return f"❌ Gagal mengambil data TA untuk {ticker}: {e}"

@app.route("/", methods=["POST"])
def webhook():
    global TA_INTERVAL, screener_thread_running
    update = request.get_json()
    message = update.get("message", {})
    text = message.get("text", "")
    chat_id = message["chat"]["id"]

    if "/start" in text:
        send_message(chat_id, "🤖 Screener aktif.\nPerintah:\n/set_criteria EMA5>EMA20 AND RSI>50\n/set_interval 1h\n/screener_start\n/screener_stop\n/ta BBCA")

    elif text.startswith("/set_criteria"):
        if parse_criteria(text):
            send_message(chat_id, f"✅ Kriteria disimpan: {USER_CRITERIA}")
        else:
            send_message(chat_id, "❌ Format salah. Contoh:\n/set_criteria EMA5>EMA20 AND RSI>50")

    elif text.startswith("/set_interval"):
        mapping = {
            "1m": Interval.INTERVAL_1_MINUTE,
            "5m": Interval.INTERVAL_5_MINUTES,
            "15m": Interval.INTERVAL_15_MINUTES,
            "1h": Interval.INTERVAL_1_HOUR,
            "1d": Interval.INTERVAL_1_DAY
        }
        param = text.split(" ")[-1].lower()
        if param in mapping:
            TA_INTERVAL = mapping[param]
            send_message(chat_id, f"✅ Interval diubah ke {param}")
        else:
            send_message(chat_id, "❌ Interval tidak dikenal. Pilih: 1m 5m 15m 1h 1d")

    elif text.startswith("/screener_start"):
        if not screener_thread_running:
            screener_thread_running = True
            threading.Thread(target=screener_loop, args=(chat_id,), daemon=True).start()
            send_message(chat_id, "▶️ Screener dimulai.")
        else:
            send_message(chat_id, "Screener sudah berjalan.")

    elif text.startswith("/screener_stop"):
        screener_thread_running = False
        send_message(chat_id, "⏹️ Screener dihentikan.")

    elif text.startswith("/ta"):
        parts = text.split()
        if len(parts) >= 2:
            ticker = parts[1].strip().upper()
            ta_text = fetch_ta_for_ticker(ticker)
            send_message(chat_id, f"📊 TA {ticker}:\n{ta_text}")
        else:
            send_message(chat_id, "❌ Format salah. Contoh: /ta BBCA")

    return {"ok": True}

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080)

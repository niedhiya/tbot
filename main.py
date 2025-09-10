import time
import os
import requests
import pandas as pd
from tradingview_ta import TA_Handler, Interval

# ---------------- Telegram Bot Config ----------------
TOKEN = os.environ.get("TELEGRAM_TOKEN")
URL = f"https://api.telegram.org/bot{TOKEN}"

# Interval default
INTERVAL = Interval.INTERVAL_1_DAY

# Cache opsional
ta_cache = {}  # {ticker: {indicators, summary}}

# ---------------- Ambil list ticker ----------------
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
        print(f"Gagal ambil ticker dari TradingView: {e}")
        return []

tickers_list = load_idx_tickers_from_tv()

# ---------------- Telegram Helper ----------------
def send_message(chat_id, text):
    try:
        requests.post(f"{URL}/sendMessage", json={"chat_id": chat_id, "text": text})
    except Exception as e:
        print(f"Error sending message: {e}")

# ---------------- Ambil TA per ticker ----------------
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

# ---------------- Screener ----------------
def screener(chat_id, criteria=None):
    """
    criteria: dict berisi indikator dan kondisi filter
    Contoh:
    criteria = {
        "MACD": "cross_up",
        "RSI": "<30",
        "StochK": "cross_up",
    }
    """
    results = []
    for ticker in tickers_list:
        indicators, summary = get_tv_ta(ticker)
        if not indicators:
            continue  # skip jika TA tidak tersedia

        # Cek filter
        match = True
        if criteria:
            for key, condition in criteria.items():
                val = indicators.get(key)
                if val is None:
                    match = False
                    break
                # Contoh condition parsing sederhana
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

    if results:
        msg = "🔍 Screener IDX:\n"
        for t, s in results:
            msg += f"{t} → {s}\n"
        send_message(chat_id, msg)
    else:
        send_message(chat_id, "❌ Tidak ada ticker yang sesuai kriteria.")

# ---------------- Telegram Main Loop ----------------
def main():
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
                        send_message(chat_id, "Bot aktif. Perintah:\n/ta <TICKER>\n/screener")

                    elif text.startswith("/ta "):
                        parts = text.split()
                        if len(parts) == 2:
                            symbol = parts[1].upper()
                            indicators, summary = get_tv_ta(symbol)
                            if indicators:
                                msg = f"{symbol} TA:\n"
                                for k, v in indicators.items():
                                    msg += f"{k}: {v}\n"
                                msg += f"Summary: {summary.get('RECOMMENDATION')}"
                                send_message(chat_id, msg)
                            else:
                                send_message(chat_id, f"TA {symbol} tidak tersedia")

                    elif text.startswith("/screener"):
                        # Contoh kriteria screener default, bisa disesuaikan
                        criteria = {
                            "MACD": "cross_up",
                            "RSI": "<30"
                        }
                        screener(chat_id, criteria)

                    offset = update["update_id"] + 1
        except Exception as e:
            print(f"Error: {e}")
        time.sleep(5)

if __name__ == "__main__":
    main()
 

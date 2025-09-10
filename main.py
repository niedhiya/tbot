import os
import requests
import time
import pickle
from tradingview_ta import TA_Handler
from concurrent.futures import ThreadPoolExecutor

TOKEN = os.getenv("TELEGRAM_TOKEN", "YOUR_BOT_TOKEN")
URL = f"https://api.telegram.org/bot{TOKEN}"

# Cache TA
TA_CACHE_FILE = "ta_cache.pkl"
TA_CACHE_TTL = 300  # 5 menit
try:
    with open(TA_CACHE_FILE, "rb") as f:
        ta_cache = pickle.load(f)
except:
    ta_cache = {}

# Ambil semua ticker IDX dari TradingView JSON
def get_tickers_json():
    url = "https://scanner.tradingview.com/indonesia/scan"
    payload = {
        "filter": [],
        "symbols": {"query": {"types": []}, "tickers": []},
        "columns": ["symbol"]
    }
    try:
        response = requests.post(url, json=payload)
        data = response.json()
        tickers = [item['s'] for item in data.get('data', [])]
        return tickers
    except Exception as e:
        print("Error getting tickers:", e)
        return []

tickers_list = get_tickers_json()
print(f"Total tickers: {len(tickers_list)}")

# User settings
user_criteria = {}  # kriteria user per chat_id
user_interval = {}  # interval per chat_id
default_interval = "1d"

# Kirim pesan ke Telegram
def send_message(chat_id, text):
    requests.post(f"{URL}/sendMessage", json={"chat_id": chat_id, "text": text})

# Fetch TA dengan cache
def fetch_ta(symbol, interval):
    now = time.time()
    key = f"{symbol}_{interval}"
    if key in ta_cache:
        cached_time, data = ta_cache[key]
        if now - cached_time < TA_CACHE_TTL:
            return data
    try:
        handler = TA_Handler(symbol=symbol, screener="indonesia", exchange="IDX", interval=interval)
        analysis = handler.get_analysis()
        data = {"indicators": analysis.indicators, "summary": analysis.summary}
        ta_cache[key] = (now, data)
        with open(TA_CACHE_FILE, "wb") as f:
            pickle.dump(ta_cache, f)
        return data
    except Exception as e:
        print(f"Error fetching TA {symbol}: {e}")
        return None

# Screener
def run_screener(chat_id):
    criteria = user_criteria.get(chat_id, {})
    interval = user_interval.get(chat_id, default_interval)
    results = []

    def check_ticker(symbol):
        data = fetch_ta(symbol, interval)
        if not data:
            return None
        indicators = data["indicators"]
        summary = data["summary"]
        match = True

        # Cek kriteria user
        for k, v in criteria.items():
            k = k.upper()
            try:
                # MACD
                if k == "MACD" and v.lower() in ["goldencross","deathcross"]:
                    macd = indicators.get("MACD.macd")
                    signal = indicators.get("MACD.signal")
                    if macd is None or signal is None:
                        match = False
                        break
                    if v.lower() == "goldencross" and macd <= signal:
                        match = False
                        break
                    elif v.lower() == "deathcross" and macd >= signal:
                        match = False
                        break
                # RSI
                elif k.endswith("_MIN"):
                    ind = k.replace("_MIN","")
                    if indicators.get(ind) is None or indicators[ind] < float(v):
                        match = False
                        break
                elif k.endswith("_MAX"):
                    ind = k.replace("_MAX","")
                    if indicators.get(ind) is None or indicators[ind] > float(v):
                        match = False
                        break
                # Summary
                elif k == "SUMMARY":
                    if summary.get("RECOMMENDATION") != v:
                        match = False
                        break
            except:
                match = False
                break

        if match:
            return symbol
        return None

    with ThreadPoolExecutor(max_workers=10) as executor:
        futures = [executor.submit(check_ticker, s) for s in tickers_list]
        for f in futures:
            res = f.result()
            if res:
                results.append(res)

    return results

# /setcriteria
def set_criteria(chat_id, text):
    criteria = {}
    parts = text.replace("/setcriteria","").strip().split()
    for p in parts:
        if "=" in p:
            key,val = p.split("=")
            criteria[key.upper()] = val
        elif ">" in p:
            key,val = p.split(">")
            criteria[key.upper()+"_MIN"] = val
        elif "<" in p:
            key,val = p.split("<")
            criteria[key.upper()+"_MAX"] = val
    user_criteria[chat_id] = criteria
    send_message(chat_id, f"Kriteria tersimpan:\n{criteria}")

# /setinterval
def set_interval(chat_id, text):
    parts = text.split()
    if len(parts)==2 and parts[1] in ["1m","5m","15m","1h","1d"]:
        user_interval[chat_id] = parts[1]
        send_message(chat_id, f"Interval diset ke {parts[1]}")
    else:
        send_message(chat_id,"Gunakan interval: 1m,5m,15m,1h,1d")

# /ta <ticker>
def get_ta(chat_id, ticker):
    interval = user_interval.get(chat_id, default_interval)
    data = fetch_ta(ticker, interval)
    if not data:
        send_message(chat_id, f"TA {ticker} tidak tersedia")
        return
    msg = f"{ticker} TA:\n"
    for k,v in data["indicators"].items():
        msg += f"{k}: {v}\n"
    msg += f"Summary: {data['summary'].get('RECOMMENDATION','N/A')}"
    send_message(chat_id, msg)

# /help
def help_message():
    return ("/start - Mulai bot\n"
            "/help - Panduan\n"
            "/ta <ticker> - Analisis teknikal\n"
            "/setcriteria - Set filter screener\n"
            "/setinterval - Set interval TA\n"
            "/screener - Jalankan screener saham")

# Main loop
def main():
    offset = None
    while True:
        try:
            updates = requests.get(f"{URL}/getUpdates", params={"offset":offset,"timeout":100}).json()
            for update in updates.get("result",[]):
                msg = update.get("message")
                if not msg: continue
                chat_id = msg["chat"]["id"]
                text = msg.get("text","").lower()
                if "/start" in text:
                    send_message(chat_id,"Bot aktif. Gunakan /help untuk panduan.")
                elif "/help" in text:
                    send_message(chat_id, help_message())
                elif text.startswith("/ta"):
                    parts = text.split()
                    if len(parts)==2:
                        get_ta(chat_id, parts[1].upper())
                elif text.startswith("/setcriteria"):
                    set_criteria(chat_id, text)
                elif text.startswith("/setinterval"):
                    set_interval(chat_id, text)
                elif "/screener" in text:
                    res = run_screener(chat_id)
                    if res:
                        send_message(chat_id,"Screener saham:\n" + "\n".join(res))
                    else:
                        send_message(chat_id,"Tidak ada saham lolos kriteria saat ini.")
                offset = update["update_id"]+1
        except Exception as e:
            print("Error:", e)
        time.sleep(5)

if __name__=="__main__":
    main()

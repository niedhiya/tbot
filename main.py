import os
import requests
import time
import pickle
from bs4 import BeautifulSoup
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

# Ambil ticker dari TradingView Indonesia
TRADINGVIEW_URL = "https://id.tradingview.com/markets/stocks-indonesia/market-movers-all-stocks/"
def get_tickers():
    try:
        response = requests.get(TRADINGVIEW_URL)
        soup = BeautifulSoup(response.text, 'html.parser')
        tickers = []
        for a in soup.find_all('a', {'class':'tv-widget-symbol__link'}):
            ticker = a.get_text(strip=True)
            if ticker:
                tickers.append(f"{ticker}.JK")
        return tickers
    except:
        return []

tickers_list = get_tickers()
print(f"Total tickers: {len(tickers_list)}")

# User settings
user_criteria = {}
user_interval = {}
default_interval = "1d"
default_criteria = {
    "MACD": "",
    "RSI_min": "",
    "RSI_max": "",
    "STOCHASTIC_min": "",
    "STOCHASTIC_max": "",
    "EMA50_min": "",
    "EMA50_max": "",
    "VOLUME_min": "",
    "VOLUME_max": "",
    "Summary": ""
}

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
    except:
        return None

# Screener
def run_screener(chat_id):
    criteria = user_criteria.get(chat_id, default_criteria)
    interval = user_interval.get(chat_id, default_interval)
    results = []

    def check_ticker(symbol):
        data = fetch_ta(symbol, interval)
        if not data:
            return None
        indicators = data["indicators"]
        summary = data["summary"]
        match = True

        # MACD
        macd = indicators.get("MACD.macd")
        signal = indicators.get("MACD.signal")
        if criteria.get("MACD"):
            if criteria["MACD"].lower() == "goldencross" and (macd is None or signal is None or macd <= signal):
                match = False
            elif criteria["MACD"].lower() == "deathcross" and (macd is None or signal is None or macd >= signal):
                match = False

        # RSI
        rsi = indicators.get("RSI")
        if rsi is not None:
            if criteria.get("RSI_min") != "" and rsi < float(criteria["RSI_min"]):
                match = False
            if criteria.get("RSI_max") != "" and rsi > float(criteria["RSI_max"]):
                match = False

        # Stochastic
        stoch = indicators.get("Stoch.K")
        if stoch is not None:
            if criteria.get("STOCHASTIC_min") != "" and stoch < float(criteria["STOCHASTIC_min"]):
                match = False
            if criteria.get("STOCHASTIC_max") != "" and stoch > float(criteria["STOCHASTIC_max"]):
                match = False

        # EMA50
        ema50 = indicators.get("EMA50")
        if ema50 is not None:
            if criteria.get("EMA50_min") != "" and ema50 < float(criteria["EMA50_min"]):
                match = False
            if criteria.get("EMA50_max") != "" and ema50 > float(criteria["EMA50_max"]):
                match = False

        # Volume
        vol = indicators.get("Volume")
        if vol is not None:
            if criteria.get("VOLUME_min") != "" and vol < float(criteria["VOLUME_min"]):
                match = False
            if criteria.get("VOLUME_max") != "" and vol > float(criteria["VOLUME_max"]):
                match = False

        # Summary
        if criteria.get("Summary") != "" and summary.get("RECOMMENDATION") != criteria["Summary"]:
            match = False

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
    criteria = default_criteria.copy()
    parts = text.replace("/setcriteria","").strip().split()
    for p in parts:
        if "=" in p:
            key,val = p.split("=")
            key = key.upper()
            if key in criteria:
                criteria[key] = val
        elif ">" in p:
            key,val = p.split(">")
            key = key.upper()+"_min"
            criteria[key] = val
        elif "<" in p:
            key,val = p.split("<")
            key = key.upper()+"_max"
            criteria[key] = val
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

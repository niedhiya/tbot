import os
import requests
import time
import pickle
from bs4 import BeautifulSoup
from tradingview_ta import TA_Handler
from concurrent.futures import ThreadPoolExecutor, as_completed

TOKEN = os.getenv("TELEGRAM_TOKEN", "YOUR_BOT_TOKEN")
URL = f"https://api.telegram.org/bot{TOKEN}"

# Cache TA
TA_CACHE_FILE = "ta_cache.pkl"
TA_CACHE_TTL = 300  # detik, cache 5 menit
try:
    with open(TA_CACHE_FILE, "rb") as f:
        ta_cache = pickle.load(f)
except:
    ta_cache = {}

# Ambil ticker dari TradingView
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
    "MACD": None,
    "RSI_min": None,
    "RSI_max": None,
    "STOCHASTIC_min": None,
    "STOCHASTIC_max": None,
    "EMA50_min": None,
    "EMA50_max": None,
    "VOLUME_min": None,
    "VOLUME_max": None,
    "Summary": None
}

# Kirim pesan Telegram
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
        macd = indicators.get("MACD.macd")
        signal = indicators.get("MACD.signal")
        if criteria.get("MACD")=="goldencross" and (macd is None or signal is None or macd<=signal):
            match=False
        elif criteria.get("MACD")=="deathcross" and (macd is None or signal is None or macd>=signal):
            match=False
        rsi = indicators.get("RSI")
        if rsi is not None:
            if criteria.get("RSI_min") is not None and rsi<criteria["RSI_min"]:
                match=False
            if criteria.get("RSI_max") is not None and rsi>criteria["RSI_max"]:
                match=False
        stoch = indicators.get("Stoch.K")
        if stoch is not None:
            if criteria.get("STOCHASTIC_min") is not None and stoch<criteria["STOCHASTIC_min"]:
                match=False
            if criteria.get("STOCHASTIC_max") is not None and stoch>criteria["STOCHASTIC_max"]:
                match=False
        ema50 = indicators.get("EMA50")
        if ema50 is not None:
            if criteria.get("EMA50_min") is not None and ema50<criteria["EMA50_min"]:
                match=False
            if criteria.get("EMA50_max") is not None and ema50>criteria["EMA50_max"]:
                match=False
        vol = indicators.get("Volume")
        if vol is not None:
            if criteria.get("VOLUME_min") is not None and vol<criteria["VOLUME_min"]:
                match=False
            if criteria.get("VOLUME_max") is not None and vol>criteria["VOLUME_max"]:
                match=False
        if criteria.get("Summary") and summary.get("RECOMMENDATION")!=criteria["Summary"]:
            match=False
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

# Handle /setcriteria
def set_criteria(chat_id, text):
    criteria = default_criteria.copy()
    parts = text.replace("/setcriteria","").strip().split()
    for p in parts:
        if "=" in p:
            key,val = p.split("=")
            key=key.upper()
            if key in criteria:
                criteria[key]=val
        elif ">" in p:
            key,val=p.split(">")
            key=key.upper()+"_min"
            try: criteria[key]=float(val)
            except: criteria[key]=val
        elif "<" in p:
            key,val=p.split("<")
            key=key.upper()+"_max"
            try: criteria[key]=float(val)
            except: criteria[key]=val
    user_criteria[chat_id]=criteria
    send_message(chat_id,f"Kriteria tersimpan:\n{criteria}")

# Handle /setinterval
def set_interval(chat_id,text):
    parts=text.split()
    if len(parts)==2:
        allowed=["1m","5m","15m","1h","1d"]
        if parts[1] in allowed:
            user_interval[chat_id]=parts[1]
            send_message(chat_id,f"Interval diset ke {parts[1]}")
        else:
            send_message(chat_id,"Interval tidak valid: 1m,5m,15m,1h,1d")

# Handle /ta <ticker>
def get_ta(chat_id,ticker):
    interval = user_interval.get(chat_id,default_interval)
    data = fetch_ta(ticker,interval)
    if not data:
        send_message(chat_id,f"TA {ticker} tidak tersedia")
        return
    msg=f"{ticker} TA:\n"
    for k,v in data["indicators"].items():
        msg+=f"{k}: {v}\n"
    msg+=f"Summary: {data['summary'].get('RECOMMENDATION','N/A')}"
    send_message(chat_id,msg)

# Help
def help_message():
    return ("/start - Mulai bot\n"
            "/help - Panduan\n"
            "/ta <ticker> - Analisis teknikal\n"
            "/setcriteria - Set filter screener\n"
            "/setinterval - Set interval TA\n"
            "/screener - Jalankan screener saham")

# Main bot loop
def main():
    offset=None
    while True:
        try:
            updates=requests.get(f"{URL}/getUpdates",params={"offset":offset,"timeout":100}).json()
            for update in updates.get("result",[]):
                msg=update.get("message")
                if not msg: continue
                chat_id=msg["chat"]["id"]
                text=msg.get("text","").lower()
                if "/start" in text:
                    send_message(chat_id,"Bot aktif. Gunakan /help untuk panduan.")
                elif "/help" in text:
                    send_message(chat_id,help_message())
                elif text.startswith("/ta"):
                    parts=text.split()
                    if len(parts)==2:
                        get_ta(chat_id,parts[1].upper())
                elif text.startswith("/setcriteria"):
                    set_criteria(chat_id,text)
                elif text.startswith("/setinterval"):
                    set_interval(chat_id,text)
                elif "/screener" in text:
                    res=run_screener(chat_id)
                    if res:
                        send_message(chat_id,"Screener saham:\n"+"\n".join(res))
                    else:
                        send_message(chat_id,"Tidak ada saham lolos kriteria saat ini.")
                offset=update["update_id"]+1
        except Exception as e:
            print("Error:",e)
        time.sleep(5)

if __name__=="__main__":
    main()

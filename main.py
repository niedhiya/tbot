import yfinance as yf
import pandas as pd
import pandas_ta as ta
import time
import requests
import os

TOKEN = os.environ.get("TELEGRAM_TOKEN")
URL = f"https://api.telegram.org/bot{TOKEN}"

INTERVAL = "1d"  # OHLC interval
CACHE_UPDATE_INTERVAL = 60  # detik
ta_cache = {}

# Ambil ticker IDX dari TradingView Scanner JSON
def load_idx_tickers_from_tv():
    url = 'https://scanner.tradingview.com/indonesia/scan'
    payload = {
        "filter":[],
        "options":{"lang":"en"},
        "symbols":{"query":{"types":[]}},
        "columns":["name"]
    }
    tickers = []
    try:
        r = requests.post(url, json=payload)
        data = r.json()
        for item in data.get('data', []):
            d_values = item.get('d', [])
            if len(d_values) > 0:
                name = d_values[0]
                if name:
                    tickers.append(name.replace('IDX:','') + ".JK")
    except Exception as e:
        print(f"Gagal ambil ticker: {e}")
    return tickers

tickers_list = load_idx_tickers_from_tv()

# Telegram helper
def send_message(chat_id, text):
    try:
        requests.post(f"{URL}/sendMessage", json={"chat_id": chat_id, "text": text})
    except Exception as e:
        print(f"Error sending message: {e}")

# Ambil OHLC dari Yahoo Finance dan hitung TA
def fetch_and_calculate_ta(ticker):
    try:
        df = yf.download(ticker, period="6mo", interval=INTERVAL, progress=False)
        if df.empty:
            return None
        df['EMA20'] = ta.ema(df['Close'], length=20)
        df['Vol_MA20'] = df['Volume'].rolling(20).mean()
        df['RSI'] = ta.rsi(df['Close'], length=14)
        stoch = ta.stoch(df['High'], df['Low'], df['Close'])
        df['StochK'] = stoch['STOCHK_14_3_3']
        macd = ta.macd(df['Close'])
        df['MACD'] = macd['MACD_12_26_9']
        latest = df.iloc[-1]
        return {
            'EMA20': latest['EMA20'],
            'Vol_MA20': latest['Vol_MA20'],
            'RSI': latest['RSI'],
            'StochK': latest['StochK'],
            'MACD': latest['MACD']
        }
    except Exception as e:
        print(f"Gagal hitung TA {ticker}: {e}")
        return None

# Update cache semua ticker
def update_ta_cache():
    global ta_cache
    for t in tickers_list:
        ta_data = fetch_and_calculate_ta(t)
        if ta_data:
            ta_cache[t] = ta_data
            print(f"{t} TA berhasil")
        else:
            print(f"{t} gagal")
        time.sleep(1)  # delay supaya Yahoo tidak block
    df = pd.DataFrame([{**{'Ticker': k}, **v} for k,v in ta_cache.items()])
    df.to_excel("ta_idx.xlsx", index=False)
    print("✅ Semua TA tersimpan di ta_idx.xlsx")

# Screener otomatis
def screener_bot(chat_id):
    results = []
    for ticker, data in ta_cache.items():
        macd = data['MACD']
        ema = data['EMA20']
        rsi = data['RSI']
        stoch = data['StochK']
        vol_ma20 = data['Vol_MA20']

        # Contoh filter: MACD positif, RSI < 50, StochK > 20
        if macd > 0 and rsi < 50 and stoch > 20:
            results.append(f"{ticker} ✅ MACD {macd:.2f}, RSI {rsi:.2f}, StochK {stoch:.2f}, EMA20 {ema:.2f}")

    if results:
        msg = "🔍 Screener IDX:\n" + "\n".join(results)
    else:
        msg = "🔍 Screener IDX: Tidak ada saham sesuai kriteria."
    
    send_message(chat_id, msg)

# Telegram main loop
def main():
    offset = None
    last_cache_update = 0
    default_chat_id = YOUR_TELEGRAM_CHAT_ID  # ganti dengan chat id Telegram
    while True:
        try:
            now = time.time()
            # Update cache dan screener otomatis
            if now - last_cache_update > CACHE_UPDATE_INTERVAL:
                print("Update cache TA semua ticker...")
                update_ta_cache()
                last_cache_update = now
                screener_bot(default_chat_id)

            updates = requests.get(f"{URL}/getUpdates", params={"offset": offset, "timeout":100}).json()
            for update in updates.get("result", []):
                message = update.get("message")
                if message:
                    chat_id = message["chat"]["id"]
                    text = message.get("text","").lower()

                    if "/start" in text:
                        send_message(chat_id, "Bot aktif. Gunakan /ta <TICKER> atau /screener")

                    elif text.startswith("/ta "):
                        parts = text.split()
                        if len(parts) == 2:
                            symbol = parts[1].upper()
                            data = ta_cache.get(symbol)
                            if data:
                                msg = f"{symbol} TA:\n"
                                for k,v in data.items():
                                    msg += f"{k}: {v}\n"
                                send_message(chat_id, msg)
                            else:
                                send_message(chat_id, f"TA {symbol} belum tersedia atau gagal fetch")

                    elif text.startswith("/screener"):
                        screener_bot(chat_id)

                    offset = update["update_id"] + 1

        except Exception as e:
            print(f"Error: {e}")
        time.sleep(5)

if __name__ == "__main__":
    main()

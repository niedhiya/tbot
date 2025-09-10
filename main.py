import time
import os
import requests
import pandas as pd
from tradingview_ta import TA_Handler
from concurrent.futures import ThreadPoolExecutor, as_completed

TOKEN = os.environ.get("TELEGRAM_TOKEN")
URL = f"https://api.telegram.org/bot{TOKEN}"

# Load IDX tickers
def load_idx_tickers(file_path="tickers_idx.xlsx"):
    df = pd.read_excel(file_path)
    # Ambil kolom 'Code' dan hapus spasi
    tickers = df['Code'].astype(str).str.strip().tolist()
    return tickers

tickers_list = load_idx_tickers()

user_criteria = {}
user_interval = {}
default_interval = "1d"

default_criteria = {}

def send_message(chat_id, text):
    try:
        requests.post(f"{URL}/sendMessage", json={"chat_id": chat_id, "text": text})
    except Exception as e:
        print(f"Error sending message: {e}")

# Fetch TA satu ticker, format TradingView IDX:NAMAEMITEN
def fetch_ta(symbol, interval):
    tv_symbol = f"IDX:{symbol.replace('.JK','')}"  # ubah BBCA.JK → IDX:BBCA
    try:
        handler = TA_Handler(
            symbol=tv_symbol,
            screener="indonesia",
            exchange="IDX",
            interval=interval
        )
        analysis = handler.get_analysis()
        return {"indicators": analysis.indicators, "summary": analysis.summary}
    except Exception as e:
        print(f"TA error {symbol}: {e}")
        return None

# Fetch TA semua ticker paralel
def fetch_all_ta_parallel(interval):
    all_ta = {}
    with ThreadPoolExecutor(max_workers=10) as executor:
        futures = {executor.submit(fetch_ta, symbol, interval): symbol for symbol in tickers_list}
        for future in as_completed(futures):
            symbol = futures[future]
            data = future.result()
            if data is not None:
                all_ta[symbol] = data
    return all_ta

# Set criteria
def set_criteria(chat_id, text):
    criteria = default_criteria.copy()
    parts = text.replace("/setcriteria","").strip().split()
    for p in parts:
        if "=" in p:
            key, value = p.split("=")
            key = key.upper()
            if key in criteria:
                criteria[key] = value
        elif ">" in p:
            key, value = p.split(">")
            key = key.upper() + "_min"
            try:
                criteria[key] = float(value)
            except:
                criteria[key] = value
        elif "<" in p:
            key, value = p.split("<")
            key = key.upper() + "_max"
            try:
                criteria[key] = float(value)
            except:
                criteria[key] = value
    user_criteria[chat_id] = criteria
    send_message(chat_id, f"Kriteria screener berhasil disimpan:\n{criteria}")

# Set interval
def set_interval(chat_id, text):
    parts = text.split()
    if len(parts) == 2:
        interval_map = {"1m":"1m","5m":"5m","15m":"15m","1h":"1h","1d":"1d"}
        interval_str = parts[1].lower()
        if interval_str in interval_map:
            user_interval[chat_id] = interval_map[interval_str]
            send_message(chat_id, f"Interval berhasil diatur ke {interval_str}")
        else:
            send_message(chat_id, "Interval tidak valid. Gunakan 1m,5m,15m,1h,1d")

# Screener
def run_screener(chat_id):
    criteria = user_criteria.get(chat_id, default_criteria)
    interval = user_interval.get(chat_id, default_interval)
    all_ta = fetch_all_ta_parallel(interval)
    screened = []

    for symbol, data in all_ta.items():
        indicators = data.get("indicators")
        summary = data.get("summary")
        if not indicators or not summary:
            continue

        match = True
        macd = indicators.get("MACD.macd")
        signal = indicators.get("MACD.signal")
        if criteria.get("MACD") == "goldencross" and (macd is None or signal is None or macd <= signal):
            match = False
        elif criteria.get("MACD") == "deathcross" and (macd is None or signal is None or macd >= signal):
            match = False

        rsi = indicators.get("RSI")
        if rsi is not None:
            if criteria.get("RSI_min") is not None and rsi < criteria["RSI_min"]:
                match = False
            if criteria.get("RSI_max") is not None and rsi > criteria["RSI_max"]:
                match = False

        stoch = indicators.get("Stoch.K")
        if stoch is not None:
            if criteria.get("STOCHASTIC_min") is not None and stoch < criteria["STOCHASTIC_min"]:
                match = False
            if criteria.get("STOCHASTIC_max") is not None and stoch > criteria["STOCHASTIC_max"]:
                match = False

        ema50 = indicators.get("EMA50")
        if ema50 is not None:
            if criteria.get("EMA50_min") is not None and ema50 < criteria["EMA50_min"]:
                match = False
            if criteria.get("EMA50_max") is not None and ema50 > criteria["EMA50_max"]:
                match = False

        vol = indicators.get("Volume")
        if vol is not None:
            if criteria.get("VOLUME_min") is not None and vol < criteria["VOLUME_min"]:
                match = False
            if criteria.get("VOLUME_max") is not None and vol > criteria["VOLUME_max"]:
                match = False

        if criteria.get("Summary") and summary.get("RECOMMENDATION") != criteria["Summary"]:
            match = False

        if match:
            screened.append(symbol)
    return screened

# Help
def help_message():
    msg = (
        "📌 *Bot Data Saham IDX*\n\n"
        "/start - Mulai bot\n"
        "/help - Panduan\n"
        "/ta <TICKER> - Tampilkan TA TradingView (IDX:NAMAEMITEN)\n"
        "/setcriteria macd=goldencross rsi>60 rsi<90 ema50>5000 volume>1000000 summary=BUY - Set kriteria\n"
        "/setinterval 1m|5m|15m|1h|1d - Set interval TA\n"
        "/screener - Menampilkan semua saham yang memenuhi kriteria"
    )
    return msg

# Main loop
def main():
    offset = None
    print("Bot started...")
    while True:
        try:
            updates = requests.get(f"{URL}/getUpdates", params={"offset": offset, "timeout":100}).json()
            for update in updates.get("result", []):
                message = update.get("message")
                if message:
                    chat_id = message["chat"]["id"]
                    text = message.get("text","")
                    if "/start" in text.lower():
                        send_message(chat_id, "Bot Data Saham IDX aktif.\nGunakan /help untuk panduan.")
                    elif "/help" in text.lower():
                        send_message(chat_id, help_message())
                    elif text.lower().startswith("/ta"):
                        parts = text.split()
                        if len(parts)==2:
                            symbol = parts[1].upper()
                            data = fetch_ta(symbol, user_interval.get(chat_id, default_interval))
                            if data is not None:
                                indicators = data["indicators"]
                                summary = data["summary"]
                                msg = f"{symbol} Technical Analysis:\n"
                                for k,v in indicators.items():
                                    msg += f"{k}: {v}\n"
                                msg += f"Summary: {summary.get('RECOMMENDATION')}"
                                send_message(chat_id, msg)
                            else:
                                send_message(chat_id,f"TA {symbol} tidak tersedia")
                        else:
                            send_message(chat_id,"Gunakan format: /ta <TICKER>")
                    elif text.lower().startswith("/setcriteria"):
                        set_criteria(chat_id, text)
                    elif text.lower().startswith("/setinterval"):
                        set_interval(chat_id, text)
                    elif "/screener" in text.lower():
                        screened = run_screener(chat_id)
                        if screened:
                            msg = "🔍 Screener IDX:\n" + "\n".join(screened)
                        else:
                            msg = "Tidak ada saham memenuhi kriteria saat ini."
                        send_message(chat_id, msg)
                    offset = update["update_id"] + 1
        except Exception as e:
            print(f"Error: {e}")
        time.sleep(5)

if __name__ == "__main__":
    main()

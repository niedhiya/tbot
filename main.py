import time
import os
import requests
import pandas as pd
from tradingview_ta import TA_Handler, Interval

TOKEN = os.environ.get("TELEGRAM_TOKEN")
URL = f"https://api.telegram.org/bot{TOKEN}"

# Load ticker IDX
def load_idx_tickers(file_path="tickers_idx.xlsx"):
    df = pd.read_excel(file_path)
    tickers = df['Code'].astype(str).tolist()
    return tickers, df.set_index('Code')

tickers_list, tickers_df = load_idx_tickers()

# Storage per chat
user_criteria = {}
user_interval = {}

def send_message(chat_id, text):
    try:
        requests.post(f"{URL}/sendMessage", json={"chat_id": chat_id, "text": text})
    except Exception as e:
        print(f"Error sending message: {e}")

# TradingView TA dengan interval per chat
def get_tv_ta_dynamic(symbol, chat_id):
    interval = user_interval.get(chat_id, Interval.INTERVAL_1_DAY)
    try:
        handler = TA_Handler(
            symbol=symbol,
            screener="indonesia",
            exchange="IDX",
            interval=interval
        )
        analysis = handler.get_analysis()
        return analysis.indicators, analysis.summary
    except Exception as e:
        print(f"TradingView TA error for {symbol}: {e}")
        return None, None

# Set criteria per chat
def set_criteria(chat_id, text):
    default_criteria = {
        "MACD": None, "RSI_min": None, "RSI_max": None,
        "Stochastic_min": None, "Stochastic_max": None,
        "EMA50_min": None, "EMA50_max": None,
        "Volume_min": None, "Volume_max": None,
        "Summary": None
    }
    criteria = default_criteria.copy()
    parts = text.split()[1:]
    for p in parts:
        if "=" in p:
            key, value = p.split("=")
            key = key.upper()
            if key in criteria:
                criteria[key] = value
        elif ">" in p or "<" in p:
            if ">" in p:
                key, value = p.split(">")
                key = key.upper() + "_min"
            if "<" in p:
                key, value = p.split("<")
                key = key.upper() + "_max"
            if key in criteria:
                criteria[key] = float(value)
    user_criteria[chat_id] = criteria
    send_message(chat_id, f"Kriteria screener berhasil disimpan: {criteria}")

# Set interval per chat
def set_interval(chat_id, text):
    parts = text.split()
    if len(parts) == 2:
        interval_map = {
            "1m": Interval.INTERVAL_1_MIN,
            "5m": Interval.INTERVAL_5_MIN,
            "15m": Interval.INTERVAL_15_MIN,
            "1h": Interval.INTERVAL_1_HOUR,
            "1d": Interval.INTERVAL_1_DAY
        }
        interval_str = parts[1].lower()
        if interval_str in interval_map:
            user_interval[chat_id] = interval_map[interval_str]
            send_message(chat_id, f"Interval berhasil diatur ke {interval_str}")
        else:
            send_message(chat_id, "Interval tidak valid. Gunakan 1m,5m,15m,1h,1d")

# Screener per chat
def run_screener(chat_id):
    criteria = user_criteria.get(chat_id, {})
    screened = []
    for symbol in tickers_list:
        indicators, summary = get_tv_ta_dynamic(symbol, chat_id)
        if not indicators or not summary:
            continue
        match = True
        macd_summary = summary.get("MACD")
        if criteria.get("MACD") and macd_summary != criteria["MACD"].capitalize():
            match = False
        rsi = indicators.get("RSI")
        if rsi is not None:
            if criteria.get("RSI_min") and rsi < criteria["RSI_min"]:
                match = False
            if criteria.get("RSI_max") and rsi > criteria["RSI_max"]:
                match = False
        stoch = indicators.get("Stoch.K")
        if stoch is not None:
            if criteria.get("STOCHASTIC_MIN") and stoch < criteria["STOCHASTIC_MIN"]:
                match = False
            if criteria.get("STOCHASTIC_MAX") and stoch > criteria["STOCHASTIC_MAX"]:
                match = False
        ema50 = indicators.get("EMA50")
        if ema50 is not None:
            if criteria.get("EMA50_MIN") and ema50 < criteria["EMA50_MIN"]:
                match = False
            if criteria.get("EMA50_MAX") and ema50 > criteria["EMA50_MAX"]:
                match = False
        vol = indicators.get("Volume")
        if vol is not None:
            if criteria.get("VOLUME_MIN") and vol < criteria["VOLUME_MIN"]:
                match = False
            if criteria.get("VOLUME_MAX") and vol > criteria["VOLUME_MAX"]:
                match = False
        if criteria.get("Summary") and summary.get("RECOMMENDATION") != criteria["Summary"]:
            match = False
        if match:
            screened.append(symbol)
    return screened

# Help command
def send_help(chat_id):
    help_text = (
        "/start - Mulai bot\n"
        "/help - Panduan penggunaan\n"
        "/ta <TICKER> - Tampilkan TA lengkap dan bid/ask\n"
        "/setcriteria ... - Atur kriteria screener (contoh: /setcriteria rsi>60 rsi<90 ema50>5000 volume>1000000 summary=BUY macd=goldencross)\n"
        "/setinterval <1m/5m/15m/1h/1d> - Atur interval TA\n"
        "/screener - Tampilkan saham yang memenuhi kriteria\n"
    )
    send_message(chat_id, help_text)

# Main loop
offset = None
print("Bot started...")
while True:
    try:
        updates = requests.get(f"{URL}/getUpdates", params={"offset": offset, "timeout":100}).json()
        for update in updates.get("result", []):
            message = update.get("message")
            if message:
                chat_id = message["chat"]["id"]
                text = message.get("text", "").lower()
                if "/start" in text:
                    send_message(chat_id, "Bot Data Saham IDX aktif. Gunakan /help untuk panduan.")
                elif "/help" in text:
                    send_help(chat_id)
                elif text.startswith("/ta"):
                    parts = text.split()
                    if len(parts) == 2:
                        symbol = parts[1].upper()
                        indicators, summary = get_tv_ta_dynamic(symbol, chat_id)
                        if indicators:
                            msg = f"{symbol} Technical Analysis:\n"
                            for k,v in indicators.items():
                                msg += f"{k}: {v}\n"
                            msg += f"Summary: {summary.get('RECOMMENDATION')}"
                            send_message(chat_id, msg)
                        else:
                            send_message(chat_id, f"TA {symbol} tidak tersedia")
                    else:
                        send_message(chat_id, "Gunakan format: /ta <TICKER>")
                elif text.startswith("/setcriteria"):
                    set_criteria(chat_id, text)
                elif text.startswith("/setinterval"):
                    set_interval(chat_id, text)
                elif "/screener" in text:
                    screened = run_screener(chat_id)
                    if screened:
                        msg = "🔍 Screener IDX (sesuai kriteria):\n" + "\n".join(screened)
                    else:
                        msg = "Tidak ada saham memenuhi kriteria saat ini."
                    send_message(chat_id, msg)
                offset = update["update_id"] + 1
    except Exception as e:
        print(f"Error: {e}")
    time.sleep(5)

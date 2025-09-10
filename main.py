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

tickers_list, tickers_df = load_idx_tickers("tickers_idx.xlsx")

# Telegram helper
def send_message(chat_id, text):
    try:
        requests.post(f"{URL}/sendMessage", json={"chat_id": chat_id, "text": text})
    except Exception as e:
        print(f"Error sending message: {e}")

# TradingView TA
def get_tv_ta(symbol):
    try:
        handler = TA_Handler(
            symbol=symbol,
            screener="indonesia",
            exchange="IDX",
            interval=Interval.INTERVAL_1_DAY
        )
        analysis = handler.get_analysis()
        indicators = analysis.indicators
        summary = analysis.summary
        return indicators, summary
    except Exception as e:
        print(f"TradingView TA error for {symbol}: {e}")
        return None, None

# Screener otomatis
def run_screener():
    screened = []
    for t in tickers_list:
        symbol = t
        indicators, summary = get_tv_ta(symbol)
        if summary:
            if summary.get('RECOMMENDATION') == 'BUY':
                screened.append(symbol)
    return screened

# Main loop
def main():
    subscribers = set()
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
                        send_message(chat_id, "Bot Data Saham IDX aktif.\nPerintah:\n/ta <TICKER>\n/screener")
                        subscribers.add(chat_id)
                    elif text.startswith("/ta"):
                        parts = text.split()
                        if len(parts) == 2:
                            symbol = parts[1].upper()
                            indicators, summary = get_tv_ta(symbol)
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
                    elif "/screener" in text:
                        screened = run_screener()
                        if screened:
                            msg = "🔍 Screener IDX (Summary BUY):\n" + "\n".join(screened)
                        else:
                            msg = "Tidak ada saham memenuhi kriteria saat ini."
                        send_message(chat_id, msg)
                    offset = update["update_id"] + 1
        except Exception as e:
            print(f"Error: {e}")
        time.sleep(5)

if __name__ == "__main__":
    main()

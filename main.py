import time
import os
import requests
import pandas as pd
import yfinance as yf
import talib

TOKEN = os.environ.get("TELEGRAM_TOKEN")
URL = f"https://api.telegram.org/bot{TOKEN}"

# Load ticker IDX
def load_idx_tickers(file_path="tickers_idx.xlsx"):
    df = pd.read_excel(file_path)
    tickers = df['Code'].astype(str).tolist()
    tickers = [t + ".JK" for t in tickers]
    return tickers, df.set_index('Code')

tickers_list, tickers_df = load_idx_tickers("tickers_idx.xlsx")

# Telegram helper
def send_message(chat_id, text):
    try:
        requests.post(f"{URL}/sendMessage", json={"chat_id": chat_id, "text": text})
    except Exception as e:
        print(f"Error sending message: {e}")

# Harga saham
def get_price(ticker):
    try:
        data = yf.Ticker(ticker).history(period="1d")
        if data.empty:
            return None
        last_price = data['Close'].iloc[-1]
        prev_close = data['Close'].iloc[-2] if len(data) > 1 else data['Open'].iloc[-1]
        change = ((last_price - prev_close) / prev_close) * 100
        return last_price, change
    except:
        return None

# Analisis teknikal dengan perbaikan
def get_ta(ticker):
    try:
        df = yf.download(ticker, period="60d", interval="1d")  # gunakan 60 hari
        print(f"{ticker} data length: {len(df)}")
        if df.empty or len(df) < 26:
            print("Data tidak cukup untuk TA")
            return None

        macd, signal, hist = talib.MACD(df['Close'], fastperiod=12, slowperiod=26, signalperiod=9)
        rsi = talib.RSI(df['Close'], timeperiod=14)

        # cek NaN
        if macd.isna().any() or signal.isna().any() or rsi.isna().any():
            print("Data TA mengandung NaN")
            return None

        macd_status = "Neutral"
        if macd.iloc[-2] < signal.iloc[-2] and macd.iloc[-1] > signal.iloc[-1]:
            macd_status = "Golden Cross ✅"
        elif macd.iloc[-2] > signal.iloc[-2] and macd.iloc[-1] < signal.iloc[-1]:
            macd_status = "Death Cross ❌"

        rsi_val = rsi.iloc[-1]
        if rsi_val > 70:
            rsi_status = f"{rsi_val:.2f} (Overbought)"
        elif rsi_val < 30:
            rsi_status = f"{rsi_val:.2f} (Oversold)"
        else:
            rsi_status = f"{rsi_val:.2f} (Normal)"

        sma20 = talib.SMA(df['Close'], timeperiod=20).iloc[-1]
        ema50 = talib.EMA(df['Close'], timeperiod=50).iloc[-1]
        trend_sma = "↑" if df['Close'].iloc[-1] > sma20 else "↓"
        trend_ema = "↑" if df['Close'].iloc[-1] > ema50 else "↓"

        return macd_status, rsi_status, sma20, trend_sma, ema50, trend_ema
    except Exception as e:
        print(f"TA error for {ticker}: {e}")
        return None

# Top Gainers / Losers
def get_top_gainers_losers():
    results = []
    for t in tickers_list:
        price_data = get_price(t)
        if price_data:
            last, change = price_data
            results.append((t, last, change))
    df = pd.DataFrame(results, columns=['Ticker','Price','Change'])
    top_gainers = df.sort_values('Change', ascending=False).head(5)
    top_losers = df.sort_values('Change', ascending=True).head(5)
    return top_gainers, top_losers

# Screener otomatis
def run_screener():
    screened = []
    for t in tickers_list:
        ta = get_ta(t)
        if ta:
            macd_status, rsi_status, _, _, _, _ = ta
            if "Golden Cross" in macd_status or "Oversold" in rsi_status:
                screened.append(t)
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
                        send_message(chat_id, "Bot Data Saham IDX aktif.\nPerintah:\n/price <TICKER>\n/topgainers\n/toplosers\n/ta <TICKER>\n/screener")
                        subscribers.add(chat_id)
                    elif text.startswith("/price"):
                        parts = text.split()
                        if len(parts) == 2:
                            ticker = parts[1].upper()
                            if not ticker.endswith(".JK"):
                                ticker += ".JK"
                            price_data = get_price(ticker)
                            if price_data:
                                last, change = price_data
                                company_name = tickers_df.loc[ticker.replace(".JK",""),'Company'] if ticker.replace(".JK","") in tickers_df.index else ""
                                send_message(chat_id, f"{company_name} ({ticker}):\nHarga: {last:.2f}\nPerubahan: {change:.2f}%")
                            else:
                                send_message(chat_id, f"Ticker {ticker} tidak ditemukan atau data kosong.")
                        else:
                            send_message(chat_id, "Gunakan format: /price <TICKER>")
                    elif "/topgainers" in text:
                        top_gainers, _ = get_top_gainers_losers()
                        msg = "📈 Top Gainers IDX:\n"
                        for i,row in top_gainers.iterrows():
                            msg += f"{row['Ticker']}: {row['Price']:.2f} ({row['Change']:.2f}%)\n"
                        send_message(chat_id, msg)
                    elif "/toplosers" in text:
                        _, top_losers = get_top_gainers_losers()
                        msg = "📉 Top Losers IDX:\n"
                        for i,row in top_losers.iterrows():
                            msg += f"{row['Ticker']}: {row['Price']:.2f} ({row['Change']:.2f}%)\n"
                        send_message(chat_id, msg)
                    elif text.startswith("/ta"):
                        parts = text.split()
                        if len(parts) == 2:
                            ticker = parts[1].upper()
                            if not ticker.endswith(".JK"):
                                ticker += ".JK"
                            ta = get_ta(ticker)
                            if ta:
                                macd_status, rsi_status, sma20, trend_sma, ema50, trend_ema = ta
                                send_message(chat_id, f"{ticker} Technical Analysis:\nMACD: {macd_status}\nRSI: {rsi_status}\nSMA20: {sma20:.2f} {trend_sma}\nEMA50: {ema50:.2f} {trend_ema}")
                            else:
                                send_message(chat_id, f"TA {ticker} tidak tersedia")
                        else:
                            send_message(chat_id, "Gunakan format: /ta <TICKER>")
                    elif "/screener" in text:
                        screened = run_screener()
                        if screened:
                            msg = "🔍 Screener IDX (MACD Golden Cross / RSI Oversold):\n"
                            msg += "\n".join(screened)
                        else:
                            msg = "Tidak ada saham memenuhi kriteria saat ini."
                        send_message(chat_id, msg)
                    offset = update["update_id"] + 1
        except Exception as e:
            print(f"Error: {e}")
        time.sleep(5)

if __name__ == "__main__":
    main()

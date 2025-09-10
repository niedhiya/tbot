import os
import requests
import pandas as pd
import yfinance as yf

TOKEN = os.environ.get("TELEGRAM_TOKEN")
URL = f"https://api.telegram.org/bot{TOKEN}"

# Load semua ticker IDX
def load_idx_tickers(file_path="tickers_idx.xlsx"):
    df = pd.read_excel(file_path)
    tickers = df['Code'].astype(str).tolist()  # kolom 'Code' sesuai XLSX IDX
    tickers = [t + ".JK" for t in tickers]
    return tickers, df.set_index('Code')

tickers_list, tickers_df = load_idx_tickers("tickers_idx.xlsx")

def send_message(chat_id, text):
    try:
        requests.post(f"{URL}/sendMessage", json={"chat_id": chat_id, "text": text})
    except Exception as e:
        print(f"Error sending message: {e}")

# Fungsi harga saham
def get_price(ticker):
    try:
        data = yf.Ticker(ticker).history(period="1d")
        if data.empty:
            return None
        last_price = data['Close'].iloc[-1]
        prev_close = data['Close'].iloc[-2] if len(data) > 1 else data['Open'].iloc[-1]
        change = ((last_price - prev_close) / prev_close) * 100
        return last_price, change
    except Exception as e:
        print(f"Error fetching {ticker}: {e}")
        return None

# Fungsi top gainers/losers
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
                    text = message.get("text", "").lower()
                    if "/start" in text:
                        send_message(chat_id, "Bot Data Saham IDX aktif.\nPerintah:\n/price <TICKER>\n/topgainers\n/toplosers")
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

                    offset = update["update_id"] + 1
        except Exception as e:
            print(f"Error: {e}")

import time
import os
import requests
import pandas as pd

TOKEN = os.environ.get("TELEGRAM_TOKEN")
URL = f"https://api.telegram.org/bot{TOKEN}"

# --- Telegram helper ---
def send_message(chat_id, text):
    try:
        requests.post(f"{URL}/sendMessage", json={"chat_id": chat_id, "text": text})
    except Exception as e:
        print(f"Error sending message: {e}")

# --- Ambil data TradingView scanner Indonesia ---
def fetch_tradingview_idx():
    url = "https://scanner.tradingview.com/indonesia/scan"
    payload = {
        "filter": [],
        "options": {"lang":"en"},
        "symbols": {"query":{"types":[]},"tickers":[]},
        "columns": [
            "name",
            "close",
            "change",
            "change_abs",
            "high",
            "low",
            "volume",
            "Recommend.All"  # summary TA
        ]
    }
    try:
        resp = requests.post(url, json=payload)
        data = resp.json()
        rows = []
        for item in data.get("data", []):
            d = item.get("d", [])
            s = item.get("s", "")
            row = {"Ticker": s}
            for i, col in enumerate(payload["columns"]):
                if i < len(d):
                    row[col] = d[i]
                else:
                    row[col] = None
            rows.append(row)
        df = pd.DataFrame(rows)
        df.to_csv("tradingview_idx.csv", index=False)
        return df
    except Exception as e:
        print(f"[ERROR] Failed fetch TradingView: {e}")
        return pd.DataFrame()

# --- Screener --- 
# Contoh filter: hanya yang summary TA 'BUY' dan volume > 100000
def screener(df):
    filtered = df[(df['Recommend.All']=='BUY') & (df['volume']>100000)]
    return filtered

# --- Bot main loop ---
def main():
    offset = None
    subscribers = set()
    while True:
        try:
            updates = requests.get(f"{URL}/getUpdates", params={"offset": offset, "timeout":100}).json()
            for update in updates.get("result", []):
                message = update.get("message")
                if message:
                    chat_id = message["chat"]["id"]
                    text = message.get("text","").lower()

                    if "/start" in text:
                        send_message(chat_id, "Bot aktif. Perintah:\n/fetch_tv -> Ambil data TradingView scanner IDX\n/screener -> Jalankan screener TA")
                        subscribers.add(chat_id)

                    elif "/fetch_tv" in text:
                        send_message(chat_id, "Mulai fetch data TradingView IDX...")
                        df = fetch_tradingview_idx()
                        if not df.empty:
                            send_message(chat_id, f"✅ Data berhasil diambil. Total ticker: {len(df)}\nCSV tersimpan: tradingview_idx.csv")
                        else:
                            send_message(chat_id, "❌ Gagal mengambil data TradingView")

                    elif "/screener" in text:
                        send_message(chat_id, "Menjalankan screener...")
                        try:
                            df = pd.read_csv("tradingview_idx.csv")
                            filtered = screener(df)
                            if filtered.empty:
                                send_message(chat_id, "Tidak ada ticker yang sesuai filter.")
                            else:
                                msg = "🔍 Screener Result:\n" + "\n".join(filtered['Ticker'].tolist())
                                send_message(chat_id, msg)
                        except Exception as e:
                            send_message(chat_id, f"Gagal jalankan screener: {e}")

                    offset = update["update_id"] + 1
        except Exception as e:
            print(f"Error: {e}")
        time.sleep(5)

if __name__ == "__main__":
    main()

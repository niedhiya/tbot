import os
import requests
from bs4 import BeautifulSoup
from tradingview_ta import TA_Handler
from concurrent.futures import ThreadPoolExecutor

# Token API Telegram
TOKEN = os.getenv("TELEGRAM_TOKEN", "YOUR_BOT_TOKEN")
URL = f"https://api.telegram.org/bot{TOKEN}"

# URL halaman daftar saham Indonesia di TradingView
TRADINGVIEW_URL = "https://id.tradingview.com/markets/stocks-indonesia/market-movers-all-stocks/"

# Mendapatkan daftar saham dari TradingView
def get_tickers():
    response = requests.get(TRADINGVIEW_URL)
    soup = BeautifulSoup(response.text, 'html.parser')
    tickers = []
    for a in soup.find_all('a', {'class': 'tv-widget-symbol__link'}):
        ticker = a.get_text(strip=True)
        if ticker:
            tickers.append(f"{ticker}.JK")
    return tickers

# Mengirim pesan ke pengguna
def send_message(chat_id, text):
    requests.post(f"{URL}/sendMessage", json={"chat_id": chat_id, "text": text})

# Mendapatkan analisis teknikal untuk saham
def get_technical_analysis(symbol, interval="1d"):
    handler = TA_Handler(
        symbol=symbol,
        screener="indonesia",
        exchange="IDX",
        interval=interval
    )
    analysis = handler.get_analysis()
    return analysis

# Menangani pesan masuk dari pengguna
def handle_message(message):
    chat_id = message["chat"]["id"]
    text = message.get("text", "").lower()

    if text == "/start":
        send_message(chat_id, "Selamat datang di Bot Saham IDX! Gunakan /ta <ticker> untuk analisis teknikal.")
    elif text.startswith("/ta"):
        ticker = text.split()[1].upper()
        try:
            analysis = get_technical_analysis(ticker)
            indicators = analysis.indicators
            summary = analysis.summary
            msg = f"Analisis Teknikal {ticker}:\n"
            for key, value in indicators.items():
                msg += f"{key}: {value}\n"
            msg += f"Rekomendasi: {summary.get('RECOMMENDATION', 'Tidak tersedia')}"
            send_message(chat_id, msg)
        except Exception as e:
            send_message(chat_id, f"Terjadi kesalahan: {e}")
    else:
        send_message(chat_id, "Perintah tidak dikenali. Gunakan /start untuk memulai.")

# Mendapatkan pembaruan pesan dari Telegram
def get_updates():
    response = requests.get(f"{URL}/getUpdates")
    return response.json().get("result", [])

# Menjalankan bot
def run_bot():
    print("Bot sedang berjalan...")
    last_update_id = None
    while True:
        updates = get_updates()
        for update in updates:
            update_id = update["update_id"]
            if update_id != last_update_id:
                handle_message(update["message"])
                last_update_id = update_id

if __name__ == "__main__":
    run_bot()

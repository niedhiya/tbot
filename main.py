import pandas as pd
from tradingview_ta import TA_Handler, Interval
from telegram import Update
from telegram.ext import Updater, CommandHandler, CallbackContext
from concurrent.futures import ThreadPoolExecutor
import time

# === Load ticker IDX dari Excel ===
df = pd.read_excel("tickers_idx.xlsx")  # pastikan ada kolom 'KodeEmiten'
tickers_list = [f"{row}.JK" for row in df['Code']]
print(f"Total tickers: {len(tickers_list)}")

# === Global ===
user_criteria = {}
cache_ta = {}  # cache TA untuk setiap ticker
CACHE_EXPIRY = 60  # detik
current_interval = Interval.INTERVAL_1_DAY  # default interval

# === Fungsi fetch TA dengan cache ===
def fetch_ta(symbol, interval=current_interval):
    now = time.time()
    if symbol in cache_ta:
        ta_data, ts = cache_ta[symbol]
        if now - ts < CACHE_EXPIRY:
            return ta_data
    try:
        handler = TA_Handler(symbol=symbol, screener="indonesia", exchange="IDX", interval=interval)
        analysis = handler.get_analysis()
        ta_data = {
            "symbol": symbol,
            "indicators": analysis.indicators,
            "summary": analysis.summary
        }
        cache_ta[symbol] = (ta_data, now)
        return ta_data
    except Exception as e:
        print(f"Skipped {symbol}: {e}")
        return None

# === Screener ===
def run_screener():
    results = []

    def check_ticker(symbol):
        data = fetch_ta(symbol)
        if not data:
            return None
        indicators = data['indicators']
        if not user_criteria:
            # tampil seluruh indikator
            indicator_str = ", ".join([f"{k}:{v}" for k, v in indicators.items()])
            return f"{symbol} - {indicator_str} - Recommendation: {data['summary'].get('RECOMMENDATION','N/A')}"
        passed = True
        for key, val in user_criteria.items():
            indicator_val = indicators.get(key)
            if indicator_val is None:
                passed = False
                break
            min_val, max_val = val
            if not (min_val <= indicator_val <= max_val):
                passed = False
                break
        if passed:
            indicator_str = ", ".join([f"{k}:{v}" for k, v in indicators.items()])
            return f"{symbol} - {indicator_str} - Recommendation: {data['summary'].get('RECOMMENDATION','N/A')}"
        return None

    with ThreadPoolExecutor(max_workers=10) as executor:
        futures = [executor.submit(check_ticker, s) for s in tickers_list]
        for f in futures:
            res = f.result()
            if res:
                results.append(res)
    return results

# === Telegram Bot Handlers ===
def start(update: Update, context: CallbackContext):
    update.message.reply_text("Halo! Bot screener saham IDX lanjutan siap.\nGunakan /help untuk panduan.")

def help_command(update: Update, context: CallbackContext):
    update.message.reply_text(
        "/setcriteria key min max - set kriteria indikator (RSI, MACD, EMA, Stoch, StochRSI, Volume)\n"
        "/interval 1m|5m|1d - set interval TA\n"
        "/screener - jalankan screener sesuai kriteria\n"
        "/clearcriteria - hapus semua kriteria\n"
        "Tanpa kriteria, screener menampilkan semua indikator TA"
    )

def set_criteria(update: Update, context: CallbackContext):
    if len(context.args) != 3:
        update.message.reply_text("Format salah. Contoh: /setcriteria RSI 60 90")
        return
    key = context.args[0]
    try:
        min_val = float(context.args[1])
        max_val = float(context.args[2])
        user_criteria[key] = (min_val, max_val)
        update.message.reply_text(f"Kriteria disimpan: {key} between {min_val} dan {max_val}")
    except:
        update.message.reply_text("Nilai harus angka. Contoh: /setcriteria RSI 60 90")

def clear_criteria(update: Update, context: CallbackContext):
    user_criteria.clear()
    update.message.reply_text("Semua kriteria dihapus.")

def set_interval(update: Update, context: CallbackContext):
    global current_interval
    if not context.args:
        update.message.reply_text("Contoh penggunaan: /interval 1m")
        return
    arg = context.args[0]
    mapping = {
        "1m": Interval.INTERVAL_1_MIN,
        "5m": Interval.INTERVAL_5_MIN,
        "15m": Interval.INTERVAL_15_MIN,
        "1h": Interval.INTERVAL_1_HOUR,
        "1d": Interval.INTERVAL_1_DAY
    }
    if arg in mapping:
        current_interval = mapping[arg]
        update.message.reply_text(f"Interval TA diubah menjadi {arg}")
    else:
        update.message.reply_text("Interval tidak valid. Pilih 1m,5m,15m,1h,1d")

def screener(update: Update, context: CallbackContext):
    update.message.reply_text("Menjalankan screener, tunggu sebentar...")
    results = run_screener()
    if results:
        # batasi 20 ticker agar output tetap terbaca
        update.message.reply_text("\n\n".join(results[:20]))
    else:
        update.message.reply_text("Tidak ada saham yang lolos kriteria.")

# === Main ===
def main():
    TOKEN = "YOUR_TELEGRAM_BOT_TOKEN"
    updater = Updater(TOKEN, use_context=True)
    dp = updater.dispatcher

    dp.add_handler(CommandHandler("start", start))
    dp.add_handler(CommandHandler("help", help_command))
    dp.add_handler(CommandHandler("setcriteria", set_criteria))
    dp.add_handler(CommandHandler("clearcriteria", clear_criteria))
    dp.add_handler(CommandHandler("interval", set_interval))
    dp.add_handler(CommandHandler("screener", screener))

    updater.start_polling()
    updater.idle()

if __name__ == "__main__":
    main()

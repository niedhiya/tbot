import requests
from tradingview_ta import TA_Handler
from time import sleep

# Ambil ticker IDX dari JSON TradingView
def get_tickers_json():
    url = "https://scanner.tradingview.com/indonesia/scan"
    payload = {
        "filter": [],
        "symbols": {"query": {"types": []}, "tickers": []},
        "columns": ["symbol"]
    }
    response = requests.post(url, json=payload)
    data = response.json()
    tickers = [item['s'] for item in data.get('data', [])]
    return tickers

tickers_list = get_tickers_json()
print(f"Total tickers: {len(tickers_list)}")

# Fetch TA dengan retry
def fetch_ta(symbol, interval="1d", retries=2):
    for attempt in range(retries):
        try:
            handler = TA_Handler(symbol=symbol, screener="indonesia", exchange="IDX", interval=interval)
            analysis = handler.get_analysis()
            return {"symbol": symbol, "indicators": analysis.indicators, "summary": analysis.summary}
        except Exception as e:
            print(f"Attempt {attempt+1} failed for {symbol}: {e}")
            sleep(1)  # tunggu sebelum retry
    return None

# Testing TA semua ticker
results = []
for symbol in tickers_list:
    data = fetch_ta(symbol)
    if data:
        rec = data["summary"].get("RECOMMENDATION","N/A")
        print(f"{symbol}: {rec}")
        # print indikator lengkap jika perlu
        # print(data["indicators"])
        results.append(symbol)
    else:
        print(f"{symbol}: TA not available")

print(f"Total available TA: {len(results)}")

import requests
from bs4 import BeautifulSoup
from tradingview_ta import TA_Handler
from concurrent.futures import ThreadPoolExecutor

# Ambil ticker IDX dari TradingView
TRADINGVIEW_URL = "https://id.tradingview.com/markets/stocks-indonesia/market-movers-all-stocks/"
def get_tickers():
    response = requests.get(TRADINGVIEW_URL)
    soup = BeautifulSoup(response.text, 'html.parser')
    tickers = []
    for a in soup.find_all('a', {'class':'tv-widget-symbol__link'}):
        ticker = a.get_text(strip=True)
        if ticker:
            tickers.append(f"{ticker}.JK")
    return tickers

tickers_list = get_tickers()
print(f"Total tickers: {len(tickers_list)}")

# Fetch TA function
def fetch_ta(symbol, interval="1d"):
    try:
        handler = TA_Handler(symbol=symbol, screener="indonesia", exchange="IDX", interval=interval)
        analysis = handler.get_analysis()
        return {"symbol": symbol, "indicators": analysis.indicators, "summary": analysis.summary}
    except Exception as e:
        print(f"Error fetching {symbol}: {e}")
        return None

# Screener testing: tampilkan semua saham TA tersedia
def run_screener_test():
    results = []

    def check_ticker(symbol):
        data = fetch_ta(symbol)
        if data:
            # Menampilkan semua TA tanpa filter
            rec = data["summary"].get("RECOMMENDATION", "N/A")
            return f"{symbol}: {rec}"
        return None

    with ThreadPoolExecutor(max_workers=10) as executor:
        futures = [executor.submit(check_ticker, s) for s in tickers_list]
        for f in futures:
            res = f.result()
            if res:
                results.append(res)

    return results

if __name__ == "__main__":
    res = run_screener_test()
    print("Hasil Screener Testing (tanpa filter):")
    for r in res:
        print(r)

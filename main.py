import pandas as pd
from tradingview_ta import TA_Handler
from concurrent.futures import ThreadPoolExecutor

# Load ticker IDX dari CSV
df = pd.read_csv("tickers_idx.csv")  # pastikan kolom ada 'KodeEmiten'
tickers_list = [f"{row}.JK" for row in df['KodeEmiten']]

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

# Screener testing: tampilkan semua saham dengan summary TA
def run_screener_test():
    results = []

    def check_ticker(symbol):
        data = fetch_ta(symbol)
        if data:
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

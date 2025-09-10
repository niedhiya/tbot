import requests

def get_tickers_json():
    url = "https://scanner.tradingview.com/indonesia/scan"
    payload = {
        "filter": [],
        "symbols": {"query": {"types": []}, "tickers": []},
        "columns": ["symbol"]
    }
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                      "(KHTML, like Gecko) Chrome/114.0.0.0 Safari/537.36",
        "Accept": "*/*",
        "Content-Type": "application/json"
    }
    try:
        response = requests.post(url, json=payload, headers=headers)
        data = response.json()
        if "data" not in data:
            print("Response JSON tidak ada 'data':", data)
            return []
        tickers = [item['s'] for item in data['data']]
        return tickers
    except Exception as e:
        print("Error getting tickers:", e)
        return []

tickers_list = get_tickers_json()
print(f"Total tickers: {len(tickers_list)}")

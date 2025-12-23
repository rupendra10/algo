import requests

urls = [
    "https://assets.upstox.com/feed/market-status/70/instruments/NSE_FO.csv.gz",
    "https://assets.upstox.com/market-quote/instruments/exchange/NSE_FO.json.gz",
    "https://assets.upstox.com/market-quote/instruments/exchange/complete.csv.gz",
    "https://assets.upstox.com/market-quote/instruments/exchange/complete.json.gz",
    "http://assets.upstox.com/feed/market-status/70/instruments/NSE_FO.csv.gz"
]

headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'}

print("Testing URLs...")
for url in urls:
    try:
        r = requests.head(url, headers=headers, timeout=5)
        print(f"{r.status_code} : {url}")
    except Exception as e:
        print(f"Error {url}: {e}")

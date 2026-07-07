import urllib.request
import json
import pandas as pd
import time
from datetime import datetime, timezone

def fetch_bybit_m5(symbol="BTCUSDT", days=90):
    print(f"Downloading {days} days of M5 data for {symbol} from Bybit...")
    interval = "5"
    category = "linear"
    url_base = "https://api.bybit.com/v5/market/kline"
    
    # Calculate timestamps in ms
    end_time_ms = int(time.time() * 1000)
    start_time_ms = end_time_ms - (days * 24 * 60 * 60 * 1000)
    
    current_end = end_time_ms
    all_data = []
    
    while current_end > start_time_ms:
        url = f"{url_base}?category={category}&symbol={symbol}&interval={interval}&limit=1000&end={current_end}"
        try:
            req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
            with urllib.request.urlopen(req) as response:
                res = json.loads(response.read().decode())
                if res.get("retCode") != 0:
                    msg = str(res.get("retMsg", ""))
                    if "Rate Limit" in msg or "Too many" in msg:
                        print("Rate limit — esperando 30 s y reintentando...")
                        time.sleep(30)
                        continue
                    print(f"API Error: {msg}")
                    break
                klines = res.get("result", {}).get("list", [])
                if not klines:
                    break
                all_data.extend(klines)
                # The oldest timestamp in the current batch
                oldest_ts = int(klines[-1][0])
                if oldest_ts >= current_end:
                    break  # Avoid infinite loop
                current_end = oldest_ts - 1
                
                # Print progress
                dt_str = datetime.fromtimestamp(oldest_ts/1000, tz=timezone.utc).strftime('%Y-%m-%d %H:%M')
                print(f"Fetched up to: {dt_str} UTC")
                time.sleep(0.25) # Respect rate limits
        except Exception as e:
            print(f"Network error: {e}")
            break
            
    if not all_data:
        print("No data fetched.")
        return
        
    # Columns in Bybit list: [start_time, open, high, low, close, volume, turnover]
    df = pd.DataFrame(all_data, columns=["timestamp", "open", "high", "low", "close", "volume", "turnover"])
    df["timestamp"] = pd.to_datetime(df["timestamp"].astype(float), unit="ms")
    df = (df.sort_values("timestamp")
            .drop_duplicates(subset="timestamp", keep="first")
            .reset_index(drop=True))
    
    # Select and rename columns for satar_backtest
    df = df[["timestamp", "open", "high", "low", "close", "volume"]]
    
    filename = f"{symbol.lower()}_m5.csv"
    df.to_csv(filename, index=False)
    print(f"Saved {len(df)} candles to {filename}!")

if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser(description="Descarga klines M5 de Bybit (FASE-4 §1)")
    ap.add_argument("--symbol", default="BTCUSDT")
    ap.add_argument("--days", type=int, default=90,
                    help="días de historia (BTCUSDT perp disponible desde ~2020: usar 2000+)")
    a = ap.parse_args()
    fetch_bybit_m5(a.symbol, days=a.days)

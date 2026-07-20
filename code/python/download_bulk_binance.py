# -*- coding: utf-8 -*-
"""
SATAR-1 — Descarga MASIVA de velas 5m desde Binance Vision (archivos mensuales ZIP).

Ventaja sobre download_data.py (API Bybit): un solo archivo por mes en vez de
~8.600 llamadas por trimestre — mucho más tolerante a redes con DNS inestable.
Los datos son de futuros USDT-M de Binance (BTCUSDT perp disponible desde 2020-01);
para el backtest del Pilar C son equivalentes a Bybit (mismo subyacente, se
modelan las fricciones de Bybit aparte, FASE-4 §3).

Uso:
  python download_bulk_binance.py --symbol BTCUSDT --start 2020-01
  python download_bulk_binance.py --symbol ETHUSDT --start 2021-01 --end 2026-06
Salida: {symbol}_m5.csv (compatible con satar_backtest.py; fusiona si ya existe)
"""
import argparse, csv, io, os, time, urllib.request, zipfile
from datetime import datetime, timezone
import pandas as pd

BASE = "https://data.binance.vision/data/futures/um/monthly/klines"


def month_range(start: str, end: str):
    y, m = map(int, start.split("-"))
    ye, me = map(int, end.split("-"))
    while (y, m) <= (ye, me):
        yield f"{y:04d}-{m:02d}"
        m += 1
        if m > 12:
            m, y = 1, y + 1


def fetch_month(symbol: str, interval: str, ym: str) -> pd.DataFrame | None:
    url = f"{BASE}/{symbol}/{interval}/{symbol}-{interval}-{ym}.zip"
    for attempt in range(1, 6):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=60) as r:
                blob = r.read()
            break
        except urllib.error.HTTPError as e:
            if e.code == 404:
                return None                      # mes no publicado (aún) o símbolo sin historia
            print(f"  HTTP {e.code} en {ym}, reintento {attempt}/5...")
            time.sleep(5 * attempt)
        except Exception as e:
            print(f"  Red ({e}) en {ym}, reintento {attempt}/5...")
            time.sleep(5 * attempt)
    else:
        print(f"  [aviso] {ym} omitido tras 5 intentos")
        return None
    with zipfile.ZipFile(io.BytesIO(blob)) as z:
        with z.open(z.namelist()[0]) as f:
            rows = list(csv.reader(io.TextIOWrapper(f, encoding="utf-8")))
    if rows and not rows[0][0].isdigit():
        rows = rows[1:]                          # archivos recientes traen cabecera
    df = pd.DataFrame(rows, columns=["open_time", "open", "high", "low", "close",
                                     "volume", "close_time", "qv", "n", "tbv", "tbqv", "ig"])
    t = df["open_time"].astype(float)
    unit = "us" if t.iloc[0] > 1e14 else "ms"    # Binance pasó a microsegundos en 2025
    out = pd.DataFrame({
        "timestamp": pd.to_datetime(t, unit=unit),
        "open": df["open"].astype(float), "high": df["high"].astype(float),
        "low": df["low"].astype(float), "close": df["close"].astype(float),
        "volume": df["volume"].astype(float),
    })
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--symbol", default="BTCUSDT")
    ap.add_argument("--interval", default="5m")
    ap.add_argument("--start", default="2020-01", help="YYYY-MM inicial")
    ap.add_argument("--end", default=None, help="YYYY-MM final (default: mes pasado)")
    a = ap.parse_args()
    now = datetime.now(timezone.utc)
    end = a.end or (f"{now.year}-{now.month-1:02d}" if now.month > 1 else f"{now.year-1}-12")

    parts, total = [], 0
    for ym in month_range(a.start, end):
        df = fetch_month(a.symbol, a.interval, ym)
        if df is None:
            print(f"{ym}: sin datos")
            continue
        parts.append(df)
        total += len(df)
        print(f"{ym}: {len(df)} velas (acum. {total})")
    if not parts:
        print("No se descargó nada."); return

    df = pd.concat(parts)
    filename = f"{a.symbol.lower()}_m5.csv"
    if os.path.exists(filename):
        old = pd.read_csv(filename, parse_dates=["timestamp"])
        df = pd.concat([old, df])
        print(f"Fusionado con {len(old)} velas existentes (incluye lo reciente de Bybit).")
    df = (df.sort_values("timestamp").drop_duplicates("timestamp").reset_index(drop=True))
    df.to_csv(filename, index=False)
    print(f"OK: {len(df)} velas -> {filename} | {df.timestamp.min()} -> {df.timestamp.max()}")


if __name__ == "__main__":
    main()

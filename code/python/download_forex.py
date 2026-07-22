# -*- coding: utf-8 -*-
"""
Hipótesis 5 — Descarga de datos forex M5 desde Dukascopy (tick→M5 resampleo).

Descarga los datos tick (bid) comprimidos de Dukascopy, los descomprime
en memoria y los resamplea a velas M5 compatibles con satar_backtest.py.

Dukascopy organiza los datos en archivos .bi5 (LZMA) por hora:
  https://datafeed.dukascopy.com/datafeed/{SYMBOL}/{YYYY}/{MM-1}/{DD}/{HH}h_ticks.bi5

Cada tick = 20 bytes: (ms_offset:u32, ask:u32, bid:u32, ask_vol:f32, bid_vol:f32)
  - ms_offset: milisegundos desde el inicio de la hora
  - ask/bid: precio × 10^digits (5 para FX, 3 para XAUUSD)
  - ask_vol/bid_vol: volúmenes en lotes

El mercado forex opera de domingo ~22:00 UTC a viernes ~22:00 UTC.
Los archivos de horas sin actividad (fines de semana) simplemente no existen
o tienen 0 bytes → se ignoran.

Uso:
  python download_forex.py --symbol EURUSD --start 2010 --end 2026
  python download_forex.py --symbol XAUUSD --start 2010 --end 2026
  python download_forex.py --symbol EURUSD --start 2024 --end 2024   # un solo año

Salida: {symbol}_m5.csv (compatible con satar_backtest.py)
"""
from __future__ import annotations
import argparse, io, lzma, os, struct, sys, time
from datetime import datetime, timedelta, timezone
from concurrent.futures import ThreadPoolExecutor, as_completed
import numpy as np
import pandas as pd
import urllib.request
import ssl

# Crear un contexto SSL no verificado global para evitar problemas con proxies de red corporativos
ssl_context = ssl._create_unverified_context()

# --- Configuración de activos ---
INSTRUMENT_CFG = {
    "EURUSD": {"digits": 5, "duka_name": "EURUSD"},
    "GBPUSD": {"digits": 5, "duka_name": "GBPUSD"},
    "USDJPY": {"digits": 3, "duka_name": "USDJPY"},
    "XAUUSD": {"digits": 3, "duka_name": "XAUUSD"},
}

BASE_URL = "https://datafeed.dukascopy.com/datafeed"


def decode_bi5(data: bytes, digits: int, hour_start: datetime) -> list[dict]:
    """Decodifica un archivo .bi5 (LZMA) de Dukascopy a lista de ticks."""
    if not data or len(data) < 10:
        return []
    try:
        raw = lzma.decompress(data)
    except Exception:
        return []
    if len(raw) == 0:
        return []
    tick_size = 20  # 5 campos × 4 bytes
    n_ticks = len(raw) // tick_size
    if n_ticks == 0:
        return []

    divisor = 10 ** digits
    ticks = []
    for i in range(n_ticks):
        offset = i * tick_size
        ms_off, ask_i, bid_i, ask_vol, bid_vol = struct.unpack(
            ">IIIff", raw[offset:offset + tick_size]
        )
        ts = hour_start + timedelta(milliseconds=ms_off)
        bid = bid_i / divisor
        ask = ask_i / divisor
        vol = bid_vol + ask_vol
        ticks.append({"timestamp": ts, "bid": bid, "ask": ask, "volume": vol})
    return ticks


def fetch_hour(symbol: str, dt_hour: datetime, digits: int) -> list[dict]:
    """Descarga y decodifica un archivo .bi5 para una hora específica."""
    duka_name = INSTRUMENT_CFG[symbol]["duka_name"]
    # Dukascopy usa mes 0-indexed (enero=00)
    url = (
        f"{BASE_URL}/{duka_name}/"
        f"{dt_hour.year}/{dt_hour.month - 1:02d}/{dt_hour.day:02d}/"
        f"{dt_hour.hour:02d}h_ticks.bi5"
    )
    for attempt in range(3):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=30, context=ssl_context) as r:
                data = r.read()
            if len(data) == 0:
                return []
            return decode_bi5(data, digits, dt_hour)
        except urllib.error.HTTPError as e:
            if e.code == 404:
                return []  # hora sin datos (fin de semana, feriado)
            if attempt == 2:
                return []
            time.sleep(1)
        except Exception:
            if attempt == 2:
                return []
            time.sleep(1)
    return []


def is_weekend(dt: datetime) -> bool:
    """Retorna True si el timestamp cae en fin de semana forex.
    Forex cierra viernes ~22:00 UTC y abre domingo ~22:00 UTC."""
    wd = dt.weekday()  # 0=lun, 5=sáb, 6=dom
    if wd == 5:  # sábado completo
        return True
    if wd == 6 and dt.hour < 22:  # domingo antes de las 22:00
        return True
    if wd == 4 and dt.hour >= 22:  # viernes después de las 22:00
        return True
    return False


def ticks_to_m5(ticks: list[dict]) -> pd.DataFrame:
    """Convierte lista de ticks a velas M5 usando precio bid."""
    if not ticks:
        return pd.DataFrame()
    df = pd.DataFrame(ticks)
    df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
    df = df.set_index("timestamp").sort_index()
    # Usar bid como precio (convención para backtesting forex)
    ohlcv = df["bid"].resample("5min", label="left", closed="left").ohlc()
    ohlcv.columns = ["open", "high", "low", "close"]
    ohlcv["volume"] = df["volume"].resample("5min", label="left", closed="left").sum()
    ohlcv = ohlcv.dropna()
    return ohlcv


def download_day(symbol: str, date: datetime, digits: int) -> pd.DataFrame:
    """Descarga todas las horas de un día y retorna velas M5."""
    all_ticks = []
    for h in range(24):
        dt_hour = datetime(date.year, date.month, date.day, h, tzinfo=timezone.utc)
        if is_weekend(dt_hour):
            continue
        ticks = fetch_hour(symbol, dt_hour, digits)
        all_ticks.extend(ticks)
    return ticks_to_m5(all_ticks)


def download_month(symbol: str, year: int, month: int, digits: int,
                    threads: int = 8) -> pd.DataFrame:
    """Descarga un mes completo en paralelo (por hora) y retorna M5."""
    from calendar import monthrange
    _, n_days = monthrange(year, month)
    hours = []
    for d in range(1, n_days + 1):
        for h in range(24):
            dt_hour = datetime(year, month, d, h, tzinfo=timezone.utc)
            if not is_weekend(dt_hour):
                hours.append(dt_hour)

    all_ticks = []
    with ThreadPoolExecutor(max_workers=threads) as pool:
        futures = {
            pool.submit(fetch_hour, symbol, dt_h, digits): dt_h
            for dt_h in hours
        }
        for fut in as_completed(futures):
            ticks = fut.result()
            all_ticks.extend(ticks)
    return ticks_to_m5(all_ticks)


def load_existing_max_ts(filename: str):
    """Ultimo timestamp ya guardado en el CSV, o None si no existe/esta vacio."""
    if not os.path.exists(filename):
        return None
    try:
        df_existing = pd.read_csv(filename, usecols=["timestamp"], parse_dates=["timestamp"])
        if len(df_existing) == 0:
            return None
        return df_existing["timestamp"].max()
    except Exception as e:
        print(f"[aviso] No se pudo leer {filename} existente: {e}")
        return None


def append_month(filename: str, df_month: pd.DataFrame, write_header: bool):
    """Escribe el mes a disco INMEDIATAMENTE (modo append). Si el proceso muere
    a mitad de la descarga (reinicio de la maquina, corte de luz, etc.), solo se
    pierde el mes en curso -- no todo el rango descargado hasta ese momento."""
    df_month = df_month.sort_index()
    df_month = df_month[~df_month.index.duplicated(keep="first")]
    out = df_month.reset_index()
    out.columns = ["timestamp", "open", "high", "low", "close", "volume"]
    out.to_csv(filename, mode="a", header=write_header, index=False)


def main():
    ap = argparse.ArgumentParser(description="Descarga datos forex M5 desde Dukascopy")
    ap.add_argument("--symbol", required=True, choices=list(INSTRUMENT_CFG.keys()))
    ap.add_argument("--start", required=True, type=int, help="Año inicial (e.g. 2010)")
    ap.add_argument("--end", required=True, type=int, help="Año final (e.g. 2026)")
    ap.add_argument("--threads", type=int, default=12, help="Hilos de descarga paralela")
    args = ap.parse_args()

    cfg = INSTRUMENT_CFG[args.symbol]
    digits = cfg["digits"]
    filename = f"{args.symbol.lower()}_m5.csv"
    total_candles = 0

    # Resume: si el CSV ya tiene datos, retomar desde el mes del ultimo timestamp
    # guardado (ese mes se re-descarga completo por seguridad; la limpieza final
    # elimina los duplicados que eso genere).
    resume_year, resume_month = args.start, 1
    existing_max = load_existing_max_ts(filename)
    file_has_header = os.path.exists(filename)
    if existing_max is not None:
        resume_year, resume_month = existing_max.year, existing_max.month
        print(f"[resume] {filename} ya tiene datos hasta {existing_max} -> retomando desde {resume_year}-{resume_month:02d}")

    now = datetime.now(timezone.utc)
    for year in range(args.start, args.end + 1):
        for month in range(1, 13):
            # No descargar meses futuros
            if year == now.year and month > now.month:
                break
            if year > now.year:
                break
            if (year, month) < (resume_year, resume_month):
                continue
            t0 = time.time()
            df_month = download_month(args.symbol, year, month, digits, args.threads)
            if len(df_month) == 0:
                print(f"  {year}-{month:02d}: sin datos")
                continue
            append_month(filename, df_month, write_header=not file_has_header)
            file_has_header = True
            total_candles += len(df_month)
            elapsed = time.time() - t0
            print(f"  {year}-{month:02d}: {len(df_month)} velas M5 ({elapsed:.1f}s) [acum sesion: {total_candles}]", flush=True)

    if not file_has_header:
        print("No se descargó nada.")
        return

    # Limpieza final: dedup (el mes de reanudacion se re-descarga completo a
    # proposito) + filtro de fin de semana residual.
    df = pd.read_csv(filename, parse_dates=["timestamp"])
    df = df.sort_values("timestamp").drop_duplicates("timestamp").reset_index(drop=True)
    df = df[~df["timestamp"].apply(lambda x: is_weekend(x.to_pydatetime()))].reset_index(drop=True)
    df.to_csv(filename, index=False)
    print(f"\nOK: {len(df)} velas M5 -> {filename}")
    print(f"    Rango: {df.timestamp.min()} -> {df.timestamp.max()}")


if __name__ == "__main__":
    main()

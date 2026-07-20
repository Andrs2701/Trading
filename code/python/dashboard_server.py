# -*- coding: utf-8 -*-
"""
SATAR-1 / BREAKOUT-ATR — Web Dashboard Server (Flask API + Embedded UI).

Servidor Web para monitorear en tiempo real la estrategia BREAKOUT-ATR:
- Selección de criptomoneda (SOLUSDT, ETHUSDT, BTCUSDT)
- Gráfico interactivo con velas, EMA50, Rangos y marcadores de entrada/salida
- Análisis de régimen (Hurst, Volumen, Expansión ATR, Bollinger Squeeze)
- Histórico completo de trades con métricas de rendimiento (PF, WR, Expectancy, Drawdown)
- Estado en vivo de la posición actual y ejecutor en vivo
"""
from __future__ import annotations
import argparse, json, math, os, sys, time
from datetime import datetime, timezone
import numpy as np
import pandas as pd
from flask import Flask, jsonify, render_template, request

from breakout_backtest import BreakoutEngine, BreakoutParams, resample, ema, atr, hurst_rs, rolling_range, vol_ma
from breakout_live import load_state, fetch_klines_m5, make_params, FROZEN_CONFIG

APPROVED_SYMBOLS = ["SOLUSDT", "ETHUSDT", "BTCUSDT"]

app = Flask(__name__, template_folder="templates")

# Cache local de motores y dataframes por símbolo
_CACHE = {}

def get_engine_data(symbol: str, use_bb_filter: bool = True):
    symbol = symbol.upper()
    cache_key = f"{symbol}_{use_bb_filter}"
    
    csv_file = f"{symbol.lower()}_m5.csv"
    if not os.path.exists(csv_file):
        # Fallback a synthetic data o error
        return None, None, f"No se encontró el archivo {csv_file}"
        
    df = pd.read_csv(csv_file, parse_dates=["timestamp"], index_col="timestamp")
    if df.index.tz is None:
        df.index = df.index.tz_localize("UTC")
        
    p = make_params()
    eng = BreakoutEngine(df, p, symbol=symbol, funnel=True)
    metrics = eng.run()
    
    # Formatear trades para la UI
    trades_data = []
    for t in eng.trades:
        trades_data.append({
            "id": len(trades_data) + 1,
            "symbol": t.symbol,
            "direction": "LONG" if t.direction > 0 else "SHORT",
            "entry_time": pd.to_datetime(t.t_entry, unit="s", utc=True).strftime("%Y-%m-%d %H:%M"),
            "exit_time": pd.to_datetime(t.t_exit, unit="s", utc=True).strftime("%Y-%m-%d %H:%M") if t.t_exit else "-",
            "entry_price": round(t.entry, 2),
            "exit_price": round(t.exit, 2) if t.exit else 0.0,
            "sl_init": round(t.sl_init, 2),
            "tp": round(t.tp, 2),
            "qty": round(t.qty, 4),
            "pnl": round(t.pnl, 2),
            "r_multiple": round(t.r, 2),
            "reason": t.reason or "open"
        })
        
    # Formatear velas H1 para el gráfico (últimas 500 velas H1)
    Hdf = eng.Hdf.iloc[-500:].copy()
    h1_ema = ema(Hdf["close"].to_numpy(float), p.ema_trail_n)
    h1_atr = atr(Hdf["high"].to_numpy(float), Hdf["low"].to_numpy(float), Hdf["close"].to_numpy(float), p.atr_n)
    r_high, r_low = rolling_range(Hdf, p.lookback_hours)
    
    chart_candles = []
    for i in range(len(Hdf)):
        ts = int(Hdf.index[i].timestamp())
        chart_candles.append({
            "time": ts,
            "open": float(Hdf["open"].iloc[i]),
            "high": float(Hdf["high"].iloc[i]),
            "low": float(Hdf["low"].iloc[i]),
            "close": float(Hdf["close"].iloc[i]),
            "volume": float(Hdf["volume"].iloc[i]),
            "ema50": float(h1_ema[i]) if not np.isnan(h1_ema[i]) else None,
            "atr": float(h1_atr[i]) if not np.isnan(h1_atr[i]) else None,
            "range_high": float(r_high[i]) if not np.isnan(r_high[i]) else None,
            "range_low": float(r_low[i]) if not np.isnan(r_low[i]) else None,
        })
        
    # Estado en vivo si existe
    live_st = load_state(symbol)
    
    # Análisis de régimen actual (últimos valores)
    latest_g = eng.Gdf.iloc[-1]
    latest_h = Hdf.iloc[-1]
    last_hurst = float(eng.G.hurst[-1]) if len(eng.G.hurst) > 0 and not np.isnan(eng.G.hurst[-1]) else 0.50
    last_vol = float(latest_h["volume"])
    vol_avg = float(eng.H.vol_ma[-1]) if len(eng.H.vol_ma) > 0 and not np.isnan(eng.H.vol_ma[-1]) else 1.0
    vol_ratio = round(last_vol / (vol_avg + 1e-12), 2)
    last_body = abs(float(latest_h["close"]) - float(latest_h["open"]))
    last_atr_h1 = float(eng.H.atr[-1]) if len(eng.H.atr) > 0 and not np.isnan(eng.H.atr[-1]) else 1.0
    body_atr_ratio = round(last_body / (last_atr_h1 + 1e-12), 2)
    
    analysis = {
        "hurst_exponent": round(last_hurst, 3),
        "hurst_status": "Persistente (Tendencia)" if last_hurst >= 0.52 else ("Anti-persistente" if last_hurst <= 0.48 else "Aleatorio"),
        "hurst_ok": bool(last_hurst >= p.hurst_filter),
        "vol_ratio": vol_ratio,
        "vol_ok": bool(vol_ratio > p.vol_spike_mult),
        "body_atr_ratio": body_atr_ratio,
        "body_atr_ok": bool(body_atr_ratio > p.range_expansion_mult),
        "funnel": metrics.get("counters", {})
    }
    
    demo_info = {
        "active": True,
        "phase": "FASE 9 (DEMO 90 DÍAS)",
        "equity": 200.0,
        "risk_usd": 2.00,
        "target_pf": 1.50,
        "target_dd": -0.10
    }

    return {
        "symbol": symbol,
        "metrics": metrics,
        "trades": trades_data,
        "chart_candles": chart_candles,
        "live_state": live_st,
        "analysis": analysis,
        "demo": demo_info,
        "config": {
            "vol_spike_mult": p.vol_spike_mult,
            "range_expansion_mult": p.range_expansion_mult,
            "stop_atr_mult": p.stop_atr_mult,
            "trail_buf_atr": p.trail_buf_atr,
            "hurst_filter": p.hurst_filter
        }
    }, None, ""

@app.route("/")
def index():
    return render_template("index.html")

@app.route("/api/data")
def api_data():
    symbol = request.args.get("symbol", "SOLUSDT").upper()
    data, eng, err = get_engine_data(symbol)
    if err:
        return jsonify({"error": err}), 400
    return jsonify(data)

@app.route("/health")
def health_check():
    return jsonify({"status": "ok", "timestamp": time.time()})

# Hilo en segundo plano para ejecutar la estrategia 24/7 en Render
def _start_background_bot():
    import threading
    def _bot_loop():
        from breakout_live import cycle, make_params
        symbol = os.environ.get("TRADING_SYMBOL", "SOLUSDT")
        testnet = os.environ.get("BYBIT_TESTNET", "true").lower() == "true"
        live = os.environ.get("BYBIT_LIVE", "true").lower() == "true"
        equity = float(os.environ.get("TRADING_EQUITY", "200.0"))
        p = make_params()
        print(f"\n[RENDER 24/7] Bot de Trading iniciado en segundo plano para {symbol} (Testnet={testnet}, Live={live})...\n")
        while True:
            try:
                cycle(symbol, p, live=live, testnet=testnet, equity=equity)
            except Exception as e:
                print(f"[RENDER bot error] {e}")
            time.sleep(60)

    t = threading.Thread(target=_bot_loop, daemon=True)
    t.start()

# Iniciar bot automáticamente si están configuradas las variables en Render
if os.environ.get("BYBIT_API_KEY") or os.environ.get("ENABLE_BACKGROUND_BOT") == "true":
    _start_background_bot()

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=5000)
    ap.add_argument("--host", default="0.0.0.0")
    args = ap.parse_args()
    print(f"\n[OK] Servidor Dashboard corriendo en: http://{args.host}:{args.port}\n")
    app.run(host=args.host, port=args.port, debug=False)

# -*- coding: utf-8 -*-
"""
BREAKOUT-ATR — Backtest multi-activo con la configuración CONGELADA del WFO
(la misma que corre breakout_live.py en producción), sin re-optimizar nada
por activo. Objetivo: ver si algún candidato nuevo tiene un edge parecido
al de SOLUSDT antes de considerar agregarlo a la operativa en vivo.

Motor: BreakoutEngine (plano), el mismo que usa breakout_live.py -- NO el
AdvancedBreakoutEngine con filtro Bollinger de test_bb_squeeze.py, que nunca
pasó por WFO/Monte Carlo y no es lo que está desplegado.

Uso:
  python breakout_multiasset_frozen.py
  python breakout_multiasset_frozen.py --symbols SOLUSDT,ETHUSDT,BTCUSDT
"""
from __future__ import annotations
import argparse, json, os
import pandas as pd

from breakout_backtest import BreakoutEngine, BreakoutParams
from breakout_live import FROZEN_CONFIG

DEFAULT_SYMBOLS = [
    "SOLUSDT", "ETHUSDT", "BTCUSDT",   # ya conocidos (portfolio actual)
    "XRPUSDT", "BNBUSDT",              # ya tenían datos de Fase C
    "AVAXUSDT", "ADAUSDT", "LINKUSDT", # candidatos nuevos
]


def run_symbol(symbol: str) -> dict | None:
    csv_file = f"{symbol.lower()}_m5.csv"
    if not os.path.exists(csv_file):
        return None
    df = pd.read_csv(csv_file, parse_dates=["timestamp"], index_col="timestamp")
    if df.index.tz is None:
        df.index = df.index.tz_localize("UTC")

    p = BreakoutParams(**FROZEN_CONFIG)  # SOLO los 3 parametros del WFO; el resto queda en default
    eng = BreakoutEngine(df, p, symbol=symbol)
    res = eng.run()
    res["symbol"] = symbol
    res["rango"] = f"{df.index[0].date()} -> {df.index[-1].date()}"
    return res


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--symbols", type=str, default=None,
                     help="Lista separada por comas. Default: todos los disponibles.")
    args = ap.parse_args()
    symbols = args.symbols.split(",") if args.symbols else DEFAULT_SYMBOLS

    print(f"Config congelada (WFO, la misma de produccion): {FROZEN_CONFIG}\n")
    print(f"{'Activo':10s} {'Trades':>7s} {'WR':>7s} {'PF':>7s} {'Exp_R':>9s} {'MaxDD':>8s} {'Trades/año':>11s}  Rango")
    print("-" * 100)

    results = {}
    for sym in symbols:
        res = run_symbol(sym)
        if res is None:
            print(f"{sym:10s}  [sin datos -- {sym.lower()}_m5.csv no encontrado]")
            continue
        results[sym] = res
        if res.get("trades", 0) == 0:
            print(f"{sym:10s}  [0 trades] {res.get('nota', '')}")
            continue
        print(f"{sym:10s} {res['trades']:7d} {res['win_rate']*100:6.1f}% {res['profit_factor']:7.3f} "
              f"{res['expectancy_R']:+8.4f}R {res['max_drawdown']*100:7.1f}% {res['trades_por_año']:11.1f}  {res['rango']}")

    os.makedirs("results", exist_ok=True)
    with open("results/breakout_multiasset_frozen.json", "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2, ensure_ascii=False, default=str)
    print(f"\n[OK] resultados -> results/breakout_multiasset_frozen.json")


if __name__ == "__main__":
    main()

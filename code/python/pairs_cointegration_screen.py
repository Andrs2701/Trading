# -*- coding: utf-8 -*-
"""
Hipótesis 6 (Pairs Trading) — Screening de cointegración.

Para cada par de los 11 activos y cada temporalidad candidata (H1/H4/D1),
prueba cointegración Engle-Granger + ADF sobre el spread OLS, usando SOLO
el período de formación (primer 70% cronológico de la historia común a
ambos activos). Ver docs/PAIRS-formalizacion.md §2-3.

Filtro estadístico, no de rentabilidad: no se mira ningún resultado de
backtest en este paso.

Uso:
  python pairs_cointegration_screen.py
"""
from __future__ import annotations
import itertools
import json
import os
import numpy as np
import pandas as pd
from statsmodels.tsa.stattools import coint, adfuller

from satar_backtest import resample

ASSETS = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "XRPUSDT", "BNBUSDT",
          "LINKUSDT", "AVAXUSDT", "INJUSDT", "UNIUSDT", "ARBUSDT", "OPUSDT"]
TIMEFRAMES = {"H1": "1h", "H4": "4h", "D1": "1D"}
FORMATION_FRACTION = 0.70
P_VALUE_THRESHOLD = 0.05


def load_m5(symbol: str) -> pd.DataFrame:
    fn = f"{symbol.lower()}_m5.csv"
    df = pd.read_csv(fn, parse_dates=["timestamp"], index_col="timestamp")
    if df.index.tz is None:
        df.index = df.index.tz_localize("UTC")
    return df.sort_index()


def build_tf_closes(m5_data: dict) -> dict:
    """Devuelve {symbol: {tf_name: serie_de_cierres}} resampleado desde M5."""
    out = {}
    for sym, df in m5_data.items():
        out[sym] = {}
        for tf_name, rule in TIMEFRAMES.items():
            r = resample(df, rule)
            out[sym][tf_name] = r["close"]
    return out


def test_pair(close_a: pd.Series, close_b: pd.Series) -> dict | None:
    """Cointegracion Engle-Granger + ADF sobre el residuo OLS, en el
    periodo de formacion (primer 70% de la historia comun)."""
    common = close_a.index.intersection(close_b.index)
    if len(common) < 200:
        return None
    a = close_a.loc[common].sort_index()
    b = close_b.loc[common].sort_index()

    n_formation = int(len(common) * FORMATION_FRACTION)
    if n_formation < 150:
        return None
    a_form = a.iloc[:n_formation]
    b_form = b.iloc[:n_formation]

    log_a = np.log(a_form.to_numpy())
    log_b = np.log(b_form.to_numpy())

    # Engle-Granger (statsmodels ya hace la regresion + ADF sobre el residuo internamente)
    try:
        eg_stat, eg_pvalue, _ = coint(log_a, log_b)
    except Exception:
        return None

    # Hedge ratio via OLS explicito (lo necesita el motor de trading para
    # construir el spread) + ADF de confirmacion sobre el residuo.
    X = np.column_stack([np.ones(len(log_b)), log_b])
    beta_ols, *_ = np.linalg.lstsq(X, log_a, rcond=None)
    alpha, beta = beta_ols
    resid = log_a - (alpha + beta * log_b)
    try:
        adf_stat, adf_pvalue, *_ = adfuller(resid, autolag="AIC")
    except Exception:
        adf_pvalue = 1.0

    return {
        "n_bars_common": len(common),
        "n_bars_formation": n_formation,
        "formation_start": str(a_form.index[0]),
        "formation_end": str(a_form.index[-1]),
        "eg_pvalue": round(float(eg_pvalue), 5),
        "adf_pvalue_resid": round(float(adf_pvalue), 5),
        "hedge_ratio_beta": round(float(beta), 6),
        "alpha": round(float(alpha), 6),
        "cointegrado": bool(eg_pvalue < P_VALUE_THRESHOLD and adf_pvalue < P_VALUE_THRESHOLD),
    }


def main():
    print(f"Cargando M5 de {len(ASSETS)} activos...")
    m5_data = {}
    for sym in ASSETS:
        try:
            m5_data[sym] = load_m5(sym)
        except FileNotFoundError:
            print(f"  [omitido] {sym}: sin CSV")
    print(f"Resampleando a {list(TIMEFRAMES.keys())}...")
    tf_closes = build_tf_closes(m5_data)

    pairs = list(itertools.combinations(m5_data.keys(), 2))
    print(f"Probando cointegracion sobre {len(pairs)} pares x {len(TIMEFRAMES)} temporalidades "
          f"= {len(pairs) * len(TIMEFRAMES)} combinaciones...\n")

    results = []
    for a, b in pairs:
        for tf_name in TIMEFRAMES:
            r = test_pair(tf_closes[a][tf_name], tf_closes[b][tf_name])
            if r is None:
                continue
            r["pair"] = f"{a}-{b}"
            r["asset_a"] = a
            r["asset_b"] = b
            r["timeframe"] = tf_name
            results.append(r)

    cointegrados = [r for r in results if r["cointegrado"]]
    cointegrados.sort(key=lambda r: r["eg_pvalue"])

    print(f"=== {len(cointegrados)} de {len(results)} combinaciones par x temporalidad cointegran (p<{P_VALUE_THRESHOLD}) ===\n")
    for r in cointegrados:
        print(f"  {r['pair']:22s} {r['timeframe']:3s}  EG p={r['eg_pvalue']:.4f}  "
              f"ADF p={r['adf_pvalue_resid']:.4f}  beta={r['hedge_ratio_beta']:+.3f}  "
              f"N_formacion={r['n_bars_formation']}")

    os.makedirs("results", exist_ok=True)
    with open("results/pairs_cointegration_screen.json", "w", encoding="utf-8") as f:
        json.dump({"all_results": results, "cointegrados": cointegrados,
                    "p_value_threshold": P_VALUE_THRESHOLD,
                    "formation_fraction": FORMATION_FRACTION}, f, indent=2, ensure_ascii=False)
    print(f"\n[OK] resultados -> results/pairs_cointegration_screen.json")


if __name__ == "__main__":
    main()

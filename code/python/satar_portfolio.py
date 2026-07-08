# -*- coding: utf-8 -*-
"""
SATAR-1 — Consolidador de Portfolio (FASE C)
Fusiona trades de múltiples activos y calcula métricas agregadas de portfolio.

Entrada: trades_{sym}_hmm.csv (Pilar C + B con HMM activado)
Salida: results/portfolio_metrics.json + reporte en consola

Uso: python satar_portfolio.py
"""
import os
import json
import pandas as pd
import numpy as np
import math


def load_asset_trades(symbol: str) -> pd.DataFrame:
    """Carga trades de un activo, devuelve None si no existe el archivo."""
    fn = f"trades_{symbol.lower()}_hmm.csv"
    if not os.path.exists(fn):
        print(f"[aviso] {fn} no encontrado")
        return None
    df = pd.read_csv(fn)
    df['symbol'] = symbol  # añadir columna de símbolo si no la tiene
    return df


def calculate_metrics(trades_df: pd.DataFrame, name: str = "Portfolio") -> dict:
    """Calcula métricas de un lote de trades (FASE-4 §4)."""
    if trades_df is None or len(trades_df) == 0:
        return {"trades": 0, "nota": "sin operaciones"}

    tr = trades_df
    pnl = np.array(tr['pnl'])
    win = pnl[pnl > 0]
    los = pnl[pnl < 0]

    # Equity curve partiendo de capital inicial (mismo que el motor: 10.000 USD)
    EQUITY0 = 10_000.0
    equity_curve = EQUITY0 + np.cumsum(pnl)
    peak = np.maximum.accumulate(equity_curve)
    dd = (equity_curve - peak) / peak          # peak siempre >= EQUITY0 > 0
    equity_final = float(equity_curve[-1])

    # Años reales a partir de los timestamps de los trades (t_entry .. t_exit en epoch s)
    if 't_entry' in tr.columns and 't_exit' in tr.columns and len(tr) > 0:
        t0 = float(tr['t_entry'].min())
        t1 = float(tr['t_exit'].max())
        years = max((t1 - t0) / 31_557_600.0, 1e-9)   # segundos por año juliano
    else:
        years = max(1.0, len(tr) / 5.7)               # fallback: ~5.7 trades/año (BTC)

    # Retornos por-trade para Sharpe/Sortino (proxy; no anualizado por día real)
    try:
        rets = np.diff(equity_curve, prepend=EQUITY0) / np.concatenate([[EQUITY0], equity_curve[:-1]])
        rets = rets[np.isfinite(rets)]
        sharpe = float(rets.mean() / rets.std() * math.sqrt(len(rets))) if len(rets) > 2 and rets.std() > 0 else 0.0
        dnn = rets[rets < 0]
        sortino = float(rets.mean() / dnn.std() * math.sqrt(len(rets))) if len(dnn) > 2 and dnn.std() > 0 else 0.0
    except Exception:
        sharpe = sortino = 0.0

    # Rachas
    streaks = {"win": 0, "loss": 0}
    cw = cl = 0
    for x in pnl:
        cw, cl = (cw + 1, 0) if x > 0 else (0, cl + 1)
        streaks["win"] = max(streaks["win"], cw)
        streaks["loss"] = max(streaks["loss"], cl)

    ret_total = equity_final / EQUITY0 - 1.0
    cagr = (equity_final / EQUITY0) ** (1.0 / years) - 1.0 if equity_final > 0 else -1.0

    metrics = {
        "nombre": name,
        "trades": len(tr),
        "win_rate": round(float(len(win) / len(tr)) if len(tr) else 0, 4),
        "profit_factor": round(float(win.sum() / abs(los.sum())) if len(los) and los.sum() != 0 else (float("inf") if len(win) > 0 else 0), 3),
        "expectancy_usd": round(float(pnl.mean()), 2),
        "expectancy_R": round(float(np.mean([t for t in tr['r']])) if 'r' in tr.columns else 0, 3),
        "max_drawdown": round(float(dd.min()), 4),
        "recovery_factor": round(float((equity_final - EQUITY0) / abs(dd.min() * peak.max())) if dd.min() < 0 else float("inf"), 2),
        "sharpe": round(sharpe, 2),
        "sortino": round(sortino, 2),
        "cagr": round(cagr, 4),
        "ret_total": round(ret_total, 4),
        "años": round(years, 2),
        "trades_por_año": round(float(len(tr) / years), 1),
        "racha_max": streaks,
        "pnl_total": round(float(pnl.sum()), 2),
        "pnl_ganador_medio": round(float(win.mean()) if len(win) else 0, 2),
        "pnl_perdedor_medio": round(float(los.mean()) if len(los) else 0, 2),
    }
    return metrics


def main():
    # Símbolos a consolidar (BTC ya se corrió en línea base)
    symbols = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "XRPUSDT", "BNBUSDT"]

    print("[FASE-C] Cargando trades de todos los activos...")
    all_trades = []
    metrics_por_activo = {}

    for sym in symbols:
        df = load_asset_trades(sym)
        if df is not None:
            print(f"  {sym}: {len(df)} trades")
            all_trades.append(df)
            metrics_por_activo[sym] = calculate_metrics(df, name=sym)
        else:
            metrics_por_activo[sym] = {"trades": 0, "nota": "dataset no encontrado"}

    if not all_trades:
        print("[error] No se encontró ningún archivo de trades.")
        return

    # Fusionar todos
    portfolio_trades = pd.concat(all_trades, ignore_index=True)
    portfolio_trades = portfolio_trades.sort_values('t_entry').reset_index(drop=True)

    print(f"\n[FASE-C] Portfolio consolidado: {len(portfolio_trades)} trades totales")

    # Métricas agregadas
    metrics_portfolio = calculate_metrics(portfolio_trades, name="PORTFOLIO AGREGADO")

    # Hipótesis H0 de Alex Ruiz (FASE-4)
    h0 = {
        "nombre": "Hipótesis Alex Ruiz (H0)",
        "win_rate": 0.57,
        "trades_por_año": 80,
        "cagr": 0.34,
        "max_drawdown": -0.10,
        "profit_factor": 1.5,
    }

    # Comparativa
    print("\n" + "="*80)
    print("METRICAS POR ACTIVO")
    print("="*80)
    for sym, m in metrics_por_activo.items():
        if m.get("trades", 0) > 0:
            print(f"\n{sym}:")
            print(f"  Trades: {m['trades']} | WR: {m['win_rate']:.1%} | PF: {m['profit_factor']} | Exp_R: {m['expectancy_R']}")
            print(f"  CAGR: {m['cagr']:.1%} | DD: {m['max_drawdown']:.1%} | Trades/año: {m['trades_por_año']}")

    print("\n" + "="*80)
    print("AGREGADO PORTFOLIO")
    print("="*80)
    print(f"Trades totales: {metrics_portfolio['trades']}")
    print(f"Win Rate: {metrics_portfolio['win_rate']:.1%}")
    print(f"Profit Factor: {metrics_portfolio['profit_factor']}")
    print(f"Expectancy_R: {metrics_portfolio['expectancy_R']}")
    print(f"CAGR: {metrics_portfolio['cagr']:.1%}")
    print(f"Max Drawdown: {metrics_portfolio['max_drawdown']:.1%}")
    print(f"Trades/año: {metrics_portfolio['trades_por_año']}")

    print("\n" + "="*80)
    print("COMPARATIVA vs. HIPOTESIS H0 (Alex Ruiz)")
    print("="*80)
    print(f"WR: {metrics_portfolio['win_rate']:.1%} vs. H0 {h0['win_rate']:.1%} [{'PASS' if metrics_portfolio['win_rate'] > h0['win_rate']*0.75 else 'FAIL'}]")
    print(f"Trades/año: {metrics_portfolio['trades_por_año']:.1f} vs. H0 {h0['trades_por_año']:.1f} [{'PASS' if metrics_portfolio['trades_por_año'] > h0['trades_por_año']*0.75 else 'FAIL'}]")
    print(f"CAGR: {metrics_portfolio['cagr']:.1%} vs. H0 {h0['cagr']:.1%} [{'PASS' if metrics_portfolio['cagr'] > 0 else 'FAIL'}]")
    print(f"DD: {metrics_portfolio['max_drawdown']:.1%} vs. H0 {h0['max_drawdown']:.1%} [{'PASS' if abs(metrics_portfolio['max_drawdown']) < abs(h0['max_drawdown'])*1.5 else 'FAIL'}]")
    print(f"PF: {metrics_portfolio['profit_factor']} vs. H0 {h0['profit_factor']} [{'PASS' if metrics_portfolio['profit_factor'] > 1.0 else 'FAIL'}]")

    # Guardar JSON
    os.makedirs("results", exist_ok=True)
    with open("results/portfolio_metrics.json", "w") as f:
        json.dump({
            "portfolio": metrics_portfolio,
            "por_activo": metrics_por_activo,
            "h0": h0,
            "timestamp": str(pd.Timestamp.now()),
        }, f, indent=2, ensure_ascii=False)
    print(f"\n[OK] Resultados guardados en results/portfolio_metrics.json")


if __name__ == "__main__":
    main()

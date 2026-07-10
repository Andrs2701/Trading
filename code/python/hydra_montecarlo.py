# -*- coding: utf-8 -*-
"""
HYDRA — Monte Carlo, sensibilidad y estabilidad.

Se ejecuta SOBRE LA CONFIGURACIÓN CONGELADA post-WFO (results/wfo_results_hydra.json).
Tres familias de Monte Carlo + sensibilidad de parámetros + estabilidad.
"""
from __future__ import annotations
import argparse, glob, json, math, os
import numpy as np
import pandas as pd

from satar_backtest import resample
from hydra_backtest import HydraParams, HydraEngine, TFH, TF, hurst_rs, vwap_rolling, _sec

ASSETS = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "XRPUSDT", "BNBUSDT"]
EQUITY0 = 10_000.0
WARMUP_DAYS = 400
HOLDOUT_START = pd.Timestamp("2025-07-01", tz="UTC")


def load_asset(sym: str) -> pd.DataFrame | None:
    fn = f"{sym.lower()}_m5.csv"
    if not os.path.exists(fn):
        return None
    df = pd.read_csv(fn, parse_dates=["timestamp"], index_col="timestamp")
    if df.index.tz is None:
        df.index = df.index.tz_localize("UTC")
    return df.sort_index()


def collect_trades(params: HydraParams, assets: list, upto=HOLDOUT_START) -> list:
    pooled = []
    for s in assets:
        df = load_asset(s)
        if df is None:
            continue
        sub = df.loc[df.index < upto]
        if len(sub) < 5000:
            continue
        eng = HydraEngine(sub, params, symbol=s, equity0=EQUITY0)
        eng.run()
        we = int(upto.timestamp())
        pooled += [t for t in eng.trades if t.t_entry < we]
    return sorted(pooled, key=lambda t: t.t_entry)


def equity_dd(r: np.ndarray) -> float:
    """Equity COMPUESTO (cumprod), no aditivo: con cumsum(r) la formula puede
    producir equity negativo (matematicamente imposible -- en la realidad la
    cuenta habria quebrado antes) y drawdowns >100%, como se detecto en la
    auditoria de HYDRA (dd_worst=-605%). cumprod nunca cruza cero: converge
    asintoticamente a la ruina (0), que es el limite economico real."""
    eq = EQUITY0 * np.cumprod(1.0 + np.clip(0.01 * r, -0.99, None))
    peak = np.maximum.accumulate(eq)
    return float(((eq - peak) / peak).min())


# MC-1: bootstrap de la secuencia de R
def mc_bootstrap(r: np.ndarray, iters: int, rng) -> dict:
    n = len(r)
    dds, max_losses = np.empty(iters), np.empty(iters)
    for i in range(iters):
        sample = rng.choice(r, size=n, replace=True)
        dds[i] = equity_dd(sample)
        cl = ml = 0
        for x in sample:
            cl = cl + 1 if x <= 0 else 0
            ml = max(ml, cl)
        max_losses[i] = ml
    return {
        "dd_mean": round(float(dds.mean()), 4),
        "dd_p95": round(float(np.percentile(dds, 5)), 4),
        "dd_worst": round(float(dds.min()), 4),
        "max_loss_streak_p95": int(np.percentile(max_losses, 95)),
        "max_loss_streak_worst": int(max_losses.max()),
    }


# MC-2: perturbación de fricciones
def mc_frictions(trades: list, iters: int, rng, base: HydraParams) -> dict:
    r = np.array([t.r for t in trades], dtype=float)
    stop_pct = np.array([abs(t.entry - t.sl_init) / t.entry for t in trades], dtype=float)
    exps = np.empty(iters)
    for i in range(iters):
        slip_mult = rng.uniform(1.0, 3.0, size=len(r))
        spread_mult = rng.uniform(1.0, 2.0, size=len(r))
        extra_cost = (base.slip_pct * 2 * (slip_mult - 1) +
                      base.spread_pct * (spread_mult - 1))
        haircut_R = extra_cost / np.maximum(stop_pct, 1e-9)
        exps[i] = float((r - haircut_R).mean())
    return {
        "expectancy_mean": round(float(exps.mean()), 4),
        "expectancy_p25": round(float(np.percentile(exps, 25)), 4),
        "expectancy_p05": round(float(np.percentile(exps, 5)), 4),
        "pasa_p25_positivo": bool(np.percentile(exps, 25) > 0),
    }


# MC-3: perturbación de precios de entrada
def mc_price_noise(trades: list, iters: int, rng) -> dict:
    r = np.array([t.r for t in trades], dtype=float)
    base_exp = float(r.mean())
    winners = r > 0
    n_winners = int(winners.sum())
    exps = np.empty(iters)
    flip_rate = np.empty(iters)
    for i in range(iters):
        sigma = 0.05 * np.abs(r) + 0.02
        noisy = r + rng.normal(0.0, sigma)
        exps[i] = float(noisy.mean())
        flip_rate[i] = float((noisy[winners] <= 0).sum()) / n_winners if n_winners else 0.0
    drop = float(flip_rate.mean())
    return {
        "expectancy_base": round(base_exp, 4),
        "expectancy_mean_noisy": round(float(exps.mean()), 4),
        "expectancy_p05_noisy": round(float(np.percentile(exps, 5)), 4),
        "caida_relativa": round(drop, 4),
        "gatillo_fragil": bool(drop > 0.40),
    }


# Sensibilidad de parámetros NO optimizables (±20%)
NON_OPT_PARAMS = ["buf_atr", "stop_min_atr", "stop_max_atr", "tp_lookback", "pin_ratio", "armed_window"]


def sensitivity(base_overrides: dict, assets: list) -> list:
    base_exp = base_metrics(base_overrides, assets)["expectancy_R"]
    rows = []
    for pname in NON_OPT_PARAMS:
        base_val = getattr(HydraParams(), pname)
        for direction, factor in (("-20%", 0.8), ("+20%", 1.2)):
            ov = dict(base_overrides)
            newval = type(base_val)(base_val * factor) if not isinstance(base_val, int) else max(1, int(round(base_val * factor)))
            ov[pname] = newval
            m = base_metrics(ov, assets)
            d_exp = (m["expectancy_R"] - base_exp) / abs(base_exp) if base_exp != 0 else 0.0
            rows.append({
                "param": pname, "cambio": direction, "valor": newval,
                "expectancy_R": m["expectancy_R"], "trades": m["trades"],
                "delta_rel": round(float(d_exp), 3), "critico": bool(abs(d_exp) > 0.30),
            })
    return rows


def base_metrics(overrides: dict, assets: list) -> dict:
    p = HydraParams(**overrides)
    trades = collect_trades(p, assets)
    if not trades:
        return {"trades": 0, "expectancy_R": 0.0, "max_dd": 0.0, "win_rate": 0.0}
    r = np.array([t.r for t in trades], dtype=float)
    return {"trades": len(trades), "expectancy_R": round(float(r.mean()), 4),
            "max_dd": round(equity_dd(r), 4), "win_rate": round(float((r > 0).mean()), 4)}


# Estabilidad temporal y por activo
def stability(overrides: dict, assets: list) -> dict:
    p = HydraParams(**overrides)
    trades = collect_trades(p, assets)
    if not trades:
        return {}

    # Por activo
    asset_res = {}
    for s in assets:
        tr_s = [t for t in trades if t.symbol == s]
        n_s = len(tr_s)
        r_s = np.array([t.r for t in tr_s]) if tr_s else np.array([])
        asset_res[s] = {
            "trades": n_s,
            "expectancy_R": round(float(r_s.mean()), 4) if n_s else 0.0,
            "win_rate": round(float((r_s > 0).mean()), 4) if n_s else 0.0,
        }

    # Por tercios temporales
    trades_sorted = sorted(trades, key=lambda t: t.t_entry)
    n = len(trades_sorted)
    t1 = trades_sorted[:n // 3]
    t2 = trades_sorted[n // 3: 2 * n // 3]
    t3 = trades_sorted[2 * n // 3:]

    temporal_res = {}
    for idx, t_slice in enumerate([t1, t2, t3], 1):
        n_slice = len(t_slice)
        r_slice = np.array([t.r for t in t_slice]) if t_slice else np.array([])
        temporal_res[f"tercio_{idx}"] = {
            "trades": n_slice,
            "expectancy_R": round(float(r_slice.mean()), 4) if n_slice else 0.0,
            "win_rate": round(float((r_slice > 0).mean()), 4) if n_slice else 0.0,
        }

    return {"activos": asset_res, "temporal": temporal_res}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--config-from-wfo", action="store_true")
    ap.add_argument("--defaults", action="store_true")
    ap.add_argument("--iters", type=int, default=5000)
    ap.add_argument("--seed", type=int, default=7)
    args = ap.parse_args()

    overrides = {}
    if args.config_from_wfo:
        fn = "results/wfo_results_hydra.json"
        if os.path.exists(fn):
            with open(fn, encoding="utf-8") as f:
                wfo = json.load(f)
            overrides = wfo.get("config_congelada", {})
            print(f"[MC] Configuración congelada del WFO cargada: {overrides}")
        else:
            print(f"[error] {fn} no encontrado — ejecuta primero el WFO")
            return
    elif args.defaults:
        print("[MC] Usando parámetros por defecto de HYDRA")
    else:
        ap.print_help(); return

    assets = [s for s in ASSETS if os.path.exists(f"{s.lower()}_m5.csv")]
    print(f"[MC] Analizando robustez sobre pool: {assets}")

    p_base = HydraParams(**overrides)
    print("[MC] Recolectando trades históricos...")
    trades = collect_trades(p_base, assets)
    n = len(trades)
    print(f"[MC] {n} trades totales recolectados.")

    if n < 5:
        print("[error] Muestra insuficiente de trades (<5). Revisa filtros.")
        return

    r = np.array([t.r for t in trades], dtype=float)
    rng = np.random.default_rng(args.seed)

    print(f"[MC] Ejecutando bootstrap ({args.iters} iters)...")
    boot = mc_bootstrap(r, args.iters, rng)

    print(f"[MC] Ejecutando estresado de fricciones ({args.iters} iters)...")
    fric = mc_frictions(trades, args.iters, rng, p_base)

    print(f"[MC] Ejecutando perturbación de precios ({args.iters} iters)...")
    noise = mc_price_noise(trades, args.iters, rng)

    print("[MC] Ejecutando análisis de sensibilidad...")
    sens = sensitivity(overrides, assets)

    print("[MC] Ejecutando análisis de estabilidad...")
    stab = stability(overrides, assets)

    results = {
        "trades_totales": n,
        "expectancy_base": round(float(r.mean()), 4),
        "mc_1_bootstrap": boot,
        "mc_2_fricciones": fric,
        "mc_3_ruido_precio": noise,
        "sensibilidad": sens,
        "estabilidad": stab,
    }

    # Guardar resultados
    os.makedirs("results", exist_ok=True)
    out_fn = "results/montecarlo_results_hydra.json"
    with open(out_fn, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2, ensure_ascii=False)

    print(f"\n[MC] Análisis completado. Resultados en: {out_fn}")

    # Imprimir resumen
    print("\n" + "="*50)
    print("HYDRA RESUMEN DE ROBUSTEZ MONTE CARLO")
    print("="*50)
    print(f"Expectancy base:            {results['expectancy_base']:.4f} R")
    print(f"DD Percentil 95 (Bootstrap): {boot['dd_p95']*100:.2f}%")
    print(f"Expectancy p25 (Fricciones): {fric['expectancy_p25']:.4f} R (Pasa: {fric['pasa_p25_positivo']})")
    print(f"Caída por ruido de precio:   {noise['caida_relativa']*100:.1f}% (Frágil: {noise['gatillo_fragil']})")
    print("="*50)


if __name__ == "__main__":
    main()

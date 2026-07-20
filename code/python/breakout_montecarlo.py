# -*- coding: utf-8 -*-
"""
BREAKOUT-ATR — Monte Carlo, sensibilidad y estabilidad.

Se ejecuta SOBRE LA CONFIGURACIÓN CONGELADA post-WFO (results/wfo_results_breakout.json).
"""
from __future__ import annotations
import argparse, json, math, os
import numpy as np
import pandas as pd

from breakout_backtest import BreakoutParams, BreakoutEngine

ASSETS = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "XRPUSDT", "BNBUSDT"]
EQUITY0 = 10_000.0
HOLDOUT_START = pd.Timestamp("2025-07-01", tz="UTC")


def load_asset(sym: str) -> pd.DataFrame | None:
    fn = f"{sym.lower()}_m5.csv"
    if not os.path.exists(fn):
        return None
    df = pd.read_csv(fn, parse_dates=["timestamp"], index_col="timestamp")
    if df.index.tz is None:
        df.index = df.index.tz_localize("UTC")
    return df.sort_index()


def collect_trades(params: BreakoutParams, assets: list, upto=HOLDOUT_START) -> list:
    pooled = []
    for s in assets:
        df = load_asset(s)
        if df is None:
            continue
        sub = df.loc[df.index < upto]
        if len(sub) < 3000:
            continue
        eng = BreakoutEngine(sub, params, symbol=s, equity0=EQUITY0)
        eng.run()
        we = int(upto.timestamp())
        pooled += [t for t in eng.trades if t.t_entry < we]
    return sorted(pooled, key=lambda t: t.t_entry)


def equity_dd(r: np.ndarray) -> float:
    eq = EQUITY0 * np.cumprod(1.0 + np.clip(0.01 * r, -0.99, None))
    peak = np.maximum.accumulate(eq)
    return float(((eq - peak) / peak).min())


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


def mc_frictions(trades: list, iters: int, rng, base: BreakoutParams) -> dict:
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


NON_OPT_PARAMS = ["lookback_hours", "vol_ma_window_hours", "ema_trail_n",
                  "hurst_window_days", "hurst_filter", "stop_min_atr", "stop_max_atr"]


def sensitivity(base_overrides: dict, assets: list) -> list:
    base_exp = base_metrics(base_overrides, assets)["expectancy_R"]
    rows = []
    for pname in NON_OPT_PARAMS:
        base_val = getattr(BreakoutParams(), pname)
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
    p = BreakoutParams(**overrides)
    trades = collect_trades(p, assets)
    if not trades:
        return {"trades": 0, "expectancy_R": 0.0, "max_dd": 0.0, "win_rate": 0.0}
    r = np.array([t.r for t in trades], dtype=float)
    return {"trades": len(trades), "expectancy_R": round(float(r.mean()), 4),
            "max_dd": round(equity_dd(r), 4), "win_rate": round(float((r > 0).mean()), 4)}


def stability(overrides: dict, assets: list) -> dict:
    p = BreakoutParams(**overrides)
    per_asset = {}
    all_r = []
    for s in assets:
        df = load_asset(s)
        if df is None:
            continue
        sub = df.loc[df.index < HOLDOUT_START]
        if len(sub) < 3000:
            continue
        eng = BreakoutEngine(sub, p, symbol=s, equity0=EQUITY0)
        eng.run()
        we = int(HOLDOUT_START.timestamp())
        tr = [t for t in eng.trades if t.t_entry < we]
        pnl = sum(t.pnl for t in tr)
        per_asset[s] = {"trades": len(tr), "pnl": round(pnl, 2)}
        for t in tr:
            all_r.append((t.t_entry, t.r, t.pnl))

    total_pnl = sum(v["pnl"] for v in per_asset.values())
    max_asset_share = max((abs(v["pnl"]) / abs(total_pnl) if total_pnl else 0)
                          for v in per_asset.values()) if per_asset else 0

    all_r.sort(key=lambda x: x[0])
    thirds = [0.0, 0.0, 0.0]
    if all_r:
        t_min, t_max = all_r[0][0], all_r[-1][0]
        span = t_max - t_min
        cut1, cut2 = t_min + span / 3, t_min + 2 * span / 3
        for t_entry, _, pnl in all_r:
            if span <= 0 or t_entry < cut1:
                idx = 0
            elif t_entry < cut2:
                idx = 1
            else:
                idx = 2
            thirds[idx] += pnl
    max_third_share = max((abs(t) / abs(sum(thirds)) if sum(thirds) else 0) for t in thirds) if all_r else 0

    return {
        "por_activo": per_asset,
        "pnl_total": round(total_pnl, 2),
        "max_share_activo": round(float(max_asset_share), 3),
        "alarma_concentracion_activo": bool(max_asset_share > 0.50),
        "pnl_por_tercio": [round(t, 2) for t in thirds],
        "max_share_tercio": round(float(max_third_share), 3),
        "alarma_concentracion_temporal": bool(max_third_share > 0.60),
    }


def get_config() -> dict:
    fn = "results/wfo_results_breakout.json"
    if os.path.exists(fn):
        with open(fn, encoding="utf-8") as f:
            wfo = json.load(f)
        return wfo.get("config_congelada", {})
    return {}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--config-from-wfo", action="store_true")
    ap.add_argument("--defaults", action="store_true")
    ap.add_argument("--iters", type=int, default=5000)
    ap.add_argument("--seed", type=int, default=7)
    args = ap.parse_args()

    if args.config_from_wfo:
        overrides = get_config()
        print(f"[MC] config congelada del WFO: {overrides}")
    else:
        overrides = {}
        print("[MC] usando parámetros por defecto (modo diagnóstico)")

    rng = np.random.default_rng(args.seed)
    assets = [s for s in ASSETS if os.path.exists(f"{s.lower()}_m5.csv")]
    base = BreakoutParams(**overrides)

    print(f"[MC] recolectando trades (región no-holdout, hasta {HOLDOUT_START.date()})...")
    trades = collect_trades(base, assets)
    r = np.array([t.r for t in trades], dtype=float)
    print(f"[MC] {len(trades)} trades | expectancy_R={r.mean():.4f} | WR={(r>0).mean():.1%}")

    if len(trades) < 10:
        print("[MC] muy pocos trades — abortando MC")
        return

    print(f"[MC] MC-1 bootstrap ({args.iters} iters)...")
    mc1 = mc_bootstrap(r, args.iters, rng)
    print(f"[MC] MC-2 fricciones ({args.iters} iters)...")
    mc2 = mc_frictions(trades, args.iters, rng, base)
    print(f"[MC] MC-3 ruido de precios ({args.iters} iters)...")
    mc3 = mc_price_noise(trades, args.iters, rng)
    print("[MC] sensibilidad de parámetros no optimizables (±20%)...")
    sens = sensitivity(overrides, assets)
    print("[MC] estabilidad temporal y por activo...")
    stab = stability(overrides, assets)

    out = {
        "config": overrides,
        "n_trades": len(trades),
        "expectancy_R_base": round(float(r.mean()), 4),
        "mc1_bootstrap": mc1,
        "mc2_frictions": mc2,
        "mc3_price_noise": mc3,
        "sensibilidad": sens,
        "estabilidad": stab,
    }
    os.makedirs("results", exist_ok=True)
    out_fn = "results/montecarlo_results_breakout.json"
    with open(out_fn, "w", encoding="utf-8") as f:
        json.dump(out, f, indent=2, ensure_ascii=False)

    print("\n=== RESUMEN MONTE CARLO BREAKOUT ===")
    print(f"MC-1 DD p95: {mc1['dd_p95']:.1%} (worst {mc1['dd_worst']:.1%})")
    print(f"MC-2 expectancy p25 con fricciones estresadas: {mc2['expectancy_p25']:.4f} R [{'OK' if mc2['pasa_p25_positivo'] else 'FAIL'}]")
    print(f"MC-3 caída de expectancy con ruido: {mc3['caida_relativa']:.1%} [{'FRAGIL' if mc3['gatillo_fragil'] else 'ROBUSTO'}]")
    print(f"Concentración activo: {stab['max_share_activo']:.1%} [{'ALARMA' if stab['alarma_concentracion_activo'] else 'ok'}]")
    print(f"Concentración temporal: {stab['max_share_tercio']:.1%} [{'ALARMA' if stab['alarma_concentracion_temporal'] else 'ok'}]")
    print(f"\n[OK] resultados -> {out_fn}")


if __name__ == "__main__":
    main()

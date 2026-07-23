# -*- coding: utf-8 -*-
"""
Hipótesis 6 (Pairs Trading) — Monte Carlo, sensibilidad y estabilidad.

Se ejecuta SOBRE LA CONFIGURACIÓN CONGELADA post-WFO de una temporalidad
dada (results/wfo_results_pairs_{TF}.json).
"""
from __future__ import annotations
import argparse, json, math, os
import numpy as np
import pandas as pd

from pairs_backtest import PairsParams, PairsEngine, load_close

EQUITY0 = 10_000.0
HOLDOUT_START = pd.Timestamp("2025-07-01", tz="UTC")

NON_OPT_PARAMS = ["max_holding_mult", "fee_pct", "spread_pct", "slip_pct"]


def load_pairs_for_tf(timeframe: str) -> list[str]:
    with open("results/pairs_cointegration_screen.json", encoding="utf-8") as f:
        scr = json.load(f)
    return [r["pair"] for r in scr["cointegrados"] if r["timeframe"] == timeframe]


def collect_trades(overrides: dict, pairs: list, timeframe: str, upto=HOLDOUT_START) -> list:
    pooled = []
    p = PairsParams(**overrides)
    for pair in pairs:
        sym_a, sym_b = pair.split("-")
        close_a = load_close(sym_a, timeframe)
        close_b = load_close(sym_b, timeframe)
        common = close_a.index.intersection(close_b.index)
        mask = common < upto
        sub_common = common[mask]
        if len(sub_common) < p.lookback_bars + 20:
            continue
        eng = PairsEngine(close_a.loc[sub_common], close_b.loc[sub_common], p, pair, equity0=EQUITY0)
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


def mc_frictions(trades: list, iters: int, rng, base: PairsParams) -> dict:
    """Estresa fee/spread/slip en AMBAS piernas (doble impacto vs single-asset)."""
    r = np.array([t.r for t in trades], dtype=float)
    # distancia al stop en unidades de R ~ 1 (por construccion del sizing), asi que
    # el "haircut" se aplica directo como fraccion del riesgo via el costo extra de friccion.
    notional_ref = np.array([t.qty_a * t.entry_a + t.qty_b * t.entry_b for t in trades], dtype=float)
    risk_ref = np.array([abs(t.pnl / t.r) if t.r != 0 else 1.0 for t in trades], dtype=float)
    exps = np.empty(iters)
    for i in range(iters):
        slip_mult = rng.uniform(1.0, 3.0, size=len(r))
        spread_mult = rng.uniform(1.0, 2.0, size=len(r))
        extra_cost_frac = (base.slip_pct * 2 * (slip_mult - 1) + base.spread_pct * (spread_mult - 1))
        # x2 porque son 2 piernas, x2 porque es entrada+salida
        extra_cost_usd = extra_cost_frac * notional_ref * 4
        haircut_R = extra_cost_usd / np.maximum(risk_ref, 1e-9)
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


def base_metrics(overrides: dict, pairs: list, timeframe: str) -> dict:
    trades = collect_trades(overrides, pairs, timeframe)
    if not trades:
        return {"trades": 0, "expectancy_R": 0.0, "max_dd": 0.0, "win_rate": 0.0}
    r = np.array([t.r for t in trades], dtype=float)
    return {"trades": len(trades), "expectancy_R": round(float(r.mean()), 4),
            "max_dd": round(equity_dd(r), 4), "win_rate": round(float((r > 0).mean()), 4)}


def sensitivity(base_overrides: dict, pairs: list, timeframe: str) -> list:
    base_exp = base_metrics(base_overrides, pairs, timeframe)["expectancy_R"]
    rows = []
    for pname in NON_OPT_PARAMS:
        base_val = getattr(PairsParams(), pname)
        for direction, factor in (("-20%", 0.8), ("+20%", 1.2)):
            ov = dict(base_overrides)
            ov[pname] = base_val * factor
            m = base_metrics(ov, pairs, timeframe)
            d_exp = (m["expectancy_R"] - base_exp) / abs(base_exp) if base_exp != 0 else 0.0
            rows.append({
                "param": pname, "cambio": direction, "valor": round(ov[pname], 6),
                "expectancy_R": m["expectancy_R"], "trades": m["trades"],
                "delta_rel": round(float(d_exp), 3), "critico": bool(abs(d_exp) > 0.30),
            })
    return rows


def stability(overrides: dict, pairs: list, timeframe: str) -> dict:
    p = PairsParams(**overrides)
    per_pair = {}
    all_r = []
    for pair in pairs:
        sym_a, sym_b = pair.split("-")
        close_a = load_close(sym_a, timeframe)
        close_b = load_close(sym_b, timeframe)
        common = close_a.index.intersection(close_b.index)
        sub_common = common[common < HOLDOUT_START]
        if len(sub_common) < p.lookback_bars + 20:
            continue
        eng = PairsEngine(close_a.loc[sub_common], close_b.loc[sub_common], p, pair, equity0=EQUITY0)
        eng.run()
        we = int(HOLDOUT_START.timestamp())
        tr = [t for t in eng.trades if t.t_entry < we]
        pnl = sum(t.pnl for t in tr)
        per_pair[pair] = {"trades": len(tr), "pnl": round(pnl, 2)}
        for t in tr:
            all_r.append((t.t_entry, t.r, t.pnl))

    total_pnl = sum(v["pnl"] for v in per_pair.values())
    max_pair_share = max((abs(v["pnl"]) / abs(total_pnl) if total_pnl else 0)
                         for v in per_pair.values()) if per_pair else 0

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
        "por_par": per_pair,
        "pnl_total": round(total_pnl, 2),
        "max_share_par": round(float(max_pair_share), 3),
        "alarma_concentracion_par": bool(max_pair_share > 0.50),
        "pnl_por_tercio": [round(t, 2) for t in thirds],
        "max_share_tercio": round(float(max_third_share), 3),
        "alarma_concentracion_temporal": bool(max_third_share > 0.60),
    }


def get_config(timeframe: str, tag: str | None = None) -> dict:
    suffix = f"_{tag}" if tag else ""
    fn = f"results/wfo_results_pairs_{timeframe}{suffix}.json"
    if os.path.exists(fn):
        with open(fn, encoding="utf-8") as f:
            wfo = json.load(f)
        return wfo.get("config_congelada", {})
    return {}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--timeframe", required=True, choices=["H1", "H4", "D1"])
    ap.add_argument("--config-from-wfo", action="store_true")
    ap.add_argument("--iters", type=int, default=5000)
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--exclude", type=str, default=None,
                     help="Pares a excluir del pool, separados por coma")
    ap.add_argument("--tag", type=str, default=None,
                     help="Sufijo para leer/escribir resultados sin pisar el canonico")
    args = ap.parse_args()
    exclude = set(args.exclude.split(",")) if args.exclude else set()

    pairs = [p for p in load_pairs_for_tf(args.timeframe) if p not in exclude]
    if args.config_from_wfo:
        overrides = get_config(args.timeframe, tag=args.tag)
        print(f"[MC-PAIRS-{args.timeframe}] config congelada del WFO: {overrides}")
    else:
        overrides = {}
        print(f"[MC-PAIRS-{args.timeframe}] usando parametros por defecto")

    rng = np.random.default_rng(args.seed)
    base = PairsParams(**overrides)

    print(f"[MC-PAIRS-{args.timeframe}] recolectando trades (region no-holdout, hasta {HOLDOUT_START.date()})...")
    trades = collect_trades(overrides, pairs, args.timeframe)
    r = np.array([t.r for t in trades], dtype=float)
    print(f"[MC-PAIRS-{args.timeframe}] {len(trades)} trades | expectancy_R={r.mean():.4f} | WR={(r>0).mean():.1%}")

    if len(trades) < 10:
        print(f"[MC-PAIRS-{args.timeframe}] muy pocos trades -- abortando MC")
        return

    print(f"[MC-PAIRS-{args.timeframe}] MC-1 bootstrap ({args.iters} iters)...")
    mc1 = mc_bootstrap(r, args.iters, rng)
    print(f"[MC-PAIRS-{args.timeframe}] MC-2 fricciones ({args.iters} iters)...")
    mc2 = mc_frictions(trades, args.iters, rng, base)
    print(f"[MC-PAIRS-{args.timeframe}] MC-3 ruido de precios ({args.iters} iters)...")
    mc3 = mc_price_noise(trades, args.iters, rng)
    print(f"[MC-PAIRS-{args.timeframe}] sensibilidad de parametros no optimizables (+/-20%)...")
    sens = sensitivity(overrides, pairs, args.timeframe)
    print(f"[MC-PAIRS-{args.timeframe}] estabilidad temporal y por par...")
    stab = stability(overrides, pairs, args.timeframe)

    out = {
        "timeframe": args.timeframe, "pairs": pairs, "config": overrides,
        "n_trades": len(trades), "expectancy_R_base": round(float(r.mean()), 4),
        "mc1_bootstrap": mc1, "mc2_frictions": mc2, "mc3_price_noise": mc3,
        "sensibilidad": sens, "estabilidad": stab,
    }
    os.makedirs("results", exist_ok=True)
    suffix = f"_{args.tag}" if args.tag else ""
    out_fn = f"results/montecarlo_results_pairs_{args.timeframe}{suffix}.json"
    with open(out_fn, "w", encoding="utf-8") as f:
        json.dump(out, f, indent=2, ensure_ascii=False)

    criticos = [s for s in sens if s["critico"]]
    print(f"\n=== RESUMEN MONTE CARLO PAIRS {args.timeframe} ===")
    print(f"MC-1 DD p95: {mc1['dd_p95']:.1%} (worst {mc1['dd_worst']:.1%})")
    print(f"MC-2 expectancy p25 con fricciones estresadas: {mc2['expectancy_p25']:.4f} R [{'OK' if mc2['pasa_p25_positivo'] else 'FAIL'}]")
    print(f"MC-3 caida de expectancy con ruido: {mc3['caida_relativa']:.1%} [{'FRAGIL' if mc3['gatillo_fragil'] else 'ROBUSTO'}]")
    print(f"Sensibilidad: {len(criticos)} de {len(sens)} parametros criticos (delta>30%)")
    print(f"Concentracion por par: {stab['max_share_par']:.1%} [{'ALARMA' if stab['alarma_concentracion_par'] else 'ok'}]")
    print(f"Concentracion temporal: {stab['max_share_tercio']:.1%} [{'ALARMA' if stab['alarma_concentracion_temporal'] else 'ok'}]")
    print(f"\n[OK] resultados -> {out_fn}")


if __name__ == "__main__":
    main()

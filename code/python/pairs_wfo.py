# -*- coding: utf-8 -*-
"""
Hipótesis 6 (Pairs Trading) — Walk-Forward Optimization.

Se corre por separado para cada temporalidad (H1/H4/D1) sobre el pool de
pares cointegrados en esa temporalidad (results/pairs_cointegration_screen.json).
La temporalidad "ganadora" se decide comparando los 3 veredictos OOS, no
mirando resultados intermedios (docs/PAIRS-formalizacion.md §3).
"""
from __future__ import annotations
import argparse, itertools, json, math, os, time
import numpy as np
import pandas as pd

from pairs_backtest import PairsParams, PairsEngine, load_close

EQUITY0 = 10_000.0
MIN_TRADES = 5
HOLDOUT_START = pd.Timestamp("2025-07-01", tz="UTC")

FOLDS = [
    {"name": "F1", "is": ("2020-01-01", "2023-01-01"), "oos": ("2023-01-01", "2024-01-01")},
    {"name": "F2", "is": ("2020-01-01", "2024-01-01"), "oos": ("2024-01-01", "2025-01-01")},
    {"name": "F3", "is": ("2020-01-01", "2025-01-01"), "oos": ("2025-01-01", "2025-07-01")},
]

GRID_BY_TF = {
    "H1": {"lookback_bars": [50, 100, 150], "z_entry": [1.5, 2.0, 2.5],
           "z_exit": [0.25, 0.5, 0.75], "z_stop": [3.0, 4.0, 5.0]},
    "H4": {"lookback_bars": [30, 60, 100], "z_entry": [1.5, 2.0, 2.5],
           "z_exit": [0.25, 0.5, 0.75], "z_stop": [3.0, 4.0, 5.0]},
    "D1": {"lookback_bars": [15, 20, 30], "z_entry": [1.5, 2.0, 2.5],
           "z_exit": [0.25, 0.5, 0.75], "z_stop": [3.0, 4.0, 5.0]},
}

_DATA: dict[str, tuple] = {}


def load_pairs_for_tf(timeframe: str) -> list[str]:
    with open("results/pairs_cointegration_screen.json", encoding="utf-8") as f:
        scr = json.load(f)
    return [r["pair"] for r in scr["cointegrados"] if r["timeframe"] == timeframe]


def _init_worker(pairs: list[str], timeframe: str):
    global _DATA
    _DATA = {}
    for pair in pairs:
        sym_a, sym_b = pair.split("-")
        _DATA[pair] = (load_close(sym_a, timeframe), load_close(sym_b, timeframe))


BAR_TIMEDELTA = {"H1": pd.Timedelta(hours=1), "H4": pd.Timedelta(hours=4), "D1": pd.Timedelta(days=1)}


def run_window(pair: str, overrides: dict, win_start: pd.Timestamp, win_end: pd.Timestamp,
               warmup_bars: int, timeframe: str) -> list:
    close_a, close_b = _DATA[pair]
    # Margen de calentamiento en unidades reales de la temporalidad (bug corregido:
    # antes asumia 6h/vela para todas, insuficiente para D1). x1.5 de colchon por
    # huecos de fin de semana/feriados en los datos.
    lo = win_start - BAR_TIMEDELTA[timeframe] * warmup_bars * 1.5
    mask_a = (close_a.index >= lo) & (close_a.index < win_end)
    mask_b = (close_b.index >= lo) & (close_b.index < win_end)
    sub_a, sub_b = close_a.loc[mask_a], close_b.loc[mask_b]
    if len(sub_a) < warmup_bars + 20 or len(sub_b) < warmup_bars + 20:
        return []
    p = PairsParams(**overrides)
    eng = PairsEngine(sub_a, sub_b, p, pair, equity0=EQUITY0)
    eng.run()
    ws, we = int(win_start.timestamp()), int(win_end.timestamp())
    return [t for t in eng.trades if ws <= t.t_entry < we]


def objective(trades: list) -> tuple[float, dict]:
    n = len(trades)
    if n < MIN_TRADES:
        return -999.0, {"trades": n, "expectancy_R": 0.0, "max_dd": 0.0, "win_rate": 0.0}
    trades = sorted(trades, key=lambda t: t.t_entry)
    r = np.array([t.r for t in trades], dtype=float)
    E_R = float(r.mean())
    eq = EQUITY0 * np.cumprod(1.0 + np.clip(0.01 * r, -0.99, None))
    peak = np.maximum.accumulate(eq)
    dd = float(((eq - peak) / peak).min())
    wr = float((r > 0).mean())
    obj = E_R * math.sqrt(n) / (1.0 + abs(dd) * 5.0)
    return obj, {"trades": n, "expectancy_R": round(E_R, 4),
                 "max_dd": round(dd, 4), "win_rate": round(wr, 4)}


def eval_combo(overrides: dict, win_start: pd.Timestamp, win_end: pd.Timestamp,
               pairs: list, lookback: int, timeframe: str) -> tuple[float, dict]:
    pooled = []
    for pr in pairs:
        pooled += run_window(pr, overrides, win_start, win_end, lookback, timeframe)
    return objective(pooled)


def _ts(s) -> pd.Timestamp:
    t = pd.Timestamp(s)
    return t.tz_localize("UTC") if t.tzinfo is None else t.tz_convert("UTC")


def _task(args):
    combo_id, overrides, is_start, is_end, pairs, timeframe = args
    obj, m = eval_combo(overrides, _ts(is_start), _ts(is_end), pairs, overrides["lookback_bars"], timeframe)
    return combo_id, overrides, obj, m


def build_grid(grid: dict) -> list[dict]:
    keys = list(grid.keys())
    return [dict(zip(keys, vals)) for vals in itertools.product(*grid.values())]


def run_wfo_tf(timeframe: str, jobs: int) -> dict:
    pairs = load_pairs_for_tf(timeframe)
    if not pairs:
        print(f"[PAIRS-WFO-{timeframe}] sin pares cointegrados en esta temporalidad, se omite")
        return {}
    grid = GRID_BY_TF[timeframe]
    combos = build_grid(grid)
    print(f"[PAIRS-WFO-{timeframe}] {len(pairs)} pares: {pairs} -> {len(combos)} combos/fold, {len(FOLDS)} folds")
    print(f"[PAIRS-WFO-{timeframe}] holdout intocable desde {HOLDOUT_START.date()}")

    from multiprocessing import Pool
    results = {"timeframe": timeframe, "pairs": pairs, "grid_keys": list(grid.keys()),
               "holdout_start": str(HOLDOUT_START), "folds": []}

    is_objs, oos_objs = [], []
    for fold in FOLDS:
        t0 = time.time()
        is_s, is_e = fold["is"]
        oos_s, oos_e = fold["oos"]
        assert pd.Timestamp(oos_e, tz="UTC") <= HOLDOUT_START, "OOS invade holdout!"

        tasks = [(i, ov, is_s, is_e, pairs, timeframe) for i, ov in enumerate(combos)]
        if jobs > 1:
            with Pool(jobs, initializer=_init_worker, initargs=(pairs, timeframe)) as pool:
                scored = pool.map(_task, tasks)
        else:
            _init_worker(pairs, timeframe)
            scored = [_task(t) for t in tasks]

        scored.sort(key=lambda x: x[2], reverse=True)
        best_id, best_ov, best_is_obj, best_is_m = scored[0]

        _init_worker(pairs, timeframe)
        oos_obj, oos_m = eval_combo(best_ov, _ts(oos_s), _ts(oos_e), pairs, best_ov["lookback_bars"], timeframe)

        is_objs.append(best_is_obj)
        oos_objs.append(oos_obj)

        fold_res = {
            "fold": fold["name"], "is_window": [is_s, is_e], "oos_window": [oos_s, oos_e],
            "best_overrides": best_ov,
            "is": {"obj": round(best_is_obj, 4), **best_is_m},
            "oos": {"obj": round(oos_obj, 4), **oos_m},
            "elapsed_s": round(time.time() - t0, 1),
        }
        results["folds"].append(fold_res)
        print(f"[PAIRS-WFO-{timeframe}] {fold['name']}: IS obj={best_is_obj:.4f} (N={best_is_m['trades']}, "
              f"E_R={best_is_m['expectancy_R']}) | OOS obj={oos_obj:.4f} (N={oos_m['trades']}, "
              f"E_R={oos_m['expectancy_R']}) | best={best_ov} | {fold_res['elapsed_s']}s")

        os.makedirs("results", exist_ok=True)
        with open(f"results/wfo_results_pairs_{timeframe}_partial.json", "w", encoding="utf-8") as f:
            json.dump(results, f, indent=2, ensure_ascii=False)

    mean_is = float(np.mean(is_objs)) if is_objs else 0.0
    mean_oos = float(np.mean(oos_objs)) if oos_objs else 0.0
    wfe = mean_oos / mean_is if mean_is > 0 else None
    results["mean_is_obj"] = round(mean_is, 4)
    results["mean_oos_obj"] = round(mean_oos, 4)
    results["wfe"] = round(wfe, 4) if wfe is not None else None

    if mean_is <= 0:
        verdict = f"NO RENTABLE IN-SAMPLE (mean_is={mean_is:.4f}<=0)"
    elif mean_oos <= 0:
        verdict = f"NO RENTABLE OOS (mean_oos={mean_oos:.4f}<=0)"
    elif wfe >= 0.7:
        verdict = "BUENO (WFE>=0.7)"
    elif wfe >= 0.5:
        verdict = "ACEPTABLE (WFE>=0.5)"
    elif wfe >= 0.4:
        verdict = "DEBIL (0.4<=WFE<0.5)"
    else:
        verdict = "SOBREOPTIMIZACION (WFE<0.4)"
    results["wfe_verdict"] = verdict
    results["rentable_is"] = bool(mean_is > 0)
    results["rentable_oos"] = bool(mean_oos > 0)
    results["config_congelada"] = results["folds"][-1]["best_overrides"]

    wfe_str = f"{wfe:.4f}" if wfe is not None else "N/A"
    print(f"\n[PAIRS-WFO-{timeframe}] WFE = {wfe_str} -> {verdict}")
    print(f"[PAIRS-WFO-{timeframe}] mean IS obj={mean_is:.4f} | mean OOS obj={mean_oos:.4f}")
    print(f"[PAIRS-WFO-{timeframe}] config congelada: {results['config_congelada']}\n")
    return results


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--timeframe", choices=["H1", "H4", "D1", "all"], default="all")
    ap.add_argument("--jobs", type=int, default=4)
    args = ap.parse_args()

    tfs = ["H1", "H4", "D1"] if args.timeframe == "all" else [args.timeframe]
    all_results = {}
    for tf in tfs:
        res = run_wfo_tf(tf, args.jobs)
        if res:
            all_results[tf] = res
            os.makedirs("results", exist_ok=True)
            with open(f"results/wfo_results_pairs_{tf}.json", "w", encoding="utf-8") as f:
                json.dump(res, f, indent=2, ensure_ascii=False)

    print("=== COMPARACION ENTRE TEMPORALIDADES ===")
    for tf, res in all_results.items():
        print(f"  {tf}: mean_oos_obj={res['mean_oos_obj']:.4f} | WFE={res['wfe']} | {res['wfe_verdict']}")


if __name__ == "__main__":
    main()

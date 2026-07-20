# -*- coding: utf-8 -*-
"""
HYDRA — Walk-Forward Optimization (WFO) anclado-rodante.

Optimiza los parámetros de HYDRA sobre el POOL combinado de los 5 activos cripto,
con particiones estrictas IS/OOS y un HOLDOUT final excluido.

Parámetros optimizables (HYDRA):
  hurst_trend, hurst_mean_rev, vol_spike_mult, score_threshold, bb_std, tp_rr_range
"""
from __future__ import annotations
import argparse, itertools, json, math, os, time
import numpy as np
import pandas as pd

from satar_backtest import resample
from hydra_backtest import HydraParams, HydraEngine, TFH, TF, hurst_rs, vwap_rolling, _sec

# ---------------------------------------------------------------------------
ASSETS = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "XRPUSDT", "BNBUSDT"]
WARMUP_DAYS = 400          # para calentar Hurst y Bollinger
EQUITY0 = 10_000.0
MIN_TRADES = 5             # piso duro de trades

# Holdout intocable
HOLDOUT_START = pd.Timestamp("2025-07-01", tz="UTC")

# Folds
FOLDS = [
    {"name": "F1", "is": ("2020-01-01", "2023-01-01"), "oos": ("2023-01-01", "2024-01-01")},
    {"name": "F2", "is": ("2020-01-01", "2024-01-01"), "oos": ("2024-01-01", "2025-01-01")},
    {"name": "F3", "is": ("2020-01-01", "2025-01-01"), "oos": ("2025-01-01", "2025-07-01")},
]

# Rejilla optimización
GRID_FULL = {
    "hurst_trend":    [0.51, 0.53, 0.55],
    "hurst_mean_rev": [0.45, 0.47, 0.49],
    "vol_spike_mult": [1.2, 1.5, 1.8],
    "score_threshold":[3, 4],
    "bb_std":         [1.8, 2.0, 2.2],
    "tp_rr_range":    [1.8, 2.2, 2.6],
}

GRID_COARSE = {
    "hurst_trend":    [0.51, 0.53, 0.55],
    "score_threshold":[3, 4],
    "tp_rr_range":    [1.8, 2.2, 2.6],
}

# Cache global por worker
_DATA: dict[str, pd.DataFrame] = {}


def load_assets(assets) -> dict:
    data = {}
    for s in assets:
        fn = f"{s.lower()}_m5.csv"
        if not os.path.exists(fn):
            print(f"[aviso] {fn} no encontrado — {s} excluido")
            continue
        df = pd.read_csv(fn, parse_dates=["timestamp"], index_col="timestamp")
        if df.index.tz is None:
            df.index = df.index.tz_localize("UTC")
        data[s] = df.sort_index()
    return data


def _init_worker(assets):
    global _DATA
    _DATA = load_assets(assets)


def run_window(df: pd.DataFrame, params: HydraParams, win_start: pd.Timestamp,
               win_end: pd.Timestamp, symbol: str) -> list:
    lo = win_start - pd.Timedelta(days=WARMUP_DAYS)
    mask = (df.index >= lo) & (df.index < win_end)
    sub = df.loc[mask]
    if len(sub) < 5000:
        return []
    eng = HydraEngine(sub, params, symbol=symbol, equity0=EQUITY0)
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
    # Equity COMPUESTO (cumprod), no aditivo -- ver hydra_montecarlo.py::equity_dd
    # para el detalle del bug que esto corrige (equity negativo, DD >100%).
    eq = EQUITY0 * np.cumprod(1.0 + np.clip(0.01 * r, -0.99, None))
    peak = np.maximum.accumulate(eq)
    dd = float(((eq - peak) / peak).min())
    wr = float((r > 0).mean())
    obj = E_R * math.sqrt(n) / (1.0 + abs(dd) * 5.0)
    return obj, {"trades": n, "expectancy_R": round(E_R, 4),
                 "max_dd": round(dd, 4), "win_rate": round(wr, 4)}


def eval_combo(overrides: dict, win_start: pd.Timestamp, win_end: pd.Timestamp,
               assets: list) -> tuple[float, dict]:
    # Partimos de los defaults de HydraParams y aplicamos overrides
    p = HydraParams(**overrides)
    pooled = []
    for s in assets:
        if s in _DATA:
            pooled += run_window(_DATA[s], p, win_start, win_end, symbol=s)
    return objective(pooled)


def _ts(s) -> pd.Timestamp:
    t = pd.Timestamp(s)
    return t.tz_localize("UTC") if t.tzinfo is None else t.tz_convert("UTC")


def _task(args):
    combo_id, overrides, is_start, is_end, assets = args
    obj, m = eval_combo(overrides, _ts(is_start), _ts(is_end), assets)
    return combo_id, overrides, obj, m


def build_grid(grid: dict) -> list[dict]:
    keys = list(grid.keys())
    return [dict(zip(keys, vals)) for vals in itertools.product(*grid.values())]


def run_wfo(grid_name: str, jobs: int, assets: list) -> dict:
    grid = GRID_FULL if grid_name == "full" else GRID_COARSE
    combos = build_grid(grid)
    print(f"[WFO] grid='{grid_name}' -> {len(combos)} combos/fold · {len(assets)} activos · {len(FOLDS)} folds")
    print(f"[WFO] holdout intocable desde {HOLDOUT_START.date()} (excluido de todos los folds)")

    from multiprocessing import Pool
    results = {"grid": grid_name, "grid_keys": list(grid.keys()),
               "assets": assets, "holdout_start": str(HOLDOUT_START), "folds": []}

    is_objs, oos_objs = [], []
    for fold in FOLDS:
        t0 = time.time()
        is_s, is_e = fold["is"]
        oos_s, oos_e = fold["oos"]
        assert pd.Timestamp(oos_e, tz="UTC") <= HOLDOUT_START, "OOS invade holdout!"

        tasks = [(i, ov, is_s, is_e, assets) for i, ov in enumerate(combos)]
        if jobs > 1:
            with Pool(jobs, initializer=_init_worker, initargs=(assets,)) as pool:
                scored = pool.map(_task, tasks)
        else:
            _init_worker(assets)
            scored = [_task(t) for t in tasks]

        # mejor combo IN-SAMPLE
        scored.sort(key=lambda x: x[2], reverse=True)
        best_id, best_ov, best_is_obj, best_is_m = scored[0]

        # evaluar ese combo UNA vez en OOS
        _init_worker(assets)
        oos_obj, oos_m = eval_combo(best_ov, _ts(oos_s), _ts(oos_e), assets)

        is_objs.append(best_is_obj)
        oos_objs.append(oos_obj)

        top5 = [{"overrides": ov, "obj": round(o, 4), **m} for _, ov, o, m in scored[:5]]

        fold_res = {
            "fold": fold["name"],
            "is_window": [is_s, is_e], "oos_window": [oos_s, oos_e],
            "best_overrides": best_ov,
            "is": {"obj": round(best_is_obj, 4), **best_is_m},
            "oos": {"obj": round(oos_obj, 4), **oos_m},
            "top5_is": top5,
            "elapsed_s": round(time.time() - t0, 1),
        }
        results["folds"].append(fold_res)
        print(f"[WFO] {fold['name']}: IS obj={best_is_obj:.4f} (N={best_is_m['trades']}, "
              f"E_R={best_is_m['expectancy_R']}) | OOS obj={oos_obj:.4f} "
              f"(N={oos_m['trades']}, E_R={oos_m['expectancy_R']}) | best={best_ov} | {fold_res['elapsed_s']}s")

    mean_is = float(np.mean(is_objs)) if is_objs else 0.0
    mean_oos = float(np.mean(oos_objs)) if oos_objs else 0.0
    wfe = mean_oos / mean_is if mean_is > 0 else None
    results["mean_is_obj"] = round(mean_is, 4)
    results["mean_oos_obj"] = round(mean_oos, 4)
    results["wfe"] = round(wfe, 4) if wfe is not None else None

    if mean_is <= 0:
        verdict = "NO RENTABLE IN-SAMPLE (mean_is<=0)"
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
    print(f"\n[WFO] WFE = {wfe_str} -> {verdict}")
    print(f"[WFO] mean IS obj={mean_is:.4f} | mean OOS obj={mean_oos:.4f}")
    print(f"[WFO] config congelada: {results['config_congelada']}")
    return results


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--smoke", action="store_true", help="plumbing rápido")
    ap.add_argument("--time", action="store_true", help="cronometra 1 combo")
    ap.add_argument("--grid", choices=["coarse", "full"], default="coarse")
    ap.add_argument("--jobs", type=int, default=1)
    args = ap.parse_args()

    if args.time:
        _init_worker(ASSETS)
        t0 = time.time()
        obj, m = eval_combo({}, _ts(FOLDS[0]["is"][0]), _ts(FOLDS[0]["is"][1]), ASSETS)
        dt = time.time() - t0
        print(f"[time] 1 combo (5 activos) sobre IS de F1 (3 años): {dt:.1f}s")
        print(f"[time] obj={obj:.4f} {m}")
        return

    if args.smoke:
        _init_worker(["BTCUSDT"])
        p = HydraParams()
        trades = run_window(_DATA["BTCUSDT"], p, _ts(FOLDS[0]["is"][0]),
                            _ts(FOLDS[0]["is"][1]), "BTCUSDT")
        obj, m = objective(trades)
        print(f"[smoke] BTC IS F1: {len(trades)} trades, obj={obj:.4f}, {m}")
        print("[smoke] OK — plumbing funciona" if trades else "[smoke] 0 trades")
        return

    assets = [s for s in ASSETS if os.path.exists(f"{s.lower()}_m5.csv")]
    res = run_wfo(args.grid, args.jobs, assets)
    os.makedirs("results", exist_ok=True)
    with open("results/wfo_results_hydra.json", "w", encoding="utf-8") as f:
        json.dump(res, f, indent=2, ensure_ascii=False)
    print("\n[OK] resultados -> results/wfo_results_hydra.json")


if __name__ == "__main__":
    main()

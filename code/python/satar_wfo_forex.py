# -*- coding: utf-8 -*-
"""
Hipótesis 5 — Walk-Forward Optimization de SATAR-1 sobre Forex.

Reutiliza la infraestructura auditada de satar_wfo.py con las siguientes
adaptaciones mínimas:
  - Activos: EURUSD, GBPUSD, USDJPY, XAUUSD (en vez de 5 cripto)
  - Fricciones: calibradas por par forex (sin comisión taker, spread en pips)
  - Offset D1: 22:00 UTC (cierre NY, convención forex)
  - Folds: 4 folds anclados-rodantes sobre 2010-2025 (más historia que cripto)
  - Holdout: 2025-01-01 en adelante (~15% final)

Los parámetros de trading (P01-P37) NO se modifican. La prueba es:
"¿funciona la misma regla SATAR-1 en forex sin recalibración?"

Uso:
  python satar_wfo_forex.py --smoke
  python satar_wfo_forex.py --grid coarse --jobs 4
  python satar_wfo_forex.py --grid full --jobs 8
"""
from __future__ import annotations
import argparse, itertools, json, math, os, time
import numpy as np
import pandas as pd

from satar_backtest import Params, Engine
from satar_forex_config import FOREX_FRICTIONS, FOREX_ASSETS, FOREX_DAILY_OFFSET

# ---------------------------------------------------------------------------
ASSETS = FOREX_ASSETS
WARMUP_DAYS = 400
EQUITY0 = 10_000.0
MIN_TRADES = 5

HOLDOUT_START = pd.Timestamp("2025-01-01", tz="UTC")

# Folds anclados-rodantes: más historia permite 4 folds
FOLDS = [
    {"name": "F1", "is": ("2010-01-01", "2016-01-01"), "oos": ("2016-01-01", "2018-01-01")},
    {"name": "F2", "is": ("2010-01-01", "2018-01-01"), "oos": ("2018-01-01", "2020-01-01")},
    {"name": "F3", "is": ("2010-01-01", "2020-01-01"), "oos": ("2020-01-01", "2022-01-01")},
    {"name": "F4", "is": ("2010-01-01", "2022-01-01"), "oos": ("2022-01-01", "2025-01-01")},
]

# Misma rejilla que cripto — no se recalibra
GRID_FULL = {
    "zone_w_atr":   [0.375, 0.5, 0.625],
    "er_clean":     [0.22, 0.30, 0.38],
    "er_arrive":    [0.26, 0.35, 0.44],
    "decel_max":    [0.45, 0.60, 0.75],
    "chase_atr":    [0.375, 0.5, 0.625],
    "armed_window": [8, 12, 16],
}
GRID_COARSE = {
    "er_clean":     [0.22, 0.30, 0.38],
    "er_arrive":    [0.26, 0.35, 0.44],
    "decel_max":    [0.45, 0.60, 0.75],
}

_DATA: dict[str, pd.DataFrame] = {}


# ---------------------------------------------------------------------------
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


def _make_params(symbol: str, overrides: dict) -> Params:
    """Crea Params con fricciones forex del activo + overrides del grid."""
    friction = FOREX_FRICTIONS.get(symbol, {})
    return Params(**{**friction, **overrides})


def run_window(df: pd.DataFrame, symbol: str, overrides: dict,
               win_start: pd.Timestamp, win_end: pd.Timestamp) -> list:
    """Corre el motor con warm-up y devuelve trades dentro de [win_start, win_end)."""
    lo = win_start - pd.Timedelta(days=WARMUP_DAYS)
    mask = (df.index >= lo) & (df.index < win_end)
    sub = df.loc[mask]
    if len(sub) < 5000:
        return []
    params = _make_params(symbol, overrides)
    eng = Engine(sub, params, symbol=symbol, equity0=EQUITY0,
                 daily_offset=FOREX_DAILY_OFFSET)
    eng.run()
    ws, we = int(win_start.timestamp()), int(win_end.timestamp())
    return [t for t in eng.trades if ws <= t.t_entry < we]


def objective(trades: list) -> tuple[float, dict]:
    """obj = E_R · sqrt(N) / (1 + |DD|·5)."""
    n = len(trades)
    if n < MIN_TRADES:
        return -999.0, {"trades": n, "expectancy_R": 0.0, "max_dd": 0.0, "win_rate": 0.0}
    trades = sorted(trades, key=lambda t: t.t_entry)
    r = np.array([t.r for t in trades], dtype=float)
    E_R = float(r.mean())
    eq = EQUITY0 * (1.0 + 0.01 * np.cumsum(r))
    peak = np.maximum.accumulate(eq)
    dd = float(((eq - peak) / peak).min())
    wr = float((r > 0).mean())
    obj = E_R * math.sqrt(n) / (1.0 + abs(dd) * 5.0)
    return obj, {"trades": n, "expectancy_R": round(E_R, 4),
                 "max_dd": round(dd, 4), "win_rate": round(wr, 4)}


def eval_combo(overrides: dict, win_start: pd.Timestamp, win_end: pd.Timestamp,
               assets: list) -> tuple[float, dict]:
    pooled = []
    for s in assets:
        if s in _DATA:
            pooled += run_window(_DATA[s], s, overrides, win_start, win_end)
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
    print(f"[WFO-FX] grid='{grid_name}' -> {len(combos)} combos/fold · {len(assets)} activos · {len(FOLDS)} folds")
    print(f"[WFO-FX] holdout intocable desde {HOLDOUT_START.date()} (excluido de todos los folds)")

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

        scored.sort(key=lambda x: x[2], reverse=True)
        best_id, best_ov, best_is_obj, best_is_m = scored[0]

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
        print(f"[WFO-FX] {fold['name']}: IS obj={best_is_obj:.4f} (N={best_is_m['trades']}, "
              f"E_R={best_is_m['expectancy_R']}) | OOS obj={oos_obj:.4f} "
              f"(N={oos_m['trades']}, E_R={oos_m['expectancy_R']}) | best={best_ov} | {fold_res['elapsed_s']}s")

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
    print(f"\n[WFO-FX] WFE = {wfe_str} -> {verdict}")
    print(f"[WFO-FX] mean IS obj={mean_is:.4f} | mean OOS obj={mean_oos:.4f}")
    print(f"[WFO-FX] config congelada: {results['config_congelada']}")
    return results


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--smoke", action="store_true")
    ap.add_argument("--time", action="store_true")
    ap.add_argument("--grid", choices=["coarse", "full"], default="coarse")
    ap.add_argument("--jobs", type=int, default=1)
    args = ap.parse_args()

    if args.time:
        _init_worker(ASSETS)
        t0 = time.time()
        obj, m = eval_combo({}, _ts(FOLDS[0]["is"][0]), _ts(FOLDS[0]["is"][1]), ASSETS)
        dt = time.time() - t0
        print(f"[time] 1 combo (4 activos FX) sobre IS de F1 (6 años): {dt:.1f}s")
        print(f"[time] obj={obj:.4f} {m}")
        full = 729 * len(FOLDS)
        print(f"[time] estimado grid full ({full} evals): {dt*full/60:.0f} min a 1 job; "
              f"{dt*full/60/8:.0f} min a 8 jobs")
        return

    if args.smoke:
        _init_worker(ASSETS[:1])  # solo primer activo
        first_asset = ASSETS[0]
        if first_asset not in _DATA:
            print(f"[smoke] {first_asset.lower()}_m5.csv no encontrado. Descargue primero.")
            return
        trades = run_window(_DATA[first_asset], first_asset, {},
                            _ts(FOLDS[0]["is"][0]), _ts(FOLDS[0]["is"][1]))
        obj, m = objective(trades)
        print(f"[smoke] {first_asset} IS F1: {len(trades)} trades, obj={obj:.4f}, {m}")
        print("[smoke] OK — plumbing funciona" if trades else "[smoke] 0 trades (revisar ventana)")
        return

    assets = [s for s in ASSETS if os.path.exists(f"{s.lower()}_m5.csv")]
    if not assets:
        print("[error] No hay CSVs forex. Ejecute primero download_forex.py")
        return
    res = run_wfo(args.grid, args.jobs, assets)
    os.makedirs("results", exist_ok=True)
    with open("results/wfo_results_forex.json", "w", encoding="utf-8") as f:
        json.dump(res, f, indent=2, ensure_ascii=False)
    print(f"\n[OK] resultados -> results/wfo_results_forex.json")


if __name__ == "__main__":
    main()

# -*- coding: utf-8 -*-
"""
SATAR-1 — Fase 5 §1: Walk-Forward Optimization (WFO) anclado-rodante.

Optimiza los 6 parámetros PERMITIDOS (FASE-3/FASE-5) sobre el POOL combinado de
los 5 activos cripto, con particiones estrictas IS/OOS y un HOLDOUT final que
este script NUNCA toca (se abre una sola vez en la Fase E).

Parámetros optimizables (los únicos permitidos — anti data-snooping):
  P09 zone_w_atr · P11 er_clean · P15 er_arrive · P17 decel_max · P21 chase_atr · P22 armed_window

Diseño:
  - Región WFO = todo menos el 15% final (holdout). Holdout = [HOLDOUT_START, fin].
  - Folds anclados-rodantes: IS ancla en el inicio y crece; OOS = 1 año siguiente; avance 1 año.
  - Objetivo (FASE-5 §1): obj = E_R · sqrt(N) / (1 + |DD|·5).  NUNCA retorno bruto.
  - WFE = media(OOS_obj) / media(IS_obj).  >=0.5 aceptable, <0.4 sobreoptimización.
  - Anti look-ahead: cada ventana se corre con WARMUP_DAYS de historia previa SOLO para
    calentar indicadores; se cuentan únicamente los trades con entrada dentro de la ventana.
    El motor es causal (velas cerradas), así que truncar el futuro no altera el pasado.

Uso:
  python satar_wfo.py --smoke               # plumbing rápido (grid 1 valor, 1 fold, 1 activo)
  python satar_wfo.py --time                # cronometra 1 combo sobre 1 ventana IS
  python satar_wfo.py --grid coarse --jobs 8   # WFO real (grid reducido, multiproceso)
  python satar_wfo.py --grid full --jobs 8     # WFO real (3^6 = 729 combos/fold)
"""
from __future__ import annotations
import argparse, itertools, json, math, os, time
import numpy as np
import pandas as pd

from satar_backtest import Params, Engine

# ---------------------------------------------------------------------------
ASSETS = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "XRPUSDT", "BNBUSDT"]
WARMUP_DAYS = 400          # cubre zone_lookback(250 D1) + swings + EMA/ADX warm-up
EQUITY0 = 10_000.0
MIN_TRADES = 5             # piso duro: menos trades ⇒ objetivo inválido

# Frontera del holdout (15% final ≈ último año). Región WFO = antes de esto.
HOLDOUT_START = pd.Timestamp("2025-07-01", tz="UTC")

# Folds anclados-rodantes dentro de la región WFO (2020-01 .. 2025-07)
FOLDS = [
    {"name": "F1", "is": ("2020-01-01", "2023-01-01"), "oos": ("2023-01-01", "2024-01-01")},
    {"name": "F2", "is": ("2020-01-01", "2024-01-01"), "oos": ("2024-01-01", "2025-01-01")},
    {"name": "F3", "is": ("2020-01-01", "2025-01-01"), "oos": ("2025-01-01", "2025-07-01")},
]

# Rejilla de los 6 parámetros (valores alrededor del default de la Fase 2, ±25%)
GRID_FULL = {
    "zone_w_atr":   [0.375, 0.5, 0.625],   # P09
    "er_clean":     [0.22, 0.30, 0.38],    # P11
    "er_arrive":    [0.26, 0.35, 0.44],    # P15
    "decel_max":    [0.45, 0.60, 0.75],    # P17
    "chase_atr":    [0.375, 0.5, 0.625],   # P21
    "armed_window": [8, 12, 16],           # P22
}
# Rejilla reducida: 3 valores en los 3 parámetros que el embudo (FASE-4-multiactivo §4)
# señaló como dominantes en la ENTRADA; los otros 3 fijos en su default.
GRID_COARSE = {
    "er_clean":     [0.22, 0.30, 0.38],    # P11 (G1)
    "er_arrive":    [0.26, 0.35, 0.44],    # P15 (G3)
    "decel_max":    [0.45, 0.60, 0.75],    # P17 (G4)
}

# cache global por proceso worker
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
    """Carga los datasets una sola vez por proceso worker."""
    global _DATA
    _DATA = load_assets(assets)


def run_window(df: pd.DataFrame, params: Params, win_start: pd.Timestamp,
               win_end: pd.Timestamp, symbol: str) -> list:
    """Corre el motor con warm-up previo y devuelve SOLO los trades cuya entrada
    cae dentro de [win_start, win_end). Causal ⇒ sin look-ahead.

    IMPORTANTE: df.loc[lo:win_end] en pandas INCLUYE el extremo win_end (a
    diferencia de slicing normal de Python). Para folds cuyo win_end coincide
    con HOLDOUT_START (p.ej. OOS de F3), eso filtraría una vela que técnicamente
    pertenece al holdout hacia el cálculo de indicadores. Se usa máscara estricta
    [lo, win_end) para que el holdout jamás se lea, ni siquiera para warm-up."""
    lo = win_start - pd.Timedelta(days=WARMUP_DAYS)
    mask = (df.index >= lo) & (df.index < win_end)
    sub = df.loc[mask]
    if len(sub) < 5000:                      # ventana sin datos suficientes
        return []
    eng = Engine(sub, params, symbol=symbol, equity0=EQUITY0)
    eng.run()
    ws, we = int(win_start.timestamp()), int(win_end.timestamp())
    return [t for t in eng.trades if ws <= t.t_entry < we]


def objective(trades: list) -> tuple[float, dict]:
    """obj = E_R · sqrt(N) / (1 + |DD|·5). Devuelve (obj, métricas).

    Los trades se ordenan por t_entry antes del cumsum: eval_combo() concatena
    los trades activo por activo (todo BTC, luego todo ETH, ...), y el max
    drawdown de una curva de equity es path-dependent — sin este orden cronológico
    las rachas perdedoras simultáneas entre activos correlacionados (cripto) se
    dispersan artificialmente y el DD queda subestimado, corrompiendo el único
    término de riesgo del objetivo."""
    n = len(trades)
    if n < MIN_TRADES:
        return -999.0, {"trades": n, "expectancy_R": 0.0, "max_dd": 0.0, "win_rate": 0.0}
    trades = sorted(trades, key=lambda t: t.t_entry)
    r = np.array([t.r for t in trades], dtype=float)
    E_R = float(r.mean())
    # Equity COMPUESTO (cumprod), no aditivo -- la version aditiva (cumsum)
    # puede producir equity negativo y drawdowns >100% (bug encontrado en la
    # auditoria de HYDRA, ver docs/HYDRA-resultados-veredicto.md). No se
    # manifesto visiblemente aqui (SATAR-1 tiene mejor expectancy que HYDRA)
    # pero la formula correcta es esta independientemente del resultado.
    eq = EQUITY0 * np.cumprod(1.0 + np.clip(0.01 * r, -0.99, None))
    peak = np.maximum.accumulate(eq)
    dd = float(((eq - peak) / peak).min())
    wr = float((r > 0).mean())
    obj = E_R * math.sqrt(n) / (1.0 + abs(dd) * 5.0)
    return obj, {"trades": n, "expectancy_R": round(E_R, 4),
                 "max_dd": round(dd, 4), "win_rate": round(wr, 4)}


def eval_combo(overrides: dict, win_start: pd.Timestamp, win_end: pd.Timestamp,
               assets: list) -> tuple[float, dict]:
    """Evalúa un combo de parámetros sobre una ventana, POOL de todos los activos."""
    p = Params(**overrides)
    pooled = []
    for s in assets:
        if s in _DATA:
            pooled += run_window(_DATA[s], p, win_start, win_end, symbol=s)
    return objective(pooled)


def _ts(s) -> pd.Timestamp:
    """Timestamp UTC-aware (los datasets tienen índice tz-aware UTC)."""
    t = pd.Timestamp(s)
    return t.tz_localize("UTC") if t.tzinfo is None else t.tz_convert("UTC")


def _task(args):
    """Worker: evalúa un combo sobre la ventana IS de un fold."""
    combo_id, overrides, is_start, is_end, assets = args
    obj, m = eval_combo(overrides, _ts(is_start), _ts(is_end), assets)
    return combo_id, overrides, obj, m


# ---------------------------------------------------------------------------
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
        # sanidad: OOS jamás entra en holdout
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
        _init_worker(assets)  # asegura cache en el proceso principal
        oos_obj, oos_m = eval_combo(best_ov, _ts(oos_s), _ts(oos_e), assets)

        is_objs.append(best_is_obj)
        oos_objs.append(oos_obj)

        # top-5 para mapa de estabilidad (meseta vs pico aislado)
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

    # WFE — el ratio SOLO es interpretable cuando la config es rentable IS y OOS.
    # mean_oos/mean_is con ambos negativos da un ratio POSITIVO engañoso (dos
    # negativos entre sí), y cuanto peor degrada OOS, MAYOR sale el WFE — el
    # caso exacto que este gate debe rechazar. Se evalúa primero rentabilidad,
    # el WFE numérico solo se usa como umbral de calidad cuando ambos son >0.
    mean_is = float(np.mean(is_objs)) if is_objs else 0.0
    mean_oos = float(np.mean(oos_objs)) if oos_objs else 0.0
    wfe = mean_oos / mean_is if mean_is > 0 else None
    results["mean_is_obj"] = round(mean_is, 4)
    results["mean_oos_obj"] = round(mean_oos, 4)
    results["wfe"] = round(wfe, 4) if wfe is not None else None

    if mean_is <= 0:
        verdict = "NO RENTABLE IN-SAMPLE (mean_is<=0) — WFE no interpretable; la mejor config IS ya pierde dinero, ni siquiera aplica evaluar degradación OOS"
    elif mean_oos <= 0:
        verdict = f"NO RENTABLE OOS (mean_oos={mean_oos:.4f}<=0) — la config optimizada IS pierde dinero fuera de muestra, independientemente del WFE numérico"
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

    # combo recomendado = el más frecuente / el del último fold (más historia IS)
    results["config_congelada"] = results["folds"][-1]["best_overrides"]

    wfe_str = f"{wfe:.4f}" if wfe is not None else "N/A"
    print(f"\n[WFO] WFE = {wfe_str} -> {verdict}")
    print(f"[WFO] mean IS obj={mean_is:.4f} | mean OOS obj={mean_oos:.4f}")
    print(f"[WFO] config congelada (para holdout/Fase E): {results['config_congelada']}")
    return results


# ---------------------------------------------------------------------------
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--smoke", action="store_true", help="plumbing rápido")
    ap.add_argument("--time", action="store_true", help="cronometra 1 combo sobre IS de F1")
    ap.add_argument("--grid", choices=["coarse", "full"], default="coarse")
    ap.add_argument("--jobs", type=int, default=1)
    args = ap.parse_args()

    if args.time:
        _init_worker(ASSETS)
        p = Params()  # defaults
        t0 = time.time()
        obj, m = eval_combo({}, _ts(FOLDS[0]["is"][0]), _ts(FOLDS[0]["is"][1]), ASSETS)
        dt = time.time() - t0
        print(f"[time] 1 combo (5 activos) sobre IS de F1 (3 años): {dt:.1f}s")
        print(f"[time] obj={obj:.4f} {m}")
        full = 729 * len(FOLDS)
        print(f"[time] estimado grid full ({full} evals): {dt*full/60:.0f} min a 1 job; "
              f"{dt*full/60/8:.0f} min a 8 jobs")
        return

    if args.smoke:
        _init_worker(["BTCUSDT"])
        p = Params()
        trades = run_window(_DATA["BTCUSDT"], p, _ts(FOLDS[0]["is"][0]),
                            _ts(FOLDS[0]["is"][1]), "BTCUSDT")
        obj, m = objective(trades)
        print(f"[smoke] BTC IS F1: {len(trades)} trades, obj={obj:.4f}, {m}")
        print("[smoke] OK — plumbing funciona" if trades else "[smoke] 0 trades (revisar ventana)")
        return

    assets = [s for s in ASSETS if os.path.exists(f"{s.lower()}_m5.csv")]
    res = run_wfo(args.grid, args.jobs, assets)
    os.makedirs("results", exist_ok=True)
    with open("results/wfo_results.json", "w", encoding="utf-8") as f:
        json.dump(res, f, indent=2, ensure_ascii=False)
    print("\n[OK] resultados -> results/wfo_results.json")


if __name__ == "__main__":
    main()

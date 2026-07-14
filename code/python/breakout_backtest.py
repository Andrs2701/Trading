# -*- coding: utf-8 -*-
"""
BREAKOUT-ATR — Motor de backtesting event-driven para la estrategia de
Momentum de Ruptura de Rango con Expansión de Volatilidad (docs/BREAKOUT-formalizacion.md).

Hipótesis: las criptomonedas exhiben impulsos direccionales muy fuertes (fat tails)
debido a liquidaciones en cascada y FOMO. Operar la ruptura con volumen y rango anómalos
y dejar correr con un trailing EMA permite capturar estos impulsos de alta asimetría.

Reutiliza la infraestructura auditada de SATAR-1/HYDRA/SWEEP: fricciones,
position sizing, trailing EMA H1, y mapeo causal sin look-ahead.
"""
from __future__ import annotations
import argparse, json, math, os, sys
from dataclasses import dataclass, asdict
import numpy as np
import pandas as pd

from satar_backtest import _sec, resample, synthetic_m5, ema, atr, Trade


# ----------------------------------------------------------------------------
# Parámetros (docs/BREAKOUT-formalizacion.md §3)
# ----------------------------------------------------------------------------
@dataclass
class BreakoutParams:
    # --- No optimizables (identidad estructural) ---
    lookback_hours: int = 24           # ventana para definir el rango en H1
    vol_ma_window_hours: int = 20      # ventana H1 para volumen promedio
    ema_trail_n: int = 50              # EMA de trailing (H1)
    atr_n: int = 14                    # ATR para stop y filtros
    hurst_window_days: int = 100       # ventana Hurst (D1)
    hurst_filter: float = 0.52         # Hurst mínimo para permitir operar
    stop_min_atr: float = 0.15
    stop_max_atr: float = 3.0
    risk_pct: float = 0.01
    leverage_cap: float = 5.0
    fee_pct: float = 0.00055
    spread_pct: float = 0.0002
    slip_pct: float = 0.0002
    # --- Optimizables (WFO, Fase B4) ---
    range_expansion_mult: float = 1.2  # multiplicador de ATR H1 para el cuerpo de la ruptura
    vol_spike_mult: float = 1.5        # multiplicador de volumen H1 para confirmar
    stop_atr_mult: float = 1.5         # SL inicial en unidades de ATR H1
    trail_buf_atr: float = 1.0         # buffer del trailing stop (H1 ATR)


# ----------------------------------------------------------------------------
# Indicadores auxiliares
# ----------------------------------------------------------------------------
def vol_ma(vol: np.ndarray, period: int) -> np.ndarray:
    """SMA de volumen (rolling, vectorizado)."""
    s = pd.Series(vol)
    return s.rolling(period, min_periods=period).mean().to_numpy()


def rolling_range(df: pd.DataFrame, lookback: int):
    """Calcula el range_high y range_low de las últimas `lookback` velas H1,
    EXCLUYENDO la vela actual (shift 1) para evitar look-ahead."""
    high_prev = df["high"].shift(1)
    low_prev = df["low"].shift(1)
    range_high = high_prev.rolling(lookback, min_periods=lookback).max().to_numpy()
    range_low = low_prev.rolling(lookback, min_periods=lookback).min().to_numpy()
    return range_high, range_low


def hurst_rs(c: np.ndarray, window: int = 100) -> np.ndarray:
    """Hurst exponent via Rescaled Range (R/S) sobre cierres diarios (D1)."""
    n = len(c)
    out = np.full(n, np.nan, dtype=float)
    if n < window:
        return out
    log_c = np.log(np.maximum(c, 1e-10))
    for i in range(window, n):
        seg = log_c[i - window:i]
        ret = np.diff(seg)
        m = ret.mean()
        dev = np.cumsum(ret - m)
        R = dev.max() - dev.min()
        S = ret.std(ddof=0)
        if S > 1e-12 and R > 0:
            out[i] = math.log(R / S) / math.log(window)
        else:
            out[i] = 0.5  # default a random walk
    return out


# ----------------------------------------------------------------------------
# Contenedores de Temporalidad
# ----------------------------------------------------------------------------
class TFH:
    """Contenedor de indicadores para H1: OHLCV + EMA trailing + ATR + Rango + VolMA."""
    def __init__(self, df: pd.DataFrame, p: BreakoutParams):
        self.t = _sec(df.index)
        self.o = df["open"].to_numpy(float)
        self.h = df["high"].to_numpy(float)
        self.l = df["low"].to_numpy(float)
        self.c = df["close"].to_numpy(float)
        self.v = df["volume"].to_numpy(float)
        self.ema = ema(self.c, p.ema_trail_n)
        self.atr = atr(self.h, self.l, self.c, p.atr_n)
        self.range_high, self.range_low = rolling_range(df, p.lookback_hours)
        self.vol_ma = vol_ma(self.v, p.vol_ma_window_hours)
        self.n = len(self.c)


class TFG:
    """Contenedor de indicadores para D1: Hurst."""
    def __init__(self, df: pd.DataFrame, p: BreakoutParams):
        self.c = df["close"].to_numpy(float)
        self.hurst = hurst_rs(self.c, p.hurst_window_days)
        self.n = len(self.c)


# ----------------------------------------------------------------------------
# Motor principal
# ----------------------------------------------------------------------------
class BreakoutEngine:
    def __init__(self, m5: pd.DataFrame, p: BreakoutParams, symbol: str = "SYM",
                 equity0: float = 10_000.0, funnel: bool = False):
        self.p, self.symbol = p, symbol
        self.M = m5
        self.M_t = _sec(m5.index)
        self.M_o = m5["open"].to_numpy(float)
        self.M_h = m5["high"].to_numpy(float)
        self.M_l = m5["low"].to_numpy(float)
        self.M_c = m5["close"].to_numpy(float)
        self.M_atr = atr(self.M_h, self.M_l, self.M_c, p.atr_n)  # ATR local M5 para stop buffers
        self.M_n = len(self.M_c)

        # Resamples H1 y D1
        self.Hdf = resample(m5, "1h")
        self.H = TFH(self.Hdf, p)
        self.Gdf = resample(m5, "1D")
        self.G = TFG(self.Gdf, p)

        # Mapeos temporales sin look-ahead
        m5_close_ts = _sec(m5.index + pd.Timedelta(minutes=5))
        h_close_ts = _sec(self.Hdf.index + pd.Timedelta(hours=1))
        g_close_ts = _sec(self.Gdf.index + pd.Timedelta(days=1))
        self.map_h = np.searchsorted(h_close_ts, m5_close_ts, side="right") - 1
        self.map_g = np.searchsorted(g_close_ts, m5_close_ts, side="right") - 1

        self.pos: Trade | None = None
        self.equity = equity0; self.equity0 = equity0
        self.trades: list[Trade] = []; self.ecurve = []
        self.funnel = funnel

        # Embudo de diagnóstico
        self.counters = {
            "h_eval": 0,
            "breakout_long": 0,
            "breakout_short": 0,
            "hurst_ok": 0,
            "vol_ok": 0,
            "range_exp_ok": 0,
            "sanity_ok": 0,
            "entered": 0
        }

    def _breakout_check(self, g: int, d1_idx: int) -> int:
        """Chequea si la vela H1 `g` que acaba de cerrar representa una ruptura válida.
        Causalidad: se corre al cierre de la vela H1, evaluándose con datos de H1 cerrados."""
        H, G, p = self.H, self.G, self.p
        r_high, r_low = H.range_high[g], H.range_low[g]
        if math.isnan(r_high) or math.isnan(r_low) or math.isnan(H.atr[g]) or math.isnan(H.vol_ma[g]):
            return 0

        # Filtro de Régimen Hurst en D1 (último día cerrado)
        if d1_idx < 0 or d1_idx >= G.n or math.isnan(G.hurst[d1_idx]) or G.hurst[d1_idx] < p.hurst_filter:
            return 0
        if self.funnel:
            self.counters["hurst_ok"] += 1

        # Detección de ruptura alcista/bajista
        is_long = H.c[g] > r_high
        is_short = H.c[g] < r_low

        if not (is_long or is_short):
            return 0
        if self.funnel:
            if is_long: self.counters["breakout_long"] += 1
            if is_short: self.counters["breakout_short"] += 1

        # Confirmación de volumen en H1
        if H.v[g] <= p.vol_spike_mult * H.vol_ma[g]:
            return 0
        if self.funnel:
            self.counters["vol_ok"] += 1

        # Confirmación de expansión de rango (cuerpo de la vela H1 > mult * ATR)
        body = abs(H.c[g] - H.o[g])
        if body <= p.range_expansion_mult * H.atr[g]:
            return 0
        if self.funnel:
            self.counters["range_exp_ok"] += 1

        return 1 if is_long else -1

    def run(self) -> dict:
        p = self.p
        warm = max(p.lookback_hours * 12, 500)  # calentamiento inicial
        last_h = -1
        for m in range(warm, self.M_n - 1):
            g = self.map_h[m]
            d1 = self.map_g[m]
            if g < 0 or g >= self.H.n:
                continue

            if self.pos:
                self._manage(m, g, last_h)

            # Trigger: se activa en la primera vela M5 después de cerrar una vela H1
            if g != last_h and last_h >= 0:
                if self.funnel:
                    self.counters["h_eval"] += 1
                if self.pos is None:
                    # Evaluamos si la vela H1 que acaba de cerrar (last_h) cumplió las condiciones
                    d = self._breakout_check(last_h, d1)
                    if d != 0:
                        self._try_enter(m, last_h, d)

            last_h = g
            self.ecurve.append((self.M_t[m], self.equity + self._open_pnl(m)))

        if self.pos:
            self._exit(self.M_n - 1, self.M_c[-1], "eod")
        return self.metrics()

    def _open_pnl(self, m):
        if not self.pos:
            return 0.0
        return (self.M_c[m] - self.pos.entry) * self.pos.direction * self.pos.qty

    def _try_enter(self, m: int, g: int, d: int):
        p, M_o, M_atr = self.p, self.M_o, self.M_atr
        if m + 1 >= self.M_n:
            return
        raw = M_o[m + 1]  # entramos a la apertura de la vela M5 siguiente
        entry = raw * (1 + d * (p.spread_pct / 2 + p.slip_pct))
        
        # Stop loss inicial: a una distancia fija de ATR en H1
        dist = p.stop_atr_mult * self.H.atr[g]
        if math.isnan(dist) or dist < p.stop_min_atr * self.H.atr[g] or dist > p.stop_max_atr * self.H.atr[g]:
            return
        if self.funnel:
            self.counters["sanity_ok"] += 1

        sl0 = (entry - dist) if d > 0 else (entry + dist)
        tp = entry + d * dist * 4.0   # TP holgado (4R inicial), pero la salida real se maneja por trailing

        qty = (p.risk_pct * self.equity) / dist
        qty = min(qty, p.leverage_cap * self.equity / entry)
        fee = entry * qty * p.fee_pct

        self.pos = Trade(self.symbol, d, self.M_t[m + 1], entry, sl0, tp, qty, sl_init=sl0)
        self.pos.pnl -= fee
        if self.funnel:
            self.counters["entered"] += 1

    def _manage(self, m: int, g: int, last_h: int):
        p, pos = self.p, self.pos
        d = pos.direction
        # Trailing stop restrictivo al cierre de cada vela H1
        if g != last_h and g >= 0 and not math.isnan(self.H.ema[g]):
            # Trailing EMA50 H1 +/- buffer ATR
            cand = self.H.ema[g] + (p.trail_buf_atr * self.H.atr[g] if d < 0 else -p.trail_buf_atr * self.H.atr[g])
            # El trailing stop solo se mueve a favor
            pos.sl0 = min(pos.sl0, cand) if d < 0 else max(pos.sl0, cand)

        h, l, o = self.M_h[m], self.M_l[m], self.M_o[m]
        hit_sl = h >= pos.sl0 if d < 0 else l <= pos.sl0
        hit_tp = l <= pos.tp if d < 0 else h >= pos.tp
        if hit_sl and hit_tp:
            hit_tp = False  # conservador: stop primero
        if hit_sl:
            px = max(pos.sl0, o) if d < 0 else min(pos.sl0, o)
            self._exit(m, px, "stop")
        elif hit_tp:
            self._exit(m, pos.tp, "tp")

    def _exit(self, m: int, price: float, reason: str):
        p, pos = self.p, self.pos
        px = price * (1 - pos.direction * (p.spread_pct / 2 + p.slip_pct))
        gross = (px - pos.entry) * pos.direction * pos.qty
        fee = px * pos.qty * p.fee_pct
        pos.pnl += gross - fee
        pos.t_exit, pos.exit, pos.reason = int(self.M_t[m]), px, reason
        pos.r = pos.pnl / (p.risk_pct * self.equity) if self.equity > 0 else 0.0
        self.equity += pos.pnl
        self.trades.append(pos)
        self.pos = None

    def metrics(self) -> dict:
        tr = self.trades
        if not tr:
            return {"trades": 0, "nota": "sin operaciones", "counters": self.counters}
        pnl = np.array([t.pnl for t in tr]); win = pnl[pnl > 0]; los = pnl[pnl < 0]
        r = np.array([t.r for t in tr])
        eq = self.equity0 * np.cumprod(1.0 + np.clip(0.01 * r, -0.99, None))
        peak = np.maximum.accumulate(eq); dd = (eq - peak) / peak
        years = max((tr[-1].t_exit - tr[0].t_entry) / 31_557_600, 1e-9)
        out = {
            "trades": len(tr), "win_rate": round(float((r > 0).mean()), 4),
            "profit_factor": round(float(win.sum() / -los.sum()), 3) if len(los) else float("inf"),
            "expectancy_R": round(float(r.mean()), 4),
            "max_drawdown": round(float(dd.min()), 4),
            "trades_por_año": round(len(tr) / years, 1),
        }
        if self.funnel:
            out["counters"] = self.counters
        return out


# ----------------------------------------------------------------------------
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--smoke", action="store_true")
    ap.add_argument("--csv", type=str)
    ap.add_argument("--funnel", action="store_true")
    args = ap.parse_args()
    if args.smoke:
        df = synthetic_m5(days=400)
        print(f"[smoke] {len(df)} velas M5 sintéticas")
    elif args.csv:
        df = pd.read_csv(args.csv, parse_dates=["timestamp"], index_col="timestamp")
        if df.index.tz is None:
            df.index = df.index.tz_localize("UTC")
    else:
        ap.print_help(); sys.exit(1)
    p = BreakoutParams()
    eng = BreakoutEngine(df, p, funnel=args.funnel)
    res = eng.run()
    print(json.dumps(res, indent=2, ensure_ascii=False))
    if eng.trades:
        out = pd.DataFrame([asdict(t) for t in eng.trades])
        out.to_csv("trades_breakout_out.csv", index=False)
        print(f"[ok] {len(eng.trades)} trades -> trades_breakout_out.csv")


if __name__ == "__main__":
    main()

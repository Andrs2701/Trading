# -*- coding: utf-8 -*-
"""
SWEEP — Motor de backtesting event-driven para la estrategia de liquidity
sweep / stop hunt (docs/SWEEP-formalizacion.md).

Hipótesis: en perpetuos cripto apalancados, el precio barre zonas densas de
liquidez (stops) por encima/debajo de la estructura semanal (H1, 168 velas)
antes de revertir. Se opera la reversión, no la ruptura.

Reutiliza infraestructura auditada de SATAR-1/HYDRA: friccciones, position
sizing, trailing EMA H1, mapeo causal M5->H1 (satar_backtest.py).

Uso:
  python sweep_backtest.py --smoke                     (datos sintéticos)
  python sweep_backtest.py --csv btcusdt_m5.csv         (backtest real)
  python sweep_backtest.py --csv btcusdt_m5.csv --funnel (+ diagnóstico de embudo)
"""
from __future__ import annotations
import argparse, json, math, sys
from dataclasses import dataclass, asdict
import numpy as np
import pandas as pd

from satar_backtest import _sec, resample, synthetic_m5, ema, atr, Trade


# ----------------------------------------------------------------------------
# Parámetros (docs/SWEEP-formalizacion.md §8)
# ----------------------------------------------------------------------------
@dataclass
class SweepParams:
    # --- No optimizables (identidad estructural) ---
    structure_lookback_h1: int = 168   # 1 semana de velas H1
    vol_ma_window: int = 20            # ventana M5 para volumen promedio
    ema_trail_n: int = 50              # EMA de trailing (H1)
    atr_n: int = 14
    stop_min_atr: float = 0.15
    stop_max_atr: float = 3.0
    risk_pct: float = 0.01
    leverage_cap: float = 5.0
    fee_pct: float = 0.00055
    spread_pct: float = 0.0002
    slip_pct: float = 0.0002
    # --- Optimizables (WFO, Fase S4) ---
    vol_spike_mult: float = 1.5
    buf_atr: float = 0.15              # buffer del SL sobre el wick (M5 ATR)
    rr_min: float = 3.0                # R:R mínimo para aceptar el trade
    trail_buf_atr: float = 0.10        # buffer del trailing (H1 ATR)


# ----------------------------------------------------------------------------
# Indicadores auxiliares
# ----------------------------------------------------------------------------
def vol_ma(vol: np.ndarray, period: int) -> np.ndarray:
    """SMA de volumen (rolling, vectorizado)."""
    s = pd.Series(vol)
    return s.rolling(period, min_periods=period).mean().to_numpy()


def rolling_structure(h1: pd.DataFrame, lookback: int):
    """resistance/support: max(H1.high)/min(H1.low) rodante, INCLUYE la vela
    actual (se usa contra la última vela H1 CERRADA en el mapeo causal, así
    que no hay look-ahead: en el momento en que una vela M5 consulta esto, la
    vela H1 más reciente incluida ya cerró)."""
    resistance = h1["high"].rolling(lookback, min_periods=lookback).max().to_numpy()
    support = h1["low"].rolling(lookback, min_periods=lookback).min().to_numpy()
    return resistance, support


class TFH:
    """Contenedor de indicadores para H1: OHLC + EMA trailing + ATR + estructura."""
    def __init__(self, df: pd.DataFrame, p: SweepParams):
        self.t = _sec(df.index)
        self.o = df["open"].to_numpy(float); self.h = df["high"].to_numpy(float)
        self.l = df["low"].to_numpy(float); self.c = df["close"].to_numpy(float)
        self.ema = ema(self.c, p.ema_trail_n)
        self.atr = atr(self.h, self.l, self.c, p.atr_n)
        self.resistance, self.support = rolling_structure(df, p.structure_lookback_h1)
        self.n = len(self.c)


class TFM:
    """Contenedor de indicadores para M5: OHLCV + ATR + MA de volumen."""
    def __init__(self, df: pd.DataFrame, p: SweepParams):
        self.t = _sec(df.index)
        self.o = df["open"].to_numpy(float); self.h = df["high"].to_numpy(float)
        self.l = df["low"].to_numpy(float); self.c = df["close"].to_numpy(float)
        self.v = df["volume"].to_numpy(float)
        self.atr = atr(self.h, self.l, self.c, p.atr_n)
        self.vol_ma = vol_ma(self.v, p.vol_ma_window)
        self.n = len(self.c)


# ----------------------------------------------------------------------------
# Motor principal
# ----------------------------------------------------------------------------
class SweepEngine:
    def __init__(self, m5: pd.DataFrame, p: SweepParams, symbol: str = "SYM",
                 equity0: float = 10_000.0, funnel: bool = False):
        self.p, self.symbol = p, symbol
        self.M = TFM(m5, p)
        self.Hdf = resample(m5, "1h")
        self.H = TFH(self.Hdf, p)
        m5_close_ts = _sec(m5.index + pd.Timedelta(minutes=5))
        h_close_ts = _sec(self.Hdf.index + pd.Timedelta(hours=1))
        self.map_h = np.searchsorted(h_close_ts, m5_close_ts, side="right") - 1
        self.pos: Trade | None = None
        self.equity = equity0; self.equity0 = equity0
        self.trades: list[Trade] = []; self.ecurve = []
        self.funnel = funnel
        self.counters = {"m_eval": 0, "sweep_short": 0, "sweep_long": 0,
                          "vol_ok": 0, "sanity_ok": 0, "rr_ok": 0, "entered": 0}

    def _sweep_check(self, m: int, g: int) -> int:
        """Devuelve -1 (short), +1 (long) o 0 (sin señal) para la vela M5 m,
        usando la estructura de la última vela H1 CERRADA (g)."""
        H, M, p = self.H, self.M, self.p
        res, sup = H.resistance[g], H.support[g]
        if math.isnan(res) or math.isnan(sup):
            return 0
        if self.funnel:
            self.counters["m_eval"] += 1
        sweep_short = M.h[m] > res and M.c[m] < res
        sweep_long = M.l[m] < sup and M.c[m] > sup
        if sweep_short and sweep_long:
            return 0  # ambiguo (raro, ambas condiciones a la vez) -> descartar
        if sweep_short:
            if self.funnel:
                self.counters["sweep_short"] += 1
            if not (M.vol_ma[m] > 0 and M.v[m] > p.vol_spike_mult * M.vol_ma[m]):
                return 0
            if self.funnel:
                self.counters["vol_ok"] += 1
            return -1
        if sweep_long:
            if self.funnel:
                self.counters["sweep_long"] += 1
            if not (M.vol_ma[m] > 0 and M.v[m] > p.vol_spike_mult * M.vol_ma[m]):
                return 0
            if self.funnel:
                self.counters["vol_ok"] += 1
            return 1
        return 0

    def run(self) -> dict:
        p = self.p
        warm = max(p.structure_lookback_h1 * 12, p.vol_ma_window, 300)  # ~horas H1 en velas M5
        last_h = -1
        for m in range(warm, self.M.n - 1):
            g = self.map_h[m]
            if g < 0 or g >= self.H.n:
                continue
            if self.pos:
                self._manage(m, g, last_h)
            last_h = g
            if self.pos is None:
                d = self._sweep_check(m, g)
                if d != 0:
                    self._try_enter(m, g, d)
            self.ecurve.append((self.M.t[m], self.equity + self._open_pnl(m)))
        if self.pos:
            self._exit(self.M.n - 1, self.M.c[-1], "eod")
        return self.metrics()

    def _open_pnl(self, m):
        if not self.pos:
            return 0.0
        return (self.M.c[m] - self.pos.entry) * self.pos.direction * self.pos.qty

    def _try_enter(self, m: int, g: int, d: int):
        p, M, H = self.p, self.M, self.H
        if m + 1 >= M.n:
            return
        raw = M.o[m + 1]
        entry = raw * (1 + d * (p.spread_pct / 2 + p.slip_pct))
        buf = p.buf_atr * M.atr[m]
        if math.isnan(buf):
            return
        sl0 = (M.h[m] + buf) if d < 0 else (M.l[m] - buf)
        dist = abs(sl0 - entry)
        if math.isnan(M.atr[m]) or dist < p.stop_min_atr * M.atr[m] or dist > p.stop_max_atr * M.atr[m]:
            return
        if self.funnel:
            self.counters["sanity_ok"] += 1
        tp = H.support[g] if d < 0 else H.resistance[g]
        rr = abs(entry - tp) / dist if dist > 0 else 0.0
        if rr < p.rr_min:
            return
        if self.funnel:
            self.counters["rr_ok"] += 1
        qty = (p.risk_pct * self.equity) / dist
        qty = min(qty, p.leverage_cap * self.equity / entry)
        fee = entry * qty * p.fee_pct
        self.pos = Trade(self.symbol, d, self.M.t[m + 1], entry, sl0, tp, qty, sl_init=sl0)
        self.pos.pnl -= fee
        if self.funnel:
            self.counters["entered"] += 1

    def _manage(self, m: int, g: int, last_h: int):
        p, pos = self.p, self.pos
        d = pos.direction
        if g != last_h and g >= 0 and not math.isnan(self.H.ema[g]):
            cand = self.H.ema[g] + (p.trail_buf_atr * self.H.atr[g] if d < 0 else -p.trail_buf_atr * self.H.atr[g])
            pos.sl0 = min(pos.sl0, cand) if d < 0 else max(pos.sl0, cand)
        h, l, o = self.M.h[m], self.M.l[m], self.M.o[m]
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
        pos.t_exit, pos.exit, pos.reason = int(self.M.t[m]), px, reason
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
    p = SweepParams()
    eng = SweepEngine(df, p, funnel=args.funnel)
    res = eng.run()
    print(json.dumps(res, indent=2, ensure_ascii=False))
    if eng.trades:
        out = pd.DataFrame([asdict(t) for t in eng.trades])
        out.to_csv("trades_sweep_out.csv", index=False)
        print(f"[ok] {len(eng.trades)} trades -> trades_sweep_out.csv")


if __name__ == "__main__":
    main()

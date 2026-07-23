# -*- coding: utf-8 -*-
"""
Hipótesis 6 — Motor de backtest de Pairs Trading / Reversión a la Media.

Reglas exactas: docs/PAIRS-formalizacion.md. Opera el spread log(P_A) -
beta_t*log(P_B), con beta_t (hedge ratio) recalculado en cada barra vía
regresión rodante (rolling cov/var — solo datos pasados, sin look-ahead).
Entra cuando |z-score del spread| > z_entry; sale por reversión (z_exit),
por invalidación/stop (z_stop), o por tiempo máximo en posición.

Sizing: pierna A con notional N, pierna B con notional beta*N (ponderado
por el hedge ratio, no dólar-neutral ingenuo) — así el PnL de la posición
combinada es aproximadamente proporcional al movimiento del spread mismo,
lo que permite dimensionar el riesgo directamente por la distancia
z_entry -> z_stop. Fricciones aplicadas a AMBAS piernas, entrada y salida.
"""
from __future__ import annotations
import argparse, json, math, os
from dataclasses import dataclass, asdict
import numpy as np
import pandas as pd

from satar_backtest import resample


@dataclass
class PairsParams:
    lookback_bars: int = 100
    z_entry: float = 2.0
    z_exit: float = 0.5
    z_stop: float = 4.0
    max_holding_mult: float = 4.0   # max_holding_bars = lookback_bars * este multiplicador (P05, fijo)
    risk_pct: float = 0.01
    fee_pct: float = 0.00055
    spread_pct: float = 0.0002
    slip_pct: float = 0.0002


@dataclass
class PairsTrade:
    pair: str
    direction: int          # +1 = long spread (long A / short B), -1 = short spread
    t_entry: int
    t_exit: int | None = None
    entry_a: float = 0.0
    entry_b: float = 0.0
    exit_a: float = 0.0
    exit_b: float = 0.0
    beta: float = 0.0
    qty_a: float = 0.0
    qty_b: float = 0.0
    z_entry_val: float = 0.0
    z_exit_val: float = 0.0
    pnl: float = 0.0
    r: float = 0.0
    reason: str = ""


def compute_spread_zscore(close_a: pd.Series, close_b: pd.Series, lookback: int):
    """Beta rodante (cov/var, solo pasado), spread, y z-score. Vectorizado."""
    log_a = np.log(close_a)
    log_b = np.log(close_b)
    roll_cov = log_a.rolling(lookback).cov(log_b)
    roll_var_b = log_b.rolling(lookback).var()
    beta = roll_cov / roll_var_b
    spread = log_a - beta * log_b
    roll_mean = spread.rolling(lookback).mean()
    roll_std = spread.rolling(lookback).std()
    z = (spread - roll_mean) / roll_std
    return beta, spread, roll_std, z


class PairsEngine:
    def __init__(self, close_a: pd.Series, close_b: pd.Series, p: PairsParams,
                 pair_name: str, equity0: float = 10_000.0):
        common = close_a.index.intersection(close_b.index)
        self.a = close_a.loc[common].sort_index()
        self.b = close_b.loc[common].sort_index()
        self.t = np.array([int(ts.timestamp()) for ts in self.a.index])
        self.p = p
        self.pair_name = pair_name
        self.equity = equity0
        self.equity0 = equity0
        self.n = len(self.a)

        beta, spread, roll_std, z = compute_spread_zscore(self.a, self.b, p.lookback_bars)
        self.beta = beta.to_numpy()
        self.roll_std = roll_std.to_numpy()
        self.z = z.to_numpy()
        self.a_np = self.a.to_numpy()
        self.b_np = self.b.to_numpy()

        self.pos: PairsTrade | None = None
        self.entry_bar_idx = -1
        self.trades: list[PairsTrade] = []
        self.max_holding_bars = int(p.lookback_bars * p.max_holding_mult)

    def _friction(self, notional: float) -> float:
        return notional * (self.p.fee_pct + self.p.spread_pct / 2 + self.p.slip_pct)

    def _enter(self, i: int, direction: int):
        p = self.p
        beta_i = self.beta[i]
        std_i = self.roll_std[i]
        if math.isnan(beta_i) or math.isnan(std_i) or std_i <= 1e-12:
            return
        adverse_move = abs(p.z_stop - p.z_entry) * std_i
        if adverse_move <= 1e-12:
            return
        risk_usd = p.risk_pct * self.equity
        notional_a = risk_usd / adverse_move
        notional_b = abs(beta_i) * notional_a

        price_a, price_b = self.a_np[i], self.b_np[i]
        qty_a = notional_a / price_a
        qty_b = notional_b / price_b

        fee = self._friction(notional_a) + self._friction(notional_b)

        self.pos = PairsTrade(
            pair=self.pair_name, direction=direction, t_entry=int(self.t[i]),
            entry_a=price_a, entry_b=price_b, beta=beta_i,
            qty_a=qty_a, qty_b=qty_b, z_entry_val=self.z[i],
        )
        self.pos.pnl -= fee
        self.entry_bar_idx = i

    def _exit(self, i: int, reason: str):
        pos = self.pos
        price_a, price_b = self.a_np[i], self.b_np[i]
        # direction=+1 (long spread) -> long A, short B. direction=-1 -> short A, long B.
        dir_a = pos.direction
        dir_b = -pos.direction
        pnl_a = pos.qty_a * (price_a - pos.entry_a) * dir_a
        pnl_b = pos.qty_b * (price_b - pos.entry_b) * dir_b
        fee = self._friction(pos.qty_a * price_a) + self._friction(pos.qty_b * price_b)
        pos.pnl += pnl_a + pnl_b - fee
        pos.t_exit = int(self.t[i])
        pos.exit_a, pos.exit_b = price_a, price_b
        pos.z_exit_val = self.z[i]
        pos.reason = reason
        pos.r = pos.pnl / (self.p.risk_pct * self.equity) if self.equity > 0 else 0.0
        self.equity += pos.pnl
        self.trades.append(pos)
        self.pos = None
        self.entry_bar_idx = -1

    def run(self) -> list[PairsTrade]:
        warm = self.p.lookback_bars + 5
        for i in range(warm, self.n):
            zi = self.z[i]
            if math.isnan(zi):
                continue

            if self.pos is not None:
                held = i - self.entry_bar_idx
                if abs(zi) < self.p.z_exit:
                    self._exit(i, "reversion")
                    continue
                if abs(zi) > self.p.z_stop:
                    self._exit(i, "stop")
                    continue
                if held >= self.max_holding_bars:
                    self._exit(i, "tiempo_max")
                    continue
            else:
                if zi > self.p.z_entry:
                    self._enter(i, direction=-1)   # spread caro -> short spread
                elif zi < -self.p.z_entry:
                    self._enter(i, direction=+1)   # spread barato -> long spread

        if self.pos is not None:
            self._exit(self.n - 1, "eod")
        return self.trades

    def metrics(self) -> dict:
        tr = self.trades
        if not tr:
            return {"trades": 0, "nota": "sin operaciones"}
        r = np.array([t.r for t in tr])
        pnl = np.array([t.pnl for t in tr])
        win = pnl[pnl > 0]; los = pnl[pnl < 0]
        eq = self.equity0 * np.cumprod(1.0 + np.clip(0.01 * r, -0.99, None))
        peak = np.maximum.accumulate(eq)
        dd = (eq - peak) / peak
        return {
            "trades": len(tr),
            "win_rate": round(float((r > 0).mean()), 4),
            "profit_factor": round(float(win.sum() / -los.sum()), 3) if len(los) else float("inf"),
            "expectancy_R": round(float(r.mean()), 4),
            "max_drawdown": round(float(dd.min()), 4),
        }


def load_close(symbol: str, timeframe: str) -> pd.Series:
    fn = f"{symbol.lower()}_m5.csv"
    df = pd.read_csv(fn, parse_dates=["timestamp"], index_col="timestamp")
    if df.index.tz is None:
        df.index = df.index.tz_localize("UTC")
    df = df.sort_index()
    rule = {"H1": "1h", "H4": "4h", "D1": "1D"}[timeframe]
    r = resample(df, rule)
    return r["close"]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pair", required=True, help="p.ej. ETHUSDT-SOLUSDT")
    ap.add_argument("--timeframe", required=True, choices=["H1", "H4", "D1"])
    args = ap.parse_args()

    sym_a, sym_b = args.pair.split("-")
    close_a = load_close(sym_a, args.timeframe)
    close_b = load_close(sym_b, args.timeframe)

    p = PairsParams()
    eng = PairsEngine(close_a, close_b, p, args.pair)
    eng.run()
    res = eng.metrics()
    print(json.dumps(res, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()

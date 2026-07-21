# -*- coding: utf-8 -*-
"""
Script de prueba para evaluar la estrategia BREAKOUT-ATR en temporalidad de 15 Minutos (15m)
sobre SOLUSDT, ETHUSDT y BTCUSDT.
"""
import math, sys, os
import numpy as np
import pandas as pd

from breakout_backtest import BreakoutEngine, BreakoutParams, TFH, TFG, rolling_range, vol_ma, hurst_rs, Trade, _sec, resample, ema, atr

def bollinger_bandwidth(c: np.ndarray, period: int = 20, std_mult: float = 2.0):
    s = pd.Series(c)
    sma = s.rolling(period, min_periods=period).mean()
    std = s.rolling(period, min_periods=period).std(ddof=0)
    upper = sma + std_mult * std
    lower = sma - std_mult * std
    bw = (upper - lower) / (sma + 1e-12)
    return bw.to_numpy()

class BreakoutEngine15M(BreakoutEngine):
    def __init__(self, m5: pd.DataFrame, p: BreakoutParams, symbol: str = "SYM", equity0: float = 10000.0, use_bb_d1: bool = True):
        self.p, self.symbol = p, symbol
        self.M = m5
        self.M_t = _sec(m5.index)
        self.M_o = m5["open"].to_numpy(float)
        self.M_h = m5["high"].to_numpy(float)
        self.M_l = m5["low"].to_numpy(float)
        self.M_c = m5["close"].to_numpy(float)
        self.M_atr = atr(self.M_h, self.M_l, self.M_c, p.atr_n)
        self.M_n = len(self.M_c)

        # Resample M5 -> 15min en vez de 1h
        self.Hdf = resample(m5, "15min")
        self.H = TFH(self.Hdf, p)
        self.Gdf = resample(m5, "1D")
        self.G = TFG(self.Gdf, p)

        # Bollinger D1
        self.g_bb_bw = bollinger_bandwidth(self.G.c, 20)
        s_bw = pd.Series(self.g_bb_bw)
        self.g_bb_pctl = s_bw.rolling(50, min_periods=50).apply(
            lambda x: (x.iloc[-1] - x.min()) / (x.max() - x.min() + 1e-12) if x.max() > x.min() else 0.5,
            raw=False
        ).to_numpy()
        self.use_bb_d1 = use_bb_d1

        # Mapeos temporales sin look-ahead
        m5_close_ts = _sec(m5.index + pd.Timedelta(minutes=5))
        h_close_ts = _sec(self.Hdf.index + pd.Timedelta(minutes=15))
        g_close_ts = _sec(self.Gdf.index + pd.Timedelta(days=1))
        self.map_h = np.searchsorted(h_close_ts, m5_close_ts, side="right") - 1
        self.map_g = np.searchsorted(g_close_ts, m5_close_ts, side="right") - 1

        self.pos: Trade | None = None
        self.equity = equity0; self.equity0 = equity0
        self.trades: list[Trade] = []; self.ecurve = []
        self.funnel = False
        self.counters = {}

    def _breakout_check(self, g: int, d1_idx: int) -> int:
        d = super()._breakout_check(g, d1_idx)
        if d == 0:
            return 0
        if self.use_bb_d1:
            if d1_idx < 1 or d1_idx >= self.G.n or np.isnan(self.g_bb_bw[d1_idx]):
                return 0
            if self.g_bb_bw[d1_idx] <= self.g_bb_bw[d1_idx-1]:
                return 0
            if np.isnan(self.g_bb_pctl[d1_idx]) or self.g_bb_pctl[d1_idx] < 0.20:
                return 0
        return d

def run_15m_backtest():
    symbols = ["SOLUSDT", "ETHUSDT", "BTCUSDT"]
    print("=" * 85)
    print(" BACKTEST EN TEMPORALIDAD DE 15 MINUTOS (15m) VS 1 HORA (1h)")
    print("=" * 85)

    for sym in symbols:
        csv_file = f"{sym.lower()}_m5.csv"
        if not os.path.exists(csv_file):
            continue
        df = pd.read_csv(csv_file, parse_dates=["timestamp"], index_col="timestamp")
        if df.index.tz is None:
            df.index = df.index.tz_localize("UTC")

        # 1. Baseline 1H (referencia)
        p1h = BreakoutParams()
        p1h.vol_spike_mult = 1.8
        p1h.range_expansion_mult = 1.4
        p1h.stop_atr_mult = 1.8
        eng1h = BreakoutEngine(df, p1h, symbol=sym)
        res1h = eng1h.run()

        # 2. Temporalidad 15M (Directa)
        p15m = BreakoutParams()
        p15m.vol_spike_mult = 1.8
        p15m.range_expansion_mult = 1.4
        p15m.stop_atr_mult = 1.8
        eng15m = BreakoutEngine15M(df, p15m, symbol=sym, use_bb_d1=False)
        res15m = eng15m.run()

        # 3. Temporalidad 15M (Con Filtro Bollinger D1)
        eng15m_bb = BreakoutEngine15M(df, p15m, symbol=sym, use_bb_d1=True)
        res15m_bb = eng15m_bb.run()

        print(f"\n--- {sym} ---")
        print(f"1. 1 Hora H1 (Base 1H)              | Trades: {res1h['trades']:4d} | WR: {res1h.get('win_rate',0)*100:5.2f}% | PF: {res1h.get('profit_factor',0):6.3f} | Exp_R: {res1h.get('expectancy_R',0):+7.4f}R | MaxDD: {res1h.get('max_drawdown',0)*100:6.2f}%")
        print(f"2. 15 Minutos 15m (Sin filtro D1)   | Trades: {res15m['trades']:4d} | WR: {res15m.get('win_rate',0)*100:5.2f}% | PF: {res15m.get('profit_factor',0):6.3f} | Exp_R: {res15m.get('expectancy_R',0):+7.4f}R | MaxDD: {res15m.get('max_drawdown',0)*100:6.2f}%")
        print(f"3. 15 Minutos 15m (Con filtro D1 BB)| Trades: {res15m_bb['trades']:4d} | WR: {res15m_bb.get('win_rate',0)*100:5.2f}% | PF: {res15m_bb.get('profit_factor',0):6.3f} | Exp_R: {res15m_bb.get('expectancy_R',0):+7.4f}R | MaxDD: {res15m_bb.get('max_drawdown',0)*100:6.2f}%")

if __name__ == "__main__":
    run_15m_backtest()

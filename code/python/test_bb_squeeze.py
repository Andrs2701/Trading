# -*- coding: utf-8 -*-
"""
Test extendido de Bollinger Band Expansion / Squeeze en H1 y D1
para la estrategia BREAKOUT-ATR sobre los 5 activos del portfolio.
"""
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

class AdvancedBreakoutParams(BreakoutParams):
    use_bb_h1: bool = False
    bb_h1_window: int = 20
    bb_h1_expansion: bool = True     # bw_h1[g] > bw_h1[g-1]

    use_bb_d1: bool = False
    bb_d1_window: int = 20
    bb_d1_expansion: bool = True     # bw_d1[d1] > bw_d1[d1-1]
    bb_d1_min_percentile: float = 0.0 # e.g. 0.20 percentile rank over 50 days

class AdvancedTFH(TFH):
    def __init__(self, df: pd.DataFrame, p: AdvancedBreakoutParams):
        super().__init__(df, p)
        self.bb_bw = bollinger_bandwidth(self.c, p.bb_h1_window)

class AdvancedTFG(TFG):
    def __init__(self, df: pd.DataFrame, p: AdvancedBreakoutParams):
        super().__init__(df, p)
        self.bb_bw = bollinger_bandwidth(self.c, p.bb_d1_window)
        s_bw = pd.Series(self.bb_bw)
        # Percentil rolling de 50 días
        self.bb_bw_pctl = s_bw.rolling(50, min_periods=50).apply(
            lambda x: (x.iloc[-1] - x.min()) / (x.max() - x.min() + 1e-12) if x.max() > x.min() else 0.5,
            raw=False
        ).to_numpy()

class AdvancedBreakoutEngine(BreakoutEngine):
    def __init__(self, m5: pd.DataFrame, p: AdvancedBreakoutParams, symbol: str = "SYM", equity0: float = 10000.0, funnel: bool = False):
        super().__init__(m5, p, symbol=symbol, equity0=equity0, funnel=funnel)
        self.p = p
        self.H = AdvancedTFH(self.Hdf, p)
        self.G = AdvancedTFG(self.Gdf, p)

    def _breakout_check(self, g: int, d1_idx: int) -> int:
        d = super()._breakout_check(g, d1_idx)
        if d == 0:
            return 0
        p, H, G = self.p, self.H, self.G

        if p.use_bb_h1:
            if g < 1 or np.isnan(H.bb_bw[g]):
                return 0
            if p.bb_h1_expansion and H.bb_bw[g] <= H.bb_bw[g-1]:
                return 0

        if p.use_bb_d1:
            if d1_idx < 1 or d1_idx >= G.n or np.isnan(G.bb_bw[d1_idx]):
                return 0
            if p.bb_d1_expansion and G.bb_bw[d1_idx] <= G.bb_bw[d1_idx-1]:
                return 0
            if p.bb_d1_min_percentile > 0 and (np.isnan(G.bb_bw_pctl[d1_idx]) or G.bb_bw_pctl[d1_idx] < p.bb_d1_min_percentile):
                return 0

        return d

def run_advanced_tests():
    symbols = ["SOLUSDT", "ETHUSDT", "BTCUSDT"]
    configs = [
        ("1. Base Baseline", False, False, False, 0.0),
        ("2. H1 BB Expansion", True, True, False, 0.0),
        ("3. D1 BB Expansion", False, False, True, 0.0),
        ("4. H1 + D1 BB Expansion", True, True, True, 0.0),
        ("5. D1 BB Exp + Pctl>20%", False, False, True, 0.20),
    ]

    print("=" * 80)
    print(" EVALUACIÓN DE REGIMEN BOLLINGER SQUEEZE / EXPANSION (H1 & D1)")
    print("=" * 80)

    for sym in symbols:
        csv_file = f"{sym.lower()}_m5.csv"
        try:
            df = pd.read_csv(csv_file, parse_dates=["timestamp"], index_col="timestamp")
            if df.index.tz is None:
                df.index = df.index.tz_localize("UTC")
        except FileNotFoundError:
            print(f"[omitido] {csv_file} no encontrado")
            continue

        print(f"\n--- {sym} ---")
        for name, use_h1, exp_h1, use_d1, pctl_d1 in configs:
            p = AdvancedBreakoutParams()
            p.use_bb_h1 = use_h1
            p.bb_h1_expansion = exp_h1
            p.use_bb_d1 = use_d1
            p.bb_d1_expansion = True
            p.bb_d1_min_percentile = pctl_d1

            eng = AdvancedBreakoutEngine(df, p, symbol=sym)
            res = eng.run()
            print(f"{name:32s} | Trades: {res['trades']:4d} | WR: {res.get('win_rate',0)*100:5.2f}% | PF: {res.get('profit_factor',0):6.3f} | Exp_R: {res.get('expectancy_R',0):+7.4f}R | MaxDD: {res.get('max_drawdown',0)*100:6.2f}%")

if __name__ == "__main__":
    run_advanced_tests()

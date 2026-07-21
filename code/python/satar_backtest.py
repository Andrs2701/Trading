# -*- coding: utf-8 -*-
"""
SATAR-1 — Motor de backtesting event-driven del Pilar C (+ hook Pilar B).
Implementa la máquina de estados de FASE-2 §13 sobre velas M5 con resampling
H1/D1 de velas CERRADAS (cero look-ahead, cero repintado).

Uso:  python satar_backtest.py --smoke          (test con datos sintéticos)
      python satar_backtest.py --csv datos.csv  (CSV M5: timestamp,open,high,low,close,volume)

Los IDs de reglas (R-Cxx) y parámetros (Pxx) refieren a docs/FASE-1 y FASE-2.
"""
from __future__ import annotations
import argparse, json, math, sys
from dataclasses import dataclass, field, asdict
import numpy as np
import pandas as pd


# ----------------------------------------------------------------------------
# Parámetros (FASE-2 §10)
# ----------------------------------------------------------------------------
@dataclass
class Params:
    ema_n: int = 50            # P01 (exponencial, identidad de la estrategia)
    atr_n: int = 14            # P02
    rsi_n: int = 14            # P03
    adx_n: int = 14            # P04
    er_n: int = 20             # P05
    k_frac_i: int = 2          # P06
    k_piv_g: int = 3           # P07
    zone_lookback: int = 250   # P08
    zone_w_atr: float = 0.5    # P09
    zone_min_touches: int = 2  # P10
    er_clean: float = 0.30     # P11 (D-4)
    adx_clean: float = 20.0    # P12 (D-4)
    touch_window: int = 3      # P13
    arrive_n: int = 5          # P14
    er_arrive: float = 0.35    # P15
    rsi_extreme: float = 70.0  # P16 (short; long usa 100-P16)
    decel_max: float = 0.6     # P17 (D-2)
    pin_ratio: float = 2.0     # P18
    dtop_tol_atr: float = 0.25 # P19
    bias_expiry: int = 3       # P20 velas G
    chase_atr: float = 0.5     # P21 (D-5)
    armed_window: int = 12     # P22 velas I (D-5)
    buf_atr: float = 0.1       # P23 (D-1/D-6)
    stop_min_atr: float = 0.15 # P24
    stop_max_atr: float = 3.0  # P25
    tp_lookback: int = 100     # P26
    rr_min: float = 0.5        # P27
    risk_pct: float = 0.01     # P28
    leverage_cap: float = 5.0  # P37 — nocional máx = 5×equity (FASE-6 §5)
    max_dd_day: float = 0.02   # P30
    max_dd_week: float = 0.04  # P31
    max_dd_month: float = 0.06 # P32
    trail_tf: str = "I"        # P36 ∈ {"I","P"} (hallazgo C3, Fase 3)
    # Fricciones (FASE-4 §3) — como fracción del precio
    fee_pct: float = 0.00055   # taker Bybit por lado
    spread_pct: float = 0.0002
    slip_pct: float = 0.0002


# ----------------------------------------------------------------------------
# Indicadores (FASE-2 §1) — sobre arrays de velas cerradas
# ----------------------------------------------------------------------------
def ema(c: np.ndarray, n: int) -> np.ndarray:
    out = np.full_like(c, np.nan, dtype=float)
    if len(c) < n:
        return out
    a = 2.0 / (n + 1)
    out[n - 1] = c[:n].mean()
    for i in range(n, len(c)):
        out[i] = a * c[i] + (1 - a) * out[i - 1]
    return out

def _wilder(x: np.ndarray, n: int) -> np.ndarray:
    out = np.full_like(x, np.nan, dtype=float)
    if len(x) < n:
        return out
    out[n - 1] = x[:n].mean()
    for i in range(n, len(x)):
        out[i] = (out[i - 1] * (n - 1) + x[i]) / n
    return out

def atr(h, l, c, n):
    pc = np.roll(c, 1); pc[0] = c[0]
    tr = np.maximum(h - l, np.maximum(abs(h - pc), abs(l - pc)))
    return _wilder(tr, n)

def rsi(c, n):
    d = np.diff(c, prepend=c[0])
    up = _wilder(np.where(d > 0, d, 0.0), n)
    dn = _wilder(np.where(d < 0, -d, 0.0), n)
    rs = np.divide(up, dn, out=np.full_like(up, np.inf), where=dn != 0)
    return 100 - 100 / (1 + rs)

def adx(h, l, c, n):
    up = np.diff(h, prepend=h[0]); dn = -np.diff(l, prepend=l[0])
    plus = np.where((up > dn) & (up > 0), up, 0.0)
    minus = np.where((dn > up) & (dn > 0), dn, 0.0)
    a = atr(h, l, c, n)
    pdi = 100 * np.divide(_wilder(plus, n), a, out=np.zeros_like(a), where=a > 0)
    mdi = 100 * np.divide(_wilder(minus, n), a, out=np.zeros_like(a), where=a > 0)
    s = pdi + mdi
    dx = 100 * np.divide(abs(pdi - mdi), s, out=np.zeros_like(s), where=s > 0)
    return _wilder(dx, n)

def eff_ratio(c, n):
    out = np.full_like(c, np.nan, dtype=float)
    ac = np.abs(np.diff(c, prepend=c[0]))
    csum = np.cumsum(ac)
    for i in range(n, len(c)):
        den = csum[i] - csum[i - n]
        out[i] = abs(c[i] - c[i - n]) / den if den > 0 else 0.0
    return out


# ----------------------------------------------------------------------------
# Estructura: swings (FASE-2 §2.1) y zonas extremas (§2.2)
# ----------------------------------------------------------------------------
def swings(h: np.ndarray, l: np.ndarray, k: int, upto: int, start: int = 0):
    """Swings CONFIRMADOS con información disponible en la vela `upto` (incluida).
    Un swing en t requiere k velas posteriores ⇒ solo t ≤ upto-k.
    `start` acota la ventana (rendimiento O(N·W)); los consumidores solo usan
    los swings recientes, así que el resultado es equivalente."""
    sh, sl = [], []
    for t in range(max(k, start), upto - k + 1):
        win_h = h[t - k:t + k + 1]; win_l = l[t - k:t + k + 1]
        if h[t] == win_h.max() and (win_h == h[t]).sum() == 1:
            sh.append((t, h[t]))
        if l[t] == win_l.min() and (win_l == l[t]).sum() == 1:
            sl.append((t, l[t]))
    return sh, sl

def zones(piv: list, width: float, min_touch: int):
    """Clustering de pivotes por distancia ≤ width; devuelve [(centro, n_toques)]."""
    if not piv:
        return []
    prices = sorted(p for _, p in piv)
    out, cur = [], [prices[0]]
    for p in prices[1:]:
        if p - cur[-1] <= width:
            cur.append(p)
        else:
            if len(cur) >= min_touch:
                out.append((float(np.median(cur)), len(cur)))
            cur = [p]
    if len(cur) >= min_touch:
        out.append((float(np.median(cur)), len(cur)))
    return out


# ----------------------------------------------------------------------------
# Contenedor por temporalidad con indicadores precalculados
# ----------------------------------------------------------------------------
def _sec(idx: pd.DatetimeIndex) -> np.ndarray:
    """Epoch en segundos, robusto ante dtype datetime64[ns]/[us]/[ms]."""
    return idx.as_unit("ns").view("int64") // 10 ** 9


class TF:
    def __init__(self, df: pd.DataFrame, p: Params):
        self.t = _sec(df.index)
        self.o = df["open"].to_numpy(float); self.h = df["high"].to_numpy(float)
        self.l = df["low"].to_numpy(float);  self.c = df["close"].to_numpy(float)
        self.ema = ema(self.c, p.ema_n)
        self.atr = atr(self.h, self.l, self.c, p.atr_n)
        self.atr10 = atr(self.h, self.l, self.c, 10)
        self.rsi = rsi(self.c, p.rsi_n)
        self.adx = adx(self.h, self.l, self.c, p.adx_n)
        self.er = eff_ratio(self.c, p.er_n)
        self.n = len(self.c)


def resample(m5: pd.DataFrame, rule: str, offset: str | None = None) -> pd.DataFrame:
    agg = {"open": "first", "high": "max", "low": "min", "close": "last", "volume": "sum"}
    return m5.resample(rule, label="left", closed="left", offset=offset).agg(agg).dropna()


# ----------------------------------------------------------------------------
# Motor principal
# ----------------------------------------------------------------------------
@dataclass
class Trade:
    symbol: str; direction: int; t_entry: int = 0; entry: float = 0.0
    sl0: float = 0.0; tp: float = 0.0; qty: float = 0.0
    sl_init: float = 0.0    # stop inicial (sl0 se actualiza con el trailing)
    t_exit: int = 0; exit: float = 0.0; reason: str = ""; pnl: float = 0.0; r: float = 0.0
    mfe_pct: float = 0.0; mae_pct: float = 0.0
    mfe_r: float = 0.0; mae_r: float = 0.0
    duration_m5: int = 0


class Engine:
    def __init__(self, m5: pd.DataFrame, p: Params, symbol: str = "SYM",
                 equity0: float = 10_000.0, hmm_mult=None, funnel: bool = False,
                 daily_offset: str | None = None):
        self.p, self.symbol = p, symbol
        self.m5df = m5
        self.P = TF(m5, p)
        self.Idf = resample(m5, "1h");  self.I = TF(self.Idf, p)
        self.Gdf = resample(m5, "1D", offset=daily_offset);  self.G = TF(self.Gdf, p)
        # índice de la última vela I/G CERRADA para cada vela M5 (cerrada)
        m5_close_ts = _sec(m5.index + pd.Timedelta(minutes=5))
        i_close_ts = _sec(self.Idf.index + pd.Timedelta(hours=1))
        g_close_ts = _sec(self.Gdf.index + pd.Timedelta(days=1))
        self.map_i = np.searchsorted(i_close_ts, m5_close_ts, side="right") - 1
        self.map_g = np.searchsorted(g_close_ts, m5_close_ts, side="right") - 1
        self.hmm_mult = hmm_mult  # callable(g_idx)->float o None
        # Estado
        self.state = "IDLE"; self.bias = 0; self.bias_g_idx = -1
        self.o_imp = self.f_imp = math.nan; self.armed_i_idx = -1
        self.pos: Trade | None = None
        self.equity = equity0; self.equity0 = equity0
        self.trades: list[Trade] = []; self.ecurve = []
        self.day_pnl = {}; self.week_pnl = {}; self.month_pnl = {}
        self.day_start_equity = {}; self.week_start_equity = {}; self.month_start_equity = {}
        
        self.pos_max_fav = 0.0
        self.pos_max_adv = 0.0
        self.pos_entry_m = 0
        
        self.funnel_active = funnel
        if self.funnel_active:
            self.funnel_counters = {
                "g_eval": 0,
                "g1_pass": 0,
                "g2_touch": 0,
                "g3_arrive": 0,
                "g4_decel": 0,
                "g5_pattern": 0,
                "g5_pattern_engulfing": 0,
                "g5_pattern_pinbar": 0,
                "g5_pattern_double_top": 0,
                "g6_valid": 0,
                "i1_ema": 0,
                "i2_bos": 0,
                "i3_swings": 0,
                "i4_fib_reach": 0,
                "i5_antichase": 0,
                "i6_expired": 0,
                "i7_invalidated": 0,
                "trigger_fired": 0,
                "reject_stop_dist": 0,
                "reject_tp_pool": 0,
                "reject_rr_min": 0,
                "reject_killswitch": 0,
                "entered": 0
            }

    # ---------------- módulo G (FASE-2 §3) ----------------
    def _accumulate_g_counters(self, g2, g3, g4, g5, g6, engulfing, pinbar, dtop):
        if g2: self.funnel_counters['g2_touch'] += 1
        if g3: self.funnel_counters['g3_arrive'] += 1
        if g4: self.funnel_counters['g4_decel'] += 1
        if g5: self.funnel_counters['g5_pattern'] += 1
        if engulfing: self.funnel_counters['g5_pattern_engulfing'] += 1
        if pinbar: self.funnel_counters['g5_pattern_pinbar'] += 1
        if dtop: self.funnel_counters['g5_pattern_double_top'] += 1
        if g6: self.funnel_counters['g6_valid'] += 1

    def _bias_check(self, g: int) -> int:
        p, G = self.p, self.G
        if g < max(p.er_n, p.zone_lookback // 4, p.adx_n * 2):
            return 0
        if self.funnel_active:
            self.funnel_counters['g_eval'] += 1
        g1_passed = G.er[g] >= p.er_clean and G.adx[g] >= p.adx_clean
        if self.funnel_active and g1_passed:
            self.funnel_counters['g1_pass'] += 1
        if not g1_passed:        # G1
            return 0
        lo = max(0, g - p.zone_lookback)
        sh, sl_ = swings(G.h, G.l, p.k_piv_g, g, start=lo)
        w = p.zone_w_atr * G.atr[g]
        
        local_g2 = False
        local_g3 = False
        local_g4 = False
        local_g5 = False
        local_g6 = False
        local_g5_engulfing = False
        local_g5_pinbar = False
        local_g5_double_top = False

        for d, piv in ((-1, sh), (+1, sl_)):                               # short en resistencia, long en soporte
            for center, _ in zones(piv, w, p.zone_min_touches):
                zlo, zhi = center - w, center + w
                # G2: toque de la zona en las últimas P13 velas
                touched = None
                for j in range(max(0, g - p.touch_window + 1), g + 1):
                    px = G.h[j] if d < 0 else G.l[j]
                    if zlo <= px <= zhi:
                        touched = j
                if touched is not None:
                    local_g2 = True
                else:
                    continue
                # G3: llegada acelerada (OR, AMBIG-2)
                seg = G.c[max(0, touched - p.arrive_n):touched + 1]
                den = np.abs(np.diff(seg)).sum()
                er_seg = abs(seg[-1] - seg[0]) / den if den > 0 else 0.0
                rsi_ok = G.rsi[touched] >= p.rsi_extreme if d < 0 else G.rsi[touched] <= 100 - p.rsi_extreme
                if er_seg >= p.er_arrive or rsi_ok:
                    local_g3 = True
                else:
                    continue
                # G4: desaceleración (D-2)
                body = np.abs(G.c[g - 2:g + 1] - G.o[g - 2:g + 1]).mean()
                if G.atr10[g] > 0 and body / G.atr10[g] <= p.decel_max:
                    local_g4 = True
                else:
                    continue
                # G5: patrón de giro (uno de tres)
                pattern = self._reversal_pattern(g, d, zlo, zhi)
                if pattern:
                    local_g5 = True
                    if pattern == "engulfing":
                        local_g5_engulfing = True
                    elif pattern == "pinbar":
                        local_g5_pinbar = True
                    elif pattern == "double_top":
                        local_g5_double_top = True
                else:
                    continue
                # G6: no invalidado (cierre confirmado fuera de la zona)
                brk = (G.c[g] > zhi and G.c[g - 1] > zhi) if d < 0 else (G.c[g] < zlo and G.c[g - 1] < zlo)
                if brk:
                    continue
                local_g6 = True
                self._zone = (zlo, zhi)
                if self.funnel_active:
                    self._accumulate_g_counters(local_g2, local_g3, local_g4, local_g5, local_g6,
                                                local_g5_engulfing, local_g5_pinbar, local_g5_double_top)
                return d
        if self.funnel_active:
            self._accumulate_g_counters(local_g2, local_g3, local_g4, local_g5, local_g6,
                                        local_g5_engulfing, local_g5_pinbar, local_g5_double_top)
        return 0

    def _reversal_pattern(self, g, d, zlo, zhi) -> str | None:
        p, G = self.p, self.G
        o1, c1, o0, c0 = G.o[g - 1], G.c[g - 1], G.o[g], G.c[g]
        h0, l0 = G.h[g], G.l[g]
        b0, b1 = abs(c0 - o0), abs(c1 - o1)
        if d < 0:  # short: envolvente bajista / pinbar alto / doble techo
            if c0 < o0 and o0 >= c1 and c0 < o1 and b0 > b1:
                return "engulfing"
            if b0 > 0 and (h0 - max(o0, c0)) >= p.pin_ratio * b0 and c0 <= (h0 + l0) / 2 + 0.1 * (h0 - l0):
                return "pinbar"
            sh, _ = swings(G.h, G.l, self.p.k_frac_i, g, start=max(0, g - 150))
            inz = [(t, v) for t, v in sh[-4:] if zlo <= v <= zhi]
            if len(inz) >= 2 and abs(inz[-1][1] - inz[-2][1]) <= p.dtop_tol_atr * G.atr[g]:
                neck = G.l[inz[-2][0]:inz[-1][0] + 1].min()      # mínimo entre los dos techos
                if c0 < neck:                                     # G5c: cierre bajo el neckline
                    return "double_top"
        else:      # long simétrico
            if c0 > o0 and o0 <= c1 and c0 > o1 and b0 > b1:
                return "engulfing"
            if b0 > 0 and (min(o0, c0) - l0) >= p.pin_ratio * b0 and c0 >= (h0 + l0) / 2 - 0.1 * (h0 - l0):
                return "pinbar"
            _, sl_ = swings(G.h, G.l, self.p.k_frac_i, g, start=max(0, g - 150))
            inz = [(t, v) for t, v in sl_[-4:] if zlo <= v <= zhi]
            if len(inz) >= 2 and abs(inz[-1][1] - inz[-2][1]) <= p.dtop_tol_atr * G.atr[g]:
                neck = G.h[inz[-2][0]:inz[-1][0] + 1].max()      # máximo entre los dos suelos
                if c0 > neck:                                     # G5c: cierre sobre el neckline
                    return "double_top"
        return None

    # ---------------- módulo I (FASE-2 §4) ----------------
    def _structure_check(self, i: int) -> bool:
        p, I, d = self.p, self.I, self.bias
        if i < p.ema_n or np.isnan(I.ema[i]):
            return False
        i1_passed = (I.c[i] < I.ema[i]) if d < 0 else (I.c[i] > I.ema[i])
        if self.funnel_active and i1_passed:
            self.funnel_counters['i1_ema'] += 1
        if not i1_passed:    # I1
            return False
        sh, sl_ = swings(I.h, I.l, p.k_frac_i, i, start=max(0, i - 400))
        if d < 0:
            if len(sl_) < 2 or len(sh) < 2:
                return False
            i2_passed = I.c[i] < sl_[-1][1]
            if self.funnel_active and i2_passed:
                self.funnel_counters['i2_bos'] += 1
            if not i2_passed:                                  # I2 BOS
                return False
            i3_passed = sh[-1][1] < sh[-2][1]
            if self.funnel_active and i3_passed:
                self.funnel_counters['i3_swings'] += 1
            if not i3_passed:                                # I3 máx decrecientes
                return False
            self.o_imp = sh[-1][1]
            self.f_imp = I.l[max(0, i - 20):i + 1].min()
        else:
            if len(sh) < 2 or len(sl_) < 2:
                return False
            i2_passed = I.c[i] > sh[-1][1]
            if self.funnel_active and i2_passed:
                self.funnel_counters['i2_bos'] += 1
            if not i2_passed:
                return False
            i3_passed = sl_[-1][1] > sl_[-2][1]
            if self.funnel_active and i3_passed:
                self.funnel_counters['i3_swings'] += 1
            if not i3_passed:
                return False
            self.o_imp = sl_[-1][1]
            self.f_imp = I.h[max(0, i - 20):i + 1].max()
        return abs(self.o_imp - self.f_imp) > 1e-12

    def _fib(self, r: float) -> float:
        return self.f_imp + r * (self.o_imp - self.f_imp)

    def _zone_check(self, i: int) -> bool:
        p, I, d = self.p, self.I, self.bias
        if math.isnan(self.f_imp):
            return False
        # re-anclaje (R-C26)
        if d < 0 and I.l[i] < self.f_imp:
            self.f_imp = I.l[i]
        if d > 0 and I.h[i] > self.f_imp:
            self.f_imp = I.h[i]
        px = I.h[i] if d < 0 else I.l[i]
        reach = px >= self._fib(0.382) if d < 0 else px <= self._fib(0.382)  # I4
        if self.funnel_active and reach:
            self.funnel_counters['i4_fib_reach'] += 1
        if not reach:
            return False
        dist = abs(px - I.ema[i])                                            # I5 anti-chase (D-5)
        touched_ema = (px >= I.ema[i]) if d < 0 else (px <= I.ema[i])
        antichase = touched_ema or dist <= p.chase_atr * I.atr[i]
        if self.funnel_active and antichase:
            self.funnel_counters['i5_antichase'] += 1
        if not antichase:
            return False
        # I7 invalidación
        invalidated = (I.c[i] > self._fib(1.0)) if d < 0 else (I.c[i] < self._fib(1.0))
        if invalidated:
            if self.funnel_active:
                self.funnel_counters['i7_invalidated'] += 1
            self.state = "IDLE"; self.bias = 0
            return False
        return True

    # ---------------- módulo P (FASE-2 §5) ----------------
    def _trigger(self, m: int) -> bool:
        P, d = self.P, self.bias
        if m < 1 or np.isnan(P.ema[m]) or np.isnan(P.ema[m - 1]):
            return False
        if d < 0:
            return P.c[m] < P.ema[m] and P.c[m - 1] >= P.ema[m - 1]
        return P.c[m] > P.ema[m] and P.c[m - 1] <= P.ema[m - 1]

    # ---------------- riesgo / límites (FASE-2 §9) ----------------
    def _kill_switch(self, ts: int) -> bool:
        d = pd.Timestamp(ts, unit="s")
        day_key = d.strftime("%Y%m%d")
        week_key = f"{d.isocalendar().year}w{d.isocalendar().week}"
        month_key = d.strftime("%Y%m")
        
        eq_day = self.day_start_equity.get(day_key, self.equity0)
        eq_week = self.week_start_equity.get(week_key, self.equity0)
        eq_month = self.month_start_equity.get(month_key, self.equity0)
        
        lim_day = self.p.max_dd_day * eq_day
        lim_week = self.p.max_dd_week * eq_week
        lim_month = self.p.max_dd_month * eq_month
        
        return (self.day_pnl.get(day_key, 0.0) <= -lim_day or
                self.week_pnl.get(week_key, 0.0) <= -lim_week or
                self.month_pnl.get(month_key, 0.0) <= -lim_month)

    def _book_pnl(self, ts: int, pnl: float):
        d = pd.Timestamp(ts, unit="s")
        for b, k in ((self.day_pnl, d.strftime("%Y%m%d")),
                     (self.week_pnl, f"{d.isocalendar().year}w{d.isocalendar().week}"),
                     (self.month_pnl, d.strftime("%Y%m"))):
            b[k] = b.get(k, 0.0) + pnl

    # ---------------- bucle principal ----------------
    def run(self) -> dict:
        p = self.p
        last_g = last_i = -1
        for m in range(p.ema_n + 1, self.P.n - 1):
            g, i = self.map_g[m], self.map_i[m]
            ts = self.P.t[m]
            
            # Registrar capital al inicio de cada período
            dt = pd.Timestamp(ts, unit="s")
            day_key = dt.strftime("%Y%m%d")
            week_key = f"{dt.isocalendar().year}w{dt.isocalendar().week}"
            month_key = dt.strftime("%Y%m")
            if day_key not in self.day_start_equity:
                self.day_start_equity[day_key] = self.equity
            if week_key not in self.week_start_equity:
                self.week_start_equity[week_key] = self.equity
            if month_key not in self.month_start_equity:
                self.month_start_equity[month_key] = self.equity
            # --- gestión de posición (intravela sobre la vela M5 m+1 se hace al abrirla;
            #     aquí: stops/TP contra la vela m ya cerrada del flujo en curso) ---
            if self.pos:
                self._manage(m, i, last_i)
            # --- cierre de vela G nueva ---
            if g != last_g and g >= 0:
                last_g = g
                if self.pos is None:
                    d = self._bias_check(g)
                    if d != 0:
                        self.state, self.bias, self.bias_g_idx = "BIAS", d, g
                    elif self.state in ("BIAS", "STRUCTURE", "ARMED") and g - self.bias_g_idx >= p.bias_expiry:
                        self.state, self.bias = "IDLE", 0                   # R-C24 caducidad
            # --- cierre de vela I nueva ---
            if i != last_i and i >= 0:
                last_i = i
                if self.state == "BIAS" and self._structure_check(i):
                    self.state = "STRUCTURE"
                if self.state == "STRUCTURE" and self._zone_check(i):
                    self.state, self.armed_i_idx = "ARMED", i
                elif self.state == "ARMED":
                    if not self._zone_check(i) and self.state == "IDLE":
                        pass                                                 # invalidado en zone_check
                    elif i - self.armed_i_idx > p.armed_window:              # I6 expiración
                        if self.funnel_active:
                            self.funnel_counters['i6_expired'] += 1
                        self.state = "STRUCTURE"
            # --- cierre de vela P: gatillo ---
            if self.state == "ARMED" and self.pos is None and self._trigger(m):
                if self.funnel_active:
                    self.funnel_counters['trigger_fired'] += 1
                killswitch_active = self._kill_switch(ts)
                if killswitch_active:
                    if self.funnel_active:
                        self.funnel_counters['reject_killswitch'] += 1
                if not killswitch_active and (self.hmm_mult is None or self.hmm_mult(g) > 0):
                    self._enter(m, i, g)
            self.ecurve.append((ts, self.equity + self._open_pnl(m)))
        if self.pos:                                                          # cierre forzado al final
            self._exit(self.P.n - 1, self.P.c[-1], "eod")
        if self.funnel_active:
            self.save_and_print_funnel()
        return self.metrics()

    def _open_pnl(self, m):
        if not self.pos:
            return 0.0
        return (self.P.c[m] - self.pos.entry) * self.pos.direction * self.pos.qty

    def _enter(self, m, i, g):
        p, I, d = self.p, self.I, self.bias
        raw = self.P.o[m + 1]                                       # apertura vela siguiente
        entry = raw * (1 + d * (p.spread_pct / 2 + p.slip_pct))     # fricciones D-3
        sh, sl_ = swings(I.h, I.l, p.k_frac_i, i, start=max(0, i - 400))
        depth = (abs((self.I.h[i] if d < 0 else self.I.l[i]) - self.f_imp)
                 / abs(self.o_imp - self.f_imp))
        buf = p.buf_atr * I.atr[i]
        if depth <= 0.618:                                          # R-C35 / D-1
            sl0 = self._fib(0.75) + (buf if d < 0 else -buf)
        else:
            ext = self._fib(1.0)
            if d < 0:
                last_sh = sh[-1][1] if sh else ext
                sl0 = max(ext, last_sh) + buf
            else:
                last_sl = sl_[-1][1] if sl_ else ext
                sl0 = min(ext, last_sl) - buf
        dist = abs(sl0 - entry)
        if dist < p.stop_min_atr * I.atr[i] or dist > p.stop_max_atr * I.atr[i]:
            if self.funnel_active:
                self.funnel_counters['reject_stop_dist'] += 1
            self.state = "STRUCTURE"; return                        # sanidad §6
        # TP: extremo estructural previo (§7)
        pool = sl_ if d < 0 else sh
        pool = [v for t, v in pool if t >= i - p.tp_lookback]
        if not pool:
            if self.funnel_active:
                self.funnel_counters['reject_tp_pool'] += 1
            self.state = "STRUCTURE"; return
        tp = min(pool) if d < 0 else max(pool)
        rr = abs(entry - tp) / dist
        if rr < p.rr_min:
            if self.funnel_active:
                self.funnel_counters['reject_rr_min'] += 1
            self.state = "STRUCTURE"; return
        mult = self.hmm_mult(g) if self.hmm_mult else 1.0           # Pilar B §11
        qty = (p.risk_pct * mult * self.equity) / dist
        qty = min(qty, p.leverage_cap * self.equity / entry)        # P37 (FASE-6 §5)
        fee = entry * qty * p.fee_pct
        self.pos = Trade(self.symbol, d, self.P.t[m + 1], entry, sl0, tp, qty, sl_init=sl0)
        self.pos.pnl -= fee
        
        self.pos_max_fav = 0.0
        self.pos_max_adv = 0.0
        self.pos_entry_m = m + 1
        
        if self.funnel_active:
            self.funnel_counters['entered'] += 1
        self.state = "IN_POSITION"

    def _manage(self, m, i, last_i):
        """Trailing al cierre de vela de la TF de gestión (D-6/P36) + stops intravela."""
        p, pos = self.p, self.pos
        d = pos.direction
        
        h_m5, l_m5 = self.P.h[m], self.P.l[m]
        if d > 0:
            fav = h_m5 - pos.entry
            adv = pos.entry - l_m5
        else:
            fav = pos.entry - l_m5
            adv = h_m5 - pos.entry
        self.pos_max_fav = max(getattr(self, 'pos_max_fav', 0.0), fav)
        self.pos_max_adv = max(getattr(self, 'pos_max_adv', 0.0), adv)

        # trailing al cierre de vela de gestión
        if p.trail_tf == "I":
            if i != last_i and i >= 0 and not np.isnan(self.I.ema[i]):
                cand = self.I.ema[i] + (p.buf_atr * self.I.atr[i] if d < 0 else -p.buf_atr * self.I.atr[i])
                pos.sl0 = min(pos.sl0, cand) if d < 0 else max(pos.sl0, cand)
        else:
            if not np.isnan(self.P.ema[m]):
                cand = self.P.ema[m] + (p.buf_atr * self.P.atr[m] if d < 0 else -p.buf_atr * self.P.atr[m])
                pos.sl0 = min(pos.sl0, cand) if d < 0 else max(pos.sl0, cand)
        # ejecución intravela en la vela m (peor precio ante gap)
        h, l, o = self.P.h[m], self.P.l[m], self.P.o[m]
        hit_sl = h >= pos.sl0 if d < 0 else l <= pos.sl0
        hit_tp = l <= pos.tp if d < 0 else h >= pos.tp
        if hit_sl and hit_tp:
            hit_tp = False                                          # conservador: stop primero
        if hit_sl:
            px = max(pos.sl0, o) if d < 0 else min(pos.sl0, o)
            self._exit(m, px, "stop")
        elif hit_tp:
            self._exit(m, pos.tp, "tp")

    def _exit(self, m, price, reason):
        p, pos = self.p, self.pos
        px = price * (1 - pos.direction * (p.spread_pct / 2 + p.slip_pct))
        gross = (px - pos.entry) * pos.direction * pos.qty
        fee = px * pos.qty * p.fee_pct
        pos.pnl += gross - fee
        pos.t_exit, pos.exit, pos.reason = int(self.P.t[m]), px, reason
        pos.r = pos.pnl / (p.risk_pct * self.equity) if self.equity > 0 else 0.0
        
        h_m5, l_m5 = self.P.h[m], self.P.l[m]
        if pos.direction > 0:
            fav = h_m5 - pos.entry
            adv = pos.entry - l_m5
        else:
            fav = pos.entry - l_m5
            adv = h_m5 - pos.entry
        self.pos_max_fav = max(getattr(self, 'pos_max_fav', 0.0), fav)
        self.pos_max_adv = max(getattr(self, 'pos_max_adv', 0.0), adv)
        
        pos.mfe_pct = self.pos_max_fav / pos.entry
        pos.mae_pct = self.pos_max_adv / pos.entry
        
        risk_dist = abs(pos.entry - pos.sl_init)
        pos.mfe_r = self.pos_max_fav / risk_dist if risk_dist > 0 else 0.0
        pos.mae_r = self.pos_max_adv / risk_dist if risk_dist > 0 else 0.0
        
        pos.duration_m5 = m - getattr(self, 'pos_entry_m', m) + 1
        
        self.equity += pos.pnl
        self._book_pnl(pos.t_exit, pos.pnl)
        self.trades.append(pos)
        self.pos = None
        self.state, self.bias = "IDLE", 0

    # ---------------- métricas (FASE-4 §4) ----------------
    def metrics(self) -> dict:
        tr = self.trades
        if not tr:
            return {"trades": 0, "nota": "sin operaciones — revisar filtros/datos"}
        pnl = np.array([t.pnl for t in tr]); win = pnl[pnl > 0]; los = pnl[pnl < 0]
        eq = np.array([e for _, e in self.ecurve])
        peak = np.maximum.accumulate(eq); dd = (eq - peak) / peak
        daily = pd.Series(eq, index=pd.to_datetime([t for t, _ in self.ecurve], unit="s")) \
                  .resample("1D").last().dropna().pct_change().dropna()
        sharpe = float(daily.mean() / daily.std() * math.sqrt(252)) if len(daily) > 2 and daily.std() > 0 else 0.0
        dnn = daily[daily < 0]
        sortino = float(daily.mean() / dnn.std() * math.sqrt(252)) if len(dnn) > 2 and dnn.std() > 0 else 0.0
        streaks = {"win": 0, "loss": 0}; cw = cl = 0
        for x in pnl:
            cw, cl = (cw + 1, 0) if x > 0 else (0, cl + 1)
            streaks["win"] = max(streaks["win"], cw); streaks["loss"] = max(streaks["loss"], cl)
        years = max((self.ecurve[-1][0] - self.ecurve[0][0]) / 31_557_600, 1e-9)
        return {
            "trades": len(tr), "win_rate": round(len(win) / len(tr), 4),
            "profit_factor": round(float(win.sum() / -los.sum()), 3) if len(los) else float("inf"),
            "expectancy_usd": round(float(pnl.mean()), 2),
            "expectancy_R": round(float(np.mean([t.r for t in tr])), 3),
            "max_drawdown": round(float(dd.min()), 4),
            "recovery_factor": round(float((eq[-1] - eq[0]) / abs(dd.min() * peak.max())), 2) if dd.min() < 0 else float("inf"),
            "sharpe": round(sharpe, 2), "sortino": round(sortino, 2),
            "cagr": round((self.equity / self.equity0) ** (1 / years) - 1, 4),
            "ret_total": round(self.equity / self.equity0 - 1, 4),
            "trades_por_año": round(len(tr) / years, 1),
            "racha_max": streaks,
        }

    def save_and_print_funnel(self):
        import os
        exits_info = {}
        for reason in ["stop", "tp", "eod"]:
            trades_reason = [t for t in self.trades if t.reason == reason]
            count = len(trades_reason)
            if count > 0:
                total_r = sum(t.r for t in trades_reason)
                avg_r = total_r / count
                avg_duration = sum(t.duration_m5 for t in trades_reason) / count
            else:
                total_r = 0.0
                avg_r = 0.0
                avg_duration = 0.0
            exits_info[reason] = {
                "count": count,
                "total_r": round(total_r, 4),
                "avg_r": round(avg_r, 4),
                "avg_duration_m5": round(avg_duration, 2)
            }
        
        all_mfe_pct = [t.mfe_pct for t in self.trades]
        all_mae_pct = [t.mae_pct for t in self.trades]
        all_mfe_r = [t.mfe_r for t in self.trades]
        all_mae_r = [t.mae_r for t in self.trades]
        
        mfe_mae_summary = {
            "avg_mfe_pct": round(float(np.mean(all_mfe_pct)), 6) if all_mfe_pct else 0.0,
            "avg_mae_pct": round(float(np.mean(all_mae_pct)), 6) if all_mae_pct else 0.0,
            "avg_mfe_r": round(float(np.mean(all_mfe_r)), 4) if all_mfe_r else 0.0,
            "avg_mae_r": round(float(np.mean(all_mae_r)), 4) if all_mae_r else 0.0,
            "max_mfe_r": round(float(np.max(all_mfe_r)), 4) if all_mfe_r else 0.0,
            "max_mae_r": round(float(np.max(all_mae_r)), 4) if all_mae_r else 0.0,
        }
        
        funnel_data = {
            "symbol": self.symbol,
            "counters": self.funnel_counters,
            "exits": exits_info,
            "mfe_mae_summary": mfe_mae_summary,
            "trades": [
                {
                    "t_entry": int(t.t_entry),
                    "t_exit": int(t.t_exit),
                    "direction": t.direction,
                    "entry": round(t.entry, 4),
                    "exit": round(t.exit, 4),
                    "reason": t.reason,
                    "pnl": round(t.pnl, 4),
                    "r": round(t.r, 4),
                    "duration_m5": t.duration_m5,
                    "mfe_pct": round(t.mfe_pct, 6),
                    "mae_pct": round(t.mae_pct, 6),
                    "mfe_r": round(t.mfe_r, 4),
                    "mae_r": round(t.mae_r, 4)
                } for t in self.trades
            ]
        }
        
        # Guardar en archivo JSON
        results_dir = "C:/Users/camilo.chitiva/Trading/code/python/results"
        os.makedirs(results_dir, exist_ok=True)
        filepath = os.path.join(results_dir, f"funnel_{self.symbol}.json")
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(funnel_data, f, indent=2, ensure_ascii=False)
        print(f"\n[funnel] Datos del embudo guardados en: {filepath}")
        
        # Imprimir tabla ordenada y legible en consola
        fc = self.funnel_counters
        g_eval = fc.get("g_eval", 0)
        g1 = fc.get("g1_pass", 0)
        g2 = fc.get("g2_touch", 0)
        g3 = fc.get("g3_arrive", 0)
        g4 = fc.get("g4_decel", 0)
        g5 = fc.get("g5_pattern", 0)
        g6 = fc.get("g6_valid", 0)
        
        i1 = fc.get("i1_ema", 0)
        i2 = fc.get("i2_bos", 0)
        i3 = fc.get("i3_swings", 0)
        i4 = fc.get("i4_fib_reach", 0)
        i5 = fc.get("i5_antichase", 0)
        
        tr_fired = fc.get("trigger_fired", 0)
        entered = fc.get("entered", 0)
        
        pct_g1 = (g1 / g_eval * 100) if g_eval > 0 else 0.0
        pct_g2 = (g2 / g1 * 100) if g1 > 0 else 0.0
        pct_g3 = (g3 / g2 * 100) if g2 > 0 else 0.0
        pct_g4 = (g4 / g3 * 100) if g3 > 0 else 0.0
        pct_g5 = (g5 / g4 * 100) if g4 > 0 else 0.0
        pct_g6 = (g6 / g5 * 100) if g5 > 0 else 0.0
        
        pct_i2 = (i2 / i1 * 100) if i1 > 0 else 0.0
        pct_i3 = (i3 / i2 * 100) if i2 > 0 else 0.0
        pct_i4 = (i4 / i3 * 100) if i3 > 0 else 0.0
        pct_i5 = (i5 / i4 * 100) if i4 > 0 else 0.0
        
        pct_entered = (entered / tr_fired * 100) if tr_fired > 0 else 0.0
        
        print("\n" + "="*65)
        print(f"SATAR-1 EMBUDO DE FILTROS (Símbolo: {self.symbol})")
        print("="*65)
        print("MÓDULO G (Filtros Diarios de Bias):")
        print(f"  g_eval (Velas G Evaluadas):               {g_eval}")
        print(f"  g1_pass (Eficiencia y ADX):               {g1} ({pct_g1:.1f}% de eval)")
        print(f"  g2_touch (Toque Zona Extrema):            {g2} ({pct_g2:.1f}% de G1)")
        print(f"  g3_arrive (Llegada Acelerada):            {g3} ({pct_g3:.1f}% de G2)")
        print(f"  g4_decel (Desaceleración Máxima):         {g4} ({pct_g4:.1f}% de G3)")
        print(f"  g5_pattern (Patrón de Giro):              {g5} ({pct_g5:.1f}% de G4)")
        print(f"    - engulfing (Envolvente):               {fc.get('g5_pattern_engulfing', 0)}")
        print(f"    - pinbar:                               {fc.get('g5_pattern_pinbar', 0)}")
        print(f"    - double_top (Doble Techo/Suelo):       {fc.get('g5_pattern_double_top', 0)}")
        print(f"  g6_valid (No Cierre Fuera - Bias OK):     {g6} ({pct_g6:.1f}% de G5)")
        print("-"*65)
        print("MÓDULO I (Estructura en H1):")
        print(f"  i1_ema (Tendencia EMA H1):                {i1}")
        print(f"  i2_bos (Ruptura de Estructura BOS):       {i2} ({pct_i2:.1f}% de I1)")
        print(f"  i3_swings (Swings de Estructura):         {i3} ({pct_i3:.1f}% de BOS)")
        print(f"  i4_fib_reach (Entrada a Zona Fib 0.382):  {i4} ({pct_i4:.1f}% de swings)")
        print(f"  i5_antichase (Anti-chase):                {i5} ({pct_i5:.1f}% de Fib)")
        print(f"  i6_expired (Expiración Temporal):         {fc.get('i6_expired', 0)}")
        print(f"  i7_invalidated (Invalidación Fib 1.0):    {fc.get('i7_invalidated', 0)}")
        print("-"*65)
        print("GATILLO Y SANIDAD DE ENTRADA (M5):")
        print(f"  trigger_fired (Cruce EMA M5):             {tr_fired}")
        print(f"  reject_stop_dist (Filtro Distancia Stop): {fc.get('reject_stop_dist', 0)}")
        print(f"  reject_tp_pool (Sin Pivotes TP):          {fc.get('reject_tp_pool', 0)}")
        print(f"  reject_rr_min (R:R Mínimo Insuficiente):  {fc.get('reject_rr_min', 0)}")
        print(f"  reject_killswitch (Killswitch Activo):    {fc.get('reject_killswitch', 0)}")
        print(f"  entered (Trades Abiertos):                {entered} ({pct_entered:.1f}% de triggers)")
        print("-"*65)
        print("DISTRIBUCIÓN DE SALIDAS Y MÉTRICAS DE RIESGO:")
        for r_name, info in exits_info.items():
            print(f"  {r_name:<6}: {info['count']:>3} trades | Prom. R: {info['avg_r']:>6.2f} R | Total R: {info['total_r']:>7.2f} R | Prom. Duración: {info['avg_duration_m5']:>6.1f} velas M5")
        print(f"  MFE Promedio: {mfe_mae_summary['avg_mfe_r']:.2f} R ({mfe_mae_summary['avg_mfe_pct']*100:.3f}%) | MAE Promedio: {mfe_mae_summary['avg_mae_r']:.2f} R ({mfe_mae_summary['avg_mae_pct']*100:.3f}%)")
        print(f"  MFE Máximo:   {mfe_mae_summary['max_mfe_r']:.2f} R | MAE Máximo:   {mfe_mae_summary['max_mae_r']:.2f} R")
        print("="*65 + "\n")


# ----------------------------------------------------------------------------
# Pilar B — multiplicador HMM opcional (FASE-2 §11); requiere hmmlearn
# ----------------------------------------------------------------------------
def make_hmm_mult(Gdf: pd.DataFrame, window: int = 750, refit: int = 21):
    try:
        from hmmlearn.hmm import GaussianHMM
    except ImportError:
        print("[aviso] hmmlearn no instalado — Pilar B desactivado (mult=1.0)")
        return None
    c = Gdf["close"].to_numpy(float)
    r = np.diff(np.log(c), prepend=0.0)
    f = np.column_stack([pd.Series(r).rolling(20).std().to_numpy(),
                         pd.Series(r).rolling(20).sum().to_numpy(),
                         pd.Series(c).pct_change(10).to_numpy()])
    mult = np.ones(len(c))
    last_fit, model, order = -1, None, None
    for g in range(window, len(c)):
        if model is None or g - last_fit >= refit:
            X = f[g - window:g]; X = X[~np.isnan(X).any(axis=1)]
            if len(X) < 100:
                continue
            mu, sd = X.mean(0), X.std(0); sd[sd == 0] = 1
            best = None
            for k in (2, 3, 4, 5):
                try:
                    m_ = GaussianHMM(k, covariance_type="full", n_iter=100, random_state=7).fit((X - mu) / sd)
                    bic = -2 * m_.score((X - mu) / sd) + k * (k + 6) * math.log(len(X))
                    if best is None or bic < best[0]:
                        best = (bic, m_, mu, sd)
                except Exception:
                    pass
            if best is None:
                continue
            _, model, mu, sd = best; last_fit = g
            mret = model.means_[:, 1]; mvol = model.means_[:, 0]
            order = {"crisis": int(np.argmin(mret - mvol)), "trend": int(np.argmax(np.abs(mret) - mvol))}
        if model is not None and not np.isnan(f[g]).any():
            probs = model.predict_proba(((f[max(0, g - 50):g + 1] - mu) / sd))[-1]   # filtered aprox.
            s = int(np.argmax(probs))
            if probs[s] > 0.6:
                mult[g] = 0.0 if s == order["crisis"] else (1.0 if s == order["trend"] else 0.5)
    return lambda g_idx: float(mult[g_idx]) if 0 <= g_idx < len(mult) else 1.0


# ----------------------------------------------------------------------------
# Datos sintéticos para smoke-test (NO son evidencia de rentabilidad)
# ----------------------------------------------------------------------------
def synthetic_m5(days=250, seed=7) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    n = days * 288
    regime = np.repeat(rng.choice([0, 1, 2], size=n // 2000 + 1, p=[.5, .3, .2]), 2000)[:n]
    drift = np.where(regime == 1, 4e-5, np.where(regime == 2, -4e-5, 0.0))
    vol = np.where(regime == 0, 6e-4, 9e-4)
    ret = rng.normal(drift, vol)
    close = 100 * np.exp(np.cumsum(ret))
    o = np.roll(close, 1); o[0] = close[0]
    spread = np.abs(rng.normal(0, vol)) * close
    h = np.maximum(o, close) + spread; l = np.minimum(o, close) - spread
    idx = pd.date_range("2024-01-02", periods=n, freq="5min", tz="UTC")
    return pd.DataFrame({"open": o, "high": h, "low": l, "close": close,
                         "volume": rng.integers(1, 1000, n)}, index=idx)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--smoke", action="store_true")
    ap.add_argument("--csv", type=str, help="CSV M5 con columnas timestamp,open,high,low,close,volume")
    ap.add_argument("--hmm", action="store_true", help="activar Pilar B (requiere hmmlearn)")
    ap.add_argument("--trail", choices=["I", "P"], default="I", help="P36: TF del trailing")
    ap.add_argument("--funnel", action="store_true", help="activar instrumentación de embudo no invasiva")
    args = ap.parse_args()
    if args.smoke:
        df = synthetic_m5()
        print(f"[smoke] {len(df)} velas M5 sintéticas")
    elif args.csv:
        df = pd.read_csv(args.csv, parse_dates=["timestamp"], index_col="timestamp")
        if df.index.tz is None:
            df.index = df.index.tz_localize("UTC")
    else:
        ap.print_help(); sys.exit(1)
    p = Params(trail_tf=args.trail)
    
    # Extraer símbolo del nombre de archivo CSV para el guardado de datos de funnel
    symbol = "SYM"
    if args.csv:
        import os
        base = os.path.basename(args.csv)
        symbol = base.split("_")[0].upper()
    elif args.smoke:
        symbol = "SMOKE"
        
    hmm = make_hmm_mult(resample(df, "1D")) if args.hmm else None
    eng = Engine(df, p, symbol=symbol, hmm_mult=hmm, funnel=args.funnel)
    res = eng.run()
    print(json.dumps(res, indent=2, ensure_ascii=False))
    if eng.trades:
        out = pd.DataFrame([asdict(t) for t in eng.trades])
        out.to_csv("trades_out.csv", index=False)
        print(f"[ok] {len(eng.trades)} trades -> trades_out.csv")


if __name__ == "__main__":
    main()

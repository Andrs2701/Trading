# -*- coding: utf-8 -*-
"""
HYDRA — Hybrid Dynamic Regime-Adaptive Trading System.
Motor de backtesting event-driven con detección de régimen (HMM + Hurst)
y entrada por confluencia ponderada (momentum pullback + mean-reversion).

Reutiliza la infraestructura auditada de SATAR-1: trailing EMA H1, kill-switch,
position sizing, indicadores (EMA, ATR, RSI, ADX, ER), y pipeline de datos.

Uso:
  python hydra_backtest.py --smoke
  python hydra_backtest.py --csv btcusdt_m5.csv
  python hydra_backtest.py --csv btcusdt_m5.csv --hmm
"""
from __future__ import annotations
import argparse, json, math, os, sys
from dataclasses import dataclass, field, asdict
import numpy as np
import pandas as pd

# Reutilizar infraestructura base de SATAR-1
from satar_backtest import (
    ema, _wilder, atr, rsi, adx, eff_ratio,
    swings, zones, _sec, TF, Trade, resample,
    make_hmm_mult, synthetic_m5, Params as _BaseParams,
)


# ============================================================================
# Nuevos indicadores
# ============================================================================
def hurst_rs(c: np.ndarray, window: int = 100) -> np.ndarray:
    """Hurst exponent via Rescaled Range (R/S) method, rolling."""
    n = len(c)
    out = np.full(n, np.nan, dtype=float)
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
            out[i] = 0.5  # indeterminado → random walk
    return out


def bollinger(c: np.ndarray, period: int = 20, std_mult: float = 2.0):
    """Bollinger Bands: (upper, lower, sma). Rolling."""
    n = len(c)
    sma = np.full(n, np.nan, dtype=float)
    upper = np.full(n, np.nan, dtype=float)
    lower = np.full(n, np.nan, dtype=float)
    for i in range(period - 1, n):
        seg = c[i - period + 1:i + 1]
        m = seg.mean()
        s = seg.std(ddof=0)
        sma[i] = m
        upper[i] = m + std_mult * s
        lower[i] = m - std_mult * s
    return upper, lower, sma


def vol_ma(vol: np.ndarray, period: int = 20) -> np.ndarray:
    """SMA del volumen."""
    n = len(vol)
    out = np.full(n, np.nan, dtype=float)
    cs = np.cumsum(vol)
    for i in range(period - 1, n):
        out[i] = (cs[i] - (cs[i - period] if i >= period else 0.0)) / period
    return out


def vol_trend(vol: np.ndarray, n_bars: int = 3) -> np.ndarray:
    """Pendiente normalizada del volumen sobre n_bars. >0 = creciente, <0 = decreciente."""
    n = len(vol)
    out = np.full(n, 0.0, dtype=float)
    for i in range(n_bars, n):
        seg = vol[i - n_bars + 1:i + 1]
        mean_v = seg.mean()
        if mean_v > 0:
            # pendiente normalizada: (último - primero) / media
            out[i] = (seg[-1] - seg[0]) / mean_v
    return out


def vwap_rolling(h: np.ndarray, l: np.ndarray, c: np.ndarray,
                 vol: np.ndarray, window: int = 288) -> np.ndarray:
    """VWAP rolling (default 288 = 24h en M5). Retorna (vwap, vwap_std)."""
    tp = (h + l + c) / 3.0
    n = len(c)
    vwap = np.full(n, np.nan, dtype=float)
    vwap_std = np.full(n, np.nan, dtype=float)
    for i in range(window - 1, n):
        seg_tp = tp[i - window + 1:i + 1]
        seg_v = vol[i - window + 1:i + 1]
        sv = seg_v.sum()
        if sv > 0:
            vw = (seg_tp * seg_v).sum() / sv
            vwap[i] = vw
            # desviación estándar ponderada por volumen
            vwap_std[i] = math.sqrt(max(0, ((seg_tp - vw)**2 * seg_v).sum() / sv))
        else:
            vwap[i] = seg_tp.mean()
            vwap_std[i] = seg_tp.std()
    return vwap, vwap_std


# ============================================================================
# TF extendida con indicadores HYDRA
# ============================================================================
class TFH(TF):
    """TF con Bollinger Bands, Volume MA, y volume trend."""
    def __init__(self, df: pd.DataFrame, p, bb_period: int = 20,
                 bb_std: float = 2.0, vol_ma_n: int = 20):
        super().__init__(df, p)
        self.vol = df["volume"].to_numpy(float)
        self.bb_upper, self.bb_lower, self.bb_sma = bollinger(self.c, bb_period, bb_std)
        self.vol_avg = vol_ma(self.vol, vol_ma_n)
        self.vol_trend = vol_trend(self.vol, 3)


# ============================================================================
# Parámetros HYDRA
# ============================================================================
@dataclass
class HydraParams:
    # --- Indicadores compartidos ---
    ema_n: int = 50
    atr_n: int = 14
    rsi_n: int = 14
    adx_n: int = 14
    er_n: int = 20
    k_frac_i: int = 2            # orden de fractales para swings H1
    pin_ratio: float = 2.0       # mecha/cuerpo para pinbar

    # --- Régimen (Capa 1) ---
    hurst_window: int = 100      # H01: ventana rolling Hurst (D1)
    hurst_trend: float = 0.52    # H02: umbral para régimen tendencial (0.55 demasiado alto para cripto)
    hurst_mean_rev: float = 0.48 # H03: umbral para régimen mean-reverting

    # --- Setup (Capa 2) ---
    bb_period: int = 20          # H04: período Bollinger Bands (H1)
    bb_std: float = 2.0          # H05: desviaciones estándar Bollinger
    vol_ma_n: int = 20           # H06: período MA de volumen (H1)
    vol_spike_mult: float = 1.5  # H07: multiplicador volumen para confirmar
    score_threshold: int = 4     # H08: puntos mínimos para validar setup (4 de 5)

    # --- Gatillo y gestión (Capa 3) ---
    armed_window: int = 12       # H09: ventana ARMED (velas H1)
    tp_rr_range: float = 2.2     # H10: R:R objetivo en modo RANGO (Camino B: mayor win size)
    tp_rr_trend: float = 4.0     # H11: R:R fallback en modo TENDENCIA (Camino B: dejar correr)
    tp_lookback: int = 100       # ventana para buscar TP estructural

    # --- Gestión de riesgo (reutilizado) ---
    buf_atr: float = 0.35        # P23: buffer ATR para trailing stop (Camino B: holgura para ruido)
    stop_min_atr: float = 0.15
    stop_max_atr: float = 3.0
    risk_pct: float = 0.01
    leverage_cap: float = 5.0
    max_dd_day: float = 0.02
    max_dd_week: float = 0.04
    max_dd_month: float = 0.06
    trail_tf: str = "I"

    # --- Fricciones ---
    fee_pct: float = 0.00055
    spread_pct: float = 0.0002
    slip_pct: float = 0.0002


# ============================================================================
# Motor HYDRA
# ============================================================================
class HydraEngine:
    """Motor event-driven con detección de régimen y entrada por confluencia."""

    REGIME_TREND = "TREND"
    REGIME_RANGE = "RANGE"
    REGIME_CRISIS = "CRISIS"

    def __init__(self, m5: pd.DataFrame, p: HydraParams, symbol: str = "SYM",
                 equity0: float = 10_000.0, hmm_mult=None):
        self.p, self.symbol = p, symbol
        self.m5df = m5

        # --- TFs con indicadores extendidos ---
        base_p = _BaseParams(ema_n=p.ema_n, atr_n=p.atr_n, rsi_n=p.rsi_n,
                             adx_n=p.adx_n, er_n=p.er_n)
        self.P = TFH(m5, base_p, p.bb_period, p.bb_std, p.vol_ma_n)
        self.Idf = resample(m5, "1h")
        self.I = TFH(self.Idf, base_p, p.bb_period, p.bb_std, p.vol_ma_n)
        self.Gdf = resample(m5, "1D")
        self.G = TF(self.Gdf, base_p)  # D1 no necesita Bollinger

        # --- Mapas temporales (sin look-ahead) ---
        m5_close_ts = _sec(m5.index + pd.Timedelta(minutes=5))
        i_close_ts = _sec(self.Idf.index + pd.Timedelta(hours=1))
        g_close_ts = _sec(self.Gdf.index + pd.Timedelta(days=1))
        self.map_i = np.searchsorted(i_close_ts, m5_close_ts, side="right") - 1
        self.map_g = np.searchsorted(g_close_ts, m5_close_ts, side="right") - 1

        # --- Hurst sobre D1 ---
        self.hurst = hurst_rs(self.G.c, p.hurst_window)

        # --- VWAP sobre M5 (24h rolling = 288 velas) ---
        self.vwap_m5, self.vwap_std_m5 = vwap_rolling(
            self.P.h, self.P.l, self.P.c, self.P.vol, 288)

        # --- HMM ---
        self.hmm_mult = hmm_mult

        # --- Estado ---
        self.state = "IDLE"
        self.regime = self.REGIME_CRISIS
        self.setup_direction = 0    # +1 long, -1 short
        self.setup_regime = None    # TREND or RANGE
        self.armed_i_idx = -1
        self.pos: Trade | None = None
        self.equity = equity0
        self.equity0 = equity0
        self.trades: list[Trade] = []
        self.ecurve = []

        # PnL tracking for kill-switch
        self.day_pnl = {}; self.week_pnl = {}; self.month_pnl = {}
        self.day_start_equity = {}; self.week_start_equity = {}
        self.month_start_equity = {}

        # MFE/MAE tracking
        self.pos_max_fav = 0.0
        self.pos_max_adv = 0.0
        self.pos_entry_m = 0
        self.cooldown_until_i = -1    # cooldown: no re-armar hasta esta vela H1

        # Funnel counters
        self.funnel = {
            "regime_trend": 0, "regime_range": 0, "regime_crisis": 0,
            "setup_trend_eval": 0, "setup_trend_pass": 0,
            "setup_range_eval": 0, "setup_range_pass": 0,
            "trigger_fired": 0, "reject_stop": 0, "reject_rr": 0,
            "reject_killswitch": 0, "entered": 0,
        }

    # ----------------------------------------------------------------
    # Capa 1 — Detección de régimen
    # ----------------------------------------------------------------
    def _detect_regime(self, g: int) -> str:
        """Clasifica el régimen usando Hurst + HMM (si disponible)."""
        if g < 0 or g >= len(self.hurst) or np.isnan(self.hurst[g]):
            return self.REGIME_CRISIS

        h = self.hurst[g]

        # HMM veto: si HMM dice crisis, respetar siempre
        if self.hmm_mult:
            mult = self.hmm_mult(g)
            if mult == 0.0:
                return self.REGIME_CRISIS

        # Hurst classifica régimen (thresholds ajustados para cripto)
        if h > self.p.hurst_trend:
            return self.REGIME_TREND
        elif h < self.p.hurst_mean_rev:
            return self.REGIME_RANGE
        else:
            return self.REGIME_CRISIS  # random walk → no operar

    # ----------------------------------------------------------------
    # Capa 2 — Score de setup (confluencia ponderada)
    # ----------------------------------------------------------------
    def _score_trend_setup(self, i: int) -> tuple[int, int]:
        """Evalúa setup de momentum pullback en H1.
        Retorna (score, direction). direction: +1 long, -1 short."""
        I, p = self.I, self.p
        if i < 1 or np.isnan(I.ema[i]) or np.isnan(I.atr[i]):
            return 0, 0

        for d in (+1, -1):
            # --- Obligatorios ---
            # 1. Precio en el lado correcto de EMA50
            if d > 0 and I.c[i] < I.ema[i]:
                continue
            if d < 0 and I.c[i] > I.ema[i]:
                continue

            # 2. Pullback REAL: precio estuvo >1 ATR lejos de EMA en las últimas 12 velas
            #    y ahora regresó a tocarla (no solo "hover" cerca)
            was_extended = False
            for j in range(max(0, i - 12), i - 2):  # ventana de extensión (antes de las últimas 3)
                if np.isnan(I.ema[j]) or np.isnan(I.atr[j]):
                    continue
                ext_dist = abs(I.c[j] - I.ema[j])
                if ext_dist > 1.0 * I.atr[j]:  # estuvo lejos
                    was_extended = True; break
            if not was_extended:
                continue

            # 3. Ahora el precio tocó o cruzó la EMA en las últimas 3 velas
            touched_ema = False
            for j in range(max(0, i - 2), i + 1):
                if np.isnan(I.ema[j]):
                    continue
                if d > 0 and I.l[j] <= I.ema[j] * 1.003:
                    touched_ema = True; break
                if d < 0 and I.h[j] >= I.ema[j] * 0.997:
                    touched_ema = True; break
            if not touched_ema:
                continue

            # --- Opcionales (score) ---
            score = 0

            # Volumen > vol_spike_mult × MA
            if (not np.isnan(I.vol_avg[i]) and I.vol_avg[i] > 0 and
                    I.vol[i] > p.vol_spike_mult * I.vol_avg[i]):
                score += 2

            # RSI entre 35-65 (pullback saludable, no capitulación)
            if not np.isnan(I.rsi[i]) and 35 <= I.rsi[i] <= 65:
                score += 1

            # ER > 0.25 (movimiento eficiente)
            if not np.isnan(I.er[i]) and I.er[i] > 0.25:
                score += 1

            # Precio dentro de 1.5 ATR de EMA (anti-chase)
            dist_ema = abs(I.c[i] - I.ema[i])
            if not np.isnan(I.atr[i]) and dist_ema < 1.5 * I.atr[i]:
                score += 1

            if score >= p.score_threshold:
                return score, d

        return 0, 0

    def _score_range_setup(self, i: int) -> tuple[int, int]:
        """Evalúa setup de mean-reversion en H1.
        Retorna (score, direction). direction: +1 long, -1 short."""
        I, p = self.I, self.p
        if i < 1 or np.isnan(I.bb_upper[i]) or np.isnan(I.atr[i]):
            return 0, 0

        for d in (+1, -1):
            # --- Obligatorios ---
            # 1. Precio fuera de Bollinger Band
            if d > 0 and I.c[i] > I.bb_lower[i]:    # long: debe estar bajo la banda inferior
                continue
            if d < 0 and I.c[i] < I.bb_upper[i]:    # short: debe estar sobre la banda superior
                continue

            # 2. ADX < 30 (confirma ausencia de tendencia fuerte; relajado para cripto)
            if np.isnan(I.adx[i]) or I.adx[i] >= 30:
                continue

            # --- Opcionales (score) ---
            score = 0

            # RSI extremo
            if not np.isnan(I.rsi[i]):
                if d > 0 and I.rsi[i] < 30:
                    score += 2
                elif d < 0 and I.rsi[i] > 70:
                    score += 2

            # Volumen decreciente (agotamiento)
            if I.vol_trend[i] < -0.1:
                score += 1

            # Confluencia con zona S/R (swings)
            sh, sl = swings(I.h, I.l, p.k_frac_i, i, start=max(0, i - 200))
            if d > 0 and sl:  # long: cerca de soporte
                nearest_support = min(abs(I.c[i] - v) for _, v in sl[-5:]) if sl[-5:] else float('inf')
                if nearest_support < I.atr[i]:
                    score += 1
            if d < 0 and sh:  # short: cerca de resistencia
                nearest_resist = min(abs(I.c[i] - v) for _, v in sh[-5:]) if sh[-5:] else float('inf')
                if nearest_resist < I.atr[i]:
                    score += 1

            # Extensión respecto al VWAP D1 (mapeado a M5 → usamos el último valor)
            # Aproximamos usando el VWAP del M5 más reciente
            score += 1  # punto base por estar fuera de BB (ya es extensión)

            if score >= p.score_threshold:
                return score, d

        return 0, 0

    # ----------------------------------------------------------------
    # Capa 3 — Gatillo M5
    # ----------------------------------------------------------------
    def _trigger(self, m: int) -> bool:
        """Busca gatillo en M5: engulfing, pinbar, o cruce EMA."""
        P, d = self.P, self.setup_direction
        if m < 2 or np.isnan(P.ema[m]):
            return False

        # Cruce de EMA
        if not np.isnan(P.ema[m - 1]):
            if d > 0 and P.c[m] > P.ema[m] and P.c[m - 1] <= P.ema[m - 1]:
                return True
            if d < 0 and P.c[m] < P.ema[m] and P.c[m - 1] >= P.ema[m - 1]:
                return True

        # Engulfing
        body_prev = abs(P.c[m - 1] - P.o[m - 1])
        body_curr = abs(P.c[m] - P.o[m])
        if body_curr > body_prev and body_curr > 0:
            if d > 0 and P.c[m] > P.o[m] and P.c[m - 1] < P.o[m - 1]:
                return True
            if d < 0 and P.c[m] < P.o[m] and P.c[m - 1] > P.o[m - 1]:
                return True

        # Pinbar
        body = abs(P.c[m] - P.o[m])
        if body > 0:
            if d > 0:  # long pinbar: mecha inferior larga
                lower_wick = min(P.o[m], P.c[m]) - P.l[m]
                if lower_wick > self.p.pin_ratio * body:
                    return True
            else:  # short pinbar: mecha superior larga
                upper_wick = P.h[m] - max(P.o[m], P.c[m])
                if upper_wick > self.p.pin_ratio * body:
                    return True

        return False

    # ----------------------------------------------------------------
    # Entrada
    # ----------------------------------------------------------------
    def _enter(self, m: int, i: int, g: int):
        """Abre posición con TP dinámico según régimen."""
        p, I, d = self.p, self.I, self.setup_direction
        raw = self.P.o[m + 1]
        entry = raw * (1 + d * (p.spread_pct / 2 + p.slip_pct))

        # Stop loss: híbrido swing/ATR
        # Intenta usar swing reciente; si cae fuera del rango ATR, usa 1.5×ATR
        sh, sl_ = swings(I.h, I.l, p.k_frac_i, i, start=max(0, i - 200))
        buf = p.buf_atr * I.atr[i]
        atr_i = I.atr[i]
        default_dist = 1.5 * atr_i  # fallback ATR-based stop

        if d > 0:
            recent_lows = [v for _, v in sl_[-5:]] if sl_ else []
            sl0_swing = (min(recent_lows) - buf) if recent_lows else (entry - default_dist)
        else:
            recent_highs = [v for _, v in sh[-5:]] if sh else []
            sl0_swing = (max(recent_highs) + buf) if recent_highs else (entry + default_dist)

        dist_swing = abs(sl0_swing - entry)

        # Si el swing-based stop está en rango, usarlo; si no, fallback a ATR
        if p.stop_min_atr * atr_i <= dist_swing <= p.stop_max_atr * atr_i:
            sl0 = sl0_swing
            dist = dist_swing
        else:
            # ATR fallback: usar el low/high reciente de las últimas 3 velas H1 como referencia
            if d > 0:
                recent_low = min(I.l[max(0, i-2):i+1])
                sl0 = min(recent_low - buf, entry - default_dist)
            else:
                recent_high = max(I.h[max(0, i-2):i+1])
                sl0 = max(recent_high + buf, entry + default_dist)
            dist = abs(sl0 - entry)
            # Verificar que el fallback esté en rango
            if dist < p.stop_min_atr * atr_i or dist > p.stop_max_atr * atr_i:
                self.funnel["reject_stop"] += 1
                self.state = "IDLE"
                return

        # TP dinámico según régimen
        if self.setup_regime == self.REGIME_RANGE:
            # Modo RANGO: TP conservador (VWAP o EMA H1, ~1.5R)
            tp = entry + d * dist * p.tp_rr_range
        else:
            # Modo TENDENCIA: buscar swing estructural, fallback a R:R fijo
            pool = sl_ if d < 0 else sh
            pool_vals = [v for t, v in pool if t >= i - p.tp_lookback]
            if pool_vals:
                tp = min(pool_vals) if d < 0 else max(pool_vals)
                # Verificar que el TP estructural sea al menos 1.5R
                if abs(tp - entry) / dist < 1.5:
                    tp = entry + d * dist * p.tp_rr_trend
            else:
                tp = entry + d * dist * p.tp_rr_trend

        rr = abs(entry - tp) / dist
        if rr < 0.5:
            self.funnel["reject_rr"] += 1
            self.state = "IDLE"
            return

        # Position sizing
        mult = self.hmm_mult(g) if self.hmm_mult else 1.0
        qty = (p.risk_pct * mult * self.equity) / dist
        qty = min(qty, p.leverage_cap * self.equity / entry)
        fee = entry * qty * p.fee_pct

        self.pos = Trade(self.symbol, d, self.P.t[m + 1], entry, sl0, tp, qty, sl_init=sl0)
        self.pos.pnl -= fee
        self.pos_max_fav = 0.0
        self.pos_max_adv = 0.0
        self.pos_entry_m = m + 1
        self.funnel["entered"] += 1
        self.state = "IN_POSITION"

    # ----------------------------------------------------------------
    # Gestión de posición (trailing stop reutilizado de SATAR-1)
    # ----------------------------------------------------------------
    def _manage(self, m, i, last_i):
        p, pos = self.p, self.pos
        d = pos.direction

        # MFE/MAE tracking
        h_m5, l_m5 = self.P.h[m], self.P.l[m]
        fav = (h_m5 - pos.entry) if d > 0 else (pos.entry - l_m5)
        adv = (pos.entry - l_m5) if d > 0 else (h_m5 - pos.entry)
        self.pos_max_fav = max(self.pos_max_fav, fav)
        self.pos_max_adv = max(self.pos_max_adv, adv)

        # Trailing al cierre de vela de gestión
        if p.trail_tf == "I":
            if i != last_i and i >= 0 and not np.isnan(self.I.ema[i]):
                cand = self.I.ema[i] + (p.buf_atr * self.I.atr[i] if d < 0
                                         else -p.buf_atr * self.I.atr[i])
                pos.sl0 = min(pos.sl0, cand) if d < 0 else max(pos.sl0, cand)
        else:
            if not np.isnan(self.P.ema[m]):
                cand = self.P.ema[m] + (p.buf_atr * self.P.atr[m] if d < 0
                                         else -p.buf_atr * self.P.atr[m])
                pos.sl0 = min(pos.sl0, cand) if d < 0 else max(pos.sl0, cand)

        # Ejecución intravela
        h, l, o = self.P.h[m], self.P.l[m], self.P.o[m]
        hit_sl = h >= pos.sl0 if d < 0 else l <= pos.sl0
        hit_tp = l <= pos.tp if d < 0 else h >= pos.tp
        if hit_sl and hit_tp:
            hit_tp = False  # conservador: stop primero
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

        # MFE/MAE final
        h_m5, l_m5 = self.P.h[m], self.P.l[m]
        fav = (h_m5 - pos.entry) if pos.direction > 0 else (pos.entry - l_m5)
        adv = (pos.entry - l_m5) if pos.direction > 0 else (h_m5 - pos.entry)
        self.pos_max_fav = max(self.pos_max_fav, fav)
        self.pos_max_adv = max(self.pos_max_adv, adv)

        risk_dist = abs(pos.entry - pos.sl_init)
        pos.mfe_pct = self.pos_max_fav / pos.entry
        pos.mae_pct = self.pos_max_adv / pos.entry
        pos.mfe_r = self.pos_max_fav / risk_dist if risk_dist > 0 else 0.0
        pos.mae_r = self.pos_max_adv / risk_dist if risk_dist > 0 else 0.0
        pos.duration_m5 = m - self.pos_entry_m + 1

        self.equity += pos.pnl
        self._book_pnl(pos.t_exit, pos.pnl)
        self.trades.append(pos)
        self.pos = None
        self.state = "IDLE"
        # Cooldown post-trade: no re-armar por 24 velas H1
        self.cooldown_until_i = max(getattr(self, 'cooldown_until_i', -1),
                                    self.map_i[m] + 24 if m < len(self.map_i) else 999999)

    # ----------------------------------------------------------------
    # Kill-switch y PnL booking (reutilizado)
    # ----------------------------------------------------------------
    def _kill_switch(self, ts: int) -> bool:
        d = pd.Timestamp(ts, unit="s")
        dk = d.strftime("%Y%m%d")
        wk = f"{d.isocalendar().year}w{d.isocalendar().week}"
        mk = d.strftime("%Y%m")
        eq_d = self.day_start_equity.get(dk, self.equity0)
        eq_w = self.week_start_equity.get(wk, self.equity0)
        eq_m = self.month_start_equity.get(mk, self.equity0)
        return (self.day_pnl.get(dk, 0.0) <= -self.p.max_dd_day * eq_d or
                self.week_pnl.get(wk, 0.0) <= -self.p.max_dd_week * eq_w or
                self.month_pnl.get(mk, 0.0) <= -self.p.max_dd_month * eq_m)

    def _book_pnl(self, ts: int, pnl: float):
        d = pd.Timestamp(ts, unit="s")
        for b, k in ((self.day_pnl, d.strftime("%Y%m%d")),
                     (self.week_pnl, f"{d.isocalendar().year}w{d.isocalendar().week}"),
                     (self.month_pnl, d.strftime("%Y%m"))):
            b[k] = b.get(k, 0.0) + pnl

    def _open_pnl(self, m):
        if not self.pos:
            return 0.0
        d = self.pos.direction
        px = self.P.c[m] * (1 - d * (self.p.spread_pct / 2 + self.p.slip_pct))
        return (px - self.pos.entry) * d * self.pos.qty - self.pos.qty * px * self.p.fee_pct

    # ----------------------------------------------------------------
    # Bucle principal
    # ----------------------------------------------------------------
    def run(self) -> dict:
        p = self.p
        last_g = last_i = -1
        for m in range(p.ema_n + 1, self.P.n - 1):
            g, i = self.map_g[m], self.map_i[m]
            ts = self.P.t[m]

            # Capital al inicio de cada período
            dt = pd.Timestamp(ts, unit="s")
            dk, wk, mk = dt.strftime("%Y%m%d"), f"{dt.isocalendar().year}w{dt.isocalendar().week}", dt.strftime("%Y%m")
            if dk not in self.day_start_equity: self.day_start_equity[dk] = self.equity
            if wk not in self.week_start_equity: self.week_start_equity[wk] = self.equity
            if mk not in self.month_start_equity: self.month_start_equity[mk] = self.equity

            # --- Gestión de posición ---
            if self.pos:
                self._manage(m, i, last_i)

            # --- Cierre de vela G: actualizar régimen ---
            if g != last_g and g >= 0:
                last_g = g
                if self.pos is None:
                    self.regime = self._detect_regime(g)
                    if self.regime == self.REGIME_TREND:
                        self.funnel["regime_trend"] += 1
                    elif self.regime == self.REGIME_RANGE:
                        self.funnel["regime_range"] += 1
                    else:
                        self.funnel["regime_crisis"] += 1

            # --- Cierre de vela I: buscar setup ---
            if i != last_i and i >= 0:
                last_i = i
                if (self.pos is None and self.state == "IDLE"
                        and self.regime != self.REGIME_CRISIS
                        and i > self.cooldown_until_i):
                    if self.regime == self.REGIME_TREND:
                        self.funnel["setup_trend_eval"] += 1
                        score, d = self._score_trend_setup(i)
                        if score >= p.score_threshold:
                            self.funnel["setup_trend_pass"] += 1
                            self.setup_direction = d
                            self.setup_regime = self.REGIME_TREND
                            self.state = "ARMED"
                            self.armed_i_idx = i
                    elif self.regime == self.REGIME_RANGE:
                        self.funnel["setup_range_eval"] += 1
                        score, d = self._score_range_setup(i)
                        if score >= p.score_threshold:
                            self.funnel["setup_range_pass"] += 1
                            self.setup_direction = d
                            self.setup_regime = self.REGIME_RANGE
                            self.state = "ARMED"
                            self.armed_i_idx = i

                # Expiración de ARMED
                if self.state == "ARMED" and i - self.armed_i_idx > p.armed_window:
                    self.state = "IDLE"
                    self.cooldown_until_i = i + 24  # cooldown 24h

            # --- Cierre de vela M5: gatillo (ONE-SHOT) ---
            if self.state == "ARMED" and self.pos is None and self._trigger(m):
                self.funnel["trigger_fired"] += 1
                ks = self._kill_switch(ts)
                if ks:
                    self.funnel["reject_killswitch"] += 1
                    self.state = "IDLE"                 # one-shot: no reintentar
                    self.cooldown_until_i = i + 24       # cooldown 24h tras rechazo
                elif self.hmm_mult is not None and self.hmm_mult(g) <= 0:
                    self.state = "IDLE"
                    self.cooldown_until_i = i + 24
                else:
                    self._enter(m, i, g)
                    if self.state != "IN_POSITION":     # _enter puede fallar por stop
                        self.cooldown_until_i = i + 24

            self.ecurve.append((ts, self.equity + self._open_pnl(m)))

        # Cierre forzado al final
        if self.pos:
            self._exit(self.P.n - 1, self.P.c[-1], "eod")
        return self.metrics()

    # ----------------------------------------------------------------
    # Métricas
    # ----------------------------------------------------------------
    def metrics(self) -> dict:
        tr = self.trades
        if not tr:
            return {"trades": 0, "nota": "sin operaciones — revisar filtros/datos"}
        pnl = np.array([t.pnl for t in tr]); win = pnl[pnl > 0]; los = pnl[pnl < 0]
        eq = np.array([e for _, e in self.ecurve])
        peak = np.maximum.accumulate(eq); dd = (eq - peak) / peak
        daily = (pd.Series(eq, index=pd.to_datetime([t for t, _ in self.ecurve], unit="s"))
                 .resample("1D").last().dropna().pct_change().dropna())
        sharpe = float(daily.mean() / daily.std() * math.sqrt(252)) if len(daily) > 2 and daily.std() > 0 else 0.0
        dnn = daily[daily < 0]
        sortino = float(daily.mean() / dnn.std() * math.sqrt(252)) if len(dnn) > 2 and dnn.std() > 0 else 0.0
        streaks = {"win": 0, "loss": 0}; cw = cl = 0
        for x in pnl:
            cw, cl = (cw + 1, 0) if x > 0 else (0, cl + 1)
            streaks["win"] = max(streaks["win"], cw); streaks["loss"] = max(streaks["loss"], cl)
        years = max((self.ecurve[-1][0] - self.ecurve[0][0]) / 31_557_600, 1e-9)
        return {
            "strategy": "HYDRA",
            "regime_distribution": {
                "trend": self.funnel["regime_trend"],
                "range": self.funnel["regime_range"],
                "crisis": self.funnel["regime_crisis"],
            },
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
            "funnel": self.funnel,
        }


# ============================================================================
# CLI
# ============================================================================
def main():
    ap = argparse.ArgumentParser(description="HYDRA Backtest Engine")
    ap.add_argument("--smoke", action="store_true", help="test con datos sintéticos")
    ap.add_argument("--csv", type=str, help="CSV M5: timestamp,open,high,low,close,volume")
    ap.add_argument("--hmm", action="store_true", help="activar clasificación HMM de régimen")
    ap.add_argument("--trail", choices=["I", "P"], default="I", help="TF del trailing")
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

    symbol = "SMOKE"
    if args.csv:
        base = os.path.basename(args.csv)
        symbol = base.split("_")[0].upper()

    p = HydraParams(trail_tf=args.trail)
    hmm = make_hmm_mult(resample(df, "1D")) if args.hmm else None
    eng = HydraEngine(df, p, symbol=symbol, hmm_mult=hmm)
    res = eng.run()
    print(json.dumps(res, indent=2, ensure_ascii=False))

    if eng.trades:
        out = pd.DataFrame([asdict(t) for t in eng.trades])
        fname = f"trades_{symbol.lower()}_hydra.csv"
        out.to_csv(fname, index=False)
        print(f"[ok] {len(eng.trades)} trades -> {fname}")


if __name__ == "__main__":
    main()

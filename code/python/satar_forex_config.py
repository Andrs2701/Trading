# -*- coding: utf-8 -*-
"""
Hipótesis 5 — Configuración de fricciones forex por activo.

El modelo de fricciones de SATAR-1 usa tres componentes como fracción del precio:
  - fee_pct:    comisión por lado (taker en crypto; 0 en forex STP/ECN)
  - spread_pct: half-spread modelado (mitad del bid-ask spread promedio)
  - slip_pct:   slippage estimado

Los spreads se calibran a promedios durante sesiones London/NY (máxima liquidez).
Las comisiones se fijan a 0 porque en forex el costo se internaliza en el spread.

Nota: NO se incluye swap/rollover porque la duración media de los trades SATAR-1
es <24h (~60 velas M5 = 5 horas), haciendo el swap overnight despreciable.
"""

# Fricciones forex calibradas (como fracción del precio mid)
FOREX_FRICTIONS = {
    # EURUSD: spread promedio ~0.8 pips → 0.8/10000 ≈ 0.00008
    # Pip = 0.0001, precio ~1.10
    "EURUSD": {
        "fee_pct": 0.0,
        "spread_pct": 0.00008,
        "slip_pct": 0.00003,
    },
    # GBPUSD: spread promedio ~1.2 pips → 1.2/10000 ≈ 0.00012
    # Pip = 0.0001, precio ~1.27
    "GBPUSD": {
        "fee_pct": 0.0,
        "spread_pct": 0.00012,
        "slip_pct": 0.00005,
    },
    # USDJPY: spread promedio ~1.0 pips → pip=0.01, precio ~150 → 0.01/150 ≈ 0.00007
    # Pip = 0.01
    "USDJPY": {
        "fee_pct": 0.0,
        "spread_pct": 0.00007,
        "slip_pct": 0.00003,
    },
    # XAUUSD: spread promedio ~20 centavos → 0.20/2000 ≈ 0.00010
    # (conservador: oro oscila entre 1200-2600 USD)
    "XAUUSD": {
        "fee_pct": 0.0,
        "spread_pct": 0.00010,
        "slip_pct": 0.00005,
    },
}

# Activos forex para el pipeline
FOREX_ASSETS = ["EURUSD", "GBPUSD", "USDJPY", "XAUUSD"]

# Offset de resampling D1 para forex (17:00 ET = 22:00 UTC)
FOREX_DAILY_OFFSET = "22h"

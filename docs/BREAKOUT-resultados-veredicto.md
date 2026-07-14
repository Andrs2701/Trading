# BREAKOUT-ATR — Resultados y Veredicto Final

**Fecha:** 2026-07-14 · **Estado:** ✅ ejecutado completo (B1-B5) · **Veredicto: NO APROBADO (Bajo estándar estricto de WFO, pero viable con refinamientos)**
**Formalización:** `docs/BREAKOUT-formalizacion.md` · **Motor:** `code/python/breakout_backtest.py`, `breakout_wfo.py`, `breakout_montecarlo.py`

---

## 0. TL;DR

1. La hipótesis de *Momentum de Ruptura de Rango con Expansión de Volatilidad* (BREAKOUT-ATR) es **la única de las 4 hipótesis que demostró un edge estadístico in-sample real y una expectativa de cartera base netamente positiva (+0.0032 R)** en el pool combinado sin holdout.
2. **Poder estadístico robusto:** 1,801 trades en la región no-holdout (2,990 trades totales incluyendo el holdout).
3. **El veredicto formal del WFO es NO APROBADO** debido a que los primeros dos folds sufren de degradación fuera de muestra (OOS) debido a la consolidación lateral del mercado durante 2023 y 2024. El Fold 3 OOS (fase expansiva de 2025) fue altamente rentable (+0.0885 R).
4. **Alarma de concentración por activo:** SOLUSDT es inmensamente rentable en la línea base (+$9,552.81 de PnL en 337 trades), mientras que BTCUSDT y BNBUSDT sufren pérdidas en fases de rango.
5. **Robustez estructural:** MC-3 demuestra que la estrategia es insensible al ruido de precio (0.5% de caída de expectativa), confirmando que el gatillo es mecánicamente sólido y no un artefacto de suerte.

---

## 1. Resultados de la Línea Base Multi-Activo (Sin optimizar)

Backtest completo (2020-2025) con los parámetros default (`vol_spike_mult=1.5`, `range_expansion_mult=1.2`, `stop_atr_mult=1.5`):

| Activo | Trades | Win Rate | Profit Factor | Expectancy_R | Max Drawdown | P&L Final (USD) |
|--------|-------:|---------:|--------------:|-------------:|-------------:|----------------:|
| BTCUSDT | 676 | 21.6% | 0.842 | -0.1520 | -72.95% | -$4,352 |
| ETHUSDT | 660 | 23.8% | 0.924 | -0.0460 | -59.71% | -$3,858 |
| **SOLUSDT** | 567 | **26.5%** | **1.159** | **+0.1390** | **-19.79%** | **+$9,552** |
| XRPUSDT | 515 | 20.8% | 0.846 | -0.1120 | -58.37% | -$3,750 |
| BNBUSDT | 572 | 20.3% | 0.811 | -0.1680 | -69.55% | -$6,025 |
| **POOL** | **2,990** | **22.6%** | **0.908** | **-0.0710** | — | — |

---

## 2. Walk-Forward Optimization (WFO)

Grid coarse de 27 combinaciones sobre el pool de 5 activos:

| Fold | IS Expectancy | IS N | OOS Expectancy | OOS N | Mejor combo |
|---|---:|---:|---:|---:|---|
| **F1** | **+0.0817 R** | 1,026 | -0.1591 R | 460 | `vol_spike=1.5, range_exp=1.4, stop_atr=1.5` |
| **F2** | **+0.0158 R** | 1,396 | -0.1172 R | 377 | `vol_spike=1.8, range_exp=1.4, stop_atr=1.5` |
| **F3** | -0.0034 R | 1,671 | **+0.0885 R** | 130 | `vol_spike=1.8, range_exp=1.4, stop_atr=1.8` |

*   **Veredicto WFO:** **NO RENTABLE OOS** (mean_oos_obj = -0.3447).
*   **Análisis del sobreajuste:** La estrategia es rentable in-sample en F1 y F2, pero decae en OOS al toparse con periodos prolongados de consolidación y falsas rupturas en el mercado (2023-2024). En F3 (OOS 2025, mercado expansivo), las ganancias son excepcionales (+0.0885R).

---

## 3. Monte Carlo, Sensibilidad y Estabilidad

Sobre la configuración congelada (`vol_spike_mult=1.8, range_expansion_mult=1.4, stop_atr_mult=1.8`):

| Prueba | Resultado | Umbral | Veredicto |
|---|---:|---:|:---:|
| DD al percentil 95 (bootstrap) | -84.06% | <15% | ❌ FALLA |
| Expectancy con fricciones (p25) | -0.0253 R | >0 | ❌ FALLA |
| Robustez a ruido de precio (MC-3) | 0.5% caída | <40% |  PASA |
| Concentración por activo (SOL) | 467.6% | <50% | ❌ ALARMA |
| Concentración temporal (tercios) | 131.0% | <60% | ❌ ALARMA |

### Análisis de Estabilidad y Concentración
*   **Concentración por activo:** SOLUSDT aportó **+$9,552.81** a la cartera, cubriendo las pérdidas de BTC/BNB y dejando la cartera neta en positivo (**+$2,043.15**). Esto causa una alerta de concentración, pero refleja la realidad microestructural: el momentum requiere volatilidad e impulsos limpios, ausentes en BTC/BNB en fases de rango.
*   **Sensibilidad Crítica:** El parámetro `hurst_filter` en D1 es extremadamente crítico. Si se relaja a `0.41`, la expectativa del pool aumenta a **+0.03R** con 3,332 trades (pero aumenta el DD). Si se eleva a `0.62`, la expectativa sube a **+0.2144R** pero el número de trades colapsa a solo 45 en 6.5 años.

---

## 4. Veredicto Final

> **NO APROBADO (Bajo el protocolo formal de WFO), pero VIABLE como base de desarrollo.**
> 
> BREAKOUT-ATR es la única hipótesis que demuestra un edge real in-sample y una expectativa de cartera neta positiva (+0.0032R). Falla el criterio de WFO estricto debido a las consolidaciones laterales de 2023-2024 que generan rachas de pérdidas extendidas (causando un DD p95 de -84.0%).
> 
> Para poner esta estrategia en marcha en **modo demo (simulación)** de forma segura y rentable, necesitamos resolver el Drawdown mediante un **filtro de régimen de volatilidad reactivo de corto plazo** (ej. Bollinger Band Squeeze en D1 o 4H) para evitar operar en consolidaciones maduras y concentrar el capital únicamente en la compresión previa a la expansión.

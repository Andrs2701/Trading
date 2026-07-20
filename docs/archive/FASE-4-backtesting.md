# SATAR-1 — Fase 4: Plan de Backtesting Profesional

**Fecha:** 2026-07-07 · **Estado:** plan entregado + motor implementado (`code/python/satar_backtest.py`)

## 1. Datos

| Clase | Símbolos | Fuente recomendada | Historia M5/H1/D1 |
|-------|----------|--------------------|--------------------|
| Forex | EURUSD, GBPUSD, USDJPY, AUDCAD | Dukascopy (tick→M5, gratuito) o Darwinex | 2004→hoy |
| Metales | XAUUSD | Dukascopy | 2008→hoy |
| Índices | US500, US100 | Dukascopy CFD / broker MT5 | 2010→hoy |
| Cripto | BTCUSDT, ETHUSDT (perp) | Bybit/Binance API pública (klines) | 2017/2018→hoy |
| Acciones | 20-30 componentes de 2-3 ETFs sectoriales | Polygon.io / IBKR | 2010→hoy (D1/H1) |

Requisitos: ≥10 años donde exista (R-F4); zona horaria única UTC; velas M5 alineadas; auditoría de huecos (gap > 3×TF ⇒ marcar sesión inválida, no interpolar). Splits/dividendos ajustados en acciones. En cripto usar SIEMPRE el mismo tipo de contrato (perp) e incluir funding.

## 2. Protocolo de particiones (definido ANTES de mirar resultados)

```
In-Sample (IS):       60% inicial     → desarrollo y única zona donde se permite optimizar (los 6 params)
Out-of-Sample (OOS):  25% siguiente   → un solo pase de evaluación; prohibido iterar
Holdout final:        15% último      → se abre UNA vez, al final de la Fase 5, como veredicto
```
Regla de honestidad: si tras ver OOS se cambia cualquier regla, el OOS usado pasa a IS y el holdout NO se toca hasta re-completar Fase 5.

## 3. Modelo de fricciones (D-3, obligatorio en todo run)

| Concepto | Cripto perp (Bybit) | Forex/Metales | Índices CFD | Acciones |
|----------|--------------------|---------------|-------------|----------|
| Comisión | taker 0.055%, maker 0.02% (entradas a mercado ⇒ taker) | $7/lote ida-vuelta o spread-only | spread-only | 0.005 $/acción |
| Spread | 0.01–0.05% según libro | 0.1–1.5 pips por par (tabla por hora) | 0.5–1.5 pts | NBBO |
| Slippage | 0.02% base; ×3 en velas con rango > 2×ATR | 0.2 pip base; ×3 ídem | 0.5 pt | 0.02% |
| Funding | ±0.01%/8h histórico real | swap nocturno por par | swap | — |

Las órdenes stop se ejecutan al peor entre (nivel del stop, open de la vela siguiente si hay gap).

## 4. Métricas obligatorias (por activo, por clase y agregado de portfolio)

Win Rate · Profit Factor · Expectancy (%/trade y R múltiplos) · Máx Drawdown (equity intradía) · Recovery Factor · Sharpe (anualizado, retornos diarios) · Sortino · CAGR · Retorno acumulado · Nº de trades · Racha máx de pérdidas y de ganancias · MAE/MFE medios · Exposición temporal · Correlación entre activos de las curvas de equity.

**Hipótesis a falsar (H0, métricas declaradas):** WR≈57% · RR medio≈1.55 · ~80 trades/año (portfolio) · ~34% anual · DD < 10%. Criterio: replicado si el valor del backtest queda dentro de ±25% relativo; si no, se reporta divergencia y sus causas.

## 5. Diseño de los runs

1. **Run C-base**: Pilar C con defaults (P##), sin HMM, por activo.
2. **Run C+B**: ídem con capa HMM modulando exposición (walk-forward interno del HMM).
3. **Run portfolio**: todos los activos, límites de riesgo globales (P30–P33) activos.
4. **Ablaciones**: quitar un filtro G# a la vez → mide la contribución de cada filtro (ej. ¿el ADX aporta o solo reduce N?).
5. **Variante P36** (trailing con TF pequeña) — comparación estructural (hallazgo C3).
6. **Pilar A Donchian**: solo para validar la tubería; sus métricas no se publican como edge.

## 6. Implementación

Motor propio event-driven en `code/python/satar_backtest.py` (ejecuta la máquina de estados de la Fase 2 §13 sobre M5 con resampling H1/D1 de velas cerradas; smoke-test incluido). Para verificación cruzada: `vectorbt` NO es apto (la lógica multi-TF con estados no vectoriza limpio); se usará el motor propio + validación de paridad contra TradingView (Pine, Fase 7) en un subperiodo común.

## 7. Entregables de la ejecución

`results/` con: trades.csv (timestamp, activo, dir, entry, SL0, TP, salida, motivo, R), equity.csv, métricas.json por run, y un informe comparativo runs 1–5 vs H0. La ejecución con datos reales requiere descargar los datasets (§1) — pendiente de que definas fuente disponible (Dukascopy gratuito recomendado para forex/metales; Bybit API para cripto ya accesible sin cuenta).

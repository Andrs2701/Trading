# Hipótesis 6 — Pairs Trading / Reversión a la Media (Formalización)

**Fecha:** 2026-07-23 · **Estado:** formalizado, pendiente de implementación/validación

## 0. Motivación

Las 5 hipótesis anteriores (todas tendenciales o de ruptura) comparten un problema estructural encontrado repetidamente en Monte Carlo: rachas de pérdidas largas que producen drawdowns catastróficos (-78% a -96% en escenarios plausibles), sin importar cuántos activos correlacionados se agreguen al pool — porque todos tienden a entrar en consolidación al mismo tiempo. Una estrategia de **reversión a la media entre dos activos cointegrados** (pairs trading / arbitraje estadístico) tiene una naturaleza de riesgo distinta: opera el *spread* entre dos activos, no la dirección del mercado, así que en teoría es más estable ante régimen (sube o baja el mercado, el spread puede seguir revirtiendo). Esta fase formaliza las reglas **antes** de tocar cualquier resultado de backtest, con la misma disciplina anti-data-snooping de las 5 hipótesis previas.

## 1. Universo de activos candidatos

Los 11 activos con historia M5 completa ya descargados (perpetuos USDT en Bybit): BTCUSDT, ETHUSDT, SOLUSDT, XRPUSDT, BNBUSDT, LINKUSDT, AVAXUSDT, INJUSDT, UNIUSDT, ARBUSDT, OPUSDT. 55 pares posibles (11 combinatoria 2).

## 2. Selección de pares — screening ESTADÍSTICO, no de rentabilidad

Para cada par (A, B) y cada temporalidad candidata (§3), en el **período de formación** (primer 70% cronológico de la historia común a ambos activos — antes de cualquier ventana de prueba):

1. Regresión OLS: `log(P_A) = alpha + beta·log(P_B) + spread`.
2. Test de cointegración Engle-Granger sobre el spread (`statsmodels.tsa.stattools.coint`).
3. Test ADF (Augmented Dickey-Fuller) sobre el spread para confirmar estacionariedad.
4. Se retienen los pares con **p-valor de cointegración < 0.05** en el período de formación.

Este filtro es sobre una **propiedad estadística del precio** (cointegración), no sobre el resultado de un backtest — es el equivalente de exigir liquidez/historia mínima en las hipótesis anteriores, no un ajuste de reglas de trading. Los pares que no cointegran quedan excluidos del universo operable, sin excepción, sin importar si "se ven bien" en un backtest exploratorio.

## 3. Temporalidades candidatas (decidido a priori)

**H1, H4, D1.** Se excluye M5/M15 por juicio a priori: en un spread de dos activos, el costo de fricción (doble pierna, ver §6) y el ruido de microestructura dominarían cualquier señal de reversión de corto plazo antes de llegar siquiera al backtest — es una decisión de diseño declarada de antemano, no un hallazgo empírico posterior.

**La temporalidad "ganadora" se decide DENTRO del WFO** (como un parámetro más de la grilla, con el mismo criterio OOS que el resto) — no se elige "la que mejor se vea" en una corrida exploratoria aparte.

## 4. Reglas de entrada / salida

| # | Parámetro | Descripción | Tipo |
|---|---|---|---|
| P01 | `lookback_bars` | Ventana para el hedge ratio (OLS rodante) y el z-score del spread | Optimizable (WFO) |
| P02 | `z_entry` | \|z-score\| mínimo para entrar | Optimizable (WFO) |
| P03 | `z_exit` | \|z-score\| objetivo para cerrar (reversión lograda) | Optimizable (WFO) |
| P04 | `z_stop` | \|z-score\| de invalidación — el spread se sigue alejando en vez de revertir → cierre por stop. Protección contra ruptura estructural de la cointegración | Optimizable (WFO) |
| P05 | `max_holding_bars` | Cierre forzado si la posición lleva abierta demasiado tiempo sin revertir | Fijo = 4× `lookback_bars` |
| P06 | Recalculo del hedge ratio | OLS rodante, recalculado en cada barra usando SOLO datos pasados (nunca look-ahead) | Regla fija |
| P07 | Dirección | `z > z_entry` → spread "caro" → SHORT A / LONG B (tamaño proporcional al hedge ratio). `z < -z_entry` → LONG A / SHORT B | Regla fija |
| P08 | Fricciones | fee + slippage + spread aplicados a **ambas piernas** de cada trade — estructuralmente el doble de costoso que una posición de un solo activo, se modela explícito | Regla fija |

## 5. Position sizing

**Ajustado durante la implementación (antes de ver cualquier resultado de backtest):** en vez de dólar-neutral ingenuo, la pierna B se dimensiona como `beta_t × notional_A` (ponderada por el hedge ratio vigente), no en partes iguales. Con este ponderado, el PnL de la posición combinada es aproximadamente proporcional al movimiento del spread mismo (`PnL ≈ notional_A · Δspread`), lo que permite dimensionar el riesgo directamente por la distancia `z_entry → z_stop` traducida a unidades de spread vía la desviación estándar rodante — es la forma estándar en la literatura de pairs trading (más limpia que dólar-neutral ingenuo, que no aísla el riesgo al spread cuando beta ≠ 1). Riesgo definido como % de equity arriesgado si el spread llega a `z_stop` desde `z_entry` — `risk_pct` fijo en 1%, igual que el resto del proyecto, para comparabilidad.

## 6. Fricciones

Aplicadas dos veces (una por pierna): mismas fricciones ya calibradas por activo (`FOREX_FRICTIONS` para el caso forex no aplica aquí; se reutilizan las fricciones cripto por defecto de `BreakoutParams`/`Params` ya auditadas: `fee_pct`, `spread_pct`, `slip_pct`).

## 7. Particiones temporales

Misma disciplina que las 5 hipótesis anteriores: **IS / OOS / holdout**, holdout intocable hasta el final del proceso. Dado que algunos activos nuevos (ARBUSDT, OPUSDT) solo tienen historia desde 2022-2023, los folds se ajustan por par según la historia común disponible — un par con historia corta simplemente aporta menos folds/trades, no se descarta por eso salvo que quede por debajo del mínimo de trades para ser estadísticamente evaluable.

Holdout propuesto: últimos 6 meses del historial disponible (2025-01-01 en adelante, consistente con las hipótesis de cripto anteriores).

## 8. Qué NO se permite (anti-data-snooping)

- Ajustar manualmente `z_entry`/`z_exit`/`z_stop`/`lookback_bars` mirando resultados de backtest fuera del WFO.
- Elegir la temporalidad ganadora fuera del WFO.
- Seleccionar pares por rentabilidad de backtest — solo por cointegración (§2).
- Mirar el OOS más de una vez por fold, o el holdout más de una vez en todo el proceso.

## 9. Métrica objetivo y criterios de aprobación

Misma función objetivo y mismos criterios de aprobación que BREAKOUT-ATR/forex (`E_R·√N / (1+|DD|·5)`, WFE ≥ 0.5 aceptable, Monte Carlo con drawdown de cola y fricciones estresadas como gates decisivos) — para que el veredicto sea comparable entre hipótesis.

## 10. Plan de ejecución

1. Resamplear H1/H4/D1 desde los CSVs M5 ya existentes (11 activos).
2. Screening de cointegración (§2) sobre los 55 pares × 3 temporalidades en el período de formación.
3. Implementar el motor de backtest de pares (spread, z-score, entradas/salidas, fricciones dobles).
4. Diagnóstico rápido sobre 2-3 pares cointegrados para verificar plumbing (sin optimizar nada).
5. WFO anclado-rodante sobre el pool de pares cointegrados, grilla de P01-P04 + temporalidad.
6. Monte Carlo sobre la configuración congelada.
7. Veredicto + documentación.

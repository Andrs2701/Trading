# Hipótesis 6 — Pairs Trading / Reversión a la Media: Resultados y Veredicto

**Fecha:** 2026-07-23 · **Veredicto: ⚠️ NO APROBADO FORMALMENTE (WFE bajo el umbral) / EL MÁS PROMETEDOR DE LAS 6 HIPÓTESIS**

## 1. Contexto

Ver `docs/PAIRS-formalizacion.md` para las reglas exactas (fijadas antes de ver cualquier resultado). Motivación: las 5 hipótesis anteriores (todas tendenciales/de ruptura) comparten un problema estructural de drawdown catastrófico en Monte Carlo (-78% a -96%) que ni diversificar entre activos ni reducir el riesgo por operación resuelven, porque las criptos tienden a consolidar todas a la vez. Pairs trading opera el *spread* entre dos activos cointegrados — naturaleza de riesgo distinta en teoría.

## 2. Screening de cointegración

55 pares posibles (11 activos), 3 temporalidades candidatas (H1/H4/D1) decididas a priori. **6 pares únicos cointegran** (Engle-Granger + ADF, p<0.05, período de formación): XRPUSDT-UNIUSDT, ETHUSDT-SOLUSDT, ETHUSDT-UNIUSDT, ETHUSDT-AVAXUSDT (los 4 cointegran en las 3 temporalidades), más ETHUSDT-XRPUSDT y XRPUSDT-BNBUSDT (solo cointegran en H4). Detalle: `results/pairs_cointegration_screen.json`.

## 3. WFO — comparación entre temporalidades

| Temporalidad | Pares | mean_oos_obj | WFE | Veredicto |
|---|---|---|---|---|
| H1 | 4 | -0.1689 | -1.4568 | ❌ NO RENTABLE OOS |
| **H4** | **6** | **+0.2460** | **0.4401** | ⚠️ DÉBIL (el mejor WFE de las 6 hipótesis del proyecto) |
| D1 | 4 | +0.0259 | 0.0235 | ❌ SOBREOPTIMIZACIÓN |

**H1** se rechaza sin ambigüedad: los 3 folds OOS negativos.

**D1** sobreoptimiza: IS excelente (obj 0.87–1.31, expectancy hasta +0.18R) pero OOS se derrumba en 2 de 3 folds, con muestras muy chicas (14–60 trades OOS) — clásica señal de que el "buen" resultado IS es ruido, no señal.

**H4** es el resultado más interesante de todo el proyecto:

| Fold | OOS ventana | Trades OOS | IS Expectancy | OOS Expectancy |
|---|---|---|---|---|
| F1 | 2023 | 158 | +0.025R | **+0.037R** (OOS > IS) |
| F2 | 2024 | 144 | +0.029R | **+0.078R** (OOS > IS) |
| F3 | 2025 H1 | 68 | +0.040R | -0.055R |

Dos de tres folds tienen **desempeño OOS mejor que IS** — lo opuesto de la señal típica de sobreajuste. El único fold débil es 2025 H1, y tiene una explicación económica coherente: fue un período de tendencia fuerte y expansiva (el mismo semestre que "salvó" el resultado de BREAKOUT-ATR en cripto) — un régimen tendencial es estructuralmente adverso para una estrategia de reversión a la media, cuyo supuesto es precisamente que los precios vuelven a su relación histórica en vez de romperla.

Config congelada H4: `lookback_bars=60, z_entry=2.5, z_exit=0.25, z_stop=4.0`.

## 4. Monte Carlo (H4, config congelada, 723 trades no-holdout)

| Métrica | H4 (pairs) | Referencia: BREAKOUT-ATR (mejor variante cripto) |
|---|---|---|
| Expectancy base | +0.0306R | +0.0479R (11 activos) |
| Win rate | 45.5% | ~26% |
| **MC-1 DD bootstrap p95** | **-20.8%** | -81.9% |
| **MC-1 DD peor caso** | **-36.1%** | -96.2% |
| MC-2 fricciones estresadas | +0.0168R **[OK]** | +0.0234R [OK] |
| MC-3 ruido de precios | 7.8% caída [ROBUSTO] | 0.4% [ROBUSTO] |
| Sensibilidad — parámetros críticos | **0 de 8** | (no comparable, distinto set de parámetros) |
| Concentración temporal | 39.8% [ok] | 48.0% [ok] |
| **Concentración por par/activo** | **139.4% [ALARMA]** | 49.6% [ok] (11 activos) |

**El drawdown de Monte Carlo es, por un margen enorme, el mejor de las 6 hipótesis probadas en este proyecto** — de un rango histórico de -78% a -96% en todas las variantes tendenciales, a -21%/-36% aquí. Es la primera vez que el riesgo de cola se ve genuinamente tratable. La sensibilidad también es la más limpia del proyecto (0 parámetros críticos, contra 12 de 18 en forex o varios críticos en cada hipótesis cripto).

**Pero hay una alarma de concentración real, no un artefacto estadístico** (a diferencia de casos anteriores donde la alarma se debía a dividir entre un total casi cero): de los 6 pares, **ETHUSDT-XRPUSDT solo aporta +$3,461.93**, más que el PnL neto total del pool (+$2,484.08) — los otros 5 pares suman negativo o casi plano (XRPUSDT-UNIUSDT +$55, ETHUSDT-SOLUSDT -$43, ETHUSDT-AVAXUSDT -$137, XRPUSDT-BNBUSDT -$107, ETHUSDT-UNIUSDT -$746). El resultado depende sustancialmente de un solo par.

Racha de pérdidas (bootstrap): p95=14, peor caso=25 operaciones seguidas — mucho más corta que las 31–54 encontradas en las variantes tendenciales, consistente con el win rate más alto (45.5% vs ~26%).

## 5. Veredicto

**No se aprueba formalmente** bajo el criterio estricto establecido desde el inicio del proyecto (WFE≥0.5 para "aceptable"; H4 da 0.44, justo por debajo). El criterio no se relaja porque el resultado se vea prometedor — es la misma regla aplicada a las 5 hipótesis anteriores.

Dicho esto, **es objetivamente el resultado más sólido de las 6 hipótesis**: el único que resuelve el problema de drawdown catastrófico que afectó a SATAR-1, HYDRA, SWEEP y BREAKOUT-ATR en todas sus variantes (incluida la de 11 activos), el único con sensibilidad completamente limpia, y el único con dos folds OOS mejores que IS. La razón por la que no pasa el umbral formal es la concentración en un solo par (ETHUSDT-XRPUSDT) y el WFE marginalmente bajo el corte — no un fallo de expectativa ni de riesgo de cola.

### Recomendación honesta

**No operar con capital real todavía**, por la misma disciplina del resto del proyecto — pero esta hipótesis es la candidata más clara para una segunda ronda de refinamiento, con dos caminos concretos y no excluyentes:

1. **Ampliar el universo de pares candidatos.** Solo se probaron los 11 activos ya usados en BREAKOUT-ATR. Correr el mismo screening de cointegración (§2) sobre un universo más amplio de criptos podría encontrar más pares genuinamente cointegrados, reduciendo la dependencia de ETHUSDT-XRPUSDT — es exactamente el tipo de diversificación que en las hipótesis tendenciales no resolvía el problema de fondo (racha de pérdidas correlacionada), pero aquí sí sería relevante porque el riesgo de cola ya está resuelto; el problema restante es concentración de fuente de retorno, no de riesgo de cola.
2. **Re-optimizar excluyendo ETHUSDT-XRPUSDT** para ver si el resto de los pares, evaluados de forma más limpia (sin que el par dominante oculte su desempeño individual), sostienen un WFE aceptable por sí solos — esto SÍ requeriría un nuevo WFO completo (no se puede decidir mirando el resultado ya obtenido, sería data-snooping).

Cualquiera de los dos caminos es una continuación legítima de esta misma hipótesis, no una hipótesis nueva.

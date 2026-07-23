# Hipótesis 5 — Forex/Materias Primas: Resultados y Veredicto

**Fecha:** 2026-07-23 · **Veredicto: ❌ NO APROBADO**

## 1. Contexto

Tras el veredicto de las 4 hipótesis en cripto (SATAR-1, HYDRA, SWEEP, BREAKOUT-ATR — ver `docs/ESTADO-Y-CONTINUIDAD.md`), se probó si la regla SATAR-1 **original, sin recalibrar ningún parámetro** (P01-P37), tiene edge en un mercado con microestructura distinta: forex y oro, con comisiones internalizadas en el spread, sesiones horarias marcadas, y menor volatilidad relativa que cripto.

Mismo protocolo de rigor que todas las hipótesis anteriores: formalización → WFO anclado-rodante → Monte Carlo → veredicto, con holdout intocable (desde 2025-01-01) y prohibición explícita de ajustar parámetros mirando resultados.

- **Activos:** EURUSD, GBPUSD, USDJPY, XAUUSD.
- **Fuente:** ticks de Dukascopy (2010-01-01 → presente), resampleados a M5.
- **Adaptaciones (solo infraestructura, no reglas de trading):** fricciones calibradas por par (`satar_forex_config.py`), offset D1 a las 22:00 UTC (cierre NY, convención forex).

## 2. Bugs encontrados y corregidos durante esta fase

1. **`resample()` con `offset` no aplicaba el ajuste de sesión.** Pandas ignora silenciosamente `offset`/`origin` en `resample()` cuando la frecuencia no es "Tick-like" (h/m/s/ms/us/ns) — para `'1D'` el offset nunca tuvo efecto, solo un `RuntimeWarning`. Esto significaba que el D1 usado para el filtro de régimen Hurst y el mapeo causal **siempre estuvo anclado a medianoche UTC**, no a las 22:00 UTC como pretendía la adaptación de la Fase F1, desde que se implementó. Corregido desplazando el índice manualmente (único método confiable en pandas para esto). Verificado: cambia los resultados de forma material (el smoke test de EURUSD pasó de 16 a 18 trades, expectancy de -0.392R a -0.097R).
2. **`mean_oos_obj` del WFO contaminado por el sentinel de muestra insuficiente.** El Fold 2 (OOS 2018-2020) tuvo solo 1 trade, disparando el valor `-999` que `objective()` usa para descartar combinaciones *dentro* de la búsqueda de grid — no diseñado para promediarse en un veredicto agregado. Eso arrastraba `mean_oos_obj` a -249.93, un número sin sentido. Corregido: se reporta también `oos_pooled_expectancy_R` (ponderado por trades, ignorando el objective compuesto) como lectura honesta.
3. **`UnicodeEncodeError`** con el carácter griego Δ en el resumen final de consola de Monte Carlo (cosmético — el crash ocurría después de guardar el JSON de resultados, no se perdió nada).
4. **Dos reinicios de la máquina** durante las ~15+ horas que tomó descargar los 4 pares desde Dukascopy se comieron el progreso completo dos veces, porque `download_forex.py` solo escribía a disco al terminar todo el rango 2010-2026. Corregido: guarda cada mes al vuelo y es resumible desde el último punto guardado.

Sin estos fixes, cualquier resultado de esta fase habría sido, como mínimo, no confiable, y en el caso del offset de sesión, directamente inválido respecto a lo que la Fase F1 pretendía probar.

## 3. Resultados WFO (`results/wfo_results_forex.json`)

Grid coarse (27 combos/fold: `er_clean`, `er_arrive`, `decel_max`), 4 folds anclados-rodantes:

| Fold | Ventana OOS | Trades OOS | Expectancy OOS |
|---|---|---|---|
| F1 | 2016 → 2018 | 10 | -0.083R |
| F2 | 2018 → 2020 | 1 | 0.000R *(muestra insuficiente)* |
| F3 | 2020 → 2022 | 26 | -0.114R |
| F4 | 2022 → 2025 | 32 | +0.003R |

- **IS pooled:** 262 trades, expectancy **+0.034R**
- **OOS pooled:** 69 trades, expectancy **-0.054R**
- Config congelada resultante: `er_clean=0.38, er_arrive=0.35, decel_max=0.75`

## 4. Resultados Monte Carlo (`results/montecarlo_results_forex.json`)

Sobre la config congelada, corrida completa de la región no-holdout (2010 → 2025-01-01): **120 trades**.

- Expectancy base: **-0.0027R** (prácticamente plano)
- MC-1 bootstrap DD: p95=**-17.0%**, peor caso=**-27.0%** — mucho más moderado que BREAKOUT-ATR en cripto (que llegó a -78%/-95%)
- MC-2 fricciones estresadas: expectancy p25=**-0.0614R** → **FALLA** (ya negativo en base, empeora bajo estrés realista)
- MC-3 ruido de precios: caída 1.6% → **ROBUSTO**
- Por activo: EURUSD -$153.85 (33 trades) · GBPUSD +$185.28 (26) · USDJPY +$257.55 (27) · XAUUSD -$350.95 (34) — **PnL neto total: -$61.97**
- Sensibilidad: 12 de 18 variantes de parámetros no-optimizables marcadas "críticas" (|Δrelativo|>30%)

### Nota metodológica sobre los indicadores de alarma

Tanto la "concentración de activo" (566%) como la "concentración temporal" (697%) y buena parte de la sensibilidad (Δ relativo) son **ratios que dividen entre un total/base muy cercano a cero** (PnL neto de -$62, expectancy base de -0.0027R). Cualquier variación pequeña en términos absolutos se ve como un porcentaje enorme cuando el denominador es casi cero. A diferencia de cripto — donde SOLUSDT dominaba un resultado neto genuinamente positivo, y esa concentración era una señal real de riesgo — aquí ningún activo domina de forma alarmante en términos absolutos (todos entre -$351 y +$258). El patrón real no es "un activo se come todo el resultado"; es simplemente que **no hay un resultado neto claro** sobre el cual una proporción tenga sentido. Se documentan los números crudos junto a los porcentajes para no prestarse a lectura errónea.

## 5. Veredicto: NO APROBADO

A diferencia de BREAKOUT-ATR en cripto (edge real medible pero con riesgo de cola catastrófico), aquí el hallazgo es más simple y menos dramático: **la regla SATAR-1 original, sin modificar, casi no dispara en forex** (120-331 trades según el corte, contra miles en las hipótesis de cripto), y lo poco que dispara está esencialmente en cero — ligeramente negativo bajo fricciones realistas. No hay muestra suficiente para afirmar con confianza que el edge es negativo, pero tampoco la hay para afirmar que existe. El drawdown de Monte Carlo es comparativamente moderado (-17% a -27%), pero eso es secundario cuando no hay expectancy positiva que lo justifique.

**No se recomienda operar esta forma de la hipótesis**, ni en demo ni en real.

### Caminos posibles si se quiere seguir explorando forex (no iniciados)

- Adaptar los **parámetros** de entrada (no solo la infraestructura) específicamente a la volatilidad/estructura de forex. Esto requeriría formalizarse como una hipótesis nueva (Hipótesis 6) — modificar P01-P37 fuera de un WFO propio violaría el protocolo anti-data-snooping de este proyecto.
- Probar timeframes más altos (H1/H4 en vez de M5), dado que forex tiene menos ruido de alta frecuencia que cripto y la regla podría comportarse distinto a otra escala.

# SATAR-1 — Fase 5: Robustez (WFO, OOS, Monte Carlo, Sensibilidad)

**Fecha:** 2026-07-07 · **Estado:** protocolo entregado (se ejecuta tras la corrida de Fase 4 con datos reales)

## 1. Walk-Forward Optimization (WFO)

- Esquema **anclado-rodante**: ventana IS de 3 años → OOS de 1 año → avance de 1 año. Con 10 años: 7 folds.
- Solo se optimizan los 6 parámetros permitidos (P09, P11, P15, P17, P21, P22) con búsqueda en rejilla gruesa (3-4 valores por parámetro ⇒ ≤ 1.296 combinaciones por fold).
- Función objetivo: **Expectancy_R × √N** penalizada por drawdown (obj = E_R·√N / (1+|DD|·5)). Nunca optimizar retorno bruto.
- **WFE (Walk-Forward Efficiency)** = media(OOS_perf) / media(IS_perf). Criterio: WFE ≥ 0.5 aceptable, ≥ 0.7 bueno. WFE < 0.4 ⇒ sobreoptimización declarada.

## 2. Out-of-Sample y Holdout

Según particiones de Fase 4 §2. El holdout (15% final) se abre UNA sola vez con la configuración congelada del WFO. Resultado del holdout = veredicto; no hay segunda oportunidad sin reiniciar el protocolo completo.

## 3. Monte Carlo (3 familias, 5.000 iteraciones c/u)

1. **Reordenamiento de trades** (bootstrap con reemplazo sobre la secuencia de R): distribución de DD máximo y de rachas. Métrica de decisión: **DD al percentil 95** — este valor, no el DD del backtest, alimenta los límites de la Fase 6.
2. **Perturbación de fricciones**: slippage ×U(1,3), spread ×U(1,2) por trade. La estrategia debe conservar expectancy > 0 al percentil 25.
3. **Perturbación de precios**: ruido gaussiano σ=0.05×ATR sobre OHLC de entrada (sensibilidad del gatillo). Caída de expectancy > 40% ⇒ el gatillo es frágil.

## 4. Análisis de sensibilidad y estabilidad de parámetros

- Perturbar cada parámetro NO optimizable ±20% (uno a la vez): |Δexpectancy| > 30% ⇒ parámetro crítico, documentar y considerar fijarlo por estructura, no por rendimiento.
- **Mapa de estabilidad** de los 6 optimizables: heatmaps por pares; el óptimo elegido debe estar en una meseta (vecinos con ≥80% del rendimiento del pico), nunca en un pico aislado.
- Variante estructural P36 (trailing I vs P) y variante AND/OR de G3: se comparan como sistemas distintos con el mismo protocolo; se elige por OOS, no por IS.

## 5. Pruebas de no-degradación adicionales

- **Estabilidad temporal**: expectancy por año calendario; ningún tercio del histórico debe concentrar > 60% del beneficio total.
- **Estabilidad por activo**: el portfolio no puede depender de un solo símbolo (> 50% del PnL ⇒ señal de alarma).
- **Prueba de truncado (anti look-ahead)**: re-ejecutar con el último 20% de datos eliminado; las señales del 80% común deben ser idénticas byte a byte.

## 6. Criterio integrado de aprobación de la Fase 5

APROBADO si: WFE ≥ 0.5 · expectancy OOS > 0 con fricciones estresadas (P25 de MC-2) · DD_p95 (MC-1) < 15% · óptimos en meseta · sin concentración temporal/activo. Cualquier fallo ⇒ el sistema NO pasa a Fase 9 y se documenta la causa (posibilidad real: el edge declarado no existe una vez objetivado — resultado válido del proyecto).

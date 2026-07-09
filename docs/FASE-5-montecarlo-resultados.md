# SATAR-1 — Fase 5 §3-6: Monte Carlo, Sensibilidad, Estabilidad y Veredicto Final

**Fecha:** 2026-07-09 · **Estado:** ✅ ejecutado (diagnóstico, no gate — el WFO ya decidió el veredicto en `FASE-5-wfo-resultados.md`)
**Config evaluada:** `{er_clean: 0.30, er_arrive: 0.26, decel_max: 0.45}` (congelada por el WFO)
**Región:** todo el histórico NO-holdout (2020-01 → 2025-07-01), 5 activos, 132 trades

---

## 0. TL;DR

El WFO (`FASE-5-wfo-resultados.md`) ya determinó que la config falla out-of-sample y no está en meseta — **no aprueba la Fase 5** independientemente de lo que siga. Este Monte Carlo se corrió como **diagnóstico adicional**, no como segundo gate, y confirma el mismo veredicto desde tres ángulos independientes:

1. **MC-1 (bootstrap):** DD al percentil 95 = **-24.3%**, muy por encima del límite de 15% del protocolo.
2. **MC-2 (fricciones estresadas):** expectancy cae a **-0.0002R en promedio** (¡negativa incluso en la media, no solo en el percentil 25!). **FALLA.**
3. **Estabilidad:** el resultado positivo del período completo (+3.8%R) es una **cancelación entre activos y entre tercios calendario**, no un edge diversificado: ETH solo aporta 192% del PnL neto (compensando pérdidas de XRP/BNB), y el primer tercio calendario (2020-2022) aporta 166% del PnL neto — los tercios 2 y 3 son **netamente negativos**. Confirma exactamente el patrón de sobreajuste temporal que ya mostró el WFO.

La única prueba que "pasa" es MC-3 (robustez al ruido de precio) — y es una lectura genuinamente útil: el mecanismo del gatillo en sí no es frágil a micro-perturbaciones de precio. El problema no es la ejecución del gatillo, es que el patrón que dispara ese gatillo no generaliza en el tiempo.

---

## 1. MC-1 — Bootstrap de la secuencia de R (5.000 iteraciones)

| Métrica | Valor |
|---|---:|
| DD medio (bootstrap) | -13.2% |
| **DD al percentil 95** | **-24.3%** |
| DD peor caso | -48.2% |
| Racha de pérdidas, percentil 95 | 24 |
| Racha de pérdidas, peor caso | 47 |

**Criterio FASE-5 §6: DD_p95 < 15%.** Resultado: **-24.3% → FALLA** (62% peor que el límite). Reordenar la secuencia real de 132 operaciones con reemplazo revela que, incluso si el orden histórico exacto fue benigno, la composición de resultados admite razonablemente escenarios de drawdown severo (hasta -48% en el peor de 5.000 sorteos) y rachas de hasta 47 pérdidas consecutivas.

## 2. MC-2 — Perturbación de fricciones (5.000 iteraciones)

Slippage ×U(1,3), spread ×U(1,2) por trade, costo convertido a R vía la distancia de stop real de cada trade (`|entry-sl_init|/entry` — fix aplicado tras la auditoría, ver §1 de `FASE-5-wfo-resultados.md`).

| Métrica | Valor |
|---|---:|
| Expectancy media bajo estrés | **-0.0002R** |
| Expectancy percentil 25 | **-0.0015R** |
| Expectancy percentil 5 | -0.0035R |

**Criterio FASE-5 §6: expectancy > 0 al percentil 25 bajo fricciones estresadas.** Resultado: **FALLA**, y de forma contundente — la expectativa base ya positiva (+3.8%R) es tan delgada que el estrés de fricciones realista (nada extremo: slippage hasta 3× y spread hasta 2×, rangos típicos de condiciones de mercado adversas, no un escenario de cola) la vuelve negativa **incluso en el promedio**, antes de mirar siquiera el percentil 25.

## 3. MC-3 — Perturbación de precios de entrada (5.000 iteraciones)

Métrica corregida tras la auditoría (la original daba "ROBUSTO" siempre, ver `FASE-5-wfo-resultados.md` §1): tasa de trades ganadores que el ruido gaussiano (σ=0.05×|R|+0.02) invierte a perdedores.

| Métrica | Valor |
|---|---:|
| Tasa de inversión ganador→perdedor | **0.8%** |
| Veredicto | **ROBUSTO** (umbral: >40% = frágil) |

**Única prueba que pasa.** Lectura honesta: el mecanismo de disparo (cruce de EMA50 en M5, dado que ya se armó el patrón G/I) no depende de un nivel de precio milimétricamente exacto — no es un artefacto de precisión numérica. El problema de la estrategia no está en la ejecución del gatillo sino en qué tan seguido ese gatillo identifica setups genuinamente rentables.

## 4. Sensibilidad de parámetros NO optimizables (±20%, FASE-5 §4)

18 filas evaluadas (9 parámetros × 2 direcciones), **4 críticos** (|Δexpectancy| > 30%):

| Parámetro | Cambio | Expectancy_R | Δ relativo | Crítico |
|---|---|---:|---:|:---:|
| `pin_ratio` | -20% (1.6) | +0.007R | -82.6% | ✅ |
| `pin_ratio` | +20% (2.4) | +0.069R | +81.3% | ✅ |
| `arrive_n` | -20% (4) | **-0.155R** | **-508%** | ✅ |
| `arrive_n` | +20% (6) | **-0.090R** | **-336%** | ✅ |

**Hallazgo más grave de esta sección: `arrive_n` (P14, ventana de "llegada acelerada" del módulo G).** Es un parámetro NO optimizable — por protocolo (FASE-3) su valor default (5) está fijo y no se calibra. Sin embargo, moverlo apenas ±20% (a 4 o a 6) **invierte el signo completo del resultado**: de +3.8%R a -15.5%R o -8.9%R. Esto significa que el resultado "positivo" del período completo (que ya de por sí falla MC-1/MC-2) depende de un parámetro estructural que, por diseño del protocolo, nunca fue validado por robustez — está fijado desde la Fase 2 sin más justificación que el valor por defecto. `pin_ratio` (forma del patrón pin-bar) también es sensible pero en menor magnitud.

Los otros 7 parámetros (`buf_atr`, `stop_min_atr`, `stop_max_atr`, `tp_lookback`, `rr_min`, `dtop_tol_atr`, `touch_window`) no muestran sensibilidad crítica.

## 5. Estabilidad temporal y por activo (FASE-5 §5)

### Por activo

| Activo | Trades | PnL (USD) |
|---|---:|---:|
| BTCUSDT | 35 | +36.58 |
| ETHUSDT | 34 | **+857.74** |
| SOLUSDT | 14 | +295.43 |
| XRPUSDT | 28 | -311.07 |
| BNBUSDT | 21 | -431.81 |
| **Total** | **132** | **+446.87** |

**max_share_activo = 191.9% → ALARMA** (criterio: >50%). ETH por sí solo genera **más del doble** del PnL neto total — el resto de la cartera, en conjunto, resta valor. Esto no es diversificación: es un único activo compensando pérdidas de otros dos, con BTC y SOL como aportes menores. Un portfolio con este perfil depende críticamente de que ETH siga comportándose igual; no hay evidencia de que el "edge" generalice entre activos.

### Por tercio de calendario

| Tercio | PnL (USD) |
|---|---:|
| 1° (≈2020-2022) | **+740.52** |
| 2° (≈2022-2024) | -58.29 |
| 3° (≈2024-2025) | -235.37 |

**max_share_tercio = 165.7% → ALARMA** (criterio: >60%). El primer tercio del histórico —que incluye el ciclo alcista 2020-2021— genera **166% del PnL neto total**; los tercios 2° y 3° son **ambos negativos**. Esto es la contraparte estadística exacta del hallazgo del WFO (§2 de `FASE-5-wfo-resultados.md`): la config fue calibrada sobre un período que ya no se repite, y el rendimiento decae monótonamente con el tiempo.

## 6. Veredicto integrado de la Fase 5

Aplicando el criterio de aprobación de `docs/FASE-5-robustez.md` §6 (WFE≥0.5 **Y** expectancy OOS>0 con fricciones estresadas **Y** DD_p95<15% **Y** óptimos en meseta **Y** sin concentración temporal/activo):

| Criterio | Resultado | Veredicto |
|---|---|:---:|
| WFE ≥ 0.5 | mean_oos_obj ≤ 0 (no rentable OOS) | ❌ FALLA |
| Expectancy > 0 con fricciones (MC-2, p25) | -0.0015R | ❌ FALLA |
| DD_p95 (MC-1) < 15% | -24.3% | ❌ FALLA |
| Óptimo en meseta | Pico aislado (F2/F3 colapsan a negativo a 1 paso de grid) | ❌ FALLA |
| Sin concentración por activo (<50%) | 191.9% | ❌ FALLA |
| Sin concentración temporal (<60%) | 165.7% | ❌ FALLA |
| Robustez a ruido de precio (MC-3) | 0.8% (umbral 40%) | ✅ PASA |

**6 de 7 criterios fallan.** El único que pasa (MC-3) indica que el mecanismo de ejecución del gatillo es técnicamente sólido — el problema no es un bug de precisión numérica, es que el patrón formalizado de Alex Ruiz, en el universo cripto probado (5 activos, 6.5 años), **no muestra un edge estadístico que sobreviva fuera de muestra, resista fricciones realistas, ni generalice entre activos o períodos de calendario**.

### Sobre el holdout

Consistente con la recomendación de `FASE-5-wfo-resultados.md` §6: **el holdout NO se abre**. El protocolo lo reserva como confirmación final de un candidato que ya sobrevivió IS/OOS/Monte Carlo; aquí el candidato fue rechazado en 6 de 7 criterios independientes antes de llegar a esa etapa. Abrirlo no cambiaría el veredicto y consumiría un recurso de un solo uso sin aportar información.

### Veredicto del proyecto (FASE-5 §6, aplicado)

> **NO APROBADO.** La metodología de Alex Ruiz, formalizada objetivamente en el Pilar C (impulso-pullback-continuación multi-timeframe con EMA50/Fibonacci/patrón de giro) y probada sobre 5 activos cripto (BTC/ETH/SOL/XRP/BNB, 2020-2025, 683k+ velas M5 por activo), **no muestra edge estadístico robusto**. El sistema no pasa a Fase 9 (demo). Esta es una conclusión legítima del proyecto — la Fase 5 existe exactamente para poder llegar a este veredicto sin caer en sobreajuste ni en data-snooping, y el propio proceso de auditoría (que encontró y corrigió 8 bugs en el código de validación antes de confiar en sus resultados) refuerza la seriedad del hallazgo: no es un artefacto de errores de implementación, es un resultado que sobrevivió a la corrección de esos errores.

## 7. Archivos generados

```
code/python/
├── satar_montecarlo.py              MC-1/2/3 + sensibilidad + estabilidad (con 6 fixes de auditoría)
└── results/
    └── montecarlo_results.json       Resultados completos de esta corrida
```

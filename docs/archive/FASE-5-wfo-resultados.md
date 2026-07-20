# SATAR-1 — Fase 5 §1-2: Resultados del Walk-Forward Optimization (WFO)

**Fecha:** 2026-07-09 · **Estado:** ✅ ejecutado · **Veredicto: NO APROBADO (config sobreoptimizada, OOS negativo)**
**Precede a:** decisión sobre abrir el holdout (§6 de este documento) y Fase 6/9.

> Nota: una versión previa de este documento (2026-07-08) contenía números de una corrida anterior a
> la auditoría y corrección de bugs de `satar_wfo.py` (ver §1). Este documento refleja la corrida real
> post-fix (`results/wfo_results.json`, generado 2026-07-09 08:47 UTC-5).

---

## 0. TL;DR

1. Se optimizaron 3 de los 6 parámetros permitidos (`er_clean`, `er_arrive`, `decel_max`; grid reducido — ver §1) sobre el pool de 5 activos, en 3 folds anclados-rodantes (2020→2025-07, holdout intocable después).
2. **La config ganadora es rentable en cada IS y pierde dinero en cada OOS, cada vez peor**: E_R pasa de +14.1%/+8.7%/+6.3% (IS) a -1.8%/-7.8%/-15.8% (OOS) en F1/F2/F3. Degradación monotónica — firma clásica de sobreajuste.
3. **El "óptimo" no está en meseta, está en un pico aislado**: en F2 y F3, mover `decel_max` un solo paso de grid (0.45→0.60) hace que el objetivo se desplome de fuertemente positivo a negativo. Viola directamente el criterio de FASE-5 §4 ("el óptimo elegido debe estar en una meseta... nunca en un pico aislado").
4. **WFE = -0.44**, pero el número correcto a mirar es más simple y más contundente: `mean_oos_obj = -0.2849 <= 0`. Antes de preguntar "¿qué tan bien sobrevivió el edge de IS a OOS?", la pregunta previa ya tiene respuesta: **no hay edge que sobreviva — la config pierde dinero fuera de muestra**.
5. **Recomendación: NO abrir el holdout.** Ver §6.

---

## 1. Metodología

- **Grid reducido** (documentado y justificado por el gate de presupuesto de cómputo, FASE plan §D.3): grid *full* (6 parámetros × 3 valores = 729 combos/fold) se estimó en ~4.5h a 6 núcleos; se usó el grid *coarse* (`er_clean`, `er_arrive`, `decel_max` — los 3 parámetros que el diagnóstico del embudo de `FASE-4-multiactivo.md` §4 señaló como dominantes en la ENTRADA), 27 combos/fold, ~10-15 min. Los otros 3 parámetros optimizables (`zone_w_atr`, `chase_atr`, `armed_window`) quedaron fijos en su default.
- **Folds anclados-rodantes** (IS ancla en 2020-01-01 y crece, OOS = 1 año siguiente, excepto F3 cuyo OOS es 6 meses por límite del holdout):

| Fold | IS | OOS |
|---|---|---|
| F1 | 2020-01-01 → 2023-01-01 (3 años) | 2023-01-01 → 2024-01-01 |
| F2 | 2020-01-01 → 2024-01-01 (4 años) | 2024-01-01 → 2025-01-01 |
| F3 | 2020-01-01 → 2025-01-01 (5 años) | 2025-01-01 → 2025-07-01 |

- **Holdout**: 2025-07-01 → fin (≈15% final) — **no tocado** en este documento.
- **Objetivo**: `obj = E_R · √N / (1 + |DD|·5)`, pool combinado de 5 activos (BTC/ETH/SOL/XRP/BNB), trades ordenados cronológicamente antes de calcular el DD (ver bugs corregidos abajo).
- **Auditoría previa**: antes de esta corrida real, un workflow de revisión adversarial (4 lentes independientes + verificación adversarial de cada hallazgo) encontró y se corrigieron 2 bugs en `satar_wfo.py`:
  - **(A)** Fuga de holdout por slicing inclusivo de pandas (`df.loc[lo:win_end]` incluye el extremo) → corregido a máscara estricta.
  - **(B, crítico)** El WFE podía dar un ratio positivo engañoso cuando IS y OOS eran ambos negativos (dos negativos entre sí) → corregido con guarda de signo explícita (ver el veredicto textual en vez de un umbral numérico ciego).
  - **(C, alto)** El pool de trades de 5 activos se concatenaba activo-por-activo sin ordenar cronológicamente antes del `cumsum()` del drawdown, subestimando el DD real de una cuenta compartida con activos correlacionados → corregido con `sorted(pooled, key=lambda t: t.t_entry)`. Verificado empíricamente: la misma ventana pasó de DD=-6.5% a DD=-10.8% tras el fix.
  - El mismo patrón (A)/(pooling) se encontró y corrigió también en `satar_montecarlo.py` (6 fixes adicionales, ver `results/montecarlo_results.json`).

## 2. Resultados por fold

| Fold | IS obj | IS N | IS E_R | IS WR | OOS obj | OOS N | OOS E_R | OOS WR |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| F1 | **0.8487** | 66 | **+14.12%** | 24.2% | -0.0742 | 34 | **-1.78%** | 23.5% |
| F2 | **0.6166** | 100 | **+8.71%** | 24.0% | -0.2655 | 17 | **-7.84%** | 11.8% |
| F3 | **0.4594** | 117 | **+6.31%** | 22.2% | -0.5150 | 15 | **-15.75%** | 26.7% |

**Config ganadora, idéntica en los 3 folds:** `er_clean=0.30` (= default), `er_arrive=0.26` (más laxo que el default 0.35 → deja pasar más señales en G3), `decel_max=0.45` (más estricto que el default 0.60 → exige desaceleración más marcada en G4).

**Patrón:** el objetivo IS decrece monótonamente al crecer la ventana (0.85→0.62→0.46) mientras el objetivo OOS empeora monótonamente (-0.07→-0.27→-0.52). Esto es consistente con una config afinada a las particularidades de los primeros 3 años (2020-2023, incluye el ciclo alcista de 2020-2021) que no generaliza a los períodos posteriores.

## 3. WFE — con la fórmula corregida

```
mean_is_obj  = 0.6416   (promedio de los 3 folds, todos positivos)
mean_oos_obj = -0.2849  (promedio de los 3 folds, todos negativos)
WFE = mean_oos_obj / mean_is_obj = -0.4441
```

Con la guarda de signo aplicada (`satar_wfo.py`, fix crítico), el veredicto no se basa ciegamente en el número -0.44: como `mean_oos_obj <= 0`, el script declara explícitamente **"NO RENTABLE OOS"**, sin pasar por los umbrales de calidad de WFE (que solo son interpretables cuando ambos lados son rentables). En este caso particular el ratio numérico también resulta negativo y caería en "SOBREOPTIMIZACION (WFE<0.4)" de todos modos — las dos lecturas coinciden — pero la lectura correcta y más directa es la primera: **la config pierde dinero fuera de muestra, punto**.

## 4. Análisis de meseta (FASE-5 §4) — el óptimo es un pico aislado

El protocolo exige que el óptimo elegido esté en una meseta (vecinos con ≥80% del rendimiento del pico), nunca en un pico aislado. Los top-5 IS por fold (`results/wfo_results.json`) muestran justo lo contrario:

| Fold | #1 (ganador) | #2 | #3 | ¿Meseta? |
|---|---:|---:|---:|:---:|
| F1 | 0.8487 | 0.3746 (44%) | 0.3390 (40%) | ❌ No |
| F2 | 0.6166 | 0.5142 (83%) | **-0.1312** (negativo) | ❌ No |
| F3 | 0.4594 | 0.1684 (37%) | **-0.1697** (negativo) | ❌ No |

En **F2 y F3**, el 3er lugar es directamente **negativo** — y la única diferencia con el ganador es mover `decel_max` de 0.45 a 0.60 (un solo paso de grid, de 27 valores probados). Es decir: **la rentabilidad in-sample depende de un umbral de desaceleración calibrado al decimal**, no de una zona ancha de buenos parámetros. Esto es evidencia adicional e independiente de sobreajuste, coherente con el fallo en OOS de §2-3.

## 5. Cruce con el diagnóstico del embudo (FASE-4-multiactivo.md §4)

El diagnóstico previo ya había señalado a G4 (desaceleración) como uno de los mayores cuellos de botella de la entrada. El WFO confirma que ese filtro es también el más **inestable**: apretarlo (decel_max=0.45) mejora fuertemente el resultado IS reciente, pero esa mejora no es una señal estructural real — es ruido de sobreajuste a los datos de calibración, tal como lo revela el colapso en OOS y la ausencia de meseta.

## 6. Recomendación: NO abrir el holdout

El protocolo (`docs/FASE-5-robustez.md` §6) define la aprobación como: WFE≥0.5 **Y** expectancy OOS>0 con fricciones estresadas **Y** DD_p95<15% **Y** óptimos en meseta **Y** sin concentración temporal/activo. **Ya fallan 2 de 5 criterios de forma directa y anterior a cualquier test de fricciones**: expectancy OOS es negativa (§2-3) y el óptimo no está en meseta (§4).

El holdout es un recurso de un solo uso ("se abre UNA sola vez... y no hay segunda oportunidad sin reiniciar el protocolo completo"). Abrirlo sobre una configuración que ya reprobó dos criterios independientes no aportaría información científica adicional — su valor está en confirmar candidatos que ya sobrevivieron IS/OOS/MC, no en usarse como un segundo intento sobre una config descartada. **Se recomienda NO abrir el holdout en esta iteración del protocolo.**

Como diagnóstico adicional (no como gate de aprobación, ya que el WFO ya decidió el veredicto), se ejecutó Monte Carlo sobre la config congelada — ver `results/montecarlo_results.json` y el resumen en `docs/ESTADO-Y-CONTINUIDAD.md` (actualizado en la Fase F).

## 7. Archivos generados

```
code/python/
├── satar_wfo.py                    Walk-Forward Optimization (con 3 fixes aplicados)
└── results/
    └── wfo_results.json             IS/OOS por fold, top5, WFE, config congelada
```

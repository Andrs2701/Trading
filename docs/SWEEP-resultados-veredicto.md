# SWEEP — Resultados y Veredicto Final

**Fecha:** 2026-07-09 · **Estado:** ✅ ejecutado completo (S1-S5) · **Veredicto: NO APROBADO**
**Formalización:** `docs/SWEEP-formalizacion.md` · **Motor:** `code/python/sweep_backtest.py`, `sweep_wfo.py`, `sweep_montecarlo.py`

---

## 0. TL;DR

1. La hipótesis de *liquidity sweep / stop hunt* sobre estructura semanal (H1, 168 velas) **no muestra edge estadístico** en el universo cripto probado (5 activos, 2020-2025).
2. **No es un caso de sobreajuste** (rentable in-sample, fallando out-of-sample) — es más contundente que eso: **nunca fue rentable ni siquiera in-sample**, en ningún fold, con ningún combo del grid, incluido el extremo más favorable probado.
3. **Muestra grande**: 5924 trades combinados (vs. 144 de SATAR-1 y 2851-3542 de HYDRA) — el resultado negativo tiene mucho poder estadístico, no es ruido de muestra chica.
4. **Sin concentración**: a diferencia de SATAR-1 (donde el resultado "positivo" dependía de un solo activo y un solo período), SWEEP pierde de forma pareja en los 5 activos y en los 3 tercios del histórico — no hay un rincón con suerte escondiendo un edge real.
5. **Auditoría propia aplicada desde el diseño**: se corrigió un bug de fórmula de equity (aditiva → compuesta) encontrado en HYDRA *antes* de escribir el motor de SWEEP, evitando reintroducirlo.

## 1. Metodología

Pipeline idéntico al usado para SATAR-1/HYDRA (mismo estándar de rigor): formalización previa (S1) → diagnóstico single-asset con embudo (S2) → multi-activo (S3) → WFO anclado-rodante 3 folds + holdout intocable (S4) → Monte Carlo + sensibilidad + estabilidad (S4) → veredicto (S5).

**Corrección aplicada desde el inicio**: la auditoría de HYDRA (ver `docs/ESTADO-Y-CONTINUIDAD.md` §5.1) encontró que la fórmula de drawdown aditiva (`equity = E0·(1+0.01·Σr)`) puede producir equity negativo y drawdowns >100% (matemáticamente imposibles). `sweep_montecarlo.py`/`sweep_wfo.py` usan desde el diseño la versión compuesta (`equity = E0·Π(1+0.01·r)`, con piso de -99% por trade) — por eso los drawdowns reportados aquí nunca exceden -100%.

## 2. Diagnóstico del embudo (single-asset, BTC)

| Etapa | Candidatos |
|---|---:|
| Velas M5 evaluadas | 675,799 |
| Sweep detectado (short+long) | 2,746 |
| Pasa filtro de volumen (`vol_ok`) | 1,528 (56%) |
| Pasa sanidad de stop | 1,367 |
| Pasa R:R mínimo (`rr_min`) | 1,366 (99.9% de los que llegan) |

**Hallazgo de diseño**: el filtro de R:R casi no filtra nada con los parámetros default — tiene explicación estructural (el SL se escala al ATR de M5, muy chico; el TP es el ancho de la estructura semanal, mucho más grande), así que R:R alto es casi automático, no una señal de calidad real. Esto también explica la frecuencia alta observada (~200 trades/año por activo): la "resistencia/soporte" rodante de 168h se toca con más frecuencia de la que sugiere la narrativa original de "caza de stops" como evento raro y dramático.

## 3. Resultados por activo (multi-activo, S3)

| Activo | Trades | Win Rate | Profit Factor | Expectancy_R |
|---|---:|---:|---:|---:|
| BTCUSDT | 1366 | 30.9% | 0.449 | -0.3615 |
| ETHUSDT | 1360 | 32.5% | 0.453 | -0.3139 |
| SOLUSDT | 1252 | 31.2% | 0.450 | -0.2984 |
| XRPUSDT | 1057 | 32.2% | 0.569 | -0.3236 |
| BNBUSDT | 1225 | 29.5% | 0.369 | -0.4412 |
| **PORTFOLIO** | **5924** | **31.1%** | **0.430** | **-0.3700** |

Los 5 activos fallan con parámetros muy similares (WR 30-33%, PF 0.37-0.57) — consistencia que descarta que sea un problema específico de un activo.

## 4. Walk-Forward Optimization

Grid: `vol_spike_mult` ∈ [1.2, 1.5, 1.8, 2.0], `rr_min` ∈ [2.0, 3.0, 4.0] (12 combos/fold).

| Fold | IS Expectancy | IS N | OOS Expectancy | OOS N | Mejor combo |
|---|---:|---:|---:|---:|---|
| F1 | -0.288R | 1882 | -0.369R | 567 | vol_spike_mult=2.0, rr_min=2.0 |
| F2 | -0.306R | 2449 | -0.312R | 751 | vol_spike_mult=2.0, rr_min=2.0 |
| F3 | -0.308R | 3200 | -0.393R | 342 | vol_spike_mult=2.0, rr_min=2.0 |

**El optimizador convergió al extremo del grid en las 3 ventanas** (`vol_spike_mult=2.0` = el más estricto probado, `rr_min=2.0` = el más laxo probado) — y aun así, ninguna combinación es rentable. No hace falta ampliar el grid: en el borde más favorable disponible, el resultado sigue siendo decisivamente negativo, no hay indicio de una región oculta mejor.

**Veredicto WFO: NO RENTABLE IN-SAMPLE** (mean_is_obj ≤ 0). No aplica calcular WFE — la pregunta de "¿sobrevive el edge a OOS?" no llega a plantearse porque nunca hubo edge in-sample que optimizar.

## 5. Monte Carlo, sensibilidad, estabilidad

Sobre la config congelada (`vol_spike_mult=2.0, rr_min=2.0`), 3542 trades en la región no-holdout:

| Prueba | Resultado | Umbral | Veredicto |
|---|---:|---:|:---:|
| DD al percentil 95 (bootstrap) | -100.0% | <15% | ❌ FALLA |
| Expectancy con fricciones estresadas (p25) | -0.4142R | >0 | ❌ FALLA |
| Robustez a ruido de precio | 0.8% inversión | <40% | ✅ PASA |
| Concentración por activo | 20.9% | <50% | ✅ PASA |
| Concentración temporal | 52.2% | <60% | ✅ PASA |

**Sensibilidad**: ningún parámetro no-optimizable es crítico (todos los deltas <5% ante ±20%) — a diferencia de HYDRA (`arrive_n` invertía el signo completo), SWEEP es estructuralmente estable. Esto no cambia el veredicto (la expectativa base ya es negativa), pero es una señal de que el motor está bien calibrado, no es un artefacto frágil de un parámetro mal puesto.

**Estabilidad por activo**: los 5 activos pierden dinero de forma similar (-8,491 a -9,340 USD cada uno sobre $10,000 iniciales) — ninguna alarma de concentración, lo cual paradójicamente confirma que el fracaso es estructural y generalizado, no un accidente de un activo o período.

## 6. Veredicto final

> **NO APROBADO.** La hipótesis de liquidity sweep / stop hunt sobre estructura semanal, formalizada objetivamente (docs/SWEEP-formalizacion.md) y probada sobre 5 activos cripto con 5924 trades combinados, **no muestra edge estadístico**. A diferencia de SATAR-1 (margen pequeño, casi en equilibrio) y HYDRA (sobreajuste con degradación IS→OOS), SWEEP falla de la forma más limpia posible: sin rentabilidad in-sample en ningún fold, sin concentración que sugiera un rincón con suerte, y con un mecanismo de ejecución robusto (no frágil al ruido). El holdout no se abre — no hay razón para hacerlo sobre un candidato rechazado en la etapa más temprana del protocolo.

### Tres hipótesis ya descartadas con este mismo rigor

| Hipótesis | Resultado | Firma del fallo |
|---|---|---|
| SATAR-1 (pullback EMA, metodología Alex Ruiz) | NO APROBADO | Rentable pero por debajo del punto de equilibrio, margen pequeño, concentrado en 2020-2022 |
| HYDRA (pullback + régimen HMM/Hurst) | NO APROBADO | Nunca rentable in-sample, sobreajuste, parámetro crítico no-optimizable |
| SWEEP (liquidity sweep / stop hunt) | NO APROBADO | Nunca rentable in-sample, sin concentración, mecanismo robusto pero sin edge |

## 7. Archivos generados

```
docs/
├── SWEEP-formalizacion.md              Reglas exactas + parámetros (Fase S1)
└── SWEEP-resultados-veredicto.md       ESTE ARCHIVO
code/python/
├── sweep_backtest.py                    Motor de referencia SWEEP
├── sweep_wfo.py                         Walk-Forward Optimization
├── sweep_montecarlo.py                  Monte Carlo + sensibilidad + estabilidad
├── trades_sweep_{sym}.csv               Trades por activo (5 archivos)
└── results/
    ├── wfo_results_sweep.json
    └── montecarlo_results_sweep.json
```

# HYDRA — Resultados y Veredicto Final

**Fecha:** 2026-07-10 · **Estado:** ✅ ejecutado completo · **Veredicto: NO APROBADO**
**Motor:** `code/python/hydra_backtest.py`, `hydra_wfo.py`, `hydra_montecarlo.py`

---

## 0. TL;DR

1. HYDRA extiende SATAR-1 (pullback multi-timeframe a EMA50) con clasificación de régimen — Hidden Markov Model + exponente de Hurst — para filtrar cuándo operar el pullback.
2. **Nunca fue rentable in-sample**, en ningún fold, con ningún combo del grid probado. No es sobreajuste (rentable IS, falla OOS) — es un rechazo más directo: el filtro de régimen no rescató un edge que nunca existió.
3. **Bug de auditoría encontrado y corregido**: la fórmula de drawdown era aditiva (`equity = E0·(1+0.01·Σr)`), lo que puede producir equity negativo y drawdowns matemáticamente imposibles (>100%). Reportaba hasta **-605%**. Corregida a fórmula compuesta (`cumprod`) con piso de -99% por trade — ver `docs/ESTADO-Y-CONTINUIDAD.md` §7. El drawdown real corregido: **-99.5% (percentil 95), -99.8% (peor caso)** — igual de catastrófico, pero ahora un número real, no un artefacto.
4. El veredicto no cambia con la corrección — la expectativa cruda (nunca calculada con la fórmula rota) ya era decisivamente negativa.

## 1. Walk-Forward Optimization

Grid coarse: `hurst_trend` ∈ [0.51, 0.53, 0.55], `score_threshold` ∈ [3, 4], `tp_rr_range` ∈ [1.8, 2.2, 2.6] (18 combos/fold). 3 folds anclados-rodantes 2020→2025-07, holdout intocable.

| Fold | IS Expectancy | IS N | IS WR | OOS Expectancy | OOS N | OOS WR |
|---|---:|---:|---:|---:|---:|---:|
| F1 | -0.108R | 1396 | 20.1% | -0.206R | 593 | 18.0% |
| F2 | -0.138R | 1989 | 19.4% | -0.136R | 572 | 21.5% |
| F3 | -0.137R | 2561 | 19.9% | -0.246R | 290 | 19.7% |

**Config congelada** (idéntica en los 3 folds): `hurst_trend=0.51, score_threshold=3, tp_rr_range=2.6`.

**Veredicto WFO: NO RENTABLE IN-SAMPLE** (mean_is_obj ≤ 0 en los 3 folds). Igual que SWEEP, no aplica calcular WFE — nunca hubo edge in-sample que optimizar. A diferencia de SATAR-1 (que sí fue rentable IS y falló solo al pasar a OOS), HYDRA reprueba en la etapa más temprana posible del protocolo.

*Nota: los valores de `max_dd` en `results/wfo_results_hydra.json` (hasta -336% en F3 IS) fueron calculados con la fórmula de equity aditiva, antes de la corrección de auditoría — no son económicamente interpretables como porcentaje, aunque no afectan el veredicto (que se basa en expectancy, no en drawdown). El WFO no se re-ejecutó completo tras el fix porque el grid de 18 combos × 3 folds vuelve a tardar el mismo orden de magnitud por el cálculo de Hurst no vectorizado, y el veredicto cualitativo no depende de esa métrica. El Monte Carlo (§2) sí se re-verificó con la fórmula corregida.</em>

## 2. Monte Carlo (re-verificado con fórmula de equity corregida)

Sobre la config congelada, 2851 trades en la región no-holdout: expectancy -0.1483R, win rate 19.8%.

| Prueba | Resultado (corregido) | Resultado (buggy, pre-fix) |
|---|---:|---:|
| DD al percentil 95 (bootstrap) | **-99.5%** | -508.2% (imposible) |
| DD peor caso | **-99.8%** | -605.2% (imposible) |
| Racha de pérdidas, percentil 95 | 42 | 42 (sin cambio, no depende de la fórmula) |

El resto de las pruebas (fricciones estresadas, ruido de precio, sensibilidad, estabilidad) **no usan la fórmula de equity para sus métricas reportadas** (usan expectancy_R o PnL directo), así que no fue necesario re-ejecutarlas — sus resultados originales siguen siendo válidos:

| Prueba | Resultado | Umbral | Veredicto |
|---|---:|---:|:---:|
| Expectancy con fricciones estresadas (p25) | -0.1872R | >0 | ❌ FALLA |
| Robustez a ruido de precio | 1.76% inversión | <40% | ✅ PASA |
| Sensibilidad — parámetro crítico | `arrive_n` invierte el signo completo (±20%) | — | ⚠️ Hallazgo grave |

**Hallazgo de `arrive_n`**: es un parámetro no-optimizable (fijo por protocolo), y moverlo ±20% cambia la expectativa de -0.15R a valores muy distintos, incluida inversión de signo en algún extremo — señal de que cualquier resultado positivo aislado con esta familia de reglas sería frágil/casual, no un edge estructural.

## 3. Veredicto final

> **NO APROBADO.** HYDRA (pullback + filtro de régimen HMM/Hurst) nunca fue rentable in-sample en ningún fold del WFO. El filtro de régimen, diseñado para mejorar sobre SATAR-1 filtrando cuándo operar, no rescata un edge que la Fase 5 de SATAR-1 ya había mostrado como marginal en el mejor de los casos. El holdout no se abre — el candidato fue rechazado en la etapa más temprana posible del protocolo (no rentable in-sample).

## 4. Comparación con las otras 2 hipótesis

Ver tabla comparativa completa en `docs/ESTADO-Y-CONTINUIDAD.md` §0. HYDRA y SWEEP comparten la misma firma de fallo (nunca rentable in-sample) pero por razones distintas: HYDRA porque el filtro de régimen no compensa un edge de entrada ya débil; SWEEP porque la hipótesis de "sweep de liquidez" en sí no tiene ventaja estadística verificable en este universo.

## 5. Archivos generados

```
code/python/
├── hydra_backtest.py                   Motor (pullback + HMM + Hurst)
├── hydra_wfo.py                        Walk-Forward Optimization (equity corregido)
├── hydra_montecarlo.py                 Monte Carlo + sensibilidad + estabilidad (equity corregido)
└── results/
    ├── wfo_results_hydra.json          Resultados WFO (max_dd histórico, ver nota §1)
    └── montecarlo_results_hydra.json   Resultados MC completos (fricciones/ruido/sensibilidad/estabilidad
                                          con la corrida original; ver §2 de este doc para el DD corregido)
```

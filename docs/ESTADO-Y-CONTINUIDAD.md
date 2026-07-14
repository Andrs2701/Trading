# Trading — Estado del Proyecto y Guía de Continuidad

**Última actualización:** 2026-07-10 · **Repo:** https://github.com/Andrs2701/Trading (rama `main`)
**Propósito de este documento:** punto de entrada único para retomar el proyecto — resume las hipótesis probadas, el veredicto de cada una, y qué sigue.

---

## 0. TL;DR

Se han probado **3 hipótesis de trading algorítmico en cripto perpetuos**, todas con el mismo protocolo de rigor (formalización → diagnóstico → multi-activo → Walk-Forward Optimization → Monte Carlo → veredicto, con holdout intocable y prohibición explícita de ajustar parámetros a mano mirando resultados). **Las 3 fueron rechazadas.**

| # | Hipótesis | Veredicto | Documentación |
|---|---|---|---|
| 1 | **SATAR-1**: metodología de trading reverse-engineered de un creador de contenido (pullback a EMA50, multi-timeframe) | ❌ NO APROBADO | `docs/archive/` (FASE-0…10) |
| 2 | **HYDRA**: SATAR-1 + filtro de régimen HMM/Hurst | ❌ NO APROBADO | resultados en `code/python/results/*_hydra.json` (informe narrativo pendiente) |
| 3 | **SWEEP**: liquidity sweep / stop hunt sobre estructura semanal | ❌ NO APROBADO | `docs/SWEEP-formalizacion.md`, `docs/SWEEP-resultados-veredicto.md` |

Ninguna de las tres muestra edge estadístico verificable sobre 5 activos cripto (BTC/ETH/SOL/XRP/BNB, 2020-2025). El patrón que se repite: el "pullback a la EMA" (hipótesis 1 y 2) y el "sweep de liquidez" (hipótesis 3) — dos paradigmas de entrada completamente distintos — fallan por razones distintas pero igual de concluyentes.

## 1. Organización del repositorio

- **`docs/archive/`** — documentación completa de SATAR-1 (Fases 0-10 del proyecto original, reverse-engineering de una metodología de trading divulgada en YouTube). Congelada, no se toca salvo error de hecho.
- **`docs/SWEEP-*.md`** — hipótesis activa más reciente, formalización y veredicto.
- **`code/python/satar_*.py`** — motor e infraestructura de SATAR-1 (auditados, reutilizados como base por HYDRA y SWEEP).
- **`code/python/hydra_*.py`** — motor de HYDRA (reutiliza infraestructura de `satar_backtest.py`).
- **`code/python/sweep_*.py`** — motor de SWEEP (reutiliza infraestructura de `satar_backtest.py`).

## 2. Hipótesis 1 — SATAR-1 (metodología reverse-engineered)

Ver `docs/archive/ESTADO-Y-CONTINUIDAD.md` para el detalle completo. Resumen: rentable en la región IS más antigua (2020-2022) pero **6 de 7 criterios de aprobación de la Fase 5 fallan** — óptimo en pico aislado (no meseta), OOS negativo y empeorando, drawdown al percentil 95 de -24.3%, expectancy negativa bajo fricciones, y 166% del PnL neto concentrado en un solo tercio del histórico. Auditoría multi-agente encontró y corrigió 9 bugs en el motor de validación antes de confiar en el veredicto.

## 3. Hipótesis 2 — HYDRA (pullback + régimen HMM/Hurst)

Extensión de SATAR-1 añadiendo clasificación de régimen (Hidden Markov Model + exponente de Hurst) para filtrar cuándo operar el pullback. Resultado del WFO (`code/python/results/wfo_results_hydra.json`):

- **Nunca rentable in-sample**, en ningún fold, con ningún combo del grid probado (expectancy entre -0.108R y -0.245R, win rate ~18-21%, en los 3 folds).
- A diferencia de SATAR-1, esto no es sobreajuste (rentable IS, falla OOS) — es un rechazo más directo: el enfoque nunca despegó.
- **Nota técnica importante**: se encontró y corrigió un bug de fórmula de equity (aditiva `E0·(1+0.01·Σr)` → compuesta `E0·Π(1+0.01·r)`) que producía drawdowns matemáticamente imposibles (>100%, hasta -605% reportado antes del fix). El bug estaba en `hydra_montecarlo.py` y el objetivo de `hydra_wfo.py`; se corrigió y se re-verificó que el veredicto (ya negativo por expectativa cruda) no depende de esa métrica rota.
- El parámetro no-optimizable `arrive_n` resultó extremadamente sensible (±20% invierte el signo completo del resultado) — otra señal de que cualquier resultado positivo aislado sería frágil/casual, no un edge real.

Informe completo con el drawdown re-verificado (fórmula compuesta): `docs/HYDRA-resultados-veredicto.md`.

## 4. Hipótesis 3 — SWEEP (liquidity sweep / stop hunt)

Ver `docs/SWEEP-formalizacion.md` (reglas exactas) y `docs/SWEEP-resultados-veredicto.md` (resultados completos). Resumen:

- Paradigma completamente distinto al pullback: opera la reversión cuando el precio barre (wick) la resistencia/soporte semanal (H1, 168 velas) con volumen anómalo, y cierra de vuelta dentro de la estructura.
- **5924 trades combinados** (la muestra más grande de las 3 hipótesis) — win rate 31.1%, profit factor 0.430, expectancy -0.37R.
- El WFO converge al extremo más favorable del grid en los 3 folds y **sigue sin ser rentable ni in-sample**.
- Sin concentración por activo ni por período (a diferencia de SATAR-1) — el fracaso es parejo y estructural, no un accidente de muestra.
- El mecanismo de ejecución en sí es robusto (no frágil al ruido de precio) — el problema es la hipótesis de edge, no la implementación.

## 5. Qué sigue (decisión pendiente)

Con 3 hipótesis independientes rechazadas bajo el mismo protocolo riguroso, hay tres caminos honestos:

1. **Expandir a otro universo de activos** (forex, materias primas) — ninguna de las 3 hipótesis se ha probado fuera de cripto perpetuos.
2. **Probar una cuarta hipótesis** con paradigma distinto a "pullback" y "sweep" (ej. arbitraje estadístico entre activos correlacionados, o seguimiento de tendencia puro sin entrada por retroceso).
3. **Declarar el programa de investigación concluido** en cripto intradía con entrada discrecional-sistematizada: tres paradigmas de entrada razonables, formalizados sin ambigüedad y validados con el mismo rigor, no muestran edge.

**Regla que se mantiene sin excepción**: cualquier hipótesis nueva sigue el mismo protocolo (formalización previa sin mirar resultados → diagnóstico → multi-activo → WFO → Monte Carlo → veredicto), con holdout intocable y sin ajuste manual de parámetros fuera del WFO.

## 6. Cómo retomar (comandos)

```bash
cd code/python

# SATAR-1 / HYDRA / SWEEP comparten datasets (no versionados, ~40MB c/u)
python download_bulk_binance.py --symbol BTCUSDT --start 2020-01
# ... ETHUSDT (2020-01), SOLUSDT (2020-10), XRPUSDT (2020-01), BNBUSDT (2020-02)

# Re-correr diagnostico/WFO/MC de cualquier hipotesis (mismo patron):
python sweep_backtest.py --csv btcusdt_m5.csv --funnel
python sweep_wfo.py --grid coarse --jobs 6
python sweep_montecarlo.py --config-from-wfo --iters 5000
```

## 7. Decisiones técnicas que NO hay que repetir/redescubrir

- **Patrón de bug a vigilar en CUALQUIER motor nuevo** (encontrado 2 veces ya, en SATAR-1/HYDRA): la fórmula de equity para drawdown debe ser **compuesta** (`cumprod`), nunca aditiva (`cumsum`) — la aditiva puede producir equity negativo y drawdowns >100%, matemáticamente imposibles.
- `df.loc[:fecha]` de pandas incluye el extremo derecho — usar máscara estricta `df.index < fecha` en cualquier frontera de holdout.
- Al agrupar trades de varios activos, ordenar por `t_entry` antes de cualquier `cumsum()`/`cumprod()` de equity — si no, el resultado es path-dependent.
- Cualquier ratio tipo WFE que divida dos magnitudes que puedan ser negativas necesita guarda de signo explícita.
- El motor base (`satar_backtest.py`: indicadores, fricciones, position sizing, trailing EMA) está auditado y es reutilizable — nuevas hipótesis deben importar de ahí, no reimplementar desde cero.

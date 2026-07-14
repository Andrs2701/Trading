# Trading — Estado del Proyecto y Guía de Continuidad

**Última actualización:** 2026-07-10 · **Repo:** https://github.com/Andrs2701/Trading (rama `main`)
**Propósito de este documento:** punto de entrada único para retomar el proyecto — resume las hipótesis probadas, el veredicto de cada una, y qué sigue.

---

## 0. TL;DR

Se han probado **4 hipótesis de trading algorítmico en cripto perpetuos**, todas con el mismo protocolo de rigor (formalización → diagnóstico → multi-activo → Walk-Forward Optimization → Monte Carlo → veredicto, con holdout intocable y prohibición explícita de ajustar parámetros a mano mirando resultados). **Las 4 fueron rechazadas formalmente bajo WFO, pero la Hipótesis 4 demostró viabilidad estructural.**

| # | Hipótesis | Veredicto | Documentación |
|---|---|---|---|
| 1 | **SATAR-1**: pullback a la EMA50 (multi-timeframe) | ❌ NO APROBADO | `docs/archive/` (FASE-0…10) |
| 2 | **HYDRA**: SATAR-1 + filtro de régimen HMM/Hurst | ❌ NO APROBADO | `docs/HYDRA-resultados-veredicto.md` |
| 3 | **SWEEP**: liquidity sweep / stop hunt sobre estructura semanal | ❌ NO APROBADO | `docs/SWEEP-formalizacion.md`, `docs/SWEEP-resultados-veredicto.md` |
| 4 | **BREAKOUT-ATR**: momentum de ruptura de rango diario con expansión de volatilidad | ⚠️ NO APROBADO WFO / VIABLE | `docs/BREAKOUT-formalizacion.md`, `docs/BREAKOUT-resultados-veredicto.md` |

Las tres primeras hipótesis carecen de edge in-sample y out-of-sample. La cuarta hipótesis (BREAKOUT-ATR) es la única que arrojó una expectativa neta combinada positiva (+0.0032R) y rentabilidad real (+$2,043.15 en la cartera), demostrando la existencia de un edge real que falla temporalmente en consolidaciones largas pero triunfa en periodos expansivos.

## 1. Organización del repositorio

- **`docs/archive/`** — documentación completa de SATAR-1 (congelada).
- **`docs/SWEEP-*.md`** — hipótesis SWEEP (formalización y veredicto).
- **`docs/BREAKOUT-*.md`** — hipótesis BREAKOUT-ATR (formalización y veredicto).
- **`code/python/satar_*.py`** — motor base SATAR-1 (reutilizado por las demás estrategias).
- **`code/python/hydra_*.py`** — motor de HYDRA.
- **`code/python/sweep_*.py`** — motor de SWEEP.
- **`code/python/breakout_*.py`** — motor de BREAKOUT-ATR.

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

- Paradigma de reversión: opera cuando el precio barre wicks semanales H1 (168 velas) con volumen y cierra de vuelta dentro de la estructura.
- **5924 trades combinados** — win rate 31.1%, PF 0.430, expectancy -0.37R.
- El WFO in-sample no logró ser rentable en ningún combo. No hay edge en la hipótesis simple.

## 5. Hipótesis 4 — BREAKOUT-ATR (Momentum de Ruptura)

Ver `docs/BREAKOUT-formalizacion.md` (reglas exactas) y `docs/BREAKOUT-resultados-veredicto.md` (resultados completos). Resumen:

- Paradigma tendencial: opera la ruptura del rango de 24 horas con expansión de volatilidad H1 (cuerpo de vela H1 > 1.2x ATR) y volumen (> 1.5x MA).
- **2990 trades totales** — win rate 22.6%, PF 0.908, expectancy combinada en la línea base de **-0.071R**.
- **Edge demostrado:** SOLUSDT es rentable a **+0.139R** (+$9,552 de PnL).
- La optimización WFO arrojó una expectativa neta de cartera positiva de **+0.0032R** en la región no-holdout (la primera de las 4 hipótesis en lograrlo).
- Falla el criterio estricto de WFO debido a la ineficiencia temporal en las consolidaciones extendidas de 2023-2024. El Fold 3 OOS (mercado expansivo de 2025) fue altamente rentable (+0.0885R).

## 6. Qué sigue (decisión pendiente)

Para poner el proyecto en marcha en **modo demo (simulación en Bybit Testnet)** con una base sólida, los caminos recomendados son:

1.  **Refinar la Hipótesis 4 (Bollinger Squeeze Filter):** Modificar `breakout_backtest.py` para añadir un filtro de régimen de corto plazo basado en la compresión de las bandas de Bollinger diarias. Solo se operan breakouts si las bandas están expandiéndose (evitando consolidaciones maduras y falsas rupturas). Es la opción más rápida para modo demo.
2.  **Probar una quinta hipótesis (Pairs Trading / Arbitraje Estadístico):** Operar el spread de cointegración entre activos altamente correlacionados (ej. SOL vs ETH o BTC). Al ser mean-reverting, el edge es estructuralmente más estable ante comisiones.
3.  **Iniciar modo demo seco de BREAKOUT-ATR:** Correr la configuración congelada de la Hipótesis 4 limitando la operativa únicamente a activos de alta beta/volatilidad (SOLUSDT, ETHUSDT) donde el edge es rentable.

## 7. Cómo retomar (comandos)

```bash
cd code/python

# Descargar datos actualizados
python download_bulk_binance.py --symbol BTCUSDT --start 2020-01

# Correr diagnóstico base
python breakout_backtest.py --csv btcusdt_m5.csv --funnel

# Correr Walk-Forward Optimization
python breakout_wfo.py --grid coarse --jobs 4

# Correr simulación Monte Carlo
python breakout_montecarlo.py --config-from-wfo --iters 5000
```

## 8. Decisiones técnicas que NO hay que repetir/redescubrir

- **Fórmula de Equity:** Siempre compuesta (`cumprod`), nunca aditiva (`cumsum`) — la aditiva reporta drawdowns matemáticamente imposibles (>100%).
- **Mapeo causal:** Para cualquier indicador H1/D1, shift(1) antes de operar en M5 para evitar fugas de información.
- **Filtro de volumen:** El volumen relativo es un confirmador de momentum y de sweeps; sin volumen, la tasa de fakeouts en cripto se duplica.
- El motor base (`satar_backtest.py`: indicadores, fricciones, position sizing, trailing EMA) está auditado y es reutilizable — nuevas hipótesis deben importar de ahí, no reimplementar desde cero.

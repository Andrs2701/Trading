# Trading — Estado del Proyecto y Guía de Continuidad

**Última actualización:** 2026-07-23 · **Repo:** https://github.com/Andrs2701/Trading (rama `main`)
**Propósito de este documento:** punto de entrada único para retomar el proyecto — resume las hipótesis probadas, el veredicto de cada una, y qué sigue.

> **Nota 2026-07-21:** el proyecto pasó de "en desarrollo" a "desplegado en
> vivo" (`trading-bot-satar.onrender.com`, BREAKOUT-ATR/SOLUSDT, Bybit
> Testnet). Una auditoría del bot en producción encontró y corrigió varios
> problemas de honestidad/seguridad — ver `§9` para el detalle completo.

---

## 0. TL;DR

Se han probado **5 hipótesis de trading algorítmico** (4 en cripto perpetuos + 1 en forex/materias primas), todas con el mismo protocolo de rigor (formalización → diagnóstico → multi-activo → Walk-Forward Optimization → Monte Carlo → veredicto, con holdout intocable y prohibición explícita de ajustar parámetros a mano mirando resultados). **Las 5 fueron rechazadas formalmente bajo WFO, pero la Hipótesis 4 demostró viabilidad estructural.**

| # | Hipótesis | Veredicto | Documentación |
|---|---|---|---|
| 1 | **SATAR-1**: pullback a la EMA50 (multi-timeframe) | ❌ NO APROBADO | `docs/archive/` (FASE-0…10) |
| 2 | **HYDRA**: SATAR-1 + filtro de régimen HMM/Hurst | ❌ NO APROBADO | `docs/HYDRA-resultados-veredicto.md` |
| 3 | **SWEEP**: liquidity sweep / stop hunt sobre estructura semanal | ❌ NO APROBADO | `docs/SWEEP-formalizacion.md`, `docs/SWEEP-resultados-veredicto.md` |
| 4 | **BREAKOUT-ATR**: momentum de ruptura de rango diario con expansión de volatilidad | ⚠️ NO APROBADO WFO / VIABLE | `docs/BREAKOUT-formalizacion.md`, `docs/BREAKOUT-resultados-veredicto.md` |
| 5 | **Forex/Materias Primas**: SATAR-1 original sin recalibrar, sobre EURUSD/GBPUSD/USDJPY/XAUUSD | ❌ NO APROBADO | `docs/FOREX-resultados-veredicto.md` |

Las hipótesis 1, 2, 3 y 5 carecen de edge in-sample/out-of-sample creíble. La Hipótesis 4 (BREAKOUT-ATR) es la única que arrojó una expectativa neta combinada positiva (+0.0032R) y rentabilidad real (+$2,043.15 en la cartera) — aunque con riesgo de cola severo (Monte Carlo: drawdown de hasta -95% en escenarios plausibles). La Hipótesis 5 (forex) es un rechazo de otro tipo: no es que pierda dinero de forma clara, es que la regla original casi no dispara en ese mercado (120-331 trades en 15 años × 4 activos) y lo poco que dispara está esencialmente en cero.

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
3.  ~~**Iniciar modo demo seco de BREAKOUT-ATR**~~ — **ya en curso** (ver §9): desplegado en Render desde el 2026-07-20, demo Fase-9 de 90 días activa en Bybit Testnet sobre SOLUSDT.
4.  ~~**Hipótesis 5 (Forex/Materias Primas)**~~ — **completada, NO APROBADO** (ver §10 y `docs/FOREX-resultados-veredicto.md`): la regla original casi no dispara en forex y lo poco que dispara está en cero.

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

## 9. Auditoría del bot en vivo (2026-07-21)

El bot BREAKOUT-ATR/SOLUSDT lleva desplegado en Render (`trading-bot-satar.onrender.com`) desde el 2026-07-20. Una auditoría completa (código + dashboard en producción + Bybit) encontró varios problemas, todos corregidos en esta sesión salvo donde se indica:

1. **Dashboard engañoso (corregido).** Mostraba solo las métricas de SOLUSDT (el único activo rentable) como si representaran a todo el sistema, sin mencionar en ningún lado que el WFO dio **NO RENTABLE OOS** (`mean_oos=-0.3447`) ni que el Monte Carlo mostró **468% de concentración** del resultado en un solo activo. ETHUSDT (-53.8% DD histórico, -$4,066.72) y BTCUSDT (plano) solo eran visibles al hacer click en sus pestañas. Ahora hay un banner de veredicto siempre visible y un resumen de los 3 activos en una sola vista.
2. **Riesgo subido manualmente sin respaldo (corregido).** El 2026-07-20 a las 19:20 se subió `TRADING_RISK_PCT` de 1% a 2% ($2→$4/trade) y se aflojó `target_dd` de -10% a -20% ("para mayor velocidad") — justo lo opuesto de lo que sugiere el propio veredicto NO APROBADO. Revertido a 1%.
3. **Sin candado a mainnet (corregido).** No existía ninguna protección que impidiera pasar de testnet a dinero real sin revisión. Se añadió `assert_mainnet_allowed()` en `breakout_live.py`, que bloquea órdenes en mainnet salvo aprobación explícita (archivo `APROBADO_PARA_MAINNET.txt` o `MAINNET_APPROVED=true`).
4. **Demo Fase-9 nunca se actualizaba (corregido).** `demo_phase_tracker.json` llevaba en 0 trades desde el despliegue porque nada en el código escribía en él. Ahora `register_demo_trade()` registra cada cierre real (PnL vía `/v5/position/closed-pnl` de Bybit).
5. **Bug de seguridad preexistente en `check_position_closed()` (corregido).** Consultaba un endpoint privado de Bybit sin firmar; el error de autenticación resultante se interpretaba como "posición cerrada", arriesgando abrir una posición duplicada mientras la original seguía abierta en el exchange.
6. **El hilo del bot se duerme con el plan free de Render (mitigado, no resuelto de raíz).** `_start_background_bot()` corre dentro del mismo proceso web; Render duerme ese proceso tras ~15 min sin tráfico HTTP, matando el hilo que evalúa el mercado cada 60s. Confirmado en vivo: `live_state` mostraba `last_signal_ts=null` y `position=null`. Se añadió un ping cada 10 min vía GitHub Actions (`.github/workflows/keepalive.yml`) como mitigación gratuita inmediata; la solución robusta es pasar a un plan de Render que no duerma, o a un servicio de tipo *Background Worker*.
7. **Deploy directo a `main` sin CI/staging.** Se confirmó que un error de sintaxis introducido junto con el cambio de riesgo (punto 2) estuvo en producción ~90 minutos el 2026-07-20 antes de corregirse. No se cambió el flujo de deploy en esta sesión — queda como riesgo de proceso a decidir.
8. **El histórico mostrado no era el que realmente opera en vivo (corregido).** `historical_trades_summary.json` (y `trades_data_static.py`, que el dashboard prioriza) se generaban con `AdvancedBreakoutEngine` + filtro de compresión de Bollinger D1 (`test_bb_squeeze.py`) — una variante que nunca pasó por WFO ni Monte Carlo, distinta de `BreakoutEngine` + `FROZEN_CONFIG` que sí corre en producción. La diferencia no era cosmética: para ETHUSDT la variante sin validar decía PF 0.715 (PERDEDOR, -$4,066.72); con el motor real da PF 1.016 (prácticamente neutro, +$643.55). `export_trades_json.py` corregido para usar el motor real.

**Reconciliación de historial:** mientras se hacía esta auditoría, `origin/main` recibió una serie de hotfixes operativos directos (errores 500, carga de klines, filtros del dashboard) en paralelo. Ambos historiales se unificaron con un merge real (`--allow-unrelated-histories`, no squash ni force-push) que preserva la autoría completa de los dos lados.

## 10. Hipótesis 5 — Forex/Materias Primas (❌ NO APROBADO)

Se probó si la regla SATAR-1 original (sin recalibrar ningún parámetro P01-P37) tiene edge en forex — un mercado con microestructura distinta (sin comisión taker, spreads más bajos, sesiones horarias). Ver `docs/FOREX-resultados-veredicto.md` para el detalle completo. Resumen:

- **Activos:** EURUSD, GBPUSD, USDJPY, XAUUSD · **Fuente:** ticks de Dukascopy resampleados a M5, 2010 → presente.
- **Adaptaciones (solo infraestructura, no reglas de trading):** fricciones calibradas por par, offset D1 a las 22:00 UTC (cierre NY).
- **Bug importante encontrado durante esta fase:** pandas ignora silenciosamente `offset`/`origin` en `resample()` para frecuencias no-Tick-like como `'1D'` — el ajuste de sesión de la Fase F1 nunca había tenido efecto real hasta corregirse con un desplazamiento manual del índice.
- **WFO:** OOS pooled 69 trades, expectancy -0.054R (IS pooled 262 trades, +0.034R).
- **Monte Carlo** (config congelada, 120 trades no-holdout): expectancy base -0.0027R (prácticamente plano), fricciones estresadas FALLA (p25=-0.0614R), drawdown bootstrap moderado (p95=-17%, peor=-27%, mucho menos severo que BREAKOUT-ATR en cripto).
- **Veredicto:** a diferencia de las demás hipótesis, aquí no hay un resultado claramente negativo — hay muy poca señal (120-331 trades en 15 años × 4 activos) y lo que hay está esencialmente en cero. No se recomienda operar esta forma de la hipótesis.

## 11. Exploración — ¿ampliar el universo de activos de BREAKOUT-ATR? (2026-07-21)

Se evaluaron 5 candidatos nuevos (XRPUSDT, BNBUSDT ya tenían datos de Fase C; AVAXUSDT, ADAUSDT, LINKUSDT se descargaron) con la config congelada del WFO **sin re-optimizar nada** (`breakout_multiasset_frozen.py`, resultados en `results/breakout_multiasset_frozen.json`):

| Activo | Trades | PF | Expectancy | MaxDD |
|---|---|---|---|---|
| SOLUSDT (referencia) | 404 | 1.245 | +0.176R | -20.3% |
| **LINKUSDT** | 348 | 1.213 | **+0.163R** | -22.1% |
| AVAXUSDT | 397 | 1.106 | +0.090R | -18.6% |
| ETHUSDT | 506 | 1.016 | +0.028R | -48.7% |
| XRPUSDT | 383 | 0.972 | -0.004R | -28.5% |
| ADAUSDT | 374 | 0.968 | -0.007R | -32.2% |
| BTCUSDT | 522 | 0.841 | -0.124R | -57.6% |
| BNBUSDT | 446 | 0.792 | -0.155R | -54.2% |

LINKUSDT y AVAXUSDT fueron los únicos con expectancy positiva comparable a SOLUSDT. Se re-corrió el WFO y Monte Carlo completos con el universo ampliado (BTC/ETH/SOL/XRP/BNB/LINK/AVAX, 7 activos; logs en `results/wfo_expanded_link_avax_log.txt` y `results/mc_expanded_link_avax_log.txt`) para ver si esto cambia el veredicto:

- **WFO**: mean_oos_obj mejora de -0.3447 (5 activos) a **-0.0746** (7 activos) — mejora real, pero **sigue NO RENTABLE OOS**. Fold por fold: 2023 sigue claramente negativo (-0.092R, N=619), 2024 casi neutro (-0.015R), 2025 H1 positivo (+0.099R) — mismo patrón temporal que siempre: consolidación mata la estrategia, mercado expansivo la favorece.
- **Monte Carlo**: expectancy sube a +0.0405R (12x vs 0.0032R), fricciones estresadas ahora SÍ pasan (antes fallaban), concentración de activo baja de 468% a 78.5% (LINK ahora comparte el peso con SOL) — todas mejoras reales. **Pero el drawdown de bootstrap NO mejora**: p95 sigue en -78.7% (peor caso -95.2%), prácticamente igual de catastrófico que antes (-84.1%).

**Veredicto: NO agregar LINKUSDT/AVAXUSDT a la operativa en vivo.** El drawdown de Monte Carlo es la razón — un escenario plausible de -78% a -95% de la cuenta es inaceptable sin importar cuánto mejore la expectativa promedio. `wfo_results_breakout.json`/`montecarlo_results_breakout.json` en producción se dejaron en su versión original de 5 activos (respaldo en `results/*_5activos_original.json`) para no desalinear el dashboard, que solo muestra SOL/ETH/BTC.

### Segunda ronda (2026-07-23): screening de 18 candidatos más

A pedido del usuario ("no puedo irme con pocos trades y un solo activo"), se amplió el screening a 18 criptos líquidas más (sin re-optimizar nada, `breakout_multiasset_frozen.py`, resultados en `results/breakout_multiasset_frozen.json`). Los dos con expectancy destacable:

| Activo | Trades | PF | Expectancy | MaxDD |
|---|---|---|---|---|
| **INJUSDT** | 206 | 1.138 | **+0.100R** | -22.9% |
| **UNIUSDT** | 278 | 1.112 | **+0.084R** | **-18.3%** (el más bajo de todos los positivos, mejor que SOL) |

(El resto — DOGE, DOT, ATOM, NEAR, LTC, TRX, ETC, FIL, SAND, MANA, ALGO, ARB, OP, SUI, APT — quedó entre plano y negativo; ARBUSDT +0.063R y OPUSDT +0.048R también positivos pero con menos historial, 3-4 años.)

Se re-corrió el WFO y Monte Carlo con el universo ampliado a 11 activos (BTC/ETH/SOL/XRP/BNB/LINK/AVAX + INJ/UNI/ARB/OP; logs en `results/wfo_expanded2_11activos_log.txt` y `results/mc_expanded2_11activos_log.txt`):

- **WFO**: mean_oos_obj pasa a **positivo por primera vez en todo el proyecto** (+0.2892), pero el veredicto formal es **"SOBREOPTIMIZACIÓN"** (WFE=0.36, bajo el umbral de 0.4 para siquiera calificar "débil"). Fold por fold explica por qué: 2023 OOS negativo (-0.022R, N=887), 2024 OOS negativo (-0.009R, N=742), 2025 H1 OOS **+0.201R (N=307)** — un solo semestre, con menos de la mitad de los trades de cualquiera de los otros dos folds, carga todo el promedio positivo. Mismo patrón de siempre (consolidación mata, expansión favorece), ahora con más activos pero el mismo problema de fondo.
- **Monte Carlo** (3732 trades pooled): expectancy sube a +0.0479R, fricciones estresadas pasan (p25=+0.0234R), concentración de activo **por fin baja de la alarma** (49.6%, ok) y concentración temporal también (48.0%, ok) — 8 de 11 activos terminan en positivo (SOL +$10,291, AVAX +$6,569, LINK +$5,821, OP +$3,314, INJ +$2,546, UNI +$870, XRP +$147, ARB +$175; BTC -$4,554, BNB -$3,128, ETH -$1,314). **El drawdown de bootstrap NO mejora — de hecho empeora ligeramente**: p95=-81.9% (peor caso -96.2%, vs -84.1%/-78.7% de las rondas anteriores). Racha de pérdidas: p95=31, peor caso=54 operaciones seguidas.

**Por qué el drawdown no se mueve pese a todo lo demás mejorando:** la concentración (cuántos activos generan la ganancia) y el riesgo de racha (cuántas pérdidas seguidas puede tener la secuencia) son problemas *distintos*. Diversificar entre más criptos arregla el primero — ya no depende de un solo activo — pero no arregla el segundo, porque todas las criptos tienden a entrar en consolidación al mismo tiempo (están correlacionadas), y con win rate ~26% y riesgo fijo del 1% por operación, una racha larga de pérdidas simultánea en varios activos sigue siendo plausible y sigue componiendo hacia abajo con la misma fuerza. Agregar más activos correlacionados no reduce ese riesgo estructural.

**Veredicto: sigue sin recomendarse operar el universo ampliado con capital real.** El hallazgo positivo real de esta ronda — INJUSDT y UNIUSDT tienen edge crudo genuino, UNIUSDT en particular con el drawdown individual más bajo de todos los activos probados — queda documentado para si en el futuro se explora reducir el riesgo por operación (position sizing más conservador) en vez de solo agregar activos, que es la palanca que realmente podría atacar el problema de racha de pérdidas.

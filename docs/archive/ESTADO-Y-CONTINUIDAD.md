# SATAR-1 — Estado del Proyecto y Guía de Continuidad

**Última actualización:** 2026-07-09 · **Repo:** https://github.com/Andrs2701/Trading (rama `main`)
**Propósito de este documento:** que cualquiera (tú, o un asistente nuevo sin memoria de esta conversación) pueda retomar el proyecto exactamente donde quedó, sin releer todo el historial.

---

## 0. TL;DR — lo que hay que saber en 30 segundos

1. **La Fase 5 (WFO + Monte Carlo) se completó. Veredicto: NO APROBADO.** La metodología de Alex Ruiz, formalizada objetivamente en el Pilar C y probada sobre 5 activos cripto (BTC/ETH/SOL/XRP/BNB, 2020-2025, 683k+ velas M5/activo), **no muestra edge estadístico robusto**. Ver §5.
2. **6 de 7 criterios de aprobación de la Fase 5 fallan**: rentabilidad out-of-sample negativa y empeorando por fold, óptimo en pico aislado (no meseta), drawdown al percentil 95 de -24.3% (límite 15%), expectancy negativa bajo fricciones estresadas, concentración extrema por activo (192% del PnL neto viene de un solo activo) y por período calendario (166% del PnL neto viene solo de 2020-2022). Solo pasa la robustez al ruido de precio del gatillo.
3. **El holdout final (15%) NO se abrió** — el candidato ya fue rechazado por 6 criterios independientes antes de llegar a esa etapa; abrirlo no aportaría información y es un recurso de un solo uso.
4. **El sistema NO pasa a Fase 9 (demo con dinero).** Esta es la conclusión legítima del proyecto — la Fase 5 existe exactamente para poder llegar a este veredicto sin caer en sobreajuste ni data-snooping.
5. Durante la validación se auditó el código con revisión adversarial multi-agente y se encontraron y corrigieron **9 bugs reales** en el propio motor de validación (`satar_wfo.py`, `satar_montecarlo.py`, `satar_portfolio.py`) — incluidos 2 críticos: un WFE que podía mentir cuando el sistema pierde dinero, y un test de Monte Carlo que nunca podía detectar fragilidad. El veredicto negativo **sobrevivió** a esas correcciones — no es un artefacto de bugs de implementación.
6. **Próximos pasos posibles** (requieren tu decisión, ver §7): expandir a forex/materias primas (el corpus original de Alex Ruiz es multi-activo, no solo cripto), o declarar el proyecto concluido con este veredicto documentado.

---

## 1. Qué es este proyecto (mandato original)

Ingeniería inversa, formalización matemática, validación estadística y automatización de la metodología de trading de **Alex Ruiz** (YouTube, @AlexRuiiz), NO una estrategia inventada. Regla de oro del proyecto: **nada se acepta como rentable solo porque el youtuber lo dice — todo se demuestra con backtesting**. Arquitectura de 3 pilares:

- **Pilar C (edge)**: impulso–pullback–continuación multi-timeframe (D1 grande / H1 intermedia / M5 pequeña), EMA50 exponencial, Fibonacci 0.382–0.618, riesgo 1%/trade, trailing con EMA50 H1.
- **Pilar B (meta-capa)**: Hidden Markov Model de regímenes de mercado que modula la exposición (100%/50%/0%) — nunca re-optimiza parámetros de la estrategia.
- **Pilar A (infraestructura)**: canales de Donchian en 15m, solo como banco de pruebas de la tubería de ejecución (Bybit), sin pretensión de edge.

## 2. Estado por fase

| Fase | Documento | Estado |
|---|---|---|
| 0. Corpus | `FASE-0-corpus.md`, `FASE-0-audit.md` | ✅ Completa — 5 transcripciones en `corpus/` con trazabilidad |
| 1. Ingeniería inversa | `FASE-1-ingenieria-inversa.md` | ✅ Completa — 47+7+3 reglas etiquetadas [E]/[I]/[F] |
| 2. Formalización | `FASE-2-formalizacion.md` | ✅ Completa — máquina de estados, fórmulas exactas, 33 parámetros |
| 3. Validación | `FASE-3-validacion.md` | ✅ Completa — 8 ambigüedades resueltas, contradicciones y sesgos documentados |
| 4. Backtesting | `FASE-4-backtesting.md`, `FASE-4-diagnostico-embudo.md`, `FASE-4-multiactivo.md` | ✅ Completa — motor funcionando, diagnóstico del embudo de filtros, 5 activos probados (144 trades) |
| 5. Robustez | `FASE-5-robustez.md`, `FASE-5-wfo-resultados.md`, `FASE-5-montecarlo-resultados.md` | ✅ **Completa — WFO + Monte Carlo ejecutados. Veredicto: NO APROBADO** (ver §5) |
| 6. Riesgo | `FASE-6-riesgo.md`, `FASE-6-audit-completo.md` | ✅ Completa — kill-switch, position sizing, apalancamiento tope (P37), auditado y con bugs corregidos |
| 7. Automatización | `FASE-7-automatizacion.md` | ✅ Motor Python + Pine v6 completos. `satar_live.py` (ejecutor dry-run/testnet Bybit) funcional. MQL5 en plantilla (módulos G/I con TODO, no operable) |
| 8. Plataforma | `FASE-8-plataforma.md` | ✅ Completa — decisión: Python+Bybit para cripto, MT5 para forex, TradingView solo monitoreo |
| 9. Demo 90 días | `FASE-9-demo.md` | ⛔ **Bloqueada — no se cumplió la precondición** (aprobar Fase 5). No iniciar sin nueva evidencia (ej. universo forex) |
| 10. Producción | `FASE-10-produccion.md` | ⛔ No aplica — depende de Fase 9 |

## 3. Hallazgo inicial — primer backtest, solo BTC (2026-07-07)

**Dataset:** BTCUSDT perpetuo, M5, fusión Binance Vision (2020-01→2026-04) + Bybit API (2026-04→07). 685.428 velas, **0 huecos >30min**. Comisiones/spread/slippage modelados (FASE-4 §3).

| Métrica | Resultado real | Declarado por Alex Ruiz |
|---|---|---|
| Trades (6.5 años) | 37 (5.7/año) | ~80/año |
| Win Rate | **16.2%** | 57% |
| Profit Factor | 0.625 | (implícito >1.5) |
| Expectancy | **-0.186R** | +0.427% (positiva) |
| R medio ganador / perdedor | +2.00 / -0.61 | — (el trailing SÍ funciona) |

Este resultado con un solo activo fue el disparador de todo el trabajo posterior (§4-5): diagnóstico del embudo, expansión multi-activo, y finalmente la Fase 5.

## 4. Diagnóstico y multi-activo (Fase 4 completa)

- **Diagnóstico del embudo** (`FASE-4-diagnostico-embudo.md`): el problema está en la **entrada**, no en la salida. Los filtros G1 (ADX/ER limpio) y G4 (desaceleración) eliminan la mayoría de las señales candidatas; el patrón doble-techo/doble-suelo casi nunca dispara en cripto. El trailing y el TP producen la asimetría correcta (ganadores grandes, perdedores chicos) — no es ahí donde está el problema.
- **Multi-activo** (`FASE-4-multiactivo.md`): BTC/ETH/SOL/XRP/BNB, 144 trades combinados. Todos negativos, pero el margen es pequeño (ETH casi en equilibrio) — el win-rate real está solo 2-6 puntos por debajo del win-rate de equilibrio que exige la asimetría del trailing. Esto motivó ejecutar el WFO antes de concluir nada.

## 5. FASE 5 — Resultados finales y veredicto (2026-07-09)

Documentos completos: `docs/FASE-5-wfo-resultados.md` (WFO) y `docs/FASE-5-montecarlo-resultados.md` (Monte Carlo + sensibilidad + estabilidad + veredicto integrado).

### 5.1 Auditoría previa (importante para confiar en el resultado)

Antes de confiar en los resultados de `satar_wfo.py` y `satar_montecarlo.py`, se corrieron **2 workflows de revisión adversarial multi-agente** que encontraron y corrigieron **9 bugs reales**:

- **Crítico**: el cálculo de WFE (`mean_oos/mean_is`) podía dar un ratio positivo engañoso cuando ambos eran negativos — corregido con guarda de signo explícita.
- **Alto**: el drawdown se calculaba sobre trades de varios activos concatenados sin ordenar cronológicamente, subestimando el riesgo real de una cuenta compartida con activos correlacionados (verificado: el mismo cálculo pasó de -6.5% a -10.8% tras el fix).
- **Crítico**: el test de Monte Carlo de robustez al ruido de precio (MC-3) tenía una falla matemática que lo hacía reportar "ROBUSTO" siempre, sin importar los datos — corregido con una métrica que sí puede fallar.
- **Alto**: fuga de holdout por slicing inclusivo de pandas (`.loc[:fecha]` incluye el extremo) en varias funciones — corregido con máscaras estrictas.
- Más 5 bugs adicionales (constante arbitraria en el test de fricciones, tercios de estabilidad repartidos por cantidad de trades en vez de tiempo calendario, Sharpe/Sortino inflados ~2.5x, recovery_factor mal calculado, piso de años demasiado permisivo).

**El veredicto negativo sobrevivió a las 9 correcciones** — no es un artefacto de errores de implementación.

### 5.2 Walk-Forward Optimization

Grid reducido (3 de 6 parámetros optimizables, justificado por presupuesto de cómputo), 3 folds anclados-rodantes 2020→2025-07 (holdout intocable después). Config ganadora idéntica en los 3 folds: `er_clean=0.30, er_arrive=0.26, decel_max=0.45`.

| Fold | IS Expectancy | OOS Expectancy |
|---|---:|---:|
| F1 (2020-23 → 2023-24) | **+14.1%** | **-1.8%** |
| F2 (2020-24 → 2024-25) | **+8.7%** | **-7.8%** |
| F3 (2020-25 → 2025 H1) | **+6.3%** | **-15.8%** |

Degradación monótona IS→OOS, cada vez peor — firma clásica de sobreajuste. Además, el óptimo **no está en meseta**: en F2/F3, mover `decel_max` un solo paso de grid (0.45→0.60) colapsa el resultado a negativo. WFE = -0.44, veredicto: **NO RENTABLE OOS**.

### 5.3 Monte Carlo, sensibilidad, estabilidad

Sobre la config congelada del WFO, período completo no-holdout (132 trades):

| Prueba | Resultado | Umbral | Veredicto |
|---|---:|---:|:---:|
| DD al percentil 95 (bootstrap) | -24.3% | <15% | ❌ FALLA |
| Expectancy con fricciones estresadas (p25) | -0.0015R | >0 | ❌ FALLA |
| Óptimo en meseta | Pico aislado | meseta | ❌ FALLA |
| Concentración por activo | 192% (solo ETH) | <50% | ❌ FALLA |
| Concentración temporal | 166% (solo 2020-22) | <60% | ❌ FALLA |
| Robustez a ruido de precio | 0.8% inversión | <40% | ✅ PASA |

**Hallazgo adicional grave**: el parámetro `arrive_n` (no optimizable, fijo por protocolo) es extremadamente sensible — moverlo ±20% invierte el signo completo del resultado (de +3.8%R a -15.5%R). El resultado "positivo" del período completo depende de un parámetro que nunca fue validado por robustez.

### 5.4 Veredicto final

> **NO APROBADO.** 6 de 7 criterios de la Fase 5 fallan de forma independiente. El sistema no pasa a Fase 9. El holdout no se abrió (candidato ya rechazado antes de esa etapa). Esta es una conclusión legítima y documentada del proyecto.

## 6. Inventario de archivos (actualizado)

```
SATAR-1/
├── README.md                              Índice y quickstart
├── corpus/                                5 transcripciones fuente (trazabilidad)
├── docs/
│   ├── FASE-0…3, 6…10 (*.md)              Documentos por fase (sin cambios)
│   ├── FASE-4-backtesting.md              Plan original de backtesting
│   ├── FASE-4-diagnostico-embudo.md       Diagnóstico del embudo de filtros (BTC, 6.5 años)
│   ├── FASE-4-multiactivo.md              Backtests multi-activo (5 criptos, 144 trades)
│   ├── FASE-5-robustez.md                 Protocolo diseñado (WFO, MC, sensibilidad)
│   ├── FASE-5-wfo-resultados.md           Resultados reales del WFO + auditoría
│   ├── FASE-5-montecarlo-resultados.md    Resultados MC/sensibilidad/estabilidad + VEREDICTO FINAL
│   └── ESTADO-Y-CONTINUIDAD.md            ESTE ARCHIVO
├── code/python/
│   ├── satar_backtest.py                  Motor de referencia (máquina de estados FASE-2)
│   ├── satar_portfolio.py                 Consolidador de métricas de portfolio
│   ├── satar_wfo.py                       Walk-Forward Optimization (con fixes de auditoría)
│   ├── satar_montecarlo.py                Monte Carlo + sensibilidad + estabilidad (con fixes)
│   ├── satar_live.py                      Ejecutor demo/live Bybit v5 (dry-run por defecto)
│   ├── download_bulk_binance.py           Descarga masiva mensual Binance Vision (recomendado)
│   ├── {btc,eth,sol,xrp,bnb}usdt_m5.csv   Datasets locales (NO versionados, .gitignore)
│   ├── trades_{sym}_{base,hmm}.csv        Resultados de backtest por activo (SÍ versionados)
│   └── results/
│       ├── funnel_{sym}.json              Diagnóstico de embudo por activo
│       ├── portfolio_metrics.json         Métricas agregadas del portfolio
│       ├── wfo_results.json               Resultados completos del WFO
│       └── montecarlo_results.json        Resultados completos de Monte Carlo
├── code/pine/SATAR1_PilarC.pine           Estrategia TradingView v6
└── code/mql5/SATAR1_PilarC.mq5            Plantilla MT5 (módulos G/I incompletos — NO operar)
```

## 7. Próximos pasos posibles (requieren tu decisión)

Con el veredicto de la Fase 5 en mano, hay dos caminos honestos — ninguno es "seguir intentando forzar un resultado positivo en cripto":

1. **Expandir a forex/materias primas.** El corpus original de Alex Ruiz es multi-activo (no solo cripto); el propio ESTADO anterior ya señalaba esto como hipótesis no descartada. Requeriría: fuente de datos (Dukascopy gratuito), adaptar el motor (ya es agnóstico de activo), y repetir el protocolo completo (Fases 4-5) sobre ese universo — sin reutilizar ni sesgar con lo aprendido en cripto.
2. **Declarar el proyecto concluido** con este veredicto: la metodología de Alex Ruiz, formalizada objetivamente, no muestra edge estadístico verificable en el universo cripto probado. Esto es un resultado de investigación válido y ya está completamente documentado.

**Lo que NO se debe hacer**: tocar los 33 parámetros a mano para "mejorar" el resultado, ampliar el grid del WFO hasta que algo salga positivo, o repetir el Monte Carlo con distintas semillas hasta que pase — eso es exactamente el data-snooping que la Fase 3 prohibió desde el principio.

## 8. Cómo retomar (comandos)

```bash
cd code/python

# Regenerar datasets si hace falta (no versionados, ~40MB cada uno)
python download_bulk_binance.py --symbol BTCUSDT --start 2020-01
python download_bulk_binance.py --symbol ETHUSDT --start 2020-01
# ... SOLUSDT (2020-10), XRPUSDT (2020-01), BNBUSDT (2020-02)

# Re-correr un backtest individual
python satar_backtest.py --csv btcusdt_m5.csv --trail I
python satar_backtest.py --csv btcusdt_m5.csv --hmm

# Diagnóstico del embudo de filtros
python satar_backtest.py --csv btcusdt_m5.csv --funnel

# Consolidar portfolio multi-activo
python satar_portfolio.py

# Re-correr el WFO (smoke test primero, luego real)
python satar_wfo.py --smoke
python satar_wfo.py --grid coarse --jobs 6

# Monte Carlo sobre la config congelada del último WFO
python satar_montecarlo.py --config-from-wfo --iters 5000
```

## 9. Decisiones y hallazgos técnicos que NO hay que repetir/redescubrir

- El motor Python es la **fuente de verdad**; Pine v6 es una traducción con aproximaciones documentadas en su cabecera (A1–A3) — paridad formal aún pendiente por falta de barras suficientes en TradingView plan Basic.
- `download_bulk_binance.py` (Binance Vision) es muy superior a `download_data.py` (API Bybit) para historia larga — usar el primero.
- Kill-switch mide contra el equity de INICIO DE CADA PERIODO, apalancamiento tope 5×equity (P37), neckline doble-techo/suelo (G5c) — todo implementado en Python y Pine.
- **Patrones de bug a vigilar si se toca `satar_wfo.py`/`satar_montecarlo.py` de nuevo** (encontrados por auditoría, ver §5.1): (a) `df.loc[:fecha]` de pandas incluye el extremo derecho — usar máscara estricta `df.index < fecha` cerca de cualquier frontera de holdout; (b) al agrupar (`pool`) trades de varios activos, **ordenar por `t_entry` antes de cualquier `cumsum()`** de equity/drawdown — si no, el resultado es path-dependent y subestima el riesgo; (c) cualquier ratio tipo WFE que divida dos magnitudes que puedan ser negativas necesita guarda de signo explícita, no solo guarda de división-por-cero.
- **NO pagar TradingView todavía** — no resuelve el problema de paridad y todo lo demás es gratuito en esta etapa. El primer gasto justificado del proyecto sería un VPS (~US$5-10/mes), y solo si se decide continuar a Fase 9 con un universo distinto que sí apruebe la Fase 5.

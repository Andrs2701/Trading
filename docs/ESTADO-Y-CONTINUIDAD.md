# SATAR-1 — Estado del Proyecto y Guía de Continuidad

**Última actualización:** 2026-07-07 · **Repo:** https://github.com/Andrs2701/Trading (rama `main`)
**Propósito de este documento:** que cualquiera (tú, o un asistente nuevo sin memoria de esta conversación) pueda retomar el proyecto exactamente donde quedó, sin releer todo el historial.

---

## 0. TL;DR — lo que hay que saber en 30 segundos

1. Las **11 fases del plan (0–10) están documentadas** en `docs/FASE-0…10-*.md` y el código base existe (Python, Pine v6, plantilla MQL5).
2. **Se corrió el primer backtest con datos reales completos** (BTCUSDT, 6.5 años, 685.428 velas M5, 2020-01-01 → 2026-07-07, sin huecos). Resultado: `code/python/trades_base.csv` y `trades_hmm.csv`.
3. **El resultado es NEGATIVO.** Ver §3 — Win Rate real 16.2% vs. el 57% que declara Alex Ruiz en los videos. Esto es un hallazgo válido del proyecto, no un error: la Fase 3/4 existen precisamente para poder falsear esto.
4. **Lo que falta antes de sacar conclusiones firmes:** correr WFO/Monte Carlo (Fase 5) sobre este resultado, probar el universo multi-activo completo (no solo BTC), y diagnosticar si el problema es de calibración de parámetros o del edge en sí. Ver §5.

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
| 4. Backtesting | `FASE-4-backtesting.md` | ⚠️ **Plan completo + motor funcionando + PRIMERA CORRIDA REAL HECHA (ver §3). Falta: universo multi-activo, partición IS/OOS/holdout formal** |
| 5. Robustez | `FASE-5-robustez.md` | ⚠️ Protocolo diseñado (WFO, Monte Carlo, sensibilidad) — **NO ejecutado todavía** sobre datos reales |
| 6. Riesgo | `FASE-6-riesgo.md`, `FASE-6-audit-completo.md` | ✅ Completa — kill-switch, position sizing, apalancamiento tope (P37), auditado y con bugs corregidos |
| 7. Automatización | `FASE-7-automatizacion.md` | ✅ Motor Python + Pine v6 completos. `satar_live.py` (ejecutor dry-run/testnet Bybit) funcional. MQL5 en plantilla (módulos G/I con TODO, no operable) |
| 8. Plataforma | `FASE-8-plataforma.md` | ✅ Completa — decisión: Python+Bybit para cripto, MT5 para forex, TradingView solo monitoreo |
| 9. Demo 90 días | `FASE-9-demo.md` | ✅ Protocolo especificado (≥150 trades, PF>1.5, DD<10%) — **no iniciado** (precondición: aprobar Fase 5 primero) |
| 10. Producción | `FASE-10-produccion.md` | ✅ Protocolo especificado — no aplica todavía |

## 3. HALLAZGO CLAVE — primer backtest con datos reales (2026-07-07)

**Dataset:** BTCUSDT perpetuo, M5, fusión Binance Vision (2020-01→2026-04) + Bybit API (2026-04→07). 685.428 velas, **0 huecos >30min** (integridad verificada). Comisiones/spread/slippage modelados (FASE-4 §3).

### Resultado Pilar C solo (`trades_base.csv`)

| Métrica | Resultado real | Declarado por Alex Ruiz | Divergencia |
|---|---|---|---|
| Trades (6.5 años) | 37 (5.7/año) | ~80/año | Muy por debajo — esperado con 1 solo activo (ver FASE-3 §2 C2) |
| Win Rate | **16.2%** | 57% | **Enorme** |
| Profit Factor | 0.625 | (implícito >1.5) | Negativo |
| Expectancy | **-0.186R** | +0.427% (positiva) | **Signo opuesto** |
| Max Drawdown | -10.35% | <10% (su cifra) | Similar orden pero sistema pierde dinero |
| CAGR | -1.1% | ~34% anual | **Signo opuesto** |
| Retorno total 6.5 años | -6.93% | — | Negativo |
| Racha máx. de pérdidas | 13 | — | Muy alta |
| R medio ganador / perdedor | +2.00 / -0.61 | — | El trailing SÍ funciona (asimetría correcta) |

### Resultado Pilar C + Pilar B/HMM (`trades_hmm.csv`)

35 trades, WR 17.1%, PF 0.549, expectancy -0.198R, DD -9.69%, CAGR -1.09%. **El HMM no rescata el resultado** — filtra 2 trades pero no cambia el signo.

### Lectura honesta de esto

- **No es (necesariamente) un fallo de código**: el smoke-test sintético sigue dando resultados coherentes, los indicadores están verificados, y el patrón "pocos TP grandes, muchos SL pequeños con trailing" es consistente con el diseño (R+2.0 / R-0.61 confirma que el trailing protege capital como debía).
- **El WR de 16% vs. 57% declarado es la divergencia más grave del proyecto hasta ahora.** Hipótesis a investigar (ninguna descartada aún):
  1. **Filtros G1–G6 demasiado estrictos o mal calibrados** (el diagnóstico previo con 190 días ya mostró que el embudo es muy selectivo — ver README).
  2. **Definición de "llegada acelerada" u otro parámetro no optimizable** puede estar sesgado (ninguno de los 33 parámetros fue calibrado todavía — todos están en su valor por defecto de la Fase 2, nunca se corrió el WFO de la Fase 5).
  3. **Un solo activo (BTC) no es representativo** — el propio corpus dice que Alex Ruiz opera multi-activo; puede que el patrón funcione en forex/oro y no en cripto 5m.
  4. **Posible bug real no detectado**: candidatos a revisar primero — el filtro de "zona de entrada" (I4/I5) podría estar dejando pasar muy pocos setups de calidad, o el TP (extremo estructural) podría ser sistemáticamente peor colocado que el SL.
  5. **La estrategia declarada por Alex Ruiz simplemente no es rentable tal como está formalizada** — resultado legítimo y sería la conclusión del proyecto si sobrevive a la Fase 5.

**Esto NO es motivo para relajar reglas ad-hoc.** El protocolo del proyecto (Fase 5, WFO+Monte Carlo+sensibilidad) es exactamente el mecanismo diseñado para diferenciar entre "mal calibrado" y "no funciona". Saltárselo y tocar parámetros a mano para forzar un resultado positivo sería el data-snooping que la Fase 3 ya identificó y prohibió (Pilar A, sesgo S1).

## 4. Inventario de archivos

```
SATAR-1/
├── README.md                          Índice y quickstart
├── corpus/                            5 transcripciones fuente (trazabilidad)
├── docs/
│   ├── FASE-0 … FASE-10 (*.md)        Documentos por fase
│   ├── FASE-6-audit-completo.md       Auditoría de código (bugs encontrados/corregidos)
│   ├── informe_validacion_y_pruebas.md Ruta de pruebas paso a paso
│   └── ESTADO-Y-CONTINUIDAD.md         ESTE ARCHIVO
├── code/
│   ├── python/
│   │   ├── satar_backtest.py          Motor de referencia (máquina de estados FASE-2)
│   │   ├── satar_live.py              Ejecutor demo/live Bybit v5 (dry-run por defecto)
│   │   ├── download_data.py           Descarga incremental API Bybit (con reintentos/fusión)
│   │   ├── download_bulk_binance.py   Descarga masiva mensual Binance Vision (recomendado)
│   │   ├── btcusdt_m5.csv             Dataset local 2020-2026 (NO versionado, 41MB, .gitignore)
│   │   └── trades_base.csv / trades_hmm.csv   Resultados del backtest de §3 (SÍ versionados)
│   ├── pine/SATAR1_PilarC.pine        Estrategia TradingView v6 (guardada también en tu cuenta TV)
│   └── mql5/SATAR1_PilarC.mq5         Plantilla MT5 (módulos G/I incompletos — NO operar)
```

## 5. Próximos pasos concretos (en orden)

1. **Diagnóstico del hallazgo de §3** (prioridad inmediata): instrumentar el motor para contar cuántos setups pasan cada filtro (G1…G6, I1…I7) sobre el dataset completo — ya se hizo algo similar con 190 días, repetir con los 6.5 años. Objetivo: aislar si el problema está en la entrada (pocos setups, calidad mala) o en la salida (TP mal ubicado, SL demasiado ajustado).
2. **Ejecutar la Fase 5 (WFO)** sobre este dataset: optimizar los 6 parámetros permitidos (P09, P11, P15, P17, P21, P22) solo en el 60% in-sample, evaluar en 25% OOS. Esto puede revertir o confirmar el signo negativo.
3. **Multi-activo**: descargar y correr ETHUSDT, SOLUSDT como mínimo (mismo `download_bulk_binance.py`), y forex vía Dukascopy si se quiere cubrir el universo real de Alex Ruiz.
4. **Monte Carlo** (reordenamiento de trades, estrés de fricciones) una vez haya una configuración post-WFO.
5. Solo si la Fase 5 aprueba (WFE≥0.5, expectancy OOS positiva) → continuar a paridad Pine↔Python y luego Fase 9 (demo).
6. Si la Fase 5 **no** aprueba → el veredicto documentado del proyecto es que la metodología de Alex Ruiz, tal como fue formalizada objetivamente, no muestra edge estadístico en BTC 5m — y eso se reporta como conclusión, no se oculta.

## 6. Cómo retomar (comandos)

```bash
cd C:\Users\Andres\SATAR-1\code\python

# Ya existe btcusdt_m5.csv con 2020-2026 (41MB, no se sube a git).
# Si no está, regenerarlo:
python download_bulk_binance.py --symbol BTCUSDT --start 2020-01

# Re-correr el backtest base (resultado ya documentado en §3):
python satar_backtest.py --csv btcusdt_m5.csv --trail I

# Con el filtro HMM:
python satar_backtest.py --csv btcusdt_m5.csv --hmm

# Diagnóstico del embudo de filtros (adaptar rango de fechas):
# ver el patrón de instrumentación usado en la sesión anterior sobre eng._bias_check
```

## 7. Decisiones y hallazgos técnicos que NO hay que repetir/redescubrir

- El motor Python es la **fuente de verdad**; Pine v6 es una traducción con aproximaciones documentadas en su cabecera (A1–A3) — paridad formal aún pendiente de validar por falta de barras suficientes en TradingView plan Basic (necesita ~72.000 velas de warm-up, ni el plan Premium alcanza).
- `download_data.py` (API Bybit) sirve para actualizaciones incrementales recientes; `download_bulk_binance.py` (Binance Vision) es muy superior para historia larga — usar este último como primera opción.
- Kill-switch corregido para medir contra el equity de INICIO DE CADA PERIODO (día/semana/mes), no contra el capital inicial de toda la cuenta.
- Apalancamiento nocional tope 5×equity (P37) ya implementado en Python y Pine.
- El neckline del patrón doble-techo/doble-suelo (G5c) está implementado en ambos lenguajes.
- **NO pagar TradingView todavía** — no resuelve el problema de paridad (ni el plan más caro tiene suficientes velas) y todo lo demás (datos, backtesting, demo) es gratuito en esta etapa. El primer gasto justificado del proyecto es un VPS (~US$5-10/mes) recién en la Fase 9.

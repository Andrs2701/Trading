# SWEEP — Formalización de la estrategia (equivalente Fase 2/3)

**Fecha:** 2026-07-09 · **Estado:** formalización previa a implementación (Fase S1 del plan de continuidad post-Fase 5)
**Origen:** hipótesis propia (NO reverseingeniería de un corpus externo) — microestructura de mercado: *liquidity sweep / stop hunt* en perpetuos cripto apalancados. No hereda ningún parámetro de SATAR-1/HYDRA; solo reutiliza infraestructura de motor (indicadores, fricciones, position sizing).

Este documento existe para resolver TODAS las ambigüedades **antes** de escribir `sweep_backtest.py`, siguiendo la misma disciplina anti-data-snooping que exigió la Fase 3 original: nada se decide mirando resultados de backtest.

---

## 1. Regla de estructura (H1)

En cada cierre de vela H1:
```
resistance[t] = max(H1.high[t-168 : t])   # 168 velas H1 = 1 semana, ventana rodante
support[t]    = min(H1.low[t-168 : t])
```
Máximo/mínimo simple, sin pivotes ni clustering — es exactamente lo que se especificó originalmente ("precio máximo y mínimo de las últimas 168 horas"). Se recalcula en cada cierre H1 nuevo.

## 2. Detección del sweep (M5) — regla exacta, sin ambigüedad

En cada vela M5 **cerrada**:

**Short (barrido de resistencia):**
```
sweep_short = M5.high[m] > resistance[g]  AND  M5.close[m] < resistance[g]
```
**Long (barrido de soporte):**
```
sweep_long  = M5.low[m]  < support[g]     AND  M5.close[m] > support[g]
```
`resistance[g]`/`support[g]` es el valor de la última vela H1 cerrada (`g` = índice H1 mapeado a `m`, mismo mecanismo causal que usa `satar_backtest.py`). **Se usa el `close` de la vela M5**, no el cuerpo ni ninguna otra definición — esto resuelve la ambigüedad original de "cierre por debajo de resistencia".

## 3. Confirmación de volumen

```
vol_ok = M5.volume[m] > vol_spike_mult × MA20(M5.volume)[m]
```
`MA20` sobre las 20 velas M5 anteriores (reutiliza `vol_ma()` ya implementado en `hydra_backtest.py`). Señal válida solo si `sweep_short/long AND vol_ok` en la misma vela `m`.

## 4. Take Profit — resuelto (sin condición OR ambigua)

La especificación original tenía una ambigüedad real: *"extremo opuesto de la estructura **o** reversión a EMA50 H1"* sin criterio de desempate. Se resuelve así:

- **TP único = extremo opuesto de la estructura** (`support[g]` para short, `resistance[g]` para long), congelado en el momento de la señal (no se recalcula después de entrar).
- **La EMA50 H1 queda reservada exclusivamente para el trailing** (§6) — no es un target alternativo. Esto es consistente con lo que la especificación original ya asignaba al trailing, y elimina la ambigüedad sin inventar una regla nueva.
- **Filtro de calidad**: si `R:R = |entry - TP| / |entry - SL| < rr_min` (default 3.0), el trade se descarta — mismo patrón de sanidad que `rr_min` en SATAR-1 (§6 del motor original).

## 5. Entrada — causal, sin look-ahead

Señal confirmada en el cierre de la vela M5 `m` (sweep + volumen) → entrada a mercado en la **apertura de la vela `m+1`**, con fricciones (spread/2 + slippage) aplicadas igual que en `satar_backtest.py::_enter`. Nunca se entra en la misma vela que generó la señal.

## 6. Stop Loss y Trailing

- **SL inicial**: extremo del wick de la vela de barrido ± buffer — `M5.high[m] + buf_atr×ATR_M5` (short) / `M5.low[m] - buf_atr×ATR_M5` (long).
- **Sanidad**: distancia SL-entrada debe estar en `[stop_min_atr, stop_max_atr] × ATR_M5` (0.15–3.0, igual que SATAR-1) — si no, no se opera.
- **Trailing**: EMA50(H1) ± `trail_buf_atr×ATR_H1`, actualizado en cada cierre H1, solo se ajusta a favor (nunca se afloja) — mismo mecanismo que `satar_backtest.py::_manage`.

## 7. Position sizing y fricciones

Idénticos a SATAR-1 para que los resultados sean comparables: riesgo 1% del equity por trade, tope de apalancamiento 5×equity (P37), fricciones `fee_pct=0.00055 · spread_pct=0.0002 · slip_pct=0.0002`. Un solo trade abierto a la vez (sin pirámides).

## 8. Parámetros — lista fija, registrada ANTES de tocar código

### No optimizables (identidad estructural de la estrategia, fijos siempre)
| Parámetro | Valor | Por qué es fijo |
|---|---|---|
| `structure_lookback_h1` | 168 (1 semana) | Define qué es "estructura" — cambiar esto cambia la estrategia, no la calibra |
| `vol_ma_window` | 20 velas M5 | Ventana estándar, no forma parte de la hipótesis de edge |
| `ema_trail_n` | 50 (H1) | Mismo mecanismo de trailing que SATAR-1, ya validado como funcional |
| `atr_n` | 14 | Estándar |
| `stop_min_atr` / `stop_max_atr` | 0.15 / 3.0 | Sanidad de ejecución, no edge |
| `risk_pct` / `leverage_cap` | 0.01 / 5.0 | Gestión de riesgo (Fase 6), no se toca |

### Optimizables — ÚNICOS 4 que entrarán al WFO (Fase S4)
| Parámetro | Default | Rango de grid propuesto |
|---|---|---|
| `vol_spike_mult` | 1.5 | [1.2, 1.5, 1.8, 2.0] |
| `buf_atr` (SL) | 0.15 | [0.10, 0.15, 0.20] |
| `rr_min` | 3.0 | [2.0, 3.0, 4.0] |
| `trail_buf_atr` | 0.10 | [0.05, 0.10, 0.15] |

**Regla anti-data-snooping explícita**: estos 4 parámetros solo se ajustan dentro del WFO (Fase S4), nunca a mano mirando el resultado de un backtest suelto. Si en la Fase S2 (diagnóstico single-asset) el resultado se ve mal, **no se toca ningún número** — se documenta y se sigue al siguiente paso del plan.

## 9. Instrumentación esperada (embudo, Fase S2)

Igual que se hizo para SATAR-1: contar por cada vela M5 cuántas veces se cumple cada condición en cascada (`sweep_detectado → vol_ok → sanidad_stop → rr_ok → entrada`), para saber desde el principio si la frecuencia de señales es suficiente para significancia estadística — un sweep sobre estructura semanal es plausible que sea más raro que un pullback intradía, y es mejor descubrirlo aquí que después de un WFO completo.

## 10. Qué NO cubre esta formalización (fuera de alcance por ahora)

- Filtro de régimen (HMM/Hurst) — HYDRA ya demostró que esa capa no rescata un edge inexistente; SWEEP se prueba primero en su forma más simple.
- Múltiples niveles de estructura (solo 1 semana, no se combinan varios lookbacks).
- Salidas parciales / scaling out — una sola posición, un solo TP.

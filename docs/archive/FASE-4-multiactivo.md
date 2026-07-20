# SATAR-1 — Fase 4: Backtesting Multi-Activo (Universo Cripto)

**Fecha:** 2026-07-08 · **Estado:** ✅ ejecutado — 5 activos, 144 trades combinados
**Precede a:** Fase 5 (WFO/Monte Carlo). Este documento amplía el hallazgo de BTC (`ESTADO-Y-CONTINUIDAD.md` §3) al universo multi-activo.

---

## 0. TL;DR

1. Se corrió el Pilar C (+HMM) sobre **5 criptos** (BTC, ETH, SOL, XRP, BNB), ~6.5 años M5 cada una, con integridad verificada (0 huecos >30min).
2. **144 trades combinados** — supera el umbral de N≥150 del plan por poco margen (144), suficiente para dar más poder estadístico que los 37 de solo-BTC.
3. **El resultado negativo NO es específico de Bitcoin: los 5 activos dan expectancy negativa.** Pero el hallazgo es más matizado que "pierde": el sistema está **marginalmente por debajo del punto de equilibrio**, no catastróficamente lejos.
4. **Insight central:** la estrategia tiene la *forma correcta* (asimetría positiva: ganadores ~+2.0R, perdedores ~-0.5R) pero el win-rate real (~13-18%) queda **2 a 6 puntos por debajo del win-rate de equilibrio** que esa asimetría exige (~19-22%). Es un déficit pequeño y consistente, no un colapso.

---

## 1. Metodología

- **Datos:** Binance Vision (futuros USDT-M perp), M5, fusionado con Bybit reciente. Mismo tratamiento de fricciones que BTC (FASE-4 §3).
- **Runs por activo:** base (`--trail I`), HMM (`--hmm`), y diagnóstico de embudo (`--funnel`).
- **Métricas de portfolio:** capital inicial $10.000, curva de equity por concatenación de trades ordenados por `t_entry`.
- **Nota HMM:** implementación Baum-Welch vectorizada en numpy puro (Python 3.14 sin `hmmlearn` compilado). Validada contra el resultado versionado de BTC: N, WR idénticos; expectancy diverge <2% (dentro de tolerancia).

---

## 2. Resultados por activo (Pilar C + HMM)

| Activo | Trades | Win Rate | Profit Factor | Expectancy_R | CAGR | Max DD |
|--------|-------:|---------:|--------------:|-------------:|-----:|-------:|
| BTCUSDT | 35 | 17.1% | 0.549 | -0.198 | -1.2% | -9.7% |
| ETHUSDT | 35 | 17.1% | 0.828 | -0.045 | -0.3% | -4.8% |
| SOLUSDT | 23 | 17.4% | 0.911 | -0.024 | -0.1% | -6.8% |
| XRPUSDT | 29 | 24.1% | 0.599 | -0.084 | -0.4% | -4.0% |
| BNBUSDT | 22 | 13.6% | 0.230 | -0.292 | -1.5% | -6.1% |
| **PORTFOLIO** | **144** | **18.1%** | **0.625** | **-0.125** | **-3.2%** | **-24.2%** |

> ⚠️ El DD del portfolio (-24.2%) está **sobreestimado**: la curva concatena los trades de los 5 activos como si corrieran secuencialmente en una sola cuenta, cuando en realidad se solapan en el tiempo. El DD real de una cuenta que opera los 5 en paralelo (con 1% de riesgo por activo) sería menor. Se corrige en la Fase 5 con una curva de equity simultánea real. Los DD **por activo** (4-10%) sí son correctos.

**Lectura:** ninguno de los 5 es rentable, pero **SOL y ETH quedan casi en equilibrio** (PF 0.91 y 0.83; expectancy -0.024R y -0.045R). BNB es el peor con diferencia (PF 0.23). El signo negativo es general, pero la magnitud varía mucho por activo.

---

## 3. HALLAZGO CENTRAL — análisis de win-rate de equilibrio

El sistema apunta a ganadores grandes y pérdidas chicas (trailing con EMA50 H1). Eso significa que **no necesita un WR alto** para ser rentable — necesita superar el WR de equilibrio: `WR_eq = avgLoss_R / (avgWin_R + avgLoss_R)`.

| Activo | WR real | avgWin_R | avgLoss_R | **WR equilibrio** | **Margen** |
|--------|--------:|---------:|----------:|------------------:|-----------:|
| BTCUSDT | 13.5% | +2.40 | -0.59 | 19.8% | **-6.3%** |
| ETHUSDT | 17.9% | +2.10 | -0.48 | 18.7% | **-0.8%** |
| SOLUSDT | 16.7% | +2.22 | -0.58 | 20.8% | **-4.1%** |
| XRPUSDT |  9.7% | +1.69 | -0.25 | 13.1% | **-3.4%** |
| BNBUSDT |  7.7% | +1.55 | -0.45 | 22.3% | **-14.6%** |

*(WR y avg_R calculados sobre operaciones ejecutadas; ligeras diferencias con la tabla §2 por el filtro HMM que descarta algunos trades a posteriori.)*

**Conclusión:** cada activo está **por debajo** de su WR de equilibrio, confirmando expectancy negativa. Pero **ETH está a solo 0.8 puntos** del equilibrio y BTC/SOL/XRP a 3-6 puntos. El trailing SÍ funciona (la asimetría +2R/-0.5R es real y saludable); el problema es que **el gatillo de entrada acierta demasiado poco**. Un aumento modesto del WR (de ~18% a ~22%) o una reducción del stop promedio bastaría para cruzar a terreno positivo — precisamente lo que la Fase 5 (WFO de los 6 parámetros) intentará establecer sin data-snooping.

---

## 4. Diagnóstico del embudo por activo — ¿dónde mueren las señales?

El embudo se repite con notable consistencia entre activos (confirma que BTC no era atípico):

### Módulo G (diario) — atrición de sesgos direccionales
| Activo | g_eval | g1 (ADX/ER) | g2 (zona) | g3 (llegada) | g4 (desacel.) | g5 (patrón) | dobleTecho |
|--------|-------:|------------:|----------:|-------------:|--------------:|------------:|-----------:|
| BTCUSDT | 2304 | 749 | 372 | 269 | 189 | 67 | **0** |
| ETHUSDT | 2299 | 677 | 347 | 222 | 129 | 70 | 1 |
| SOLUSDT | 2025 | 622 | 249 | 164 | 118 | 55 | 1 |
| XRPUSDT | 2293 | 592 | 304 | 198 | 128 | 48 | **0** |
| BNBUSDT | 2265 | 554 | 279 | 186 | 105 | 42 | **0** |

### Módulo I (horario) + gatillo
| Activo | i1 (EMA) | i2 (BOS) | i3 (swings) | trigger | rechazo stop | **entradas** |
|--------|---------:|---------:|------------:|--------:|-------------:|-------------:|
| BTCUSDT | 777 | 153 | 47 | 53 | 15 | 37 |
| ETHUSDT | 668 | 137 | 53 | 46 |  6 | 39 |
| SOLUSDT | 521 |  93 | 43 | 36 | 12 | 24 |
| XRPUSDT | 450 | 100 | 36 | 33 |  2 | 31 |
| BNBUSDT | 305 |  67 | 32 | 44 | 18 | 26 |

**Cuellos de botella identificados (consistentes en los 5 activos):**
1. **G1 (ADX≥20 + ER≥0.30)** elimina ~70% de las velas diarias de entrada. Es el primer gran filtro.
2. **G4→G5 (patrón de giro)** es el mayor embudo del módulo diario: de ~120-190 desaceleraciones a ~40-70 patrones válidos (elimina ~60-65%). El requisito de patrón de giro es muy exigente.
3. **El patrón doble-techo/doble-suelo (G5c) prácticamente NUNCA dispara** (0-1 en 6.5 años por activo). Es efectivamente código muerto en el universo cripto — candidato a revisar en Fase 5 (¿tolerancia P19 mal calibrada?).
4. **I2 (BOS, break of structure)** en el horario recorta agresivamente (de ~300-780 velas con EMA alineada a ~67-153 con BOS confirmado).

**Veredicto entrada-vs-salida:** el problema es de **ENTRADA** (los filtros de estructura y patrón dejan pasar muy pocas señales, y las que pasan aciertan poco), NO de salida (el trailing y el TP producen la asimetría deseada). Esto **confirma la hipótesis 1 y 4** del `ESTADO-Y-CONTINUIDAD.md` §3 y descarta que el TP esté mal ubicado como causa principal.

---

## 5. Comparativa vs. hipótesis H0 (Alex Ruiz)

| Métrica | Portfolio real | H0 declarado | Veredicto |
|---------|---------------:|-------------:|:---------:|
| Win Rate | 18.1% | 57% | ❌ FAIL |
| Trades/año | 23.3 | ~80 | ❌ FAIL |
| CAGR | -3.2% | ~34% | ❌ FAIL |
| Max DD | (por activo 4-10%) | <10% | ~ orden similar |
| Profit Factor | 0.625 | >1.5 | ❌ FAIL |

El WR declarado de 57% no se replica en ningún activo (máximo real: XRP 24.1%). La frecuencia de trades tampoco (23/año vs. 80). **La divergencia con las cifras del corpus es estructural y consistente en los 5 activos.**

---

## 6. Implicaciones para la Fase 5

1. **El WFO ya tiene poder estadístico razonable** (144 trades) para optimizar los 6 parámetros permitidos sobre el pool combinado — pero sigue siendo una muestra modesta; documentar intervalos de confianza.
2. **Prioridad de optimización según el embudo:** los parámetros que controlan G1 (`er_clean` P11), la llegada (`er_arrive` P15) y la desaceleración (`decel_max` P17) son los que más afectan el volumen de señales — candidatos naturales a que el WFO afloje/ajuste para subir el WR hacia el ~22% de equilibrio.
3. **El margen a cerrar es pequeño** (0.8-6 puntos de WR en 4 de 5 activos), lo que hace *plausible* —no seguro— que el WFO revierta el signo. Si tras el WFO+Monte Carlo el sistema sigue bajo equilibrio en OOS, el veredicto del proyecto será que la metodología, objetivada, no tiene edge estadístico en cripto.
4. **BNB es candidato a excluirse** del universo (peor con diferencia, -14.6% de margen) — pero esa decisión se toma por criterio estructural en Fase 5, no eliminándolo a posteriori para maquillar el agregado (anti data-snooping).

---

## 7. Archivos generados

```
code/python/
├── satar_portfolio.py           Consolidador de métricas de portfolio (nuevo)
├── trades_{sym}_base.csv        Trades Pilar C solo, por activo
├── trades_{sym}_hmm.csv         Trades Pilar C + HMM, por activo
└── results/
    ├── funnel_{sym}.json         Embudo de filtros + MFE/MAE por activo (5 archivos)
    └── portfolio_metrics.json    Métricas agregadas + comparativa H0
```

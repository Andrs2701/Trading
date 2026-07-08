# Diagnóstico del Embudo de Filtros — SATAR-1 (BTCUSDT)

Este documento detalla los resultados obtenidos al instrumentar y ejecutar el análisis del embudo de filtros sobre el dataset histórico completo de 6.5 años de BTCUSDT (velas M5).

## Tabla del Embudo de Filtros

A continuación se muestra el número de velas que superaron cada etapa del proceso de filtrado:

| Etapa / Filtro | Descripción | Velas / Eventos | % de Conversión |
| :--- | :--- | :--- | :--- |
| **MÓDULO G (Diario)** | **Filtros de Bias** | | |
| `g_eval` | Velas G Evaluadas | 2304 | 100.0% |
| `g1_pass` | Filtro de Eficiencia (ER) y ADX | 749 | 32.5% de eval |
| `g2_touch` | Toque de Zona Extrema Reciente | 372 | 49.7% de G1 |
| `g3_arrive` | Llegada Acelerada (ER o RSI) | 269 | 72.3% de G2 |
| `g4_decel` | Desaceleración Máxima | 189 | 70.3% de G3 |
| `g5_pattern` | Patrón de Giro (Envolvente/Pinbar/Doble techo) | 67 | 35.4% de G4 |
| - *engulfing* | Envolvente | 31 | 46.3% de G5 |
| - *pinbar* | Pinbar | 36 | 53.7% de G5 |
| - *double_top* | Doble Techo / Doble Suelo | 0 | 0.0% de G5 |
| `g6_valid` | Confirmación (No cierre fuera de zona) | 65 | 97.0% de G5 |
| **MÓDULO I (H1)** | **Estructura** | | |
| `i1_ema` | Tendencia alineada con la EMA H1 | 777 | 100.0% |
| `i2_bos` | Ruptura de Estructura (BOS) | 153 | 19.7% de I1 |
| `i3_swings` | Swings de Estructura Válidos | 47 | 30.7% de BOS |
| `i4_fib_reach` | Toque de Zona Fibonacci (0.382) * | 340 | 723.4% de swings |
| `i5_antichase` | Respeto de Anti-chase (EMA/ATR) | 118 | 34.7% de Fib |
| `i6_expired` | Expiración Temporal (armed_window) | 1 | - |
| `i7_invalidated`| Invalidación por cruce del 1.0 Fib | 4 | - |
| **GATILLO (M5)** | **Sanidad y Entrada** | | |
| `trigger_fired` | Gatillo EMA M5 | 53 | 100.0% |
| `reject_stop_dist`| Rechazo por Stop ATR fuera de límites | 15 | 28.3% de trig |
| `reject_tp_pool` | Rechazo por falta de Pivotes para TP | 0 | 0.0% de trig |
| `reject_rr_min` | Rechazo por R:R Mínimo (<0.5) | 1 | 1.9% de trig |
| `reject_killswitch`| Rechazo por límite de Drawdown | 0 | 0.0% de trig |
| **entered** | **Trades Abiertos** | **37** | **69.8% de trig** |

*\* Nota: En `i4_fib_reach` el conteo excede el número de swings porque una vez que se activa el estado de estructura, la comprobación se realiza vela a vela sobre la temporalidad H1, acumulando múltiples toques antes de salir del estado.*

---

## Análisis de Filtros Dominantes

El embudo revela tres cuellos de botella principales que limitan drásticamente el número de operaciones:

1. **La Estructura Horaria (BOS y Swings - Módulo I):**
   El filtro de Ruptura de Estructura (`i2_bos`) reduce las señales candidatas al **19.7%**, y la validación de swings de estructura decrecientes/crecientes (`i3_swings`) la reduce aún más al **30.7%**. Esto significa que la gran mayoría de las tendencias no logran formalizar una estructura de swings y ruptura lo suficientemente limpia según el modelo.
2. **El Filtro de Patrones de Giro Diarios (`g5_pattern`):**
   De las velas diarias que alcanzan niveles de desaceleración óptimos, solo el **35.4%** presenta una vela con patrón de giro válido. Adicionalmente, el patrón de **Doble Techo/Suelo registró 0 eventos en 6.5 años**, lo cual indica que la regla matemática que lo detecta en el código es extremadamente estricta o inaplicable a nivel diario con las tolerancias especificadas.
3. **El Filtro Anti-chase (`i5_antichase`):**
   De las velas H1 que entran al retroceso Fibonacci, solo el **34.7%** cumple con la distancia mínima a la EMA o ATR, descartando el resto por considerarse una persecución tardía del precio.
4. **Distancia del Stop Loss (`reject_stop_dist`):**
   Casi un **28.3%** de los disparos del gatillo en M5 son descartados porque la distancia al stop estructural calculada excede el límite del parámetro de control `stop_max_atr` (3.0 ATR) o no alcanza el mínimo `stop_min_atr` (0.15 ATR).

---

## Veredicto Entrada vs. Salida

### 1. El Problema de la Entrada
El volumen de operaciones es extraordinariamente bajo (**37 trades en 6.5 años**, equivalente a ~5.7 trades/año) debido a la **estricta concatenación de filtros multi-temporalidad**. El sistema requiere que ocurra un patrón diario muy particular, seguido de una estructura H1 perfectamente definida, y finalmente un gatillo de entrada en M5 con parámetros de stop exactos. La probabilidad conjunta de este evento es ínfima, lo que quita poder estadístico para cualquier análisis de robustez.

### 2. El Problema de la Salida
A pesar de la estricta selección, el rendimiento es deficiente:
* **Win Rate real de 16.2%** (6 trades ganadores vs. 31 perdedores).
* **Distribución de motivos de salida:**
  * **Stop:** 32 trades (86.5%) | Promedio R: **-0.59 R** | Duración promedio: 51.9 velas M5.
  * **Take Profit:** 5 trades (13.5%) | Promedio R: **+2.40 R** | Duración promedio: 224.2 velas M5.
* **MAE y MFE Promedio:**
  * El MFE promedio es **0.71 R** (con un MFE máximo alcanzado de 5.73 R).
  * El MAE promedio es **0.56 R**.

**Veredicto:** El Take Profit basado en el extremo estructural previo (`tp_lookback = 100`) es demasiado ambicioso para la tasa de acierto del sistema. Muchos trades llegan a estar en terreno positivo (MFE promedio de 0.71R) pero terminan retrocediendo y tocando el Stop Loss (que gracias al trailing por EMA H1 se reduce a un promedio de -0.59R).

Para lograr rentabilidad con un Win Rate del 16%, el R:R promedio del sistema necesitaría ser superior a 5.2R. Actualmente es de 2.4R, por lo que el expectancy es netamente negativo (-0.187R).

---

## Hipótesis para la Fase 5 (WFO)

Para la optimización formal de parámetros (WFO) en la Fase D, priorizaremos los siguientes parámetros que afectan de manera directa los filtros dominantes identificados:
1. **P09 (`zone_w_atr`):** Aumentar el ancho de las zonas extremas diarias podría incrementar de manera sustancial la cantidad de toques (`g2_touch`) y patrones (`g5_pattern`).
2. **P21 (`chase_atr`):** Relajar el filtro anti-chase para permitir entradas cuando el precio esté ligeramente más alejado de la EMA H1.
3. **P22 (`armed_window`):** Ampliar la ventana de espera del estado ARMED en H1 para dar más tiempo a que ocurra el gatillo en M5.
4. **P25 (`stop_max_atr`):** Aumentar el límite máximo de stop para evitar rechazar entradas válidas con alta volatilidad.

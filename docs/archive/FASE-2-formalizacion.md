# SATAR-1 — Fase 2: Formalización Matemática

**Fecha:** 2026-07-07 · **Estado:** entregado, pendiente aprobación
**Regla de oro:** toda condición se evalúa sobre VELAS CERRADAS de su temporalidad (sin repintado). La única acción intravela es la ejecución de órdenes stop/TP ya colocadas. Referencias `R-xNN` → Fase 1; `P##` → tabla de parámetros (§10).

---

## 0. Modelo de datos y notación

- Series OHLCV por temporalidad: `TF_G` (grande), `TF_I` (intermedia), `TF_P` (pequeña). Day trading: D1/H1/M5 (tríada por estilo, R-C10).
- `O_t, H_t, L_t, C_t, V_t`: valores de la vela `t` (índice creciente; `t` = última cerrada).
- Dirección `d ∈ {+1 (long), −1 (short)}`. Todas las fórmulas se escriben para short (`d=−1`); la versión long se obtiene reflejando (max↔min, >↔<, H↔L).
- Sincronización: una vela `TF_I` solo se procesa cuando su timestamp de cierre ≤ ahora; en backtest, los TF se alinean por timestamp de cierre (nunca usar la vela D1 en curso).

## 1. Indicadores (definiciones exactas)

```
EMA_n(t)   = α·C_t + (1−α)·EMA_n(t−1),  α = 2/(n+1), semilla = SMA_n     # P01 n=50, exponencial
TR_t       = max(H_t−L_t, |H_t−C_{t−1}|, |L_t−C_{t−1}|)
ATR_n(t)   = Wilder: ATR_t = (ATR_{t−1}·(n−1) + TR_t)/n                  # P02 n=14
RSI_n      = Wilder estándar                                             # P03 n=14
ADX_n      = Wilder estándar (DI+, DI−, DX suavizados)                   # P04 n=14
ER_n(t)    = |C_t − C_{t−n}| / Σ_{i=t−n+1..t} |C_i − C_{i−1}|            # P05 n=20 (0 si denom=0)
Body_t     = |C_t − O_t|
DecelRatio(t) = mean(Body_{t−2}, Body_{t−1}, Body_t) / ATR_10(t)          # R-C21
```

## 2. Estructura: swings, extremos, impulso

### 2.1 Swings (fractales)
```
SwingHigh(t): H_t > H_{t±i} ∀ i ∈ 1..k        # confirmado k velas después
SwingLow(t):  L_t < L_{t±i} ∀ i ∈ 1..k        # P06 k=2
```
`SH[]`, `SL[]`: listas cronológicas de swings confirmados por TF.

### 2.2 Zonas extremas en TF_G (R-C19)
```
Pivotes:    swings de TF_G con k=P07(=3) en lookback P08(=250) velas
Clustering: pivotes cuya distancia ≤ P09(=0.5)·ATR14_G se agrupan; centro = mediana
Zona Z:     [centro − P09·ATR14_G , centro + P09·ATR14_G]
Válida si:  nº de toques históricos ≥ P10(=2)   (toque = H o L dentro de Z)
EnExtremo_short(t): H_t ∈ Z_resistencia  (long: L_t ∈ Z_soporte)
```

### 2.3 Impulso en TF_I (para Fibonacci)
```
Impulso bajista = tramo desde el último SH relevante (origen O_imp) hasta el
mínimo posterior más bajo (fin F_imp), confirmado por el BOS (§4.2).
Re-anclaje (R-C26): si tras el BOS aparece L < F_imp antes de entrada, F_imp ← nuevo mínimo
y los niveles Fib se recalculan.
Fib(r) = F_imp + r·(O_imp − F_imp)      # r ∈ {0.382, 0.5, 0.618, 0.75, 1.0}
```

## 3. Módulo TF_G — sesgo direccional (BIAS)

Evaluado al cierre de cada vela TF_G. Sesgo short si TODAS:

```
G1 Limpieza (R-C08/D-4):        ER_20_G ≥ P11(=0.30)  AND  ADX_14_G ≥ P12(=20)
G2 Extremo (R-C19):             EnExtremo_short — vela actual o alguna de las últimas P13(=3) velas tocó Z_res
G3 Llegada acelerada (R-C20):   ER del tramo de aproximación (últimas P14(=5) velas hasta el toque) ≥ P15(=0.35)
                                 OR RSI_14_G en el toque ≥ P16(=70)          # variante AMBIG-2, default OR
G4 Desaceleración (R-C21/D-2):  DecelRatio ≤ P17(=0.6)
G5 Giro (R-C22): al menos uno:
     (a) Envolvente bajista:  C_t < O_t AND O_t ≥ C_{t−1} AND C_t < O_{t−1} AND Body_t > Body_{t−1}
     (b) High-test/pinbar:    (H_t − max(O_t,C_t)) ≥ P18(=2.0)·Body_t AND C_t ≤ (H_t+L_t)/2 + 0.1·(H_t−L_t)
     (c) Doble techo:         dos SH consecutivos en Z_res con |SH1−SH2| ≤ P19(=0.25)·ATR14_G
                              y cierre bajo el mínimo intermedio (neckline)
G6 No invalidado (R-C23):       NO existe vela con C > sup(Z_res) confirmada por la siguiente vela
```

```
BIAS = short; expira tras P20(=3) velas TF_G sin posición abierta (R-C24)   # AMBIG-3
Si G6 falla con BIAS activo → BIAS = null (invalidación inmediata)
```

## 4. Módulo TF_I — estructura y zona de entrada

Evaluado al cierre de cada vela TF_I, solo con `BIAS=short` activo.

### 4.1 Prerrequisito EMA
```
I1: C_t < EMA50_I(t)            # ruptura de la media intermedia (R-C25)
```
### 4.2 Cambio de estructura (BOS)
```
I2: C_t < último SL_I confirmado (cierre, no sombra)
I3: el último SH_I posterior al inicio del impulso es < SH_I previo (máximos decrecientes)
BOS confirmado ⇒ anclar Fibonacci (§2.3)
```
### 4.3 Zona de entrada y anti-chase (R-C27/28, D-5)
```
ZonaEntrada = [Fib(0.382), Fib(0.618)]                        # en precio
I4 Pullback:   H_t ≥ Fib(0.382)                               # el retroceso alcanzó la zona
I5 Confluencia EMA (anti-chase): dist = |H_t − EMA50_I(t)| ;  dist ≤ P21(=0.5)·ATR14_I
   (o el pullback tocó la EMA50_I: H_t ≥ EMA50_I)
I6 Ventana: el gatillo TF_P debe ocurrir en ≤ P22(=12) velas TF_I tras cumplirse I4∧I5;
   si expira → estado ARMED se cancela; puede rearmarse con nuevo impulso/BOS
I7 Invalidación (R-C29): C_t > Fib(1.0) ⇒ setup cancelado y BIAS reevaluado
Profundidad: depth = (max H alcanzado en pullback − F_imp)/(O_imp − F_imp)   # para el SL (§6)
```

## 5. Módulo TF_P — gatillo (R-C30/32/33)

Evaluado al cierre de cada vela TF_P, solo en estado `ARMED` (I4∧I5 cumplidos, I6 no expirado):
```
P1: C_t < EMA50_P(t)                       # cierre, no sombra
P2: C_{t−1} ≥ EMA50_P(t−1)                 # es un cruce, no continuación (anti-señal repetida)
⇒ ORDEN: venta a mercado en la apertura de la vela TF_P siguiente
```

## 6. Stop Loss inicial (R-C35 / D-1)

```
buffer = P23(=0.1)·ATR14_I
si depth ≤ 0.618:   SL0 = Fib(0.75)  + buffer
si depth  > 0.618:  SL0 = max(Fib(1.0), último SH_I) + buffer
Sanidad: si |SL0 − entry| < P24(=0.15)·ATR14_I ⇒ descartar trade (stop degenerado)
         si |SL0 − entry| > P25(=3.0)·ATR14_I ⇒ descartar trade (riesgo desproporcionado)
```

## 7. Take Profit (R-C36/37)

```
TP = último SL_I estructural previo al impulso (mínimos anteriores relevantes)
   = min( SL_I[-1], SL_I[-2] ) restringido a lookback P26(=100) velas TF_I
Fijo durante todo el trade. RR_teórico = (entry−TP)/(SL0−entry); registrar, no filtrar
(rango esperado 0.8–2.0, R-C38). Si RR_teórico < P27(=0.5) ⇒ descartar trade.
```

## 8. Gestión: trailing y salidas (R-C39–43 / D-6)

Al CIERRE de cada vela TF_I con posición abierta:
```
stop_candidato = EMA50_I(t) + P23·ATR14_I(t)          # short
stop_nuevo     = min(stop_actual, stop_candidato)      # solo a favor, nunca se aleja
```
- El stop es orden real: se ejecuta intravela si `H` lo toca.
- TP orden límite fija. Salida = primero que ocurra: TP, stop, o invalidación de sesgo
  (nueva vela TF_G cierra > sup(Z_res) con confirmación ⇒ cierre a mercado).
- "Riesgo libre" (R-C42): emergente del trailing; NO hay cierre parcial (interpretación AMBIG-1).

## 9. Riesgo y position sizing (R-C44 + límites R-C09)

```
riesgo_trade   = P28(=1%) de equity  (swing: P29(=3%))
qty            = (riesgo_trade · equity) / |entry − SL0|      (ajustar a lote/step del broker)
mult_HMM       ∈ {1.0, 0.5, 0.0} según régimen (§11)          # riesgo efectivo = riesgo·mult
Límites (kill-switch, [F] propuestos): pérdida diaria ≥ P30(=2%) ⇒ no nuevas entradas hasta día sig.
  semanal ≥ P31(=4%) ⇒ pausa 1 semana · mensual ≥ P32(=6%) ⇒ pausa hasta mes sig. + revisión manual
Máx posiciones simultáneas: P33(=3), máx 1 por activo; exposición correlacionada (misma divisa base
o cripto) cuenta doble contra P33.
```

## 10. Tabla maestra de parámetros

| # | Parámetro | Default | Rango Fase 5 | Origen |
|---|-----------|---------|--------------|--------|
| P01 | EMA período | 50 exp | fijo (identidad de la estrategia) | [E] |
| P02 | ATR período | 14 | fijo | convención |
| P05 | ER período | 20 | 10–30 | D-4 |
| P06 | k fractal TF_I | 2 | 2–3 | [I] |
| P07 | k pivote TF_G | 3 | 2–5 | [I] |
| P08 | lookback zonas | 250 | 150–500 | [F] |
| P09 | ancho zona (×ATR) | 0.5 | 0.25–1.0 | [F] |
| P10 | toques mínimos | 2 | 2–3 | [E] "varias veces" |
| P11 | ER limpieza | 0.30 | 0.20–0.40 | D-4 |
| P12 | ADX limpieza | 20 | 15–25 | D-4 |
| P13 | ventana toque extremo | 3 | 2–5 | [I] |
| P14 | velas tramo llegada | 5 | 3–8 | [I] |
| P15 | ER llegada | 0.35 | 0.25–0.50 | [F] |
| P16 | RSI extremo | 70/30 | 65–80 | [F] |
| P17 | umbral desaceleración | 0.6 | 0.4–0.8 | D-2 |
| P18 | ratio mecha pinbar | 2.0 | 1.5–3.0 | convención |
| P19 | tolerancia doble techo | 0.25 | 0.1–0.5 | [I] |
| P20 | caducidad sesgo (velas G) | 3 | 2–4 | AMBIG-3 |
| P21 | anti-chase (×ATR_I) | 0.5 | 0.25–1.0 | D-5 |
| P22 | ventana gatillo (velas I) | 12 | 6–24 | D-5 |
| P23 | buffer stop (×ATR_I) | 0.1 | 0.05–0.3 | D-1/D-6 |
| P24/25 | stop mín/máx (×ATR_I) | 0.15 / 3.0 | — | sanidad |
| P26 | lookback TP | 100 | 50–200 | [I] |
| P27 | RR mínimo | 0.5 | 0.3–0.8 | [E] acepta 0.8 |
| P28/29 | riesgo day / swing | 1% / 3% | fijo | [E] |
| P30-32 | límites d/s/m | 2/4/6% | Fase 6 | [F] |
| P33 | posiciones máx | 3 | 1–5 | [F] |

**Compromiso anti-sobreajuste:** solo P09, P11, P15, P17, P21, P22 entran a optimización WFO; el resto se somete únicamente a análisis de sensibilidad (perturbación ±20%).

## 11. Pilar B — especificación HMM

```
Datos: TF_G del activo. Features en t (z-score con media/σ de la ventana de entrenamiento):
  f1 = std(retornos log, 20)          # volatilidad
  f2 = Σ retornos log, 20             # retorno acumulado
  f3 = C_t/C_{t−10} − 1               # momentum ROC(10)
Modelo: Gaussian HMM, covarianza full. K ∈ {2..6} elegido por BIC en la ventana de entrenamiento.
Entrenamiento walk-forward (R-B07): ventana rodante P34(=750) velas; re-fit cada P35(=21) velas;
  el estado de t usa solo información ≤ t (filtered probabilities, NO smoothed).
Etiquetado de estados (automático, por momentos del estado):
  crisis      : menor media de f2 y mayor f1
  tendencia   : |f2| alto y f1 medio-bajo ·  rango: |f2| bajo · resto: intermedio/recuperación
Política de exposición (R-B06): mult = 1.0 (tendencia, tendencia suave) · 0.5 (rango, recuperación)
  · 0.0 (crisis). Histéresis: cambio de mult solo si P(régimen) > 0.6 en 2 velas consecutivas.
```

## 12. Pilar A — placeholder Donchian (solo infraestructura)

```
M15 cripto (BTCUSDT perp). Upper = max(H, 20), Lower = min(L, 20), Mid opuesto n=10.
Long: C cruza sobre Upper[t−1] · Short: C cruza bajo Lower[t−1]
Salida: canal opuesto(10) o stop 2×ATR(14). Riesgo 0.5% por trade. Sin HMM.
Propósito único: validar órdenes/reconexión/contabilidad en subcuenta Bybit (R-A03).
```

## 13. Máquina de estados del trade (por activo)

```
IDLE ──(G1..G6 al cierre TF_G)──▶ BIAS[d, expira P20 velas G]
BIAS ──(I1∧I2∧I3 al cierre TF_I)──▶ STRUCTURE[Fib anclado]
STRUCTURE ──(I4∧I5)──▶ ARMED[expira P22 velas I]     ──(I7 ó expiración)──▶ IDLE/BIAS
ARMED ──(P1∧P2 al cierre TF_P)──▶ ENTRY(open sig. vela) ▶ IN_POSITION[SL0 §6, TP §7]
IN_POSITION ──(cierre TF_I)──▶ trailing §8 ──(TP | stop | invalidación G)──▶ CLOSED → IDLE
Eventos globales: kill-switch (§9) bloquea transiciones a ENTRY; HMM (§11) escala qty en ENTRY.
```

## 14. Criterios de aceptación de la implementación (Fase 4/7)

1. Reproducibilidad: mismo dataset ⇒ mismas operaciones en Python y Pine (tolerancia: diferencias solo por redondeo de qty).
2. Cero look-ahead: prueba con datos truncados — la señal en t no cambia al añadir t+1..t+n.
3. Cero repintado: señales calculadas solo con velas cerradas (k fractal introduce retardo de confirmación de 2-3 velas: es intencional y se acepta).

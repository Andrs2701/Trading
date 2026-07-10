# SATAR-1 — Fase 1: Ingeniería Inversa

**Fecha:** 2026-07-07 · **Estado:** entregado, pendiente aprobación
**Fuentes:** 5 transcripciones en `/corpus` (citas abreviadas; texto íntegro en los .txt)

## 0. Convenciones

Cada regla tiene un ID (`R-C##` pilar C, `R-B##` pilar B, `R-A##` pilar A) y una etiqueta:

- **[E] Explícita** — declarada textualmente en un video (se incluye cita).
- **[I] Inferida** — reconstruida a partir de ejemplos o del contexto; requiere ratificación en Fase 3.
- **[F] Faltante** — necesaria para programar y no definida por el autor; se propone valor por defecto sujeto a Fase 3/5.

Decisiones ya adoptadas por el usuario (2026-07-07): **D-1** SL dinámico por profundidad de retroceso; **D-2** proxies de desaceleración (Body/ATR(10) < 0.6 + patrón de reversión); **D-3** fricciones estrictas en backtest; **D-4** limpieza por ER(20)≥0.30 + ADX(14)≥20; **D-5** anti-chase 0.5×ATR(14,H1) + caducidad 12 velas H1; **D-6** trailing con EMA50 de temporalidad intermedia al cierre de vela, buffer 0.1×ATR.

---

## 1. PILAR C — Estrategia personal (impulso–pullback–continuación multi-timeframe)

### 1.1 Filosofía y principios rectores

| ID | Regla | Etiqueta | Fuente / cita |
|----|-------|----------|---------------|
| R-C01 | Tres pilares personales: sencillez, moderación (objetivo primario = perder poco), repetición | [E] | l90: "mi objetivo no era ganar mucho, sino que era perder poco" |
| R-C02 | Principio operativo: primero proteger capital; desde la no-pérdida se busca la ganancia | [E] | ege74: "no perder significa que orientas... en proteger tu capital" |
| R-C03 | Estrategia = patrón + conjunto de normas + largo plazo (≥1000 trades para significancia) | [E] | dXz: "10 trades no es la realidad; 1000 trades empieza a ser la realidad" |
| R-C04 | Calidad sobre cantidad: solo setups "limpios"; descartar los dudosos aunque funcionen | [E] | ege74: comparación AUDCAD vs USDCAD |

### 1.2 Reglas de no-trading (filtros de sesión y estado)

| ID | Regla | Etiqueta | Nota de formalización |
|----|-------|----------|----------------------|
| R-C05 | No operar si no se siguió la rutina habitual (noche anterior + día actual) | [E] ege74 | No programable en el bot; pasa al protocolo humano (Fase 9/10) |
| R-C06 | No operar intranquilo/ocupado/enfadado | [E] ege74 | Ídem — checklist pre-sesión |
| R-C07 | No operar si el trade no se puede justificar en 1-2 frases | [E] ege74 | Se sustituye por: solo señales que cumplan TODAS las condiciones formales |
| R-C08 | No operar si la temporalidad grande "no está limpia" | [E] ege74 | **Proxy D-4**: ER(20) ≥ 0.30 y ADX(14) ≥ 20 en la temporalidad grande |
| R-C09 | No operar si se alcanzó el límite de pérdida diaria/semanal/mensual | [E] ege74 | **[F] valores no declarados.** Propuesta: día −2% (2 pérdidas plenas), semana −4%, mes −6%. A calibrar en Fase 6 |

### 1.3 Estilos y tríada de temporalidades

| ID | Regla | Etiqueta |
|----|-------|----------|
| R-C10 | Tres estilos con tríadas fijas — Swing: W1/D1/H1 · Day: D1/H1/M5 · Scalp: H1/M5/M1. La lógica es idéntica; solo cambia la tríada | [E] ege74 (tabla de estilos) |
| R-C11 | Tareas por temporalidad — GRANDE: dirección de las próximas 2-3 velas · INTERMEDIA: patrón (cambio de estructura + pullback) · PEQUEÑA: ejecución | [E] ege74/dXz |
| R-C12 | Estilo de referencia del autor: day trading (D1/H1/M5) | [E] l90/ege74 |
| R-C13 | Alineación obligatoria: las tres temporalidades deben apuntar a la misma dirección en el momento de la entrada | [E] ege74: "alineo desde la temporalidad grande hasta la pequeña" |

### 1.4 Activos y universo

| ID | Regla | Etiqueta |
|----|-------|----------|
| R-C14 | Multi-activo: divisas, índices, metales, criptomonedas y acciones US — "voy donde está la oportunidad" | [E] ege74 |
| R-C15 | Acciones: cribado top-down por sector/industria (ETF sectorial, ej. IBB) → analizar solo las 20-30 componentes cuando el sector muestra patrón | [E] ege74 |
| R-C16 | Universo de backtest (Fase 4): EURUSD, GBPUSD, USDJPY, AUDCAD, XAUUSD, US500, US100, BTCUSD, ETHUSD + cesta de ETFs sectoriales | [I] — construido para cubrir las clases que él menciona |

### 1.5 Horarios

| ID | Regla | Etiqueta |
|----|-------|----------|
| R-C17 | Sin sesión obligatoria: análisis matinal (~06:00-06:30 CET), colocación de alertas y gestión asíncrona; el trading se adapta a la rutina | [E] ege74 |
| R-C18 | Para el sistema automatizado: sin filtro horario de partida en cripto (24/7); en forex/índices evitar el cierre/rollover (22:00-23:00 UTC) y los primeros minutos de apertura de sesión con spread ensanchado | [F] propuesta propia; validar con datos en Fase 4-5 |

### 1.6 Temporalidad GRANDE — dirección de las próximas 2-3 velas

Setup direccional (ejemplo short; el long es simétrico):

| ID | Regla | Etiqueta | Formalización propuesta |
|----|-------|----------|------------------------|
| R-C19 | El precio debe estar en un EXTREMO del mercado (zona S/R horizontal testeada varias veces); la zona intermedia no interesa | [E] l90: "me interesa encontrarme el gráfico diario en un extremo... en los extremos es donde alberga más liquidez" | Pivotes: máximos/mínimos locales con ventana 20-50 velas D1; zona = precio ± 0.5×ATR(14,D1) del pivote; ≥2 toques históricos |
| R-C20 | Llegada al extremo ACELERADA (sobrecompra/sobreventa): el tramo de aproximación es direccional y con velas grandes | [E] l90 | ER del tramo de llegada ≥ 0.35 y/o RSI(14) > 70 (short) / < 30 (long) — variante a fijar en Fase 2 |
| R-C21 | DESACELERACIÓN en el extremo: velas cada vez más pequeñas, entrada de órdenes contrarias | [E] l90: "detecto desaceleración, detecto dudas..." | **D-2**: media de |cuerpo| de las últimas 3 velas / ATR(10) < 0.6 |
| R-C22 | GIRO confirmado por patrón de velas: envolvente, high-test/pinbar, cierre por encima/debajo de aperturas previas; doble techo/suelo suma | [E] l90 (vela de giro descrita), dXz (envolvente + doble suelo) | Catálogo formal de 3 patrones en Fase 2 |
| R-C23 | Si el precio ROMPE y CIERRA más allá del extremo y la vela siguiente confirma, el setup de reversión queda invalidado (posible continuación) | [E] ege74: "si rompe, cierra y confirma la ruptura, dejamos atrás la resistencia" |
| R-C24 | Salida direccional: se esperan 2-3 velas de la temporalidad grande en la dirección del giro; el sesgo caduca tras 3 velas sin desarrollo | [E] dirección / [I] caducidad — propuesta: sesgo válido 3 velas D1 |

### 1.7 Temporalidad INTERMEDIA — patrón y zona de entrada

| ID | Regla | Etiqueta | Formalización |
|----|-------|----------|---------------|
| R-C25 | Cambio de estructura (BOS): ruptura de los mínimos del último tramo + máximos decrecientes (short); además ruptura de la EMA50 exp H1 | [E] ege74/dXz | Swings por fractales (2 velas a cada lado); BOS = cierre H1 más allá del último swing |
| R-C26 | Fibonacci del impulso completo (del inicio al fin del tramo que rompió estructura); si el impulso se extiende, se re-ancla al nuevo extremo | [E] l90: "vamos a alargar esa estructura de Fibonacci" |
| R-C27 | Zona de entrada: retroceso a 0.382 / 0.50 / 0.618 con confluencia de EMA50 exp H1 y S/R previa | [E] ege74: "esperar a que llegue hasta 0,382, 0,5 o 0,618" + "media móvil de 50 y niveles de Fibonacci" |
| R-C28 | Anti-chase (media "en Cuenca"): pullback válido solo si toca la EMA50 H1 o queda a < 0.5×ATR(14,H1) de ella; gatillo de M5 debe ocurrir dentro de las 12 velas H1 posteriores al contacto | [E] concepto (dXz: "espérate a que el precio llegue y se acerque a la media móvil") / **[F→D-5]** cuantificación |
| R-C29 | Invalidación del setup: retroceso que supera el nivel 1.0 (extremo del impulso) anula el cambio de estructura | [I] — implícito en la lógica de máximos/mínimos decrecientes |

### 1.8 Temporalidad PEQUEÑA — gatillo de ejecución

| ID | Regla | Etiqueta |
|----|-------|----------|
| R-C30 | Gatillo objetivo (el que se automatiza): CIERRE de vela M5 más allá de la EMA50 exp M5 en la dirección del trade, estando el precio en la zona R-C27/28. "Hasta que no cierre, no entras" — la sombra no basta | [E] ege74 (ruptura EMA50 M5) + dXz (exigencia de cierre) |
| R-C31 | Gatillo alternativo discrecional: ruptura de diagonal (línea de tendencia del pullback). NO se automatiza; queda documentado | [E] ege74: "una es más arriesgada y la otra es más conservadora" |
| R-C32 | La ruptura de EMA50 M5 solo vale DESPUÉS de alcanzada la zona de confluencia H1 (rupturas en zona intermedia se ignoran) | [E] ege74: "aquí se rompe la media móvil después de que el precio llegue a ciertas zonas" |
| R-C33 | Orden: a mercado al cierre de la vela gatillo (no limit) | [I] — en los ejemplos ejecuta al confirmarse la ruptura |

### 1.9 Stop Loss (con resolución de la inconsistencia A)

| ID | Regla | Etiqueta |
|----|-------|----------|
| R-C34 | Evidencia bruta: l90 coloca SL "por debajo del nivel de 0,75"; ege74 dice "stop loss en 0,618"; excepción ege74: si el retroceso ya superó 0.618 (llegó a ~0.75), SL sobre el máximo/mínimo anterior | [E] ambas citas — contradictorias |
| R-C35 | **Regla adoptada (D-1), SL dinámico:** si el gatillo ocurre con retroceso H1 ≤ 0.618 → SL en el nivel 0.75 ± buffer; si el retroceso superó 0.618 → SL en el extremo estructural (1.0 / swing anterior) ± buffer. Buffer = 0.1×ATR(14,H1) | [F→decisión de Fase 2, aprobada por usuario] |

### 1.10 Take Profit

| ID | Regla | Etiqueta |
|----|-------|----------|
| R-C36 | TP en el extremo anterior de la estructura (mínimos previos en short / máximos previos en long); "mínimo en los máximos anteriores" | [E] ege74/dXz |
| R-C37 | El TP NO se mueve durante el trade | [E] ege74: "sin mover el take profit, voy acotando el precio" |
| R-C38 | R:R resultante variable 0.8–2.0 (promedio declarado 1.55); se acepta R:R < 1 por el WR esperado | [E] ege74/l90 |

### 1.11 Gestión de la posición

| ID | Regla | Etiqueta |
|----|-------|----------|
| R-C39 | Sin parciales, sin promediar, sin añadir posiciones | [E] ege74: "no a través de parciales... sino a través de medias móviles" |
| R-C40 | Trailing objetivo con EMA50 exp de la temporalidad de gestión: el stop sigue a la media ("más cerca, yo más cerca; más lejos, yo más lejos"), solo a favor | [E] ege74 |
| R-C41 | **Mecánica adoptada (D-6):** temporalidad de gestión = intermedia (H1 en day); stop reubicado al CIERRE de cada vela H1 en EMA50_H1 ± 0.1×ATR(14,H1); ejecución del stop intravela | [F→decisión aprobada] |
| R-C42 | "Quitar el riesgo": ante primer recorrido favorable, el trailing lleva el stop a reducir el riesgo al ~50% y luego a break-even → "riesgo libre". AMBIGÜEDAD: podría leerse como cierre parcial, pero R-C39 lo excluye; se interpreta como desplazamiento del stop | [E] texto / [I] interpretación — ratificar en Fase 3 |
| R-C43 | Salida final: lo primero que ocurra — TP, stop (trailing) o invalidación del sesgo D1 (R-C24) | [I] síntesis |

### 1.12 Riesgo y métricas declaradas (a validar, no aceptadas)

| ID | Regla | Etiqueta |
|----|-------|----------|
| R-C44 | Riesgo por operación: 1% (day/scalp); 3% en swing ("en swing arriesgo el triple") | [E] dXz (1%) + ege74 (triple) |
| R-C45 | Pérdida media efectiva −0.73% (< 1% arriesgado) gracias al trailing | [E] ege74 |
| R-C46 | Métricas declaradas: ~80 trades/año, WR 57% (56% en l90), ganancia media +1.30%, RR promedio 1.55, ~34% anual (41% compuesto), DD máx anual 4.33% | [E] — **hipótesis a falsar en Fase 4**, no supuestos |

### 1.13 Gestión emocional (protocolo humano, Fases 9-10)

R-C47 [E]: rutina fija, diario de trading en Excel (capital, WR, WR sin break-evens, DD), backtesting y journaling periódicos, no ser "esclavo del trading" (alertas en vez de pantalla), aceptar rachas (meses negativos existen: junio 2025 −1.67%).

---

## 2. PILAR B — Filtro de régimen HMM (meta-capa)

| ID | Regla | Etiqueta |
|----|-------|----------|
| R-B01 | Features de entrada: volatilidad, retornos acumulados y momentum | [E] Cdh: "ponemos volatilidad, retornos acumulados y momentum" — **[F]** ventanas exactas; propuesta: vol = std de retornos 20 velas, retorno acumulado 20 velas, momentum = ROC(10), sobre la temporalidad grande |
| R-B02 | Número de estados: automático (selección por criterio tipo BIC) o fijado; su demo en BTC diario arrojó 5: tendencia suave (~26%), tendencia (~25%), rango (~22%), recuperación (~15%), crisis (~11%) | [E] |
| R-B03 | La matriz de transición da probabilidades de permanencia/cambio (ej. tendencia suave → permanece 80%) | [E] |
| R-B04 | **Uso correcto (regla central):** parámetros de la estrategia FIJOS; el HMM decide QUÉ estrategia se activa, CUÁNDO y con CUÁNTO riesgo. No re-optimizar parámetros por régimen (estados poco frecuentes → parámetros no fiables) | [E] Cdh: "El verdadero valor del HMM está en la gestión del portfolio, no en el ajuste de las estrategias" |
| R-B05 | La salida es probabilística: modular por P(régimen), no por régimen puntual | [E] Cdh: "hay un 80% de probabilidades..." |
| R-B06 | Política de exposición propuesta: tendencia/tendencia suave → riesgo 100% (1%); rango/recuperación → 50%; crisis → 0% (sistema en pausa) — con histéresis: cambio de política solo si P(régimen) > 0.6 dos velas seguidas | [F] propuesta propia coherente con R-B04; calibrar en Fase 5-6 |
| R-B07 | Entrenamiento walk-forward: HMM re-entrenado con ventana rodante (ej. 3 años), nunca con datos futuros; re-fit mensual | [F] propuesta — imprescindible para evitar look-ahead |

## 3. PILAR A — Donchian 15m (banco de pruebas de infraestructura)

Rol ratificado por el usuario: **solo validación de la tubería Python↔Bybit** (subcuenta, API keys restringidas a trading, sin retiros), no fuente de edge.

| ID | Regla | Etiqueta |
|----|-------|----------|
| R-A01 | Canales de Donchian en M15, cripto futuros (BTC; extendido a ETH/SOL/DOGE), long y short, ≤2 indicadores | [E] K3x |
| R-A02 | Parámetros exactos del canal, SL y TP: **[F] — nunca se muestran en el video.** Placeholder estándar documentado: Donchian(20) breakout con salida por canal opuesto(10) y stop 2×ATR(14) | [F] |
| R-A03 | Advertencias del propio autor: backtest sin comisiones/spread/slippage; 9 trades no significativos; "lo más probable es que no se tenga éxito a largo plazo" | [E] K3x — el pilar A jamás pasa a producción sin cumplir Fase 4-5-9 |

## 4. Registro de ambigüedades abiertas → entrada de la Fase 3

1. R-C42: "quitar el 50% del riesgo" — ¿stop a media distancia o cierre parcial? (interpretado: stop; ratificar).
2. R-C20: definición única de "llegada acelerada" (ER del tramo vs RSI extremo vs ambas).
3. R-C24: caducidad exacta del sesgo direccional (2 vs 3 velas de la temporalidad grande).
4. R-C09: valores de límites de pérdida diaria/semanal/mensual (no declarados).
5. R-C18: filtros horarios por clase de activo.
6. WR 56% vs 57% y RR "1,6" vs 1,55 — se toman los del video más reciente y formal (ege74) como declaración canónica.
7. R-B01: ventanas de features del HMM.
8. Temporalidad de gestión del trailing en scalping (¿M5 o H1?) — propuesta: la intermedia de la tríada (M5).

## 5. Decisiones ya cerradas (no reabrir salvo evidencia en contra)

D-1 SL dinámico (R-C35) · D-2 desaceleración Body/ATR<0.6 + patrón (R-C21/22) · D-3 fricciones Bybit 0.02/0.055%, spread 0.01-0.05%, slippage en mercado (Fase 4) · D-4 limpieza ER(20)≥0.30 + ADX(14)≥20 (R-C08) · D-5 anti-chase 0.5×ATR + 12 velas (R-C28) · D-6 trailing EMA50 intermedia al cierre + buffer 0.1×ATR (R-C41) · Alcance A(infra)+B(meta-capa)+C(edge).

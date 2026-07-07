# SATAR-1 — Auditoría y Validación: Fase 0 (Adquisición del Corpus)

**Proyecto:** Sistema de Trading Automatizado — Metodología Alex Ruiz  
**Fecha de Auditoría:** 2026-07-07  
**Estado de la Fase 0:** **APROBADA CON OBSERVACIONES CRÍTICAS** (Se requiere incorporar esta auditoría y la matriz de trazabilidad para dar por cerrada la Fase 0 e iniciar la Fase 1).

---

## 1. Diagnóstico de Completitud y Brechas

El documento original `FASE-0-corpus.md` presentaba una excelente catalogación general y una identificación preliminar de inconsistencias. Sin embargo, **no era una entrega completa** bajo los términos definidos en la especificación original del proyecto:

> **Fase 0. Adquisición del corpus (nueva, necesaria):** ... matriz video→regla con cita textual como trazabilidad.

El documento carecía de dicha **matriz de trazabilidad**. Para subsanar esta brecha, esta auditoría extrae y consolida de forma exhaustiva las reglas lógicas, operativas y de gestión de riesgo a partir de los subtítulos e intercepciones directas del DOM del navegador, garantizando que la Fase 1 (Ingeniería Inversa) parta de una base documental matemática y textual sólida.

---

## 2. Matriz de Trazabilidad: Video $\rightarrow$ Regla (Citas Textuales)

A continuación se detalla la matriz que conecta cada pilar del sistema con sus reglas exactas y las citas textuales que las respaldan:

### Pilar C: Estrategia Personal de Alex Ruiz (Núcleo)
*Fuentes: Videos `l90QtxULIkE` (Estrategia Aburrida), `ege74_2NExk` (Estrategia 2026 - Video Núcleo), `dXzF9ohdewE` (Webinar Filtrado)*

| Código Regla | Categoría | Descripción Técnica | Cita Textual de Trazabilidad |
| :--- | :--- | :--- | :--- |
| **PC-REG-01** | **No-Trading (Rutina)** | No operar si se rompe la rutina diaria o el descanso nocturno. | *"No haré trading si no he seguido mi rutina habitual por los motivos que sean durante la noche anterior y durante el día actual."* (`ege74_2NExk.txt`) |
| **PC-REG-02** | **No-Trading (Estado Mental)** | No operar en estados emocionales alterados o de distracción. | *"No haré trading si estoy intranquilo, ocupado o enfadado por algún motivo."* (`ege74_2NExk.txt`) |
| **PC-REG-03** | **No-Trading (Claridad)** | No operar si el trade no se justifica con extrema sencillez. | *"No haré trading si no veo claro un trade y eso significa que no pueda justificarlo con una o dos frases."* (`ege74_2NExk.txt`) |
| **PC-REG-04** | **No-Trading (Limpieza)** | No operar si el gráfico de temporalidad mayor tiene ruido o no es claro. | *"No haré trading si el gráfico principal, la temporalidad más grande no está limpia."* (`ege74_2NExk.txt`) |
| **PC-REG-05** | **No-Trading (Límites P/L)** | Detener la operativa si se alcanza el drawdown máximo del periodo. | *"No haré trading si alcanzo el límite de pérdida diaria, semanal o mensual."* (`ege74_2NExk.txt`) |
| **PC-REG-06** | **Universo de Activos** | Operar de forma global donde se identifique la ventaja estadística. | *"voy donde está la oportunidad... mi escuela lo que yo he aprendido y lo que a mí me gusta es tener un control global del mercado... a veces acciones, a veces divisas, a veces criptomonedas, a veces índices"* (`ege74_2NExk.txt`) |
| **PC-REG-07** | **Fractalidad y Tríadas** | Clasificación operativa en 3 niveles de temporalidad según el estilo. | *"Swing trading: gráficos semanal, diario y horario... Day trading: diario, horario y 5 minutos... Scalping: horario, 5 minutos y 1 minuto... En cada estilo hay una temporalidad grande, una intermedia y una pequeña."* (`ege74_2NExk.txt`) |
| **PC-REG-08** | **Tareas de Temporalidad** | Distribución de funciones analíticas por gráfico (Grande/Intermedia/Pequeña). | *"En la temporalidad GRANDE lo que buscaremos será la dirección de las próximas dos o tres velas. En la temporalidad INTERMEDIA lo que buscaremos es la estrategia en sí, buscando el patrón... Y en la temporalidad PEQUEÑA lo único que harás será ejecutar."* (`ege74_2NExk.txt`) |
| **PC-REG-09** | **Filtro de Tendencia (EMA)** | Uso de la EMA de 50 periodos en los tres marcos temporales. | *"ES UNA MEDIA MÓVIL DE 50 SESIONES EXPONENCIAL, en gráfico de 5 minutos, de una hora y diario."* (`ege74_2NExk.txt`) |
| **PC-REG-10** | **Zonas de Interés (Fibonacci)** | Retrocesos de Fibonacci para delimitar el final del pullback en temporalidad intermedia. | *"esperar a que el precio en gráfico horario vuelva y ataque ciertos niveles... Fibonacci desde máximos hasta mínimos y vamos a esperar a que el gráfico horario llegue hasta 0,382, 0,5 o 0,618. En el momento en el cual lleguemos a esos niveles, bajaremos a gráfico de 5 minutos para ejecutar la posición."* (`ege74_2NExk.txt`) |
| **PC-REG-11** | **Gatillo de Entrada (EMA/Diag)** | Ejecución en temporalidad menor por ruptura de EMA 50 o directriz/diagonal. | *"Forma número uno, buscando algún tipo de diagonal (línea de tendencia)... Forma número dos, utilizando la media móvil: en el momento en el cual se rompa la media móvil, entiendo que es un cambio de tendencia y ejecuto."* (`ege74_2NExk.txt`) |
| **PC-REG-12** | **Parámetros Stop Loss (SL)** | Colocación inicial del stop loss en nivel de Fibonacci o extremo estructural. | *Opción A:* *"ponemos el stop loss en 0,618 de Fibonacci"* (`ege74_2NExk.txt`). *Opción B:* *"como el precio ya ha corregido hasta 0,75 (por encima de 0,618), el stop loss lo ponemos encima del máximo anterior"* (`ege74_2NExk.txt`). *Opción C:* *"pondríamos el stop loss por debajo de el nivel de 0,75 de Fibonacci"* (`l90QtxULIkE.txt` / demo en vivo). |
| **PC-REG-13** | **Parámetros Take Profit (TP)** | Colocación del TP en mínimos/máximos del movimiento anterior. | *"y el take profit en los mínimos anteriores."* (`ege74_2NExk.txt`) o *"máximos anteriores"* (`l90QtxULIkE.txt`). |
| **PC-REG-14** | **Gestión de Riesgo por Trade** | Porcentaje de asignación de riesgo según estilo (Swing vs. Day/Scalp). | *"riesgo 1%... en swing arriesgo el triple (nota: su riesgo base es 1%, en swing 3%)"* (`ege74_2NExk.txt` y `dXzF9ohdewE.txt`). |
| **PC-REG-15** | **Mitigación Activa de Riesgo** | Eliminación de riesgo al primer impulso a favor (Break-Even o Riesgo Libre). | *"con estas condiciones es muy difícil que el precio como mínimo no empiece a caer y me dé tiempo a quitar el 50% de riesgo o, dependiendo de la caída, el 100% del riesgo, y a partir de ahí vamos a riesgo libre."* (`ege74_2NExk.txt`) |
| **PC-REG-16** | **Gestión de Salida (Trailing)** | Trailing stop dinámico y objetivo utilizando la EMA 50 en temporalidad de ejecución. | *"en la medida en la cual el precio va cayendo, yo voy ajustando el stop loss siguiendo la media móvil (trailing)... Y esto lo hago de forma totalmente objetiva: la media móvil está más cerca, yo más cerca; la media móvil está más lejos, yo más lejos."* (`ege74_2NExk.txt`) |

---

### Pilar B: Meta-Capa de Filtro HMM (Hidden Markov Model)
*Fuente: Video `Cdhqu6rIvb0` (Estrategia Definitiva con Claude)*

| Código Regla | Categoría | Descripción Técnica | Cita Textual de Trazabilidad |
| :--- | :--- | :--- | :--- |
| **PB-REG-01** | **Propósito del Modelo** | El HMM regula la exposición del portafolio (activación/desactivación), no optimiza parámetros individuales. | *"El verdadero valor del HMM está en la gestión del portfolio, no en el ajuste de las estrategias. Los parámetros se mantienen fijos y lo que va variando es qué estrategia se activa, cuándo se activa, con qué riesgo se activa..."* (`Cdhqu6rIvb0.txt`) |
| **PB-REG-02** | **Variables de Entrada (Inputs)** | Indicadores matemáticos utilizados para alimentar el modelo estadístico. | *"volatilidad, retornos acumulados y momentum... a través de detectar acciones... deduce qué es lo que quieres y qué es lo que no quieres."* (`Cdhqu6rIvb0.txt`) |
| **PB-REG-03** | **Regímenes del Mercado** | Estados identificados de forma matemática para modular la estrategia. | *"El mercado no se comporta todo el rato del mismo tiempo... regímenes del mercado... calma y estrés... [o en automático] tendencia suave, tendencia, rango, crisis y recuperación."* (`Cdhqu6rIvb0.txt`) |
| **PB-REG-04** | **Adaptación al Rango** | Adaptar órdenes de entrada y SL si el HMM detecta estado no tendencial. | *"El propio HMM me dice: vete con cuidado. El mercado no está tendencial, el mercado está en rango... tu estrategia cambia y tú no ejecutas en límit, tú ejecutas en stop... o no pones un stop loss en el nivel de 0,75 de Fibonacci, tú lo pones por debajo de todos los mínimos... del propio rango."* (`Cdhqu6rIvb0.txt`) |

---

## 3. Validación de Inconsistencias y Puntos Críticos (Fase 3 Adelanto)

La auditoría de las transcripciones confirma contradicciones y ambigüedades críticas que deben resolverse cuantitativamente en la **Fase 2 y 3** para evitar fallos de implementación en Pine Script / Python:

### A. Inconsistencia en la colocación del Stop Loss (SL)
- **Video 3 (`l90QtxULIkE`)**: Ejecuta en vivo colocando el SL *"por debajo del nivel de 0,75 de Fibonacci"*.
- **Video 4 (`ege74_2NExk`)**: Especifica la regla teórica colocando el SL *"en 0,618 de Fibonacci"*.
- **Excepción en Video 4**: Si el precio corrige profundamente (hasta 0,75), el SL se desplaza *"encima/debajo del máximo/mínimo anterior"* (estructura extrema).
- **Riesgo:** Si el stop se coloca en 0,618 en un retroceso estándar, la probabilidad de ser barrido prematuramente es alta. Si se coloca en 0,75 de forma fija, el R:R cambia.
- **Solución para Fase 2:** Definiremos una regla matemática de SL dinámico: si el gatillo de 5m ocurre cuando la temporalidad intermedia (1h) ha corregido entre 0,382 y 0,618, el SL va al nivel de 0,75. Si el retroceso de 1h superó el 0,618 y llegó al 0,75, el SL se coloca en el extremo estructural (1.0 o máximo/mínimo anterior) más un buffer de holgura (por ejemplo, $0.1 \times ATR$).

### B. Ambigüedad en la definición de "Desaceleración" y "Gráfico Limpio" (HTF)
- Alex Ruiz determina de forma visual y discrecional si las próximas 2-3 velas diarias irán a la baja basándose en que el gráfico *"está limpio"* y *"empieza a desacelerar"* al tocar un extremo.
- **Riesgo:** Esto es imposible de programar de forma directa en un algoritmo sin proxies objetivos.
- **Solución para Fase 2:** Implementar proxies matemáticos cuantitativos:
  1. *Filtro de Extremo (Soporte/Resistencia)*: Zonas de pivote horizontales calculadas mediante máximos/mínimos locales de un periodo largo (ej. 20 o 50 velas diarias).
  2. *Desaceleración*: Disminución del rango de las velas diarias (cuerpos más pequeños) medida con el ratio $\frac{\text{Body Range}}{\text{ATR}(10)} < 0.6$ y aparición de patrones de reversión formales (velas tipo Pinbar/High-Test, Envolventes o Divergencias de Momentum en RSI).

### C. Sesgo de Selección y Falta de Fricciones en el Pilar A
- El video del Pilar A muestra un backtest rápido en TradingView que arrojó $+56\%$ en una semana, pero el mismo autor reconoce que carecía de realismo.
- **Riesgo:** Sesgo de supervivencia y de selección masivos. No modelar comisiones, spread ni slippage destruirá cualquier estrategia de 15m.
- **Solución para Fase 4:** En el backtesting en Python se modelarán de forma estricta las fricciones: comisiones de Bybit (ej. 0.02% maker / 0.055% taker), spread de futuros (0.01% - 0.05%) y slippage en ejecuciones de mercado (gatillo de 5m por ruptura de media móvil).

---

## 4. Determinación sobre el Alcance Recomendado (A + B + C)

Se ratifica que la combinación de los tres pilares es la aproximación más potente y profesional:
- **Pilar C (Estrategia Real)** provee el "Edge" o ventaja estadística base del sistema en diferentes activos.
- **Pilar B (HMM)** actúa como la meta-capa de control de riesgo, determinando si el entorno de mercado favorece la estrategia tendencial (Pilar C) y modulando el tamaño de posición o deteniendo la operativa durante fases de pánico o crisis extrema.
- **Pilar A (Claude Donchian)** se conserva únicamente como entorno de prueba y validación de infraestructura de Python/Bybit (ejemplo de bot que corre en la subcuenta).

---

## 5. Recomendación y Plan de Acción Inmediato (Fase 1)

Para proceder formalmente con la **Fase 1 (Ingeniería Inversa)**, se propone estructurar el documento técnico resolviendo los siguientes puntos que requieren definición en la Fase 3, pero cuyos límites deben trazarse desde ya:

1. **Definición de "Gráfico Limpio" en Diario:** ¿Utilizaremos un indicador de tendencia como el ADX o un canal de regresión lineal para cuantificar la "limpieza"?
2. **Definición de la Media Móvil Horaria:** Se establece que la EMA 50 es la referencia, pero Alex Ruiz menciona que *"si la media móvil está en Cuenca [muy lejos], esperamos a que el precio se acerque"*. Debemos establecer una distancia máxima matemática en términos de ATR para evitar entradas tardías (Chase).
3. **Mecánica del Trailing Stop:** ¿El stop de salida sigue la EMA 50 al cierre de la vela de ejecución (5m) o en tiempo real? (Recomendado: al cierre de vela para evitar falsos picos de volatilidad).

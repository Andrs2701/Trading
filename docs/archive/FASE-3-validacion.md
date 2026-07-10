# SATAR-1 — Fase 3: Validación de Consistencia

**Fecha:** 2026-07-07 · **Estado:** entregado

## 1. Resolución de las 8 ambigüedades (registro de Fase 1 §4)

| # | Ambigüedad | Resolución adoptada | Justificación |
|---|-----------|---------------------|---------------|
| 1 | "Quitar el 50% del riesgo": ¿stop a media distancia o cierre parcial? | **Desplazamiento del stop** (sin parciales) | R-C39 es explícita: "no a través de parciales... sino a través de medias móviles" (ege74). El trailing produce ese efecto de forma emergente |
| 2 | "Llegada acelerada" | **OR**: ER(tramo 5 velas) ≥ 0.35 **o** RSI(14) ≥ 70 / ≤ 30 | El OR replica su lectura visual (a veces habla de velas grandes, a veces de sobrecompra). La variante AND entra al análisis de sensibilidad (Fase 5) |
| 3 | Caducidad del sesgo direccional | **3 velas** de la temporalidad grande | "las próximas dos o tres velas" — se toma el límite superior; P20 con rango 2–4 en sensibilidad |
| 4 | Límites de pérdida d/s/m (nunca declarados) | **Provisional −2% / −4% / −6%** | Coherente con su peor mes auditado (−1.67%) y DD anual 4.33%. Se recalibrará tras la Fase 4 a 3σ de la distribución mensual del backtest |
| 5 | Filtros horarios | Cripto: 24/7. Forex/metales: bloquear 21:00–23:00 UTC (rollover) y fin de semana. Índices/acciones: solo horario regular de la bolsa de referencia | [F] operativo; el autor no fija sesiones (R-C17) |
| 6 | WR 56% vs 57%, RR "1,6" vs 1,55 | **Canónico: ege74** (57% / 1.55 / +1.30 / −0.73) | Video más reciente y más formal; l90 es narrativo |
| 7 | Features del HMM | vol=std(ret,20), ret. acum(20), ROC(10), z-score, filtered probs | Fase 2 §11; ventanas a sensibilidad |
| 8 | Temporalidad del trailing en scalping | La **intermedia** de la tríada (M5 en scalping) | Coherencia con D-6; ver contradicción C3 abajo |

## 2. Contradicciones internas detectadas (declaración vs. ejemplos)

**C1. "100% objetivo" vs. práctica discrecional.** Alex declara operar de forma objetiva "algoritmizada" por la EMA50, pero sus ejemplos incluyen decisiones discrecionales: elegir el trade "más limpio" (AUDCAD vs USDCAD), la diagonal como gatillo alternativo, "según la personalidad de cada uno" para el TP. **Tratamiento:** el sistema automatiza solo la rama objetiva (EMA + filtros formales D-2/D-4); la rama discrecional queda documentada y excluida. Consecuencia esperable: nuestra distribución de trades ≠ la suya; se acepta.

**C2. Frecuencia declarada (~80 trades/año) vs. filtros estrictos.** La cadena G1–G6 + confluencia + gatillo es muy selectiva. 80/año solo es plausible sumando un universo multi-activo amplio (20–40 símbolos). Si el backtest sobre el universo definido (R-C16) produce <40 trades/año, la métrica declarada queda no replicada y se reporta como tal.

**C3. Temporalidad del trailing.** En el ejemplo de swing (tríada W1/D1/H1) gestiona con la EMA50 de **una hora** — la temporalidad *pequeña* de esa tríada, no la intermedia. Esto contradice la lectura natural de D-6 (intermedia). **Tratamiento:** D-6 se mantiene como principal (H1 en day trading) y se añade el parámetro discreto **P36 = TF de gestión ∈ {intermedia, pequeña}** como variante estructural a comparar en Fase 5. Es la contradicción con mayor impacto en resultados (trailing pequeño = salidas más rápidas, WR↑, ganancia media↓).

**C4. "Sé lo que voy a ganar este año" (dXz).** Proyectar la expectancy pasada como certeza contradice su propio énfasis en probabilidades. Sin consecuencia para el sistema; se ignora como retórica.

**C5. R:R aceptado hasta 0.80 con WR 57%.** Expectancy = 0.57·1.30 − 0.43·0.73 = **+0.427%/trade** — positiva y consistente con ~34%/año a 80 trades. Los números declarados son internamente coherentes; eso NO valida que sean reales (ver S4).

## 3. Sesgos del proceso y del material fuente

| ID | Sesgo | Dónde aparece | Mitigación en SATAR-1 |
|----|-------|---------------|----------------------|
| S1 | Selección | Pilar A: "genera 5 estrategias y quédate la rentable" es data-snooping puro | Pilar A degradado a infraestructura (sin edge). Cualquier selección de variantes del Pilar C se hace SOLO en in-sample y se juzga en out-of-sample |
| S2 | Supervivencia | Testimonios (Ivania, Iván) y su propio track record: los alumnos que pierden no aparecen | Ninguna métrica de testimonios entra al sistema |
| S3 | Conflicto de interés | El autor vende formación (Trading Lab); los videos son embudo comercial | Se usan solo las reglas técnicas, no las promesas de rendimiento |
| S4 | Publicación/verificación | "Track record auditado" no es verificable públicamente desde los videos | Métricas declaradas = hipótesis H0 a falsar en Fase 4 |
| S5 | Look-ahead | Fractales confirman k velas tarde; Fib re-anclado; HMM suavizado | Solo velas cerradas; confirmación retardada aceptada; filtered probs; prueba de truncado (Fase 2 §14) |
| S6 | Sobreajuste | 33 parámetros posibles | Solo 6 optimizables; resto sensibilidad ±20% (Fase 2 §10) |
| S7 | Fricciones | Backtest del Pilar A sin comisiones/spread/slippage (admitido por el autor) | D-3: modelo de fricciones estricto (Fase 4 §3) |

## 4. Variables ocultas identificadas

1. **Ejecución humana experta**: Alex ajusta entradas "de forma muy precisa" (l90) — habilidad no codificable; el sistema será más torpe en entradas. 
2. **Contexto de noticias**: menciona noticias solo de pasada; el sistema no filtra calendario macro → propuesta: bloquear entradas ±15 min alrededor de eventos de alto impacto (parámetro opcional, Fase 6).
3. **Tamaño/liquidez**: él opera cuentas grandes en IBKR; nuestros supuestos de slippage deben estresarse en Monte Carlo.

## 5. Veredicto de la Fase 3

La estrategia es **formalizable y coherente internamente** una vez resueltas las ambigüedades; ninguna contradicción es fatal. Los riesgos dominantes no están en las reglas sino en (a) la brecha discrecional→objetivo (C1), (b) la frecuencia de señales (C2) y (c) la no-verificabilidad de las métricas declaradas (S4). Los tres se resuelven empíricamente en las Fases 4–5.

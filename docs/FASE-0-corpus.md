# SATAR-1 — Fase 0: Adquisición del Corpus

**Proyecto:** Sistema de Trading Automatizado — Metodología Alex Ruiz
**Fecha:** 2026-07-07
**Estado:** COMPLETADA (pendiente aprobación del usuario)

## Arquitectura aprobada

- **Pilar A** — Estrategia Donchian 15m cripto (video 1): estrategia base de ejemplo generada con Claude.
- **Pilar B** — Filtro de régimen HMM (video 2): meta-capa de activación/riesgo por régimen de mercado.
- **Pilar C** — Estrategia personal de Alex Ruiz (videos 3-5): impulso-pullback-continuación multi-timeframe. **Núcleo del sistema.**

## Corpus adquirido (5 videos, transcripciones completas en /corpus)

| # | Archivo | Video | Pilar | Contenido clave |
|---|---------|-------|-------|-----------------|
| 1 | K3xbHDqczZU.txt | "Le Doy $100 a Claude Para Que Haga Trading Por Mí" | A | Flujo de 3 pasos: generar 5 estrategias (BTC futuros, 15min tras iterar, ≤2 indicadores, long+short) → backtest Pine Script → deploy Bybit. Resultado +56% en 8 días / 9 trades / 78% WR. El propio autor lo declara NO significativo (sin comisiones/spread/slippage en backtest). |
| 2 | Cdhqu6rIvb0.txt | "Creo La Estrategia De Trading Definitiva Con Claude" | B | HMM con volatilidad+retornos+momentum; 5 regímenes detectados en BTC (tendencia suave 26%, tendencia 25%, rango 22%, recuperación 15%, crisis 11%); matriz de transición. CONCLUSIÓN CLAVE: el HMM no es para re-optimizar parámetros por régimen sino para gestión de portfolio (qué estrategia se activa, cuándo, con qué riesgo; parámetros fijos). |
| 3 | l90QtxULIkE.txt | "Esta Estrategia De Trading Es Aburrida Pero Vivo De Ella [55.181,82€/mes]" | C | Filosofía (sencillez/moderación/repetición), broker IBKR, WR 56%, RR ~1,6 aceptando hasta 0,80, DD máx anual 4,33%. Estructura 2 temporalidades: diaria (extremos del mercado, sobrecompra/sobreventa, desaceleración, giro) + horaria (cambio de estructura, Fibonacci 0,618 + EMA50 exponencial) + ejecución 5min (ruptura de diagonal/EMA). SL bajo 0,75 Fib; TP en máximos/mínimos anteriores. |
| 4 | ege74_2NExk.txt | "La ÚNICA ESTRATEGIA de trading que usaré en 2026 (paso a paso)" | C | **VIDEO NÚCLEO.** Reglas de no-trading (5), estilos swing/day/scalp con tríadas de temporalidades, tareas por temporalidad (grande=dirección 2-3 velas; intermedia=patrón; pequeña=ejecución), EMA50 exponencial en las 3 temporalidades, entrada por ruptura de EMA50 5min tras llegada a Fib 0,382/0,5/0,618 + EMA50 horaria, SL en 0,618 Fib (o sobre máximo anterior si corrigió a 0,75), TP en mínimos/máximos anteriores, trailing stop con EMA50, riesgo 1% (3% en swing). Métricas declaradas: 80 trades/año, RR promedio 1,55, WR 57%, ganancia media +1,30%, pérdida media −0,73%, ~34% anual (41% compuesto). |
| 5 | dXzF9ohdewE.txt | "(Vídeo Oculto) Explicando mi simple estrategia de trading" (webinar) | C | Fundamentos: estrategia = patrón + normas + largo plazo (≥1000 trades para significancia); principios no-perder/libertad/adaptación; fractalidad; entrada como unión de temporalidades; media móvil como "algoritmización" objetiva; riesgo 1%; gestión: quitar 50-100% del riesgo al primer recorrido favorable → riesgo libre; pérdida efectiva media 0,73% vs 1% arriesgado; 3 trades de ejemplo (2 long, 1 short). |

## Método de extracción

Videos 1-2: yt-dlp (subtítulos automáticos es-orig). Videos 3-5: bloqueo anti-bot de YouTube → extracción vía Chrome (hook fetch/XHR sobre timedtext del reproductor + volcado por DOM). Captcha resuelto manualmente por el usuario.

## Catálogo del canal (últimos 30 videos revisados, 2026-07-07)

Complementarios candidatos (NO descargados aún):
- QY7Kchg9nEU — "Cómo Ganar Dinero con el Trading… Incluso Cuando te Equivocas" (30 min) → candidato para Fase 6 (gestión de riesgo/expectancy).
- ilRAG0wC1as — "Preguntando a Traders Rentables por sus Peores Errores" → psicología (Fase 6/10).
- LSDFjPHl65w — "El Trading Con VWAP Nunca Ha Sido Tan Fácil" → indicador complementario (baja prioridad).
- zGhLmOHZFKo — "Esta Es La Estrategia De Trading Que Seguiría Si Solo Tuviera $5" / oXb2lySZhCU — "La Caja" → estrategias alternativas (fuera de alcance salvo petición).
El resto del listado son análisis de mercado diarios de Bitcoin (no contienen reglas de estrategia) y entrevistas.

## Inconsistencias ya detectadas (a desarrollar en Fase 3)

1. WR declarado varía: 56% (video 3) vs 57% (videos 4-5) — menor.
2. RR: video 3 dice "1,6" y acepta 0,80; videos 4-5 formalizan RR promedio 1,55 con rango 0,80–2,0.
3. SL: video 3 → bajo 0,75 Fib; video 4 → en 0,618 Fib, o sobre el extremo anterior si el retroceso superó 0,618; regla a formalizar con precisión en Fase 2.
4. "Dirección de las próximas 2-3 velas" en temporalidad grande es parcialmente subjetivo (desaceleración, "limpieza" del gráfico) → requiere proxies cuantitativos (Fase 2-3).
5. Las métricas (80 trades/año, 34% anual) son declaradas, no auditadas públicamente → deben validarse por backtesting (Fase 4), no aceptarse.
6. El video del pilar A advierte explícitamente que su resultado (+56%/semana) no es significativo.

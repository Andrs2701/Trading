# SATAR-1 — Fase 9: Protocolo de Cuenta Demo (90 días)

**Fecha:** 2026-07-07 · **Estado:** entregado · **Este documento prevalece sobre el esbozo del informe de validación (§5), que indicaba ≥100 trades: el criterio del plan es ≥150.**

## 0. Precondiciones para iniciar la demo

No se inicia el reloj de 90 días hasta que: Fase 4 ejecutada con datos reales (≥10 años donde exista) · Fase 5 APROBADA (WFE ≥ 0.5, DD_p95 < 15%, óptimos en meseta) · paridad Pine↔Python validada · 2 semanas de testnet técnico sin fallos operativos (FASE-7 §4).

## 1. Configuración

- Cuenta demo Bybit (cripto) con equity igual al capital previsto de producción (FASE-10).
- Sistema completo: Pilar C + HMM + kill-switch, parámetros CONGELADOS (los del WFO). Cambiar cualquier parámetro reinicia los 90 días.
- Universo: el portfolio definido en R-C16 (necesario para alcanzar la muestra — con un solo activo el sistema no genera 150 trades en 90 días; ver diagnóstico BTC de la Fase 4).
- Journal automático: cada trade con timestamp de señal teórica, timestamp de ejecución, slippage observado, R planificado vs R realizado.

## 2. Criterios de aprobación (los del plan — TODOS obligatorios al día 90)

| Criterio | Umbral |
|----------|--------|
| Profit Factor | > 1.5 |
| Drawdown máximo | < 10% |
| Expectancy | > 0 (objetivo: ≥ +0.15R) |
| Operaciones | **≥ 150** |
| Consistencia mensual | ≥ 2 de los 3 meses en positivo y ningún mes < −4% |

Si no se cumplen TODOS ⇒ **el sistema NO pasa a dinero real** (regla dura del proyecto).
Si la muestra queda entre 100–149 trades con el resto aprobado ⇒ extender la demo 45 días, no relajar el umbral.

## 3. Descalificación anticipada (aborta antes del día 90)

1. DD alcanza 10% en cualquier momento.
2. Racha de 8 pérdidas consecutivas con HMM activo.
3. Fallo de paridad operativa: >10% de los trades con desfase señal→ejecución superior a 5 velas M5, o >5% de señales teóricas no ejecutadas por fallos técnicos.
4. Kill-switch mensual disparado 2 meses seguidos.

Abortar ⇒ post-mortem escrito y regreso a la fase que corresponda (bug ⇒ F7; edge inexistente ⇒ F4/F5).

## 4. Detección de degradación demo-vs-backtest (revisión semanal)

- **Correlación** de la curva de equity demo vs la curva simulada del mismo periodo: alerta si < 0.7 durante 4 semanas.
- **Slippage real vs modelado**: si el observado > 2× el modelo de fricciones, recalibrar FASE-4 §3 y re-simular (sin tocar la estrategia).
- **Distribución de R**: test de Kolmogorov–Smirnov entre R demo y R backtest cada 30 trades; p < 0.05 sostenido ⇒ investigar (ejecución o régimen).
- **Embudo de señales**: nº de BIAS/ARMED/gatillos por semana comparado con la tasa histórica del backtest; divergencia > 50% ⇒ revisar feed de datos.

## 5. Salida de la fase

Informe final de demo con las métricas de FASE-4 §4, el veredicto contra §2–§3 y la recomendación GO/NO-GO firmada en el journal. Solo con GO se abre la Fase 10.

# SATAR-1 — Fase 10: Producción

**Fecha:** 2026-07-07 · **Estado:** entregado (se activa SOLO con el GO de la Fase 9)

## 1. Capital inicial y escalamiento progresivo

- **Capital inicial recomendado:** el menor entre (a) capital cuyo 1%/trade soporte el tamaño mínimo de contrato del universo sin exceder 1.2% de riesgo real, y (b) dinero cuya pérdida total no comprometa las finanzas personales. Referencia práctica: 5.000–10.000 USD.
- **Escalón 0 (meses 1–3):** 50% del capital previsto, riesgo 0.5%/trade (mitad del validado). Objetivo: verificar que producción ≈ demo, no ganar.
- **Escalón 1 (meses 4–6):** si PF ≥ 1.4 y correlación equity-real↔backtest ≥ 0.7 ⇒ 100% del capital, riesgo 1%.
- **Escalones siguientes (trimestrales):** añadir capital solo tras trimestre positivo; retirar 30% de beneficios realizados, reinvertir 70%. El equity de referencia del sizing se actualiza mensualmente (FASE-6 §5).
- Nunca aumentar el % de riesgo por trade: el escalamiento es SIEMPRE por capital, no por riesgo.

## 2. Control psicológico (protocolo humano, R-C47 y reglas de no-trading)

- El operador NO interviene trades del bot (prohibido cerrar/mover manualmente salvo emergencia operativa documentada). Cada intervención manual se registra y 3 intervenciones/mes ⇒ revisión del protocolo.
- Checklist diario de 2 minutos (mercado abierto, bot vivo, posiciones reconciliadas) y revisión semanal de 30 min con el dashboard — el resto del tiempo, fuera de la pantalla (filosofía "alertas, no pantalla" del corpus).
- Reglas R-C05/06 aplican al MANTENIMIENTO del sistema: no tocar código ni parámetros en caliente, ni tras un día de pérdidas.

## 3. Registro de operaciones (journal)

Automático (extiende el de la demo): por trade — señal, ejecución, slippage, R plan/real, régimen HMM, estado del kill-switch; por día — equity, exposición, incidencias. Export mensual a CSV + resumen. Es el insumo del monitoreo de degradación (§5).

## 4. Dashboard de métricas y alertas automáticas

- **Dashboard** (semanal): equity y DD actual vs DD_p95; PF/WR/expectancy móviles (ventana 30 trades) vs backtest; distribución de R; señales por semana; estado HMM por activo; slippage medio.
- **Alertas push/email inmediatas:** kill-switch disparado (cualquier nivel) · DD > 6% · bot caído o sin datos > 15 min · discrepancia posición bot↔exchange · racha de pérdidas ≥ 5 · cambio de régimen HMM a crisis.

## 5. Plan de retirada del sistema (condiciones de apagado definitivo)

Se detiene el sistema y se pasa a revisión completa (no se "ajusta en caliente") si:
1. DD en real supera **12%** (por encima del límite demo: margen de degradación agotado).
2. Correlación equity-real ↔ backtest < 0.7 durante un mes completo (alpha decay estructural).
3. Expectancy móvil (últimos 60 trades) < 0 durante 2 meses consecutivos.
4. 3+ fallos operativos graves (API/VPS/ejecución) en una semana.
5. Cambio estructural del mercado o del exchange que invalide supuestos (delisting, cambio de funding/fees > 2× lo modelado).

Tras la retirada: post-mortem, re-validación completa (Fases 4–5 con datos que incluyan el periodo real) y, si procede, re-entrada por la Fase 9. El capital retirado descansa en stable/efectivo — nunca se "recupera" subiendo el riesgo.

## 6. Cierre del proyecto

Con esto, el ciclo de vida completo queda definido: corpus → reglas → formalización → validación → evidencia → robustez → riesgo → código → plataforma → demo → producción → retirada. El sistema solo existe en producción mientras la evidencia lo sostenga — fiel al mandato original del proyecto: nada se asume rentable sin demostrarlo.

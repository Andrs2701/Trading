# SATAR-1 — Fase 6: Sistema de Gestión de Riesgo

**Fecha:** 2026-07-07 · **Estado:** entregado (valores marcados ⚙ se recalibran con la distribución real del backtest de Fase 4)

## 1. Riesgo por operación

- Base: **1%** del equity (R-C44); swing 3% solo en operación manual — el sistema automatizado usa 1% uniforme.
- Riesgo efectivo = 1% × mult_HMM (1.0 / 0.5 / 0.0 según régimen, Fase 2 §11) × factor de reducción dinámica (§4).
- Pérdida esperada real < 1% por el trailing (histórico declarado: −0.73% media).

## 2. Límites jerárquicos y kill-switch automático

| Nivel | Límite ⚙ | Acción automática |
|-------|---------|-------------------|
| Trade | 1% (hard, por SL0 + sanidad P24/P25) | qty calculada sobre distancia al stop |
| Día | −2% | no nuevas entradas hasta el día siguiente (posiciones abiertas conservan su gestión) |
| Semana | −4% | pausa hasta el lunes siguiente |
| Mes | −6% | pausa hasta el mes siguiente + revisión manual obligatoria |
| Racha | 6 pérdidas consecutivas ⚙ | reducción dinámica activada (§4) |
| Drawdown global | 10% desde máximo de equity | **detención total del sistema** + post-mortem antes de rearmar |

⚙ Recalibración post-Fase 4: límite mensual = percentil 95 de la distribución Monte Carlo de meses perdedores; racha = racha_p95 + 1; DD global = min(10%, DD_p95 × 1.25).

## 3. Position sizing

- **Fixed-fractional**: qty = (riesgo_efectivo × equity) / |entry − SL0|, redondeado al step del instrumento; si el mínimo del broker implica riesgo > 1.2%, el trade se descarta.
- **Kelly como referencia (NO como sizing)**: con métricas declaradas (p=0.57, b=1.78 bruto por trade ganador/perdedor) f* = p − q/b ≈ 0.57 − 0.43/1.78 ≈ **0.33**. Kelly completo es inaceptable (DD teórico >50%); 1% ≈ Kelly/33 — confirma que el 1% es conservador y correcto.
- Correlación: posiciones en activos correlacionados (misma divisa base, o cripto entre sí) cuentan doble contra el máximo de 3 simultáneas (P33).

## 4. Reducción dinámica del tamaño

```
racha_pérdidas ≥ 3  ⇒ riesgo × 0.75
racha_pérdidas ≥ 6  ⇒ riesgo × 0.50
recuperación: 2 ganadores consecutivos restauran el escalón anterior
DD actual > 5%      ⇒ riesgo × 0.50 hasta que DD < 3%
```

## 5. Gestión de capital (cuenta)

- Capital de trading segregado del capital personal; retiros solo desde beneficios realizados trimestrales.
- El equity de referencia para el 1% se actualiza a cierre de cada mes (no intra-mes) — evita espiral de sizing en rachas.
- Buffer de margen: exposición nocional total ≤ 5× equity (cripto perp) / según margen del broker en forex.

## 6. Riesgos operacionales (no de mercado)

| Riesgo | Mitigación |
|--------|-----------|
| Caída de conexión/VPS con posición abierta | SL y TP SIEMPRE como órdenes en el servidor del broker/exchange, nunca solo en memoria del bot |
| API keys comprometidas | permisos solo-trading (sin retiros), subcuenta dedicada (patrón del Pilar A), rotación trimestral |
| Fallo del feed de datos | watchdog: sin datos > 3 velas TF_P ⇒ no nuevas entradas; > 1 vela TF_I ⇒ alerta |
| Bug del bot | reconciliación posición-bot vs posición-exchange cada vela TF_P; discrepancia ⇒ cierre y detención |
| Evento macro extremo | (opcional, Fase 3 §4) bloqueo de entradas ±15 min en eventos de alto impacto |

## 7. Interacción con el Pilar B

El HMM es la primera línea de defensa (crisis ⇒ exposición 0). El kill-switch es la segunda y es independiente: aunque el HMM falle en detectar el régimen, los límites jerárquicos acotan la pérdida. Nunca se desactivan mutuamente.

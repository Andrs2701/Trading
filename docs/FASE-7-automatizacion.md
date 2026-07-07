# SATAR-1 — Fase 7: Automatización

**Fecha:** 2026-07-07 · **Estado:** entregado (Pine ✅ · Python backtest ✅ · Python live ✅ esqueleto validado · MQL5 ⚠ plantilla)

## 1. Artefactos y su estado

| Artefacto | Rol | Estado |
|-----------|-----|--------|
| `code/pine/SATAR1_PilarC.pine` | Estrategia Pine v6 completa (backtest visual + alertas TradingView) | Completo; anti-repintado `expr[1]+lookahead_on`; aproximaciones A1–A3 documentadas en cabecera; paridad pendiente de validar vs Python (FASE-2 §14) |
| `code/python/satar_backtest.py` | Motor de referencia (fuente de verdad de la lógica) | Completo y corregido (pinbar, neckline, SL profundo, kill-switch por periodo) |
| `code/python/download_data.py` | Adquisición de klines M5 Bybit | Completo (backoff ante rate-limit, dedupe, `--symbol/--days`) |
| `code/python/satar_live.py` | **Ejecutor live/demo nativo** (Pilar C + hook HMM) sobre Bybit v5 | Esqueleto funcional: dry-run por defecto, testnet, SL/TP server-side, trailing por `trading-stop`, estado local anti-duplicado |
| `code/mql5/SATAR1_PilarC.mq5` | Port a MetaTrader 5 (forex/metales) | **Plantilla**: máquina de estados, trailing D-6, gatillo M5, sizing y kill-switch listos; módulo G e I marcados TODO — NO usar hasta completar y validar paridad |

## 2. Arquitectura de ejecución (resuelve la pregunta del bridge)

Se descartó el esquema "alertas TradingView → webhook → bridge" como camino principal:
TradingView no puede ejecutar el HMM ni el kill-switch de portfolio, los webhooks añaden
un punto de fallo y el free tier limita alertas. **Decisión: ejecutor nativo en Python**
(`satar_live.py`) que recalcula la máquina de estados sobre una ventana rodante de
klines y usa la MISMA clase `Engine` del backtest — paridad backtest↔live por
construcción. TradingView queda como capa de monitoreo/gráficos y alertas redundantes.

```
Bybit REST (klines M5) ──▶ satar_live.py (Engine FASE-2 + HMM FASE-2 §11)
                               │ señal fresca → orden Market + SL/TP server-side
                               │ cierre H1   → amend stop (trailing D-6)
                               ▼
                        Bybit v5 (subcuenta, API solo-trading)
TradingView (Pine) ────▶ monitoreo visual + alerta redundante (no ejecuta)
```

## 3. Requisitos de despliegue

- VPS Linux/Windows con reloj NTP sincronizado; Python 3.11+, `pandas`, `numpy` (+`hmmlearn` para Pilar B).
- Claves API en variables de entorno (`BYBIT_API_KEY/SECRET`), subcuenta dedicada, permisos solo-trading, sin retiros (patrón del Pilar A, R-A03).
- Watchdog (FASE-6 §6): systemd/NSSM con reinicio automático; sin datos > 3 velas M5 ⇒ no nuevas entradas.
- Logs: cada ciclo escribe señal/estado; `satar_live_state.json` versiona la posición local; reconciliación contra `/v5/position/list` en cada ciclo (TODO menor).

## 4. Orden de puesta en marcha

1. `python satar_live.py --symbol BTCUSDT --once` (dry-run, valida datos y señal).
2. `--testnet --live` durante ≥2 semanas (valida órdenes, trailing, reconexión).
3. Demo FASE-9 (90 días) → solo entonces considerar mainnet con capital de FASE-10.

## 5. Pendientes explícitos

- Validación de paridad Pine↔Python en subperiodo común (criterio FASE-2 §14).
- Completar módulos G/I del EA MQL5 y su prueba en Strategy Tester.
- Reconciliación automática posición-bot vs exchange y bloqueo multi-símbolo (P33) en `satar_live.py` (hoy opera 1 símbolo por proceso).

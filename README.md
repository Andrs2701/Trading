# SATAR-1 — Sistema de Trading Automatizado

Ingeniería inversa, validación estadística y automatización de la metodología propia de trading. **Nada se asume rentable sin demostrarlo**: las métricas
declaradas en los videos son hipótesis a falsar, no supuestos.

**👉 Para retomar el proyecto, empieza siempre por [`docs/ESTADO-Y-CONTINUIDAD.md`](docs/ESTADO-Y-CONTINUIDAD.md)** — resume qué está hecho, el hallazgo empírico más reciente y los próximos pasos concretos.

## Arquitectura

- **Pilar C** (edge): impulso–pullback–continuación multi-timeframe (D1/H1/M5), EMA50 exponencial, Fibonacci 0.382–0.618, riesgo 1%, trailing por EMA50 H1.
- **Pilar B** (meta-capa): HMM de regímenes que modula exposición (1.0/0.5/0.0) — nunca re-optimiza parámetros.
- **Pilar A** (infraestructura): Donchian 15m como banco de pruebas de la tubería Bybit.

## Estructura

| Ruta | Contenido |
|------|-----------|
| `corpus/` | 5 transcripciones fuente (trazabilidad de cada regla) |
| `docs/FASE-0…10` | Documentos por fase (corpus → reglas → formalización → validación → backtesting → robustez → riesgo → automatización → plataforma → demo → producción) |
| `docs/FASE-6-audit-completo.md` · `docs/informe_validacion_y_pruebas.md` | Auditoría de código y hoja de ruta de pruebas |
| `code/python/satar_backtest.py` | **Motor de referencia** (máquina de estados FASE-2, fricciones FASE-4, kill-switch FASE-6) |
| `code/python/download_data.py` | Descarga de klines M5 (Bybit v5) |
| `code/python/satar_live.py` | Ejecutor demo/live (dry-run por defecto; testnet; SL/TP server-side) |
| `code/pine/SATAR1_PilarC.pine` | Estrategia TradingView (Pine v6, anti-repintado) |
| `code/mql5/SATAR1_PilarC.mq5` | Plantilla de port a MT5 (módulo G/I pendientes — no operar) |

## Inicio rápido

```bash
cd code/python
pip install numpy pandas hmmlearn      # hmmlearn requerido para el Pilar B
python satar_backtest.py --smoke       # validar el motor
python download_bulk_binance.py --symbol BTCUSDT --start 2020-01   # historia larga (recomendado)
python satar_backtest.py --csv btcusdt_m5.csv          # Pilar C
python satar_backtest.py --csv btcusdt_m5.csv --hmm    # Pilar C + B
python satar_live.py --symbol BTCUSDT --once           # señal actual (dry-run)
```

Ruta de pruebas completa: `docs/informe_validacion_y_pruebas.md` §3.
Reglas duras: no dinero real sin aprobar Fase 5 (robustez) y Fase 9 (demo 90 días,
PF>1.5 · DD<10% · expectancy>0 · **≥150 trades** · consistencia mensual).

## Estado (2026-07-09)

**Proyecto completado — Veredicto: NO APROBADO.** Fases 0–8 completas. Fase 4 corrida sobre
5 activos cripto (BTC/ETH/SOL/XRP/BNB, 144 trades). Fase 5 (WFO + Monte Carlo) ejecutada
completa: 6 de 7 criterios de aprobación fallan (OOS negativo y empeorando, óptimo en pico
aislado, DD_p95 -24.3%, expectancy negativa bajo fricciones, concentración extrema por
activo y por período). La metodología de Alex Ruiz, formalizada objetivamente, **no muestra
edge estadístico verificable** en el universo cripto probado. El sistema no pasa a Fase 9.
Ver el veredicto completo y las opciones de continuidad en
`docs/ESTADO-Y-CONTINUIDAD.md` §5 y §7.

**Descargo:** proyecto educativo/de investigación. Ni el código ni los documentos
constituyen asesoría financiera.

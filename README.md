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
| `corpus/` | 5 transcripciones fuente (trazabilidad de cada regla, hipótesis SATAR-1) |
| `docs/archive/FASE-0…10` | SATAR-1: documentos por fase (corpus → reglas → formalización → validación → backtesting → robustez → riesgo → automatización → plataforma → demo → producción) |
| `docs/SWEEP-formalizacion.md` · `docs/SWEEP-resultados-veredicto.md` | Hipótesis SWEEP: reglas exactas y veredicto |
| `code/python/satar_backtest.py` | **Motor de referencia** (auditado, reutilizado por HYDRA y SWEEP) |
| `code/python/hydra_backtest.py` · `hydra_wfo.py` · `hydra_montecarlo.py` | Motor e infraestructura de validación de la hipótesis HYDRA |
| `code/python/sweep_backtest.py` · `sweep_wfo.py` · `sweep_montecarlo.py` | Motor e infraestructura de validación de la hipótesis SWEEP |
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

## Estado (2026-07-10)

**3 hipótesis probadas con el mismo protocolo de rigor — las 3 rechazadas.** SATAR-1
(pullback a EMA multi-timeframe), HYDRA (pullback + filtro de régimen HMM/Hurst) y
SWEEP (liquidity sweep / stop hunt sobre estructura semanal) fueron formalizadas sin
ambigüedad, probadas sobre 5 activos cripto (BTC/ETH/SOL/XRP/BNB, 2020-2025) y llevadas por
Walk-Forward Optimization + Monte Carlo con holdout intocable. Ninguna muestra edge
estadístico verificable. Detalle completo y opciones de continuidad en
[`docs/ESTADO-Y-CONTINUIDAD.md`](docs/ESTADO-Y-CONTINUIDAD.md).

**Descargo:** proyecto educativo/de investigación. Ni el código ni los documentos
constituyen asesoría financiera.

# SATAR-1 — Fase 8: Selección de Plataforma

**Fecha:** 2026-07-07 · **Estado:** entregado

## 1. Matriz comparativa (criterios del plan)

| Plataforma | Facilidad | Costo | Automatización | Backtesting | Broker compatible | Escalabilidad | Veredicto |
|---|---|---|---|---|---|---|---|
| **TradingView (Pine v6)** | Alta | $0–60/mes | Media (alertas/webhooks; sin HMM, sin riesgo de portfolio) | Bueno visual, sin fricciones finas ni multi-activo | Vía webhooks a terceros | Baja | Monitoreo y prototipado; NO motor de ejecución |
| **Python puro (REST/ccxt + VPS)** | Media | ~$5–20/mes VPS | Excelente (control total: HMM, kill-switch, multi-activo) | Motor propio ya construido | Bybit/Binance/cualquier REST | Alta | **Elegida para cripto** |
| **MetaTrader 5 (MQL5)** | Media | $0 (broker) | Excelente en FX/CFD; HMM requiere puente (archivo/socket a Python) | Strategy Tester con ticks reales — muy bueno | Enorme oferta FX/CFD | Alta | **Elegida para forex/metales/índices** |
| **cTrader (C#)** | Media | $0 | Buena (cAlgo); ecosistema menor | Bueno | Menos brokers | Media | Alternativa a MT5 si el broker lo exige |
| **NinjaTrader** | Media-baja | Licencia | Buena en futuros US | Bueno | Futuros US | Media | Solo si se migra a futuros regulados |
| **QuantConnect (LEAN)** | Baja (curva alta) | $0–20+/mes | Excelente; investigación de primer nivel | Excelente (datos institucionales) | IB, cripto, FX | Alta | Candidata para re-validación independiente del backtest (fase de investigación, no ejecución) |
| **IBKR API** | Baja | Comisiones | Excelente | Requiere motor propio | IBKR (el broker real de Alex Ruiz) | Alta | Para la pata de ACCIONES/ETFs si se activa (R-C15) |

## 2. Recomendación justificada

**Arquitectura híbrida por clase de activo, con el motor Python como cerebro único:**

1. **Cripto → Python + Bybit v5** (`satar_live.py`). Único camino que ejecuta el sistema completo tal como fue validado: misma clase `Engine` del backtest (paridad por construcción), HMM en tiempo real, kill-switch jerárquico y sizing exactos. Costo marginal ~un VPS.
2. **Forex/metales → MT5 (MQL5)** cuando se active esa pata: mejor ejecución/backtest tick-level del ecosistema retail y acceso a los pares que Alex opera. El HMM y el riesgo global siguen en Python (puente por archivo/named-pipe) para no duplicar lógica.
3. **TradingView** se conserva solo como capa visual y de alertas redundantes.
4. **QuantConnect** queda anotada como verificador independiente del backtest (anti-sesgo de implementación propia) antes de producción, si se desea una segunda opinión.

Razón de fondo: el edge del sistema no está en la latencia sino en la disciplina de reglas
multi-timeframe + gestión de riesgo; la plataforma óptima es la que ejecuta EXACTAMENTE la
lógica validada. Esa es el motor Python — todo lo demás son terminales.

# Hipótesis 4 — Estrategia BREAKOUT-ATR (Volatility Expansion Breakout)

## *Momentum de Ruptura de Rango con Expansión de Volatilidad*

---

## 1. Justificación y Fundamento de Microestructura

Las tres hipótesis previas (SATAR-1, HYDRA, SWEEP) demostraron que buscar **giros o pullbacks** en marcos de tiempo de corto plazo (M5/H1) carece de edge matemático debido al ruido y los costos de fricción que destruyen los ratios R:R ajustados.

En criptomonedas perpetuas, la ineficiencia de mercado más persistente y explotada por fondos cuantitativos es el **Momentum / Trend-Following de Ruptura** respaldado por las colas anchas (fat tails) de la distribución de retornos. Debido al apalancamiento masivo de la retail y los esquemas de liquidaciones en cascada, cuando el precio rompe un rango relevante con expansión de volatilidad, tiende a generar impulsos prolongados e inerciales.

---

## 2. Reglas Lógicas de la Estrategia

### 2.1 Definición de Estructura (H1)
1. **Rango de Referencia (24h):** Calculamos dinámicamente el precio máximo (`range_high`) y mínimo (`range_low`) de las últimas 24 velas de H1 (24 horas).
2. **Volatilidad Local:** Medimos el ATR de 14 períodos en H1 (`atr_h1`).

### 2.2 Filtro de Régimen (D1)
- Evaluamos el **Hurst Exponent** de 100 días sobre velas D1.
- Solo operamos si `Hurst > 0.52` (mercado persistente/tendencial). Si el mercado está en rango (`Hurst < 0.48`), desactivamos las entradas para evitar falsas rupturas.

### 2.3 Setup de Entrada (H1)
*   **Setup Long:** El precio de H1 cierra por encima de `range_high`.
*   **Setup Short:** El precio de H1 cierra por debajo de `range_low`.

### 2.4 Gatillo y Filtro de Confirmación (H1 -> M5)
Cuando se confirma el setup en H1, esperamos en la primera vela de M5 correspondiente a la nueva hora:
1.  **Expansión de Rango:** La vela de ruptura H1 debe tener un cuerpo (Close - Open) mayor a `range_expansion_mult` (1.2x) del `atr_h1` (confirmación de momentum real, no un goteo lento).
2.  **Confirmación de Volumen:** El volumen de la vela de ruptura H1 debe ser superior a 1.5x la media de volumen de las últimas 20 horas.
3.  **Entrada:** Entrada a mercado al inicio del nuevo ciclo H1 (primera vela M5) si se cumplen las condiciones de volumen y rango en la vela H1 que acaba de cerrar.

### 2.5 Gestión de Posición
*   **Stop Loss Inicial (SL0):** Se coloca a `stop_atr_mult` (1.5x) del `atr_h1` desde el precio de entrada. Esto protege la posición contra el retroceso normal intradía (*retest* del rango roto).
*   **Take Profit (TP) Dinámico:** No usamos un TP fijo. La estrategia busca capturar "runs" extendidos.
*   **Trailing Stop:** Se activa un trailing stop a favor del trade en base a la EMA50 de H1 más un buffer de 1.0x ATR de H1. El trailing stop solo se actualiza de forma restrictiva al cierre de cada vela H1 para evitar salidas prematuras por ruido en M5.

---

## 3. Parámetros del Sistema (BREAKOUT-ATR)

| # | Parámetro | Default | Descripción |
|---|---|---|---|
| B01 | `lookback_hours` | 24 | Ventana para definir el rango estructural (H1) |
| B02 | `range_expansion_mult` | 1.2 | Multiplicador de ATR para validar la fuerza de la vela de ruptura |
| B03 | `vol_spike_mult` | 1.5 | Multiplicador de volumen promedio para confirmar participación institucional |
| B04 | `stop_atr_mult` | 1.5 | Distancia del Stop Loss inicial en unidades de ATR H1 |
| B05 | `trail_atr_buffer` | 1.0 | Buffer de ATR H1 para sumar/restar a la EMA50 H1 en el trailing |
| B06 | `hurst_filter` | 0.52 | Filtro mínimo de Hurst en D1 para permitir operar momentum |

---

## 4. Plan de Verificación

El pipeline se ejecutará con el mismo estándar de rigor absoluto del repositorio:
1.  **Plumbing (Smoke Test):** Ejecutar sobre BTCUSDT para asegurar que no hay look-ahead ni bugs de ejecución.
2.  **Multi-activo (S3):** Probar el pool de 5 activos (BTC, ETH, SOL, XRP, BNB) para medir la consistencia del edge.
3.  **WFO (S4):** Optimizar la combinación de `range_expansion_mult`, `stop_atr_mult` y `vol_spike_mult`.
4.  **Monte Carlo (S4):** Validar la robustez al ruido de precio y fricciones con la fórmula de equity compuesta corregida.

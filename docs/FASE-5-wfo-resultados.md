# Resultados de Walk-Forward Optimization (WFO) — Fase 5

Este documento detalla los resultados obtenidos al ejecutar la optimización Walk-Forward en el pool combinado de los 5 activos cripto (BTCUSDT, ETHUSDT, SOLUSDT, XRPUSDT, BNBUSDT) bajo el protocolo anti data-snooping.

## Configuración del WFO

* **Partición Temporal (Región WFO):** 2020-01-01 a 2025-07-01 (Holdout final del 15% reservado).
* **Esquema de Folds (Anclado-Rodante):**
  * **Fold 1:** In-Sample (IS) 2020-01-01 a 2023-01-01 (3 años) | Out-of-Sample (OOS) 2023-01-01 a 2024-01-01 (1 año).
  * **Fold 2:** In-Sample (IS) 2020-01-01 a 2024-01-01 (4 años) | Out-of-Sample (OOS) 2024-01-01 a 2025-01-01 (1 año).
  * **Fold 3:** In-Sample (IS) 2020-01-01 a 2025-01-01 (5 años) | Out-of-Sample (OOS) 2025-01-01 a 2025-07-01 (6 meses).
* **Parámetros Optimizados (Grid Coarse):**
  * `er_clean` (P11): [0.22, 0.30, 0.38]
  * `er_arrive` (P15): [0.26, 0.35, 0.44]
  * `decel_max` (P17): [0.45, 0.60, 0.75]
* **Métrica Objetivo:** $Obj = \frac{E_R \cdot \sqrt{N}}{1 + |DD| \cdot 5}$ (Prioriza expectativa de R y número de operaciones penalizando el drawdown).

---

## Tabla de Resultados por Fold

| Fold | Ventana IS | Ventana OOS | Mejor Combo (IS) | Obj IS | Trades IS | Exp. R IS | Obj OOS | Trades OOS | Exp. R OOS |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **F1** | 2020–2023 | 2023–2024 | `{'er_clean': 0.30, 'er_arrive': 0.26, 'decel_max': 0.45}` | 0.9548 | 66 | +0.1412 R | -0.0788 | 34 | -0.0178 R |
| **F2** | 2020–2024 | 2024–2025 | `{'er_clean': 0.30, 'er_arrive': 0.26, 'decel_max': 0.45}` | 0.6084 | 100 | +0.0871 R | -0.2872 | 17 | -0.0784 R |
| **F3** | 2020–2025 | 2025 (H1) | `{'er_clean': 0.30, 'er_arrive': 0.26, 'decel_max': 0.45}` | 0.4658 | 117 | +0.0631 R | -0.4731 | 15 | -0.1575 R |

---

## Análisis y Hallazgos Clave

### 1. Consistencia del Combo Optimizador
El optimizador seleccionó exactamente el mismo combo de parámetros en los 3 folds:
* **`er_clean` = 0.30** (Mantiene el default original).
* **`er_arrive` = 0.26** (Reduce el filtro de llegada acelerada de 0.35 a 0.26, permitiendo que entren más operaciones al sistema).
* **`decel_max` = 0.45** (Aumenta la exigencia sobre la desaceleración del precio diaria de 0.60 a 0.45 para filtrar trades con demasiado impulso adverso).

### 2. Rendimiento In-Sample (IS) vs. Out-of-Sample (OOS)
* **In-Sample (Rentable):** La optimización logró encontrar un "edge" en las ventanas in-sample, resultando en un expectancy positivo de entre **+0.063R y +0.141R** con una muestra de hasta 117 operaciones.
* **Out-of-Sample (Pérdidas):** Al aplicar la configuración óptima sobre datos futuros no vistos (OOS), el rendimiento se deteriora y vuelve a ser negativo en los 3 folds:
  * Fold 1 OOS: **-0.0178 R** (Cerca del punto de equilibrio).
  * Fold 2 OOS: **-0.0784 R**.
  * Fold 3 OOS: **-0.1575 R**.

### 3. Veredicto del Walk-Forward Efficiency (WFE)
$$\text{WFE} = \frac{\text{Media OOS Obj}}{\text{Media IS Obj}} = \frac{-0.2797}{0.6763} = -0.4136$$

**Veredicto:** **SOBREOPTIMIZACIÓN (WFE < 0.4)**

El WFE negativo confirma que la rentabilidad obtenida In-Sample se debió al ajuste de curvas sobre datos históricos (curve fitting) y no a una ventaja comercial robusta y generalizable. La estrategia no logra mantener una expectativa positiva en datos fuera de muestra (OOS).

---

## Configuración Congelada para la Fase E

A pesar del veredicto negativo del WFO, el protocolo exige congelar los mejores parámetros del último fold (F3, que cuenta con mayor cantidad de datos históricos In-Sample) para evaluar el Holdout final:

```json
{
  "er_clean": 0.30,
  "er_arrive": 0.26,
  "decel_max": 0.45
}
```

Estos parámetros se utilizarán en la Fase E para la ejecución del Holdout (último 15% de los datos) y las simulaciones de Monte Carlo.

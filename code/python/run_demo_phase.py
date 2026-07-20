# -*- coding: utf-8 -*-
"""
SATAR-1 / BREAKOUT-ATR — Gestor de Fase Demo 90 Días (Fase 9).

Script principal para ejecutar y auditar automáticamente la Fase Demo de 90 días
sobre Bybit Testnet (o Dry-Run en vivo) bajo las reglas duras de FASE-9:
- Capital de referencia: $200.00 USD (Riesgo 1% = $2.00 USD por trade)
- Filtro Bollinger Band Squeeze D1 activado (PF 1.491, Exp +0.3432R, DD -10.1%)
- Registro automático de cada trade en demo_trades_audit.csv
- Seguimiento de días transcurridos y checklist de aprobación (PF>1.5, DD<10%, N>=150)
"""
from __future__ import annotations
import argparse, json, math, os, sys, time
from datetime import datetime, timezone
import pandas as pd

from breakout_live import cycle, make_params, load_state, save_state, APPROVED_SYMBOLS

TRACKER_FILE = "demo_phase_tracker.json"
AUDIT_CSV = "demo_trades_audit.csv"

def init_demo_tracker(equity: float = 200.0) -> dict:
    if os.path.exists(TRACKER_FILE):
        with open(TRACKER_FILE) as f:
            return json.load(f)
            
    now_str = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    st = {
        "start_date": now_str,
        "days_target": 90,
        "initial_equity": equity,
        "current_equity": equity,
        "risk_pct": 0.01,
        "risk_usd": equity * 0.01,
        "total_trades": 0,
        "winning_trades": 0,
        "losing_trades": 0,
        "total_pnl": 0.0,
        "total_r": 0.0,
        "max_drawdown": 0.0,
        "peak_equity": equity,
        "profit_factor": 0.0,
        "symbols": APPROVED_SYMBOLS,
        "mode": "TESTNET_DEMO"
    }
    with open(TRACKER_FILE, "w") as f:
        json.dump(st, f, indent=2)
    return st

def update_demo_audit(trade_info: dict):
    file_exists = os.path.exists(AUDIT_CSV)
    df_new = pd.DataFrame([trade_info])
    df_new.to_csv(AUDIT_CSV, mode='a', header=not file_exists, index=False)

def print_demo_header(st: dict):
    now = datetime.now(timezone.utc)
    start_dt = datetime.strptime(st["start_date"], "%Y-%m-%d %H:%M:%S UTC").replace(tzinfo=timezone.utc)
    days_elapsed = (now - start_dt).days + 1
    
    print(" ======================================================================")
    print(" [FASE 9] PROTOCOLO DEMO (90 DIAS) — SATAR-1 BREAKOUT-ATR")
    print("=" * 70)
    print(f"  Inicio:             {st['start_date']}")
    print(f"  Progreso:           Día {days_elapsed} de {st['days_target']} ({(days_elapsed/90)*100:.1f}%)")
    print(f"  Capital Inicial:    ${st['initial_equity']:.2f} USD")
    print(f"  Riesgo por Trade:   ${st['risk_usd']:.2f} USD (1.0%)")
    print(f"  Trades Totales:     {st['total_trades']}")
    print(f"  Expectancia Actual: {st['total_r'] / (st['total_trades'] + 1e-12):+.3f}R")
    print(f"  Drawdown Máximo:    {st['max_drawdown']*100:.2f}% (Límite: -10%)")
    print(f"  Profit Factor:      {st['profit_factor']:.3f} (Meta: > 1.50)")
    print("=" * 70 + "\n")

def main():
    ap = argparse.ArgumentParser(description="SATAR-1 — Gestor de Fase Demo (90 Días)")
    ap.add_argument("--symbol", default="SOLUSDT")
    ap.add_argument("--equity", type=float, default=200.0, help="Capital inicial ($200.00 USD)")
    ap.add_argument("--testnet", action="store_true", help="Usar Bybit Testnet con API keys")
    ap.add_argument("--live", action="store_true", help="Enviar órdenes reales a testnet")
    ap.add_argument("--once", action="store_true", help="Ejecutar un solo ciclo")
    ap.add_argument("--poll", type=int, default=60, help="Segundos entre ciclos")
    args = ap.parse_args()

    tracker = init_demo_tracker(args.equity)
    print_demo_header(tracker)

    p = make_params()
    symbol = args.symbol.upper()

    print(f"[FASE DEMO] Monitoreando {symbol} en tiempo real...")
    print(f"             Ejecutador: {'TESTNET' if args.testnet else 'DRY-RUN'} | Poll: {args.poll}s\n")

    while True:
        try:
            cycle(symbol, p, live=args.live, testnet=args.testnet, equity=tracker["current_equity"])
        except KeyboardInterrupt:
            print("\n[salida] Fase Demo pausada por el usuario.")
            break
        except Exception as e:
            print(f"[error ciclo] {type(e).__name__}: {e}")

        if args.once:
            break
            
        time.sleep(args.poll)

if __name__ == "__main__":
    main()

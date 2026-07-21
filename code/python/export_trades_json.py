# -*- coding: utf-8 -*-
"""
Exporta la lista de trades históricos auditados para SOLUSDT, ETHUSDT y BTCUSDT
a un archivo JSON liviano (historical_trades_summary.json) para la UI del Dashboard.
"""
import json, os
import pandas as pd
from test_bb_squeeze import AdvancedBreakoutEngine, AdvancedBreakoutParams

symbols = ['ETHUSDT', 'BTCUSDT', 'SOLUSDT']
out = {}

for sym in symbols:
    csv_file = f"{sym.lower()}_m5.csv"
    if not os.path.exists(csv_file):
        continue
    df = pd.read_csv(csv_file, parse_dates=['timestamp'], index_col='timestamp')
    if df.index.tz is None: df.index = df.index.tz_localize('UTC')
    
    p = AdvancedBreakoutParams()
    p.use_bb_d1 = True
    p.bb_d1_expansion = True
    p.bb_d1_min_percentile = 0.20
    
    eng = AdvancedBreakoutEngine(df, p, symbol=sym)
    res = eng.run()
    
    t_list = []
    for idx, t in enumerate(eng.trades):
        t_list.append({
            'id': idx + 1,
            'symbol': sym,
            'direction': 'LONG' if t.direction > 0 else 'SHORT',
            'entry_time': pd.to_datetime(t.t_entry, unit='s', utc=True).strftime('%Y-%m-%d %H:%M'),
            'exit_time': pd.to_datetime(t.t_exit, unit='s', utc=True).strftime('%Y-%m-%d %H:%M') if t.t_exit else '-',
            'entry_price': round(t.entry, 2),
            'exit_price': round(t.exit, 2) if t.exit else 0.0,
            'sl_init': round(t.sl_init, 2),
            'tp': round(t.tp, 2),
            'qty': round(t.qty, 4),
            'pnl': round(t.pnl, 2),
            'r_multiple': round(t.r, 2),
            'reason': t.reason or 'open'
        })
    out[sym] = t_list
    print(f"OK: {sym} -> {len(t_list)} trades exportados")

with open('historical_trades_summary.json', 'w') as f:
    json.dump(out, f, indent=2)

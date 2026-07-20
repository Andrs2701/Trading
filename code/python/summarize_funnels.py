# -*- coding: utf-8 -*-
"""Resumen compacto de los 5 funnels + win-rate de equilibrio por activo."""
import json, os

symbols = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "XRPUSDT", "BNBUSDT"]
print(f"{'Activo':<9} {'entered':>7} {'WR':>6} {'avgWin_R':>9} {'avgLoss_R':>10} {'BE_WR':>7} {'margen':>8}")
print("-" * 62)
rows = []
for sym in symbols:
    fn = f"results/funnel_{sym}.json"
    if not os.path.exists(fn):
        print(f"{sym:<9} (no encontrado)")
        continue
    d = json.load(open(fn, encoding="utf-8"))
    ex = d["exits"]
    n_tp = ex["tp"]["count"]; n_stop = ex["stop"]["count"]; n_eod = ex["eod"]["count"]
    n = n_tp + n_stop + n_eod
    wr = n_tp / n if n else 0
    avg_win = ex["tp"]["avg_r"] if n_tp else 0
    avg_loss = abs(ex["stop"]["avg_r"]) if n_stop else 0
    # Break-even WR = avg_loss / (avg_win + avg_loss)
    be_wr = avg_loss / (avg_win + avg_loss) if (avg_win + avg_loss) > 0 else 0
    margen = wr - be_wr
    print(f"{sym:<9} {n:>7} {wr:>6.1%} {avg_win:>9.2f} {avg_loss:>10.2f} {be_wr:>7.1%} {margen:>+8.1%}")
    rows.append((sym, d["counters"]))

print()
print("=== EMBUDO MODULO G (diario) — atricion de senales ===")
print(f"{'Activo':<9} {'g_eval':>7} {'g1_ADX':>7} {'g2_zona':>8} {'g3_lleg':>8} {'g4_desac':>9} {'g5_patr':>8} {'dobleT':>7}")
for sym, c in rows:
    print(f"{sym:<9} {c['g_eval']:>7} {c['g1_pass']:>7} {c['g2_touch']:>8} {c['g3_arrive']:>8} {c['g4_decel']:>9} {c['g5_pattern']:>8} {c['g5_pattern_double_top']:>7}")

print()
print("=== EMBUDO MODULO I (horario) + gatillo ===")
print(f"{'Activo':<9} {'i1_ema':>7} {'i2_BOS':>7} {'i3_swing':>8} {'trigger':>8} {'rej_stop':>9} {'entered':>8}")
for sym, c in rows:
    print(f"{sym:<9} {c['i1_ema']:>7} {c['i2_bos']:>7} {c['i3_swings']:>8} {c['trigger_fired']:>8} {c['reject_stop_dist']:>9} {c['entered']:>8}")

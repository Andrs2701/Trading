# -*- coding: utf-8 -*-
import os
import subprocess
import shutil

symbols = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "XRPUSDT", "BNBUSDT"]
os.makedirs("results", exist_ok=True)

for sym in symbols:
    csv_file = f"{sym.lower()}_m5.csv"
    if not os.path.exists(csv_file):
        print(f"File {csv_file} not found, skipping.")
        continue
        
    print(f"\n================ Running backtests for {sym} ================")
    
    # 1. Run Base
    print(f"[{sym}] Running BASE backtest...")
    subprocess.run(["python", "satar_backtest.py", "--csv", csv_file, "--trail", "I"], check=True)
    if os.path.exists("trades_out.csv"):
        shutil.move("trades_out.csv", f"results/trades_{sym.lower()}_base.csv")
        print(f"[{sym}] Saved base trades to results/trades_{sym.lower()}_base.csv")
        
    # 2. Run HMM
    print(f"[{sym}] Running HMM backtest...")
    subprocess.run(["python", "satar_backtest.py", "--csv", csv_file, "--trail", "I", "--hmm"], check=True)
    if os.path.exists("trades_out.csv"):
        shutil.move("trades_out.csv", f"results/trades_{sym.lower()}_hmm.csv")
        print(f"[{sym}] Saved HMM trades to results/trades_{sym.lower()}_hmm.csv")
        
    # 3. Run Funnel (writes results/funnel_{SYMBOL}.json automatically)
    print(f"[{sym}] Running FUNNEL backtest...")
    subprocess.run(["python", "satar_backtest.py", "--csv", csv_file, "--trail", "I", "--funnel"], check=True)
    
print("\nAll batch backtests completed successfully!")

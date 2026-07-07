# -*- coding: utf-8 -*-
"""
SATAR-1 — Ejecutor live/demo del Pilar C sobre Bybit v5 (FASE-7).

Arquitectura (decisión FASE-8): ejecutor NATIVO en Python. No depende de alertas
de TradingView: recalcula la máquina de estados de FASE-2 sobre una ventana
rodante de klines M5 y detecta si la ÚLTIMA vela cerrada disparó una señal.
El HMM (Pilar B) puede activarse igual que en backtest (--hmm).

SEGURIDAD (FASE-6 §6):
  · Por defecto DRY-RUN: imprime órdenes, no envía nada.
  · --live exige BYBIT_API_KEY / BYBIT_API_SECRET en variables de entorno.
  · Usar SIEMPRE subcuenta dedicada con API keys de solo-trading (sin retiros).
  · SL y TP viajan EN la orden (server-side), nunca solo en memoria del bot.
  · Empezar en testnet (--testnet) y pasar por la FASE-9 (demo 90 días) antes
    de considerar dinero real. Este script NO es una recomendación de inversión.

Uso:
  python satar_live.py --symbol BTCUSDT                (dry-run, mainnet data)
  python satar_live.py --symbol BTCUSDT --testnet --live   (órdenes a testnet)
"""
from __future__ import annotations
import argparse, hashlib, hmac, json, os, time, urllib.request, urllib.parse
import pandas as pd

from satar_backtest import Engine, Params, make_hmm_mult, resample

STATE_FILE = "satar_live_state.json"
WINDOW_DAYS = 120          # historia mínima para indicadores D1 (ADX/ER/zonas)
POLL_SECONDS = 60          # ciclo de sondeo (la señal solo cambia al cierre M5)


# ----------------------------- API Bybit v5 ---------------------------------
def base_url(testnet: bool) -> str:
    return "https://api-testnet.bybit.com" if testnet else "https://api.bybit.com"

def http_get(url: str) -> dict:
    req = urllib.request.Request(url, headers={"User-Agent": "SATAR-1"})
    with urllib.request.urlopen(req, timeout=15) as r:
        return json.loads(r.read().decode())

def signed_post(path: str, body: dict, testnet: bool) -> dict:
    key = os.environ.get("BYBIT_API_KEY", "")
    sec = os.environ.get("BYBIT_API_SECRET", "")
    if not key or not sec:
        raise RuntimeError("Faltan BYBIT_API_KEY / BYBIT_API_SECRET en el entorno")
    ts = str(int(time.time() * 1000))
    recv = "5000"
    payload = json.dumps(body)
    sign = hmac.new(sec.encode(), (ts + key + recv + payload).encode(), hashlib.sha256).hexdigest()
    req = urllib.request.Request(
        base_url(testnet) + path, data=payload.encode(), method="POST",
        headers={"X-BAPI-API-KEY": key, "X-BAPI-TIMESTAMP": ts, "X-BAPI-RECV-WINDOW": recv,
                 "X-BAPI-SIGN": sign, "Content-Type": "application/json", "User-Agent": "SATAR-1"})
    with urllib.request.urlopen(req, timeout=15) as r:
        return json.loads(r.read().decode())

def fetch_klines_m5(symbol: str, days: int, testnet: bool) -> pd.DataFrame:
    end = int(time.time() * 1000)
    start = end - days * 86_400_000
    rows, cur = [], end
    while cur > start:
        q = urllib.parse.urlencode({"category": "linear", "symbol": symbol,
                                    "interval": "5", "limit": 1000, "end": cur})
        res = http_get(f"{base_url(testnet)}/v5/market/kline?{q}")
        if res.get("retCode") != 0:
            if "Rate" in str(res.get("retMsg", "")):
                time.sleep(10); continue
            raise RuntimeError(res.get("retMsg"))
        kl = res["result"]["list"]
        if not kl:
            break
        rows.extend(kl)
        oldest = int(kl[-1][0])
        if oldest >= cur:
            break
        cur = oldest - 1
        time.sleep(0.25)
    df = pd.DataFrame(rows, columns=["timestamp", "open", "high", "low", "close", "volume", "turnover"])
    df["timestamp"] = pd.to_datetime(df["timestamp"].astype(float), unit="ms", utc=True)
    df = (df.astype({c: float for c in ["open", "high", "low", "close", "volume"]})
            .sort_values("timestamp").drop_duplicates("timestamp").set_index("timestamp")
            [["open", "high", "low", "close", "volume"]])
    # descartar la vela M5 EN CURSO (solo velas cerradas — FASE-2 regla de oro)
    last_closed = pd.Timestamp.utcnow().floor("5min") - pd.Timedelta(minutes=5)
    return df[df.index <= last_closed]


# ----------------------------- Estado local ---------------------------------
def load_state() -> dict:
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE) as f:
            return json.load(f)
    return {"position": None, "last_signal_ts": None}

def save_state(st: dict):
    with open(STATE_FILE, "w") as f:
        json.dump(st, f, indent=2)


# ----------------------------- Órdenes ---------------------------------------
def place_order(symbol, side, qty, sl, tp, live, testnet):
    body = {"category": "linear", "symbol": symbol, "side": side, "orderType": "Market",
            "qty": f"{qty:.6f}", "stopLoss": f"{sl:.2f}", "takeProfit": f"{tp:.2f}",
            "slTriggerBy": "LastPrice", "tpTriggerBy": "LastPrice", "timeInForce": "IOC"}
    if not live:
        print(f"[DRY-RUN] ORDEN: {json.dumps(body)}")
        return {"dryRun": True}
    res = signed_post("/v5/order/create", body, testnet)
    print(f"[LIVE] respuesta: {res.get('retCode')} {res.get('retMsg')}")
    return res

def amend_stop(symbol, new_sl, live, testnet):
    body = {"category": "linear", "symbol": symbol, "stopLoss": f"{new_sl:.2f}",
            "slTriggerBy": "LastPrice", "positionIdx": 0}
    if not live:
        print(f"[DRY-RUN] TRAILING: stopLoss -> {new_sl:.2f}")
        return {"dryRun": True}
    res = signed_post("/v5/position/trading-stop", body, testnet)
    print(f"[LIVE] trailing: {res.get('retCode')} {res.get('retMsg')}")
    return res


# ----------------------------- Ciclo principal -------------------------------
def cycle(symbol: str, p: Params, use_hmm: bool, live: bool, testnet: bool, equity: float):
    df = fetch_klines_m5(symbol, WINDOW_DAYS, testnet)
    if len(df) < 5000:
        print(f"[aviso] historia insuficiente ({len(df)} velas)"); return
    hmm = make_hmm_mult(resample(df, "1D")) if use_hmm else None
    eng = Engine(df, p, symbol=symbol, equity0=equity, hmm_mult=hmm)
    eng.run()
    st = load_state()
    last_ts = int(df.index[-1].timestamp())

    # 1) ¿Señal fresca? El motor entra en la apertura de la vela SIGUIENTE a la del
    #    gatillo ⇒ una posición del motor con t_entry == última vela cerrada + 5min
    #    equivale a "ejecutar ahora a mercado".
    if eng.pos is not None and eng.pos.t_entry >= last_ts and st["position"] is None:
        pos = eng.pos
        side = "Sell" if pos.direction < 0 else "Buy"
        print(f"[SEÑAL] {symbol} {side} qty={pos.qty:.6f} SL={pos.sl0:.2f} TP={pos.tp:.2f}")
        if st.get("last_signal_ts") != last_ts:                      # anti-duplicado
            place_order(symbol, side, pos.qty, pos.sl0, pos.tp, live, testnet)
            st["position"] = {"dir": pos.direction, "sl": pos.sl0, "tp": pos.tp,
                              "entry_ts": last_ts}
            st["last_signal_ts"] = last_ts
            save_state(st)
        return

    # 2) Trailing de posición viva (D-6): recalcular stop con la EMA50/ATR H1
    if st["position"] is not None:
        h1 = resample(df, "1h")
        from satar_backtest import ema as _ema, atr as _atr
        c = h1["close"].to_numpy(float)
        e50 = _ema(c, p.ema_n)[-1]
        a14 = _atr(h1["high"].to_numpy(float), h1["low"].to_numpy(float), c, p.atr_n)[-1]
        d = st["position"]["dir"]
        cand = e50 + (p.buf_atr * a14 if d < 0 else -p.buf_atr * a14)
        new_sl = min(st["position"]["sl"], cand) if d < 0 else max(st["position"]["sl"], cand)
        if abs(new_sl - st["position"]["sl"]) > 1e-9:
            amend_stop(symbol, new_sl, live, testnet)
            st["position"]["sl"] = new_sl
            save_state(st)
        print(f"[gestión] dir={d} sl={st['position']['sl']:.2f} (EMA50 H1={e50:.2f})")
        # Nota: el cierre por SL/TP lo ejecuta el exchange (server-side). La
        # reconciliación con /v5/position/list marca position=None al cerrarse.
    else:
        print(f"[{pd.Timestamp.utcnow():%H:%M}] sin señal — estado motor: {eng.state}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--symbol", default="BTCUSDT")
    ap.add_argument("--equity", type=float, default=10_000.0)
    ap.add_argument("--hmm", action="store_true")
    ap.add_argument("--live", action="store_true", help="enviar órdenes reales (default: dry-run)")
    ap.add_argument("--testnet", action="store_true")
    ap.add_argument("--once", action="store_true", help="un solo ciclo (para cron/pruebas)")
    a = ap.parse_args()
    if a.live and not a.testnet:
        print("ADVERTENCIA: --live en mainnet. El protocolo FASE-9 exige 90 días de demo antes.")
    p = Params()
    while True:
        try:
            cycle(a.symbol, p, a.hmm, a.live, a.testnet, a.equity)
        except Exception as e:
            print(f"[error] {e}")
        if a.once:
            break
        time.sleep(POLL_SECONDS)


if __name__ == "__main__":
    main()

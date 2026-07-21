# -*- coding: utf-8 -*-
"""
BREAKOUT-ATR — Ejecutor live/demo sobre Bybit v5.

Arquitectura: ejecutor NATIVO en Python. Recalcula el BreakoutEngine sobre una
ventana rodante de klines M5 y detecta si la ÚLTIMA vela H1 cerrada disparó
una señal de ruptura. Usa la configuración congelada del WFO (Fase B4).

SEGURIDAD (heredada de FASE-6 §6):
  · Por defecto DRY-RUN: imprime órdenes, no envía nada.
  · --live exige BYBIT_API_KEY / BYBIT_API_SECRET en variables de entorno.
  · Usar SIEMPRE subcuenta dedicada con API keys de solo-trading (sin retiros).
  · SL y TP viajan EN la orden (server-side), nunca solo en memoria del bot.
  · Empezar en testnet (--testnet) y completar demo antes de dinero real.
  · Este script NO es una recomendación de inversión.

Uso:
  python breakout_live.py --symbol SOLUSDT --once              (dry-run, un ciclo)
  python breakout_live.py --symbol SOLUSDT                     (dry-run, loop)
  python breakout_live.py --symbol SOLUSDT --testnet --live    (órdenes a testnet)

Configuración congelada WFO (results/wfo_results_breakout.json):
  vol_spike_mult=1.8, range_expansion_mult=1.4, stop_atr_mult=1.8
"""
from __future__ import annotations
import argparse, hashlib, hmac, json, math, os, sys, time
import urllib.request, urllib.parse
from datetime import datetime, timezone
import numpy as np
import pandas as pd

from breakout_backtest import BreakoutEngine, BreakoutParams
from satar_backtest import _sec, resample, ema, atr

# ─────────────────────────── Configuración ───────────────────────────────────
STATE_FILE = "breakout_live_state.json"
WINDOW_DAYS = 150          # historia para indicadores D1 (Hurst 100d) + calentamiento
POLL_SECONDS = 60          # ciclo de sondeo (señal cambia al cierre de vela H1)
DEMO_TRACKER_FILE = "demo_phase_tracker.json"          # FASE-9: registro demo 90 días
MAINNET_APPROVAL_FILE = "APROBADO_PARA_MAINNET.txt"    # candado a mainnet (ver assert_mainnet_allowed)

# Configuración congelada del WFO (Fase B4) — NO modificar sin re-validar
FROZEN_CONFIG = {
    "vol_spike_mult": 1.8,
    "range_expansion_mult": 1.4,
    "stop_atr_mult": 1.8,
}

# Activos en validación — el WFO de BREAKOUT-ATR dio NO RENTABLE OOS
# (mean_oos=-0.3447 <= 0, ver docs/BREAKOUT-resultados-veredicto.md). NINGÚN
# activo tiene un edge demostrado todavía. La demo de 90 días en testnet está
# en curso para confirmar o descartar el edge antes de considerar mainnet.
APPROVED_SYMBOLS = ["SOLUSDT", "ETHUSDT"]


# ─────────────────────────── Candado a mainnet ────────────────────────────────
def mainnet_trading_allowed() -> bool:
    """¿Hay aprobación EXPLÍCITA para operar en mainnet (dinero real)?

    Se aprueba con un archivo APROBADO_PARA_MAINNET.txt en el repo (junto a
    este script o en el cwd) o con la variable de entorno
    MAINNET_APPROVED=true. Ninguna de las dos existe hoy, así que por
    defecto esta función devuelve False y mainnet queda bloqueado.
    """
    candidates = [
        MAINNET_APPROVAL_FILE,
        os.path.join(os.path.dirname(os.path.abspath(__file__)), MAINNET_APPROVAL_FILE),
    ]
    if any(os.path.exists(c) for c in candidates):
        return True
    return os.environ.get("MAINNET_APPROVED", "").strip().lower() == "true"


def assert_mainnet_allowed(live: bool, testnet: bool):
    """Capa de seguridad ADICIONAL a la exigencia de BYBIT_API_KEY/SECRET:
    esa protección depende de si el usuario puso las keys; esta no depende
    de eso — bloquea igual aunque las keys ya estén configuradas.

    Aborta (RuntimeError) si se intenta enviar órdenes reales en mainnet
    (--live sin --testnet) sin aprobación explícita. Se llama desde main(),
    cycle() y place_order() para cubrir tanto el uso por CLI como el hilo de
    fondo de dashboard_server.py (que llama cycle()/place_order() sin pasar
    por main()).
    """
    if live and not testnet and not mainnet_trading_allowed():
        raise RuntimeError(
            "Bloqueado: el WFO de BREAKOUT-ATR dio NO RENTABLE OOS "
            "(mean_oos=-0.3447). No se opera en mainnet sin aprobación "
            "explícita tras completar la demo de 90 días. Cree el archivo "
            f"'{MAINNET_APPROVAL_FILE}' en el repo o defina la variable de "
            "entorno MAINNET_APPROVED=true para autorizarlo."
        )


# ─────────────────────────── API Bybit v5 ────────────────────────────────────
def base_url(testnet: bool) -> str:
    return "https://api-testnet.bybit.com" if testnet else "https://api.bybit.com"


def http_get(url: str) -> dict:
    req = urllib.request.Request(url, headers={"User-Agent": "BREAKOUT-ATR/1.0"})
    with urllib.request.urlopen(req, timeout=15) as r:
        return json.loads(r.read().decode())


def signed_get(path: str, params: dict, testnet: bool) -> dict:
    """GET autenticado a un endpoint PRIVADO de Bybit v5 (misma firma HMAC que
    signed_post, pero sobre el query string en vez del body JSON). Necesario
    porque /v5/position/list y /v5/position/closed-pnl requieren autenticación
    — un GET sin firmar a esas rutas falla con error de auth."""
    key = os.environ.get("BYBIT_API_KEY", "")
    sec = os.environ.get("BYBIT_API_SECRET", "")
    if not key or not sec:
        raise RuntimeError("Faltan BYBIT_API_KEY / BYBIT_API_SECRET en el entorno")
    ts = str(int(time.time() * 1000))
    recv = "5000"
    qs = urllib.parse.urlencode(params)
    sign = hmac.new(
        sec.encode(), (ts + key + recv + qs).encode(), hashlib.sha256
    ).hexdigest()
    req = urllib.request.Request(
        f"{base_url(testnet)}{path}?{qs}",
        headers={
            "X-BAPI-API-KEY": key,
            "X-BAPI-TIMESTAMP": ts,
            "X-BAPI-RECV-WINDOW": recv,
            "X-BAPI-SIGN": sign,
            "User-Agent": "BREAKOUT-ATR/1.0",
        },
    )
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
    sign = hmac.new(
        sec.encode(), (ts + key + recv + payload).encode(), hashlib.sha256
    ).hexdigest()
    req = urllib.request.Request(
        base_url(testnet) + path,
        data=payload.encode(),
        method="POST",
        headers={
            "X-BAPI-API-KEY": key,
            "X-BAPI-TIMESTAMP": ts,
            "X-BAPI-RECV-WINDOW": recv,
            "X-BAPI-SIGN": sign,
            "Content-Type": "application/json",
            "User-Agent": "BREAKOUT-ATR/1.0",
        },
    )
    with urllib.request.urlopen(req, timeout=15) as r:
        return json.loads(r.read().decode())


def fetch_klines_m5(symbol: str, days: int, testnet: bool) -> pd.DataFrame:
    """Descarga velas M5 cerradas de Bybit v5 (paginado)."""
    end = int(time.time() * 1000)
    start = end - days * 86_400_000
    rows, cur = [], end
    retries = 0
    while cur > start:
        q = urllib.parse.urlencode({
            "category": "linear", "symbol": symbol,
            "interval": "5", "limit": 1000, "end": cur,
        })
        try:
            res = http_get(f"{base_url(testnet)}/v5/market/kline?{q}")
        except Exception as e:
            retries += 1
            if retries > 10:
                raise RuntimeError(f"Demasiados reintentos descargando klines: {e}")
            print(f"  [red] {e}, reintento {retries}/10...")
            time.sleep(5 * retries)
            continue
        if res.get("retCode") != 0:
            msg = res.get("retMsg", "")
            if "Rate" in msg or "rate" in msg:
                print(f"  [rate-limit] esperando 10s...")
                time.sleep(10)
                continue
            raise RuntimeError(f"API error: {res.get('retCode')} {msg}")
        kl = res["result"]["list"]
        if not kl:
            break
        rows.extend(kl)
        oldest = int(kl[-1][0])
        if oldest >= cur:
            break
        cur = oldest - 1
        time.sleep(0.25)

    if not rows:
        raise RuntimeError(f"Sin datos para {symbol}")

    df = pd.DataFrame(
        rows,
        columns=["timestamp", "open", "high", "low", "close", "volume", "turnover"],
    )
    df["timestamp"] = pd.to_datetime(df["timestamp"].astype(float), unit="ms", utc=True)
    df = (
        df.astype({c: float for c in ["open", "high", "low", "close", "volume"]})
        .sort_values("timestamp")
        .drop_duplicates("timestamp")
        .set_index("timestamp")[["open", "high", "low", "close", "volume"]]
    )
    # Descartar la vela M5 EN CURSO (solo velas cerradas)
    last_closed = pd.Timestamp.now(tz="UTC").floor("5min") - pd.Timedelta(minutes=5)
    return df[df.index <= last_closed]


# ─────────────────────────── Estado local ────────────────────────────────────
def load_state(symbol: str) -> dict:
    fname = f"breakout_live_state_{symbol}.json"
    if os.path.exists(fname):
        with open(fname) as f:
            return json.load(f)
    return {"position": None, "last_signal_ts": None, "symbol": symbol}


def save_state(st: dict):
    fname = f"breakout_live_state_{st['symbol']}.json"
    with open(fname, "w") as f:
        json.dump(st, f, indent=2)


# ─────────────────────────── Órdenes ─────────────────────────────────────────
def place_order(symbol: str, side: str, qty: float, sl: float, tp: float,
                live: bool, testnet: bool) -> dict:
    # Candado a mainnet: capa adicional independiente de si hay API keys.
    assert_mainnet_allowed(live, testnet)
    # Redondear qty y precios según el activo
    qty_str = f"{qty:.4f}" if "SOL" in symbol else f"{qty:.6f}"
    body = {
        "category": "linear",
        "symbol": symbol,
        "side": side,
        "orderType": "Market",
        "qty": qty_str,
        "stopLoss": f"{sl:.2f}",
        "takeProfit": f"{tp:.2f}",
        "slTriggerBy": "LastPrice",
        "tpTriggerBy": "LastPrice",
        "timeInForce": "IOC",
    }
    if not live:
        print(f"  [DRY-RUN] ORDEN: {json.dumps(body, indent=2)}")
        return {"dryRun": True}
    res = signed_post("/v5/order/create", body, testnet)
    code = res.get("retCode")
    msg = res.get("retMsg", "")
    print(f"  [LIVE] Orden enviada: retCode={code} msg={msg}")
    if code != 0:
        print(f"  [ERROR] La orden falló: {res}")
    return res


def amend_stop(symbol: str, new_sl: float, live: bool, testnet: bool) -> dict:
    body = {
        "category": "linear",
        "symbol": symbol,
        "stopLoss": f"{new_sl:.2f}",
        "slTriggerBy": "LastPrice",
        "positionIdx": 0,
    }
    if not live:
        print(f"  [DRY-RUN] TRAILING: stopLoss -> {new_sl:.2f}")
        return {"dryRun": True}
    res = signed_post("/v5/position/trading-stop", body, testnet)
    print(f"  [LIVE] Trailing: retCode={res.get('retCode')} msg={res.get('retMsg')}")
    return res


def check_position_closed(symbol: str, live: bool, testnet: bool) -> bool:
    """Consulta si la posición sigue abierta en el exchange.

    /v5/position/list es un endpoint PRIVADO — requiere GET firmado (antes
    usaba http_get sin firmar, que Bybit rechaza por auth; ese error caía en
    el `except` y a su vez el código pre-existente devolvía True bajo error,
    o sea "cerrada", en la rama de éxito con retCode!=0 también caía en
    `return True` por defecto). Ambos casos son peligrosos: un fallo de red/
    auth reportaría "cerrada" y el bot borraría el estado local, arriesgando
    abrir una posición DUPLICADA mientras la original sigue viva. Por eso
    aquí el fallo es fail-safe: ante cualquier error se asume que la
    posición SIGUE abierta (False) y no se toca el estado local.
    """
    if not live:
        return False  # En dry-run no podemos consultar
    try:
        res = signed_get(
            "/v5/position/list",
            {"category": "linear", "symbol": symbol, "settleCoin": "USDT"},
            testnet,
        )
        if res.get("retCode") == 0:
            positions = res["result"].get("list", [])
            for pos in positions:
                if pos["symbol"] == symbol and float(pos.get("size", 0)) > 0:
                    return False  # Posición aún abierta
            return True  # Lista vacía / size=0 -> cerrada
        print(f"  [aviso] position/list retCode={res.get('retCode')} {res.get('retMsg')}")
        return False  # Fail-safe: error de API -> asumir que sigue abierta
    except Exception as e:
        print(f"  [aviso] No se pudo consultar posición: {e}")
        return False  # Fail-safe: no se pudo confirmar -> asumir que sigue abierta


def fetch_closed_pnl(symbol: str, testnet: bool) -> dict | None:
    """Consulta en Bybit el último registro de PnL realizado (closed-pnl) para
    el símbolo. Se usa para registrar en demo_phase_tracker.json el resultado
    REAL (pnl en USD) de una operación que el exchange cerró por SL/TP
    server-side, sin que el bot enviara él mismo la orden de cierre."""
    try:
        res = signed_get(
            "/v5/position/closed-pnl",
            {"category": "linear", "symbol": symbol, "limit": 1},
            testnet,
        )
        if res.get("retCode") == 0:
            lst = res["result"].get("list", [])
            if lst:
                return lst[0]
        else:
            print(f"  [aviso] closed-pnl retCode={res.get('retCode')} {res.get('retMsg')}")
    except Exception as e:
        print(f"  [aviso] No se pudo consultar closed-pnl: {e}")
    return None


# ─────────────────────────── Demo Fase-9 (90 días) ────────────────────────────
def load_demo_tracker() -> dict | None:
    if os.path.exists(DEMO_TRACKER_FILE):
        try:
            with open(DEMO_TRACKER_FILE) as f:
                return json.load(f)
        except Exception as e:
            print(f"  [aviso] No se pudo leer {DEMO_TRACKER_FILE}: {e}")
    return None


def save_demo_tracker(tr: dict):
    with open(DEMO_TRACKER_FILE, "w") as f:
        json.dump(tr, f, indent=2)


def register_demo_trade(symbol: str, pos_info: dict, testnet: bool):
    """Registra en demo_phase_tracker.json (FASE-9, demo de 90 días) el
    resultado de una operación que el exchange acaba de cerrar.

    Solo se llama desde la rama `live=True` de cycle(): en dry-run puro no
    hay ninguna orden real en Bybit (ni siquiera en testnet) que pueda
    cerrarse, así que no hay nada que contar. Con BYBIT_TESTNET=true SÍ
    cuenta: ahí el bot manda órdenes reales al testnet de Bybit (ejecución
    real, dinero ficticio), que es exactamente lo que la demo de 90 días
    de FASE-9 debe auditar.

    Fuente del PnL: endpoint /v5/position/closed-pnl de Bybit (dato real de
    la operación). Si esa consulta falla (red, límites de API, timing),
    se usa como respaldo una estimación con el SL vigente guardado en el
    estado local (el trailing stop ya mantiene ese valor sincronizado con
    el SL real en el exchange) para no perder el conteo de la operación,
    aunque el monto quede aproximado — se marca igual en el log cuál fuente
    se usó.

    profit_factor requiere las sumas de ganancias y pérdidas por separado,
    que el esquema original del tracker no guarda (solo total_pnl neto). Se
    añaden dos campos auxiliares (_gross_win_usd/_gross_loss_usd) para poder
    recalcularlo de forma incremental entre reinicios, sin tocar ni
    renombrar ninguno de los campos que ya existían en el archivo.
    """
    tr = load_demo_tracker()
    if tr is None:
        print(f"  [aviso] {DEMO_TRACKER_FILE} no existe — no se registra el trade demo")
        return

    entry = float(pos_info.get("entry", 0.0) or 0.0)
    sl = float(pos_info.get("sl", 0.0) or 0.0)
    qty = float(pos_info.get("qty", 0.0) or 0.0)
    d = pos_info.get("dir", 1)

    closed = fetch_closed_pnl(symbol, testnet)
    if closed is not None:
        pnl = float(closed.get("closedPnl", 0.0) or 0.0)
        source = "bybit_closed_pnl"
    else:
        pnl = (sl - entry) * qty * d  # estimación: SL vigente como precio de salida
        source = "estimado_sl_local"
        print("  [aviso] Sin dato closed-pnl de Bybit — estimando resultado con el SL local")

    # R = pnl / dólares realmente en riesgo en ESTA operación (distancia al SL
    # inicial * qty ejecutada) — no el % nominal, para reflejar el riesgo real
    # tras redondeos de qty / tope de apalancamiento.
    risk_usd_trade = abs(entry - sl) * qty
    if risk_usd_trade <= 1e-9:
        risk_usd_trade = tr.get("risk_usd") or 1.0  # evita división por cero
    r_multiple = pnl / risk_usd_trade

    tr["total_trades"] = tr.get("total_trades", 0) + 1
    tr.setdefault("_gross_win_usd", 0.0)
    tr.setdefault("_gross_loss_usd", 0.0)
    if pnl > 0:
        tr["winning_trades"] = tr.get("winning_trades", 0) + 1
        tr["_gross_win_usd"] = round(tr["_gross_win_usd"] + pnl, 4)
    else:
        tr["losing_trades"] = tr.get("losing_trades", 0) + 1
        tr["_gross_loss_usd"] = round(tr["_gross_loss_usd"] + abs(pnl), 4)

    tr["total_pnl"] = round(tr.get("total_pnl", 0.0) + pnl, 4)
    tr["total_r"] = round(tr.get("total_r", 0.0) + r_multiple, 4)
    tr["current_equity"] = round(tr.get("current_equity", tr.get("initial_equity", 0.0)) + pnl, 4)
    tr["peak_equity"] = round(max(tr.get("peak_equity", tr["current_equity"]), tr["current_equity"]), 4)
    if tr["peak_equity"] > 0:
        dd = (tr["current_equity"] - tr["peak_equity"]) / tr["peak_equity"]
        tr["max_drawdown"] = round(min(tr.get("max_drawdown", 0.0), dd), 4)
    tr["profit_factor"] = (
        round(tr["_gross_win_usd"] / tr["_gross_loss_usd"], 4)
        if tr["_gross_loss_usd"] > 1e-9 else (999.0 if tr["_gross_win_usd"] > 0 else 0.0)
    )

    save_demo_tracker(tr)
    print(f"  [demo] Trade #{tr['total_trades']} registrado ({source}): "
          f"pnl={pnl:+.2f} USD ({r_multiple:+.2f}R) | equity={tr['current_equity']:.2f} | "
          f"PF={tr['profit_factor']:.2f}")


# ─────────────────────────── Ciclo principal ─────────────────────────────────
def cycle(symbol: str, p: BreakoutParams, live: bool, testnet: bool, equity: float):
    """Un ciclo del ejecutor: descarga datos, corre el motor, detecta señal."""
    # Candado a mainnet: se revisa en CADA ciclo (no solo en main()) porque
    # dashboard_server.py llama cycle() directo desde su hilo de fondo, sin
    # pasar por main() ni por sus validaciones de arranque.
    assert_mainnet_allowed(live, testnet)
    now = datetime.now(timezone.utc)
    print(f"\n{'='*60}")
    print(f"[{now:%Y-%m-%d %H:%M:%S UTC}] Ciclo {symbol}")
    print(f"{'='*60}")

    # 1) Descargar datos M5
    print(f"  Descargando {WINDOW_DAYS} días de klines M5...")
    df = fetch_klines_m5(symbol, WINDOW_DAYS, testnet)
    if len(df) < 5000:
        print(f"  [aviso] Historia insuficiente ({len(df)} velas, necesita >=5000)")
        return
    print(f"  OK: {len(df)} velas M5 ({df.index[0]} -> {df.index[-1]})")

    # 2) Correr el motor de backtest sobre la ventana
    eng = BreakoutEngine(df, p, symbol=symbol, equity0=equity)
    result = eng.run()
    print(f"  Motor: {result.get('trades', 0)} trades en la ventana, "
          f"exp_R={result.get('expectancy_R', 'N/A')}")

    # 3) Cargar estado local
    st = load_state(symbol)

    # 4) Reconciliación: si tenemos posición local, verificar si el exchange la
    #    cerró (SL/TP server-side, sin que el bot enviara la orden de cierre).
    #    El bot nunca "cierra" una operación él mismo -- Bybit lo hace vía
    #    SL/TP adjuntos a la orden -- así que la única forma de detectar el
    #    cierre y su resultado es consultando el exchange aquí.
    if st["position"] is not None and live:
        if check_position_closed(symbol, live, testnet):
            print(f"  [reconciliación] Posición cerrada en exchange — registrando resultado")
            register_demo_trade(symbol, st["position"], testnet)
            st["position"] = None
            save_state(st)

    last_ts = int(df.index[-1].timestamp())

    # 5) ¿Señal fresca? El motor entra en la apertura de la vela SIGUIENTE al
    #    trigger H1 — una posición con t_entry >= última vela cerrada = "ejecutar ahora"
    if eng.pos is not None and eng.pos.t_entry >= last_ts and st["position"] is None:
        pos = eng.pos
        side = "Sell" if pos.direction < 0 else "Buy"
        print(f"\n  ╔══════════════════════════════════════════╗")
        print(f"  ║  🚀 SEÑAL DETECTADA                      ║")
        print(f"  ╠══════════════════════════════════════════╣")
        print(f"  ║  {symbol} {side:4s}                          ║")
        print(f"  ║  Entry: {pos.entry:.2f}                      ║")
        print(f"  ║  Qty:   {pos.qty:.6f}                   ║")
        print(f"  ║  SL:    {pos.sl0:.2f}                      ║")
        print(f"  ║  TP:    {pos.tp:.2f}                      ║")
        print(f"  ╚══════════════════════════════════════════╝\n")

        # Anti-duplicado: no enviar la misma señal dos veces
        if st.get("last_signal_ts") != last_ts:
            place_order(symbol, side, pos.qty, pos.sl0, pos.tp, live, testnet)
            st["position"] = {
                "dir": pos.direction,
                "sl": pos.sl0,
                "tp": pos.tp,
                "entry": pos.entry,
                "entry_ts": last_ts,
                "side": side,
                "qty": pos.qty,  # necesario para estimar PnL/R al cerrar (ver register_demo_trade)
            }
            st["last_signal_ts"] = last_ts
            save_state(st)
        else:
            print(f"  [anti-dup] Señal ya procesada (ts={last_ts})")
        return

    # 6) Trailing de posición viva: recalcular EMA50 H1 + ATR buffer
    if st["position"] is not None:
        h1 = resample(df, "1h")
        c = h1["close"].to_numpy(float)
        h = h1["high"].to_numpy(float)
        l = h1["low"].to_numpy(float)
        e50 = ema(c, p.ema_trail_n)[-1]
        a14 = atr(h, l, c, p.atr_n)[-1]
        d = st["position"]["dir"]
        # Trailing: EMA50 ± buffer ATR
        cand = e50 + (p.trail_buf_atr * a14 if d < 0 else -p.trail_buf_atr * a14)
        old_sl = st["position"]["sl"]
        new_sl = min(old_sl, cand) if d < 0 else max(old_sl, cand)

        if abs(new_sl - old_sl) > 0.01:  # Solo actualizar si cambió significativamente
            print(f"  [trailing] SL: {old_sl:.2f} -> {new_sl:.2f} "
                  f"(EMA50={e50:.2f}, ATR={a14:.2f})")
            amend_stop(symbol, new_sl, live, testnet)
            st["position"]["sl"] = new_sl
            save_state(st)
        else:
            print(f"  [gestión] Posición {st['position']['side']} activa | "
                  f"SL={old_sl:.2f} | EMA50={e50:.2f}")


def make_params() -> BreakoutParams:
    """Crea parámetros con la configuración congelada del WFO."""
    risk = float(os.environ.get("TRADING_RISK_PCT", "0.02"))
    return BreakoutParams(
        vol_spike_mult=FROZEN_CONFIG["vol_spike_mult"],
        range_expansion_mult=FROZEN_CONFIG["range_expansion_mult"],
        stop_atr_mult=FROZEN_CONFIG["stop_atr_mult"],
        risk_pct=risk
    )


def main():
    ap = argparse.ArgumentParser(
        description="BREAKOUT-ATR Live Executor — Bybit v5",
        epilog="⚠️  Este script NO es asesoría financiera. Use bajo su responsabilidad."
    )
    ap.add_argument("--symbol", default="SOLUSDT",
                    help=f"Par a operar (aprobados: {', '.join(APPROVED_SYMBOLS)})")
    ap.add_argument("--equity", type=float, default=10_000.0,
                    help="Equity de referencia para position sizing")
    ap.add_argument("--live", action="store_true",
                    help="Enviar órdenes reales (default: dry-run)")
    ap.add_argument("--testnet", action="store_true",
                    help="Usar Bybit testnet")
    ap.add_argument("--once", action="store_true",
                    help="Un solo ciclo (para cron o pruebas)")
    ap.add_argument("--poll", type=int, default=POLL_SECONDS,
                    help=f"Segundos entre ciclos (default: {POLL_SECONDS})")
    a = ap.parse_args()

    # Validaciones de seguridad
    if a.symbol not in APPROVED_SYMBOLS:
        print(f"⚠️  {a.symbol} no está en los activos configurados ({APPROVED_SYMBOLS}).")
        print(f"   El WFO de BREAKOUT-ATR dio NO RENTABLE OOS: ningún activo tiene un")
        print(f"   edge demostrado todavía (ver docs/BREAKOUT-resultados-veredicto.md).")
        print(f"   Proceder bajo su riesgo.")
        resp = input("¿Continuar? [s/N]: ").strip().lower()
        if resp != "s":
            sys.exit(0)

    if a.live and not a.testnet:
        print("=" * 60)
        print("⚠️  ADVERTENCIA: --live en MAINNET (dinero real).")
        print("   El protocolo FASE-9 exige 90 días de demo antes.")
        print("=" * 60)

    # Candado a mainnet: capa adicional independiente de si hay API keys
    # configuradas -- bloquea salvo aprobación explícita (ver
    # assert_mainnet_allowed). cycle()/place_order() ya lo revalidan en cada
    # ciclo; aquí se hace también para fallar rápido y con salida limpia
    # desde la CLI, sin esperar al primer ciclo.
    try:
        assert_mainnet_allowed(a.live, a.testnet)
    except RuntimeError as e:
        print(f"❌ {e}")
        sys.exit(1)

    if a.live and not os.environ.get("BYBIT_API_KEY"):
        print("❌ --live requiere BYBIT_API_KEY y BYBIT_API_SECRET en variables de entorno.")
        sys.exit(1)

    p = make_params()
    print(f"\n{'='*60}")
    print(f"  BREAKOUT-ATR Live Executor v1.0")
    print(f"  Símbolo:  {a.symbol}")
    print(f"  Equity:   ${a.equity:,.0f}")
    print(f"  Modo:     {'LIVE' if a.live else 'DRY-RUN'} | "
          f"{'TESTNET' if a.testnet else 'MAINNET'}")
    print(f"  Config:   {FROZEN_CONFIG}")
    print(f"  Poll:     {a.poll}s")
    print(f"{'='*60}\n")

    while True:
        try:
            cycle(a.symbol, p, a.live, a.testnet, a.equity)
        except KeyboardInterrupt:
            print("\n[salida] Interrumpido por usuario.")
            break
        except Exception as e:
            print(f"  [error] {type(e).__name__}: {e}")
            import traceback
            traceback.print_exc()
        if a.once:
            break
        print(f"\n  Próximo ciclo en {a.poll}s...")
        try:
            time.sleep(a.poll)
        except KeyboardInterrupt:
            print("\n[salida] Interrumpido por usuario.")
            break

    print("\n[fin] Executor detenido.")


if __name__ == "__main__":
    main()

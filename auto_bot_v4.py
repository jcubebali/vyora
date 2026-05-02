"""
====================================================
  BINANCE FULL AUTO TRADING BOT v4.0
  Entry + SL + TP — 100% Otomatis
  Interval: 15 menit
  Strategy: EMA + RSI + Volume
  Fix: round_step menggunakan math.floor
====================================================
"""

import os
import math
import hmac
import hashlib
import time
import requests
import json
import logging
try:
    from update_stats import push_trade, update_balance
    FIRESTORE_OK = True
except Exception as e:
    FIRESTORE_OK = False
    print(f"[FIRESTORE] Disabled: {e}")

try:
    from ai_analyst import ai_analyze
    AI_OK = True
    print("[AI] Groq AI analyst loaded!")
except Exception as e:
    AI_OK = False
    print(f"[AI] Disabled: {e}")

try:
    from ai_analyst import ai_analyze
    AI_OK = True
    print("[AI] Groq AI analyst loaded!")
except Exception as e:
    AI_OK = False
    print(f"[AI] Disabled: {e}")
import urllib3
from datetime import datetime
from urllib.parse import urlencode

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# ─────────────────────────────────────────────────
# KONFIGURASI
# ─────────────────────────────────────────────────

BINANCE_API_URL  = "https://api.binance.com"
INTERVAL_MINUTES = 15
SYMBOLS          = ["BTCUSDT"]
RISK_PER_TRADE   = 0.01
MAX_OPEN_TRADES  = 1
EMA_FAST         = 20
EMA_SLOW         = 50
RSI_PERIOD       = 14
RSI_MIN          = 35
RSI_MAX          = 75
VOLUME_MIN       = 0.8
TP_PERCENT       = 0.03
SL_PERCENT       = 0.015
SSL_VERIFY       = True

# ── Ganti dengan API key kamu ──
os.environ["BINANCE_API_KEY"]    = os.getenv("BINANCE_API_KEY","")
os.environ["BINANCE_API_SECRET"] = os.getenv("BINANCE_API_SECRET","")

# ─────────────────────────────────────────────────
# LOGGING
# ─────────────────────────────────────────────────

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler("auto_bot.log"),
        logging.StreamHandler()
    ]
)
log = logging.getLogger(__name__)

# ─────────────────────────────────────────────────
# BINANCE API
# ─────────────────────────────────────────────────

def _get_credentials():
    key    = os.environ.get("BINANCE_API_KEY", "").strip()
    secret = os.environ.get("BINANCE_API_SECRET", "").strip()
    if not key or not secret:
        raise ValueError("Set BINANCE_API_KEY dan BINANCE_API_SECRET!")
    return key, secret

def _sign(params, secret):
    query = urlencode(params)
    return hmac.new(secret.encode("utf-8"), query.encode("utf-8"), hashlib.sha256).hexdigest()

def _get(endpoint, params=None, signed=False):
    key, secret = _get_credentials()
    params = params or {}
    if signed:
        params["timestamp"] = int(time.time() * 1000)
        params["signature"] = _sign(params, secret)
    try:
        r = requests.get(
            BINANCE_API_URL + endpoint,
            headers={"X-MBX-APIKEY": key},
            params=params, timeout=10, verify=SSL_VERIFY
        )
        r.raise_for_status()
        return r.json()
    except Exception as e:
        log.error(f"GET {endpoint}: {e}")
        return None

def _post(endpoint, params):
    key, secret = _get_credentials()
    params["timestamp"] = int(time.time() * 1000)
    params["signature"] = _sign(params, secret)
    try:
        r = requests.post(
            BINANCE_API_URL + endpoint,
            headers={"X-MBX-APIKEY": key},
            params=params, timeout=10, verify=SSL_VERIFY
        )
        r.raise_for_status()
        return r.json()
    except Exception as e:
        log.error(f"POST {endpoint}: {e}")
        return None

def get_klines(symbol, interval="15m", limit=220):
    data = _get("/api/v3/klines", {"symbol": symbol, "interval": interval, "limit": limit})
    if not data:
        return []
    return [{"close": float(c[4]), "high": float(c[2]), "low": float(c[3]), "volume": float(c[5])} for c in data]

def get_balance(asset="USDT"):
    data = _get("/api/v3/account", signed=True)
    if not data:
        return 0.0
    for b in data.get("balances", []):
        if b["asset"] == asset:
            return float(b["free"])
    return 0.0

def get_symbol_info(symbol):
    data = _get("/api/v3/exchangeInfo", {"symbol": symbol})
    if not data:
        return {}
    symbols = data.get("symbols", [])
    return symbols[0] if symbols else {}

# ─────────────────────────────────────────────────
# INDIKATOR
# ─────────────────────────────────────────────────

def calc_ema(closes, period):
    if len(closes) < period:
        return []
    k = 2 / (period + 1)
    ema = [sum(closes[:period]) / period]
    for p in closes[period:]:
        ema.append(p * k + ema[-1] * (1 - k))
    return ema

def calc_rsi(closes, period=14):
    if len(closes) < period + 1:
        return 50.0
    gains  = [max(closes[i] - closes[i-1], 0) for i in range(1, len(closes))]
    losses = [max(closes[i-1] - closes[i], 0) for i in range(1, len(closes))]
    ag = sum(gains[:period]) / period
    al = sum(losses[:period]) / period
    for i in range(period, len(gains)):
        ag = (ag * (period - 1) + gains[i]) / period
        al = (al * (period - 1) + losses[i]) / period
    if al == 0:
        return 100.0
    return round(100 - (100 / (1 + ag / al)), 2)

def calc_avg_volume(candles, period=20):
    vols = [c["volume"] for c in candles[-period-1:-1]]
    return sum(vols) / len(vols) if vols else 0

def get_signal(candles):
    if len(candles) < EMA_SLOW + 10:
        return {"signal": "HOLD", "confidence": "LOW", "score": 0, "reason": "Data kurang", "rsi": 50, "vol_ratio": 0, "price": 0, "ema_fast": 0, "ema_slow": 0}

    closes  = [c["close"] for c in candles]
    ema_f   = calc_ema(closes, EMA_FAST)
    ema_s   = calc_ema(closes, EMA_SLOW)
    rsi_val = calc_rsi(closes, RSI_PERIOD)
    cur_vol = candles[-1]["volume"]
    avg_vol = calc_avg_volume(candles)
    price   = closes[-1]

    vol_ratio   = cur_vol / avg_vol if avg_vol > 0 else 0
    uptrend     = len(ema_f) >= 2 and len(ema_s) >= 2 and ema_f[-1] > ema_s[-1]
    above_ma200 = price > (sum(closes[-200:]) / 200) if len(closes) >= 200 else True

    score, reason = 0, []
    if uptrend:        score += 2; reason.append(f"EMA{EMA_FAST}>{EMA_SLOW}")
    if RSI_MIN <= rsi_val <= RSI_MAX: score += 2; reason.append(f"RSI={rsi_val}")
    if vol_ratio >= VOLUME_MIN: score += 2; reason.append(f"Vol={vol_ratio:.1f}x")
    if above_ma200:    score += 1; reason.append("Price>MA200")

    conf   = "HIGH" if score >= 5 else ("MEDIUM" if score >= 3 else "LOW")
    signal = "BUY" if score >= 4 and uptrend else "HOLD"

    return {
        "signal": signal, "confidence": conf, "score": score,
        "reason": ", ".join(reason) or "Tidak ada sinyal",
        "rsi": rsi_val, "vol_ratio": round(vol_ratio, 2), "price": price,
        "ema_fast": round(ema_f[-1], 2) if ema_f else 0,
        "ema_slow": round(ema_s[-1], 2) if ema_s else 0,
    }

# ─────────────────────────────────────────────────
# ORDER MANAGER
# ─────────────────────────────────────────────────

def round_step(value, step):
    from decimal import Decimal, ROUND_DOWN
    if step <= 0:
        return value
    d_value = Decimal(str(value))
    d_step = Decimal(str(step))
    result = (d_value / d_step).to_integral_value(rounding=ROUND_DOWN) * d_step
    return float(result)

def get_step_size(symbol_info):
    for f in symbol_info.get("filters", []):
        if f["filterType"] == "LOT_SIZE":
            return float(f["stepSize"])
    return 0.00001

def get_tick_size(symbol_info):
    for f in symbol_info.get("filters", []):
        if f["filterType"] == "PRICE_FILTER":
            return float(f["tickSize"])
    return 0.01

def place_buy(symbol, balance, price):
    sym_info  = get_symbol_info(symbol)
    step_size = get_step_size(sym_info)

    usdt_to_use = balance * 0.90
    qty = round_step(usdt_to_use / price, step_size)

    log.info(f"   place_buy: balance=${balance:.2f} | usdt=${usdt_to_use:.2f} | qty={qty} | value=${qty*price:.2f}")

    if qty * price < 5:
        log.warning(f"⚠️  {symbol}: Balance tidak cukup (${qty*price:.2f} < $5 minimum)")
        return {}

    log.info(f"🟢 BUY {symbol} | qty={qty} | price~${price:,.2f} | value=${qty*price:.2f}")
    result = _post("/api/v3/order", {
        "symbol": symbol, "side": "BUY", "type": "MARKET", "quantity": qty,
    })
    return result or {}

def place_oco(symbol, qty, entry_price):
    sym_info  = get_symbol_info(symbol)
    tick_size = get_tick_size(sym_info)
    step_size = get_step_size(sym_info)

    tp_price   = round_step(entry_price * (1 + TP_PERCENT), tick_size)
    sl_trigger = round_step(entry_price * (1 - SL_PERCENT), tick_size)
    sl_limit   = round_step(sl_trigger * 0.998, tick_size)
    qty        = round_step(qty, step_size)

    log.info(f"📌 OCO {symbol} | TP=${tp_price:,.2f} | SL=${sl_trigger:,.2f}")
    result = _post("/api/v3/order/oco", {
        "symbol": symbol, "side": "SELL", "quantity": qty,
        "price": tp_price, "stopPrice": sl_trigger,
        "stopLimitPrice": sl_limit, "stopLimitTimeInForce": "GTC",
    })
    return result or {}

# ─────────────────────────────────────────────────
# JURNAL
# ─────────────────────────────────────────────────

def save_journal(action, symbol, price, qty, reason, pnl=None):
    entry = {
        "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "action": action, "symbol": symbol,
        "price": price, "qty": qty, "reason": reason, "pnl": pnl,
    }
    with open("jurnal.json", "a") as f:
        f.write(json.dumps(entry) + "\n")

# ─────────────────────────────────────────────────
# BOT UTAMA
# ─────────────────────────────────────────────────

class AutoBot:
    def __init__(self):
        self.open_trades = {}
        self.highest_price = {}  # Track harga tertinggi untuk trailing stop

    def check_exit(self, symbol, price):
        if symbol not in self.open_trades:
            return
        trade   = self.open_trades[symbol]
        pnl     = (price - trade["entry"]) * trade["qty"]
        pnl_pct = (price - trade["entry"]) / trade["entry"] * 100

        if price >= trade["tp"]:
            log.info(f"🎯 TP HIT {symbol} | PnL=+${pnl:.4f} (+{pnl_pct:.2f}%)")
            if FIRESTORE_OK:
                try:
                    push_trade(symbol, "BUY", trade["entry"], price, trade["qty"], pnl, pnl_pct)
                    bal = get_balance("USDT")
                    update_balance(bal, pnl, 1, 1)
                except Exception as fe: print(f"[FIRESTORE] {fe}")
            save_journal("SELL_TP", symbol, price, trade["qty"], "TP hit", pnl)
            del self.open_trades[symbol]
        elif price <= trade["sl"]:
            log.info(f"🛑 SL HIT {symbol} | PnL=${pnl:.4f} ({pnl_pct:.2f}%)")
            if FIRESTORE_OK:
                try:
                    push_trade(symbol, "BUY", trade["entry"], price, trade["qty"], pnl, pnl_pct)
                    bal = get_balance("USDT")
                    update_balance(bal, pnl, 1, 0)
                except Exception as fe: print(f"[FIRESTORE] {fe}")
            save_journal("SELL_SL", symbol, price, trade["qty"], "SL hit", pnl)
            del self.open_trades[symbol]
        else:
            # Update highest price untuk trailing stop
            if symbol not in self.highest_price:
                self.highest_price[symbol] = price
            if price > self.highest_price[symbol]:
                self.highest_price[symbol] = price

            # Trailing stop — aktif setelah profit > 1%
            highest = self.highest_price.get(symbol, trade["entry"])
            trail_sl = round(highest * (1 - SL_PERCENT), 2)

            if pnl_pct > 1.0 and price <= trail_sl:
                log.info(f"🔄 TRAILING STOP {symbol} | PnL={pnl_pct:+.2f}% | Trail SL=${trail_sl:,.2f}")
                if FIRESTORE_OK:
                    try:
                        push_trade(symbol, "BUY", trade["entry"], price, trade["qty"], pnl, pnl_pct)
                        bal = get_balance("USDT")
                        update_balance(bal, pnl, 1, 1)
                    except Exception as fe: print(f"[FIRESTORE] {fe}")
                save_journal("SELL_TRAIL", symbol, price, trade["qty"], f"Trailing SL hit @ ${trail_sl}", pnl)
                del self.open_trades[symbol]
                if symbol in self.highest_price:
                    del self.highest_price[symbol]
            else:
                log.info(f"📊 {symbol} OPEN | Entry=${trade['entry']:,.2f} | Now=${price:,.2f} | PnL={pnl_pct:+.2f}% | High=${highest:,.2f} | Trail SL=${trail_sl:,.2f}")

    def run_cycle(self, cycle):
        print(f"\n{'='*45}")
        print(f"  🤖 BINANCE AUTO BOT v4.0 | Cycle #{cycle}")
        print(f"  {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"{'='*45}")

        balance = get_balance("USDT")
        log.info(f"💰 Balance: ${balance:.4f} USDT")
        # Push cycle count ke Firestore
        if FIRESTORE_OK:
            try:
                update_balance(balance, 0, 0, 0)
                # Update bot status
                import json, urllib.request
                from update_stats import get_token
                token = get_token()
                uid = open(os.path.expanduser("~/.nexus_uid")).read().strip()
                doc = {"fields": {
                    "botCycle": {"integerValue": str(cycle)},
                    "botStatus": {"stringValue": "RUNNING"},
                    "botLastSeen": {"timestampValue": datetime.now().isoformat()}
                }}
                mask = "updateMask.fieldPaths=botCycle&updateMask.fieldPaths=botStatus&updateMask.fieldPaths=botLastSeen"
                url = f"https://firestore.googleapis.com/v1/projects/nexus-trade-e449e/databases/(default)/documents/users/{uid}?{mask}"
                body = json.dumps(doc).encode()
                req = urllib.request.Request(url, data=body, headers={
                    "Authorization": f"Bearer {token}",
                    "Content-Type": "application/json"
                }, method="PATCH")
                urllib.request.urlopen(req)
                log.info(f"[FIRESTORE] Cycle #{cycle} pushed")
            except Exception as fe:
                log.error(f"[FIRESTORE] Cycle push error: {fe}")

        for symbol in SYMBOLS:
            try:
                candles = get_klines(symbol, "15m", 220)
                if not candles:
                    continue

                sig   = get_signal(candles)
                price = candles[-1]["close"]

                log.info(f"{'─'*40}")
                log.info(f"📈 {symbol} | ${price:,.2f}")
                log.info(f"   EMA{EMA_FAST}=${sig['ema_fast']:,.2f} | EMA{EMA_SLOW}=${sig['ema_slow']:,.2f}")
                log.info(f"   RSI={sig['rsi']} | Vol={sig['vol_ratio']}x")
                log.info(f"   Signal={sig['signal']} | Confidence={sig['confidence']} | Score={sig['score']}/7")
                log.info(f"   Reason: {sig['reason']}")

                self.check_exit(symbol, price)

                if symbol in self.open_trades:
                    continue
                if len(self.open_trades) >= MAX_OPEN_TRADES:
                    continue

                if sig["signal"] == "BUY" and sig["confidence"] in ["HIGH", "MEDIUM"]:
                    # AI confirmation
                    if AI_OK:
                        log.info(f"🤖 Meminta konfirmasi AI...")
                        ai = ai_analyze(
                            symbol, price,
                            sig.get("rsi", 50),
                            sig.get("ema_fast", price),
                            sig.get("ema_slow", price),
                            price * 0.985,
                            sig.get("macd_hist", 0),
                            sig.get("vol_ratio", 1),
                            "Uptrend" if int(str(sig.get("score","0/7")).split("/")[0]) >= 4 else "Sideways"
                        )
                        log.info(f"🤖 AI: {ai['signal']} ({ai['confidence']})")
                        log.info(f"🤖 {ai['analysis'][:150]}...")
                        if ai["signal"] != "BUY":
                            log.info(f"🛑 AI tidak konfirmasi BUY ({ai['signal']}) — skip trade")
                            continue
                    log.info(f"⚡ ENTRY SIGNAL — Eksekusi BUY!")
                    order = place_buy(symbol, balance, price)

                    if order and order.get("orderId"):
                        fills       = order.get("fills", [])
                        entry_price = float(fills[0]["price"]) if fills else price
                        qty         = float(order.get("executedQty", 0))
                        tp = round(entry_price * (1 + TP_PERCENT), 2)
                        sl = round(entry_price * (1 - SL_PERCENT), 2)

                        self.open_trades[symbol] = {"entry": entry_price, "qty": qty, "tp": tp, "sl": sl}
                        log.info(f"✅ BUY OK | Entry=${entry_price:,.2f} | Qty={qty} | TP=${tp:,.2f} | SL=${sl:,.2f}")
                        save_journal("BUY", symbol, entry_price, qty, sig["reason"])

                        time.sleep(2)
                        oco = place_oco(symbol, qty, entry_price)
                        if oco:
                            log.info(f"✅ OCO TERPASANG — TP/SL aktif otomatis!")
                        else:
                            log.warning(f"⚠️  OCO gagal — pantau manual!")
                    else:
                        log.error(f"❌ BUY gagal untuk {symbol}")
                else:
                    log.info(f"⏸  HOLD — tidak ada setup")

            except Exception as e:
                log.error(f"Error {symbol}: {e}")

    def start(self):
        log.info("🚀 AUTO BOT v4.0 STARTED")
        log.info(f"   Pairs: {SYMBOLS} | TP: {TP_PERCENT*100}% | SL: {SL_PERCENT*100}% | Interval: {INTERVAL_MINUTES}m")

        cycle = 1
        while True:
            try:
                self.run_cycle(cycle)
            except KeyboardInterrupt:
                log.info("🛑 Bot dihentikan")
                break
            except Exception as e:
                log.error(f"Cycle error: {e}")

            log.info(f"\n⏳ Menunggu {INTERVAL_MINUTES} menit... (Ctrl+C untuk stop)\n")
            time.sleep(INTERVAL_MINUTES * 60)
            cycle += 1

if __name__ == "__main__":
    bot = AutoBot()
    bot.start()

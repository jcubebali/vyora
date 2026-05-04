"""
╔══════════════════════════════════════════════╗
║  VYORA AUTO BOT v5.0                        ║
║  By J-CUBE | Intelligent Crypto Trading     ║
║                                              ║
║  Entry  : EMA + RSI + MACD + BB + Volume    ║
║  Confirm: Groq LLaMA 3.3 70B AI             ║
║  Exit   : Trailing Stop + AI Analysis       ║
║  Safety : Hard SL + Hard TP                 ║
╚══════════════════════════════════════════════╝
"""

import os, hmac, hashlib, time, requests, json, logging
from datetime import datetime
from urllib.parse import urlencode

# ─── LOGGING ──────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler("bot.log"),
        logging.StreamHandler()
    ]
)
log = logging.getLogger(__name__)

# ─── CONFIG ───────────────────────────────────────
API_URL        = "https://api.binance.com"
SYMBOLS        = ["BTCUSDT"]
INTERVAL       = "15m"
INTERVAL_MINS  = 15

# Risk Management
TP_PCT         = 0.030   # 3.0% hard take profit
SL_PCT         = 0.015   # 1.5% hard stop loss
TRAIL_PCT      = 0.015   # 1.5% trailing distance
TRAIL_ACTIVATE = 0.010   # Trailing aktif setelah +1%
AI_EXIT_MIN    = 0.005   # AI exit hanya kalau profit > 0.5%
RISK_PCT       = 0.90    # 90% balance per trade
MAX_OPEN       = 1

# Signal
EMA_FAST   = 20
EMA_SLOW   = 50
EMA_TREND  = 200
RSI_PERIOD = 14
MIN_SCORE  = 5

# AI
GROQ_KEY   = os.environ.get("GROQ_API_KEY", "")
GROQ_MODEL = "llama-3.3-70b-versatile"

# ─── INTEGRATIONS ─────────────────────────────────
try:
    from update_stats import push_trade, update_balance, get_token
    FIRESTORE_OK = True
    log.info("[FIRESTORE] ✅ Connected")
except Exception as e:
    FIRESTORE_OK = False
    log.warning(f"[FIRESTORE] Disabled: {e}")

# ─── BINANCE API ──────────────────────────────────
def _sign(params):
    secret = os.environ.get("BINANCE_API_SECRET", "")
    return hmac.new(secret.encode(), urlencode(params).encode(), hashlib.sha256).hexdigest()

def _headers():
    return {"X-MBX-APIKEY": os.environ.get("BINANCE_API_KEY", "")}

def _get(endpoint, params=None, signed=False):
    if params is None: params = {}
    if signed:
        params["timestamp"] = int(time.time() * 1000)
        params["signature"] = _sign(params)
    try:
        r = requests.get(f"{API_URL}{endpoint}", params=params,
                        headers=_headers(), timeout=10)
        return r.json()
    except Exception as e:
        log.error(f"GET {endpoint}: {e}")
        return {}

def _post(endpoint, params):
    params["timestamp"] = int(time.time() * 1000)
    params["signature"] = _sign(params)
    try:
        r = requests.post(f"{API_URL}{endpoint}", params=params,
                         headers=_headers(), timeout=10)
        return r.json()
    except Exception as e:
        log.error(f"POST {endpoint}: {e}")
        return {}

# ─── MARKET DATA ──────────────────────────────────
def get_klines(symbol, interval="15m", limit=220):
    data = _get("/api/v3/klines", {"symbol": symbol, "interval": interval, "limit": limit})
    if not isinstance(data, list): return []
    return [{"close": float(c[4]), "high": float(c[2]),
             "low": float(c[3]), "volume": float(c[5])} for c in data]

def get_balance(asset="USDT"):
    data = _get("/api/v3/account", {}, signed=True)
    for b in data.get("balances", []):
        if b["asset"] == asset:
            return float(b["free"])
    return 0.0

def get_symbol_info(symbol):
    data = _get("/api/v3/exchangeInfo", {"symbol": symbol})
    for s in data.get("symbols", []):
        if s["symbol"] == symbol:
            return s
    return {}

def round_step(value, step):
    if step == 0: return value
    precision = len(str(step).rstrip("0").split(".")[-1]) if "." in str(step) else 0
    return round(round(value / step) * step, precision)

def get_filters(symbol_info):
    step = tick = 0.00001
    min_notional = 5.0
    for f in symbol_info.get("filters", []):
        if f["filterType"] == "LOT_SIZE":
            step = float(f["stepSize"])
        elif f["filterType"] == "PRICE_FILTER":
            tick = float(f["tickSize"])
        elif f["filterType"] == "MIN_NOTIONAL":
            min_notional = float(f.get("minNotional", 5.0))
    return step, tick, min_notional

# ─── INDICATORS ───────────────────────────────────
def ema(closes, period):
    if len(closes) < period: return closes[-1] if closes else 0
    k = 2 / (period + 1)
    e = sum(closes[:period]) / period
    for p in closes[period:]: e = p * k + e * (1 - k)
    return round(e, 4)

def rsi(closes, period=14):
    if len(closes) < period + 1: return 50.0
    gains = [max(closes[i] - closes[i-1], 0) for i in range(1, len(closes))]
    losses = [max(closes[i-1] - closes[i], 0) for i in range(1, len(closes))]
    ag = sum(gains[:period]) / period
    al = sum(losses[:period]) / period
    for i in range(period, len(gains)):
        ag = (ag * (period - 1) + gains[i]) / period
        al = (al * (period - 1) + losses[i]) / period
    if al == 0: return 100.0
    return round(100 - (100 / (1 + ag / al)), 2)

def macd(closes, fast=12, slow=26, signal=9):
    if len(closes) < slow + signal: return 0, 0, 0
    def _ema(data, p):
        k = 2/(p+1); e = sum(data[:p])/p
        for x in data[p:]: e = x*k + e*(1-k)
        return e
    macd_vals = [_ema(closes[max(0,i-fast*3):i+1], fast) - 
                 _ema(closes[max(0,i-slow*3):i+1], slow)
                 for i in range(slow, len(closes))]
    if len(macd_vals) < signal: return 0, 0, 0
    ml = macd_vals[-1]
    sl = _ema(macd_vals[-signal*3:], signal)
    return round(ml, 4), round(sl, 4), round(ml - sl, 4)

def bollinger(closes, period=20, std_dev=2):
    if len(closes) < period: return closes[-1], closes[-1], closes[-1]
    recent = closes[-period:]
    mid = sum(recent) / period
    std = (sum((x - mid) ** 2 for x in recent) / period) ** 0.5
    return round(mid + std_dev * std, 2), round(mid, 2), round(mid - std_dev * std, 2)

# ─── SIGNAL ENGINE ────────────────────────────────
def get_signal(candles):
    if len(candles) < EMA_SLOW + 10:
        return {"signal": "WAIT", "score": 0, "confidence": "LOW", "reason": "Data kurang"}

    closes = [c["close"] for c in candles]
    price  = closes[-1]

    ema20  = ema(closes, EMA_FAST)
    ema50  = ema(closes, EMA_SLOW)
    ema200 = ema(closes, EMA_TREND)
    rsi_v  = rsi(closes, RSI_PERIOD)
    ml, ms, mh = macd(closes)
    bb_up, bb_mid, bb_low = bollinger(closes)

    avg_vol   = sum(c["volume"] for c in candles[-21:-1]) / 20
    vol_ratio = round(candles[-1]["volume"] / avg_vol, 2) if avg_vol > 0 else 0

    score   = 0
    reasons = []

    if ema20 > ema50:       score += 2; reasons.append(f"EMA{EMA_FAST}>{EMA_SLOW}")
    if price > ema200:      score += 1; reasons.append("Price>MA200")
    if rsi_v < 55:          score += 2; reasons.append(f"RSI={rsi_v}")
    if mh > 0:              score += 1; reasons.append("MACD+")
    if price < bb_low:      score += 1; reasons.append("BB oversold")
    if vol_ratio > 0.8:     score += 1; reasons.append(f"Vol={vol_ratio}x")

    if score >= MIN_SCORE:
        conf = "HIGH" if score >= 6 else "MEDIUM"
        return {"signal": "BUY", "score": f"{score}/8", "confidence": conf,
                "reason": ", ".join(reasons), "rsi": rsi_v, "ema20": ema20,
                "ema50": ema50, "ema200": ema200, "macd_h": mh, "vol_ratio": vol_ratio,
                "bb_low": bb_low, "price": price}

    return {"signal": "HOLD", "score": f"{score}/8", "confidence": "LOW",
            "reason": ", ".join(reasons) if reasons else "Score rendah",
            "rsi": rsi_v, "ema20": ema20, "ema50": ema50, "ema200": ema200,
            "macd_h": mh, "vol_ratio": vol_ratio, "price": price}

# ─── GROQ AI ──────────────────────────────────────
def _ask_groq(prompt):
    if not GROQ_KEY: return None
    try:
        r = requests.post(
            "https://api.groq.com/openai/v1/chat/completions",
            headers={"Authorization": f"Bearer {GROQ_KEY}", "Content-Type": "application/json"},
            json={"model": GROQ_MODEL, "messages": [
                {"role": "system", "content": "You are an expert crypto trader. Be concise and decisive."},
                {"role": "user", "content": prompt}
            ], "max_tokens": 150, "temperature": 0.2},
            timeout=25
        )
        return r.json()["choices"][0]["message"]["content"]
    except Exception as e:
        log.error(f"[AI] Groq error: {e}")
        return None

def ai_entry(symbol, price, sig):
    """AI konfirmasi entry"""
    prompt = f"""Crypto entry signal:
{symbol} @ ${price:,.2f} | RSI: {sig['rsi']} | Score: {sig['score']}
EMA20: ${sig['ema20']:,.2f} > EMA50: ${sig['ema50']:,.2f} | MACD: {sig['macd_h']}
Volume: {sig['vol_ratio']}x avg | Reason: {sig['reason']}

Should I BUY now? Reply: BUY or HOLD — one sentence reason."""
    resp = _ask_groq(prompt)
    if not resp: return "HOLD", "AI unavailable"
    sig_out = "BUY" if "BUY" in resp.upper() else "HOLD"
    return sig_out, resp

def ai_exit(symbol, price, entry, pnl_pct, rsi_v, macd_h, highest, trail_sl):
    """AI analisa exit — dipanggil setiap cycle"""
    prompt = f"""Active trade monitoring:
{symbol} | Entry: ${entry:,.2f} | Now: ${price:,.2f} | PnL: {pnl_pct:+.2f}%
RSI: {rsi_v:.1f} | MACD Hist: {macd_h:.2f}
Peak: ${highest:,.2f} | Trailing SL: ${trail_sl:,.2f}
Target TP: ${entry*(1+TP_PCT):,.2f} | Hard SL: ${entry*(1-SL_PCT):,.2f}

Decision: HOLD (keep running) or EXIT (sell now)?
Consider momentum, profit protection, risk.
Reply: HOLD or EXIT — one sentence reason."""
    resp = _ask_groq(prompt)
    if not resp: return "HOLD", "AI unavailable"
    decision = "EXIT" if "EXIT" in resp.upper() else "HOLD"
    return decision, resp

# ─── ORDER EXECUTION ──────────────────────────────
def market_buy(symbol, balance):
    info = get_symbol_info(symbol)
    step, tick, min_notional = get_filters(info)
    price = float(_get("/api/v3/ticker/price", {"symbol": symbol}).get("price", 0))
    usdt = balance * RISK_PCT
    if usdt < min_notional:
        log.warning(f"⚠️ Balance tidak cukup: ${usdt:.2f} < ${min_notional}")
        return None
    qty = round_step(usdt / price, step)
    log.info(f"   BUY: ${usdt:.2f} USDT → {qty} {symbol} @ ~${price:,.2f}")
    return _post("/api/v3/order", {"symbol": symbol, "side": "BUY", "type": "MARKET", "quantity": qty})

def market_sell(symbol, qty):
    info = get_symbol_info(symbol)
    step, _, _ = get_filters(info)
    qty = round_step(qty, step)
    log.info(f"   SELL: {qty} {symbol}")
    return _post("/api/v3/order", {"symbol": symbol, "side": "SELL", "type": "MARKET", "quantity": qty})

# ─── FIRESTORE SYNC ───────────────────────────────
def sync_firestore(balance, pnl, trades, wins, cycle, status="RUNNING"):
    if not FIRESTORE_OK: return
    try:
        update_balance(balance, pnl, trades, wins)
        token = get_token()
        uid = open(os.path.expanduser("~/.nexus_uid")).read().strip()
        doc = {"fields": {
            "botCycle":    {"stringValue": str(cycle)},
            "botStatus":   {"stringValue": status},
            "botLastSeen": {"stringValue": datetime.now().isoformat()}
        }}
        mask = "&".join([f"updateMask.fieldPaths={f}" for f in ["botCycle","botStatus","botLastSeen"]])
        url = f"https://firestore.googleapis.com/v1/projects/nexus-trade-e449e/databases/(default)/documents/users/{uid}?{mask}"
        import urllib.request
        req = urllib.request.Request(url, data=json.dumps(doc).encode(),
            headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
            method="PATCH")
        urllib.request.urlopen(req)
    except Exception as e:
        log.error(f"[FIRESTORE] Sync error: {e}")

def log_trade(symbol, side, entry, exit_price, qty, pnl, pnl_pct, status="CLOSED"):
    if not FIRESTORE_OK: return
    try:
        push_trade(symbol, side, entry, exit_price, qty, pnl, pnl_pct, status)
    except Exception as e:
        log.error(f"[FIRESTORE] Trade log error: {e}")

# ─── MAIN BOT ─────────────────────────────────────
class VyoraBot:
    def __init__(self):
        self.trades  = {}   # {symbol: {entry, qty, tp, sl}}
        self.highest = {}   # {symbol: highest_price}
        self.stats   = {"wins": 0, "losses": 0, "pnl": 0.0, "total": 0}

    def _exit_trade(self, symbol, price, reason, is_win):
        trade  = self.trades[symbol]
        pnl    = (price - trade["entry"]) * trade["qty"]
        pnl_pct = (price - trade["entry"]) / trade["entry"] * 100

        order = market_sell(symbol, trade["qty"])
        if not order or not order.get("orderId"):
            log.error(f"❌ Sell gagal: {order}")
            return False

        exit_price = float(order.get("fills", [{}])[0].get("price", price)) if order.get("fills") else price

        emoji = "🎯" if is_win else "🛑"
        log.info(f"{emoji} {reason} | {symbol} | Entry=${trade['entry']:,.2f} | Exit=${exit_price:,.2f} | PnL={pnl_pct:+.2f}% (${pnl:+.4f})")

        # Update stats
        if is_win:
            self.stats["wins"] += 1
        else:
            self.stats["losses"] += 1
        self.stats["total"] += 1
        self.stats["pnl"]   += pnl

        # Firestore
        balance = get_balance("USDT")
        log_trade(symbol, "BUY", trade["entry"], exit_price, trade["qty"], pnl, pnl_pct)
        sync_firestore(balance, self.stats["pnl"], self.stats["total"], self.stats["wins"], 0)

        # Cleanup
        del self.trades[symbol]
        if symbol in self.highest: del self.highest[symbol]
        return True

    def monitor_position(self, symbol, price, candles):
        """Monitor posisi open — exit logic priority:
        1. Hard SL (keselamatan modal)
        2. Trailing Stop (lock profit)
        3. AI Exit Analysis (smart exit)
        4. Hard TP (profit target)
        """
        trade   = self.trades[symbol]
        entry   = trade["entry"]
        pnl_pct = (price - entry) / entry * 100

        # Update highest
        if symbol not in self.highest or price > self.highest[symbol]:
            self.highest[symbol] = price
        highest   = self.highest[symbol]
        trail_sl  = round(highest * (1 - TRAIL_PCT), 2)

        # ① HARD SL — prioritas tertinggi
        hard_sl = entry * (1 - SL_PCT)
        if price <= hard_sl:
            log.info(f"🛑 HARD SL triggered @ ${price:,.2f} (SL: ${hard_sl:,.2f})")
            self._exit_trade(symbol, price, "HARD_SL", False)
            return

        # ② TRAILING STOP — aktif setelah profit > TRAIL_ACTIVATE
        if pnl_pct > TRAIL_ACTIVATE * 100 and price <= trail_sl:
            log.info(f"🔄 TRAILING STOP @ ${price:,.2f} | Peak: ${highest:,.2f} | Trail SL: ${trail_sl:,.2f}")
            self._exit_trade(symbol, price, "TRAILING_STOP", True)
            return

        # ③ AI EXIT ANALYSIS — smart exit
        closes = [c["close"] for c in candles]
        rsi_v  = rsi(closes, RSI_PERIOD)
        _, _, macd_h = macd(closes)

        if pnl_pct > AI_EXIT_MIN * 100:
            ai_dec, ai_reason = ai_exit(symbol, price, entry, pnl_pct, rsi_v, macd_h, highest, trail_sl)
            log.info(f"🤖 AI Exit: {ai_dec} | {ai_reason[:80]}")

            if ai_dec == "EXIT":
                log.info(f"🤖 AI EXIT triggered | PnL={pnl_pct:+.2f}%")
                self._exit_trade(symbol, price, "AI_EXIT", pnl_pct > 0)
                return

        # ④ HARD TP
        hard_tp = entry * (1 + TP_PCT)
        if price >= hard_tp:
            log.info(f"🎯 HARD TP triggered @ ${price:,.2f} (TP: ${hard_tp:,.2f})")
            self._exit_trade(symbol, price, "HARD_TP", True)
            return

        # Still holding
        log.info(f"📊 HOLDING {symbol} | Entry: ${entry:,.2f} | Now: ${price:,.2f} | PnL: {pnl_pct:+.2f}%")
        log.info(f"   Peak: ${highest:,.2f} | Trail SL: ${trail_sl:,.2f} | Hard TP: ${hard_tp:,.2f} | Hard SL: ${hard_sl:,.2f}")

    def run_cycle(self, cycle):
        print(f"\n{'='*50}")
        print(f"  🤖 VYORA BOT v5.0 | Cycle #{cycle}")
        print(f"  {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"  Wins: {self.stats['wins']} | Losses: {self.stats['losses']} | PnL: ${self.stats['pnl']:+.4f}")
        print(f"{'='*50}")

        balance = get_balance("USDT")
        log.info(f"💰 Balance: ${balance:.4f} USDT")

        # Sync Firestore
        sync_firestore(balance, self.stats["pnl"], self.stats["total"], self.stats["wins"], cycle)

        for symbol in SYMBOLS:
            try:
                candles = get_klines(symbol, INTERVAL, 220)
                if not candles: continue

                sig   = get_signal(candles)
                price = candles[-1]["close"]

                log.info(f"{'─'*50}")
                log.info(f"📈 {symbol} | ${price:,.2f}")
                log.info(f"   EMA20=${sig['ema20']:,.2f} | EMA50=${sig['ema50']:,.2f} | EMA200=${sig['ema200']:,.2f}")
                log.info(f"   RSI={sig['rsi']} | MACD={sig['macd_h']} | Vol={sig['vol_ratio']}x")
                log.info(f"   Signal={sig['signal']} | Score={sig['score']} | Conf={sig['confidence']}")
                log.info(f"   Reason: {sig['reason']}")

                # Monitor open position
                if symbol in self.trades:
                    self.monitor_position(symbol, price, candles)
                    continue

                if len(self.trades) >= MAX_OPEN: continue

                # Entry logic
                if sig["signal"] == "BUY" and sig["confidence"] in ["HIGH", "MEDIUM"]:
                    log.info(f"🤖 AI Entry confirmation...")
                    ai_sig, ai_reason = ai_entry(symbol, price, sig)
                    log.info(f"🤖 AI: {ai_sig} | {ai_reason[:80]}")

                    if ai_sig != "BUY":
                        log.info(f"🛑 AI skip entry ({ai_sig})")
                        continue

                    log.info(f"⚡ ENTRY! AI confirmed BUY")
                    order = market_buy(symbol, balance)

                    if order and order.get("orderId"):
                        fills = order.get("fills", [])
                        entry_price = float(fills[0]["price"]) if fills else price
                        qty = float(order.get("executedQty", 0))
                        tp  = round(entry_price * (1 + TP_PCT), 2)
                        sl  = round(entry_price * (1 - SL_PCT), 2)

                        self.trades[symbol]  = {"entry": entry_price, "qty": qty, "tp": tp, "sl": sl}
                        self.highest[symbol] = entry_price

                        log.info(f"✅ BUY OK | Entry=${entry_price:,.2f} | Qty={qty}")
                        log.info(f"   TP=${tp:,.2f} (+{TP_PCT*100}%) | SL=${sl:,.2f} (-{SL_PCT*100}%)")
                        log.info(f"   Trailing aktif setelah +{TRAIL_ACTIVATE*100}%")

                        log_trade(symbol, "BUY", entry_price, entry_price, qty, 0, 0, "OPEN")
                    else:
                        log.error(f"❌ BUY gagal: {order}")

            except Exception as e:
                log.error(f"❌ {symbol} error: {e}", exc_info=True)

    def start(self, restore_trade=None):
        log.info("🚀 VYORA BOT v5.0 STARTED")
        log.info(f"   Strategy: EMA+RSI+MACD+BB+Volume + Groq AI")
        log.info(f"   Exit: Trailing Stop + AI Analysis")
        log.info(f"   TP: {TP_PCT*100}% | SL: {SL_PCT*100}% | Trail: {TRAIL_PCT*100}%")

        if restore_trade:
            symbol = restore_trade["symbol"]
            self.trades[symbol]  = restore_trade
            self.highest[symbol] = restore_trade.get("highest", restore_trade["entry"])
            log.info(f"📌 Restored: {symbol} | Entry=${restore_trade['entry']:,.2f} | Qty={restore_trade['qty']}")

        cycle = 1
        while True:
            try:
                self.run_cycle(cycle)
            except KeyboardInterrupt:
                log.info("🛑 Bot stopped by user")
                sync_firestore(get_balance(), self.stats["pnl"],
                              self.stats["total"], self.stats["wins"], cycle, "STOPPED")
                break
            except Exception as e:
                log.error(f"❌ Cycle error: {e}", exc_info=True)

            log.info(f"\n⏳ Next cycle in {INTERVAL_MINS} min... (Ctrl+C to stop)\n")
            time.sleep(INTERVAL_MINS * 60)
            cycle += 1

if __name__ == "__main__":
    bot = VyoraBot()
    bot.start(restore_trade={
        "symbol":  "BTCUSDT",
        "entry":   78457.81,
        "qty":     0.00015,
        "tp":      round(78457.81 * 1.03, 2),
        "sl":      round(78457.81 * 0.985, 2),
        "highest": 78457.81
    })

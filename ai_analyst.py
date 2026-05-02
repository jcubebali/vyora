import os, requests

GROQ_KEY = os.environ.get("GROQ_API_KEY", "")
MODEL = "llama-3.3-70b-versatile"

def ai_analyze(symbol, price, rsi, ema20, ema50, ema200, macd_hist, volume_ratio, trend_1h=""):
    prompt = f"""Kamu adalah trader crypto profesional dengan pengalaman 10 tahun.

Analisa teknikal {symbol}:
- Harga: ${price:,.2f}
- EMA20: ${ema20:,.2f} | EMA50: ${ema50:,.2f} | EMA200: ${ema200:,.2f}
- RSI(14): {rsi:.1f}
- MACD Histogram: {macd_hist:.2f}
- Volume: {volume_ratio:.2f}x rata-rata
- Trend 1H: {trend_1h}

Berikan analisa dalam format:
SIGNAL: [BUY/SELL/HOLD]
CONFIDENCE: [HIGH/MEDIUM/LOW]
ALASAN: [2-3 kalimat penjelasan]
RISIKO: [1 kalimat risiko utama]"""

    try:
        r = requests.post(
            "https://api.groq.com/openai/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {GROQ_KEY}",
                "Content-Type": "application/json"
            },
            json={
                "model": MODEL,
                "messages": [
                    {"role": "system", "content": "Kamu adalah trader crypto profesional. Selalu jawab dalam format yang diminta."},
                    {"role": "user", "content": prompt}
                ],
                "max_tokens": 300,
                "temperature": 0.2
            },
            timeout=30
        )
        data = r.json()
        if "choices" in data:
            text = data["choices"][0]["message"]["content"]
            # Parse signal
            signal = "HOLD"
            confidence = "LOW"
            if "SIGNAL: BUY" in text or "SIGNAL:BUY" in text: signal = "BUY"
            elif "SIGNAL: SELL" in text or "SIGNAL:SELL" in text: signal = "SELL"
            if "HIGH" in text: confidence = "HIGH"
            elif "MEDIUM" in text: confidence = "MEDIUM"
            return {"signal": signal, "confidence": confidence, "analysis": text, "ok": True}
        return {"signal": "HOLD", "confidence": "LOW", "analysis": "AI tidak tersedia", "ok": False}
    except Exception as e:
        return {"signal": "HOLD", "confidence": "LOW", "analysis": f"Error: {e}", "ok": False}

if __name__ == "__main__":
    result = ai_analyze("BTCUSDT", 78298, 53.86, 78256, 78217, 77125, -29, 0.19, "Uptrend lemah")
    print(result["analysis"])

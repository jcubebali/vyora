import json, time, os
import urllib.request
import jwt
from cryptography.hazmat.primitives import serialization

SA_FILE = os.path.expanduser("~/binance_bot/serviceAccount.json")
PROJECT = "nexus-trade-e449e"
UID = open(os.path.expanduser("~/.nexus_uid")).read().strip()
FIRESTORE = f"https://firestore.googleapis.com/v1/projects/{PROJECT}/databases/(default)/documents"

def get_token():
    sa = json.load(open(SA_FILE))
    now = int(time.time())
    payload = {
        "iss": sa["client_email"],
        "sub": sa["client_email"],
        "aud": "https://oauth2.googleapis.com/token",
        "iat": now,
        "exp": now + 3600,
        "scope": "https://www.googleapis.com/auth/datastore"
    }
    private_key = serialization.load_pem_private_key(
        sa["private_key"].encode(), password=None
    )
    assertion = jwt.encode(payload, private_key, algorithm="RS256")
    data = f"grant_type=urn%3Aietf%3Aparams%3Aoauth%3Agrant-type%3Ajwt-bearer&assertion={assertion}".encode()
    req = urllib.request.Request("https://oauth2.googleapis.com/token", data=data)
    with urllib.request.urlopen(req) as r:
        return json.loads(r.read())["access_token"]

def patch(path, fields):
    token = get_token()
    mask = "&".join(f"updateMask.fieldPaths={k}" for k in fields)
    url = f"{FIRESTORE}/{path}?{mask}"
    doc = {"fields": {}}
    for k, v in fields.items():
        if isinstance(v, float): doc["fields"][k] = {"doubleValue": v}
        elif isinstance(v, int): doc["fields"][k] = {"integerValue": str(v)}
        else: doc["fields"][k] = {"stringValue": str(v)}
    body = json.dumps(doc).encode()
    req = urllib.request.Request(url, data=body, headers={
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }, method="PATCH")
    with urllib.request.urlopen(req) as r:
        return r.status

def update_balance(total_usdt, total_pnl, total_trades, wins):
    wr = round(wins/total_trades*100, 1) if total_trades > 0 else 0.0
    code = patch(f"users/{UID}", {
        "totalUsdt": float(total_usdt),
        "totalPnl": float(total_pnl),
        "totalTrades": int(total_trades),
        "winRate": float(wr),
    })
    if code == 200:
        print(f"[NEXUS] ✅ bal=${total_usdt:.2f} pnl={total_pnl:+.4f} wr={wr}%")
    else:
        print(f"[NEXUS] ❌ Error: {code}")

if __name__ == "__main__":
    bal    = float(input("Balance USDT: ") or "0")
    pnl    = float(input("Total PnL: ") or "0")
    trades = int(input("Total trades: ") or "0")
    wins   = int(input("Total wins: ") or "0")
    update_balance(bal, pnl, trades, wins)

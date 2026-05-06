"""
VYORA — User Activation Script
Jalankan: python3 activate_user.py
"""
import json, time, os, urllib.request
import jwt
from cryptography.hazmat.primitives import serialization

def get_token():
    SA = os.path.expanduser("~/binance_bot/serviceAccount.json")
    sa = json.load(open(SA))
    now = int(time.time())
    payload = {
        "iss": sa["client_email"], "sub": sa["client_email"],
        "aud": "https://oauth2.googleapis.com/token",
        "iat": now, "exp": now + 3600,
        "scope": "https://www.googleapis.com/auth/datastore"
    }
    key = serialization.load_pem_private_key(sa["private_key"].encode(), password=None)
    assertion = jwt.encode(payload, key, algorithm="RS256")
    data = f"grant_type=urn%3Aietf%3Aparams%3Aoauth%3Agrant-type%3Ajwt-bearer&assertion={assertion}".encode()
    with urllib.request.urlopen(urllib.request.Request("https://oauth2.googleapis.com/token", data=data)) as r:
        return json.loads(r.read())["access_token"]

def get_users(token):
    url = "https://firestore.googleapis.com/v1/projects/nexus-trade-e449e/databases/(default)/documents/users"
    req = urllib.request.Request(url, headers={"Authorization": f"Bearer {token}"})
    with urllib.request.urlopen(req) as r:
        docs = json.loads(r.read())
    users = []
    for doc in docs.get("documents", []):
        fields = doc.get("fields", {})
        uid = doc["name"].split("/")[-1]
        users.append({
            "uid": uid,
            "name": list(fields.get("name", {}).values())[0] if "name" in fields else "--",
            "email": list(fields.get("email", {}).values())[0] if "email" in fields else "--",
            "plan": list(fields.get("plan", {}).values())[0] if "plan" in fields else "trial",
        })
    return users

def activate_plan(token, uid, plan, months):
    from datetime import datetime, timedelta
    expiry = (datetime.now() + timedelta(days=30*months)).strftime("%Y-%m-%dT%H:%M:%SZ")
    doc = {"fields": {
        "plan": {"stringValue": plan},
        "planExpiry": {"stringValue": expiry},
        "lastPayment": {"stringValue": datetime.now().strftime("%Y-%m-%dT%H:%M:%SZ")}
    }}
    mask = "updateMask.fieldPaths=plan&updateMask.fieldPaths=planExpiry&updateMask.fieldPaths=lastPayment"
    url = f"https://firestore.googleapis.com/v1/projects/nexus-trade-e449e/databases/(default)/documents/users/{uid}?{mask}"
    req = urllib.request.Request(url, data=json.dumps(doc).encode(),
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        method="PATCH")
    urllib.request.urlopen(req)
    return expiry

def main():
    print("\n" + "="*50)
    print("  VYORA — USER ACTIVATION PANEL")
    print("="*50)

    print("\n⏳ Loading users...")
    token = get_token()
    users = get_users(token)

    print(f"\n📋 DAFTAR USER ({len(users)} total):")
    print(f"{'No':<4} {'Nama':<20} {'Email':<30} {'Plan':<10}")
    print("-"*65)
    for i, u in enumerate(users):
        plan_icon = "🟢" if u["plan"] in ["pro","elite"] else "🟡" if u["plan"] == "basic" else "⚪"
        print(f"{i+1:<4} {u['name'][:18]:<20} {u['email'][:28]:<30} {plan_icon} {u['plan']}")

    print("\n" + "-"*65)
    try:
        choice = int(input("\nPilih nomor user (0 untuk cancel): "))
        if choice == 0:
            print("Cancelled.")
            return
        if choice < 1 or choice > len(users):
            print("❌ Nomor tidak valid!")
            return
    except ValueError:
        print("❌ Input tidak valid!")
        return

    user = users[choice-1]
    print(f"\n👤 User: {user['name']} ({user['email']})")
    print(f"   Plan saat ini: {user['plan']}")

    print("\nPilih plan baru:")
    print("  1. Basic   — Rp99.000/bulan")
    print("  2. Pro     — Rp199.000/bulan")
    print("  3. Elite   — Rp499.000/bulan")
    print("  4. Trial   — Reset trial")

    try:
        plan_choice = int(input("\nPilih (1-4): "))
        plans = {1:"basic", 2:"pro", 3:"elite", 4:"trial"}
        if plan_choice not in plans:
            print("❌ Pilihan tidak valid!")
            return
        plan = plans[plan_choice]
    except ValueError:
        print("❌ Input tidak valid!")
        return

    try:
        months = int(input("Berapa bulan? (1/3/6/12): "))
    except ValueError:
        months = 1

    print(f"\n⚠️  Konfirmasi:")
    print(f"   User  : {user['name']} ({user['email']})")
    print(f"   Plan  : {user['plan']} → {plan.upper()}")
    print(f"   Durasi: {months} bulan")

    confirm = input("\nLanjutkan? (y/n): ")
    if confirm.lower() != 'y':
        print("Cancelled.")
        return

    expiry = activate_plan(token, user['uid'], plan, months)
    print(f"\n✅ BERHASIL!")
    print(f"   {user['name']} → {plan.upper()}")
    print(f"   Aktif sampai: {expiry[:10]}")
    print("\n" + "="*50)

if __name__ == "__main__":
    main()

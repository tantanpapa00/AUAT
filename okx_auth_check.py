# okx_auth_check.py
# Run in the SAME PowerShell session where env vars are set.
#   cd C:\autobot
#   python .\okx_auth_check.py

import os, json, base64, hmac, requests
from datetime import datetime

def ts():
    return datetime.utcnow().isoformat(timespec="milliseconds") + "Z"

def sign(secret: str, prehash: str) -> str:
    mac = hmac.new(secret.encode("utf-8"), prehash.encode("utf-8"), digestmod="sha256").digest()
    return base64.b64encode(mac).decode("utf-8")

def headers(t, s, key, passphrase, simulated):
    h = {
        "Content-Type": "application/json",
        "OK-ACCESS-KEY": key,
        "OK-ACCESS-SIGN": s,
        "OK-ACCESS-TIMESTAMP": t,
        "OK-ACCESS-PASSPHRASE": passphrase,
    }
    if simulated == "1":
        h["x-simulated-trading"] = "1"
    return h

def main():
    base = os.getenv("OKX_BASE_URL", "https://www.okx.com").rstrip("/")
    key = (os.getenv("OKX_API_KEY") or "").strip()
    sec = (os.getenv("OKX_API_SECRET") or "").strip()
    pas = (os.getenv("OKX_API_PASSPHRASE") or "").strip()
    sim = (os.getenv("OKX_SIMULATED") or "0").strip()

    if not (key and sec and pas):
        print("ERROR: missing OKX_API_KEY/OKX_API_SECRET/OKX_API_PASSPHRASE")
        return

    # auth-required endpoint (no trading): account balance
    path = "/api/v5/account/balance"
    query = "ccy=USDT"
    url = f"{base}{path}?{query}"

    t = ts()
    prehash = f"{t}GET{path}?{query}"
    s = sign(sec, prehash)
    h = headers(t, s, key, pas, sim)

    print(f"OKX_BASE_URL={base}")
    print(f"OKX_SIMULATED={sim}")
    print(f"OKX_API_KEY(prefix)={key[:6]}...")

    try:
        r = requests.get(url, headers=h, timeout=10)
        print("HTTP", r.status_code)
        txt = r.text
        try:
            j = r.json()
            print("code:", j.get("code"), "msg:", j.get("msg"))
        except Exception:
            print("body:", txt[:500])
    except Exception as e:
        print("REQUEST ERROR:", e)

if __name__ == "__main__":
    main()

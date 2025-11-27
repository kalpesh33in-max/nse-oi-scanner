# nifty.py → KALPE BHAI NIFTY OI SCANNER → NEVER STOPS + AUTO RECOVER (NOV 2025)
import os
import time
import threading
import requests
import pytz
from datetime import datetime, time as dtime

# ================== CONFIG ==================
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
CHAT_IDS = [int(x.strip()) for x in os.environ.get("TELEGRAM_CHAT_IDS", "").split(",") if x.strip()]

NIFTY_LOT = 25
ATM_RANGE = 400

MODES = {
    "AGGRESSIVE": {"OI": 10, "LOTS": 4,  "IVROC": 8},
    "MODERATE":   {"OI": 16, "LOTS": 8,  "IVROC": 13},
    "SAFE":       {"OI": 25, "LOTS": 12, "IVROC": 20},
}

SUPER_A = {"SPIKE": 45, "LOTS": 15, "IVROC": 28}
SUPER_B = {"SPIKE": 80, "LOTS": 25, "IVROC": 45}

# ================== NSE SESSION ==================
session = requests.Session()
session.headers.update({
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Accept": "application/json, text/plain, */*",
    "Referer": "https://www.nseindia.com/option-chain",
    "Origin": "https://www.nseindia.com",
    "X-Requested-With": "XMLHttpRequest",
})

def refresh_nse():
    try:
        session.get("https://www.nseindia.com", timeout=15)
        print(f"[NSE] Cookies refreshed → {now_ist().strftime('%H:%M:%S')}")
    except:
        pass

refresh_nse()

# ================== TIME ==================
IST = pytz.timezone("Asia/Kolkata")
def now_ist(): return datetime.now(IST)
def market_open():
    n = now_ist()
    return n.weekday() < 5 and dtime(9, 15) <= n.time() <= dtime(15, 30)

# ================== TELEGRAM ==================
def send(msg):
    if not TELEGRAM_TOKEN or not CHAT_IDS:
        print("TG OFF →", msg.replace("\n"," ")[:120])
        return
    for cid in CHAT_IDS:
        try:
            requests.post(f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
                         json={"chat_id": cid, "text": msg, "parse_mode": "Markdown"}, timeout=10)
        except:
            pass
    print("SENT →", msg.split("\n")[0])

# ================== DATA CACHE ==================
lock = threading.Lock()
latest = None
blocked = False

def fetch_data():
    global latest, blocked
    urls = [
        "https://www.nseindia.com/api/option-chain-indices?symbol=NIFTY",
        "https://www.nseindia.com/api/option-chain-v3?type=Indices&symbol=NIFTY"
    ]
    for url in urls:
        try:
            refresh_nse()
            time.sleep(1.8)
            r = session.get(url, timeout=20)
            if r.status_code != 200:
                continue
            j = r.json()
            records = j.get("records") or j.get("filtered") or {}
            data = records.get("data") or []
            spot = records.get("underlyingValue") or j.get("underlyingValue") or 0
            if data and spot:
                with lock:
                    latest = (data, round(spot), time.time())
                if blocked:
                    send("NSE UNBLOCKED! Scanner FULL POWER ON!")
                    blocked = False
                print(f"[OK] Spot {spot} | {len(data)} strikes | {now_ist().strftime('%H:%M:%S')}")
                return True
        except Exception as e:
            print(f"[FAIL] {e}")
    if not blocked:
        blocked = True
        send("NSE BLOCKED! Auto-retrying every 30s...")
    return False

def fetch_loop():
    while True:
        if market_open():
            fetch_data()
            time.sleep(34)
        else:
            time.sleep(40)

# ================== SCANNER ==================
def run_scanner(mode_name, cfg):
    hist = {}
    cooldown = {}
    send(f"*{mode_name} MODE ACTIVATED*\nOI ≥ {cfg['OI']}%, ≥ {cfg['LOTS']} lots, IV ROC ≥ {cfg['IVROC']}%")

    while True:
        time.sleep(1)
        if not market_open() or not latest:
            continue
        data, spot, ts = latest
        if time.time() - ts > 120:
            continue

        for row in data:
            strike = row["strikePrice"]
            if abs(strike - spot) > ATM_RANGE:
                continue
            for typ in ("CE", "PE"):
                opt = row.get(typ)
                if not opt: continue
                key = f"{strike}_{typ}_{row['expiryDate']}"
                oi = opt["openInterest"]
                chg = opt["changeinOpenInterest"]
                vol = opt["totalTradedVolume"]
                iv = opt.get("impliedVolatility") or 0
                lots = abs(chg) // NIFTY_LOT
                sign = "BUYERS" if chg > 0 else "WRITERS" if chg < 0 else "NEUTRAL"

                if key not in hist:
                    hist[key] = {"oi": oi, "iv": iv}
                    continue

                old = hist[key]
                spike = (oi - old["oi"]) / old["oi"] * 100 if old["oi"] > 0 else 0
                iv_roc = (iv - old["iv"]) / old["iv"] * 100 if old["iv"] > 0 else 0

                now = time.time()
                if now - cooldown.get(key, 0) < 80:
                    hist[key] = {"oi": oi, "iv": iv}
                    continue

                # SUPER B
                if (spike >= SUPER_B["SPIKE"] or abs(iv_roc) >= SUPER_B["IVROC"]) and lots >= SUPER_B["LOTS"]:
                    send(f"""
EXTREME BLAST!!!
*NIFTY {strike} {typ}* 
OI +{spike:.1f}% | {lots} lots | IV ROC {iv_roc:+.1f}%
Side: *{sign}*
Time: {now_ist().strftime('%H:%M:%S')}
                    """)
                    cooldown[key] = now

                # SUPER A
                elif (spike >= SUPER_A["SPIKE"] or abs(iv_roc) >= SUPER_A["IVROC"]) and lots >= SUPER_A["LOTS"]:
                    send(f"""
SUPER SPIKE!!!
*NIFTY {strike} {typ}* → {lots} lots
OI +{spike:.1f}% | IV ROC {iv_roc:+.1f}%
Side: {sign} | {now_ist().strftime('%H:%M:%S')}
                    """)
                    cooldown[key] = now

                # NORMAL
                elif spike >= cfg["OI"] and lots >= cfg["LOTS"] and abs(iv_roc) >= cfg["IVROC"]:
                    direction = "BULLISH" if (typ=="CE" and sign=="BUYERS") or (typ=="PE" and sign=="WRITERS") else "BEARISH"
                    send(f"""
[{mode_name}] *ALERT*
*NIFTY {strike} {typ}* → {direction}
+{spike:.1f}% OI | {lots} lots | IV ROC {iv_roc:+.1f}%
Time: {now_ist().strftime('%H:%M:%S')}
                    """)
                    cooldown[key] = now

                hist[key] = {"oi": oi, "iv": iv}

# ================== MAIN → NEVER DIES ==================
def heartbeat():
    while True:
        print(f"ALIVE & SCANNING → {now_ist()}")
        time.sleep(60)

def main():
    send("KALPE BHAI SCANNER STARTED → WILL RUN FOREVER!")
    threading.Thread(target=fetch_loop, daemon=True).start()
    threading.Thread(target=heartbeat, daemon=True).start()
    for mode, cfg in MODES.items():
        threading.Thread(target=run_scanner, args=(mode, cfg), daemon=True).start()
    # This keeps process alive forever
    while True:
        time.sleep(99999)

if __name__ == "__main__":
    main()

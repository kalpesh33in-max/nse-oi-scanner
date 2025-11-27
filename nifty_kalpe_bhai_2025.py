# nifty_kalpe_bhai_2025_final.py → KALPE BHAI NIFTY OI SCANNER → UNKILLABLE EDITION (NOV 2025)
import os
import time
import threading
import requests
import pytz
from datetime import datetime, time as dtime, timedelta

# ================== CONFIG ==================
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
CHAT_IDS = [int(x.strip()) for x in os.environ.get("TELEGRAM_CHAT_IDS", "").split(",") if x.strip()]
NIFTY_LOT = 25
ATM_RANGE = 450
COOLDOWN_SEC = 65  # Reduced from 80s → faster alerts

MODES = {
    "AGGRESSIVE": {"OI": 10, "LOTS": 4,  "IVROC": 8},
    "MODERATE":   {"OI": 16, "LOTS": 8,  "IVROC": 13},
    "SAFE":       {"OI": 25, "LOTS": 12, "IVROC": 20},
}

SUPER_A = {"SPIKE": 45, "LOTS": 15, "IVROC": 28}
SUPER_B = {"SPIKE": 80, "LOTS": 25, "IVROC": 45}

# ================== NSE SESSION (2025 ANTI-BLOCK) ==================
session = requests.Session()

def get_rotating_headers():
    agents = [
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0 Safari/537.36",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_6_1) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.0 Safari/605.1.15",
        "Mozilla/5.0 (X11; Linux x86_64; rv:131.0) Gecko/20100101 Firefox/131.0",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:131.0) Gecko/20100101 Firefox/131.0"
    ]
    return {
        "User-Agent": agents[int(time.time()) % len(agents)],
        "Accept": "application/json, text/plain, */*",
        "Accept-Encoding": "gzip, deflate, br",
        "Accept-Language": "en-US,en;q=0.9",
        "Referer": "https://www.nseindia.com/option-chain",
        "Origin": "https://www.nseindia.com",
        "X-Requested-With": "XMLHttpRequest",
        "Connection": "keep-alive",
        "sec-ch-ua": '"Google Chrome";v="131", "Chromium";v="131", "Not=A?Brand";v="24"',
        "sec-ch-ua-mobile": "?0",
        "sec-ch-ua-platform": '"Windows"',
        "sec-fetch-dest": "empty",
        "sec-fetch-mode": "cors",
        "sec-fetch-site": "same-origin",
    }

def refresh_nse():
    try:
        session.headers.update(get_rotating_headers())
        session.get("https://www.nseindia.com", timeout=15)
        time.sleep(1)
        session.get("https://www.nseindia.com/option-chain", timeout=15)
        print(f"[NSE] Session refreshed → {now_ist().strftime('%H:%M:%S')}")
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
        print("TG OFF →", msg.replace("\n", " ").replace("*", "")[:140])
        return
    for cid in CHAT_IDS:
        try:
            requests.post(
                f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
                json={"chat_id": cid, "text": msg, "parse_mode": "Markdown", "disable_web_page_preview": True},
                timeout=10
            )
        except:
            pass
    print("SENT →", msg.strip().split("\n")[0])

# ================== DATA CACHE ==================
lock = threading.Lock()
latest = None
blocked = False
last_pcr_time = 0

def fetch_data():
    global latest, blocked, last_pcr_time
    urls = [
        "https://www.nseindia.com/api/option-chain-indices?symbol=NIFTY",
        "https://www.nseindia.com/api/option-chain-v3?type=Indices&symbol=NIFTY",
    ]
    for url in urls:
        try:
            refresh_nse()
            time.sleep(2)
            session.headers.update(get_rotating_headers())
            r = session.get(url, timeout=20)
            if r.status_code != 200:
                continue
            j = r.json()
            records = j.get("records") or j.get("filtered") or {}
            data = records.get("data") or []
            spot = round(records.get("underlyingValue") or j.get("underlyingValue") or 0)
            timestamp = records.get("timestamp") or now_ist().strftime("%d-%b-%Y %H:%M:%S")

            if data and spot > 15000:  # sanity check
                with lock:
                    latest = (data, spot, time.time(), timestamp)
                if blocked:
                    send("NSE UNBLOCKED! KALPE BHAI BACK IN ACTION!")
                    blocked = False
                print(f"[OK] NIFTY {spot} | {len(data)} strikes | {now_ist().strftime('%H:%M:%S')}")
                
                # === PCR ALERT (every 2 mins) ===
                if time.time() - last_pcr_time > 120:
                    try:
                        ce_oi = sum(d["CE"]["openInterest"] for d in data if "CE" in d and abs(d["strikePrice"] - spot) <= 800)
                        pe_oi = sum(d["PE"]["openInterest"] for d in data if "PE" in d and abs(d["strikePrice"] - spot) <= 800)
                        pcr = round(pe_oi / ce_oi, 2) if ce_oi > 0 else 99
                        if pcr < 0.70:
                            send(f"PCR DUMP → *{pcr}* → STRONG BULLISH BIAS")
                        elif pcr > 1.40:
                            send(f"PCR SPIKE → *{pcr}* → STRONG BEARISH BIAS")
                        last_pcr_time = time.time()
                    except:
                        pass
                
                return True
        except Exception as e:
            print(f"[FAIL] {url[-40:]} → {e}")
    
    if not blocked:
        blocked = True
        send("NSE BLOCKED! Kalpe Bhai is fighting back... Auto-retrying...")
    return False

def fetch_loop():
    while True:
        if market_open():
            fetch_data()
            time.sleep(36)
        else:
            time.sleep(60)

# ================== SCANNER CORE ==================
def run_scanner(mode_name, cfg):
    hist = {}
    cooldown = {}
    send(f"*{mode_name.upper()} MODE ACTIVATED*\nOI ≥ {cfg['OI']}%, ≥ {cfg['LOTS']} lots, IV ROC ≥ {cfg['IVROC']}%")
    
    while True:
        time.sleep(1)
        if not market_open() or not latest:
            continue
        
        data, spot, ts, timestamp = latest
        if time.time() - ts > 150:
            continue

        # Get current + next weekly expiry only
        expiries = sorted(set(row["expiryDate"] for row in data))
        allowed_expiries = expiries[:2]  # Current + next week

        for row in data:
            if row["expiryDate"] not in allowed_expiries:
                continue
            if abs(row["strikePrice"] - spot) > ATM_RANGE:
                continue

            for typ in ("CE", "PE"):
                opt = row.get(typ)
                if not opt or opt["openInterest"] < 1000:  # filter junk
                    continue

                key = f"{row['strikePrice']}_{typ}_{row['expiryDate']}"
                oi = opt["openInterest"]
                chg = opt["changeinOpenInterest"]
                iv = opt.get("impliedVolatility") or 0
                lots = abs(chg) // NIFTY_LOT
                sign = "BUYERS" if chg > 0 else "WRITERS" if chg < 0 else "NEUTRAL"

                if key not in hist:
                    hist[key] = {"oi": oi, "iv": iv}
                    continue

                old_oi = hist[key]["oi"]
                old_iv = hist[key]["iv"] or 0.1
                spike = (oi - old_oi) / old_oi * 100 if old_oi > 0 else 0
                iv_roc = (iv - old_iv) / old_iv * 100 if old_iv > 0 else 0

                now = time.time()
                if now - cooldown.get(key, 0) < COOLDOWN_SEC:
                    hist[key] = {"oi": oi, "iv": iv}
                    continue

                direction = "BULLISH" if (typ == "CE" and sign == "BUYERS") or (typ == "PE" and sign == "WRITERS") else "BEARISH"

                # SUPER B → EXTREME
                if (spike >= SUPER_B["SPIKE"] or abs(iv_roc) >= SUPER_B["IVROC"]) and lots >= SUPER_B["LOTS"]:
                    send(f"""
EXTREME BLAST DETECTED!!!
*NIFTY {row['strikePrice']} {typ}* ({row['expiryDate']})
OI +{spike:.1f}% → {lots} lots | IV ROC {iv_roc:+.1f}%
Side: *{sign}* | Direction: *{direction}*
Time: {now_ist().strftime('%H:%M:%S')}
                    """)
                    cooldown[key] = now

                # SUPER A
                elif (spike >= SUPER_A["SPIKE"] or abs(iv_roc) >= SUPER_A["IVROC"]) and lots >= SUPER_A["LOTS"]:
                    send(f"""
SUPER SPIKE!!!
*NIFTY {row['strikePrice']} {typ}* → {lots} lots
OI +{spike:.1f}% | IV ROC {iv_roc:+.1f}%
Side: {sign} | {direction}
Time: {now_ist().strftime('%H:%M:%S')}
                    """)
                    cooldown[key] = now

                # NORMAL ALERT
                elif spike >= cfg["OI"] and lots >= cfg["LOTS"] and abs(iv_roc) >= cfg["IVROC"]:
                    send(f"""
[{mode_name}] ALERT
*NIFTY {row['strikePrice']} {typ}* → {direction}
OI +{spike:.1f}% | {lots} lots | IV ROC {iv_roc:+.1f}%
Expiry: {row['expiryDate']}
Time: {now_ist().strftime('%H:%M:%S')}
                    """)
                    cooldown[key] = now

                hist[key] = {"oi": oi, "iv": iv}

# ================== HEARTBEAT & MAIN ==================
def heartbeat():
    while True:
        print(f"KALPE BHAI SCANNER ALIVE → {now_ist().strftime('%d-%b %H:%M:%S')}")
        time.sleep(60)

def main():
    send("KALPE BHAI NIFTY SCANNER 2025 STARTED!\nUNBLOCKABLE • UNSTOPPABLE • AUTO-RECOVER\nRunning AGGRESSIVE + MODERATE + SAFE modes + PCR + SUPER alerts")
    
    threading.Thread(target=fetch_loop, daemon=True).start()
    threading.Thread(target=heartbeat, daemon=True).start()
    
    for mode, cfg in MODES.items():
        threading.Thread(target=run_scanner, args=(mode, cfg), daemon=True).start()
    
    # Keep alive forever
    while True:
        time.sleep(99999)

if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        send(f"CRITICAL ERROR! Restarting... {e}")
        time.sleep(10)
        main()

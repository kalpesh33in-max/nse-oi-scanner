# nifty_kalpe_bhai_2025_75lot_threadsafe.py

import os
import time
import threading
import requests
import pytz
from datetime import datetime, time as dtime

def run_kalpe_2025_scanner():

    # ================== CONFIG ==================
    TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
    CHAT_IDS = [int(x.strip()) for x in os.environ.get("TELEGRAM_CHAT_IDS", "").split(",") if x.strip()]

    NIFTY_LOT = 75
    ATM_RANGE = 450
    COOLDOWN_SEC = 65

    MODES = {
        "AGGRESSIVE": {"OI": 10, "LOTS": 12, "IVROC": 8},
        "MODERATE": {"OI": 16, "LOTS": 25, "IVROC": 13},
        "SAFE": {"OI": 25, "LOTS": 38, "IVROC": 20},
    }

    SUPER_A = {"SPIKE": 45, "LOTS": 45, "IVROC": 28}
    SUPER_B = {"SPIKE": 80, "LOTS": 75, "IVROC": 45}

    IST = pytz.timezone("Asia/Kolkata")
    session = requests.Session()

    def now_ist():
        return datetime.now(IST)

    # ================== MARKET TIME ==================
    def market_open():
        t = now_ist()
        return t.weekday() < 5 and dtime(9, 15) <= t.time() <= dtime(15, 30)

    # ================== TELEGRAM ==================
    def send(msg):
        if not TELEGRAM_TOKEN or not CHAT_IDS:
            print("TG OFF:", msg[:120])
            return
        for cid in CHAT_IDS:
            try:
                requests.post(
                    f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
                    json={"chat_id": cid, "text": msg, "parse_mode": "Markdown"},
                    timeout=10
                )
            except Exception as e:
                print("[TG ERROR]", e)

    # ================== ROTATING HEADERS ==================
    def get_headers():
        agents = [
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/131",
            "Mozilla/5.0 (Macintosh; Intel Mac OS X) Safari/605",
            "Mozilla/5.0 (X11; Linux x86_64) Firefox/131",
            "Mozilla/5.0 (Windows NT 10.0) Firefox/131"
        ]
        return {
            "User-Agent": agents[int(time.time()) % len(agents)],
            "Accept": "*/*",
            "Referer": "https://www.nseindia.com/option-chain",
        }

    # ================== REFRESH NSE ==================
    def refresh_nse():
        try:
            session.headers.update(get_headers())
            session.get("https://www.nseindia.com", timeout=10)
            time.sleep(1)
        except:
            pass

    refresh_nse()

    # ================== DATA CACHE ==================
    lock = threading.Lock()
    latest = None
    blocked = False
    last_pcr_time = 0

    # ---------------- FETCH DATA ----------------
    def fetch_data():
        nonlocal latest, blocked, last_pcr_time

        urls = [
            "https://www.nseindia.com/api/option-chain-indices?symbol=NIFTY",
            "https://www.nseindia.com/api/option-chain-v3?type=Indices&symbol=NIFTY",
        ]

        for url in urls:
            try:
                refresh_nse()
                session.headers.update(get_headers())
                r = session.get(url, timeout=15)
                if r.status_code != 200:
                    continue

                j = r.json()
                records = j.get("records") or j.get("filtered") or {}
                data = records.get("data") or []
                spot = round(records.get("underlyingValue") or 0)

                if data and spot > 15000:
                    with lock:
                        latest = (data, spot, time.time())

                    if blocked:
                        send("🟢 NSE UNBLOCKED — Kalpe Scanner Running Again")
                        blocked = False

                    return True
            except:
                continue

        if not blocked:
            blocked = True
            send("🔴 NSE BLOCKED — Retrying...")

        return False

    def fetch_loop():
        while True:
            if market_open():
                fetch_data()
                time.sleep(35)
            else:
                time.sleep(50)

    # ------------------ MODE SCANNER --------------------
    def run_mode(mode_name, cfg):
        hist = {}
        cooldown = {}

        send(f"*{mode_name} MODE ACTIVE* — OI {cfg['OI']}%, LOTS ≥ {cfg['LOTS']}")

        while True:
            time.sleep(1)
            if not market_open() or not latest:
                continue

            data, spot, ts = latest
            if time.time() - ts > 120:
                continue

            for row in data:
                strike = row["strikePrice"]
                expiry = row["expiryDate"]

                if abs(strike - spot) > ATM_RANGE:
                    continue

                for typ in ("CE", "PE"):
                    opt = row.get(typ)
                    if not opt:
                        continue

                    key = f"{strike}_{typ}_{expiry}"
                    oi = opt["openInterest"]
                    iv = opt.get("impliedVolatility") or 0
                    chg = opt["changeinOpenInterest"]

                    lots = abs(chg) // NIFTY_LOT
                    spike = 0
                    roc = 0

                    if key in hist:
                        old = hist[key]
                        if old["oi"] > 0:
                            spike = (oi - old["oi"]) / old["oi"] * 100
                        if old["iv"] > 0:
                            roc = (iv - old["iv"]) / old["iv"] * 100

                    now_t = time.time()
                    if now_t - cooldown.get(key, 0) < COOLDOWN_SEC:
                        hist[key] = {"oi": oi, "iv": iv}
                        continue

                    # SUPER B
                    if spike >= SUPER_B["SPIKE"] and lots >= SUPER_B["LOTS"]:
                        send(f"🚨 EXTREME SPIKE — {strike} {typ} | {lots} lots | {spike:.1f}% OI")
                        cooldown[key] = now_t

                    # SUPER A
                    elif spike >= SUPER_A["SPIKE"] and lots >= SUPER_A["LOTS"]:
                        send(f"🔥 SUPER SPIKE — {strike} {typ} | {lots} lots | {spike:.1f}%")
                        cooldown[key] = now_t

                    # NORMAL
                    elif spike >= cfg["OI"] and lots >= cfg["LOTS"]:
                        send(f"[{mode_name}] {strike} {typ} | {lots} lots | {spike:.1f}%")
                        cooldown[key] = now_t

                    hist[key] = {"oi": oi, "iv": iv}

    # ---------------- HEARTBEAT ----------------
    def heartbeat():
        while True:
            print("KALPE 2025 Scanner alive:", now_ist())
            time.sleep(60)

    # ---------------- MAIN LOOP ----------------
    def main():
        send("🚀 KALPE BHAI 2025 NIFTY SCANNER STARTED (75 LOT UPDATE)")

        threading.Thread(target=fetch_loop, daemon=True).start()
        threading.Thread(target=heartbeat, daemon=True).start()

        for mode, cfg in MODES.items():
            threading.Thread(target=run_mode, args=(mode, cfg), daemon=True).start()

        while True:
            time.sleep(99999)

    main()


if __name__ == "__main__":
    run_kalpe_2025_scanner()

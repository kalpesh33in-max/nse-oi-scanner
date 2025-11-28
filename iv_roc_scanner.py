# iv_roc_scanner.py → KALPE BHAI IV ROC GREEN/RED DOT SCANNER
# Converted to run as normal function: run_iv_roc_scanner()

def run_iv_roc_scanner():
    import os
    import time
    import json
    import threading
    import pytz
    import requests
    from datetime import datetime, time as dtime

    # ================== TELEGRAM (Railway Variables) ==================
    TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN", "")
    CHAT_IDS_RAW = os.getenv("TELEGRAM_CHAT_IDS") or os.getenv("TELEGRAM_CHAT_ID", "")
    CHAT_IDS = [c.strip() for c in CHAT_IDS_RAW.split(",") if c.strip()]

    # simple sync telegram sender (no asyncio)
    def send(msg: str):
        if not TELEGRAM_TOKEN or not CHAT_IDS:
            print("IV ROC TG OFF →", msg.replace("\n", " ")[:120])
            return
        for chat in CHAT_IDS:
            try:
                requests.post(
                    f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
                    json={"chat_id": chat, "text": msg},
                    timeout=10,
                )
            except Exception as e:
                print("[IV ROC TG ERROR]", e)
        print("IV ROC →", msg.split("\n")[0])

    # ================== NSE SESSION ==================
    session = requests.Session()
    session.headers.update({
        "authority": "www.nseindia.com",
        "accept": "*/*",
        "accept-encoding": "gzip, deflate, br, zstd",
        "accept-language": "en-US,en;q=0.9",
        "referer": "https://www.nseindia.com/option-chain",
        "sec-ch-ua": '"Chromium";v="142", "Microsoft Edge";v="142", "Not_A Brand";v="99"',
        "sec-ch-ua-mobile": "?1",
        "sec-ch-ua-platform": '"Android"',
        "sec-fetch-dest": "empty",
        "sec-fetch-mode": "cors",
        "sec-fetch-site": "same-origin",
        "user-agent": (
            "Mozilla/5.0 (Linux; Android 6.0; Nexus 5 Build/MRA58N) "
            "AppleWebKit/537.36 Chrome/142.0.0.0 "
            "Mobile Safari/537.36 Edg/142.0.0.0"
        ),
    })

    # ================== CONFIG ==================
    INDICES = ["NIFTY", "BANKNIFTY", "SENSEX"]
    MIN_ROC = 5                   # minimum IV change to alert
    SCAN_INTERVAL = 180           # seconds between scans
    DATA_DIR = "data"
    DATA_FILE = os.path.join(DATA_DIR, "prev_iv.json")

    if not os.path.exists(DATA_DIR):
        os.makedirs(DATA_DIR, exist_ok=True)

    IST = pytz.timezone("Asia/Kolkata")

    def now_ist():
        return datetime.now(IST)

    def is_market_time():
        n = now_ist()
        if n.weekday() >= 5:
            return False
        t = n.time()
        return dtime(9, 15) <= t <= dtime(15, 30)

    # ================== STATE ==================
    latest_data = {}          # { "NIFTY": (data, spot, exp, ts), ... }
    latest_lock = threading.Lock()
    blocked = False
    last_block_time = 0.0
    prev_iv = {}              # { key: {"ce": , "pe": } }

    # ================== LOAD/SAVE PREVIOUS IV ==================
    def load_prev():
        nonlocal prev_iv
        try:
            with open(DATA_FILE, "r") as f:
                prev_iv = json.load(f)
            print("[IV ROC] Loaded previous IV file")
        except Exception:
            prev_iv = {}
            print("[IV ROC] No previous IV file, starting fresh")

    def save_prev():
        try:
            with open(DATA_FILE, "w") as f:
                json.dump(prev_iv, f)
        except Exception as e:
            print("[IV ROC] Failed to save prev_iv:", e)

    # ================== NSE FETCH ==================
    def fetch_chain(symbol):
        urls = [
            f"https://www.nseindia.com/api/option-chain-v3?type=Indices&symbol={symbol}",
            f"https://www.nseindia.com/api/option-chain-indices?symbol={symbol}",
        ]
        for url in urls:
            try:
                r = session.get(url, timeout=15)
                if r.status_code == 200:
                    j = r.json()
                    rec = j.get("records") or j.get("filtered") or {}
                    data = rec.get("data")
                    if data:
                        spot = rec.get("underlyingValue", 0)
                        exp_dates = rec.get("expiryDates") or []
                        exp = exp_dates[0][:10] if exp_dates else ""
                        return data, spot, exp
            except Exception as e:
                print(f"[IV ROC FETCH ERROR] {symbol} {url} → {e}")
        return None, None, None

    def data_loop():
        nonlocal blocked, last_block_time, latest_data
        while True:
            if not is_market_time():
                time.sleep(30)
                continue

            # If blocked → wait 5 minutes
            if blocked and (time.time() - last_block_time) < 300:
                time.sleep(10)
                continue

            for sym in INDICES:
                data, spot, exp = fetch_chain(sym)
                if data and spot:
                    with latest_lock:
                        latest_data[sym] = (data, spot, exp, time.time())

                    if blocked:
                        send("🟢 IV ROC: RECOVERED! NSE working again.")
                        blocked = False
                        last_block_time = 0.0
                else:
                    # some failure
                    if not blocked:
                        blocked = True
                        last_block_time = time.time()
                        send("🔴 IV ROC: NSE BLOCKED / ERROR! Waiting 5 minutes then retry…")

            time.sleep(30)

    # ================== ONE SCAN CYCLE ==================
    def scan_once():
        nonlocal prev_iv
        if not is_market_time():
            return

        t = now_ist()
        tm = t.strftime("%H:%M:%S")
        dt = t.strftime("%Y-%m-%d")

        with latest_lock:
            snapshot = latest_data.copy()

        for sym, pack in snapshot.items():
            if not pack:
                continue
            data, spot, exp, ts = pack
            if time.time() - ts > 60:
                continue

            # strike spacing
            step = 50 if sym == "NIFTY" else 100
            atm = int(round(float(spot) / step)) * step

            ce, pe = None, None
            for row in data:
                if row.get("strikePrice") == atm:
                    ce = row.get("CE")
                    pe = row.get("PE")
                    break

            if not ce or not pe:
                continue

            iv_ce = round(ce.get("impliedVolatility", 0.0) or 0.0, 1)
            iv_pe = round(pe.get("impliedVolatility", 0.0) or 0.0, 1)
            ltp_ce = ce.get("lastPrice", 0.0)
            ltp_pe = pe.get("lastPrice", 0.0)

            key = f"{sym}_{atm}_{exp}"
            old_ce = prev_iv.get(key, {}).get("ce", iv_ce)
            old_pe = prev_iv.get(key, {}).get("pe", iv_pe)

            roc_ce = round(iv_ce - old_ce, 1)
            roc_pe = round(iv_pe - old_pe, 1)

            prev_iv.setdefault(key, {})
            prev_iv[key]["ce"] = iv_ce
            prev_iv[key]["pe"] = iv_pe
            save_prev()

            if abs(roc_ce) >= MIN_ROC or abs(roc_pe) >= MIN_ROC:
                if roc_ce <= -MIN_ROC:
                    msg = (
                        f"🟢 [{tm}] {dt}\n"
                        f"{sym} ATM: {atm} | EXP: {exp}\n"
                        f"LTP CE: {ltp_ce} | LTP PE: {ltp_pe}\n"
                        f"IV Δ CE: {roc_ce} | IV Δ PE: {roc_pe}\n"
                        f"Setup: BUY {atm} CE (ITM best)"
                    )
                else:
                    msg = (
                        f"🔴 [{tm}] {dt}\n"
                        f"{sym} ATM: {atm} | EXP: {exp}\n"
                        f"LTP CE: {ltp_ce} | LTP PE: {ltp_pe}\n"
                        f"IV Δ CE: {roc_ce} | IV Δ PE: {roc_pe}\n"
                        f"Setup: BUY {atm} PE (ITM best)"
                    )
                send(msg)

    # ================== MAIN LOOP ==================
    def main_loop():
        load_prev()
        send("IV ROC GREEN/RED DOT SCANNER STARTED (NSE Fixed Version)\nWaiting for 9:15 AM...")

        threading.Thread(target=data_loop, daemon=True).start()

        market_sent = False

        while True:
            if is_market_time():
                if not market_sent:
                    send("Market OPEN! IV ROC Scanner LIVE 🔥")
                    market_sent = True

                scan_once()
            else:
                # Only send close message once per day
                now_time = now_ist().strftime("%H:%M")
                if market_sent and now_time > "15:30":
                    send("Market Closed. Relax now – See you tomorrow 🙏")
                    market_sent = False

            time.sleep(SCAN_INTERVAL)

    # Start loop (this never returns)
    main_loop()

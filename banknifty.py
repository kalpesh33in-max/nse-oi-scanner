# banknifty.py - KALPE BHAI BANKNIFTY SCANNER (FUNCTION VERSION FOR MULTI-SCANNER)

def run_banknifty_scanner():

    import os
    import time
    import threading
    import requests
    import pytz
    from datetime import datetime, time as dtime

    TOKEN = os.environ.get("TELEGRAM_TOKEN")
    CHATS = [int(x.strip()) for x in os.environ.get("TELEGRAM_CHAT_IDS","").split(",") if x.strip()]

    session = requests.Session()
    session.headers.update({
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
    })

    def refresh():
        try:
            session.get("https://www.nseindia.com", timeout=15)
        except:
            pass

    refresh()

    IST = pytz.timezone("Asia/Kolkata")
    def now():
        return datetime.now(IST)

    def market():
        return (
            now().weekday() < 5 and
            dtime(9, 15) <= now().time() <= dtime(15, 30)
        )

    def send(msg):
        if not TOKEN or not CHATS:
            print("BANKNIFTY TG OFF →", msg.replace("\n", " ")[:120])
            return

        for c in CHATS:
            try:
                requests.post(
                    f"https://api.telegram.org/bot{TOKEN}/sendMessage",
                    json={"chat_id": c, "text": msg, "parse_mode": "Markdown"},
                    timeout=10
                )
            except:
                pass

        print("BANKNIFTY →", msg.split("\n")[0])

    latest = None
    lock = threading.Lock()

    def fetch():
        nonlocal latest
        url = "https://www.nseindia.com/api/option-chain-indices?symbol=BANKNIFTY"

        try:
            refresh()
            time.sleep(2)
            r = session.get(url, timeout=20)

            if r.status_code == 200:
                j = r.json()
                records = j.get("records", {})
                data = records.get("data", [])
                spot = records.get("underlyingValue", 0)

                if data and spot:
                    with lock:
                        latest = (data, round(spot), time.time())
                    print(f"[BANKNIFTY] Spot {spot} | strikes {len(data)}")

        except Exception as e:
            print("[BNF FETCH ERROR]", e)

    def fetch_loop():
        while True:
            if market():
                fetch()
                time.sleep(35)
            else:
                time.sleep(40)

    def scanner():
        send("BANKNIFTY SCANNER LIVE ON RAILWAY!")
        hist = {}

        while True:
            time.sleep(3)

            if not market() or not latest:
                continue

            data, spot, ts = latest
            if time.time() - ts > 120:
                continue

            for row in data:
                strike = row["strikePrice"]

                # Wider range than NIFTY
                if abs(strike - spot) > 800:
                    continue

                for side in ("CE", "PE"):
                    opt = row.get(side)
                    if not opt:
                        continue

                    key = f"{strike}_{side}"
                    oi = opt["openInterest"]
                    chg = opt["changeinOpenInterest"]
                    lots = abs(chg) // 15  # banknifty lot size

                    # 15 lots (~375 qty) threshold
                    if lots >= 15:

                        # New spike or strong change
                        if key not in hist or abs(oi - hist[key]) > 2000:
                            send(f"""
🔥 BANKNIFTY BLAST 🔥
Strike: *{strike} {side}*
Lots added: *{lots} LOTS*
OI Change Spike!

Time: `{now().strftime('%H:%M:%S')}`
                            """)

                            hist[key] = oi

    # Start scanner threads
    threading.Thread(target=fetch_loop, daemon=True).start()
    threading.Thread(target=scanner, daemon=True).start()

    # Keep alive forever
    while True:
        print("BANKNIFTY SCANNER HEARTBEAT →", now())
        time.sleep(60)

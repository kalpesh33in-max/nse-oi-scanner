import os
import time
import threading
import requests
import pytz
from datetime import datetime, time as dtime

def run_kalpe_super_scanner():

    TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
    CHAT_IDS = [int(x.strip()) for x in os.environ.get("TELEGRAM_CHAT_IDS", "").split(",") if x.strip()]

    NIFTY_LOT = 75
    ATM_RANGE = 450
    COOLDOWN_SEC = 65

    SUPER_A = {"SPIKE": 45, "LOTS": 45}
    SUPER_B = {"SPIKE": 80, "LOTS": 75}

    IST = pytz.timezone("Asia/Kolkata")
    session = requests.Session()

    def now_ist():
        return datetime.now(IST)

    def market_open():
        t = now_ist()
        return t.weekday() < 5 and dtime(9, 15) <= t.time() <= dtime(15, 30)

    def send(msg):
        if not TELEGRAM_TOKEN or not CHAT_IDS:
            print("TG OFF:", msg)
            return
        for cid in CHAT_IDS:
            try:
                requests.post(
                    f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
                    json={"chat_id": cid, "text": msg, "parse_mode": "Markdown"},
                    timeout=10
                )
            except:
                pass

    def get_headers():
        agents = [
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/131",
            "Mozilla/5.0 (Macintosh; Intel Mac OS X) Safari/605",
            "Mozilla/5.0 (X11; Linux x86_64) Firefox/131",
            "Mozilla/5.0 (Windows NT 10.0) Firefox/131"
        ]
        return {"User-Agent": agents[int(time.time()) % len(agents)], "Accept": "*/*"}

    def refresh_nse():
        try:
            session.headers.update(get_headers())
            session.get("https://www.nseindia.com", timeout=10)
            time.sleep(1)
        except:
            pass

    refresh_nse()

    latest = None
    latest_future = None
    blocked = False
    lock = threading.Lock()

    def fetch_future_data():
        """Fetch NIFTY future OI + Price"""
        nonlocal latest_future
        try:
            url = "https://www.nseindia.com/api/live-analysis-oi-spurts-underlyings?index=FUTIDX"
            session.headers.update(get_headers())
            r = session.get(url, timeout=15)
            j = r.json()

            for item in j.get("data", []):
                if item.get("symbol") == "NIFTY":
                    latest_future = {
                        "oi": item.get("oi", 0),
                        "prev_oi": item.get("prev_oi", 0),
                        "price": item.get("ltp", 0),
                        "prev_price": item.get("prev_ltp", 0)
                    }
                    return True

        except:
            return False

    def fetch_data():
        nonlocal latest, blocked

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
                        send("🟢 NSE UNBLOCKED — Scanner Running")
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
                fetch_future_data()
                time.sleep(30)
            else:
                time.sleep(60)

    def expiry_type(expiry, all_exp):
        all_sorted = sorted(list(set(all_exp)))
        if expiry == all_sorted[0]:
            return "(Weekly)"
        elif len(all_sorted) > 1 and expiry == all_sorted[1]:
            return "(Next Weekly)"
        return "(Monthly)"

    def classify_option_trend(price_now, price_old, oi_now, oi_old):
        if oi_now > oi_old and price_now > price_old:
            return "Buyer Dominant (Price ↑ , OI ↑)"
        if oi_now > oi_old and price_now < price_old:
            return "Writer Dominant (Price ↓ , OI ↑)"
        if oi_now < oi_old and price_now > price_old:
            return "Short Covering (Price ↑ , OI ↓)"
        if oi_now < oi_old and price_now < price_old:
            return "Long Unwinding (Price ↓ , OI ↓)"
        return "Mixed"

    def classify_future_trend(f):
        if not f:
            return ("Unknown", "")

        p, pp = f["price"], f["prev_price"]
        o, po = f["oi"], f["prev_oi"]

        if o > po and p > pp:
            return ("Long Build-up", "(Future Price ↑ , Future OI ↑)")
        if o > po and p < pp:
            return ("Short Build-up", "(Future Price ↓ , Future OI ↑)")
        if o < po and p > pp:
            return ("Short Cover", "(Future Price ↑ , Future OI ↓)")
        if o < po and p < pp:
            return ("Long Unwinding", "(Future Price ↓ , Future OI ↓)")
        return ("Unknown", "")

    def super_scanner():
        hist = {}
        cooldown = {}

        send("⚡ SUPER-SPIKE SCANNER ACTIVE (Full Details Enabled)")

        while True:
            time.sleep(1)
            if not market_open() or not latest:
                continue

            data, spot, ts = latest

            if time.time() - ts > 120:
                continue

            expiries = [row["expiryDate"] for row in data]

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
                    chg_oi = opt["changeinOpenInterest"]
                    lots = abs(chg_oi) // NIFTY_LOT
                    iv = opt.get("impliedVolatility") or 0
                    price = opt.get("lastPrice") or opt.get("bidprice") or 0

                    spike = 0
                    ivroc = 0

                    if key in hist:
                        p_old = hist[key]["price"]
                        oi_old = hist[key]["oi"]
                        iv_old = hist[key]["iv"]

                        if oi_old > 0:
                            spike = ((oi - oi_old) / oi_old) * 100
                        if iv_old > 0:
                            ivroc = ((iv - iv_old) / iv_old) * 100
                    else:
                        hist[key] = {"oi": oi, "iv": iv, "price": price}
                        continue

                    now_t = time.time()
                    if now_t - cooldown.get(key, 0) < COOLDOWN_SEC:
                        hist[key] = {"oi": oi, "iv": iv, "price": price}
                        continue

                    trigger = None
                    if spike >= SUPER_B["SPIKE"] and lots >= SUPER_B["LOTS"]:
                        trigger = "👑 EXTREME SPIKE"
                    elif spike >= SUPER_A["SPIKE"] and lots >= SUPER_A["LOTS"]:
                        trigger = "🔥 SUPER SPIKE"

                    if trigger:
                        f_trend, f_msg = classify_future_trend(latest_future)

                        opt_trend = classify_option_trend(
                            price, hist[key]["price"], oi, hist[key]["oi"]
                        )

                        msg = (
                            f"{trigger}\n"
                            f"Spot: {spot}\n"
                            f"Strike: {strike} {typ}\n"
                            f"Expiry: {expiry} {expiry_type(expiry, expiries)}\n"
                            f"Price: ₹{price}\n\n"
                            f"OI Details:\n"
                            f"• OI: {oi:,}\n"
                            f"• Change in OI: {chg_oi:+,}\n"
                            f"• Lots: {lots}\n"
                            f"• IV: {iv:.2f}%\n"
                            f"• IV ROC: {ivroc:+.1f}%\n\n"
                            f"Option Trend: {opt_trend}\n\n"
                            f"Futures OI: {f_trend}\n"
                            f"{f_msg}\n"
                            f"Future Price: ₹{latest_future['price'] if latest_future else 'N/A'}"
                        )

                        send(msg)
                        cooldown[key] = now_t

                    hist[key] = {"oi": oi, "iv": iv, "price": price}

    def heartbeat():
        while True:
            print("Scanner alive:", now_ist())
            time.sleep(60)

    def main():
        send("🚀 KALPE BHAI SUPER SPIKE SCANNER STARTED")
        threading.Thread(target=fetch_loop, daemon=True).start()
        threading.Thread(target=super_scanner, daemon=True).start()
        threading.Thread(target=heartbeat, daemon=True).start()

        while True:
            time.sleep(999999)

    main()


if __name__ == "__main__":
    run_kalpe_super_scanner()

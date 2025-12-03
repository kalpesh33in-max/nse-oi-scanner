import os
import time
import threading
import requests
import pytz
from datetime import datetime, timedelta, time as dtime


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
            print("TG-OFF:", msg[:200])
            return
        for cid in CHAT_IDS:
            try:
                requests.post(
                    f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
                    json={"chat_id": cid, "text": msg, "parse_mode": "Markdown"},
                    timeout=10
                )
            except Exception as e:
                print("TG ERROR:", e)

    def get_headers():
        agents = [
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/131",
            "Mozilla/5.0 (Macintosh; Intel Mac OS X) Safari/605",
            "Mozilla/5.0 (X11; Linux x86_64) Firefox/131"
        ]
        return {
            "User-Agent": agents[int(time.time()) % len(agents)],
            "Accept": "*/*",
            "Referer": "https://www.nseindia.com"
        }

    def refresh_nse():
        try:
            session.headers.update(get_headers())
            session.get("https://www.nseindia.com", timeout=10)
        except:
            pass

    refresh_nse()

    latest = None
    latest_future = None
    blocked = False
    last_block_time = 0
    lock = threading.Lock()

    # --------------------------
    # AUTO FETCH NIFTY FUTURE MONTHLY
    # --------------------------
    def fetch_nifty_future_auto():
        """Fetch the nearest MONTHLY expiry NIFTY future."""
        nonlocal latest_future
        try:
            url = "https://www.nseindia.com/api/quote-derivative?symbol=NIFTY"
            session.headers.update(get_headers())
            r = session.get(url, timeout=10)
            if r.status_code != 200:
                return False

            j = r.json()
            items = j.get("stocks", [])
            futures = [x for x in items if x.get("instrumentType") == "FUTIDX"]

            if not futures:
                return False

            # Sort all futures by expiry date
            futures_sorted = sorted(
                futures,
                key=lambda x: datetime.strptime(x["expiryDate"], "%d-%b-%Y")
            )

            fut = futures_sorted[0]  # nearest monthly future

            latest_future = {
                "price": fut.get("lastPrice", 0),
                "prev_price": fut.get("prevClose", 0),
                "oi": fut.get("openInterest", 0),
                "prev_oi": fut.get("openInterest", 0) - fut.get("changeinOpenInterest", 0),
                "expiry": fut.get("expiryDate", "")
            }
            return True

        except Exception as e:
            print("[FUTURE ERROR]", e)
            return False

    # --------------------------
    # OPTION EXPIRY LABEL FIXED LOGIC
    # --------------------------
    def expiry_type(expiry, all_exp):
        """Return Weekly / Next Weekly / Monthly."""
        if not all_exp:
            return ""

        # Unique sorted
        unique_sorted = sorted(
            set(all_exp),
            key=lambda x: datetime.strptime(x, "%d-%b-%Y")
        )

        today = now_ist().date()

        # Keep only expiries after today
        valid = [
            e for e in unique_sorted
            if datetime.strptime(e, "%d-%b-%Y").date() >= today
        ]

        if not valid:
            return ""

        # Current & Next Weekly
        current_week = valid[0]
        next_week = valid[1] if len(valid) > 1 else None

        # Monthly expiry = last Thursday of that month
        def last_thursday(dt):
            temp = datetime(dt.year, dt.month, 28)
            while temp.month == dt.month:
                temp += timedelta(days=1)
            temp -= timedelta(days=1)
            while temp.weekday() != 3:
                temp -= timedelta(days=1)
            return temp.strftime("%d-%b-%Y")

        monthly = None
        for e in valid:
            dt = datetime.strptime(e, "%d-%b-%Y")
            if e == last_thursday(dt):
                monthly = e

        if expiry == current_week:
            return "(Weekly)"
        if expiry == next_week:
            return "(Next Weekly)"
        if expiry == monthly:
            return "(Monthly)"
        return ""

    # --------------------------
    # OPTION TREND
    # --------------------------
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

    # --------------------------
    # FUTURE TREND
    # --------------------------
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

    # --------------------------
    # MARKET BIAS = CE/PE + FUTURE TREND
    # --------------------------
    def market_bias(opt_type, opt_trend, fut_trend):
        future_buy = fut_trend in ["Long Build-up", "Short Cover"]
        future_sell = fut_trend in ["Short Build-up", "Long Unwinding"]

        # CALL logic
        if opt_type == "CE":
            if future_sell:
                return "Bearish", "CALL Writing + Future SELL → Bearish"
            if future_buy:
                return "Weak Bullish", "CALL Buying + Future BUY → Trap / Reversal"

        # PUT logic
        if opt_type == "PE":
            if future_buy:
                return "Strong Bearish", "PUT Buying + Future SELL → Strong Downtrend"
            if future_sell:
                return "Bullish", "PUT Writing + Future BUY → Uptrend strong"

        return "Neutral", "No clear bias"

    # --------------------------
    # FETCH LOOP
    # --------------------------
    def fetch_loop():
        while True:
            if market_open():
                fetch_data()
                fetch_nifty_future_auto()
                time.sleep(30)
            else:
                time.sleep(60)
    # --------------------------
    # FETCH OPTION-CHAIN
    # --------------------------
    def fetch_data():
        nonlocal latest, blocked, last_block_time

        if blocked and (time.time() - last_block_time) < 60:
            return False

        urls = [
            "https://www.nseindia.com/api/option-chain-indices?symbol=NIFTY",
            "https://www.nseindia.com/api/option-chain-v3?type=Indices&symbol=NIFTY"
        ]

        for url in urls:
            try:
                refresh_nse()
                session.headers.update(get_headers())
                r = session.get(url, timeout=10)
                if r.status_code != 200:
                    raise Exception(f"HTTP {r.status_code}")

                j = r.json()
                records = j.get("records") or j.get("filtered") or {}
                data = records.get("data") or []
                spot = round(records.get("underlyingValue") or 0)

                if data and spot > 15000:
                    with lock:
                        latest = (data, spot, time.time())

                    if blocked:
                        send("🟢 *NSE Unblocked — Scanner Resumed*")
                        blocked = False
                        last_block_time = 0
                    return True

            except Exception as e:
                err = str(e).lower()
                print("FETCH ERROR:", e)

                if any(t in err for t in ["403", "429", "blocked", "captcha"]):
                    if not blocked:
                        blocked = True
                        last_block_time = time.time()
                        send("🔴 *Scanner Blocked — Retrying every 1 min*")
                    else:
                        last_block_time = time.time()

        return False

    # --------------------------
    # SUPER SCANNER MAIN LOGIC
    # --------------------------
    def super_scanner():
        hist = {}
        cooldown = {}
        send("⚡ *SUPER-SPIKE SCANNER ACTIVE*")

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

                label = expiry_type(expiry, expiries)

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

                    if key not in hist:
                        hist[key] = {"oi": oi, "iv": iv, "price": price}
                        continue

                    oi_old = hist[key]["oi"]
                    price_old = hist[key]["price"]
                    iv_old = hist[key]["iv"]

                    spike = ((oi - oi_old) / oi_old * 100) if oi_old else 0
                    ivroc = ((iv - iv_old) / iv_old * 100) if iv_old else 0

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
                        opt_trend = classify_option_trend(price, price_old, oi, oi_old)
                        bias, reason = market_bias(typ, opt_trend, f_trend)

                        fut_price = latest_future["price"]
                        fut_oi = latest_future["oi"]
                        fut_doi = fut_oi - latest_future["prev_oi"]
                        fut_pc = latest_future["expiry"]

                        msg = (
                            f"{trigger}\n\n"
                            f"Expiry: {expiry} {label:<32} • Future Expiry: {fut_pc}\n"
                            f"Strike: {strike} {typ}, Price: ₹{price}        • Futures OI: {f_trend}\n\n"
                            f"OI Details: as below now Spot price: {spot:<8}  Future:\n"
                            f"• OI: {oi:,} & Change in OI: {chg_oi:+,}        • Price: ₹{fut_price}\n"
                            f"• Lots: {lots} & IV: {iv:.2f}% & IV ROC: {ivroc:+.1f}%  • OI: {fut_oi:,}\n"
                            f"                                               • ΔOI: {fut_doi:+,}\n\n"
                            f"Option Trend: {opt_trend:<35} {f_msg}\n\n"
                            f"🟩 Market Bias: *{bias}*\n"
                            f"Reason: {reason}\n\n"
                            f"Time: {now_ist().strftime('%H:%M:%S')} IST"
                        )

                        send(msg)
                        cooldown[key] = now_t

                    hist[key] = {"oi": oi, "iv": iv, "price": price}

    # --------------------------
    # HEARTBEAT
    # --------------------------
    def heartbeat():
        while True:
            print("ALIVE:", now_ist())
            time.sleep(60)

    # --------------------------
    # MAIN RUNNER
    # --------------------------
    def main():
        send("🚀 *KALPE SUPER SCANNER STARTED*")
        threading.Thread(target=fetch_loop, daemon=True).start()
        threading.Thread(target=super_scanner, daemon=True).start()
        threading.Thread(target=heartbeat, daemon=True).start()

        while True:
            time.sleep(99999)

    main()


def run_kalpe_2025_scanner():
    run_kalpe_super_scanner()


if __name__ == "__main__":
    run_kalpe_super_scanner()

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

    # ================== NSE SESSION & HEADERS (DESKTOP) ==================
    BASE_HEADERS = {
        "authority": "www.nseindia.com",
        "accept": "application/json, text/plain, */*",
        "accept-encoding": "gzip, deflate, br, zstd",
        "accept-language": "en-US,en;q=0.9,en-IN;q=0.8",
        "referer": "https://www.nseindia.com/option-chain",
        "user-agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0.0.0 Safari/537.36"
        ),
        "connection": "keep-alive",

        # extra headers to look more like a real browser
        "sec-fetch-site": "same-origin",
        "sec-fetch-mode": "cors",
        "sec-fetch-dest": "empty",
        "sec-ch-ua": '"Not/A)Brand";v="99", "Chromium";v="120", "Google Chrome";v="120"',
        "sec-ch-ua-mobile": "?0",
        "sec-ch-ua-platform": '"Windows"',
        "x-requested-with": "XMLHttpRequest",
    }
    session.headers.update(BASE_HEADERS)
    _last_cookie_refresh = 0.0

    def ensure_nse_session(force: bool = False):
        """
        NSE ko stable banane ke liye:
        - Home page hit karo taaki cookies mil jaye
        - Har ~30 min refresh
        - Agar force=True, turant refresh
        """
        nonlocal _last_cookie_refresh
        now = time.time()
        if not force and (now - _last_cookie_refresh) < 1800:
            return

        try:
            r = session.get("https://www.nseindia.com", timeout=10)
            if r.status_code == 200:
                _last_cookie_refresh = now
                print("[NSE] Session refreshed OK")
            else:
                print("[NSE] Session refresh status:", r.status_code)
        except Exception as e:
            print("[NSE] Session refresh error:", e)

    def _ensure_json_response(r: requests.Response, label: str):
        """
        Some NSE blocks: HTML / Captcha page.
        JSON parse se pehle check kar lein.
        """
        ct = r.headers.get("content-type", "").lower()
        text_preview = r.text[:120].strip().lower()

        if (
            "text/html" in ct
            or text_preview.startswith("<!doctype html")
            or text_preview.startswith("<html")
        ):
            raise RuntimeError(f"{label}: HTML_BLOCKED")
        return r

    # ================== TIME & MARKET HELPERS ==================
    def now_ist():
        return datetime.now(IST)

    def market_open():
        t = now_ist()
        return t.weekday() < 5 and dtime(9, 15) <= t.time() <= dtime(15, 30)

    # ================== TELEGRAM ==================
    def send(msg):
        if not TELEGRAM_TOKEN or not CHAT_IDS:
            print("TG-OFF:", msg[:200].replace("\n", " "))
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

    # ================== GLOBAL STATE ==================
    latest = None          # (data, spot, ts)
    latest_future = None   # dict or None
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
            ensure_nse_session()
            url = "https://www.nseindia.com/api/quote-derivative?symbol=NIFTY"
            r = session.get(url, timeout=10)

            # handle hard NSE blocks
            if r.status_code in (401, 403, 429, 500):
                print("[FUTURE BLOCK]", r.status_code)
                return False

            r.raise_for_status()
            _ensure_json_response(r, "FUTURES")

            j = r.json()
            items = j.get("stocks", [])
            futures = [x for x in items if x.get("instrumentType") == "FUTIDX"]

            if not futures:
                return False

            futures_sorted = sorted(
                futures,
                key=lambda x: datetime.strptime(x["expiryDate"], "%d-%b-%Y")
            )

            fut = futures_sorted[0]  # nearest future

            latest_future = {
                "price": fut.get("lastPrice", 0),
                "prev_price": fut.get("prevClose", 0),
                "oi": fut.get("openInterest", 0),
                "prev_oi": fut.get("openInterest", 0) - fut.get("changeinOpenInterest", 0),
                "expiry": fut.get("expiryDate", "")
            }
            print("[FUT] OK", latest_future["expiry"], latest_future["oi"])
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

        unique_sorted = sorted(
            set(all_exp),
            key=lambda x: datetime.strptime(x, "%d-%b-%Y")
        )

        today = now_ist().date()

        valid = [
            e for e in unique_sorted
            if datetime.strptime(e, "%d-%b-%Y").date() >= today
        ]

        if not valid:
            return ""

        current_week = valid[0]
        next_week = valid[1] if len(valid) > 1 else None

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
    # FETCH OPTION-CHAIN (with retry + block handling)
    # --------------------------
    def fetch_data():
        nonlocal latest, blocked, last_block_time

        # if already blocked, back off for 60 seconds
        if blocked and (time.time() - last_block_time) < 60:
            return False

        urls = [
            "https://www.nseindia.com/api/option-chain-indices?symbol=NIFTY",
            "https://www.nseindia.com/api/option-chain-v3?type=Indices&symbol=NIFTY"
        ]

        got_records = False

        # 2 attempts: second attempt forces new cookies
        for attempt in range(2):
            if attempt == 1 and not got_records:
                print("[NSE] Forcing cookie refresh in fetch_data()...")
                ensure_nse_session(force=True)
                time.sleep(2)

            for url in urls:
                try:
                    r = session.get(url, timeout=15)

                    # handle hard NSE API blocks
                    if r.status_code in (401, 403, 429, 500):
                        print("[FETCH STATUS BLOCK]", url, ":", r.status_code)
                        continue

                    r.raise_for_status()
                    _ensure_json_response(r, "OPTION_CHAIN")

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

                        print("[OC] OK", url, "spot:", spot)
                        got_records = True
                        break

                except RuntimeError as e:
                    # HTML_BLOCKED etc
                    print("FETCH ERROR (HTML/BLOCK):", url, ":", e)
                except Exception as e:
                    print("FETCH ERROR:", url, ":", e)

            if got_records:
                break

        # if still nothing, mark as blocked
        if not got_records:
            err_msg = "UNKNOWN_BLOCK"
            if not blocked:
                blocked = True
                last_block_time = time.time()
                send("🔴 *Scanner Blocked — Retrying every 1 min*")
            else:
                last_block_time = time.time()
            print("[FETCH_DATA] No usable option chain, marking blocked:", err_msg)
            return False

        return True

    # --------------------------
    # FETCH LOOP
    # --------------------------
    def fetch_loop():
        # Force first cookie refresh
        ensure_nse_session(force=True)
        while True:
            if market_open():
                fetch_data()
                fetch_nifty_future_auto()
                # IMPORTANT: This scanner runs with 4 more scanners.
                time.sleep(30)
            else:
                time.sleep(60)

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
                        # --- Future trend & bias ---
                        f_trend, f_msg = classify_future_trend(latest_future)
                        opt_trend = classify_option_trend(price, price_old, oi, oi_old)
                        bias, reason = market_bias(typ, opt_trend, f_trend)

                        # Safe defaults if futures missing
                        if latest_future:
                            fut_price = latest_future["price"]
                            fut_oi = latest_future["oi"]
                            fut_doi = fut_oi - latest_future["prev_oi"]
                            fut_pc = latest_future["expiry"]
                        else:
                            fut_price = 0
                            fut_oi = 0
                            fut_doi = 0
                            fut_pc = "N/A"

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

# ============================================================
# BANKNIFTY MASTER SCANNER (Fixed NSE Block Handling)
# Same Logic • Improved Stability • Retry • Cookie Refresh
# ============================================================

import os
import time
import requests
import pytz
from datetime import datetime, time as dtime

# ========================= TELEGRAM ==========================
TOKEN = os.environ.get("TELEGRAM_TOKEN", "")
CHAT_RAW = (
    os.environ.get("TELEGRAM_CHAT_IDS")
    or os.environ.get("TELEGRAM_CHAT_ID")
    or ""
)
CHAT_IDS = [c.strip() for c in CHAT_RAW.split(",") if c.strip()]


def send(msg: str):
    if not TOKEN or not CHAT_IDS:
        print("TG OFF:", msg[:150])
        return
    for cid in CHAT_IDS:
        try:
            requests.post(
                f"https://api.telegram.org/bot{TOKEN}/sendMessage",
                json={"chat_id": cid, "text": msg, "parse_mode": "Markdown"},
                timeout=10,
            )
        except:
            pass


# ========================= CONSTANTS =========================
SYMBOL = "BANKNIFTY"
LOT = 35

ATM_RANGE = 3000
HEDGE_RANGE = 200

SUPER_A = {"SPIKE": 20, "LOTS": 100}
SUPER_B = {"SPIKE": 35, "LOTS": 200}
COOLDOWN = 60

REVERSAL_MIN_IVROC = 10
REVERSAL_MIN_LOTS = 80

IST = pytz.timezone("Asia/Kolkata")


def now_ist():
    return datetime.now(IST)


def is_market_time():
    n = now_ist()
    if n.weekday() >= 5:
        return False
    return dtime(9, 15) <= n.time() <= dtime(15, 30)


# ========================= NSE SESSION =======================
session = requests.Session()


def update_headers():
    session.headers.update({
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            f"AppleWebKit/537.{int(time.time())%100} "
            "(KHTML, like Gecko) Chrome/131 Safari/537.36"
        ),
        "Accept": "*/*",
        "Origin": "https://www.nseindia.com",
        "Referer": "https://www.nseindia.com/",
    })


def refresh_nse():
    try:
        update_headers()
        session.get("https://www.nseindia.com", timeout=10)
        time.sleep(0.2)
    except:
        pass


update_headers()


# ========================= EXPIRY HELPERS ====================
def parse_expiry(s):
    try:
        return datetime.strptime(s, "%d-%b-%Y").date()
    except:
        return None


def classify_expiry(exp, all_list):
    d = parse_expiry(exp)
    if not d:
        return exp, "MONTHLY"

    disp = d.strftime("%d %b %Y").upper()
    parsed = [parse_expiry(x) for x in all_list if parse_expiry(x)]
    parsed.sort()

    try:
        idx = parsed.index(d)
    except:
        idx = 0

    if idx == 0:
        etype = "NEAR MONTH"
    elif idx == 1:
        etype = "NEXT MONTH"
    else:
        etype = "FAR MONTH"

    return disp, etype


# ========================= FETCH OPTION-CHAIN =================
def fetch_option_chain():
    urls = [
        f"https://www.nseindia.com/api/option-chain-v3?type=Indices&symbol={SYMBOL}",
        f"https://www.nseindia.com/api/option-chain-indices?symbol={SYMBOL}",
    ]

    last_err = ""

    for url in urls:
        try:
            refresh_nse()
            update_headers()
            r = session.get(url, timeout=15)

            if r.status_code in (403, 429):
                raise Exception("BLOCKED_BY_NSE")

            if r.text.strip().startswith("<") or len(r.text.strip()) < 30:
                raise Exception("HTML_BLOCKED")

            j = r.json()
            records = j.get("records") or j.get("filtered") or {}
            data = records.get("data")
            expiry = records.get("expiryDates")
            spot = records.get("underlyingValue")

            if not data or not expiry or not spot:
                raise Exception("EMPTY_DATA")

            return data, round(spot), expiry

        except Exception as e:
            last_err = str(e)
            print("[FETCH ERROR]", e)

    raise Exception(f"FAILED_ALL_URLS: {last_err}")


# ========================= FETCH FUTURES =====================
def fetch_futures():
    try:
        refresh_nse()
        update_headers()

        url = f"https://www.nseindia.com/api/quote-derivative?symbol={SYMBOL}"
        r = session.get(url, timeout=15)

        if r.status_code in (403, 429):
            return None
        if r.text.strip().startswith("<"):
            return None

        j = r.json()
        futs = []

        for row in j.get("stocks", []):
            meta = row.get("metadata", {})
            if "FUT" in meta.get("instrumentType", ""):
                exp = meta.get("expiryDate")
                oi = meta.get("openInterest", 0)
                chg = meta.get("changeinOpenInterest", 0)
                futs.append((exp, oi, chg))

        if not futs:
            return None

        futs.sort(key=lambda x: datetime.strptime(x[0], "%d-%b-%Y"))
        return futs[0]

    except:
        return None


# ========================= MASTER SCANNER ====================
def run_banknifty_scanner():

    send(
        "🚀 *BANKNIFTY MASTER SCANNER (Stable Version)* 🚀\n"
        "• Monthly expiry only\n"
        "• Super Spike / Extreme Spike\n"
        "• Reversal Alerts\n"
        "• NSE Block Auto-Recover Enabled\n"
    )

    prev_oi = {}
    prev_iv = {}
    last_dir = {}

    cool_A = {}
    cool_B = {}
    cool_R = {}

    blocked = False
    block_ts = 0

    while True:
        try:
            if not is_market_time():
                time.sleep(10)
                continue

            # ========================= NSE BLOCK HANDLING =====================
            try:
                data, spot, expiry_list = fetch_option_chain()

                if blocked:
                    send("🟢 *BANKNIFTY Scanner Recovered — NSE Online Again*")
                    blocked = False

            except Exception as e:
                print("[BLOCK DETECTED]", e)

                if not blocked:
                    send("🔴 *BANKNIFTY Scanner Blocked — Retrying Every 1 Minute…*")
                    blocked = True
                    block_ts = time.time()

                if time.time() - block_ts < 60:
                    time.sleep(5)
                    continue

                block_ts = time.time()
                continue

            # ========================= FUTURES =========================
            fut = fetch_futures()
            fut_exp, fut_chg = "", 0
            if fut:
                fut_exp, _, fut_chg = fut

            # ========================= MAIN LOOP START ===================
            for row in data:
                strike = row.get("strikePrice")
                exp_raw = row.get("expiryDate")
                if strike is None or abs(strike - spot) > ATM_RANGE:
                    continue

                exp_disp, exp_type = classify_expiry(exp_raw, expiry_list)

                ce = row.get("CE")
                pe = row.get("PE")

                for opt, leg in (("CE", ce), ("PE", pe)):
                    if not leg:
                        continue

                    key = f"{strike}_{opt}_{exp_raw}"

                    oi = leg.get("openInterest", 0)
                    chg_oi = leg.get("changeinOpenInterest", 0)
                    iv = leg.get("impliedVolatility", 0.0) or 0.0
                    ltp = leg.get("lastPrice", 0.0)

                    ce_ltp = ce.get("lastPrice", 0.0) if ce else 0.0
                    pe_ltp = pe.get("lastPrice", 0.0) if pe else 0.0

                    old_oi = prev_oi.get(key, 0)
                    old_iv = prev_iv.get(key, 0.0)

                    spike = ((oi - old_oi) / old_oi * 100) if old_oi > 0 else 0.0
                    lots = abs(oi - old_oi) // LOT
                    ivroc = ((iv - old_iv) / old_iv * 100) if (old_iv > 0 and iv > 0) else 0.0

                    if opt == "CE":
                        price_line = f"CE Price: `₹{ce_ltp}`\n\n"
                    else:
                        price_line = f"PE Price: `₹{pe_ltp}`\n\n"

                    sign = 1 if (oi - old_oi) > 0 else -1 if (oi - old_oi) < 0 else 0
                    now_ts = time.time()

                    # ====================================================
                    # EXTREME SUPER SPIKE (TYPE B)
                    # ====================================================
                    if spike >= SUPER_B["SPIKE"] and lots >= SUPER_B["LOTS"]:
                        if now_ts - cool_B.get(key, 0) > COOLDOWN:
                            send(
                                f"👑 *EXTREME SUPER SPIKE (TYPE B)* 👑\n\n"
                                f"Expiry: `{exp_disp}` ({exp_type})\n"
                                f"*BANKNIFTY {strike} {opt}*\n\n"
                                f"{price_line}"
                                f"{opt} OI Spike: `+{spike:.1f}%`\n"
                                f"{opt} IV: `{iv:.1f}%` (ROC: `{ivroc:+.1f}%`)\n"
                                f"Lots: `{lots}` LOTS\n\n"
                                f"Time: `{now_ist().strftime('%H:%M:%S')}` IST"
                            )
                            cool_B[key] = now_ts

                    # ====================================================
                    # SUPER SPIKE (TYPE A)
                    # ====================================================
                    if spike >= SUPER_A["SPIKE"] and lots >= SUPER_A["LOTS"]:
                        if now_ts - cool_A.get(key, 0) > COOLDOWN:
                            send(
                                f"🔥 *SUPER SPIKE (TYPE A)* 🔥\n\n"
                                f"Expiry: `{exp_disp}` ({exp_type})\n"
                                f"*BANKNIFTY {strike} {opt}*\n\n"
                                f"{price_line}"
                                f"{opt} OI Spike: `+{spike:.1f}%`\n"
                                f"{opt} IV: `{iv:.1f}%` (ROC: `{ivroc:+.1f}%`)\n"
                                f"Lots: `{lots}` LOTS\n\n"
                                f"Time: `{now_ist().strftime('%H:%M:%S')}` IST"
                            )
                            cool_A[key] = now_ts

                    # ====================================================
                    # EXTREME REVERSAL
                    # ====================================================
                    last_s = last_dir.get(key, 0)
                    if (
                        sign != 0
                        and last_s != 0
                        and sign != last_s
                        and lots >= REVERSAL_MIN_LOTS
                        and abs(ivroc) >= REVERSAL_MIN_IVROC
                    ):
                        if now_ts - cool_R.get(key, 0) > COOLDOWN:
                            old_side = "BUYERS ACTIVE" if last_s > 0 else "WRITERS ACTIVE"
                            new_side = "WRITERS ACTIVE" if sign < 0 else "BUYERS ACTIVE"

                            send(
                                f"🔄 *EXTREME REVERSAL ALERT* 🔄\n\n"
                                f"Expiry: `{exp_disp}` ({exp_type})\n"
                                f"*BANKNIFTY {strike} {opt}*\n\n"
                                f"{price_line}"
                                f"Old Side: *{old_side}*\n"
                                f"New Side: *{new_side}*\n"
                                f"OI (Lots): `{lots}`\n"
                                f"IV: `{iv:.1f}%` (ROC: `{ivroc:+.1f}%`)\n\n"
                                f"Time: `{now_ist().strftime('%H:%M:%S')}` IST"
                            )
                            cool_R[key] = now_ts

                    prev_oi[key] = oi
                    prev_iv[key] = iv
                    if sign != 0:
                        last_dir[key] = sign

            time.sleep(3)

        except Exception as e:
            print("[MAIN LOOP ERROR]", e)
            time.sleep(5)

# ============================================================
# BANKNIFTY MASTER SCANNER (Stable NSE Handling)
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
        print("TG OFF:", msg[:150].replace("\n", " "))
        return
    for cid in CHAT_IDS:
        try:
            requests.post(
                f"https://api.telegram.org/bot{TOKEN}/sendMessage",
                json={"chat_id": cid, "text": msg, "parse_mode": "Markdown"},
                timeout=10,
            )
        except Exception as e:
            print("TG ERROR:", e)


# ========================= CONSTANTS =========================
SYMBOL = "BANKNIFTY"
LOT = 35

ATM_RANGE = 3000
HEDGE_RANGE = 200  # (not used in current logic, kept for future)

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
    global _last_cookie_refresh
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
    text_preview = r.text.strip().lower()[:80]

    if (
        "text/html" in ct
        or text_preview.startswith("<!doctype html")
        or text_preview.startswith("<html")
    ):
        raise RuntimeError(f"{label}: HTML_BLOCKED")

    return r


# ========================= EXPIRY HELPERS ====================
def parse_expiry(s):
    try:
        return datetime.strptime(s, "%d-%b-%Y").date()
    except Exception:
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
    except Exception:
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
            ensure_nse_session()
            r = session.get(url, timeout=15)
            r.raise_for_status()
            _ensure_json_response(r, "OPTION_CHAIN")

            j = r.json()
            records = j.get("records") or j.get("filtered") or {}
            data = records.get("data")
            expiry = records.get("expiryDates")
            spot = records.get("underlyingValue")

            if not data or not expiry or not spot:
                raise RuntimeError("EMPTY_DATA")

            print("[OC] OK", url, "spot:", spot)
            return data, round(spot), expiry

        except Exception as e:
            last_err = str(e)
            print("[FETCH ERROR]", url, ":", e)

    raise RuntimeError(f"FAILED_ALL_URLS: {last_err}")


# ========================= FETCH FUTURES =====================
def fetch_futures():
    try:
        ensure_nse_session()
        url = f"https://www.nseindia.com/api/quote-derivative?symbol={SYMBOL}"
        r = session.get(url, timeout=15)
        r.raise_for_status()
        _ensure_json_response(r, "FUTURES")

        j = r.json()
        futs = []

        for row in j.get("stocks", []):
            meta = row.get("metadata", {})
            if "FUT" in str(meta.get("instrumentType", "")):
                exp = meta.get("expiryDate")
                oi = meta.get("openInterest", 0)
                chg = meta.get("changeinOpenInterest", 0)
                futs.append((exp, oi, chg))

        if not futs:
            return None

        futs.sort(key=lambda x: datetime.strptime(x[0], "%d-%b-%Y"))
        return futs[0]

    except Exception as e:
        print("[FUT ERROR]", e)
        return None


# ========================= MASTER SCANNER ====================
def run_banknifty_scanner():

    send(
        "🚀 *BANKNIFTY MASTER SCANNER (Stable Version)* 🚀\n"
        "• Monthly-style expiry classification\n"
        "• Super Spike / Extreme Super Spike\n"
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

    # Force first cookie refresh
    ensure_nse_session(force=True)

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

                # wait a bit before next retry
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

            # Frequency – same as before, but you can increase to 5–10s if NSE still blocks
            time.sleep(3)

        except Exception as e:
            print("[MAIN LOOP ERROR]", e)
            time.sleep(5)

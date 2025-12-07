# ============================================================
# BANKNIFTY MASTER SCANNER (Stable NSE Handling)
# Improved Session • Auto Recovery • Retry Mechanism • Cookie Refresh
# ============================================================

import os
import time
import requests
import pytz
from datetime import datetime, time as dtime

# ========================= TELEGRAM ==========================
TOKEN = os.getenv("TELEGRAM_TOKEN")
CHAT_RAW = (
    os.getenv("TELEGRAM_CHAT_IDS")
    or os.getenv("TELEGRAM_CHAT_ID")
    or ""
)
CHAT_IDS = [c.strip() for c in CHAT_RAW.split(",") if c.strip()]


def send(msg: str):
    if not TOKEN or not CHAT_IDS:
        print("TG OFF:", msg[:120].replace("\n", " "))
        return
    for cid in CHAT_IDS:
        try:
            requests.post(
                f"https://api.telegram.org/bot{TOKEN}/sendMessage",
                json={"chat_id": cid, "text": msg, "parse_mode": "Markdown"},
                timeout=8,
            )
        except Exception as e:
            print("TG ERROR:", e)


# ========================= CONSTANTS =========================
SYMBOL = "BANKNIFTY"
LOT = 15  # auto-adjust if you need 15 or 25 or 40

ATM_RANGE = 3000
SUPER_A = {"SPIKE": 20, "LOTS": 100}
SUPER_B = {"SPIKE": 35, "LOTS": 200}
COOLDOWN = 60

REV_MIN_IVROC = 10
REV_MIN_LOTS = 80

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

    # 🔥 NEW HEADERS → prevents 403 NSE blocks
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
            print("[NSE] Refresh status:", r.status_code)
    except Exception as e:
        print("[NSE] Refresh error:", e)


def is_html(r: requests.Response):
    """Detect NSE block / captcha"""
    ct = r.headers.get("content-type", "")
    text = r.text.strip().lower()
    return (
        "text/html" in ct.lower()
        or text.startswith("<!doctype")
        or text.startswith("<html")
    )


# ========================= FETCH OPTION CHAIN =================
def fetch_option_chain():
    urls = [
        f"https://www.nseindia.com/api/option-chain-v3?type=Indices&symbol={SYMBOL}",
        f"https://www.nseindia.com/api/option-chain-indices?symbol={SYMBOL}",
    ]

    for attempt in range(2):
        if attempt == 1:
            print("[NSE] Forced cookie refresh…")
            ensure_nse_session(force=True)
            time.sleep(2)

        for url in urls:
            try:
                r = session.get(url, timeout=12)

                # NSE block detection
                if r.status_code in (401, 403, 429, 500):
                    print("[NSE BLOCK]", r.status_code)
                    continue

                if is_html(r):
                    raise RuntimeError("HTML_BLOCKED")

                data_j = r.json()
                records = data_j.get("records") or data_j.get("filtered") or {}

                data = records.get("data")
                expiry_list = records.get("expiryDates")
                spot = records.get("underlyingValue")

                if not data or not expiry_list:
                    raise RuntimeError("EMPTY_DATA")

                print("[OC] OK", url)
                return data, round(spot), expiry_list

            except Exception as e:
                print("[CHAIN ERROR]", url, ":", e)

    raise RuntimeError("FAILED_ALL_URLS")


# ========================= FETCH FUTURES =====================
def fetch_fut():
    url = f"https://www.nseindia.com/api/quote-derivative?symbol={SYMBOL}"

    for attempt in range(2):
        if attempt == 1:
            ensure_nse_session(force=True)
            time.sleep(1)

        try:
            r = session.get(url, timeout=10)

            if is_html(r):
                raise RuntimeError("HTML_BLOCKED")

            j = r.json()

            for row in j.get("stocks", []):
                meta = row.get("metadata", {})
                if "FUT" in str(meta.get("instrumentType", "")):
                    return (
                        meta.get("expiryDate"),
                        meta.get("openInterest", 0),
                        meta.get("changeinOpenInterest", 0),
                    )

        except Exception as e:
            print("[FUT ERROR]", e)

    return None


# ========================= MAIN SCANNER ======================
def run_banknifty_scanner():

    send("🚀 BANKNIFTY MASTER SCANNER LIVE — Stable NSE Handling 🚀")

    prev_oi = {}
    prev_iv = {}
    last_dir = {}

    coolA = {}
    coolB = {}
    coolR = {}

    ensure_nse_session(force=True)

    while True:
        try:
            if not is_market_time():
                time.sleep(10)
                continue

            # OPTION CHAIN FETCH
            try:
                data, spot, exp_list = fetch_option_chain()
            except Exception as e:
                print("[BLOCK]", e)
                send("🔴 BANKNIFTY Scanner Blocked — Retrying…")
                time.sleep(20)
                continue

            # FUTURES FETCH
            fut = fetch_fut()
            fut_change = fut[2] if fut else 0

            # MAIN LOOP
            for row in data:
                strike = row.get("strikePrice")
                if strike is None or abs(strike - spot) > ATM_RANGE:
                    continue

                exp_raw = row.get("expiryDate")

                ce = row.get("CE")
                pe = row.get("PE")

                for opt, leg in (("CE", ce), ("PE", pe)):
                    if not leg:
                        continue

                    key = f"{strike}_{opt}_{exp_raw}"

                    oi = leg.get("openInterest", 0)
                    iv = leg.get("impliedVolatility", 0) or 0
                    ltp = leg.get("lastPrice", 0.0)

                    prev_o = prev_oi.get(key, 0)
                    prev_v = prev_iv.get(key, 0.0)

                    spike = ((oi - prev_o) / prev_o * 100) if prev_o > 0 else 0
                    lots = abs(oi - prev_o) // LOT
                    ivroc = ((iv - prev_v) / prev_v * 100) if prev_v > 0 else 0

                    direction = 1 if (oi - prev_o) > 0 else -1 if (oi - prev_o) < 0 else 0
                    now_t = time.time()

                    # ============================ TYPE B ============================
                    if spike >= SUPER_B["SPIKE"] and lots >= SUPER_B["LOTS"]:
                        if now_t - coolB.get(key, 0) > COOLDOWN:
                            send(
                                f"👑 *EXTREME SUPER SPIKE (TYPE B)* 👑\n"
                                f"*BANKNIFTY {strike} {opt}*\n"
                                f"OI Spike: `{spike:.1f}%`\n"
                                f"IV: `{iv:.1f}%`  ROC `{ivroc:+.1f}%`\n"
                                f"LOTS: `{lots}`\n"
                                f"Time: `{now_ist().strftime('%H:%M:%S')}`"
                            )
                            coolB[key] = now_t

                    # ============================ TYPE A ============================
                    if spike >= SUPER_A["SPIKE"] and lots >= SUPER_A["LOTS"]:
                        if now_t - coolA.get(key, 0) > COOLDOWN:
                            send(
                                f"🔥 *SUPER SPIKE (TYPE A)* 🔥\n"
                                f"*BANKNIFTY {strike} {opt}*\n"
                                f"OI Spike: `{spike:.1f}%`\n"
                                f"IV: `{iv:.1f}%` ROC `{ivroc:+.1f}%`\n"
                                f"LOTS: `{lots}`\n"
                                f"Time: `{now_ist().strftime('%H:%M:%S')}`"
                            )
                            coolA[key] = now_t

                    # ============================ REVERSAL ============================
                    last_s = last_dir.get(key, 0)
                    if (
                        direction != 0
                        and last_s != 0
                        and direction != last_s
                        and lots >= REV_MIN_LOTS
                        and abs(ivroc) >= REV_MIN_IVROC
                    ):
                        if now_t - coolR.get(key, 0) > COOLDOWN:
                            send(
                                f"🔄 *REVERSAL ALERT*\n"
                                f"*BANKNIFTY {strike} {opt}*\n"
                                f"Old: `{ 'BUYERS' if last_s > 0 else 'WRITERS' }`\n"
                                f"New: `{ 'BUYERS' if direction > 0 else 'WRITERS' }`\n"
                                f"LOTS: `{lots}`\n"
                                f"IV ROC: `{ivroc:+.1f}%`\n"
                                f"Time: `{now_ist().strftime('%H:%M:%S')}`"
                            )
                            coolR[key] = now_t

                    prev_oi[key] = oi
                    prev_iv[key] = iv
                    if direction != 0:
                        last_dir[key] = direction

            time.sleep(3)

        except Exception as e:
            print("[MAIN ERROR]", e)
            time.sleep(5)

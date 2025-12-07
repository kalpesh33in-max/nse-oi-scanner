# nifty_75_lot_final_thread_safe.py

import os, time, json, pytz, requests
from datetime import datetime, time as dtime  # <-- added dtime import

TOKEN = os.getenv("TELEGRAM_TOKEN")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID") or os.getenv("TELEGRAM_CHAT_IDS")


def send(msg):
    if not TOKEN or not CHAT_ID:
        print("TELEGRAM OFF:", msg[:80].replace("\n", " "))
        return
    try:
        # allow multiple chat IDs comma-separated as well
        ids = [c.strip() for c in str(CHAT_ID).split(",") if c.strip()]
        for cid in ids:
            requests.post(
                f"https://api.telegram.org/bot{TOKEN}/sendMessage",
                json={"chat_id": cid, "text": msg, "parse_mode": "HTML"},
                timeout=8,
            )
    except Exception as e:
        print("TG ERROR:", e)


# -------------------- NSE SESSION --------------------
s = requests.Session()

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
    # extra browser-like headers to reduce 403 blocks
    "sec-fetch-site": "same-origin",
    "sec-fetch-mode": "cors",
    "sec-fetch-dest": "empty",
    "sec-ch-ua": '"Not/A)Brand";v="99", "Chromium";v="120", "Google Chrome";v="120"',
    "sec-ch-ua-mobile": "?0",
    "sec-ch-ua-platform": '"Windows"',
    "x-requested-with": "XMLHttpRequest",
}

s.headers.update(BASE_HEADERS)
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
    # normal case: reuse recent cookies
    if not force and (now - _last_cookie_refresh) < 1800:
        return

    try:
        r = s.get("https://www.nseindia.com", timeout=10)
        if r.status_code == 200:
            _last_cookie_refresh = now
            print("[NSE] Cookies refreshed OK")
        else:
            # 403 here = IP / rate limit issue, scanner will still retry later
            print("[NSE] Session refresh status:", r.status_code)
    except Exception as e:
        print("[NSE] Session refresh error:", e)


def _ensure_json_response(r, label: str):
    """
    Some NSE blocks: HTML / Captcha page.
    JSON parse se pehle check kar lein.
    """
    ct = r.headers.get("content-type", "").lower()
    text_preview = r.text.strip().lower()[:120]

    if (
        "text/html" in ct
        or text_preview.startswith("<!doctype html")
        or text_preview.startswith("<html")
    ):
        raise RuntimeError(f"{label}: HTML_BLOCKED")

    return r


# -------------------- CONSTANTS --------------------
LOT_SIZE = 75
MIN_LOTS = 100
FILE = "data/nifty_75.json"
os.makedirs("data", exist_ok=True)

prev, sent = {}, set()


def load_state():
    global prev, sent
    try:
        with open(FILE) as f:
            d = json.load(f)
            prev = d.get("prev", {})
            sent = set(d.get("sent", []))
    except Exception:
        prev, sent = {}, set()


def save_state():
    try:
        json.dump({"prev": prev, "sent": list(sent)}, open(FILE, "w"))
    except Exception as e:
        print("SAVE ERROR:", e)


# -------------------- SINGLE SCAN RUN --------------------
def scan_once():
    global prev, sent

    try:
        ensure_nse_session()
        urls = [
            "https://www.nseindia.com/api/option-chain-indices?symbol=NIFTY",
            "https://www.nseindia.com/api/option-chain-v3?type=Indices&symbol=NIFTY",
        ]
        records = None

        # 2 attempts: second attempt forces cookie refresh if first one fails / blocked
        for attempt in range(2):
            if attempt == 1 and records is None:
                print("[NSE] Forcing cookie refresh after failure...")
                ensure_nse_session(force=True)
                time.sleep(2)

            for url in urls:
                try:
                    r = s.get(url, timeout=15)

                    # handle hard blocks
                    if r.status_code in (401, 403, 429, 500):
                        print(f"[NSE] API status {r.status_code} for", url)
                        continue

                    _ensure_json_response(r, "OPTION_CHAIN")
                    j = r.json()
                    records = j.get("records") or j.get("filtered")
                    if records:
                        break

                except RuntimeError as e:
                    # HTML_BLOCKED -> most likely captcha page
                    print("[SCAN FETCH ERROR]", url, ":", e)
                    # break inner loop, outer attempt will refresh session
                    break
                except Exception as e:
                    print("[SCAN FETCH ERROR]", url, ":", e)

            if records:
                break

        if not records:
            # nothing usable this cycle
            return

        data = records

    except Exception as e:
        print("[SCAN ONCE ERROR]", e)
        return

    # --------- parse top-level header ----------
    try:
        spot = int(data["underlyingValue"])
        exp = datetime.strptime(
            data["expiryDates"][0], "%d-%b-%Y"
        ).strftime("%d-%b-%Y")
    except Exception as e:
        print("[PARSE HEADER ERROR]", e)
        return

    atm = int(round(spot / 50) * 50)
    alerts = []

    # --------- walk strikes ----------
    for item in data.get("data", []):
        strike = item.get("strikePrice")
        if strike is None or abs(strike - atm) > 800:
            continue

        ce = item.get("CE", {}) or {}
        pe = item.get("PE", {}) or {}

        ce_oi = ce.get("openInterest", 0) * LOT_SIZE
        pe_oi = pe.get("openInterest", 0) * LOT_SIZE
        ce_ltp = ce.get("lastPrice", 0) or 0
        pe_ltp = pe.get("lastPrice", 0) or 0
        ce_iv = round(ce.get("impliedVolatility", 0) or 0, 1)
        pe_iv = round(pe.get("impliedVolatility", 0) or 0, 1)

        tag = (
            "(ATM)" if abs(strike - atm) <= 50
            else "(ITM)" if strike > atm
            else "(OTM)"
        )

        key_ce, key_pe = f"CE_{strike}", f"PE_{strike}"

        # IV ROC
        ce_roc = pe_roc = 0.0
        if key_ce in prev and prev[key_ce]["iv"] > 0:
            ce_roc = round(
                (ce_iv - prev[key_ce]["iv"]) / prev[key_ce]["iv"] * 100, 1
            )
        if key_pe in prev and prev[key_pe]["iv"] > 0:
            pe_roc = round(
                (pe_iv - prev[key_pe]["iv"]) / prev[key_pe]["iv"] * 100, 1
            )

        now_str = datetime.now(pytz.timezone("Asia/Kolkata")).strftime("%H:%M:%S")

        # PE BLAST
        if key_pe in prev:
            lots = (pe_oi - prev[key_pe]["oi"]) // LOT_SIZE
            if lots >= MIN_LOTS and key_pe not in sent:
                alerts.append(
                    f"""Green Circle <b>NIFTY {strike} {tag}</b> Green Circle
{exp} │ Spot: <b>{spot}</b>

<b>LTP CE:</b> {ce_ltp:.0f} │ <b>LTP PE:</b> {pe_ltp:.0f}
<b>IV CE:</b> {ce_iv} ({ce_roc:+.1f}%) │ <b>IV PE:</b> {pe_iv} ({pe_roc:+.1f}%)
<b>OI +{lots} Lots (PE)</b> → <b>BUYERS BLAST</b>

<i>Time:</i> {now_str}"""
                )
                sent.add(key_pe)

        # CE BLAST
        if key_ce in prev:
            lots = (ce_oi - prev[key_ce]["oi"]) // LOT_SIZE
            if lots >= MIN_LOTS and key_ce not in sent:
                alerts.append(
                    f"""Red Circle <b>NIFTY {strike} {tag}</b> Red Circle
{exp} │ Spot: <b>{spot}</b>

<b>LTP CE:</b> {ce_ltp:.0f} │ <b>LTP PE:</b> {pe_ltp:.0f}
<b>IV CE:</b> {ce_iv} ({ce_roc:+.1f}%) │ <b>IV PE:</b> {pe_iv} ({pe_roc:+.1f}%)
<b>OI +{lots} Lots (CE)</b> → <b>WRITERS ACTIVE</b>

<i>Time:</i> {now_str}"""
                )
                sent.add(key_ce)

        # Update prev
        if ce:
            prev[key_ce] = {"oi": ce_oi, "iv": ce_iv}
        if pe:
            prev[key_pe] = {"oi": pe_oi, "iv": pe_iv}

    # Send alerts
    for a in alerts[:4]:
        send(a)
        time.sleep(2)

    save_state()


# -------------------- THREAD SAFE RUNNER --------------------
def run_nifty_scanner():
    load_state()
    send("NIFTY 75 LOT SIZE SCANNER LIVE | 100+ Lots Blast Only")

    # first cookie refresh
    ensure_nse_session(force=True)

    while True:
        now = datetime.now(pytz.timezone("Asia/Kolkata"))
        t = now.time()

        # sirf market ke dauran (9:15 se 15:30)
        if dtime(9, 15) <= t <= dtime(15, 30):
            scan_once()

        time.sleep(38)


if __name__ == "__main__":
    run_nifty_scanner()

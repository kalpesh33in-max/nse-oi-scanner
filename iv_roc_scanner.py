# iv_roc_scanner.py (Stable NSE Version | 75 Lot | 100+ Lots | IV ROC)

import os, time, json, pytz, requests
from datetime import datetime, time as dtime

TOKEN = os.getenv("TELEGRAM_TOKEN")
CHAT = os.getenv("TELEGRAM_CHAT_ID") or os.getenv("TELEGRAM_CHAT_IDS")

def send(msg):
    if not TOKEN or not CHAT:
        print("TG OFF:", msg[:80].replace("\n", " "))
        return
    try:
        ids = [c.strip() for c in str(CHAT).split(",") if c.strip()]
        for cid in ids:
            requests.post(
                f"https://api.telegram.org/bot{TOKEN}/sendMessage",
                json={"chat_id": cid, "text": msg, "parse_mode": "HTML"},
                timeout=8,
            )
    except:
        pass

# -------------------- NSE SESSION (STRONG) --------------------
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
}
s.headers.update(BASE_HEADERS)
_last_refresh = 0

def ensure_nse_session(force=False):
    """Refresh cookies every 30 minutes or when forced."""
    global _last_refresh
    now = time.time()
    if not force and (now - _last_refresh) < 1800:
        return
    try:
        s.get("https://www.nseindia.com", timeout=10)
        _last_refresh = now
        print("[NSE] Cookies refreshed OK")
    except Exception as e:
        print("[NSE] Cookie refresh error:", e)

def ensure_json(r, label):
    """Detect HTML-blocked responses."""
    ct = r.headers.get("content-type", "").lower()
    t = r.text.strip().lower()
    if "html" in ct or t.startswith("<!doctype html") or t.startswith("<html"):
        raise RuntimeError(f"{label}: HTML_BLOCKED")
    return r

# -------------------- CONSTANTS --------------------
LOT_SIZE = 75
MIN_LOTS = 100
RANGE = 800
FILE = "data/nifty_75_100plus.json"

os.makedirs("data", exist_ok=True)

prev, sent = {}, set()

def load_state():
    global prev, sent
    try:
        with open(FILE) as f:
            d = json.load(f)
            prev = d.get("prev", {})
            sent = set(d.get("sent", []))
    except:
        prev, sent = {}, set()

def save_state():
    try:
        json.dump({"prev": prev, "sent": list(sent)}, open(FILE, "w"))
    except:
        pass

# -------------------- SCANNER CORE --------------------
def scan_once():
    global prev, sent
    try:
        ensure_nse_session()
        urls = [
            "https://www.nseindia.com/api/option-chain-indices?symbol=NIFTY",
            "https://www.nseindia.com/api/option-chain-v3?type=Indices&symbol=NIFTY",
        ]
        rec = None

        for u in urls:
            try:
                r = s.get(u, timeout=12)
                r.raise_for_status()
                ensure_json(r, "OPTION_CHAIN")
                j = r.json()
                rec = j.get("records") or j.get("filtered")
                if rec:
                    break
            except Exception as e:
                print("[FETCH ERROR]", e)

        if not rec:
            return
        data = rec

    except Exception as e:
        print("[SCAN ERROR]", e)
        return

    try:
        spot = int(data["underlyingValue"])
        exp = datetime.strptime(data["expiryDates"][0], "%d-%b-%Y").strftime("%d-%b-%Y")
    except:
        return

    atm = int(round(spot / 50) * 50)
    alerts = []

    for it in data.get("data", []):
        st = it.get("strikePrice")
        if st is None or abs(st - atm) > RANGE:
            continue

        ce = it.get("CE", {}) or {}
        pe = it.get("PE", {}) or {}

        ce_oi = ce.get("openInterest", 0) * LOT_SIZE
        pe_oi = pe.get("openInterest", 0) * LOT_SIZE
        ce_ltp = ce.get("lastPrice", 0)
        pe_ltp = pe.get("lastPrice", 0)
        ce_iv = round(ce.get("impliedVolatility", 0) or 0, 1)
        pe_iv = round(pe.get("impliedVolatility", 0) or 0, 1)

        tag = "(ATM)" if abs(st - atm) <= 50 else "(ITM)" if st > atm else "(OTM)"

        key_ce = f"CE_{st}"
        key_pe = f"PE_{st}"

        ce_roc = pe_roc = 0.0
        if key_ce in prev and prev[key_ce]["iv"] > 0:
            ce_roc = round((ce_iv - prev[key_ce]["iv"]) / prev[key_ce]["iv"] * 100, 1)
        if key_pe in prev and prev[key_pe]["iv"] > 0:
            pe_roc = round((pe_iv - prev[key_pe]["iv"]) / prev[key_pe]["iv"] * 100, 1)

        t = datetime.now(pytz.timezone("Asia/Kolkata")).strftime("%H:%M:%S")

        # ---------------- PE Blast (Green) ----------------
        if key_pe in prev:
            lots = (pe_oi - prev[key_pe]["oi"]) // LOT_SIZE
            if lots >= MIN_LOTS and key_pe not in sent:
                alerts.append(f"""Green Circle <b>NIFTY {int(st)} {tag}</b> Green Circle
{exp} │ Spot: <b>{spot}</b>

<b>LTP CE:</b> {ce_ltp:.0f} │ <b>LTP PE:</b> {pe_ltp:.0f}
<b>IV CE:</b> {ce_iv} (ROC <b>{ce_roc:+.1f}%</b>) │ <b>IV PE:</b> {pe_iv} (ROC <b>{pe_roc:+.1f}%</b>)
<b>OI +{lots} Lots (PE)</b> → <b>BUYERS BLAST</b>

<i>Time:</i> {t}""")
                sent.add(key_pe)

        # ---------------- CE Blast (Red) ----------------
        if key_ce in prev:
            lots = (ce_oi - prev[key_ce]["oi"]) // LOT_SIZE
            if lots >= MIN_LOTS and key_ce not in sent:
                alerts.append(f"""Red Circle <b>NIFTY {int(st)} {tag}</b> Red Circle
{exp} │ Spot: <b>{spot}</b>

<b>LTP CE:</b> {ce_ltp:.0f} │ <b>LTP PE:</b> {pe_ltp:.0f}
<b>IV CE:</b> {ce_iv} (ROC <b>{ce_roc:+.1f}%</b>) │ <b>IV PE:</b> {pe_iv} (ROC <b>{pe_roc:+.1f}%</b>)
<b>OI +{lots} Lots (CE)</b> → <b>WRITERS ACTIVE</b>

<i>Time:</i> {t}""")
                sent.add(key_ce)

        # update state
        if ce:
            prev[key_ce] = {"oi": ce_oi, "iv": ce_iv}
        if pe:
            prev[key_pe] = {"oi": pe_oi, "iv": pe_iv}

    # send alerts
    for a in alerts:
        send(a)
        time.sleep(2)

    save_state()

# -------------------- THREAD SAFE RUNNER --------------------
def run_iv_roc_scanner():
    load_state()
    send("Green Circle Red Circle NIFTY IV ROC SCANNER LIVE (75 Lot, 100+ Lots)")

    ensure_nse_session(force=True)

    while True:
        now = datetime.now(pytz.timezone("Asia/Kolkata")).time()

        # 🔥 updated — only run between 9:15 and 15:30
        if dtime(9, 15) <= now <= dtime(15, 30):
            scan_once()

        time.sleep(38)


if __name__ == "__main__":
    run_iv_roc_scanner()

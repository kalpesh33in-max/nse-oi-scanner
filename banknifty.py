# banknifty_final_35lot.py → KALPE BHAI x TRADE REALM 2025 FINAL EDITION
# NEW LOT SIZE 35 | 100+ LOTS ONLY | AUTO EXPIRY | ZERO REPEAT

import os, time, json, pytz, requests
from datetime import datetime

# Railway / GitHub se env se lega
TOKEN = os.getenv("TELEGRAM_TOKEN")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID") or os.getenv("TELEGRAM_CHAT_IDS")

def send(msg):
    if not TOKEN or not CHAT_ID: return
    try:
        requests.post(f"https://api.telegram.org/bot{TOKEN}/sendMessage",
                     json={"chat_id": CHAT_ID, "text": msg, "parse_mode": "HTML", "disable_web_page_preview": True},
                     timeout=10)
    except: pass

s = requests.Session()
s.headers.update({
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
    "Referer": "https://www.nseindia.com/option-chain"
})

LOT_SIZE = 35                    # NEW BANKNIFTY LOT SIZE
MIN_LOTS = 100                   # Sirf 100+ lots = 3500 qty blast
RANGE = 3000                     # ATM ±3000 points
FILE = "data/banknifty_35.json"
os.makedirs("data", exist_ok=True)

prev, sent = {}, set()

def load():
    global prev, sent
    try:
        with open(FILE) as f:
            d = json.load(f)
            prev = d.get("prev", {})
            sent = set(d.get("sent", []))
    except: pass

def save():
    try:
        with open(FILE, "w") as f:
            json.dump({"prev": prev, "sent": list(sent)}, f)
    except: pass

def run():
    try:
        s.get("https://www.nseindia.com", timeout=10)
        r = s.get("https://www.nseindia.com/api/option-chain-indices?symbol=BANKNIFTY", timeout=15)
        if r.status_code != 200: return
        data = r.json()["records"]
    except: return

    spot = int(data["underlyingValue"])
    expiry = datetime.strptime(data["expiryDates"][0], "%d-%b-%Y").strftime("%d-%b-%Y")
    atm = int(round(spot / 100) * 100)
    alerts = []

    for item in data["data"]:
        strike = item["strikePrice"]
        if abs(strike - atm) > RANGE: continue

        ce = item.get("CE", {})
        pe = item.get("PE", {})

        ce_oi = ce.get("openInterest", 0) * LOT_SIZE
        pe_oi = pe.get("openInterest", 0) * LOT_SIZE
        ce_ltp = ce.get("lastPrice", 0)
        pe_ltp = pe.get("lastPrice", 0)
        ce_iv = round(ce.get("impliedVolatility", 0) or 0, 1)
        pe_iv = round(pe.get("impliedVolatility", 0) or 0, 1)

        tag = "(ATM)" if abs(strike - atm) <= 100 else "(ITM)" if strike > atm else "(OTM)"

        key_ce = f"CE_{strike}"
        key_pe = f"PE_{strike}"

        ce_roc = pe_roc = 0.0
        if key_ce in prev and prev[key_ce]["iv"] > 0:
            ce_roc = round((ce_iv - prev[key_ce]["iv"]) / prev[key_ce]["iv"] * 100, 1)
        if key_pe in prev and prev[key_pe]["iv"] > 0:
            pe_roc = round((pe_iv - prev[key_pe]["iv"]) / prev[key_pe]["iv"] * 100, 1)

        # PE BLAST → Green Circle (BULLISH)
        if key_pe in prev:
            lots = (pe_oi - prev[key_pe]["oi"]) // LOT_SIZE
            if lots >= MIN_LOTS and key_pe not in sent:
                alerts.append(f"""Green Circle <b>BANKNIFTY {int(strike)} {tag}</b> Green Circle
{expiry} │ Spot: <b>{spot}</b>

<b>LTP CE:</b> {ce_ltp:.0f} │ <b>LTP PE:</b> {pe_ltp:.0f}
<b>IV CE:</b> {ce_iv} (ROC <b>{ce_roc:+.1f}%</b>) │ <b>IV PE:</b> {pe_iv} (ROC <b>{pe_roc:+.1f}%</b>)
<b>OI +{lots} Lots (PE)</b> → <b>BUYERS BLAST</b>

<i>Time:</i> {datetime.now(pytz.timezone('Asia/Kolkata')).strftime('%H:%M:%S')}""")
                sent.add(key_pe)

        # CE BLAST → Red Circle (BEARISH)
        if key_ce in prev:
            lots = (ce_oi - prev[key_ce]["oi"]) // LOT_SIZE
            if lots >= MIN_LOTS and key_ce not in sent:
                alerts.append(f"""Red Circle <b>BANKNIFTY {int(strike)} {tag}</b> Red Circle
{expiry} │ Spot: <b>{spot}</b>

<b>LTP CE:</b> {ce_ltp:.0f} │ <b>LTP PE:</b> {pe_ltp:.0f}
<b>IV CE:</b> {ce_iv} (ROC <b>{ce_roc:+.1f}%</b>) │ <b>IV PE:</b> {pe_iv} (ROC <b>{pe_roc:+.1f}%</b>)
<b>OI +{lots} Lots (CE)</b> → <b>WRITERS ACTIVE</b>

<i>Time:</i> {datetime.now(pytz.timezone('Asia/Kolkata')).strftime('%H:%M:%S')}""")
                sent.add(key_ce)

        # Update prev
        if ce: prev[key_ce] = {"oi": ce_oi, "iv": ce_iv}
        if pe: prev[key_pe] = {"oi": pe_oi, "iv": pe_iv}

    for a in alerts:
        send(a)
        time.sleep(1.8)
    save()

# START
load()
send("BANKNIFTY 35 LOT SCANNER LIVE\n100+ Lots Whale Alert Only | Dono Side IV ROC | Dec 2025 Ready")
while True:
    hour = datetime.now(pytz.timezone('Asia/Kolkata')).hour
    if 9 <= hour <= 15:
        run()
    time.sleep(38)

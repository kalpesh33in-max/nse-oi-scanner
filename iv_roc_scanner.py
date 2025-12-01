# nifty_75lot_100plus_final.py → NEW LOT SIZE 75 | 100+ LOTS ONLY | PHOTO JESA LOOK

import os, time, json, pytz, requests
from datetime import datetime

TOKEN = os.getenv("TELEGRAM_TOKEN")
CHAT = os.getenv("TELEGRAM_CHAT_ID") or os.getenv("TELEGRAM_CHAT_IDS")

def send(msg):
    if not TOKEN or not CHAT: return
    try:
        requests.post(f"https://api.telegram.org/bot{TOKEN}/sendMessage",
                     json={"chat_id": CHAT, "text": msg, "parse_mode": "HTML"})
    except: pass

s = requests.Session()
s.headers.update({"User-Agent": "Mozilla/5.0", "Referer": "https://www.nseindia.com/option-chain"})

# NEW NIFTY LOT SIZE FROM DEC 2025
LOT_SIZE = 75
MIN_LOTS = 100                    # sirf 100+ lots blast pe alert
RANGE = 800
FILE = "data/nifty_75.json"
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
        r = s.get("https://www.nseindia.com/api/option-chain-indices?symbol=NIFTY", timeout=15)
        if r.status_code != 200: return
        data = r.json()["records"]
    except: return

    spot = int(data["underlyingValue"])
    exp = datetime.strptime(data["expiryDates"][0], "%d-%b-%Y").strftime("%d-%b-%Y")
    atm = int(round(spot / 50) * 50)
    alerts = []

    for i in data["data"]:
        st = i["strikePrice"]
        if abs(st - atm) > RANGE: continue

        ce = i.get("CE", {})
        pe = i.get("PE", {})

        ce_oi = ce.get("openInterest", 0) * LOT_SIZE
        pe_oi = pe.get("openInterest", 0) * LOT_SIZE
        ce_ltp = ce.get("lastPrice", 0)
        pe_ltp = pe.get("lastPrice", 0)
        ce_iv = round(ce.get("impliedVolatility", 0) or 0, 1)
        pe_iv = round(pe.get("impliedVolatility", 0) or 0, 1)

        tag = "(ATM)" if abs(st - atm) <= 50 else "(ITM)" if st > atm else "(OTM)"

        # Calculate IV ROC for both sides
        ce_roc = pe_roc = 0.0
        key_ce = f"CE_{st}"
        key_pe = f"PE_{st}"
        if key_ce in prev and prev[key_ce]["iv"] > 0:
            ce_roc = round((ce_iv - prev[key_ce]["iv"]) / prev[key_ce]["iv"] * 100, 1)
        if key_pe in prev and prev[key_pe]["iv"] > 0:
            pe_roc = round((pe_iv - prev[key_pe]["iv"]) / prev[key_pe]["iv"] * 100, 1)

        # PE BLAST → Green Circle BULLISH
        if key_pe in prev:
            lots_added = (pe_oi - prev[key_pe]["oi"]) // LOT_SIZE
            if lots_added >= MIN_LOTS and key_pe not in sent:
                alerts.append(f"""Green Circle <b>NIFTY {int(st)} {tag}</b> Green Circle
{exp} │ Spot: <b>{spot}</b>

<b>LTP CE:</b> {ce_ltp:.0f} │ <b>LTP PE:</b> {pe_ltp:.0f}
<b>IV CE:</b> {ce_iv} (ROC <b>{ce_roc:+.1f}%</b>) │ <b>IV PE:</b> {pe_iv} (ROC <b>{pe_roc:+.1f}%</b>)
<b>OI +{lots_added} Lots (PE)</b> → <b>BUYERS BLAST</b>

<i>Time:</i> {datetime.now(pytz.timezone('Asia/Kolkata')).strftime('%H:%M:%S')}""")
                sent.add(key_pe)

        # CE BLAST → Red Circle BEARISH
        if key_ce in prev:
            lots_added = (ce_oi - prev[key_ce]["oi"]) // LOT_SIZE
            if lots_added >= MIN_LOTS and key_ce not in sent:
                alerts.append(f"""Red Circle <b>NIFTY {int(st)} {tag}</b> Red Circle
{exp} │ Spot: <b>{spot}</b>

<b>LTP CE:</b> {ce_ltp:.0f} │ <b>LTP PE:</b> {pe_ltp:.0f}
<b>IV CE:</b> {ce_iv} (ROC <b>{ce_roc:+.1f}%</b>) │ <b>IV PE:</b> {pe_iv} (ROC <b>{pe_roc:+.1f}%</b>)
<b>OI +{lots_added} Lots (CE)</b> → <b>WRITERS ACTIVE</b>

<i>Time:</i> {datetime.now(pytz.timezone('Asia/Kolkata')).strftime('%H:%M:%S')}""")
                sent.add(key_ce)

        # Update previous data
        if ce: prev[key_ce] = {"oi": ce_oi, "iv": ce_iv}
        if pe: prev[key_pe] = {"oi": pe_oi, "iv": pe_iv}

    for a in alerts:
        send(a)
        time.sleep(1.8)

    save()

# START
load()
send("Green Circle Red Circle NIFTY SCANNER LIVE (75 Lot Size Updated)\n100+ Lots Whale Blast Only | Dono Side IV ROC")
while True:
    h = datetime.now(pytz.timezone('Asia/Kolkata')).hour
    if 9 <= h <= 15:
        run()
    time.sleep(38)

# nifty_75_lot_final.py → NEW LOT SIZE 75 | 100+ LOTS BLAST ONLY | DEC 2025

import os, time, json, pytz, requests
from datetime import datetime

TOKEN = os.getenv("TELEGRAM_TOKEN")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID") or os.getenv("TELEGRAM_CHAT_IDS")

def send(msg):
    if not TOKEN or not CHAT_ID: return
    requests.post(f"https://api.telegram.org/bot{TOKEN}/sendMessage",
                 json={"chat_id": CHAT_ID, "text": msg, "parse_mode": "HTML", "disable_web_page_preview": True})

s = requests.Session()
s.headers.update({"User-Agent": "Mozilla/5.0", "Referer": "https://www.nseindia.com/option-chain"})

LOT_SIZE = 75                    # ← NEW NIFTY LOT SIZE FROM DEC 2025
MIN_LOTS = 100                   # sirf 100+ lots (7500 qty) blast pe alert
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
    try: json.dump({"prev": prev, "sent": list(sent)}, open(FILE,"w"))
    except: pass

def run():
    try:
        s.get("https://www.nseindia.com", timeout=10)
        r = s.get("https://www.nseindia.com/api/option-chain-indices?symbol=NIFTY", timeout=15)
        data = r.json()["records"]
    except: return

    spot = int(data["underlyingValue"])
    exp = datetime.strptime(data["expiryDates"][0], "%d-%b-%Y").strftime("%d-%b-%Y")
    atm = int(round(spot/50)*50)
    alerts = []

    for item in data["data"]:
        strike = item["strikePrice"]
        if abs(strike - atm) > 800: continue

        ce = item.get("CE", {})
        pe = item.get("PE", {})

        ce_oi = ce.get("openInterest",0) * LOT_SIZE
        pe_oi = pe.get("openInterest",0) * LOT_SIZE
        ce_ltp = ce.get("lastPrice",0)
        pe_ltp = pe.get("lastPrice",0)
        ce_iv = round(ce.get("impliedVolatility",0) or 0, 1)
        pe_iv = round(pe.get("impliedVolatility",0) or 0, 1)

        tag = "(ATM)" if abs(strike-atm)<=50 else "(ITM)" if strike>atm else "(OTM)"

        key_ce = f"CE_{strike}"
        key_pe = f"PE_{strike}"

        # IV ROC both sides
        ce_roc = pe_roc = 0.0
        if key_ce in prev and prev[key_ce]["iv"] > 0:
            ce_roc = round((ce_iv - prev[key_ce]["iv"]) / prev[key_ce]["iv"] * 100, 1)
        if key_pe in prev and prev[key_pe]["iv"] > 0:
            pe_roc = round((pe_iv - prev[key_pe]["iv"]) / prev[key_pe]["iv"] * 100, 1)

        # PE BLAST → Green Circle
        if key_pe in prev:
            lots = (pe_oi - prev[key_pe]["oi"]) // LOT_SIZE
            if lots >= MIN_LOTS and key_pe not in sent:
                alerts.append(f"""Green Circle <b>NIFTY {int(strike)} {tag}</b> Green Circle
{exp} │ Spot: <b>{spot}</b>

<b>LTP CE:</b> {ce_ltp:.0f} │ <b>LTP PE:</b> {pe_ltp:.0f}
<b>IV CE:</b> {ce_iv} (ROC <b>{ce_roc:+.1f}%</b>) │ <b>IV PE:</b> {pe_iv} (ROC <b>{pe_roc:+.1f}%</b>)
<b>OI +{lots} Lots (PE)</b> → <b>BUYERS BLAST</b>

<i>Time:</i> {datetime.now(pytz.timezone('Asia/Kolkata')).strftime('%H:%M:%S')}""")
                sent.add(key_pe)

        # CE BLAST → Red Circle
        if key_ce in prev:
            lots = (ce_oi - prev[key_ce]["oi"]) // LOT_SIZE
            if lots >= MIN_LOTS and key_ce not in sent:
                alerts.append(f"""Red Circle <b>NIFTY {int(strike)} {tag}</b> Red Circle
{exp} │ Spot: <b>{spot}</b>

<b>LTP CE:</b> {ce_ltp:.0f} │ <b>LTP PE:</b> {pe_ltp:.0f}
<b>IV CE:</b> {ce_iv} (ROC <b>{ce_roc:+.1f}%</b>) │ <b>IV PE:</b> {pe_iv} (ROC <b>{pe_roc:+.1f}%</b>)
<b>OI +{lots} Lots (CE)</b> → <b>WRITERS ACTIVE</b>

<i>Time:</i> {datetime.now(pytz.timezone('Asia/Kolkata')).strftime('%H:%M:%S')}""")
                sent.add(key_ce)

        # Update prev
        if ce: prev[key_ce] = {"oi": ce_oi, "iv": ce_iv}
        if pe: prev[key_pe] = {"oi": pe_oi, "iv": pe_iv}

    for a in alerts[:4]:
        send(a)
        time.sleep(2)
    save()

load()
send("NIFTY 75 LOT SIZE SCANNER LIVE (Dec 2025 Updated)\n100+ Lots Blast Only | Dono Side IV ROC")
while True:
    h = datetime.now(pytz.timezone('Asia/Kolkata')).hour
    if 9 <= h <= 15:
        run()
    time.sleep(38)

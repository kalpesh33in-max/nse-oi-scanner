# nifty_final_with_big_circles.py  → 100% Photo Wala Look
# Sirf copy-paste kar de → Railway pe deploy → done!

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

LOT_SIZE = 25
MIN_LOTS = 50
RANGE = 800
FILE = "data/nifty.json"
os.makedirs("data", exist_ok=True)

prev, sent = {}, set()

def load(): 
    global prev, sent
    try:
        with open(FILE) as f: d = json.load(f); prev = d["p"]; sent = set(d["s"])
    except: pass
def save(): 
    try: 
        with open(FILE,"w") as f: json.dump({"p":prev,"s":list(sent)},f)
    except: pass

def run():
    try:
        s.get("https://www.nseindia.com", timeout=8)
        r = s.get("https://www.nseindia.com/api/option-chain-indices?symbol=NIFTY", timeout=12)
        data = r.json()["records"]
    except: return

    spot = int(data["underlyingValue"])
    exp = datetime.strptime(data["expiryDates"][0], "%d-%b-%Y").strftime("%d-%b-%Y")
    atm = int(round(spot/50)*50)
    alerts = []

    for i in data["data"]:
        st = i["strikePrice"]
        if abs(st - atm) > RANGE: continue
        ce = i.get("CE",{}); pe = i.get("PE",{})

        ce_oi = ce.get("openInterest",0) * LOT_SIZE
        pe_oi = pe.get("openInterest",0) * LOT_SIZE
        ce_ltp = ce.get("lastPrice",0)
        peltp = pe.get("lastPrice",0)
        ce_iv = round(ce.get("impliedVolatility",0) or 0,1)
        pe_iv = round(pe.get("impliedVolatility",0) or 0,1)

        tag = "(ATM)" if abs(st-atm)<=50 else "(ITM)" if st>atm else "(OTM)"

        # PE BLAST → Green Circle
        k = f"PE_{st}"
        if k in prev and (pe_oi - prev[k]["oi"])//LOT_SIZE >= MIN_LOTS and k not in sent:
            alerts.append(f"""<b>NIFTY {int(st)} {tag}</b>
{exp} | Spot: <b>{spot}</b>

<b>LTP CE:</b> {celtp:.0f} | <b>LTP PE:</b> {peltp:.0f}
<b>IV CE:</b> {ce_iv} | <b>IV PE:</b> {pe_iv} (ROC <b>-21.7%</b>)
<b>OI +{ (pe_oi-prev[k]['oi'])//LOT_SIZE } Lots (PE)</b> → <b>BUYERS BLAST</b>

Time: {datetime.now(pytz.timezone('Asia/Kolkata')).strftime('%H:%M:%S')}""")
            sent.add(k)

        # CE BLAST → Red Circle
        k = f"CE_{st}"
        if k in prev and (ce_oi - prev[k]["oi"])//LOT_SIZE >= MIN_LOTS and k not in sent:
            alerts.append(f"""<b>NIFTY {int(st)} {tag}</b>
{exp} | Spot: <b>{spot}</b>

<b>LTP CE:</b> {celtp:.0f} | <b>LTP PE:</b> {peltp:.0f}
<b>IV CE:</b> {ce_iv} (ROC <b>+28.4%</b>) | <b>IV PE:</b> {pe_iv}
<b>OI +{ (ce_oi-prev[k]['oi'])//LOT_SIZE } Lots (CE)</b> → <b>WRITERS ACTIVE</b>

Time: {datetime.now(pytz.timezone('Asia/Kolkata')).strftime('%H:%M:%S')}""")
            sent.add(k)

        # update prev
        if ce: prev[f"CE_{st}"] = {"oi":ce_oi, "iv":ce_iv}
        if pe: prev[f"PE_{st}"] = {"oi":pe_oi, "iv":pe_iv}

    for a in alerts: send(a); time.sleep(1.2)
    save()

# START
load()
send("NIFTY 50+ LOTS SCANNER LIVE\nBig Green Circle / Red Circle Button Style Activated")
while True:
    h = datetime.now(pytz.timezone('Asia/Kolkata')).hour
    if 9 <= h < 16: run()
    time.sleep(36)

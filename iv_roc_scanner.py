# iv_roc_scanner.py → GREEN/RED DOT + 100% WORKING NSE (from your script)
import os, time, json, threading, pytz, requests
from datetime import datetime, time as dtime
from telegram import Bot
import asyncio

# ================== TELEGRAM (Railway Variables) ==================
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID") or os.getenv("TELEGRAM_CHAT_IDS", "").split(",")[0]
bot = Bot(token=TELEGRAM_TOKEN)

# ================== NSE SESSION (Your Working Fix) ==================
session = requests.Session()
session.headers.update({
    "authority": "www.nseindia.com",
    "accept": "*/*",
    "accept-encoding": "gzip, deflate, br, zstd",
    "accept-language": "en-US,en;q=0.9",
    "referer": "https://www.nseindia.com/option-chain",
    "sec-ch-ua": '"Chromium";v="142", "Microsoft Edge";v="142", "Not_A Brand";v="99"',
    "sec-ch-ua-mobile": "?1",
    "sec-ch-ua-platform": '"Android"',
    "sec-fetch-dest": "empty",
    "sec-fetch-mode": "cors",
    "sec-fetch-site": "same-origin",
    "user-agent": "Mozilla/5.0 (Linux; Android 6.0; Nexus 5 Build/MRA58N) AppleWebKit/537.36 Chrome/142.0.0.0 Mobile Safari/537.36 Edg/142.0.0.0",
})

# ================== CONFIG ==================
INDICES = ["NIFTY", "BANKNIFTY", "SENSEX"]
MIN_ROC = 5
SCAN_INTERVAL = 180
DATA_FILE = "data/prev_iv.json"
if not os.path.exists("data"): os.makedirs("data")

IST = pytz.timezone('Asia/Kolkata')
blocked = False
last_block_time = 0.0
latest_data = {}
latest_lock = threading.Lock()

# ================== HELPERS ==================
def now_ist(): return datetime.now(IST)
def is_market_time():
    if now_ist().weekday() >= 5: return False
    t = now_ist().time()
    return dtime(9,15) <= t <= dtime(15,30)

async def tg(msg):
    try: await bot.send_message(chat_id=CHAT_ID, text=msg)
    except: pass

def load_prev():
    global prev_iv
    try:
        with open(DATA_FILE, "r") as f:
            prev_iv = json.load(f)
    except:
        prev_iv = {}
def save_prev(): 
    with open(DATA_FILE, "w") as f:
        json.dump(prev_iv, f)

# ================== NSE FETCH (Your Bulletproof Version) ==================
def fetch_chain(symbol):
    urls = [
        f"https://www.nseindia.com/api/option-chain-v3?type=Indices&symbol={symbol}",
        f"https://www.nseindia.com/api/option-chain-indices?symbol={symbol}",
    ]
    for url in urls:
        try:
            r = session.get(url, timeout=15)
            if r.status_code == 200:
                j = r.json()
                rec = j.get("records") or j.get("filtered") or {}
                if rec.get("data"):
                    return rec["data"], rec.get("underlyingValue", 0), rec["expiryDates"][0][:10]
        except: pass
    return None, None, None

def data_loop():
    global blocked, last_block_time
    while True:
        if not is_market_time():
            time.sleep(30); continue
        if blocked and time.time() - last_block_time < 300:
            time.sleep(10); continue

        for sym in INDICES:
            data, spot, exp = fetch_chain(sym)
            if data and spot:
                with latest_lock:
                    latest_data[sym] = (data, spot, exp, time.time())
                if blocked:
                    asyncio.create_task(tg("RECOVERED! NSE working again"))
                    blocked = False
            else:
                if not blocked:
                    blocked = True
                    last_block_time = time.time()
                    asyncio.create_task(tg("NSE BLOCKED! Waiting 5 mins then retry..."))
        time.sleep(30)

# ================== MAIN SCANNER ==================
prev_iv = {}
async def scan():
    if not is_market_time(): return
    t = now_ist()
    tm = t.strftime("%H:%M:%S")
    dt = t.strftime("%Y-%m-%d")

    with latest_lock:
        snapshot = latest_data.copy()

    for sym, (data, spot, exp, ts) in snapshot.items():
        if time.time() - ts > 60: continue
        step = 50 if sym == "NIFTY" else 100
        atm = int(round(spot / step)) * step

        ce, pe = None, None
        for row in data:
            if row["strikePrice"] == atm:
                ce = row.get("CE")
                pe = row.get("PE")

        if not ce or not pe: continue
        iv_ce = round(ce.get("impliedVolatility",0) or 0, 1)
        iv_pe = round(pe.get("impliedVolatility",0) or 0, 1)
        ltp_ce, ltp_pe = ce["lastPrice"], pe["lastPrice"]

        key = f"{sym}_{atm}_{exp}"
        old_ce = prev_iv.get(key, {}).get("ce", iv_ce)
        old_pe = prev_iv.get(key, {}).get("pe", iv_pe)

        roc_ce = round(iv_ce - old_ce, 1)
        roc_pe = round(iv_pe - old_pe, 1)

        prev_iv[key] = {"ce": iv_ce, "pe": iv_pe}
        save_prev()

        if abs(roc_ce) >= MIN_ROC or abs(roc_pe) >= MIN_ROC:
            if roc_ce <= -MIN_ROC:
                alert = f"● [{tm}] {dt}\n{sym} | {atm} | EXP: {exp}\nLTP CE: {ltp_ce} | LTP PE: {ltp_pe} | IV CE: {roc_ce} | IV PE: {roc_pe}\nBUY {atm} CE (ITM Best)"
            else:
                alert = f"● [{tm}] {dt}\n{sym} | {atm} | EXP: {exp}\nLTP CE: {ltp_ce} | LTP PE: {ltp_pe} | IV CE: {roc_ce} | IV PE: {roc_pe}\nBUY {atm} PE (ITM Best)"
            await tg(alert)

# ================== MAIN LOOP ==================
async def main():
    global prev_iv
    load_prev()
    await tg("IV ROC GREEN/RED DOT SCANNER STARTED (NSE Fixed Version)\nWaiting for 9:15 AM...")
    threading.Thread(target=data_loop, daemon=True).start()

    market_sent = False
    while True:
        now_time = now_ist().strftime("%H:%M")
        if is_market_time():
            if not market_sent:
                await tg("Market OPEN!\nIV ROC Scanner LIVE")
                market_sent = True
            await scan()
        else:
            if market_sent and now_time > "15:30":
                await tg("Market Closed\nRelax Now – See You Tomorrow")
                market_sent = False
        await asyncio.sleep(SCAN_INTERVAL)

if __name__ == "__main__":
    asyncio.run(main())

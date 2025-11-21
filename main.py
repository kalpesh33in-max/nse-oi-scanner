
import requests, time, threading
from datetime import datetime
import pytz

# ---------------- TELEGRAM SETTINGS ----------------
TOKEN = "8587757379:AAEa1zQmNAN8xcYLaQlXzsMzqph3bNqUpgg"
CHAT_IDS = ["530388484", "5332055063"]

# ---------------- SYMBOLS & LOT SIZES -------------
ASSETS = {
    "NIFTY": 75,
    "BANKNIFTY": 35,
    "FINNIFTY": 65,
    "MIDCPNIFTY": 140,
    "HDFCBANK": 550,
    "RELIANCE": 500,
    "ICICIBANK": 700,
    "INFY": 400,
    "TCS": 175,
    "BHARTIARTL": 475,
    "ITC": 1600,
    "KOTAKBANK": 400,
    "HINDUNILVR": 300,
    "LT": 175
}

# ---------------- THREE MODES ---------------------
MODES = {
    "AGGRESSIVE": {"OI": 6, "VOL": 50, "VOLM": 1.0, "LOTS": 1},
    "MODERATE":   {"OI": 10, "VOL": 100, "VOLM": 1.2, "LOTS": 2},
    "SAFE":       {"OI": 20, "VOL": 150, "VOLM": 1.5, "LOTS": 5},
}

ATM_RANGE = 200          # strikes around spot
ALERT_COOLDOWN = 60      # seconds between alerts per key per mode

# --------------- NSE SESSION ----------------------
session = requests.Session()
session.headers.update({
    "User-Agent": "Mozilla/5.0",
    "Referer": "https://www.nseindia.com"
})

# --------------- HELPERS --------------------------
def now_ist():
    tz = pytz.timezone("Asia/Kolkata")
    return datetime.now(tz)

def is_market_time():
    t = now_ist().time()
    return (t >= t.replace(hour=9, minute=15, second=0, microsecond=0) and
            t <= t.replace(hour=15, minute=30, second=0, microsecond=0))

def send(msg: str):
    for chat in CHAT_IDS:
        try:
            requests.post(
                f"https://api.telegram.org/bot{TOKEN}/sendMessage",
                json={"chat_id": chat, "text": msg, "parse_mode": "Markdown"},
                timeout=10
            )
        except Exception:
            pass

def get_option_chain(symbol: str, is_index: bool):
    url = f"https://www.nseindia.com/api/option-chain-{'indices' if is_index else 'equities'}?symbol={symbol}"
    try:
        r = session.get(url, timeout=15).json()
        spot = r.get("underlyingValue") or r.get("info", {}).get("lastPrice", 0)
        data = r["records"]["data"] if is_index else r["filtered"]["data"]
        return data, round(spot)
    except Exception:
        return [], 0

# --------------- SCANNER PER MODE -----------------
def run_mode(mode_name: str, cfg: dict):
    prev_oi = {}
    prev_vol = {}
    last_alert = {}
    last_sign = {}  # +1 buyer side, -1 writer side

    send(f"*{mode_name} MODE STARTED*  "
         f"OI ≥ {cfg['OI']}%, Min lots {cfg['LOTS']}")

    while True:
        try:
            if not is_market_time():
                # outside market hours: sleep longer
                time.sleep(60)
                continue

            for symbol, lot_size in ASSETS.items():
                is_index = symbol in ["NIFTY", "BANKNIFTY", "FINNIFTY", "MIDCPNIFTY"]
                data, spot = get_option_chain(symbol, is_index)
                if not data or spot == 0:
                    continue

                for row in data:
                    strike = row["strikePrice"]
                    expiry = row.get("expiryDate", "NA")

                    if abs(strike - spot) > ATM_RANGE:
                        continue

                    for opt_type in ["CE", "PE"]:
                        o = row.get(opt_type)
                        if not o:
                            continue

                        key = f"{mode_name}_{symbol}_{strike}_{opt_type}_{expiry}"

                        oi = o.get("openInterest", 0)
                        vol = o.get("totalTradedVolume", 0)
                        ltp = o.get("lastPrice", 0.0)
                        chg = o.get("changeinOpenInterest", 0)

                        if key not in prev_oi:
                            prev_oi[key] = oi
                            prev_vol[key] = vol
                            last_sign[key] = 0
                            continue

                        old_oi = prev_oi[key]
                        old_vol = prev_vol[key]

                        spike = ((oi - old_oi) / old_oi * 100) if old_oi > 0 else 0
                        lots = abs(chg) // lot_size

                        vol_threshold = max(cfg["VOL"], old_vol * cfg["VOLM"])
                        vol_ok = vol >= vol_threshold
                        base_ok = (spike >= cfg["OI"] and lots >= cfg["LOTS"] and vol_ok)

                        sign = 1 if chg > 0 else -1 if chg < 0 else 0

                        # Position tag
                        if abs(strike - spot) <= 60:
                            pos = "ATM"
                        else:
                            if (opt_type == "CE" and strike < spot) or (opt_type == "PE" and strike > spot):
                                pos = "ITM"
                            else:
                                pos = "OTM"

                        # -------- ENTRY / ADD ALERT --------
                        if (base_ok and sign != 0 and sign == last_sign.get(key, 0)
                                and time.time() - last_alert.get(key, 0) > ALERT_COOLDOWN):

                            action = "BUYER BOUGHT" if chg > 0 else "WRITER SOLD"
                            if opt_type == "CE" and chg > 0:
                                signal = "BUY CALL"
                            elif opt_type == "PE" and chg > 0:
                                signal = "BUY PUT"
                            else:
                                signal = "SHORT (WRITER ACTIVE)"

                            msg = f"""
[{mode_name}] *{symbol} {strike} {opt_type} ({pos})*
Expiry: `{expiry}`

**{action} {lots} LOTS**  
OI Spike: `+{spike:.1f}%`  
Vol: `{vol}`

LTP: `₹{ltp}`
Approx Exposure: `₹{round(lots * lot_size * ltp):,}`

Signal: *{signal}* (Observation only)

Time: `{now_ist().strftime('%H:%M:%S')}` IST
                            """.strip()

                            send(msg)
                            last_alert[key] = time.time()

                        # -------- EXIT / REVERSAL ALERT ----
                        if (base_ok and sign != 0 and last_sign.get(key, 0) != 0
                                and sign != last_sign[key]
                                and time.time() - last_alert.get(key, 0) > ALERT_COOLDOWN):

                            if sign > 0 and last_sign[key] < 0:
                                exit_text = "WRITER EXITED / SHORT COVER"
                                new_side = "BUYERS ACTIVE"
                            elif sign < 0 and last_sign[key] > 0:
                                exit_text = "BUYER EXITED / PROFIT BOOKING"
                                new_side = "WRITERS ACTIVE"
                            else:
                                exit_text = "POSITION SHIFT"
                                new_side = "POSITION CHANGED"

                            msg = f"""
[{mode_name}] *EXIT ALERT — {symbol} {strike} {opt_type} ({pos})*
Expiry: `{expiry}`

**{exit_text}**  
OI Change: `{chg}`  
Spike: `+{spike:.1f}%`  
Lots change: `{lots}`

New side: *{new_side}*

LTP: `₹{ltp}`
Time: `{now_ist().strftime('%H:%M:%S')}` IST
                            """.strip()

                            send(msg)
                            last_alert[key] = time.time()

                        prev_oi[key] = oi
                        prev_vol[key] = vol
                        if sign != 0:
                            last_sign[key] = sign

                # small delay per symbol to be gentle with NSE
                time.sleep(0.3)

        except Exception as e:
            print(f"[{mode_name}] ERROR:", e)
            time.sleep(5)

# --------------- MAIN ----------------------------
def main():
    send("🚀 *KALPE BHAI OI SCANNER LIVE ON RAILWAY* 🚀")
    for mode_name, cfg in MODES.items():
        t = threading.Thread(target=run_mode, args=(mode_name, cfg), daemon=True)
        t.start()

    # heartbeat to keep process alive
    while True:
        print("Heartbeat", now_ist())
        time.sleep(300)

if __name__ == "__main__":
    main()

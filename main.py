import os
import time
import threading
from datetime import datetime, time as dtime
import requests
import pytz

# --------------------------------------------------
# SAFER TELEGRAM SETTINGS (use Railway Variables)
# --------------------------------------------------
# In Railway → Service → Variables, set:
# TELEGRAM_TOKEN     = 8545053757:AAFm0Og3HsLbmznRgaswT32av718DNkSxnw
# TELEGRAM_CHAT_IDS  = 530388484,5332055063
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN", "")
CHAT_IDS_RAW = os.environ.get("TELEGRAM_CHAT_IDS", "")
CHAT_IDS = [c.strip() for c in CHAT_IDS_RAW.split(",") if c.strip()]

# --------------------------------------------------
# SYMBOLS & LOT SIZES
# --------------------------------------------------
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
    "LT": 175,
}

# --------------------------------------------------
# MODES
# --------------------------------------------------
MODES = {
    "AGGRESSIVE": {"OI": 6, "VOL": 50, "VOLM": 1.0, "LOTS": 1},
    "MODERATE":   {"OI": 10, "VOL": 100, "VOLM": 1.2, "LOTS": 2},
    "SAFE":       {"OI": 20, "VOL": 150, "VOLM": 1.5, "LOTS": 5},
}

ATM_RANGE = 200          # strikes around spot
ALERT_COOLDOWN = 60      # seconds between alerts per key per mode

# --------------------------------------------------
# NSE SESSION (ONE SESSION SHARED)
# --------------------------------------------------
session = requests.Session()
session.headers.update({
    "User-Agent": "Mozilla/5.0",
    "Referer": "https://www.nseindia.com",
    "Accept": "application/json,text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
})

# --------------------------------------------------
# TIME HELPERS
# --------------------------------------------------
IST_TZ = pytz.timezone("Asia/Kolkata")


def now_ist() -> datetime:
    return datetime.now(IST_TZ)


def is_trading_day() -> bool:
    """Mon–Fri only."""
    return now_ist().weekday() < 5  # 0 = Monday, 6 = Sunday


def is_market_time() -> bool:
    """Between 9:15 and 15:30 IST on trading days."""
    now = now_ist()
    if now.weekday() >= 5:  # Sat/Sun
        return False
    t = now.time()
    return dtime(9, 15) <= t <= dtime(15, 30)


# --------------------------------------------------
# TELEGRAM SEND (WITH BASIC SAFETY)
# --------------------------------------------------
def send(msg: str) -> None:
    if not TELEGRAM_TOKEN or not CHAT_IDS:
        # no token or chats configured → avoid error flood
        print("TELEGRAM NOT CONFIGURED. Message would be:", msg[:80], "...")
        return

    for chat in CHAT_IDS:
        try:
            resp = requests.post(
                f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
                json={"chat_id": chat, "text": msg, "parse_mode": "Markdown"},
                timeout=10,
            )
            if resp.status_code != 200:
                print("Telegram error:", resp.text[:100])
        except Exception as e:
            print("Telegram send error:", e)


# --------------------------------------------------
# GLOBAL CACHE: OPTION CHAIN (ONE FETCH LOOP)
# --------------------------------------------------
latest_chain_lock = threading.Lock()
latest_chain = {}  # symbol -> (data_list, spot, timestamp)


def fetch_option_chain(symbol: str, is_index: bool):
    url = f"https://www.nseindia.com/api/option-chain-{'indices' if is_index else 'equities'}?symbol={symbol}"
    r = session.get(url, timeout=15)
    r.raise_for_status()
    j = r.json()
    spot = j.get("underlyingValue") or j.get("info", {}).get("lastPrice", 0)
    if is_index:
        data = j["records"]["data"]
    else:
        data = j["filtered"]["data"]
    return data, round(spot or 0)


def data_fetch_loop():
    """
    Single loop that refreshes data for all symbols roughly every ~5 seconds,
    only during market time on Mon–Fri.
    Automatic backoff on errors.
    """
    backoff = 5
    INDEX_SYMBOLS = {"NIFTY", "BANKNIFTY", "FINNIFTY", "MIDCPNIFTY"}

    while True:
        try:
            if not is_trading_day():
                time.sleep(60)
                continue

            if not is_market_time():
                time.sleep(30)
                continue

            start = time.time()

            for symbol in ASSETS:
                is_index = symbol in INDEX_SYMBOLS
                try:
                    data, spot = fetch_option_chain(symbol, is_index)
                    with latest_chain_lock:
                        latest_chain[symbol] = (data, spot, time.time())
                    # tiny delay between calls so NSE is happy
                    time.sleep(0.2)
                except Exception as e:
                    print(f"[FETCH] Error for {symbol}:", e)
                    # light backoff for that symbol
                    time.sleep(backoff)

            # one full round done → reset backoff smaller
            backoff = max(5, backoff // 2)

            # keep overall cycle around 5 seconds if possible
            elapsed = time.time() - start
            sleep_extra = max(0, 5 - elapsed)
            time.sleep(sleep_extra)

        except Exception as e:
            print("[FETCH LOOP] Fatal error:", e)
            backoff = min(backoff * 2, 60)
            time.sleep(backoff)


# --------------------------------------------------
# SCANNER PER MODE  (USES CACHED DATA ONLY)
# --------------------------------------------------
def run_mode(mode_name: str, cfg: dict):
    prev_oi = {}
    prev_vol = {}
    last_alert = {}
    last_sign = {}  # +1 buyer side, -1 writer side

    send(
        f"*{mode_name} MODE STARTED*  "
        f"OI ≥ {cfg['OI']}%, Min lots {cfg['LOTS']}"
    )

    while True:
        try:
            if not is_trading_day():
                time.sleep(60)
                continue

            if not is_market_time():
                # outside market hours → relax
                time.sleep(30)
                continue

            # take a snapshot so we don't hold lock for long
            with latest_chain_lock:
                snapshot = dict(latest_chain)

            now_ts = time.time()

            for symbol, lot_size in ASSETS.items():
                if symbol not in snapshot:
                    continue

                data, spot, ts = snapshot[symbol]
                # skip stale data
                if not data or spot == 0 or now_ts - ts > 20:
                    continue

                for row in data:
                    strike = row.get("strikePrice")
                    expiry = row.get("expiryDate", "NA")

                    if strike is None or abs(strike - spot) > ATM_RANGE:
                        continue

                    for opt_type in ("CE", "PE"):
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

                        # ATM / ITM / OTM tag
                        if abs(strike - spot) <= 60:
                            pos = "ATM"
                        else:
                            if (opt_type == "CE" and strike < spot) or (
                                opt_type == "PE" and strike > spot
                            ):
                                pos = "ITM"
                            else:
                                pos = "OTM"

                        now_time = time.time()
                        last_t = last_alert.get(key, 0)

                        # -------- ENTRY / ADD ALERT --------
                        if (
                            base_ok
                            and sign != 0
                            and sign == last_sign.get(key, 0)
                            and now_time - last_t > ALERT_COOLDOWN
                        ):
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
                            last_alert[key] = now_time

                        # -------- EXIT / REVERSAL ALERT ----
                        if (
                            base_ok
                            and sign != 0
                            and last_sign.get(key, 0) != 0
                            and sign != last_sign[key]
                            and now_time - last_t > ALERT_COOLDOWN
                        ):
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
                            last_alert[key] = now_time

                        prev_oi[key] = oi
                        prev_vol[key] = vol
                        if sign != 0:
                            last_sign[key] = sign

            # small rest: this loop is only CPU, no HTTP
            time.sleep(1)

        except Exception as e:
            print(f"[{mode_name}] ERROR:", e)
            time.sleep(5)


# --------------------------------------------------
# DAILY RESTART LOOP (9:10 AM, ONLY MON–FRI)
# --------------------------------------------------
def daily_restart_loop():
    last_restart_date = None
    while True:
        now = now_ist()
        if now.weekday() < 5:  # only Mon–Fri
            if now.time().hour == 9 and now.time().minute == 10:
                if last_restart_date != now.date():
                    send("♻️ Restarting OI scanner for new trading day (9:10 AM IST).")
                    # exit process → Railway restarts container
                    os._exit(0)
            else:
                # reset flag after 09:11 so next day can restart
                if last_restart_date != now.date() and now.time() > dtime(9, 11):
                    last_restart_date = now.date()
        else:
            last_restart_date = None

        time.sleep(30)


# --------------------------------------------------
# MAIN
# --------------------------------------------------
def main():
    send("🚀 *KALPE BHAI OI SCANNER LIVE ON RAILWAY* 🚀")

    # 1) Start shared data fetch loop (5s scheduler)
    threading.Thread(target=data_fetch_loop, daemon=True).start()

    # 2) Start each mode as separate light thread (no HTTP inside)
    for mode_name, cfg in MODES.items():
        t = threading.Thread(target=run_mode, args=(mode_name, cfg), daemon=True)
        t.start()

    # 3) Daily restart watcher
    threading.Thread(target=daily_restart_loop, daemon=True).start()

    # 4) Heartbeat – very light, just for logs
    while True:
        print("Heartbeat", now_ist())
        time.sleep(60)


if __name__ == "__main__":
    main()

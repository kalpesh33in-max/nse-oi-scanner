import os
import time
import threading
from datetime import datetime, time as dtime
import requests
import pytz

# ================== TELEGRAM SETTINGS (Railway env) ==================
# In Railway → Service → Variables, set:
# TELEGRAM_TOKEN     = 8545053757:AAFm0Og3HsLbmznRgaswT32av718DNkSxnw
# TELEGRAM_CHAT_IDS  = 530388484,5332055063
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN", "")
CHAT_IDS_RAW = os.environ.get("TELEGRAM_CHAT_IDS", "")
CHAT_IDS = [c.strip() for c in CHAT_IDS_RAW.split(",") if c.strip()]

# ================== NIFTY SETTINGS ==================
NIFTY_SYMBOL = "NIFTY"
NIFTY_LOT = 75

# We still keep 3 modes, but only for NIFTY
MODES = {
    "AGGRESSIVE": {"OI": 6, "VOL": 30, "LOTS": 1, "IVROC": 5},
    "MODERATE":   {"OI": 10, "VOL": 60, "LOTS": 2, "IVROC": 8},
    "SAFE":       {"OI": 14, "VOL": 100, "LOTS": 3, "IVROC": 10},
}

ATM_RANGE = 200              # strikes around spot
ALERT_COOLDOWN = 60          # seconds between normal alerts per key per mode

# Super Spike thresholds (Option C)
SUPER_A = {"SPIKE": 30, "LOTS": 5, "IVROC": 15}   # strong move
SUPER_B = {"SPIKE": 50, "LOTS": 10, "IVROC": 25}  # extreme move
SUPER_COOLDOWN = 60                               # seconds per key

# ================== NSE SESSION (shared) ==================
session = requests.Session()

# Use the REAL headers you captured from DevTools (without cookies)
session.headers.update({
    "authority": "www.nseindia.com",
    "accept": "*/*",
    "accept-encoding": "gzip, deflate, br, zstd",
    "accept-language": "en-US,en;q=0.9,en-IN;q=0.8",
    "referer": "https://www.nseindia.com/option-chain",
    "sec-ch-ua": '"Chromium";v="142", "Microsoft Edge";v="142", "Not_A Brand";v="99"',
    "sec-ch-ua-mobile": "?1",
    "sec-ch-ua-platform": '"Android"',
    "sec-fetch-dest": "empty",
    "sec-fetch-mode": "cors",
    "sec-fetch-site": "same-origin",
    "user-agent": (
        "Mozilla/5.0 (Linux; Android 6.0; Nexus 5 Build/MRA58N) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/142.0.0.0 Mobile Safari/537.36 Edg/142.0.0.0"
    ),
})

# ================== TIME HELPERS ==================
IST_TZ = pytz.timezone("Asia/Kolkata")


def now_ist() -> datetime:
    return datetime.now(IST_TZ)


def is_trading_day() -> bool:
    """Mon–Fri only."""
    return now_ist().weekday() < 5  # 0=Mon, 6=Sun


def is_market_time() -> bool:
    """Between 9:15 and 15:30 IST on trading days."""
    now = now_ist()
    if now.weekday() >= 5:  # Sat/Sun
        return False
    t = now.time()
    return dtime(9, 15) <= t <= dtime(15, 30)


# ================== TELEGRAM HELPERS ==================
def send(msg: str) -> None:
    if not TELEGRAM_TOKEN or not CHAT_IDS:
        print("TELEGRAM NOT CONFIGURED. Message would be:", msg[:120].replace("\n", " "), "...")
        return

    for chat in CHAT_IDS:
        try:
            resp = requests.post(
                f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
                json={"chat_id": chat, "text": msg, "parse_mode": "Markdown"},
                timeout=10,
            )
            if resp.status_code != 200:
                print("Telegram error:", resp.text[:200])
        except Exception as e:
            print("Telegram send error:", e)


# ================== GLOBAL OPTION DATA CACHE ==================
latest_lock = threading.Lock()
latest_nifty = None  # (data_list, spot, timestamp)


def fetch_option_chain_nifty():
    """
    Try new v3 API first, then fall back to old indices API.
    Uses the same headers as your browser.
    """
    urls = [
        f"https://www.nseindia.com/api/option-chain-v3?type=Indices&symbol={NIFTY_SYMBOL}",
        f"https://www.nseindia.com/api/option-chain-indices?symbol={NIFTY_SYMBOL}",
    ]
    last_error = None

    for url in urls:
        try:
            r = session.get(url, timeout=15)
            r.raise_for_status()
            j = r.json()

            # v3 and old API both usually contain "records"
            records = j.get("records") or j.get("filtered")
            if not isinstance(records, dict):
                raise ValueError("Unexpected JSON structure")

            data = records.get("data")
            if not data:
                raise ValueError("No 'data' in records")

            spot = (
                records.get("underlyingValue")
                or j.get("underlyingValue")
                or 0
            )

            print(f"[FETCH] OK from {url}")
            return data, round(spot or 0)

        except Exception as e:
            print(f"[FETCH] Error for URL {url}: {e}")
            last_error = e

    # If both URLs fail
    raise last_error or RuntimeError("Could not fetch NIFTY option chain")


def data_fetch_loop():
    """
    Fetch NIFTY option chain roughly every ~5s during market.
    """
    backoff = 5

    while True:
        try:
            if not is_trading_day():
                time.sleep(60)
                continue

            if not is_market_time():
                time.sleep(30)
                continue

            start = time.time()

            try:
                data, spot = fetch_option_chain_nifty()
                with latest_lock:
                    global latest_nifty
                    latest_nifty = (data, spot, time.time())
                # very short sleep so NSE is happy
                time.sleep(0.5)
            except Exception as e:
                print("[FETCH] Error for NIFTY:", e)
                time.sleep(backoff)

            # keep loop around 5 seconds
            elapsed = time.time() - start
            sleep_extra = max(0, 5 - elapsed)
            time.sleep(sleep_extra)

        except Exception as e:
            print("[FETCH LOOP] Fatal error:", e)
            backoff = min(backoff * 2, 60)
            time.sleep(backoff)


# ================== SCANNER PER MODE ==================
def run_mode(mode_name: str, cfg: dict):
    prev_oi = {}
    prev_vol = {}
    prev_iv = {}
    last_alert = {}
    last_sign = {}      # +1 buyers, -1 writers
    last_super_a = {}   # cooldown for super A
    last_super_b = {}   # cooldown for super B

    send(
        f"*{mode_name} MODE STARTED*  "
        f"OI ≥ {cfg['OI']}%, Min {cfg['LOTS']} lots, IV ROC ≥ {cfg['IVROC']}%"
    )

    while True:
        try:
            if not is_trading_day():
                time.sleep(60)
                continue

            if not is_market_time():
                time.sleep(30)
                continue

            with latest_lock:
                snapshot = latest_nifty

            if snapshot is None:
                time.sleep(1)
                continue

            data, spot, ts = snapshot
            now_ts = time.time()

            # data stale?
            if not data or spot == 0 or now_ts - ts > 20:
                time.sleep(1)
                continue

            for row in data:
                strike = row.get("strikePrice")
                expiry = row.get("expiryDate", "NA")
                if strike is None:
                    continue

                if abs(strike - spot) > ATM_RANGE:
                    continue

                for opt_type in ("CE", "PE"):
                    o = row.get(opt_type)
                    if not o:
                        continue

                    key = f"{mode_name}_{strike}_{opt_type}_{expiry}"

                    oi = o.get("openInterest", 0)
                    vol = o.get("totalTradedVolume", 0)
                    ltp = o.get("lastPrice", 0.0)
                    chg_oi = o.get("changeinOpenInterest", 0)
                    iv = o.get("impliedVolatility", 0.0) or 0.0

                    if key not in prev_oi:
                        prev_oi[key] = oi
                        prev_vol[key] = vol
                        prev_iv[key] = iv
                        last_sign[key] = 0
                        continue

                    old_oi = prev_oi[key]
                    old_vol = prev_vol[key]
                    old_iv = prev_iv[key]

                    spike = ((oi - old_oi) / old_oi * 100) if old_oi > 0 else 0.0
                    lots = abs(chg_oi) // NIFTY_LOT

                    vol_threshold = max(cfg["VOL"], old_vol)
                    vol_ok = vol >= vol_threshold

                    iv_roc = ((iv - old_iv) / old_iv * 100) if old_iv > 0 else 0.0

                    base_ok = (
                        spike >= cfg["OI"]
                        and lots >= cfg["LOTS"]
                        and vol_ok
                    )

                    sign = 1 if chg_oi > 0 else -1 if chg_oi < 0 else 0

                    # ATM / ITM / OTM
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

                    # ---------- SUPER SPIKE TYPE B (EXTREME) ----------
                    if (
                        (spike >= SUPER_B["SPIKE"] and lots >= SUPER_B["LOTS"])
                        or iv_roc >= SUPER_B["IVROC"]
                    ):
                        last_sb = last_super_b.get(key, 0)
                        if now_time - last_sb > SUPER_COOLDOWN:
                            side_text = (
                                "BUYERS AGGRESSIVE" if chg_oi > 0 else "WRITERS DOMINATING"
                            )
                            msg = f"""
🚨🚨 *EXTREME SUPER SPIKE (TYPE B)* 🚨🚨
*{NIFTY_SYMBOL} {strike} {opt_type} ({pos})*
Expiry: `{expiry}`

OI Spike: `+{spike:.1f}%`
Lots Added: `{lots}` LOTS
Volume: `{vol}`
IV: `{old_iv:.2f}% → {iv:.2f}%`
IV ROC: `{iv_roc:+.1f}%`

Side: *{side_text}*
Reason: *Extreme OI / IV explosion detected ❗*

Time: `{now_ist().strftime('%H:%M:%S')}` IST
                            """.strip()
                            send(msg)
                            last_super_b[key] = now_time

                    # ---------- SUPER SPIKE TYPE A (STRONG) ----------
                    if (
                        (spike >= SUPER_A["SPIKE"] and lots >= SUPER_A["LOTS"])
                        or iv_roc >= SUPER_A["IVROC"]
                    ):
                        last_sa = last_super_a.get(key, 0)
                        if now_time - last_sa > SUPER_COOLDOWN:
                            side_text = (
                                "BUYERS AGGRESSIVE" if chg_oi > 0 else "WRITERS ACTIVE"
                            )
                            msg = f"""
🔥🔥 *SUPER SPIKE ALERT (TYPE A)* 🔥🔥
*{NIFTY_SYMBOL} {strike} {opt_type} ({pos})*
Expiry: `{expiry}`

OI Spike: `+{spike:.1f}%`
Lots Added: `{lots}` LOTS
Volume: `{vol}`
IV: `{old_iv:.2f}% → {iv:.2f}%`
IV ROC: `{iv_roc:+.1f}%`

Side: *{side_text}*
Reason: *Massive OI spike + IV expansion*

Time: `{now_ist().strftime('%H:%M:%S')}` IST
                            """.strip()
                            send(msg)
                            last_super_a[key] = now_time

                    # ---------- TREND CONTINUATION SIGNAL ----------
                    if (
                        base_ok
                        and sign != 0
                        and iv_roc >= cfg["IVROC"]
                        and now_time - last_t > ALERT_COOLDOWN
                    ):
                        if chg_oi > 0:
                            # Writers adding
                            if opt_type == "PE":
                                direction = "TREND UP — BUY CALL SETUP"
                                trade_signal = "BUY CALL (CE)"
                            else:  # CE
                                direction = "TREND DOWN — BUY PUT SETUP"
                                trade_signal = "BUY PUT (PE)"
                        else:
                            # Writers exiting but IV still rising
                            if opt_type == "CE":
                                direction = "REVERSAL UP — BUY CALL SETUP"
                                trade_signal = "BUY CALL (CE)"
                            else:
                                direction = "REVERSAL DOWN — BUY PUT SETUP"
                                trade_signal = "BUY PUT (PE)"

                        msg = f"""
[{mode_name}] *{NIFTY_SYMBOL} {strike} {opt_type} ({pos})*
Expiry: `{expiry}`

**{direction}**
OI Spike: `+{spike:.1f}%`
Lots Added: `{lots}` LOTS
Volume: `{vol}`
IV: `{old_iv:.2f}% → {iv:.2f}%`
IV ROC: `{iv_roc:+.1f}%`

Signal: *{trade_signal}*  (Observation only)

Time: `{now_ist().strftime('%H:%M:%S')}` IST
                        """.strip()

                        send(msg)
                        last_alert[key] = now_time

                    # ---------- EXIT / REVERSAL ALERT (IV ROC flip) ----------
                    if (
                        base_ok
                        and sign != 0
                        and last_sign.get(key, 0) != 0
                        and sign != last_sign[key]
                        and iv_roc <= -cfg["IVROC"]
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
[{mode_name}] *EXIT / REVERSAL — {NIFTY_SYMBOL} {strike} {opt_type} ({pos})*
Expiry: `{expiry}`

**{exit_text}**
OI Change: `{chg_oi}`
Spike: `{spike:+.1f}%`
Lots change: `{lots}`

IV ROC flipped to `{iv_roc:+.1f}%`
New side: *{new_side}*

LTP: `₹{ltp}`
Time: `{now_ist().strftime('%H:%M:%S')}` IST
                        """.strip()

                        send(msg)
                        last_alert[key] = now_time

                    # update history
                    prev_oi[key] = oi
                    prev_vol[key] = vol
                    prev_iv[key] = iv
                    if sign != 0:
                        last_sign[key] = sign

            time.sleep(1)

        except Exception as e:
            print(f"[{mode_name}] ERROR:", e)
            time.sleep(5)


# ================== DAILY RESTART (9:10 AM) ==================
def daily_restart_loop():
    last_restart_date = None
    while True:
        now = now_ist()
        if now.weekday() < 5:  # Mon–Fri
            if now.time().hour == 9 and now.time().minute == 10:
                if last_restart_date != now.date():
                    send("♻️ Restarting OI scanner for new trading day (9:10 AM IST).")
                    os._exit(0)
            else:
                if last_restart_date != now.date() and now.time() > dtime(9, 11):
                    last_restart_date = now.date()
        else:
            last_restart_date = None
        time.sleep(30)


# ================== MARKET OPEN / CLOSE ALERTS ==================
def market_alerts_loop():
    sent_open_for = None
    sent_close_for = None

    while True:
        now = now_ist()
        t = now.time()
        d = now.date()
        weekday = now.weekday()

        if weekday < 5:
            if dtime(9, 15) <= t <= dtime(9, 16) and sent_open_for != d:
                send("🌞 *Good Morning Kalpe Bhai!* \n\nMarket opened — OI Scanner is now *LIVE* 🔥")
                sent_open_for = d
                sent_close_for = None

            if dtime(15, 30) <= t <= dtime(15, 31) and sent_close_for != d:
                send("🔻 *Market Closed* 🔻\n\nKalpe Bhai, Scanner stopped scanning.\nSee you tomorrow! 🙏")
                sent_close_for = d

        time.sleep(20)


# ================== MAIN ==================
def main():
    send("🚀 *KALPE BHAI NIFTY OI + IV + IV ROC SCANNER LIVE ON RAILWAY* 🚀")

    threading.Thread(target=data_fetch_loop, daemon=True).start()

    for mode_name, cfg in MODES.items():
        threading.Thread(target=run_mode, args=(mode_name, cfg), daemon=True).start()

    threading.Thread(target=daily_restart_loop, daemon=True).start()
    threading.Thread(target=market_alerts_loop, daemon=True).start()

    while True:
        print("Heartbeat", now_ist())
        time.sleep(60)


if __name__ == "__main__":
    main()

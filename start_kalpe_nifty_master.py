import os
import time
import threading
from datetime import datetime, date as ddate, time as dtime, timedelta
import calendar
import requests
import pytz

# ================== TELEGRAM SETTINGS ==================
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN", "")
CHAT_IDS_RAW = os.environ.get("TELEGRAM_CHAT_IDS", "")
CHAT_IDS = [c.strip() for c in CHAT_IDS_RAW.split(",") if c.strip()]

# ================== NIFTY SETTINGS ==================
NIFTY_SYMBOL = "NIFTY"
NIFTY_LOT = 75

ATM_RANGE = 200              # strikes around spot to scan
HEDGE_STRIKE_RANGE = 200     # CE–PE hedge detection range around main strike

# SUPER SPIKE LEVELS
SUPER_A = {"SPIKE": 30, "LOTS": 5, "IVROC": 15}
SUPER_B = {"SPIKE": 50, "LOTS": 10, "IVROC": 25}
SUPER_COOLDOWN = 60

# REVERSAL LIMITS
REVERSAL_MIN_IVROC = 10
REVERSAL_MIN_LOTS = 3
REVERSAL_COOLDOWN = 60

# ================== NSE SESSION ==================
session = requests.Session()

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


def is_trading_day():
    return now_ist().weekday() < 5


def is_market_time():
    now = now_ist()
    if now.weekday() >= 5:
        return False
    t = now.time()
    return dtime(9, 15) <= t <= dtime(15, 30)


# ================== TELEGRAM ==================
def send(msg: str):
    if not TELEGRAM_TOKEN or not CHAT_IDS:
        print("TELEGRAM NOT CONFIGURED:", msg[:150].replace("\n", " "))
        return

    for chat in CHAT_IDS:
        try:
            r = requests.post(
                f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
                json={"chat_id": chat, "text": msg, "parse_mode": "Markdown"},
                timeout=10,
            )
            if r.status_code != 200:
                print("Telegram error:", r.text[:200])
        except Exception as e:
            print("TG ERROR:", e)


# ================== GLOBAL DATA ==================
latest_lock = threading.Lock()
latest_nifty = None  # (data, spot, expiry_list, ts)
latest_fut = None    # (fut_oi, fut_chg_oi, fut_expiry, ts)

blocked = False
last_block_time = 0.0


# ================== EXPIRY HELPERS ==================
def parse_expiry(s: str):
    try:
        return datetime.strptime(s, "%d-%b-%Y").date()
    except Exception:
        return None


def classify_expiry(exp_raw: str, all_expiries):
    """
    Convert raw expiry string to:
    - Pretty display like '09 DEC 2025'
    - Type: WEEKLY / NEXT WEEK / MONTHLY / FAR EXPIRY
    """
    d = parse_expiry(exp_raw)
    if not d:
        return exp_raw, "EXPIRY"

    disp = d.strftime("%d %b %Y").upper()

    try:
        sorted_dates = sorted(parse_expiry(e) for e in all_expiries if parse_expiry(e))
        idx = sorted_dates.index(d)
    except Exception:
        idx = -1

    last_day = ddate(d.year, d.month, calendar.monthrange(d.year, d.month)[1])
    offset = (last_day.weekday() - 3) % 7  # Thursday = 3
    last_thu = last_day - timedelta(days=offset)

    if d == last_thu:
        etype = "MONTHLY"
    elif idx == 0:
        etype = "WEEKLY"
    elif idx == 1:
        etype = "NEXT WEEK"
    else:
        etype = "FAR EXPIRY"

    return disp, etype


# ================== FETCH OPTIONS ==================
def fetch_option_chain():
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

            records = j.get("records") or j.get("filtered")
            if not isinstance(records, dict):
                raise ValueError("Bad JSON: no records")

            data = records.get("data")
            spot = records.get("underlyingValue") or 0
            expiry_list = records.get("expiryDates")
            if not data or not expiry_list:
                raise ValueError("Bad JSON: no data/expiryDates")

            print("[FETCH] OC OK", url)
            return data, round(spot), expiry_list

        except Exception as e:
            print("[FETCH] OC ERROR", url, ":", e)
            last_error = e

    raise last_error or RuntimeError("Could not fetch option chain")


# ================== FETCH FUTURES ==================
def fetch_futures():
    url = f"https://www.nseindia.com/api/quote-derivative?symbol={NIFTY_SYMBOL}"
    r = session.get(url, timeout=15)
    r.raise_for_status()
    j = r.json()

    stocks = j.get("stocks") or []
    futures = []

    for item in stocks:
        meta = item.get("metadata", {})
        if "futures" in str(meta.get("instrumentType", "")).lower():
            exp = meta.get("expiryDate")
            oi = meta.get("openInterest", 0)
            chg = meta.get("changeinOpenInterest", 0)
            if exp:
                futures.append((exp, oi, chg))

    if not futures:
        return None

    def _p(x):
        try:
            return datetime.strptime(x, "%d-%b-%Y")
        except Exception:
            return datetime.max

    futures.sort(key=lambda x: _p(x[0]))
    exp, oi, chg = futures[0]
    print("[FETCH] FUT OK", exp, oi, chg)
    return exp, oi, chg


# ================== FETCH LOOP ==================
def data_fetch_loop():
    global latest_nifty, latest_fut, blocked, last_block_time

    while True:
        try:
            if not is_trading_day():
                time.sleep(60)
                continue
            if not is_market_time():
                time.sleep(30)
                continue

            if blocked:
                if time.time() - last_block_time < 300:
                    time.sleep(10)
                    continue

            try:
                data, spot, exp_list = fetch_option_chain()
                fut = None
                try:
                    fut = fetch_futures()
                except Exception as fe:
                    print("[FUT ERROR]", fe)
            except Exception as e:
                err = str(e).lower()
                print("[FETCH LOOP ERROR]", e)
                if any(x in err for x in ["403", "forbidden", "blocked", "429", "captcha"]):
                    if not blocked:
                        blocked = True
                        last_block_time = time.time()
                        send("🔴 *NSE BLOCKED / ERROR!*\n\nScanner sleeping 5 minutes then retry…")
                else:
                    time.sleep(10)
                continue

            with latest_lock:
                latest_nifty = (data, spot, exp_list, time.time())
                if fut:
                    latest_fut = (fut[1], fut[2], fut[0], time.time())

            if blocked:
                send("🟢 *RECOVERED!* NSE unlocked, scanner live again 🔥")
                blocked = False
                last_block_time = 0.0

            time.sleep(30)

        except Exception as e:
            print("[DATA LOOP FATAL]", e)
            time.sleep(30)


# ================== MASTER SCANNER ==================
def run_master():
    """
    One clean scanner:
    - SUPER SPIKE (A)
    - EXTREME SUPER SPIKE (B)
    - EXTREME REVERSAL
    With CE–PE hedge detection (±200) and Futures OI.
    """
    prev_oi = {}
    prev_iv = {}
    last_sign = {}
    last_A = {}
    last_B = {}
    last_R = {}

    send(
        "🚀 *KALPE BHAI NIFTY MASTER SCANNER STARTED*\n\n"
        "Alerts:\n"
        "1️⃣ *SUPER SPIKE (TYPE A)* — Big OI + IV ROC\n"
        "2️⃣ *EXTREME SUPER SPIKE (TYPE B)* — Very large OI / IV explosion\n"
        "3️⃣ *EXTREME REVERSAL / EXIT* — Strong trend shift\n\n"
        "Expiry auto: WEEKLY / NEXT WEEK / MONTHLY / FAR.\n"
        "Hedge Analysis: CE–PE ±200 + Futures OI."
    )

    # ---------- inner helper: CE–PE hedge analysis ----------
    def build_hedge_block(data, exp_raw, main_strike, fut_oi, fut_chg, fut_exp):
        """
        Scan all strikes of SAME expiry within ±HEDGE_STRIKE_RANGE
        and build detailed hedge analysis text block.
        """
        best_ce_exit = None   # (abs(chg), strike, chg)
        best_ce_add = None
        best_pe_exit = None
        best_pe_add = None

        for row in data:
            if row.get("expiryDate") != exp_raw:
                continue
            s = row.get("strikePrice")
            if s is None:
                continue
            if abs(s - main_strike) > HEDGE_STRIKE_RANGE:
                continue

            for opt_type in ("CE", "PE"):
                o = row.get(opt_type)
                if not o:
                    continue
                chg_oi = o.get("changeinOpenInterest", 0)
                if chg_oi == 0:
                    continue

                # classify into 4 buckets
                if opt_type == "CE":
                    if chg_oi < 0:  # writers exit (bullish)
                        if (best_ce_exit is None) or (abs(chg_oi) > best_ce_exit[0]):
                            best_ce_exit = (abs(chg_oi), s, chg_oi)
                    else:          # writers add (bearish)
                        if (best_ce_add is None) or (chg_oi > best_ce_add[0]):
                            best_ce_add = (chg_oi, s, chg_oi)
                else:  # PE
                    if chg_oi < 0:  # writers exit (bearish)
                        if (best_pe_exit is None) or (abs(chg_oi) > best_pe_exit[0]):
                            best_pe_exit = (abs(chg_oi), s, chg_oi)
                    else:          # writers add (bullish)
                        if (best_pe_add is None) or (chg_oi > best_pe_add[0]):
                            best_pe_add = (chg_oi, s, chg_oi)

        lines = []
        lines.append("\n\n📌 *Hedge Analysis (Detailed)*")

        # CE writer exit (bullish)
        if best_ce_exit:
            _, s, chg = best_ce_exit
            lots = abs(chg) // NIFTY_LOT
            lines.append(
                f"\n🟢 *CE Writer Exit (Bullish)*\n"
                f"• Strike: `{s} CE`\n"
                f"• OI Δ: `{chg}`\n"
                f"• Lots Removed: `{lots}` LOTS"
            )
        else:
            lines.append("\n🟢 *CE Writer Exit (Bullish)*\n• No strong exit in ±200 zone")

        # CE writer add (bearish)
        if best_ce_add:
            _, s, chg = best_ce_add
            lots = abs(chg) // NIFTY_LOT
            lines.append(
                f"\n🔻 *CE Writer Add (Bearish)*\n"
                f"• Strike: `{s} CE`\n"
                f"• OI Δ: `+{chg}`\n"
                f"• Lots Added: `{lots}` LOTS"
            )
        else:
            lines.append("\n🔻 *CE Writer Add (Bearish)*\n• No strong build-up in ±200 zone")

        # PE writer exit (bearish)
        if best_pe_exit:
            _, s, chg = best_pe_exit
            lots = abs(chg) // NIFTY_LOT
            lines.append(
                f"\n🔻 *PE Writer Exit (Bearish Downside)*\n"
                f"• Strike: `{s} PE`\n"
                f"• OI Δ: `{chg}`\n"
                f"• Lots Removed: `{lots}` LOTS"
            )
        else:
            lines.append("\n🔻 *PE Writer Exit (Bearish Downside)*\n• No strong exit in ±200 zone")

        # PE writer add (bullish)
        if best_pe_add:
            _, s, chg = best_pe_add
            lots = abs(chg) // NIFTY_LOT
            lines.append(
                f"\n🟢 *PE Writer Add (Bullish Support)*\n"
                f"• Strike: `{s} PE`\n"
                f"• OI Δ: `+{chg}`\n"
                f"• Lots Added: `{lots}` LOTS"
            )
        else:
            lines.append("\n🟢 *PE Writer Add (Bullish Support)*\n• No strong build-up in ±200 zone")

        # Futures block
        if fut_exp:
            fut_lots = abs(fut_chg) // NIFTY_LOT if fut_chg else 0
            if fut_chg > 0:
                fut_side = "FUT LONGS ADDED (Bullish)"
            elif fut_chg < 0:
                fut_side = "FUT SHORTS ADDED (Bearish)"
            else:
                fut_side = "FUT OI FLAT"

            lines.append(
                f"\n\n📘 *Futures Position (NIFTY)*\n"
                f"• Expiry: `{fut_exp}`\n"
                f"• OI Δ: `{fut_chg}`\n"
                f"• Lots Change: `{fut_lots}` LOTS\n"
                f"• View: *{fut_side}*"
            )
        else:
            lines.append("\n\n📘 *Futures Position (NIFTY)*\n• Not available / stale")

        # Interpretation
        lines.append("\n\n📌 *Interpretation*")

        bullish_score = 0
        bearish_score = 0

        if best_ce_exit:
            bullish_score += 1
        if best_pe_add:
            bullish_score += 1
        if best_ce_add:
            bearish_score += 1
        if best_pe_exit:
            bearish_score += 1
        if fut_chg > 0:
            bullish_score += 1
        elif fut_chg < 0:
            bearish_score += 1

        if bullish_score >= bearish_score + 1 and bullish_score >= 2:
            lines.append("\n**Hedge Bias: Bullish — Upside trend supported by hedge flows.**")
        elif bearish_score >= bullish_score + 1 and bearish_score >= 2:
            lines.append("\n**Hedge Bias: Bearish — Downside trend supported by hedge flows.**")
        else:
            lines.append("\n**Hedge Bias: Mixed / Neutral — No clear strong hedge direction.**")

        return "".join(lines)

    # ---------- main loop ----------
    while True:
        try:
            if not is_trading_day():
                time.sleep(60)
                continue
            if not is_market_time():
                time.sleep(30)
                continue

            with latest_lock:
                snap = latest_nifty
                fut = latest_fut

            if not snap:
                time.sleep(1)
                continue

            data, spot, exp_list, ts = snap
            if not data or spot == 0 or (time.time() - ts) > 20:
                time.sleep(1)
                continue

            fut_oi = fut_chg = 0
            fut_exp = ""
            if fut:
                f_oi, f_chg, f_exp, f_ts = fut
                if time.time() - f_ts < 300:
                    fut_oi = f_oi
                    fut_chg = f_chg
                    fut_exp = f_exp

            for row in data:
                strike = row.get("strikePrice")
                exp_raw = row.get("expiryDate", "NA")
                if strike is None:
                    continue
                if abs(strike - spot) > ATM_RANGE:
                    continue

                exp_disp, exp_type = classify_expiry(exp_raw, exp_list)

                for opt_type in ("CE", "PE"):
                    o = row.get(opt_type)
                    if not o:
                        continue

                    key = f"{strike}_{opt_type}_{exp_raw}"

                    oi = o.get("openInterest", 0)
                    chg_oi = o.get("changeinOpenInterest", 0)
                    iv = o.get("impliedVolatility", 0.0) or 0.0
                    ltp = o.get("lastPrice", 0.0)

                    if key not in prev_oi:
                        prev_oi[key] = oi
                        prev_iv[key] = iv
                        last_sign[key] = 0
                        continue

                    old_oi = prev_oi[key]
                    old_iv = prev_iv[key]

                    spike = ((oi - old_oi) / old_oi * 100) if old_oi > 0 else 0.0
                    iv_roc = ((iv - old_iv) / old_iv * 100) if old_iv > 0 else 0.0
                    lots = abs(chg_oi) // NIFTY_LOT

                    sign = 1 if chg_oi > 0 else -1 if chg_oi < 0 else 0

                    if abs(strike - spot) <= 60:
                        pos = "ATM"
                    elif (opt_type == "CE" and strike < spot) or (opt_type == "PE" and strike > spot):
                        pos = "ITM"
                    else:
                        pos = "OTM"

                    now = time.time()

                    # ---------- EXTREME SUPER SPIKE (TYPE B) ----------
                    if (
                        (spike >= SUPER_B["SPIKE"] and lots >= SUPER_B["LOTS"])
                        or iv_roc >= SUPER_B["IVROC"]
                    ):
                        if now - last_B.get(key, 0) > SUPER_COOLDOWN:
                            side_text = (
                                "BUYERS AGGRESSIVE" if chg_oi > 0 else "WRITERS DOMINATING"
                            )
                            hedge_block = build_hedge_block(
                                data, exp_raw, strike, fut_oi, fut_chg, fut_exp
                            )
                            msg = f"""
👑 *EXTREME SUPER SPIKE (TYPE B)* 👑
*{NIFTY_SYMBOL} {strike} {opt_type} ({pos})*
Expiry: `{exp_disp}` ({exp_type})

OI Spike: `+{spike:.1f}%`
Lots Added: `{lots}` LOTS
IV ROC: `{iv_roc:+.1f}%`

Side: *{side_text}*{hedge_block}

Time: `{now_ist().strftime('%H:%M:%S')}` IST
                            """.strip()
                            send(msg)
                            last_B[key] = now

                    # ---------- SUPER SPIKE (TYPE A) ----------
                    if (
                        (spike >= SUPER_A["SPIKE"] and lots >= SUPER_A["LOTS"])
                        or iv_roc >= SUPER_A["IVROC"]
                    ):
                        if now - last_A.get(key, 0) > SUPER_COOLDOWN:
                            side_text = (
                                "BUYERS AGGRESSIVE" if chg_oi > 0 else "WRITERS ACTIVE"
                            )
                            hedge_block = build_hedge_block(
                                data, exp_raw, strike, fut_oi, fut_chg, fut_exp
                            )
                            msg = f"""
🔥 *SUPER SPIKE (TYPE A)* 🔥
*{NIFTY_SYMBOL} {strike} {opt_type} ({pos})*
Expiry: `{exp_disp}` ({exp_type})

OI Spike: `+{spike:.1f}%`
Lots Added: `{lots}` LOTS
IV ROC: `{iv_roc:+.1f}%`

Side: *{side_text}*{hedge_block}

Time: `{now_ist().strftime('%H:%M:%S')}` IST
                            """.strip()
                            send(msg)
                            last_A[key] = now

                    # ---------- EXTREME REVERSAL ----------
                    if (
                        sign != 0
                        and last_sign.get(key, 0) != 0
                        and sign != last_sign[key]
                        and abs(iv_roc) >= REVERSAL_MIN_IVROC
                        and lots >= REVERSAL_MIN_LOTS
                    ):
                        if now - last_R.get(key, 0) > REVERSAL_COOLDOWN:
                            if last_sign[key] > 0 and sign < 0:
                                old_side = "BUYERS DOMINATING"
                                new_side = "WRITERS ACTIVE"
                                reason = "BUYER EXIT / PROFIT BOOKING"
                            else:
                                old_side = "WRITERS DOMINATING"
                                new_side = "BUYERS ACTIVE"
                                reason = "WRITER EXIT / SHORT COVER"

                            hedge_block = build_hedge_block(
                                data, exp_raw, strike, fut_oi, fut_chg, fut_exp
                            )
                            msg = f"""
🔄 *EXTREME REVERSAL ALERT*
*{NIFTY_SYMBOL} {strike} {opt_type} ({pos})*
Expiry: `{exp_disp}` ({exp_type})

Old Side: *{old_side}*
New Side: *{new_side}*
Reason: *{reason}*

OI Δ: `{chg_oi}`
Lots: `{lots}`
IV ROC: `{iv_roc:+.1f}%`
LTP: `₹{ltp}`{hedge_block}

Time: `{now_ist().strftime('%H:%M:%S')}` IST
                            """.strip()
                            send(msg)
                            last_R[key] = now

                    # update history
                    prev_oi[key] = oi
                    prev_iv[key] = iv
                    if sign != 0:
                        last_sign[key] = sign

            time.sleep(1)

        except Exception as e:
            print("[MASTER ERROR]", e)
            time.sleep(5)


# ================== MARKET ALERTS ==================
def market_alerts_loop():
    sent_open = None
    sent_close = None

    while True:
        now = now_ist()
        d = now.date()
        t = now.time()

        if now.weekday() < 5:
            if dtime(9, 15) <= t <= dtime(9, 16) and sent_open != d:
                send("🌞 *Good Morning Kalpe Bhai!* Market LIVE, Scanner ON 🔥")
                sent_open = d

            if dtime(15, 30) <= t <= dtime(15, 31) and sent_close != d:
                send("🔻 *Market Closed* — Scanner stopped. See you tomorrow 🙏")
                sent_close = d

        time.sleep(20)


# ================== START ==================
def start_kalpe_nifty_master():
    send("🚀 *KALPE BHAI MASTER SCANNER LIVE (24×7)* 🚀")

    threading.Thread(target=data_fetch_loop, daemon=True).start()
    threading.Thread(target=run_master, daemon=True).start()
    threading.Thread(target=market_alerts_loop, daemon=True).start()

    while True:
        print("Heartbeat", now_ist())
        time.sleep(60)


if __name__ == "__main__":
    start_kalpe_nifty_master()

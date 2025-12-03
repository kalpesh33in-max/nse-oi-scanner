# banknifty.py - Kalpe Bhai 2025 BankNifty Master Scanner
# Monthly Expiry Only • Super Spike • Extreme Spike • Reversal
# Hedge (±200) • Futures OI • Only CE/PE Price

import os
import time
import requests
import pytz
from datetime import datetime, time as dtime

# ========================= TELEGRAM ==========================
TOKEN = os.environ.get("TELEGRAM_TOKEN", "")
CHAT_RAW = (
    os.environ.get("TELEGRAM_CHAT_IDS")
    or os.environ.get("TELEGRAM_CHAT_ID")
    or ""
)
CHAT_IDS = [c.strip() for c in CHAT_RAW.split(",") if c.strip()]


def send(msg: str):
    if not TOKEN or not CHAT_IDS:
        print("TG OFF:", msg[:150])
        return
    for cid in CHAT_IDS:
        try:
            requests.post(
                f"https://api.telegram.org/bot{TOKEN}/sendMessage",
                json={"chat_id": cid, "text": msg, "parse_mode": "Markdown"},
                timeout=10,
            )
        except:
            pass


# ========================= CONSTANTS =========================
SYMBOL = "BANKNIFTY"
LOT = 35

ATM_RANGE = 3000
HEDGE_RANGE = 200

SUPER_A = {"SPIKE": 20, "LOTS": 100}
SUPER_B = {"SPIKE": 35, "LOTS": 200}
COOLDOWN = 60

REVERSAL_MIN_IVROC = 10
REVERSAL_MIN_LOTS = 80

IST = pytz.timezone("Asia/Kolkata")


def now_ist():
    return datetime.now(IST)


def is_market_time():
    n = now_ist()
    if n.weekday() >= 5:
        return False
    t = n.time()
    return dtime(9, 15) <= t <= dtime(15, 30)


# ========================= NSE SESSION =======================
session = requests.Session()
session.headers.update({
    "User-Agent": "Mozilla/5.0",
    "referer": "https://www.nseindia.com/option-chain",
})


# ========================= EXPIRY HELPERS ====================
def parse_expiry(s):
    try:
        return datetime.strptime(s, "%d-%b-%Y").date()
    except:
        return None


def classify_expiry(exp, all_list):
    d = parse_expiry(exp)
    if not d:
        return exp, "MONTHLY"

    disp = d.strftime("%d %b %Y").upper()
    parsed = [parse_expiry(x) for x in all_list if parse_expiry(x)]
    parsed.sort()

    try:
        idx = parsed.index(d)
    except:
        idx = 0

    if idx == 0:
        etype = "NEAR MONTH"
    elif idx == 1:
        etype = "NEXT MONTH"
    else:
        etype = "FAR MONTH"

    return disp, etype


# ========================= FETCH DATA ========================
def fetch_option_chain():
    urls = [
        f"https://www.nseindia.com/api/option-chain-v3?type=Indices&symbol={SYMBOL}",
        f"https://www.nseindia.com/api/option-chain-indices?symbol={SYMBOL}",
    ]
    last_err = None
    for url in urls:
        try:
            r = session.get(url, timeout=15)
            r.raise_for_status()
            j = r.json()

            records = j.get("records") or j.get("filtered")
            data = records.get("data")
            expiry = records.get("expiryDates")
            spot = records.get("underlyingValue")

            if not data or not expiry or not spot:
                raise ValueError("Invalid JSON")

            return data, round(spot), expiry
        except Exception as e:
            last_err = e
            print("[FETCH ERROR]", e)
    raise last_err


def fetch_futures():
    try:
        url = f"https://www.nseindia.com/api/quote-derivative?symbol={SYMBOL}"
        r = session.get(url, timeout=15)
        r.raise_for_status()
        j = r.json()

        futs = []
        for row in j.get("stocks", []):
            meta = row.get("metadata", {})
            if "futures" in str(meta.get("instrumentType", "")).lower():
                exp = meta.get("expiryDate")
                oi = meta.get("openInterest", 0)
                chg = meta.get("changeinOpenInterest", 0)
                futs.append((exp, oi, chg))

        if not futs:
            return None

        def sort_key(x):
            try:
                return datetime.strptime(x[0], "%d-%b-%Y")
            except:
                return datetime.max

        futs.sort(key=sort_key)
        return futs[0]
    except:
        return None


# ========================= MASTER SCANNER =====================
def run_banknifty_scanner():
    send(
        "🚀 *BANKNIFTY MASTER SCANNER (Final Revised)* 🚀\n"
        "Monthly expiry only\n"
        "Only CE/PE price shown per alert\n"
        "Super Spike, Extreme Spike, Reversal\n"
        "Hedge only in Type-B & Reversal\n"
        "Active 09:15–15:30"
    )

    prev_oi = {}
    prev_iv = {}
    last_dir = {}

    cool_A = {}
    cool_B = {}
    cool_R = {}

    while True:
        try:
            if not is_market_time():
                time.sleep(10)
                continue

            data, spot, expiry_list = fetch_option_chain()
            fut = fetch_futures()
            fut_exp, fut_chg = "", 0
            if fut:
                fut_exp, _, fut_chg = fut

            # --------------------------------------------
            # HEDGE BLOCK (only for Type B & Reversal)
            # --------------------------------------------
            def hedge_block(exp_raw, base_strike):
                best_ce_exit = best_ce_add = None
                best_pe_exit = best_pe_add = None

                # Scan ±200
                for row in data:
                    if row.get("expiryDate") != exp_raw:
                        continue
                    s = row.get("strikePrice")
                    if s is None or abs(s - base_strike) > HEDGE_RANGE:
                        continue

                    for opt in ("CE", "PE"):
                        leg = row.get(opt)
                        if not leg:
                            continue
                        chg = leg.get("changeinOpenInterest", 0)
                        if chg == 0:
                            continue

                        if opt == "CE":
                            if chg < 0:  # exit
                                if (best_ce_exit is None) or (abs(chg) > best_ce_exit[0]):
                                    best_ce_exit = (abs(chg), s, chg)
                            else:
                                if (best_ce_add is None) or (chg > best_ce_add[0]):
                                    best_ce_add = (chg, s, chg)
                        else:
                            if chg < 0:
                                if (best_pe_exit is None) or (abs(chg) > best_pe_exit[0]):
                                    best_pe_exit = (abs(chg), s, chg)
                            else:
                                if (best_pe_add is None) or (chg > best_pe_add[0]):
                                    best_pe_add = (chg, s, chg)

                txt = "\n\n📌 *Hedge Analysis (Detailed)*"

                # CE exit
                if best_ce_exit:
                    _, s, chg = best_ce_exit
                    txt += (
                        f"\n\n🟢 *CE Writer Exit*\n"
                        f"• Strike: `{s} CE`\n"
                        f"• OI Δ: `{chg}`\n"
                        f"• Lots: `{abs(chg)//LOT}`"
                    )
                else:
                    txt += "\n\n🟢 *CE Writer Exit*\n• No strong exit"

                # CE add
                if best_ce_add:
                    _, s, chg = best_ce_add
                    txt += (
                        f"\n\n🔻 *CE Writer Add*\n"
                        f"• Strike: `{s} CE`\n"
                        f"• OI Δ: `+{chg}`\n"
                        f"• Lots: `{chg//LOT}`"
                    )
                else:
                    txt += "\n\n🔻 *CE Writer Add*\n• No strong build-up"

                # PE exit
                if best_pe_exit:
                    _, s, chg = best_pe_exit
                    txt += (
                        f"\n\n🔻 *PE Writer Exit*\n"
                        f"• Strike: `{s} PE`\n"
                        f"• OI Δ: `{chg}`\n"
                        f"• Lots: `{abs(chg)//LOT}`"
                    )
                else:
                    txt += "\n\n🔻 *PE Writer Exit*\n• No strong exit"

                # PE add
                if best_pe_add:
                    _, s, chg = best_pe_add
                    txt += (
                        f"\n\n🟢 *PE Writer Add*\n"
                        f"• Strike: `{s} PE`\n"
                        f"• OI Δ: `+{chg}`\n"
                        f"• Lots: `{chg//LOT}`"
                    )
                else:
                    txt += "\n\n🟢 *PE Writer Add*\n• No strong build-up"

                # futures
                if fut_exp:
                    fut_lots = abs(fut_chg) // LOT
                    view = (
                        "FUT LONGS ADDED" if fut_chg > 0 else
                        "FUT SHORTS ADDED" if fut_chg < 0 else
                        "FUT OI FLAT"
                    )
                    txt += (
                        f"\n\n📘 *Futures Position*\n"
                        f"• Expiry: `{fut_exp}`\n"
                        f"• OI Δ: `{fut_chg}`\n"
                        f"• Lots: `{fut_lots}`\n"
                        f"• View: {view}"
                    )

                return txt

            # --------------------------------------------
            # MAIN LOOP
            # --------------------------------------------
            for row in data:
                strike = row.get("strikePrice")
                exp_raw = row.get("expiryDate")
                if strike is None or abs(strike - spot) > ATM_RANGE:
                    continue

                exp_disp, exp_type = classify_expiry(exp_raw, expiry_list)

                ce = row.get("CE")
                pe = row.get("PE")

                for opt, leg in (("CE", ce), ("PE", pe)):
                    if not leg:
                        continue

                    key = f"{strike}_{opt}_{exp_raw}"

                    oi = leg.get("openInterest", 0)
                    chg_oi = leg.get("changeinOpenInterest", 0)
                    iv = leg.get("impliedVolatility", 0.0) or 0.0
                    ltp = leg.get("lastPrice", 0.0)

                    ce_ltp = ce.get("lastPrice", 0.0) if ce else 0.0
                    pe_ltp = pe.get("lastPrice", 0.0) if pe else 0.0

                    old_oi = prev_oi.get(key, 0)
                    old_iv = prev_iv.get(key, 0.0)

                    spike = ((oi - old_oi) / old_oi * 100) if old_oi > 0 else 0.0
                    lots = abs(oi - old_oi) // LOT

                    ivroc = ((iv - old_iv) / old_iv * 100) if (old_iv > 0 and iv > 0) else 0.0

                    # IV formatting
                    if iv <= 0:
                        iv_display = "N/A"
                        ivroc_display = "N/A"
                    elif old_iv <= 0:
                        iv_display = f"{iv:.1f}%"
                        ivroc_display = "NEW"
                    else:
                        iv_display = f"{iv:.1f}%"
                        ivroc_display = f"{ivroc:+.1f}%"

                    # Position
                    if abs(strike - spot) <= 100:
                        pos = "ATM"
                    elif (opt == "CE" and strike < spot) or (opt == "PE" and strike > spot):
                        pos = "ITM"
                    else:
                        pos = "OTM"

                    sign = 1 if (oi - old_oi) > 0 else -1 if (oi - old_oi) < 0 else 0
                    now_ts = time.time()

                    # Only required price line
                    if opt == "CE":
                        price_line = f"CE Price: `₹{ce_ltp}`\n\n"
                    else:
                        price_line = f"PE Price: `₹{pe_ltp}`\n\n"

                    # ===============================================
                    # EXTREME SUPER SPIKE (TYPE B)
                    # ===============================================
                    if spike >= SUPER_B["SPIKE"] and lots >= SUPER_B["LOTS"]:
                        if now_ts - cool_B.get(key, 0) > COOLDOWN:
                            side = "BUYERS AGGRESSIVE" if chg_oi > 0 else "WRITERS DOMINATING"

                            send(
                                f"👑 *EXTREME SUPER SPIKE (TYPE B)* 👑\n\n"
                                f"Expiry: `{exp_disp}` ({exp_type})\n"
                                f"*BANKNIFTY {strike} {opt} ({pos})*\n\n"
                                f"{price_line}"
                                f"{opt} OI Spike: `+{spike:.1f}%`\n"
                                f"{opt} IV: `{iv_display}` ({opt} ROC: `{ivroc_display}`)\n"
                                f"Lots Change: `{lots}` LOTS\n\n"
                                f"Side: *{side}*"
                                f"{hedge_block(exp_raw, strike)}\n\n"
                                f"Time: `{now_ist().strftime('%H:%M:%S')}` IST"
                            )
                            cool_B[key] = now_ts

                    # ===============================================
                    # SUPER SPIKE (TYPE A)
                    # ===============================================
                    if spike >= SUPER_A["SPIKE"] and lots >= SUPER_A["LOTS"]:
                        if now_ts - cool_A.get(key, 0) > COOLDOWN:
                            side = "BUYERS AGGRESSIVE" if chg_oi > 0 else "WRITERS ACTIVE"

                            send(
                                f"🔥 *SUPER SPIKE (TYPE A)* 🔥\n\n"
                                f"Expiry: `{exp_disp}` ({exp_type})\n"
                                f"*BANKNIFTY {strike} {opt} ({pos})*\n\n"
                                f"{price_line}"
                                f"{opt} OI Spike: `+{spike:.1f}%`\n"
                                f"{opt} IV: `{iv_display}` ({opt} ROC: `{ivroc_display}`)\n"
                                f"Lots Change: `{lots}` LOTS\n\n"
                                f"Side: *{side}*\n\n"
                                f"Time: `{now_ist().strftime('%H:%M:%S')}` IST"
                            )
                            cool_A[key] = now_ts

                    # ===============================================
                    # EXTREME REVERSAL
                    # ===============================================
                    last_s = last_dir.get(key, 0)
                    if (
                        sign != 0
                        and last_s != 0
                        and sign != last_s
                        and lots >= REVERSAL_MIN_LOTS
                        and abs(ivroc) >= REVERSAL_MIN_IVROC
                    ):
                        if now_ts - cool_R.get(key, 0) > COOLDOWN:
                            if last_s > 0:
                                old_side = "BUYERS DOMINATING"
                                new_side = "WRITERS ACTIVE"
                                reason = "BUYER EXIT / PROFIT BOOKING"
                            else:
                                old_side = "WRITERS DOMINATING"
                                new_side = "BUYERS ACTIVE"
                                reason = "WRITER EXIT / SHORT COVER"

                            send(
                                f"🔄 *EXTREME REVERSAL ALERT*\n\n"
                                f"Expiry: `{exp_disp}` ({exp_type})\n"
                                f"*BANKNIFTY {strike} {opt} ({pos})*\n\n"
                                f"{price_line}"
                                f"Old Side: *{old_side}*\n"
                                f"New Side: *{new_side}*\n"
                                f"Reason: *{reason}*\n\n"
                                f"{opt} OI Δ (Lots): `{lots}` LOTS\n"
                                f"{opt} IV: `{iv_display}` ({opt} ROC: `{ivroc_display}`)\n"
                                f"LTP: `₹{ltp}`"
                                f"{hedge_block(exp_raw, strike)}\n\n"
                                f"Time: `{now_ist().strftime('%H:%M:%S')}` IST"
                            )
                            cool_R[key] = now_ts

                    # Update history
                    prev_oi[key] = oi
                    prev_iv[key] = iv
                    if sign != 0:
                        last_dir[key] = sign

            time.sleep(5)

        except Exception as e:
            print("[ERROR]", e)
            time.sleep(10)

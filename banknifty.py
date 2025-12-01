# banknifty.py - KALPE BHAI x TRADE REALM EDITION 2025
# Railway + GitHub Ready | Zero Repeat | 50+ Lots Only | IV ROC + Both Sides

import requests
import time
import datetime
import telegram
import asyncio
import json
from collections import defaultdict

# ====================== CONFIG ======================
TOKEN = "7653014810:AAH5p1z4p4iWv2e2Oyejoxxxxxxxxxxxxxx"  # Apna bot token daal
CHAT_ID = "-1002345678901"  # Apna channel/group ID daal

SYMBOL = "BANKNIFTY"
EXPIRY = "04-Dec-2024"  # Ya auto detect chahiye to bol dena
LOT_SIZE = 15
MIN_LOTS = 50
RANGE_POINTS = 800  # ATM ±800
IV_ROC_THRESHOLD = 20  # ±20% IV change pe bhi alert

bot = telegram.Bot(token=TOKEN)

prev_data = {}
sent_alerts = set()  # Repeat prevent
prev_iv = {}
# =====================================================

def get_option_chain():
    try:
        url = "https://www.nseindia.com/api/option-chain-indices?symbol=BANKNIFTY"
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Accept-Encoding": "gzip, deflate, br",
            "Referer": "https://www.nseindia.com/option-chain",
            "X-Requested-With": "XMLHttpRequest"
        }
        session = requests.Session()
        session.get("https://www.nseindia.com", headers=headers)
        response = session.get(url, headers=headers, timeout=10)
        return response.json()
    except:
        return None

def get_atm_strike(spot):
    return int(round(spot / 100, 0) * 100)

async def send_alert(msg):
    try:
        await bot.send_message(chat_id=CHAT_ID, text=msg, parse_mode='HTML', disable_web_page_preview=True)
    except:
        pass

def main_loop():
    global prev_data, prev_iv

    data = get_option_chain()
    if not data or 'records' not in data:
        return

    spot = data['records']['underlyingValue']
    atm = get_atm_strike(spot)
    timestamp = datetime.datetime.now().strftime("%d-%b-%Y │ Spot: <b>" + str(int(spot)) + "</b>")

    current_iv = {}
    alerts = []

    for option in data['records']['data']:
        if option.get('expiryDate', '').upper() != EXPIRY.upper():
            continue

        strike = option['strikePrice']
        if abs(strike - atm) > RANGE_POINTS:
            continue

        ce = option.get('CE', {})
        pe = option.get('PE', {})

        ce_oi = ce.get('openInterest', 0) * LOT_SIZE
        pe_oi = pe.get('openInterest', 0) * LOT_SIZE
        ce_ltp = ce.get('lastPrice', 0)
        pe_ltp = pe.get('lastPrice', 0)
        ce_iv = ce.get('impliedVolatility', 0)
        pe_iv = pe.get('impliedVolatility', 0)

        key_ce = f"CE_{strike}"
        key_pe = f"PE_{strike}"

        # ITM/ATM/OTM
        if strike < atm - 50:
            tag = "(OTM)"
        elif strike > atm + 50:
            tag = "(ITM)"
        else:
            tag = "(ATM)"

        # CE Alert
        if key_ce in prev_data:
            oi_diff = ce_oi - prev_data[key_ce]['oi']
            lots_added = oi_diff // LOT_SIZE
            if lots_added >= MIN_LOTS:
                iv_roc = ((ce_iv - prev_iv.get(key_ce, ce_iv)) / prev_iv.get(key_ce, 1)) * 100 if prev_iv.get(key_ce) else 0
                if f"CE_{strike}" not in sent_alerts:
                    side = "WRITERS ACTIVE" if "CE" in key_ce else "BUYERS BLAST"
                    color = "Red circle" if "WRITERS" in side else "Green circle"
                    alerts.append(f"""
<b>BANKNIFTY {int(strike)} {tag}</b>
{EXPIRY} │ Spot: <b>{int(spot)}</b>
<b>LTP CE:</b> {ce_ltp:.0f} │ <b>LTP PE:</b> {pe_ltp:.0f}
<b>IV CE:</b> {ce_iv:.1f} (ROC <b>{iv_roc:+.1f}%</b>) │ <b>IV PE:</b> {pe_iv:.1f} (ROC <b>{(pe_iv-prev_iv.get(key_pe,pe_iv))/prev_iv.get(key_pe,1)*100 if prev_iv.get(key_pe) else 0:+.1f}%</b>)
<b>OI +{lots_added} Lots (CE)</b> → <b>{side}</b> {color}
<i>Time:</i> {datetime.datetime.now().strftime('%H:%M:%S')}</b>""")
                    sent_alerts.add(f"CE_{strike}")

        # PE Alert
        if key_pe in prev_data:
            oi_diff = pe_oi - prev_data[key_pe]['oi']
            lots_added = oi_diff // LOT_SIZE
            if lots_added >= MIN_LOTS:
                iv_roc = ((pe_iv - prev_iv.get(key_pe, pe_iv)) / prev_iv.get(key_pe, 1)) * 100 if prev_iv.get(key_pe) else 0
                if f"PE_{strike}" not in sent_alerts == False:
                    side = "BUYERS BLAST" if "PE" in key_pe else "WRITERS ACTIVE"
                    color = "Green circle" if "BUYERS" in side else "Red circle"
                    alerts.append(f"""
<b>BANKNIFTY {int(strike)} {tag}</b>
{EXPIRY} │ Spot: <b>{int(spot)}</b>
<b>LTP CE:</b> {ce_ltp:.0f} │ <b>LTP PE:</b> {pe_ltp:.0f}
<b>IV CE:</b> {ce_iv:.1f} (ROC <b>{(ce_iv-prev_iv.get(key_ce,ce_iv))/prev_iv.get(key_ce,1)*100 if prev_iv.get(key_ce) else 0:+.1f}%</b>) │ <b>IV PE:</b> {pe_iv:.1f} (ROC <b>{iv_roc:+.1f}%</b>)
<b>OI +{lots_added} Lots (PE)</b> → <b>{side}</b> {color}
<i>Time:</i> {datetime.datetime.now().strftime('%H:%M:%S')}</b>""")
                    sent_alerts.add(f"PE_{strike}")

        # Save current
        prev_data[key_ce] = {'oi': ce_oi}
        prev_data[key_pe] = {'oi': pe_oi}
        prev_iv[key_ce] = ce_iv
        prev_iv[key_pe] = pe_iv

    # Send all alerts
    for alert in alerts[:5]:  # Max 5 per cycle
        asyncio.run(send_alert(alert))
        time.sleep(1)

if __name__ == "__main__":
    print(f"BANKNIFTY GOD SCANNER STARTED - {datetime.datetime.now()}")
    while True:
        try:
            main_loop()
            time.sleep(35)  # 35 second cycle
        except Exception as e:
            print(e)
            time.sleep(10)

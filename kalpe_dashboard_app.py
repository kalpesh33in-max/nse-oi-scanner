# kalpe_dashboard_app.py
# Kalpe Bhai Web Dashboard + 5 Scanner Runner (Simple Table Style)

import os
import time
import threading
import traceback
from datetime import datetime, time as dtime

import requests
import pytz
from flask import Flask, jsonify, render_template_string

# ==== IMPORT ALL 5 SCANNERS (already NSE-safe) ====
from start_kalpe_nifty_master import start_kalpe_nifty_master
from nifty import run_nifty_scanner
from banknifty import run_banknifty_scanner
from iv_roc_scanner import run_iv_roc_scanner
from nifty_kalpe_bhai_2025 import run_kalpe_2025_scanner


# ======================================================
#   THREAD STARTER: AUTO-RESTART ANY CRASHED SCANNER
# ======================================================

def start_scanner(name, target):
    """Runs each scanner in a self-restarting thread."""
    def runner():
        while True:
            try:
                print(f"\n[{name}] STARTED at {datetime.now()}")
                target()
            except Exception as e:
                print(f"\n[{name}] CRASHED at {datetime.now()}")
                print("Error:", e)
                traceback.print_exc()
                print(f"[{name}] RESTARTING IN 5 SECONDS...\n")
                time.sleep(5)

    t = threading.Thread(target=runner, daemon=True)
    t.start()
    return t


# ======================================================
#   DASHBOARD DATA FETCHER (LIGHT, 1 REQ / MIN / SYMBOL)
# ======================================================

IST = pytz.timezone("Asia/Kolkata")

session = requests.Session()
session.headers.update({
    "authority": "www.nseindia.com",
    "accept": "application/json, text/plain, */*",
    "accept-encoding": "gzip, deflate, br, zstd",
    "accept-language": "en-US,en;q=0.9,en-IN;q=0.8",
    "referer": "https://www.nseindia.com/option-chain",
    "user-agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
})

_last_cookie_refresh = 0.0


def ensure_nse_session(force=False):
    """Refresh NSE cookies approx every 30 min."""
    global _last_cookie_refresh
    now = time.time()
    if not force and (now - _last_cookie_refresh) < 1800:
        return
    try:
        session.get("https://www.nseindia.com", timeout=10)
        _last_cookie_refresh = now
        print("[DASHBOARD] NSE cookies refreshed")
    except Exception as e:
        print("[DASHBOARD] Cookie refresh error:", e)


def ensure_json(r):
    """Detect HTML / captcha instead of JSON."""
    ct = r.headers.get("content-type", "").lower()
    txt = r.text.strip().lower()
    if "html" in ct or txt.startswith("<!doctype html") or txt.startswith("<html"):
        raise RuntimeError("HTML_BLOCKED")
    return r


# Shared dashboard state
dashboard_lock = threading.Lock()
dashboard_data = {
    "updated": None,
    "rows": []  # list of dicts
}

# Previous snapshot for % change (per symbol+strike+type)
prev_snapshot = {
    "NIFTY": {},
    "BANKNIFTY": {},
}


def fetch_oc(symbol: str):
    urls = [
        f"https://www.nseindia.com/api/option-chain-indices?symbol={symbol}",
        f"https://www.nseindia.com/api/option-chain-v3?type=Indices&symbol={symbol}",
    ]
    ensure_nse_session()
    last_err = None
    for u in urls:
        try:
            r = session.get(u, timeout=15)
            r.raise_for_status()
            ensure_json(r)
            j = r.json()
            rec = j.get("records") or j.get("filtered")
            if rec:
                return rec
        except Exception as e:
            last_err = e
            print(f"[DASHBOARD] {symbol} fetch error:", e)
    raise last_err or RuntimeError(f"{symbol} no data")


def dash_updater_loop():
    """Background: refresh dashboard rows every 60 sec."""
    ensure_nse_session(force=True)
    while True:
        try:
            now = datetime.now(IST)
            t = now.time()

            # Only during market hours
            if not (dtime(9, 15) <= t <= dtime(15, 30)):
                time.sleep(30)
                continue

            rows = []

            for symbol in ("NIFTY", "BANKNIFTY"):
                try:
                    rec = fetch_oc(symbol)
                except Exception as e:
                    print(f"[DASHBOARD] {symbol} skipped:", e)
                    continue

                spot = rec.get("underlyingValue") or 0
                if not spot:
                    continue

                if symbol == "NIFTY":
                    step = 50
                    rng = 200
                else:
                    step = 100
                    rng = 500

                atm = round(spot / step) * step
                prev = prev_snapshot[symbol]

                for item in rec.get("data", []):
                    strike = item.get("strikePrice")
                    if strike is None or abs(strike - atm) > rng:
                        continue

                    tag = (
                        "ATM" if abs(strike - atm) <= step
                        else "ITM" if strike > atm else "OTM"
                    )

                    for opt_type in ("CE", "PE"):
                        leg = item.get(opt_type) or {}
                        oi = int(leg.get("openInterest", 0) or 0)
                        iv = float(leg.get("impliedVolatility", 0) or 0.0)
                        ltp = float(leg.get("lastPrice", 0) or 0.0)

                        key = f"{symbol}_{strike}_{opt_type}"
                        old = prev.get(key, {"oi": oi, "iv": iv})

                        oi_roc = ((oi - old["oi"]) / old["oi"] * 100) if old["oi"] > 0 else 0.0
                        iv_roc = ((iv - old["iv"]) / old["iv"] * 100) if old["iv"] > 0 else 0.0

                        ovroc = oi_roc + iv_roc   # simple combined score
                        ovroc_pct = ovroc         # for display both OVROC & OVROC%

                        prev[key] = {"oi": oi, "iv": iv}

                        rows.append({
                            "symbol": symbol,
                            "strike": int(strike),
                            "type": opt_type,
                            "tag": tag,
                            "spot": round(spot),
                            "ltp": round(ltp, 2),
                            "oi": oi,
                            "oi_roc": round(oi_roc, 1),
                            "iv": round(iv, 2),
                            "iv_roc": round(iv_roc, 1),
                            "ovroc": round(ovroc, 1),
                            "ovroc_pct": round(ovroc_pct, 1),
                        })

            # Sort rows: strongest OVROC on top
            rows.sort(key=lambda r: abs(r["ovroc"]), reverse=True)

            with dashboard_lock:
                dashboard_data["updated"] = datetime.now(IST).strftime("%H:%M:%S")
                dashboard_data["rows"] = rows

        except Exception as e:
            print("[DASHBOARD] updater fatal:", e)
            traceback.print_exc()

        time.sleep(60)


# ======================================================
#   FLASK WEB APP (STYLE A – SIMPLE TABLE)
# ======================================================

app = Flask(__name__)

HTML_PAGE = """
<!doctype html>
<html>
<head>
  <meta charset="utf-8">
  <title>Kalpe Bhai – OI & IV Dashboard</title>
  <style>
    body { font-family: Arial, sans-serif; background:#050816; color:#e5e7eb; margin:0; }
    h1 { text-align:center; padding:10px 0; margin:0; }
    .info { text-align:center; font-size:13px; color:#9ca3af; margin-bottom:8px; }
    table { width:98%; margin:0 auto 16px auto; border-collapse:collapse; font-size:12px; }
    th, td { padding:4px 5px; border-bottom:1px solid #111827; text-align:right; }
    th { background:#0f172a; position:sticky; top:0; z-index:10; }
    td.symbol, th.symbol { text-align:left; }
    td.center { text-align:center; }
    tr:nth-child(even) { background:#020617; }
    tr:nth-child(odd) { background:#020617; }
    .bull { color:#22c55e; font-weight:bold; }
    .bear { color:#f97373; font-weight:bold; }
    .neutral { color:#e5e7eb; }
  </style>
</head>
<body>
  <h1>Kalpe Bhai – OI / IV / ROC Dashboard</h1>
  <div class="info">
    Simple Table View • Auto refresh 10 sec • Updated: <span id="updated">--:--:--</span>
  </div>
  <table id="tbl">
    <thead>
      <tr>
        <th class="symbol">Symbol</th>
        <th>Strike</th>
        <th>Type</th>
        <th>Tag</th>
        <th>Spot</th>
        <th>LTP</th>
        <th>OI</th>
        <th>OI%</th>
        <th>IV</th>
        <th>IV%</th>
        <th>OVROC</th>
        <th>OVROC%</th>
      </tr>
    </thead>
    <tbody></tbody>
  </table>

<script>
async function loadData() {
  try {
    const res = await fetch('/api/dashboard');
    const js = await res.json();

    document.getElementById('updated').innerText = js.updated || '--:--:--';

    const tbody = document.querySelector('#tbl tbody');
    tbody.innerHTML = '';

    (js.rows || []).forEach(row => {
      const tr = document.createElement('tr');

      const biasClass =
        row.ovroc > 20 ? 'bull' :
        row.ovroc < -20 ? 'bear' : 'neutral';

      tr.innerHTML = `
        <td class="symbol">${row.symbol}</td>
        <td>${row.strike}</td>
        <td class="center">${row.type}</td>
        <td class="center">${row.tag}</td>
        <td>${row.spot}</td>
        <td>${row.ltp.toFixed(2)}</td>
        <td>${row.oi.toLocaleString()}</td>
        <td>${row.oi_roc.toFixed(1)}%</td>
        <td>${row.iv.toFixed(2)}</td>
        <td>${row.iv_roc.toFixed(1)}%</td>
        <td class="${biasClass}">${row.ovroc.toFixed(1)}</td>
        <td class="${biasClass}">${row.ovroc_pct.toFixed(1)}%</td>
      `;
      tbody.appendChild(tr);
    });
  } catch (e) {
    console.error('load error', e);
  }
}

loadData();
setInterval(loadData, 10000);
</script>
</body>
</html>
"""

@app.route("/")
def index():
    return render_template_string(HTML_PAGE)

@app.route("/api/dashboard")
def api_dashboard():
    with dashboard_lock:
        return jsonify(dashboard_data)


# ======================================================
#   ENTRY POINT: START 5 SCANNERS + DASHBOARD SERVER
# ======================================================

def main():
    print("🔥 Starting 5 scanners + Web Dashboard for Kalpe Bhai")

    # scanners in background threads
    start_scanner("MASTER", start_kalpe_nifty_master)
    start_scanner("NIFTY_75", run_nifty_scanner)
    start_scanner("BANKNIFTY", run_banknifty_scanner)
    start_scanner("IV_ROC", run_iv_roc_scanner)
    start_scanner("KALPE_2025", run_kalpe_2025_scanner)

    # dashboard data updater thread
    threading.Thread(target=dash_updater_loop, daemon=True).start()

    # Flask app in main thread (Railway will expose this)
    port = int(os.getenv("PORT", "8000"))
    app.run(host="0.0.0.0", port=port)

if __name__ == "__main__":
    main()

# ===============================================================
# KALPE BHAI — LIVE OI / IV / IV ROC DASHBOARD + 5 SCANNERS
# ===============================================================

import threading
import time
from datetime import datetime
from flask import Flask, render_template_string

# ---------------- IMPORT SCANNERS ----------------
from start_kalpe_nifty_master import start_kalpe_nifty_master
from nifty import run_nifty_scanner
from banknifty import run_banknifty_scanner
from iv_roc_scanner import run_iv_roc_scanner
from nifty_kalpe_bhai_2025 import run_kalpe_2025_scanner

# ===============================================================
# GLOBAL DATA STORAGE (All scanners write here)
# ===============================================================

latest_data = {}       # strike → CE/PE data block
last_update = ""       # last refresh time


# ===============================================================
# BACKGROUND COLLECTOR THREAD
# ===============================================================

def data_collector():
    global last_update

    while True:
        try:
            now = datetime.now().strftime("%H:%M:%S")
            last_update = now

            # Scanners themselves already process / calculate.
            # Here we just update heartbeat timestamp.
            time.sleep(5)

        except Exception as e:
            print("Collector error:", e)
            time.sleep(5)


# ===============================================================
# RUN SCANNERS IN SAFE THREADS
# ===============================================================

def start_scanner(name, target):
    """Auto-restart on crash."""
    def wrapper():
        while True:
            try:
                print(f"[{name}] STARTED")
                target()
            except Exception as e:
                print(f"[{name}] CRASHED:", e)
                time.sleep(3)

    t = threading.Thread(target=wrapper, daemon=True)
    t.start()


def start_all_scanners():
    start_scanner("MASTER", start_kalpe_nifty_master)
    start_scanner("NIFTY_75", run_nifty_scanner)
    start_scanner("BANKNIFTY", run_banknifty_scanner)
    start_scanner("IV_ROC", run_iv_roc_scanner)
    start_scanner("NIFTY_2025", run_kalpe_2025_scanner)

    # Data collector
    threading.Thread(target=data_collector, daemon=True).start()


# ===============================================================
# FLASK DASHBOARD (Style A)
# ===============================================================

app = Flask(__name__)

HTML = """
<!DOCTYPE html>
<html>
<head>
<title>KALPE BHAI LIVE DASHBOARD</title>
<meta http-equiv="refresh" content="5">

<style>
    body { font-family: Arial; background: #111; color: #eee; }
    table { width: 98%; margin: auto; border-collapse: collapse; }
    th, td { padding: 8px 12px; text-align: center; }
    th { background: #333; }
    tr:nth-child(even) { background: #1c1c1c; }
    tr:nth-child(odd) { background: #171717; }
    .green { color: #00ff88; font-weight: bold; }
    .red { color: #ff4444; font-weight: bold; }
    .yellow { color: #ffd700; font-weight: bold; }
</style>
</head>

<body>
<h2 style="text-align:center;">🔥 KALPE BHAI LIVE DASHBOARD 🔥</h2>
<p style="text-align:center;">Last Update: {{ upd }}</p>

<table border="1">
<tr>
    <th>STRIKE</th>
    <th>CE OI</th>
    <th>CE OI%</th>
    <th>CE IV</th>
    <th>CE IVROC%</th>

    <th>PE OI</th>
    <th>PE OI%</th>
    <th>PE IV</th>
    <th>PE IVROC%</th>
</tr>

{% for row in rows %}
<tr>
    <td class="yellow">{{ row.strike }}</td>

    <td>{{ row.ce_oi }}</td>
    <td class="{{ row.ce_oichg_class }}">{{ row.ce_oichg }}</td>
    <td>{{ row.ce_iv }}</td>
    <td class="{{ row.ce_ivroc_class }}">{{ row.ce_ivroc }}</td>

    <td>{{ row.pe_oi }}</td>
    <td class="{{ row.pe_oichg_class }}">{{ row.pe_oichg }}</td>
    <td>{{ row.pe_iv }}</td>
    <td class="{{ row.pe_ivroc_class }}">{{ row.pe_ivroc }}</td>
</tr>
{% endfor %}
</table>

<br><br>
<p style="text-align:center;font-size:12px;color:#666;">
Auto-refresh every 5 seconds | Railway Powered
</p>

</body>
</html>
"""


@app.route("/")
def home():
    rows = []

    # Example dummy rows for dashboard test (real scanners will fill data)
    example = {
        "strike": "18000",
        "ce_oi": "120k",
        "ce_oichg": "+8%",
        "ce_oichg_class": "green",
        "ce_iv": "12.4",
        "ce_ivroc": "+3%",
        "ce_ivroc_class": "green",

        "pe_oi": "95k",
        "pe_oichg": "-5%",
        "pe_oichg_class": "red",
        "pe_iv": "14.8",
        "pe_ivroc": "-1%",
        "pe_ivroc_class": "red",
    }

    # add 5 dummy lines to show working UI
    for _ in range(5):
        rows.append(example)

    return render_template_string(HTML, rows=rows, upd=last_update)


# ===============================================================
# MAIN ENTRY
# ===============================================================

if __name__ == "__main__":
    print("🔥 Starting Kalpe Dashboard + 5 Scanners...")
    start_all_scanners()
    app.run(host="0.0.0.0", port=5000)

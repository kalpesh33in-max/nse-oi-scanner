# ==========================================================
#  KALPE BHAI – LIVE OI / IV / IV ROC DASHBOARD + 5 SCANNERS
# ==========================================================

import os
import threading
import time
from datetime import datetime
from flask import Flask, render_template_string

# -------------------- IMPORT SCANNERS --------------------
from start_kalpe_nifty_master import start_kalpe_nifty_master
from nifty import run_nifty_scanner
from banknifty import run_banknifty_scanner
from iv_roc_scanner import run_iv_roc_scanner
from nifty_kalpe_bhai_2025 import run_kalpe_2025_scanner


# Shared memory for UI
DATA = {
    "last_update": "Never",
    "records": []
}

# -------------------- FLASK APP --------------------
app = Flask(__name__)


HTML = """
<!DOCTYPE html>
<html>
<head>
    <title>KALPE BHAI LIVE DASHBOARD</title>
    <style>
        body { font-family: Arial; background: #111; color: #eee; padding:20px; }
        h1 { color: #6cf; }
        table { width:100%; border-collapse: collapse; margin-top:20px; }
        th, td { padding:8px; border-bottom:1px solid #444; text-align:center; }
        tr:hover { background:#222; }
        .green { color:#00ff00; }
        .red { color:#ff3333; }
        .time { font-size:14px; color:#999; }
    </style>
    <meta http-equiv="refresh" content="5">
</head>
<body>

<h1>🔥 KALPE BHAI LIVE DASHBOARD 🔥</h1>
<div class="time">Last Update: {{ last_update }}</div>

<table>
    <tr>
        <th>Strike</th>
        <th>CE OI</th>
        <th>PE OI</th>
        <th>CE IV</th>
        <th>PE IV</th>
        <th>CE ROC%</th>
        <th>PE ROC%</th>
    </tr>

    {% for r in records %}
    <tr>
        <td>{{ r.strike }}</td>
        <td>{{ r.ce_oi }}</td>
        <td>{{ r.pe_oi }}</td>

        <td class="{{ 'green' if r.ce_iv_change > 0 else 'red' }}">{{ r.ce_iv }}</td>
        <td class="{{ 'green' if r.pe_iv_change > 0 else 'red' }}">{{ r.pe_iv }}</td>

        <td class="{{ 'green' if r.ce_iv_change > 0 else 'red' }}">{{ r.ce_iv_change }}%</td>
        <td class="{{ 'green' if r.pe_iv_change > 0 else 'red' }}">{{ r.pe_iv_change }}%</td>
    </tr>
    {% endfor %}
</table>

</body>
</html>
"""


@app.route("/")
def home():
    return render_template_string(HTML, last_update=DATA["last_update"], records=DATA["records"])


# -------------------- BACKGROUND WORKER --------------------

def update_dashboard_loop():
    """
    This dummy loop updates UI every 5 sec.
    Later, real scanner data can be inserted.
    """
    while True:
        DATA["last_update"] = datetime.now().strftime("%H:%M:%S")

        # Sample dummy format — List of dicts
        DATA["records"] = [
            {
                "strike": 22000,
                "ce_oi": 120000,
                "pe_oi": 98000,
                "ce_iv": 12.4,
                "pe_iv": 14.8,
                "ce_iv_change": +3.1,
                "pe_iv_change": -2.4
            }
        ]

        time.sleep(5)


# -------------------- START SCANNERS --------------------

def start_thread(name, target):
    def wrapper():
        print(f"[{name}] Started")
        try:
            target()
        except Exception as e:
            print(f"[{name}] ERROR → {e}")

    t = threading.Thread(target=wrapper, daemon=True)
    t.start()


def start_all():
    # Start your 5 scanners
    start_thread("MASTER", start_kalpe_nifty_master)
    start_thread("NIFTY_75", run_nifty_scanner)
    start_thread("BANKNIFTY", run_banknifty_scanner)
    start_thread("IV_ROC", run_iv_roc_scanner)
    start_thread("KALPE_2025", run_kalpe_2025_scanner)

    # Start dashboard update loop
    threading.Thread(target=update_dashboard_loop, daemon=True).start()


# -------------------- MAIN --------------------
if __name__ == "__main__":
    start_all()

    port = int(os.environ.get("PORT", 8080))
    print(f"🔥 Dashboard running on port {port}")


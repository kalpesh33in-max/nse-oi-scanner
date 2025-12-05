# ================================================================
#   KALPE BHAI – LIVE OI / IV / IV ROC DASHBOARD + 5 SCANNERS
# ================================================================

import os
import threading
import time
from datetime import datetime
from flask import Flask, render_template_string

app = Flask(__name__)

# Flag to enable scanners only when required
RUN_SCANNERS = os.environ.get("RUN_SCANNERS", "0") == "1"


# ------------------------- IMPORT SCANNERS --------------------------
from start_kalpe_nifty_master import start_kalpe_nifty_master
from nifty import run_nifty_scanner
from banknifty import run_banknifty_scanner
from iv_roc_scanner import run_iv_roc_scanner
from nifty_kalpe_bhai_2025 import run_kalpe_2025_scanner


# --------------------- THREAD STARTER FUNCTION ----------------------
def start_thread(name, func):
    """Runs each scanner inside a protected background thread."""
    def wrapper():
        try:
            print(f"[{name}] Started")
            func()
        except Exception as e:
            print(f"[{name}] ERROR: {e}")

    t = threading.Thread(target=wrapper, daemon=True)
    t.start()
    return t


# ---------------------- START ALL SCANNERS --------------------------
def start_all():
    start_thread("MASTER", start_kalpe_nifty_master)
    start_thread("NIFTY_75", run_nifty_scanner)
    start_thread("BANKNIFTY", run_banknifty_scanner)
    start_thread("IV_ROC", run_iv_roc_scanner)
    start_thread("KALPE_2025", run_kalpe_2025_scanner)


# ----------------------- DASHBOARD ROUTE ----------------------------
@app.route("/")
def home():
    now = datetime.now().strftime("%H:%M:%S")
    return f"""
    <h2>🔥 Kalpe Bhai LIVE Dashboard</h2>
    <p>Updated: {now}</p>
    <p>Scanner Status: {"RUNNING" if RUN_SCANNERS else "OFF"}</p>
    """


# ----------------------- MAIN ENTRY POINT ---------------------------
def start_background_scanners():
    print("🔥 Starting all scanners in background threads...")
    start_all()


if __name__ == "__main__":

    # Start scanners ONLY if enabled
    if RUN_SCANNERS:
        threading.Thread(
            target=start_background_scanners,
            daemon=True
        ).start()

    port = int(os.environ.get("PORT", 8080))
    print(f"🔥 Dashboard running on port {port}")

    # Needed for Gunicorn + Railway
    app.run(host="0.0.0.0", port=port)

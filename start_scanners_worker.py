# ================================================================
#   KALPE BHAI – SCANNERS WORKER (NO WEB SERVER)
#   Runs all scanners in background threads for Railway worker.
# ================================================================

import threading
import time

from start_kalpe_nifty_master import start_kalpe_nifty_master
from nifty import run_nifty_scanner
from banknifty import run_banknifty_scanner
from iv_roc_scanner import run_iv_roc_scanner
from nifty_kalpe_bhai_2025 import run_kalpe_2025_scanner


def start_thread(name, func):
    """Runs each scanner inside a protected background thread."""
    def wrapper():
        try:
            print(f"[{name}] Started")
            func()
        except Exception as e:
            print(f"[{name}] ERROR: {e}", flush=True)

    t = threading.Thread(target=wrapper, daemon=True)
    t.start()
    return t


def start_all():
    print("🔥 Starting all Kalpe Bhai scanners...", flush=True)
    start_thread("MASTER", start_kalpe_nifty_master)
    start_thread("NIFTY_75", run_nifty_scanner)
    start_thread("BANKNIFTY", run_banknifty_scanner)
    start_thread("IV_ROC", run_iv_roc_scanner)
    start_thread("KALPE_2025", run_kalpe_2025_scanner)


if __name__ == "__main__":
    start_all()

    # Keep the worker process alive forever
    while True:
        time.sleep(60)

# all_scanners_5_runner.py
# Kalpe Bhai 5-in-1 Scanner Runner for Railway

import threading
import time
from datetime import datetime

from start_kalpe_nifty_master import start_kalpe_nifty_master
from nifty import run_nifty_scanner
from banknifty import run_banknifty_scanner
from iv_roc_scanner import run_iv_roc_scanner
from nifty_kalpe_bhai_2025 import run_kalpe_2025_scanner


def start_thread(name, target):
    """Helper to start each scanner in its own daemon thread."""
    def wrapper():
        try:
            print(f"[{name}] Thread started at {datetime.now()}")
            target()
        except Exception as e:
            print(f"[{name}] CRASHED with error: {e}")

    t = threading.Thread(target=wrapper, daemon=True)
    t.start()
    return t


def main():
    print("🔥 Starting 5 scanners together for Kalpe Bhai on Railway...")

    # 1) Master NIFTY OI + IV + IV ROC scanner (multi-mode)
    start_thread("KALPE_MASTER", start_kalpe_nifty_master)

    # 2) NIFTY 75 lot — 100+ lots blast only
    start_thread("NIFTY_75_BLAST", run_nifty_scanner)

    # 3) BANKNIFTY 35 lot — 100+ lots blast only
    start_thread("BANKNIFTY_35_BLAST", run_banknifty_scanner)

    # 4) NIFTY IV ROC blast scanner (Green/Red circle style)
    start_thread("NIFTY_IV_ROC", run_iv_roc_scanner)

    # 5) KALPE BHAI 2025 NIFTY SCANNER (AGGR / MOD / SAFE + SUPER)
    start_thread("KALPE_2025", run_kalpe_2025_scanner)

    # Keep container alive forever for Railway
    while True:
        print("❤️ ALL SCANNERS RUNNING... ", datetime.now())
        time.sleep(60)


if __name__ == "__main__":
    main()

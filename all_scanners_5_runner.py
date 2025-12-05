# ===============================================================
#  KALPE BHAI — SUPER STABLE 5 SCANNER RUNNER FOR RAILWAY
#  Auto-Restart | Crash-Proof | Block-Proof | Thread-Safe
# ===============================================================

import threading
import time
from datetime import datetime
import traceback

from start_kalpe_nifty_master import start_kalpe_nifty_master
from nifty import run_nifty_scanner
from banknifty import run_banknifty_scanner
from iv_roc_scanner import run_iv_roc_scanner
from nifty_kalpe_bhai_2025 import run_kalpe_2025_scanner


# ---------------------------------------------------------------
#  SAFE THREAD STARTER — WILL AUTO-RESTART ANY CRASHED SCANNER
# ---------------------------------------------------------------

def start_scanner(name, target):
    """Runs each scanner in a self-restarting infinite loop."""
    def runner():
        while True:
            try:
                print(f"\n[{name}] STARTED at {datetime.now()}")
                target()     # <-- actual scanner
            except Exception as e:
                print(f"\n[{name}] CRASHED at {datetime.now()}")
                print("Error:", e)
                traceback.print_exc()
                print(f"[{name}] RESTARTING IN 5 SECONDS...\n")
                time.sleep(5)  # <-- prevents rapid crash loops

    t = threading.Thread(target=runner, daemon=True)
    t.start()
    return t


# ---------------------------------------------------------------
#                     MAIN STARTER
# ---------------------------------------------------------------

def main():
    print("🔥 KALPE BHAI — 5 SCANNERS LAUNCHING ON RAILWAY...\n")

    # MASTER SCANNER
    start_scanner("MASTER_SCANNER", start_kalpe_nifty_master)

    # NIFTY 75 LOT (100+ lots)
    start_scanner("NIFTY_75_BLAST", run_nifty_scanner)

    # BANKNIFTY SCANNER
    start_scanner("BANKNIFTY_SCANNER", run_banknifty_scanner)

    # NIFTY IV ROC SCANNER
    start_scanner("NIFTY_IV_ROC", run_iv_roc_scanner)

    # NIFTY KALPE 2025 SCANNER
    start_scanner("KALPE_2025", run_kalpe_2025_scanner)

    # KEEP RAILWAY CONTAINER ALIVE
    while True:
        print("❤️ ALL SCANNERS RUNNING OK —", datetime.now())
        time.sleep(60)


if __name__ == "__main__":
    main()

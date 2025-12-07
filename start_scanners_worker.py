# ===============================================================
#   KALPE BHAI – SCANNER WORKER (NSE OI / IV / IV ROC / MASTER)
#   Runs 24×7 on Railway background worker
# ===============================================================

import threading
import time

from nifty import run_nifty_scanner
from banknifty import run_banknifty_scanner
from iv_roc_scanner import run_iv_roc_scanner
from nifty_kalpe_bhai_2025 import run_kalpe_2025_scanner
from start_kalpe_nifty_master import start_kalpe_nifty_master


def start_thread(name, func):
    def wrapper():
        print(f"[{name}] started.")
        try:
            func()
        except Exception as e:
            print(f"[{name}] ERROR: {e}")

    t = threading.Thread(target=wrapper, daemon=True)
    t.start()
    return t


def main():
    print("🔥 Starting ALL scanners (worker mode)...")

    start_thread("MASTER", start_kalpe_nifty_master)
    start_thread("NIFTY", run_nifty_scanner)
    start_thread("BANKNIFTY", run_banknifty_scanner)
    start_thread("IV_ROC", run_iv_roc_scanner)
    start_thread("KALPE_2025", run_kalpe_2025_scanner)

    while True:
        time.sleep(5)


if __name__ == "__main__":
    main()

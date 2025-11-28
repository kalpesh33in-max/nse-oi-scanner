# all_scanners_5_runner.py → KALPE BHAI 5-SCANNER LAUNCHER

import threading
import time

from main import start_kalpe_nifty_master
from nifty import run_nifty_scanner
from banknifty import run_banknifty_scanner
from iv_roc_scanner import run_iv_roc_scanner
from nifty_kalpe_bhai_2025 import run_kalpe_2025_scanner   # file name yahi rakho

def main():
    print("🔥 Starting 5 scanners together for Kalpe Bhai...")

    threading.Thread(target=start_kalpe_nifty_master, daemon=True).start()
    threading.Thread(target=run_nifty_scanner, daemon=True).start()
    threading.Thread(target=run_banknifty_scanner, daemon=True).start()
    threading.Thread(target=run_iv_roc_scanner, daemon=True).start()
    threading.Thread(target=run_kalpe_2025_scanner, daemon=True).start()

    while True:
        print("ALL-5-SCANNERS HEARTBEAT...")
        time.sleep(60)

if __name__ == "__main__":
    main()

import threading
import time

from start_kalpe_nifty_master import start_kalpe_nifty_master
from nifty import run_nifty_scanner
from banknifty import run_banknifty_scanner
from iv_roc_scanner import run_iv_roc_scanner
from nifty_kalpe_bhai_2025 import run_kalpe_2025_scanner


def main():
    print("🔥 Starting 5 scanners together for Kalpe Bhai...")

    # Start all scanners
    threading.Thread(target=start_kalpe_nifty_master, daemon=True).start()
    threading.Thread(target=run_nifty_scanner, daemon=True).start()
    threading.Thread(target=run_banknifty_scanner, daemon=True).start()
    threading.Thread(target=run_iv_roc_scanner, daemon=True).start()
    threading.Thread(target=run_kalpe_2025_scanner, daemon=True).start()

    # KEEP CONTAINER ALIVE (Railway auto-shutdown fix)
    while True:
        print("❤️ Scanner Running in Background...")
        time.sleep(60)


if __name__ == "__main__":
    main()

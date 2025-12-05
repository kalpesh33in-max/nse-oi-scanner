# ================================================================
#   KALPE BHAI – LIVE OI / IV / IV ROC DASHBOARD (WEB ONLY)
#   Scanners now run in a separate Railway worker service.
# ================================================================

import os
from datetime import datetime
from flask import Flask

app = Flask(__name__)


@app.route("/")
def home():
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    return f"""
    <h2>🔥 Kalpe Bhai LIVE Dashboard</h2>
    <p>Updated: {now}</p>
    <p>Scanners Status: RUNNING (separate Railway worker)</p>
    """


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    print(f"🔥 Dashboard running on port {port}")
    app.run(host="0.0.0.0", port=port)

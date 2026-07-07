"""
VisionX — Flask Backend (refactored slim entry point)
Architecture:
  ESP32-CAM ──MJPEG──► Flask Backend ──► AI Modules ──► Frontend Dashboard
"""

import os
import sys
import json
import logging

from flask import Flask, send_from_directory, abort
from flask_cors import CORS

# ── Paths ─────────────────────────────────────────────────────────────────────
BASE_DIR     = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONFIG_PATH  = os.path.join(BASE_DIR, "config", "backend_config.json")
FRONTEND_DIR = os.path.join(BASE_DIR, "frontend")

sys.path.insert(0, BASE_DIR)

# ── Config ────────────────────────────────────────────────────────────────────
with open(CONFIG_PATH) as f:
    config = json.load(f)

BACKEND_PORT = config.get("network", {}).get("backend_port", 5000)

# ── Logging ───────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler()],
)
logger = logging.getLogger("smartcap")

# ── Flask App ─────────────────────────────────────────────────────────────────
app = Flask(__name__, static_folder=FRONTEND_DIR)
CORS(app)

# ── Static frontend ───────────────────────────────────────────────────────────
@app.route("/")
def serve_index():
    return send_from_directory(FRONTEND_DIR, "index.html")

@app.route("/<path:path>")
def serve_static(path):
    if path.startswith("api/"):
        abort(404)
    return send_from_directory(FRONTEND_DIR, path)

# ── Register Blueprints ───────────────────────────────────────────────────────
from backend.routes import register_all
register_all(app, config)

# ── Entry Point ───────────────────────────────────────────────────────────────
def main():
    logger.info("=" * 55)
    logger.info("  VisionX — AI Wearable Backend")
    logger.info(f"  Dashboard : http://localhost:{BACKEND_PORT}")
    logger.info(f"  ESP32     : {config.get('esp32', {}).get('stream_url', 'not configured')}")
    logger.info("=" * 55)

    # Start background workers
    from backend.workers.device_watchdog import DeviceWatchdog
    from backend.workers.ai_worker       import AIWorker

    DeviceWatchdog().start()
    AIWorker(config).start()

    app.run(host="0.0.0.0", port=BACKEND_PORT, debug=False, threaded=True)


if __name__ == "__main__":
    main()

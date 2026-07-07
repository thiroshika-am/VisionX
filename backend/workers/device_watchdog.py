"""Device watchdog — marks ESP32 offline after 30 s of silence."""

import time
import logging
import threading
from datetime import datetime, timezone

import backend.state as state

logger = logging.getLogger("smartcap")
OFFLINE_AFTER_SEC = 30


class DeviceWatchdog:
    def __init__(self):
        self._thread = threading.Thread(target=self._run, daemon=True)

    def start(self):
        self._thread.start()
        logger.info("[Watchdog] Started")

    def _run(self):
        while True:
            time.sleep(10)
            with state.status_lock:
                last_seen = state.device_status.get("last_seen")
                if last_seen:
                    last = datetime.fromisoformat(last_seen)
                    if last.tzinfo is None:
                        last = last.replace(tzinfo=timezone.utc)
                    delta = (datetime.now(timezone.utc) - last).total_seconds()
                    if delta > OFFLINE_AFTER_SEC:
                        state.device_status["online"] = False

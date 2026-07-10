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

            with state.frame_lock:
                frame_time = state.latest_frame_time

            with state.status_lock:
                # If we haven't seen a frame in 15 seconds, and device is online
                if time.time() - frame_time > 15:
                    if not state.device_status.get("camera_offline"):
                        state.device_status["camera_offline"] = True
                        logger.warning("[Watchdog] Camera feed interrupted or dead.")
                else:
                    if state.device_status.get("camera_offline"):
                        state.device_status["camera_offline"] = False
                        logger.info("[Watchdog] Camera feed restored.")

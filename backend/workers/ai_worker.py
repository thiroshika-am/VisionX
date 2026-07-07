"""
Background AI Worker
Continuously processes the latest camera frame through face recognition
and gesture detection at configurable intervals.
"""

import os
import sys
import time
import base64
import logging
import threading
from datetime import datetime

import cv2
import numpy as np

import backend.state as state

logger = logging.getLogger("smartcap")

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))


def _decode_b64(image_b64: str):
    try:
        if "," in image_b64:
            image_b64 = image_b64.split(",")[1]
        arr = np.frombuffer(base64.b64decode(image_b64), dtype=np.uint8)
        return cv2.imdecode(arr, cv2.IMREAD_COLOR)
    except Exception:
        return None


def _trigger_vibration(esp_stream_url: str, pattern: str):
    import requests
    def run():
        try:
            ip = esp_stream_url.split("/")[2].split(":")[0]
            requests.get(f"http://{ip}:80/vibrate?pattern={pattern}", timeout=2)
        except Exception:
            pass
    threading.Thread(target=run, daemon=True).start()


class AIWorker:
    def __init__(self, config: dict):
        self.config         = config
        self.family_cfg     = config.get("modules", {}).get("family_recognition", {
            "enabled": True, "interval_sec": 1.5,
            "confidence_threshold": 0.6, "announce_cooldown_sec": 30,
        })
        self.gesture_cfg    = config.get("modules", {}).get("gesture_recognition", {
            "enabled": True, "interval_sec": 0.5, "hold_duration_sec": 0.5,
        })
        self.esp_stream_url = config.get("esp32", {}).get("stream_url", "")
        self._thread        = threading.Thread(target=self._run, daemon=True)

    def start(self):
        self._thread.start()
        logger.info("[AIWorker] Background AI worker started")

    # ── Main loop ─────────────────────────────────────────────────────────────

    def _run(self):
        last_face_run    = 0.0
        last_gesture_run = 0.0
        face_interval    = float(self.family_cfg.get("interval_sec", 1.5))
        gesture_interval = float(self.gesture_cfg.get("interval_sec", 0.5))

        while True:
            try:
                time.sleep(0.05)

                image_b64 = None
                with state.frame_lock:
                    if state.latest_frame_data:
                        image_b64 = state.latest_frame_data
                        state.latest_frame_data = None

                if image_b64 is None:
                    continue

                frame = _decode_b64(image_b64)
                if frame is None:
                    continue

                now = time.time()

                # ── Face recognition ──────────────────────────────────────────
                if self.family_cfg.get("enabled", True) and (now - last_face_run >= face_interval):
                    last_face_run = now
                    self._run_face(frame, now)

                # ── Gesture recognition ───────────────────────────────────────
                if self.gesture_cfg.get("enabled", True) and (now - last_gesture_run >= gesture_interval):
                    last_gesture_run = now
                    self._run_gesture(frame, now)

                # ── Fall detection (periodic, every 2s) ───────────────────────
                if now % 2.0 < 0.1:
                    self._run_fall(frame)

            except Exception as e:
                logger.error(f"[AIWorker] Error: {e}", exc_info=True)

    # ── Face ─────────────────────────────────────────────────────────────────

    def _run_face(self, frame, now):
        try:
            from ai_modules.face_recognition_engine import get_face_engine
            result = get_face_engine().detect(frame)
            with state.ai_results_lock:
                state.latest_faces_result = result

            conf_threshold  = float(self.family_cfg.get("confidence_threshold", 0.6))
            cooldown_sec    = float(self.family_cfg.get("announce_cooldown_sec", 30))

            for face in result.get("faces", []):
                if not face.get("is_known"):
                    continue
                if face.get("confidence", 0) < conf_threshold:
                    continue
                name      = face["name"]
                last_seen = state.last_face_announcements.get(name, 0)
                if now - last_seen < cooldown_sec:
                    continue
                face["should_announce"] = True
                state.last_face_announcements[name] = now
                with state.sightings_lock:
                    state.family_recent_sightings.insert(0, {
                        "name":       name,
                        "timestamp":  datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                        "confidence": face["confidence"],
                    })
                    if len(state.family_recent_sightings) > 50:
                        state.family_recent_sightings.pop()
                state.add_announcement(f"{name} is nearby.")
                logger.info(f"[AIWorker] Face: {name} ({face['confidence']:.2f})")
                _trigger_vibration(self.esp_stream_url, "family_nearby")
        except Exception as e:
            logger.error(f"[AIWorker] Face error: {e}")

    # ── Gesture ──────────────────────────────────────────────────────────────

    GESTURE_MEANINGS = {
        "Thumb_Up": "Yes / OK",   "thumbs_up": "Yes / OK",
        "Thumb_Down": "No",        "thumbs_down": "No",
        "Open_Palm": "Stop",       "open_palm": "Stop / Wait",
        "Pointing_Up": "Question", "pointing": "Question / Repeat that",
        "Victory": "Hello",        "victory": "Hello / Goodbye",
        "ILoveYou": "Help",        "fist": "Help / Emergency",
        "rock_on": "Help",         "call_me": "Help / Emergency",
    }

    def _run_gesture(self, frame, now):
        try:
            from ai_modules.gesture_engine import get_gesture_engine
            result = get_gesture_engine().detect(frame)
            with state.ai_results_lock:
                state.latest_gesture_result = result

            gestures     = result.get("gestures", [])
            hold_duration= float(self.gesture_cfg.get("hold_duration_sec", 0.5))

            if not gestures:
                state.gesture_hold_state["gesture"]    = None
                state.gesture_hold_state["first_seen"] = None
                return

            g            = gestures[0]
            gesture_name = g["gesture"]
            confidence   = g["confidence"]

            if state.gesture_hold_state["gesture"] == gesture_name:
                first = state.gesture_hold_state["first_seen"]
                if first and (now - first >= hold_duration):
                    if now - state.gesture_hold_state["last_fired"] > 2.0:
                        state.gesture_hold_state["last_fired"] = now
                        meaning = self.GESTURE_MEANINGS.get(gesture_name, "Unknown gesture")
                        with state.gesture_lock:
                            state.latest_debounced_gesture = {
                                "gesture":      gesture_name,
                                "display_name": g.get("display_name", gesture_name),
                                "meaning":      meaning,
                                "confidence":   confidence,
                                "timestamp":    datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                            }
                        state.add_announcement(f"User is signaling: {meaning}")
                        logger.info(f"[AIWorker] Gesture: {gesture_name} → {meaning}")
                        _trigger_vibration(self.esp_stream_url, "gesture_confirm")
            else:
                state.gesture_hold_state["gesture"]    = gesture_name
                state.gesture_hold_state["first_seen"] = now
        except Exception as e:
            logger.error(f"[AIWorker] Gesture error: {e}")

    # ── Fall ─────────────────────────────────────────────────────────────────

    def _run_fall(self, frame):
        try:
            src_path = os.path.join(os.path.dirname(__file__), "..", "..", "src")
            sys.path.insert(0, src_path)
            from ai.fall_detector import get_fall_detector
            result = get_fall_detector().detect(frame)
            if result.get("fall_detected"):
                logger.warning("[AIWorker] FALL DETECTED")
                state.add_announcement("Alert! A fall has been detected.")
                _trigger_vibration(self.esp_stream_url, "sos_active")
        except Exception:
            pass

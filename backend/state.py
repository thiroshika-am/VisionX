"""
VisionX — Shared Mutable State
All background-worker and route handlers import from this module.
Thread-safe via per-field locks.
"""

import threading
from datetime import datetime, timezone


# ── GPS ──────────────────────────────────────────────────────────────────────

gps_data = {
    "latitude": 12.9716,
    "longitude": 77.5946,
    "accuracy": 0,
    "speed": 0,
    "altitude": 0,
    "timestamp": datetime.now(timezone.utc).isoformat(),
    "source": "placeholder",
}
gps_lock = threading.Lock()

# ── Device Status ─────────────────────────────────────────────────────────────

device_status = {
    "online": False,
    "last_seen": None,
    "battery": None,
    "wifi_rssi": None,
    "distance_mm": None,
    "alert_level": "SAFE",
    "uptime": 0,
}
status_lock = threading.Lock()

# ── Latest camera frame (base64) ──────────────────────────────────────────────

latest_frame_data = None
latest_frame_time = 0.0
frame_lock = threading.Lock()

# ── Cached AI results ─────────────────────────────────────────────────────────

latest_faces_result   = {"faces": [], "count": 0}
latest_gesture_result = {"gestures": [], "count": 0}
ai_results_lock = threading.Lock()

# ── Debounced gesture ─────────────────────────────────────────────────────────

latest_debounced_gesture = {
    "gesture": "None",
    "display_name": "No Gesture",
    "meaning": "No Gesture",
    "confidence": 0.0,
    "timestamp": None,
}
gesture_lock = threading.Lock()

# ── Family sightings log ──────────────────────────────────────────────────────

family_recent_sightings = []   # [{name, timestamp, confidence}]
sightings_lock = threading.Lock()

# ── Pending TTS announcements ─────────────────────────────────────────────────

pending_announcements = []
announcements_lock = threading.Lock()

# ── Cooldown / hold states ────────────────────────────────────────────────────

last_face_announcements: dict = {}   # name -> float timestamp
gesture_hold_state = {
    "gesture": None,
    "first_seen": None,
    "last_fired": 0,
}

# ── Helpers ───────────────────────────────────────────────────────────────────

def add_announcement(text: str):
    with announcements_lock:
        pending_announcements.append(text)


def pop_announcements() -> list:
    with announcements_lock:
        msgs = list(pending_announcements)
        pending_announcements.clear()
        return msgs

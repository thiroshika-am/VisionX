"""
Smart Prioritizer — Context-aware detection filter for VisionX.

Scores detections by danger level, human presence, movement, and proximity.
Maintains a 60-second context memory to suppress repeated/stale announcements.
Ensures the blind user only hears what matters right now.
"""

import time
import threading
from typing import Dict, List, Optional

# ── Class taxonomy ────────────────────────────────────────────────────────────

DANGER_CLASSES = {
    "car", "truck", "bus", "motorcycle", "bicycle",
    "train", "fire hydrant", "stairs", "step",
}
HUMAN_CLASSES = {"person"}
MOVING_CLASSES = {"car", "truck", "bus", "motorcycle", "bicycle", "dog", "cat"}
NAV_CUE_CLASSES = {
    "traffic light", "stop sign", "door", "elevator",
    "stairs", "bench", "crosswalk",
}

ANNOUNCE_COOLDOWN: Dict[str, float] = {
    # class → seconds before re-announcing
    "person":       15.0,
    "car":          8.0,
    "truck":        8.0,
    "bus":          8.0,
    "bicycle":      10.0,
    "motorcycle":   8.0,
    "traffic light": 5.0,
    "stop sign":    5.0,
    "_default":     12.0,
}


class SmartPrioritizer:
    """Priority-based detection filter with 60-second context memory."""

    def __init__(self, context_window_sec: float = 60.0):
        self._context_window  = context_window_sec
        self._context_memory: Dict[str, dict] = {}  # class → {last_seen, position, distance, alert}
        self._last_announced:  Dict[str, float] = {}  # class → timestamp
        self._lock = threading.Lock()

    # ── Public API ────────────────────────────────────────────────────────────

    def prioritize(self, detections: List[dict]) -> List[dict]:
        """
        Filter and sort detections by importance.
        Also updates context memory and marks each detection with should_announce.
        """
        now = time.time()
        with self._lock:
            scored = []
            for det in detections:
                score = self._score(det, now)
                det["priority_score"] = score
                det["should_announce"] = self._should_announce(det["class"], now)
                scored.append((score, det))

            # Sort highest priority first
            scored.sort(key=lambda x: x[0], reverse=True)

            # Update context memory
            for _, det in scored:
                self._context_memory[det["class"]] = {
                    "last_seen": now,
                    "position":  det.get("position", "center"),
                    "distance":  det.get("distance_m"),
                    "alert":     det.get("alert_level", "SAFE"),
                }

            # Purge expired entries
            cutoff = now - self._context_window
            expired = [k for k, v in self._context_memory.items() if v["last_seen"] < cutoff]
            for k in expired:
                del self._context_memory[k]

            return [det for _, det in scored]

    def should_announce(self, cls: str) -> bool:
        """Mark a class as announced (call after actually speaking the alert)."""
        with self._lock:
            now = time.time()
            result = self._should_announce(cls, now)
            if result:
                self._last_announced[cls] = now
            return result

    def get_context_summary(self) -> dict:
        """Return a snapshot of the recent context memory (for scene description)."""
        now = time.time()
        with self._lock:
            return {
                k: v for k, v in self._context_memory.items()
                if now - v["last_seen"] <= 30.0
            }

    # ── Internal scoring ──────────────────────────────────────────────────────

    def _score(self, det: dict, now: float) -> float:
        cls     = det.get("class", "")
        alert   = det.get("alert_level", "SAFE")
        move    = det.get("movement", {})
        dist_m  = det.get("distance_m") or 999

        score = 0.0

        # Category base score
        if cls in DANGER_CLASSES:
            score += 100
        elif cls in HUMAN_CLASSES:
            score += 80
        elif cls in NAV_CUE_CLASSES:
            score += 50
        elif cls in MOVING_CLASSES:
            score += 60
        else:
            score += 20

        # Alert level boost
        if alert == "CRITICAL":
            score += 60
        elif alert == "WARNING":
            score += 30

        # Approaching boost (highest priority)
        if move.get("approaching"):
            score += 50

        # Distance boost — closer = more important
        if dist_m < 1.0:
            score += 40
        elif dist_m < 2.5:
            score += 20
        elif dist_m < 5.0:
            score += 10

        # Cooldown penalty — suppress recently announced objects
        cooldown = ANNOUNCE_COOLDOWN.get(cls, ANNOUNCE_COOLDOWN["_default"])
        last = self._last_announced.get(cls, 0)
        if now - last < cooldown:
            score -= 50

        return score

    def _should_announce(self, cls: str, now: float) -> bool:
        cooldown = ANNOUNCE_COOLDOWN.get(cls, ANNOUNCE_COOLDOWN["_default"])
        last = self._last_announced.get(cls, 0)
        return (now - last) >= cooldown


# Singleton
_prioritizer = None
_prioritizer_lock = threading.Lock()

def get_prioritizer() -> SmartPrioritizer:
    global _prioritizer
    if _prioritizer is None:
        with _prioritizer_lock:
            if _prioritizer is None:
                _prioritizer = SmartPrioritizer()
    return _prioritizer

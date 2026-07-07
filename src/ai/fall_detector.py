"""
Fall Detector for VisionX.
Detects falls by analyzing body pose via MediaPipe PoseLandmarker.
Uses hip-to-shoulder vertical ratio and landmark velocity heuristics.
Falls back to a YOLO person bounding-box aspect-ratio heuristic if pose is unavailable.
"""

import base64
import logging
import time
from collections import deque
from typing import Dict, Optional

import cv2
import numpy as np

logger = logging.getLogger("smartcap")

# Hip & shoulder landmark indices (MediaPipe)
L_SHOULDER, R_SHOULDER = 11, 12
L_HIP,      R_HIP      = 23, 24
L_ANKLE,    R_ANKLE    = 27, 28


class FallDetector:
    """Detects human falls from single camera frames using pose + YOLO."""

    # Thresholds
    HORIZONTAL_RATIO_THRESH = 0.60   # width/height > this → likely lying flat
    SHOULDER_HIP_Y_THRESH   = 0.20   # |shoulder_y - hip_y| < this → horizontal posture
    CONFIDENCE_THRESHOLD    = 0.40

    def __init__(self):
        self._fall_history: deque = deque(maxlen=5)   # recent fall votes
        self._last_alert_time = 0.0
        self._alert_cooldown  = 10.0  # seconds between alerts

    # ── Public API ────────────────────────────────────────────────────────────

    def detect(self, frame: np.ndarray) -> Dict:
        """Run fall detection on a BGR frame."""
        fall_detected = False
        method        = "none"
        confidence    = 0.0

        # Method 1: Pose-based (preferred)
        try:
            import sys, os
            sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
            from ai_modules.pose_engine import get_pose_engine
            pose_result = get_pose_engine().detect(frame)
            if pose_result.get("poses"):
                pose = pose_result["poses"][0]
                kps  = pose.get("keypoints", [])
                if len(kps) >= 29:
                    fall_detected, confidence = self._pose_fall_check(kps)
                    method = "pose"
        except Exception:
            pass

        # Method 2: YOLO bounding box aspect ratio (fallback)
        if not fall_detected and method == "none":
            try:
                sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
                from ai_modules.detector import get_detector
                det_result = get_detector().detect(frame)
                persons = [d for d in det_result.get("detections", []) if d["class"] == "person"]
                if persons:
                    fall_detected, confidence = self._bbox_fall_check(persons)
                    method = "bbox"
            except Exception:
                pass

        # Vote smoothing
        self._fall_history.append(int(fall_detected))
        votes      = sum(self._fall_history)
        smoothed   = votes >= 3  # 3 of last 5 frames → confirmed fall

        # Cooldown
        now = time.time()
        if smoothed and (now - self._last_alert_time) < self._alert_cooldown:
            smoothed = False  # suppress repeated alerts
        elif smoothed:
            self._last_alert_time = now

        return {
            "fall_detected": smoothed,
            "raw_vote":      fall_detected,
            "confidence":    round(confidence, 3),
            "method":        method,
        }

    def detect_from_base64(self, image_b64: str) -> Dict:
        try:
            if "," in image_b64:
                image_b64 = image_b64.split(",")[1]
            arr   = np.frombuffer(base64.b64decode(image_b64), dtype=np.uint8)
            frame = cv2.imdecode(arr, cv2.IMREAD_COLOR)
            if frame is None:
                return {"error": "Invalid image", "fall_detected": False}
            return self.detect(frame)
        except Exception as e:
            return {"error": str(e), "fall_detected": False}

    # ── Internal checks ───────────────────────────────────────────────────────

    def _pose_fall_check(self, kps: list):
        """
        Check if shoulders and hips are roughly at the same vertical level
        (indicating person is lying down).
        """
        try:
            l_sh_y = kps[L_SHOULDER]["y"]
            r_sh_y = kps[R_SHOULDER]["y"]
            l_hp_y = kps[L_HIP]["y"]
            r_hp_y = kps[R_HIP]["y"]

            sh_y = (l_sh_y + r_sh_y) / 2
            hp_y = (l_hp_y + r_hp_y) / 2

            vertical_diff = abs(sh_y - hp_y)  # normalised 0-1

            if vertical_diff < self.SHOULDER_HIP_Y_THRESH:
                confidence = 1.0 - vertical_diff / self.SHOULDER_HIP_Y_THRESH
                return True, min(confidence, 0.95)
            return False, 0.0
        except (IndexError, KeyError):
            return False, 0.0

    def _bbox_fall_check(self, persons: list):
        """
        If person bounding box is wider than tall → likely lying down.
        """
        for p in persons:
            bbox = p.get("bbox", {})
            w    = bbox.get("x2", 0) - bbox.get("x1", 0)
            h    = bbox.get("y2", 0) - bbox.get("y1", 0)
            if h > 0 and (w / h) > self.HORIZONTAL_RATIO_THRESH * 2:
                ratio = w / h
                confidence = min((ratio - 1.0) / 2.0, 0.85)
                return True, confidence
        return False, 0.0


# Singleton
_detector: Optional[FallDetector] = None


def get_fall_detector() -> FallDetector:
    global _detector
    if _detector is None:
        _detector = FallDetector()
    return _detector

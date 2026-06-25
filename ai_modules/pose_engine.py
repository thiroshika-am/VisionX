"""
Pose Estimation & Body Language Engine for VisionX
Detects human body keypoints and interprets posture/body language
using MediaPipe Pose model (33 landmarks).

Supports multi-person via YOLO person bounding boxes.
"""

import base64
import math
from typing import Dict, List, Optional, Tuple

import cv2
import numpy as np

try:
    import mediapipe as mp
    try:
        _test = mp.solutions.pose
        MEDIAPIPE_AVAILABLE = True
    except AttributeError:
        try:
            from mediapipe.python import solutions as _mp_solutions
            mp.solutions = _mp_solutions
            MEDIAPIPE_AVAILABLE = True
        except Exception:
            MEDIAPIPE_AVAILABLE = False
            print('[PoseEngine] mediapipe.solutions not available in this build')
except ImportError:
    MEDIAPIPE_AVAILABLE = False
    print('[PoseEngine] mediapipe not installed. Run: pip install mediapipe')


# ── MediaPipe Pose landmark indices ─────────────────────────────────────────
class PoseLandmark:
    NOSE = 0
    LEFT_EYE_INNER = 1;  LEFT_EYE = 2;  LEFT_EYE_OUTER = 3
    RIGHT_EYE_INNER = 4; RIGHT_EYE = 5; RIGHT_EYE_OUTER = 6
    LEFT_EAR = 7;  RIGHT_EAR = 8
    MOUTH_LEFT = 9; MOUTH_RIGHT = 10
    LEFT_SHOULDER = 11;  RIGHT_SHOULDER = 12
    LEFT_ELBOW = 13;     RIGHT_ELBOW = 14
    LEFT_WRIST = 15;     RIGHT_WRIST = 16
    LEFT_PINKY = 17;     RIGHT_PINKY = 18
    LEFT_INDEX = 19;     RIGHT_INDEX = 20
    LEFT_THUMB = 21;     RIGHT_THUMB = 22
    LEFT_HIP = 23;       RIGHT_HIP = 24
    LEFT_KNEE = 25;      RIGHT_KNEE = 26
    LEFT_ANKLE = 27;     RIGHT_ANKLE = 28
    LEFT_HEEL = 29;      RIGHT_HEEL = 30
    LEFT_FOOT_INDEX = 31; RIGHT_FOOT_INDEX = 32


# Skeleton connections for frontend drawing
POSE_CONNECTIONS = [
    (11, 12), (11, 13), (13, 15), (12, 14), (14, 16),  # arms
    (11, 23), (12, 24), (23, 24),                        # torso
    (23, 25), (25, 27), (24, 26), (26, 28),              # legs
    (27, 29), (29, 31), (28, 30), (30, 32),              # feet
    (0, 11),  (0, 12),                                    # head to shoulders
]


class PoseEngine:
    """MediaPipe Pose for body language analysis."""

    def __init__(self):
        self.mp_pose = None
        self.pose = None
        self.initialized = False
        self._init_mediapipe()

    def _init_mediapipe(self):
        if not MEDIAPIPE_AVAILABLE:
            return
        try:
            self.mp_pose = mp.solutions.pose
            self.pose = self.mp_pose.Pose(
                static_image_mode=False,
                model_complexity=1,            # 0=lite, 1=full, 2=heavy
                smooth_landmarks=True,
                enable_segmentation=False,
                min_detection_confidence=0.55,
                min_tracking_confidence=0.50,
            )
            self.initialized = True
            print("[PoseEngine] MediaPipe Pose initialized (model_complexity=1)")
        except Exception as e:
            print(f"[PoseEngine] Init failed: {e}")

    # ── Geometry helpers ─────────────────────────────────────────────────────

    @staticmethod
    def _angle_3pts(a, b, c) -> float:
        """Angle at b between a→b and b→c (degrees)."""
        ba = np.array([a.x - b.x, a.y - b.y])
        bc = np.array([c.x - b.x, c.y - b.y])
        cos_a = np.dot(ba, bc) / (np.linalg.norm(ba) * np.linalg.norm(bc) + 1e-9)
        return float(np.degrees(np.arccos(np.clip(cos_a, -1.0, 1.0))))

    @staticmethod
    def _midpoint(a, b):
        class _P:
            pass
        p = _P()
        p.x = (a.x + b.x) / 2
        p.y = (a.y + b.y) / 2
        p.visibility = min(a.visibility, b.visibility)
        return p

    def _landmark_visible(self, lm, idx: int, threshold: float = 0.4) -> bool:
        return lm[idx].visibility >= threshold

    # ── Posture classifiers ──────────────────────────────────────────────────

    def _classify_posture(self, lm) -> Tuple[str, float, List[str]]:
        """
        Classify body language from pose landmarks.
        Returns (posture_label, confidence, notes_list)
        """
        notes = []

        L  = PoseLandmark
        ls = lm[L.LEFT_SHOULDER];  rs = lm[L.RIGHT_SHOULDER]
        lh = lm[L.LEFT_HIP];       rh = lm[L.RIGHT_HIP]
        lk = lm[L.LEFT_KNEE];      rk = lm[L.RIGHT_KNEE]
        la = lm[L.LEFT_ANKLE];     ra = lm[L.RIGHT_ANKLE]
        lw = lm[L.LEFT_WRIST];     rw = lm[L.RIGHT_WRIST]
        le = lm[L.LEFT_ELBOW];     re = lm[L.RIGHT_ELBOW]
        nose = lm[L.NOSE]

        # ── Visibility check ────────────────────────────────────────────────
        upper_visible = (
            self._landmark_visible(lm, L.LEFT_SHOULDER) and
            self._landmark_visible(lm, L.RIGHT_SHOULDER)
        )
        lower_visible = (
            self._landmark_visible(lm, L.LEFT_HIP) and
            self._landmark_visible(lm, L.RIGHT_HIP) and
            self._landmark_visible(lm, L.LEFT_KNEE) and
            self._landmark_visible(lm, L.RIGHT_KNEE)
        )

        if not upper_visible:
            return "upper_body_only", 0.40, ["Only upper body visible"]

        # ── Knee angle (sitting vs standing) ────────────────────────────────
        left_knee_angle = right_knee_angle = 180.0
        if lower_visible:
            left_knee_angle  = self._angle_3pts(lh, lk, la)
            right_knee_angle = self._angle_3pts(rh, rk, ra)
        avg_knee_angle = (left_knee_angle + right_knee_angle) / 2

        # ── Hip position relative to shoulders (for sitting/standing) ───────
        shoulder_mid_y = (ls.y + rs.y) / 2
        hip_mid_y      = (lh.y + rh.y) / 2
        torso_length   = abs(hip_mid_y - shoulder_mid_y)

        # ── Arm positions ────────────────────────────────────────────────────
        # Raised hand: wrist above shoulder
        left_hand_raised  = lw.y < ls.y - 0.05
        right_hand_raised = rw.y < rs.y - 0.05

        # Crossed arms: wrists crossed at chest level
        wrists_at_chest = (abs(lw.y - ls.y) < 0.15 and abs(rw.y - rs.y) < 0.15)
        wrists_crossed  = (lw.x > rs.x * 0.5 and rw.x < ls.x * 1.5 and wrists_at_chest)

        # Arms wide open: wrists far outside shoulder width
        shoulder_width = abs(ls.x - rs.x)
        arms_wide = (
            abs(lw.x - rw.x) > shoulder_width * 2.0 and
            abs(lw.y - ls.y) < 0.15 and abs(rw.y - rs.y) < 0.15
        )

        # ── Classify ─────────────────────────────────────────────────────────

        # Walking — knees bent + hip displacement
        if lower_visible and 100 < avg_knee_angle < 160:
            left_knee_ang  = self._angle_3pts(lh, lk, la)
            right_knee_ang = self._angle_3pts(rh, rk, ra)
            asymmetry = abs(left_knee_ang - right_knee_ang)
            if asymmetry > 15:
                return "walking", 0.82, ["Asymmetric knee bend detected"]

        # Sitting — knee angle < ~100 degrees
        if lower_visible and avg_knee_angle < 110:
            notes.append(f"Knee angle {avg_knee_angle:.0f}°")
            return "sitting", 0.88, notes

        # Both hands raised (surrender / cheer)
        if left_hand_raised and right_hand_raised:
            return "both_hands_raised", 0.90, ["Both wrists above shoulders"]

        # One hand raised
        if left_hand_raised and not right_hand_raised:
            notes.append("Left wrist above shoulder")
            return "raising_left_hand", 0.85, notes
        if right_hand_raised and not left_hand_raised:
            notes.append("Right wrist above shoulder")
            return "raising_right_hand", 0.85, notes

        # Crossed arms (defensive/thinking)
        if wrists_crossed:
            return "crossed_arms", 0.80, ["Wrists crossed at chest level"]

        # Arms wide (welcoming / open stance)
        if arms_wide:
            return "arms_wide_open", 0.82, ["Arms extended wide"]

        # Default standing
        if lower_visible and avg_knee_angle > 155:
            return "standing", 0.88, [f"Knee angle {avg_knee_angle:.0f}°"]

        return "standing", 0.65, ["Default posture"]

    # ── Bending/leaning analysis ──────────────────────────────────────────────

    def _analyze_body_lean(self, lm) -> Optional[Dict]:
        """Detect body lean direction."""
        L = PoseLandmark
        if not (self._landmark_visible(lm, L.LEFT_SHOULDER) and
                self._landmark_visible(lm, L.RIGHT_SHOULDER) and
                self._landmark_visible(lm, L.LEFT_HIP) and
                self._landmark_visible(lm, L.RIGHT_HIP)):
            return None

        shoulder_mid_x = (lm[L.LEFT_SHOULDER].x + lm[L.RIGHT_SHOULDER].x) / 2
        hip_mid_x      = (lm[L.LEFT_HIP].x       + lm[L.RIGHT_HIP].x)       / 2
        lean_offset    = shoulder_mid_x - hip_mid_x

        if abs(lean_offset) < 0.04:
            direction = "upright"
        elif lean_offset > 0:
            direction = "leaning_right"
        else:
            direction = "leaning_left"

        return {"direction": direction, "magnitude": round(abs(lean_offset), 3)}

    # ── Main detection ────────────────────────────────────────────────────────

    def detect(self, frame: np.ndarray) -> Dict:
        """Detect pose in a BGR frame."""
        if not self.initialized:
            return {"poses": [], "error": "MediaPipe not available", "count": 0}

        try:
            h, w = frame.shape[:2]
            rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            results = self.pose.process(rgb)

            if not results.pose_landmarks:
                return {"poses": [], "count": 0}

            lm = results.pose_landmarks.landmark

            # Classify posture
            posture, confidence, notes = self._classify_posture(lm)
            lean = self._analyze_body_lean(lm)

            # Flatten 33 keypoints for frontend
            keypoints = [
                {
                    "x": round(l.x, 4),
                    "y": round(l.y, 4),
                    "z": round(l.z, 4),
                    "visibility": round(l.visibility, 3),
                }
                for l in lm
            ]

            # Compute body bounding box from visible landmarks
            visible_xs = [l.x * w for l in lm if l.visibility > 0.4]
            visible_ys = [l.y * h for l in lm if l.visibility > 0.4]
            if visible_xs and visible_ys:
                pad = 20
                bbox = {
                    "x1": max(0, int(min(visible_xs)) - pad),
                    "y1": max(0, int(min(visible_ys)) - pad),
                    "x2": min(w, int(max(visible_xs)) + pad),
                    "y2": min(h, int(max(visible_ys)) + pad),
                }
            else:
                bbox = {"x1": 0, "y1": 0, "x2": w, "y2": h}

            pose_data = {
                "posture": posture,
                "display_name": posture.replace("_", " ").title(),
                "confidence": round(confidence, 3),
                "notes": notes,
                "lean": lean,
                "keypoints": keypoints,
                "connections": POSE_CONNECTIONS,
                "bbox": bbox,
            }

            return {"poses": [pose_data], "count": 1}

        except Exception as e:
            return {"poses": [], "error": str(e), "count": 0}

    def detect_from_base64(self, image_b64: str) -> Dict:
        """Detect pose from base64 image."""
        try:
            if "," in image_b64:
                image_b64 = image_b64.split(",")[1]
            img_bytes = base64.b64decode(image_b64)
            img_array = np.frombuffer(img_bytes, dtype=np.uint8)
            frame = cv2.imdecode(img_array, cv2.IMREAD_COLOR)
            if frame is None:
                return {"poses": [], "error": "Invalid image", "count": 0}
            return self.detect(frame)
        except Exception as e:
            return {"poses": [], "error": str(e), "count": 0}

    def close(self):
        if self.pose:
            self.pose.close()


# Singleton
_pose_engine: Optional[PoseEngine] = None

def get_pose_engine() -> PoseEngine:
    global _pose_engine
    if _pose_engine is None:
        _pose_engine = PoseEngine()
    return _pose_engine

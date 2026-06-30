"""
Pose Estimation & Body Language Engine for VisionX
Uses MediaPipe Tasks API (0.10+) PoseLandmarker for 33-keypoint detection.
Classifies posture: standing, sitting, walking, raising hand, crossed arms, etc.
"""

import base64
import math
import os
import urllib.request
from typing import Dict, List, Optional, Tuple

import cv2
import numpy as np

# ── Model download ────────────────────────────────────────────────────────────
MODELS_DIR = os.path.join(os.path.dirname(__file__), "..", "config", "models")
os.makedirs(MODELS_DIR, exist_ok=True)

POSE_MODEL_PATH = os.path.join(MODELS_DIR, "pose_landmarker_full.task")
POSE_MODEL_URL = (
    "https://storage.googleapis.com/mediapipe-models/pose_landmarker/"
    "pose_landmarker_full/float16/latest/pose_landmarker_full.task"
)

MEDIAPIPE_AVAILABLE = False
try:
    import mediapipe as mp
    from mediapipe.tasks import python as mp_python
    from mediapipe.tasks.python import vision as mp_vision
    MEDIAPIPE_AVAILABLE = True
except ImportError:
    print("[PoseEngine] mediapipe not installed.")


def _download_model(url: str, path: str, name: str) -> bool:
    if os.path.exists(path):
        return True
    try:
        print(f"[PoseEngine] Downloading {name}...")
        urllib.request.urlretrieve(url, path)
        print(f"[PoseEngine] Downloaded to {path}")
        return True
    except Exception as e:
        print(f"[PoseEngine] Download failed: {e}")
        return False


# ── Landmark index constants ──────────────────────────────────────────────────
class L:
    NOSE = 0
    LEFT_SHOULDER = 11;  RIGHT_SHOULDER = 12
    LEFT_ELBOW    = 13;  RIGHT_ELBOW    = 14
    LEFT_WRIST    = 15;  RIGHT_WRIST    = 16
    LEFT_HIP      = 23;  RIGHT_HIP      = 24
    LEFT_KNEE     = 25;  RIGHT_KNEE     = 26
    LEFT_ANKLE    = 27;  RIGHT_ANKLE    = 28
    LEFT_FOOT     = 31;  RIGHT_FOOT     = 32
    PINKY         = 17;  THUMB          = 21


# Skeleton connections for frontend drawing
POSE_CONNECTIONS = [
    (11, 12), (11, 13), (13, 15), (12, 14), (14, 16),
    (11, 23), (12, 24), (23, 24),
    (23, 25), (25, 27), (24, 26), (26, 28),
    (27, 29), (29, 31), (28, 30), (30, 32),
]


class PoseEngine:
    """MediaPipe Tasks API pose estimation and body language analysis."""

    def __init__(self):
        self.pose_landmarker = None
        self.initialized = False
        self._init()

    def _init(self):
        if not MEDIAPIPE_AVAILABLE:
            return
        if not _download_model(POSE_MODEL_URL, POSE_MODEL_PATH, "PoseLandmarker"):
            print("[PoseEngine] Model not available, will retry on next request")
            return
        try:
            base_options = mp_python.BaseOptions(model_asset_path=POSE_MODEL_PATH)
            options = mp_vision.PoseLandmarkerOptions(
                base_options=base_options,
                running_mode=mp_vision.RunningMode.IMAGE,
                num_poses=1,
                min_pose_detection_confidence=0.55,
                min_pose_presence_confidence=0.5,
                min_tracking_confidence=0.5,
            )
            self.pose_landmarker = mp_vision.PoseLandmarker.create_from_options(options)
            self.initialized = True
            print("[PoseEngine] PoseLandmarker initialized")
        except Exception as e:
            print(f"[PoseEngine] Init failed: {e}")

    # ── Geometry helpers ──────────────────────────────────────────────────────

    @staticmethod
    def _angle_3pts(a, b, c) -> float:
        ba = np.array([a.x - b.x, a.y - b.y])
        bc = np.array([c.x - b.x, c.y - b.y])
        cos_a = np.dot(ba, bc) / (np.linalg.norm(ba) * np.linalg.norm(bc) + 1e-9)
        return float(np.degrees(np.arccos(np.clip(cos_a, -1.0, 1.0))))

    def _vis(self, lm, idx: int, thresh: float = 0.4) -> bool:
        return lm[idx].visibility >= thresh

    # ── Posture classification ────────────────────────────────────────────────

    def _classify(self, lm) -> Tuple[str, float, Dict]:
        upper_ok = self._vis(lm, L.LEFT_SHOULDER) and self._vis(lm, L.RIGHT_SHOULDER)
        lower_ok = (self._vis(lm, L.LEFT_HIP) and self._vis(lm, L.RIGHT_HIP) and
                    self._vis(lm, L.LEFT_KNEE) and self._vis(lm, L.RIGHT_KNEE))

        if not upper_ok:
            return "upper_body_only", 0.45, {}

        ls, rs = lm[L.LEFT_SHOULDER],  lm[L.RIGHT_SHOULDER]
        lh, rh = lm[L.LEFT_HIP],       lm[L.RIGHT_HIP]
        lk, rk = lm[L.LEFT_KNEE],      lm[L.RIGHT_KNEE]
        la, ra = lm[L.LEFT_ANKLE],     lm[L.RIGHT_ANKLE]
        lw, rw = lm[L.LEFT_WRIST],     lm[L.RIGHT_WRIST]

        # Compute knee angles
        avg_knee = 180.0
        if lower_ok:
            left_ka  = self._angle_3pts(lh, lk, la)
            right_ka = self._angle_3pts(rh, rk, ra)
            avg_knee = (left_ka + right_ka) / 2

        # Arm raises
        left_raised  = self._vis(lm, L.LEFT_WRIST)  and lw.y < ls.y - 0.05
        right_raised = self._vis(lm, L.RIGHT_WRIST) and rw.y < rs.y - 0.05

        # Crossed arms
        wrists_at_chest = (abs(lw.y - ls.y) < 0.15 and abs(rw.y - rs.y) < 0.15)
        crossed = wrists_at_chest and lw.x > rs.x * 0.5 and rw.x < ls.x * 1.5

        # Arms wide
        sw = abs(ls.x - rs.x)
        arms_wide = abs(lw.x - rw.x) > sw * 2.0 and abs(lw.y - ls.y) < 0.15

        # Lean analysis
        sh_mid_x = (ls.x + rs.x) / 2
        hp_mid_x = (lh.x + rh.x) / 2
        lean_off  = sh_mid_x - hp_mid_x
        lean_dir  = "upright" if abs(lean_off) < 0.04 else ("leaning_right" if lean_off > 0 else "leaning_left")
        lean = {"direction": lean_dir, "magnitude": round(abs(lean_off), 3)}

        # Sitting
        if lower_ok and avg_knee < 115:
            return "sitting", 0.88, lean

        # Walking
        if lower_ok and 100 < avg_knee < 162:
            left_ka  = self._angle_3pts(lh, lk, la)
            right_ka = self._angle_3pts(rh, rk, ra)
            if abs(left_ka - right_ka) > 15:
                return "walking", 0.82, lean

        # Both hands raised
        if left_raised and right_raised:
            return "both_hands_raised", 0.90, lean

        # One hand raised
        if left_raised:
            return "raising_left_hand", 0.85, lean
        if right_raised:
            return "raising_right_hand", 0.85, lean

        # Crossed arms
        if crossed:
            return "crossed_arms", 0.80, lean

        # Arms wide
        if arms_wide:
            return "arms_wide_open", 0.82, lean

        # Default standing
        if lower_ok and avg_knee > 155:
            return "standing", 0.88, lean

        return "standing", 0.65, lean

    # ── Main detection ────────────────────────────────────────────────────────

    def detect(self, frame: np.ndarray) -> Dict:
        if not self.initialized:
            # Try lazy init (model might have downloaded since startup)
            if not self.pose_landmarker:
                self._init()
            if not self.initialized:
                return {"poses": [], "count": 0,
                        "note": "PoseLandmarker model downloading..."}

        try:
            h, w = frame.shape[:2]
            rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb)
            result = self.pose_landmarker.detect(mp_image)

            if not result.pose_landmarks:
                return {"poses": [], "count": 0}

            poses = []
            for lm_list in result.pose_landmarks:
                posture, confidence, lean = self._classify(lm_list)

                # Flatten keypoints for frontend
                keypoints = [
                    {"x": round(l.x, 4), "y": round(l.y, 4), "z": round(l.z, 4),
                     "visibility": round(getattr(l, "visibility", 1.0), 3)}
                    for l in lm_list
                ]

                # Body bounding box
                vis_xs = [l.x * w for l in lm_list if getattr(l, "visibility", 1.0) > 0.4]
                vis_ys = [l.y * h for l in lm_list if getattr(l, "visibility", 1.0) > 0.4]
                pad = 20
                bbox = ({"x1": max(0, int(min(vis_xs)) - pad),
                          "y1": max(0, int(min(vis_ys)) - pad),
                          "x2": min(w, int(max(vis_xs)) + pad),
                          "y2": min(h, int(max(vis_ys)) + pad)}
                         if vis_xs and vis_ys else {"x1": 0, "y1": 0, "x2": w, "y2": h})

                poses.append({
                    "posture":      posture,
                    "display_name": posture.replace("_", " ").title(),
                    "confidence":   round(confidence, 3),
                    "lean":         lean,
                    "keypoints":    keypoints,
                    "connections":  POSE_CONNECTIONS,
                    "bbox":         bbox,
                })

            return {"poses": poses, "count": len(poses)}
        except Exception as e:
            return {"poses": [], "error": str(e), "count": 0}

    def detect_from_base64(self, image_b64: str) -> Dict:
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
        if self.pose_landmarker:
            self.pose_landmarker.close()


# Singleton
_pose_engine: Optional[PoseEngine] = None

def get_pose_engine() -> PoseEngine:
    global _pose_engine
    if _pose_engine is None:
        _pose_engine = PoseEngine()
    return _pose_engine

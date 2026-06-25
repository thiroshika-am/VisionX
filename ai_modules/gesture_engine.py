"""
Gesture Recognition Engine for VisionX
Detects and classifies hand gestures using MediaPipe Hand Landmarker.
Supports: thumbs_up, thumbs_down, stop, pointing, waving, victory,
          open_palm, fist, ok_sign, and more.
"""

import base64
import math
import time
from typing import Dict, List, Optional, Tuple

import cv2
import numpy as np

try:
    import mediapipe as mp
    # MediaPipe 0.10+ still exposes solutions but via different path on some builds
    # Try the standard path first, then the python sub-path
    try:
        _test = mp.solutions.hands
        MEDIAPIPE_AVAILABLE = True
    except AttributeError:
        try:
            from mediapipe.python import solutions as _mp_solutions
            mp.solutions = _mp_solutions
            MEDIAPIPE_AVAILABLE = True
        except Exception:
            MEDIAPIPE_AVAILABLE = False
            print('[GestureEngine] mediapipe.solutions not available in this build')
except ImportError:
    MEDIAPIPE_AVAILABLE = False
    print('[GestureEngine] mediapipe not installed. Run: pip install mediapipe')


# ── Landmark indices (MediaPipe Hand model) ─────────────────────────────────
WRIST      = 0
THUMB_CMC  = 1; THUMB_MCP  = 2; THUMB_IP   = 3; THUMB_TIP  = 4
INDEX_MCP  = 5; INDEX_PIP  = 6; INDEX_DIP  = 7; INDEX_TIP  = 8
MIDDLE_MCP = 9; MIDDLE_PIP = 10; MIDDLE_DIP = 11; MIDDLE_TIP = 12
RING_MCP   = 13; RING_PIP  = 14; RING_DIP   = 15; RING_TIP  = 16
PINKY_MCP  = 17; PINKY_PIP = 18; PINKY_DIP  = 19; PINKY_TIP = 20


class GestureEngine:
    """MediaPipe-based hand gesture recognition."""

    def __init__(self):
        self.mp_hands = None
        self.hands = None
        self.mp_drawing = None
        self.initialized = False
        self._init_mediapipe()
        self._last_gesture_time: Dict[str, float] = {}

    def _init_mediapipe(self):
        if not MEDIAPIPE_AVAILABLE:
            return
        try:
            self.mp_hands = mp.solutions.hands
            self.hands = self.mp_hands.Hands(
                static_image_mode=False,
                max_num_hands=2,
                min_detection_confidence=0.6,
                min_tracking_confidence=0.5,
                model_complexity=1,   # 0=lite, 1=full — use full for accuracy
            )
            self.mp_drawing = mp.solutions.drawing_utils
            self.initialized = True
            print("[GestureEngine] MediaPipe Hands initialized (model_complexity=1)")
        except Exception as e:
            print(f"[GestureEngine] Init failed: {e}")

    # ── Geometry helpers ────────────────────────────────────────────────────

    @staticmethod
    def _dist(a, b) -> float:
        return math.sqrt((a.x - b.x)**2 + (a.y - b.y)**2 + (a.z - b.z)**2)

    @staticmethod
    def _angle(a, b, c) -> float:
        """Angle at vertex b between vectors b→a and b→c (degrees)."""
        ba = (a.x - b.x, a.y - b.y, a.z - b.z)
        bc = (c.x - b.x, c.y - b.y, c.z - b.z)
        dot = sum(ba[i] * bc[i] for i in range(3))
        mag_ba = math.sqrt(sum(x**2 for x in ba)) + 1e-9
        mag_bc = math.sqrt(sum(x**2 for x in bc)) + 1e-9
        cos_angle = max(-1.0, min(1.0, dot / (mag_ba * mag_bc)))
        return math.degrees(math.acos(cos_angle))

    def _finger_extended(self, lm, tip_idx: int, pip_idx: int, mcp_idx: int) -> bool:
        """Return True if the finger is extended (tip above pip above mcp in y)."""
        tip  = lm[tip_idx]
        pip  = lm[pip_idx]
        mcp  = lm[mcp_idx]
        # In image coords y increases downward, so "above" means smaller y
        return tip.y < pip.y and pip.y < mcp.y

    def _thumb_extended(self, lm, handedness: str) -> bool:
        """Thumb extension check using lateral displacement."""
        tip = lm[THUMB_TIP]
        ip  = lm[THUMB_IP]
        mcp = lm[THUMB_MCP]
        cmc = lm[THUMB_CMC]
        # Thumb extends sideways; compare x-displacement from palm
        if handedness == "Right":
            return tip.x < ip.x and ip.x < mcp.x  # tip is to the left = extended
        else:
            return tip.x > ip.x and ip.x > mcp.x

    def _fingers_state(self, lm, handedness: str) -> Tuple[bool, bool, bool, bool, bool]:
        """Returns (thumb, index, middle, ring, pinky) extension state."""
        thumb  = self._thumb_extended(lm, handedness)
        index  = self._finger_extended(lm, INDEX_TIP,  INDEX_PIP,  INDEX_MCP)
        middle = self._finger_extended(lm, MIDDLE_TIP, MIDDLE_PIP, MIDDLE_MCP)
        ring   = self._finger_extended(lm, RING_TIP,   RING_PIP,   RING_MCP)
        pinky  = self._finger_extended(lm, PINKY_TIP,  PINKY_PIP,  PINKY_MCP)
        return thumb, index, middle, ring, pinky

    # ── Gesture classifiers ─────────────────────────────────────────────────

    def _classify_gesture(self, lm, handedness: str) -> Tuple[str, float]:
        """Classify gesture from landmarks. Returns (gesture_name, confidence)."""
        t, i, m, r, p = self._fingers_state(lm, handedness)
        finger_count = sum([t, i, m, r, p])

        # ── Thumbs Up ──────────────────────────────────────────────────────
        if t and not i and not m and not r and not p:
            # Thumb tip is significantly above wrist
            if lm[THUMB_TIP].y < lm[WRIST].y - 0.05:
                return "thumbs_up", 0.90

        # ── Thumbs Down ────────────────────────────────────────────────────
        if t and not i and not m and not r and not p:
            if lm[THUMB_TIP].y > lm[WRIST].y + 0.05:
                return "thumbs_down", 0.88

        # ── Fist ───────────────────────────────────────────────────────────
        if finger_count == 0:
            return "fist", 0.92

        # ── Open Palm (stop) ───────────────────────────────────────────────
        if finger_count == 5:
            # All fingers extended and spread
            spread = self._dist(lm[INDEX_TIP], lm[PINKY_TIP])
            if spread > 0.20:
                return "open_palm", 0.91
            return "stop", 0.85

        # ── Pointing (index only) ──────────────────────────────────────────
        if i and not m and not r and not p:
            return "pointing", 0.93

        # ── Victory / Peace ────────────────────────────────────────────────
        if i and m and not r and not p and not t:
            spread = self._dist(lm[INDEX_TIP], lm[MIDDLE_TIP])
            if spread > 0.05:
                return "victory", 0.90

        # ── OK Sign ────────────────────────────────────────────────────────
        if not i and not m and not r:
            thumb_index_dist = self._dist(lm[THUMB_TIP], lm[INDEX_TIP])
            if thumb_index_dist < 0.06:
                return "ok_sign", 0.88

        # ── Three / Count Three ────────────────────────────────────────────
        if i and m and r and not p and not t:
            return "three", 0.85

        # ── Four ───────────────────────────────────────────────────────────
        if i and m and r and p and not t:
            return "four", 0.85

        # ── Rock On (index + pinky) ────────────────────────────────────────
        if i and p and not m and not r:
            return "rock_on", 0.82

        # ── Call Me (thumb + pinky) ────────────────────────────────────────
        if t and p and not i and not m and not r:
            return "call_me", 0.82

        return "unknown", 0.50

    # ── Main detection ──────────────────────────────────────────────────────

    def detect(self, frame: np.ndarray) -> Dict:
        """Detect gestures in a BGR frame. Returns list of gesture results."""
        if not self.initialized:
            return {"gestures": [], "error": "MediaPipe not available", "count": 0}

        try:
            h, w = frame.shape[:2]
            # MediaPipe expects RGB
            rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            results = self.hands.process(rgb)

            gestures = []

            if results.multi_hand_landmarks and results.multi_handedness:
                for hand_lm, hand_info in zip(
                    results.multi_hand_landmarks,
                    results.multi_handedness
                ):
                    lm = hand_lm.landmark
                    handedness = hand_info.classification[0].label  # "Left" or "Right"
                    hand_confidence = hand_info.classification[0].score

                    gesture_name, gesture_conf = self._classify_gesture(lm, handedness)

                    # Compute bounding box from landmarks
                    xs = [l.x * w for l in lm]
                    ys = [l.y * h for l in lm]
                    pad = 20
                    bbox = {
                        "x1": max(0, int(min(xs)) - pad),
                        "y1": max(0, int(min(ys)) - pad),
                        "x2": min(w, int(max(xs)) + pad),
                        "y2": min(h, int(max(ys)) + pad),
                    }

                    # Flatten landmarks for frontend rendering
                    landmarks_2d = [
                        {"x": round(l.x, 4), "y": round(l.y, 4)}
                        for l in lm
                    ]

                    gestures.append({
                        "gesture": gesture_name,
                        "display_name": gesture_name.replace("_", " ").title(),
                        "confidence": round(float(gesture_conf * hand_confidence), 3),
                        "hand": handedness,
                        "bbox": bbox,
                        "landmarks": landmarks_2d,
                        "emoji": self._gesture_emoji(gesture_name),
                    })

            return {"gestures": gestures, "count": len(gestures)}

        except Exception as e:
            return {"gestures": [], "error": str(e), "count": 0}

    def detect_from_base64(self, image_b64: str) -> Dict:
        """Detect gestures from base64 image string."""
        try:
            if "," in image_b64:
                image_b64 = image_b64.split(",")[1]
            img_bytes = base64.b64decode(image_b64)
            img_array = np.frombuffer(img_bytes, dtype=np.uint8)
            frame = cv2.imdecode(img_array, cv2.IMREAD_COLOR)
            if frame is None:
                return {"gestures": [], "error": "Invalid image", "count": 0}
            return self.detect(frame)
        except Exception as e:
            return {"gestures": [], "error": str(e), "count": 0}

    @staticmethod
    def _gesture_emoji(gesture: str) -> str:
        EMOJIS = {
            "thumbs_up":   "👍",
            "thumbs_down": "👎",
            "open_palm":   "✋",
            "stop":        "🛑",
            "pointing":    "☝️",
            "victory":     "✌️",
            "fist":        "✊",
            "ok_sign":     "👌",
            "three":       "3️⃣",
            "four":        "4️⃣",
            "rock_on":     "🤘",
            "call_me":     "🤙",
            "waving":      "👋",
            "unknown":     "🤚",
        }
        return EMOJIS.get(gesture, "🤚")

    def close(self):
        if self.hands:
            self.hands.close()


# Singleton
_gesture_engine: Optional[GestureEngine] = None

def get_gesture_engine() -> GestureEngine:
    global _gesture_engine
    if _gesture_engine is None:
        _gesture_engine = GestureEngine()
    return _gesture_engine

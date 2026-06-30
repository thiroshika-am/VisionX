"""
Gesture Recognition Engine for VisionX
Uses MediaPipe Tasks API (0.10+) with HandLandmarker for 21-keypoint detection,
then classifies gestures with rule-based logic.

Alternatively uses GestureRecognizer (if model file available) for direct classification.
"""

import base64
import math
import os
import urllib.request
from typing import Dict, List, Optional, Tuple

import cv2
import numpy as np

# ── Model download URLs ───────────────────────────────────────────────────────
MODELS_DIR = os.path.join(os.path.dirname(__file__), "..", "config", "models")
os.makedirs(MODELS_DIR, exist_ok=True)

GESTURE_MODEL_PATH = os.path.join(MODELS_DIR, "gesture_recognizer.task")
HAND_MODEL_PATH    = os.path.join(MODELS_DIR, "hand_landmarker.task")

GESTURE_MODEL_URL = (
    "https://storage.googleapis.com/mediapipe-models/gesture_recognizer/"
    "gesture_recognizer/float16/latest/gesture_recognizer.task"
)
HAND_MODEL_URL = (
    "https://storage.googleapis.com/mediapipe-models/hand_landmarker/"
    "hand_landmarker/float16/latest/hand_landmarker.task"
)

MEDIAPIPE_AVAILABLE = False
try:
    import mediapipe as mp
    from mediapipe.tasks import python as mp_python
    from mediapipe.tasks.python import vision as mp_vision
    MEDIAPIPE_AVAILABLE = True
    print("[GestureEngine] MediaPipe Tasks API available")
except ImportError:
    print("[GestureEngine] mediapipe not installed. Run: pip install mediapipe")


# ── Landmark indices ─────────────────────────────────────────────────────────
WRIST      = 0
THUMB_CMC  = 1; THUMB_MCP  = 2; THUMB_IP   = 3; THUMB_TIP  = 4
INDEX_MCP  = 5; INDEX_PIP  = 6; INDEX_DIP  = 7; INDEX_TIP  = 8
MIDDLE_MCP = 9; MIDDLE_PIP = 10; MIDDLE_DIP = 11; MIDDLE_TIP = 12
RING_MCP   = 13; RING_PIP  = 14; RING_DIP   = 15; RING_TIP  = 16
PINKY_MCP  = 17; PINKY_PIP = 18; PINKY_DIP  = 19; PINKY_TIP = 20

# Built-in gesture label mapping from GestureRecognizer model
BUILTIN_GESTURE_EMOJIS = {
    "None":        "🤚",
    "Closed_Fist": "✊",
    "Open_Palm":   "✋",
    "Pointing_Up": "☝️",
    "Thumb_Down":  "👎",
    "Thumb_Up":    "👍",
    "Victory":     "✌️",
    "ILoveYou":    "🤟",
}

CUSTOM_EMOJIS = {
    "thumbs_up":   "👍",
    "thumbs_down": "👎",
    "open_palm":   "✋",
    "stop":        "🛑",
    "pointing":    "☝️",
    "victory":     "✌️",
    "fist":        "✊",
    "ok_sign":     "👌",
    "rock_on":     "🤘",
    "call_me":     "🤙",
    "unknown":     "🤚",
}


def _download_model(url: str, path: str, name: str) -> bool:
    if os.path.exists(path):
        return True
    try:
        print(f"[GestureEngine] Downloading {name}...")
        urllib.request.urlretrieve(url, path)
        print(f"[GestureEngine] {name} downloaded to {path}")
        return True
    except Exception as e:
        print(f"[GestureEngine] Download failed for {name}: {e}")
        return False


class GestureEngine:
    """MediaPipe Tasks API gesture recognition."""

    def __init__(self):
        self.gesture_recognizer = None
        self.hand_landmarker    = None
        self.mode = "none"
        self.initialized = False
        self._init()

    def _init(self):
        if not MEDIAPIPE_AVAILABLE:
            return

        # Try full GestureRecognizer first (best, classifies directly)
        if _download_model(GESTURE_MODEL_URL, GESTURE_MODEL_PATH, "GestureRecognizer"):
            try:
                base_options = mp_python.BaseOptions(model_asset_path=GESTURE_MODEL_PATH)
                options = mp_vision.GestureRecognizerOptions(
                    base_options=base_options,
                    running_mode=mp_vision.RunningMode.IMAGE,
                    num_hands=2,
                    min_hand_detection_confidence=0.55,
                    min_hand_presence_confidence=0.5,
                    min_tracking_confidence=0.5,
                )
                self.gesture_recognizer = mp_vision.GestureRecognizer.create_from_options(options)
                self.mode = "gesture_recognizer"
                self.initialized = True
                print("[GestureEngine] GestureRecognizer initialized")
                return
            except Exception as e:
                print(f"[GestureEngine] GestureRecognizer failed: {e}")

        # Fallback: HandLandmarker + rule-based classifier
        if _download_model(HAND_MODEL_URL, HAND_MODEL_PATH, "HandLandmarker"):
            try:
                base_options = mp_python.BaseOptions(model_asset_path=HAND_MODEL_PATH)
                options = mp_vision.HandLandmarkerOptions(
                    base_options=base_options,
                    running_mode=mp_vision.RunningMode.IMAGE,
                    num_hands=2,
                    min_hand_detection_confidence=0.55,
                    min_tracking_confidence=0.5,
                )
                self.hand_landmarker = mp_vision.HandLandmarker.create_from_options(options)
                self.mode = "hand_landmarker"
                self.initialized = True
                print("[GestureEngine] HandLandmarker initialized (rule-based classifier)")
                return
            except Exception as e:
                print(f"[GestureEngine] HandLandmarker failed: {e}")

        print("[GestureEngine] No model available — models will download on next start")

    # ── Rule-based helpers ────────────────────────────────────────────────────

    @staticmethod
    def _dist(a, b) -> float:
        return math.sqrt((a.x - b.x)**2 + (a.y - b.y)**2)

    def _finger_extended(self, lm, tip_idx, pip_idx, mcp_idx) -> bool:
        return lm[tip_idx].y < lm[pip_idx].y and lm[pip_idx].y < lm[mcp_idx].y

    def _thumb_extended(self, lm, handedness: str) -> bool:
        tip, mcp = lm[THUMB_TIP], lm[THUMB_MCP]
        return tip.x < mcp.x if handedness == "Right" else tip.x > mcp.x

    def _classify_landmarks(self, lm, handedness: str) -> Tuple[str, float]:
        t = self._thumb_extended(lm, handedness)
        i = self._finger_extended(lm, INDEX_TIP,  INDEX_PIP,  INDEX_MCP)
        m = self._finger_extended(lm, MIDDLE_TIP, MIDDLE_PIP, MIDDLE_MCP)
        r = self._finger_extended(lm, RING_TIP,   RING_PIP,   RING_MCP)
        p = self._finger_extended(lm, PINKY_TIP,  PINKY_PIP,  PINKY_MCP)

        count = sum([t, i, m, r, p])

        if count == 0:
            return "fist", 0.90
        if count == 5:
            spread = self._dist(lm[INDEX_TIP], lm[PINKY_TIP])
            return ("open_palm", 0.91) if spread > 0.15 else ("stop", 0.84)
        if t and not i and not m and not r and not p:
            return ("thumbs_up", 0.90) if lm[THUMB_TIP].y < lm[WRIST].y else ("thumbs_down", 0.88)
        if i and not m and not r and not p:
            return "pointing", 0.93
        if i and m and not r and not p:
            return "victory", 0.90
        if t and p and not i and not m and not r:
            return "call_me", 0.82
        if i and p and not m and not r:
            return "rock_on", 0.82
        if not i and not m and not r:
            if self._dist(lm[THUMB_TIP], lm[INDEX_TIP]) < 0.06:
                return "ok_sign", 0.86
        return "unknown", 0.50

    # ── Main detection ────────────────────────────────────────────────────────

    def detect(self, frame: np.ndarray) -> Dict:
        if not self.initialized:
            return {"gestures": [], "count": 0,
                    "note": "Models downloading, try again in a moment"}

        try:
            rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb)

            if self.mode == "gesture_recognizer":
                return self._detect_with_recognizer(mp_image, frame.shape)
            elif self.mode == "hand_landmarker":
                return self._detect_with_landmarker(mp_image, frame.shape)
        except Exception as e:
            return {"gestures": [], "error": str(e), "count": 0}

    def _detect_with_recognizer(self, mp_image, shape) -> Dict:
        result = self.gesture_recognizer.recognize(mp_image)
        h, w = shape[:2]
        gestures = []
        for i, (gesture_list, handedness_list, hand_lm) in enumerate(zip(
            result.gestures or [],
            result.handedness or [],
            result.hand_landmarks or []
        )):
            if not gesture_list:
                continue
            top_gesture  = gesture_list[0]
            handedness   = handedness_list[0].category_name if handedness_list else "Right"
            gesture_name = top_gesture.category_name
            confidence   = round(float(top_gesture.score), 3)

            # Map built-in labels to display names
            display_name = gesture_name.replace("_", " ").title()
            emoji        = BUILTIN_GESTURE_EMOJIS.get(gesture_name, "🤚")

            # Bounding box
            xs = [l.x * w for l in hand_lm]; ys = [l.y * h for l in hand_lm]
            pad = 20
            bbox = {"x1": max(0, int(min(xs)) - pad), "y1": max(0, int(min(ys)) - pad),
                    "x2": min(w, int(max(xs)) + pad), "y2": min(h, int(max(ys)) + pad)}

            landmarks_2d = [{"x": round(l.x, 4), "y": round(l.y, 4)} for l in hand_lm]

            gestures.append({
                "gesture": gesture_name,
                "display_name": display_name,
                "confidence": confidence,
                "hand": handedness,
                "bbox": bbox,
                "landmarks": landmarks_2d,
                "emoji": emoji,
            })
        return {"gestures": gestures, "count": len(gestures)}

    def _detect_with_landmarker(self, mp_image, shape) -> Dict:
        result = self.hand_landmarker.detect(mp_image)
        h, w = shape[:2]
        gestures = []
        for hand_lm, handedness_list in zip(
            result.hand_landmarks or [],
            result.handedness or []
        ):
            handedness = handedness_list[0].category_name if handedness_list else "Right"
            gesture_name, conf = self._classify_landmarks(hand_lm, handedness)

            xs = [l.x * w for l in hand_lm]; ys = [l.y * h for l in hand_lm]
            pad = 20
            bbox = {"x1": max(0, int(min(xs)) - pad), "y1": max(0, int(min(ys)) - pad),
                    "x2": min(w, int(max(xs)) + pad), "y2": min(h, int(max(ys)) + pad)}
            landmarks_2d = [{"x": round(l.x, 4), "y": round(l.y, 4)} for l in hand_lm]

            gestures.append({
                "gesture": gesture_name,
                "display_name": gesture_name.replace("_", " ").title(),
                "confidence": round(conf, 3),
                "hand": handedness,
                "bbox": bbox,
                "landmarks": landmarks_2d,
                "emoji": CUSTOM_EMOJIS.get(gesture_name, "🤚"),
            })
        return {"gestures": gestures, "count": len(gestures)}

    def detect_from_base64(self, image_b64: str) -> Dict:
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

    def close(self):
        if self.gesture_recognizer:
            self.gesture_recognizer.close()
        if self.hand_landmarker:
            self.hand_landmarker.close()


# Singleton
_gesture_engine: Optional[GestureEngine] = None

def get_gesture_engine() -> GestureEngine:
    global _gesture_engine
    if _gesture_engine is None:
        _gesture_engine = GestureEngine()
    return _gesture_engine

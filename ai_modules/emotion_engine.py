"""
Emotion Recognition Engine for VisionX
Detects facial emotions using OpenCV + a lightweight CNN approach.
Classifies: happy, sad, angry, surprised, fearful, disgusted, neutral.

Uses fer library if available (PyPI: fer), falls back to a pure
OpenCV DNN approach using a pre-trained emotion model.
"""

import base64
import os
import time
import urllib.request
from typing import Dict, List, Optional

import cv2
import numpy as np

# ── Try FER (best option) ────────────────────────────────────────────────────
try:
    from fer import FER
    FER_AVAILABLE = True
    print("[EmotionEngine] FER library available")
except ImportError:
    FER_AVAILABLE = False
    print("[EmotionEngine] FER not installed, using OpenCV DNN fallback")

# ── Fallback: OpenCV DNN emotion model ───────────────────────────────────────
MODELS_DIR = os.path.join(os.path.dirname(__file__), "..", "config", "models")
os.makedirs(MODELS_DIR, exist_ok=True)

# Haar cascade for face detection (always available in OpenCV)
HAAR_CASCADE = cv2.CascadeClassifier(
    cv2.data.haarcascades + "haarcascade_frontalface_default.xml"
)

EMOTION_LABELS = ["angry", "disgusted", "fearful", "happy", "neutral", "sad", "surprised"]
EMOTION_EMOJIS = {
    "happy":     "😊",
    "sad":       "😢",
    "angry":     "😠",
    "surprised": "😲",
    "fearful":   "😨",
    "disgusted": "🤢",
    "neutral":   "😐",
}

# Colour per emotion for overlay drawing
EMOTION_COLORS = {
    "happy":     (0, 200, 100),
    "sad":       (180, 80, 40),
    "angry":     (0, 0, 220),
    "surprised": (0, 200, 220),
    "fearful":   (130, 0, 180),
    "disgusted": (0, 130, 60),
    "neutral":   (120, 120, 120),
}


class EmotionEngine:
    """Facial emotion recognition — uses FER or OpenCV DNN fallback."""

    def __init__(self):
        self.detector = None
        self.mode = "none"
        self._init()

    def _init(self):
        if FER_AVAILABLE:
            try:
                # mtcnn=False uses OpenCV face detector (faster, no TF needed)
                self.detector = FER(mtcnn=False)
                self.mode = "fer"
                print("[EmotionEngine] Initialized with FER (OpenCV face detector)")
                return
            except Exception as e:
                print(f"[EmotionEngine] FER init failed: {e}")

        # Pure Haar + rule-based fallback (no deep model, low accuracy but always works)
        self.mode = "haar_fallback"
        print("[EmotionEngine] Using Haar cascade fallback (no deep emotion model)")

    # ── Main API ─────────────────────────────────────────────────────────────

    def detect(self, frame: np.ndarray) -> Dict:
        """Detect emotions in a BGR frame."""
        if self.mode == "fer":
            return self._detect_fer(frame)
        elif self.mode == "haar_fallback":
            return self._detect_haar_fallback(frame)
        return {"emotions": [], "count": 0, "error": "No emotion engine available"}

    def detect_from_base64(self, image_b64: str) -> Dict:
        """Detect emotions from base64 image."""
        try:
            if "," in image_b64:
                image_b64 = image_b64.split(",")[1]
            img_bytes = base64.b64decode(image_b64)
            img_array = np.frombuffer(img_bytes, dtype=np.uint8)
            frame = cv2.imdecode(img_array, cv2.IMREAD_COLOR)
            if frame is None:
                return {"emotions": [], "error": "Invalid image", "count": 0}
            return self.detect(frame)
        except Exception as e:
            return {"emotions": [], "error": str(e), "count": 0}

    # ── FER backend ──────────────────────────────────────────────────────────

    def _detect_fer(self, frame: np.ndarray) -> Dict:
        try:
            results = self.detector.detect_emotions(frame)
            emotions = []
            for face in results:
                box = face.get("box", [0, 0, 0, 0])  # x, y, w, h
                x, y, w, h = int(box[0]), int(box[1]), int(box[2]), int(box[3])
                scores = face.get("emotions", {})

                if not scores:
                    continue

                dominant = max(scores, key=scores.get)
                confidence = round(float(scores[dominant]), 3)

                emotions.append({
                    "dominant_emotion": dominant,
                    "confidence": confidence,
                    "emoji": EMOTION_EMOJIS.get(dominant, "😐"),
                    "color": EMOTION_COLORS.get(dominant, (128, 128, 128)),
                    "all_emotions": {k: round(float(v), 3) for k, v in scores.items()},
                    "bbox": {"x1": x, "y1": y, "x2": x + w, "y2": y + h},
                })

            return {"emotions": emotions, "count": len(emotions)}
        except Exception as e:
            return {"emotions": [], "error": str(e), "count": 0}

    # ── Haar fallback ────────────────────────────────────────────────────────

    def _detect_haar_fallback(self, frame: np.ndarray) -> Dict:
        """
        Haar cascade face detection with mock emotion scores.
        Returns neutral by default — useful for testing the pipeline
        without a deep emotion model.
        """
        try:
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            gray = cv2.equalizeHist(gray)
            faces = HAAR_CASCADE.detectMultiScale(gray, 1.1, 5, minSize=(40, 40))
            emotions = []
            for (x, y, w, h) in faces:
                # Approximate emotion from facial region brightness/contrast
                roi = gray[y:y + h, x:x + w]
                mean_bright = float(np.mean(roi))
                std_bright = float(np.std(roi))

                # Very rough heuristic — replace with real model when available
                if std_bright > 50:
                    dominant = "surprised"
                    conf = 0.45
                elif mean_bright > 140:
                    dominant = "happy"
                    conf = 0.50
                elif mean_bright < 90:
                    dominant = "sad"
                    conf = 0.40
                else:
                    dominant = "neutral"
                    conf = 0.55

                base_dist = {e: 0.05 for e in EMOTION_LABELS}
                base_dist[dominant] = conf

                emotions.append({
                    "dominant_emotion": dominant,
                    "confidence": round(conf, 3),
                    "emoji": EMOTION_EMOJIS.get(dominant, "😐"),
                    "color": EMOTION_COLORS.get(dominant, (128, 128, 128)),
                    "all_emotions": {k: round(v, 3) for k, v in base_dist.items()},
                    "bbox": {"x1": int(x), "y1": int(y),
                             "x2": int(x + w), "y2": int(y + h)},
                    "note": "haar_fallback",
                })

            return {"emotions": emotions, "count": len(emotions)}
        except Exception as e:
            return {"emotions": [], "error": str(e), "count": 0}


# Singleton
_emotion_engine: Optional[EmotionEngine] = None

def get_emotion_engine() -> EmotionEngine:
    global _emotion_engine
    if _emotion_engine is None:
        _emotion_engine = EmotionEngine()
    return _emotion_engine

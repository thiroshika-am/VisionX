"""
Face Recognition Engine for SmartCap AI
Detects and recognizes known people from camera frames.
Uses OpenCV DNN SFace embeddings for accurate recognition.
"""

import os
import cv2
import numpy as np
import base64
import json
import time
import urllib.request
from typing import Dict, List, Optional

# ============================================
# PATHS
# ============================================

BASE_DIR = os.path.join(os.path.dirname(__file__), "..")
KNOWN_FACES_DIR = os.path.join(BASE_DIR, "config", "known_faces")
KNOWN_FACES_DB = os.path.join(BASE_DIR, "config", "known_faces.json")
MODELS_DIR = os.path.join(BASE_DIR, "config", "models")

# Ensure directories exist
os.makedirs(KNOWN_FACES_DIR, exist_ok=True)
os.makedirs(MODELS_DIR, exist_ok=True)

# ============================================
# MODEL URLS
# ============================================
YUNET_URL = "https://github.com/opencv/opencv_zoo/raw/main/models/face_detection_yunet/face_detection_yunet_2023mar.onnx"
SFACE_URL = "https://github.com/opencv/opencv_zoo/raw/main/models/face_recognition_sface/face_recognition_sface_2021dec.onnx"

YUNET_PATH = os.path.join(MODELS_DIR, "face_detection_yunet_2023mar.onnx")
SFACE_PATH = os.path.join(MODELS_DIR, "face_recognition_sface_2021dec.onnx")

# Fallback Haar cascade for when DNN models aren't available
HAAR_CASCADE = cv2.CascadeClassifier(cv2.data.haarcascades + "haarcascade_frontalface_default.xml")

import threading
_face_engine = None
_face_engine_lock = threading.Lock()

def get_face_engine():
    global _face_engine
    if _face_engine is None:
        with _face_engine_lock:
            if _face_engine is None:
                _face_engine = FaceRecognitionEngine()
    return _face_engine


def _download_model(url, path):
    """Download a model file if not already present."""
    if os.path.exists(path):
        return True
    try:
        print(f"[FaceEngine] Downloading model: {os.path.basename(path)}...")
        urllib.request.urlretrieve(url, path)
        print(f"[FaceEngine] Downloaded: {os.path.basename(path)} ({os.path.getsize(path)} bytes)")
        return True
    except Exception as e:
        print(f"[FaceEngine] Failed to download {os.path.basename(path)}: {e}")
        return False


class FaceRecognitionEngine:
    """Face detection and recognition engine using DNN embeddings."""

    def __init__(self):
        self.known_people = {}        # id -> {name, photo, added}
        self.known_embeddings = {}    # person_id -> list of embedding vectors
        self.last_recognized = {}     # person_id -> timestamp (cooldown)
        self.cooldown = 10            # seconds between re-announcing same person

        # Similarity threshold (cosine): higher = stricter match
        # SFace cosine similarity: 1.0 = identical, 0.0 = totally different
        self.match_threshold = 0.45   # Raised from 0.363 to reduce false positives
        self.margin = 0.05            # Best must be this much better than 2nd best

        self.detector = None
        self.recognizer = None
        self.use_dnn = False

        # Try to load DNN models
        self._init_dnn_models()

        # Load database & compute embeddings
        self._load_db()
        self._compute_all_embeddings()

        print(f"[FaceEngine] Initialized with {len(self.known_people)} known people (DNN={self.use_dnn})")

    def _init_dnn_models(self):
        """Initialize YuNet detector and SFace recognizer."""
        yunet_ok = _download_model(YUNET_URL, YUNET_PATH)
        sface_ok = _download_model(SFACE_URL, SFACE_PATH)

        if yunet_ok and sface_ok:
            try:
                self.detector = cv2.FaceDetectorYN.create(
                    YUNET_PATH, "", (320, 320),
                    score_threshold=0.6,
                    nms_threshold=0.3,
                    top_k=10
                )
                self.recognizer = cv2.FaceRecognizerSF.create(SFACE_PATH, "")
                self.use_dnn = True
                print("[FaceEngine] DNN models loaded (YuNet + SFace)")
            except Exception as e:
                print(f"[FaceEngine] DNN init failed: {e}, falling back to Haar")
                self.use_dnn = False
        else:
            print("[FaceEngine] DNN models unavailable, falling back to Haar+LBPH")

    # ============================================
    # DATABASE
    # ============================================

    def _load_db(self):
        """Load known faces database."""
        if os.path.exists(KNOWN_FACES_DB):
            try:
                with open(KNOWN_FACES_DB, "r") as f:
                    self.known_people = json.load(f)
                print(f"[FaceEngine] Loaded {len(self.known_people)} people from DB")
            except Exception as e:
                print(f"[FaceEngine] Error loading DB: {e}")
                self.known_people = {}
        else:
            self.known_people = {}

    def _save_db(self):
        """Save known faces database."""
        try:
            with open(KNOWN_FACES_DB, "w") as f:
                json.dump(self.known_people, f, indent=2)
        except Exception as e:
            print(f"[FaceEngine] Error saving DB: {e}")

    # ============================================
    # EMBEDDING COMPUTATION
    # ============================================

    def _extract_embedding(self, img):
        """Extract face embedding(s) from an image.
        Returns list of (embedding, bbox) tuples.
        """
        if not self.use_dnn or self.recognizer is None:
            return []

        h, w = img.shape[:2]
        self.detector.setInputSize((w, h))
        _, faces_detected = self.detector.detect(img)

        if faces_detected is None or len(faces_detected) == 0:
            return []

        results = []
        for face in faces_detected:
            aligned = self.recognizer.alignCrop(img, face)
            embedding = self.recognizer.feature(aligned)
            bbox = face[:4].astype(int).tolist()
            results.append((embedding.flatten(), bbox))

        return results

    def _compute_all_embeddings(self):
        """Compute embeddings for all known people."""
        self.known_embeddings = {}

        if not self.use_dnn:
            print("[FaceEngine] Skipping embedding computation (DNN not available)")
            return

        for person_id, person in self.known_people.items():
            photo_path = os.path.join(KNOWN_FACES_DIR, person.get("photo", ""))
            if not os.path.exists(photo_path):
                print(f"[FaceEngine] Photo not found for {person['name']}: {photo_path}")
                continue

            img = cv2.imread(photo_path)
            if img is None:
                print(f"[FaceEngine] Cannot read photo for {person['name']}")
                continue

            embeddings = self._extract_embedding(img)
            if embeddings:
                # Store all face embeddings found in the photo (usually just 1)
                self.known_embeddings[person_id] = [emb for emb, _ in embeddings]
                print(f"[FaceEngine] Computed {len(embeddings)} embedding(s) for {person['name']}")
            else:
                # Fallback: try with Haar cascade + resize, then feed through SFace
                gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
                detected = HAAR_CASCADE.detectMultiScale(gray, 1.1, 4, minSize=(30, 30))
                if len(detected) > 0:
                    x, y, w, h = detected[0]
                    pad = int(0.2 * w)
                    x1, y1 = max(0, x - pad), max(0, y - pad)
                    x2 = min(img.shape[1], x + w + pad)
                    y2 = min(img.shape[0], y + h + pad)
                    face_crop = img[y1:y2, x1:x2]
                    # Try embedding on crop
                    emb_list = self._extract_embedding(face_crop)
                    if emb_list:
                        self.known_embeddings[person_id] = [emb for emb, _ in emb_list]
                        print(f"[FaceEngine] Computed embedding for {person['name']} (via Haar fallback)")
                    else:
                        print(f"[FaceEngine] WARNING: No face found in photo for {person['name']}")
                else:
                    print(f"[FaceEngine] WARNING: No face found in photo for {person['name']}")

        print(f"[FaceEngine] Embeddings computed for {len(self.known_embeddings)}/{len(self.known_people)} people")

    def _match_embedding(self, embedding):
        """Match an embedding against all known people.
        Uses margin-based matching: best score must exceed threshold AND
        be significantly better than second-best to avoid confusion.
        Returns (person_id, name, similarity) or (None, None, 0).
        """
        scores = []

        for person_id, embeddings in self.known_embeddings.items():
            best_person_score = -1
            for known_emb in embeddings:
                score = self.recognizer.match(
                    embedding.reshape(1, -1),
                    known_emb.reshape(1, -1),
                    cv2.FaceRecognizerSF_FR_COSINE
                )
                if score > best_person_score:
                    best_person_score = score
            scores.append((best_person_score, person_id))

        if not scores:
            return None, None, 0

        # Sort descending by score
        scores.sort(key=lambda x: x[0], reverse=True)
        best_score, best_id = scores[0]
        second_score = scores[1][0] if len(scores) > 1 else -1

        # Must exceed threshold
        if best_score < self.match_threshold:
            return None, None, 0

        # Must have sufficient margin over second best
        if len(scores) > 1 and (best_score - second_score) < self.margin:
            print(f"[FaceEngine] Ambiguous match: best={best_score:.3f}, 2nd={second_score:.3f}, margin={best_score - second_score:.3f} < {self.margin}")
            return None, None, 0

        best_name = self.known_people.get(best_id, {}).get("name", "?")
        return best_id, best_name, best_score

    # ============================================
    # ADD / REMOVE / LIST PEOPLE
    # ============================================

    def add_person(self, name: str, photo_b64: str) -> Dict:
        """Add a new known person with their photo."""
        try:
            person_id = f"person_{int(time.time() * 1000)}"

            if "," in photo_b64:
                photo_b64 = photo_b64.split(",")[1]

            img_bytes = base64.b64decode(photo_b64)
            img_array = np.frombuffer(img_bytes, dtype=np.uint8)
            img = cv2.imdecode(img_array, cv2.IMREAD_COLOR)

            if img is None:
                return {"success": False, "error": "Invalid image"}

            # Save photo
            photo_filename = f"{person_id}.jpg"
            photo_path = os.path.join(KNOWN_FACES_DIR, photo_filename)
            cv2.imwrite(photo_path, img)

            # Add to database
            self.known_people[person_id] = {
                "name": name,
                "photo": photo_filename,
                "added": time.strftime("%Y-%m-%d %H:%M:%S"),
            }
            self._save_db()

            # Compute embedding for new person
            embeddings = self._extract_embedding(img)
            if embeddings:
                self.known_embeddings[person_id] = [emb for emb, _ in embeddings]
                print(f"[FaceEngine] Added {name} with {len(embeddings)} embedding(s)")
            else:
                print(f"[FaceEngine] WARNING: No face detected in photo for {name}")

            return {"success": True, "person_id": person_id, "name": name}

        except Exception as e:
            return {"success": False, "error": str(e)}

    def remove_person(self, person_id: str) -> Dict:
        """Remove a known person."""
        if person_id not in self.known_people:
            return {"success": False, "error": "Person not found"}

        person = self.known_people[person_id]
        photo_path = os.path.join(KNOWN_FACES_DIR, person.get("photo", ""))
        if os.path.exists(photo_path):
            os.remove(photo_path)

        del self.known_people[person_id]
        self.known_embeddings.pop(person_id, None)
        self._save_db()

        return {"success": True, "removed": person_id}

    def list_people(self) -> List[Dict]:
        """List all known people."""
        result = []
        for pid, person in self.known_people.items():
            result.append({
                "id": pid,
                "name": person["name"],
                "photo": person.get("photo", ""),
                "added": person.get("added", ""),
            })
        return result

    # ============================================
    # FACE DETECTION & RECOGNITION
    # ============================================

    def detect_from_base64(self, image_b64: str) -> Dict:
        """Detect and recognize faces in a base64 image."""
        try:
            if "," in image_b64:
                image_b64 = image_b64.split(",")[1]

            img_bytes = base64.b64decode(image_b64)
            img_array = np.frombuffer(img_bytes, dtype=np.uint8)
            frame = cv2.imdecode(img_array, cv2.IMREAD_COLOR)

            if frame is None:
                return {"faces": [], "error": "Failed to decode image"}

            return self.detect(frame)

        except Exception as e:
            return {"faces": [], "error": str(e)}

    def detect(self, frame: np.ndarray) -> Dict:
        """Detect and recognize faces in frame."""
        try:
            if not self.use_dnn:
                return self._detect_haar_fallback(frame)

            h, w = frame.shape[:2]
            self.detector.setInputSize((w, h))
            _, faces_detected = self.detector.detect(frame)

            faces = []
            now = time.time()

            if faces_detected is None:
                return {"faces": [], "count": 0}

            for face in faces_detected:
                bbox = face[:4].astype(int)
                face_info = {
                    "bbox": {"x": int(bbox[0]), "y": int(bbox[1]),
                             "w": int(bbox[2]), "h": int(bbox[3])},
                    "name": None,
                    "person_id": None,
                    "confidence": 0,
                    "is_known": False,
                    "should_announce": False,
                }

                # Get embedding for this face
                try:
                    aligned = self.recognizer.alignCrop(frame, face)
                    embedding = self.recognizer.feature(aligned).flatten()

                    # Match against known people
                    person_id, name, score = self._match_embedding(embedding)

                    if person_id:
                        face_info["name"] = name
                        face_info["person_id"] = person_id
                        face_info["confidence"] = round(float(score), 2)
                        face_info["is_known"] = True
                        print(f"[FaceEngine] ✓ Matched: {name} (cosine={score:.3f})")

                        # Cooldown check
                        last_time = self.last_recognized.get(person_id, 0)
                        if now - last_time >= self.cooldown:
                            face_info["should_announce"] = True
                            self.last_recognized[person_id] = now
                    else:
                        print(f"[FaceEngine] Unknown face (best cosine={score:.3f})")

                except Exception as e:
                    print(f"[FaceEngine] Embedding error: {e}")

                faces.append(face_info)

            return {"faces": faces, "count": len(faces)}

        except Exception as e:
            print(f"[FaceEngine] Detection error: {e}")
            return {"faces": [], "error": str(e)}

    def _detect_haar_fallback(self, frame):
        """Fallback detection using Haar cascade (no recognition)."""
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        gray = cv2.equalizeHist(gray)
        detected = HAAR_CASCADE.detectMultiScale(gray, 1.1, 4, minSize=(40, 40))
        faces = []
        for (x, y, w, h) in detected:
            faces.append({
                "bbox": {"x": int(x), "y": int(y), "w": int(w), "h": int(h)},
                "name": None, "person_id": None,
                "confidence": 0, "is_known": False, "should_announce": False,
            })
        return {"faces": faces, "count": len(faces)}

    def get_photo_path(self, person_id: str) -> Optional[str]:
        """Get the photo file path for a person."""
        person = self.known_people.get(person_id)
        if not person:
            return None
        path = os.path.join(KNOWN_FACES_DIR, person.get("photo", ""))
        return path if os.path.exists(path) else None

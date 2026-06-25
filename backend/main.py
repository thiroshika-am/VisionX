"""
==========================================
SMART AI CAP — Backend Server
Serves the frontend, proxies ESP32-CAM stream, and handles GPS data
==========================================
"""

import os
import json
import time
import logging
import threading
import hashlib
import secrets
from datetime import datetime, timezone
from flask import Flask, Response, jsonify, send_from_directory, request, abort
from flask_cors import CORS
import requests

# Import AI detector
import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from ai_modules.detector import get_detector
from ai_modules.llm_alerts import get_alert_generator
from ai_modules.ocr_engine import get_ocr_reader
from ai_modules.face_recognition_engine import get_face_engine
from ai_modules.gesture_engine import get_gesture_engine
from ai_modules.emotion_engine import get_emotion_engine
from ai_modules.pose_engine import get_pose_engine

# ============================================
# CONFIGURATION
# ============================================

CONFIG_PATH = os.path.join(os.path.dirname(__file__), "..", "config", "backend_config.json")

with open(CONFIG_PATH, "r") as f:
    config = json.load(f)

ESP32_STREAM_URL = config.get("esp32", {}).get("stream_url", "http://192.168.1.100:80/stream")
ESP32_STATUS_URL = config.get("esp32", {}).get("status_url", "http://192.168.1.100:80/status")
ESP32_DISTANCE_URL = config.get("esp32", {}).get("distance_url", "http://192.168.1.100:80/distance")
BACKEND_PORT = config.get("network", {}).get("backend_port", 5000)

# ============================================
# LOGGING
# ============================================

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler()],
)
logger = logging.getLogger("smartcap")

# ============================================
# IN-MEMORY STATE
# ============================================

# Latest GPS data received from ESP32
gps_data = {
    "latitude": 12.9716,    # Default: Bangalore, India (placeholder)
    "longitude": 77.5946,
    "accuracy": 0,
    "speed": 0,
    "altitude": 0,
    "timestamp": datetime.now(timezone.utc).isoformat(),
    "source": "placeholder",
}

# Device status
device_status = {
    "online": False,
    "last_seen": None,
    "battery": None,
    "wifi_rssi": None,
    "distance_mm": None,
    "alert_level": "SAFE",
    "uptime": 0,
}

gps_lock = threading.Lock()
status_lock = threading.Lock()

# ============================================
# FLASK APP
# ============================================

FRONTEND_DIR = os.path.join(os.path.dirname(__file__), "..", "frontend")

app = Flask(__name__, static_folder=FRONTEND_DIR)
CORS(app)


# --- Serve Frontend ---

@app.route("/")
def serve_index():
    return send_from_directory(FRONTEND_DIR, "index.html")


@app.route("/<path:path>")
def serve_static(path):
    # Don't serve /api/* as static files — let Flask handle those routes
    if path.startswith("api/"):
        abort(404)
    return send_from_directory(FRONTEND_DIR, path)


# --- API: Camera Stream Proxy ---

@app.route("/api/stream")
def stream_proxy():
    """
    Proxies the ESP32-CAM MJPEG stream to the frontend.
    The ESP32 serves an MJPEG stream at /stream.
    """
    def generate():
        try:
            resp = requests.get(ESP32_STREAM_URL, stream=True, timeout=(3, 10))
            for chunk in resp.iter_content(chunk_size=4096):
                yield chunk
        except requests.exceptions.RequestException as e:
            logger.warning(f"ESP32 stream unavailable: {e}")
            return

    return Response(generate(), mimetype="multipart/x-mixed-replace; boundary=frame")


# --- API: GPS Data ---

@app.route("/api/gps", methods=["GET"])
def get_gps():
    """Return latest GPS coordinates."""
    with gps_lock:
        return jsonify(gps_data)


@app.route("/api/gps", methods=["POST"])
def update_gps():
    """
    ESP32 posts GPS data here.
    Expected JSON: { "latitude": float, "longitude": float, "accuracy": float, ... }
    """
    data = request.get_json(force=True)
    with gps_lock:
        gps_data["latitude"] = data.get("latitude", gps_data["latitude"])
        gps_data["longitude"] = data.get("longitude", gps_data["longitude"])
        gps_data["accuracy"] = data.get("accuracy", 0)
        gps_data["speed"] = data.get("speed", 0)
        gps_data["altitude"] = data.get("altitude", 0)
        gps_data["timestamp"] = datetime.now(timezone.utc).isoformat()
        gps_data["source"] = "esp32"
    logger.info(f"GPS updated: {gps_data['latitude']}, {gps_data['longitude']}")
    return jsonify({"status": "ok"})


# --- API: Device Status ---

@app.route("/api/status", methods=["GET"])
def get_status():
    """Return device status."""
    with status_lock:
        return jsonify(device_status)


@app.route("/api/status", methods=["POST"])
def update_status():
    """
    ESP32 posts heartbeat/status here.
    Expected JSON: { "battery": int, "wifi_rssi": int, "distance_mm": int, "alert_level": str, "uptime": int }
    """
    data = request.get_json(force=True)
    with status_lock:
        device_status["online"] = True
        device_status["last_seen"] = datetime.now(timezone.utc).isoformat()
        device_status["battery"] = data.get("battery")
        device_status["wifi_rssi"] = data.get("wifi_rssi")
        device_status["distance_mm"] = data.get("distance_mm")
        device_status["alert_level"] = data.get("alert_level", "SAFE")
        device_status["uptime"] = data.get("uptime", 0)
    return jsonify({"status": "ok"})


# --- API: Distance (proxy to ESP32) ---

@app.route("/api/distance")
def get_distance():
    """Proxy distance request to ESP32."""
    try:
        resp = requests.get(ESP32_DISTANCE_URL, timeout=3)
        return jsonify(resp.json())
    except Exception:
        return jsonify({"distance_mm": None, "error": "ESP32 unreachable"})


# ============================================
# AUTHENTICATION
# ============================================

USERS_PATH = os.path.join(os.path.dirname(__file__), "..", "config", "users.json")

def load_users():
    """Load users from JSON file."""
    try:
        with open(USERS_PATH, "r") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {"users": {}}

def save_users(data):
    """Save users to JSON file."""
    with open(USERS_PATH, "w") as f:
        json.dump(data, f, indent=2)

def hash_password(password, salt=None):
    """Hash password with salt."""
    if salt is None:
        salt = secrets.token_hex(16)
    hashed = hashlib.sha256((salt + password).encode()).hexdigest()
    return f"{salt}${hashed}"

def verify_password(password, stored_hash):
    """Verify password against stored hash."""
    if '$' not in stored_hash:
        return False
    salt, _ = stored_hash.split('$', 1)
    return hash_password(password, salt) == stored_hash


@app.route("/api/login", methods=["POST"])
def login():
    """Authenticate user and return token."""
    try:
        data = request.get_json(force=True)
        username = data.get("username", "").strip()
        password = data.get("password", "")

        if not username or not password:
            return jsonify({"success": False, "message": "Username and password required"}), 400

        users_data = load_users()
        user = users_data.get("users", {}).get(username)

        if not user:
            return jsonify({"success": False, "message": "Invalid username or password"}), 401

        if not verify_password(password, user.get("password_hash", "")):
            return jsonify({"success": False, "message": "Invalid username or password"}), 401

        # Generate session token
        token = secrets.token_hex(32)

        # Update last login
        users_data["users"][username]["last_login"] = datetime.now(timezone.utc).isoformat()
        save_users(users_data)

        logger.info(f"User '{username}' logged in successfully")
        return jsonify({"success": True, "token": token, "username": username})

    except Exception as e:
        logger.error(f"Login error: {e}")
        return jsonify({"success": False, "message": "Server error"}), 500


@app.route("/api/register", methods=["POST"])
def register():
    """Register a new user."""
    try:
        data = request.get_json(force=True)
        username = data.get("username", "").strip()
        password = data.get("password", "")
        email = data.get("email", "").strip()

        if not username or not password:
            return jsonify({"success": False, "message": "Username and password required"}), 400

        if len(username) < 3:
            return jsonify({"success": False, "message": "Username must be at least 3 characters"}), 400

        if len(password) < 4:
            return jsonify({"success": False, "message": "Password must be at least 4 characters"}), 400

        users_data = load_users()

        if username in users_data.get("users", {}):
            return jsonify({"success": False, "message": "Username already exists"}), 409

        # Create user
        password_hash = hash_password(password)
        users_data.setdefault("users", {})[username] = {
            "password_hash": password_hash,
            "email": email,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "last_login": datetime.now(timezone.utc).isoformat()
        }
        save_users(users_data)

        token = secrets.token_hex(32)
        logger.info(f"New user registered: '{username}'")
        return jsonify({"success": True, "token": token, "username": username})

    except Exception as e:
        logger.error(f"Register error: {e}")
        return jsonify({"success": False, "message": "Server error"}), 500


@app.route("/api/verify-token", methods=["POST"])
def verify_token():
    """Simple token verification (always valid for now)."""
    data = request.get_json(force=True)
    token = data.get("token", "")
    if token:
        return jsonify({"valid": True})
    return jsonify({"valid": False}), 401


# --- Health Check ---

@app.route("/api/health")
def health():
    return jsonify({"status": "ok", "time": datetime.now(timezone.utc).isoformat()})


# --- API: Object Detection ---

@app.route("/api/detect", methods=["POST"])
def detect_objects():
    """
    Run YOLOv5 object detection on a frame.
    Expected JSON: { "image": "base64_encoded_image" }
    Returns: { "detections": [...], "alert_level": str, "annotated_frame": base64 }
    """
    try:
        logger.info("Detection request received")
        data = request.get_json(force=True)
        image_b64 = data.get("image")
        
        if not image_b64:
            logger.warning("No image data in request")
            return jsonify({"error": "No image provided", "detections": [], "count": 0}), 400
        
        logger.info(f"Image data received, length: {len(image_b64)}")
        logger.info("Loading detector...")
        detector = get_detector()
        logger.info("Detector loaded, running detection...")
        result = detector.detect_from_base64(image_b64)
        logger.info(f"Detection complete: {result['count']} objects found")
        
        return jsonify(result)
        
    except Exception as e:
        logger.error(f"Detection error: {e}", exc_info=True)
        return jsonify({"error": str(e), "detections": [], "count": 0}), 500


# --- API: Generate Smart Alert (LLM) ---

@app.route("/api/generate-alert", methods=["POST"])
def generate_smart_alert():
    """
    Generate a natural language alert using LLM.
    Expected JSON: { "detections": [...], "location": "optional location name" }
    Returns: { "alert": "natural language alert text" }
    """
    try:
        data = request.get_json(force=True)
        detections = data.get("detections", [])
        location = data.get("location")
        
        if not detections:
            return jsonify({"alert": None})
        
        generator = get_alert_generator()
        alert_text = generator.generate_alert(detections, location)
        
        return jsonify({"alert": alert_text})
        
    except Exception as e:
        logger.error(f"Alert generation error: {e}")
        return jsonify({"alert": None, "error": str(e)}), 500


# --- API: OCR Text Detection ---

@app.route("/api/ocr", methods=["POST"])
def detect_text():
    """
    Detect text in an image using OCR.
    Expected JSON: { "image": "base64_encoded_image" }
    Returns: { "texts": [...], "combined_text": str, "count": int }
    """
    try:
        data = request.get_json(force=True)
        image_b64 = data.get("image")
        
        if not image_b64:
            return jsonify({"error": "No image provided", "texts": []}), 400
        
        logger.info("OCR request received")
        ocr = get_ocr_reader()
        result = ocr.detect_from_base64(image_b64)
        
        # Log what was found
        if result.get("error"):
            logger.warning(f"OCR error: {result['error']}")
        elif result.get("combined_text"):
            logger.info(f"OCR detected text: '{result['combined_text'][:80]}' (count: {result.get('count', 0)})")
        else:
            logger.debug("OCR: No text found in image")
        
        return jsonify(result)
        
    except Exception as e:
        logger.error(f"OCR error: {e}", exc_info=True)
        return jsonify({"error": str(e), "texts": []}), 500


# ============================================
# BACKGROUND: Device Online Checker
# ============================================


# --- API: Face Recognition ---

@app.route("/api/faces", methods=["GET"])
def list_faces():
    """List all known people."""
    try:
        engine = get_face_engine()
        people = engine.list_people()
        return jsonify({"people": people, "count": len(people)})
    except Exception as e:
        logger.error(f"Face list error: {e}")
        return jsonify({"error": str(e), "people": []}), 500


@app.route("/api/faces", methods=["POST"])
def add_face():
    """Add a new known person.
    Expected JSON: { "name": "Person Name", "photo": "base64_image" }
    """
    try:
        data = request.get_json(force=True)
        name = data.get("name", "").strip()
        photo = data.get("photo", "")

        if not name:
            return jsonify({"error": "Name is required"}), 400
        if not photo:
            return jsonify({"error": "Photo is required"}), 400

        engine = get_face_engine()
        result = engine.add_person(name, photo)

        if result["success"]:
            logger.info(f"Added person: {name} (ID: {result['person_id']})")
            return jsonify(result)
        else:
            return jsonify(result), 400

    except Exception as e:
        logger.error(f"Face add error: {e}", exc_info=True)
        return jsonify({"error": str(e)}), 500


@app.route("/api/faces/<person_id>", methods=["DELETE"])
def remove_face(person_id):
    """Remove a known person."""
    try:
        engine = get_face_engine()
        result = engine.remove_person(person_id)
        if result["success"]:
            logger.info(f"Removed person: {person_id}")
            return jsonify(result)
        else:
            return jsonify(result), 404
    except Exception as e:
        logger.error(f"Face remove error: {e}")
        return jsonify({"error": str(e)}), 500


@app.route("/api/faces/photo/<person_id>")
def get_face_photo(person_id):
    """Get the photo of a known person."""
    try:
        engine = get_face_engine()
        photo_path = engine.get_photo_path(person_id)
        if photo_path:
            directory = os.path.dirname(photo_path)
            filename = os.path.basename(photo_path)
            return send_from_directory(directory, filename)
        return jsonify({"error": "Photo not found"}), 404
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/face-detect", methods=["POST"])
def detect_faces():
    """Detect and recognize faces in an image.
    Expected JSON: { "image": "base64_image" }
    """
    try:
        data = request.get_json(force=True)
        image_b64 = data.get("image")

        if not image_b64:
            return jsonify({"error": "No image provided", "faces": []}), 400

        engine = get_face_engine()
        result = engine.detect_from_base64(image_b64)

        known = [f for f in result.get("faces", []) if f.get("is_known")]
        if known:
            names = ", ".join(f["name"] for f in known)
            logger.info(f"Recognized: {names}")

        return jsonify(result)

    except Exception as e:
        logger.error(f"Face detect error: {e}", exc_info=True)
        return jsonify({\"error\": str(e), \"faces\": []}), 500


# ============================================
# GESTURE RECOGNITION
# ============================================

@app.route("/api/gesture", methods=["POST"])
def detect_gesture():
    """
    Detect hand gestures in an image using MediaPipe.
    Expected JSON: { "image": "base64_image" }
    Returns: { "gestures": [...], "count": int }
    """
    try:
        data = request.get_json(force=True)
        image_b64 = data.get("image")
        if not image_b64:
            return jsonify({"error": "No image provided", "gestures": []}), 400

        engine = get_gesture_engine()
        result = engine.detect_from_base64(image_b64)

        if result.get("gestures"):
            names = ", ".join(g["gesture"] for g in result["gestures"])
            logger.info(f"[Gesture] Detected: {names}")

        return jsonify(result)
    except Exception as e:
        logger.error(f"Gesture detection error: {e}", exc_info=True)
        return jsonify({"error": str(e), "gestures": []}), 500


# ============================================
# EMOTION RECOGNITION
# ============================================

@app.route("/api/emotion", methods=["POST"])
def detect_emotion():
    """
    Detect facial emotions in an image.
    Expected JSON: { "image": "base64_image" }
    Returns: { "emotions": [...], "count": int }
    """
    try:
        data = request.get_json(force=True)
        image_b64 = data.get("image")
        if not image_b64:
            return jsonify({"error": "No image provided", "emotions": []}), 400

        engine = get_emotion_engine()
        result = engine.detect_from_base64(image_b64)

        if result.get("emotions"):
            dominant = result["emotions"][0].get("dominant_emotion", "?")
            logger.info(f"[Emotion] Dominant: {dominant}")

        return jsonify(result)
    except Exception as e:
        logger.error(f"Emotion detection error: {e}", exc_info=True)
        return jsonify({"error": str(e), "emotions": []}), 500


# ============================================
# POSE ESTIMATION
# ============================================

@app.route("/api/pose", methods=["POST"])
def detect_pose():
    """
    Detect body pose and posture in an image.
    Expected JSON: { "image": "base64_image" }
    Returns: { "poses": [...], "count": int }
    """
    try:
        data = request.get_json(force=True)
        image_b64 = data.get("image")
        if not image_b64:
            return jsonify({"error": "No image provided", "poses": []}), 400

        engine = get_pose_engine()
        result = engine.detect_from_base64(image_b64)

        if result.get("poses"):
            posture = result["poses"][0].get("posture", "?")
            logger.info(f"[Pose] Posture: {posture}")

        return jsonify(result)
    except Exception as e:
        logger.error(f"Pose detection error: {e}", exc_info=True)
        return jsonify({"error": str(e), "poses": []}), 500


# ============================================
# SCENE DESCRIPTION (LLM)
# ============================================

@app.route("/api/scene", methods=["POST"])
def describe_scene():
    """
    Generate a natural language description of the scene.
    Expected JSON: {
        "detections": [...],
        "gestures": [...],
        "emotions": [...],
        "poses": [...]
    }
    Returns: { "description": "..." }
    """
    try:
        data = request.get_json(force=True)
        generator = get_alert_generator()
        description = generator.generate_scene_description(
            detections=data.get("detections", []),
            gestures=data.get("gestures", []),
            emotions=data.get("emotions", []),
            poses=data.get("poses", []),
        )
        logger.info(f"[Scene] {description[:80]}...")
        return jsonify({"description": description})
    except Exception as e:
        logger.error(f"Scene description error: {e}", exc_info=True)
        return jsonify({"error": str(e), "description": ""}), 500


# ============================================
# UNIFIED MULTIMODAL ANALYSIS
# ============================================

@app.route("/api/analyze-frame", methods=["POST"])
def analyze_frame():
    """
    Run ALL AI modules on a single frame in parallel.
    Expected JSON: { "image": "base64_image", "include_scene": bool }
    Returns combined result from all engines.
    """
    import time
    from concurrent.futures import ThreadPoolExecutor, as_completed

    t_start = time.time()
    try:
        data = request.get_json(force=True)
        image_b64 = data.get("image")
        include_scene = data.get("include_scene", False)

        if not image_b64:
            return jsonify({"error": "No image provided"}), 400

        results = {}
        errors = {}

        # Run all engines in parallel
        def run_detection():
            return "objects", get_detector().detect_from_base64(image_b64)

        def run_gesture():
            return "gestures", get_gesture_engine().detect_from_base64(image_b64)

        def run_emotion():
            return "emotions", get_emotion_engine().detect_from_base64(image_b64)

        def run_pose():
            return "poses", get_pose_engine().detect_from_base64(image_b64)

        tasks = [run_detection, run_gesture, run_emotion, run_pose]

        with ThreadPoolExecutor(max_workers=4) as executor:
            futures = {executor.submit(fn): fn.__name__ for fn in tasks}
            for future in as_completed(futures, timeout=15):
                try:
                    key, value = future.result()
                    results[key] = value
                except Exception as e:
                    fn_name = futures[future]
                    errors[fn_name] = str(e)
                    logger.warning(f"[analyze-frame] {fn_name} failed: {e}")

        # Optional: generate scene description from all results
        description = None
        if include_scene:
            try:
                generator = get_alert_generator()
                description = generator.generate_scene_description(
                    detections=results.get("objects", {}).get("detections", []),
                    gestures=results.get("gestures", {}).get("gestures", []),
                    emotions=results.get("emotions", {}).get("emotions", []),
                    poses=results.get("poses", {}).get("poses", []),
                )
            except Exception as e:
                errors["scene"] = str(e)

        processing_ms = round((time.time() - t_start) * 1000)

        return jsonify({
            "objects":      results.get("objects", {}).get("detections", []),
            "gestures":     results.get("gestures", {}).get("gestures", []),
            "emotions":     results.get("emotions", {}).get("emotions", []),
            "poses":        results.get("poses", {}).get("poses", []),
            "alert_level":  results.get("objects", {}).get("alert_level", "SAFE"),
            "annotated_frame": results.get("objects", {}).get("annotated_frame"),
            "scene_description": description,
            "processing_ms": processing_ms,
            "errors": errors if errors else None,
        })

    except Exception as e:
        logger.error(f"analyze-frame error: {e}", exc_info=True)
        return jsonify({"error": str(e)}), 500


def device_watchdog():
    """Marks device as offline if no heartbeat received in 30 seconds."""
    while True:
        time.sleep(10)
        with status_lock:
            if device_status["last_seen"]:
                last = datetime.fromisoformat(device_status["last_seen"])
                now = datetime.now(timezone.utc)
                # Ensure both are timezone-aware for comparison
                if last.tzinfo is None:
                    last = last.replace(tzinfo=timezone.utc)
                delta = (now - last).total_seconds()
                if delta > 30:
                    device_status["online"] = False


# ============================================
# MAIN ENTRY POINT
# ============================================

def main():
    logger.info("=" * 50)
    logger.info("  SMART AI CAP — Backend Server")
    logger.info(f"  Frontend: http://localhost:{BACKEND_PORT}")
    logger.info(f"  ESP32 Stream: {ESP32_STREAM_URL}")
    logger.info("=" * 50)

    # Start watchdog thread
    watchdog = threading.Thread(target=device_watchdog, daemon=True)
    watchdog.start()

    app.run(host="0.0.0.0", port=BACKEND_PORT, debug=False, threaded=True)


if __name__ == "__main__":
    main()

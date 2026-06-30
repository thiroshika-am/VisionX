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
import base64
import cv2
import numpy as np
from datetime import datetime, timezone
from flask import Flask, Response, jsonify, send_from_directory, request, abort
from flask_cors import CORS
import requests

# Import AI modules
import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from ai_modules.detector import get_detector
from ai_modules.llm_alerts import get_alert_generator
from ai_modules.ocr_engine import get_ocr_reader
from ai_modules.face_recognition_engine import get_face_engine
from ai_modules.gesture_engine import get_gesture_engine
from ai_modules.emotion_engine import get_emotion_engine
from ai_modules.pose_engine import get_pose_engine
from ai_modules.voice_commander import get_voice_commander
from ai_modules.scheduler import get_scheduler, Priority

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

# Module configs (new structure)
MODULES = config.get("modules", {})
FAMILY_CONFIG = MODULES.get("family_recognition", {
    "enabled": True,
    "confidence_threshold": 0.6,
    "cooldown_sec": 30,
    "interval_sec": 1.5
})
GESTURE_CONFIG = MODULES.get("gesture_recognition", {
    "enabled": True,
    "hold_duration_sec": 0.5,
    "interval_sec": 0.5
})

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

# Latest raw image frame received from client (base64)
latest_frame_data = None
frame_lock = threading.Lock()

# Cached AI results
latest_faces_result = {"faces": [], "count": 0}
latest_gesture_result = {"gestures": [], "count": 0}
ai_results_lock = threading.Lock()

# Sighting logs
family_recent_sightings = []  # List of {name, timestamp, confidence}
sightings_lock = threading.Lock()

latest_debounced_gesture = {
    "gesture": "None",
    "display_name": "No Gesture",
    "meaning": "No Gesture",
    "confidence": 0.0,
    "timestamp": None
}
gesture_lock = threading.Lock()

# Pending browser announcements (TTS messages)
pending_announcements = []
announcements_lock = threading.Lock()

# Cooldown & hold states
last_face_announcements = {}  # name -> timestamp
gesture_hold_state = {
    "gesture": None,
    "first_seen": None,
    "last_fired": 0
}

# Gesture translations
GESTURE_MEANINGS = {
    "Thumb_Up": "Yes / OK",
    "thumbs_up": "Yes / OK",
    "Thumb_Down": "No",
    "thumbs_down": "No",
    "Open_Palm": "Stop / Wait",
    "open_palm": "Stop / Wait",
    "stop": "Stop / Wait",
    "Pointing_Up": "Question / Repeat that",
    "pointing": "Question / Repeat that",
    "Victory": "Hello / Goodbye",
    "victory": "Hello / Goodbye",
    "ILoveYou": "Help / Emergency",
    "rock_on": "Help / Emergency",
    "call_me": "Help / Emergency",
    "fist": "Help / Emergency"
}

def decode_base64_to_frame(image_b64):
    try:
        if "," in image_b64:
            image_b64 = image_b64.split(",")[1]
        img_bytes = base64.b64decode(image_b64)
        img_array = np.frombuffer(img_bytes, dtype=np.uint8)
        return cv2.imdecode(img_array, cv2.IMREAD_COLOR)
    except Exception as e:
        logger.error(f"Error decoding base64 image: {e}")
        return None

def add_pending_announcement(text):
    with announcements_lock:
        pending_announcements.append(text)

def get_and_clear_pending_announcements():
    with announcements_lock:
        res = list(pending_announcements)
        pending_announcements.clear()
        return res

def trigger_esp32_vibration(pattern):
    def run():
        try:
            esp_ip = config.get("esp32", {}).get("stream_url", "").split("/")[2].split(":")[0]
            if esp_ip:
                url = f"http://{esp_ip}:80/vibrate?pattern={pattern}"
                logger.info(f"Sending vibration command to ESP32: {url}")
                requests.get(url, timeout=2)
        except Exception as e:
            logger.warning(f"Failed to send vibration command to ESP32: {e}")
    threading.Thread(target=run, daemon=True).start()

def background_ai_worker():
    global latest_frame_data, latest_faces_result, latest_gesture_result, latest_debounced_gesture
    logger.info("Background AI Worker thread started")
    
    last_face_run = 0
    last_gesture_run = 0
    
    # Interval controls
    face_interval = 1.5      # seconds
    gesture_interval = 0.5   # seconds
    
    while True:
        try:
            time.sleep(0.05)
            
            image_b64 = None
            with frame_lock:
                if latest_frame_data is not None:
                    image_b64 = latest_frame_data
                    latest_frame_data = None
            
            if image_b64 is None:
                continue
                
            frame = decode_base64_to_frame(image_b64)
            if frame is None:
                continue
                
            now = time.time()
            
            # --- Face Recognition ---
            if FAMILY_CONFIG.get("enabled", True) and (now - last_face_run >= face_interval):
                last_face_run = now
                try:
                    engine = get_face_engine()
                    result = engine.detect(frame)
                    
                    with ai_results_lock:
                        latest_faces_result = result
                        
                    faces = result.get("faces", [])
                    conf_threshold = FAMILY_CONFIG.get("confidence_threshold", 0.6)
                    for face in faces:
                        if face.get("is_known") and face.get("confidence", 0) >= conf_threshold:
                            name = face["name"]
                            cooldown_sec = FAMILY_CONFIG.get("announce_cooldown_sec", 30)
                            last_seen = last_face_announcements.get(name, 0)
                            if now - last_seen >= cooldown_sec:
                                face["should_announce"] = True
                                last_face_announcements[name] = now
                                
                                with sightings_lock:
                                    sighting = {
                                        "name": name,
                                        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                                        "confidence": face["confidence"]
                                    }
                                    family_recent_sightings.insert(0, sighting)
                                    if len(family_recent_sightings) > 50:
                                        family_recent_sightings.pop()
                                
                                logger.info(f"[BG-AI] Family member matched: {name} ({face['confidence']})")
                                trigger_esp32_vibration("family_nearby")
                except Exception as ex:
                    logger.error(f"Background Face Recognition failed: {ex}")
            
            # --- Gesture Recognition ---
            if GESTURE_CONFIG.get("enabled", True) and (now - last_gesture_run >= gesture_interval):
                last_gesture_run = now
                try:
                    engine = get_gesture_engine()
                    result = engine.detect(frame)
                    
                    with ai_results_lock:
                        latest_gesture_result = result
                        
                    gestures = result.get("gestures", [])
                    if gestures:
                        g = gestures[0]
                        gesture_name = g["gesture"]
                        confidence = g["confidence"]
                        hold_duration = GESTURE_CONFIG.get("hold_duration_sec", 0.5)
                        
                        if gesture_hold_state["gesture"] == gesture_name:
                            first_seen = gesture_hold_state["first_seen"]
                            if first_seen and (now - first_seen >= hold_duration):
                                if now - gesture_hold_state["last_fired"] > 2.0:
                                    gesture_hold_state["last_fired"] = now
                                    meaning = GESTURE_MEANINGS.get(gesture_name, "Unknown Gesture")
                                    
                                    with gesture_lock:
                                        latest_debounced_gesture = {
                                            "gesture": gesture_name,
                                            "display_name": g.get("display_name", gesture_name),
                                            "meaning": meaning,
                                            "confidence": confidence,
                                            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                                        }
                                    
                                    logger.info(f"[BG-AI] Gesture debounced & fired: {gesture_name} -> {meaning}")
                                    trigger_esp32_vibration("gesture_confirm")
                                    add_pending_announcement(f"User is signaling: {meaning}")
                        else:
                            gesture_hold_state["gesture"] = gesture_name
                            gesture_hold_state["first_seen"] = now
                    else:
                        gesture_hold_state["gesture"] = None
                        gesture_hold_state["first_seen"] = None
                except Exception as ex:
                    logger.error(f"Background Gesture Recognition failed: {ex}")
                    
        except Exception as e:
            logger.error(f"Error in background AI worker: {e}", exc_info=True)

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
        status_copy = dict(device_status)
    status_copy["announcements"] = get_and_clear_pending_announcements()
    return jsonify(status_copy)


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


# --- Voice Command Dispatcher ---

@app.route("/api/voice/command", methods=["POST"])
def handle_voice_command():
    """
    Receive a voice command transcript from the frontend and dispatch it.
    Expected JSON: { "transcript": "what's around me" }
    Returns: { "action": str, "params": dict, "result": str, "speak": str }
    """
    try:
        data = request.get_json(force=True)
        transcript = data.get("transcript", "").strip()

        if not transcript:
            return jsonify({"error": "No transcript provided", "action": "unknown"}), 400

        commander = get_voice_commander()
        parsed = commander.parse(transcript)
        action = parsed["action"]
        params = parsed.get("params", {})

        result_text = ""
        speak_text = ""

        if action == "scene_describe":
            speak_text = "Scene description is not yet available. It will be added in Phase 2."
            result_text = speak_text

        elif action == "ocr_read":
            # Use current frame for OCR
            image_b64 = None
            with frame_lock:
                image_b64 = latest_frame_data
            if image_b64:
                reader = get_ocr_reader()
                ocr_result = reader.read_from_base64(image_b64)
                texts = ocr_result.get("texts", [])
                if texts:
                    combined = " ".join(t.get("text", "") for t in texts)
                    speak_text = f"I can read: {combined}"
                    result_text = combined
                else:
                    speak_text = "I don't see any text right now."
                    result_text = "No text detected"
            else:
                speak_text = "No camera frame available."
                result_text = speak_text

        elif action == "location_query":
            with gps_lock:
                lat = gps_data.get("latitude")
                lng = gps_data.get("longitude")
                source = gps_data.get("source", "unknown")
            if source != "placeholder" and lat and lng:
                speak_text = f"Your coordinates are {lat:.4f}, {lng:.4f}."
                result_text = f"Lat: {lat:.6f}, Lng: {lng:.6f}"
            else:
                speak_text = "GPS location is not available yet."
                result_text = speak_text

        elif action == "face_scan":
            speak_text = "Scanning for faces nearby."
            result_text = "Face scan triggered"
            # Force an immediate face recognition cycle
            with ai_results_lock:
                faces = latest_faces_result.get("faces", [])
                known = [f for f in faces if f.get("is_known")]
                if known:
                    names = ", ".join(f["name"] for f in known)
                    speak_text = f"I can see: {names}"
                    result_text = f"Recognized: {names}"
                else:
                    speak_text = "I don't recognize anyone nearby right now."

        elif action == "nav_start":
            destination = params.get("destination", "")
            speak_text = f"Navigation to {destination} is not yet available. It will be added in Phase 3."
            result_text = speak_text

        elif action == "nav_stop":
            speak_text = "Navigation stopped."
            result_text = speak_text

        elif action == "currency_detect":
            image_b64 = None
            with frame_lock:
                image_b64 = latest_frame_data
            if image_b64:
                try:
                    from ai_modules.currency_detector import get_currency_detector
                    detector = get_currency_detector()
                    curr_result = detector.detect_from_base64(image_b64)
                    if curr_result.get("detected"):
                        denomination = curr_result.get("denomination", "unknown")
                        speak_text = f"This looks like a {denomination} rupee note."
                        result_text = f"₹{denomination}"
                    else:
                        speak_text = "I can't identify a currency note. Try holding it closer."
                        result_text = "No currency detected"
                except Exception as ex:
                    speak_text = "Currency detection encountered an error."
                    result_text = str(ex)
            else:
                speak_text = "No camera frame available."
                result_text = speak_text

        elif action == "object_identify":
            speak_text = "Object identification is not yet available. It will be added in Phase 2."
            result_text = speak_text

        elif action == "sos_trigger":
            speak_text = "SOS triggered. Emergency contacts will be notified."
            result_text = "SOS activated"
            trigger_esp32_vibration("sos_active")

        else:
            help_text = commander.get_help_text()
            speak_text = f"I didn't understand that command. {help_text}"
            result_text = "Unknown command"

        # Queue announcement for TTS
        if speak_text:
            add_pending_announcement(speak_text)

        logger.info(f"[VoiceCmd] '{transcript}' → {action}: {result_text}")

        return jsonify({
            "action": action,
            "params": params,
            "result": result_text,
            "speak": speak_text,
            "transcript": transcript
        })

    except Exception as e:
        logger.error(f"Voice command error: {e}", exc_info=True)
        return jsonify({"error": str(e), "action": "error"}), 500


# --- Scheduler Status ---

@app.route("/api/scheduler/status", methods=["GET"])
def scheduler_status():
    """Return the current scheduler stats and active modules."""
    try:
        scheduler = get_scheduler()
        stats = scheduler.get_stats()
        stats["active_modules"] = {
            name: mod.get("enabled", False)
            for name, mod in MODULES.items()
        }
        return jsonify(stats)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

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
        
        # Update latest frame for background processing
        global latest_frame_data
        with frame_lock:
            latest_frame_data = image_b64
        
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
    """Detect and recognize faces in an image (returns cached results)."""
    try:
        data = request.get_json(force=True)
        image_b64 = data.get("image")

        if image_b64:
            global latest_frame_data
            with frame_lock:
                latest_frame_data = image_b64

        with ai_results_lock:
            return jsonify(latest_faces_result)

    except Exception as e:
        logger.error(f"Face detect error: {e}", exc_info=True)
        return jsonify({"error": str(e), "faces": []}), 500


# --- API: Family Recognition Endpoints ---

@app.route("/api/family/enroll", methods=["POST"])
def enroll_family_member():
    """Enroll a new family member (delegates to add_face)."""
    return add_face()


@app.route("/api/family/recent", methods=["GET"])
def get_recent_family_sightings():
    """Get the log of recent family sightings."""
    with sightings_lock:
        return jsonify({
            "sightings": family_recent_sightings,
            "count": len(family_recent_sightings)
        })


@app.route("/api/gesture/latest", methods=["GET"])
def get_latest_gesture():
    """Get the most recent debounced gesture and translation."""
    with gesture_lock:
        return jsonify(latest_debounced_gesture)


# ============================================
# GESTURE RECOGNITION
# ============================================

@app.route("/api/gesture", methods=["POST"])
def detect_gesture():
    """Detect hand gestures in an image (returns cached results)."""
    try:
        data = request.get_json(force=True)
        image_b64 = data.get("image")

        if image_b64:
            global latest_frame_data
            with frame_lock:
                latest_frame_data = image_b64

        with ai_results_lock:
            return jsonify(latest_gesture_result)

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

    # Start background AI worker thread
    ai_thread = threading.Thread(target=background_ai_worker, daemon=True)
    ai_thread.start()

    app.run(host="0.0.0.0", port=BACKEND_PORT, debug=False, threaded=True)


if __name__ == "__main__":
    main()

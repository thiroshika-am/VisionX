"""AI routes — all detection, recognition, and analysis endpoints."""

import os
import sys
import logging
import time
import base64
import numpy as np
import cv2
from concurrent.futures import ThreadPoolExecutor, as_completed
from flask import Blueprint, jsonify, request

import backend.state as state

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

logger = logging.getLogger("smartcap")

GESTURE_MEANINGS = {
    "Thumb_Up": "Yes / OK", "thumbs_up": "Yes / OK",
    "Thumb_Down": "No", "thumbs_down": "No",
    "Open_Palm": "Stop / Wait", "open_palm": "Stop / Wait", "stop": "Stop / Wait",
    "Pointing_Up": "Question / Repeat that", "pointing": "Question / Repeat that",
    "Victory": "Hello / Goodbye", "victory": "Hello / Goodbye",
    "ILoveYou": "Help / Emergency", "rock_on": "Help / Emergency",
    "call_me": "Help / Emergency", "fist": "Help / Emergency",
}



def _trigger_vibration(config, pattern: str):
    import threading
    import requests as r
    def run():
        try:
            ip = config.get("esp32", {}).get("stream_url", "").split("/")[2].split(":")[0]
            if ip:
                r.get(f"http://{ip}:80/vibrate?pattern={pattern}", timeout=2)
        except Exception:
            pass
    threading.Thread(target=run, daemon=True).start()


def build_ai_bp(config):
    bp = Blueprint("ai", __name__)
    family_cfg  = config.get("modules", {}).get("family_recognition", {})
    gesture_cfg = config.get("modules", {}).get("gesture_recognition", {})

    # ── Object Detection ──────────────────────────────────────────────────────

    @bp.route("/api/detect", methods=["POST"])
    def detect_objects():
        try:
            data      = request.get_json(force=True)
            image_b64 = data.get("image")
            if not image_b64:
                return jsonify({"error": "No image", "detections": [], "count": 0}), 400
            with state.frame_lock:
                state.latest_frame_data = image_b64
                state.latest_frame_time = time.time()
            from ai_modules.detector import get_detector
            result = get_detector().detect_from_base64(image_b64)

            # Apply smart prioritizer
            try:
                src_path = os.path.join(os.path.dirname(__file__), "..", "..", "src")
                sys.path.insert(0, src_path)
                from ai.smart_prioritizer import get_prioritizer
                result["detections"] = get_prioritizer().prioritize(result["detections"])
            except Exception:
                pass

            # Log detection
            try:
                from core.logger import get_logger
                get_logger().log_detection(result)
            except Exception:
                pass

            # Update system FPS
            try:
                from core.system_monitor import get_monitor
                get_monitor().record_frame()
            except Exception:
                pass

            logger.info(f"Detection: {result['count']} objects, alert={result['alert_level']}")
            return jsonify(result)
        except Exception as e:
            logger.error(f"Detection error: {e}", exc_info=True)
            return jsonify({"error": str(e), "detections": [], "count": 0}), 500

    # ── LLM Alert Generation ──────────────────────────────────────────────────

    @bp.route("/api/generate-alert", methods=["POST"])
    def generate_alert():
        try:
            data       = request.get_json(force=True)
            detections = data.get("detections", [])
            location   = data.get("location")
            if not detections:
                return jsonify({"alert": None})
            from ai_modules.llm_alerts import get_alert_generator
            alert = get_alert_generator().generate_alert(detections, location)
            return jsonify({"alert": alert})
        except Exception as e:
            return jsonify({"alert": None, "error": str(e)}), 500

    # ── OCR ───────────────────────────────────────────────────────────────────

    @bp.route("/api/ocr", methods=["POST"])
    def detect_text():
        try:
            data      = request.get_json(force=True)
            image_b64 = data.get("image")
            if not image_b64:
                return jsonify({"error": "No image", "texts": []}), 400
            from ai_modules.ocr_engine import get_ocr_reader
            result = get_ocr_reader().detect_from_base64(image_b64)
            if result.get("combined_text"):
                logger.info(f"OCR: '{result['combined_text'][:80]}'")
            return jsonify(result)
        except Exception as e:
            logger.error(f"OCR error: {e}", exc_info=True)
            return jsonify({"error": str(e), "texts": []}), 500

    # ── Face Recognition ──────────────────────────────────────────────────────

    @bp.route("/api/faces", methods=["GET"])
    def list_faces():
        try:
            from ai_modules.face_recognition_engine import get_face_engine
            people = get_face_engine().list_people()
            return jsonify({"people": people, "count": len(people)})
        except Exception as e:
            return jsonify({"error": str(e), "people": []}), 500

    @bp.route("/api/faces", methods=["POST"])
    def add_face():
        try:
            data  = request.get_json(force=True)
            name  = (data.get("name") or "").strip()
            photo = data.get("photo", "")
            if not name:
                return jsonify({"error": "Name required"}), 400
            if not photo:
                return jsonify({"error": "Photo required"}), 400
            from ai_modules.face_recognition_engine import get_face_engine
            result = get_face_engine().add_person(name, photo)
            if result["success"]:
                logger.info(f"Added person: {name}")
                return jsonify(result)
            return jsonify(result), 400
        except Exception as e:
            return jsonify({"error": str(e)}), 500

    @bp.route("/api/faces/<person_id>", methods=["DELETE"])
    def remove_face(person_id):
        try:
            from ai_modules.face_recognition_engine import get_face_engine
            result = get_face_engine().remove_person(person_id)
            return jsonify(result) if result["success"] else (jsonify(result), 404)
        except Exception as e:
            return jsonify({"error": str(e)}), 500

    @bp.route("/api/faces/photo/<person_id>")
    def get_face_photo(person_id):
        from flask import send_from_directory, abort
        try:
            from ai_modules.face_recognition_engine import get_face_engine
            path = get_face_engine().get_photo_path(person_id)
            if path:
                return send_from_directory(os.path.dirname(path), os.path.basename(path))
            abort(404)
        except Exception as e:
            return jsonify({"error": str(e)}), 500

    @bp.route("/api/face-detect", methods=["POST"])
    def detect_faces():
        try:
            data      = request.get_json(force=True)
            image_b64 = data.get("image")
            if image_b64:
                with state.frame_lock:
                    state.latest_frame_data = image_b64
                    state.latest_frame_time = time.time()
            with state.ai_results_lock:
                return jsonify(state.latest_faces_result)
        except Exception as e:
            return jsonify({"error": str(e), "faces": []}), 500

    # ── Family Recognition Helpers ────────────────────────────────────────────

    @bp.route("/api/family/enroll", methods=["POST"])
    def enroll_family():
        return add_face()

    @bp.route("/api/family/recent", methods=["GET"])
    def recent_sightings():
        with state.sightings_lock:
            return jsonify({"sightings": state.family_recent_sightings,
                            "count": len(state.family_recent_sightings)})

    # ── Gesture Recognition ───────────────────────────────────────────────────

    @bp.route("/api/gesture", methods=["POST"])
    def detect_gesture():
        try:
            data      = request.get_json(force=True)
            image_b64 = data.get("image")
            if image_b64:
                with state.frame_lock:
                    state.latest_frame_data = image_b64
                    state.latest_frame_time = time.time()
            with state.ai_results_lock:
                return jsonify(state.latest_gesture_result)
        except Exception as e:
            return jsonify({"error": str(e), "gestures": []}), 500

    @bp.route("/api/gesture/latest", methods=["GET"])
    def latest_gesture():
        with state.gesture_lock:
            return jsonify(state.latest_debounced_gesture)

    # ── Emotion Detection ─────────────────────────────────────────────────────

    @bp.route("/api/emotion", methods=["POST"])
    def detect_emotion():
        try:
            data      = request.get_json(force=True)
            image_b64 = data.get("image")
            if not image_b64:
                return jsonify({"error": "No image", "emotions": []}), 400
            
            with state.frame_lock:
                state.latest_frame_data = image_b64
                state.latest_frame_time = time.time()
                
            from ai_modules.emotion_engine import get_emotion_engine
            result = get_emotion_engine().detect_from_base64(image_b64)
            return jsonify(result)
        except Exception as e:
            return jsonify({"error": str(e), "emotions": []}), 500

    # ── Pose Estimation ───────────────────────────────────────────────────────

    @bp.route("/api/pose", methods=["POST"])
    def detect_pose():
        try:
            data      = request.get_json(force=True)
            image_b64 = data.get("image")
            if not image_b64:
                return jsonify({"error": "No image", "poses": []}), 400
            
            with state.frame_lock:
                state.latest_frame_data = image_b64
                state.latest_frame_time = time.time()
                
            from ai_modules.pose_engine import get_pose_engine
            result = get_pose_engine().detect_from_base64(image_b64)
            return jsonify(result)
        except Exception as e:
            return jsonify({"error": str(e), "poses": []}), 500

    # ── Depth Estimation ──────────────────────────────────────────────────────

    @bp.route("/api/depth", methods=["POST"])
    def estimate_depth():
        try:
            data      = request.get_json(force=True)
            image_b64 = data.get("image")
            if not image_b64:
                return jsonify({"error": "No image"}), 400
            
            with state.frame_lock:
                state.latest_frame_data = image_b64
                state.latest_frame_time = time.time()
                
            src_path = os.path.join(os.path.dirname(__file__), "..", "..", "src")
            sys.path.insert(0, src_path)
            from ai.depth_estimator import get_depth_estimator
            result = get_depth_estimator().estimate_from_base64(image_b64)
            return jsonify(result)
        except Exception as e:
            logger.error(f"Depth error: {e}", exc_info=True)
            return jsonify({"error": str(e)}), 500

    # ── Fall Detection ────────────────────────────────────────────────────────

    @bp.route("/api/fall-detect", methods=["POST"])
    def fall_detect():
        try:
            data      = request.get_json(force=True)
            image_b64 = data.get("image")
            if not image_b64:
                return jsonify({"error": "No image"}), 400
            
            with state.frame_lock:
                state.latest_frame_data = image_b64
                state.latest_frame_time = time.time()
                
            src_path = os.path.join(os.path.dirname(__file__), "..", "..", "src")
            sys.path.insert(0, src_path)
            from ai.fall_detector import get_fall_detector
            result = get_fall_detector().detect_from_base64(image_b64)
            if result.get("fall_detected"):
                logger.warning("FALL DETECTED!")
                state.add_announcement("Alert! A fall has been detected.")
                _trigger_vibration(config, "sos_active")
            return jsonify(result)
        except Exception as e:
            return jsonify({"error": str(e), "fall_detected": False}), 500

    # ── Scene Description ─────────────────────────────────────────────────────

    @bp.route("/api/scene", methods=["POST"])
    def describe_scene():
        try:
            data = request.get_json(force=True)
            from ai_modules.llm_alerts import get_alert_generator
            desc = get_alert_generator().generate_scene_description(
                detections=data.get("detections", []),
                gestures  =data.get("gestures",   []),
                emotions  =data.get("emotions",   []),
                poses     =data.get("poses",      []),
            )
            return jsonify({"description": desc})
        except Exception as e:
            return jsonify({"error": str(e), "description": ""}), 500

    # ── Unified Multi-Modal Analysis ──────────────────────────────────────────

    @bp.route("/api/analyze-frame", methods=["POST"])
    def analyze_frame():
        t0 = time.time()
        try:
            data          = request.get_json(force=True)
            image_b64     = data.get("image")
            include_scene = data.get("include_scene", False)
            include_depth = data.get("include_depth", False)
            language      = data.get("language", "en")
            if not image_b64:
                return jsonify({"error": "No image"}), 400

            results = {}
            errors  = {}

            def run_objects():
                from ai_modules.detector import get_detector
                return "objects", get_detector().detect_from_base64(image_b64)

            def run_gesture():
                from ai_modules.gesture_engine import get_gesture_engine
                return "gestures", get_gesture_engine().detect_from_base64(image_b64)

            def run_emotion():
                from ai_modules.emotion_engine import get_emotion_engine
                return "emotions", get_emotion_engine().detect_from_base64(image_b64)

            def run_pose():
                from ai_modules.pose_engine import get_pose_engine
                return "poses", get_pose_engine().detect_from_base64(image_b64)

            def run_depth():
                src_path = os.path.join(os.path.dirname(__file__), "..", "..", "src")
                sys.path.insert(0, src_path)
                from ai.depth_estimator import get_depth_estimator
                return "depth", get_depth_estimator().estimate_from_base64(image_b64)

            tasks = [run_objects, run_gesture, run_emotion, run_pose]
            if include_depth:
                tasks.append(run_depth)

            with ThreadPoolExecutor(max_workers=5) as ex:
                futures = {ex.submit(fn): fn.__name__ for fn in tasks}
                for fut in as_completed(futures, timeout=20):
                    try:
                        key, val = fut.result()
                        results[key] = val
                    except Exception as e:
                        errors[futures[fut]] = str(e)

            # Update shared frame
            with state.frame_lock:
                state.latest_frame_data = image_b64
                state.latest_frame_time = time.time()

            # Smart prioritize objects
            raw_detections = results.get("objects", {}).get("detections", [])
            try:
                src_path = os.path.join(os.path.dirname(__file__), "..", "..", "src")
                sys.path.insert(0, src_path)
                from ai.smart_prioritizer import get_prioritizer
                raw_detections = get_prioritizer().prioritize(raw_detections)
            except Exception:
                pass

            description = None
            if include_scene:
                try:
                    from ai_modules.llm_alerts import get_alert_generator
                    description = get_alert_generator().generate_scene_description(
                        detections=raw_detections,
                        gestures  =results.get("gestures", {}).get("gestures", []),
                        emotions  =results.get("emotions", {}).get("emotions", []),
                        poses     =results.get("poses",    {}).get("poses",    []),
                        language  =language
                    )
                except Exception as e:
                    errors["scene"] = str(e)

            processing_ms = round((time.time() - t0) * 1000)

            return jsonify({
                "objects":           raw_detections,
                "gestures":          results.get("gestures", {}).get("gestures", []),
                "emotions":          results.get("emotions", {}).get("emotions", []),
                "poses":             results.get("poses",    {}).get("poses",    []),
                "depth":             results.get("depth",    {}).get("depth_map_b64"),
                "alert_level":       results.get("objects",  {}).get("alert_level", "SAFE"),
                "annotated_frame":   results.get("objects",  {}).get("annotated_frame"),
                "scene_description": description,
                "processing_ms":     processing_ms,
                "errors":            errors or None,
            })
        except Exception as e:
            logger.error(f"analyze-frame error: {e}", exc_info=True)
            return jsonify({"error": str(e)}), 500

    # ── Voice Command Dispatcher ──────────────────────────────────────────────

    @bp.route("/api/voice/command", methods=["POST"])
    def voice_command():
        try:
            data       = request.get_json(force=True)
            transcript = (data.get("transcript") or "").strip()
            language   = data.get("language", "en")
            if not transcript:
                return jsonify({"error": "No transcript", "action": "unknown"}), 400

            from ai_modules.voice_commander import get_voice_commander
            commander = get_voice_commander()
            parsed    = commander.parse(transcript)
            action    = parsed["action"]
            params    = parsed.get("params", {})
            speak     = ""
            result    = ""

            if action == "scene_describe":
                speak = result = "Scene description requested. Analyzing your surroundings now."

            elif action == "ocr_read":
                image_b64 = None
                with state.frame_lock:
                    image_b64 = state.latest_frame_data
                if image_b64:
                    from ai_modules.ocr_engine import get_ocr_reader
                    ocr = get_ocr_reader().detect_from_base64(image_b64)
                    texts = ocr.get("texts", [])
                    combined = " ".join(t.get("text", "") for t in texts)
                    speak = f"I can read: {combined}" if combined else "I don't see any text right now."
                    result = combined or "No text detected"
                else:
                    speak = result = "No camera frame available."

            elif action == "location_query":
                with state.gps_lock:
                    lat    = state.gps_data.get("latitude")
                    lng    = state.gps_data.get("longitude")
                    source = state.gps_data.get("source", "placeholder")
                speak = (f"Your coordinates are {lat:.4f}, {lng:.4f}."
                         if source != "placeholder" and lat and lng
                         else "GPS location is not available yet.")
                result = speak

            elif action == "face_scan":
                with state.ai_results_lock:
                    faces = state.latest_faces_result.get("faces", [])
                known = [f for f in faces if f.get("is_known")]
                if known:
                    names = ", ".join(f["name"] for f in known)
                    speak = f"I can see: {names}"
                    result = f"Recognized: {names}"
                else:
                    speak = result = "I don't recognize anyone nearby right now."

            elif action == "nav_start":
                dest  = params.get("destination", "")
                speak = result = f"Starting navigation to {dest}."

            elif action == "currency_detect":
                image_b64 = None
                with state.frame_lock:
                    image_b64 = state.latest_frame_data
                if image_b64:
                    try:
                        from ai_modules.currency_detector import get_currency_detector
                        curr = get_currency_detector().detect_from_base64(image_b64)
                        currency_info = curr.get("currency")
                        if currency_info:
                            denom = currency_info.get("denomination", "unknown")
                            speak = f"This looks like a {denom} rupee note."
                            result = f"₹{denom}"
                        else:
                            speak = result = "I can't identify a currency note. Hold it closer."
                    except Exception as ex:
                        speak = result = "Currency detection error."
                else:
                    speak = result = "No camera frame available."

            elif action == "ask_assistant":
                query_text = params.get("query", transcript)
                image_b64 = None
                with state.frame_lock:
                    image_b64 = state.latest_frame_data
                with state.gps_lock:
                    gps = dict(state.gps_data)
                
                from ai_modules.interactive_assistant import get_interactive_assistant
                ia_result = get_interactive_assistant(config).query(query_text, image_b64, gps, language=language)
                speak = ia_result.get("speak", "I couldn't find an answer to that.")
                result = ia_result.get("summary", speak)

            elif action == "sos_trigger":
                speak = result = "SOS triggered. Emergency contacts will be notified."
                _trigger_vibration(config, "sos_active")

            else:
                speak = f"I didn't understand that. {commander.get_help_text()}"
                result = "Unknown command"

            if speak:
                state.add_announcement(speak)
            logger.info(f"[Voice] '{transcript}' → {action}: {result}")
            return jsonify({"action": action, "params": params,
                            "result": result, "speak": speak, "transcript": transcript})
        except Exception as e:
            logger.error(f"Voice command error: {e}", exc_info=True)
            return jsonify({"error": str(e), "action": "error"}), 500

    # ── Interactive Assistant ──────────────────────────────────────────────────

    @bp.route("/api/assistant/query", methods=["POST"])
    def assistant_query():
        """Universal interactive query — ask about places, people, objects, text."""
        try:
            data = request.get_json(force=True)
            query = (data.get("query") or "").strip()
            language = data.get("language", "en")
            if not query:
                return jsonify({"error": "No query", "speak": "Please ask a question."}), 400
            
            image_b64 = data.get("image")
            if not image_b64:
                with state.frame_lock:
                    image_b64 = state.latest_frame_data
            
            with state.gps_lock:
                gps = dict(state.gps_data)
            
            from ai_modules.interactive_assistant import get_interactive_assistant
            result = get_interactive_assistant(config).query(query, image_b64, gps, language=language)
            
            if result.get("speak"):
                state.add_announcement(result["speak"])
            
            return jsonify(result)
        except Exception as e:
            logger.error(f"Assistant query error: {e}", exc_info=True)
            return jsonify({"error": str(e), "speak": "An error occurred."}), 500

    return bp

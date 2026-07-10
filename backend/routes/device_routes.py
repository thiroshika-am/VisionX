"""Device routes — GPS, status, ESP32 stream proxy, distance."""

import logging
from datetime import datetime, timezone

import requests as http_requests
from flask import Blueprint, Response, jsonify, request

import backend.state as state

logger = logging.getLogger("smartcap")


def build_device_bp(config):
    bp = Blueprint("device", __name__)

    ESP32_STREAM_URL   = config.get("esp32", {}).get("stream_url",   "http://192.168.1.100:80/stream")
    ESP32_STATUS_URL   = config.get("esp32", {}).get("status_url",   "http://192.168.1.100:80/status")
    ESP32_DISTANCE_URL = config.get("esp32", {}).get("distance_url", "http://192.168.1.100:80/distance")

    # ── Camera stream proxy ───────────────────────────────────────────────────

    @bp.route("/api/stream")
    def stream_proxy():
        def generate():
            try:
                resp = http_requests.get(ESP32_STREAM_URL, stream=True, timeout=(3, 10))
                for chunk in resp.iter_content(chunk_size=4096):
                    yield chunk
            except http_requests.exceptions.RequestException as e:
                logger.warning(f"ESP32 stream unavailable: {e}")
        return Response(generate(), mimetype="multipart/x-mixed-replace; boundary=frame")

    # ── GPS ───────────────────────────────────────────────────────────────────

    @bp.route("/api/gps", methods=["GET"])
    def get_gps():
        with state.gps_lock:
            return jsonify(state.gps_data)

    @bp.route("/api/gps", methods=["POST"])
    def update_gps():
        data = request.get_json(force=True)
        with state.gps_lock:
            state.gps_data.update({
                "latitude":  data.get("latitude",  state.gps_data["latitude"]),
                "longitude": data.get("longitude", state.gps_data["longitude"]),
                "accuracy":  data.get("accuracy",  0),
                "speed":     data.get("speed",     0),
                "altitude":  data.get("altitude",  0),
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "source":    "esp32",
            })
            lat = state.gps_data['latitude']
            lng = state.gps_data['longitude']
        logger.info(f"GPS updated: {lat}, {lng}")
        return jsonify({"status": "ok"})

    # ── Device heartbeat ──────────────────────────────────────────────────────

    @bp.route("/api/status", methods=["GET"])
    def get_status():
        with state.status_lock:
            copy = dict(state.device_status)
        copy["announcements"] = state.pop_announcements()
        return jsonify(copy)

    @bp.route("/api/status", methods=["POST"])
    def update_status():
        data = request.get_json(force=True)
        with state.status_lock:
            state.device_status.update({
                "online":      True,
                "last_seen":   datetime.now(timezone.utc).isoformat(),
                "battery":     data.get("battery"),
                "wifi_rssi":   data.get("wifi_rssi"),
                "distance_mm": data.get("distance_mm"),
                "alert_level": data.get("alert_level", "SAFE"),
                "uptime":      data.get("uptime", 0),
            })
        return jsonify({"status": "ok"})

    # ── Distance proxy ────────────────────────────────────────────────────────

    @bp.route("/api/distance")
    def get_distance():
        try:
            resp = http_requests.get(ESP32_DISTANCE_URL, timeout=3)
            return jsonify(resp.json())
        except Exception:
            return jsonify({"distance_mm": None, "error": "ESP32 unreachable"})

    return bp

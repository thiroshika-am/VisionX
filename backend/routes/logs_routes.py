"""Logs routes — read and clear structured event logs."""

import os
import json
import logging

from flask import Blueprint, jsonify, request

logger = logging.getLogger("smartcap")

BASE_DIR  = os.path.join(os.path.dirname(__file__), "..", "..")
LOGS_DIR  = os.path.join(BASE_DIR, "logs")


def _read_jsonl(path: str, limit: int = 100) -> list:
    rows = []
    if not os.path.exists(path):
        return rows
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    rows.append(json.loads(line))
                except json.JSONDecodeError:
                    pass
    return rows[-limit:]


def build_logs_bp(config):
    bp = Blueprint("logs", __name__)
    os.makedirs(LOGS_DIR, exist_ok=True)

    VALID_KINDS = {"events", "detections", "performance"}

    @bp.route("/api/logs")
    def get_logs():
        kind  = request.args.get("kind", "events")   # events | detections | performance
        if kind not in VALID_KINDS:
            return jsonify({"error": "Invalid log kind", "logs": [], "count": 0}), 400
        try:
            limit = int(request.args.get("limit", 100))
        except (ValueError, TypeError):
            limit = 100
        path  = os.path.join(LOGS_DIR, f"{kind}.jsonl")
        rows  = _read_jsonl(path, limit)
        return jsonify({"logs": rows, "count": len(rows), "kind": kind})

    @bp.route("/api/logs", methods=["DELETE"])
    def clear_logs():
        kind = request.args.get("kind", "events")
        if kind not in VALID_KINDS:
            return jsonify({"error": "Invalid log kind"}), 400
        path = os.path.join(LOGS_DIR, f"{kind}.jsonl")
        if os.path.exists(path):
            with open(path, "w") as f:
                pass
        return jsonify({"status": "cleared", "kind": kind})

    return bp

"""Auth routes — login, register, verify-token."""

import os
import json
import hashlib
import secrets
import logging
from datetime import datetime, timezone

from flask import Blueprint, request, jsonify

logger = logging.getLogger("smartcap")

USERS_PATH = os.path.join(os.path.dirname(__file__), "..", "..", "config", "users.json")


def _load_users():
    try:
        with open(USERS_PATH) as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {"users": {}}


def _save_users(data):
    with open(USERS_PATH, "w") as f:
        json.dump(data, f, indent=2)


def _hash_pw(password, salt=None):
    if salt is None:
        salt = secrets.token_hex(16)
    h = hashlib.sha256((salt + password).encode()).hexdigest()
    return f"{salt}${h}"


def _verify_pw(password, stored):
    if "$" not in stored:
        return False
    salt, _ = stored.split("$", 1)
    return _hash_pw(password, salt) == stored


def build_auth_bp(config):
    bp = Blueprint("auth", __name__)

    @bp.route("/api/login", methods=["POST"])
    def login():
        data = request.get_json(force=True)
        if not isinstance(data, dict):
            return jsonify({"success": False, "message": "Invalid JSON payload"}), 400
        username = (data.get("username") or "").strip()
        password = data.get("password") or ""
        if not username or not password:
            return jsonify({"success": False, "message": "Username and password required"}), 400
        users_data = _load_users()
        user = users_data.get("users", {}).get(username)
        if not user or not _verify_pw(password, user.get("password_hash", "")):
            return jsonify({"success": False, "message": "Invalid username or password"}), 401
        token = secrets.token_hex(32)
        users_data["users"][username]["last_login"] = datetime.now(timezone.utc).isoformat()
        users_data["users"][username]["token"] = token
        _save_users(users_data)
        logger.info(f"User '{username}' logged in")
        return jsonify({"success": True, "token": token, "username": username})

    @bp.route("/api/register", methods=["POST"])
    def register():
        data = request.get_json(force=True)
        if not isinstance(data, dict):
            return jsonify({"success": False, "message": "Invalid JSON payload"}), 400
        username = (data.get("username") or "").strip()
        password = data.get("password") or ""
        email    = (data.get("email") or "").strip()
        if not username or not password:
            return jsonify({"success": False, "message": "Username and password required"}), 400
        if len(username) < 3:
            return jsonify({"success": False, "message": "Username must be at least 3 characters"}), 400
        if len(password) < 6:
            return jsonify({"success": False, "message": "Password must be at least 6 characters"}), 400
        users_data = _load_users()
        if username in users_data.get("users", {}):
            return jsonify({"success": False, "message": "Username already exists"}), 409
        now = datetime.now(timezone.utc).isoformat()
        token = secrets.token_hex(32)
        users_data.setdefault("users", {})[username] = {
            "password_hash": _hash_pw(password),
            "email": email,
            "created_at": now,
            "last_login": now,
            "token": token,
        }
        _save_users(users_data)
        logger.info(f"New user registered: '{username}'")
        return jsonify({"success": True, "token": token, "username": username})

    @bp.route("/api/verify-token", methods=["POST"])
    def verify_token():
        data = request.get_json(force=True)
        if not isinstance(data, dict):
            return jsonify({"valid": False}), 400
        token = data.get("token", "")
        if not token:
            return jsonify({"valid": False})
        users_data = _load_users()
        for user in users_data.get("users", {}).values():
            if user.get("token") == token:
                return jsonify({"valid": True})
        return jsonify({"valid": False})

    return bp

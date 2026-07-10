"""System routes — health, system stats, scheduler status."""

import os
import sys
import logging
from datetime import datetime, timezone

from flask import Blueprint, jsonify

logger = logging.getLogger("smartcap")


def build_system_bp(config):
    bp = Blueprint("system", __name__)

    modules_cfg = config.get("modules", {})

    @bp.route("/api/health")
    def health():
        return jsonify({"status": "ok", "time": datetime.now(timezone.utc).isoformat()})

    @bp.route("/api/system")
    def system_stats():
        """Live CPU, RAM, GPU, FPS stats."""
        try:
            sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "src"))
            from core.system_monitor import get_monitor
            monitor = get_monitor()
            return jsonify(monitor.get_stats())
        except Exception as e:
            logger.warning(f"system_monitor unavailable: {e}")
            # Fallback — bare psutil
            try:
                import psutil
                mem = psutil.virtual_memory()
                return jsonify({
                    "cpu_percent": psutil.cpu_percent(interval=None),
                    "ram_percent": mem.percent,
                    "ram_used_mb": round(mem.used / 1024 / 1024),
                    "ram_total_mb": round(mem.total / 1024 / 1024),
                    "fps": 0,
                    "gpu_available": False,
                    "uptime_sec": 0,
                })
            except Exception as e2:
                return jsonify({"error": str(e2)}), 500

    @bp.route("/api/scheduler/status")
    def scheduler_status():
        try:
            sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
            from ai_modules.scheduler import get_scheduler
            scheduler = get_scheduler()
            stats = scheduler.get_stats()
            stats["active_modules"] = {
                name: mod.get("enabled", False)
                for name, mod in modules_cfg.items()
            }
            return jsonify(stats)
        except Exception as e:
            return jsonify({"error": str(e)}), 500

    @bp.route("/api/context")
    def get_context():
        """Return the smart prioritizer's recent context memory."""
        try:
            sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "src"))
            from ai.smart_prioritizer import get_prioritizer
            p = get_prioritizer()
            return jsonify({"context": p.get_context_summary()})
        except Exception as e:
            return jsonify({"context": {}, "error": str(e)})

    return bp

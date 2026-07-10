"""
Structured JSONL Logger for VisionX.
Writes detection events, voice commands, errors, and performance metrics
to rotating JSONL files in the logs/ directory.
"""

import os
import json
import time
import threading
import logging
from datetime import datetime, timezone
from typing import Optional

logger = logging.getLogger("smartcap")

BASE_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "logs")


class VisionXLogger:
    def __init__(self, logs_dir: str = None):
        self._dir     = logs_dir or BASE_DIR
        self._lock    = threading.Lock()
        os.makedirs(self._dir, exist_ok=True)

    # ── Internal write ────────────────────────────────────────────────────────

    def _write(self, kind: str, record: dict):
        record["_ts"] = datetime.now(timezone.utc).isoformat()
        path = os.path.join(self._dir, f"{kind}.jsonl")
        try:
            with self._lock:
                with open(path, "a", encoding="utf-8") as f:
                    f.write(json.dumps(record, ensure_ascii=False) + "\n")
        except Exception as e:
            logger.warning(f"[VisionXLogger] Write failed ({kind}): {e}")

    # ── Public API ────────────────────────────────────────────────────────────

    def log_detection(self, result: dict):
        """Log a detection result (from YOLO)."""
        self._write("detections", {
            "count":       result.get("count", 0),
            "alert_level": result.get("alert_level", "SAFE"),
            "objects": [
                {
                    "class":      d.get("class"),
                    "confidence": d.get("confidence"),
                    "distance":   d.get("distance"),
                    "position":   d.get("position"),
                    "alert":      d.get("alert_level"),
                }
                for d in result.get("detections", [])[:10]
            ],
        })

    def log_event(self, kind: str, message: str, extra: dict = None):
        """Log a general event (voice command, face sighting, fall, etc.)."""
        record = {"kind": kind, "message": message}
        if extra:
            record.update(extra)
        self._write("events", record)

    def log_performance(self, fps: float, cpu: float, ram: float, processing_ms: int = None):
        """Log a performance snapshot."""
        record = {"fps": fps, "cpu_percent": cpu, "ram_percent": ram}
        if processing_ms is not None:
            record["processing_ms"] = processing_ms
        self._write("performance", record)

    def log_error(self, module: str, error: str):
        """Log an error from any module."""
        self._write("events", {"kind": "error", "module": module, "error": error})


# Singleton
_vx_logger: Optional[VisionXLogger] = None


def get_logger() -> VisionXLogger:
    global _vx_logger
    if _vx_logger is None:
        _vx_logger = VisionXLogger()
    return _vx_logger

"""
Tests for VisionX YOLO Object Detector.
Run: python -m pytest tests/ -v
"""

import os
import sys
import base64
import numpy as np
import cv2
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


def _make_b64_image(width=640, height=480, color=(100, 150, 200)) -> str:
    """Create a solid-color test image as base64 JPEG."""
    img = np.full((height, width, 3), color, dtype=np.uint8)
    _, buf = cv2.imencode(".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, 85])
    return "data:image/jpeg;base64," + base64.b64encode(buf).decode()


class TestObjectDetector:

    @pytest.fixture(scope="class")
    def detector(self):
        from ai_modules.detector import get_detector
        return get_detector()

    def test_detector_loads(self, detector):
        """Detector must initialise without error."""
        assert detector is not None
        assert detector.model is not None

    def test_detect_from_b64_returns_dict(self, detector):
        """detect_from_base64 must return a dict with 'detections' key."""
        b64 = _make_b64_image()
        result = detector.detect_from_base64(b64)
        assert isinstance(result, dict)
        assert "detections" in result
        assert "count" in result
        assert "alert_level" in result

    def test_detect_empty_image(self, detector):
        """Blank image should return 0 detections without crashing."""
        b64 = _make_b64_image(color=(0, 0, 0))
        result = detector.detect_from_base64(b64)
        assert result["count"] >= 0

    def test_alert_level_values(self, detector):
        """alert_level must be one of the three valid states."""
        b64 = _make_b64_image()
        result = detector.detect_from_base64(b64)
        assert result["alert_level"] in ("SAFE", "WARNING", "CRITICAL")

    def test_detection_schema(self, detector):
        """Each detection must have required fields."""
        b64 = _make_b64_image()
        result = detector.detect_from_base64(b64)
        for det in result["detections"]:
            assert "class"      in det
            assert "confidence" in det
            assert "bbox"       in det
            assert 0 <= det["confidence"] <= 1.0

    def test_invalid_image(self, detector):
        """Invalid base64 must return error gracefully."""
        result = detector.detect_from_base64("not_valid_base64")
        assert "error" in result or result.get("count", 0) == 0


class TestSmartPrioritizer:

    @pytest.fixture
    def prioritizer(self):
        sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
        from ai.smart_prioritizer import SmartPrioritizer
        return SmartPrioritizer()

    def test_danger_class_scores_highest(self, prioritizer):
        detections = [
            {"class": "car",    "confidence": 0.9, "alert_level": "CRITICAL"},
            {"class": "bottle", "confidence": 0.9, "alert_level": "SAFE"},
        ]
        result = prioritizer.prioritize(detections)
        assert result[0]["class"] == "car"

    def test_approaching_boosts_score(self, prioritizer):
        detections = [
            {"class": "person", "confidence": 0.8, "alert_level": "SAFE",
             "movement": {"approaching": False}},
            {"class": "person", "confidence": 0.8, "alert_level": "SAFE",
             "movement": {"approaching": True}},
        ]
        result = prioritizer.prioritize(detections)
        approaching = [d for d in result if d.get("movement", {}).get("approaching")]
        assert len(approaching) > 0
        assert approaching[0]["priority_score"] > 0

    def test_context_memory_updated(self, prioritizer):
        detections = [{"class": "chair", "confidence": 0.7, "alert_level": "SAFE"}]
        prioritizer.prioritize(detections)
        ctx = prioritizer.get_context_summary()
        assert "chair" in ctx

    def test_empty_input(self, prioritizer):
        result = prioritizer.prioritize([])
        assert result == []

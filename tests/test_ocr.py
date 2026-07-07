"""
Tests for VisionX OCR Engine.
Run: python -m pytest tests/test_ocr.py -v
"""

import os
import sys
import base64
import numpy as np
import cv2
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


def _text_image(text: str, width=640, height=200) -> str:
    """Render white text on black background as base64 JPEG."""
    img = np.zeros((height, width, 3), dtype=np.uint8)
    cv2.putText(img, text, (50, height // 2), cv2.FONT_HERSHEY_SIMPLEX,
                2.0, (255, 255, 255), 3)
    _, buf = cv2.imencode(".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, 95])
    return "data:image/jpeg;base64," + base64.b64encode(buf).decode()


def _blank_image() -> str:
    img = np.zeros((480, 640, 3), dtype=np.uint8)
    _, buf = cv2.imencode(".jpg", img)
    return "data:image/jpeg;base64," + base64.b64encode(buf).decode()


class TestOCREngine:

    @pytest.fixture(scope="class")
    def ocr(self):
        from ai_modules.ocr_engine import get_ocr_reader
        return get_ocr_reader()

    def test_ocr_loads(self, ocr):
        assert ocr is not None

    def test_blank_image_no_crash(self, ocr):
        result = ocr.detect_from_base64(_blank_image())
        assert isinstance(result, dict)
        assert "texts" in result

    def test_invalid_input(self, ocr):
        result = ocr.detect_from_base64("invalid_base64")
        assert "error" in result or result.get("count", 0) == 0

    def test_result_schema(self, ocr):
        result = ocr.detect_from_base64(_blank_image())
        assert "texts" in result
        assert "count" in result
        for item in result["texts"]:
            assert "text"       in item
            assert "confidence" in item
            assert "bbox"       in item

    def test_cooldown_logic(self, ocr):
        """is_new_text should return True on first call, False on immediate repeat."""
        assert ocr.is_new_text("HELLO WORLD", cooldown_seconds=60) is True
        assert ocr.is_new_text("HELLO WORLD", cooldown_seconds=60) is False

    @pytest.mark.skipif(
        not os.getenv("VISIONX_FULL_TESTS"),
        reason="Slow test, set VISIONX_FULL_TESTS=1 to run"
    )
    def test_reads_rendered_text(self, ocr):
        """Full integration: render text image and check OCR finds it."""
        b64 = _text_image("HELLO")
        result = ocr.detect_from_base64(b64)
        combined = result.get("combined_text", "").upper()
        # Allow partial match (OCR may split characters)
        assert "HELL" in combined or "HELLO" in combined

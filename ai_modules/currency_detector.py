"""
INR Currency Detection Module for SmartCap AI
Detects Indian Rupee banknotes using color analysis + OCR text matching.

Supports: ₹10, ₹20, ₹50, ₹100, ₹200, ₹500, ₹2000
"""

import cv2
import numpy as np
import base64
from typing import Dict, Optional, List

# ============================================
# INR NOTE COLOR PROFILES (HSV ranges)
# Each note has a dominant color visible from front/back
# ============================================

INR_COLOR_PROFILES = {
    10: {
        "name": "Ten Rupees",
        "color_desc": "chocolate brown / orange",
        # HSV range for chocolate brown/orange tones
        "hsv_ranges": [
            {"lower": (5, 50, 80), "upper": (20, 200, 230)},
            {"lower": (0, 60, 100), "upper": (12, 180, 220)},
        ],
    },
    20: {
        "name": "Twenty Rupees",
        "color_desc": "greenish yellow",
        "hsv_ranges": [
            {"lower": (25, 40, 100), "upper": (45, 180, 230)},
            {"lower": (20, 50, 120), "upper": (40, 170, 240)},
        ],
    },
    50: {
        "name": "Fifty Rupees",
        "color_desc": "fluorescent blue",
        "hsv_ranges": [
            {"lower": (90, 40, 100), "upper": (115, 200, 240)},
            {"lower": (85, 30, 110), "upper": (120, 190, 250)},
        ],
    },
    100: {
        "name": "Hundred Rupees",
        "color_desc": "lavender / light purple",
        "hsv_ranges": [
            {"lower": (120, 20, 100), "upper": (155, 130, 230)},
            {"lower": (115, 15, 110), "upper": (150, 120, 240)},
        ],
    },
    200: {
        "name": "Two Hundred Rupees",
        "color_desc": "bright yellow / orange",
        "hsv_ranges": [
            {"lower": (15, 80, 130), "upper": (35, 255, 255)},
            {"lower": (18, 60, 140), "upper": (30, 250, 255)},
        ],
    },
    500: {
        "name": "Five Hundred Rupees",
        "color_desc": "stone grey / light brown",
        "hsv_ranges": [
            {"lower": (0, 10, 100), "upper": (25, 70, 200)},
            {"lower": (5, 15, 110), "upper": (20, 80, 210)},
        ],
    },
    2000: {
        "name": "Two Thousand Rupees",
        "color_desc": "magenta / pink",
        "hsv_ranges": [
            {"lower": (140, 40, 80), "upper": (175, 200, 240)},
            {"lower": (145, 30, 100), "upper": (170, 180, 230)},
        ],
    },
}

# Denomination strings that might appear on notes (OCR detection)
DENOMINATION_PATTERNS = {
    "2000": 2000,
    "500": 500,
    "200": 200,
    "100": 100,
    "50": 50,
    "20": 20,
    "10": 10,
}

import threading
_currency_detector = None
_currency_detector_lock = threading.Lock()

def get_currency_detector():
    global _currency_detector
    if _currency_detector is None:
        with _currency_detector_lock:
            if _currency_detector is None:
                _currency_detector = CurrencyDetector()
    return _currency_detector


class CurrencyDetector:
    """Detects INR currency notes using color + OCR analysis."""

    def __init__(self):
        self.min_note_area_ratio = 0.05  # Note must cover at least 5% of frame
        self.max_note_area_ratio = 0.85  # Note shouldn't cover more than 85%
        print("[CurrencyDetector] INR currency detector initialized")

    def detect_from_base64(self, image_b64: str, ocr_texts: Optional[List[str]] = None) -> Dict:
        """
        Detect INR currency from base64 image.
        
        Args:
            image_b64: Base64 encoded image
            ocr_texts: Optional list of OCR-detected texts from the same frame
        """
        try:
            if ',' in image_b64:
                image_b64 = image_b64.split(',')[1]

            img_bytes = base64.b64decode(image_b64)
            img_array = np.frombuffer(img_bytes, dtype=np.uint8)
            frame = cv2.imdecode(img_array, cv2.IMREAD_COLOR)

            if frame is None:
                return {"currency": None, "error": "Failed to decode image"}

            return self.detect(frame, ocr_texts)

        except Exception as e:
            return {"currency": None, "error": str(e)}

    def detect(self, frame: np.ndarray, ocr_texts: Optional[List[str]] = None) -> Dict:
        """
        Detect INR currency notes in frame.
        
        Returns dict with:
            currency: { denomination, name, confidence, method }
            or None if no currency detected
        """
        try:
            h, w = frame.shape[:2]
            total_pixels = h * w

            # Convert to HSV for color analysis
            hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)

            # 1. Try to find a rectangular note-like region
            note_region, note_mask = self._find_note_region(frame)

            # 2. Color-based denomination detection
            color_results = self._detect_by_color(hsv, note_mask, total_pixels)

            # 3. OCR-based denomination detection
            ocr_result = self._detect_by_ocr(ocr_texts)

            # 4. Combine results
            final = self._combine_results(color_results, ocr_result)

            if final:
                return {
                    "currency": {
                        "denomination": final["denomination"],
                        "name": f"₹{final['denomination']}",
                        "full_name": INR_COLOR_PROFILES.get(final["denomination"], {}).get("name", ""),
                        "confidence": round(final["confidence"], 2),
                        "method": final["method"],
                    }
                }

            return {"currency": None}

        except Exception as e:
            return {"currency": None, "error": str(e)}

    def _find_note_region(self, frame: np.ndarray):
        """Find rectangular note-like region in the frame."""
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        blurred = cv2.GaussianBlur(gray, (5, 5), 0)
        edges = cv2.Canny(blurred, 30, 100)

        # Dilate to connect nearby edges
        kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (5, 5))
        edges = cv2.dilate(edges, kernel, iterations=2)

        contours, _ = cv2.findContours(edges, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

        h, w = frame.shape[:2]
        total_area = h * w
        note_mask = np.zeros((h, w), dtype=np.uint8)

        best_contour = None
        best_area = 0

        for cnt in contours:
            area = cv2.contourArea(cnt)
            ratio = area / total_area

            if ratio < self.min_note_area_ratio or ratio > self.max_note_area_ratio:
                continue

            # Check if roughly rectangular (note aspect ratio ~2:1)
            peri = cv2.arcLength(cnt, True)
            approx = cv2.approxPolyDP(cnt, 0.04 * peri, True)

            if 4 <= len(approx) <= 8 and area > best_area:
                rect = cv2.minAreaRect(cnt)
                w_r, h_r = rect[1]
                if w_r > 0 and h_r > 0:
                    aspect = max(w_r, h_r) / min(w_r, h_r)
                    # Indian notes have aspect ratio roughly 1.8 to 2.3
                    if 1.4 <= aspect <= 3.0:
                        best_contour = cnt
                        best_area = area

        if best_contour is not None:
            cv2.drawContours(note_mask, [best_contour], -1, 255, -1)
            # Extract region
            x, y, rw, rh = cv2.boundingRect(best_contour)
            note_region = frame[y:y+rh, x:x+rw]
            return note_region, note_mask

        return None, None

    def _detect_by_color(self, hsv: np.ndarray, note_mask: Optional[np.ndarray], total_pixels: int) -> List[Dict]:
        """Detect denomination by dominant color matching."""
        results = []

        for denomination, profile in INR_COLOR_PROFILES.items():
            total_match = 0

            for hsv_range in profile["hsv_ranges"]:
                lower = np.array(hsv_range["lower"])
                upper = np.array(hsv_range["upper"])
                mask = cv2.inRange(hsv, lower, upper)

                # If we found a note region, only check within it
                if note_mask is not None:
                    mask = cv2.bitwise_and(mask, note_mask)
                    region_pixels = cv2.countNonZero(note_mask)
                    if region_pixels == 0:
                        continue
                    match_ratio = cv2.countNonZero(mask) / region_pixels
                else:
                    match_ratio = cv2.countNonZero(mask) / total_pixels

                total_match = max(total_match, match_ratio)

            # Need at least 20% color match
            if total_match >= 0.20:
                # Scale confidence: 20% match=0.35, 50%+ match=0.9
                confidence = min(0.95, 0.35 + (total_match - 0.20) * 1.8)
                results.append({
                    "denomination": denomination,
                    "confidence": confidence,
                    "match_ratio": total_match,
                    "method": "color",
                })

        # Sort by confidence
        results.sort(key=lambda x: x["confidence"], reverse=True)
        return results

    def _detect_by_ocr(self, ocr_texts: Optional[List[str]]) -> Optional[Dict]:
        """Detect denomination from OCR text results."""
        if not ocr_texts:
            return None

        combined = " ".join(ocr_texts).strip()
        if not combined:
            return None

        # Look for denomination numbers and rupee symbol
        has_rupee_symbol = "₹" in combined or "rs" in combined.lower() or "rupee" in combined.lower()
        
        # Check for "RESERVE BANK OF INDIA" or "RBI" or "भारतीय" (indicates a note)
        has_rbi = any(kw in combined.upper() for kw in ["RESERVE BANK", "RBI", "INDIA", "PROMISE", "BEARER", "MAHATMA", "GANDHI"])

        for pattern, denomination in DENOMINATION_PATTERNS.items():
            if pattern in combined:
                confidence = 0.5
                if has_rupee_symbol:
                    confidence += 0.2
                if has_rbi:
                    confidence += 0.2
                # Longer pattern = more specific
                if len(pattern) >= 3:
                    confidence += 0.05

                return {
                    "denomination": denomination,
                    "confidence": min(0.95, confidence),
                    "method": "ocr",
                }

        return None

    def _combine_results(self, color_results: List[Dict], ocr_result: Optional[Dict]) -> Optional[Dict]:
        """Combine color and OCR results for final decision."""
        if not color_results and not ocr_result:
            return None

        # If both agree on denomination, boost confidence
        if ocr_result and color_results:
            for cr in color_results:
                if cr["denomination"] == ocr_result["denomination"]:
                    combined_conf = min(0.98, cr["confidence"] * 0.5 + ocr_result["confidence"] * 0.5 + 0.15)
                    return {
                        "denomination": cr["denomination"],
                        "confidence": combined_conf,
                        "method": "color+ocr",
                    }

        # OCR alone is fairly reliable for denomination numbers
        if ocr_result and ocr_result["confidence"] >= 0.5:
            return ocr_result

        # Strong color match alone
        if color_results and color_results[0]["confidence"] >= 0.55:
            return color_results[0]

        # Weak OCR result
        if ocr_result:
            return ocr_result

        # Weak color result
        if color_results and color_results[0]["confidence"] >= 0.35:
            return color_results[0]

        return None

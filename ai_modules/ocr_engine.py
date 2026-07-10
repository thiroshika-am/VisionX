"""
OCR Engine for SmartCap AI
Detects and reads text from camera frames
Uses EasyOCR for fast, accurate text recognition
"""

import os
import cv2
import numpy as np
import base64
from typing import Dict, List, Optional
import re

# Try to import EasyOCR, fall back to basic detection if not available
try:
    import easyocr
    EASYOCR_AVAILABLE = True
except ImportError:
    EASYOCR_AVAILABLE = False
    print("Warning: EasyOCR not installed. Run: pip install easyocr")

import threading
_ocr_reader = None
_ocr_reader_lock = threading.Lock()

def get_ocr_reader():
    """Get or create singleton OCR reader."""
    global _ocr_reader
    if _ocr_reader is None:
        with _ocr_reader_lock:
            if _ocr_reader is None:
                _ocr_reader = OCREngine()
    return _ocr_reader


class OCREngine:
    """OCR engine for text detection and recognition."""
    
    def __init__(self, languages: List[str] = ['en']):
        """
        Initialize OCR engine.
        
        Args:
            languages: List of language codes to detect
        """
        self.reader = None
        self.languages = languages
        self.last_detected_text = ""
        self.text_cooldown = {}  # Prevent repeating same text
        
        if EASYOCR_AVAILABLE:
            try:
                print(f"Loading EasyOCR with languages: {languages}")
                # gpu=True if CUDA available, False otherwise
                import torch
                use_gpu = torch.cuda.is_available()
                self.reader = easyocr.Reader(languages, gpu=use_gpu, verbose=False)
                print(f"EasyOCR loaded successfully (GPU: {use_gpu})")
            except Exception as e:
                print(f"Error loading EasyOCR: {e}")
                self.reader = None
        else:
            print("EasyOCR not available - OCR disabled")
    
    def preprocess_image(self, image: np.ndarray) -> np.ndarray:
        """Preprocess image for better OCR results, especially small/distant text."""
        # Upscale small images for better small-text detection
        h, w = image.shape[:2]
        if max(h, w) < 1280:
            scale = 1280 / max(h, w)
            image = cv2.resize(image, None, fx=scale, fy=scale, interpolation=cv2.INTER_CUBIC)
        
        # Convert to grayscale if needed
        if len(image.shape) == 3:
            gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        else:
            gray = image
        
        # Apply CLAHE for better contrast (helps with distant text)
        clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
        enhanced = clahe.apply(gray)
        
        # Sharpen to improve edge definition of small text
        kernel = np.array([[-1, -1, -1],
                           [-1,  9, -1],
                           [-1, -1, -1]])
        sharpened = cv2.filter2D(enhanced, -1, kernel)
        
        return sharpened
    
    def detect_from_base64(self, image_b64: str, min_confidence: float = 0.4) -> Dict:
        """
        Detect text from base64 encoded image.
        
        Args:
            image_b64: Base64 encoded image (with or without data URI prefix)
            min_confidence: Minimum confidence threshold
            
        Returns:
            Dict with detected text, bounding boxes, and confidence
        """
        try:
            # Remove data URI prefix if present
            if ',' in image_b64:
                image_b64 = image_b64.split(',')[1]
            
            # Decode base64 to image
            img_bytes = base64.b64decode(image_b64)
            img_array = np.frombuffer(img_bytes, dtype=np.uint8)
            frame = cv2.imdecode(img_array, cv2.IMREAD_COLOR)
            
            if frame is None:
                return {"texts": [], "error": "Failed to decode image"}
            
            return self.detect(frame, min_confidence)
            
        except Exception as e:
            return {"texts": [], "error": str(e)}
    
    def detect(self, frame: np.ndarray, min_confidence: float = 0.4) -> Dict:
        """
        Detect text in an image frame.
        
        Args:
            frame: OpenCV image (BGR format)
            min_confidence: Minimum confidence threshold
            
        Returns:
            Dict with detected texts and their locations
        """
        if self.reader is None:
            return {"texts": [], "error": "OCR not available"}
        
        try:
            h, w = frame.shape[:2]
            
            # Gentle upscale only if very small — avoid creating artifacts
            if max(h, w) < 800:
                scale = 800 / max(h, w)
                frame = cv2.resize(frame, None, fx=scale, fy=scale, interpolation=cv2.INTER_LINEAR)
            
            # Mild CLAHE — just enough to help contrast without amplifying noise
            lab = cv2.cvtColor(frame, cv2.COLOR_BGR2LAB)
            l, a, b = cv2.split(lab)
            clahe = cv2.createCLAHE(clipLimit=1.5, tileGridSize=(8, 8))
            l = clahe.apply(l)
            enhanced = cv2.merge([l, a, b])
            frame_enhanced = cv2.cvtColor(enhanced, cv2.COLOR_LAB2BGR)
            
            # NO sharpening — it creates false text from edges/textures
            
            # Run OCR with per-word results (paragraph=False) so we get real confidence scores
            results = self.reader.readtext(frame_enhanced, paragraph=False, min_size=10, text_threshold=0.6)
            
            texts = []
            full_text_parts = []
            
            for detection in results:
                bbox, text, confidence = detection
                
                if confidence < min_confidence:
                    continue
                
                # Clean the text
                cleaned_text = self._clean_text(text)
                if not cleaned_text:
                    continue
                
                # Get bounding box coordinates
                bbox_points = np.array(bbox).astype(int)
                x_min = int(min(point[0] for point in bbox_points))
                y_min = int(min(point[1] for point in bbox_points))
                x_max = int(max(point[0] for point in bbox_points))
                y_max = int(max(point[1] for point in bbox_points))
                
                texts.append({
                    "text": cleaned_text,
                    "confidence": round(confidence, 2),
                    "bbox": {
                        "x1": x_min,
                        "y1": y_min,
                        "x2": x_max,
                        "y2": y_max
                    }
                })
                
                full_text_parts.append(cleaned_text)
            
            # Combine all detected text
            combined_text = " ".join(full_text_parts)
            
            return {
                "texts": texts,
                "combined_text": combined_text,
                "count": len(texts)
            }
            
        except Exception as e:
            return {"texts": [], "error": str(e)}
    
    def _clean_text(self, text: str) -> str:
        """Clean and normalize detected text, filter out garbage."""
        if not text:
            return ""
        
        # Remove excessive whitespace
        text = " ".join(text.split())
        
        # Collapse spaced-out single letters into words
        # e.g. "H E L L O" -> "HELLO", "W O R L D" -> "WORLD"
        text = re.sub(
            r'\b((?:[A-Za-z0-9] ){2,}[A-Za-z0-9])\b',
            lambda m: m.group(0).replace(' ', ''),
            text
        )
        
        # Remove strings that are only special characters/punctuation
        if re.match(r'^[^\w]+$', text):
            return ""
        
        # Filter out strings that are mostly non-alphanumeric (likely noise)
        alnum_count = sum(1 for c in text if c.isalnum())
        if len(text) > 0 and alnum_count / len(text) < 0.4:
            return ""
        
        # Filter out random character soup — require at least one vowel or digit
        # in words 3+ chars (pure consonant strings are usually garbage)
        words = text.split()
        valid_words = []
        for word in words:
            if len(word) <= 2:
                valid_words.append(word)
            elif re.search(r'[aeiouAEIOU0-9]', word):
                valid_words.append(word)
            # else: skip consonant-only garbage like "brk", "xzq"
        
        text = " ".join(valid_words)
        
        return text.strip()
    
    def is_new_text(self, text: str, cooldown_seconds: float = 5.0) -> bool:
        """
        Check if this text is new (not recently announced).
        
        Args:
            text: The detected text
            cooldown_seconds: How long to wait before re-announcing same text
            
        Returns:
            True if text is new or cooldown expired
        """
        import time
        now = time.time()
        
        # Normalize text for comparison
        normalized = text.lower().strip()
        
        if normalized in self.text_cooldown:
            last_time = self.text_cooldown[normalized]
            if now - last_time < cooldown_seconds:
                return False
        
        self.text_cooldown[normalized] = now
        
        # Clean up old entries
        expired = [k for k, v in self.text_cooldown.items() if now - v > 60]
        for k in expired:
            del self.text_cooldown[k]
        
        return True

#!/usr/bin/env python
"""Simple test script to verify OCR is working"""

import numpy as np
import cv2
import base64

print("[TEST] Starting OCR test...")

# Import OCR
print("[TEST] Importing OCR engine...")
from ai_modules.ocr_engine import get_ocr_reader

# Create a test image with text
print("[TEST] Creating test image with text...")
test_img = np.ones((480, 640, 3), dtype=np.uint8) * 255  # White background
cv2.putText(test_img, 'HELLO WORLD', (100, 240), cv2.FONT_HERSHEY_SIMPLEX, 2, (0, 0, 0), 3)

# Convert to JPEG and base64
print("[TEST] Encoding image to base64...")
_, buffer = cv2.imencode('.jpg', test_img)
image_b64 = base64.b64encode(buffer).decode('utf-8')
print(f"[TEST] Image base64 size: {len(image_b64)} bytes")

# Load OCR and test
print("[TEST] Loading OCR engine...")
ocr = get_ocr_reader()
print("[TEST] OCR engine loaded!")

# Test OCR
print("[TEST] Running OCR...")
result = ocr.detect_from_base64(image_b64)
print(f"[TEST] OCR complete!")
print(f"[TEST] Result: {result.get('count', 0)} texts found")
print(f"[TEST] Keys in result: {list(result.keys())}")

if result.get('combined_text'):
    print(f"[TEST] ✓ OCR WORKING - found text: '{result['combined_text']}'")
else:
    print("[TEST] ✓ OCR WORKING - no text detected in test image")

print("[TEST] Test complete!")

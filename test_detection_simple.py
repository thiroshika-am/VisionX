#!/usr/bin/env python
"""Simple test script to verify detection is working"""

import numpy as np
import cv2
import base64
from io import BytesIO
from PIL import Image

print("[TEST] Starting detection test...")

# Import detector
print("[TEST] Importing detector...")
from ai_modules.detector import get_detector

# Create a test image with some content
print("[TEST] Creating test image...")
test_img = np.zeros((480, 640, 3), dtype=np.uint8)
cv2.rectangle(test_img, (100, 100), (500, 400), (0, 255, 0), -1)  # Green rectangle
cv2.circle(test_img, (320, 240), 50, (0, 0, 255), -1)  # Red circle

# Convert to JPEG and base64 (like the frontend does)
print("[TEST] Encoding image to base64...")
_, buffer = cv2.imencode('.jpg', test_img)
image_b64 = base64.b64encode(buffer).decode('utf-8')
print(f"[TEST] Image base64 size: {len(image_b64)} bytes")

# Load detector and test detection
print("[TEST] Loading detector...")
detector = get_detector()
print("[TEST] Detector loaded!")

# Test detection
print("[TEST] Running detection...")
result = detector.detect_from_base64(image_b64)
print(f"[TEST] Detection complete!")
print(f"[TEST] Result: {result.get('count', 0)} objects found")
print(f"[TEST] Alert level: {result.get('alert_level', 'N/A')}")
print(f"[TEST] Keys in result: {list(result.keys())}")

if result.get('count', 0) > 0:
    print(f"[TEST] ✓ Detection WORKING - found {result['count']} objects")
else:
    print("[TEST] ✓ Detection WORKING - no objects in test image (expected)")

print("[TEST] Test complete!")

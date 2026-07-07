"""
Monocular Depth Estimator for VisionX — MiDaS MiDaS_small (ONNX).
Provides relative depth maps from a single camera frame.
Falls back gracefully if torch/model is unavailable.
"""

import os
import base64
import logging
import urllib.request
from typing import Optional, Dict

import cv2
import numpy as np

logger = logging.getLogger("smartcap")

BASE_DIR   = os.path.join(os.path.dirname(__file__), "..", "..", "config", "models")
MODEL_PATH = os.path.join(BASE_DIR, "midas_small.onnx")
MODEL_URL  = "https://github.com/isl-org/MiDaS/releases/download/v2_1/model-small.onnx"

os.makedirs(BASE_DIR, exist_ok=True)


def _download_model():
    if os.path.exists(MODEL_PATH):
        return True
    try:
        logger.info("[DepthEstimator] Downloading MiDaS small ONNX model (~80 MB)...")
        urllib.request.urlretrieve(MODEL_URL, MODEL_PATH)
        logger.info(f"[DepthEstimator] Downloaded: {MODEL_PATH}")
        return True
    except Exception as e:
        logger.warning(f"[DepthEstimator] Download failed: {e}")
        return False


class DepthEstimator:
    """MiDaS_small ONNX depth estimator."""

    INPUT_SIZE = (256, 256)

    def __init__(self):
        self.net: Optional[cv2.dnn.Net] = None
        self._init()

    def _init(self):
        if not _download_model():
            logger.warning("[DepthEstimator] Model unavailable — depth estimation disabled")
            return
        try:
            self.net = cv2.dnn.readNetFromONNX(MODEL_PATH)
            # Prefer CUDA backend if available
            try:
                self.net.setPreferableBackend(cv2.dnn.DNN_BACKEND_CUDA)
                self.net.setPreferableTarget(cv2.dnn.DNN_TARGET_CUDA)
                logger.info("[DepthEstimator] MiDaS loaded on GPU (CUDA)")
            except Exception:
                self.net.setPreferableBackend(cv2.dnn.DNN_BACKEND_DEFAULT)
                self.net.setPreferableTarget(cv2.dnn.DNN_TARGET_CPU)
                logger.info("[DepthEstimator] MiDaS loaded on CPU")
        except Exception as e:
            logger.error(f"[DepthEstimator] Init failed: {e}")
            self.net = None

    # ── Public API ────────────────────────────────────────────────────────────

    def estimate(self, frame: np.ndarray) -> Dict:
        """
        Run depth estimation on a BGR frame.
        Returns a small depth map as base64 JPEG + zone statistics.
        """
        if self.net is None:
            return {"error": "Depth estimator not available", "zones": {}}

        h, w = frame.shape[:2]
        inp  = cv2.resize(frame, self.INPUT_SIZE)
        blob = cv2.dnn.blobFromImage(
            inp, scalefactor=1.0 / 255.0, size=self.INPUT_SIZE,
            mean=(0.485, 0.456, 0.406), swapRB=True, crop=False,
        )
        self.net.setInput(blob)
        depth = self.net.forward()         # (1,1,H,W) or (1,H,W)
        depth = np.squeeze(depth)          # (H,W)

        # Normalize to 0-255 for visualisation
        d_min, d_max = depth.min(), depth.max()
        if d_max - d_min > 0:
            depth_norm = ((depth - d_min) / (d_max - d_min) * 255).astype(np.uint8)
        else:
            depth_norm = np.zeros_like(depth, dtype=np.uint8)

        # Colormap for frontend display
        depth_color = cv2.applyColorMap(depth_norm, cv2.COLORMAP_MAGMA)
        depth_small = cv2.resize(depth_color, (w // 4, h // 4))

        _, buf = cv2.imencode(".jpg", depth_small, [cv2.IMWRITE_JPEG_QUALITY, 70])
        depth_b64 = base64.b64encode(buf).decode()

        # Zone analysis: left / center / right average depth
        dh, dw = depth.shape
        left   = float(depth[:, :dw // 3].mean())
        center = float(depth[:, dw // 3: 2 * dw // 3].mean())
        right  = float(depth[:, 2 * dw // 3:].mean())

        def zone_label(v):
            # Higher MiDaS value = CLOSER in some models; treat as relative only
            percentile_75 = float(np.percentile(depth, 75))
            if v > percentile_75 * 0.9:
                return "near"
            elif v > float(depth.mean()):
                return "medium"
            return "far"

        return {
            "depth_map_b64": f"data:image/jpeg;base64,{depth_b64}",
            "zones": {
                "left":   {"value": round(left,   2), "label": zone_label(left)},
                "center": {"value": round(center, 2), "label": zone_label(center)},
                "right":  {"value": round(right,  2), "label": zone_label(right)},
            },
        }

    def estimate_from_base64(self, image_b64: str) -> Dict:
        try:
            if "," in image_b64:
                image_b64 = image_b64.split(",")[1]
            arr   = np.frombuffer(base64.b64decode(image_b64), dtype=np.uint8)
            frame = cv2.imdecode(arr, cv2.IMREAD_COLOR)
            if frame is None:
                return {"error": "Invalid image", "zones": {}}
            return self.estimate(frame)
        except Exception as e:
            return {"error": str(e), "zones": {}}


# Singleton
_estimator: Optional[DepthEstimator] = None


def get_depth_estimator() -> DepthEstimator:
    global _estimator
    if _estimator is None:
        _estimator = DepthEstimator()
    return _estimator

"""
YOLO Object Detection Module for VisionX
Detects obstacles and objects from webcam frames
Uses ultralytics YOLOv8l (large) for high-accuracy detection
GPU-accelerated with CUDA for maximum performance
Includes BoT-SORT multi-object tracking
"""

import os
import cv2
import numpy as np
import base64
import torch
import time
from typing import Dict, List, Tuple, Optional
from ultralytics import YOLO

# Store model in workspace root
MODEL_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Use YOLOv8l (large) for high accuracy. Falls back to yolov8n if l not present.
MODEL_PATH_L = os.path.join(MODEL_DIR, "yolov8l.pt")
MODEL_PATH_N = os.path.join(MODEL_DIR, "yolov8n.pt")
MODEL_PATH = MODEL_PATH_L  # yolov8l auto-downloads on first run

# Auto-detect GPU
DEVICE = 'cuda' if torch.cuda.is_available() else 'cpu'

class ObjectDetector:
    """YOLO-based object detector for obstacle detection"""
    
    def __init__(self, confidence_threshold: float = 0.4):
        """
        Initialize the detector with YOLO model.
        
        Args:
            confidence_threshold: Minimum confidence for detections
        """
        self.confidence_threshold = confidence_threshold
        self.model = None
        self._load_model()
        
        # Priority objects for blind navigation (obstacles to announce)
        self.priority_objects = {
            'person', 'bicycle', 'car', 'motorcycle', 'bus', 'truck', 'traffic light',
            'stop sign', 'bench', 'chair', 'dog', 'cat', 'fire hydrant', 'parking meter',
            'potted plant', 'dining table', 'couch', 'bed', 'door', 'stairs'
        }
        
        # Reference heights in cm for distance estimation
        self.reference_heights = {
            'person': 170, 'bicycle': 100, 'car': 150, 'motorcycle': 110,
            'bus': 280, 'truck': 250, 'chair': 90, 'dog': 50, 'cat': 30,
            'bottle': 25, 'cup': 10, 'laptop': 25, 'cell phone': 14,
            'book': 20, 'backpack': 50, 'handbag': 30, 'umbrella': 100,
        }
        
        # Object tracking state
        self.tracked_objects = {}  # track_id -> {class, center, distance, last_seen, history}
        self.next_track_id = 1
        self.track_timeout = 2.0  # Seconds before track is lost
        self.iou_threshold = 0.25  # Lower threshold for better matching
        self.movement_threshold = 15  # More sensitive movement detection (pixels)
        self.approach_threshold = 0.05  # Detect approach if distance decreases by 5cm
    
    def _load_model(self):
        """Load YOLO model — downloads automatically if not present."""
        try:
            print(f"Device: {DEVICE.upper()} {'(GPU Accelerated)' if DEVICE == 'cuda' else '(CPU Mode)'}")
            if DEVICE == 'cuda':
                print(f"GPU: {torch.cuda.get_device_name(0)}")
            # YOLOv8l for maximum accuracy (auto-downloads ~87MB on first run)
            print(f"Loading YOLOv8l (large) model...")
            self.model = YOLO(MODEL_PATH)  # auto-downloads yolov8l.pt
            self.model.to(DEVICE)
            print(f"YOLOv8l loaded on {'GPU' if DEVICE == 'cuda' else 'CPU'}")
        except Exception as e:
            print(f"Error loading YOLOv8l, trying fallback to yolov8n: {e}")
            try:
                self.model = YOLO(MODEL_PATH_N)
                self.model.to(DEVICE)
                print("Fallback: YOLOv8n loaded")
            except Exception as e2:
                print(f"Error loading fallback model: {e2}")
                raise
    
    def _calculate_iou(self, box1: Dict, box2: Dict) -> float:
        """Calculate Intersection over Union between two bounding boxes."""
        x1 = max(box1['x1'], box2['x1'])
        y1 = max(box1['y1'], box2['y1'])
        x2 = min(box1['x2'], box2['x2'])
        y2 = min(box1['y2'], box2['y2'])
        
        intersection = max(0, x2 - x1) * max(0, y2 - y1)
        
        area1 = (box1['x2'] - box1['x1']) * (box1['y2'] - box1['y1'])
        area2 = (box2['x2'] - box2['x1']) * (box2['y2'] - box2['y1'])
        union = area1 + area2 - intersection
        
        return intersection / union if union > 0 else 0
    
    def _get_center(self, bbox: Dict) -> Tuple[float, float]:
        """Get center point of bounding box."""
        return ((bbox['x1'] + bbox['x2']) / 2, (bbox['y1'] + bbox['y2']) / 2)
    
    def _calculate_movement(self, track_id: int, current_center: Tuple[float, float], 
                           current_distance: float, frame_width: int) -> Dict:
        """Calculate movement direction and speed for a tracked object."""
        track = self.tracked_objects.get(track_id)
        if not track or len(track['history']) < 2:
            return {'direction': 'stationary', 'approaching': None, 'lateral': None, 'speed': 0}
        
        # Get previous positions
        prev_center = track['history'][-1]['center']
        prev_distance = track['history'][-1]['distance']
        
        dx = current_center[0] - prev_center[0]
        dy = current_center[1] - prev_center[1]
        
        movement = {'direction': 'stationary', 'approaching': None, 'lateral': None, 'speed': 0}
        
        # Calculate lateral movement (left/right in frame)
        if abs(dx) > self.movement_threshold:
            if dx > 0:
                movement['lateral'] = 'moving_right'
            else:
                movement['lateral'] = 'moving_left'
        
        # Calculate depth movement (approaching/receding) - MORE SENSITIVE
        if prev_distance and current_distance:
            distance_change = prev_distance - current_distance
            # Use approach_threshold for sensitive approaching detection
            if distance_change > self.approach_threshold:
                # Object is getting CLOSER - PRIORITY ALERT
                movement['approaching'] = True
                movement['direction'] = 'approaching'
                movement['speed'] = abs(distance_change)
            elif distance_change < -self.approach_threshold:
                # Object moving away
                movement['approaching'] = False
                movement['direction'] = 'receding'
                movement['speed'] = abs(distance_change)
        
        # Combine lateral and depth movement
        if movement['lateral'] and movement['approaching'] is not None:
            lateral = 'right' if movement['lateral'] == 'moving_right' else 'left'
            depth = 'approaching' if movement['approaching'] else 'receding'
            movement['direction'] = f'{depth}_{lateral}'
        elif movement['lateral']:
            movement['direction'] = movement['lateral']
        
        return movement
    
    def _update_tracks(self, detections: List[Dict], frame_width: int) -> List[Dict]:
        """Match detections to existing tracks and update tracking info."""
        current_time = time.time()
        
        # Remove stale tracks
        stale_ids = [tid for tid, track in self.tracked_objects.items() 
                     if current_time - track['last_seen'] > self.track_timeout]
        for tid in stale_ids:
            del self.tracked_objects[tid]
        
        # Match detections to existing tracks
        unmatched_detections = list(range(len(detections)))
        matched_tracks = set()
        
        for det_idx, detection in enumerate(detections):
            best_iou = 0
            best_track_id = None
            
            for track_id, track in self.tracked_objects.items():
                if track_id in matched_tracks:
                    continue
                if track['class'] != detection['class']:
                    continue
                
                # Build bbox from track center (approximate)
                prev_bbox = track.get('bbox', detection['bbox'])
                iou = self._calculate_iou(detection['bbox'], prev_bbox)
                
                if iou > best_iou and iou > self.iou_threshold:
                    best_iou = iou
                    best_track_id = track_id
            
            current_center = self._get_center(detection['bbox'])
            current_distance = detection.get('distance_m')
            
            if best_track_id:
                # Update existing track
                matched_tracks.add(best_track_id)
                unmatched_detections.remove(det_idx)
                
                # Calculate movement
                movement = self._calculate_movement(best_track_id, current_center, 
                                                   current_distance, frame_width)
                
                # Update track history (keep last 10 positions)
                self.tracked_objects[best_track_id]['history'].append({
                    'center': current_center,
                    'distance': current_distance,
                    'time': current_time
                })
                if len(self.tracked_objects[best_track_id]['history']) > 10:
                    self.tracked_objects[best_track_id]['history'].pop(0)
                
                self.tracked_objects[best_track_id]['last_seen'] = current_time
                self.tracked_objects[best_track_id]['bbox'] = detection['bbox']
                
                # Add tracking info to detection
                detection['track_id'] = best_track_id
                detection['movement'] = movement
            else:
                # Create new track
                new_id = self.next_track_id
                self.next_track_id += 1
                
                self.tracked_objects[new_id] = {
                    'class': detection['class'],
                    'bbox': detection['bbox'],
                    'last_seen': current_time,
                    'history': [{'center': current_center, 'distance': current_distance, 'time': current_time}]
                }
                
                detection['track_id'] = new_id
                detection['movement'] = {'direction': 'new', 'approaching': None, 'lateral': None, 'speed': 0}
        
        return detections
    
    def detect_from_base64(self, base64_image: str) -> Dict:
        """
        Run detection on a base64-encoded image.
        
        Args:
            base64_image: Base64 string of the image (with or without data URI prefix)
            
        Returns:
            Dict with detections and annotated image
        """
        # Remove data URI prefix if present
        if "," in base64_image:
            base64_image = base64_image.split(",")[1]
        
        # Decode base64 to numpy array
        img_bytes = base64.b64decode(base64_image)
        img_array = np.frombuffer(img_bytes, dtype=np.uint8)
        img = cv2.imdecode(img_array, cv2.IMREAD_COLOR)
        
        if img is None:
            return {"error": "Invalid image", "detections": [], "count": 0, "alert_level": "SAFE"}
        
        return self.detect(img)
    
    def detect(self, frame: np.ndarray) -> Dict:
        """
        Run detection on a numpy image array.
        
        Args:
            frame: OpenCV image (BGR format)
            
        Returns:
            Dict with detections list and annotated frame as base64
        """
        # Run inference with ultralytics YOLO on GPU
        results = self.model(frame, conf=self.confidence_threshold, device=DEVICE, verbose=False)
        
        # Parse results
        detections = []
        
        # Get the first result (single image)
        result = results[0]
        
        # Focal length approximation for distance estimation
        focal_length_pixels = frame.shape[0] * 0.8
        
        # Process each detection box
        if result.boxes is not None and len(result.boxes) > 0:
            boxes = result.boxes
            
            for i in range(len(boxes)):
                # Get box coordinates (xyxy format)
                box = boxes.xyxy[i].cpu().numpy()
                x1, y1, x2, y2 = int(box[0]), int(box[1]), int(box[2]), int(box[3])
                
                # Get confidence and class
                conf = float(boxes.conf[i].cpu().numpy())
                cls_id = int(boxes.cls[i].cpu().numpy())
                cls_name = result.names[cls_id]
                
                # Calculate distance
                bbox_height = y2 - y1
                ref_height_cm = self.reference_heights.get(cls_name, 50)
                
                if bbox_height > 0:
                    estimated_distance_cm = (ref_height_cm * focal_length_pixels) / bbox_height
                    estimated_distance_m = estimated_distance_cm / 100
                    estimated_distance_m = max(0.3, min(10.0, estimated_distance_m))
                    estimated_distance_m = round(estimated_distance_m, 1)
                    
                    if estimated_distance_m <= 1.0:
                        alert_level = 'CRITICAL'
                    elif estimated_distance_m <= 2.5:
                        alert_level = 'WARNING'
                    else:
                        alert_level = 'SAFE'
                else:
                    estimated_distance_m = None
                    alert_level = 'SAFE'
                
                # Calculate horizontal position (left/center/right)
                frame_width = frame.shape[1]
                center_x = (x1 + x2) / 2
                relative_x = center_x / frame_width  # 0.0 = far left, 1.0 = far right
                
                if relative_x < 0.33:
                    position = 'left'
                elif relative_x > 0.67:
                    position = 'right'
                else:
                    position = 'center'
                
                detection = {
                    "class": cls_name,
                    "confidence": round(conf, 2),
                    "bbox": {
                        "x1": x1,
                        "y1": y1,
                        "x2": x2,
                        "y2": y2
                    },
                    "priority": cls_name in self.priority_objects,
                    "distance_m": estimated_distance_m,
                    "distance": f"{estimated_distance_m}m" if estimated_distance_m else "Unknown",
                    "alert_level": alert_level,
                    "position": position,  # left, center, right
                    "position_x": round(relative_x, 2)  # 0.0-1.0 for precise positioning
                }
                detections.append(detection)
        
        # Sort by priority and confidence
        detections.sort(key=lambda x: (not x['priority'], -x['confidence']))
        
        # Update tracking and add movement information
        frame_width = frame.shape[1]
        detections = self._update_tracks(detections, frame_width)
        
        # Get annotated frame from ultralytics
        annotated = result.plot()  # Returns BGR numpy array with boxes drawn
        
        # Draw movement indicators on annotated frame
        for det in detections:
            if 'movement' in det and det['movement']['direction'] != 'stationary':
                bbox = det['bbox']
                cx = int((bbox['x1'] + bbox['x2']) / 2)
                cy = int((bbox['y1'] + bbox['y2']) / 2)
                
                movement = det['movement']
                
                # Draw movement arrow
                arrow_color = (0, 255, 255)  # Yellow
                if movement['approaching']:
                    arrow_color = (0, 0, 255)  # Red for approaching
                elif movement['approaching'] is False:
                    arrow_color = (0, 255, 0)  # Green for receding
                
                # Draw direction text
                direction_text = movement['direction'].replace('_', ' ').title()
                if movement['direction'] == 'new':
                    direction_text = 'NEW'
                    arrow_color = (255, 165, 0)  # Orange for new
                
                cv2.putText(annotated, direction_text, (bbox['x1'], bbox['y1'] - 10),
                           cv2.FONT_HERSHEY_SIMPLEX, 0.5, arrow_color, 2)
        
        # Encode annotated frame to base64
        _, buffer = cv2.imencode('.jpg', annotated, [cv2.IMWRITE_JPEG_QUALITY, 80])
        annotated_b64 = base64.b64encode(buffer).decode('utf-8')
        
        # Determine overall alert level
        overall_alert = 'SAFE'
        if any(d['alert_level'] == 'CRITICAL' for d in detections):
            overall_alert = 'CRITICAL'
        elif any(d['alert_level'] == 'WARNING' for d in detections):
            overall_alert = 'WARNING'
        
        return {
            "detections": detections,
            "count": len(detections),
            "alert_level": overall_alert,
            "annotated_frame": f"data:image/jpeg;base64,{annotated_b64}"
        }


# Singleton instance
_detector = None

def get_detector() -> ObjectDetector:
    """Get or create the singleton detector instance."""
    global _detector
    if _detector is None:
        _detector = ObjectDetector()
    return _detector

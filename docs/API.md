# VisionX — REST API Reference

**Base URL:** `http://localhost:5000`

---

## Auth

| Method | Endpoint | Body | Response |
|--------|----------|------|----------|
| POST | `/api/login` | `{username, password}` | `{success, token, username}` |
| POST | `/api/register` | `{username, password, email}` | `{success, token}` |
| POST | `/api/verify-token` | `{token}` | `{valid}` |

---

## AI — Detection

### POST `/api/detect`
YOLO object detection on a single frame.
```json
// Request
{ "image": "<base64-jpeg>" }

// Response
{
  "detections": [
    {
      "class": "person", "confidence": 0.87,
      "distance": "1.2m", "distance_m": 1.2,
      "position": "center-left",
      "alert_level": "CRITICAL",
      "movement": { "approaching": true },
      "bbox": { "x1": 10, "y1": 20, "x2": 200, "y2": 400 },
      "priority_score": 190.0,
      "should_announce": true
    }
  ],
  "count": 1,
  "alert_level": "CRITICAL",
  "annotated_frame": "<base64-jpeg-with-boxes>"
}
```

### POST `/api/analyze-frame`
Multi-modal parallel analysis (objects + gesture + emotion + pose + optional scene/depth).
```json
// Request
{ "image": "<b64>", "include_scene": true, "include_depth": false }
// Response: objects, gestures, emotions, poses, alert_level, scene_description, processing_ms
```

---

## AI — Specialized

| Method | Endpoint | Purpose |
|--------|----------|---------|
| POST | `/api/ocr` | EasyOCR text detection |
| POST | `/api/emotion` | FER emotion detection |
| POST | `/api/pose` | MediaPipe pose estimation |
| POST | `/api/gesture` | MediaPipe gesture recognition |
| GET  | `/api/gesture/latest` | Last debounced gesture |
| POST | `/api/depth` | MiDaS depth map + zone analysis |
| POST | `/api/fall-detect` | Fall detection from pose |
| POST | `/api/scene` | LLM scene description |
| POST | `/api/generate-alert` | Context-aware alert text |

---

## Voice

### POST `/api/voice/command`
```json
// Request
{ "transcript": "what is around me" }

// Response
{
  "action": "scene_describe",
  "result": "Scene description requested...",
  "speak": "...",
  "transcript": "what is around me"
}
```

**Recognized actions:**
`scene_describe` · `ocr_read` · `location_query` · `face_scan`
`currency_detect` · `nav_start` · `nav_stop` · `sos_trigger`

---

## Device

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/gps` | Current GPS coordinates |
| POST | `/api/gps` | Update GPS from ESP32 |
| GET | `/api/status` | Device online/battery/alert + announcements |
| POST | `/api/status` | ESP32 heartbeat |
| GET | `/api/distance` | HC-SR04 distance reading |
| GET | `/api/stream` | MJPEG stream proxy from ESP32 |

---

## Faces

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/faces` | List enrolled people |
| POST | `/api/faces` | Enroll new person `{name, photo}` |
| DELETE | `/api/faces/<id>` | Remove person |
| GET | `/api/faces/photo/<id>` | Get person photo |
| GET | `/api/family/recent` | Recent face sightings log |

---

## System

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/health` | `{status: "ok", time}` |
| GET | `/api/system` | CPU, RAM, GPU, FPS, uptime |
| GET | `/api/scheduler/status` | Queue stats + active modules |
| GET | `/api/context` | Smart prioritizer context memory |

---

## Logs

| Method | Endpoint | Query | Description |
|--------|----------|-------|-------------|
| GET | `/api/logs` | `?kind=events&limit=100` | Read JSONL logs |
| DELETE | `/api/logs` | `?kind=events` | Clear log file |

**Log kinds:** `events` · `detections` · `performance`

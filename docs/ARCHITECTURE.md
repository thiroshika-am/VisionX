# VisionX — System Architecture

## Overview

```
┌─────────────────────────────────────────────────────────────────────┐
│                         VisionX AI System                            │
│                                                                      │
│  ┌──────────────┐   HTTP MJPEG   ┌──────────────────────────────┐   │
│  │  ESP32-CAM   │ ─────────────► │      Flask Backend           │   │
│  │  Wearable    │                │                              │   │
│  └──────────────┘                │  ┌────────────────────────┐  │   │
│         ▲                        │  │     AI Scheduler       │  │   │
│  USB HID │                       │  │  (Priority Queue)      │  │   │
│  ┌──────────────┐                │  └────────┬───────────────┘  │   │
│  │  Ultrasonic  │                │           │                   │   │
│  │  + Vibration │                │  ┌────────▼───────────────┐  │   │
│  └──────────────┘                │  │    AI Modules          │  │   │
│                                  │  │  ┌─────────────────┐   │  │   │
│                                  │  │  │ YOLO Detection  │   │  │   │
│                                  │  │  │ Depth (MiDaS)   │   │  │   │
│                                  │  │  │ Face Recog.     │   │  │   │
│                                  │  │  │ Gesture (MP)    │   │  │   │
│                                  │  │  │ Emotion (FER)   │   │  │   │
│                                  │  │  │ Pose (MP)       │   │  │   │
│                                  │  │  │ OCR (EasyOCR)   │   │  │   │
│                                  │  │  │ Scene (LLM)     │   │  │   │
│                                  │  │  │ Smart Priority  │   │  │   │
│                                  │  │  │ Fall Detector   │   │  │   │
│                                  │  │  └─────────────────┘   │  │   │
│                                  │  └────────────────────────┘  │   │
│                                  │           │                   │   │
│                                  │  ┌────────▼───────────────┐  │   │
│                                  │  │  Structured Logging    │  │   │
│                                  │  └────────────────────────┘  │   │
│                                  └──────────────┬───────────────┘   │
│                                                 │ REST API           │
│                                  ┌──────────────▼───────────────┐   │
│                                  │    Frontend Dashboard         │   │
│                                  │  (5-Tab Glassmorphism UI)     │   │
│                                  └──────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────┘
```

## Module Registry

| Module | File | Always-On | Latency |
|--------|------|-----------|---------|
| YOLO Object Detection | `ai_modules/detector.py` | ✅ | ~60ms |
| Depth Estimation | `src/ai/depth_estimator.py` | Opt. | ~150ms |
| Face Recognition | `ai_modules/face_recognition_engine.py` | Periodic | ~30ms |
| Gesture Recognition | `ai_modules/gesture_engine.py` | Periodic | ~15ms |
| Emotion Detection | `ai_modules/emotion_engine.py` | On-demand | ~50ms |
| Pose Estimation | `ai_modules/pose_engine.py` | On-demand | ~20ms |
| OCR | `ai_modules/ocr_engine.py` | On-demand | ~300ms |
| Fall Detection | `src/ai/fall_detector.py` | Periodic | ~30ms |
| Smart Prioritizer | `src/ai/smart_prioritizer.py` | Always-On | <1ms |
| Scene Understanding | `ai_modules/llm_alerts.py` | On-demand | ~500ms |
| Voice Commander | `ai_modules/voice_commander.py` | On-demand | <1ms |
| Currency Detector | `ai_modules/currency_detector.py` | On-demand | ~100ms |
| System Monitor | `src/core/system_monitor.py` | Background | <1ms |
| Structured Logger | `src/core/logger.py` | Background | <1ms |

## Flask Routes (Blueprint Architecture)

| Blueprint | Prefix | File |
|-----------|--------|------|
| Auth | `/api/login`, `/api/register` | `backend/routes/auth_routes.py` |
| AI | `/api/detect`, `/api/ocr`, `/api/analyze-frame`, ... | `backend/routes/ai_routes.py` |
| Device | `/api/gps`, `/api/status`, `/api/stream` | `backend/routes/device_routes.py` |
| System | `/api/system`, `/api/scheduler/status` | `backend/routes/system_routes.py` |
| Logs | `/api/logs` | `backend/routes/logs_routes.py` |

## AI Priority Schedule

```
CRITICAL (P0):  Obstacle alerts, SOS, Fall detection
HIGH (P1):      User voice commands (scene, OCR, currency)
MEDIUM (P2):    Face recognition, Emotion
LOW (P3):       Gesture recognition, Pose
```

## Smart Prioritizer Logic

```
score = category_base
      + alert_level_boost     (CRITICAL +60, WARNING +30)
      + approaching_boost      (+50 if moving toward camera)
      + proximity_boost        (+40 if < 1m, +20 if < 2.5m)
      - cooldown_penalty       (-50 if announced recently)

High score → announce first
Low score  → suppress (still detected, just not spoken)
```

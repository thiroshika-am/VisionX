# VisionX — AI Wearable Assistant for the Visually Impaired

<div align="center">

![VisionX](https://img.shields.io/badge/VisionX-AI%20Wearable-00D4FF?style=for-the-badge)
![Python](https://img.shields.io/badge/Python-3.10+-blue?style=for-the-badge&logo=python)
![Flask](https://img.shields.io/badge/Flask-3.0-black?style=for-the-badge&logo=flask)
![YOLO](https://img.shields.io/badge/YOLO-v11n-purple?style=for-the-badge)
![MediaPipe](https://img.shields.io/badge/MediaPipe-0.10-red?style=for-the-badge)

**Real-time AI-powered wearable assistant that helps visually impaired people understand their surroundings through computer vision and speech.**

</div>

---

## Architecture

```
ESP32-CAM ──MJPEG──► Flask Backend ──► AI Modules ──► Frontend Dashboard
```

**14 AI modules** running on a priority scheduler — from YOLO object detection to depth estimation, face recognition, gesture, emotion, OCR, and fall detection.

## Features

| Feature | Technology |
|---------|-----------|
| 🎯 Object Detection | YOLO11n (20-30 FPS on Pi 5) |
| 🌊 Depth Estimation | MiDaS_small ONNX |
| 👤 Face Recognition | YuNet + SFace (offline) |
| ✋ Gesture Recognition | MediaPipe GestureRecognizer |
| 😊 Emotion Detection | FER / OpenCV DNN |
| 🧘 Pose Estimation | MediaPipe PoseLandmarker |
| 📝 OCR | EasyOCR (multilingual) |
| 🌍 Scene Description | LLM (Groq → Gemini → Template) |
| 🎤 Voice Commands | Web Speech API |
| 🆘 Fall Detection | Pose + YOLO bbox analysis |
| 🧠 Smart Prioritizer | Context memory, cooldowns |
| 📍 GPS | Browser Geolocation + ESP32 |
| 💵 Currency Detection | Custom CNN |
| 📊 System Monitor | psutil + real-time FPS |

## Quick Start

```bash
# 1. Install dependencies
pip install -r config/requirements.txt

# 2. Run backend
python backend/main.py

# 3. Open dashboard
# http://localhost:5000
```

## Hardware (Wearable Build)

- **Raspberry Pi 5** (4 GB) — main AI compute
- **ESP32-CAM** (AI-Thinker, 160° lens) — camera + WiFi stream
- **HC-SR04** ultrasonic sensor (wired to ESP32)
- **Haptic motor** (vibration feedback via ESP32 GPIO)
- **Bone conduction headphones** — audio feedback
- **10 000 mAh** USB-C power bank — 6+ hours runtime

## Dashboard Tabs

| Tab | Description |
|-----|-------------|
| 👁 **Live** | Camera feed with detection overlay, scene description, voice shortcuts |
| 🎯 **Detections** | Detection history grid with priority/distance/emotion/pose |
| 🎤 **Voice** | Voice command interface, TTS controls, command history |
| 🗺 **Map** | GPS map (Leaflet), device status panel |
| 👤 **Faces** | Known faces enrolment and recent sightings |
| ⚡ **System** | CPU/RAM/GPU gauges, FPS counter, AI module status, event log |

## Voice Commands

| Say | Action |
|-----|--------|
| "What's around me?" | Full scene description |
| "Read this" | OCR the current frame |
| "Who is near me?" | Face recognition scan |
| "Where am I?" | Read GPS coordinates |
| "What bill is this?" | Currency identification |
| "Help" / "SOS" | Emergency alert + vibration |

## Project Structure

```
VisionX/
├── backend/
│   ├── main.py              # Slim Flask entry point
│   ├── state.py             # Shared mutable state
│   ├── routes/              # Flask Blueprints (5 files)
│   └── workers/             # Background AI + watchdog
├── ai_modules/              # All AI engines (preserved + upgraded)
├── src/
│   ├── ai/                  # New: depth, fall, prioritizer, scene
│   └── core/                # New: system_monitor, logger
├── frontend/                # Premium 5-tab glassmorphism dashboard
├── config/                  # backend_config.json, requirements.txt
├── docs/                    # ARCHITECTURE, INSTALL, API, DEMO_SCRIPT
├── tests/                   # pytest test suite
└── logs/                    # JSONL structured logs (auto-created)
```

## Run Tests

```bash
pytest tests/ -v                          # fast tests only
VISIONX_FULL_TESTS=1 pytest tests/ -v    # include slow OCR test
```

## License
MIT — Built for accessibility.

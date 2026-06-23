# 🎯 Smart AI Cap — TODO List

> Blind Obstacle Detection System with ESP32-CAM + GPS Tracking  
> Last updated: 2026-02-15

---

## ✅ Completed

- [x] Project cleanup — removed old model files (YOLO .pt, OpenVINO), dev scripts, and test suites
- [x] ESP32-CAM firmware (`firmware/esp32_main.cpp`)
- [x] Frontend dashboard — live camera feed + GPS location map
- [x] Backend API — serves camera stream proxy & GPS data
- [x] Project restructure

---

## 🔧 Hardware Setup

- [ ] Flash ESP32-CAM with `firmware/esp32_main.cpp`
- [ ] Configure WiFi SSID & password in firmware
- [ ] Configure backend server IP in firmware
- [ ] Wire HC-SR04 ultrasonic sensor (Trigger → GPIO12, Echo → GPIO13)
- [ ] Wire IR Obstacle Sensor (OUT → GPIO 2)
- [ ] Wire vibration motor (→ GPIO14)
- [ ] Connect GPS module (NEO-6M) → ESP32 (TX → GPIO16)
- [ ] Power system — Li-Po 5000mAh battery + voltage regulator
- [ ] 3D print or build cap enclosure

---

## 🖥️ Backend

- [ ] Add real ESP32-CAM stream URL configuration (replace placeholder)
- [ ] Implement WebSocket for real-time GPS updates from ESP32
- [ ] Add obstacle detection alert forwarding to frontend
- [ ] Add distance sensor data API endpoint
- [ ] Implement battery level monitoring endpoint
- [ ] Add device connection status (online/offline detection)
- [ ] Logging & error recovery for dropped ESP32 connections

---

## 🌐 Frontend

- [ ] Connect to real ESP32 camera stream (currently uses placeholder)
- [ ] Add real-time GPS tracking from ESP32 GPS module
- [ ] Add obstacle alert notifications (visual + audio)
- [ ] Add distance sensor readout widget
- [ ] Add battery status indicator
- [ ] Add device connection status indicator (green/red dot)
- [ ] Add alert history / event log panel
- [ ] Mobile-responsive layout improvements
- [ ] Add settings panel (configure ESP32 IP, alert thresholds, etc.)

---

## 📡 ESP32 Firmware

- [ ] Add GPS module integration (NMEA parsing → lat/lng)
- [ ] Add GPS data to sensor packet sent to backend
- [ ] Implement MJPEG streaming endpoint (`/stream`)
- [ ] Add OTA (Over-The-Air) firmware update support
- [ ] Implement deep-sleep wake on motion for battery saving
- [ ] Add BLE fallback when WiFi is unavailable
- [ ] Calibrate ultrasonic sensor for outdoor use

---

## 🧪 Testing

- [ ] Test ESP32 → Backend frame transmission over WiFi
- [ ] Test GPS accuracy outdoors
- [ ] Test frontend camera feed latency
- [ ] Test map location accuracy
- [ ] Battery life test (target: 8+ hours)
- [ ] Range test (WiFi distance from router)

---

## 📦 Deployment

- [ ] Docker container for backend + frontend
- [ ] Docker Compose for easy deployment
- [ ] Setup guide for Raspberry Pi deployment
- [ ] Setup guide for TrueNAS / NAS deployment

---

## 🚀 Future Enhancements

- [ ] AI object detection on backend (YOLO / TFLite)
- [ ] Voice alerts via TTS (text-to-speech)
- [ ] Geofencing alerts (safe zone boundaries)
- [ ] Caregiver mobile app (companion tracking)
- [ ] Multi-device support (track multiple blind users)
- [ ] Cloud dashboard for remote monitoring

---

## 👁️ Vision Enhancements (Planned)

- [ ] Implement Monocular Depth Estimation (e.g., MiDaS) to replace hardcoded height-based distance heuristics.
- [ ] Add Pathway & Surface Segmentation (YOLO-seg or MobileNet) to explicitly detect walkable paths vs hazards.
- [ ] Implement Low-Light Image Enhancement (e.g., Zero-DCE) preprocessing for better ESP32-CAM night vision.
- [ ] Train/Tune specialized hazard detection models for blind-specific hazards (potholes, low-hanging branches, traffic lights).
- [ ] Optimize models for Edge Processing (TFLite/TensorRT) to reduce latency.

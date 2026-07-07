# VisionX — Installation Guide

## Laptop / PC (Development)

```bash
# 1. Clone
git clone <repo> VisionX && cd VisionX

# 2. Create virtualenv
python -m venv .venv
.venv\Scripts\activate          # Windows
# source .venv/bin/activate     # Linux/Mac

# 3. Install dependencies
pip install -r config/requirements.txt

# 4. Run backend
python backend/main.py

# 5. Open browser
# http://localhost:5000
```

> **Login**: Register on first launch or use the default credentials if set.

---

## Raspberry Pi 5 (Production)

### Hardware
- Raspberry Pi 5 (4 GB+ RAM recommended)
- ESP32-CAM (AI Thinker, 160° wide-angle lens)
- HC-SR04 ultrasonic sensor (optional, wired to ESP32)
- Haptic motor / vibration module (on ESP32 GPIO)
- Bone conduction headphones or earpiece
- 10 000 mAh USB-C power bank

### Install OS
```
Raspberry Pi OS Lite (64-bit, Bookworm)
```

### System Dependencies
```bash
sudo apt update && sudo apt upgrade -y
sudo apt install -y python3-pip python3-venv libopencv-dev \
    libatlas-base-dev libjpeg-dev portaudio19-dev \
    ffmpeg espeak libespeak1
```

### Python
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r config/requirements.txt
```

### Auto-start (systemd)
```bash
sudo nano /etc/systemd/system/visionx.service
```

```ini
[Unit]
Description=VisionX AI Backend
After=network.target

[Service]
User=pi
WorkingDirectory=/home/pi/VisionX
ExecStart=/home/pi/VisionX/.venv/bin/python backend/main.py
Restart=on-failure
RestartSec=5

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl enable visionx
sudo systemctl start visionx
```

---

## ESP32-CAM Setup

1. Flash `esp32_cam/esp32_cam.ino` using Arduino IDE
2. Set your WiFi credentials in the sketch
3. Note the IP printed to Serial Monitor
4. Update `config/backend_config.json`:
```json
{
  "esp32": {
    "stream_url": "http://<ESP32_IP>:80/stream"
  }
}
```

---

## First Run Checklist
- [ ] Backend starts without error: `python backend/main.py`
- [ ] Dashboard loads: `http://localhost:5000`
- [ ] Register an account
- [ ] Camera feed appears in Live tab
- [ ] Detections display with bounding boxes
- [ ] Voice command responds to "what's around me"
- [ ] (Optional) ESP32-CAM stream replaces webcam

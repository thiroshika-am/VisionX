# 🔌 How to Connect ESP32-CAM to the SmartCap Dashboard

> Step-by-step guide to get your ESP32-CAM streaming live video to the dashboard.

---

## 📋 What You Need

| Item | Purpose |
|------|---------|
| **ESP32-CAM** (AI-Thinker) | Camera + WiFi module |
| **FTDI USB-to-Serial adapter** (or ESP32-CAM-MB board) | For flashing firmware |
| **Jumper wires** | Connecting FTDI to ESP32-CAM |
| **Your PC** running the backend server | Receives stream & serves dashboard |
| **WiFi Router** | Both ESP32 and PC must be on the **same WiFi network** |

---

## 🛠️ Step-by-Step Setup

### Step 1: Find Your PC's IP Address

Open PowerShell on your PC and run:

```powershell
ipconfig
```

Look for **"IPv4 Address"** under your WiFi adapter. It will look like:

```
IPv4 Address. . . . . . . . . . . : 192.168.1.5
```

**Write this down** — you'll need it in the next step.

---

### Step 2: Edit the ESP32 Firmware

Open `firmware/esp32_main.cpp` and find these 3 lines near the top (around line 58):

```cpp
#define WIFI_SSID          "your_wifi_ssid"        // ← PUT YOUR WIFI NAME HERE
#define WIFI_PASSWORD      "your_wifi_password"    // ← PUT YOUR WIFI PASSWORD HERE
#define BACKEND_IP         "192.168.x.x"           // ← PUT YOUR PC's IP ADDRESS HERE
```

**Replace them with your actual values:**

```cpp
#define WIFI_SSID          "MyHomeWifi"            // Your actual WiFi name
#define WIFI_PASSWORD      "mypassword123"         // Your actual WiFi password
#define BACKEND_IP         "192.168.1.5"           // Your PC's IP from Step 1
```

---

### Step 3: Flash the Firmware to ESP32-CAM

#### Option A: Using Arduino IDE (Recommended for beginners)

1. **Install Arduino IDE** from https://www.arduino.cc/en/software

2. **Add ESP32 board support:**
   - Go to `File → Preferences`
   - In **"Additional Board Manager URLs"**, paste:
     ```
     https://raw.githubusercontent.com/espressif/arduino-esp32/gh-pages/package_esp32_index.json
     ```
   - Go to `Tools → Board → Board Manager`
   - Search **"ESP32"** and install **"esp32 by Espressif Systems"**

3. **Select the board:**
   - `Tools → Board → ESP32 Arduino → AI Thinker ESP32-CAM`

4. **Wire the FTDI adapter to ESP32-CAM:**

   ```
   FTDI          ESP32-CAM
   ────          ─────────
   5V     →      5V
   GND    →      GND
   TX     →      U0R (GPIO 3)
   RX     →      U0T (GPIO 1)
   
   ⚠️ IMPORTANT: Connect GPIO 0 to GND to enter flash mode!
   ```

   Or if you have the **ESP32-CAM-MB** USB adapter board, just plug the ESP32-CAM directly onto it and connect via USB.

5. **Upload:**
   - Select `Tools → Port → COM?` (your FTDI COM port)
   - Click **Upload** (→ arrow button)
   - When you see `Connecting........_____`, press the **RST** button on the ESP32-CAM

6. **After upload:**
   - **Disconnect GPIO 0 from GND**
   - Press **RST** to reboot in normal mode

#### Option B: Using PlatformIO (for advanced users)

```bash
# platformio.ini
[env:esp32cam]
platform = espressif32
board = esp32cam
framework = arduino
monitor_speed = 115200
```

Then run: `pio run -t upload`

---

### Step 4: Check the ESP32 Serial Output

Open the **Serial Monitor** in Arduino IDE (`Tools → Serial Monitor`, baud rate `115200`).

You should see output like:

```
===== Smart AI Cap Startup =====
✓ GPIO pins initialized
✓ Camera initialized
.....
WiFi Connected!
IP address: 192.168.1.100       ← This is your ESP32's IP!
Signal strength (RSSI): -45 dBm
✓ Bluetooth initialized
✓ Interrupts configured
HTTP server started at http://192.168.1.100:80
===== Startup Complete =====
```

**Write down the ESP32's IP address** (e.g., `192.168.1.100`).

---

### Step 5: Update the Backend Config

Open `config/backend_config.json` and replace the ESP32 IP:

```json
{
  "esp32": {
    "stream_url": "http://192.168.1.100:80/stream",
    "status_url": "http://192.168.1.100:80/status",
    "distance_url": "http://192.168.1.100:80/distance",
    "frame_url": "http://192.168.1.100:80/frame"
  },
  "network": {
    "backend_ip": "0.0.0.0",
    "backend_port": 5000
  },
  "alert_settings": {
    "critical_distance_cm": 50,
    "warning_distance_cm": 100
  }
}
```

Replace all `192.168.1.100` with your ESP32's actual IP from Step 4.

---

### Step 6: Start the Backend

```bash
pip install -r config/requirements.txt
python backend/main.py
```

You should see:

```
==================================================
  SMART AI CAP — Backend Server
  Frontend: http://localhost:5000
  ESP32 Stream: http://192.168.1.100:80/stream
==================================================
```

---

### Step 7: Open the Dashboard! 🎉

Open your browser and go to:

**👉 http://localhost:5000**

You should see:
- **Live camera feed** from the ESP32-CAM
- **Device status** showing "ESP32 Online" (green dot)
- **Distance readings** from the ultrasonic sensor
- **GPS map** (placeholder until GPS module is added)

---

## 🔧 Troubleshooting

### Camera shows "Waiting for ESP32-CAM…"

| Check | Fix |
|-------|-----|
| ESP32 not connected to WiFi | Serial monitor should show "WiFi Connected!" |
| Wrong IP in config | Make sure `config/backend_config.json` has the correct ESP32 IP |
| Firewall blocking | Allow port 80 (ESP32) and 5000 (backend) through Windows Firewall |
| Not on same WiFi | ESP32 and your PC must be on the **exact same** WiFi network |

### Test ESP32 directly

Before using the dashboard, test the ESP32 directly in your browser:

```
http://192.168.1.100/status     → Should return JSON status
http://192.168.1.100/frame      → Should show a single camera snapshot
http://192.168.1.100/stream     → Should show live MJPEG video feed
http://192.168.1.100/distance   → Should return distance in mm
```

### Device shows "Offline"

The ESP32 sends a heartbeat every 5 seconds to `/api/status`. If the backend doesn't receive one for 30 seconds, it marks the device as offline.

- Make sure the `BACKEND_IP` in the firmware points to your PC's IP
- Make sure port 5000 isn't blocked by firewall

---

## 📊 How It All Connects

```
┌──────────────┐         WiFi          ┌──────────────┐       Browser        ┌──────────────┐
│              │ ──── /stream ────────▶ │              │  ── localhost:5000 ─▶│              │
│   ESP32-CAM  │ ──── heartbeat POST ─▶│    Backend    │                     │   Dashboard  │
│   (cap)      │◀──── /api commands ───│    (Python)   │◀─── API calls ──────│   (Browser)  │
│              │                       │  port 5000    │                     │              │
└──────────────┘                       └──────────────┘                      └──────────────┘
      |                                                                           |
  Captures video                                                          Shows live feed
  Reads sensors                                                           Shows GPS map
  Sends data                                                              Shows alerts
```

---

## 📌 Quick Reference — Endpoints

### ESP32 HTTP Server (port 80)

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/status` | GET | Device status (RSSI, uptime, alert level) |
| `/distance` | GET | Ultrasonic distance in mm |
| `/frame` | GET | Single JPEG snapshot |
| `/stream` | GET | MJPEG live video stream |

### Backend API (port 5000)

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/stream` | GET | Proxied ESP32 camera stream |
| `/api/gps` | GET | Latest GPS coordinates |
| `/api/gps` | POST | ESP32 posts GPS data |
| `/api/status` | GET | Device status |
| `/api/status` | POST | ESP32 heartbeat (every 5s) |
| `/api/distance` | GET | Proxied distance reading |
| `/api/health` | GET | Backend health check |

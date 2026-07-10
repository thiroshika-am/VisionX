# 🔌 Smart AI Cap - Wiring Diagram

This guide details how to wire the components for the Smart AI Cap project based on the current firmware configuration.

## 🧠 Core Component: ESP32-CAM (AI-Thinker)

The project uses the **ESP32-CAM** module to handle both vision and sensors.

> **⚠️ PINOUT WARNING:** The ESP32-CAM has limited available pins.  We must use specific pins to avoid conflicts with the camera, SD card, or boot process.

### 📊 Implementation Status
- ✅ **HC-SR04 Ultrasonic Sensor** - Fully implemented
- ✅ **Vibration Motor (PWM Control)** - Fully implemented  
- ✅ **Status LED** - Fully implemented
- ⏳ **IR Sensor** - Not yet implemented in current firmware
- ⏳ **GPS Module** - Not yet implemented in current firmware

---

## 📐 Visual Wiring Structure (Current Implementation)

```text
       [ POWER SOURCE (5V) ] 
               | + (Red)
               v
      /------------------\ 
      |  ESP32-CAM Board | 
      |                  |
      |          GND o---+----------------------------------------+-----------------+---+
      |                  |                                        |                 |   |
      |           5V o---+--------------------+-------------------|-----------------|---|------+
      |                  |                    |                   |                 |   |      |
      |      GPIO 12 o---|--------------------|----[ Trig ]       |                 |   |      |
      |      GPIO 13 o---|--------------------|----[ Echo ]       |                 |   |      |
      |                  |                    | (HC-SR04)         |                 |   |      |
      |                  |                    |                   |                 |   |      |
      |      GPIO 14 o---|--------------------|----[ PWM ]        |                 |   |      |
      |                  |                    |  (Vibration)      |                 |   |      |
      |                  |                    |                   |                 |   |      |
      |      GPIO 33 o---|--------------------|-------------------|----[ + ]        |   |      |
      |                  |                    |                   |  (Status LED)   |   |      |
      |                  |                    |                   |    (via ~470Ω) |   |      |
      |                  |                    |                   |                 |   |      |
      |                  |                    |                   |                 |   |      |
      \------------------/                    |                   |                 |   |      |
                                              |                   |                 |   |      |
                                           [ GND ]             [ GND ]           [ GND ][ GND ]
```

## 📌 Pin Allocation Reference

**Available External Pins** (after accounting for camera & SD card):
```text
   Pins Used by Camera/SD:    0, 5, 18, 19, 21, 22, 23, 25, 26, 27, 32, 34, 35, 36, 39
   
   Safe Pins for Sensors:     12, 13, 14, 15, 2, 4, 16, 17
   
   ⚠️ Boot-Critical Pins:
   - GPIO 0:  Strapping pin (must not be pulled LOW during boot - reserved for flashing)
   - GPIO 2:  Strapping pin (must not be pulled LOW during boot - used in camera Y2)
   - GPIO 15: Strapping pin (must not be pulled HIGH during boot)
   - GPIO 13: Can have issues with some sensor configurations
```

---

## 📝 Pin Connection Table (Current Implementation)

| Component | Pin Label | ESP32-CAM GPIO | Type | Description |
| :--- | :--- | :--- | :--- | :--- |
| **HC-SR04** | VCC | **5V** | Power | Power supply |
| | GND | **GND** | Ground | Common ground |
| | Trig | **GPIO 12** | Output | Trigger pulse (0→1→0, 10µs) |
| | Echo | **GPIO 13** | Input | Echo pulse measure (via 10kΩ pull-down) |
| **Vibration Motor** | VCC | **5V** | Power | Motor power (via FET/transistor) |
| | GND | **GND** | Ground | Common ground |
| | PWM In | **GPIO 14** | Output | PWM control signal (via 1kΩ series R) |
| **Status LED** | Anode (+) | **GPIO 33** | Output | Indicator LED |
| | Cathode (-) | **GND** | Ground | via ~470Ω current limiting resistor |

### 📡 Future Components (Not Yet Implemented)

| Component | Pin Label | Suggested GPIO | Notes |
| :--- | :--- | :--- | :--- |
| **IR Sensor** | VCC | **5V / 3.3V** | ⏳ Reserved for future implementation |
| | GND | **GND** | Ground |
| | OUT | **GPIO 4** or **GPIO 17** | (Avoid GPIO 2 - conflicts with camera Y2) |
| **GPS (NEO-6M)** | VCC | **5V / 3.3V** | ⏳ Reserved for future implementation |
| | GND | **GND** | Ground |
| | TX | **GPIO 16** (U2RX) | Serial data input |
| | RX | **Not needed** | ESP32 doesn't need to transmit to GPS |

### ⚠️ Critical Design Notes

#### 1️⃣ **Boot Pin Behavior (Critical for Flashing)**
- **GPIO 0**: MUST be HIGH to run normally. Pull to GND only during flashing. If any sensor pulls it LOW, flashing will fail.
- **GPIO 2**: Part of camera data line (Y2). Also acts as strapping pin. Should not be used for external sensors.
- **GPIO 15**: Should not be pulled HIGH during boot. Can cause boot issues.
- **GPIO 13**: Can sometimes interfere with boot sequence under high load conditions.

**Current Setup Impact**: GPIO 12 & 13 are safe but placed with caution because:
- They're not camera pins (unlike 5, 18, 19, 21-27)
- Not boot-critical strapping pins (unlike 0, 2, 15)
- Echo pin (GPIO 13) should have a 10kΩ pull-down resistor to ensure clean LOW state during boot

#### 2️⃣ **Voltage Level Shifting (Important!)**
The HC-SR04 sensor outputs 5V on the Echo pin, but ESP32 GPIO accepts max 3.3V.
- **SOLUTION**: Use a voltage divider for Echo pin:
  ```
  Echo (5V) ---|100kΩ|--+--GPIO13(3.3V max)
                        |
                      10kΩ
                        |
                       GND
  ```
- Or simpler: Use a 10kΩ pull-down resistor to clamp the signal

#### 3️⃣ **Power Supply & Current Draw**
The ESP32-CAM draws significant current:
- **Idle**: ~80mA
- **WiFi Active**: ~150-250mA
- **Camera + WiFi**: **300-500mA** (peaks to 1A during transmission)
- **Vibration Motor** (5V): ~300-500mA when active

**Recommended Power Setup**:
- Use a **separate 5V regulated power supply** (2A+ rated), NOT laptop USB
- Use good quality **shielded USB cable** or power leads < 1m
- Add **100µF electrolytic + 0.1µF ceramic capacitors** across 5V and GND near ESP32-CAM
- **Keep battery leads short** to minimize voltage drop

#### 4️⃣ **Status LED Configuration**
GPIO 33 drives the status indicator:
- **Circuit**: GPIO 33 → 470Ω resistor → LED anode → LED cathode → GND
- Current at 3.3V: (3.3 - 2.0V) / 470Ω ≈ 2.8mA (safe for GPIO pin)
- If using high-brightness LED, reduce resistor to 220Ω

#### 5️⃣ **Vibration Motor Control**
GPIO 14 outputs PWM signals but cannot drive motors directly:
- **Required Circuit**: 
  ```
  GPIO14(3.3V) ---|1kΩ|--[MOSFET Gate]
                          [   (e.g., 2N7000 or IRF520N) ]
                          [   Drain → +5V ]
                          [ Source → Motor+ ]
                          [   Motor- → GND ]
  ```
- Gate pull-down: 10kΩ to GND (for stability)
- Motor back-EMF protection: Add diode across motor terminals

#### 6️⃣ **HC-SR04 Timing Considerations**
- **Trigger Duration**: Must be 10µs (firmware handles this)
- **Echo Pulse Range**: 150µs (3cm) to 23,200µs (400cm)
- **Sensor Frequency**: Max ~50Hz (measurement every 20ms)
- Currently configured: 100ms interval between measurements

---

## 🔧 Dual-Board Architecture (Recommended for Future Expansion)

If you want to add more sensors or reduce power draw on the camera module, use a separate **standard ESP32 Dev Board**:

```
┌──────────────────────────────────┐     ┌─────────────────────────────────┐
│     ESP32-CAM Board              │     │    ESP32 Dev Board (I2C/UART)   │
│  (Camera + WiFi Stream)          │     │  (Sensors + Control Logic)      │
│                                  │     │                                 │
│  Duties:                         │     │  Duties:                        │
│  • Image capture/compression     │     │  • HC-SR04 ultrasonic          │
│  • WiFi video streaming          │◄────┤  • IR sensor (GPIO inputs)     │
│  • Low-level camera control      │ I2C │  • Vibration motor (PWM)       │
│  • SPIFFS file storage           │     │  • GPS serial (UART)           │
│                                  │     │  • Voice output (I2S/DAC)      │
│                                  │     │  • Bluetooth control            │
│                                  │     │  • Battery management           │
└──────────────────────────────────┘     └─────────────────────────────────┘
         5V Power                                   5V Power
         Common GND <──────────────────────────────────────>
              
              ↓ WiFi/UART Connection ↓
              
        ➡️ Backend Server (Flask/Python)
```

**Advantages**:
- More GPIO pins available for future sensors
- Better power distribution
- Separated concerns (vision vs. sensors)
- Easier to debug individual modules

**Implementation**: Requires firmware changes to support dual-board I2C/UART communication Protocol (see `firmware/esp32_main.cpp` for expansion points)

---

## 🔧 Detailed Sensor Schematics

### HC-SR04 Ultrasonic Sensor Wiring

```
        ┌────────────────────────────────────────────┐
        │         HC-SR04 Module                     │
        │  ┌──────────────────────────────────┐      │
        │  │ [1] VCC  [2] Trig [3] Echo [4]GND│      │
        │  └──────────────────────────────────┘      │
        └─┬──────────────────────────────────────────┘
          │

   5V ────┴──→ [1] VCC              
                [2] Trig ──────→ GPIO 12 (ESP32-CAM)
                [3] Echo ──100kΩ┬──→ GPIO 13 (via pull-down)
                           10kΩ │
                                GND
                [4] GND ────────→ GND (ESP32-CAM)

   Distance Calculation:
   distance(cm) = (echo_time_µs / 2) / 29.1
   Example: 580µs echo → 10cm distance
```

### Vibration Motor PWM Control

```
   5V ──────────[100µF Electrolytic]──────┐
                       GND                  │
                                           │
   GPIO 14 ──[1kΩ]──┬──[MOSFET Gate]      │
   (ESP32-CAM)     │                       │
              [10kΩ│pull-down]             │ 
                    │                       │
                   GND                      │
                                           │
                             ┌─[Drain]─────┴┬──→ Motor +
                             │              │
                         2N7000 or      [100nF]
                         IRF520N         (decoupling)
                             │              │
                             └─[Source]─────┴──→ Motor -
                                               │
                                              1N4007 Diode
                                               (back-EMF protection)
                                              
   PWM Settings (firmware):
   • Frequency: 5000 Hz
   • Duty Cycle: 0-255 (0% to 100%)
   • Intensity Levels:
     - 0-50:   Weak vibration (warning)
     - 50-150: Medium vibration (caution)
     - 150-255: Strong vibration (critical alarm)
```

### Status LED Indicator

```
   GPIO 33 ──[470Ω resistor]──→ LED Anode (+)
   (3.3V output)                    │
                                    ├──→ 2-3V voltage drop
                                    │
                                LED Cathode (-)
                                    │
                                   GND

   LED Behavior (from firmware):
   • OFF:        System boot/idle
   • Slow Blink: Normal operation
   • Fast Blink: WiFi searching
   • Solid ON:   WiFi connected
   • Flashing:   Alert/sensor active
```

---

## ✅ Assembly & Testing Checklist

### Pre-Assembly Checks
- [ ] Verify ESP32-CAM board revision (AI-Thinker v1.0 or later)
- [ ] Inspect all sensor modules for physical damage
- [ ] Test multimeter on continuity (no shorts)
- [ ] Prepare soldering iron (if hand-wiring required)

### Wiring Verification
- [ ] HC-SR04 power wires securely connected (5V, GND)
- [ ] HC-SR04 Trigger (GPIO 12) confirmed
- [ ] HC-SR04 Echo (GPIO 13) with voltage divider installed
- [ ] Vibration motor polarity correct (check datasheet)
- [ ] MOSFET Gate pull-down resistor installed
- [ ] Status LED polarity correct (anode to GPIO 33)
- [ ] All GND connections are common (multimeter test)
- [ ] Power supply produces stable 5V (multimeter test)

### Firmware Verification
```cpp
// Test pins allocation in firmware:
TRIGGER_PIN = 12   ✓
ECHO_PIN = 13      ✓
VIBRO_PIN = 14     ✓
STATUS_LED = 33    ✓
```

### Post-Assembly Testing
- [ ] Power on: Status LED should blink
- [ ] Measure distance with multimeter: should change 0-400cm
- [ ] Vibration test: applies PWM should spin/vibrate
- [ ] Monitor serial output for sensor data messages

---

## 🐛 Troubleshooting Guide

| Problem | Likely Cause | Solution |
| :--- | :--- | :--- |
| ESP32 won't flash | GPIO 0 pulled LOW by sensor | Disconnect all sensors during flashing |
| HC-SR04 not responding | Wrong GPIO or no power | Verify GPIO 12/13 in code, check 5V supply |
| Echo pin reads always HIGH | Voltage too high or no pull-down | Install 10kΩ pull-down resistor on GPIO 13 |
| Vibration motor won't activate | MOSFET not triggering or motor power OFF | Test GPIO 14 with LED, verify 5V at motor |
| Distance readings erratic | Ultrasonic interference or unstable power | Move away from other ultrasonic devices, add capacitors |
| Status LED won't light | GPIO 33 misconfigured or LED reversed | Check LED polarity, verify GPIO 33 in code |
| WiFi connection drops | Voltage unstable under WiFi load | Upgrade power supply to 2A+ regulated |

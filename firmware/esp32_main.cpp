/*
 * ==========================================
 * SMART AI CAP FIRMWARE - ESP32
 * Main controller for sensor data collection and transmission
 * ==========================================
 *
 * Features:
 *   - ESP32 CAM image capture and compression
 *   - HC-SR04 ultrasonic distance measurement
 *   - WiFi-based image transmission
 *   - Bluetooth low-energy for control/alerts
 *   - Low-power modes
 *   - Real-time sensor fusion
 *
 * Hardware Requirements:
 *   - ESP32 Dev Board
 *   - ESP32-CAM module
 *   - HC-SR04 Ultrasonic sensor
 *   - Li-Po 5000mAh battery
 *   - Vibration motor with FET driver
 */

#include <BluetoothSerial.h>
#include <SPIFFS.h>
#include <WebServer.h>
#include <WiFi.h>
#include <esp_camera.h>


// ============================================
// PIN DEFINITIONS
// ============================================
#define TRIGGER_PIN 12 // Changed from 5 (Camera Y2)
#define ECHO_PIN 13    // Changed from 19 (Camera Y4)
#define VIBRO_PIN 14   // Changed from 27 (Camera SIOC)
#define STATUS_LED 33  // Status indicator LED

// ESP32-CAM specific pins (internal)
#define PWDN_GPIO_NUM 32
#define RESET_GPIO_NUM -1
#define XCLK_GPIO_NUM 0
#define SIOD_GPIO_NUM 26 // SDA (I2C)
#define SIOC_GPIO_NUM 27 // SCL (I2C)
#define Y9_GPIO_NUM 35
#define Y8_GPIO_NUM 34
#define Y7_GPIO_NUM 39
#define Y6_GPIO_NUM 36
#define Y5_GPIO_NUM 21
#define Y4_GPIO_NUM 19
#define Y3_GPIO_NUM 18
#define Y2_GPIO_NUM 5
#define VSYNC_GPIO_NUM 25
#define HREF_GPIO_NUM 23
#define PCLK_GPIO_NUM 22

// ============================================
// CONFIGURATION PARAMETERS
// ============================================
#define WIFI_SSID "your_wifi_ssid"         // ← PUT YOUR WIFI NAME HERE
#define WIFI_PASSWORD "your_wifi_password" // ← PUT YOUR WIFI PASSWORD HERE
#define BACKEND_IP "192.168.x.x"           // ← PUT YOUR PC's IP ADDRESS HERE
#define BACKEND_PORT 5000                  // Backend port
#define FRAME_INTERVAL 100                 // ms between frames
#define ULTRASONIC_TIMEOUT 23200           // µs timeout (~400cm)
#define HEARTBEAT_INTERVAL 5000            // ms between heartbeat POSTs

#include <HTTPClient.h> // For heartbeat POST requests

// ============================================
// GLOBAL VARIABLES
// ============================================
WebServer server(80);
BluetoothSerial SerialBT;
unsigned long lastFrameTime = 0;
unsigned long sensorReadTime = 0;
unsigned long lastHeartbeatTime = 0;
volatile unsigned long pulseStartTime = 0;
volatile unsigned long echoPulseLength = 0;

// Alert priority levels
enum AlertLevel { SAFE, WARNING, CRITICAL };
AlertLevel currentAlertLevel = SAFE;

// ============================================
// FUNCTION PROTOTYPES
// ============================================
void initCamera();
void initWiFi();
void initBluetooth();
void setupPins();
void setupInterrupts();
void captureAndSendFrame();
unsigned long measureDistance();
void updateVibrationAlert(AlertLevel level);
void handleBackendCommand();
void handleStream();
void handleVibrateCommand();
void sendHeartbeat();
String buildSensorDataPacket();
void logToSerial(const char *message);

// ============================================
// SETUP ROUTINE
// ============================================
void setup() {
  Serial.begin(115200);
  Serial.println("\n\n===== Smart AI Cap Startup =====");

  // Initialize file system
  if (!SPIFFS.begin(true)) {
    Serial.println("ERROR: SPIFFS Mount Failed");
  }

  // Setup GPIO pins
  setupPins();
  Serial.println("✓ GPIO pins initialized");

  // Initialize camera
  initCamera();
  Serial.println("✓ Camera initialized");

  // Initialize WiFi
  initWiFi();
  Serial.println("✓ WiFi connected");

  // Initialize Bluetooth
  initBluetooth();
  Serial.println("✓ Bluetooth initialized");

  // Setup interrupt handlers
  setupInterrupts();
  Serial.println("✓ Interrupts configured");

  Serial.println("===== Startup Complete =====\n");

  // Status LED indication (3 blinks = ready)
  for (int i = 0; i < 3; i++) {
    digitalWrite(STATUS_LED, HIGH);
    delay(100);
    digitalWrite(STATUS_LED, LOW);
    delay(100);
  }
}

// ============================================
// MAIN LOOP
// ============================================
void loop() {
  // Check for Bluetooth commands
  if (SerialBT.available()) {
    handleBackendCommand();
  }

  // Periodically capture and transmit frame
  unsigned long currentTime = millis();
  if (currentTime - lastFrameTime >= FRAME_INTERVAL) {
    lastFrameTime = currentTime;

    // Capture image
    camera_fb_t *fb = esp_camera_fb_get();

    if (!fb) {
      Serial.println("ERROR: Camera capture failed");
      digitalWrite(STATUS_LED, HIGH); // Error indicator
      delay(100);
      digitalWrite(STATUS_LED, LOW);
      esp_camera_fb_return(fb);
      return;
    }

    // Measure distance
    unsigned long distance = measureDistance();

    // Build packet with frame + sensor data
    // Format: [HEADER][FRAME_DATA][METADATA][CHECKSUM]
    //
    // Note: Full transmission to backend happens here
    // In a real system, you'd stream this over WiFi to Python backend

    // Connect to backend if not connected
    WiFiClient client;
    if (client.connect(BACKEND_IP, BACKEND_PORT)) {
      // Build packet: [MAGIC][VER][TYPE][LEN][METADATA_LEN][METADATA][PAYLOAD]
      // Simplified for this example: Just sending raw JPEG with header

      // 1. Send Header (Custom Protocol)
      // Magic: "CAP1", Ver: 1, Type: 1 (Frame), Len: fb->len
      uint8_t header[10];
      memcpy(header, "CAP1", 4);
      header[4] = 1; // Version
      header[5] = 1; // Type = Frame
      uint32_t len = fb->len;
      memcpy(&header[6], &len, 4);

      client.write(header, 10);

      // 2. Send Metadata (zero length for now, or could send distance)
      // For simplicity, we stick to the basic frame structure expected by
      // backend Backend expects: Header (10) + Metadata Len (4) + Metadata +
      // Payload

      uint32_t metaLen =
          0; // No metadata for now to keep it simple, or JSON string length
      // Let's create simple metadata JSON
      String meta = "{\"dist\":" + String(distance) + "}";
      metaLen = meta.length();

      client.write((const uint8_t *)&metaLen, 4);
      client.print(meta);

      // 3. Send Frame Data
      size_t sent = 0;
      size_t toSend = fb->len;
      while (sent < toSend) {
        size_t chunk = (toSend - sent > 1024) ? 1024 : (toSend - sent);
        client.write(fb->buf + sent, chunk);
        sent += chunk;
      }

      Serial.printf("Sent frame (%u bytes) + meta to backend\n", fb->len);
      client.stop();
    } else {
      Serial.println("Connection to backend failed");
    }

    // Return frame buffer
    esp_camera_fb_return(fb);
  }

  // Handle any wireless commands
  server.handleClient();

  // Send heartbeat to backend every HEARTBEAT_INTERVAL ms
  if (currentTime - lastHeartbeatTime >= HEARTBEAT_INTERVAL) {
    lastHeartbeatTime = currentTime;
    sendHeartbeat();
  }

  // Power management
  if (esp_get_free_heap_size() < 20000) {
    Serial.println("WARNING: Low memory, optimizing...");
    esp_camera_fb_return(nullptr); // Clear buffers
  }
}

// ============================================
// PIN INITIALIZATION
// ============================================
void setupPins() {
  pinMode(TRIGGER_PIN, OUTPUT);
  pinMode(ECHO_PIN, INPUT);
  pinMode(VIBRO_PIN, OUTPUT);
  pinMode(STATUS_LED, OUTPUT);

  // Initialize PWM for vibration motor (frequency 20kHz, resolution 8-bit)
  ledcSetup(0, 20000, 8); // Channel 0, 20kHz, 8-bit
  ledcAttachPin(VIBRO_PIN, 0);

  // Set initial states
  digitalWrite(TRIGGER_PIN, LOW);
  digitalWrite(STATUS_LED, LOW);
  ledcWrite(0, 0); // Motor off
}

// ============================================
// INTERRUPT SETUP FOR HIGH-PRECISION TIMING
// ============================================
void setupInterrupts() {
  // Attach interrupt to ECHO pin for precise pulse measurement
  attachInterrupt(digitalPinToInterrupt(ECHO_PIN), echoInterruptHandler,
                  CHANGE);
}

// ISR for measuring echo pulse
void IRAM_ATTR echoInterruptHandler() {
  if (digitalRead(ECHO_PIN) == HIGH) {
    // Rising edge - capture start time
    pulseStartTime = micros();
  } else {
    // Falling edge - calculate pulse length
    echoPulseLength = micros() - pulseStartTime;
  }
}

// ============================================
// CAMERA INITIALIZATION
// ============================================
void initCamera() {
  camera_config_t config;
  config.ledc_channel = LEDC_CHANNEL_0;
  config.ledc_timer = LEDC_TIMER_0;
  config.pin_d0 = Y2_GPIO_NUM;
  config.pin_d1 = Y3_GPIO_NUM;
  config.pin_d2 = Y4_GPIO_NUM;
  config.pin_d3 = Y5_GPIO_NUM;
  config.pin_d4 = Y6_GPIO_NUM;
  config.pin_d5 = Y7_GPIO_NUM;
  config.pin_d6 = Y8_GPIO_NUM;
  config.pin_d7 = Y9_GPIO_NUM;
  config.pin_xclk = XCLK_GPIO_NUM;
  config.pin_pclk = PCLK_GPIO_NUM;
  config.pin_vsync = VSYNC_GPIO_NUM;
  config.pin_href = HREF_GPIO_NUM;
  config.pin_scc = SIOC_GPIO_NUM;
  config.pin_sda = SIOD_GPIO_NUM;
  config.pin_pwdn = PWDN_GPIO_NUM;
  config.pin_reset = RESET_GPIO_NUM;
  config.xclk_freq_hz = 20000000; // 20MHz clock
  config.pixel_format = PIXELFORMAT_JPEG;
  config.frame_size = FRAMESIZE_VGA; // 640x480
  config.jpeg_quality = 85;          // Compression: 0-63 (lower = smaller file)
  config.fb_count = 1;               // Only 1 frame buffer to save RAM

  esp_err_t err = esp_camera_init(&config);
  if (err != ESP_OK) {
    Serial.printf("Camera init failed with error 0x%x\n", err);
    return;
  }

  // Adjust camera settings
  sensor_t *s = esp_camera_sensor_get();
  s->set_brightness(s, 0);     // -2 to 2
  s->set_contrast(s, 0);       // -2 to 2
  s->set_saturation(s, 0);     // -2 to 2
  s->set_special_effect(s, 0); // 0 to 6 (normal, greyscale, sepia, etc)
  s->set_whitebal(s, 1);       // Auto white balance
  s->set_awb_gain(s, 1);       // Auto gain
  s->set_exposure_ctrl(s, 1);  // Auto exposure
}

// ============================================
// WiFi INITIALIZATION
// ============================================
void initWiFi() {
  WiFi.mode(WIFI_STA);
  WiFi.begin(WIFI_SSID, WIFI_PASSWORD);

  int attempts = 0;
  while (WiFi.status() != WL_CONNECTED && attempts < 20) {
    delay(500);
    Serial.print(".");
    attempts++;
  }

  if (WiFi.status() == WL_CONNECTED) {
    Serial.println("\nWiFi Connected!");
    Serial.print("IP address: ");
    Serial.println(WiFi.localIP());
    Serial.printf("Signal strength (RSSI): %d dBm\n", WiFi.RSSI());
  } else {
    Serial.println("\nWiFi connection failed - will retry");
  }

  // Setup HTTP server endpoints
  server.on("/status", handleStatus);
  server.on("/distance", handleDistance);
  server.on("/frame", handleFrame);
  server.on("/stream", handleStream); // ← MJPEG live stream
  server.on("/vibrate", handleVibrateCommand);
  server.begin();
  Serial.printf("HTTP server started at http://%s:80\n",
                WiFi.localIP().toString().c_str());
}

// ============================================
// BLUETOOTH INITIALIZATION
// ============================================
void initBluetooth() {
  SerialBT.begin("SmartCap_BLE"); // Bluetooth device name
  Serial.println("Bluetooth device started");
}

// ============================================
// ULTRASONIC DISTANCE MEASUREMENT
// ============================================
unsigned long measureDistance() {
  // Send 10µs trigger pulse
  digitalWrite(TRIGGER_PIN, HIGH);
  delayMicroseconds(10);
  digitalWrite(TRIGGER_PIN, LOW);

  // Wait for echo (with timeout to prevent hanging)
  unsigned long startTime = micros();
  while (digitalRead(ECHO_PIN) == LOW &&
         (micros() - startTime) < ULTRASONIC_TIMEOUT) {
    // Wait for signal
  }

  if ((micros() - startTime) >= ULTRASONIC_TIMEOUT) {
    return 0; // Timeout - no object detected
  }

  // Measure echo pulse width
  unsigned long pulseWidth = echoPulseLength;

  // Convert pulse width to distance
  // Speed of sound: 343 m/s = 0.343 mm/µs
  // Distance = (pulse_width_µs / 2) * 0.343 mm/µs
  unsigned long distanceMM = (pulseWidth * 343) / 2000;

  return distanceMM;
}

// ============================================
// VIBRATION ALERT CONTROL
// ============================================
void updateVibrationAlert(AlertLevel level) {
  /*
   * Vibration Pattern Map:
   * SAFE:     No vibration
   * WARNING:  3 pulses at 100ms intervals
   * CRITICAL: Continuous rapid vibration (10Hz)
   */

  switch (level) {
  case SAFE:
    ledcWrite(0, 0); // Off
    break;

  case WARNING:
    // 3 pulses: 100ms ON, 100ms OFF, repeat
    for (int i = 0; i < 3; i++) {
      ledcWrite(0, 200); // 78% duty cycle
      delay(100);
      ledcWrite(0, 0);
      delay(100);
    }
    break;

  case CRITICAL:
    // Rapid 10Hz vibration (50ms on, 50ms off)
    ledcWrite(0, 255); // Max intensity
    delay(500);        // Continuous for 500ms
    ledcWrite(0, 0);
    break;
  }

  currentAlertLevel = level;
}

// ============================================
// HTTP HANDLER - STATUS ENDPOINT
// ============================================
void handleStatus() {
  String json = "{";
  json += "\"wifi_rssi\":" + String(WiFi.RSSI()) + ",";
  json += "\"heap_free\":" + String(esp_get_free_heap_size()) + ",";
  json += "\"uptime\":" + String(millis() / 1000) + ",";
  json += "\"frame_rate\":" + String(1000.0 / FRAME_INTERVAL) + ",";
  json += "\"alert_level\":" + String(currentAlertLevel) + "";
  json += "}";

  server.send(200, "application/json", json);
}

// ============================================
// HTTP HANDLER - DISTANCE ENDPOINT
// ============================================
void handleDistance() {
  unsigned long distance = measureDistance();
  String json = "{\"distance_mm\":" + String(distance) + "}";
  server.send(200, "application/json", json);
}

// ============================================
// HTTP HANDLER - FRAME ENDPOINT
// ============================================
void handleFrame() {
  camera_fb_t *fb = esp_camera_fb_get();

  if (!fb) {
    server.send(500, "text/plain", "Camera capture failed");
    return;
  }

  server.sendHeader("Content-Type", "image/jpeg");
  server.sendHeader("Content-Length", (String)fb->len);
  server.send(200, "image/jpeg", (const char *)fb->buf, fb->len);

  esp_camera_fb_return(fb);
}

// ============================================
// HTTP HANDLER - MJPEG STREAM ENDPOINT
// ============================================
void handleStream() {
  WiFiClient client = server.client();

  // Send MJPEG multipart header
  String response = "HTTP/1.1 200 OK\r\n";
  response += "Content-Type: multipart/x-mixed-replace; boundary=frame\r\n\r\n";
  client.print(response);

  while (client.connected()) {
    camera_fb_t *fb = esp_camera_fb_get();
    if (!fb) {
      Serial.println("Stream: capture failed");
      break;
    }

    // Send each JPEG frame as a multipart chunk
    String header = "--frame\r\n";
    header += "Content-Type: image/jpeg\r\n";
    header += "Content-Length: " + String(fb->len) + "\r\n\r\n";

    client.print(header);
    client.write(fb->buf, fb->len);
    client.print("\r\n");

    esp_camera_fb_return(fb);

    // ~10 FPS
    delay(100);
  }
}

// ============================================
// HTTP HANDLER - VIBRATE ENDPOINT
// ============================================
void handleVibrateCommand() {
  if (!server.hasArg("pattern")) {
    server.send(400, "text/plain", "Missing pattern argument");
    return;
  }

  String pattern = server.arg("pattern");
  Serial.printf("Received vibration request: %s\n", pattern.c_str());

  if (pattern == "obstacle_critical") {
    // Continuous high-frequency vibration
    ledcWrite(0, 255);
    delay(500);
    ledcWrite(0, 0);
  } else if (pattern == "obstacle_warning") {
    // 3 quick pulses
    for (int i = 0; i < 3; i++) {
      ledcWrite(0, 200);
      delay(100);
      ledcWrite(0, 0);
      delay(100);
    }
  } else if (pattern == "family_nearby") {
    // 2 gentle, long pulses (lower intensity: 150)
    for (int i = 0; i < 2; i++) {
      ledcWrite(0, 150);
      delay(300);
      ledcWrite(0, 0);
      delay(200);
    }
  } else if (pattern == "gesture_confirm") {
    // Triple-tap confirmation pulse
    for (int i = 0; i < 3; i++) {
      ledcWrite(0, 200);
      delay(70);
      ledcWrite(0, 0);
      delay(50);
    }
  } else if (pattern == "turn_left") {
    // 2 short left-weighted pulses (lower intensity = "soft" directional cue)
    for (int i = 0; i < 2; i++) {
      ledcWrite(0, 140);
      delay(120);
      ledcWrite(0, 0);
      delay(80);
    }
  } else if (pattern == "turn_right") {
    // 2 short right-weighted pulses (higher intensity = "strong" directional cue)
    for (int i = 0; i < 2; i++) {
      ledcWrite(0, 220);
      delay(120);
      ledcWrite(0, 0);
      delay(80);
    }
  } else if (pattern == "arrived") {
    // Double-pulse confirmation: two medium buzzes
    ledcWrite(0, 180);
    delay(200);
    ledcWrite(0, 0);
    delay(150);
    ledcWrite(0, 180);
    delay(200);
    ledcWrite(0, 0);
  } else if (pattern == "nav_alert") {
    // Single medium pulse for upcoming turn
    ledcWrite(0, 160);
    delay(250);
    ledcWrite(0, 0);
  } else if (pattern == "sos_active") {
    // Repeating SOS pattern: 3 short, 3 long, 3 short
    for (int i = 0; i < 3; i++) { ledcWrite(0, 255); delay(100); ledcWrite(0, 0); delay(80); }
    delay(100);
    for (int i = 0; i < 3; i++) { ledcWrite(0, 255); delay(300); ledcWrite(0, 0); delay(100); }
    delay(100);
    for (int i = 0; i < 3; i++) { ledcWrite(0, 255); delay(100); ledcWrite(0, 0); delay(80); }
  } else if (pattern == "stop") {
    ledcWrite(0, 0);
  } else {
    server.send(400, "text/plain", "Unknown pattern: " + pattern);
    return;
  }

  server.send(200, "application/json", "{\"status\":\"ok\",\"pattern\":\"" + pattern + "\"}");
}

// ============================================
// HEARTBEAT — POST STATUS TO BACKEND
// ============================================
void sendHeartbeat() {
  if (WiFi.status() != WL_CONNECTED)
    return;

  HTTPClient http;
  String url = "http://" + String(BACKEND_IP) + ":" + String(BACKEND_PORT) +
               "/api/status";

  http.begin(url);
  http.addHeader("Content-Type", "application/json");

  unsigned long distance = measureDistance();

  String json = "{";
  json += "\"wifi_rssi\":" + String(WiFi.RSSI()) + ",";
  json += "\"distance_mm\":" + String(distance) + ",";
  json +=
      "\"alert_level\":\"" +
      String(currentAlertLevel == SAFE
                 ? "SAFE"
                 : (currentAlertLevel == WARNING ? "WARNING" : "CRITICAL")) +
      "\",";
  json += "\"uptime\":" + String(millis() / 1000);
  json += "}";

  int httpCode = http.POST(json);
  if (httpCode > 0) {
    Serial.printf("Heartbeat sent (HTTP %d)\n", httpCode);
  } else {
    Serial.printf("Heartbeat failed: %s\n",
                  http.errorToString(httpCode).c_str());
  }
  http.end();
}

// ============================================
// HANDLE BLUETOOTH COMMANDS FROM BACKEND
// ============================================
void handleBackendCommand() {
  char command = SerialBT.read();

  switch (command) {
  case 'V': // Vibrate command
  {
    uint8_t intensity = SerialBT.read(); // 0-255
    ledcWrite(0, intensity);
  } break;

  case 'L': // LED control
  {
    uint8_t state = SerialBT.read();
    digitalWrite(STATUS_LED, state ? HIGH : LOW);
  } break;

  case 'S': // Sleep command
    esp_light_sleep_start();
    break;

  case 'R': // Request sensor data
    SerialBT.print(buildSensorDataPacket());
    break;

  case '?': // Ping
    SerialBT.print("OK");
    break;

  default:
    Serial.printf("Unknown command: %c\n", command);
  }
}

// ============================================
// BUILD SENSOR DATA PACKET
// ============================================
String buildSensorDataPacket() {
  unsigned long distance = measureDistance();

  String packet = "{";
  packet += "\"ts\":" + String(millis()) + ",";
  packet += "\"dist\":" + String(distance) + ",";
  packet += "\"rssi\":" + String(WiFi.RSSI()) + ",";
  packet += "\"temp\":" + String((uint8_t)temperatureRead()) + "";
  packet += "}";

  return packet;
}

// ============================================
// UTILITY LOGGING FUNCTION
// ============================================
void logToSerial(const char *message) {
  Serial.print("[");
  Serial.print(millis());
  Serial.print("] ");
  Serial.println(message);
}

// ============================================
// ADVANCED: POWER OPTIMIZATION
// ============================================

/*
 * For extended battery life, implement these modes:
 *
 * 1. ACTIVE MODE (Default)
 *    - WiFi ON, camera 30FPS
 *    - Power: ~300mA
 *    - Latency: ~100ms
 *
 * 2. BALANCED MODE
 *    - WiFi ON, camera 10FPS
 *    - Power: ~150mA
 *    - Latency: ~300ms
 *
 * 3. ECO MODE
 *    - WiFi OFF, BLE only
 *    - Camera disabled
 *    - Ultrasonic every 500ms
 *    - Power: ~40mA
 *    - Latency: ~600ms
 *
 * 4. STANDBY MODE
 *    - All systems sleep
 *    - Wake on trigger (button/motion)
 *    - Power: < 1mA
 */

void enableEcoMode() {
  // Disable camera
  esp_camera_deinit();

  // WiFi sleep
  WiFi.setSleep(WIFI_PS_MAX_MODEM);

  // Increase measurement interval
  // Check ultrasonic every 500ms instead of 100ms
}

void disableEcoMode() {
  // Re-enable camera
  initCamera();

  // Resume WiFi
  WiFi.setSleep(WIFI_PS_NONE);
}

// EOF

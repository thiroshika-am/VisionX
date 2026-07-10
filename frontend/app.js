/**
 * VisionX — Modular Dashboard Application
 * Handles: Camera, AI detection, Voice, TTS, GPS, Faces, System monitoring
 */

const API = "http://localhost:5000";

// ── State ─────────────────────────────────────────────────────────────────────
const state = {
  activeTab:          "live",
  detectionEnabled:   true,
  currentMode:        "detect",
  frameInterval:      null,
  statusInterval:     null,
  systemInterval:     null,
  logsInterval:       null,
  voiceListening:     false,
  recognition:        null,
  synthesis:          window.speechSynthesis,
  ttsRate:            1.0,
  ttsVol:             1.0,
  ttsPitch:           1.0,
  map:                null,
  mapMarker:          null,
  detectionHistory:   [],
  enrollPhotoB64:     null,
  fpsFrameTimes:      [],
  lastAlertLevel:     "SAFE",
  isProcessingFrame:  false,
  lastGuidanceTime:   0,
  directionsService:  null,
  directionsRenderer: null,
  navigationSteps:    [],
  currentStepIndex:   0,
  isNavigating:       false,
  gps_data:           null,
};

// ── Bootstrap ─────────────────────────────────────────────────────────────────
document.addEventListener("DOMContentLoaded", boot);

async function boot() {
  animateLoading();
  await startCamera();
  initMap();
  loadFaces();
  loadLogs();
  startPolling();
  setTimeout(hideLoading, 2500);
}

// ── Loading ───────────────────────────────────────────────────────────────────
function animateLoading() {
  const fill = document.getElementById("loading-fill");
  const status = document.getElementById("loading-status");
  const steps = [
    [10, "Connecting to backend…"],
    [35, "Loading YOLO model…"],
    [60, "Initializing face engine…"],
    [80, "Starting camera…"],
    [100, "Ready!"],
  ];
  let i = 0;
  const tick = () => {
    if (i >= steps.length) return;
    const [pct, msg] = steps[i++];
    fill.style.width = pct + "%";
    status.textContent = msg;
    setTimeout(tick, 400);
  };
  tick();
}

function hideLoading() {
  const el = document.getElementById("loading-screen");
  el.style.opacity = "0";
  el.style.transition = "opacity 0.5s ease";
  setTimeout(() => el.remove(), 600);
}

// ── Camera ────────────────────────────────────────────────────────────────────
async function startCamera() {
  const video = document.getElementById("webcam-video");
  try {
    const stream = await navigator.mediaDevices.getUserMedia({
      video: { width: { ideal: 1280 }, height: { ideal: 720 }, facingMode: "environment" },
      audio: false,
    });
    video.srcObject = stream;
    await video.play();
    startFrameCapture();
  } catch (e) {
    console.warn("Camera not available:", e);
  }
}

function startFrameCapture() {
  if (state.frameInterval) clearTimeout(state.frameInterval);
  state.frameInterval = setTimeout(captureAndProcess, 600);
}

async function captureAndProcess() {
  if (!state.detectionEnabled || state.isProcessingFrame) {
    state.frameInterval = setTimeout(captureAndProcess, 600);
    return;
  }
  
  const video = document.getElementById("webcam-video");
  if (!video.videoWidth) {
    state.frameInterval = setTimeout(captureAndProcess, 600);
    return;
  }

  state.isProcessingFrame = true;

  try {
    const canvas = document.createElement("canvas");
    canvas.width  = video.videoWidth;
    canvas.height = video.videoHeight;
    canvas.getContext("2d").drawImage(video, 0, 0);
    const b64 = canvas.toDataURL("image/jpeg", 0.75);

    // Track FPS
    const now = Date.now();
    state.fpsFrameTimes = state.fpsFrameTimes.filter(t => now - t < 5000);
    state.fpsFrameTimes.push(now);
    const fps = state.fpsFrameTimes.length > 1
      ? ((state.fpsFrameTimes.length - 1) / ((now - state.fpsFrameTimes[0]) / 1000)).toFixed(1)
      : "0.0";
    document.getElementById("fps-display").textContent = fps + " FPS";
    document.getElementById("stat-fps").textContent = fps;
    document.getElementById("fps-big").textContent = Math.round(fps);

    if (state.currentMode === "detect") await runDetection(b64);
    else if (state.currentMode === "ocr")    await runOCR(b64);
    else if (state.currentMode === "depth")  await runDepth(b64);
    else if (state.currentMode === "emotion") await runEmotion(b64);
  } finally {
    state.isProcessingFrame = false;
    state.frameInterval = setTimeout(captureAndProcess, 600);
  }
}

// ── Detection ─────────────────────────────────────────────────────────────────
async function runDetection(b64) {
  try {
    const res  = await apiFetch("/api/detect", { method: "POST", body: { image: b64 } });
    if (!res) return;
    drawDetections(res.detections || []);
    updateLiveDetections(res.detections || []);
    updateAlertLevel(res.alert_level || "SAFE");
    addToHistory(res.detections || []);

    provideGuidance(res.detections || []);
  } catch (e) { /* ignore */ }
}

function provideGuidance(detections) {
  const now = Date.now();
  if (now - (state.lastGuidanceTime || 0) < 4000) return; // 4 second cooldown

  // Filter for interfering obstacles (WARNING or CRITICAL)
  const threats = detections.filter(d => d.alert_level === "CRITICAL" || d.alert_level === "WARNING");
  if (!threats.length) return;

  let centerBlocked = false;
  let leftBlocked = false;
  let rightBlocked = false;

  threats.forEach(t => {
    const pos = t.position || "center";
    if (pos.includes("center")) centerBlocked = true;
    if (pos.includes("left")) leftBlocked = true;
    if (pos.includes("right")) rightBlocked = true;
  });

  if (!centerBlocked && !leftBlocked && !rightBlocked) return;

  let msg = "";
  if (centerBlocked) {
    if (!leftBlocked) msg = "Obstacle ahead, turn left.";
    else if (!rightBlocked) msg = "Obstacle ahead, turn right.";
    else msg = "Path blocked, please stop.";
  } else if (leftBlocked && !rightBlocked) {
    msg = "Obstacle on left, stay right.";
  } else if (rightBlocked && !leftBlocked) {
    msg = "Obstacle on right, stay left.";
  } else if (leftBlocked && rightBlocked) {
    msg = "Obstacles on both sides, stay center.";
  }

  if (msg) {
    state.lastGuidanceTime = now;
    speak(msg);
  }
}

function drawDetections(detections) {
  const video  = document.getElementById("webcam-video");
  const canvas = document.getElementById("detection-canvas");
  const ctx    = canvas.getContext("2d");

  canvas.width  = video.offsetWidth;
  canvas.height = video.offsetHeight;
  ctx.clearRect(0, 0, canvas.width, canvas.height);

  if (!detections.length) return;

  const scaleX = canvas.width  / (video.videoWidth  || canvas.width);
  const scaleY = canvas.height / (video.videoHeight || canvas.height);

  const COLOR = { CRITICAL: "#FF3B3B", WARNING: "#FF8C00", SAFE: "#00FF88" };

  detections.forEach(det => {
    if (!det.bbox) return;
    const { x1, y1, x2, y2 } = det.bbox;
    const bx = x1 * scaleX, by = y1 * scaleY;
    const bw = (x2 - x1) * scaleX, bh = (y2 - y1) * scaleY;
    const color = COLOR[det.alert_level] || "#00D4FF";

    // Box
    ctx.strokeStyle = color;
    ctx.lineWidth   = 2;
    ctx.globalAlpha = 0.9;
    ctx.strokeRect(bx, by, bw, bh);

    // Corner accents
    const cs = 12;
    ctx.lineWidth = 3;
    [[bx, by, 1, 1], [bx+bw, by, -1, 1], [bx, by+bh, 1, -1], [bx+bw, by+bh, -1, -1]].forEach(([cx, cy, dx, dy]) => {
      ctx.beginPath(); ctx.moveTo(cx, cy + dy * cs); ctx.lineTo(cx, cy); ctx.lineTo(cx + dx * cs, cy);
      ctx.stroke();
    });

    // Label background
    const label = `${det.class} ${(det.confidence * 100).toFixed(0)}%`;
    const dist  = det.distance ? ` · ${det.distance}` : "";
    ctx.font = "bold 11px Inter, sans-serif";
    const tw = ctx.measureText(label + dist).width + 10;
    ctx.globalAlpha = 0.75;
    ctx.fillStyle = "#0D1117";
    ctx.fillRect(bx - 1, by - 20, tw, 18);

    // Label text
    ctx.globalAlpha = 1;
    ctx.fillStyle = color;
    ctx.fillText(label + dist, bx + 4, by - 6);
  });
  ctx.globalAlpha = 1;
}

function updateLiveDetections(detections) {
  const list  = document.getElementById("live-det-list");
  const count = document.getElementById("live-det-count");
  const statO = document.getElementById("stat-objects");

  count.textContent = detections.length;
  statO.textContent = detections.length;

  if (!detections.length) {
    list.innerHTML = '<div class="empty-msg">No objects detected</div>';
    return;
  }

  list.innerHTML = detections.slice(0, 8).map(d => `
    <div class="det-item ${d.alert_level || 'SAFE'}">
      <span class="det-class">${d.class}</span>
      <span class="det-dist">${d.distance || "–"}</span>
      <span class="det-pos">${d.position || "center"}</span>
    </div>
  `).join("");
}

function updateAlertLevel(level) {
  const badge = document.getElementById("alert-level-badge");
  badge.className = `alert-badge ${level}`;
  badge.textContent = level;
  state.lastAlertLevel = level;
}

function addToHistory(detections) {
  detections.forEach(d => {
    state.detectionHistory.unshift({ ...d, timestamp: new Date().toISOString() });
  });
  if (state.detectionHistory.length > 500) state.detectionHistory.length = 500;
  updateDetectionsTab();
}

function updateDetectionsTab() {
  const history = state.detectionHistory;
  const critical = history.filter(d => d.alert_level === "CRITICAL").length;
  const warning  = history.filter(d => d.alert_level === "WARNING").length;
  const classes  = new Set(history.map(d => d.class)).size;

  document.getElementById("total-detections").textContent = history.length;
  document.getElementById("critical-count").textContent   = critical;
  document.getElementById("warning-count").textContent    = warning;
  document.getElementById("unique-classes").textContent   = classes;

  const grid   = document.getElementById("detection-grid");
  const filter = document.getElementById("det-filter")?.value || "all";
  const filtered = history.filter(d => {
    if (filter === "all") return true;
    if (filter === "CRITICAL") return d.alert_level === "CRITICAL";
    if (filter === "WARNING")  return d.alert_level === "WARNING" || d.alert_level === "CRITICAL";
    if (filter === "person")   return d.class === "person";
    return true;
  }).slice(0, 50);

  if (!filtered.length) {
    grid.innerHTML = '<div class="empty-state">No detections match filter.</div>';
    return;
  }

  grid.innerHTML = filtered.map(d => `
    <div class="det-card ${d.alert_level || 'SAFE'}">
      <div class="det-card-top">
        <span class="det-card-class">${d.class}</span>
        <span class="alert-chip ${d.alert_level || 'SAFE'}">${d.alert_level || 'SAFE'}</span>
      </div>
      <div class="det-card-meta">
        ${d.distance ? `<span class="meta-tag">📏 ${d.distance}</span>` : ""}
        ${d.position ? `<span class="meta-tag">${dirEmoji(d.position)} ${d.position}</span>` : ""}
        ${d.movement?.approaching ? `<span class="meta-tag">⚡ Approaching</span>` : ""}
        <span class="meta-tag">${(d.confidence * 100).toFixed(0)}%</span>
      </div>
      <div class="conf-bar"><div class="conf-fill" style="width:${(d.confidence*100).toFixed(0)}%"></div></div>
    </div>
  `).join("");
}

function dirEmoji(pos) {
  if (pos?.includes("left"))  return "◀";
  if (pos?.includes("right")) return "▶";
  return "▼";
}

function filterDetections(val) { updateDetectionsTab(); }
function clearDetectionHistory() { state.detectionHistory = []; updateDetectionsTab(); }

// ── OCR Mode ─────────────────────────────────────────────────────────────────
async function runOCR(b64) {
  try {
    const res = await apiFetch("/api/ocr", { method: "POST", body: { image: b64 } });
    if (!res || !res.combined_text) return;
    const canvas = document.getElementById("detection-canvas");
    const ctx    = canvas.getContext("2d");
    ctx.clearRect(0, 0, canvas.width, canvas.height);
    ctx.fillStyle = "rgba(0,212,255,0.85)";
    ctx.font = "bold 14px Inter, sans-serif";
    ctx.fillText("📝 " + res.combined_text.slice(0, 60), 12, 30);
    document.getElementById("scene-text").textContent = "Read: " + res.combined_text;
    speak(res.combined_text);
  } catch (e) { /* ignore */ }
}

// ── Depth Mode ────────────────────────────────────────────────────────────────
async function runDepth(b64) {
  try {
    const res = await apiFetch("/api/depth", { method: "POST", body: { image: b64 } });
    if (!res?.zones) return;
    const card = document.getElementById("depth-card");
    card.classList.remove("hidden");
    ["left","center","right"].forEach(z => {
      const zone = res.zones[z] || {};
      document.getElementById(`dz-${z}-val`).textContent = zone.label || "–";
    });
    if (res.depth_map_b64) {
      const img = document.getElementById("depth-img");
      img.src = res.depth_map_b64;
    }
  } catch (e) { /* ignore */ }
}

// ── Emotion Mode ─────────────────────────────────────────────────────────────
async function runEmotion(b64) {
  try {
    const res = await apiFetch("/api/emotion", { method: "POST", body: { image: b64 } });
    if (!res?.emotions?.length) return;
    const top = res.emotions[0];
    const emotion = top.dominant_emotion || top.emotion || "unknown";
    const emoji = top.emoji || "";
    document.getElementById("emotion-display").textContent =
      `${emoji} ${emotion} (${(top.confidence * 100).toFixed(0)}%)`;
  } catch (e) { /* ignore */ }
}

// ── Scene Description ─────────────────────────────────────────────────────────
async function requestScene() {
  const video = document.getElementById("webcam-video");
  if (!video.videoWidth) { speak("No camera feed available."); return; }
  const canvas = document.createElement("canvas");
  canvas.width  = video.videoWidth;
  canvas.height = video.videoHeight;
  canvas.getContext("2d").drawImage(video, 0, 0);
  const b64 = canvas.toDataURL("image/jpeg", 0.75);
  document.getElementById("scene-text").textContent = "Analyzing scene…";
  try {
    const res = await apiFetch("/api/analyze-frame", {
      method: "POST", body: { image: b64, include_scene: true }
    });
    const desc = res?.scene_description || "I cannot describe the scene right now.";
    document.getElementById("scene-text").textContent = desc;
    speak(desc);
  } catch (e) {
    document.getElementById("scene-text").textContent = "Scene analysis failed.";
  }
}

// ── Polling ───────────────────────────────────────────────────────────────────
function startPolling() {
  // Device status
  state.statusInterval = setInterval(pollStatus, 2000);
  pollStatus();

  // System stats
  state.systemInterval = setInterval(pollSystem, 5000);
  pollSystem();

  // Logs
  state.logsInterval = setInterval(loadLogs, 15000);
}

async function pollStatus() {
  try {
    const res = await apiFetch("/api/status");
    if (!res) return;
    const dot   = document.getElementById("device-dot");
    const label = document.getElementById("device-label");
    const pill  = document.getElementById("device-pill");

    if (res.online) {
      dot.className   = "device-dot online";
      label.textContent = "Online";
    } else {
      dot.className   = "device-dot offline";
      label.textContent = "Offline";
    }
    
    const viewport = document.getElementById("camera-viewport");
    let offlineOverlay = document.getElementById("camera-offline-overlay");
    if (!offlineOverlay && viewport) {
      offlineOverlay = document.createElement("div");
      offlineOverlay.id = "camera-offline-overlay";
      offlineOverlay.className = "camera-offline-overlay hidden";
      offlineOverlay.innerHTML = `<span>📡 CAMERA OFFLINE</span><p style="font-size:12px; margin-top:5px; opacity:0.8;">Check device connection</p>`;
      viewport.appendChild(offlineOverlay);
    }

    if (!res.online || res.camera_offline) {
      if (offlineOverlay) offlineOverlay.classList.remove("hidden");
    } else {
      if (offlineOverlay) offlineOverlay.classList.add("hidden");
    }

    // Update device info (map tab)
    document.getElementById("dev-battery").textContent = res.battery ? res.battery + "%" : "–";
    document.getElementById("dev-rssi").textContent    = res.wifi_rssi ? res.wifi_rssi + " dBm" : "–";
    document.getElementById("dev-dist").textContent    = res.distance_mm ? res.distance_mm + " mm" : "–";
    document.getElementById("dev-alert").textContent   = res.alert_level || "SAFE";

    // TTS announcements
    if (res.announcements?.length) {
      res.announcements.forEach(msg => {
        showAlertBanner(msg, res.alert_level || "INFO");
        speak(msg);
      });
    }

    // GPS polling
    const gps = await apiFetch("/api/gps");
    if (gps) updateGPS(gps);
  } catch (e) { /* ignore */ }
}

async function pollSystem() {
  try {
    const res = await apiFetch("/api/system");
    if (!res) return;

    document.getElementById("stat-cpu").textContent = (res.cpu_percent || 0) + "%";
    document.getElementById("stat-ram").textContent = (res.ram_percent || 0) + "%";

    setGauge("cpu", res.cpu_percent || 0);
    setGauge("ram", res.ram_percent || 0);
    setGauge("gpu", res.gpu_memory_percent || 0, res.gpu_available ? null : "N/A");

    const fps = res.fps || 0;
    document.getElementById("fps-big").textContent = Math.round(fps);

    if (res.uptime_sec != null) {
      document.getElementById("uptime-badge").textContent = "Uptime: " + formatUptime(res.uptime_sec);
    }

    updateModuleStatus();
  } catch (e) { /* ignore */ }
}

function setGauge(name, percent, overrideLabel = null) {
  const path  = document.getElementById(`gauge-${name}-path`);
  const val   = document.getElementById(`gauge-${name}-val`);
  if (!path || !val) return;
  const total = 157; // half-circle arc length ≈ π * r = π * 50 ≈ 157
  const filled = (percent / 100) * total;
  path.style.strokeDasharray = `${filled} ${total}`;
  val.textContent = overrideLabel !== null ? overrideLabel : Math.round(percent) + "%";
}

async function updateModuleStatus() {
  try {
    const res = await apiFetch("/api/scheduler/status");
    if (!res?.active_modules) return;
    const list = document.getElementById("module-list");
    list.innerHTML = Object.entries(res.active_modules).map(([name, enabled]) => `
      <div class="module-item">
        <span class="module-name">${name.replace(/_/g," ")}</span>
        <span class="module-dot ${enabled ? 'ok' : 'off'}" title="${enabled ? 'Enabled' : 'Disabled'}"></span>
      </div>
    `).join("");
  } catch (e) { /* ignore */ }
}

async function loadLogs() {
  try {
    const kind = document.getElementById("log-kind")?.value || "events";
    const res  = await apiFetch(`/api/logs?kind=${kind}&limit=50`);
    if (!res?.logs) return;
    const container = document.getElementById("log-entries");
    if (!res.logs.length) {
      container.innerHTML = '<div class="empty-msg">No logs yet</div>';
      return;
    }
    container.innerHTML = res.logs.slice().reverse().map(entry => {
      const ts   = (entry._ts || "").slice(11, 19);
      const entryKind = entry.kind || "info";
      const msg  = entry.message || entry.error || JSON.stringify(entry).slice(0, 80);
      return `<div class="log-entry ${entryKind}"><span class="log-ts">${ts}</span>${msg}</div>`;
    }).join("");
  } catch (e) { /* ignore */ }
}

async function clearLogs() {
  const kind = document.getElementById("log-kind")?.value || "events";
  await apiFetch(`/api/logs?kind=${kind}`, { method: "DELETE" });
  loadLogs();
}

// ── GPS / Map ─────────────────────────────────────────────────────────────────
function initMap() {
  try {
    if (!window.google) {
      setTimeout(initMap, 100);
      return;
    }
    const defaultLoc = { lat: 12.9716, lng: 77.5946 };
    state.map = new google.maps.Map(document.getElementById("gps-map"), {
      zoom: 14,
      center: defaultLoc,
      disableDefaultUI: true,
      styles: [{ elementType: "geometry", stylers: [{ color: "#242f3e" }] }, { elementType: "labels.text.stroke", stylers: [{ color: "#242f3e" }] }, { elementType: "labels.text.fill", stylers: [{ color: "#746855" }] }]
    });

    state.mapMarker = new google.maps.Marker({
      position: defaultLoc,
      map: state.map,
      icon: {
        path: google.maps.SymbolPath.CIRCLE,
        scale: 8,
        fillColor: "#00D4FF",
        fillOpacity: 1,
        strokeWeight: 1,
        strokeColor: "#ffffff"
      }
    });

    state.directionsService = new google.maps.DirectionsService();
    state.directionsRenderer = new google.maps.DirectionsRenderer({
      map: state.map,
      suppressMarkers: true,
      polylineOptions: { strokeColor: "#00D4FF", strokeWeight: 5 }
    });

    const input = document.getElementById("destination-input");
    const autocomplete = new google.maps.places.Autocomplete(input);
    autocomplete.bindTo("bounds", state.map);
  } catch (e) { console.warn("Map init failed:", e); }
}

function updateGPS(gps) {
  state.gps_data = gps;
  const { latitude: lat, longitude: lng, accuracy, speed, source } = gps;
  document.getElementById("gps-lat").textContent = lat?.toFixed(6) || "–";
  document.getElementById("gps-lng").textContent = lng?.toFixed(6) || "–";
  document.getElementById("gps-acc").textContent = accuracy ? accuracy + " m" : "–";
  document.getElementById("gps-spd").textContent = speed ? speed + " km/h" : "–";
  document.getElementById("gps-src").textContent = source || "–";

  if (lat && lng && state.map && state.mapMarker) {
    const pos = new google.maps.LatLng(lat, lng);
    state.mapMarker.setPosition(pos);
    if (!state.isNavigating && state.map.getZoom() < 16) {
        state.map.setCenter(pos);
    }
    
    // Check navigation progress
    if (state.isNavigating && state.navigationSteps.length > state.currentStepIndex) {
      const step = state.navigationSteps[state.currentStepIndex];
      const dist = google.maps.geometry.spherical.computeDistanceBetween(pos, step.start_location);
      if (dist < 20) { // Within 20 meters of the step start
        const instruction = step.instructions.replace(/<[^>]*>?/gm, '');
        speak("Navigation: " + instruction);
        document.getElementById("nav-instruction").textContent = instruction;
        state.currentStepIndex++;
        if (state.currentStepIndex >= state.navigationSteps.length) {
          speak("You have reached your destination.");
          stopNavigation();
        }
      }
    }
  }
}

function centerMap() {
  if (state.map && state.mapMarker) {
    state.map.setCenter(state.mapMarker.getPosition());
    state.map.setZoom(16);
  }
}

async function startNavigation() {
  if (!state.gps_data || !state.gps_data.latitude) {
    speak("Cannot start navigation without a GPS lock.");
    return;
  }
  const dest = document.getElementById("destination-input").value;
  if (!dest) {
    speak("Please enter a destination.");
    return;
  }

  const origin = new google.maps.LatLng(state.gps_data.latitude, state.gps_data.longitude);
  
  document.getElementById("nav-instruction").textContent = "Calculating route...";
  document.getElementById("nav-instruction").classList.remove("hidden");
  
  state.directionsService.route(
    {
      origin: origin,
      destination: dest,
      travelMode: google.maps.TravelMode.WALKING
    },
    (response, status) => {
      if (status === "OK") {
        state.directionsRenderer.setDirections(response);
        const route = response.routes[0].legs[0];
        state.navigationSteps = route.steps;
        state.currentStepIndex = 0;
        state.isNavigating = true;
        document.getElementById("stop-nav-btn").classList.remove("hidden");
        
        speak(`Starting navigation to ${dest}. ${route.steps[0].instructions.replace(/<[^>]*>?/gm, '')}`);
        document.getElementById("nav-instruction").textContent = route.steps[0].instructions.replace(/<[^>]*>?/gm, '');
      } else {
        speak("Failed to calculate route.");
        document.getElementById("nav-instruction").classList.add("hidden");
      }
    }
  );
}

function stopNavigation() {
  state.isNavigating = false;
  state.navigationSteps = [];
  state.currentStepIndex = 0;
  if (state.directionsRenderer) {
    state.directionsRenderer.setDirections({routes: []});
  }
  document.getElementById("stop-nav-btn").classList.add("hidden");
  document.getElementById("nav-instruction").classList.add("hidden");
  document.getElementById("destination-input").value = "";
  speak("Navigation stopped.");
}

// ── Voice ─────────────────────────────────────────────────────────────────────
function initSpeechRecognition() {
  const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
  if (!SpeechRecognition) return null;
  const rec = new SpeechRecognition();
  rec.continuous = false;
  rec.interimResults = true;
  rec.lang = "en-US";
  return rec;
}

function toggleVoice() {
  if (state.voiceListening) stopVoice(); else startVoice();
}

function startVoice() {
  if (state.voiceListening) return;
  state.recognition = initSpeechRecognition();
  if (!state.recognition) {
    speak("Voice recognition is not supported in this browser.");
    return;
  }

  state.voiceListening = true;
  updateVoiceUI(true);

  state.recognition.onresult = (e) => {
    const transcript = Array.from(e.results)
      .map(r => r[0].transcript).join("");
    document.getElementById("transcript-box").textContent = transcript;
    if (e.results[e.results.length - 1].isFinal) {
      sendVoiceCmd(transcript);
    }
  };

  state.recognition.onerror = () => stopVoice();
  state.recognition.onend   = () => stopVoice();
  state.recognition.start();
}

function stopVoice() {
  state.voiceListening = false;
  state.recognition?.stop();
  updateVoiceUI(false);
}

function updateVoiceUI(listening) {
  const micBig   = document.getElementById("mic-big");
  const micBtn   = document.getElementById("mic-btn");
  const status   = document.getElementById("voice-status");
  const micIcon  = document.getElementById("mic-big-icon");
  const visual   = micBig?.closest(".voice-visual");

  if (listening) {
    micBig?.classList.add("listening");
    micBtn?.classList.add("listening");
    visual?.classList.add("listening");
    status && (status.textContent = "Listening…");
    micIcon && (micIcon.textContent = "🔴");
  } else {
    micBig?.classList.remove("listening");
    micBtn?.classList.remove("listening");
    visual?.classList.remove("listening");
    status && (status.textContent = "Tap microphone to speak");
    micIcon && (micIcon.textContent = "🎤");
  }
}

async function sendVoiceCmd(transcript) {
  document.getElementById("transcript-box").textContent = transcript;
  document.getElementById("response-box").textContent   = "Processing…";
  try {
    const res = await apiFetch("/api/voice/command", {
      method: "POST", body: { transcript }
    });
    const speak_text = res?.speak || res?.result || "Done.";
    document.getElementById("response-box").textContent = speak_text;
    speak(speak_text);
    addCmdHistory(transcript, speak_text, true);
  } catch (e) {
    document.getElementById("response-box").textContent = "Command failed.";
    addCmdHistory(transcript, "Error", false);
  }
}

function addCmdHistory(transcript, response, success) {
  const list = document.getElementById("cmd-history");
  if (list.querySelector(".empty-msg")) list.innerHTML = "";
  const entry = document.createElement("div");
  entry.className = `cmd-entry ${success ? "success" : "error"}`;
  entry.innerHTML = `
    <div class="cmd-transcript">🎤 ${transcript}</div>
    <div class="cmd-response">${response}</div>
  `;
  list.prepend(entry);
  if (list.children.length > 30) list.lastElementChild.remove();
}

// ── TTS ───────────────────────────────────────────────────────────────────────
function speak(text) {
  if (!text || !state.synthesis) return;
  state.synthesis.cancel();
  const utt   = new SpeechSynthesisUtterance(text);
  utt.rate    = state.ttsRate;
  utt.volume  = state.ttsVol;
  utt.pitch   = state.ttsPitch;
  state.synthesis.speak(utt);
}

function stopSpeaking() { state.synthesis?.cancel(); }

function updateTTS() {
  state.ttsRate  = parseFloat(document.getElementById("tts-rate")?.value  || 1);
  state.ttsVol   = parseFloat(document.getElementById("tts-vol")?.value   || 1);
  state.ttsPitch = parseFloat(document.getElementById("tts-pitch")?.value || 1);
}

// ── Alert Banner ──────────────────────────────────────────────────────────────
function showAlertBanner(msg, level = "CRITICAL") {
  const banner = document.getElementById("alert-banner");
  const text   = document.getElementById("alert-text");
  const icon   = document.getElementById("alert-icon");
  banner.className = `alert-banner ${level}`;
  text.textContent = msg;
  icon.textContent = level === "CRITICAL" ? "🚨" : level === "WARNING" ? "⚠️" : "✅";
  banner.classList.remove("hidden");
  if (level !== "CRITICAL") setTimeout(dismissAlert, 5000);
}

function dismissAlert() {
  document.getElementById("alert-banner").classList.add("hidden");
}

// ── Mode switching ────────────────────────────────────────────────────────────
function setMode(mode) {
  state.currentMode = mode;
  document.querySelectorAll(".mode-btn").forEach(b => b.classList.remove("active"));
  document.getElementById(`mode-${mode}`)?.classList.add("active");

  const depthCard = document.getElementById("depth-card");
  if (mode === "depth") depthCard.classList.remove("hidden");
  else depthCard.classList.add("hidden");

  const detCanvas = document.getElementById("detection-canvas");
  if (mode !== "detect") {
    const ctx = detCanvas.getContext("2d");
    ctx.clearRect(0, 0, detCanvas.width, detCanvas.height);
  }
}

function toggleDetection() {
  state.detectionEnabled = !state.detectionEnabled;
  const btn = document.getElementById("btn-detection");
  btn.classList.toggle("active", state.detectionEnabled);
  if (!state.detectionEnabled) {
    const canvas = document.getElementById("detection-canvas");
    canvas.getContext("2d").clearRect(0, 0, canvas.width, canvas.height);
  }
}

// ── Tab switching ─────────────────────────────────────────────────────────────
function switchTab(tab) {
  document.querySelectorAll(".tab-panel").forEach(p => p.classList.remove("active"));
  document.querySelectorAll(".nav-item").forEach(n => n.classList.remove("active"));
  document.getElementById(`tab-${tab}`)?.classList.add("active");
  document.querySelector(`.nav-item[data-tab="${tab}"]`)?.classList.add("active");
  state.activeTab = tab;

  if (tab === "system") { pollSystem(); loadLogs(); }
  if (tab === "map")    { setTimeout(() => state.map?.invalidateSize(), 300); }
  if (tab === "faces")  { loadFaces(); }
  if (tab === "detections") { updateDetectionsTab(); }
}

// ── Faces ─────────────────────────────────────────────────────────────────────
async function loadFaces() {
  try {
    const res  = await apiFetch("/api/faces");
    const grid = document.getElementById("faces-grid");
    if (!res?.people?.length) {
      grid.innerHTML = '<div class="empty-state">No known faces enrolled yet.</div>';
      return;
    }
    grid.innerHTML = res.people.map(p => `
      <div class="face-card">
        <img class="face-photo" src="${API}/api/faces/photo/${p.id}" alt="${p.name}"
             onerror="this.style.display='none'"/>
        <div class="face-name">${p.name}</div>
        <div class="face-actions">
          <button class="face-del-btn" onclick="deleteFace('${p.id}','${p.name}')">🗑 Remove</button>
        </div>
      </div>
    `).join("");

    // Recent sightings
    const sr = await apiFetch("/api/family/recent");
    const sl = document.getElementById("sightings-list");
    if (sr?.sightings?.length) {
      sl.innerHTML = sr.sightings.slice(0, 15).map(s => `
        <div class="sighting-item">
          <span class="sighting-name">${s.name}</span>
          <span class="sighting-time">${s.timestamp}</span>
        </div>
      `).join("");
    } else {
      sl.innerHTML = '<div class="empty-msg">No sightings logged</div>';
    }
  } catch (e) { /* ignore */ }
}

async function deleteFace(id, name) {
  if (!confirm(`Remove ${name}?`)) return;
  await apiFetch(`/api/faces/${id}`, { method: "DELETE" });
  loadFaces();
}

function openEnrollModal()  { document.getElementById("enroll-modal").classList.remove("hidden"); }
function closeEnrollModal() { document.getElementById("enroll-modal").classList.add("hidden"); state.enrollPhotoB64 = null; }

function captureEnrollPhoto() {
  const video  = document.getElementById("webcam-video");
  const canvas = document.createElement("canvas");
  canvas.width  = video.videoWidth  || 640;
  canvas.height = video.videoHeight || 480;
  canvas.getContext("2d").drawImage(video, 0, 0);
  state.enrollPhotoB64 = canvas.toDataURL("image/jpeg", 0.85);
  const prev = document.getElementById("enroll-preview");
  prev.innerHTML = `<img src="${state.enrollPhotoB64}" style="width:100%;height:100%;object-fit:cover"/>`;
}

async function submitEnroll() {
  const name  = document.getElementById("enroll-name").value.trim();
  const photo = state.enrollPhotoB64;
  if (!name)  { alert("Enter a name."); return; }
  if (!photo) { alert("Capture a photo first."); return; }
  try {
    const res = await apiFetch("/api/faces", { method: "POST", body: { name, photo } });
    if (res?.success) {
      closeEnrollModal();
      loadFaces();
    } else {
      alert(res?.error || "Enrollment failed.");
    }
  } catch (e) { alert("Error enrolling face."); }
}

// ── Camera controls ───────────────────────────────────────────────────────────
function takeSnapshot() {
  const video = document.getElementById("webcam-video");
  const canvas = document.createElement("canvas");
  canvas.width  = video.videoWidth;
  canvas.height = video.videoHeight;
  canvas.getContext("2d").drawImage(video, 0, 0);
  const link = document.createElement("a");
  link.download = `visionx-${Date.now()}.jpg`;
  link.href = canvas.toDataURL("image/jpeg", 0.9);
  link.click();
}

function toggleFullscreen() {
  const vp = document.getElementById("camera-viewport");
  if (!document.fullscreenElement) vp.requestFullscreen?.();
  else document.exitFullscreen?.();
}

// ── Auth ──────────────────────────────────────────────────────────────────────
function logout() {
  if (!confirm("Log out?")) return;
  localStorage.removeItem("authToken");
  window.location.href = "login.html";
}

// ── Utilities ─────────────────────────────────────────────────────────────────

function showToast(message, type = "error") {
  const container = document.getElementById("toast-container");
  if (!container) return;
  
  const toast = document.createElement("div");
  toast.className = `toast toast-${type}`;
  toast.innerHTML = `
    <span class="toast-icon">${type === 'error' ? '⚠️' : '✅'}</span>
    <span class="toast-msg">${message}</span>
  `;
  
  container.appendChild(toast);
  
  // Trigger animation
  setTimeout(() => toast.classList.add("show"), 10);
  
  // Remove after 4s
  setTimeout(() => {
    toast.classList.remove("show");
    setTimeout(() => toast.remove(), 300);
  }, 4000);
}

async function apiFetch(path, opts = {}) {
  try {
    const url = API + path;
    const headers = { "Content-Type": "application/json" };
    const token   = localStorage.getItem("authToken");
    if (token) headers["Authorization"] = "Bearer " + token;
    
    // Check if network is totally offline before even fetching
    if (!navigator.onLine) {
      if (!state.networkOfflineWarningShown) {
        showToast("No internet connection.", "error");
        state.networkOfflineWarningShown = true;
      }
      return null;
    } else {
      state.networkOfflineWarningShown = false;
    }

    const res = await fetch(url, {
      method:  opts.method || "GET",
      headers,
      body:    opts.body ? JSON.stringify(opts.body) : undefined,
    });
    
    // Reset global API error flag on success
    state.apiFailing = false;
    
    if (!res.ok) {
      console.warn(`[apiFetch] ${opts.method || 'GET'} ${path} → ${res.status}`);
      if (res.status >= 500) showToast(`Server error on ${path}`, "error");
      return null;
    }
    return res.json();
  } catch (e) {
    console.warn(`[apiFetch] ${path} failed:`, e.message);
    if (!state.apiFailing) {
      showToast("Lost connection to VisionX Backend.", "error");
      state.apiFailing = true;
    }
    return null;
  }
}

function formatUptime(sec) {
  const h = Math.floor(sec / 3600);
  const m = Math.floor((sec % 3600) / 60);
  const s = sec % 60;
  return h > 0 ? `${h}h ${m}m` : m > 0 ? `${m}m ${s}s` : `${s}s`;
}

// ── Explore / Interactive Assistant ──────────────────────────────────────────────

async function queryAssistant(queryText) {
  if (!queryText) return;
  
  // Try to get current frame
  let b64 = null;
  const video = document.getElementById("webcam-video");
  if (video && video.videoWidth) {
    const canvas = document.createElement("canvas");
    canvas.width  = video.videoWidth;
    canvas.height = video.videoHeight;
    canvas.getContext("2d").drawImage(video, 0, 0);
    b64 = canvas.toDataURL("image/jpeg", 0.75);
  }
  
  // Show loading
  const respEl = document.getElementById("explore-response");
  if (respEl) {
    respEl.innerHTML = `<span class="loading-spinner"></span> Thinking about: "${queryText}"...`;
    respEl.classList.remove("hidden");
  }
  
  const ansEl = document.getElementById("explore-main-answer");
  if (ansEl) ansEl.innerHTML = "Thinking...";
  const resCard = document.getElementById("explore-main-result");
  if (resCard) resCard.classList.remove("hidden");
  
  try {
    const res = await apiFetch("/api/assistant/query", {
      method: "POST", body: { query: queryText, image: b64 }
    });
    
    if (res) {
      renderAssistantResult(queryText, res);
      updateExploreHistory(queryText, res.speak);
      speak(res.speak);
    } else {
      if (respEl) respEl.innerHTML = "Sorry, I couldn't process that request.";
      if (ansEl) ansEl.innerHTML = "Sorry, I couldn't process that request.";
    }
  } catch (e) {
    if (respEl) respEl.innerHTML = "An error occurred.";
  }
}

function quickAssistant(queryText) {
  const inputSm = document.getElementById("explore-input");
  const inputLg = document.getElementById("explore-input-lg");
  if (inputSm) inputSm.value = queryText;
  if (inputLg) inputLg.value = queryText;
  queryAssistant(queryText);
}

function submitExploreQuery() {
  const input = document.getElementById("explore-input");
  if (input && input.value) {
    queryAssistant(input.value);
    input.value = "";
  }
}

function submitExploreQueryLg() {
  const input = document.getElementById("explore-input-lg");
  if (input && input.value) {
    queryAssistant(input.value);
    input.value = "";
  }
}

function renderAssistantResult(query, res) {
  // Mini UI
  const respEl = document.getElementById("explore-response");
  if (respEl) {
    let html = `<strong>${res.speak}</strong>`;
    if (res.places && res.places.length > 0) {
      html += `<div style="margin-top:8px; font-size:0.85em; opacity:0.8;">Found: ${res.places[0].name}</div>`;
    }
    respEl.innerHTML = html;
  }
  
  // Full UI
  const ansEl = document.getElementById("explore-main-answer");
  const listEl = document.getElementById("explore-places-list");
  
  if (ansEl) ansEl.innerHTML = res.speak;
  
  if (listEl) {
    if (res.places && res.places.length > 0) {
      listEl.innerHTML = res.places.map(p => `
        <div class="place-item">
          <span class="p-name">${p.name}</span>
          <span class="p-dist">${Math.round(p.distance)}m away</span>
        </div>
      `).join("");
    } else {
      listEl.innerHTML = "";
    }
  }
}

function updateExploreHistory(query, response) {
  const list = document.getElementById("assistant-history");
  if (!list) return;
  if (list.querySelector(".empty-msg")) list.innerHTML = "";
  
  const entry = document.createElement("div");
  entry.className = "history-item";
  entry.innerHTML = `
    <div class="history-q">👤 ${query}</div>
    <div class="history-a">🤖 ${response}</div>
  `;
  list.prepend(entry);
  if (list.children.length > 20) list.lastElementChild.remove();
}

function clearExploreHistory() {
  const list = document.getElementById("assistant-history");
  if (list) list.innerHTML = '<div class="empty-msg">Ask a question to see history</div>';
}

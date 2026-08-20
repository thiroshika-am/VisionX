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
  lastGuidanceAction: null,
  directionsService:  null,
  directionsRenderer: null,
  navigationSteps:    [],
  currentStepIndex:   0,
  isNavigating:       false,
  gps_data:           null,
  lastDetections:     [],
  navTickInterval:    null,
  language:           "en",
  ttsLang:            "en-US",
  isScanning360:      false,
  scanDetections:     [],
  scanTimeoutId:      null,
};

const TRANSLATIONS = {
  "en": {
    "obs_ahead_left": "Obstacle ahead, turn left.",
    "obs_ahead_right": "Obstacle ahead, turn right.",
    "path_blocked": "Path blocked, please stop.",
    "obs_left_right": "Obstacle on left, stay right.",
    "obs_right_left": "Obstacle on right, stay left.",
    "obs_both_center": "Obstacles on both sides, stay center.",
    "obs_both_stop": "Obstacles on both sides. Please stop and find a new path.",
    "nav_reached": "You have reached your destination.",
    "nav_stopped": "Navigation stopped.",
    "nav_start": "Starting navigation to",
    "calc_route": "Calculating route...",
    "fail_route": "Failed to calculate route.",
    "no_gps": "Cannot start navigation without a GPS lock.",
    "no_dest": "Please enter a destination.",
    "nav_instruction": "Navigation:",
    "scan_start": "Please slowly turn around in a full circle to scan the area.",
    "scan_clear_right": "Scan complete. Clear path to your right. Turn right.",
    "scan_clear_left": "Scan complete. Clear path to your left. Turn left.",
    "scan_clear_center": "Scan complete. Path ahead is clear.",
    "scan_blocked": "Scan complete. No clear path found."
  },
  "ta": {
    "obs_ahead_left": "முன்னே தடை, இடதுபுறம் திரும்பவும்.",
    "obs_ahead_right": "முன்னே தடை, வலதுபுறம் திரும்பவும்.",
    "path_blocked": "பாதை தடைபட்டுள்ளது, தயவுசெய்து நிற்கவும்.",
    "obs_left_right": "இடதுபுறம் தடை, வலதுபுறம் செல்லவும்.",
    "obs_right_left": "வலதுபுறம் தடை, இடதுபுறம் செல்லவும்.",
    "obs_both_center": "இருபுறமும் தடைகள், நடுவில் செல்லவும்.",
    "obs_both_stop": "இருபுறமும் தடைகள். தயவுசெய்து நின்று புதிய பாதையை தேடவும்.",
    "nav_reached": "நீங்கள் உங்கள் இலக்கை அடைந்துவிட்டீர்கள்.",
    "nav_stopped": "வழிசெலுத்தல் நிறுத்தப்பட்டது.",
    "nav_start": "வழிசெலுத்தல் தொடங்குகிறது",
    "calc_route": "பாதையை கணக்கிடுகிறது...",
    "fail_route": "பாதையை கணக்கிட முடியவில்லை.",
    "no_gps": "ஜிபிஎஸ் இல்லாமல் வழிசெலுத்தலை தொடங்க முடியாது.",
    "no_dest": "தயவுசெய்து ஒரு இலக்கை உள்ளிடவும்.",
    "nav_instruction": "வழிசெலுத்தல்:",
    "scan_start": "பகுதியை ஸ்கேன் செய்ய தயவுசெய்து முழு வட்டமாக திரும்பவும்.",
    "scan_clear_right": "ஸ்கேன் முடிந்தது. வலதுபுறம் பாதை தெளிவாக உள்ளது.",
    "scan_clear_left": "ஸ்கேன் முடிந்தது. இடதுபுறம் பாதை தெளிவாக உள்ளது.",
    "scan_clear_center": "ஸ்கேன் முடிந்தது. முன்னே பாதை தெளிவாக உள்ளது.",
    "scan_blocked": "ஸ்கேன் முடிந்தது. தெளிவான பாதை இல்லை."
  },
  "fr": {
    "obs_ahead_left": "Obstacle devant, tournez à gauche.",
    "obs_ahead_right": "Obstacle devant, tournez à droite.",
    "path_blocked": "Chemin bloqué, veuillez vous arrêter.",
    "obs_left_right": "Obstacle à gauche, restez à droite.",
    "obs_right_left": "Obstacle à droite, restez à gauche.",
    "obs_both_center": "Obstacles des deux côtés, restez au centre.",
    "obs_both_stop": "Obstacles des deux côtés. Veuillez vous arrêter et trouver un nouveau chemin.",
    "nav_reached": "Vous êtes arrivé à votre destination.",
    "nav_stopped": "Navigation arrêtée.",
    "nav_start": "Démarrage de la navigation vers",
    "calc_route": "Calcul de l'itinéraire...",
    "fail_route": "Échec du calcul de l'itinéraire.",
    "no_gps": "Impossible de démarrer la navigation sans GPS.",
    "no_dest": "Veuillez entrer une destination.",
    "nav_instruction": "Navigation :",
    "scan_start": "Veuillez tourner lentement sur vous-même pour scanner la zone.",
    "scan_clear_right": "Scan terminé. Chemin dégagé à droite. Tournez à droite.",
    "scan_clear_left": "Scan terminé. Chemin dégagé à gauche. Tournez à gauche.",
    "scan_clear_center": "Scan terminé. Le chemin devant est dégagé.",
    "scan_blocked": "Scan terminé. Aucun chemin dégagé trouvé."
  },
  "ja": {
    "obs_ahead_left": "前方に障害物、左に曲がってください。",
    "obs_ahead_right": "前方に障害物、右に曲がってください。",
    "path_blocked": "道が塞がれています、止まってください。",
    "obs_left_right": "左に障害物、右に寄ってください。",
    "obs_right_left": "右に障害物、左に寄ってください。",
    "obs_both_center": "両側に障害物、中央を進んでください。",
    "obs_both_stop": "両側に障害物。止まって新しい道を探してください。",
    "nav_reached": "目的地に到着しました。",
    "nav_stopped": "ナビゲーションを停止しました。",
    "nav_start": "ナビゲーションを開始します",
    "calc_route": "ルートを計算中...",
    "fail_route": "ルートの計算に失敗しました。",
    "no_gps": "GPSが取得できないためナビゲーションを開始できません。",
    "no_dest": "目的地を入力してください。",
    "nav_instruction": "ナビゲーション:",
    "scan_start": "エリアをスキャンするため、ゆっくりと一周回ってください。",
    "scan_clear_right": "スキャン完了。右側の道がクリアです。右に曲がってください。",
    "scan_clear_left": "スキャン完了。左側の道がクリアです。左に曲がってください。",
    "scan_clear_center": "スキャン完了。前方の道がクリアです。",
    "scan_blocked": "スキャン完了。クリアな道が見つかりません。"
  },
  "hi": {
    "obs_ahead_left": "आगे बाधा है, बाएं मुड़ें।",
    "obs_ahead_right": "आगे बाधा है, दाएं मुड़ें।",
    "path_blocked": "रास्ता बंद है, कृपया रुकें।",
    "obs_left_right": "बाएं बाधा है, दाएं रहें।",
    "obs_right_left": "दाएं बाधा है, बाएं रहें।",
    "obs_both_center": "दोनों तरफ बाधाएं हैं, बीच में रहें।",
    "obs_both_stop": "दोनों तरफ बाधाएं हैं। कृपया रुकें और नया रास्ता खोजें।",
    "nav_reached": "आप अपने गंतव्य पर पहुंच गए हैं।",
    "nav_stopped": "नेविगेशन बंद कर दिया गया है।",
    "nav_start": "नेविगेशन शुरू कर रहा है",
    "calc_route": "मार्ग की गणना कर रहा है...",
    "fail_route": "मार्ग की गणना करने में विफल।",
    "no_gps": "जीपीएस के बिना नेविगेशन शुरू नहीं किया जा सकता।",
    "no_dest": "कृपया एक गंतव्य दर्ज करें।",
    "nav_instruction": "नेविगेशन:",
    "scan_start": "कृपया क्षेत्र को स्कैन करने के लिए धीरे-धीरे एक पूरा चक्कर घूमें।",
    "scan_clear_right": "स्कैन पूरा हुआ। आपके दाईं ओर रास्ता साफ है। दाएं मुड़ें।",
    "scan_clear_left": "स्कैन पूरा हुआ। आपके बाईं ओर रास्ता साफ है। बाएं मुड़ें।",
    "scan_clear_center": "स्कैन पूरा हुआ। आगे का रास्ता साफ है।",
    "scan_blocked": "स्कैन पूरा हुआ। कोई साफ रास्ता नहीं मिला।"
  },
  "es": {
    "obs_ahead_left": "Obstáculo adelante, gire a la izquierda.",
    "obs_ahead_right": "Obstáculo adelante, gire a la derecha.",
    "path_blocked": "Camino bloqueado, por favor deténgase.",
    "obs_left_right": "Obstáculo a la izquierda, manténgase a la derecha.",
    "obs_right_left": "Obstáculo a la derecha, manténgase a la izquierda.",
    "obs_both_center": "Obstáculos a ambos lados, manténgase en el centro.",
    "obs_both_stop": "Obstáculos a ambos lados. Por favor deténgase y busque un nuevo camino.",
    "nav_reached": "Ha llegado a su destino.",
    "nav_stopped": "Navegación detenida.",
    "nav_start": "Iniciando navegación hacia",
    "calc_route": "Calculando ruta...",
    "fail_route": "Error al calcular la ruta.",
    "no_gps": "No se puede iniciar la navegación sin GPS.",
    "no_dest": "Por favor ingrese un destino.",
    "nav_instruction": "Navegación:",
    "scan_start": "Por favor, gire lentamente en círculo para escanear el área.",
    "scan_clear_right": "Escaneo completo. Camino despejado a su derecha.",
    "scan_clear_left": "Escaneo completo. Camino despejado a su izquierda.",
    "scan_clear_center": "Escaneo completo. El camino de enfrente está despejado.",
    "scan_blocked": "Escaneo completo. No se encontró un camino despejado."
  },
  "de": {
    "obs_ahead_left": "Hindernis voraus, links abbiegen.",
    "obs_ahead_right": "Hindernis voraus, rechts abbiegen.",
    "path_blocked": "Weg blockiert, bitte anhalten.",
    "obs_left_right": "Hindernis links, rechts halten.",
    "obs_right_left": "Hindernis rechts, links halten.",
    "obs_both_center": "Hindernisse auf beiden Seiten, in der Mitte bleiben.",
    "obs_both_stop": "Hindernisse auf beiden Seiten. Bitte anhalten und neuen Weg finden.",
    "nav_reached": "Sie haben Ihr Ziel erreicht.",
    "nav_stopped": "Navigation gestoppt.",
    "nav_start": "Starte Navigation nach",
    "calc_route": "Route berechnen...",
    "fail_route": "Route konnte nicht berechnet werden.",
    "no_gps": "Navigation ohne GPS nicht möglich.",
    "no_dest": "Bitte Ziel eingeben.",
    "nav_instruction": "Navigation:",
    "scan_start": "Bitte drehen Sie sich langsam im Kreis, um die Umgebung zu scannen.",
    "scan_clear_right": "Scan abgeschlossen. Weg frei auf der rechten Seite.",
    "scan_clear_left": "Scan abgeschlossen. Weg frei auf der linken Seite.",
    "scan_clear_center": "Scan abgeschlossen. Der Weg geradeaus ist frei.",
    "scan_blocked": "Scan abgeschlossen. Kein freier Weg gefunden."
  },
  "zh": {
    "obs_ahead_left": "前方有障碍物，向左转。",
    "obs_ahead_right": "前方有障碍物，向右转。",
    "path_blocked": "道路受阻，请停止。",
    "obs_left_right": "左侧有障碍物，靠右行。",
    "obs_right_left": "右侧有障碍物，靠左行。",
    "obs_both_center": "两侧都有障碍物，保持在中间。",
    "obs_both_stop": "两侧都有障碍物。请停止并寻找新路线。",
    "nav_reached": "您已到达目的地。",
    "nav_stopped": "导航已停止。",
    "nav_start": "开始导航至",
    "calc_route": "正在计算路线...",
    "fail_route": "计算路线失败。",
    "no_gps": "没有GPS信号，无法开始导航。",
    "no_dest": "请输入目的地。",
    "nav_instruction": "导航:",
    "scan_start": "请慢慢转一整圈以扫描周围区域。",
    "scan_clear_right": "扫描完成。右侧道路畅通，请右转。",
    "scan_clear_left": "扫描完成。左侧道路畅通，请左转。",
    "scan_clear_center": "扫描完成。前方道路畅通。",
    "scan_blocked": "扫描完成。未找到畅通的道路。"
  },
  "ar": {
    "obs_ahead_left": "عقبة في الأمام، انعطف يساراً.",
    "obs_ahead_right": "عقبة في الأمام، انعطف يميناً.",
    "path_blocked": "الطريق مسدود، يرجى التوقف.",
    "obs_left_right": "عقبة على اليسار، ابق على اليمين.",
    "obs_right_left": "عقبة على اليمين، ابق على اليسار.",
    "obs_both_center": "عقبات على كلا الجانبين، ابق في الوسط.",
    "obs_both_stop": "عقبات على كلا الجانبين. يرجى التوقف والبحث عن طريق جديد.",
    "nav_reached": "لقد وصلت إلى وجهتك.",
    "nav_stopped": "تم إيقاف الملاحة.",
    "nav_start": "بدء الملاحة إلى",
    "calc_route": "جاري حساب المسار...",
    "fail_route": "فشل في حساب المسار.",
    "no_gps": "لا يمكن بدء الملاحة بدون نظام تحديد المواقع.",
    "no_dest": "الرجاء إدخال الوجهة.",
    "nav_instruction": "الملاحة:",
    "scan_start": "يرجى الدوران ببطء في دائرة كاملة لمسح المنطقة.",
    "scan_clear_right": "اكتمل المسح. مسار واضح على يمينك.",
    "scan_clear_left": "اكتمل المسح. مسار واضح على يسارك.",
    "scan_clear_center": "اكتمل المسح. المسار أمامك واضح.",
    "scan_blocked": "اكتمل المسح. لم يتم العثور على مسار واضح."
  },
  "ru": {
    "obs_ahead_left": "Впереди препятствие, поверните налево.",
    "obs_ahead_right": "Впереди препятствие, поверните направо.",
    "path_blocked": "Путь заблокирован, пожалуйста, остановитесь.",
    "obs_left_right": "Препятствие слева, держитесь правее.",
    "obs_right_left": "Препятствие справа, держитесь левее.",
    "obs_both_center": "Препятствия с обеих сторон, держитесь центра.",
    "obs_both_stop": "Препятствия с обеих сторон. Пожалуйста, остановитесь и найдите новый путь.",
    "nav_reached": "Вы достигли пункта назначения.",
    "nav_stopped": "Навигация остановлена.",
    "nav_start": "Запуск навигации к",
    "calc_route": "Расчет маршрута...",
    "fail_route": "Не удалось рассчитать маршрут.",
    "no_gps": "Невозможно начать навигацию без GPS.",
    "no_dest": "Пожалуйста, введите пункт назначения.",
    "nav_instruction": "Навигация:",
    "scan_start": "Пожалуйста, медленно повернитесь на 360 градусов для сканирования зоны.",
    "scan_clear_right": "Сканирование завершено. Путь свободен справа.",
    "scan_clear_left": "Сканирование завершено. Путь свободен слева.",
    "scan_clear_center": "Сканирование завершено. Путь впереди свободен.",
    "scan_blocked": "Сканирование завершено. Свободный путь не найден."
  }
};

function t(key) {
  const lang = state.language || "en";
  return TRANSLATIONS[lang] ? (TRANSLATIONS[lang][key] || TRANSLATIONS["en"][key]) : TRANSLATIONS["en"][key];
}

function changeLanguage(lang, ttsCode) {
  state.language = lang;
  state.ttsLang = ttsCode;
}

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
    state.lastDetections = res.detections || [];
    drawDetections(res.detections || []);
    updateLiveDetections(res.detections || []);
    updateAlertLevel(res.alert_level || "SAFE");
    addToHistory(res.detections || []);

    provideGuidance(res.detections || []);
  } catch (e) { /* ignore */ }
}

function start360Scan() {
  if (state.isScanning360) return;
  state.isScanning360 = true;
  state.scanDetections = [];
  speak(t("scan_start"));
  const navInstr = document.getElementById("nav-instruction");
  if (navInstr) {
    navInstr.textContent = t("scan_start");
    navInstr.classList.remove("hidden");
  }
  state.scanTimeoutId = setTimeout(finish360Scan, 10000); // 10s scan
}

function finish360Scan() {
  state.isScanning360 = false;
  
  let leftHits = 0, centerHits = 0, rightHits = 0;
  state.scanDetections.forEach(d => {
    if (d.alert_level === "CRITICAL" || d.alert_level === "WARNING") {
      const pos = d.position || "center";
      if (pos.includes("left")) leftHits++;
      if (pos.includes("center")) centerHits++;
      if (pos.includes("right")) rightHits++;
    }
  });

  let msg = t("scan_blocked");
  if (centerHits <= leftHits && centerHits <= rightHits && centerHits < 15) {
    msg = t("scan_clear_center");
  } else if (rightHits <= leftHits && rightHits < 15) {
    msg = t("scan_clear_right");
  } else if (leftHits < 15) {
    msg = t("scan_clear_left");
  }
  
  const navInstr = document.getElementById("nav-instruction");
  if (navInstr) {
    navInstr.textContent = msg;
    navInstr.classList.remove("hidden");
    setTimeout(() => navInstr.classList.add("hidden"), 5000);
  }
  speak(msg);
}

function provideGuidance(detections) {
  if (state.isScanning360) {
    state.scanDetections.push(...detections);
    return;
  }

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
  let action = "";

  // Time since last guidance to check for ping-ponging
  const timeSinceLastGuidance = now - (state.lastGuidanceTime || 0);
  const memoryActive = timeSinceLastGuidance < 10000; // 10 seconds memory

  if (centerBlocked) {
    if (!leftBlocked) {
      msg = t("obs_ahead_left");
      action = "turn_left";
    } else if (!rightBlocked) {
      msg = t("obs_ahead_right");
      action = "turn_right";
    } else {
      start360Scan();
      return;
    }
  } else if (leftBlocked && !rightBlocked) {
    // Cross-check: If we recently turned left to avoid a right obstacle, we might be ping-ponging
    if (memoryActive && state.lastGuidanceAction === "stay_left") {
      start360Scan();
      return;
    } else {
      msg = t("obs_left_right");
      action = "stay_right";
    }
  } else if (rightBlocked && !leftBlocked) {
    // Cross-check: If we recently turned right to avoid a left obstacle, we might be ping-ponging
    if (memoryActive && state.lastGuidanceAction === "stay_right") {
      start360Scan();
      return;
    } else {
      msg = t("obs_right_left");
      action = "stay_left";
    }
  } else if (leftBlocked && rightBlocked) {
    msg = t("obs_both_center");
    action = "stay_center";
  }

  if (msg) {
    state.lastGuidanceTime = now;
    state.lastGuidanceAction = action;
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
      method: "POST", body: { image: b64, include_scene: true, language: state.language }
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
      const dist = google.maps.geometry.spherical.computeDistanceBetween(pos, step.end_location);
      if (dist < 20) { // Within 20 meters of the step end
        state.currentStepIndex++;
        if (state.currentStepIndex >= state.navigationSteps.length) {
          speak(t("nav_reached"));
          stopNavigation();
        } else {
          const nextStep = state.navigationSteps[state.currentStepIndex];
          const instruction = nextStep.instructions.replace(/<[^>]*>?/gm, '');
          speak(`${t("nav_instruction")} ${instruction}`);
          document.getElementById("nav-instruction").textContent = instruction;
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
    speak(t("no_gps"));
    return;
  }
  const dest = document.getElementById("destination-input").value;
  if (!dest) {
    speak(t("no_dest"));
    return;
  }

  const origin = new google.maps.LatLng(state.gps_data.latitude, state.gps_data.longitude);
  
  document.getElementById("nav-instruction").textContent = t("calc_route");
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
        
        if (state.navTickInterval) clearInterval(state.navTickInterval);
        state.navTickInterval = setInterval(navigationTick, 4000);
        
        
        speak(`${t("nav_start")} ${dest}. ${route.steps[0].instructions.replace(/<[^>]*>?/gm, '')}`);
        document.getElementById("nav-instruction").textContent = route.steps[0].instructions.replace(/<[^>]*>?/gm, '');
      } else {
        speak(t("fail_route"));
        document.getElementById("nav-instruction").classList.add("hidden");
      }
    }
  );
}

function stopNavigation() {
  state.isNavigating = false;
  state.navigationSteps = [];
  state.currentStepIndex = 0;
  if (state.navTickInterval) {
    clearInterval(state.navTickInterval);
    state.navTickInterval = null;
  }
  if (state.directionsRenderer) {
    state.directionsRenderer.setDirections({routes: []});
  }
  document.getElementById("stop-nav-btn").classList.add("hidden");
  document.getElementById("nav-instruction").classList.add("hidden");
  document.getElementById("destination-input").value = "";
  speak(t("nav_stopped"));
}

function navigationTick() {
  if (!state.isNavigating) return;

  const obstacles = state.lastDetections.filter(d => d.alert_level === "CRITICAL" || d.alert_level === "WARNING");
  const centerBlocked = obstacles.some(d => d.position === "center");
  const rightBlocked = obstacles.some(d => d.position === "right");
  const leftBlocked = obstacles.some(d => d.position === "left");

  if (centerBlocked) {
    if (rightBlocked && leftBlocked) {
      speak("Path entirely blocked. Rerouting...");
      startNavigation(); // Re-trigger startNavigation to compute new route from current GPS
    } else if (rightBlocked) {
      speak("Obstacle ahead and right. Turn left, move forward.");
    } else {
      speak("Obstacle ahead. Turn right, move forward.");
    }
  } else {
    speak("Move forward.");
  }
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
      method: "POST", body: { transcript, language: state.language }
    });
    
    if (res?.action === "nav_start" && res?.params?.destination) {
      document.getElementById("destination-input").value = res.params.destination;
      document.getElementById("response-box").textContent = res?.speak || `Navigating to ${res.params.destination}`;
      startNavigation(); // This sets up the route and handles its own speech!
      addCmdHistory(transcript, res?.speak || "Starting navigation", true);
      return; 
    }
    
    if (res?.action === "nav_stop") {
      stopNavigation();
      document.getElementById("response-box").textContent = t("nav_stopped");
      addCmdHistory(transcript, "Navigation stopped", true);
      return;
    }

    if (res?.action === "sos_trigger") {
      // Create a visual SOS alert on the dashboard
      const viewport = document.getElementById("camera-viewport");
      if (viewport) {
        let sosBanner = document.createElement("div");
        sosBanner.className = "camera-offline-overlay";
        sosBanner.style.backgroundColor = "rgba(255, 0, 0, 0.8)";
        sosBanner.innerHTML = `<span>🆘 SOS EMERGENCY TRIGGERED 🆘</span><p>Alerting contacts...</p>`;
        viewport.appendChild(sosBanner);
        setTimeout(() => sosBanner.remove(), 5000);
      }
    }

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
  utt.lang    = state.ttsLang || "en-US";
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
      method: "POST", body: { query: queryText, image: b64, language: state.language }
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

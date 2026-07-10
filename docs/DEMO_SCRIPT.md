# VisionX — Competition Demo Script

**Audience:** Judges, investors, hackathon evaluators
**Duration:** 3–5 minutes
**Setup:** Laptop + webcam (or ESP32-CAM), dashboard on screen

---

## Pre-Demo Checklist
- [ ] Backend running: `python backend/main.py`
- [ ] Browser open to `http://localhost:5000`
- [ ] Logged in to dashboard
- [ ] Camera feed visible in Live tab
- [ ] Audio on — TTS working
- [ ] Props ready: printed text card, currency note, second person nearby

---

## Demo Script

### 1. Introduction (30 sec)
*Point to dashboard*
> "VisionX is an AI-powered wearable assistant for visually impaired people.
> It runs on a Raspberry Pi 5 and an ESP32-CAM worn on the head.
> It understands the user's surroundings in real time and communicates through audio."

### 2. Object Detection (45 sec)
*Walk toward the camera*
> "When a person approaches, the system immediately detects them and says…"
*The TTS fires: "Person detected, 1.2 meters ahead, Critical"*
> "The alert level changes from Safe to Critical, and the ESP32 vibrates on the user's wrist."

### 3. OCR — Text Reading (30 sec)
*Hold up printed text card. Click OCR mode.*
> "When a user encounters a sign or document, they say 'Read this'…"
*Click 'Read Text' quick command*
*TTS reads the text from the card*

### 4. Scene Description (30 sec)
*Click 'Describe Scene'*
> "The scene description mode uses AI to generate a natural language summary of the entire environment."
*Wait for response, it speaks the description*

### 5. Currency Detection (30 sec)
*Hold up currency note. Click 'Identify Currency'.*
> "The system can identify currency notes — vital for financial independence."
*TTS: "This looks like a 500 rupee note"*

### 6. Voice Commands (45 sec)
*Click mic button and say: "Where am I?"*
> "All features are voice-controlled. The user says 'Where am I?'"
*TTS reads GPS coordinates*
*Then say: "Who is near me?"*

### 7. Face Recognition (30 sec)
*Have a second person step in front of camera*
> "The system recognizes enrolled family members and announces them."
*TTS: "[Name] is nearby"*

### 8. System Monitor (20 sec)
*Switch to System tab*
> "Judges can see real-time performance: CPU, RAM, and inference FPS.
> On a Raspberry Pi 5, we achieve 20–30 FPS for object detection."

### 9. Close (30 sec)
> "VisionX gives visually impaired users independence: they can navigate safely,
> identify people, read text, and communicate using only their voice.
> It runs fully offline on a wearable the size of a headband.
> Thank you."

---

## Key Talking Points

| Feature | Technical Achievement |
|---------|----------------------|
| Real-time detection | YOLOv11n @ 20-30 FPS on Raspberry Pi 5 |
| Smart alerts | Priority scoring prevents alert fatigue |
| Offline | No cloud dependency for detection/OCR/face |
| Modular | 14 AI modules, priority scheduler |
| Wearable | ESP32-CAM + Raspberry Pi 5, < 200g total |
| Battery | 10 000 mAh → 6+ hours runtime |

"""
Smart Interactive Assistant for VisionX
Handles universal queries: places, people, objects, medicine, and text reading.
Combines YOLO, Face Recognition, OCR, Places APIs, and LLMs.
"""

import os
import json
import logging
import requests
import time
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger("smartcap")

# Attempt to load AI modules for routing
try:
    from ai_modules.detector import get_detector
except ImportError:
    pass

try:
    from ai_modules.ocr_engine import get_ocr_reader
except ImportError:
    pass

try:
    from ai_modules.face_recognition_engine import get_face_engine
except ImportError:
    pass

try:
    from ai_modules.llm_alerts import get_alert_generator
except ImportError:
    pass

try:
    from src.ai.scene_understander import get_scene_understander
except ImportError:
    pass


class InteractiveAssistant:
    def __init__(self, config=None):
        self.config = config or {}
        self.settings = self.config.get("modules", {}).get("interactive_assistant", {})
        self.search_radius = self.settings.get("search_radius_m", 500)
        self.google_key = self.settings.get("google_places_api_key", "")
        self.provider = self.settings.get("places_provider", "auto")
        
        # Keyword mappings for Place Intent
        self.place_keywords = {
            "supermarket": ["supermarket", "grocery", "store", "shop"],
            "restaurant": ["restaurant", "food", "eat", "cafe", "dining"],
            "pharmacy": ["pharmacy", "medicine shop", "medical store", "chemist"],
            "bank": ["bank", "atm", "cash"],
            "hospital": ["hospital", "clinic", "doctor", "medical center"],
            "bus_station": ["bus stop", "bus station", "bus"],
            "gas_station": ["gas station", "petrol pump", "fuel"],
            "lodging": ["hotel", "stay", "lodge", "motel"],
            "park": ["park", "garden", "playground"],
            "public_restroom": ["toilet", "restroom", "bathroom", "washroom"]
        }
        
        # Keyword mappings for YOLO Object Intent
        self.object_keywords = {
            "bottle": ["water bottle", "bottle"],
            "cell phone": ["phone", "mobile", "cell phone", "smartphone"],
            "laptop": ["laptop", "computer", "pc"],
            "backpack": ["bag", "backpack", "rucksack"],
            "chair": ["chair", "seat", "stool"],
            "cup": ["cup", "mug", "glass"],
            "book": ["book", "notebook", "magazine"],
            "umbrella": ["umbrella"]
        }
        
    def query(self, question: str, image_b64: Optional[str], gps: Dict, language: str = "en") -> Dict:
        """Main entry point to handle a user query."""
        logger.info(f"[Assistant] Received query: '{question}'")
        
        q_lower = question.lower()
        
        # 1. Classify Intent
        intent = self._classify_query(q_lower)
        logger.info(f"[Assistant] Classified intent: {intent}")
        
        # 2. Route to Handler
        if intent == "find_place":
            return self._handle_find_place(q_lower, image_b64, gps, language)
        elif intent == "find_person":
            return self._handle_find_person(image_b64, language)
        elif intent == "find_object":
            return self._handle_find_object(q_lower, image_b64, language)
        elif intent == "read_text":
            return self._handle_read_text(q_lower, image_b64, language)
        elif intent == "path_check":
            return self._handle_path_check(image_b64, language)
        else:
            return self._handle_identify(image_b64, language)

    def _classify_query(self, q: str) -> str:
        if any(w in q for w in ["person", "someone", "anyone", "people", "who"]):
            return "find_person"
        
        if any(w in q for w in ["read", "tablet name", "medicine", "prescription", "label", "sign", "what does it say"]):
            return "read_text"
            
        if any(w in q for w in ["path clear", "blocking", "obstacle", "safe to walk"]):
            return "path_check"
            
        if "what am i holding" in q or "what is this" in q or "identify" in q:
            return "identify"
            
        # Check places
        for place_type, keywords in self.place_keywords.items():
            if any(k in q for k in keywords):
                return "find_place"
                
        # Check objects (if not caught by others, and looks like a "where is" or "find")
        if "where is" in q or "find" in q or "see" in q:
            return "find_object"
            
        return "identify"

    # ── Handlers ──────────────────────────────────────────────────────────────

    def _handle_find_place(self, q: str, image_b64: Optional[str], gps: Dict, language: str) -> Dict:
        # Determine place type
        target_type = "store" # default
        for p_type, keywords in self.place_keywords.items():
            if any(k in q for k in keywords):
                target_type = p_type
                break
                
        logger.info(f"[Assistant] Searching for place type: {target_type}")
        
        places_results = []
        lat = gps.get("latitude")
        lng = gps.get("longitude")
        
        if lat and lng:
            # Prefer Google if key exists and provider is auto/google
            if self.google_key and self.provider in ["auto", "google"]:
                places_results = self._search_places_google(lat, lng, target_type)
                
            # Fallback to OSM
            if not places_results and self.provider in ["auto", "osm"]:
                places_results = self._search_places_osm(lat, lng, target_type)
        else:
            logger.warning("[Assistant] No GPS data available for place search.")

        # Check camera for context (OCR)
        camera_text = ""
        if image_b64:
            try:
                ocr_res = get_ocr_reader().detect_from_base64(image_b64)
                camera_text = ocr_res.get("combined_text", "")
            except Exception as e:
                logger.error(f"[Assistant] OCR error: {e}")

        # Compose response
        llm = None
        try:
            llm = get_alert_generator()
        except:
            pass

        speak_text = ""
        if not places_results:
            speak_text = f"I couldn't find any {target_type.replace('_', ' ')}s nearby."
        else:
            first_place = places_results[0]
            dist_str = f" about {int(first_place['distance'])} meters away" if 'distance' in first_place else ""
            speak_text = f"Yes, there's a {first_place['name']}{dist_str}."

        if camera_text:
            speak_text += f" I can also see a sign that reads: '{camera_text}'."

        if llm and llm.llm_client:
            # Enhance with LLM if available
            prompt = f"User asked: '{q}'. Found places: {json.dumps(places_results[:3])}. Visible sign text: '{camera_text}'. Give a short, natural spoken response. You MUST reply in the language with code: {language}."
            try:
                if llm.llm_provider in ["groq", "openai"]:
                    resp = llm.llm_client.chat.completions.create(
                        model="llama-3.3-70b-versatile" if llm.llm_provider == "groq" else "gpt-4o-mini",
                        messages=[{"role": "user", "content": prompt}],
                        max_tokens=60
                    )
                    speak_text = resp.choices[0].message.content.strip().strip('"\'')
                elif llm.llm_provider == "gemini":
                    resp = llm.llm_client.generate_content(prompt)
                    speak_text = resp.text.strip().strip('"\'')
            except Exception as e:
                logger.error(f"[Assistant] LLM enhance error: {e}")

        return {
            "intent": "find_place",
            "speak": speak_text,
            "places": places_results,
            "camera_text": camera_text
        }

    def _handle_find_person(self, image_b64: Optional[str], language: str) -> Dict:
        if not image_b64:
            return {"speak": "I can't see the camera feed right now."}
            
        try:
            det_res = get_detector().detect_from_base64(image_b64)
            detections = det_res.get("detections", [])
            people_dets = [d for d in detections if d.get("class") == "person"]
            
            # Face recognition
            faces = []
            try:
                face_res = get_face_engine().detect_faces(image_b64)
                faces = face_res.get("faces", [])
            except:
                pass
                
            known_faces = [f for f in faces if f.get("is_known")]
            
            if not people_dets:
                return {"speak": "I don't see anyone near you right now."}
                
            count = len(people_dets)
            speak_text = f"I see {count} {'person' if count == 1 else 'people'} near you."
            
            # Detail closest person
            closest = min(people_dets, key=lambda x: x.get("distance_m", 99))
            dist = closest.get("distance", "unknown distance")
            pos = closest.get("position", "ahead")
            speak_text += f" The closest person is {dist} {pos}."
            
            if known_faces:
                names = ", ".join([f["name"] for f in known_faces])
                speak_text += f" I also recognize {names}."
                
            return {
                "intent": "find_person",
                "speak": speak_text,
                "people_count": count,
                "known_faces": [f["name"] for f in known_faces]
            }
        except Exception as e:
            logger.error(f"[Assistant] Person find error: {e}")
            return {"speak": "I had trouble analyzing people in the scene."}

    def _handle_find_object(self, q: str, image_b64: Optional[str], language: str) -> Dict:
        if not image_b64:
            return {"speak": "I can't see the camera feed right now."}
            
        # Map target class
        target_class = None
        for cls, keywords in self.object_keywords.items():
            if any(k in q for k in keywords):
                target_class = cls
                break
                
        if not target_class:
            return {"speak": "I'm not sure which object you are looking for."}
            
        try:
            det_res = get_detector().detect_from_base64(image_b64)
            detections = det_res.get("detections", [])
            
            matches = [d for d in detections if d.get("class") == target_class]
            
            if not matches:
                return {"speak": f"I don't see a {target_class} in view. Try looking around."}
                
            obj = matches[0]
            dist = obj.get("distance", "unknown distance")
            pos = obj.get("position", "ahead")
            
            speak_text = f"I can see a {target_class} {dist} on your {pos}."
            
            return {
                "intent": "find_object",
                "speak": speak_text,
                "object_found": target_class,
                "distance": dist,
                "position": pos
            }
        except Exception as e:
            return {"speak": "I had trouble scanning for that object."}

    def _handle_read_text(self, q: str, image_b64: Optional[str], language: str) -> Dict:
        if not image_b64:
            return {"speak": "I can't see the camera feed right now."}
            
        try:
            ocr_res = get_ocr_reader().detect_from_base64(image_b64)
            text = ocr_res.get("combined_text", "")
            
            if not text:
                return {"speak": "I don't see any text right now."}
                
            is_medicine = any(w in q for w in ["medicine", "tablet", "pill", "prescription", "drug"])
            
            llm = None
            try:
                llm = get_alert_generator()
            except:
                pass
                
            speak_text = ""
            if is_medicine and llm and llm.llm_client:
                prompt = f"Extract only the medicine/drug names from this raw OCR text. If there are none, say 'No medicines found'. Text: '{text}'. You MUST reply in the language with code: {language}."
                try:
                    if llm.llm_provider in ["groq", "openai"]:
                        resp = llm.llm_client.chat.completions.create(
                            model="llama-3.3-70b-versatile" if llm.llm_provider == "groq" else "gpt-4o-mini",
                            messages=[{"role": "user", "content": prompt}],
                            max_tokens=50
                        )
                        speak_text = f"The medicines listed are: {resp.choices[0].message.content.strip()}"
                    elif llm.llm_provider == "gemini":
                        resp = llm.llm_client.generate_content(prompt)
                        speak_text = f"The medicines listed are: {resp.text.strip()}"
                except:
                    speak_text = f"I can read: {text}"
            else:
                speak_text = f"The text says: {text}"
                
            return {
                "intent": "read_text",
                "speak": speak_text,
                "text": text
            }
        except Exception as e:
            return {"speak": "I had trouble reading the text."}

    def _handle_path_check(self, image_b64: Optional[str], language: str) -> Dict:
        if not image_b64:
            return {"speak": "I can't see the camera feed right now."}
            
        try:
            det_res = get_detector().detect_from_base64(image_b64)
            detections = det_res.get("detections", [])
            
            # Check for critical/warning in center
            center_blocks = [d for d in detections if d.get("position") == "center" and d.get("alert_level") in ["CRITICAL", "WARNING"]]
            
            if center_blocks:
                obj = center_blocks[0]
                speak_text = f"The path is blocked by a {obj.get('class')} {obj.get('distance')} ahead."
            else:
                speak_text = "The path ahead looks clear."
                
            return {
                "intent": "path_check",
                "speak": speak_text
            }
        except Exception as e:
            return {"speak": "I couldn't verify the path."}

    def _handle_identify(self, image_b64: Optional[str], language: str) -> Dict:
        if not image_b64:
            return {"speak": "I can't see the camera feed right now."}
            
        try:
            det_res = get_detector().detect_from_base64(image_b64)
            detections = det_res.get("detections", [])
            
            understander = None
            try:
                understander = get_scene_understander()
            except:
                pass
                
            if understander:
                speak_text = understander.describe(detections)
            else:
                if not detections:
                    speak_text = "I don't see any recognizable objects."
                else:
                    objs = list(set([d["class"] for d in detections[:3]]))
                    speak_text = f"I can see {', '.join(objs)}."
                    
            return {
                "intent": "identify",
                "speak": speak_text
            }
        except Exception as e:
            return {"speak": "I had trouble identifying the scene."}

    # ── API Integrations ──────────────────────────────────────────────────────
    
    def _search_places_google(self, lat: float, lng: float, place_type: str) -> List[Dict]:
        """Search using Google Places API (Text Search)"""
        if not self.google_key: return []
        
        try:
            # Using Places API (New) Text Search for broad types
            url = "https://places.googleapis.com/v1/places:searchText"
            headers = {
                "Content-Type": "application/json",
                "X-Goog-Api-Key": self.google_key,
                "X-Goog-FieldMask": "places.displayName,places.formattedAddress,places.location"
            }
            data = {
                "textQuery": place_type,
                "locationBias": {
                    "circle": {
                        "center": {"latitude": lat, "longitude": lng},
                        "radius": self.search_radius
                    }
                }
            }
            
            r = requests.post(url, headers=headers, json=data, timeout=5)
            if r.status_code == 200:
                resp = r.json()
                results = []
                for p in resp.get("places", [])[:5]:
                    plat = p.get("location", {}).get("latitude")
                    plng = p.get("location", {}).get("longitude")
                    name = p.get("displayName", {}).get("text", "Unknown")
                    
                    dist = self._calc_distance(lat, lng, plat, plng) if plat and plng else None
                    if dist and dist <= self.search_radius:
                        results.append({"name": name, "distance": dist, "source": "google"})
                        
                results.sort(key=lambda x: x.get("distance", 9999))
                return results
            else:
                logger.error(f"[Google Places] Error {r.status_code}: {r.text}")
        except Exception as e:
            logger.error(f"[Google Places] Exception: {e}")
            
        return []

    def _search_places_osm(self, lat: float, lng: float, place_type: str) -> List[Dict]:
        """Search using OpenStreetMap Overpass API (Free)"""
        # Map our broad types to OSM tags
        osm_tags = {
            "supermarket": "shop=supermarket",
            "restaurant": "amenity=restaurant",
            "pharmacy": "amenity=pharmacy",
            "bank": "amenity=bank",
            "hospital": "amenity=hospital",
            "bus_station": "highway=bus_stop",
            "gas_station": "amenity=fuel",
            "lodging": "tourism=hotel",
            "park": "leisure=park",
            "public_restroom": "amenity=toilets"
        }
        
        tag = osm_tags.get(place_type)
        if not tag:
            # Generic fallback
            tag = f'name~"{place_type}",i'

        query = f"""
        [out:json][timeout:5];
        (
          node[{tag}](around:{self.search_radius},{lat},{lng});
          way[{tag}](around:{self.search_radius},{lat},{lng});
        );
        out center;
        """
        try:
            # Use public Overpass API endpoint
            url = "https://overpass-api.de/api/interpreter"
            r = requests.post(url, data={"data": query}, timeout=5)
            if r.status_code == 200:
                data = r.json()
                results = []
                for el in data.get("elements", [])[:5]:
                    name = el.get("tags", {}).get("name")
                    if not name: continue
                    
                    plat = el.get("lat") or el.get("center", {}).get("lat")
                    plng = el.get("lon") or el.get("center", {}).get("lon")
                    
                    dist = self._calc_distance(lat, lng, plat, plng) if plat and plng else None
                    if dist:
                        results.append({"name": name, "distance": dist, "source": "osm"})
                
                results.sort(key=lambda x: x.get("distance", 9999))
                return results
            else:
                logger.error(f"[OSM] Error {r.status_code}")
        except Exception as e:
            logger.error(f"[OSM] Exception: {e}")
            
        return []
        
    def _calc_distance(self, lat1, lon1, lat2, lon2):
        """Haversine distance in meters"""
        import math
        R = 6371e3
        phi1 = lat1 * math.pi/180
        phi2 = lat2 * math.pi/180
        dphi = (lat2-lat1) * math.pi/180
        dlam = (lon2-lon1) * math.pi/180
        a = math.sin(dphi/2) * math.sin(dphi/2) + math.cos(phi1) * math.cos(phi2) * math.sin(dlam/2) * math.sin(dlam/2)
        c = 2 * math.atan2(math.sqrt(a), math.sqrt(1-a))
        return R * c

# Singleton instance
_interactive_assistant = None

def get_interactive_assistant(config=None) -> InteractiveAssistant:
    global _interactive_assistant
    if _interactive_assistant is None:
        _interactive_assistant = InteractiveAssistant(config)
    return _interactive_assistant

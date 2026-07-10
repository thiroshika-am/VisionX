"""
Voice Command Dispatcher for VisionX
Receives transcribed speech from the frontend Web Speech API,
pattern-matches against supported commands, and returns structured
actions for the backend to dispatch.

Supported commands:
  - "what's around me" / "describe scene" → scene_describe
  - "read this" / "read text" → ocr_read
  - "where am I" / "my location" → location_query
  - "who's near me" / "who is that" → face_scan
  - "take me to <place>" / "navigate to <place>" → nav_start
  - "stop navigation" → nav_stop
  - "what bill is this" / "what currency" → currency_detect
  - "what am I holding" / "what is this" → object_identify
  - "help" / "emergency" / "SOS" → sos_trigger
"""

import re
import logging
from typing import Dict, Optional, Tuple

logger = logging.getLogger(__name__)


# Command patterns: list of (compiled_regex, action_name, param_extractor)
COMMAND_PATTERNS = [
    # ── Interactive Assistant Queries ──────────────────────────────────
    
    # Find nearby places
    (re.compile(r"(?:is\s+there\s+(?:a|an|any)\s+(.+?)(?:\s+near(?:by)?|\s+around|\s+close)?|"
                r"find\s+(?:a|an|me\s+a)?\s*(.+?)(?:\s+near(?:by)?)?|"
                r"(?:where\s+is\s+(?:the\s+)?(?:nearest|closest))\s+(.+)|"
                r"(?:I\s+need|looking\s+for)\s+(?:a|an)?\s*(.+))", re.I),
     "ask_assistant", lambda m: {"query": next(g for g in m.groups() if g).strip()}),

    # Person detection
    (re.compile(r"(?:is\s+(?:there\s+)?(?:any(?:one|body)?|someone|a\s+person)\s+(?:near|around|close|here)|"
                r"(?:are\s+there\s+)?(?:people|persons)\s+(?:near|around|here))", re.I),
     "ask_assistant", lambda m: {"query": "person nearby"}),

    # Object finding
    (re.compile(r"(?:where\s+is\s+(?:my\s+)?(.+)|find\s+my\s+(.+)|"
                r"(?:can\s+you\s+)?see\s+(?:my\s+|a\s+)?(.+))", re.I),
     "ask_assistant", lambda m: {"query": "find " + next(g for g in m.groups() if g).strip()}),

    # Medicine / prescription reading
    (re.compile(r"(?:what\s+(?:is\s+the\s+)?(?:tablet|medicine|pill|drug)\s+name|"
                r"read\s+(?:this\s+)?(?:prescription|medicine|label)|"
                r"(?:what|which)\s+(?:tablets?|medicines?|pills?)\s+(?:is|are)\s+(?:this|these|here))", re.I),
     "ask_assistant", lambda m: {"query": "read medicine prescription"}),

    # Path check
    (re.compile(r"(?:is\s+(?:the\s+)?(?:path|way|road)\s+clear|"
                r"what(?:'s|\s+is)\s+(?:blocking|in\s+(?:my\s+)?(?:way|path))|"
                r"(?:can\s+I|safe\s+to)\s+(?:go|walk|move)\s+(?:ahead|forward))", re.I),
     "ask_assistant", lambda m: {"query": "is the path clear"}),

    # Scene description

    # OCR / text reading
    (re.compile(r"(?:read\s+(?:this|that|text|it|the\s+sign)|what\s+does\s+(?:it|that|this)\s+say)", re.I),
     "ocr_read", None),

    # Location query
    (re.compile(r"(?:where\s+am\s+I|my\s+location|what\s+(?:is\s+)?(?:this|my)\s+(?:location|address|place))", re.I),
     "location_query", None),

    # Face scan
    (re.compile(r"(?:who'?s?\s+(?:near|around|in front of)\s+me|who\s+is\s+(?:that|this|there)|recognize\s+face)", re.I),
     "face_scan", None),

    # Navigation start — extract destination
    (re.compile(r"(?:take\s+me\s+to|navigate\s+to|go\s+to|directions?\s+to|route\s+to)\s+(.+)", re.I),
     "nav_start", lambda m: {"destination": m.group(1).strip()}),

    # Navigation stop
    (re.compile(r"(?:stop\s+navigation|cancel\s+(?:navigation|route|directions)|I'?m?\s+(?:here|done))", re.I),
     "nav_stop", None),

    # Indoor navigation
    (re.compile(r"(?:take\s+me\s+to\s+the|go\s+to\s+the|where\s+is\s+the)\s+(.+)", re.I),
     "nav_indoor_start", lambda m: {"place": m.group(1).strip()}),

    # Currency detection
    (re.compile(r"(?:what\s+(?:bill|note|currency|money)\s+is\s+this|identify\s+(?:this\s+)?(?:bill|note|currency))", re.I),
     "currency_detect", None),

    # Object identification
    (re.compile(r"(?:what\s+am\s+I\s+holding|what\s+is\s+(?:this|that)|identify\s+(?:this|that|object))", re.I),
     "object_identify", None),

    # SOS / Emergency
    (re.compile(r"(?:help|emergency|SOS|I\s+need\s+help|call\s+for\s+help)", re.I),
     "sos_trigger", None),
]


class VoiceCommander:
    """Parses voice command transcripts into structured actions."""

    def __init__(self):
        self.last_command = None
        self.command_history = []

    def parse(self, transcript: str) -> Dict:
        """
        Parse a voice transcript into an action.
        
        Args:
            transcript: Raw transcribed text from Web Speech API
            
        Returns:
            dict with keys:
                - action: str (the command action name, or "unknown")
                - params: dict (extracted parameters, if any)
                - transcript: str (the original transcript)
                - confidence: float (1.0 for matched, 0.0 for unknown)
        """
        transcript = transcript.strip()
        if not transcript:
            return {
                "action": "unknown",
                "params": {},
                "transcript": "",
                "confidence": 0.0
            }

        for pattern, action, param_extractor in COMMAND_PATTERNS:
            match = pattern.search(transcript)
            if match:
                params = {}
                if param_extractor:
                    params = param_extractor(match)
                
                result = {
                    "action": action,
                    "params": params,
                    "transcript": transcript,
                    "confidence": 1.0
                }
                
                self.last_command = result
                self.command_history.append(result)
                # Keep history bounded
                if len(self.command_history) > 50:
                    self.command_history = self.command_history[-50:]
                
                logger.info(f"[VoiceCmd] Matched: '{transcript}' → {action} {params}")
                return result

        logger.info(f"[VoiceCmd] No match for: '{transcript}'")
        return {
            "action": "unknown",
            "params": {},
            "transcript": transcript,
            "confidence": 0.0
        }

    def get_help_text(self) -> str:
        """Return a spoken help message listing available commands."""
        return (
            "You can say: "
            "Is there a supermarket nearby, to find places. "
            "Is there anyone near me, to detect people. "
            "Where is my water bottle, to find objects. "
            "What is the tablet name, to read prescriptions. "
            "Is the path clear, to check for obstacles. "
            "Where am I, for your location. "
            "Take me to, followed by a destination. "
            "What bill is this, to identify currency. "
            "Help or emergency, for SOS."
        )


# Singleton
_commander_instance = None

def get_voice_commander() -> VoiceCommander:
    """Get or create the singleton VoiceCommander."""
    global _commander_instance
    if _commander_instance is None:
        _commander_instance = VoiceCommander()
    return _commander_instance

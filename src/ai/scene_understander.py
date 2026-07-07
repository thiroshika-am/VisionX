"""
Scene Understander — natural language scene descriptions for VisionX.
Wraps the LLM alert generator with scene-specific prompting.
Produces accessible, audio-friendly descriptions for blind users.
"""

import logging
from typing import List, Dict, Optional

logger = logging.getLogger("smartcap")


class SceneUnderstander:
    """
    Generates natural language scene summaries from multi-modal AI outputs.
    Falls back to a structured template if LLM is unavailable.
    """

    def __init__(self):
        self._llm = None

    def _get_llm(self):
        if self._llm is None:
            try:
                from ai_modules.llm_alerts import get_alert_generator
                self._llm = get_alert_generator()
            except Exception as e:
                logger.warning(f"[SceneUnderstander] LLM unavailable: {e}")
        return self._llm

    # ── Public API ────────────────────────────────────────────────────────────

    def describe(
        self,
        detections: List[Dict],
        gestures:   List[Dict] = None,
        emotions:   List[Dict] = None,
        poses:      List[Dict] = None,
        context:    Dict       = None,
    ) -> str:
        """
        Produce a natural language scene description.
        Returns a concise, audio-friendly string.
        """
        llm = self._get_llm()
        if llm:
            try:
                return llm.generate_scene_description(
                    detections=detections or [],
                    gestures  =gestures   or [],
                    emotions  =emotions   or [],
                    poses     =poses      or [],
                )
            except Exception as e:
                logger.warning(f"[SceneUnderstander] LLM failed: {e}, using template")

        return self._template_description(detections or [], gestures, emotions, poses)

    # ── Template fallback ─────────────────────────────────────────────────────

    def _template_description(
        self,
        detections: List[Dict],
        gestures:   List[Dict] = None,
        emotions:   List[Dict] = None,
        poses:      List[Dict] = None,
    ) -> str:
        if not detections:
            return "The area ahead appears clear. No objects detected."

        parts = []

        # Group by alert level
        critical = [d for d in detections if d.get("alert_level") == "CRITICAL"]
        warning  = [d for d in detections if d.get("alert_level") == "WARNING"]
        safe     = [d for d in detections if d.get("alert_level") == "SAFE"]

        if critical:
            names = self._format_list([d["class"] for d in critical])
            dists = [d.get("distance", "") for d in critical if d.get("distance")]
            dist_str = f" at {dists[0]}" if dists else ""
            parts.append(f"Danger: {names}{dist_str} directly ahead.")

        if warning:
            names = self._format_list([d["class"] for d in warning])
            parts.append(f"Caution: {names} nearby.")

        if safe:
            names = self._format_list(list({d["class"] for d in safe}))
            parts.append(f"Also in view: {names}.")

        # Gestures
        if gestures:
            g = gestures[0]
            gesture_name = g.get("display_name") or g.get("gesture", "")
            if gesture_name and gesture_name.lower() != "none":
                parts.append(f"Someone is showing a {gesture_name} gesture.")

        # Emotions
        if emotions:
            e = emotions[0]
            em = e.get("emotion") or e.get("dominant_emotion", "")
            if em:
                parts.append(f"The person looks {em}.")

        # Poses
        if poses:
            p = poses[0]
            posture = p.get("posture", "")
            if posture:
                parts.append(f"Body posture: {posture}.")

        return " ".join(parts)

    @staticmethod
    def _format_list(items: List[str]) -> str:
        unique = list(dict.fromkeys(items))  # deduplicate preserving order
        if len(unique) == 1:
            return unique[0]
        if len(unique) == 2:
            return f"{unique[0]} and {unique[1]}"
        return ", ".join(unique[:-1]) + f", and {unique[-1]}"


# Singleton
_understander: Optional[SceneUnderstander] = None


def get_scene_understander() -> SceneUnderstander:
    global _understander
    if _understander is None:
        _understander = SceneUnderstander()
    return _understander

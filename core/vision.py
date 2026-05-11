"""
Vision — webcam capture + multimodal description via Ollama.
Uses gemma4:latest (or configured vision model) which supports image input.
"""

import base64
import requests
from typing import Optional

from config import OLLAMA_URL
from core.settings_store import settings

_VISION_MODEL_FALLBACK = "gemma4:latest"


def _vision_model() -> str:
    return settings.get("models.web_agent", _VISION_MODEL_FALLBACK) or _VISION_MODEL_FALLBACK


def capture_frame(camera_index: int = 0) -> Optional[bytes]:
    """Capture one JPEG frame from the webcam. Returns bytes or None."""
    try:
        import cv2
    except ImportError:
        print("[Vision] opencv-python not installed — run: pip install opencv-python")
        return None

    cap = cv2.VideoCapture(camera_index)
    if not cap.isOpened():
        print(f"[Vision] Cannot open camera {camera_index}")
        return None
    try:
        # Discard a few frames so auto-exposure can settle
        for _ in range(3):
            cap.read()
        ret, frame = cap.read()
        if not ret or frame is None:
            print("[Vision] Failed to read frame")
            return None
        _, buf = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 85])
        return bytes(buf)
    finally:
        cap.release()


def describe(
    prompt: str = "Décris ce que tu vois en détail. Sois concis et précis.",
    camera_index: int = 0,
    model: Optional[str] = None,
) -> dict:
    """
    Capture webcam frame and ask the vision model to describe it.

    Returns:
        {
            "success": bool,
            "description": str,
            "image_b64": str | None,   # JPEG as base64 (for UI preview)
        }
    """
    jpg = capture_frame(camera_index)
    if jpg is None:
        return {"success": False, "description": "Impossible d'accéder à la webcam.", "image_b64": None}

    img_b64 = base64.b64encode(jpg).decode("utf-8")
    used_model = model or _vision_model()

    try:
        payload = {
            "model": used_model,
            "messages": [
                {
                    "role": "user",
                    "content": prompt,
                    "images": [img_b64],
                }
            ],
            "stream": False,
        }
        # OLLAMA_URL = "http://localhost:11434/api" → chat = OLLAMA_URL + "/chat"
        url = OLLAMA_URL.rstrip("/") + "/chat"
        r = requests.post(url, json=payload, timeout=120)
        r.raise_for_status()
        text = r.json().get("message", {}).get("content", "")
        return {"success": True, "description": text, "image_b64": img_b64}
    except Exception as e:
        print(f"[Vision] API error: {e}")
        return {"success": False, "description": f"Erreur vision : {e}", "image_b64": img_b64}

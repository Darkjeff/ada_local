"""
Vision — webcam capture + multimodal description via Ollama.
Uses gemma4:latest (or configured vision model) which supports image input.
"""

import base64
import requests
from typing import Optional

from config import OLLAMA_URL
from core.settings_store import settings

_VISION_MODEL_FALLBACK = "llava-phi3"

def _vision_model() -> str:
    return settings.get("models.vision", _VISION_MODEL_FALLBACK) or _VISION_MODEL_FALLBACK


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
        # Resize to max 640px wide to keep payload small
        h, w = frame.shape[:2]
        if w > 640:
            scale = 640 / w
            frame = cv2.resize(frame, (640, int(h * scale)), interpolation=cv2.INTER_AREA)
        _, buf = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 75])
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

    base = OLLAMA_URL.rstrip("/")  # "http://localhost:11434/api"

    # Try /api/generate first (compatible with moondream, llava, etc.)
    # Fall back to /api/chat for models that need it (gemma4)
    for endpoint, build_payload in [
        (
            base + "/generate",
            lambda: {"model": used_model, "prompt": prompt, "images": [img_b64], "stream": False},
        ),
        (
            base + "/chat",
            lambda: {
                "model": used_model,
                "messages": [{"role": "user", "content": prompt, "images": [img_b64]}],
                "stream": False,
            },
        ),
    ]:
        try:
            r = requests.post(endpoint, json=build_payload(), timeout=120)
            if r.status_code == 200:
                data = r.json()
                # /generate returns "response", /chat returns "message.content"
                text = data.get("response") or data.get("message", {}).get("content", "")
                if text:
                    return {"success": True, "description": text, "image_b64": img_b64}
            else:
                print(f"[Vision] {endpoint} → HTTP {r.status_code}: {r.text[:200]}")
        except Exception as e:
            print(f"[Vision] {endpoint} failed: {e}")

    return {"success": False, "description": "Erreur : aucun modèle vision n'a pu répondre.", "image_b64": img_b64}

"""
Vision — webcam capture + multimodal description via Ollama.
Tries vision models from smallest to largest, all forced to CPU (num_gpu=0)
to avoid GPU OOM crashes on machines with < 4 GB VRAM.
"""

import base64
import requests
from typing import Optional

from config import OLLAMA_URL
from core.settings_store import settings

# Ordered smallest → largest. moondream (1.6B) is tried first for speed.
_VISION_MODEL_FALLBACK = "moondream"
_VISION_MODEL_CASCADE = ["moondream", "llava-phi3", "gemma4:latest"]

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
        # Resize to max 512px wide — smaller payload = faster inference
        h, w = frame.shape[:2]
        if w > 512:
            scale = 512 / w
            frame = cv2.resize(frame, (512, int(h * scale)), interpolation=cv2.INTER_AREA)
        _, buf = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 70])
        return bytes(buf)
    finally:
        cap.release()


def _try_model(base: str, model: str, prompt: str, img_b64: str) -> Optional[str]:
    """
    Try one model via /api/chat then /api/generate.
    Forces CPU-only (num_gpu=0) to avoid OOM crash on small GPUs.
    Returns description text or None on failure.
    """
    # num_gpu=0 → full CPU, avoids llama runner crash when VRAM < 4 GB
    cpu_options = {"num_gpu": 0, "num_thread": 4}

    # Timeout scales with model size (CPU inference is slow)
    timeout = 180 if "moondream" in model else (240 if "phi" in model else 360)

    endpoints = [
        (
            base + "/chat",
            {"model": model, "messages": [{"role": "user", "content": prompt, "images": [img_b64]}],
             "options": cpu_options, "stream": False},
        ),
        (
            base + "/generate",
            {"model": model, "prompt": prompt, "images": [img_b64],
             "options": cpu_options, "stream": False},
        ),
    ]

    for endpoint, payload in endpoints:
        try:
            r = requests.post(endpoint, json=payload, timeout=timeout)
            if r.status_code == 200:
                data = r.json()
                text = data.get("response") or data.get("message", {}).get("content", "")
                if text:
                    print(f"[Vision] {model} via {endpoint.split('/')[-1]} → OK")
                    return text
            else:
                print(f"[Vision] {model} {endpoint.split('/')[-1]} → HTTP {r.status_code}: {r.text[:120]}")
        except Exception as e:
            print(f"[Vision] {model} {endpoint.split('/')[-1]} failed: {e}")

    return None


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
    base = OLLAMA_URL.rstrip("/")  # "http://localhost:11434/api"

    # Build model list: configured model first, then cascade fallbacks
    configured = model or _vision_model()
    models_to_try = [configured] + [m for m in _VISION_MODEL_CASCADE if m != configured]

    for m in models_to_try:
        print(f"[Vision] Trying model: {m}")
        text = _try_model(base, m, prompt, img_b64)
        if text:
            return {"success": True, "description": text, "image_b64": img_b64}

    return {"success": False, "description": "Erreur : aucun modèle vision n'a pu répondre.", "image_b64": img_b64}

"""
Device enumeration helpers — lists available webcams and audio I/O devices.

All three public functions are safe to call even when their optional
dependencies (cv2, sounddevice) are absent.  They always return a list.
"""

from __future__ import annotations
from typing import Any


# ──────────────────────────────────────────────────────────────────────────────
# Internal helper — separates the sounddevice I/O so tests can patch it.
# ──────────────────────────────────────────────────────────────────────────────

def _query_audio_devices() -> list[dict[str, Any]]:
    """Return raw sounddevice device list (raises if sounddevice absent)."""
    import sounddevice as sd  # noqa: PLC0415
    return list(sd.query_devices())


# ──────────────────────────────────────────────────────────────────────────────
# Public API
# ──────────────────────────────────────────────────────────────────────────────

def list_cameras(max_index: int = 5) -> list[dict[str, Any]]:
    """
    Probe webcam indices 0 … max_index-1 via cv2.

    Returns:
        [{"index": 0, "name": "Camera 0"}, ...]
        []  if cv2 is not installed or no camera found.
    """
    try:
        import cv2  # noqa: PLC0415
    except ImportError:
        return []

    cameras: list[dict[str, Any]] = []
    for i in range(max_index):
        cap = cv2.VideoCapture(i)
        if cap.isOpened():
            cameras.append({"index": i, "name": f"Camera {i}"})
            cap.release()
    return cameras


def list_audio_inputs() -> list[dict[str, Any]]:
    """
    Return all audio *input* devices via sounddevice.

    Returns:
        [{"index": 0, "name": "Microphone (Realtek)"}, ...]
        []  if sounddevice is not installed or query fails.
    """
    try:
        devices = _query_audio_devices()
        return [
            {"index": i, "name": d["name"]}
            for i, d in enumerate(devices)
            if d.get("max_input_channels", 0) > 0
        ]
    except Exception:
        return []


def list_audio_outputs() -> list[dict[str, Any]]:
    """
    Return all audio *output* devices via sounddevice.

    Returns:
        [{"index": 0, "name": "Speakers (Realtek)"}, ...]
        []  if sounddevice is not installed or query fails.
    """
    try:
        devices = _query_audio_devices()
        return [
            {"index": i, "name": d["name"]}
            for i, d in enumerate(devices)
            if d.get("max_output_channels", 0) > 0
        ]
    except Exception:
        return []

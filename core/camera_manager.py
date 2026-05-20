"""
CameraManager — discovers HA camera endpoints and captures snapshots.
"""
from __future__ import annotations

import os
import time
import unicodedata
from dataclasses import dataclass, field
from typing import Optional

from core.ha_control import ha_manager

_CACHE_DIR = os.path.join("data", "cache", "snapshots")


def _normalize(text: str) -> str:
    """Lowercase + strip accents for fuzzy matching."""
    return "".join(
        c for c in unicodedata.normalize("NFD", text.lower())
        if unicodedata.category(c) != "Mn"
    )


@dataclass
class CameraCapabilities:
    snapshot: bool = True
    motion: bool = False       # future: HA event subscription
    audio_input: bool = False  # future: inbound audio stream
    speaker: bool = False      # future: TTS to camera speaker


@dataclass
class CameraEndpoint:
    entity_id: str
    friendly_name: str
    area_id: str
    area_name: str
    state: str = "unknown"
    capabilities: CameraCapabilities = field(default_factory=CameraCapabilities)


@dataclass
class SnapshotResult:
    success: bool
    entity_id: str
    path: str
    mime_type: str = "image/jpeg"
    error: str = ""


class CameraManager:
    def __init__(self) -> None:
        self._endpoints: list[CameraEndpoint] = []

    def refresh(self) -> None:
        """Load camera.* entities from HA and resolve area names."""
        raw = ha_manager.get_camera_endpoints()
        self._endpoints = [
            CameraEndpoint(
                entity_id=r["entity_id"],
                friendly_name=r["friendly_name"],
                area_id=r["area_id"],
                area_name=r["area_name"],
                state=r["state"],
            )
            for r in raw
        ]
        print(f"[CameraManager] {len(self._endpoints)} camera(s) loaded")

    def list_endpoints(self) -> list[CameraEndpoint]:
        return list(self._endpoints)

    def find_by_area(self, hint: str) -> Optional[CameraEndpoint]:
        """
        Fuzzy-match hint against area_name and friendly_name (accent-insensitive).
        Returns the first match or None.
        """
        if not hint:
            return None
        h = _normalize(hint)
        for ep in self._endpoints:
            area = _normalize(ep.area_name)
            name = _normalize(ep.friendly_name)
            # Only match if area_name is non-empty
            if area and (h in area or area in h):
                return ep
            # Also try friendly_name as fallback
            if name and (h in name or name in h):
                return ep
        return None

    def capture_snapshot(self, entity_id: str) -> SnapshotResult:
        """
        Fetch JPEG snapshot from HA and save to data/cache/snapshots/.
        Returns SnapshotResult with success=False on any failure.
        """
        os.makedirs(_CACHE_DIR, exist_ok=True)
        jpg = ha_manager.get_camera_snapshot(entity_id)
        if jpg is None:
            return SnapshotResult(
                success=False, entity_id=entity_id, path="",
                error="Snapshot unavailable"
            )
        safe = entity_id.replace(".", "_").replace("/", "_")
        filename = f"{safe}_{int(time.time())}.jpg"
        path = os.path.join(_CACHE_DIR, filename)
        with open(path, "wb") as f:
            f.write(jpg)
        return SnapshotResult(success=True, entity_id=entity_id, path=path)


camera_manager = CameraManager()

"""
ADA — Unified provider/entity domain models.

These dataclasses form the lingua franca between provider adapters
(Kasa, Home Assistant, …) and the UI. No I/O, no Qt imports here.
"""
from __future__ import annotations

from dataclasses import dataclass, field

# ---------------------------------------------------------------------------
# Zone inference
# ---------------------------------------------------------------------------

_ZONE_KEYWORDS: dict[str, list[str]] = {
    "Bureau":    ["bureau", "office", "desk", "work", "pc", "monitor", "etagere"],
    "Chambre":   ["chambre", "bedroom", "bed", "sleep", "night", "nuit"],
    "Cuisine":   ["cuisine", "kitchen", "dining", "cook", "oven", "cafe", "cafetiere"],
    "Chillout":  ["salon", "living", "lounge", "sejour", "sofa", "tv"],
    "Extérieur": ["exterieur", "exterior", "garden", "jardin", "patio", "porch", "garage"],
    "Couloir":   ["couloir", "hall", "corridor", "stairs", "entree"],
}


def infer_zone(name: str) -> str:
    """Return the best-matching zone for a device name, or 'Other'."""
    lower = name.lower()
    for zone, keywords in _ZONE_KEYWORDS.items():
        if any(k in lower for k in keywords):
            return zone
    return "Other"


# ---------------------------------------------------------------------------
# HA domain → ADA entity type
# ---------------------------------------------------------------------------

_HA_DOMAIN_TO_TYPE: dict[str, str] = {
    "light":         "light",
    "switch":        "switch",
    "script":        "switch",
    "scene":         "switch",
    "media_player":  "media_player",
    "camera":        "camera",
    "sensor":        "sensor",
    "binary_sensor": "binary_sensor",
    "climate":       "unknown",
}


def ha_domain_to_entity_type(domain: str) -> str:
    """Convert a Home Assistant entity domain to an ADA entity type string."""
    return _HA_DOMAIN_TO_TYPE.get(domain, "unknown")


# ---------------------------------------------------------------------------
# Capability inference
# ---------------------------------------------------------------------------

def infer_capabilities(
    entity_type: str, attributes: dict, read_only: bool = False
) -> list[str]:
    """
    Return a list of capability strings for an entity given its type
    and raw attributes dict. Never raises.
    """
    caps: list[str] = ["read"]
    if not read_only:
        caps.append("control")

    if entity_type == "light":
        if "brightness" in attributes or attributes.get("is_dimmable"):
            caps.append("brightness")
        if (
            "rgb_color" in attributes
            or "hs_color" in attributes
            or attributes.get("is_color")
        ):
            caps.append("color")

    elif entity_type in ("media_player", "speaker"):
        caps.append("tts")
        if "volume_level" in attributes:
            caps.append("volume")

    elif entity_type == "camera":
        caps.append("snapshot")
        if attributes.get("motion_detection"):
            caps.append("motion")

    elif entity_type == "sensor":
        dc = attributes.get("device_class", "")
        _DC_CAP = {
            "temperature": "temperature",
            "humidity":    "humidity",
            "battery":     "battery",
            "energy":      "energy",
            "power":       "energy",
        }
        if dc in _DC_CAP:
            caps.append(_DC_CAP[dc])

    return caps


# ---------------------------------------------------------------------------
# Dataclasses
# ---------------------------------------------------------------------------

@dataclass
class Provider:
    """Metadata about a single automation provider."""
    id: str
    name: str
    enabled: bool
    type: str                           # "kasa" | "home_assistant" | "domoticz" | …
    base_url: str = ""
    token: str = ""
    priority: int = 0
    status: str = "unknown"             # "connected" | "disconnected" | "unknown" | "error"
    last_sync: float = 0.0
    capabilities: list[str] = field(default_factory=list)


@dataclass
class Entity:
    """A single normalized device/entity regardless of its origin provider."""
    id: str                             # "{provider_id}.{provider_entity_id}"
    provider: str                       # provider id ("kasa", "home_assistant", …)
    provider_entity_id: str             # original id within the provider
    name: str
    type: str                           # "light" | "camera" | "sensor" | etc.
    zone: str                           # inferred from name via infer_zone()
    state: str                          # "on" | "off" | "playing" | numeric string, …
    attributes: dict = field(default_factory=dict)
    capabilities: list[str] = field(default_factory=list)
    read_only: bool = False
    available: bool = True
    last_updated: float = 0.0

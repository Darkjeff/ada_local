"""
Home Assistant REST API client for A.D.A.
Controls HA entities via local HTTP API with a long-lived Bearer token.
"""

import requests
from typing import Any

from core.settings_store import settings


CONTROLLABLE_DOMAINS = frozenset({
    "light", "switch", "script", "scene", "media_player", "climate"
})

SENSOR_DOMAINS = frozenset({"sensor", "binary_sensor"})

CAMERA_DOMAINS = frozenset({"camera"})

DOMAIN_SERVICES = {
    "light":        ("light/turn_on",            "light/turn_off"),
    "switch":       ("switch/turn_on",           "switch/turn_off"),
    "script":       ("script/turn_on",           None),
    "scene":        ("scene/turn_on",            None),
    "media_player": ("media_player/media_play",  "media_player/media_pause"),
    "climate":      ("climate/set_hvac_mode",    "climate/turn_off"),
}


class HAManager:
    """
    Synchronous client for the Home Assistant local REST API.
    Wraps network calls — never raises, always returns False/{} on failure.
    """

    def __init__(self):
        self.entities: dict[str, Any] = {}
        self._raw_entities: dict[str, Any] = {}
        self._connected: bool = False
        self._url: str = ""
        self._token: str = ""
        self._load_config()

    # ------------------------------------------------------------------ #
    # Config                                                               #
    # ------------------------------------------------------------------ #

    def _load_config(self):
        self._url = settings.get("home_assistant.url", "").rstrip("/")
        self._token = settings.get("home_assistant.token", "")

    def reload_config(self):
        """Re-read url/token from settings (call after saving settings)."""
        self._load_config()
        self._connected = False

    def _headers(self) -> dict:
        return {
            "Authorization": f"Bearer {self._token}",
            "Content-Type": "application/json",
        }

    # ------------------------------------------------------------------ #
    # Connection                                                           #
    # ------------------------------------------------------------------ #

    @property
    def is_connected(self) -> bool:
        return self._connected

    def test_connection(self) -> bool:
        """
        GET /api/ — returns True if HA responds with HTTP 200.
        Sets self._connected accordingly.
        """
        if not self._url or not self._token:
            self._connected = False
            return False
        try:
            resp = requests.get(
                f"{self._url}/api/",
                headers=self._headers(),
                timeout=5,
            )
            self._connected = resp.status_code == 200
        except Exception as e:
            print(f"[HAManager] Connection test failed: {e}")
            self._connected = False
        return self._connected

    # ------------------------------------------------------------------ #
    # Entity discovery                                                     #
    # ------------------------------------------------------------------ #

    def _fetch_all_states(self) -> dict[str, Any]:
        """
        GET /api/states — caches full result in self._raw_entities.
        Called internally; avoids duplicate HTTP calls when both
        get_entities() and get_sensor_entities() are used together.
        """
        if not self._url or not self._token:
            return {}
        try:
            resp = requests.get(
                f"{self._url}/api/states",
                headers=self._headers(),
                timeout=5,
            )
            if resp.status_code != 200:
                print(f"[HAManager] _fetch_all_states HTTP {resp.status_code}")
                return {}
            raw: list = resp.json()
            self._raw_entities = {item["entity_id"]: item for item in raw}
            return self._raw_entities
        except Exception as e:
            print(f"[HAManager] _fetch_all_states failed: {e}")
            return {}

    def get_entities(self) -> dict[str, Any]:
        """
        Returns controllable entities only (light, switch, script, scene,
        media_player, climate). Populates _raw_entities cache as a side effect
        so get_sensor_entities() avoids a second HTTP call.
        """
        all_e = self._fetch_all_states()
        self.entities = {
            eid: info for eid, info in all_e.items()
            if eid.split(".")[0] in CONTROLLABLE_DOMAINS
        }
        return self.entities

    def get_sensor_entities(self) -> dict[str, Any]:
        """
        Returns sensor and binary_sensor entities (read-only).
        Reuses the _raw_entities cache if already populated by get_entities().
        """
        raw = self._raw_entities or self._fetch_all_states()
        return {
            eid: info for eid, info in raw.items()
            if eid.split(".")[0] in SENSOR_DOMAINS
        }

    def get_camera_entities(self) -> dict[str, Any]:
        """Returns camera entities."""
        raw = self._raw_entities or self._fetch_all_states()
        return {
            eid: info for eid, info in raw.items()
            if eid.split(".")[0] in CAMERA_DOMAINS
        }

    def _get_entity_area(self, entity_id: str) -> tuple[str, str]:
        """Return (area_id, area_name) for an entity via HA template API."""
        try:
            tmpl = (
                f'{{{{ area_id("{entity_id}") | default("") }}}}'
                f'|'
                f'{{{{ area_name("{entity_id}") | default("") }}}}'
            )
            r = requests.post(
                f"{self._url}/api/template",
                headers=self._headers(),
                json={"template": tmpl},
                timeout=5,
            )
            if r.status_code == 200:
                parts = r.text.strip().split("|", 1)
                aid = parts[0].strip()
                aid = "" if aid in ("None", "none") else aid
                aname = parts[1].strip() if len(parts) > 1 else ""
                aname = "" if aname in ("None", "none") else aname
                return aid, aname
        except Exception:
            pass
        return "", ""

    def get_camera_endpoints(self) -> list[dict]:
        """
        Returns camera.* entities with resolved area_name.
        Uses /api/states for entity list and /api/template for area resolution.
        Returns [] if HA is unreachable or not configured.
        """
        if not self._url or not self._token:
            return []
        try:
            states = self._fetch_all_states()
            cameras = {eid: info for eid, info in states.items() if eid.startswith("camera.")}
            if not cameras:
                print("[HAManager] No camera.* entities found in states")
                return []

            result = []
            for eid, info in cameras.items():
                friendly = info.get("attributes", {}).get("friendly_name", eid)
                state = info.get("state", "unknown")
                state = info.get("state", "unknown")
                area_id, area_name = self._get_entity_area(eid)
                result.append({
                    "entity_id": eid,
                    "friendly_name": friendly,
                    "area_id": area_id,
                    "area_name": area_name,
                    "state": state,
                })
            return result
        except Exception as e:
            print(f"[HAManager] get_camera_endpoints failed: {e}")
            return []

    def get_media_player_entities(self) -> dict[str, Any]:
        """
        Returns media_player entities suitable as TTS output targets.
        Reuses _raw_entities cache if already populated by get_entities().
        """
        raw = self._raw_entities or self._fetch_all_states()
        return {
            eid: info for eid, info in raw.items()
            if eid.split(".")[0] == "media_player"
        }

    def speak_to_media_player(
        self, entity_id: str, text: str, tts_service: str = "tts.piper"
    ) -> bool:
        """
        Send TTS speech to a media_player entity via HA's tts.speak service.

        Uses POST /api/services/tts/speak with the following payload:
          entity_id              — the TTS engine entity (e.g. "tts.piper")
          media_player_entity_id — the output target (e.g. "media_player.living_room")
          message                — the text to speak

        Args:
            entity_id:   HA media_player entity to speak through
            text:        Text to synthesize and play
            tts_service: HA TTS engine entity_id (default: "tts.piper")

        Returns True on success, False on any error.
        """
        if not self._url or not self._token:
            return False
        try:
            payload = {
                "entity_id": tts_service,
                "media_player_entity_id": entity_id,
                "message": text,
            }
            resp = requests.post(
                f"{self._url}/api/services/tts/speak",
                headers=self._headers(),
                json=payload,
                timeout=10,
            )
            if resp.status_code not in (200, 201):
                print(
                    f"[HAManager] speak_to_media_player HTTP {resp.status_code} "
                    f"for {entity_id!r}"
                )
                return False
            return True
        except Exception as e:
            print(f"[HAManager] speak_to_media_player({entity_id!r}) failed: {e}")
            return False

    def get_camera_snapshot(self, entity_id: str) -> bytes | None:
        """GET /api/camera_proxy/{entity_id} — returns raw image bytes or None."""
        if not self._url or not self._token:
            return None
        try:
            resp = requests.get(
                f"{self._url}/api/camera_proxy/{entity_id}",
                headers=self._headers(),
                timeout=10,
            )
            if resp.status_code == 200:
                return resp.content
        except Exception as e:
            print(f"[HAManager] camera snapshot {entity_id} failed: {e}")
        return None

    def get_state(self, entity_id: str) -> dict:
        """GET /api/states/{entity_id} — returns entity state dict or {}."""
        if not self._url or not self._token:
            return {}
        try:
            resp = requests.get(
                f"{self._url}/api/states/{entity_id}",
                headers=self._headers(),
                timeout=5,
            )
            if resp.status_code != 200:
                return {}
            return resp.json()
        except Exception as e:
            print(f"[HAManager] get_state({entity_id}) failed: {e}")
            return {}

    # ------------------------------------------------------------------ #
    # Service calls                                                        #
    # ------------------------------------------------------------------ #

    def call_service(
        self, domain: str, service: str, entity_id: str, **kwargs
    ) -> bool:
        """
        POST /api/services/{domain}/{service}
        kwargs are forwarded as extra service_data fields (brightness_pct, rgb_color…).
        """
        if not self._url or not self._token:
            return False
        try:
            payload: dict = {"entity_id": entity_id, **kwargs}
            resp = requests.post(
                f"{self._url}/api/services/{domain}/{service}",
                headers=self._headers(),
                json=payload,
                timeout=5,
            )
            if resp.status_code not in (200, 201):
                print(
                    f"[HAManager] call_service {domain}/{service} "
                    f"HTTP {resp.status_code}"
                )
                return False
            return True
        except Exception as e:
            print(f"[HAManager] call_service({domain}/{service}) failed: {e}")
            return False

    def turn_on(self, entity_id: str, **kwargs) -> bool:
        """Call the domain-appropriate turn_on service."""
        domain = entity_id.split(".")[0]
        services = DOMAIN_SERVICES.get(domain)
        if not services or not services[0]:
            print(f"[HAManager] No turn_on service for domain '{domain}'")
            return False
        svc_path = services[0]          # e.g. "light/turn_on"
        svc_domain, svc_name = svc_path.split("/")
        return self.call_service(svc_domain, svc_name, entity_id, **kwargs)

    def turn_off(self, entity_id: str) -> bool:
        """Call the domain-appropriate turn_off service."""
        domain = entity_id.split(".")[0]
        services = DOMAIN_SERVICES.get(domain)
        if not services or not services[1]:
            print(f"[HAManager] No turn_off service for domain '{domain}'")
            return False
        svc_path = services[1]          # e.g. "light/turn_off"
        svc_domain, svc_name = svc_path.split("/")
        return self.call_service(svc_domain, svc_name, entity_id)

    def play_media(self, entity_id: str, url: str, media_type: str = "music") -> bool:
        """POST /api/services/media_player/play_media — stream `url` on `entity_id`."""
        if not self._url or not self._token:
            return False
        return self.call_service(
            "media_player", "play_media", entity_id,
            media_content_id=url,
            media_content_type=media_type,
        )

    def media_pause(self, entity_id: str) -> bool:
        """POST /api/services/media_player/media_pause."""
        if not self._url or not self._token:
            return False
        return self.call_service("media_player", "media_pause", entity_id)

    def media_stop(self, entity_id: str) -> bool:
        """POST /api/services/media_player/media_stop."""
        if not self._url or not self._token:
            return False
        return self.call_service("media_player", "media_stop", entity_id)

    def media_next_track(self, entity_id: str) -> bool:
        """POST /api/services/media_player/media_next_track."""
        if not self._url or not self._token:
            return False
        return self.call_service("media_player", "media_next_track", entity_id)

    def volume_set(self, entity_id: str, level: float) -> bool:
        """POST /api/services/media_player/volume_set — `level` is 0.0 to 1.0."""
        if not self._url or not self._token:
            return False
        return self.call_service("media_player", "volume_set", entity_id, volume_level=level)

    def volume_up(self, entity_id: str) -> bool:
        """POST /api/services/media_player/volume_up."""
        if not self._url or not self._token:
            return False
        return self.call_service("media_player", "volume_up", entity_id)

    def volume_down(self, entity_id: str) -> bool:
        """POST /api/services/media_player/volume_down."""
        if not self._url or not self._token:
            return False
        return self.call_service("media_player", "volume_down", entity_id)


# Global singleton — same pattern as kasa_manager
ha_manager = HAManager()

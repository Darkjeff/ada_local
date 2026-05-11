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


# Global singleton — same pattern as kasa_manager
ha_manager = HAManager()

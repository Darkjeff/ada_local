# core/domoticz_control.py
"""
Domoticz JSON API client pour ADA.
Utilise l'API HTTP/JSON de Domoticz (authentification Basic optionnelle).

Référence : https://www.domoticz.com/wiki/Domoticz_API/JSON_URL's
"""
from __future__ import annotations

from typing import Any

import requests

from core.settings_store import settings

# Types de périphériques que l'on peut commander (toggle on/off ou level)
CONTROLLABLE_TYPES = frozenset({
    "Light/Switch",
    "Color Switch",
    "Dimmer",
    "Selector Switch",
    "Blinds",
    "Blinds + Stop",
    "Scene",
    "Group",
    "Lighting 1",
    "Lighting 2",
    "Lighting 4",
    "Lighting 5",
    "Lighting 6",
})

# Types de capteurs (lecture seule)
SENSOR_TYPES = frozenset({
    "Temp",
    "Humidity",
    "Temp + Humidity",
    "Wind",
    "Rain",
    "UV",
    "Air Quality",
    "Lux",
    "Barometer",
    "Usage",
    "Energy",
    "Current",
})


class DomoticzManager:
    """Client synchrone pour l'API JSON de Domoticz."""

    def __init__(self) -> None:
        self._base_url: str = ""
        self._username: str = ""
        self._password: str = ""
        self._connected: bool = False
        self._load_config()

    def _load_config(self) -> None:
        self._base_url = settings.get("domoticz.url", "").rstrip("/")
        self._username = settings.get("domoticz.username", "")
        self._password = settings.get("domoticz.password", "")

    def reload_config(self) -> None:
        """Recharge la configuration depuis le settings store."""
        self._load_config()

    # ------------------------------------------------------------------ #
    # Internals                                                            #
    # ------------------------------------------------------------------ #

    def _get(self, params: dict[str, str], timeout: int = 5) -> dict[str, Any]:
        """Effectue un GET /json.htm avec les paramètres donnés."""
        if not self._base_url:
            raise ValueError("Domoticz URL non configurée")
        url = f"{self._base_url}/json.htm"
        auth = (self._username, self._password) if self._username else None
        resp = requests.get(url, params=params, auth=auth, timeout=timeout)
        resp.raise_for_status()
        return resp.json()

    # ------------------------------------------------------------------ #
    # Public API                                                           #
    # ------------------------------------------------------------------ #

    def test_connection(self) -> bool:
        """Vérifie que Domoticz est joignable et répond correctement."""
        try:
            data = self._get({"type": "command", "param": "getversion"}, timeout=5)
            self._connected = data.get("status") == "OK"
            return self._connected
        except Exception as e:
            print(f"[DomoticzManager] test_connection failed: {e}")
            self._connected = False
            return False

    def fetch_devices(self) -> list[dict[str, Any]]:
        """Retourne tous les périphériques utilisés depuis Domoticz."""
        try:
            data = self._get({
                "type": "devices",
                "filter": "all",
                "used": "true",
                "order": "Name",
            })
            return data.get("result", [])
        except Exception as e:
            print(f"[DomoticzManager] fetch_devices failed: {e}")
            return []

    def switch_device(self, idx: str, on: bool) -> bool:
        """Allume ou éteint un périphérique par son IDX."""
        cmd = "On" if on else "Off"
        try:
            data = self._get({
                "type": "command",
                "param": "switchlight",
                "idx": str(idx),
                "switchcmd": cmd,
            })
            if data.get("status") == "OK":
                return True

            # Certains Group/Scene n'acceptent pas switchlight et exigent switchscene.
            data_scene = self._get({
                "type": "command",
                "param": "switchscene",
                "idx": str(idx),
                "switchcmd": cmd,
            })
            return data_scene.get("status") == "OK"
        except Exception as e:
            print(f"[DomoticzManager] switch_device({idx}, {on}) failed: {e}")
            return False

    def set_level(self, idx: str, level: int) -> bool:
        """Définit la luminosité/niveau (0-100) d'un variateur."""
        clamped = max(0, min(100, level))
        try:
            data = self._get({
                "type": "command",
                "param": "switchlight",
                "idx": str(idx),
                "switchcmd": "Set Level",
                "level": str(clamped),
            })
            return data.get("status") == "OK"
        except Exception as e:
            print(f"[DomoticzManager] set_level({idx}, {level}) failed: {e}")
            return False

    def get_device(self, idx: str) -> dict[str, Any] | None:
        """Retourne les infos d'un périphérique par son IDX."""
        try:
            data = self._get({
                "type": "devices",
                "rid": str(idx),
            })
            result = data.get("result", [])
            return result[0] if result else None
        except Exception as e:
            print(f"[DomoticzManager] get_device({idx}) failed: {e}")
            return None


# Singleton global
domoticz_manager = DomoticzManager()

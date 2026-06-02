# core/providers/domoticz_provider.py
"""
DomoticzProvider — wraps core.domoticz_control.domoticz_manager for the
multi-provider architecture. All HTTP I/O is synchronous (domoticz_manager
uses requests). All imports of domoticz_manager are lazy (inside methods)
to keep the module importable in test environments.
"""
from __future__ import annotations

import time

from core.entity_models import (
    Provider, Entity,
    infer_zone, infer_capabilities,
)
from core.providers.base_provider import BaseProvider
from core.settings_store import settings

# Types Domoticz commandables (toggle / level)
_CONTROLLABLE_TYPES = frozenset({
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

# SwitchType Domoticz pour les variateurs (dimmer)
_DIMMER_SWITCH_TYPES = frozenset({2, 7})  # 2=Dimmer, 7=Dimmer RGB


def _domoticz_to_entity_type(d_type: str, switch_type: int | None) -> str:
    """Convertit un type Domoticz en type d'entité ADA."""
    if d_type == "Thermostat":
        return "sensor"
    if d_type in ("Temp", "Humidity", "Temp + Humidity",
                  "Wind", "Rain", "UV", "Air Quality",
                  "Lux", "Barometer", "Usage", "Energy", "Current"):
        return "sensor"
    if d_type == "Scene":
        return "scene"
    if d_type == "Group":
        return "switch"
    if d_type.startswith("Lighting"):
        return "switch"
    if d_type in ("Color Switch", "Dimmer"):
        return "light"
    if d_type == "Light/Switch":
        return "light" if switch_type in _DIMMER_SWITCH_TYPES else "switch"
    if "Blind" in d_type:
        return "switch"
    return "switch"


class DomoticzProvider(BaseProvider):
    """Adapter qui expose les périphériques Domoticz comme entités ADA."""

    PROVIDER_ID = "domoticz"

    def __init__(self) -> None:
        self._idx_type_map: dict[str, str] = {}    # idx → domoticz_type
        self._idx_subtype_map: dict[str, str] = {}  # idx → domoticz_subtype
        self._provider = Provider(
            id=self.PROVIDER_ID,
            name="Domoticz",
            enabled=settings.get("domoticz.enabled", False),
            type="domoticz",
            base_url=settings.get("domoticz.url", ""),
            priority=settings.get("domoticz.priority", 80),
        )

    @property
    def provider_info(self) -> Provider:
        self._provider.enabled = settings.get("domoticz.enabled", False)
        self._provider.base_url = settings.get("domoticz.url", "")
        self._provider.priority = settings.get("domoticz.priority", 80)
        return self._provider

    # ------------------------------------------------------------------ #

    def fetch_entities(self) -> list[Entity]:
        if not self.provider_info.enabled:
            return []
        try:
            from core.domoticz_control import domoticz_manager
            domoticz_manager.reload_config()
            raw_devices = domoticz_manager.fetch_devices()
        except Exception as e:
            print(f"[DomoticzProvider] fetch_entities failed: {e}")
            return []

        entities: list[Entity] = []
        self._idx_type_map = {}  # reset à chaque fetch
        for dev in raw_devices:
            idx = str(dev.get("idx", ""))
            name = dev.get("Name", idx)
            d_type = dev.get("Type", "")
            self._idx_type_map[idx] = d_type
            subtype = dev.get("SubType", "")
            self._idx_subtype_map[idx] = subtype

            # Normalisation du SwitchType (int ou absent)
            switch_type_raw = dev.get("SwitchType")
            if isinstance(switch_type_raw, str):
                try:
                    switch_type = int(switch_type_raw)
                except ValueError:
                    switch_type = None
            elif isinstance(switch_type_raw, int):
                switch_type = switch_type_raw
            else:
                switch_type = None

            status = dev.get("Status", "")
            read_only = d_type not in _CONTROLLABLE_TYPES

            # État normalisé
            if read_only:
                state = str(dev.get("Data", status))
            else:
                state = "on" if status.lower() in ("on", "open") else "off"

            entity_type = _domoticz_to_entity_type(d_type, switch_type)

            attrs: dict = {
                "idx": idx,
                "domoticz_type": d_type,
                "subtype": subtype,
                "switch_type": switch_type,
                "description": dev.get("Description", ""),
                "hardware_name": dev.get("HardwareName", ""),
                "last_update": dev.get("LastUpdate", ""),
            }
            level_raw = dev.get("Level")
            try:
                level_val = int(str(level_raw))
                attrs["level_pct"] = max(0, min(100, level_val))
            except Exception:
                pass
            if read_only:
                attrs["data"] = dev.get("Data", "")

            caps = infer_capabilities(entity_type, attrs, read_only=read_only)

            # Ajoute la capacité brightness pour les variateurs
            if switch_type in _DIMMER_SWITCH_TYPES or d_type in ("Dimmer", "Color Switch"):
                if "brightness" not in caps:
                    caps.append("brightness")

            # HaveTimeout : True = appareil injoignable
            have_timeout = dev.get("HaveTimeout", False)
            available = have_timeout is False or have_timeout == "false"

            # Scènes et Groupes Domoticz partagent le même espace d'IDX que les
            # devices — on préfixe leur provider_entity_id avec 's' pour éviter
            # la collision (ex: Group 'Atelier' idx=19 vs Device 'DEP EXT Portail' idx=19)
            if d_type in ("Scene", "Group"):
                p_eid = f"s{idx}"
                eid   = f"{self.PROVIDER_ID}.s{idx}"
            else:
                p_eid = idx
                eid   = f"{self.PROVIDER_ID}.{idx}"

            entities.append(Entity(
                id=eid,
                provider=self.PROVIDER_ID,
                provider_entity_id=p_eid,
                name=name,
                type=entity_type,
                zone=infer_zone(name),
                state=state,
                attributes=attrs,
                capabilities=caps,
                read_only=read_only,
                available=available,
                last_updated=time.time(),
            ))

        return entities

    def test_connection(self) -> bool:
        try:
            from core.domoticz_control import domoticz_manager
            domoticz_manager.reload_config()
            ok = domoticz_manager.test_connection()
            self._provider.status = "connected" if ok else "disconnected"
            return ok
        except Exception as e:
            print(f"[DomoticzProvider] test_connection failed: {e}")
            self._provider.status = "error"
            return False

    def toggle(self, provider_entity_id: str, on: bool) -> bool:
        try:
            from core.domoticz_control import domoticz_manager
            p_eid = str(provider_entity_id)
            # Scènes/Groupes ont un provider_entity_id préfixé 's'
            if p_eid.startswith("s") and p_eid[1:].isdigit():
                real_idx = p_eid[1:]
                return domoticz_manager.switch_scene_or_group(real_idx, on)
            idx       = p_eid
            d_subtype = self._idx_subtype_map.get(idx, "")
            # Relais impulsionnels : switchcmd=Off ne transmet pas de signal RF
            # → seule la commande Toggle envoie l'impulsion physique
            if d_subtype == "Impuls":
                return domoticz_manager.switch_toggle(idx)
            return domoticz_manager.switch_device(idx, on)
        except Exception as e:
            print(f"[DomoticzProvider] toggle({provider_entity_id}, {on}) failed: {e}")
            return False

    def set_brightness(self, provider_entity_id: str, value: int) -> bool:
        try:
            from core.domoticz_control import domoticz_manager
            return domoticz_manager.set_level(provider_entity_id, value)
        except Exception as e:
            print(f"[DomoticzProvider] set_brightness({provider_entity_id}) failed: {e}")
            return False


# Singleton global
domoticz_provider = DomoticzProvider()

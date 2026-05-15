# core/providers/ha_provider.py
"""
HAProvider — wraps core.ha_control.ha_manager for the multi-provider
architecture. All HTTP I/O is synchronous (ha_manager uses requests).
All imports of ha_manager are lazy (inside methods) to keep the module
importable in test environments.
"""
from __future__ import annotations

import time

from core.entity_models import (
    Provider, Entity,
    infer_zone, infer_capabilities, ha_domain_to_entity_type,
)
from core.providers.base_provider import BaseProvider
from core.settings_store import settings

# Domains that HA considers read-only (no turn_on/turn_off service)
_READ_ONLY_DOMAINS = frozenset({"sensor", "binary_sensor", "camera"})


class HAProvider(BaseProvider):
    """Adapter that exposes Home Assistant entities as normalized ADA Entities."""

    PROVIDER_ID = "home_assistant"

    def __init__(self):
        self._provider = Provider(
            id=self.PROVIDER_ID,
            name="Home Assistant",
            enabled=settings.get("home_assistant.enabled", False),
            type="home_assistant",
            base_url=settings.get("home_assistant.url", ""),
            token=settings.get("home_assistant.token", ""),
            priority=100,
        )

    @property
    def provider_info(self) -> Provider:
        self._provider.enabled = settings.get("home_assistant.enabled", False)
        self._provider.base_url = settings.get("home_assistant.url", "")
        self._provider.token = settings.get("home_assistant.token", "")
        return self._provider

    # ------------------------------------------------------------------ #

    def fetch_entities(self) -> list[Entity]:
        if not self.provider_info.enabled:
            return []
        try:
            from core.ha_control import ha_manager
            ha_manager.reload_config()
            raw = ha_manager._fetch_all_states()
        except Exception as e:
            print(f"[HAProvider] fetch_entities failed: {e}")
            return []

        entities: list[Entity] = []
        for entity_id, info in raw.items():
            domain = entity_id.split(".")[0]
            attrs = info.get("attributes", {})
            name = attrs.get("friendly_name", entity_id)
            entity_type = ha_domain_to_entity_type(domain)
            read_only = domain in _READ_ONLY_DOMAINS

            caps = infer_capabilities(entity_type, attrs, read_only=read_only)
            state = info.get("state", "unknown")
            available = state not in ("unavailable", "unknown")

            entities.append(Entity(
                id=f"{self.PROVIDER_ID}.{entity_id}",
                provider=self.PROVIDER_ID,
                provider_entity_id=entity_id,
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
            from core.ha_control import ha_manager
            ha_manager.reload_config()
            ok = ha_manager.test_connection()
            self._provider.status = "connected" if ok else "disconnected"
            return ok
        except Exception as e:
            print(f"[HAProvider] test_connection failed: {e}")
            self._provider.status = "error"
            return False

    def toggle(self, provider_entity_id: str, on: bool) -> bool:
        try:
            from core.ha_control import ha_manager
            if on:
                return ha_manager.turn_on(provider_entity_id)
            else:
                return ha_manager.turn_off(provider_entity_id)
        except Exception as e:
            print(f"[HAProvider] toggle({provider_entity_id}, {on}) failed: {e}")
            return False

    def set_brightness(self, provider_entity_id: str, value: int) -> bool:
        try:
            from core.ha_control import ha_manager
            return ha_manager.turn_on(provider_entity_id, brightness_pct=value)
        except Exception as e:
            print(f"[HAProvider] set_brightness({provider_entity_id}) failed: {e}")
            return False


# Global singleton
ha_provider = HAProvider()

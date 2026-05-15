# core/providers/kasa_provider.py
"""
KasaProvider — wraps core.kasa_control.kasa_manager for the multi-provider
architecture. Kasa uses async discovery; we run it in a fresh event loop.
All imports of kasa_manager are lazy (inside methods) to keep the module
importable in test environments without real Kasa hardware.
"""
from __future__ import annotations

import asyncio
import time

from core.entity_models import Provider, Entity, infer_zone, infer_capabilities
from core.providers.base_provider import BaseProvider
from core.settings_store import settings


class KasaProvider(BaseProvider):
    """Adapter that exposes Kasa smart devices as normalized ADA Entities."""

    PROVIDER_ID = "kasa"

    def __init__(self):
        self._provider = Provider(
            id=self.PROVIDER_ID,
            name="Kasa",
            enabled=settings.get("kasa.enabled", True),
            type="kasa",
            priority=settings.get("kasa.priority", 50),
        )

    @property
    def provider_info(self) -> Provider:
        self._provider.enabled = settings.get("kasa.enabled", True)
        self._provider.priority = settings.get("kasa.priority", 50)
        return self._provider

    # ------------------------------------------------------------------ #

    def fetch_entities(self) -> list[Entity]:
        try:
            from core.kasa_control import kasa_manager
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            devices_dict = loop.run_until_complete(kasa_manager.discover_devices())
            loop.close()
        except Exception as e:
            print(f"[KasaProvider] fetch_entities failed: {e}")
            return []

        entities: list[Entity] = []
        for ip, dev in devices_dict.items():
            alias = dev.get("alias", ip)
            has_brightness = dev.get("brightness") is not None
            entity_type = "light" if (has_brightness or "Bulb" in dev.get("type", "")) else "switch"

            attrs: dict = {
                "ip": ip,
                "model": dev.get("model", ""),
                "kasa_type": dev.get("type", ""),
            }
            if has_brightness:
                attrs["brightness"] = dev["brightness"]
            if dev.get("is_color"):
                attrs["is_color"] = True

            caps = infer_capabilities(entity_type, attrs)

            entities.append(Entity(
                id=f"kasa.{ip}",
                provider=self.PROVIDER_ID,
                provider_entity_id=ip,
                name=alias,
                type=entity_type,
                zone=infer_zone(alias),
                state="on" if dev.get("is_on") else "off",
                attributes=attrs,
                capabilities=caps,
                read_only=False,
                available=True,
                last_updated=time.time(),
            ))
        return entities

    def test_connection(self) -> bool:
        try:
            from core.kasa_control import kasa_manager
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            result = loop.run_until_complete(kasa_manager.discover_devices())
            loop.close()
            ok = bool(result)
            self._provider.status = "connected" if ok else "disconnected"
            return ok
        except Exception as e:
            print(f"[KasaProvider] test_connection failed: {e}")
            self._provider.status = "error"
            return False

    def toggle(self, provider_entity_id: str, on: bool) -> bool:
        try:
            from core.kasa_control import kasa_manager
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            if on:
                result = loop.run_until_complete(kasa_manager.turn_on(provider_entity_id))
            else:
                result = loop.run_until_complete(kasa_manager.turn_off(provider_entity_id))
            loop.close()
            return result
        except Exception as e:
            print(f"[KasaProvider] toggle({provider_entity_id}, {on}) failed: {e}")
            return False

    def set_brightness(self, provider_entity_id: str, value: int) -> bool:
        try:
            from core.kasa_control import kasa_manager
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            result = loop.run_until_complete(
                kasa_manager.set_brightness(provider_entity_id, value)
            )
            loop.close()
            return result
        except Exception as e:
            print(f"[KasaProvider] set_brightness({provider_entity_id}) failed: {e}")
            return False


# Global singleton
kasa_provider = KasaProvider()

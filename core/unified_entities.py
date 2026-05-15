# core/unified_entities.py
"""
UnifiedEntityService — aggregates entities from all enabled providers,
merges them into a single list, and exposes action helpers for the UI.

Usage:
    from core.unified_entities import unified_entity_service
    entities = unified_entity_service.get_unified_entities(force_refresh=True)
    unified_entity_service.toggle_entity("kasa.192.168.1.10")
"""
from __future__ import annotations

import threading
from typing import Optional

from core.entity_models import Entity, Provider

class UnifiedEntityService:
    """
    Orchestrates all registered provider adapters and exposes a unified
    entity list to the UI layer.

    Thread-safe: refresh_providers() acquires a lock; the UI reads
    _entities after the background thread emits done.
    """

    def __init__(self):
        self._lock = threading.Lock()
        self._entities: list[Entity] = []
        self._providers: dict = {}
        self._refreshing = False
        self._register_defaults()

    def _register_defaults(self):
        try:
            from core.providers.kasa_provider import kasa_provider
            self._providers["kasa"] = kasa_provider
        except Exception as e:
            print(f"[UnifiedEntityService] Could not register kasa_provider: {e}")
        try:
            from core.providers.ha_provider import ha_provider
            self._providers["home_assistant"] = ha_provider
        except Exception as e:
            print(f"[UnifiedEntityService] Could not register ha_provider: {e}")

    # ------------------------------------------------------------------ #
    # Query                                                                #
    # ------------------------------------------------------------------ #

    def get_providers(self) -> list[Provider]:
        """Return current metadata for all registered providers."""
        return [p.provider_info for p in self._providers.values()]

    def get_unified_entities(self, force_refresh: bool = False) -> list[Entity]:
        """
        Return the cached entity list, optionally refreshing from all providers first.
        Callers in background threads should pass force_refresh=True.
        """
        should_refresh = force_refresh or not self._entities
        if should_refresh and not getattr(self, "_refreshing", False):
            self.refresh_providers()
        return list(self._entities)

    def get_entity(self, entity_id: str) -> Optional[Entity]:
        """Look up a single entity by its ADA entity id."""
        for e in self._entities:
            if e.id == entity_id:
                return e
        return None

    # ------------------------------------------------------------------ #
    # Refresh                                                              #
    # ------------------------------------------------------------------ #

    def refresh_providers(self):
        """
        Fetch entities from all enabled providers, merge results, deduplicate.
        Thread-safe. Individual provider failures are caught and logged.
        """
        self._refreshing = True
        lock = getattr(self, "_lock", threading.Lock())
        with lock:
            new_entities: list[Entity] = []
            seen_ids: set[str] = set()

            for provider_id, provider in self._providers.items():
                info = provider.provider_info
                if not info.enabled:
                    continue
                try:
                    for e in provider.fetch_entities():
                        if e.id not in seen_ids:
                            seen_ids.add(e.id)
                            new_entities.append(e)
                except Exception as ex:
                    print(f"[UnifiedEntityService] Provider '{provider_id}' raised: {ex}")

            self._entities = new_entities
        self._refreshing = False

    # ------------------------------------------------------------------ #
    # Actions                                                              #
    # ------------------------------------------------------------------ #

    def toggle_entity(self, entity_id: str, on: Optional[bool] = None) -> bool:
        """
        Toggle entity on/off. If `on` is None, toggles current state.
        Returns False for read-only entities or unknown ids.
        """
        entity = self.get_entity(entity_id)
        if entity is None or entity.read_only:
            return False
        provider = self._providers.get(entity.provider)
        if provider is None:
            return False
        target_on = on if on is not None else (entity.state != "on")
        try:
            result = provider.toggle(entity.provider_entity_id, target_on)
            if result:
                # Optimistic update — mutates the cached Entity in-place so
                # callers holding a reference see the new state immediately.
                entity.state = "on" if target_on else "off"
            return result
        except Exception as e:
            print(f"[UnifiedEntityService] toggle_entity({entity_id}) failed: {e}")
            return False

    def set_entity_brightness(self, entity_id: str, value: int) -> bool:
        """
        Set brightness 0-100 for an entity that has 'brightness' capability.
        Returns False if entity lacks the capability or provider fails.
        """
        entity = self.get_entity(entity_id)
        if entity is None or "brightness" not in entity.capabilities:
            return False
        provider = self._providers.get(entity.provider)
        if provider is None:
            return False
        try:
            return provider.set_brightness(entity.provider_entity_id, value)
        except Exception as e:
            print(f"[UnifiedEntityService] set_entity_brightness({entity_id}) failed: {e}")
            return False

    def send_tts_to_entity(self, entity_id: str, message: str) -> bool:
        """
        Send TTS speech to an entity that has 'tts' capability.
        Currently only HA media_player entities support TTS.
        """
        entity = self.get_entity(entity_id)
        if entity is None or "tts" not in entity.capabilities:
            return False
        if entity.provider == "home_assistant":
            try:
                from core.ha_control import ha_manager
                from core.settings_store import settings
                tts_service = settings.get("home_assistant.tts_service", "tts.piper")
                return ha_manager.speak_to_media_player(
                    entity.provider_entity_id, message, tts_service
                )
            except Exception as e:
                print(f"[UnifiedEntityService] send_tts_to_entity({entity_id}) failed: {e}")
                return False
        return False

    def test_provider_connection(self, provider_id: str) -> bool:
        """Test connectivity to a specific provider. Updates its status."""
        provider = self._providers.get(provider_id)
        if provider is None:
            return False
        try:
            return provider.test_connection()
        except Exception as e:
            print(f"[UnifiedEntityService] test_provider_connection({provider_id}) failed: {e}")
            return False


# Global singleton
unified_entity_service = UnifiedEntityService()

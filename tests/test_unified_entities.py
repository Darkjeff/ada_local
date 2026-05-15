# tests/test_unified_entities.py
"""
Tests for UnifiedEntityService — provider orchestration + entity actions.
Providers are mocked: no real Kasa/HA calls.
"""
import sys
import os
import unittest
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from core.entity_models import Provider, Entity


def _make_entity(entity_id: str, provider: str, entity_type: str = "light",
                  state: str = "on", read_only: bool = False,
                  capabilities: list | None = None) -> Entity:
    return Entity(
        id=f"{provider}.{entity_id}",
        provider=provider,
        provider_entity_id=entity_id,
        name=f"Test {entity_id}",
        type=entity_type,
        zone="Other",
        state=state,
        capabilities=capabilities or ["read", "control"],
        read_only=read_only,
    )


def _make_provider_mock(provider_id: str, entities: list[Entity], enabled: bool = True):
    mock = MagicMock()
    mock.provider_info = Provider(
        id=provider_id, name=provider_id.title(),
        enabled=enabled, type=provider_id
    )
    mock.fetch_entities.return_value = entities
    mock.toggle.return_value = True
    mock.set_brightness.return_value = True
    return mock


class TestGetUnifiedEntities(unittest.TestCase):

    def _service(self, providers: dict):
        from core.unified_entities import UnifiedEntityService
        svc = UnifiedEntityService.__new__(UnifiedEntityService)
        svc._entities = []
        svc._providers = providers
        return svc

    def test_merges_entities_from_all_enabled_providers(self):
        """get_unified_entities() aggregates entities from all providers."""
        kasa_mock = _make_provider_mock("kasa", [_make_entity("1.2.3.4", "kasa")])
        ha_mock = _make_provider_mock("home_assistant", [_make_entity("light.desk", "home_assistant")])
        svc = self._service({"kasa": kasa_mock, "home_assistant": ha_mock})

        entities = svc.get_unified_entities(force_refresh=True)
        self.assertEqual(len(entities), 2)

    def test_skips_disabled_providers(self):
        """Disabled providers are not fetched."""
        kasa_mock = _make_provider_mock("kasa", [_make_entity("1.2.3.4", "kasa")], enabled=False)
        ha_mock = _make_provider_mock("home_assistant", [_make_entity("light.desk", "home_assistant")])
        svc = self._service({"kasa": kasa_mock, "home_assistant": ha_mock})

        entities = svc.get_unified_entities(force_refresh=True)
        self.assertEqual(len(entities), 1)
        self.assertEqual(entities[0].provider, "home_assistant")

    def test_no_duplicate_entity_ids(self):
        """If two providers return the same entity id, only first is kept."""
        e1 = _make_entity("duplicate", "kasa")
        e2 = _make_entity("duplicate", "kasa")   # same id
        mock = _make_provider_mock("kasa", [e1, e2])
        svc = self._service({"kasa": mock})

        entities = svc.get_unified_entities(force_refresh=True)
        self.assertEqual(len(entities), 1)

    def test_provider_failure_does_not_crash_others(self):
        """If provider A raises, provider B still returns entities."""
        kasa_mock = _make_provider_mock("kasa", [])
        kasa_mock.fetch_entities.side_effect = RuntimeError("kasa down")
        ha_mock = _make_provider_mock("home_assistant", [_make_entity("light.desk", "home_assistant")])
        svc = self._service({"kasa": kasa_mock, "home_assistant": ha_mock})

        entities = svc.get_unified_entities(force_refresh=True)
        self.assertEqual(len(entities), 1)


class TestToggleEntity(unittest.TestCase):

    def _service_with_entities(self, entities: list[Entity], provider_mock):
        from core.unified_entities import UnifiedEntityService
        svc = UnifiedEntityService.__new__(UnifiedEntityService)
        svc._entities = entities
        svc._providers = {entities[0].provider: provider_mock}
        return svc

    def test_toggle_calls_provider_toggle(self):
        """toggle_entity() delegates to the provider's toggle()."""
        entity = _make_entity("light.desk", "kasa")
        mock = _make_provider_mock("kasa", [entity])
        svc = self._service_with_entities([entity], mock)

        result = svc.toggle_entity("kasa.light.desk")
        mock.toggle.assert_called_once()
        self.assertTrue(result)

    def test_toggle_returns_false_for_unknown_entity(self):
        """toggle_entity() returns False if entity id not found."""
        entity = _make_entity("light.desk", "kasa")
        mock = _make_provider_mock("kasa", [entity])
        svc = self._service_with_entities([entity], mock)

        result = svc.toggle_entity("kasa.nonexistent")
        self.assertFalse(result)

    def test_toggle_returns_false_for_read_only(self):
        """toggle_entity() returns False for read-only entities."""
        entity = _make_entity("sensor.temp", "kasa", read_only=True)
        mock = _make_provider_mock("kasa", [entity])
        svc = self._service_with_entities([entity], mock)

        result = svc.toggle_entity("kasa.sensor.temp")
        self.assertFalse(result)

    def test_set_brightness_calls_provider(self):
        """set_entity_brightness() delegates to provider.set_brightness()."""
        entity = _make_entity("light.desk", "kasa", capabilities=["read", "control", "brightness"])
        mock = _make_provider_mock("kasa", [entity])
        svc = self._service_with_entities([entity], mock)

        result = svc.set_entity_brightness("kasa.light.desk", 75)
        mock.set_brightness.assert_called_once_with("light.desk", 75)
        self.assertTrue(result)

    def test_set_brightness_returns_false_without_capability(self):
        """set_entity_brightness() returns False if entity lacks 'brightness' cap."""
        entity = _make_entity("switch.plug", "kasa", capabilities=["read", "control"])
        mock = _make_provider_mock("kasa", [entity])
        svc = self._service_with_entities([entity], mock)

        result = svc.set_entity_brightness("kasa.switch.plug", 50)
        self.assertFalse(result)


class TestTestProviderConnection(unittest.TestCase):

    def test_delegates_to_provider(self):
        """test_provider_connection() calls the provider's test_connection()."""
        from core.unified_entities import UnifiedEntityService
        svc = UnifiedEntityService.__new__(UnifiedEntityService)
        mock = MagicMock()
        mock.test_connection.return_value = True
        svc._providers = {"kasa": mock}
        svc._entities = []

        result = svc.test_provider_connection("kasa")
        mock.test_connection.assert_called_once()
        self.assertTrue(result)

    def test_returns_false_for_unknown_provider(self):
        """test_provider_connection() returns False for unknown provider id."""
        from core.unified_entities import UnifiedEntityService
        svc = UnifiedEntityService.__new__(UnifiedEntityService)
        svc._providers = {}
        svc._entities = []

        self.assertFalse(svc.test_provider_connection("nonexistent"))


if __name__ == "__main__":
    unittest.main()

# tests/test_ha_provider.py
"""
Tests for HAProvider adapter.
All HTTP calls are mocked — no real HA instance needed.
"""
import sys
import os
import time
import unittest
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))


def _fake_settings(key, default=None):
    return {
        "home_assistant.enabled": True,
        "home_assistant.url": "http://ha.local:8123",
        "home_assistant.token": "fake-token",
        "home_assistant.tts_service": "tts.piper",
    }.get(key, default)


class TestHAProviderFetchEntities(unittest.TestCase):

    def _provider(self):
        with patch('core.settings_store.settings') as mock_s:
            mock_s.get.side_effect = _fake_settings
            from core.providers.ha_provider import HAProvider
            return HAProvider()

    def _raw_entities(self):
        return {
            "light.kitchen": {
                "entity_id": "light.kitchen",
                "state": "on",
                "attributes": {"friendly_name": "Cuisine Light", "brightness": 200},
            },
            "sensor.temperature": {
                "entity_id": "sensor.temperature",
                "state": "22.5",
                "attributes": {"friendly_name": "Bureau Temp", "device_class": "temperature",
                               "unit_of_measurement": "°C"},
            },
            "camera.front_door": {
                "entity_id": "camera.front_door",
                "state": "idle",
                "attributes": {"friendly_name": "Front Door Camera"},
            },
            "media_player.salon": {
                "entity_id": "media_player.salon",
                "state": "idle",
                "attributes": {"friendly_name": "Salon Speaker", "volume_level": 0.4},
            },
        }

    def test_returns_entity_for_each_ha_entity(self):
        """fetch_entities() returns one Entity per HA state."""
        provider = self._provider()
        with patch('core.ha_control.ha_manager') as mock_ha:
            mock_ha.reload_config.return_value = None
            mock_ha._fetch_all_states.return_value = self._raw_entities()
            entities = provider.fetch_entities()

        self.assertEqual(len(entities), 4)

    def test_entity_ids_prefixed_with_home_assistant(self):
        """Entity.id is 'home_assistant.{ha_entity_id}'."""
        provider = self._provider()
        with patch('core.ha_control.ha_manager') as mock_ha:
            mock_ha.reload_config.return_value = None
            mock_ha._fetch_all_states.return_value = self._raw_entities()
            entities = provider.fetch_entities()

        ids = {e.id for e in entities}
        self.assertIn("home_assistant.light.kitchen", ids)
        self.assertIn("home_assistant.sensor.temperature", ids)

    def test_light_entity_has_brightness_capability(self):
        """HA light with brightness attr gets 'brightness' capability."""
        provider = self._provider()
        with patch('core.ha_control.ha_manager') as mock_ha:
            mock_ha.reload_config.return_value = None
            mock_ha._fetch_all_states.return_value = self._raw_entities()
            entities = provider.fetch_entities()

        light = next(e for e in entities if e.id == "home_assistant.light.kitchen")
        self.assertIn("brightness", light.capabilities)

    def test_sensor_is_read_only(self):
        """Sensor entities are read_only=True."""
        provider = self._provider()
        with patch('core.ha_control.ha_manager') as mock_ha:
            mock_ha.reload_config.return_value = None
            mock_ha._fetch_all_states.return_value = self._raw_entities()
            entities = provider.fetch_entities()

        sensor = next(e for e in entities if e.id == "home_assistant.sensor.temperature")
        self.assertTrue(sensor.read_only)

    def test_media_player_has_tts_capability(self):
        """HA media_player entities always have 'tts' capability."""
        provider = self._provider()
        with patch('core.ha_control.ha_manager') as mock_ha:
            mock_ha.reload_config.return_value = None
            mock_ha._fetch_all_states.return_value = self._raw_entities()
            entities = provider.fetch_entities()

        mp = next(e for e in entities if e.id == "home_assistant.media_player.salon")
        self.assertIn("tts", mp.capabilities)

    def test_zone_inferred_from_friendly_name(self):
        """Zone is inferred from the entity's friendly_name attribute."""
        provider = self._provider()
        with patch('core.ha_control.ha_manager') as mock_ha:
            mock_ha.reload_config.return_value = None
            mock_ha._fetch_all_states.return_value = self._raw_entities()
            entities = provider.fetch_entities()

        sensor = next(e for e in entities if e.id == "home_assistant.sensor.temperature")
        self.assertEqual(sensor.zone, "Bureau")

    def test_returns_empty_when_disabled(self):
        """fetch_entities() returns [] when HA is disabled in settings."""
        with patch('core.settings_store.settings') as mock_s:
            mock_s.get.side_effect = lambda key, default=None: {
                "home_assistant.enabled": False,
            }.get(key, default)
            from core.providers.ha_provider import HAProvider
            provider = HAProvider()

        entities = provider.fetch_entities()
        self.assertEqual(entities, [])

    def test_returns_empty_on_exception(self):
        """fetch_entities() returns [] if ha_manager raises."""
        provider = self._provider()
        with patch('core.ha_control.ha_manager') as mock_ha:
            mock_ha.reload_config.side_effect = RuntimeError("ha down")
            entities = provider.fetch_entities()

        self.assertEqual(entities, [])

    def test_toggle_on_calls_ha_turn_on(self):
        """toggle(entity_id, True) calls ha_manager.turn_on()."""
        provider = self._provider()
        with patch('core.ha_control.ha_manager') as mock_ha:
            mock_ha.turn_on.return_value = True
            result = provider.toggle("light.kitchen", True)

        mock_ha.turn_on.assert_called_once_with("light.kitchen")
        self.assertTrue(result)

    def test_toggle_off_calls_ha_turn_off(self):
        """toggle(entity_id, False) calls ha_manager.turn_off()."""
        provider = self._provider()
        with patch('core.ha_control.ha_manager') as mock_ha:
            mock_ha.turn_off.return_value = True
            result = provider.toggle("light.kitchen", False)

        mock_ha.turn_off.assert_called_once_with("light.kitchen")
        self.assertTrue(result)


if __name__ == "__main__":
    unittest.main()

# tests/test_kasa_provider.py
"""
Tests for KasaProvider adapter.
All network calls are mocked — no real Kasa devices needed.
"""
import sys
import os
import asyncio
import unittest
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

# Stub out the 'kasa' package and core.kasa_control so tests run without
# real hardware or the python-kasa library installed.
if 'kasa' not in sys.modules:
    _fake_kasa = MagicMock()
    sys.modules['kasa'] = _fake_kasa

_fake_kasa_control = MagicMock()
_fake_kasa_manager = MagicMock()
_fake_kasa_control.kasa_manager = _fake_kasa_manager
sys.modules['core.kasa_control'] = _fake_kasa_control


def _make_kasa_device(alias: str, ip: str, is_on: bool,
                      brightness: int | None = None, is_color: bool = False):
    return {
        "alias": alias,
        "ip": ip,
        "model": "KL130",
        "is_on": is_on,
        "type": "Bulb" if brightness is not None else "Plug",
        "brightness": brightness,
        "is_color": is_color,
        "hsv": None,
        "obj": MagicMock(),
    }


class TestKasaProviderFetchEntities(unittest.TestCase):

    def _provider(self):
        with patch('core.settings_store.settings') as mock_s:
            mock_s.get.side_effect = lambda key, default=None: {
                "kasa.enabled": True,
                "kasa.priority": 50,
            }.get(key, default)
            from core.providers.kasa_provider import KasaProvider
            return KasaProvider()

    def test_returns_entities_for_each_device(self):
        """fetch_entities() returns one Entity per discovered Kasa device."""
        provider = self._provider()

        async def mock_discover():
            return {
                "192.168.1.10": _make_kasa_device("Office Light", "192.168.1.10", True, brightness=80),
                "192.168.1.11": _make_kasa_device("Kitchen Plug", "192.168.1.11", False),
            }

        with patch('core.kasa_control.kasa_manager') as mock_km:
            mock_km.discover_devices = mock_discover
            entities = provider.fetch_entities()

        self.assertEqual(len(entities), 2)
        ids = {e.id for e in entities}
        self.assertIn("kasa.192.168.1.10", ids)
        self.assertIn("kasa.192.168.1.11", ids)

    def test_bulb_entity_has_light_type(self):
        """A Kasa bulb (brightness not None) is typed as 'light'."""
        provider = self._provider()

        async def mock_discover():
            return {"192.168.1.10": _make_kasa_device("Desk Bulb", "192.168.1.10", True, brightness=50)}

        with patch('core.kasa_control.kasa_manager') as mock_km:
            mock_km.discover_devices = mock_discover
            entities = provider.fetch_entities()

        self.assertEqual(entities[0].type, "light")

    def test_plug_entity_has_switch_type(self):
        """A Kasa plug (no brightness) is typed as 'switch'."""
        provider = self._provider()

        async def mock_discover():
            return {"192.168.1.20": _make_kasa_device("Coffee Plug", "192.168.1.20", False)}

        with patch('core.kasa_control.kasa_manager') as mock_km:
            mock_km.discover_devices = mock_discover
            entities = provider.fetch_entities()

        self.assertEqual(entities[0].type, "switch")

    def test_bulb_entity_has_brightness_capability(self):
        """Bulbs have 'brightness' in capabilities."""
        provider = self._provider()

        async def mock_discover():
            return {"192.168.1.10": _make_kasa_device("Bulb", "192.168.1.10", True, brightness=60)}

        with patch('core.kasa_control.kasa_manager') as mock_km:
            mock_km.discover_devices = mock_discover
            entities = provider.fetch_entities()

        self.assertIn("brightness", entities[0].capabilities)

    def test_color_bulb_has_color_capability(self):
        """Color bulbs have 'color' in capabilities."""
        provider = self._provider()

        async def mock_discover():
            return {"192.168.1.10": _make_kasa_device("Color Bulb", "192.168.1.10", True, brightness=80, is_color=True)}

        with patch('core.kasa_control.kasa_manager') as mock_km:
            mock_km.discover_devices = mock_discover
            entities = provider.fetch_entities()

        self.assertIn("color", entities[0].capabilities)

    def test_zone_inferred_from_alias(self):
        """Zone is inferred from the device alias."""
        provider = self._provider()

        async def mock_discover():
            return {"192.168.1.10": _make_kasa_device("Bureau Desk Lamp", "192.168.1.10", True)}

        with patch('core.kasa_control.kasa_manager') as mock_km:
            mock_km.discover_devices = mock_discover
            entities = provider.fetch_entities()

        self.assertEqual(entities[0].zone, "Bureau")

    def test_returns_empty_on_exception(self):
        """fetch_entities() returns [] if kasa_manager raises."""
        provider = self._provider()

        async def mock_discover():
            raise RuntimeError("network error")

        with patch('core.kasa_control.kasa_manager') as mock_km:
            mock_km.discover_devices = mock_discover
            entities = provider.fetch_entities()

        self.assertEqual(entities, [])

    def test_provider_info_id(self):
        """provider_info returns a Provider with id='kasa'."""
        provider = self._provider()
        self.assertEqual(provider.provider_info.id, "kasa")

    def test_toggle_calls_turn_on(self):
        """toggle(ip, True) calls kasa_manager.turn_on(ip)."""
        provider = self._provider()

        async def mock_turn_on(ip):
            return True

        with patch('core.kasa_control.kasa_manager') as mock_km:
            mock_km.turn_on = mock_turn_on
            result = provider.toggle("192.168.1.10", True)

        self.assertTrue(result)

    def test_toggle_calls_turn_off(self):
        """toggle(ip, False) calls kasa_manager.turn_off(ip)."""
        provider = self._provider()

        async def mock_turn_off(ip):
            return True

        with patch('core.kasa_control.kasa_manager') as mock_km:
            mock_km.turn_off = mock_turn_off
            result = provider.toggle("192.168.1.10", False)

        self.assertTrue(result)


if __name__ == "__main__":
    unittest.main()

# tests/test_provider_settings.py
import sys
import os
import unittest
from unittest.mock import patch, mock_open

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))


class TestKasaDefaults(unittest.TestCase):

    def setUp(self):
        """Use a fresh in-memory SettingsStore that never touches disk."""
        with patch('pathlib.Path.exists', return_value=False), \
             patch('pathlib.Path.mkdir'), \
             patch('builtins.open', mock_open()):
            from core.settings_store import SettingsStore
            self.store = SettingsStore()

    def test_kasa_enabled_default_true(self):
        self.assertTrue(self.store.get("kasa.enabled"))

    def test_kasa_priority_default_50(self):
        self.assertEqual(self.store.get("kasa.priority"), 50)

    def test_ha_enabled_default_false(self):
        """Existing HA default must still be False."""
        self.assertFalse(self.store.get("home_assistant.enabled"))

    def test_ha_tts_service_default(self):
        """Existing HA tts_service default must still be tts.piper."""
        self.assertEqual(self.store.get("home_assistant.tts_service"), "tts.piper")


if __name__ == "__main__":
    unittest.main()

"""
Tests that remote endpoint i18n keys exist in both locale files.

Run: python -m pytest tests/test_remote_endpoints_i18n.py -v
"""
import sys
import os
import json
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

LOCALES_DIR = os.path.join(os.path.dirname(__file__), '..', 'locales')

REQUIRED_SENSES_KEYS = [
    "endpoints",
    "endpoints_desc",
    "speech_output_mode",
    "speech_output_mode_desc",
    "speech_output_local",
    "ha_tts_service",
    "ha_tts_service_desc",
    "ha_tts_service_placeholder",
    "test_speech",
    "test_speech_desc",
    "test_speech_btn",
    "test_speech_phrase",
    "test_speech_sent",
    "intent_inputs",
    "intent_note",
    "badge_local",
    "badge_ha",
    "badge_cloud",
    "badge_intent_only",
    "test_speech_failed",
    "test_speech_failed_detail",
]


def _load_locale(lang: str) -> dict:
    path = os.path.join(LOCALES_DIR, f"{lang}.json")
    with open(path, 'r', encoding='utf-8') as f:
        return json.load(f)


class TestEnglishRemoteEndpointKeys(unittest.TestCase):

    def setUp(self):
        self.locale = _load_locale("en")
        self.senses = self.locale.get("senses", {})

    def test_all_required_keys_present(self):
        """All 19 remote endpoint keys exist in en.json senses section."""
        for key in REQUIRED_SENSES_KEYS:
            with self.subTest(key=key):
                self.assertIn(key, self.senses, f"Missing key: senses.{key} in en.json")

    def test_all_values_are_non_empty_strings(self):
        """All new keys have non-empty string values."""
        for key in REQUIRED_SENSES_KEYS:
            with self.subTest(key=key):
                value = self.senses.get(key, "")
                self.assertIsInstance(value, str, f"senses.{key} should be str")
                self.assertTrue(value.strip(), f"senses.{key} should not be empty")


class TestFrenchRemoteEndpointKeys(unittest.TestCase):

    def setUp(self):
        self.locale = _load_locale("fr")
        self.senses = self.locale.get("senses", {})

    def test_all_required_keys_present(self):
        """All 19 remote endpoint keys exist in fr.json senses section."""
        for key in REQUIRED_SENSES_KEYS:
            with self.subTest(key=key):
                self.assertIn(key, self.senses, f"Missing key: senses.{key} in fr.json")

    def test_all_values_are_non_empty_strings(self):
        """All new keys have non-empty string values."""
        for key in REQUIRED_SENSES_KEYS:
            with self.subTest(key=key):
                value = self.senses.get(key, "")
                self.assertIsInstance(value, str, f"senses.{key} should be str")
                self.assertTrue(value.strip(), f"senses.{key} should not be empty")


if __name__ == '__main__':
    unittest.main()

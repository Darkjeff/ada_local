"""
Tests for new remote endpoints settings defaults.

Run: python -m pytest tests/test_remote_endpoints_settings.py -v
"""
import sys
import os
import ast
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))


def _get_defaults() -> dict:
    settings_file = os.path.join(os.path.dirname(__file__), '..', 'core', 'settings_store.py')
    with open(settings_file, 'r', encoding='utf-8') as f:
        tree = ast.parse(f.read())
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id == 'DEFAULT_SETTINGS':
                    return ast.literal_eval(node.value)
    raise RuntimeError("DEFAULT_SETTINGS not found")


class TestHATTSDefaults(unittest.TestCase):

    def test_ha_tts_service_default(self):
        """home_assistant.tts_service defaults to 'tts.piper'."""
        defaults = _get_defaults()
        self.assertEqual(defaults["home_assistant"]["tts_service"], "tts.piper")

    def test_ha_tts_target_entity_default(self):
        """home_assistant.tts_target_entity defaults to empty string."""
        defaults = _get_defaults()
        self.assertEqual(defaults["home_assistant"]["tts_target_entity"], "")

    def test_ha_tts_service_is_string(self):
        """home_assistant.tts_service is a string."""
        defaults = _get_defaults()
        self.assertIsInstance(defaults["home_assistant"]["tts_service"], str)


class TestSensesSpeechOutputDefaults(unittest.TestCase):

    def test_speech_output_mode_default(self):
        """senses.speech_output_mode defaults to 'local'."""
        defaults = _get_defaults()
        self.assertEqual(defaults["senses"]["speech_output_mode"], "local")

    def test_ha_tts_entity_default(self):
        """senses.ha_tts_entity defaults to empty string."""
        defaults = _get_defaults()
        self.assertEqual(defaults["senses"]["ha_tts_entity"], "")

    def test_speech_output_mode_is_string(self):
        """senses.speech_output_mode is a string."""
        defaults = _get_defaults()
        self.assertIsInstance(defaults["senses"]["speech_output_mode"], str)

    def test_ha_tts_entity_is_string(self):
        """senses.ha_tts_entity is a string."""
        defaults = _get_defaults()
        self.assertIsInstance(defaults["senses"]["ha_tts_entity"], str)


if __name__ == '__main__':
    unittest.main()

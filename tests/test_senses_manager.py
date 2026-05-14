"""
Tests for core/senses_manager.py — device registry and can_* checks.

Run: python -m pytest tests/test_senses_manager.py -v
  or: python -m unittest tests.test_senses_manager -v
"""
import sys
import os
import unittest
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))


def make_manager():
    """Return a fresh SensesManager (not the global singleton)."""
    from core.senses_manager import SensesManager
    return SensesManager()


class TestRegistry(unittest.TestCase):

    def test_default_devices_registered(self):
        """SensesManager registers local_mic and local_speaker by default."""
        sm = make_manager()
        ids = {d["id"] for d in sm.get_devices()}
        self.assertIn("local_mic", ids)
        self.assertIn("local_speaker", ids)

    def test_register_device_adds_entry(self):
        """register_device() adds a new device to the registry."""
        sm = make_manager()
        sm.register_device({
            "id": "test_device",
            "name": "Test Player",
            "device_type": "speech_output",
            "source": "home_assistant",
            "privacy": "local_or_cloud_dependent",
            "enabled": True,
            "entity_id": "media_player.test",
        })
        ids = {d["id"] for d in sm.get_devices()}
        self.assertIn("test_device", ids)

    def test_register_device_replaces_existing_by_id(self):
        """register_device() replaces an existing device with the same id."""
        sm = make_manager()
        sm.register_device({
            "id": "local_mic",
            "name": "Updated Mic",
            "device_type": "raw_audio",
            "source": "local",
            "privacy": "local",
            "enabled": True,
            "entity_id": None,
        })
        mics = sm.get_raw_audio_inputs()
        self.assertEqual(len(mics), 1)
        self.assertEqual(mics[0]["name"], "Updated Mic")

    def test_get_devices_returns_all_when_no_filter(self):
        """get_devices() with no argument returns all registered devices."""
        sm = make_manager()
        result = sm.get_devices()
        self.assertIsInstance(result, list)
        self.assertGreaterEqual(len(result), 2)

    def test_get_devices_filters_by_type(self):
        """get_devices('speech_output') returns only speech_output devices."""
        sm = make_manager()
        result = sm.get_devices("speech_output")
        self.assertTrue(all(d["device_type"] == "speech_output" for d in result))

    def test_get_speech_outputs_matches_filter(self):
        """get_speech_outputs() == get_devices('speech_output')."""
        sm = make_manager()
        self.assertEqual(sm.get_speech_outputs(), sm.get_devices("speech_output"))

    def test_get_intent_inputs_empty_by_default(self):
        """No intent_input devices registered in default state."""
        sm = make_manager()
        self.assertEqual(sm.get_intent_inputs(), [])

    def test_get_raw_audio_inputs_contains_local_mic(self):
        """local_mic is in raw_audio inputs by default."""
        sm = make_manager()
        ids = {d["id"] for d in sm.get_raw_audio_inputs()}
        self.assertIn("local_mic", ids)

    def test_can_receive_intent_false_with_no_intent_devices(self):
        """can_receive_intent() is False when no intent_input devices exist."""
        sm = make_manager()
        self.assertFalse(sm.can_receive_intent())

    def test_can_receive_intent_true_when_intent_device_enabled(self):
        """can_receive_intent() is True when an enabled intent_input exists."""
        sm = make_manager()
        sm.register_device({
            "id": "alexa_intent",
            "name": "Alexa",
            "device_type": "intent_input",
            "source": "alexa",
            "privacy": "cloud_dependent",
            "enabled": True,
            "entity_id": None,
        })
        self.assertTrue(sm.can_receive_intent())

    def test_can_receive_intent_false_when_disabled(self):
        """can_receive_intent() is False when the intent_input device is disabled."""
        sm = make_manager()
        sm.register_device({
            "id": "alexa_intent",
            "name": "Alexa",
            "device_type": "intent_input",
            "source": "alexa",
            "privacy": "cloud_dependent",
            "enabled": False,
            "entity_id": None,
        })
        self.assertFalse(sm.can_receive_intent())

    def test_can_send_speech_true_by_default(self):
        """can_send_speech() is True by default (local_speaker is registered)."""
        sm = make_manager()
        self.assertTrue(sm.can_send_speech())

    def test_local_mic_is_raw_audio(self):
        """local_mic has device_type 'raw_audio'."""
        sm = make_manager()
        mic = next(d for d in sm.get_devices() if d["id"] == "local_mic")
        self.assertEqual(mic["device_type"], "raw_audio")

    def test_local_speaker_is_speech_output(self):
        """local_speaker has device_type 'speech_output'."""
        sm = make_manager()
        speaker = next(d for d in sm.get_devices() if d["id"] == "local_speaker")
        self.assertEqual(speaker["device_type"], "speech_output")

    def test_local_devices_have_local_privacy(self):
        """Both default local devices have privacy='local'."""
        sm = make_manager()
        local_devices = [d for d in sm.get_devices() if d["source"] == "local"]
        for d in local_devices:
            self.assertEqual(d["privacy"], "local", f"{d['id']} should have local privacy")


if __name__ == '__main__':
    unittest.main()

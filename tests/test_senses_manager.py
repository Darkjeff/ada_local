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


class TestSpeechDispatch(unittest.TestCase):

    def test_send_speech_calls_local_speech_by_default(self):
        """send_speech() with no target uses local_speaker by default."""
        sm = make_manager()
        with patch.object(sm, "_send_local_speech", return_value=True) as mock_local:
            result = sm.send_speech("Hello ADA")
        mock_local.assert_called_once_with("Hello ADA")
        self.assertTrue(result)

    def test_send_speech_explicit_local_speaker_target(self):
        """send_speech(target_id='local_speaker') routes to local TTS."""
        sm = make_manager()
        with patch.object(sm, "_send_local_speech", return_value=True) as mock_local:
            result = sm.send_speech("Test", target_id="local_speaker")
        mock_local.assert_called_once_with("Test")
        self.assertTrue(result)

    def test_send_speech_routes_to_ha_for_ha_source(self):
        """send_speech() calls _send_ha_speech for home_assistant source device."""
        sm = make_manager()
        sm.register_device({
            "id": "ha_living_room",
            "name": "Living Room",
            "device_type": "speech_output",
            "source": "home_assistant",
            "privacy": "local_or_cloud_dependent",
            "enabled": True,
            "entity_id": "media_player.living_room",
        })
        with patch.object(sm, "_send_ha_speech", return_value=True) as mock_ha:
            result = sm.send_speech("Hello", target_id="ha_living_room")
        mock_ha.assert_called_once_with("Hello", "media_player.living_room")
        self.assertTrue(result)

    def test_send_speech_returns_false_for_unknown_target(self):
        """send_speech() returns False when target_id is not in registry."""
        sm = make_manager()
        result = sm.send_speech("Hello", target_id="nonexistent_device")
        self.assertFalse(result)

    def test_send_speech_returns_false_for_disabled_target(self):
        """send_speech() returns False when the target device is disabled."""
        sm = make_manager()
        sm.register_device({
            "id": "disabled_speaker",
            "name": "Off Speaker",
            "device_type": "speech_output",
            "source": "local",
            "privacy": "local",
            "enabled": False,
            "entity_id": None,
        })
        with patch.object(sm, "_send_local_speech") as mock_local:
            result = sm.send_speech("Hello", target_id="disabled_speaker")
        mock_local.assert_not_called()
        self.assertFalse(result)

    def test_send_local_speech_calls_tts_queue_sentence(self):
        """_send_local_speech() calls tts.queue_sentence() and returns True."""
        import sys
        sm = make_manager()
        mock_tts_instance = MagicMock()
        mock_tts_instance.queue_sentence.return_value = None
        mock_tts_module = MagicMock()
        mock_tts_module.tts = mock_tts_instance
        with patch.dict(sys.modules, {"core.tts": mock_tts_module}):
            result = sm._send_local_speech("Hello world")
        mock_tts_instance.queue_sentence.assert_called_once_with("Hello world")
        self.assertTrue(result)

    def test_send_local_speech_returns_false_on_exception(self):
        """_send_local_speech() returns False when tts.queue_sentence() raises."""
        import sys
        sm = make_manager()
        mock_tts_instance = MagicMock()
        mock_tts_instance.queue_sentence.side_effect = RuntimeError("TTS engine not ready")
        mock_tts_module = MagicMock()
        mock_tts_module.tts = mock_tts_instance
        with patch.dict(sys.modules, {"core.tts": mock_tts_module}):
            result = sm._send_local_speech("Hello")
        self.assertFalse(result)

    def test_send_ha_speech_calls_ha_manager(self):
        """_send_ha_speech() calls ha_manager.speak_to_media_player()."""
        sm = make_manager()
        mock_ha = MagicMock()
        mock_ha.speak_to_media_player.return_value = True
        with patch("core.ha_control.ha_manager", mock_ha), \
             patch("core.senses_manager.settings") as mock_settings:
            mock_settings.get.return_value = "tts.piper"
            result = sm._send_ha_speech("Hello HA", "media_player.living_room")
        mock_ha.speak_to_media_player.assert_called_once_with(
            "media_player.living_room", "Hello HA", tts_service="tts.piper"
        )
        self.assertTrue(result)

    def test_send_ha_speech_returns_false_with_no_entity_id(self):
        """_send_ha_speech() returns False when entity_id is None or empty."""
        sm = make_manager()
        self.assertFalse(sm._send_ha_speech("Hello", None))
        self.assertFalse(sm._send_ha_speech("Hello", ""))


class TestIntentRouting(unittest.TestCase):

    def test_receive_external_intent_rejected_with_no_intent_inputs(self):
        """receive_external_intent() rejects any source when no intent_input devices exist."""
        sm = make_manager()
        with patch("core.intent_bridge.intent_bridge") as mock_bridge:
            sm.receive_external_intent("alexa", "Turn on the lights")
        mock_bridge.route_intent.assert_not_called()

    def test_receive_external_intent_rejected_from_unregistered_source(self):
        """receive_external_intent() rejects source not in the registry."""
        sm = make_manager()
        sm.register_device({
            "id": "google_home_input",
            "name": "Google Home",
            "device_type": "intent_input",
            "source": "google_home",
            "privacy": "cloud_dependent",
            "enabled": True,
            "entity_id": None,
        })
        with patch("core.intent_bridge.intent_bridge") as mock_bridge:
            sm.receive_external_intent("alexa", "Set timer for 5 minutes")
        mock_bridge.route_intent.assert_not_called()

    def test_receive_external_intent_routes_registered_source(self):
        """receive_external_intent() routes to intent_bridge for registered source."""
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
        with patch("core.intent_bridge.intent_bridge") as mock_bridge:
            sm.receive_external_intent("alexa", "Turn on the lights")
        mock_bridge.route_intent.assert_called_once_with("Turn on the lights")

    def test_receive_external_intent_rejected_when_device_disabled(self):
        """receive_external_intent() rejects even if source is registered but disabled."""
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
        with patch("core.intent_bridge.intent_bridge") as mock_bridge:
            sm.receive_external_intent("alexa", "Turn on the lights")
        mock_bridge.route_intent.assert_not_called()


if __name__ == '__main__':
    unittest.main()

"""
Tests for HA media player discovery and TTS dispatch in core/ha_control.py.

Run: python -m pytest tests/test_ha_tts.py -v
"""
import sys
import os
import unittest
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))


class TestGetMediaPlayerEntities(unittest.TestCase):

    def _make_manager(self):
        """Create an HAManager without triggering network calls."""
        with patch('core.settings_store.settings') as mock_s:
            mock_s.get.return_value = ""
            from core.ha_control import HAManager
            return HAManager()

    def test_returns_only_media_player_entities(self):
        """get_media_player_entities() filters to only media_player domain."""
        mgr = self._make_manager()
        mgr._raw_entities = {
            "media_player.living_room": {"entity_id": "media_player.living_room", "state": "idle",
                                          "attributes": {"friendly_name": "Living Room"}},
            "light.kitchen": {"entity_id": "light.kitchen", "state": "on",
                               "attributes": {}},
            "media_player.bedroom": {"entity_id": "media_player.bedroom", "state": "playing",
                                      "attributes": {"friendly_name": "Bedroom"}},
        }
        result = mgr.get_media_player_entities()
        self.assertEqual(set(result.keys()), {"media_player.living_room", "media_player.bedroom"})

    def test_returns_empty_when_no_media_players(self):
        """get_media_player_entities() returns {} when no media_player entities exist."""
        mgr = self._make_manager()
        mgr._raw_entities = {
            "light.kitchen": {"entity_id": "light.kitchen", "state": "on", "attributes": {}},
        }
        result = mgr.get_media_player_entities()
        self.assertEqual(result, {})

    def test_returns_empty_when_not_configured(self):
        """get_media_player_entities() returns {} when HA URL/token are empty."""
        mgr = self._make_manager()
        mgr._raw_entities = {}
        mgr._url = ""
        mgr._token = ""
        result = mgr.get_media_player_entities()
        self.assertEqual(result, {})

    def test_reuses_raw_entities_cache(self):
        """get_media_player_entities() uses _raw_entities cache, no HTTP call."""
        mgr = self._make_manager()
        mgr._raw_entities = {
            "media_player.test": {"entity_id": "media_player.test", "state": "idle",
                                   "attributes": {}}
        }
        with patch.object(mgr, '_fetch_all_states') as mock_fetch:
            mgr.get_media_player_entities()
        mock_fetch.assert_not_called()


class TestSpeakToMediaPlayer(unittest.TestCase):

    def _make_configured_manager(self):
        """Create an HAManager with URL and token set."""
        with patch('core.settings_store.settings') as mock_s:
            mock_s.get.return_value = ""
            from core.ha_control import HAManager
            mgr = HAManager()
        mgr._url = "http://homeassistant.local:8123"
        mgr._token = "test_token_abc"
        return mgr

    def test_returns_true_on_success(self):
        """speak_to_media_player() returns True when HA responds 200."""
        mgr = self._make_configured_manager()
        mock_resp = MagicMock(status_code=200)
        with patch("requests.post", return_value=mock_resp):
            result = mgr.speak_to_media_player("media_player.living_room", "Hello ADA")
        self.assertTrue(result)

    def test_posts_to_tts_speak_endpoint(self):
        """speak_to_media_player() POSTs to /api/services/tts/speak."""
        mgr = self._make_configured_manager()
        mock_resp = MagicMock(status_code=200)
        with patch("requests.post", return_value=mock_resp) as mock_post:
            mgr.speak_to_media_player("media_player.living_room", "Hello")
        url = mock_post.call_args[0][0]
        self.assertIn("tts/speak", url)
        self.assertIn("api/services", url)

    def test_payload_contains_message_and_entity(self):
        """POST payload has correct message and media_player_entity_id."""
        mgr = self._make_configured_manager()
        mock_resp = MagicMock(status_code=200)
        with patch("requests.post", return_value=mock_resp) as mock_post:
            mgr.speak_to_media_player("media_player.bedroom", "Test phrase")
        payload = mock_post.call_args[1]["json"]
        self.assertEqual(payload["message"], "Test phrase")
        self.assertEqual(payload["media_player_entity_id"], "media_player.bedroom")

    def test_uses_default_tts_service(self):
        """Default tts_service is tts.piper (entity_id in payload)."""
        mgr = self._make_configured_manager()
        mock_resp = MagicMock(status_code=200)
        with patch("requests.post", return_value=mock_resp) as mock_post:
            mgr.speak_to_media_player("media_player.test", "Hello")
        payload = mock_post.call_args[1]["json"]
        self.assertEqual(payload["entity_id"], "tts.piper")

    def test_uses_custom_tts_service(self):
        """tts_service parameter overrides the default."""
        mgr = self._make_configured_manager()
        mock_resp = MagicMock(status_code=200)
        with patch("requests.post", return_value=mock_resp) as mock_post:
            mgr.speak_to_media_player("media_player.test", "Hello",
                                       tts_service="tts.google_translate")
        payload = mock_post.call_args[1]["json"]
        self.assertEqual(payload["entity_id"], "tts.google_translate")

    def test_returns_false_without_config(self):
        """speak_to_media_player() returns False when URL or token is empty."""
        with patch('core.settings_store.settings') as mock_s:
            mock_s.get.return_value = ""
            from core.ha_control import HAManager
            mgr = HAManager()
        mgr._url = ""
        mgr._token = ""
        result = mgr.speak_to_media_player("media_player.test", "Hello")
        self.assertFalse(result)

    def test_returns_false_on_http_error(self):
        """speak_to_media_player() returns False on non-200 HTTP response."""
        mgr = self._make_configured_manager()
        mock_resp = MagicMock(status_code=500)
        with patch("requests.post", return_value=mock_resp):
            result = mgr.speak_to_media_player("media_player.test", "Hello")
        self.assertFalse(result)

    def test_returns_false_on_network_exception(self):
        """speak_to_media_player() returns False when requests raises."""
        mgr = self._make_configured_manager()
        with patch("requests.post", side_effect=Exception("Connection refused")):
            result = mgr.speak_to_media_player("media_player.test", "Hello")
        self.assertFalse(result)


if __name__ == '__main__':
    unittest.main()

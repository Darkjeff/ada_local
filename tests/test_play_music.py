import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import unittest
from unittest.mock import patch, MagicMock


FAKE_SONGS = [
    {"id": f"{i}", "title": f"Track {i}", "artist": "JazzBand"}
    for i in range(20)
]


class TestPlayMusic(unittest.TestCase):

    def _run(self, params, songs=None, room_players=None,
             default_player="media_player.chillout_area",
             play_ok=True):

        # Mock all heavy imports before importing function_executor
        heavy_mocks = {
            'PySide6': MagicMock(), 'PySide6.QtCore': MagicMock(),
            'RealTimeSTT': MagicMock(), 'sounddevice': MagicMock(),
            'pvporcupine': MagicMock(),
        }
        with patch.dict('sys.modules', heavy_mocks):
            from core.function_executor import FunctionExecutor
            executor = FunctionExecutor()

        if songs is None:
            songs = FAKE_SONGS

        _room_players = room_players if room_players is not None else {"salon": "media_player.chillout_area"}

        def settings_get(key, default=None):
            mapping = {
                "music.room_players": _room_players,
                "music.default_player": default_player,
            }
            return mapping.get(key, default)

        mock_mm = MagicMock()
        mock_mm.get_songs_by_genre.return_value = songs
        mock_mm.get_songs_by_artist.return_value = songs
        mock_mm.build_m3u.return_value = "#EXTM3U\n..."

        mock_srv = MagicMock()
        mock_srv.serve.return_value = "http://192.168.1.70:8765/playlist.m3u"

        mock_ha = MagicMock()
        mock_ha.play_media.return_value = play_ok

        with patch('core.function_executor.settings') as mock_settings, \
             patch('core.music_manager.music_manager', mock_mm), \
             patch('core.playlist_server.playlist_server', mock_srv), \
             patch('core.ha_control.ha_manager', mock_ha):

            mock_settings.get.side_effect = settings_get
            result = executor._play_music(params)

        return result, mock_mm, mock_srv, mock_ha

    def test_genre_search_called(self):
        result, mm, srv, ha = self._run({"genre": "jazz", "room": "salon"})
        mm.get_songs_by_genre.assert_called_once_with("jazz", count=15)

    def test_artist_search_called(self):
        result, mm, srv, ha = self._run({"artist": "Miles Davis", "room": "salon"})
        mm.get_songs_by_artist.assert_called_once_with("Miles Davis", count=15)

    def test_playlist_served(self):
        result, mm, srv, ha = self._run({"genre": "jazz", "room": "salon"})
        srv.serve.assert_called_once()
        m3u_arg = srv.serve.call_args[0][0]
        self.assertIn("#EXTM3U", m3u_arg)

    def test_ha_play_media_called_with_entity_and_url(self):
        result, mm, srv, ha = self._run({"genre": "jazz", "room": "salon"})
        ha.play_media.assert_called_once_with(
            "media_player.chillout_area",
            "http://192.168.1.70:8765/playlist.m3u"
        )

    def test_unknown_room_falls_back_to_default_player(self):
        result, mm, srv, ha = self._run(
            {"genre": "jazz", "room": "cuisine"},
            room_players={"salon": "media_player.chillout_area"},
            default_player="media_player.chillout_area"
        )
        ha.play_media.assert_called_once()
        entity = ha.play_media.call_args[0][0]
        self.assertEqual(entity, "media_player.chillout_area")

    def test_success_message_contains_track_count(self):
        result, mm, srv, ha = self._run({"genre": "jazz", "room": "salon"})
        self.assertTrue(result["success"])
        self.assertIn("15", result["message"])

    def test_no_genre_or_artist_returns_error(self):
        result, mm, srv, ha = self._run({"room": "salon"})
        self.assertFalse(result["success"])
        self.assertIn("genre", result["message"].lower())

    def test_no_songs_found_returns_error(self):
        result, mm, srv, ha = self._run({"genre": "klezmer"}, songs=[])
        self.assertFalse(result["success"])

    def test_no_player_configured_returns_error(self):
        result, mm, srv, ha = self._run(
            {"genre": "jazz", "room": "salon"},
            room_players={},
            default_player=""
        )
        self.assertFalse(result["success"])
        self.assertIn("lecteur", result["message"].lower())

    def test_ha_play_media_failure_returns_error(self):
        result, mm, srv, ha = self._run(
            {"genre": "jazz", "room": "salon"},
            play_ok=False
        )
        self.assertFalse(result["success"])
        self.assertIn("Impossible de lancer", result["message"])

    def test_custom_count_parameter(self):
        result, mm, srv, ha = self._run(
            {"genre": "jazz", "room": "salon", "count": "8"}
        )
        mm.get_songs_by_genre.assert_called_once_with("jazz", count=8)


if __name__ == "__main__":
    unittest.main()

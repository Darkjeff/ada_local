import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import unittest
from unittest.mock import patch, MagicMock


class TestBuildM3u(unittest.TestCase):

    def _make_manager(self):
        # Import avec settings mockées pour éviter de charger PySide6
        with patch.dict('sys.modules', {
            'PySide6': MagicMock(), 'PySide6.QtCore': MagicMock(),
        }):
            from core.music_manager import MusicManager
            m = MusicManager()
            m._base_url = lambda: "http://192.168.1.70:4533"
            m._auth = lambda: {"u": "admin", "p": "secret", "v": "1.16.1", "c": "ada", "f": "json"}
            return m

    def test_build_m3u_header(self):
        m = self._make_manager()
        songs = [{"id": "1", "title": "Blue Rondo", "artist": "Dave Brubeck"}]
        result = m.build_m3u(songs)
        self.assertTrue(result.startswith("#EXTM3U"))

    def test_build_m3u_extinf_and_url(self):
        m = self._make_manager()
        songs = [{"id": "42", "title": "Take Five", "artist": "Dave Brubeck"}]
        result = m.build_m3u(songs)
        lines = result.splitlines()
        self.assertIn("#EXTINF:-1,Dave Brubeck - Take Five", lines)
        stream_line = [l for l in lines if "/rest/stream" in l][0]
        self.assertIn("id=42", stream_line)
        self.assertIn("format=mp3", stream_line)

    def test_build_m3u_multiple_songs(self):
        m = self._make_manager()
        songs = [
            {"id": "1", "title": "A", "artist": "X"},
            {"id": "2", "title": "B", "artist": "Y"},
        ]
        result = m.build_m3u(songs)
        self.assertEqual(result.count("#EXTINF"), 2)
        self.assertEqual(result.count("/rest/stream"), 2)

    def test_build_m3u_missing_artist_field(self):
        m = self._make_manager()
        songs = [{"id": "5", "title": "Unknown Track"}]
        result = m.build_m3u(songs)
        self.assertIn("#EXTINF:-1, - Unknown Track", result)


if __name__ == "__main__":
    unittest.main()

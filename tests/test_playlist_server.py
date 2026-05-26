import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import time
import unittest
import urllib.request
from unittest.mock import patch, MagicMock


def _import_server():
    with patch.dict('sys.modules', {
        'PySide6': MagicMock(), 'PySide6.QtCore': MagicMock(),
    }):
        import importlib
        import core.playlist_server as ps_mod
        importlib.reload(ps_mod)
        return ps_mod.PlaylistServer


class TestPlaylistServer(unittest.TestCase):
    PORT = 19765  # Port de test pour éviter les conflits
    HOST = "127.0.0.1"

    def _make_server(self):
        PlaylistServer = _import_server()
        return PlaylistServer()

    def test_serve_returns_correct_url(self):
        srv = self._make_server()
        url = srv.serve("#EXTM3U\n", ttl=5, host=self.HOST, port=self.PORT)
        srv.stop()
        self.assertEqual(url, f"http://{self.HOST}:{self.PORT}/playlist.m3u")

    def test_serve_responds_with_m3u_content(self):
        content = "#EXTM3U\n#EXTINF:-1,Test\nhttp://example.com/song.mp3"
        srv = self._make_server()
        srv.serve(content, ttl=5, host=self.HOST, port=self.PORT)
        time.sleep(0.1)  # laisser le thread démarrer
        try:
            resp = urllib.request.urlopen(
                f"http://{self.HOST}:{self.PORT}/playlist.m3u", timeout=3
            )
            body = resp.read().decode("utf-8")
            self.assertEqual(body, content)
            ct = resp.headers.get("Content-Type", "")
            self.assertIn("mpegurl", ct)
        finally:
            srv.stop()

    def test_serve_404_for_other_paths(self):
        srv = self._make_server()
        srv.serve("#EXTM3U\n", ttl=5, host=self.HOST, port=self.PORT)
        time.sleep(0.1)
        try:
            with self.assertRaises(urllib.error.HTTPError) as ctx:
                urllib.request.urlopen(
                    f"http://{self.HOST}:{self.PORT}/other", timeout=3
                )
            self.assertEqual(ctx.exception.code, 404)
        finally:
            srv.stop()

    def test_stop_shuts_down_server(self):
        srv = self._make_server()
        srv.serve("#EXTM3U\n", ttl=30, host=self.HOST, port=self.PORT)
        time.sleep(0.1)
        srv.stop()
        time.sleep(0.5)
        with self.assertRaises(Exception):
            urllib.request.urlopen(
                f"http://{self.HOST}:{self.PORT}/playlist.m3u", timeout=1
            )


if __name__ == "__main__":
    unittest.main()

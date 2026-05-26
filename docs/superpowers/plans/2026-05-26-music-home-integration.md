# Music + Home Integration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Permettre à ADA de jouer une vraie playlist Navidrome (15 titres) sur le Denon AVR via Home Assistant, depuis une commande naturelle comme "Lance du jazz dans le salon".

**Architecture:** `function_executor._play_music()` est refactoré pour : (1) chercher N chansons par genre/artiste, (2) générer un fichier M3U servi par un thread HTTP local, (3) résoudre la pièce en entity_id HA via un dict de config, (4) appeler `ha_manager.play_media()` avec l'URL M3U. `ha_manager.play_media()` existe déjà et est correct.

**Tech Stack:** Python stdlib `http.server`, `unittest.mock`, pytest, `core.settings_store` (dot-notation), PySide6 absent des tests (sys.path trick).

---

## File Map

| Action | Fichier | Responsabilité |
|---|---|---|
| Modify | `core/music_manager.py` | Ajouter `build_m3u(songs)` |
| Create | `core/playlist_server.py` | Thread HTTP servant `/playlist.m3u` |
| Modify | `core/settings_store.py` | Ajouter section `music` dans `DEFAULT_SETTINGS` |
| Modify | `core/function_executor.py` | Refactorer `_play_music()`, ajouter `import random` |
| Create | `tests/test_music_manager_m3u.py` | Tests de `build_m3u()` |
| Create | `tests/test_playlist_server.py` | Tests du serveur HTTP |
| Create | `tests/test_play_music.py` | Tests de `_play_music()` avec mocks |

---

### Task 1: Ajouter `build_m3u()` à MusicManager

**Files:**
- Modify: `core/music_manager.py`
- Create: `tests/test_music_manager_m3u.py`

- [ ] **Step 1 : Écrire le test**

Crée `tests/test_music_manager_m3u.py` :

```python
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
```

- [ ] **Step 2 : Lancer le test pour vérifier qu'il échoue**

```bash
cd /home/darkjeff/ada_local
.venv/bin/python -m pytest tests/test_music_manager_m3u.py -v
```

Résultat attendu : `AttributeError: 'MusicManager' object has no attribute 'build_m3u'`

- [ ] **Step 3 : Implémenter `build_m3u()` dans `core/music_manager.py`**

Ajouter la méthode dans la classe `MusicManager`, après `build_stream_url` (ligne ~64) :

```python
def build_m3u(self, songs: list[dict]) -> str:
    """Return an M3U playlist string for the given songs list."""
    lines = ["#EXTM3U"]
    for s in songs:
        title  = s.get("title", "Unknown")
        artist = s.get("artist", "")
        lines.append(f"#EXTINF:-1,{artist} - {title}")
        lines.append(self.build_stream_url(s["id"]))
    return "\n".join(lines)
```

- [ ] **Step 4 : Lancer le test**

```bash
.venv/bin/python -m pytest tests/test_music_manager_m3u.py -v
```

Résultat attendu : `4 passed`

- [ ] **Step 5 : Commit**

```bash
git add core/music_manager.py tests/test_music_manager_m3u.py
git commit -m "feat(music): add build_m3u() to MusicManager"
```

---

### Task 2 : Créer `core/playlist_server.py`

**Files:**
- Create: `core/playlist_server.py`
- Create: `tests/test_playlist_server.py`

- [ ] **Step 1 : Écrire le test**

Crée `tests/test_playlist_server.py` :

```python
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
        time.sleep(0.2)
        with self.assertRaises(Exception):
            urllib.request.urlopen(
                f"http://{self.HOST}:{self.PORT}/playlist.m3u", timeout=1
            )


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2 : Lancer le test pour vérifier qu'il échoue**

```bash
.venv/bin/python -m pytest tests/test_playlist_server.py -v
```

Résultat attendu : `ModuleNotFoundError: No module named 'core.playlist_server'`

- [ ] **Step 3 : Créer `core/playlist_server.py`**

```python
"""Minimal HTTP server that serves a single M3U playlist file."""

import threading
import time
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Optional


class _M3UHandler(BaseHTTPRequestHandler):
    _content: bytes = b""

    def do_GET(self):
        if self.path == "/playlist.m3u":
            data = self.__class__._content
            self.send_response(200)
            self.send_header("Content-Type", "audio/x-mpegurl")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)
        else:
            self.send_response(404)
            self.end_headers()

    def log_message(self, format, *args):
        pass  # suppress request logs


class PlaylistServer:
    """Serves one M3U file over HTTP for a configurable TTL, then stops."""

    def __init__(self):
        self._server: Optional[HTTPServer] = None
        self._lock = threading.Lock()

    def serve(self, m3u_content: str, ttl: int = 300,
              host: str = None, port: int = None) -> str:
        if host is None or port is None:
            from core.settings_store import settings
            host = host or settings.get("music.playlist_server_host", "192.168.1.70")
            port = port or int(settings.get("music.playlist_server_port", 8765))

        with self._lock:
            if self._server is not None:
                self._server.server_close()
                self._server = None

            _M3UHandler._content = m3u_content.encode("utf-8")
            server = HTTPServer(("0.0.0.0", port), _M3UHandler)
            server.timeout = 1.0
            self._server = server

        deadline = time.time() + ttl
        t = threading.Thread(target=self._run, args=(server, deadline), daemon=True)
        t.start()

        return f"http://{host}:{port}/playlist.m3u"

    def _run(self, server: HTTPServer, deadline: float):
        while time.time() < deadline:
            server.handle_request()
        server.server_close()
        with self._lock:
            if self._server is server:
                self._server = None

    def stop(self):
        with self._lock:
            if self._server:
                self._server.server_close()
                self._server = None


playlist_server = PlaylistServer()
```

- [ ] **Step 4 : Lancer le test**

```bash
.venv/bin/python -m pytest tests/test_playlist_server.py -v
```

Résultat attendu : `4 passed`

- [ ] **Step 5 : Commit**

```bash
git add core/playlist_server.py tests/test_playlist_server.py
git commit -m "feat(music): add PlaylistServer for M3U HTTP delivery"
```

---

### Task 3 : Ajouter la section `music` dans `DEFAULT_SETTINGS`

**Files:**
- Modify: `core/settings_store.py`

Pas de test unitaire séparé — le deep_merge existant est déjà testé implicitement.

- [ ] **Step 1 : Ajouter la section dans `DEFAULT_SETTINGS`**

Dans `core/settings_store.py`, dans le dict `DEFAULT_SETTINGS`, après le bloc `"navidrome"` (qui se termine par `},`) et avant le bloc `"calibre"`, ajouter :

```python
    "music": {
        "default_player": "",
        "room_players": {},
        "playlist_server_host": "192.168.1.70",
        "playlist_server_port": 8765,
    },
```

- [ ] **Step 2 : Vérifier manuellement**

```bash
.venv/bin/python -c "
import sys, unittest.mock as m
with m.patch.dict('sys.modules', {'PySide6': m.MagicMock(), 'PySide6.QtCore': m.MagicMock()}):
    from core.settings_store import DEFAULT_SETTINGS
    assert 'music' in DEFAULT_SETTINGS
    assert DEFAULT_SETTINGS['music']['playlist_server_port'] == 8765
    print('OK')
"
```

Résultat attendu : `OK`

- [ ] **Step 3 : Commit**

```bash
git add core/settings_store.py
git commit -m "feat(music): add music section to DEFAULT_SETTINGS"
```

---

### Task 4 : Refactorer `_play_music()` dans `function_executor.py`

**Files:**
- Modify: `core/function_executor.py`
- Create: `tests/test_play_music.py`

- [ ] **Step 1 : Écrire le test**

Crée `tests/test_play_music.py` :

```python
import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import unittest
from unittest.mock import patch, MagicMock


def _make_executor():
    mocks = {
        'PySide6': MagicMock(), 'PySide6.QtCore': MagicMock(),
        'RealTimeSTT': MagicMock(), 'sounddevice': MagicMock(),
        'pvporcupine': MagicMock(),
    }
    with patch.dict('sys.modules', mocks):
        import importlib
        import core.function_executor as fe_mod
        importlib.reload(fe_mod)
        return fe_mod.FunctionExecutor()


FAKE_SONGS = [
    {"id": f"{i}", "title": f"Track {i}", "artist": "JazzBand"}
    for i in range(20)
]


class TestPlayMusic(unittest.TestCase):

    def _run(self, params, songs=None, room_players=None,
             default_player="media_player.chillout_area",
             play_ok=True):
        executor = _make_executor()

        if songs is None:
            songs = FAKE_SONGS

        with patch("core.function_executor.settings") as mock_settings, \
             patch("core.music_manager.music_manager") as mock_mm, \
             patch("core.playlist_server.playlist_server") as mock_srv, \
             patch("core.ha_control.ha_manager") as mock_ha:

            mock_settings.get.side_effect = lambda key, default=None: {
                "music.room_players": room_players or {"salon": "media_player.chillout_area"},
                "music.default_player": default_player,
            }.get(key, default)

            mock_mm.get_songs_by_genre.return_value = songs
            mock_mm.get_songs_by_artist.return_value = songs
            mock_mm.build_m3u.return_value = "#EXTM3U\n..."
            mock_srv.serve.return_value = "http://192.168.1.70:8765/playlist.m3u"
            mock_ha.play_media.return_value = play_ok

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
        args = srv.serve.call_args[0]
        self.assertIn("#EXTM3U", args[0])

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


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2 : Lancer le test pour vérifier qu'il échoue**

```bash
.venv/bin/python -m pytest tests/test_play_music.py -v
```

Résultat attendu : plusieurs `FAILED` — la logique actuelle ne passe pas ces assertions (pas de room, pas de M3U, songs[0] seulement).

- [ ] **Step 3 : Modifier `core/function_executor.py`**

**3a.** Vérifier que `import random` est présent en tête de fichier. S'il est absent, l'ajouter avec les autres imports stdlib (vers la ligne 5-10).

**3b.** Remplacer entièrement la méthode `_play_music` (lignes 811–845) par :

```python
def _play_music(self, params: dict) -> dict:
    from core.music_manager import music_manager
    from core.ha_control import ha_manager
    from core.playlist_server import playlist_server

    genre  = params.get("genre", "").strip()
    artist = params.get("artist", "").strip()
    room   = params.get("room", "").strip()
    count  = int(params.get("count", 15))

    room_map  = settings.get("music.room_players", {})
    entity_id = room_map.get(room.lower()) or settings.get("music.default_player", "")
    if not entity_id:
        return {
            "success": False,
            "message": "Aucun lecteur configuré. Ajoute un lecteur dans les paramètres musique.",
            "data": None,
        }

    if genre:
        songs = music_manager.get_songs_by_genre(genre, count=count)
    elif artist:
        songs = music_manager.get_songs_by_artist(artist, count=count)
    else:
        return {"success": False, "message": "Précise un genre ou un artiste.", "data": None}

    if not songs:
        label = genre or artist
        return {"success": False, "message": f"Aucun morceau trouvé pour '{label}'.", "data": None}

    random.shuffle(songs)
    playlist = songs[:count]
    m3u = music_manager.build_m3u(playlist)
    url = playlist_server.serve(m3u)
    ok  = ha_manager.play_media(entity_id, url)

    label = room or entity_id
    if ok:
        return {
            "success": True,
            "message": f"Je lance {'du ' + genre if genre else artist} dans {label} — {len(playlist)} titres en queue.",
            "data": {"entity_id": entity_id, "track_count": len(playlist)},
        }
    return {"success": False, "message": "Impossible de lancer la lecture sur le lecteur.", "data": None}
```

- [ ] **Step 4 : Lancer le test**

```bash
.venv/bin/python -m pytest tests/test_play_music.py -v
```

Résultat attendu : `9 passed`

- [ ] **Step 5 : Lancer la suite de tests complète**

```bash
.venv/bin/python -m pytest tests/ -v
```

Résultat attendu : tous les tests existants passent toujours.

- [ ] **Step 6 : Commit**

```bash
git add core/function_executor.py tests/test_play_music.py
git commit -m "feat(music): playlist M3U + room resolver in _play_music"
```

---

### Task 5 : Test manuel end-to-end

- [ ] **Step 1 : Configurer les settings**

Dans `~/.pocket_ai/settings.json`, vérifier/ajouter :

```json
"music": {
    "default_player": "media_player.chillout_area",
    "room_players": {
        "salon": "media_player.chillout_area",
        "chillout": "media_player.chillout_area"
    },
    "playlist_server_host": "192.168.1.70",
    "playlist_server_port": 8765
}
```

- [ ] **Step 2 : Démarrer ADA et taper dans le chat**

```
Lance du jazz dans le salon
```

Vérifier :
- ADA répond "Je lance du jazz dans le salon — 15 titres en queue"
- Le Denon démarre la lecture et joue plusieurs titres à la suite
- `netstat -tlnp | grep 8765` montre le port ouvert

- [ ] **Step 3 : Tester le fallback pièce inconnue**

```
Lance de la musique classique dans la cuisine
```

Vérifier : ADA lance quand même sur `media_player.chillout_area` (default_player).

- [ ] **Step 4 : Tester artiste**

```
Lance de la musique de Miles Davis
```

Vérifier : lecture démarre sur le Denon.

- [ ] **Step 5 : Vérifier arrêt du serveur après 5 min**

```bash
# Attendre 5 min puis :
netstat -tlnp | grep 8765
# Résultat attendu : aucune ligne (port libéré)
```

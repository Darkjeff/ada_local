# Music Control Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Enable ADA to search and play music from Navidrome on a configured HA media_player (Yamaha RX-V4A via MusicCast), and control playback (pause, stop, next, volume) via voice and Telegram.

**Architecture:** New `core/music_manager.py` wraps the Navidrome Subsonic REST API for genre/artist search and stream URL generation. `core/ha_control.py` gains 7 new media_player service methods. Three new LLM tools (`play_music`, `control_media`, `set_volume`) are wired into `config.py` and `core/function_executor.py`, and music utterances are added to the semantic router.

**Tech Stack:** Python `requests`, Navidrome Subsonic API v1.16.1, Home Assistant REST API, PySide6/qfluentwidgets for settings UI.

---

## Context for the implementer

This is the ADA project — a local AI assistant running on Ubuntu (192.168.1.70), built with Python + PySide6 + Ollama. The codebase uses:
- `core/settings_store.py` singleton `settings` for all config reads/writes
- `core/ha_control.py` singleton `ha_manager` with a `call_service(domain, service, entity_id, **kwargs) -> bool` method that POSTs to HA REST API
- `core/function_executor.py` `FunctionExecutor` class with an `execute(func_name, params) -> dict` method that routes to private handlers; all handlers return `{"success": bool, "message": str, "data": Any}`
- `config.py` `FUNCTIONS` list of Ollama-format tool definitions (each is `{"type": "function", "function": {"name": ..., "description": ..., "parameters": {...}}}`)
- Navidrome already configured in settings: keys `navidrome.url`, `navidrome.username`, `navidrome.password`
- Tests use `pytest` and `unittest.mock`; run with `uv run pytest tests/ -v`

---

## Task 1: `core/music_manager.py` — Navidrome Subsonic client

**Files:**
- Create: `core/music_manager.py`
- Create: `tests/test_music_manager.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_music_manager.py`:

```python
from unittest.mock import patch, MagicMock
from core.music_manager import MusicManager


def _make_manager():
    return MusicManager()


def _mock_ok(data: dict):
    r = MagicMock()
    r.raise_for_status = MagicMock()
    r.json.return_value = {"subsonic-response": {"status": "ok", **data}}
    return r


def _settings_side_effect(k, d=""):
    return {
        "navidrome.url": "http://localhost:4533",
        "navidrome.username": "jeff",
        "navidrome.password": "pass",
    }.get(k, d)


def test_get_songs_by_genre_returns_songs():
    mgr = _make_manager()
    songs = [{"id": "1", "title": "Blue in Green", "artist": "Miles Davis"}]
    with patch("core.music_manager.requests.get", return_value=_mock_ok({"songsByGenre": {"song": songs}})):
        with patch("core.music_manager.settings") as s:
            s.get.side_effect = _settings_side_effect
            result = mgr.get_songs_by_genre("jazz")
    assert len(result) == 1
    assert result[0]["title"] == "Blue in Green"


def test_get_songs_by_genre_empty_genre():
    mgr = _make_manager()
    with patch("core.music_manager.requests.get", return_value=_mock_ok({"songsByGenre": {}})):
        with patch("core.music_manager.settings") as s:
            s.get.side_effect = _settings_side_effect
            result = mgr.get_songs_by_genre("unknowngenre999")
    assert result == []


def test_get_songs_by_genre_no_url():
    mgr = _make_manager()
    with patch("core.music_manager.settings") as s:
        s.get.return_value = ""
        result = mgr.get_songs_by_genre("jazz")
    assert result == []


def test_get_songs_by_artist_returns_songs():
    mgr = _make_manager()
    songs = [{"id": "2", "title": "Voodoo Lady", "artist": "Ween"}]
    with patch("core.music_manager.requests.get", return_value=_mock_ok({"searchResult3": {"song": songs}})):
        with patch("core.music_manager.settings") as s:
            s.get.side_effect = _settings_side_effect
            result = mgr.get_songs_by_artist("ween")
    assert len(result) == 1
    assert result[0]["artist"] == "Ween"


def test_get_songs_by_artist_no_match():
    mgr = _make_manager()
    with patch("core.music_manager.requests.get", return_value=_mock_ok({"searchResult3": {}})):
        with patch("core.music_manager.settings") as s:
            s.get.side_effect = _settings_side_effect
            result = mgr.get_songs_by_artist("unknownartist999")
    assert result == []


def test_build_stream_url_contains_id_and_format():
    mgr = _make_manager()
    with patch("core.music_manager.settings") as s:
        s.get.side_effect = _settings_side_effect
        url = mgr.build_stream_url("song123")
    assert "stream" in url
    assert "song123" in url
    assert "mp3" in url
    assert "localhost:4533" in url


def test_get_returns_none_on_http_error():
    mgr = _make_manager()
    with patch("core.music_manager.requests.get", side_effect=Exception("timeout")):
        with patch("core.music_manager.settings") as s:
            s.get.side_effect = _settings_side_effect
            result = mgr.get_songs_by_genre("jazz")
    assert result == []
```

- [ ] **Step 2: Run tests to verify they fail**

```
uv run pytest tests/test_music_manager.py -v
```
Expected: `ModuleNotFoundError: No module named 'core.music_manager'`

- [ ] **Step 3: Create `core/music_manager.py`**

```python
"""Navidrome Subsonic API client — genre/artist search and stream URL generation."""

import requests
from typing import Optional

from core.settings_store import settings


class MusicManager:

    def _base_url(self) -> str:
        return settings.get("navidrome.url", "").rstrip("/")

    def _auth(self) -> dict:
        return {
            "u": settings.get("navidrome.username", ""),
            "p": settings.get("navidrome.password", ""),
            "v": "1.16.1",
            "c": "ada",
            "f": "json",
        }

    def _get(self, endpoint: str, **params) -> Optional[dict]:
        base = self._base_url()
        if not base:
            return None
        try:
            r = requests.get(
                f"{base}/rest/{endpoint}",
                params={**self._auth(), **params},
                timeout=10,
            )
            r.raise_for_status()
            data = r.json().get("subsonic-response", {})
            return data if data.get("status") == "ok" else None
        except Exception as e:
            print(f"[MusicManager] {endpoint} failed: {e}")
            return None

    def get_songs_by_genre(self, genre: str, count: int = 20) -> list[dict]:
        """Return up to `count` songs matching `genre`. Returns [] on error or no match."""
        data = self._get("getSongsByGenre", genre=genre, count=count)
        if not data:
            return []
        return data.get("songsByGenre", {}).get("song", []) or []

    def get_songs_by_artist(self, artist: str, count: int = 20) -> list[dict]:
        """Return up to `count` songs by best-matching artist. Returns [] on error or no match."""
        data = self._get("search3", query=artist, artistCount=1, albumCount=0, songCount=count)
        if not data:
            return []
        return data.get("searchResult3", {}).get("song", []) or []

    def build_stream_url(self, song_id: str) -> str:
        """Return a direct HTTP stream URL for `song_id` (includes auth params, format=mp3)."""
        base = self._base_url()
        auth = self._auth()
        qs = "&".join(f"{k}={v}" for k, v in auth.items())
        return f"{base}/rest/stream?id={song_id}&{qs}&format=mp3"


music_manager = MusicManager()
```

- [ ] **Step 4: Run tests to verify they pass**

```
uv run pytest tests/test_music_manager.py -v
```
Expected: `7 passed`

- [ ] **Step 5: Commit**

```bash
git add core/music_manager.py tests/test_music_manager.py
git commit -m "feat(music): add MusicManager Subsonic client"
```

---

## Task 2: `core/ha_control.py` — 7 new media_player methods

**Files:**
- Modify: `core/ha_control.py` (add methods after `turn_off`)
- Create: `tests/test_ha_music_control.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_ha_music_control.py`:

```python
from unittest.mock import patch, MagicMock
from core.ha_control import HAManager


def _make_manager():
    m = HAManager.__new__(HAManager)
    m._url = "http://ha.local:8123"
    m._token = "tok"
    return m


def test_play_media_calls_service_with_url():
    mgr = _make_manager()
    with patch.object(mgr, "call_service", return_value=True) as mock_cs:
        result = mgr.play_media("media_player.chillout_area", "http://stream/song.mp3")
    assert result is True
    mock_cs.assert_called_once_with(
        "media_player", "play_media", "media_player.chillout_area",
        media_content_id="http://stream/song.mp3",
        media_content_type="music",
    )


def test_play_media_not_configured():
    mgr = _make_manager()
    mgr._url = ""
    result = mgr.play_media("media_player.chillout_area", "http://stream/song.mp3")
    assert result is False


def test_media_pause():
    mgr = _make_manager()
    with patch.object(mgr, "call_service", return_value=True) as mock_cs:
        result = mgr.media_pause("media_player.chillout_area")
    assert result is True
    mock_cs.assert_called_once_with("media_player", "media_pause", "media_player.chillout_area")


def test_media_stop():
    mgr = _make_manager()
    with patch.object(mgr, "call_service", return_value=True) as mock_cs:
        result = mgr.media_stop("media_player.chillout_area")
    assert result is True
    mock_cs.assert_called_once_with("media_player", "media_stop", "media_player.chillout_area")


def test_media_next_track():
    mgr = _make_manager()
    with patch.object(mgr, "call_service", return_value=True) as mock_cs:
        result = mgr.media_next_track("media_player.chillout_area")
    assert result is True
    mock_cs.assert_called_once_with("media_player", "media_next_track", "media_player.chillout_area")


def test_volume_set():
    mgr = _make_manager()
    with patch.object(mgr, "call_service", return_value=True) as mock_cs:
        result = mgr.volume_set("media_player.chillout_area", 0.5)
    assert result is True
    mock_cs.assert_called_once_with(
        "media_player", "volume_set", "media_player.chillout_area", volume_level=0.5
    )


def test_volume_up():
    mgr = _make_manager()
    with patch.object(mgr, "call_service", return_value=True) as mock_cs:
        result = mgr.volume_up("media_player.chillout_area")
    assert result is True
    mock_cs.assert_called_once_with("media_player", "volume_up", "media_player.chillout_area")


def test_volume_down():
    mgr = _make_manager()
    with patch.object(mgr, "call_service", return_value=True) as mock_cs:
        result = mgr.volume_down("media_player.chillout_area")
    assert result is True
    mock_cs.assert_called_once_with("media_player", "volume_down", "media_player.chillout_area")
```

- [ ] **Step 2: Run tests to verify they fail**

```
uv run pytest tests/test_ha_music_control.py -v
```
Expected: `AttributeError: 'HAManager' object has no attribute 'play_media'`

- [ ] **Step 3: Add 7 methods to `core/ha_control.py`**

Add the following methods to `HAManager`, after the existing `turn_off` method:

```python
def play_media(self, entity_id: str, url: str, media_type: str = "music") -> bool:
    """POST /api/services/media_player/play_media — stream `url` on `entity_id`."""
    if not self._url or not self._token:
        return False
    return self.call_service(
        "media_player", "play_media", entity_id,
        media_content_id=url,
        media_content_type=media_type,
    )

def media_pause(self, entity_id: str) -> bool:
    """POST /api/services/media_player/media_pause."""
    if not self._url or not self._token:
        return False
    return self.call_service("media_player", "media_pause", entity_id)

def media_stop(self, entity_id: str) -> bool:
    """POST /api/services/media_player/media_stop."""
    if not self._url or not self._token:
        return False
    return self.call_service("media_player", "media_stop", entity_id)

def media_next_track(self, entity_id: str) -> bool:
    """POST /api/services/media_player/media_next_track."""
    if not self._url or not self._token:
        return False
    return self.call_service("media_player", "media_next_track", entity_id)

def volume_set(self, entity_id: str, level: float) -> bool:
    """POST /api/services/media_player/volume_set — `level` is 0.0 to 1.0."""
    if not self._url or not self._token:
        return False
    return self.call_service("media_player", "volume_set", entity_id, volume_level=level)

def volume_up(self, entity_id: str) -> bool:
    """POST /api/services/media_player/volume_up."""
    if not self._url or not self._token:
        return False
    return self.call_service("media_player", "volume_up", entity_id)

def volume_down(self, entity_id: str) -> bool:
    """POST /api/services/media_player/volume_down."""
    if not self._url or not self._token:
        return False
    return self.call_service("media_player", "volume_down", entity_id)
```

- [ ] **Step 4: Run tests to verify they pass**

```
uv run pytest tests/test_ha_music_control.py -v
```
Expected: `8 passed`

- [ ] **Step 5: Commit**

```bash
git add core/ha_control.py tests/test_ha_music_control.py
git commit -m "feat(music): add media_player control methods to HAManager"
```

---

## Task 3: `config.py` + `core/function_executor.py` — 3 new LLM tools

**Files:**
- Modify: `config.py` (add 3 entries to `FUNCTIONS` list)
- Modify: `core/function_executor.py` (add 3 handler methods + route in `execute()`)
- Create: `tests/test_music_executor.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_music_executor.py`:

```python
from unittest.mock import patch, MagicMock
from core.function_executor import FunctionExecutor


def _make_executor():
    return FunctionExecutor()


def test_play_music_by_genre_success():
    ex = _make_executor()
    songs = [{"id": "s1", "title": "So What", "artist": "Miles Davis"}]
    with patch("core.function_executor.settings") as s:
        s.get.side_effect = lambda k, d="": {
            "music.default_player": "media_player.chillout_area"
        }.get(k, d)
        with patch("core.music_manager.music_manager") as mm:
            mm.get_songs_by_genre.return_value = songs
            mm.build_stream_url.return_value = "http://stream/s1.mp3"
            with patch("core.ha_control.ha_manager") as ha:
                ha.play_media.return_value = True
                result = ex.execute("play_music", {"genre": "jazz"})
    assert result["success"] is True
    assert "So What" in result["message"]


def test_play_music_no_songs_found():
    ex = _make_executor()
    with patch("core.function_executor.settings") as s:
        s.get.side_effect = lambda k, d="": {
            "music.default_player": "media_player.chillout_area"
        }.get(k, d)
        with patch("core.music_manager.music_manager") as mm:
            mm.get_songs_by_genre.return_value = []
            result = ex.execute("play_music", {"genre": "unknowngenre999"})
    assert result["success"] is False
    assert "Aucun morceau" in result["message"]


def test_play_music_no_player_configured():
    ex = _make_executor()
    with patch("core.function_executor.settings") as s:
        s.get.return_value = ""
        result = ex.execute("play_music", {"genre": "jazz"})
    assert result["success"] is False
    assert "lecteur" in result["message"].lower()


def test_control_media_pause():
    ex = _make_executor()
    with patch("core.function_executor.settings") as s:
        s.get.return_value = "media_player.chillout_area"
        with patch("core.ha_control.ha_manager") as ha:
            ha.media_pause.return_value = True
            result = ex.execute("control_media", {"action": "pause"})
    assert result["success"] is True
    assert "pause" in result["message"].lower()


def test_control_media_stop():
    ex = _make_executor()
    with patch("core.function_executor.settings") as s:
        s.get.return_value = "media_player.chillout_area"
        with patch("core.ha_control.ha_manager") as ha:
            ha.media_stop.return_value = True
            result = ex.execute("control_media", {"action": "stop"})
    assert result["success"] is True


def test_control_media_next():
    ex = _make_executor()
    with patch("core.function_executor.settings") as s:
        s.get.return_value = "media_player.chillout_area"
        with patch("core.ha_control.ha_manager") as ha:
            ha.media_next_track.return_value = True
            result = ex.execute("control_media", {"action": "next"})
    assert result["success"] is True


def test_set_volume_up():
    ex = _make_executor()
    with patch("core.function_executor.settings") as s:
        s.get.return_value = "media_player.chillout_area"
        with patch("core.ha_control.ha_manager") as ha:
            ha.volume_up.return_value = True
            result = ex.execute("set_volume", {"action": "up"})
    assert result["success"] is True


def test_set_volume_set():
    ex = _make_executor()
    with patch("core.function_executor.settings") as s:
        s.get.return_value = "media_player.chillout_area"
        with patch("core.ha_control.ha_manager") as ha:
            ha.volume_set.return_value = True
            result = ex.execute("set_volume", {"action": "set", "level": 60})
    assert result["success"] is True
    assert "60" in result["message"]
```

- [ ] **Step 2: Run tests to verify they fail**

```
uv run pytest tests/test_music_executor.py -v
```
Expected: tests fail because `play_music`, `control_media`, `set_volume` are not handled in `execute()`.

- [ ] **Step 3: Add 3 tool definitions to `config.py` FUNCTIONS list**

Append these 3 entries inside the `FUNCTIONS` list in `config.py` (before the closing `]`):

```python
    {
        "type": "function",
        "function": {
            "name": "play_music",
            "description": "Play music by genre or artist on the default media player. Use when the user wants to listen to music.",
            "parameters": {
                "type": "object",
                "properties": {
                    "genre": {
                        "type": "string",
                        "description": "Music genre, e.g. jazz, rock, classical, blues, electro",
                    },
                    "artist": {
                        "type": "string",
                        "description": "Artist name, e.g. Ween, Miles Davis, Pink Floyd",
                    },
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "control_media",
            "description": "Control media playback: pause, stop, or skip to next track.",
            "parameters": {
                "type": "object",
                "properties": {
                    "action": {
                        "type": "string",
                        "enum": ["pause", "stop", "next"],
                        "description": "Playback action to perform",
                    },
                },
                "required": ["action"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "set_volume",
            "description": "Control the volume of the default media player.",
            "parameters": {
                "type": "object",
                "properties": {
                    "action": {
                        "type": "string",
                        "enum": ["up", "down", "set"],
                        "description": "up/down for relative change, set for absolute level",
                    },
                    "level": {
                        "type": "number",
                        "description": "Volume level 0–100, required when action is 'set'",
                    },
                },
                "required": ["action"],
            },
        },
    },
```

- [ ] **Step 4: Add 3 route entries to `execute()` in `core/function_executor.py`**

In the `execute()` method, add these routes alongside the existing ones (e.g. after the `shell_exec` entry):

```python
        elif func_name == "play_music":
            return self._play_music(params)
        elif func_name == "control_media":
            return self._control_media(params)
        elif func_name == "set_volume":
            return self._set_volume(params)
```

- [ ] **Step 5: Add 3 handler methods to `FunctionExecutor`**

Add `settings` import at the top of `core/function_executor.py` if not already present:
```python
from core.settings_store import settings
```

Add these 3 private methods to the `FunctionExecutor` class (e.g. after `_shell_exec`):

```python
    def _play_music(self, params: dict) -> dict:
        from core.music_manager import music_manager
        from core.ha_control import ha_manager

        entity_id = settings.get("music.default_player", "").strip()
        if not entity_id:
            return {
                "success": False,
                "message": "Aucun lecteur configuré. Configure le lecteur par défaut dans les paramètres musique.",
                "data": None,
            }

        genre = params.get("genre", "").strip()
        artist = params.get("artist", "").strip()

        if genre:
            songs = music_manager.get_songs_by_genre(genre)
        elif artist:
            songs = music_manager.get_songs_by_artist(artist)
        else:
            return {"success": False, "message": "Précise un genre ou un artiste.", "data": None}

        if not songs:
            label = genre or artist
            return {"success": False, "message": f"Aucun morceau trouvé pour '{label}'.", "data": None}

        song = songs[0]
        url = music_manager.build_stream_url(song["id"])
        ok = ha_manager.play_media(entity_id, url)

        if ok:
            title = song.get("title", "?")
            artist_name = song.get("artist", "?")
            return {"success": True, "message": f"Lecture de « {title} » — {artist_name}", "data": None}
        return {"success": False, "message": "Impossible de lancer la lecture sur le lecteur.", "data": None}

    def _control_media(self, params: dict) -> dict:
        from core.ha_control import ha_manager

        entity_id = settings.get("music.default_player", "").strip()
        if not entity_id:
            return {"success": False, "message": "Aucun lecteur configuré.", "data": None}

        action = params.get("action", "")
        if action == "pause":
            ok = ha_manager.media_pause(entity_id)
            msg = "Lecture en pause." if ok else "Impossible de mettre en pause."
        elif action == "stop":
            ok = ha_manager.media_stop(entity_id)
            msg = "Lecture arrêtée." if ok else "Impossible d'arrêter la lecture."
        elif action == "next":
            ok = ha_manager.media_next_track(entity_id)
            msg = "Morceau suivant." if ok else "Impossible de passer au morceau suivant."
        else:
            return {"success": False, "message": f"Action inconnue : {action}", "data": None}

        return {"success": ok, "message": msg, "data": None}

    def _set_volume(self, params: dict) -> dict:
        from core.ha_control import ha_manager

        entity_id = settings.get("music.default_player", "").strip()
        if not entity_id:
            return {"success": False, "message": "Aucun lecteur configuré.", "data": None}

        action = params.get("action", "")
        if action == "up":
            ok = ha_manager.volume_up(entity_id)
            msg = "Volume augmenté." if ok else "Impossible d'augmenter le volume."
        elif action == "down":
            ok = ha_manager.volume_down(entity_id)
            msg = "Volume baissé." if ok else "Impossible de baisser le volume."
        elif action == "set":
            level = float(params.get("level", 50))
            ok = ha_manager.volume_set(entity_id, level / 100)
            msg = f"Volume réglé à {int(level)}%." if ok else "Impossible de régler le volume."
        else:
            return {"success": False, "message": f"Action inconnue : {action}", "data": None}

        return {"success": ok, "message": msg, "data": None}
```

- [ ] **Step 6: Run tests to verify they pass**

```
uv run pytest tests/test_music_executor.py -v
```
Expected: `9 passed`

- [ ] **Step 7: Run the full test suite**

```
uv run pytest tests/ -q
```
Expected: all previously passing tests still pass.

- [ ] **Step 8: Commit**

```bash
git add config.py core/function_executor.py tests/test_music_executor.py
git commit -m "feat(music): add play_music, control_media, set_volume LLM tools"
```

---

## Task 4: `core/semantic_router.py` — music utterances

**Files:**
- Modify: `core/semantic_router.py` (add utterances to `function_gemma` route + music keyword guard)

No new tests needed — existing semantic router tests cover the structure; the utterances are tested implicitly by integration.

- [ ] **Step 1: Add music utterances to `_ROUTES["function_gemma"]` in `core/semantic_router.py`**

In the `_ROUTES` dict, find `"function_gemma"` and append these utterances to its list:

```python
        # Music playback
        "joue de la musique", "joue du jazz", "joue du rock", "joue du classique",
        "joue de la soul", "joue du blues", "joue de l'electro", "joue de la techno",
        "mets de la musique", "lance de la musique", "joue un morceau",
        "play music", "play some jazz", "play rock", "play classical",
        # Artist
        "joue un album de", "mets un album de", "play something by",
        # Playback control
        "stop la musique", "arrête la musique", "morceau suivant", "chanson suivante",
        "stop the music", "next song", "skip",
        # Volume
        "monte le son", "baisse le son", "monte le volume", "baisse le volume",
        "mets le son à", "volume plus fort", "volume moins fort",
        "turn up the volume", "turn down the volume", "set the volume",
```

- [ ] **Step 2: Add a `_MUSIC_KEYWORDS` regex guard in `core/semantic_router.py`**

After the `_VISION_KEYWORDS` and `_FUNCTION_KEYWORDS` regex definitions, add:

```python
_MUSIC_KEYWORDS = re.compile(
    r"\b(joue[rzs]?\s+(du|de\s+la|de\s+l[''']?|un?\s+album|some|some\s+\w+)"
    r"|mets\s+(du|de\s+la|de\s+l[''']?|la\s+musique)"
    r"|lance\s+(du|de\s+la|la\s+musique)"
    r"|stop\s+la\s+music\w*"
    r"|arrête\s+la\s+music\w*"
    r"|morceau\s+suivant|chanson\s+suivante"
    r"|monte\s+le\s+(son|volume)|baisse\s+le\s+(son|volume)"
    r"|volume\s+(plus\s+fort|moins\s+fort)"
    r"|next\s+song|skip\s+track|play\s+music|play\s+some)\b",
    re.IGNORECASE,
)
```

- [ ] **Step 3: Add the music guard to `get_route()` in `core/semantic_router.py`**

In the `get_route()` function, add the music check after the vision check:

```python
def get_route(prompt: str) -> str:
    if _VISION_KEYWORDS.search(prompt):
        return "vision"
    if _MUSIC_KEYWORDS.search(prompt):
        return "function_gemma"
    if _FUNCTION_KEYWORDS.search(prompt):
        return "function_gemma"
    return _router.route(prompt)
```

- [ ] **Step 4: Run the full test suite**

```
uv run pytest tests/ -q
```
Expected: all tests pass.

- [ ] **Step 5: Commit**

```bash
git add core/semantic_router.py
git commit -m "feat(music): add music utterances and keyword guard to semantic router"
```

---

## Task 5: `gui/tabs/music.py` + i18n — default player setting

**Files:**
- Modify: `gui/tabs/music.py` (add default player card)
- Modify: `locales/fr.json` (add 2 keys)
- Modify: `locales/en.json` (add 2 keys)

- [ ] **Step 1: Add 2 i18n keys to `locales/fr.json`**

Inside the `"music"` section of `locales/fr.json`, add:

```json
"default_player": "Lecteur par défaut",
"default_player_desc": "entity_id du media_player Home Assistant (ex : media_player.chillout_area)"
```

- [ ] **Step 2: Add 2 i18n keys to `locales/en.json`**

Inside the `"music"` section of `locales/en.json`, add:

```json
"default_player": "Default player",
"default_player_desc": "Home Assistant media_player entity ID (e.g. media_player.chillout_area)"
```

- [ ] **Step 3: Add the default player card to `gui/tabs/music.py`**

In `gui/tabs/music.py`, add `QLineEdit` to the PySide6 imports and `SettingCardGroup`, `SettingCard`, `FluentIcon as FIF` to the qfluentwidgets imports if not already present. Also import `Qt` from `PySide6.QtCore`.

Add a new `_PlayerLineCard` class before the `MusicTab` class:

```python
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QLineEdit
from qfluentwidgets import SettingCardGroup, SettingCard, FluentIcon as FIF


class _PlayerLineCard(SettingCard):
    """Editable card for the default HA media_player entity_id."""

    def __init__(self, parent=None):
        super().__init__(
            FIF.SPEAKERS,
            tr("music.default_player"),
            tr("music.default_player_desc"),
            parent,
        )
        self._edit = QLineEdit(settings.get("music.default_player", ""), self)
        self._edit.setPlaceholderText("media_player.chillout_area")
        self._edit.setMinimumWidth(280)
        self._edit.textChanged.connect(lambda v: settings.set("music.default_player", v.strip()))
        self.hBoxLayout.addWidget(self._edit, 0, Qt.AlignRight)
        self.hBoxLayout.addSpacing(16)

    def retranslate(self):
        self.titleLabel.setText(tr("music.default_player"))
        self.contentLabel.setText(tr("music.default_player_desc"))
```

- [ ] **Step 4: Wire the card into `MusicTab`**

In the `MusicTab.__init__` (or wherever the UI is built), add a group and the card. Find where other groups are added to the layout and insert after them:

```python
        # ── Default player ─────────────────────────────────────────────
        self._player_group = SettingCardGroup(tr("music.default_player"), self._content)
        self._player_card = _PlayerLineCard(self._player_group)
        self._player_group.addSettingCard(self._player_card)
        self._layout.addWidget(self._player_group)
```

If `MusicTab` does not have a `_content` widget and `_layout` (ExpandLayout), adapt to the existing layout structure of that file — add the group to wherever other settings groups are placed.

- [ ] **Step 5: Verify ADA launches without error**

On Ubuntu:
```bash
cd ~/Desktop/ada_local && git pull && python3 ada.py
```
Open the Music tab and verify the "Lecteur par défaut" field appears. Enter `media_player.chillout_area` and confirm it persists after restarting ADA.

- [ ] **Step 6: Commit**

```bash
git add gui/tabs/music.py locales/fr.json locales/en.json
git commit -m "feat(music): add default player setting to Music tab"
```

---

## Final Verification

- [ ] Run the full test suite one last time:

```
uv run pytest tests/ -q
```
Expected: all tests pass including the 7 + 8 + 9 new tests.

- [ ] On Ubuntu, restart ADA, configure `music.default_player = media_player.chillout_area` in the Music tab.

- [ ] Test via Telegram: send "joue du jazz" → ADA should respond with "Lecture de « … » — …" and the Yamaha should start playing.

- [ ] Test via Telegram: send "pause" → Yamaha pauses.

- [ ] Test via Telegram: send "monte le son" → volume increases.

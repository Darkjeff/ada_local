# Music Control Implementation Design

## Goal

Enable ADA to search and play music from Navidrome on a configured HA media_player (Yamaha RX-V4A via MusicCast), and control playback (pause, stop, next, volume) via voice and Telegram.

## Architecture

Three layers added to the existing ADA pipeline:

1. **`core/music_manager.py`** — Navidrome Subsonic API client
2. **`core/ha_control.py`** — extended with missing media_player HA services
3. **`core/function_executor.py` + `config.py`** — 3 new LLM tool definitions

The semantic router already routes ambiguous commands to `function_gemma`; music utterances will be added explicitly to prevent drift.

---

## Section 1 — `core/music_manager.py`

Thin Subsonic API client. Reads credentials from existing settings keys:
- `navidrome.url` (e.g. `http://192.168.1.70:4533`)
- `navidrome.username`
- `navidrome.password`

Public interface:

```python
def get_songs_by_genre(genre: str, count: int = 20) -> list[dict]:
    """GET /rest/getSongsByGenre — returns list of song dicts with 'id', 'title', 'artist'."""

def get_songs_by_artist(artist: str, count: int = 20) -> list[dict]:
    """GET /rest/search3?query=artist — returns songs for best-matching artist."""

def build_stream_url(song_id: str) -> str:
    """Returns direct HTTP stream URL for a song id (includes auth params)."""
    # http://{url}/rest/stream?id={id}&u={user}&p={pass}&v=1.16.1&c=ada&format=mp3
```

Genre matching: case-insensitive, strips accents. If no results, returns `[]`.

Artist search: uses `search3` with `artistCount=1, songCount=count`. Falls back to empty list on no match.

Singleton: `music_manager = MusicManager()` at module bottom.

---

## Section 2 — `core/ha_control.py` extensions

New methods on `HAManager`:

```python
def play_media(self, entity_id: str, url: str, media_type: str = "music") -> bool:
    """POST /api/services/media_player/play_media"""

def media_pause(self, entity_id: str) -> bool:
    """POST /api/services/media_player/media_pause"""

def media_stop(self, entity_id: str) -> bool:
    """POST /api/services/media_player/media_stop"""

def media_next_track(self, entity_id: str) -> bool:
    """POST /api/services/media_player/media_next_track"""

def volume_set(self, entity_id: str, level: float) -> bool:
    """POST /api/services/media_player/volume_set — level 0.0 to 1.0"""

def volume_up(self, entity_id: str) -> bool:
    """POST /api/services/media_player/volume_up"""

def volume_down(self, entity_id: str) -> bool:
    """POST /api/services/media_player/volume_down"""
```

All return `True` on HTTP 200, `False` on error. All guard `if not self._url or not self._token`.

---

## Section 3 — LLM Tools (`config.py` + `function_executor.py`)

### 3 new tool definitions in `config.py` FUNCTIONS list:

**`play_music`**
```json
{
  "name": "play_music",
  "description": "Play music by genre or artist on the default media player",
  "parameters": {
    "genre": {"type": "string", "description": "Music genre (e.g. jazz, rock, classical)"},
    "artist": {"type": "string", "description": "Artist name"}
  }
}
```
At least one of `genre` or `artist` must be provided. `genre` takes priority if both given.

**`control_media`**
```json
{
  "name": "control_media",
  "description": "Control media playback (pause, stop, or skip to next track)",
  "parameters": {
    "action": {"type": "string", "enum": ["pause", "stop", "next"]}
  }
}
```

**`set_volume`**
```json
{
  "name": "set_volume",
  "description": "Control the volume of the default media player",
  "parameters": {
    "action": {"type": "string", "enum": ["up", "down", "set"]},
    "level": {"type": "number", "description": "Volume 0–100, required when action is 'set'"}
  }
}
```

### Implementations in `function_executor.py`:

**`_play_music(genre, artist)`**:
1. Read `music.default_player` from settings (e.g. `media_player.chillout_area`)
2. If `genre`: call `music_manager.get_songs_by_genre(genre)`
3. Else: call `music_manager.get_songs_by_artist(artist)`
4. If empty: return `{"success": False, "message": "Aucun morceau trouvé pour ce genre/artiste."}`
5. Pick first song from results, build stream URL
6. Call `ha_manager.play_media(default_player, stream_url)`
7. Return `{"success": True, "message": f"Lecture de {title} — {artist_name}"}`

**`_control_media(action)`**:
1. Read `music.default_player`
2. Call corresponding ha_manager method (`media_pause`, `media_stop`, `media_next_track`)
3. Return success/failure message

**`_set_volume(action, level)`**:
1. Read `music.default_player`
2. `up` → `ha_manager.volume_up()`, `down` → `ha_manager.volume_down()`, `set` → `ha_manager.volume_set(level / 100)`
3. Return success/failure message

---

## Section 4 — Settings UI

Add `music.default_player` to the existing Music tab (`gui/tabs/music.py`):
- `LineEditSettingCard` — entity ID field (e.g. `media_player.chillout_area`)
- Label: "Lecteur par défaut" / "Default player"
- Saved to settings key `music.default_player`

---

## Section 5 — Semantic Router

Add music utterances to `function_gemma` route in `core/semantic_router.py`:

```python
# Music playback
"joue de la musique", "joue du jazz", "joue du rock", "joue du classique",
"mets de la musique", "lance de la musique", "joue un morceau",
"joue de", "mets du", "lance du",
"play music", "play some jazz", "play rock",
# Artist
"joue", "mets un album de", "play something by",
# Playback control
"pause", "stop la musique", "morceau suivant", "chanson suivante",
"pause the music", "stop the music", "next song", "skip",
# Volume
"monte le son", "baisse le son", "volume plus fort", "volume moins fort",
"mets le son à", "turn up the volume", "turn down the volume",
```

---

## Section 6 — i18n

No new UI keys needed beyond the settings label (added inline in music tab). Error/success messages are returned in French by the executor directly.

---

## Error Handling

- Navidrome unreachable → `{"success": False, "message": "Navidrome inaccessible."}`
- No results found → `{"success": False, "message": "Aucun morceau trouvé."}`
- `music.default_player` not configured → `{"success": False, "message": "Aucun lecteur configuré. Configure le lecteur par défaut dans les paramètres."}`
- HA play_media fails → `{"success": False, "message": "Impossible de lancer la lecture sur le lecteur."}`

---

## Testing

- `tests/test_music_manager.py` — mock Subsonic HTTP responses for genre/artist search and stream URL building
- `tests/test_ha_music_control.py` — mock HA API calls for play_media, volume, pause/stop/next

No integration test against real Navidrome/HA needed (mocked at HTTP level).

---

## Files Modified / Created

| File | Action |
|------|--------|
| `core/music_manager.py` | Create |
| `core/ha_control.py` | Extend (7 new methods) |
| `core/function_executor.py` | Extend (3 new handlers) |
| `config.py` | Extend (3 new tool definitions) |
| `core/semantic_router.py` | Extend (music utterances) |
| `gui/tabs/music.py` | Extend (default player setting) |
| `tests/test_music_manager.py` | Create |
| `tests/test_ha_music_control.py` | Create |

# Music + Home Integration — Design Spec
**Date:** 2026-05-26
**Status:** Approved

## Objectif

Permettre à ADA de répondre à une commande naturelle comme "Lance du jazz calme dans le salon" en orchestrant Navidrome (recherche + stream) et Home Assistant (media_player) pour jouer une vraie playlist de plusieurs titres à la suite.

---

## Contexte

### État existant

- `core/music_manager.py` — client Subsonic : `get_songs_by_genre()`, `get_songs_by_artist()`, `build_stream_url()`. Ne gère qu'un titre à la fois.
- `core/ha_control.py` — client HA REST. `media_player` dans `CONTROLLABLE_DOMAINS`. `play_media()` existe déjà (appelé depuis function_executor).
- `core/function_executor._play_music()` — implémentation basique : `songs[0]`, player fixe depuis `settings["music.default_player"]`, pas de notion de pièce.
- `gui/tabs/music.py` — panneau stats Navidrome + ouverture navigateur. Non concerné par ce spec.

### Setup matériel

- 1 Denon/Marantz AVR intégré dans HA comme `media_player.chillout_area` ("chillout area")
- Denon supporte nativement les playlists M3U via `media_player/play_media`
- Alexas dans les autres pièces — hors scope (ne supportent pas les streams Navidrome)
- ADA tourne sur Ubuntu 192.168.1.70, même LAN que le Denon

---

## Architecture

### Flux complet

```
User: "Lance du jazz calme dans le salon"
          │
          ▼
    semantic_router → play_music(genre="jazz", room="salon")
          │
          ▼
    function_executor._play_music()
          │
          ├─ 1. music_manager.get_songs_by_genre("jazz", count=20)  → liste shufflée
          ├─ 2. music_manager.build_m3u(songs[:15])                 → chaîne M3U
          ├─ 3. playlist_server.serve(m3u)                          → URL locale M3U
          ├─ 4. RoomResolver : settings["music.room_players"]["salon"] → entity_id
          └─ 5. ha_manager.play_media(entity_id, m3u_url)           → Denon joue 15 titres

ADA répond : "Je lance du jazz dans le salon — 15 titres en queue"
```

---

## Composants

### 1. `core/playlist_server.py` — nouveau

Singleton `PlaylistServer` — thread HTTP minimal (stdlib `http.server`) servant un fichier M3U statique.

**API publique :**
```python
playlist_server.serve(m3u_content: str, ttl: int = 300) -> str
# Démarre (ou remplace) le serveur, retourne l'URL complète.
# Ex: "http://192.168.1.70:8765/playlist.m3u"
```

**Comportement :**
- Endpoint unique : `GET /playlist.m3u`, répond `Content-Type: audio/x-mpegurl`
- Singleton : si déjà actif, remplace le contenu M3U et repart le TTL
- Auto-stop après `ttl` secondes (défaut 300s)
- Thread daemon → s'arrête proprement quand ADA quitte
- `host` = IP locale ADA lue depuis settings (`music.playlist_server_host`, défaut `192.168.1.70`)
- `port` = settings `music.playlist_server_port`, défaut `8765`

**Pas de Flask/aiohttp** — `http.server` stdlib suffit pour servir un fichier statique à un AVR.

---

### 2. `core/music_manager.py` — modification

Ajouter `build_m3u()` :

```python
def build_m3u(self, songs: list[dict]) -> str:
    lines = ["#EXTM3U"]
    for s in songs:
        title  = s.get("title", "Unknown")
        artist = s.get("artist", "")
        lines.append(f"#EXTINF:-1,{artist} - {title}")
        lines.append(self.build_stream_url(s["id"]))
    return "\n".join(lines)
```

Les URLs Subsonic incluent déjà l'authentification en query params — le Denon peut les fetcher directement.

---

### 3. `core/ha_control.py` — vérification/complétion

S'assurer que `play_media` appelle le bon service HA :

```python
def play_media(self, entity_id: str, url: str, media_type: str = "music") -> bool:
    return self._call_service("media_player/play_media", {
        "entity_id": entity_id,
        "media_content_id": url,
        "media_content_type": media_type,
    })
```

---

### 4. `core/function_executor._play_music()` — refonte

Remplace la logique actuelle :

```python
def _play_music(self, params: dict) -> dict:
    genre     = params.get("genre", "")
    artist    = params.get("artist", "")
    room      = params.get("room", "")
    count     = int(params.get("count", 15))

    # Résoudre le player
    room_map  = settings.get("music.room_players", {})
    entity_id = room_map.get(room.lower()) or settings.get("music.default_player", "")
    if not entity_id:
        return {"success": False, "message": "Aucun lecteur configuré.", "data": None}

    # Chercher les chansons
    if genre:
        songs = music_manager.get_songs_by_genre(genre, count=count)
    elif artist:
        songs = music_manager.get_songs_by_artist(artist, count=count)
    else:
        return {"success": False, "message": "Précise un genre ou un artiste.", "data": None}

    if not songs:
        return {"success": False, "message": f"Aucune chanson trouvée pour '{genre or artist}'.", "data": None}

    # Shuffler + générer M3U
    random.shuffle(songs)
    m3u = music_manager.build_m3u(songs[:count])

    # Servir + lancer
    from core.playlist_server import playlist_server
    url = playlist_server.serve(m3u)
    ok  = ha_manager.play_media(entity_id, url)

    label = room or entity_id
    return {
        "success": ok,
        "message": f"Je lance {'du ' + genre if genre else artist} dans {label} — {len(songs[:count])} titres en queue.",
        "data": {"entity_id": entity_id, "track_count": len(songs[:count])}
    }
```

---

### 5. Settings — nouvelles clés

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

---

## Ce qui est hors scope (v1)

- **Mood filtering** ("calme") : Navidrome n'a pas d'API de mood. Le paramètre est ignoré en v1, le genre suffit.
- **Alexa rooms** : ne supportent pas les streams HTTP arbitraires.
- **Détection automatique de pièce** depuis les areas HA : la map `room_players` en settings est suffisante pour l'instant.
- **UI Settings pour room_players** : configuration manuelle dans settings.json pour l'instant.
- **Contrôle playback** (pause/stop/next) : déjà géré par `_control_media()` existant, non modifié.

---

## Tests à valider manuellement

1. "Lance du jazz dans le salon" → 15 titres jouent sur le Denon
2. "Lance de la musique de Miles Davis" → fonctionne avec `artist`
3. Pièce inconnue ("cuisine") → fallback sur `default_player`
4. Navidrome offline → message d'erreur clair
5. Playlist server s'arrête bien après 300s (vérifier avec `netstat`)

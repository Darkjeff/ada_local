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

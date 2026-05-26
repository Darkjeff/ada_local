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
        except requests.RequestException as e:
            print(f"[MusicManager] {endpoint} request failed: {e}")
            return None
        try:
            data = r.json().get("subsonic-response", {})
            return data if data.get("status") == "ok" else None
        except ValueError as e:
            print(f"[MusicManager] {endpoint} JSON parse failed: {e}")
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
        from urllib.parse import urlencode
        base = self._base_url()
        auth = self._auth()
        qs = urlencode({**auth, "id": song_id, "format": "mp3"})
        return f"{base}/rest/stream?{qs}"

    def build_m3u(self, songs: list[dict]) -> str:
        """Return an M3U playlist string for the given songs list."""
        lines = ["#EXTM3U"]
        for s in songs:
            title  = s.get("title", "Unknown")
            artist = s.get("artist", "")
            lines.append(f"#EXTINF:-1,{artist} - {title}")
            lines.append(self.build_stream_url(s["id"]))
        return "\n".join(lines)


music_manager = MusicManager()

"""Calibre-Web REST API client — book search and download URL generation."""

import requests
from typing import Optional

from core.settings_store import settings

_FORMAT_PRIORITY = ["epub", "pdf", "mobi", "azw3", "fb2"]


class CalibreManager:

    def _base_url(self) -> str:
        return settings.get("calibre.url", "").rstrip("/")

    def _auth(self) -> tuple:
        return (
            settings.get("calibre.username", ""),
            settings.get("calibre.password", ""),
        )

    def _get(self, endpoint: str, **params) -> Optional[dict]:
        base = self._base_url()
        if not base:
            return None
        try:
            r = requests.get(
                f"{base}{endpoint}",
                params=params,
                auth=self._auth(),
                timeout=10,
            )
            r.raise_for_status()
        except requests.RequestException as e:
            print(f"[CalibreManager] {endpoint} request failed: {e}")
            return None
        try:
            return r.json()
        except ValueError as e:
            print(f"[CalibreManager] {endpoint} JSON parse failed: {e}")
            return None

    def _parse_book(self, raw: dict) -> dict:
        """Normalise a raw Calibre-Web book dict into a flat result dict."""
        authors = raw.get("authors") or []
        author = authors[0]["name"] if authors else ""
        pubdate = (raw.get("pubdate") or "")[:4]  # "YYYY-MM-DD" → "YYYY"
        formats = [f.lower() for f in (raw.get("formats") or [])]
        description = raw.get("description") or ""
        return {
            "id": raw.get("id"),
            "title": raw.get("title", ""),
            "author": author,
            "year": pubdate,
            "formats": formats,
            "description": description,
            "download_url": self.get_download_url(raw.get("id"), formats),
        }

    def search_books(self, query: str, search_type: str = "all", count: int = 3) -> list[dict]:
        """
        Search Calibre-Web for books matching `query`.
        search_type: "title" | "author" | "tags" | "all" (ignored server-side, passed for logging).
        Returns up to `count` normalised book dicts. Returns [] on error or no match.
        """
        print(f"[CalibreManager] search_books query={query!r} type={search_type} count={count}")
        data = self._get("/api/books", search=query, limit=count)
        if not data:
            return []
        books = data.get("books") or []
        return [self._parse_book(b) for b in books[:count]]

    def get_download_url(self, book_id: Optional[int], formats: list[str]) -> str:
        """
        Return the best download URL for `book_id`.
        Picks format by priority: epub > pdf > mobi > azw3 > fb2 > first available.
        Returns "" if book_id is None or formats is empty.
        """
        if not book_id or not formats:
            return ""
        base = self._base_url()
        if not base:
            return ""
        fmt = next((f for f in _FORMAT_PRIORITY if f in formats), formats[0])
        return f"{base}/api/books/{book_id}/download/{fmt}"


calibre_manager = CalibreManager()

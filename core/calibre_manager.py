"""Calibre-Web OPDS client — book search and download URL generation."""

import re
import requests
import xml.etree.ElementTree as ET
from typing import Optional
from urllib.parse import quote

from core.settings_store import settings

_ATOM = "http://www.w3.org/2005/Atom"
_DC   = "http://purl.org/dc/terms/"

_FORMAT_PRIORITY = ["epub", "pdf", "mobi", "azw3", "fb2"]

_MIME_TO_FMT = {
    "application/epub+zip":           "epub",
    "application/pdf":                "pdf",
    "application/x-mobipocket-ebook": "mobi",
    "application/x-mobi8-ebook":      "azw3",
    "application/fb2+xml":            "fb2",
    "application/x-fb2+zip":          "fb2",
}


class CalibreManager:

    def _base_url(self) -> str:
        return settings.get("calibre.url", "").rstrip("/")

    def _auth(self) -> tuple:
        return (
            settings.get("calibre.username", ""),
            settings.get("calibre.password", ""),
        )

    def _get_opds(self, path: str) -> Optional[ET.Element]:
        base = self._base_url()
        if not base:
            return None
        try:
            r = requests.get(f"{base}{path}", auth=self._auth(), timeout=10)
            r.raise_for_status()
        except requests.RequestException as e:
            print(f"[CalibreManager] {path} request failed: {e}")
            return None
        try:
            return ET.fromstring(r.content)
        except ET.ParseError as e:
            print(f"[CalibreManager] {path} XML parse failed: {e}")
            return None

    def _parse_entry(self, entry: ET.Element, base: str) -> dict:
        """Parse an OPDS Atom <entry> into a flat book dict."""

        def _text(ns: str, tag: str) -> str:
            el = entry.find(f"{{{ns}}}{tag}")
            return (el.text or "").strip() if el is not None else ""

        title  = _text(_ATOM, "title")
        year   = _text(_DC,   "date")[:4]
        summary = _text(_ATOM, "summary")
        description = re.sub(r"<[^>]+>", "", summary).strip()

        author_el = entry.find(f"{{{_ATOM}}}author/{{{_ATOM}}}name")
        author = (author_el.text or "").strip() if author_el is not None else ""

        # Acquisition links → formats and URLs
        formats:   list[str]       = []
        fmt_links: dict[str, str]  = {}

        for link in entry.findall(f"{{{_ATOM}}}link"):
            rel  = link.get("rel", "")
            mime = link.get("type", "")
            href = link.get("href", "")
            if "acquisition" in rel and href:
                fmt = _MIME_TO_FMT.get(mime)
                if fmt and fmt not in fmt_links:
                    formats.append(fmt)
                    fmt_links[fmt] = f"{base}{href}" if href.startswith("/") else href

        best_fmt     = next((f for f in _FORMAT_PRIORITY if f in fmt_links), formats[0] if formats else None)
        download_url = fmt_links.get(best_fmt, "") if best_fmt else ""

        # Extract numeric book_id from any download href
        book_id: Optional[int] = None
        for href in fmt_links.values():
            m = re.search(r"/download/(\d+)/", href)
            if m:
                book_id = int(m.group(1))
                break

        return {
            "id":           book_id,
            "title":        title,
            "author":       author,
            "year":         year,
            "formats":      formats,
            "description":  description,
            "download_url": download_url,
        }

    def search_books(self, query: str, search_type: str = "all", count: int = 3) -> list[dict]:
        """
        Search Calibre-Web via OPDS for books matching `query`.
        search_type is accepted but not forwarded (OPDS searches all fields).
        Returns up to `count` normalised book dicts. Returns [] on error or no match.
        """
        print(f"[CalibreManager] search_books query={query!r} type={search_type} count={count}")
        root = self._get_opds(f"/opds/search/{quote(query, safe='')}")
        if root is None:
            return []
        base    = self._base_url()
        entries = root.findall(f"{{{_ATOM}}}entry")
        return [self._parse_entry(e, base) for e in entries[:count]]

    def get_download_url(self, book_id: Optional[int], formats: list[str]) -> str:
        """
        Construct an OPDS download URL from book_id and formats list.
        Fallback used when _parse_entry cannot extract the URL directly.
        """
        if not book_id or not formats:
            return ""
        base = self._base_url()
        if not base:
            return ""
        fmt = next((f for f in _FORMAT_PRIORITY if f in formats), formats[0])
        return f"{base}/opds/download/{book_id}/{fmt}/"


calibre_manager = CalibreManager()

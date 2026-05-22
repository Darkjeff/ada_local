# tests/test_calibre_manager.py
from unittest.mock import patch, MagicMock
import requests
from core.calibre_manager import CalibreManager


def _make_manager():
    return CalibreManager()


def _settings(k, d=""):
    return {
        "calibre.url":      "http://localhost:8083",
        "calibre.username": "jeff",
        "calibre.password": "pass",
    }.get(k, d)


# ── OPDS XML helpers ─────────────────────────────────────────────────────────

def _entry_xml(title="Dune", author="Frank Herbert", year="1965",
               book_id=1, epub=True, pdf=False, description="Epic sci-fi.") -> str:
    links = ""
    if epub:
        links += (
            f'<link rel="http://opds-spec.org/acquisition" '
            f'type="application/epub+zip" href="/opds/download/{book_id}/epub/"/>'
        )
    if pdf:
        links += (
            f'<link rel="http://opds-spec.org/acquisition" '
            f'type="application/pdf" href="/opds/download/{book_id}/pdf/"/>'
        )
    author_xml = f"<author><name>{author}</name></author>" if author else ""
    return (
        f"<entry>"
        f"<title>{title}</title>"
        f"<id>urn:uuid:test-{book_id}</id>"
        f"{author_xml}"
        f"<dc:date>{year}-01-01</dc:date>"
        f"<summary>{description}</summary>"
        f"{links}"
        f"</entry>"
    )


def _make_feed(entries: str) -> bytes:
    return (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<feed xmlns="http://www.w3.org/2005/Atom"'
        ' xmlns:dc="http://purl.org/dc/terms/">'
        + entries +
        "</feed>"
    ).encode()


def _mock_response(content: bytes, status: int = 200):
    r = MagicMock()
    r.raise_for_status = MagicMock()
    r.content = content
    r.status_code = status
    return r


# ── Tests ────────────────────────────────────────────────────────────────────

def test_search_books_returns_results():
    mgr  = _make_manager()
    feed = _make_feed(_entry_xml())
    with patch("core.calibre_manager.requests.get", return_value=_mock_response(feed)):
        with patch("core.calibre_manager.settings") as s:
            s.get.side_effect = _settings
            result = mgr.search_books("Dune")
    assert len(result) == 1
    assert result[0]["title"] == "Dune"
    assert result[0]["author"] == "Frank Herbert"
    assert "epub" in result[0]["formats"]


def test_search_books_no_url():
    mgr = _make_manager()
    with patch("core.calibre_manager.settings") as s:
        s.get.return_value = ""
        result = mgr.search_books("Dune")
    assert result == []


def test_search_books_network_error():
    mgr = _make_manager()
    with patch("core.calibre_manager.requests.get",
               side_effect=requests.RequestException("timeout")):
        with patch("core.calibre_manager.settings") as s:
            s.get.side_effect = _settings
            result = mgr.search_books("Dune")
    assert result == []


def test_search_books_empty_results():
    mgr  = _make_manager()
    feed = _make_feed("")  # no entries
    with patch("core.calibre_manager.requests.get", return_value=_mock_response(feed)):
        with patch("core.calibre_manager.settings") as s:
            s.get.side_effect = _settings
            result = mgr.search_books("unknownbook99999")
    assert result == []


def test_get_download_url_epub_priority():
    mgr = _make_manager()
    with patch("core.calibre_manager.settings") as s:
        s.get.side_effect = _settings
        url = mgr.get_download_url(42, ["epub", "pdf"])
    assert "localhost:8083" in url
    assert "42" in url
    assert "epub" in url


def test_get_download_url_fallback_to_pdf():
    mgr = _make_manager()
    with patch("core.calibre_manager.settings") as s:
        s.get.side_effect = _settings
        url = mgr.get_download_url(42, ["pdf", "mobi"])
    assert "pdf" in url


def test_get_download_url_no_formats():
    mgr = _make_manager()
    with patch("core.calibre_manager.settings") as s:
        s.get.side_effect = _settings
        url = mgr.get_download_url(42, [])
    assert url == ""


def test_search_books_missing_description():
    mgr  = _make_manager()
    feed = _make_feed(_entry_xml(description=""))
    with patch("core.calibre_manager.requests.get", return_value=_mock_response(feed)):
        with patch("core.calibre_manager.settings") as s:
            s.get.side_effect = _settings
            result = mgr.search_books("Test")
    assert result[0]["description"] == ""


def test_search_books_no_authors():
    mgr = _make_manager()
    entry = (
        "<entry>"
        "<title>Anonymous</title>"
        "<id>urn:uuid:test-3</id>"
        "<dc:date>2020-01-01</dc:date>"
        "<summary></summary>"
        '<link rel="http://opds-spec.org/acquisition"'
        ' type="application/epub+zip" href="/opds/download/3/epub/"/>'
        "</entry>"
    )
    feed = _make_feed(entry)
    with patch("core.calibre_manager.requests.get", return_value=_mock_response(feed)):
        with patch("core.calibre_manager.settings") as s:
            s.get.side_effect = _settings
            result = mgr.search_books("Anonymous")
    assert result[0]["author"] == ""

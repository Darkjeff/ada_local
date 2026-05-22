# tests/test_calibre_manager.py
from unittest.mock import patch, MagicMock
import requests
from core.calibre_manager import CalibreManager


def _make_manager():
    return CalibreManager()


def _settings(k, d=""):
    return {
        "calibre.url": "http://localhost:8083",
        "calibre.username": "jeff",
        "calibre.password": "pass",
    }.get(k, d)


def _mock_response(json_data, status=200):
    r = MagicMock()
    r.raise_for_status = MagicMock()
    r.json.return_value = json_data
    r.status_code = status
    return r


def test_search_books_returns_results():
    mgr = _make_manager()
    books = [
        {
            "id": 1,
            "title": "Dune",
            "authors": [{"name": "Frank Herbert"}],
            "pubdate": "1965-01-01",
            "formats": ["epub", "pdf"],
            "description": "A science fiction epic.",
        }
    ]
    with patch("core.calibre_manager.requests.get", return_value=_mock_response({"books": books})):
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
    with patch("core.calibre_manager.requests.get", side_effect=requests.RequestException("timeout")):
        with patch("core.calibre_manager.settings") as s:
            s.get.side_effect = _settings
            result = mgr.search_books("Dune")
    assert result == []


def test_search_books_empty_results():
    mgr = _make_manager()
    with patch("core.calibre_manager.requests.get", return_value=_mock_response({"books": []})):
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
    mgr = _make_manager()
    books = [{"id": 2, "title": "Test", "authors": [{"name": "Auth"}], "pubdate": "", "formats": [], "description": None}]
    with patch("core.calibre_manager.requests.get", return_value=_mock_response({"books": books})):
        with patch("core.calibre_manager.settings") as s:
            s.get.side_effect = _settings
            result = mgr.search_books("Test")
    assert result[0]["description"] == ""


def test_search_books_no_authors():
    mgr = _make_manager()
    books = [{"id": 3, "title": "Anonymous", "authors": [], "pubdate": "2020", "formats": ["epub"], "description": ""}]
    with patch("core.calibre_manager.requests.get", return_value=_mock_response({"books": books})):
        with patch("core.calibre_manager.settings") as s:
            s.get.side_effect = _settings
            result = mgr.search_books("Anonymous")
    assert result[0]["author"] == ""

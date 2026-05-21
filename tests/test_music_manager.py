from unittest.mock import patch, MagicMock
import requests
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
    with patch("core.music_manager.requests.get", side_effect=requests.RequestException("timeout")):
        with patch("core.music_manager.settings") as s:
            s.get.side_effect = _settings_side_effect
            result = mgr.get_songs_by_genre("jazz")
    assert result == []

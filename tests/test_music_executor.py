from unittest.mock import patch, MagicMock
from core.function_executor import FunctionExecutor


def _make_executor():
    return FunctionExecutor()


def test_play_music_by_genre_success():
    ex = _make_executor()
    songs = [{"id": "s1", "title": "So What", "artist": "Miles Davis"}]
    with patch("core.function_executor.settings") as s:
        s.get.side_effect = lambda k, d="": {"music.default_player": "media_player.chillout_area"}.get(k, d)
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
        s.get.side_effect = lambda k, d="": {"music.default_player": "media_player.chillout_area"}.get(k, d)
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


def test_set_volume_down():
    ex = _make_executor()
    with patch("core.function_executor.settings") as s:
        s.get.return_value = "media_player.chillout_area"
        with patch("core.ha_control.ha_manager") as ha:
            ha.volume_down.return_value = True
            result = ex.execute("set_volume", {"action": "down"})
    assert result["success"] is True

from unittest.mock import patch, MagicMock
from core.ha_control import HAManager


def _make_manager():
    m = HAManager.__new__(HAManager)
    m._url = "http://ha.local:8123"
    m._token = "tok"
    return m


def test_play_media_calls_service_with_url():
    mgr = _make_manager()
    with patch.object(mgr, "call_service", return_value=True) as mock_cs:
        result = mgr.play_media("media_player.chillout_area", "http://stream/song.mp3")
    assert result is True
    mock_cs.assert_called_once_with(
        "media_player", "play_media", "media_player.chillout_area",
        media_content_id="http://stream/song.mp3",
        media_content_type="music",
    )


def test_play_media_not_configured():
    mgr = _make_manager()
    mgr._url = ""
    result = mgr.play_media("media_player.chillout_area", "http://stream/song.mp3")
    assert result is False


def test_media_pause():
    mgr = _make_manager()
    with patch.object(mgr, "call_service", return_value=True) as mock_cs:
        result = mgr.media_pause("media_player.chillout_area")
    assert result is True
    mock_cs.assert_called_once_with("media_player", "media_pause", "media_player.chillout_area")


def test_media_stop():
    mgr = _make_manager()
    with patch.object(mgr, "call_service", return_value=True) as mock_cs:
        result = mgr.media_stop("media_player.chillout_area")
    assert result is True
    mock_cs.assert_called_once_with("media_player", "media_stop", "media_player.chillout_area")


def test_media_next_track():
    mgr = _make_manager()
    with patch.object(mgr, "call_service", return_value=True) as mock_cs:
        result = mgr.media_next_track("media_player.chillout_area")
    assert result is True
    mock_cs.assert_called_once_with("media_player", "media_next_track", "media_player.chillout_area")


def test_volume_set():
    mgr = _make_manager()
    with patch.object(mgr, "call_service", return_value=True) as mock_cs:
        result = mgr.volume_set("media_player.chillout_area", 0.5)
    assert result is True
    mock_cs.assert_called_once_with(
        "media_player", "volume_set", "media_player.chillout_area", volume_level=0.5
    )


def test_volume_up():
    mgr = _make_manager()
    with patch.object(mgr, "call_service", return_value=True) as mock_cs:
        result = mgr.volume_up("media_player.chillout_area")
    assert result is True
    mock_cs.assert_called_once_with("media_player", "volume_up", "media_player.chillout_area")


def test_volume_down():
    mgr = _make_manager()
    with patch.object(mgr, "call_service", return_value=True) as mock_cs:
        result = mgr.volume_down("media_player.chillout_area")
    assert result is True
    mock_cs.assert_called_once_with("media_player", "volume_down", "media_player.chillout_area")

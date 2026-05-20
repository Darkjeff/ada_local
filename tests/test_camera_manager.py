# tests/test_camera_manager.py
import os
from unittest.mock import patch, MagicMock
from core.camera_manager import (
    CameraManager, CameraEndpoint, CameraCapabilities, SnapshotResult
)


def _make_manager():
    return CameraManager()


def _raw_endpoints():
    return [
        {
            "entity_id": "camera.bureau",
            "friendly_name": "camera bureau",
            "area_id": "cafe_jeff",
            "area_name": "Café Jeff",
            "state": "idle",
        },
        {
            "entity_id": "camera.entree",
            "friendly_name": "camera entree",
            "area_id": "",
            "area_name": "",
            "state": "idle",
        },
    ]


def test_refresh_populates_endpoints():
    mgr = _make_manager()
    with patch("core.camera_manager.ha_manager") as mock_ha:
        mock_ha.get_camera_endpoints.return_value = _raw_endpoints()
        mgr.refresh()
    eps = mgr.list_endpoints()
    assert len(eps) == 2
    assert eps[0].entity_id == "camera.bureau"
    assert eps[0].area_name == "Café Jeff"
    assert eps[0].capabilities.snapshot is True
    assert eps[0].capabilities.audio_input is False


def test_find_by_area_exact():
    mgr = _make_manager()
    with patch("core.camera_manager.ha_manager") as mock_ha:
        mock_ha.get_camera_endpoints.return_value = _raw_endpoints()
        mgr.refresh()
    result = mgr.find_by_area("café")
    assert result is not None
    assert result.entity_id == "camera.bureau"


def test_find_by_area_partial():
    mgr = _make_manager()
    with patch("core.camera_manager.ha_manager") as mock_ha:
        mock_ha.get_camera_endpoints.return_value = _raw_endpoints()
        mgr.refresh()
    result = mgr.find_by_area("cafe")   # no accent
    assert result is not None
    assert result.entity_id == "camera.bureau"


def test_find_by_area_no_match():
    mgr = _make_manager()
    with patch("core.camera_manager.ha_manager") as mock_ha:
        mock_ha.get_camera_endpoints.return_value = _raw_endpoints()
        mgr.refresh()
    result = mgr.find_by_area("chambre")
    assert result is None


def test_find_by_area_empty_hint():
    mgr = _make_manager()
    with patch("core.camera_manager.ha_manager") as mock_ha:
        mock_ha.get_camera_endpoints.return_value = _raw_endpoints()
        mgr.refresh()
    result = mgr.find_by_area("")
    assert result is None


def test_capture_snapshot_success(tmp_path):
    mgr = _make_manager()
    jpg = b"\xff\xd8\xff" + b"\x00" * 100   # fake JPEG bytes

    with patch("core.camera_manager.ha_manager") as mock_ha:
        mock_ha.get_camera_snapshot.return_value = jpg
        with patch("core.camera_manager._CACHE_DIR", str(tmp_path)):
            result = mgr.capture_snapshot("camera.bureau")

    assert result.success is True
    assert result.entity_id == "camera.bureau"
    assert os.path.exists(result.path)
    with open(result.path, "rb") as f:
        assert f.read() == jpg


def test_capture_snapshot_failure():
    mgr = _make_manager()
    with patch("core.camera_manager.ha_manager") as mock_ha:
        mock_ha.get_camera_snapshot.return_value = None
        result = mgr.capture_snapshot("camera.bureau")
    assert result.success is False
    assert result.error != ""

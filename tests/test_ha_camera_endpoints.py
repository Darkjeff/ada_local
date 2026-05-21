from unittest.mock import patch, MagicMock
from core.ha_control import HAManager


def _make_manager():
    m = HAManager.__new__(HAManager)
    m.entities = {}
    m._raw_entities = {}
    m._connected = False
    m._url = "http://ha.local:8123"
    m._token = "tok"
    return m


def _fake_post_area(area_id: str, area_name: str):
    """Returns a mock for requests.post to /api/template returning area_id|area_name."""
    def fake_post(url, **kw):
        r = MagicMock()
        r.status_code = 200
        r.text = f"{area_id}|{area_name}"
        return r
    return fake_post


def test_get_camera_endpoints_joins_areas():
    mgr = _make_manager()
    states = {
        "camera.bureau": {
            "state": "idle",
            "attributes": {"friendly_name": "camera bureau"},
        }
    }
    with patch.object(mgr, "_fetch_all_states", return_value=states):
        with patch("core.ha_control.requests.post", side_effect=_fake_post_area("cafe_jeff", "Café Jeff")):
            result = mgr.get_camera_endpoints()

    assert len(result) == 1
    assert result[0]["entity_id"] == "camera.bureau"
    assert result[0]["area_name"] == "Café Jeff"
    assert result[0]["area_id"] == "cafe_jeff"
    assert result[0]["friendly_name"] == "camera bureau"
    assert result[0]["state"] == "idle"


def test_get_camera_endpoints_no_area():
    mgr = _make_manager()
    states = {
        "camera.entree": {
            "state": "idle",
            "attributes": {"friendly_name": "camera entree"},
        }
    }
    with patch.object(mgr, "_fetch_all_states", return_value=states):
        with patch("core.ha_control.requests.post", side_effect=_fake_post_area("", "")):
            result = mgr.get_camera_endpoints()

    assert len(result) == 1
    assert result[0]["area_id"] == ""
    assert result[0]["area_name"] == ""
    assert result[0]["friendly_name"] == "camera entree"
    assert result[0]["state"] == "idle"


def test_get_camera_endpoints_ha_unreachable():
    mgr = _make_manager()
    with patch.object(mgr, "_fetch_all_states", side_effect=Exception("timeout")):
        result = mgr.get_camera_endpoints()
    assert result == []


def test_get_camera_endpoints_not_configured():
    mgr = _make_manager()
    mgr._url = ""
    result = mgr.get_camera_endpoints()
    assert result == []

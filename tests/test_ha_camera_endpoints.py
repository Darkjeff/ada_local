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


def test_get_camera_endpoints_joins_areas():
    mgr = _make_manager()
    entity_registry = [
        {"entity_id": "camera.bureau", "area_id": "cafe_jeff"},
        {"entity_id": "light.salon",   "area_id": "salon"},   # filtered out
    ]
    area_registry = [
        {"area_id": "cafe_jeff", "name": "Café Jeff"},
    ]
    states = {
        "camera.bureau": {
            "state": "idle",
            "attributes": {"friendly_name": "camera bureau"},
        }
    }

    def fake_get(url, **kw):
        r = MagicMock()
        r.status_code = 200
        if "entity_registry" in url:
            r.json.return_value = entity_registry
        elif "area_registry" in url:
            r.json.return_value = area_registry
        return r

    with patch("core.ha_control.requests.get", side_effect=fake_get):
        with patch.object(mgr, "_fetch_all_states", return_value=states):
            result = mgr.get_camera_endpoints()

    assert len(result) == 1
    assert result[0]["entity_id"] == "camera.bureau"
    assert result[0]["area_name"] == "Café Jeff"
    assert result[0]["friendly_name"] == "camera bureau"
    assert result[0]["state"] == "idle"


def test_get_camera_endpoints_no_area():
    mgr = _make_manager()
    entity_registry = [{"entity_id": "camera.entree", "area_id": None}]
    area_registry = []
    states = {
        "camera.entree": {
            "state": "idle",
            "attributes": {"friendly_name": "camera entree"},
        }
    }

    def fake_get(url, **kw):
        r = MagicMock()
        r.status_code = 200
        if "entity_registry" in url:
            r.json.return_value = entity_registry
        elif "area_registry" in url:
            r.json.return_value = area_registry
        return r

    with patch("core.ha_control.requests.get", side_effect=fake_get):
        with patch.object(mgr, "_fetch_all_states", return_value=states):
            result = mgr.get_camera_endpoints()

    assert len(result) == 1
    assert result[0]["area_id"] == ""
    assert result[0]["area_name"] == ""
    assert result[0]["friendly_name"] == "camera entree"
    assert result[0]["state"] == "idle"


def test_get_camera_endpoints_ha_unreachable():
    mgr = _make_manager()
    with patch("core.ha_control.requests.get", side_effect=Exception("timeout")):
        result = mgr.get_camera_endpoints()
    assert result == []


def test_get_camera_endpoints_not_configured():
    mgr = _make_manager()
    mgr._url = ""
    result = mgr.get_camera_endpoints()
    assert result == []

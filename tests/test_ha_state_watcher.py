# tests/test_ha_state_watcher.py
from unittest.mock import patch, MagicMock
from core.ha_state_watcher import HAStateWatcher


def _make_watcher():
    return HAStateWatcher(poll_interval=999)  # won't loop in tests


def test_callback_fires_on_trigger_state():
    watcher = _make_watcher()
    fired = []

    def cb(entity_id, state):
        fired.append((entity_id, state))

    watcher.subscribe("binary_sensor.door", ["on"], cb)

    with patch("core.ha_state_watcher.ha_manager") as mock_ha:
        mock_ha.get_state.return_value = {"state": "on"}
        watcher._check(watcher._subscriptions[0])

    assert fired == [("binary_sensor.door", "on")]


def test_callback_does_not_fire_on_non_trigger_state():
    watcher = _make_watcher()
    fired = []
    watcher.subscribe("binary_sensor.door", ["on"], lambda eid, s: fired.append(s))

    with patch("core.ha_state_watcher.ha_manager") as mock_ha:
        mock_ha.get_state.return_value = {"state": "off"}
        watcher._check(watcher._subscriptions[0])

    assert fired == []


def test_callback_does_not_fire_twice_for_same_state():
    watcher = _make_watcher()
    fired = []
    watcher.subscribe("binary_sensor.door", ["on"], lambda eid, s: fired.append(s))
    sub = watcher._subscriptions[0]

    with patch("core.ha_state_watcher.ha_manager") as mock_ha:
        mock_ha.get_state.return_value = {"state": "on"}
        watcher._check(sub)
        watcher._check(sub)  # second call, same state

    assert len(fired) == 1


def test_empty_entity_id_is_skipped():
    watcher = _make_watcher()
    watcher.subscribe("", ["on"], lambda eid, s: None)
    assert len(watcher._subscriptions) == 0


def test_ha_unreachable_does_not_raise():
    watcher = _make_watcher()
    watcher.subscribe("binary_sensor.door", ["on"], lambda eid, s: None)

    with patch("core.ha_state_watcher.ha_manager") as mock_ha:
        mock_ha.get_state.return_value = {}
        watcher._check(watcher._subscriptions[0])  # must not raise


def test_callback_exception_does_not_crash_watcher():
    watcher = _make_watcher()

    def bad_cb(eid, s):
        raise RuntimeError("callback error")

    watcher.subscribe("binary_sensor.door", ["on"], bad_cb)
    sub = watcher._subscriptions[0]

    with patch("core.ha_state_watcher.ha_manager") as mock_ha:
        mock_ha.get_state.return_value = {"state": "on"}
        watcher._check(sub)  # must not raise despite bad_cb

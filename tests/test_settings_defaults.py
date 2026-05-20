from core.settings_store import DEFAULT_SETTINGS


def test_hidden_entities_default_is_empty_list():
    ha = DEFAULT_SETTINGS["home_assistant"]
    assert ha["hidden_entities"] == []


def test_door_watcher_defaults():
    ha = DEFAULT_SETTINGS["home_assistant"]
    assert ha["door_entity"] == ""
    assert ha["door_message"] == "🚪 Ciel un client !"
    assert ha["door_alert_enabled"] is False

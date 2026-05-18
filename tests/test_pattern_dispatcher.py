"""
15 tests for core/pattern_dispatcher.py

PatternDispatcher.match(prompt) → (action, params) | None
"""
import pytest
from core.pattern_dispatcher import PatternDispatcher, _extract_room, _extract_duration


@pytest.fixture
def pd():
    return PatternDispatcher()


# --- Light: off ---

def test_light_off_eteins(pd):
    action, params = pd.match("éteins la lumière")
    assert action == "control-light"
    assert params["action"] == "off"
    assert params["device_name"] == "all"


def test_light_off_desactive(pd):
    action, params = pd.match("désactive l'éclairage du bureau")
    assert action == "control-light"
    assert params["action"] == "off"
    assert params["device_name"] == "bureau"


def test_light_off_coupe(pd):
    action, params = pd.match("coupe les lumières du salon")
    assert action == "control-light"
    assert params["action"] == "off"
    assert params["device_name"] == "salon"


# --- Light: on ---

def test_light_on(pd):
    action, params = pd.match("allume les lumières")
    assert action == "control-light"
    assert params["action"] == "on"
    assert params["device_name"] == "all"


def test_light_on_room(pd):
    action, params = pd.match("allume la lampe du bureau")
    assert action == "control-light"
    assert params["action"] == "on"
    assert params["device_name"] == "bureau"


# --- Light: dim ---

def test_light_dim(pd):
    action, params = pd.match("baisse la lumière")
    assert action == "control-light"
    assert params["action"] == "dim"
    assert params["device_name"] == "all"
    assert params["brightness"] == 30


# --- Timer ---

def test_timer(pd):
    action, params = pd.match("minuterie de 10 minutes")
    assert action == "set-timer"
    assert "10" in params["duration"]


# --- Shell ---

def test_shell_disk(pd):
    action, params = pd.match("espace disque")
    assert action == "shell-exec"
    assert "df" in params["command"]


def test_shell_ram(pd):
    action, params = pd.match("utilisation mémoire")
    assert action == "shell-exec"
    assert "free" in params["command"]


def test_shell_cpu(pd):
    action, params = pd.match("charge cpu")
    assert action == "shell-exec"
    assert "top" in params["command"]


# --- Weather ---

def test_weather(pd):
    action, params = pd.match("météo")
    assert action == "weather"
    assert params == {}


# --- Web search ---

def test_web_search(pd):
    action, params = pd.match("cherche python tutorial")
    assert action == "web-search"
    assert "python tutorial" in params["query"]


# --- No match ---

def test_no_match_bonjour(pd):
    assert pd.match("bonjour") is None


def test_no_match_explain(pd):
    assert pd.match("explique la relativité") is None


# --- Helper functions ---

def test_room_extraction():
    assert _extract_room("la lumière du bureau est allumée") == "bureau"


def test_extract_duration_minutes():
    assert "10" in _extract_duration("minuterie de 10 minutes")


def test_extract_duration_fallback():
    # No number in text → safe default "5 minutes"
    assert _extract_duration("set a timer") == "5 minutes"

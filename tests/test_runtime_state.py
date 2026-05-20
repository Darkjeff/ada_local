"""
Tests for core/runtime_state.py.

Run: uv run python -m pytest tests/test_runtime_state.py -v
These tests mock all network/subprocess calls so they pass offline.
"""

import sys
import types
import unittest
from unittest.mock import patch, MagicMock


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_settings_mock():
    m = MagicMock()
    m.get.side_effect = lambda key, default=None: {
        "n8n.url":              "http://localhost:5678",
        "home_assistant.url":   "",
        "home_assistant.token": "",
        "navidrome":            None,
    }.get(key, default)
    return m


def _load_manager():
    """Import RuntimeStateManager avec toutes les dépendances mockées."""
    import importlib

    fake_settings = _make_settings_mock()
    config_mod = types.ModuleType("config")
    config_mod.OLLAMA_URL = "http://localhost:11434/api"
    config_mod.RESPONDER_MODEL = "qwen3:1.7b"

    settings_mod = types.ModuleType("core.settings_store")
    settings_mod.settings = fake_settings

    with patch.dict("sys.modules", {
        "config": config_mod,
        "core.settings_store": settings_mod,
    }):
        import core.runtime_state as mod
        importlib.reload(mod)
        return mod.RuntimeStateManager()


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestRuntimeStateManager(unittest.TestCase):

    def test_get_state_returns_dict_before_refresh(self):
        """get_state() doit retourner un dict valide avant tout refresh()."""
        mgr = _load_manager()
        state = mgr.get_state()
        self.assertIsInstance(state, dict)
        self.assertIn("services", state)
        self.assertIn("docker", state)
        self.assertIn("warnings", state)
        self.assertIn("updated_at", state)

    def test_format_infra_status_fr_returns_string(self):
        """format_infra_status_fr() doit retourner une string non vide."""
        mgr = _load_manager()
        text = mgr.format_infra_status_fr()
        self.assertIsInstance(text, str)
        self.assertGreater(len(text), 0)

    def test_format_after_refresh_contains_service_names(self):
        """Après refresh(), le texte formaté contient les noms des services."""
        mgr = _load_manager()

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"models": []}

        with patch("requests.get", return_value=mock_response), \
             patch("subprocess.check_output", side_effect=FileNotFoundError):
            mgr.refresh()

        text = mgr.format_infra_status_fr()
        self.assertIn("Ollama", text)
        self.assertIn("n8n", text)
        self.assertIn("Home Assistant", text)

    def test_refresh_never_raises_when_all_services_offline(self):
        """refresh() ne doit jamais lever d'exception, même si tout est hors ligne."""
        mgr = _load_manager()
        with patch("requests.get", side_effect=ConnectionError("offline")), \
             patch("subprocess.check_output", side_effect=Exception("docker absent")):
            try:
                mgr.refresh()
            except Exception as e:
                self.fail(f"refresh() a levé une exception : {e}")

        state = mgr.get_state()
        self.assertIsInstance(state, dict)
        for svc in ("ollama", "n8n", "home_assistant", "navidrome"):
            self.assertIn(
                state["services"][svc]["status"],
                ("offline", "unknown"),
                msg=f"Service {svc} devrait être offline ou unknown",
            )

    def test_get_state_structure_after_refresh(self):
        """L'état a le bon schéma après refresh()."""
        mgr = _load_manager()
        with patch("requests.get", side_effect=ConnectionError()), \
             patch("subprocess.check_output", side_effect=FileNotFoundError()):
            mgr.refresh()

        state = mgr.get_state()
        self.assertIn("ai", state)
        self.assertIn("model", state["ai"])
        self.assertIn("cuda_available", state["ai"])
        self.assertIn("voice", state)
        self.assertIn("stt", state["voice"])
        self.assertIn("tts", state["voice"])

    def test_format_infra_status_fr_never_raises_with_corrupt_state(self):
        """format_infra_status_fr() ne doit pas lever même avec un état corrompu."""
        mgr = _load_manager()
        mgr._state = {}  # Corrompt l'état délibérément
        try:
            result = mgr.format_infra_status_fr()
        except Exception as e:
            self.fail(f"format_infra_status_fr() a levé : {e}")
        self.assertIsInstance(result, str)


if __name__ == "__main__":
    unittest.main()

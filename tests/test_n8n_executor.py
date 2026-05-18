"""
9 tests for core/n8n_executor.py

N8NExecutor.call(action, params) → {success, message, data}
Never raises. Falls back to FunctionExecutor on connection failure.
"""
import threading
import time
import unittest
from unittest.mock import MagicMock, patch

import requests

from core.n8n_executor import N8NExecutor


# ---------------------------------------------------------------------------
# Helper: build a fresh executor with controlled settings (no real HTTP)
# ---------------------------------------------------------------------------

def _make_executor(url="http://localhost:5678", timeout=10.0,
                   fallback=True, cooldown=30.0) -> N8NExecutor:
    """Return a fresh N8NExecutor whose _load_settings is overridden."""
    ex = N8NExecutor.__new__(N8NExecutor)
    ex._down_since = 0.0
    ex._lock = threading.Lock()
    ex._load_settings = lambda: (f"{url}/webhook", timeout, fallback, cooldown)
    return ex


def _ok_response(payload: dict) -> MagicMock:
    resp = MagicMock()
    resp.json.return_value = payload
    resp.raise_for_status = MagicMock()
    return resp


def _http_error(status_code: int) -> requests.exceptions.HTTPError:
    resp = MagicMock()
    resp.status_code = status_code
    exc = requests.exceptions.HTTPError(response=resp)
    return exc


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestN8NExecutorCall(unittest.TestCase):

    def test_successful_call(self):
        """POST returns {success:true} → result is passed through intact."""
        ex = _make_executor()
        payload = {"success": True, "message": "Lumière éteinte", "data": None}

        with patch("requests.post", return_value=_ok_response(payload)):
            result = ex.call("control-light", {"action": "off", "device_name": "all"})

        self.assertTrue(result["success"])
        self.assertEqual(result["message"], "Lumière éteinte")
        self.assertIsNone(result["data"])

    def test_connection_error_fallback(self):
        """ConnectionError → FunctionExecutor is called, result returned."""
        ex = _make_executor(fallback=True)
        fallback_result = {"success": True, "message": "Fallback OK", "data": None}

        with patch("requests.post", side_effect=requests.exceptions.ConnectionError()):
            with patch("core.n8n_executor.N8NExecutor._fallback",
                       return_value=fallback_result) as mock_fallback:
                result = ex.call("control-light", {"action": "off", "device_name": "all"})

        mock_fallback.assert_called_once_with("control-light",
                                               {"action": "off", "device_name": "all"})
        self.assertTrue(result["success"])

    def test_timeout_fallback(self):
        """Timeout → fallback is called."""
        ex = _make_executor(fallback=True)
        fallback_result = {"success": True, "message": "Timeout fallback", "data": None}

        with patch("requests.post", side_effect=requests.exceptions.Timeout()):
            with patch("core.n8n_executor.N8NExecutor._fallback",
                       return_value=fallback_result) as mock_fallback:
                result = ex.call("set-timer", {"duration": "5 minutes"})

        mock_fallback.assert_called_once()
        self.assertTrue(result["success"])

    def test_cooldown_respected(self):
        """No HTTP request is sent while in cooldown after a previous failure."""
        ex = _make_executor(fallback=True, cooldown=30.0)
        ex._mark_down()  # sets _down_since = time.monotonic() — cooldown starts now

        with patch("requests.post") as mock_post:
            with patch("core.n8n_executor.N8NExecutor._fallback",
                       return_value={"success": False, "message": "cooldown", "data": None}):
                ex.call("control-light", {"action": "off", "device_name": "all"})

        mock_post.assert_not_called()

    def test_cooldown_expires(self):
        """After cooldown_s seconds, a new HTTP attempt is made."""
        ex = _make_executor(fallback=True, cooldown=30.0)
        ex._mark_down()
        # Rewind _down_since by 60 s so cooldown has elapsed
        ex._down_since = time.monotonic() - 60.0

        payload = {"success": True, "message": "Back online", "data": None}
        with patch("requests.post", return_value=_ok_response(payload)):
            result = ex.call("control-light", {"action": "on", "device_name": "all"})

        self.assertTrue(result["success"])

    def test_fallback_disabled(self):
        """fallback_enabled=False → clean error dict, FunctionExecutor NOT called."""
        ex = _make_executor(fallback=False)

        with patch("requests.post", side_effect=requests.exceptions.ConnectionError()):
            with patch("core.n8n_executor.N8NExecutor._fallback") as mock_fallback:
                result = ex.call("control-light", {"action": "off", "device_name": "all"})

        mock_fallback.assert_not_called()
        self.assertFalse(result["success"])
        self.assertIn("indisponible", result["message"].lower())

    def test_404_fallback(self):
        """HTTP 404 (client error) → error dict returned, no cooldown, no fallback."""
        ex = _make_executor(fallback=True)

        with patch("requests.post",
                   side_effect=_http_error(404)):
            with patch("core.n8n_executor.N8NExecutor._fallback") as mock_fallback:
                with patch.object(ex, "_mark_down") as mock_mark_down:
                    result = ex.call("control-light", {"action": "off", "device_name": "all"})

        mock_fallback.assert_not_called()
        mock_mark_down.assert_not_called()
        self.assertFalse(result["success"])
        self.assertIn("404", result["message"])

    def test_5xx_fallback(self):
        """HTTP 503 (server error) → marks down, calls fallback."""
        ex = _make_executor(fallback=True)
        fallback_result = {"success": False, "message": "503 fallback", "data": None}

        with patch("requests.post", side_effect=_http_error(503)):
            with patch("core.n8n_executor.N8NExecutor._fallback",
                       return_value=fallback_result) as mock_fallback:
                result = ex.call("control-light", {"action": "off", "device_name": "all"})

        mock_fallback.assert_called_once()
        # Executor should now be in cooldown
        _, _, _, cooldown_s = ex._load_settings()
        self.assertTrue(ex._is_in_cooldown(cooldown_s))

    def test_normalizes_response(self):
        """Non-standard n8n response is normalised to {success, message, data}."""
        ex = _make_executor()
        # n8n returns only {"ok": True, "text": "done"} — no standard keys
        with patch("requests.post",
                   return_value=_ok_response({"ok": True, "text": "done"})):
            result = ex.call("weather", {})

        self.assertIn("success", result)
        self.assertIn("message", result)
        self.assertIn("data", result)


if __name__ == "__main__":
    unittest.main()

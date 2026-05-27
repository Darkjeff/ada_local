"""
N8NExecutor — HTTP client for n8n webhooks with FunctionExecutor fallback.

Call n8n_executor.call(action, params) → {success, message, data}.
Never raises. Falls back to FunctionExecutor if n8n is unavailable.
"""

import logging
import threading
import time
from typing import Any

import requests

from core.settings_store import settings as app_settings

logger = logging.getLogger(__name__)

# Mapping: webhook action name (hyphens) → FunctionExecutor func_name (underscores)
_WEBHOOK_TO_FUNC: dict[str, str] = {
    "control-light":   "control_light",
    "set-timer":       "set_timer",
    "set-alarm":       "set_alarm",
    "web-search":      "web_search",
    "get-info":        "get_system_info",
    "calendar-event":  "create_calendar_event",
    "weather":         "weather",
}


class N8NExecutor:
    """
    HTTP client for n8n webhooks with transparent FunctionExecutor fallback.

    - POST /webhook/<action> with {"params": params}
    - Expects response: {"success": bool, "message": str, "data": Any}
    - On ConnectionError or Timeout: activates cooldown_s-second cooldown,
      falls back to FunctionExecutor for that call and the cooldown window.
    - Never raises.
    """

    def __init__(self) -> None:
        self._down_since: float = 0.0  # monotonic timestamp of last failure; 0 = healthy
        self._lock = threading.Lock()

    # ------------------------------------------------------------------
    # Settings
    # ------------------------------------------------------------------

    def _load_settings(self) -> tuple[str, float, bool, float]:
        """Return (webhook_base_url, timeout_s, fallback_enabled, cooldown_s)."""
        cfg = app_settings.get("n8n") or {}
        base_url   = cfg.get("url", "http://localhost:5678").rstrip("/") + "/webhook"
        timeout_s  = float(cfg.get("timeout_s", 10.0))
        fallback   = bool(cfg.get("fallback_enabled", True))
        cooldown_s = float(cfg.get("cooldown_s", 30.0))
        return base_url, timeout_s, fallback, cooldown_s

    # ------------------------------------------------------------------
    # Cooldown helpers
    # ------------------------------------------------------------------

    def _is_in_cooldown(self, cooldown_s: float) -> bool:
        if self._down_since == 0.0:
            return False
        return (time.monotonic() - self._down_since) < cooldown_s

    def _mark_down(self) -> None:
        """Must be called under self._lock."""
        self._down_since = time.monotonic()

    def _mark_up(self) -> None:
        """Must be called under self._lock."""
        self._down_since = 0.0

    # ------------------------------------------------------------------
    # Fallback
    # ------------------------------------------------------------------

    def _fallback(self, action: str, params: dict) -> dict:
        """Delegate to FunctionExecutor using the equivalent underscore func_name."""
        func_name = _WEBHOOK_TO_FUNC.get(action, action.replace("-", "_"))
        try:
            from core.function_executor import executor as function_executor
            return function_executor.execute(func_name, params)
        except Exception as exc:
            logger.error("[N8N] FunctionExecutor fallback failed: %s", exc)
            return {"success": False, "message": str(exc), "data": None}

    # ------------------------------------------------------------------
    # Response normalisation
    # ------------------------------------------------------------------

    @staticmethod
    def _normalize(data: Any) -> dict:
        """Ensure response has the canonical {success, message, data} shape."""
        if data is None:
            return {"success": False, "message": "Empty response from n8n", "data": None}
        if isinstance(data, dict) and "success" in data:
            return {
                "success": bool(data["success"]),
                "message": str(data.get("message", data.get("error", str(data)))),
                "data":    data.get("data"),
            }
        # Non-standard response — wrap it
        return {
            "success": True,
            "message": str(data),
            "data":    data,
        }

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    def call(self, action: str, params: dict) -> dict:
        """
        POST /webhook/<action> with {"params": params}.
        Returns {success, message, data}. Never raises.
        """
        base_url, timeout_s, fallback_enabled, cooldown_s = self._load_settings()

        # Check cooldown under lock
        with self._lock:
            in_cooldown = self._is_in_cooldown(cooldown_s)

        if in_cooldown:
            logger.debug("[N8N] Cooldown actif, skip HTTP (action=%s)", action)
            if fallback_enabled:
                return self._fallback(action, params)
            return {"success": False,
                    "message": "n8n indisponible (cooldown actif)",
                    "data": None}

        # Attempt HTTP call (outside lock — slow operation)
        logger.info("[N8N] → POST %s/%s params=%s", base_url, action, params)
        try:
            resp = requests.post(
                f"{base_url}/{action}",
                json={"params": params},
                timeout=timeout_s,
            )
            resp.raise_for_status()
            with self._lock:
                self._mark_up()
            result = self._normalize(resp.json())
            logger.info("[N8N] ← %s success=%s message=%s", action, result.get("success"), result.get("message", "")[:80])
            return result

        except (requests.exceptions.ConnectionError,
                requests.exceptions.Timeout):
            with self._lock:
                self._mark_down()
            logger.warning("[N8N] Indisponible, fallback FunctionExecutor (action=%s)", action)
            if fallback_enabled:
                return self._fallback(action, params)
            return {"success": False, "message": "n8n indisponible", "data": None}

        except requests.exceptions.HTTPError as exc:
            status = exc.response.status_code if exc.response is not None else 0
            logger.error("[N8N] HTTP %d pour action=%s", status, action)
            # Only 5xx server errors indicate n8n is down — 4xx are client-side errors
            if status >= 500:
                with self._lock:
                    self._mark_down()
                if fallback_enabled:
                    return self._fallback(action, params)
            return {"success": False, "message": f"n8n HTTP {status}", "data": None}

        except Exception as exc:
            logger.error("[N8N] Erreur inattendue (action=%s): %s", action, exc)
            return {"success": False, "message": str(exc), "data": None}


# Module-level singleton
n8n_executor = N8NExecutor()

# n8n Integration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the fragile LLM-first action dispatch in ADA with a deterministic `PatternDispatcher` + `N8NExecutor` pipeline that sends actions to n8n webhooks, with transparent fallback to `FunctionExecutor` when n8n is unavailable.

**Architecture:** `_handle_function_gemma()` first runs the user prompt through `PatternDispatcher` (regex rules, no LLM). On a match, `N8NExecutor` POSTs to the appropriate n8n webhook; if n8n is down it falls back silently to `FunctionExecutor`. Unmatched prompts continue to the existing LLM tool-calling path (qwen3), but `function_executor.execute()` is replaced by `n8n_executor.call()` there too.

**Tech Stack:** Python 3.11+, `requests`, `unittest.mock`, `pytest`, PySide6 (handlers only)

---

## File Map

| File | Action | Responsibility |
|---|---|---|
| `core/settings_store.py` | Modify line 76 | Add `n8n` block to `DEFAULT_SETTINGS` |
| `core/pattern_dispatcher.py` | **Create** | Regex rules + `_extract_room()` + `_extract_duration()` |
| `core/n8n_executor.py` | **Create** | HTTP client, 30 s cooldown, FunctionExecutor fallback |
| `gui/handlers.py` | Modify ~lines 1–14, 345–443 | Import new modules, rewire `_handle_function_gemma()` |
| `tests/test_pattern_dispatcher.py` | **Create** | 15 tests for PatternDispatcher |
| `tests/test_n8n_executor.py` | **Create** | 8 tests for N8NExecutor |

---

## Task 1 — Add `n8n` block to `DEFAULT_SETTINGS`

**Files:**
- Modify: `core/settings_store.py:71-76`

- [ ] **Step 1: Write the failing test**

Create `tests/test_n8n_settings.py`:

```python
"""Tests that the n8n settings block is present in DEFAULT_SETTINGS."""
import pytest
from core.settings_store import DEFAULT_SETTINGS


def test_n8n_block_exists():
    assert "n8n" in DEFAULT_SETTINGS


def test_n8n_url_default():
    assert DEFAULT_SETTINGS["n8n"]["url"] == "http://localhost:5678"


def test_n8n_timeout_default():
    assert DEFAULT_SETTINGS["n8n"]["timeout_s"] == 10.0


def test_n8n_fallback_default():
    assert DEFAULT_SETTINGS["n8n"]["fallback_enabled"] is True


def test_n8n_cooldown_default():
    assert DEFAULT_SETTINGS["n8n"]["cooldown_s"] == 30.0
```

- [ ] **Step 2: Run test to verify it fails**

```
pytest tests/test_n8n_settings.py -v
```

Expected: FAIL — `KeyError: 'n8n'`

- [ ] **Step 3: Add the `n8n` block to `DEFAULT_SETTINGS`**

In `core/settings_store.py`, replace the closing of `DEFAULT_SETTINGS` (currently ending at line 76–77):

```python
    "semantic_router": {
        "embedding_model": "nomic-embed-text",
        "confidence_threshold": 0.45,
        "embed_timeout_s": 5.0,
        "retry_cooldown_s": 30.0,
    }
}
```

with:

```python
    "semantic_router": {
        "embedding_model": "nomic-embed-text",
        "confidence_threshold": 0.45,
        "embed_timeout_s": 5.0,
        "retry_cooldown_s": 30.0,
    },
    "n8n": {
        "url": "http://localhost:5678",
        "timeout_s": 10.0,
        "fallback_enabled": True,
        "cooldown_s": 30.0,
    }
}
```

- [ ] **Step 4: Run test to verify it passes**

```
pytest tests/test_n8n_settings.py -v
```

Expected: 5 passed

- [ ] **Step 5: Commit**

```bash
git add core/settings_store.py tests/test_n8n_settings.py
git commit -m "feat: add n8n settings block to DEFAULT_SETTINGS"
```

---

## Task 2 — Create `core/pattern_dispatcher.py`

**Files:**
- Create: `core/pattern_dispatcher.py`
- Create: `tests/test_pattern_dispatcher.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_pattern_dispatcher.py`:

```python
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
```

- [ ] **Step 2: Run test to verify it fails**

```
pytest tests/test_pattern_dispatcher.py -v
```

Expected: FAIL — `ModuleNotFoundError: No module named 'core.pattern_dispatcher'`

- [ ] **Step 3: Create `core/pattern_dispatcher.py`**

```python
"""
PatternDispatcher — deterministic regex-based intent extraction.

Routes common user prompts to (action, params) without any LLM round-trip.
Returns None when no rule matches; the caller falls back to LLM intent parsing.
"""

import logging
import re
from typing import Optional

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Room extraction
# ---------------------------------------------------------------------------

_ROOMS = [
    "bureau", "salon", "chambre", "cuisine", "couloir",
    "salle de bain", "garage", "extérieur", "jardin", "chillout",
]


def _extract_room(text: str) -> Optional[str]:
    """Return the first known room name found in *text*, or None."""
    text_lower = text.lower()
    return next((r for r in _ROOMS if r in text_lower), None)


# ---------------------------------------------------------------------------
# Duration extraction
# ---------------------------------------------------------------------------

def _extract_duration(text: str) -> str:
    """
    Extract a human-readable duration from *text*.

    Supports French and English: '10 minutes', '2 heures', '30 secondes'.
    Falls back to '5 minutes' when nothing is recognised.
    """
    text_lower = text.lower()

    m = re.search(r"(\d+)\s*(?:heure|heures|hour|hours|h)\b", text_lower)
    if m:
        n = int(m.group(1))
        return f"{n} heure{'s' if n > 1 else ''}"

    m = re.search(r"(\d+)\s*(?:minute|minutes|min|mn)\b", text_lower)
    if m:
        n = int(m.group(1))
        return f"{n} minute{'s' if n > 1 else ''}"

    m = re.search(r"(\d+)\s*(?:seconde|secondes|second|seconds|sec|s)\b", text_lower)
    if m:
        n = int(m.group(1))
        return f"{n} seconde{'s' if n > 1 else ''}"

    return "5 minutes"


# ---------------------------------------------------------------------------
# Ordered pattern table
# (regex_str, extractor_fn(match, full_text) → (action, params))
# ---------------------------------------------------------------------------

_PATTERNS: list[tuple[str, object]] = [
    # Lights — off
    (
        r"\b(éteins?|désactiv\w+|coupe?|arrête?\s+l[ae]s?)\b.*(lumière|lampe|éclairage|led)",
        lambda m, t: ("control-light", {"action": "off",
                                         "device_name": _extract_room(t) or "all"}),
    ),
    # Lights — on
    (
        r"\b(allume?|activ\w+|mets?\s+l[ae]s?)\b.*(lumière|lampe|éclairage|led)",
        lambda m, t: ("control-light", {"action": "on",
                                         "device_name": _extract_room(t) or "all"}),
    ),
    # Lights — dim
    (
        r"\b(baisse?|réduis?|dimme?|atténue?)\b.*(lumière|lampe)",
        lambda m, t: ("control-light", {"action": "dim",
                                         "device_name": _extract_room(t) or "all",
                                         "brightness": 30}),
    ),
    # Timers
    (
        r"\b(minuterie|timer|chrono)\b",
        lambda m, t: ("set-timer", {"duration": _extract_duration(t), "label": "Timer"}),
    ),
    # Shell — disk
    (
        r"\b(espace|disque|disk|space|df|stockage|libre)\b",
        lambda m, t: ("shell-exec", {"command": "df -h"}),
    ),
    # Shell — RAM
    (
        r"\b(ram|mémoire|mémoire|memory)\b",
        lambda m, t: ("shell-exec", {"command": "free -h"}),
    ),
    # Shell — CPU
    (
        r"\b(cpu|processeur|charge\s+système|load)\b",
        lambda m, t: ("shell-exec", {"command": "top -bn1 | head -15"}),
    ),
    # Weather
    (
        r"\b(météo|temps\s+qu[''il]\s+fait|weather|température\s+extérieure)\b",
        lambda m, t: ("weather", {}),
    ),
    # Web search  — must be last (greedy group 2 captures the rest of the prompt)
    (
        r"\b(cherche?|recherche?|search|trouve?)\b\s+(.+)",
        lambda m, t: ("web-search", {"query": m.group(2).strip()}),
    ),
]

# Compile once at import time
_COMPILED: list[tuple[re.Pattern, object]] = [
    (re.compile(pattern, re.IGNORECASE | re.UNICODE), extractor)
    for pattern, extractor in _PATTERNS
]


# ---------------------------------------------------------------------------
# PatternDispatcher
# ---------------------------------------------------------------------------

class PatternDispatcher:
    """
    Deterministic regex-based intent dispatcher.

    Call match(prompt) → (action, params) or None.
    Thread-safe: stateless after module import (compiled patterns are read-only).
    """

    def match(self, prompt: str) -> Optional[tuple[str, dict]]:
        """
        Try each rule in order. Return (action, params) for the first match,
        or None if no rule applies.
        """
        if not prompt or not prompt.strip():
            return None
        for compiled_re, extractor in _COMPILED:
            m = compiled_re.search(prompt)
            if m:
                try:
                    result = extractor(m, prompt)
                    logger.debug("[PatternDispatcher] matched action=%s", result[0])
                    return result
                except Exception as exc:
                    logger.warning("[PatternDispatcher] extractor error: %s", exc)
                    continue
        return None


# Module-level singleton
pattern_dispatcher = PatternDispatcher()
```

- [ ] **Step 4: Run tests to verify they pass**

```
pytest tests/test_pattern_dispatcher.py -v
```

Expected: 17 passed (15 spec tests + 2 extra helper tests)

- [ ] **Step 5: Commit**

```bash
git add core/pattern_dispatcher.py tests/test_pattern_dispatcher.py
git commit -m "feat: add PatternDispatcher with regex rules and helper functions"
```

---

## Task 3 — Create `core/n8n_executor.py`

**Files:**
- Create: `core/n8n_executor.py`
- Create: `tests/test_n8n_executor.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_n8n_executor.py`:

```python
"""
8 tests for core/n8n_executor.py

N8NExecutor.call(action, params) → {success, message, data}
Never raises. Falls back to FunctionExecutor on connection failure.
"""
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
        """HTTP 404 → mark down and call fallback."""
        ex = _make_executor(fallback=True)
        fallback_result = {"success": False, "message": "404 fallback", "data": None}

        with patch("requests.post",
                   side_effect=_http_error(404)) as _:
            with patch("core.n8n_executor.N8NExecutor._fallback",
                       return_value=fallback_result) as mock_fallback:
                result = ex.call("control-light", {"action": "off", "device_name": "all"})

        mock_fallback.assert_called_once()

    def test_normalizes_response(self):
        """Non-standard n8n response is normalised to {success, message, data}."""
        ex = _make_executor()
        # n8n returns only {"ok": true, "text": "done"} — no standard keys
        with patch("requests.post",
                   return_value=_ok_response({"ok": True, "text": "done"})):
            result = ex.call("weather", {})

        self.assertIn("success", result)
        self.assertIn("message", result)
        self.assertIn("data", result)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run test to verify it fails**

```
pytest tests/test_n8n_executor.py -v
```

Expected: FAIL — `ModuleNotFoundError: No module named 'core.n8n_executor'`

- [ ] **Step 3: Create `core/n8n_executor.py`**

```python
"""
N8NExecutor — HTTP client for n8n webhooks with FunctionExecutor fallback.

Call n8n_executor.call(action, params) → {success, message, data}.
Never raises. Falls back to FunctionExecutor if n8n is unavailable.
"""

import logging
import time
from typing import Any, Optional

import requests

from core.settings_store import settings as app_settings

logger = logging.getLogger(__name__)

# Mapping: webhook action name (hyphens) → FunctionExecutor func_name (underscores)
_WEBHOOK_TO_FUNC: dict[str, str] = {
    "control-light":   "control_light",
    "set-timer":       "set_timer",
    "set-alarm":       "set_alarm",
    "web-search":      "web_search",
    "shell-exec":      "shell_exec",
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
        self._down_since = time.monotonic()

    def _mark_up(self) -> None:
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
        if isinstance(data, dict) and "success" in data and "message" in data:
            return {
                "success": bool(data["success"]),
                "message": str(data["message"]),
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

        # --- Cooldown active: skip HTTP, go straight to fallback ---
        if self._is_in_cooldown(cooldown_s):
            logger.debug("[N8N] Cooldown actif, skip HTTP (action=%s)", action)
            if fallback_enabled:
                return self._fallback(action, params)
            return {"success": False,
                    "message": "n8n indisponible (cooldown actif)",
                    "data": None}

        # --- Attempt HTTP call ---
        try:
            resp = requests.post(
                f"{base_url}/{action}",
                json={"params": params},
                timeout=timeout_s,
            )
            resp.raise_for_status()
            self._mark_up()
            return self._normalize(resp.json())

        except (requests.exceptions.ConnectionError,
                requests.exceptions.Timeout):
            self._mark_down()
            logger.warning("[N8N] Indisponible, fallback FunctionExecutor (action=%s)", action)
            if fallback_enabled:
                return self._fallback(action, params)
            return {"success": False, "message": "n8n indisponible", "data": None}

        except requests.exceptions.HTTPError as exc:
            status = exc.response.status_code if exc.response is not None else 0
            logger.error("[N8N] HTTP %d pour action=%s", status, action)
            self._mark_down()
            if fallback_enabled:
                return self._fallback(action, params)
            return {"success": False, "message": f"n8n HTTP {status}", "data": None}

        except Exception as exc:
            logger.error("[N8N] Erreur inattendue (action=%s): %s", action, exc)
            return {"success": False, "message": str(exc), "data": None}


# Module-level singleton
n8n_executor = N8NExecutor()
```

- [ ] **Step 4: Run tests to verify they pass**

```
pytest tests/test_n8n_executor.py -v
```

Expected: 8 passed

- [ ] **Step 5: Run full test suite to check nothing regresses**

```
pytest tests/ -v --ignore=tests/test_n8n_settings.py -q
```

Expected: all existing tests still pass

- [ ] **Step 6: Commit**

```bash
git add core/n8n_executor.py tests/test_n8n_executor.py
git commit -m "feat: add N8NExecutor with HTTP client and FunctionExecutor fallback"
```

---

## Task 4 — Wire `gui/handlers.py`

**Files:**
- Modify: `gui/handlers.py:1-14` (imports)
- Modify: `gui/handlers.py:345-443` (`_handle_function_gemma`)

The goal is to:
1. Import `pattern_dispatcher` and `n8n_executor`
2. Replace the `_direct_shell_dispatch()` call in `_handle_function_gemma()` with `PatternDispatcher.match()`
3. Replace `function_executor.execute(func_name, params)` (LLM path) with `n8n_executor.call(action, params)`

There are no new tests for handlers.py in this task — the existing test suite (`tests/test_intent_bridge.py`, etc.) provides regression coverage. Manual smoke-test instructions are provided at the end.

- [ ] **Step 1: Add imports to `gui/handlers.py`**

After line 12 (`from core.function_executor import executor as function_executor`), add:

```python
from core.pattern_dispatcher import pattern_dispatcher
from core.n8n_executor import n8n_executor
```

The top of the file becomes:

```python
from PySide6.QtCore import QObject, Signal, QThread, QTimer
import json
import re

from config import RESPONDER_MODEL, OLLAMA_URL, MAX_HISTORY, FUNCTIONS
from core.llm import http_session
from core.tts import tts, SentenceBuffer
from core.history import history_manager
from core.model_manager import ensure_exclusive_qwen
from core.model_persistence import ensure_qwen_loaded, mark_qwen_used
from core.settings_store import settings as app_settings
from core.function_executor import executor as function_executor
from core.pattern_dispatcher import pattern_dispatcher
from core.n8n_executor import n8n_executor
from core.skill_manager import skill_manager
from core.memory_store import memory_store
```

- [ ] **Step 2: Replace `_handle_function_gemma()` body**

The current method (lines 345–443) is reproduced here for reference, then the new version follows.

**Current version (for reference — do not keep):**
```python
def _handle_function_gemma(self):
    """Use direct pattern dispatch first, then Ollama tool-calling as fallback."""
    self.status.emit("Dispatching...")

    # Fast path: rule-based shell dispatch (no LLM round-trip needed)
    if self._direct_shell_dispatch():
        return
    # … LLM code … function_executor.execute(func_name, params) …
```

**New version — replace the entire method body:**

```python
def _handle_function_gemma(self):
    """
    Intent dispatch pipeline:
    1. PatternDispatcher  — deterministic regex, <1 ms, no LLM
    2. N8NExecutor        — POST to n8n webhook; falls back to FunctionExecutor
    3. LLM (qwen3)        — fallback for ambiguous prompts
    """
    self.status.emit("Dispatching...")

    # --- 1. PatternDispatcher fast path ---
    matched = pattern_dispatcher.match(self.user_text)
    if matched:
        action, params = matched
        self.status.emit(f"Executing {action}...")

        if action == "web-search":
            self.search_start.emit(params.get("query", ""))

        result = n8n_executor.call(action, params)

        if action == "web-search":
            self.search_end.emit()

        self.toast.emit(result["message"][:120], result["success"])

        # Emit Qt signals for side-effects that require UI updates
        func_name = action.replace("-", "_")   # e.g. "set-timer" → "set_timer"
        if action == "set-timer" and result["success"]:
            seconds = result.get("data", {}).get("seconds", 0) if result.get("data") else 0
            label   = result.get("data", {}).get("label", "Timer") if result.get("data") else "Timer"
            self.set_timer_signal.emit(seconds, label)
        elif action == "set-alarm" and result["success"]:
            self.reload_alarms.emit()
        elif action == "calendar-event" and result["success"]:
            self.reload_calendar.emit()

        self._generate_response_with_context(func_name, result, action == "web-search")
        return

    # --- 2. LLM tool-calling path (qwen3) ---
    ollama_url = app_settings.get("ollama_url", OLLAMA_URL)
    model = app_settings.get("models.chat", RESPONDER_MODEL)

    try:
        ensure_qwen_loaded()
        mark_qwen_used()
        resp = http_session.post(
            f"{ollama_url}/api/chat",
            json={
                "model": model,
                "messages": [
                    {
                        "role": "system",
                        "content": (
                            "You are a smart home function dispatcher. "
                            "You MUST always call one of the available tools — NEVER respond with plain text.\n\n"
                            "Tool selection rules:\n"
                            "- control_light: for ANY request involving lights, lamps, LEDs, or room lighting "
                            "(French: lumière, lampe, éclairage, led, allume, éteins, désactive, coupe, baisse). "
                            "Use action='off' for off/éteins/désactive/coupe/arrête, "
                            "action='on' for on/allume/active/mets, "
                            "action='dim' for dim/baisse/réduis. "
                            "Set device_name to the room or device mentioned (e.g. 'bureau', 'salon', 'chambre'), "
                            "or 'all' if no specific device is mentioned.\n"
                            "- set_timer: for countdown timers (minuterie, timer, dans X minutes).\n"
                            "- shell_exec: for system commands — disk space (df -h), RAM (free -h), "
                            "CPU (top -bn1), processes (ps aux), network (ip addr), etc.\n"
                            "- web_search: for internet searches.\n"
                            "- passthrough: ONLY for greetings, chitchat, or questions needing no action.\n\n"
                            "Examples:\n"
                            "- 'éteins la lumière' → control_light(action='off', device_name='all')\n"
                            "- 'désactive l\\'éclairage du bureau' → control_light(action='off', device_name='bureau')\n"
                            "- 'allume les lumières du salon' → control_light(action='on', device_name='salon')\n"
                            "- 'baisse la lumière' → control_light(action='dim', device_name='all', brightness=30)\n"
                            "- 'coupe tout' → control_light(action='off', device_name='all')\n"
                            "- 'set a 5 minute timer' → set_timer(duration='5 minutes')\n"
                            "- 'espace disque' → shell_exec(command='df -h')"
                        ),
                    },
                    {"role": "user", "content": self.user_text},
                ],
                "tools": FUNCTIONS,
                "stream": False,
                "think": False,
            },
            timeout=90,
        )
        resp.raise_for_status()
        msg = resp.json().get("message", {})
        tool_calls = msg.get("tool_calls", [])
    except Exception as e:
        print(f"[FunctionGemma] Tool-call failed: {e}")
        self._stream_qwen_response(False)
        return

    if not tool_calls:
        self._stream_qwen_response(False)
        return

    call = tool_calls[0]
    func_name = call["function"]["name"]
    params    = call["function"].get("arguments", {})

    if func_name == "passthrough":
        self._stream_qwen_response(bool(params.get("thinking", False)))
        return

    self.status.emit(f"Executing {func_name}...")

    # Convert LLM func_name (underscores) to n8n action (hyphens)
    action = func_name.replace("_", "-")

    if func_name == "web_search":
        self.search_start.emit(params.get("query", ""))

    result = n8n_executor.call(action, params)

    if func_name == "web_search":
        self.search_end.emit()

    if func_name in ACTION_FUNCTIONS:
        self.toast.emit(result["message"], result["success"])

    if func_name == "set_timer" and result["success"]:
        seconds = result.get("data", {}).get("seconds", 0) if result.get("data") else 0
        label   = result.get("data", {}).get("label", "Timer") if result.get("data") else "Timer"
        self.set_timer_signal.emit(seconds, label)
    elif func_name == "set_alarm" and result["success"]:
        self.reload_alarms.emit()
    elif func_name == "create_calendar_event" and result["success"]:
        self.reload_calendar.emit()

    enable_thinking = (func_name == "web_search")
    self._generate_response_with_context(func_name, result, enable_thinking)
```

- [ ] **Step 3: Run the full test suite**

```
pytest tests/ -q
```

Expected: all tests pass (the test suite does not import gui/handlers.py directly, so no PySide6 dependency issues)

- [ ] **Step 4: Smoke test on Ubuntu**

Start ADA on the Ubuntu machine. Say the following prompts and verify the response:

| Prompt | Expected status bar | Expected toast |
|--------|--------------------|----|
| `éteins la lumière` | `Executing control-light...` | "Lumière éteinte" (or FunctionExecutor fallback) |
| `espace disque` | `Executing shell-exec...` | disk usage summary |
| `minuterie de 5 minutes` | `Executing set-timer...` | timer confirmation |
| `bonjour` | `Routing...` | none (goes to qwen_basic) |

- [ ] **Step 5: Commit**

```bash
git add gui/handlers.py
git commit -m "feat: wire PatternDispatcher and N8NExecutor into _handle_function_gemma"
```

---

## Self-Review

### 1. Spec coverage

| Spec requirement | Task |
|---|---|
| `PatternDispatcher` with 9 regex rules | Task 2 |
| `_extract_room()` | Task 2 |
| `_extract_duration()` | Task 2 |
| `N8NExecutor.call()` — POST webhook | Task 3 |
| Cooldown 30 s after failure | Task 3 |
| Fallback to FunctionExecutor | Task 3 |
| `fallback_enabled` setting | Tasks 1 + 3 |
| `n8n` settings block | Task 1 |
| `_handle_function_gemma()` uses PatternDispatcher + N8NExecutor | Task 4 |
| LLM path also uses N8NExecutor | Task 4 |
| 15 PatternDispatcher tests | Task 2 |
| 8 N8NExecutor tests | Task 3 |

All spec requirements covered. ✅

### 2. Type consistency

- `PatternDispatcher.match()` → `Optional[tuple[str, dict]]` — used correctly in Task 4
- `N8NExecutor.call()` → `dict` with keys `success`, `message`, `data` — consistent with `_generate_response_with_context()` expectations
- `action.replace("-", "_")` → `func_name` for signal dispatch and `_generate_response_with_context()` — consistent throughout Task 4
- `_WEBHOOK_TO_FUNC` keys all use hyphens, values all use underscores — consistent with PatternDispatcher action names and FunctionExecutor func_names

### 3. Edge cases noted

- `weather` is not natively supported by FunctionExecutor (`Unknown function: weather`). When n8n is down and `weather` is requested, the fallback returns `{success: False, message: "Unknown function: weather"}`. This is acceptable — weather requires n8n.
- `_direct_shell_dispatch()` remains in the codebase as a private method (it's never called after Task 4). It can be deleted in a future cleanup PR.

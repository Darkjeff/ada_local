# ADA Senses — Remote Voice Endpoints Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Extend ADA Senses to support remote voice/speaker endpoints — Home Assistant media players for TTS output and external voice assistants (Alexa, Google Home) as intent-only inputs — with a new SensesManager device registry, IntentBridge placeholder, HA TTS service calls, extended settings, and an updated Senses UI section.

**Architecture:** A new `SensesManager` singleton maintains a typed registry of all voice endpoints (local mic, local speaker, HA media players, intent-only assistants). Speech output is dispatched through `send_speech()` which routes to local TTS or HA `tts.speak` depending on settings. External voice assistants (Alexa, Google Home) are registered as `intent_input` only — ADA never accesses their raw audio. `IntentBridge` normalizes and routes text intents received from these sources.

**Tech Stack:** Python 3.12, PySide6 6.x, qfluentwidgets, requests (already used in ha_control.py), unittest + unittest.mock

---

## File Structure

| Action | File | Responsibility |
|--------|------|----------------|
| CREATE | `core/senses_manager.py` | Device registry, speech dispatch, intent routing |
| CREATE | `core/intent_bridge.py` | Intent normalization + routing placeholder |
| MODIFY | `core/ha_control.py` | Add `get_media_player_entities()` + `speak_to_media_player()` |
| MODIFY | `core/settings_store.py` | New HA TTS keys + senses speech output keys |
| MODIFY | `locales/en.json` | ~19 new i18n keys for remote endpoints UI |
| MODIFY | `locales/fr.json` | French translations of the same 19 keys |
| MODIFY | `gui/tabs/senses.py` | New Remote Endpoints section + 4 new card classes |
| CREATE | `tests/test_senses_manager.py` | Registry + speech dispatch tests |
| CREATE | `tests/test_intent_bridge.py` | Intent normalization tests |
| CREATE | `tests/test_ha_tts.py` | HA TTS method tests |
| CREATE | `tests/test_remote_endpoints_settings.py` | New settings defaults tests |
| MODIFY | `tests/test_senses_settings.py` | Fix `test_all_values_are_integers` (breaks with new string settings) |

---

## Context for Implementers

### Codebase Patterns

**Settings:** `core/settings_store.py` exports a singleton `settings`. Access: `settings.get("senses.camera_index", 0)`, `settings.set("senses.camera_index", 2)`. DEFAULT_SETTINGS is a nested dict at top of file.

**i18n:** `core/i18n.py` exports `tr(key)` and singleton `i18n`. Key format: `"section.key"` maps to `locales/en.json` → `{"section": {"key": "..."}}`. Language changes emit `i18n.language_changed` signal.

**HA client:** `core/ha_control.py` exports `ha_manager` singleton of class `HAManager`. Pattern for new methods: same as existing `get_camera_entities()` — filter `_raw_entities` or call `_fetch_all_states()`, return dict. Service calls use `call_service(domain, service, entity_id, **kwargs)` or direct `requests.post`.

**Tests:** Standard `unittest.TestCase`. Add `sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))` at top. For `core/` direct imports, also add `sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../core')))`. Avoid importing PySide6 in tests. Patch module attributes for isolation.

**SensesTab:** `gui/tabs/senses.py` — `SensesTab(ScrollArea)`. Cards are `SettingCard` subclasses added to `SettingCardGroup`s, which are added to `ExpandLayout`. Background probes use `QThread` subclasses. `retranslate_ui()` updates all text in-place when language changes.

---

## Task 1: SensesManager Device Registry

**Files:**
- Create: `core/senses_manager.py`
- Create: `tests/test_senses_manager.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_senses_manager.py`:

```python
"""
Tests for core/senses_manager.py — device registry and can_* checks.

Run: python -m pytest tests/test_senses_manager.py -v
  or: python -m unittest tests.test_senses_manager -v
"""
import sys
import os
import unittest
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))


def make_manager():
    """Return a fresh SensesManager (not the global singleton)."""
    from core.senses_manager import SensesManager
    return SensesManager()


class TestRegistry(unittest.TestCase):

    def test_default_devices_registered(self):
        """SensesManager registers local_mic and local_speaker by default."""
        sm = make_manager()
        ids = {d["id"] for d in sm.get_devices()}
        self.assertIn("local_mic", ids)
        self.assertIn("local_speaker", ids)

    def test_register_device_adds_entry(self):
        """register_device() adds a new device to the registry."""
        sm = make_manager()
        sm.register_device({
            "id": "test_device",
            "name": "Test Player",
            "device_type": "speech_output",
            "source": "home_assistant",
            "privacy": "local_or_cloud_dependent",
            "enabled": True,
            "entity_id": "media_player.test",
        })
        ids = {d["id"] for d in sm.get_devices()}
        self.assertIn("test_device", ids)

    def test_register_device_replaces_existing_by_id(self):
        """register_device() replaces an existing device with the same id."""
        sm = make_manager()
        sm.register_device({
            "id": "local_mic",
            "name": "Updated Mic",
            "device_type": "raw_audio",
            "source": "local",
            "privacy": "local",
            "enabled": True,
            "entity_id": None,
        })
        mics = sm.get_raw_audio_inputs()
        self.assertEqual(len(mics), 1)
        self.assertEqual(mics[0]["name"], "Updated Mic")

    def test_get_devices_returns_all_when_no_filter(self):
        """get_devices() with no argument returns all registered devices."""
        sm = make_manager()
        result = sm.get_devices()
        self.assertIsInstance(result, list)
        self.assertGreaterEqual(len(result), 2)

    def test_get_devices_filters_by_type(self):
        """get_devices('speech_output') returns only speech_output devices."""
        sm = make_manager()
        result = sm.get_devices("speech_output")
        self.assertTrue(all(d["device_type"] == "speech_output" for d in result))

    def test_get_speech_outputs_matches_filter(self):
        """get_speech_outputs() == get_devices('speech_output')."""
        sm = make_manager()
        self.assertEqual(sm.get_speech_outputs(), sm.get_devices("speech_output"))

    def test_get_intent_inputs_empty_by_default(self):
        """No intent_input devices registered in default state."""
        sm = make_manager()
        self.assertEqual(sm.get_intent_inputs(), [])

    def test_get_raw_audio_inputs_contains_local_mic(self):
        """local_mic is in raw_audio inputs by default."""
        sm = make_manager()
        ids = {d["id"] for d in sm.get_raw_audio_inputs()}
        self.assertIn("local_mic", ids)

    def test_can_receive_intent_false_with_no_intent_devices(self):
        """can_receive_intent() is False when no intent_input devices exist."""
        sm = make_manager()
        self.assertFalse(sm.can_receive_intent())

    def test_can_receive_intent_true_when_intent_device_enabled(self):
        """can_receive_intent() is True when an enabled intent_input exists."""
        sm = make_manager()
        sm.register_device({
            "id": "alexa_intent",
            "name": "Alexa",
            "device_type": "intent_input",
            "source": "alexa",
            "privacy": "cloud_dependent",
            "enabled": True,
            "entity_id": None,
        })
        self.assertTrue(sm.can_receive_intent())

    def test_can_receive_intent_false_when_disabled(self):
        """can_receive_intent() is False when the intent_input device is disabled."""
        sm = make_manager()
        sm.register_device({
            "id": "alexa_intent",
            "name": "Alexa",
            "device_type": "intent_input",
            "source": "alexa",
            "privacy": "cloud_dependent",
            "enabled": False,
            "entity_id": None,
        })
        self.assertFalse(sm.can_receive_intent())

    def test_can_send_speech_true_by_default(self):
        """can_send_speech() is True by default (local_speaker is registered)."""
        sm = make_manager()
        self.assertTrue(sm.can_send_speech())

    def test_local_mic_is_raw_audio(self):
        """local_mic has device_type 'raw_audio'."""
        sm = make_manager()
        mic = next(d for d in sm.get_devices() if d["id"] == "local_mic")
        self.assertEqual(mic["device_type"], "raw_audio")

    def test_local_speaker_is_speech_output(self):
        """local_speaker has device_type 'speech_output'."""
        sm = make_manager()
        speaker = next(d for d in sm.get_devices() if d["id"] == "local_speaker")
        self.assertEqual(speaker["device_type"], "speech_output")

    def test_local_devices_have_local_privacy(self):
        """Both default local devices have privacy='local'."""
        sm = make_manager()
        local_devices = [d for d in sm.get_devices() if d["source"] == "local"]
        for d in local_devices:
            self.assertEqual(d["privacy"], "local", f"{d['id']} should have local privacy")


if __name__ == '__main__':
    unittest.main()
```

- [ ] **Step 2: Run tests to confirm they fail**

```bash
cd C:/wamp64/www/ada_local
python -m pytest tests/test_senses_manager.py -v
```

Expected: `ModuleNotFoundError: No module named 'core.senses_manager'`

- [ ] **Step 3: Create `core/senses_manager.py`**

```python
"""
SensesManager — central registry of all ADA voice input/output endpoints.

Device types:
  raw_audio    — direct microphone access (local hardware only)
  intent_input — external voice assistant that sends normalized text intents
                 (Alexa, Google Home via HA automation — NO raw mic access)
  speech_output — TTS output target (local speaker, HA media_player)

Privacy levels:
  local                    — stays on device
  cloud_dependent          — requires cloud service (Amazon, Google)
  local_or_cloud_dependent — HA device (depends on user's HA configuration)

Privacy guarantee: intent_input devices never expose raw audio to ADA.
External assistants transcribe locally then forward text only.
"""
from __future__ import annotations

from typing import Literal

from core.settings_store import settings

DeviceType = Literal["raw_audio", "intent_input", "speech_output"]
PrivacyLevel = Literal["local", "cloud_dependent", "local_or_cloud_dependent"]
DeviceSource = Literal["local", "home_assistant", "google_home", "alexa", "ada_satellite"]


class SensesDevice(dict):
    """
    Typed dict representing one sensory endpoint.

    Required keys:
      id          (str)  — unique identifier within this registry
      name        (str)  — human-readable display name
      device_type (str)  — "raw_audio" | "intent_input" | "speech_output"
      source      (str)  — "local" | "home_assistant" | "google_home" | "alexa" | "ada_satellite"
      privacy     (str)  — "local" | "cloud_dependent" | "local_or_cloud_dependent"
      enabled     (bool) — whether the device is active
      entity_id   (str|None) — HA entity_id for home_assistant devices, else None
    """


class SensesManager:
    """
    Registry of all sensory endpoints. Manages speech dispatch and intent routing.

    Usage:
        from core.senses_manager import senses_manager
        senses_manager.send_speech("Hello!")
        senses_manager.register_device({...})
    """

    def __init__(self):
        self._devices: list[SensesDevice] = []
        self._register_defaults()

    def _register_defaults(self) -> None:
        """Register built-in local devices present in every ADA installation."""
        self.register_device({
            "id": "local_mic",
            "name": "Local Microphone",
            "device_type": "raw_audio",
            "source": "local",
            "privacy": "local",
            "enabled": True,
            "entity_id": None,
        })
        self.register_device({
            "id": "local_speaker",
            "name": "Local Speaker",
            "device_type": "speech_output",
            "source": "local",
            "privacy": "local",
            "enabled": True,
            "entity_id": None,
        })

    # ── Registry ───────────────────────────────────────────────────────────

    def register_device(self, device: SensesDevice) -> None:
        """Add or replace a device by id."""
        self._devices = [d for d in self._devices if d["id"] != device["id"]]
        self._devices.append(device)

    def get_devices(self, device_type: DeviceType | None = None) -> list[SensesDevice]:
        """Return all registered devices, optionally filtered by type."""
        if device_type is None:
            return list(self._devices)
        return [d for d in self._devices if d["device_type"] == device_type]

    def get_speech_outputs(self) -> list[SensesDevice]:
        """Return all speech_output devices."""
        return self.get_devices("speech_output")

    def get_intent_inputs(self) -> list[SensesDevice]:
        """Return all intent_input devices."""
        return self.get_devices("intent_input")

    def get_raw_audio_inputs(self) -> list[SensesDevice]:
        """Return all raw_audio devices."""
        return self.get_devices("raw_audio")

    # ── Capability checks ──────────────────────────────────────────────────

    def can_receive_intent(self) -> bool:
        """True if at least one enabled intent_input device is registered."""
        return any(d["enabled"] for d in self.get_intent_inputs())

    def can_send_speech(self) -> bool:
        """True if at least one enabled speech_output device is registered."""
        return any(d["enabled"] for d in self.get_speech_outputs())

    # ── Speech dispatch ────────────────────────────────────────────────────

    def send_speech(self, text: str, target_id: str | None = None) -> bool:
        """
        Dispatch TTS text to an output device.

        If target_id is None, the configured speech_output_mode from settings
        determines the target:
          - "local"          → "local_speaker"
          - "ha_media_player" → device id from settings key "senses.ha_tts_entity"

        Returns True if dispatched successfully, False otherwise.
        """
        if target_id is None:
            mode = settings.get("senses.speech_output_mode", "local")
            if mode == "ha_media_player":
                target_id = settings.get("senses.ha_tts_entity", "")
                if not target_id:
                    target_id = "local_speaker"
            else:
                target_id = "local_speaker"

        devices = [d for d in self._devices if d["id"] == target_id]
        if not devices:
            print(f"[SensesManager] Unknown target device: {target_id!r}")
            return False

        device = devices[0]
        if not device["enabled"]:
            print(f"[SensesManager] Target device is disabled: {target_id!r}")
            return False

        if device["source"] == "local":
            return self._send_local_speech(text)
        elif device["source"] == "home_assistant":
            return self._send_ha_speech(text, device["entity_id"])
        else:
            print(f"[SensesManager] Unsupported source for speech: {device['source']!r}")
            return False

    def _send_local_speech(self, text: str) -> bool:
        """Dispatch to local TTS engine."""
        try:
            from core.tts import tts
            tts.speak(text)
            return True
        except Exception as e:
            print(f"[SensesManager] Local TTS failed: {e}")
            return False

    def _send_ha_speech(self, text: str, entity_id: str | None) -> bool:
        """Dispatch to HA media_player via tts.speak service."""
        if not entity_id:
            print("[SensesManager] No HA entity_id configured for speech output")
            return False
        try:
            from core.ha_control import ha_manager
            tts_service = settings.get("home_assistant.tts_service", "tts.piper")
            return ha_manager.speak_to_media_player(entity_id, text, tts_service=tts_service)
        except Exception as e:
            print(f"[SensesManager] HA TTS dispatch failed: {e}")
            return False

    # ── Intent routing ─────────────────────────────────────────────────────

    def receive_external_intent(self, source: str, intent_text: str) -> None:
        """
        Called when an external voice assistant sends a text intent.

        Validates that the source is a registered, enabled intent_input device.
        If valid, routes to IntentBridge for processing.

        Privacy: this method only accepts text — never raw audio.
        """
        valid_sources = {d["source"] for d in self.get_intent_inputs() if d["enabled"]}
        if source not in valid_sources:
            print(f"[SensesManager] Rejected intent from unregistered source: {source!r}")
            return
        from core.intent_bridge import intent_bridge
        intent_bridge.route_intent(intent_text)


# Global singleton
senses_manager = SensesManager()
```

- [ ] **Step 4: Run tests — confirm they pass**

```bash
python -m pytest tests/test_senses_manager.py -v
```

Expected: `15 passed`

- [ ] **Step 5: Commit**

```bash
git add core/senses_manager.py tests/test_senses_manager.py
git commit -m "feat: add SensesManager device registry with speech dispatch and intent routing"
```

---

## Task 2: HA Media Player TTS in `ha_control.py`

**Files:**
- Modify: `core/ha_control.py` (add two methods to `HAManager`)
- Create: `tests/test_ha_tts.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_ha_tts.py`:

```python
"""
Tests for HA media player discovery and TTS dispatch in core/ha_control.py.

Run: python -m pytest tests/test_ha_tts.py -v
"""
import sys
import os
import unittest
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))


class TestGetMediaPlayerEntities(unittest.TestCase):

    def _make_manager(self):
        """Create an HAManager without triggering network calls."""
        with patch('core.settings_store.settings') as mock_s:
            mock_s.get.return_value = ""
            from core.ha_control import HAManager
            return HAManager()

    def test_returns_only_media_player_entities(self):
        """get_media_player_entities() filters to only media_player domain."""
        mgr = self._make_manager()
        mgr._raw_entities = {
            "media_player.living_room": {"entity_id": "media_player.living_room", "state": "idle",
                                          "attributes": {"friendly_name": "Living Room"}},
            "light.kitchen": {"entity_id": "light.kitchen", "state": "on",
                               "attributes": {}},
            "media_player.bedroom": {"entity_id": "media_player.bedroom", "state": "playing",
                                      "attributes": {"friendly_name": "Bedroom"}},
        }
        result = mgr.get_media_player_entities()
        self.assertEqual(set(result.keys()), {"media_player.living_room", "media_player.bedroom"})

    def test_returns_empty_when_no_media_players(self):
        """get_media_player_entities() returns {} when no media_player entities exist."""
        mgr = self._make_manager()
        mgr._raw_entities = {
            "light.kitchen": {"entity_id": "light.kitchen", "state": "on", "attributes": {}},
        }
        result = mgr.get_media_player_entities()
        self.assertEqual(result, {})

    def test_returns_empty_when_not_configured(self):
        """get_media_player_entities() returns {} when HA URL/token are empty."""
        mgr = self._make_manager()
        mgr._raw_entities = {}
        mgr._url = ""
        mgr._token = ""
        result = mgr.get_media_player_entities()
        self.assertEqual(result, {})

    def test_reuses_raw_entities_cache(self):
        """get_media_player_entities() uses _raw_entities cache, no HTTP call."""
        mgr = self._make_manager()
        mgr._raw_entities = {
            "media_player.test": {"entity_id": "media_player.test", "state": "idle",
                                   "attributes": {}}
        }
        with patch.object(mgr, '_fetch_all_states') as mock_fetch:
            mgr.get_media_player_entities()
        mock_fetch.assert_not_called()


class TestSpeakToMediaPlayer(unittest.TestCase):

    def _make_configured_manager(self):
        """Create an HAManager with URL and token set."""
        with patch('core.settings_store.settings') as mock_s:
            mock_s.get.return_value = ""
            from core.ha_control import HAManager
            mgr = HAManager()
        mgr._url = "http://homeassistant.local:8123"
        mgr._token = "test_token_abc"
        return mgr

    def test_returns_true_on_success(self):
        """speak_to_media_player() returns True when HA responds 200."""
        mgr = self._make_configured_manager()
        mock_resp = MagicMock(status_code=200)
        with patch("requests.post", return_value=mock_resp):
            result = mgr.speak_to_media_player("media_player.living_room", "Hello ADA")
        self.assertTrue(result)

    def test_posts_to_tts_speak_endpoint(self):
        """speak_to_media_player() POSTs to /api/services/tts/speak."""
        mgr = self._make_configured_manager()
        mock_resp = MagicMock(status_code=200)
        with patch("requests.post", return_value=mock_resp) as mock_post:
            mgr.speak_to_media_player("media_player.living_room", "Hello")
        url = mock_post.call_args[0][0]
        self.assertIn("tts/speak", url)
        self.assertIn("api/services", url)

    def test_payload_contains_message_and_entity(self):
        """POST payload has correct message and media_player_entity_id."""
        mgr = self._make_configured_manager()
        mock_resp = MagicMock(status_code=200)
        with patch("requests.post", return_value=mock_resp) as mock_post:
            mgr.speak_to_media_player("media_player.bedroom", "Test phrase")
        payload = mock_post.call_args[1]["json"]
        self.assertEqual(payload["message"], "Test phrase")
        self.assertEqual(payload["media_player_entity_id"], "media_player.bedroom")

    def test_uses_default_tts_service(self):
        """Default tts_service is tts.piper (entity_id in payload)."""
        mgr = self._make_configured_manager()
        mock_resp = MagicMock(status_code=200)
        with patch("requests.post", return_value=mock_resp) as mock_post:
            mgr.speak_to_media_player("media_player.test", "Hello")
        payload = mock_post.call_args[1]["json"]
        self.assertEqual(payload["entity_id"], "tts.piper")

    def test_uses_custom_tts_service(self):
        """tts_service parameter overrides the default."""
        mgr = self._make_configured_manager()
        mock_resp = MagicMock(status_code=200)
        with patch("requests.post", return_value=mock_resp) as mock_post:
            mgr.speak_to_media_player("media_player.test", "Hello",
                                       tts_service="tts.google_translate")
        payload = mock_post.call_args[1]["json"]
        self.assertEqual(payload["entity_id"], "tts.google_translate")

    def test_returns_false_without_config(self):
        """speak_to_media_player() returns False when URL or token is empty."""
        with patch('core.settings_store.settings') as mock_s:
            mock_s.get.return_value = ""
            from core.ha_control import HAManager
            mgr = HAManager()
        mgr._url = ""
        mgr._token = ""
        result = mgr.speak_to_media_player("media_player.test", "Hello")
        self.assertFalse(result)

    def test_returns_false_on_http_error(self):
        """speak_to_media_player() returns False on non-200 HTTP response."""
        mgr = self._make_configured_manager()
        mock_resp = MagicMock(status_code=500)
        with patch("requests.post", return_value=mock_resp):
            result = mgr.speak_to_media_player("media_player.test", "Hello")
        self.assertFalse(result)

    def test_returns_false_on_network_exception(self):
        """speak_to_media_player() returns False when requests raises."""
        mgr = self._make_configured_manager()
        with patch("requests.post", side_effect=Exception("Connection refused")):
            result = mgr.speak_to_media_player("media_player.test", "Hello")
        self.assertFalse(result)


if __name__ == '__main__':
    unittest.main()
```

- [ ] **Step 2: Run tests — confirm they fail**

```bash
python -m pytest tests/test_ha_tts.py -v
```

Expected: `AttributeError: 'HAManager' object has no attribute 'get_media_player_entities'`

- [ ] **Step 3: Add the two methods to `HAManager` in `core/ha_control.py`**

In `core/ha_control.py`, after the `get_camera_entities()` method (around line 149, before `get_camera_snapshot()`), insert:

```python
    def get_media_player_entities(self) -> dict[str, Any]:
        """
        Returns media_player entities suitable as TTS output targets.
        Reuses _raw_entities cache if already populated by get_entities().
        """
        raw = self._raw_entities or self._fetch_all_states()
        return {
            eid: info for eid, info in raw.items()
            if eid.split(".")[0] == "media_player"
        }

    def speak_to_media_player(
        self, entity_id: str, text: str, tts_service: str = "tts.piper"
    ) -> bool:
        """
        Send TTS speech to a media_player entity via HA's tts.speak service.

        Uses POST /api/services/tts/speak with the following payload:
          entity_id              — the TTS engine entity (e.g. "tts.piper")
          media_player_entity_id — the output target (e.g. "media_player.living_room")
          message                — the text to speak

        Args:
            entity_id:   HA media_player entity to speak through
            text:        Text to synthesize and play
            tts_service: HA TTS engine entity_id (default: "tts.piper")

        Returns True on success, False on any error.
        """
        if not self._url or not self._token:
            return False
        try:
            payload = {
                "entity_id": tts_service,
                "media_player_entity_id": entity_id,
                "message": text,
            }
            resp = requests.post(
                f"{self._url}/api/services/tts/speak",
                headers=self._headers(),
                json=payload,
                timeout=10,
            )
            if resp.status_code not in (200, 201):
                print(
                    f"[HAManager] speak_to_media_player HTTP {resp.status_code} "
                    f"for {entity_id!r}"
                )
                return False
            return True
        except Exception as e:
            print(f"[HAManager] speak_to_media_player({entity_id!r}) failed: {e}")
            return False
```

- [ ] **Step 4: Run tests — confirm they pass**

```bash
python -m pytest tests/test_ha_tts.py -v
```

Expected: `8 passed`

- [ ] **Step 5: Commit**

```bash
git add core/ha_control.py tests/test_ha_tts.py
git commit -m "feat: add get_media_player_entities and speak_to_media_player to HAManager"
```

---

## Task 3: Settings Extension for Remote Endpoints

**Files:**
- Modify: `core/settings_store.py` (extend DEFAULT_SETTINGS)
- Modify: `tests/test_senses_settings.py` (fix broken test)
- Create: `tests/test_remote_endpoints_settings.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_remote_endpoints_settings.py`:

```python
"""
Tests for new remote endpoints settings defaults.

Run: python -m pytest tests/test_remote_endpoints_settings.py -v
"""
import sys
import os
import ast
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))


def _get_defaults() -> dict:
    settings_file = os.path.join(os.path.dirname(__file__), '..', 'core', 'settings_store.py')
    with open(settings_file, 'r', encoding='utf-8') as f:
        tree = ast.parse(f.read())
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id == 'DEFAULT_SETTINGS':
                    return ast.literal_eval(node.value)
    raise RuntimeError("DEFAULT_SETTINGS not found")


class TestHATTSDefaults(unittest.TestCase):

    def test_ha_tts_service_default(self):
        """home_assistant.tts_service defaults to 'tts.piper'."""
        defaults = _get_defaults()
        self.assertEqual(defaults["home_assistant"]["tts_service"], "tts.piper")

    def test_ha_tts_target_entity_default(self):
        """home_assistant.tts_target_entity defaults to empty string."""
        defaults = _get_defaults()
        self.assertEqual(defaults["home_assistant"]["tts_target_entity"], "")

    def test_ha_tts_service_is_string(self):
        """home_assistant.tts_service is a string."""
        defaults = _get_defaults()
        self.assertIsInstance(defaults["home_assistant"]["tts_service"], str)


class TestSensesSpeechOutputDefaults(unittest.TestCase):

    def test_speech_output_mode_default(self):
        """senses.speech_output_mode defaults to 'local'."""
        defaults = _get_defaults()
        self.assertEqual(defaults["senses"]["speech_output_mode"], "local")

    def test_ha_tts_entity_default(self):
        """senses.ha_tts_entity defaults to empty string."""
        defaults = _get_defaults()
        self.assertEqual(defaults["senses"]["ha_tts_entity"], "")

    def test_speech_output_mode_is_string(self):
        """senses.speech_output_mode is a string."""
        defaults = _get_defaults()
        self.assertIsInstance(defaults["senses"]["speech_output_mode"], str)

    def test_ha_tts_entity_is_string(self):
        """senses.ha_tts_entity is a string."""
        defaults = _get_defaults()
        self.assertIsInstance(defaults["senses"]["ha_tts_entity"], str)


if __name__ == '__main__':
    unittest.main()
```

- [ ] **Step 2: Run new tests — confirm they fail**

```bash
python -m pytest tests/test_remote_endpoints_settings.py -v
```

Expected: `KeyError: 'tts_service'` (key doesn't exist yet)

- [ ] **Step 3: Run existing senses settings tests — note which will break**

```bash
python -m pytest tests/test_senses_settings.py -v
```

Note: `test_all_values_are_integers` currently passes. After adding string keys it will fail. We'll fix it next.

- [ ] **Step 4: Update `DEFAULT_SETTINGS` in `core/settings_store.py`**

Replace the `"home_assistant"` block (lines 39–44):

**Before:**
```python
    "home_assistant": {
        "url": "",
        "token": "",
        "enabled": False
    },
```

**After:**
```python
    "home_assistant": {
        "url": "",
        "token": "",
        "enabled": False,
        "tts_service": "tts.piper",       # HA TTS engine entity (e.g. tts.piper, tts.google_translate)
        "tts_target_entity": "",           # HA media_player entity_id for speech output
    },
```

Replace the `"senses"` block (lines 58–62):

**Before:**
```python
    "senses": {
        "camera_index": 0,
        "audio_input_device": -1,   # -1 = system default
        "audio_output_device": -1,  # -1 = system default
    }
```

**After:**
```python
    "senses": {
        "camera_index": 0,
        "audio_input_device": -1,          # -1 = system default
        "audio_output_device": -1,         # -1 = system default
        "speech_output_mode": "local",     # "local" | "ha_media_player"
        "ha_tts_entity": "",               # selected HA media_player entity_id (device id in registry)
    }
```

- [ ] **Step 5: Fix `test_all_values_are_integers` in `tests/test_senses_settings.py`**

The test `test_all_values_are_integers` assumes every senses setting is an int — no longer true with string keys. Replace it with a targeted test.

In `tests/test_senses_settings.py`, replace:

```python
    def test_all_values_are_integers(self):
        """All senses defaults are integers."""
        defaults = self._get_defaults()
        for key, val in defaults['senses'].items():
            self.assertIsInstance(val, int, f"senses.{key} should be int, got {type(val)}")
```

With:

```python
    def test_device_index_values_are_integers(self):
        """camera_index, audio_input_device, audio_output_device are integers (-1 or 0+)."""
        defaults = self._get_defaults()
        senses = defaults['senses']
        for key in ('camera_index', 'audio_input_device', 'audio_output_device'):
            self.assertIsInstance(senses[key], int, f"senses.{key} should be int")
```

- [ ] **Step 6: Run all senses tests — confirm they pass**

```bash
python -m pytest tests/test_senses_settings.py tests/test_remote_endpoints_settings.py -v
```

Expected: `9 passed` (4 original + 1 updated + 7 new — minus the removed test + plus the replacement)

- [ ] **Step 7: Commit**

```bash
git add core/settings_store.py tests/test_senses_settings.py tests/test_remote_endpoints_settings.py
git commit -m "feat: extend DEFAULT_SETTINGS with HA TTS and senses speech output keys"
```

---

## Task 4: SensesManager Speech Dispatch Tests + IntentBridge

**Files:**
- Modify: `tests/test_senses_manager.py` (add speech dispatch + intent routing tests)
- Create: `core/intent_bridge.py`
- Create: `tests/test_intent_bridge.py`

- [ ] **Step 1: Add speech dispatch tests to `tests/test_senses_manager.py`**

Append this new test class to the end of `tests/test_senses_manager.py` (before `if __name__ == '__main__':`):

```python
class TestSpeechDispatch(unittest.TestCase):

    def test_send_speech_calls_local_speech_by_default(self):
        """send_speech() with no target uses local_speaker by default."""
        sm = make_manager()
        with patch.object(sm, "_send_local_speech", return_value=True) as mock_local:
            result = sm.send_speech("Hello ADA")
        mock_local.assert_called_once_with("Hello ADA")
        self.assertTrue(result)

    def test_send_speech_explicit_local_speaker_target(self):
        """send_speech(target_id='local_speaker') routes to local TTS."""
        sm = make_manager()
        with patch.object(sm, "_send_local_speech", return_value=True) as mock_local:
            result = sm.send_speech("Test", target_id="local_speaker")
        mock_local.assert_called_once_with("Test")
        self.assertTrue(result)

    def test_send_speech_routes_to_ha_for_ha_source(self):
        """send_speech() calls _send_ha_speech for home_assistant source device."""
        sm = make_manager()
        sm.register_device({
            "id": "ha_living_room",
            "name": "Living Room",
            "device_type": "speech_output",
            "source": "home_assistant",
            "privacy": "local_or_cloud_dependent",
            "enabled": True,
            "entity_id": "media_player.living_room",
        })
        with patch.object(sm, "_send_ha_speech", return_value=True) as mock_ha:
            result = sm.send_speech("Hello", target_id="ha_living_room")
        mock_ha.assert_called_once_with("Hello", "media_player.living_room")
        self.assertTrue(result)

    def test_send_speech_returns_false_for_unknown_target(self):
        """send_speech() returns False when target_id is not in registry."""
        sm = make_manager()
        result = sm.send_speech("Hello", target_id="nonexistent_device")
        self.assertFalse(result)

    def test_send_speech_returns_false_for_disabled_target(self):
        """send_speech() returns False when the target device is disabled."""
        sm = make_manager()
        sm.register_device({
            "id": "disabled_speaker",
            "name": "Off Speaker",
            "device_type": "speech_output",
            "source": "local",
            "privacy": "local",
            "enabled": False,
            "entity_id": None,
        })
        with patch.object(sm, "_send_local_speech") as mock_local:
            result = sm.send_speech("Hello", target_id="disabled_speaker")
        mock_local.assert_not_called()
        self.assertFalse(result)

    def test_send_local_speech_calls_tts_speak(self):
        """_send_local_speech() calls tts.speak() and returns True."""
        sm = make_manager()
        mock_tts = MagicMock()
        mock_tts.speak.return_value = None
        with patch("core.tts.tts", mock_tts):
            result = sm._send_local_speech("Hello world")
        mock_tts.speak.assert_called_once_with("Hello world")
        self.assertTrue(result)

    def test_send_local_speech_returns_false_on_exception(self):
        """_send_local_speech() returns False when tts.speak() raises."""
        sm = make_manager()
        mock_tts = MagicMock()
        mock_tts.speak.side_effect = RuntimeError("TTS engine not ready")
        with patch("core.tts.tts", mock_tts):
            result = sm._send_local_speech("Hello")
        self.assertFalse(result)

    def test_send_ha_speech_calls_ha_manager(self):
        """_send_ha_speech() calls ha_manager.speak_to_media_player()."""
        sm = make_manager()
        mock_ha = MagicMock()
        mock_ha.speak_to_media_player.return_value = True
        with patch("core.ha_control.ha_manager", mock_ha), \
             patch("core.senses_manager.settings") as mock_settings:
            mock_settings.get.return_value = "tts.piper"
            result = sm._send_ha_speech("Hello HA", "media_player.living_room")
        mock_ha.speak_to_media_player.assert_called_once_with(
            "media_player.living_room", "Hello HA", tts_service="tts.piper"
        )
        self.assertTrue(result)

    def test_send_ha_speech_returns_false_with_no_entity_id(self):
        """_send_ha_speech() returns False when entity_id is None or empty."""
        sm = make_manager()
        self.assertFalse(sm._send_ha_speech("Hello", None))
        self.assertFalse(sm._send_ha_speech("Hello", ""))


class TestIntentRouting(unittest.TestCase):

    def test_receive_external_intent_rejected_with_no_intent_inputs(self):
        """receive_external_intent() rejects any source when no intent_input devices exist."""
        sm = make_manager()
        with patch("core.intent_bridge.intent_bridge") as mock_bridge:
            sm.receive_external_intent("alexa", "Turn on the lights")
        mock_bridge.route_intent.assert_not_called()

    def test_receive_external_intent_rejected_from_unregistered_source(self):
        """receive_external_intent() rejects source not in the registry."""
        sm = make_manager()
        sm.register_device({
            "id": "google_home_input",
            "name": "Google Home",
            "device_type": "intent_input",
            "source": "google_home",
            "privacy": "cloud_dependent",
            "enabled": True,
            "entity_id": None,
        })
        with patch("core.intent_bridge.intent_bridge") as mock_bridge:
            # "alexa" is not registered — only "google_home" is
            sm.receive_external_intent("alexa", "Set timer for 5 minutes")
        mock_bridge.route_intent.assert_not_called()

    def test_receive_external_intent_routes_registered_source(self):
        """receive_external_intent() routes to intent_bridge for registered source."""
        sm = make_manager()
        sm.register_device({
            "id": "alexa_intent",
            "name": "Alexa",
            "device_type": "intent_input",
            "source": "alexa",
            "privacy": "cloud_dependent",
            "enabled": True,
            "entity_id": None,
        })
        with patch("core.intent_bridge.intent_bridge") as mock_bridge:
            sm.receive_external_intent("alexa", "Turn on the lights")
        mock_bridge.route_intent.assert_called_once_with("Turn on the lights")

    def test_receive_external_intent_rejected_when_device_disabled(self):
        """receive_external_intent() rejects even if source is registered but disabled."""
        sm = make_manager()
        sm.register_device({
            "id": "alexa_intent",
            "name": "Alexa",
            "device_type": "intent_input",
            "source": "alexa",
            "privacy": "cloud_dependent",
            "enabled": False,  # disabled!
            "entity_id": None,
        })
        with patch("core.intent_bridge.intent_bridge") as mock_bridge:
            sm.receive_external_intent("alexa", "Turn on the lights")
        mock_bridge.route_intent.assert_not_called()
```

- [ ] **Step 2: Write IntentBridge tests**

Create `tests/test_intent_bridge.py`:

```python
"""
Tests for core/intent_bridge.py — intent normalization.

Run: python -m pytest tests/test_intent_bridge.py -v
"""
import sys
import os
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))


class TestNormalizeIntent(unittest.TestCase):

    def setUp(self):
        from core.intent_bridge import IntentBridge
        self.ib = IntentBridge()

    def test_home_assistant_source_extracts_text(self):
        """HA payload uses key 'text'."""
        result = self.ib.normalize_intent("home_assistant", {"text": "turn on the lights"})
        self.assertEqual(result, "turn on the lights")

    def test_alexa_flat_payload_extracts_query(self):
        """Flat Alexa payload uses key 'query'."""
        result = self.ib.normalize_intent("alexa", {"query": "set a timer"})
        self.assertEqual(result, "set a timer")

    def test_alexa_nested_payload_extracts_slot_value(self):
        """Nested Alexa payload traverses request.intent.slots.query.value."""
        payload = {
            "request": {
                "intent": {
                    "slots": {
                        "query": {"value": "play jazz music"}
                    }
                }
            }
        }
        result = self.ib.normalize_intent("alexa", payload)
        self.assertEqual(result, "play jazz music")

    def test_google_home_extracts_query_text(self):
        """Google Home payload uses key 'queryText'."""
        result = self.ib.normalize_intent("google_home", {"queryText": "what is the weather?"})
        self.assertEqual(result, "what is the weather?")

    def test_unknown_source_falls_back_to_text(self):
        """Unknown source tries 'text' key first."""
        result = self.ib.normalize_intent("unknown_source", {"text": "hello ada"})
        self.assertEqual(result, "hello ada")

    def test_unknown_source_falls_back_to_query(self):
        """Unknown source falls back to 'query' if 'text' is absent."""
        result = self.ib.normalize_intent("unknown_source", {"query": "hello ada"})
        self.assertEqual(result, "hello ada")

    def test_returns_none_for_empty_ha_payload(self):
        """Returns None when HA payload has no 'text' key."""
        result = self.ib.normalize_intent("home_assistant", {})
        self.assertIsNone(result)

    def test_returns_none_for_malformed_alexa_payload(self):
        """Returns None for Alexa payload with no 'query' and malformed nested dict."""
        result = self.ib.normalize_intent("alexa", {"request": {}})
        self.assertIsNone(result)


class TestRouteIntent(unittest.TestCase):

    def test_route_intent_does_not_raise(self):
        """route_intent() runs without error (placeholder implementation)."""
        from core.intent_bridge import IntentBridge
        ib = IntentBridge()
        # Should not raise any exception
        ib.route_intent("turn on the kitchen light")

    def test_route_intent_singleton_does_not_raise(self):
        """Global intent_bridge singleton works without error."""
        from core.intent_bridge import intent_bridge
        intent_bridge.route_intent("test intent")


if __name__ == '__main__':
    unittest.main()
```

- [ ] **Step 3: Run all tests — confirm they fail**

```bash
python -m pytest tests/test_senses_manager.py tests/test_intent_bridge.py -v
```

Expected: failures in the new TestSpeechDispatch and TestIntentRouting classes + ModuleNotFoundError for intent_bridge

- [ ] **Step 4: Create `core/intent_bridge.py`**

```python
"""
IntentBridge — normalizes and routes external voice assistant intents to ADA.

This is a placeholder implementation. External voice assistants (Alexa, Google Home,
Home Assistant automations) forward text commands to ADA after their own transcription.
ADA never receives raw audio from these sources.

Privacy guarantee: IntentBridge only ever handles text strings — never audio data.
"""
from __future__ import annotations


class IntentBridge:
    """
    Normalize raw intent payloads from external sources and route to ADA's pipeline.

    Supported payload formats per source:
      home_assistant — {"text": "..."}
      alexa          — {"query": "..."} or nested Alexa request envelope
      google_home    — {"queryText": "..."}
      unknown        — tries "text", then "query"
    """

    def normalize_intent(self, source: str, raw_payload: dict) -> str | None:
        """
        Extract the intent text string from a source-specific payload.

        Returns the intent text, or None if the payload is unrecognized.
        """
        if source == "home_assistant":
            return raw_payload.get("text")

        elif source == "alexa":
            # Support flat {"query": "..."} or nested Alexa request envelope
            if "query" in raw_payload:
                return raw_payload["query"]
            try:
                return raw_payload["request"]["intent"]["slots"]["query"]["value"]
            except (KeyError, TypeError):
                return None

        elif source == "google_home":
            return raw_payload.get("queryText")

        else:
            # Unknown source: try common text keys
            return raw_payload.get("text") or raw_payload.get("query")

    def route_intent(self, intent_text: str) -> None:
        """
        Route a normalized text intent to ADA's processing pipeline.

        Placeholder: logs the intent. Real implementation will invoke the
        function router or chat engine once those APIs are stable.
        """
        print(f"[IntentBridge] Routing intent: {intent_text!r}")


# Global singleton
intent_bridge = IntentBridge()
```

- [ ] **Step 5: Run all new tests — confirm they pass**

```bash
python -m pytest tests/test_senses_manager.py tests/test_intent_bridge.py -v
```

Expected: all pass (15 original registry tests + 13 new dispatch/intent tests + 10 IntentBridge tests)

- [ ] **Step 6: Commit**

```bash
git add core/intent_bridge.py tests/test_senses_manager.py tests/test_intent_bridge.py
git commit -m "feat: add IntentBridge and SensesManager speech dispatch with full test coverage"
```

---

## Task 5: i18n Keys for Remote Endpoints

**Files:**
- Modify: `locales/en.json`
- Modify: `locales/fr.json`
- Create: `tests/test_remote_endpoints_i18n.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_remote_endpoints_i18n.py`:

```python
"""
Tests that remote endpoint i18n keys exist in both locale files.

Run: python -m pytest tests/test_remote_endpoints_i18n.py -v
"""
import sys
import os
import json
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

LOCALES_DIR = os.path.join(os.path.dirname(__file__), '..', 'locales')

REQUIRED_SENSES_KEYS = [
    "endpoints",
    "endpoints_desc",
    "speech_output_mode",
    "speech_output_mode_desc",
    "speech_output_local",
    "ha_tts_service",
    "ha_tts_service_desc",
    "ha_tts_service_placeholder",
    "test_speech",
    "test_speech_desc",
    "test_speech_btn",
    "test_speech_phrase",
    "test_speech_sent",
    "intent_inputs",
    "intent_note",
    "badge_local",
    "badge_ha",
    "badge_cloud",
    "badge_intent_only",
]


def _load_locale(lang: str) -> dict:
    path = os.path.join(LOCALES_DIR, f"{lang}.json")
    with open(path, 'r', encoding='utf-8') as f:
        return json.load(f)


class TestEnglishRemoteEndpointKeys(unittest.TestCase):

    def setUp(self):
        self.locale = _load_locale("en")
        self.senses = self.locale.get("senses", {})

    def test_all_required_keys_present(self):
        """All 19 remote endpoint keys exist in en.json senses section."""
        for key in REQUIRED_SENSES_KEYS:
            with self.subTest(key=key):
                self.assertIn(key, self.senses, f"Missing key: senses.{key} in en.json")

    def test_all_values_are_non_empty_strings(self):
        """All new keys have non-empty string values."""
        for key in REQUIRED_SENSES_KEYS:
            with self.subTest(key=key):
                value = self.senses.get(key, "")
                self.assertIsInstance(value, str, f"senses.{key} should be str")
                self.assertTrue(value.strip(), f"senses.{key} should not be empty")


class TestFrenchRemoteEndpointKeys(unittest.TestCase):

    def setUp(self):
        self.locale = _load_locale("fr")
        self.senses = self.locale.get("senses", {})

    def test_all_required_keys_present(self):
        """All 19 remote endpoint keys exist in fr.json senses section."""
        for key in REQUIRED_SENSES_KEYS:
            with self.subTest(key=key):
                self.assertIn(key, self.senses, f"Missing key: senses.{key} in fr.json")

    def test_all_values_are_non_empty_strings(self):
        """All new keys have non-empty string values."""
        for key in REQUIRED_SENSES_KEYS:
            with self.subTest(key=key):
                value = self.senses.get(key, "")
                self.assertIsInstance(value, str, f"senses.{key} should be str")
                self.assertTrue(value.strip(), f"senses.{key} should not be empty")


if __name__ == '__main__':
    unittest.main()
```

- [ ] **Step 2: Run tests — confirm they fail**

```bash
python -m pytest tests/test_remote_endpoints_i18n.py -v
```

Expected: `AssertionError: Missing key: senses.endpoints in en.json`

- [ ] **Step 3: Add keys to `locales/en.json`**

In `locales/en.json`, inside the `"senses"` block, after the last existing key (`"cap_inactive": "Inactive"`), add (before the closing `}`):

```json
    "endpoints": "Remote Endpoints",
    "endpoints_desc": "External voice input and output devices",
    "speech_output_mode": "Speech Output",
    "speech_output_mode_desc": "Where ADA speaks: local speaker or HA media player",
    "speech_output_local": "Local Speaker",
    "ha_tts_service": "HA TTS Service",
    "ha_tts_service_desc": "Home Assistant TTS engine entity (e.g. tts.piper)",
    "ha_tts_service_placeholder": "tts.piper",
    "test_speech": "Test Speech Output",
    "test_speech_desc": "Send a test phrase to the selected output device",
    "test_speech_btn": "Test",
    "test_speech_phrase": "Hello, ADA is speaking.",
    "test_speech_sent": "Speech dispatched",
    "intent_inputs": "Intent Inputs",
    "intent_note": "Alexa and Google Home send text commands only — ADA never has access to their raw audio.",
    "badge_local": "Local",
    "badge_ha": "Home Assistant",
    "badge_cloud": "Cloud",
    "badge_intent_only": "Intent only"
```

- [ ] **Step 4: Add keys to `locales/fr.json`**

In `locales/fr.json`, inside the `"senses"` block, after `"cap_inactive": "Inactif"`, add:

```json
    "endpoints": "Points d'accès distants",
    "endpoints_desc": "Périphériques d'entrée et de sortie vocale externes",
    "speech_output_mode": "Sortie vocale",
    "speech_output_mode_desc": "Où ADA s'exprime : haut-parleur local ou lecteur HA",
    "speech_output_local": "Haut-parleur local",
    "ha_tts_service": "Service TTS HA",
    "ha_tts_service_desc": "Entité moteur TTS de Home Assistant (ex. tts.piper)",
    "ha_tts_service_placeholder": "tts.piper",
    "test_speech": "Tester la sortie vocale",
    "test_speech_desc": "Envoyer une phrase test au périphérique de sortie sélectionné",
    "test_speech_btn": "Tester",
    "test_speech_phrase": "Bonjour, ADA s'exprime.",
    "test_speech_sent": "Synthèse vocale envoyée",
    "intent_inputs": "Entrées par intention",
    "intent_note": "Alexa et Google Home envoient uniquement des commandes texte — ADA n'a pas accès à leur audio brut.",
    "badge_local": "Local",
    "badge_ha": "Home Assistant",
    "badge_cloud": "Cloud",
    "badge_intent_only": "Intention seulement"
```

- [ ] **Step 5: Run tests — confirm they pass**

```bash
python -m pytest tests/test_remote_endpoints_i18n.py -v
```

Expected: `4 passed` (2 EN + 2 FR test methods, each using subTest)

- [ ] **Step 6: Commit**

```bash
git add locales/en.json locales/fr.json tests/test_remote_endpoints_i18n.py
git commit -m "feat: add i18n keys for remote endpoints section (EN + FR)"
```

---

## Task 6: SensesTab Remote Endpoints UI

**Files:**
- Modify: `gui/tabs/senses.py`

This task adds a new "Remote Endpoints" section to the Senses page with:
1. `_HAProbeThread` — fetches HA media_player entities in background
2. `_format_ha_players()` — pure function: converts raw HA entities dict to display list
3. `_SpeechOutputCard` — ComboBox for local speaker vs. HA media player
4. `_LineEditCard` — text input for HA TTS service entity name
5. `_IntentInfoCard` — read-only info card about Alexa/Google (intent-only)
6. New group in `_build_ui()`
7. `_probe_ha_devices()` + `_on_ha_devices_ready()` + `_on_test_speech()`
8. `retranslate_ui()` updates

There are no unit tests for Qt widgets (they require a running display server). Visual verification: run `python main.py`, open the Senses tab, and confirm the Remote Endpoints section appears below Capabilities.

- [ ] **Step 1: Add `_format_ha_players` helper function and `_HAProbeThread` class**

In `gui/tabs/senses.py`, after the `_DeviceProbeThread` class (around line 38), insert:

```python
def _format_ha_players(entities: dict) -> list[dict]:
    """
    Convert HA media_player entities dict to a list for display.

    Args:
        entities: dict mapping entity_id → entity state dict (from ha_manager)

    Returns:
        list of {"entity_id": str, "name": str} sorted by name
    """
    result = []
    for eid, info in entities.items():
        name = info.get("attributes", {}).get("friendly_name") or eid
        result.append({"entity_id": eid, "name": name})
    return sorted(result, key=lambda x: x["name"].lower())


class _HAProbeThread(QThread):
    """Fetch HA media_player entities in background; emit result list when done."""
    done = Signal(list)   # list of {"entity_id": str, "name": str}

    def run(self) -> None:
        from core.ha_control import ha_manager
        entities = ha_manager.get_media_player_entities()
        self.done.emit(_format_ha_players(entities))
```

- [ ] **Step 2: Add `_SpeechOutputCard` class**

After `_HAProbeThread`, insert:

```python
class _SpeechOutputCard(SettingCard):
    """
    ComboBox card for selecting where ADA speaks.

    Item 0 is always "Local Speaker" (mode='local', entity_id='').
    HA media players are appended by populate_ha_players() after probe.
    userData for each item is a tuple (mode: str, entity_id: str).
    """
    output_changed = Signal(str, str)   # (mode, entity_id)

    def __init__(self, parent=None):
        super().__init__(
            FIF.SPEAKERS,
            tr("senses.speech_output_mode"),
            tr("senses.speech_output_mode_desc"),
            parent
        )
        self.combo = ComboBox(self)
        self.combo.setMinimumWidth(280)
        self.combo.addItem(tr("senses.speech_output_local"), userData=("local", ""))
        self.combo.currentIndexChanged.connect(self._on_changed)
        self.hBoxLayout.addWidget(self.combo, 0, Qt.AlignRight)
        self.hBoxLayout.addSpacing(16)

    def populate_ha_players(self, players: list[dict]) -> None:
        """
        Replace all HA items in the combo with the given players list.
        Called from main thread after _HAProbeThread finishes.
        Restores the previously saved selection when possible.
        """
        self.combo.blockSignals(True)
        # Remove all items after the "Local Speaker" entry (index 0)
        while self.combo.count() > 1:
            self.combo.removeItem(1)
        for p in players:
            self.combo.addItem(f"[HA] {p['name']}", userData=("ha_media_player", p["entity_id"]))
        # Restore saved selection
        saved_mode = settings.get("senses.speech_output_mode", "local")
        saved_entity = settings.get("senses.ha_tts_entity", "")
        for i in range(self.combo.count()):
            mode, entity_id = self.combo.itemData(i)
            if mode == saved_mode and entity_id == saved_entity:
                self.combo.setCurrentIndex(i)
                break
        self.combo.blockSignals(False)

    def _on_changed(self, combo_idx: int) -> None:
        data = self.combo.itemData(combo_idx)
        if data is not None:
            mode, entity_id = data
            settings.set("senses.speech_output_mode", mode)
            settings.set("senses.ha_tts_entity", entity_id)
            self.output_changed.emit(mode, entity_id)

    def retranslate(self) -> None:
        self.titleLabel.setText(tr("senses.speech_output_mode"))
        self.contentLabel.setText(tr("senses.speech_output_mode_desc"))
        # Update the "Local Speaker" entry text (always item 0)
        if self.combo.count() > 0:
            self.combo.blockSignals(True)
            mode, entity_id = self.combo.itemData(0)
            if mode == "local":
                self.combo.setItemText(0, tr("senses.speech_output_local"))
            self.combo.blockSignals(False)
```

- [ ] **Step 3: Add `_LineEditCard` class**

After `_SpeechOutputCard`, insert:

```python
class _LineEditCard(SettingCard):
    """
    SettingCard containing a LineEdit for single-line text settings.
    Saves to settings on editingFinished (Enter key or focus loss).
    """
    text_changed = Signal(str)

    def __init__(self, icon, title: str, description: str,
                 settings_key: str, placeholder: str = "", parent=None):
        super().__init__(icon, title, description, parent)
        self._settings_key = settings_key

        from qfluentwidgets import LineEdit
        self.edit = LineEdit(self)
        self.edit.setMinimumWidth(220)
        self.edit.setPlaceholderText(placeholder)
        self.edit.setText(settings.get(settings_key, "") or "")
        self.edit.editingFinished.connect(self._on_finished)
        self.hBoxLayout.addWidget(self.edit, 0, Qt.AlignRight)
        self.hBoxLayout.addSpacing(16)

    def _on_finished(self) -> None:
        value = self.edit.text().strip()
        settings.set(self._settings_key, value)
        self.text_changed.emit(value)

    def retranslate(self, title: str, description: str, placeholder: str = "") -> None:
        self.titleLabel.setText(title)
        self.contentLabel.setText(description)
        if placeholder:
            self.edit.setPlaceholderText(placeholder)
```

- [ ] **Step 4: Add `_IntentInfoCard` class**

After `_LineEditCard`, insert:

```python
class _IntentInfoCard(SettingCard):
    """
    Read-only card explaining that Alexa and Google Home are intent-only inputs.
    Shows an amber "Intent only" badge to indicate no raw audio access.
    """

    def __init__(self, parent=None):
        super().__init__(
            FIF.INFO,
            tr("senses.intent_inputs"),
            tr("senses.intent_note"),
            parent
        )
        self._badge = QLabel(tr("senses.badge_intent_only"), self)
        self._badge.setStyleSheet(
            "color: #f59e0b; font-size: 12px; font-weight: 500;"
            " background: rgba(245,158,11,0.12); border-radius: 4px; padding: 2px 8px;"
        )
        self.hBoxLayout.addWidget(self._badge, 0, Qt.AlignRight)
        self.hBoxLayout.addSpacing(16)

    def retranslate(self) -> None:
        self.titleLabel.setText(tr("senses.intent_inputs"))
        self.contentLabel.setText(tr("senses.intent_note"))
        self._badge.setText(tr("senses.badge_intent_only"))
```

- [ ] **Step 5: Add the Remote Endpoints group to `_build_ui()`**

In `SensesTab._build_ui()`, after `self._layout.addWidget(self.cap_group)` (the last line adding the Capabilities group), append:

```python
        # ── 5. Remote Endpoints ────────────────────────────────────────────
        self.endpoints_group = SettingCardGroup(tr("senses.endpoints"), self._content)

        self.speech_output_card = _SpeechOutputCard(self.endpoints_group)
        self.endpoints_group.addSettingCard(self.speech_output_card)

        self.ha_tts_service_card = _LineEditCard(
            icon=FIF.HEADPHONE,
            title=tr("senses.ha_tts_service"),
            description=tr("senses.ha_tts_service_desc"),
            settings_key="home_assistant.tts_service",
            placeholder=tr("senses.ha_tts_service_placeholder"),
            parent=self.endpoints_group,
        )
        self.endpoints_group.addSettingCard(self.ha_tts_service_card)

        self.test_speech_card = PushSettingCard(
            text=tr("senses.test_speech_btn"),
            icon=FIF.VOLUME,
            title=tr("senses.test_speech"),
            content=tr("senses.test_speech_desc"),
            parent=self.endpoints_group,
        )
        self.test_speech_card.clicked.connect(self._on_test_speech)
        self.endpoints_group.addSettingCard(self.test_speech_card)

        self.intent_info_card = _IntentInfoCard(self.endpoints_group)
        self.endpoints_group.addSettingCard(self.intent_info_card)

        self._layout.addWidget(self.endpoints_group)
```

- [ ] **Step 6: Add HA probe + test speech methods to `SensesTab`**

Add a new instance variable in `__init__` (after `self._probe_thread: _DeviceProbeThread | None = None`):

```python
        self._ha_probe_thread: _HAProbeThread | None = None
```

And call the HA probe in `__init__` after `self._probe_devices()`:

```python
        self._probe_ha_devices()
```

Add these three methods to `SensesTab` (after `_on_devices_ready`):

```python
    def _probe_ha_devices(self) -> None:
        """Start HA media player probe if HA is configured and enabled."""
        if not settings.get("home_assistant.enabled", False):
            return
        self._ha_probe_thread = _HAProbeThread()
        self._ha_probe_thread.done.connect(self._on_ha_devices_ready)
        self._ha_probe_thread.finished.connect(self._ha_probe_thread.deleteLater)
        self._ha_probe_thread.start()

    def _on_ha_devices_ready(self, players: list) -> None:
        """Populate speech output combo with discovered HA media players."""
        self.speech_output_card.populate_ha_players(players)
        # Register HA media players in SensesManager for speech dispatch
        from core.senses_manager import senses_manager
        for p in players:
            senses_manager.register_device({
                "id": p["entity_id"],
                "name": p["name"],
                "device_type": "speech_output",
                "source": "home_assistant",
                "privacy": "local_or_cloud_dependent",
                "enabled": True,
                "entity_id": p["entity_id"],
            })

    def _on_test_speech(self) -> None:
        """Send a test phrase to the currently configured speech output."""
        from qfluentwidgets import InfoBar, InfoBarPosition
        from core.senses_manager import senses_manager
        phrase = tr("senses.test_speech_phrase")
        ok = senses_manager.send_speech(phrase)
        if ok:
            InfoBar.success(
                title=tr("senses.test_speech_sent"),
                content="",
                orient=Qt.Horizontal,
                isClosable=True,
                position=InfoBarPosition.TOP,
                duration=2000,
                parent=self.window(),
            )
        else:
            InfoBar.warning(
                title="TTS failed",
                content="Check the application logs for details.",
                orient=Qt.Horizontal,
                isClosable=True,
                position=InfoBarPosition.TOP,
                duration=3000,
                parent=self.window(),
            )
```

- [ ] **Step 7: Update `retranslate_ui()` with the new cards**

In `SensesTab.retranslate_ui()`, after the `# Capabilities` block (after `for card in self._cap_cards: card.retranslate()`), append:

```python
        # Remote Endpoints
        self.endpoints_group.titleLabel.setText(tr("senses.endpoints"))
        self.speech_output_card.retranslate()
        self.ha_tts_service_card.retranslate(
            tr("senses.ha_tts_service"),
            tr("senses.ha_tts_service_desc"),
            tr("senses.ha_tts_service_placeholder"),
        )
        self.test_speech_card.titleLabel.setText(tr("senses.test_speech"))
        self.test_speech_card.contentLabel.setText(tr("senses.test_speech_desc"))
        self.test_speech_card.button.setText(tr("senses.test_speech_btn"))
        self.intent_info_card.retranslate()
```

- [ ] **Step 8: Visual verification**

Run the app and verify:

```bash
python main.py
```

1. Open the **Senses** tab
2. Scroll to the bottom — a **"Remote Endpoints"** section should appear below Capabilities
3. The section should have 4 cards:
   - "Speech Output" with a ComboBox (starts with "Local Speaker")
   - "HA TTS Service" with a LineEdit (shows saved value or empty)
   - "Test Speech Output" with a "Test" button
   - "Intent Inputs" with an amber "Intent only" badge
4. If Home Assistant is enabled in settings, HA media players should appear in the ComboBox after a moment
5. Click "Test" — should speak via local TTS (or show a warning if TTS is inactive)
6. Change language in Settings → all Remote Endpoints labels should update in-place

- [ ] **Step 9: Commit**

```bash
git add gui/tabs/senses.py
git commit -m "feat: add Remote Endpoints section to SensesTab with HA TTS output and intent input info"
```

---

## Final Full Test Suite Run

After all tasks are complete, run the complete test suite to verify nothing is broken:

```bash
python -m pytest tests/ -v
```

Expected: all tests pass (existing + new).

Individual suites:
```bash
python -m pytest tests/test_senses_manager.py -v       # 28 tests
python -m pytest tests/test_intent_bridge.py -v        # 10 tests
python -m pytest tests/test_ha_tts.py -v               # 8 tests
python -m pytest tests/test_remote_endpoints_settings.py -v  # 7 tests
python -m pytest tests/test_remote_endpoints_i18n.py -v      # 4 test methods (with subtests)
python -m pytest tests/test_senses_settings.py -v      # 5 tests (including updated one)
python -m pytest tests/test_device_enumerator.py -v    # 10 tests (unchanged)
```

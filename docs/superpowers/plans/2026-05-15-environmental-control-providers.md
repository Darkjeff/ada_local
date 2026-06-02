# Environmental Control — Multi-Provider Architecture Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the hardcoded Kasa/HA tabs in the Environmental Control page with a generic multi-provider architecture (Provider + Entity models, provider adapters, unified service) and a filterable UI grid by Provider/Type/Zone.

**Architecture:** Three new layers: (1) `core/entity_models.py` defines `Provider` and `Entity` dataclasses with zone-inference and capability-detection helpers; (2) `core/providers/` contains adapter classes `KasaProvider` and `HAProvider` that each implement a `BaseProvider` interface; (3) `core/unified_entities.py` provides `UnifiedEntityService`, which fetches from all enabled providers, merges results, and exposes `toggle_entity()`, `set_entity_brightness()`, `send_tts_to_entity()`. The UI (`gui/tabs/home_automation.py`) is rebuilt around three stacked filter rows (Provider / Type / Zone) feeding a single entity grid drawn with specialized cards from `gui/components/entity_cards.py`.

**Tech Stack:** Python 3.11+, PySide6, qfluentwidgets, python-kasa (async), requests (HA REST), unittest + MagicMock

---

## File Structure

| File | Action | Responsibility |
|---|---|---|
| `core/entity_models.py` | Create | `Provider`, `Entity` dataclasses; `infer_zone()`, `infer_capabilities()`, `ha_domain_to_entity_type()` |
| `core/providers/__init__.py` | Create | Package marker (empty) |
| `core/providers/base_provider.py` | Create | `BaseProvider` ABC |
| `core/providers/kasa_provider.py` | Create | `KasaProvider` wraps `kasa_manager` |
| `core/providers/ha_provider.py` | Create | `HAProvider` wraps `ha_manager` |
| `core/unified_entities.py` | Create | `UnifiedEntityService` — fetch, merge, toggle, brightness, TTS |
| `gui/components/entity_cards.py` | Create | 7 specialized card widgets + `entity_card_for()` factory |
| `gui/tabs/home_automation.py` | Modify | Replace 4 sub-tabs with 3-filter grid UI |
| `gui/tabs/settings.py` | Modify | Add "Kasa" provider settings group |
| `core/settings_store.py` | Modify | Add `kasa: {enabled, priority}` default block |
| `locales/en.json` | Modify | `"home"` + `"settings.kasa*"` keys |
| `locales/fr.json` | Modify | French equivalents |
| `tests/test_entity_models.py` | Create | Unit tests for helpers |
| `tests/test_kasa_provider.py` | Create | Unit tests (mocked kasa_manager) |
| `tests/test_ha_provider.py` | Create | Unit tests (mocked ha_manager) |
| `tests/test_unified_entities.py` | Create | Unit tests (mocked providers) |
| `tests/test_provider_settings.py` | Create | Settings defaults check |

---

## Task 1: Core entity models

**Files:**
- Create: `core/entity_models.py`
- Create: `tests/test_entity_models.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_entity_models.py
import sys
import os
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))


class TestInferZone(unittest.TestCase):

    def test_bureau_keyword(self):
        from core.entity_models import infer_zone
        self.assertEqual(infer_zone("Bureau Desk Light"), "Bureau")

    def test_chambre_keyword(self):
        from core.entity_models import infer_zone
        self.assertEqual(infer_zone("Bedroom Ceiling"), "Chambre")

    def test_cuisine_keyword(self):
        from core.entity_models import infer_zone
        self.assertEqual(infer_zone("Cafetière cuisine"), "Cuisine")

    def test_chillout_keyword(self):
        from core.entity_models import infer_zone
        self.assertEqual(infer_zone("Salon TV"), "Chillout")

    def test_unknown_returns_other(self):
        from core.entity_models import infer_zone
        self.assertEqual(infer_zone("Somewhere Unknown"), "Other")

    def test_case_insensitive(self):
        from core.entity_models import infer_zone
        self.assertEqual(infer_zone("OFFICE LAMP"), "Bureau")


class TestInferCapabilities(unittest.TestCase):

    def test_light_no_extras(self):
        from core.entity_models import infer_capabilities
        caps = infer_capabilities("light", {})
        self.assertIn("read", caps)
        self.assertIn("control", caps)
        self.assertNotIn("brightness", caps)
        self.assertNotIn("color", caps)

    def test_light_with_brightness(self):
        from core.entity_models import infer_capabilities
        caps = infer_capabilities("light", {"brightness": 128})
        self.assertIn("brightness", caps)

    def test_light_with_color(self):
        from core.entity_models import infer_capabilities
        caps = infer_capabilities("light", {"rgb_color": [255, 0, 0]})
        self.assertIn("color", caps)

    def test_read_only_no_control(self):
        from core.entity_models import infer_capabilities
        caps = infer_capabilities("sensor", {}, read_only=True)
        self.assertIn("read", caps)
        self.assertNotIn("control", caps)

    def test_sensor_temperature(self):
        from core.entity_models import infer_capabilities
        caps = infer_capabilities("sensor", {"device_class": "temperature"}, read_only=True)
        self.assertIn("temperature", caps)

    def test_sensor_humidity(self):
        from core.entity_models import infer_capabilities
        caps = infer_capabilities("sensor", {"device_class": "humidity"}, read_only=True)
        self.assertIn("humidity", caps)

    def test_media_player_has_tts(self):
        from core.entity_models import infer_capabilities
        caps = infer_capabilities("media_player", {})
        self.assertIn("tts", caps)

    def test_media_player_volume(self):
        from core.entity_models import infer_capabilities
        caps = infer_capabilities("media_player", {"volume_level": 0.5})
        self.assertIn("volume", caps)

    def test_camera_snapshot(self):
        from core.entity_models import infer_capabilities
        caps = infer_capabilities("camera", {}, read_only=True)
        self.assertIn("snapshot", caps)


class TestHaDomainToEntityType(unittest.TestCase):

    def test_light(self):
        from core.entity_models import ha_domain_to_entity_type
        self.assertEqual(ha_domain_to_entity_type("light"), "light")

    def test_binary_sensor(self):
        from core.entity_models import ha_domain_to_entity_type
        self.assertEqual(ha_domain_to_entity_type("binary_sensor"), "binary_sensor")

    def test_unknown_domain(self):
        from core.entity_models import ha_domain_to_entity_type
        self.assertEqual(ha_domain_to_entity_type("vacuum"), "unknown")

    def test_media_player(self):
        from core.entity_models import ha_domain_to_entity_type
        self.assertEqual(ha_domain_to_entity_type("media_player"), "media_player")


class TestEntityDataclass(unittest.TestCase):

    def test_entity_creation(self):
        from core.entity_models import Entity
        e = Entity(
            id="kasa.192.168.1.1",
            provider="kasa",
            provider_entity_id="192.168.1.1",
            name="Office Light",
            type="light",
            zone="Bureau",
            state="on",
        )
        self.assertEqual(e.id, "kasa.192.168.1.1")
        self.assertEqual(e.zone, "Bureau")
        self.assertFalse(e.read_only)
        self.assertTrue(e.available)

    def test_provider_creation(self):
        from core.entity_models import Provider
        p = Provider(id="kasa", name="Kasa", enabled=True, type="kasa")
        self.assertEqual(p.status, "unknown")
        self.assertEqual(p.capabilities, [])


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run tests to confirm FAIL**

```
python -m pytest tests/test_entity_models.py -v
```
Expected: `ModuleNotFoundError: No module named 'core.entity_models'`

- [ ] **Step 3: Create `core/entity_models.py`**

```python
"""
ADA — Unified provider/entity domain models.

These dataclasses form the lingua franca between provider adapters
(Kasa, Home Assistant, …) and the UI. No I/O, no Qt imports here.
"""
from __future__ import annotations

from dataclasses import dataclass, field

# ---------------------------------------------------------------------------
# Zone inference
# ---------------------------------------------------------------------------

_ZONE_KEYWORDS: dict[str, list[str]] = {
    "Bureau":    ["bureau", "office", "desk", "work", "pc", "monitor", "etagere"],
    "Chambre":   ["chambre", "bedroom", "bed", "sleep", "night", "nuit"],
    "Cuisine":   ["cuisine", "kitchen", "dining", "cook", "oven", "cafe", "cafetiere"],
    "Chillout":  ["salon", "living", "lounge", "sejour", "sofa", "tv"],
    "Extérieur": ["exterieur", "exterior", "garden", "jardin", "patio", "porch", "garage"],
    "Couloir":   ["couloir", "hall", "corridor", "stairs", "entree"],
}


def infer_zone(name: str) -> str:
    """Return the best-matching zone for a device name, or 'Other'."""
    lower = name.lower()
    for zone, keywords in _ZONE_KEYWORDS.items():
        if any(k in lower for k in keywords):
            return zone
    return "Other"


# ---------------------------------------------------------------------------
# HA domain → ADA entity type
# ---------------------------------------------------------------------------

_HA_DOMAIN_TO_TYPE: dict[str, str] = {
    "light":         "light",
    "switch":        "switch",
    "script":        "switch",
    "scene":         "switch",
    "media_player":  "media_player",
    "camera":        "camera",
    "sensor":        "sensor",
    "binary_sensor": "binary_sensor",
    "climate":       "unknown",
}


def ha_domain_to_entity_type(domain: str) -> str:
    """Convert a Home Assistant entity domain to an ADA entity type string."""
    return _HA_DOMAIN_TO_TYPE.get(domain, "unknown")


# ---------------------------------------------------------------------------
# Capability inference
# ---------------------------------------------------------------------------

def infer_capabilities(
    entity_type: str, attributes: dict, read_only: bool = False
) -> list[str]:
    """
    Return a list of capability strings for an entity given its type
    and raw attributes dict. Never raises.
    """
    caps: list[str] = ["read"]
    if not read_only:
        caps.append("control")

    if entity_type == "light":
        if "brightness" in attributes or attributes.get("is_dimmable"):
            caps.append("brightness")
        if (
            "rgb_color" in attributes
            or "hs_color" in attributes
            or attributes.get("is_color")
        ):
            caps.append("color")

    elif entity_type in ("media_player", "speaker"):
        caps.append("tts")
        if "volume_level" in attributes:
            caps.append("volume")

    elif entity_type == "camera":
        caps.append("snapshot")
        if attributes.get("motion_detection"):
            caps.append("motion")

    elif entity_type == "sensor":
        dc = attributes.get("device_class", "")
        _DC_CAP = {
            "temperature": "temperature",
            "humidity":    "humidity",
            "battery":     "battery",
            "energy":      "energy",
            "power":       "energy",
        }
        if dc in _DC_CAP:
            caps.append(_DC_CAP[dc])

    return caps


# ---------------------------------------------------------------------------
# Dataclasses
# ---------------------------------------------------------------------------

@dataclass
class Provider:
    """Metadata about a single automation provider."""
    id: str
    name: str
    enabled: bool
    type: str                           # "kasa" | "home_assistant" | "domoticz" | …
    base_url: str = ""
    token: str = ""
    priority: int = 0
    status: str = "unknown"             # "connected" | "disconnected" | "unknown" | "error"
    last_sync: float = 0.0
    capabilities: list[str] = field(default_factory=list)


@dataclass
class Entity:
    """A single normalized device/entity regardless of its origin provider."""
    id: str                             # "{provider_id}.{provider_entity_id}"
    provider: str                       # provider id ("kasa", "home_assistant", …)
    provider_entity_id: str             # original id within the provider
    name: str
    type: str                           # "light" | "camera" | "sensor" | etc.
    zone: str                           # inferred from name via infer_zone()
    state: str                          # "on" | "off" | "playing" | numeric string, …
    attributes: dict = field(default_factory=dict)
    capabilities: list[str] = field(default_factory=list)
    read_only: bool = False
    available: bool = True
    last_updated: float = 0.0
```

- [ ] **Step 4: Run tests to confirm PASS**

```
python -m pytest tests/test_entity_models.py -v
```
Expected: `21 passed`

- [ ] **Step 5: Commit**

```bash
git add core/entity_models.py tests/test_entity_models.py
git commit -m "feat: add Provider and Entity domain models with zone/capability helpers"
```

---

## Task 2: Settings — add kasa provider block

**Files:**
- Modify: `core/settings_store.py` (add `kasa` key to `DEFAULT_SETTINGS`)
- Create: `tests/test_provider_settings.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_provider_settings.py
import sys
import os
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))


class TestKasaDefaults(unittest.TestCase):

    def setUp(self):
        """Use a fresh in-memory SettingsStore that never touches disk."""
        from unittest.mock import patch
        import json
        # Patch _settings_file.exists() to False so defaults are used
        with patch('pathlib.Path.exists', return_value=False), \
             patch('pathlib.Path.mkdir'), \
             patch('builtins.open', unittest.mock.mock_open()):
            from core.settings_store import SettingsStore
            self.store = SettingsStore()

    def test_kasa_enabled_default_true(self):
        self.assertTrue(self.store.get("kasa.enabled"))

    def test_kasa_priority_default_50(self):
        self.assertEqual(self.store.get("kasa.priority"), 50)

    def test_ha_enabled_default_false(self):
        """Existing HA default must still be False."""
        self.assertFalse(self.store.get("home_assistant.enabled"))

    def test_ha_tts_service_default(self):
        """Existing HA tts_service default must still be tts.piper."""
        self.assertEqual(self.store.get("home_assistant.tts_service"), "tts.piper")


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run to confirm FAIL**

```
python -m pytest tests/test_provider_settings.py::TestKasaDefaults::test_kasa_enabled_default_true -v
```
Expected: `KeyError` or `AssertionError` — kasa key does not exist yet.

- [ ] **Step 3: Add `kasa` block to `DEFAULT_SETTINGS` in `core/settings_store.py`**

In `core/settings_store.py`, find the `DEFAULT_SETTINGS` dict (around line 15). Add the `kasa` entry **after** the `home_assistant` block:

```python
    "kasa": {
        "enabled": True,
        "priority": 50,
    },
```

The full `DEFAULT_SETTINGS` block after the change (showing only the modified area):

```python
DEFAULT_SETTINGS = {
    "theme": "Dark",
    "ollama_url": "http://localhost:11434",
    "models": {
        "chat": "qwen3:1.7b",
        "web_agent": "qwen3-vl:4b",
    },
    "web_agent_params": {
        "temperature": 1.0,
        "top_k": 20,
        "top_p": 0.95
    },
    "tts": {
        "voice": "en_GB-alba-medium"
    },
    "general": {
        "max_history": 20,
        "auto_fetch_news": True
    },
    "weather": {
        "latitude": 40.7128,
        "longitude": -74.0060,
        "city": "New York, NY"
    },
    "home_assistant": {
        "url": "",
        "token": "",
        "enabled": False,
        "tts_service": "tts.piper",
        "tts_target_entity": "",
    },
    "kasa": {
        "enabled": True,
        "priority": 50,
    },
    "k1": {
        "ip": "",
        "password": ""
    },
    # … rest unchanged …
}
```

- [ ] **Step 4: Run to confirm PASS**

```
python -m pytest tests/test_provider_settings.py -v
```
Expected: `4 passed`

- [ ] **Step 5: Commit**

```bash
git add core/settings_store.py tests/test_provider_settings.py
git commit -m "feat: add kasa provider settings defaults (enabled=True, priority=50)"
```

---

## Task 3: BaseProvider + KasaProvider adapter

**Files:**
- Create: `core/providers/__init__.py`
- Create: `core/providers/base_provider.py`
- Create: `core/providers/kasa_provider.py`
- Create: `tests/test_kasa_provider.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_kasa_provider.py
"""
Tests for KasaProvider adapter.
All network calls are mocked — no real Kasa devices needed.
"""
import sys
import os
import asyncio
import unittest
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))


def _make_kasa_device(alias: str, ip: str, is_on: bool,
                      brightness: int | None = None, is_color: bool = False):
    return {
        "alias": alias,
        "ip": ip,
        "model": "KL130",
        "is_on": is_on,
        "type": "Bulb" if brightness is not None else "Plug",
        "brightness": brightness,
        "is_color": is_color,
        "hsv": None,
        "obj": MagicMock(),
    }


class TestKasaProviderFetchEntities(unittest.TestCase):

    def _provider(self):
        with patch('core.settings_store.settings') as mock_s:
            mock_s.get.side_effect = lambda key, default=None: {
                "kasa.enabled": True,
                "kasa.priority": 50,
            }.get(key, default)
            from core.providers.kasa_provider import KasaProvider
            return KasaProvider()

    def test_returns_entities_for_each_device(self):
        """fetch_entities() returns one Entity per discovered Kasa device."""
        provider = self._provider()

        async def mock_discover():
            return {
                "192.168.1.10": _make_kasa_device("Office Light", "192.168.1.10", True, brightness=80),
                "192.168.1.11": _make_kasa_device("Kitchen Plug", "192.168.1.11", False),
            }

        with patch('core.kasa_control.kasa_manager') as mock_km:
            mock_km.discover_devices = mock_discover
            entities = provider.fetch_entities()

        self.assertEqual(len(entities), 2)
        ids = {e.id for e in entities}
        self.assertIn("kasa.192.168.1.10", ids)
        self.assertIn("kasa.192.168.1.11", ids)

    def test_bulb_entity_has_light_type(self):
        """A Kasa bulb (brightness not None) is typed as 'light'."""
        provider = self._provider()

        async def mock_discover():
            return {"192.168.1.10": _make_kasa_device("Desk Bulb", "192.168.1.10", True, brightness=50)}

        with patch('core.kasa_control.kasa_manager') as mock_km:
            mock_km.discover_devices = mock_discover
            entities = provider.fetch_entities()

        self.assertEqual(entities[0].type, "light")

    def test_plug_entity_has_switch_type(self):
        """A Kasa plug (no brightness) is typed as 'switch'."""
        provider = self._provider()

        async def mock_discover():
            return {"192.168.1.20": _make_kasa_device("Coffee Plug", "192.168.1.20", False)}

        with patch('core.kasa_control.kasa_manager') as mock_km:
            mock_km.discover_devices = mock_discover
            entities = provider.fetch_entities()

        self.assertEqual(entities[0].type, "switch")

    def test_bulb_entity_has_brightness_capability(self):
        """Bulbs have 'brightness' in capabilities."""
        provider = self._provider()

        async def mock_discover():
            return {"192.168.1.10": _make_kasa_device("Bulb", "192.168.1.10", True, brightness=60)}

        with patch('core.kasa_control.kasa_manager') as mock_km:
            mock_km.discover_devices = mock_discover
            entities = provider.fetch_entities()

        self.assertIn("brightness", entities[0].capabilities)

    def test_color_bulb_has_color_capability(self):
        """Color bulbs have 'color' in capabilities."""
        provider = self._provider()

        async def mock_discover():
            return {"192.168.1.10": _make_kasa_device("Color Bulb", "192.168.1.10", True, brightness=80, is_color=True)}

        with patch('core.kasa_control.kasa_manager') as mock_km:
            mock_km.discover_devices = mock_discover
            entities = provider.fetch_entities()

        self.assertIn("color", entities[0].capabilities)

    def test_zone_inferred_from_alias(self):
        """Zone is inferred from the device alias."""
        provider = self._provider()

        async def mock_discover():
            return {"192.168.1.10": _make_kasa_device("Bureau Desk Lamp", "192.168.1.10", True)}

        with patch('core.kasa_control.kasa_manager') as mock_km:
            mock_km.discover_devices = mock_discover
            entities = provider.fetch_entities()

        self.assertEqual(entities[0].zone, "Bureau")

    def test_returns_empty_on_exception(self):
        """fetch_entities() returns [] if kasa_manager raises."""
        provider = self._provider()

        async def mock_discover():
            raise RuntimeError("network error")

        with patch('core.kasa_control.kasa_manager') as mock_km:
            mock_km.discover_devices = mock_discover
            entities = provider.fetch_entities()

        self.assertEqual(entities, [])

    def test_provider_info_id(self):
        """provider_info returns a Provider with id='kasa'."""
        provider = self._provider()
        self.assertEqual(provider.provider_info.id, "kasa")

    def test_toggle_calls_turn_on(self):
        """toggle(ip, True) calls kasa_manager.turn_on(ip)."""
        provider = self._provider()

        async def mock_turn_on(ip):
            return True

        with patch('core.kasa_control.kasa_manager') as mock_km:
            mock_km.turn_on = mock_turn_on
            result = provider.toggle("192.168.1.10", True)

        self.assertTrue(result)

    def test_toggle_calls_turn_off(self):
        """toggle(ip, False) calls kasa_manager.turn_off(ip)."""
        provider = self._provider()

        async def mock_turn_off(ip):
            return True

        with patch('core.kasa_control.kasa_manager') as mock_km:
            mock_km.turn_off = mock_turn_off
            result = provider.toggle("192.168.1.10", False)

        self.assertTrue(result)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run to confirm FAIL**

```
python -m pytest tests/test_kasa_provider.py -v
```
Expected: `ModuleNotFoundError: No module named 'core.providers'`

- [ ] **Step 3: Create `core/providers/__init__.py`**

```python
# core/providers/__init__.py
"""Provider adapter package for ADA's multi-provider architecture."""
```

- [ ] **Step 4: Create `core/providers/base_provider.py`**

```python
# core/providers/base_provider.py
"""
Abstract base class that all provider adapters must implement.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from core.entity_models import Provider, Entity


class BaseProvider(ABC):
    """
    Contract for all automation provider adapters.

    Implementations must be resilient — every public method must catch
    exceptions internally and return safe empty values on failure.
    """

    @property
    @abstractmethod
    def provider_info(self) -> Provider:
        """Return current Provider metadata (reads live from settings)."""
        ...

    @abstractmethod
    def fetch_entities(self) -> list[Entity]:
        """
        Discover and return all entities from this provider.
        Never raises — returns [] on any error.
        """
        ...

    @abstractmethod
    def test_connection(self) -> bool:
        """
        Test reachability of this provider.
        Updates provider_info.status as a side effect.
        Never raises.
        """
        ...

    @abstractmethod
    def toggle(self, provider_entity_id: str, on: bool) -> bool:
        """
        Turn an entity on or off.
        Returns True on success, False on any error.
        Never raises.
        """
        ...

    def set_brightness(self, provider_entity_id: str, value: int) -> bool:
        """
        Set brightness 0-100. Default no-op returns False.
        Override in providers that support brightness.
        """
        return False
```

- [ ] **Step 5: Create `core/providers/kasa_provider.py`**

```python
# core/providers/kasa_provider.py
"""
KasaProvider — wraps core.kasa_control.kasa_manager for the multi-provider
architecture. Kasa uses async discovery; we run it in a fresh event loop.
All imports of kasa_manager are lazy (inside methods) to keep the module
importable in test environments without real Kasa hardware.
"""
from __future__ import annotations

import asyncio
import time

from core.entity_models import Provider, Entity, infer_zone, infer_capabilities
from core.providers.base_provider import BaseProvider
from core.settings_store import settings


class KasaProvider(BaseProvider):
    """Adapter that exposes Kasa smart devices as normalized ADA Entities."""

    PROVIDER_ID = "kasa"

    def __init__(self):
        self._provider = Provider(
            id=self.PROVIDER_ID,
            name="Kasa",
            enabled=settings.get("kasa.enabled", True),
            type="kasa",
            priority=settings.get("kasa.priority", 50),
        )

    @property
    def provider_info(self) -> Provider:
        self._provider.enabled = settings.get("kasa.enabled", True)
        self._provider.priority = settings.get("kasa.priority", 50)
        return self._provider

    # ------------------------------------------------------------------ #

    def fetch_entities(self) -> list[Entity]:
        try:
            from core.kasa_control import kasa_manager
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            devices_dict = loop.run_until_complete(kasa_manager.discover_devices())
            loop.close()
        except Exception as e:
            print(f"[KasaProvider] fetch_entities failed: {e}")
            return []

        entities: list[Entity] = []
        for ip, dev in devices_dict.items():
            alias = dev.get("alias", ip)
            has_brightness = dev.get("brightness") is not None
            entity_type = "light" if (has_brightness or "Bulb" in dev.get("type", "")) else "switch"

            attrs: dict = {
                "ip": ip,
                "model": dev.get("model", ""),
                "kasa_type": dev.get("type", ""),
            }
            if has_brightness:
                attrs["brightness"] = dev["brightness"]
            if dev.get("is_color"):
                attrs["is_color"] = True

            caps = infer_capabilities(entity_type, attrs)

            entities.append(Entity(
                id=f"kasa.{ip}",
                provider=self.PROVIDER_ID,
                provider_entity_id=ip,
                name=alias,
                type=entity_type,
                zone=infer_zone(alias),
                state="on" if dev.get("is_on") else "off",
                attributes=attrs,
                capabilities=caps,
                read_only=False,
                available=True,
                last_updated=time.time(),
            ))
        return entities

    def test_connection(self) -> bool:
        try:
            from core.kasa_control import kasa_manager
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            result = loop.run_until_complete(kasa_manager.discover_devices())
            loop.close()
            ok = bool(result)
            self._provider.status = "connected" if ok else "disconnected"
            return ok
        except Exception as e:
            print(f"[KasaProvider] test_connection failed: {e}")
            self._provider.status = "error"
            return False

    def toggle(self, provider_entity_id: str, on: bool) -> bool:
        try:
            from core.kasa_control import kasa_manager
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            if on:
                result = loop.run_until_complete(kasa_manager.turn_on(provider_entity_id))
            else:
                result = loop.run_until_complete(kasa_manager.turn_off(provider_entity_id))
            loop.close()
            return result
        except Exception as e:
            print(f"[KasaProvider] toggle({provider_entity_id}, {on}) failed: {e}")
            return False

    def set_brightness(self, provider_entity_id: str, value: int) -> bool:
        try:
            from core.kasa_control import kasa_manager
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            result = loop.run_until_complete(
                kasa_manager.set_brightness(provider_entity_id, value)
            )
            loop.close()
            return result
        except Exception as e:
            print(f"[KasaProvider] set_brightness({provider_entity_id}) failed: {e}")
            return False


# Global singleton
kasa_provider = KasaProvider()
```

- [ ] **Step 6: Run tests to confirm PASS**

```
python -m pytest tests/test_kasa_provider.py -v
```
Expected: `10 passed`

- [ ] **Step 7: Commit**

```bash
git add core/providers/__init__.py core/providers/base_provider.py core/providers/kasa_provider.py tests/test_kasa_provider.py
git commit -m "feat: add BaseProvider ABC and KasaProvider adapter"
```

---

## Task 4: HAProvider adapter

**Files:**
- Create: `core/providers/ha_provider.py`
- Create: `tests/test_ha_provider.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_ha_provider.py
"""
Tests for HAProvider adapter.
All HTTP calls are mocked — no real HA instance needed.
"""
import sys
import os
import time
import unittest
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))


def _fake_settings(key, default=None):
    return {
        "home_assistant.enabled": True,
        "home_assistant.url": "http://ha.local:8123",
        "home_assistant.token": "fake-token",
        "home_assistant.tts_service": "tts.piper",
    }.get(key, default)


class TestHAProviderFetchEntities(unittest.TestCase):

    def _provider(self):
        with patch('core.settings_store.settings') as mock_s:
            mock_s.get.side_effect = _fake_settings
            from core.providers.ha_provider import HAProvider
            return HAProvider()

    def _raw_entities(self):
        return {
            "light.kitchen": {
                "entity_id": "light.kitchen",
                "state": "on",
                "attributes": {"friendly_name": "Cuisine Light", "brightness": 200},
            },
            "sensor.temperature": {
                "entity_id": "sensor.temperature",
                "state": "22.5",
                "attributes": {"friendly_name": "Bureau Temp", "device_class": "temperature",
                               "unit_of_measurement": "°C"},
            },
            "camera.front_door": {
                "entity_id": "camera.front_door",
                "state": "idle",
                "attributes": {"friendly_name": "Front Door Camera"},
            },
            "media_player.salon": {
                "entity_id": "media_player.salon",
                "state": "idle",
                "attributes": {"friendly_name": "Salon Speaker", "volume_level": 0.4},
            },
        }

    def test_returns_entity_for_each_ha_entity(self):
        """fetch_entities() returns one Entity per HA state."""
        provider = self._provider()
        with patch('core.ha_control.ha_manager') as mock_ha:
            mock_ha.reload_config.return_value = None
            mock_ha._fetch_all_states.return_value = self._raw_entities()
            entities = provider.fetch_entities()

        self.assertEqual(len(entities), 4)

    def test_entity_ids_prefixed_with_home_assistant(self):
        """Entity.id is 'home_assistant.{ha_entity_id}'."""
        provider = self._provider()
        with patch('core.ha_control.ha_manager') as mock_ha:
            mock_ha.reload_config.return_value = None
            mock_ha._fetch_all_states.return_value = self._raw_entities()
            entities = provider.fetch_entities()

        ids = {e.id for e in entities}
        self.assertIn("home_assistant.light.kitchen", ids)
        self.assertIn("home_assistant.sensor.temperature", ids)

    def test_light_entity_has_brightness_capability(self):
        """HA light with brightness attr gets 'brightness' capability."""
        provider = self._provider()
        with patch('core.ha_control.ha_manager') as mock_ha:
            mock_ha.reload_config.return_value = None
            mock_ha._fetch_all_states.return_value = self._raw_entities()
            entities = provider.fetch_entities()

        light = next(e for e in entities if e.id == "home_assistant.light.kitchen")
        self.assertIn("brightness", light.capabilities)

    def test_sensor_is_read_only(self):
        """Sensor entities are read_only=True."""
        provider = self._provider()
        with patch('core.ha_control.ha_manager') as mock_ha:
            mock_ha.reload_config.return_value = None
            mock_ha._fetch_all_states.return_value = self._raw_entities()
            entities = provider.fetch_entities()

        sensor = next(e for e in entities if e.id == "home_assistant.sensor.temperature")
        self.assertTrue(sensor.read_only)

    def test_media_player_has_tts_capability(self):
        """HA media_player entities always have 'tts' capability."""
        provider = self._provider()
        with patch('core.ha_control.ha_manager') as mock_ha:
            mock_ha.reload_config.return_value = None
            mock_ha._fetch_all_states.return_value = self._raw_entities()
            entities = provider.fetch_entities()

        mp = next(e for e in entities if e.id == "home_assistant.media_player.salon")
        self.assertIn("tts", mp.capabilities)

    def test_zone_inferred_from_friendly_name(self):
        """Zone is inferred from the entity's friendly_name attribute."""
        provider = self._provider()
        with patch('core.ha_control.ha_manager') as mock_ha:
            mock_ha.reload_config.return_value = None
            mock_ha._fetch_all_states.return_value = self._raw_entities()
            entities = provider.fetch_entities()

        sensor = next(e for e in entities if e.id == "home_assistant.sensor.temperature")
        self.assertEqual(sensor.zone, "Bureau")

    def test_returns_empty_when_disabled(self):
        """fetch_entities() returns [] when HA is disabled in settings."""
        with patch('core.settings_store.settings') as mock_s:
            mock_s.get.side_effect = lambda key, default=None: {
                "home_assistant.enabled": False,
            }.get(key, default)
            from core.providers.ha_provider import HAProvider
            provider = HAProvider()

        entities = provider.fetch_entities()
        self.assertEqual(entities, [])

    def test_returns_empty_on_exception(self):
        """fetch_entities() returns [] if ha_manager raises."""
        provider = self._provider()
        with patch('core.ha_control.ha_manager') as mock_ha:
            mock_ha.reload_config.side_effect = RuntimeError("ha down")
            entities = provider.fetch_entities()

        self.assertEqual(entities, [])

    def test_toggle_on_calls_ha_turn_on(self):
        """toggle(entity_id, True) calls ha_manager.turn_on()."""
        provider = self._provider()
        with patch('core.ha_control.ha_manager') as mock_ha:
            mock_ha.turn_on.return_value = True
            result = provider.toggle("light.kitchen", True)

        mock_ha.turn_on.assert_called_once_with("light.kitchen")
        self.assertTrue(result)

    def test_toggle_off_calls_ha_turn_off(self):
        """toggle(entity_id, False) calls ha_manager.turn_off()."""
        provider = self._provider()
        with patch('core.ha_control.ha_manager') as mock_ha:
            mock_ha.turn_off.return_value = True
            result = provider.toggle("light.kitchen", False)

        mock_ha.turn_off.assert_called_once_with("light.kitchen")
        self.assertTrue(result)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run to confirm FAIL**

```
python -m pytest tests/test_ha_provider.py -v
```
Expected: `ModuleNotFoundError: No module named 'core.providers.ha_provider'`

- [ ] **Step 3: Create `core/providers/ha_provider.py`**

```python
# core/providers/ha_provider.py
"""
HAProvider — wraps core.ha_control.ha_manager for the multi-provider
architecture. All HTTP I/O is synchronous (ha_manager uses requests).
All imports of ha_manager are lazy (inside methods) to keep the module
importable in test environments.
"""
from __future__ import annotations

import time

from core.entity_models import (
    Provider, Entity,
    infer_zone, infer_capabilities, ha_domain_to_entity_type,
)
from core.providers.base_provider import BaseProvider
from core.settings_store import settings

# Domains that HA considers read-only (no turn_on/turn_off service)
_READ_ONLY_DOMAINS = frozenset({"sensor", "binary_sensor", "camera"})


class HAProvider(BaseProvider):
    """Adapter that exposes Home Assistant entities as normalized ADA Entities."""

    PROVIDER_ID = "home_assistant"

    def __init__(self):
        self._provider = Provider(
            id=self.PROVIDER_ID,
            name="Home Assistant",
            enabled=settings.get("home_assistant.enabled", False),
            type="home_assistant",
            base_url=settings.get("home_assistant.url", ""),
            token=settings.get("home_assistant.token", ""),
            priority=100,
        )

    @property
    def provider_info(self) -> Provider:
        self._provider.enabled = settings.get("home_assistant.enabled", False)
        self._provider.base_url = settings.get("home_assistant.url", "")
        self._provider.token = settings.get("home_assistant.token", "")
        return self._provider

    # ------------------------------------------------------------------ #

    def fetch_entities(self) -> list[Entity]:
        if not self.provider_info.enabled:
            return []
        try:
            from core.ha_control import ha_manager
            ha_manager.reload_config()
            raw = ha_manager._fetch_all_states()
        except Exception as e:
            print(f"[HAProvider] fetch_entities failed: {e}")
            return []

        entities: list[Entity] = []
        for entity_id, info in raw.items():
            domain = entity_id.split(".")[0]
            attrs = info.get("attributes", {})
            name = attrs.get("friendly_name", entity_id)
            entity_type = ha_domain_to_entity_type(domain)
            read_only = domain in _READ_ONLY_DOMAINS

            caps = infer_capabilities(entity_type, attrs, read_only=read_only)
            state = info.get("state", "unknown")
            available = state not in ("unavailable", "unknown")

            entities.append(Entity(
                id=f"{self.PROVIDER_ID}.{entity_id}",
                provider=self.PROVIDER_ID,
                provider_entity_id=entity_id,
                name=name,
                type=entity_type,
                zone=infer_zone(name),
                state=state,
                attributes=attrs,
                capabilities=caps,
                read_only=read_only,
                available=available,
                last_updated=time.time(),
            ))
        return entities

    def test_connection(self) -> bool:
        try:
            from core.ha_control import ha_manager
            ha_manager.reload_config()
            ok = ha_manager.test_connection()
            self._provider.status = "connected" if ok else "disconnected"
            return ok
        except Exception as e:
            print(f"[HAProvider] test_connection failed: {e}")
            self._provider.status = "error"
            return False

    def toggle(self, provider_entity_id: str, on: bool) -> bool:
        try:
            from core.ha_control import ha_manager
            if on:
                return ha_manager.turn_on(provider_entity_id)
            else:
                return ha_manager.turn_off(provider_entity_id)
        except Exception as e:
            print(f"[HAProvider] toggle({provider_entity_id}, {on}) failed: {e}")
            return False

    def set_brightness(self, provider_entity_id: str, value: int) -> bool:
        try:
            from core.ha_control import ha_manager
            return ha_manager.turn_on(provider_entity_id, brightness_pct=value)
        except Exception as e:
            print(f"[HAProvider] set_brightness({provider_entity_id}) failed: {e}")
            return False


# Global singleton
ha_provider = HAProvider()
```

- [ ] **Step 4: Run to confirm PASS**

```
python -m pytest tests/test_ha_provider.py -v
```
Expected: `10 passed`

- [ ] **Step 5: Commit**

```bash
git add core/providers/ha_provider.py tests/test_ha_provider.py
git commit -m "feat: add HAProvider adapter wrapping ha_manager"
```

---

## Task 5: UnifiedEntityService

**Files:**
- Create: `core/unified_entities.py`
- Create: `tests/test_unified_entities.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_unified_entities.py
"""
Tests for UnifiedEntityService — provider orchestration + entity actions.
Providers are mocked: no real Kasa/HA calls.
"""
import sys
import os
import unittest
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from core.entity_models import Provider, Entity


def _make_entity(entity_id: str, provider: str, entity_type: str = "light",
                  state: str = "on", read_only: bool = False,
                  capabilities: list | None = None) -> Entity:
    return Entity(
        id=f"{provider}.{entity_id}",
        provider=provider,
        provider_entity_id=entity_id,
        name=f"Test {entity_id}",
        type=entity_type,
        zone="Other",
        state=state,
        capabilities=capabilities or ["read", "control"],
        read_only=read_only,
    )


def _make_provider_mock(provider_id: str, entities: list[Entity], enabled: bool = True):
    mock = MagicMock()
    mock.provider_info = Provider(
        id=provider_id, name=provider_id.title(),
        enabled=enabled, type=provider_id
    )
    mock.fetch_entities.return_value = entities
    mock.toggle.return_value = True
    mock.set_brightness.return_value = True
    return mock


class TestGetUnifiedEntities(unittest.TestCase):

    def _service(self, providers: dict):
        from core.unified_entities import UnifiedEntityService
        svc = UnifiedEntityService.__new__(UnifiedEntityService)
        svc._entities = []
        svc._providers = providers
        return svc

    def test_merges_entities_from_all_enabled_providers(self):
        """get_unified_entities() aggregates entities from all providers."""
        kasa_mock = _make_provider_mock("kasa", [_make_entity("1.2.3.4", "kasa")])
        ha_mock = _make_provider_mock("home_assistant", [_make_entity("light.desk", "home_assistant")])
        svc = self._service({"kasa": kasa_mock, "home_assistant": ha_mock})

        entities = svc.get_unified_entities(force_refresh=True)
        self.assertEqual(len(entities), 2)

    def test_skips_disabled_providers(self):
        """Disabled providers are not fetched."""
        kasa_mock = _make_provider_mock("kasa", [_make_entity("1.2.3.4", "kasa")], enabled=False)
        ha_mock = _make_provider_mock("home_assistant", [_make_entity("light.desk", "home_assistant")])
        svc = self._service({"kasa": kasa_mock, "home_assistant": ha_mock})

        entities = svc.get_unified_entities(force_refresh=True)
        self.assertEqual(len(entities), 1)
        self.assertEqual(entities[0].provider, "home_assistant")

    def test_no_duplicate_entity_ids(self):
        """If two providers return the same entity id, only first is kept."""
        e1 = _make_entity("duplicate", "kasa")
        e2 = _make_entity("duplicate", "kasa")   # same id
        mock = _make_provider_mock("kasa", [e1, e2])
        svc = self._service({"kasa": mock})

        entities = svc.get_unified_entities(force_refresh=True)
        self.assertEqual(len(entities), 1)

    def test_provider_failure_does_not_crash_others(self):
        """If provider A raises, provider B still returns entities."""
        kasa_mock = _make_provider_mock("kasa", [])
        kasa_mock.fetch_entities.side_effect = RuntimeError("kasa down")
        ha_mock = _make_provider_mock("home_assistant", [_make_entity("light.desk", "home_assistant")])
        svc = self._service({"kasa": kasa_mock, "home_assistant": ha_mock})

        entities = svc.get_unified_entities(force_refresh=True)
        self.assertEqual(len(entities), 1)


class TestToggleEntity(unittest.TestCase):

    def _service_with_entities(self, entities: list[Entity], provider_mock):
        from core.unified_entities import UnifiedEntityService
        svc = UnifiedEntityService.__new__(UnifiedEntityService)
        svc._entities = entities
        svc._providers = {entities[0].provider: provider_mock}
        return svc

    def test_toggle_calls_provider_toggle(self):
        """toggle_entity() delegates to the provider's toggle()."""
        entity = _make_entity("light.desk", "kasa")
        mock = _make_provider_mock("kasa", [entity])
        svc = self._service_with_entities([entity], mock)

        result = svc.toggle_entity("kasa.light.desk")
        mock.toggle.assert_called_once()
        self.assertTrue(result)

    def test_toggle_returns_false_for_unknown_entity(self):
        """toggle_entity() returns False if entity id not found."""
        entity = _make_entity("light.desk", "kasa")
        mock = _make_provider_mock("kasa", [entity])
        svc = self._service_with_entities([entity], mock)

        result = svc.toggle_entity("kasa.nonexistent")
        self.assertFalse(result)

    def test_toggle_returns_false_for_read_only(self):
        """toggle_entity() returns False for read-only entities."""
        entity = _make_entity("sensor.temp", "kasa", read_only=True)
        mock = _make_provider_mock("kasa", [entity])
        svc = self._service_with_entities([entity], mock)

        result = svc.toggle_entity("kasa.sensor.temp")
        self.assertFalse(result)

    def test_set_brightness_calls_provider(self):
        """set_entity_brightness() delegates to provider.set_brightness()."""
        entity = _make_entity("light.desk", "kasa", capabilities=["read", "control", "brightness"])
        mock = _make_provider_mock("kasa", [entity])
        svc = self._service_with_entities([entity], mock)

        result = svc.set_entity_brightness("kasa.light.desk", 75)
        mock.set_brightness.assert_called_once_with("light.desk", 75)
        self.assertTrue(result)

    def test_set_brightness_returns_false_without_capability(self):
        """set_entity_brightness() returns False if entity lacks 'brightness' cap."""
        entity = _make_entity("switch.plug", "kasa", capabilities=["read", "control"])
        mock = _make_provider_mock("kasa", [entity])
        svc = self._service_with_entities([entity], mock)

        result = svc.set_entity_brightness("kasa.switch.plug", 50)
        self.assertFalse(result)


class TestTestProviderConnection(unittest.TestCase):

    def test_delegates_to_provider(self):
        """test_provider_connection() calls the provider's test_connection()."""
        from core.unified_entities import UnifiedEntityService
        svc = UnifiedEntityService.__new__(UnifiedEntityService)
        mock = MagicMock()
        mock.test_connection.return_value = True
        svc._providers = {"kasa": mock}
        svc._entities = []

        result = svc.test_provider_connection("kasa")
        mock.test_connection.assert_called_once()
        self.assertTrue(result)

    def test_returns_false_for_unknown_provider(self):
        """test_provider_connection() returns False for unknown provider id."""
        from core.unified_entities import UnifiedEntityService
        svc = UnifiedEntityService.__new__(UnifiedEntityService)
        svc._providers = {}
        svc._entities = []

        self.assertFalse(svc.test_provider_connection("nonexistent"))


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run to confirm FAIL**

```
python -m pytest tests/test_unified_entities.py -v
```
Expected: `ModuleNotFoundError: No module named 'core.unified_entities'`

- [ ] **Step 3: Create `core/unified_entities.py`**

```python
# core/unified_entities.py
"""
UnifiedEntityService — aggregates entities from all enabled providers,
merges them into a single list, and exposes action helpers for the UI.

Usage:
    from core.unified_entities import unified_entity_service
    entities = unified_entity_service.get_unified_entities(force_refresh=True)
    unified_entity_service.toggle_entity("kasa.192.168.1.10")
"""
from __future__ import annotations

import threading
from typing import Optional

from core.entity_models import Entity, Provider

_lock = threading.Lock()


class UnifiedEntityService:
    """
    Orchestrates all registered provider adapters and exposes a unified
    entity list to the UI layer.

    Thread-safe: refresh_providers() acquires a lock; the UI reads
    _entities after the background thread emits done.
    """

    def __init__(self):
        self._entities: list[Entity] = []
        self._providers: dict = {}
        self._register_defaults()

    def _register_defaults(self):
        try:
            from core.providers.kasa_provider import kasa_provider
            self._providers["kasa"] = kasa_provider
        except Exception as e:
            print(f"[UnifiedEntityService] Could not register kasa_provider: {e}")
        try:
            from core.providers.ha_provider import ha_provider
            self._providers["home_assistant"] = ha_provider
        except Exception as e:
            print(f"[UnifiedEntityService] Could not register ha_provider: {e}")

    # ------------------------------------------------------------------ #
    # Query                                                                #
    # ------------------------------------------------------------------ #

    def get_providers(self) -> list[Provider]:
        """Return current metadata for all registered providers."""
        return [p.provider_info for p in self._providers.values()]

    def get_unified_entities(self, force_refresh: bool = False) -> list[Entity]:
        """
        Return the cached entity list, optionally refreshing from all providers first.
        Callers in background threads should pass force_refresh=True.
        """
        if force_refresh or not self._entities:
            self.refresh_providers()
        return list(self._entities)

    def get_entity(self, entity_id: str) -> Optional[Entity]:
        """Look up a single entity by its ADA entity id."""
        for e in self._entities:
            if e.id == entity_id:
                return e
        return None

    # ------------------------------------------------------------------ #
    # Refresh                                                              #
    # ------------------------------------------------------------------ #

    def refresh_providers(self):
        """
        Fetch entities from all enabled providers, merge results, deduplicate.
        Thread-safe. Individual provider failures are caught and logged.
        """
        with _lock:
            new_entities: list[Entity] = []
            seen_ids: set[str] = set()

            for provider_id, provider in self._providers.items():
                info = provider.provider_info
                if not info.enabled:
                    continue
                try:
                    for e in provider.fetch_entities():
                        if e.id not in seen_ids:
                            seen_ids.add(e.id)
                            new_entities.append(e)
                except Exception as ex:
                    print(f"[UnifiedEntityService] Provider '{provider_id}' raised: {ex}")

            self._entities = new_entities

    # ------------------------------------------------------------------ #
    # Actions                                                              #
    # ------------------------------------------------------------------ #

    def toggle_entity(self, entity_id: str, on: Optional[bool] = None) -> bool:
        """
        Toggle entity on/off. If `on` is None, toggles current state.
        Returns False for read-only entities or unknown ids.
        """
        entity = self.get_entity(entity_id)
        if entity is None or entity.read_only:
            return False
        provider = self._providers.get(entity.provider)
        if provider is None:
            return False
        target_on = on if on is not None else (entity.state != "on")
        try:
            result = provider.toggle(entity.provider_entity_id, target_on)
            if result:
                entity.state = "on" if target_on else "off"
            return result
        except Exception as e:
            print(f"[UnifiedEntityService] toggle_entity({entity_id}) failed: {e}")
            return False

    def set_entity_brightness(self, entity_id: str, value: int) -> bool:
        """
        Set brightness 0-100 for an entity that has 'brightness' capability.
        Returns False if entity lacks the capability or provider fails.
        """
        entity = self.get_entity(entity_id)
        if entity is None or "brightness" not in entity.capabilities:
            return False
        provider = self._providers.get(entity.provider)
        if provider is None:
            return False
        try:
            return provider.set_brightness(entity.provider_entity_id, value)
        except Exception as e:
            print(f"[UnifiedEntityService] set_entity_brightness({entity_id}) failed: {e}")
            return False

    def send_tts_to_entity(self, entity_id: str, message: str) -> bool:
        """
        Send TTS speech to an entity that has 'tts' capability.
        Currently only HA media_player entities support TTS.
        """
        entity = self.get_entity(entity_id)
        if entity is None or "tts" not in entity.capabilities:
            return False
        if entity.provider == "home_assistant":
            try:
                from core.ha_control import ha_manager
                from core.settings_store import settings
                tts_service = settings.get("home_assistant.tts_service", "tts.piper")
                return ha_manager.speak_to_media_player(
                    entity.provider_entity_id, message, tts_service
                )
            except Exception as e:
                print(f"[UnifiedEntityService] send_tts_to_entity({entity_id}) failed: {e}")
                return False
        return False

    def test_provider_connection(self, provider_id: str) -> bool:
        """Test connectivity to a specific provider. Updates its status."""
        provider = self._providers.get(provider_id)
        if provider is None:
            return False
        return provider.test_connection()


# Global singleton
unified_entity_service = UnifiedEntityService()
```

- [ ] **Step 4: Run to confirm PASS**

```
python -m pytest tests/test_unified_entities.py -v
```
Expected: `11 passed`

- [ ] **Step 5: Run full suite to confirm no regressions**

```
python -m pytest tests/ -v --tb=short
```
Expected: all previously passing tests still pass.

- [ ] **Step 6: Commit**

```bash
git add core/unified_entities.py tests/test_unified_entities.py
git commit -m "feat: add UnifiedEntityService — multi-provider fetch, toggle, brightness, TTS"
```

---

## Task 6: Specialized entity cards

**Files:**
- Create: `gui/components/entity_cards.py`

No unit tests for this task — widgets require a QApplication instance. Verify by running the app and opening the Home tab after Task 7 is complete.

- [ ] **Step 1: Create `gui/components/entity_cards.py`**

```python
# gui/components/entity_cards.py
"""
Specialized card widgets for the Environmental Control grid.
Each card type matches one ADA entity type. The factory function
entity_card_for() picks the right card automatically.

All cards:
  - Accept an Entity dataclass (from core.entity_models)
  - Accept a UnifiedEntityService for dispatching actions
  - Are fixed-width QFrame widgets in the ADA dark-cyber style
"""
from __future__ import annotations

from typing import TYPE_CHECKING

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QColor, QPixmap
from PySide6.QtWidgets import (
    QFrame, QVBoxLayout, QHBoxLayout, QLabel, QPushButton
)

from qfluentwidgets import (
    FluentIcon as FIF, IconWidget, SwitchButton, Slider,
    ColorPickerButton, ToolButton
)

if TYPE_CHECKING:
    from core.entity_models import Entity
    from core.unified_entities import UnifiedEntityService

# ---------------------------------------------------------------------------
# Shared styles
# ---------------------------------------------------------------------------

_CARD_W = 300

_CARD_STYLE = lambda cls: f"""
    {cls} {{
        background-color: #1a2236;
        border: 1px solid #2a3556;
        border-radius: 20px;
    }}
"""

_ICON_BOX_STYLE = "background-color: #232d45; border-radius: 12px;"

_NAME_STYLE   = "color: white; font-weight: bold; font-size: 15px; background: transparent;"
_SUB_STYLE    = "color: #6e7a8e; font-size: 11px; font-weight: bold; background: transparent;"
_VALUE_STYLE  = "color: #33b5e5; font-size: 18px; font-weight: bold; background: transparent;"
_RO_STYLE     = "color: #6e7a8e; font-size: 10px; font-weight: bold; background: transparent;"

_PROVIDER_COLORS = {
    "kasa":           "#f59e0b",
    "home_assistant": "#33b5e5",
}

_BTN_STYLE = """
    QPushButton {
        background-color: #33b5e5; color: #0f1524;
        border-radius: 8px; padding: 3px 10px;
        font-weight: bold; border: none; font-size: 11px;
    }
    QPushButton:hover { background-color: #55caff; }
"""


def _make_icon_box(icon) -> QFrame:
    box = QFrame()
    box.setFixedSize(40, 40)
    box.setStyleSheet(_ICON_BOX_STYLE)
    lay = QVBoxLayout(box)
    lay.setAlignment(Qt.AlignCenter)
    lay.setContentsMargins(0, 0, 0, 0)
    iw = IconWidget(icon)
    iw.setFixedSize(20, 20)
    lay.addWidget(iw)
    return box


def _provider_badge(provider_id: str) -> QLabel:
    color = _PROVIDER_COLORS.get(provider_id, "#6e7a8e")
    name = provider_id.replace("_", " ").title()
    lbl = QLabel(name)
    lbl.setStyleSheet(
        f"color: {color}; font-size: 10px; font-weight: bold;"
        " background: transparent; border: none;"
    )
    return lbl


# ---------------------------------------------------------------------------
# LightEntityCard
# ---------------------------------------------------------------------------

class LightEntityCard(QFrame):
    """Card for light entities (Kasa bulbs, HA lights)."""

    def __init__(self, entity: "Entity", service: "UnifiedEntityService", parent=None):
        super().__init__(parent)
        self.entity = entity
        self.service = service
        self.setFixedSize(_CARD_W, 175)
        self.setStyleSheet(_CARD_STYLE("LightEntityCard"))

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 18, 20, 18)
        layout.setSpacing(6)

        # Header: icon + toggle
        header = QHBoxLayout()
        header.addWidget(_make_icon_box(FIF.BRIGHTNESS))
        header.addStretch()
        if not entity.read_only:
            self.toggle = SwitchButton()
            self.toggle.setChecked(entity.state == "on")
            self.toggle.checkedChanged.connect(self._on_toggle)
            header.addWidget(self.toggle)
        layout.addLayout(header)

        layout.addWidget(_label(entity.name, _NAME_STYLE))

        # Provider + zone
        meta = QHBoxLayout()
        meta.addWidget(_provider_badge(entity.provider))
        meta.addStretch()
        meta.addWidget(_label(entity.zone, _SUB_STYLE))
        layout.addLayout(meta)

        # Controls
        controls = QHBoxLayout()
        controls.setContentsMargins(0, 4, 0, 0)
        if "brightness" in entity.capabilities:
            self.slider = Slider(Qt.Horizontal)
            self.slider.setRange(0, 100)
            val = entity.attributes.get("brightness")
            if val is not None:
                # HA brightness is 0-255, Kasa is 0-100
                pct = int(val / 255 * 100) if val > 100 else int(val)
                self.slider.setValue(pct)
            else:
                self.slider.setValue(100)
            self.slider.sliderReleased.connect(self._on_brightness)
            controls.addWidget(self.slider)

        if "color" in entity.capabilities:
            self.color_btn = ColorPickerButton(QColor("#ffffff"), "Color")
            self.color_btn.setFixedSize(30, 24)
            self.color_btn.colorChanged.connect(self._on_color)
            controls.addWidget(self.color_btn)

        if controls.count():
            layout.addLayout(controls)
        else:
            layout.addStretch()

    def _on_toggle(self, checked: bool):
        self.service.toggle_entity(self.entity.id, checked)

    def _on_brightness(self):
        self.service.set_entity_brightness(self.entity.id, self.slider.value())

    def _on_color(self, color: QColor):
        # Kasa uses HSV; HA uses rgb_color — providers handle the translation
        h = color.hsvHue()
        s = int(color.hsvSaturationF() * 100)
        v = int(color.valueF() * 100)
        # For HA: store in attributes for provider to read; for Kasa: direct
        if self.entity.provider == "kasa":
            try:
                from core.kasa_control import kasa_manager
                import asyncio
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                loop.run_until_complete(
                    kasa_manager.set_hsv(self.entity.provider_entity_id, h, s, v)
                )
                loop.close()
            except Exception as e:
                print(f"[LightEntityCard] color change failed: {e}")


# ---------------------------------------------------------------------------
# SwitchEntityCard
# ---------------------------------------------------------------------------

class SwitchEntityCard(QFrame):
    """Card for switch/script/scene entities."""

    def __init__(self, entity: "Entity", service: "UnifiedEntityService", parent=None):
        super().__init__(parent)
        self.entity = entity
        self.service = service
        self.setFixedSize(_CARD_W, 160)
        self.setStyleSheet(_CARD_STYLE("SwitchEntityCard"))

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)

        header = QHBoxLayout()
        header.addWidget(_make_icon_box(FIF.TILES))
        header.addStretch()
        if not entity.read_only:
            self.toggle = SwitchButton()
            self.toggle.setChecked(entity.state == "on")
            self.toggle.checkedChanged.connect(self._on_toggle)
            header.addWidget(self.toggle)
        layout.addLayout(header)

        layout.addWidget(_label(entity.name, _NAME_STYLE))

        meta = QHBoxLayout()
        meta.addWidget(_provider_badge(entity.provider))
        meta.addStretch()
        meta.addWidget(_label(entity.zone, _SUB_STYLE))
        layout.addLayout(meta)
        layout.addStretch()

    def _on_toggle(self, checked: bool):
        self.service.toggle_entity(self.entity.id, checked)


# ---------------------------------------------------------------------------
# SensorEntityCard
# ---------------------------------------------------------------------------

_DC_ICONS = {
    "temperature": "🌡", "humidity": "💧", "pressure": "🔵",
    "battery": "🔋", "illuminance": "☀", "co2": "💨",
    "power": "⚡", "energy": "⚡", "voltage": "⚡", "current": "⚡",
    "motion": "👁", "door": "🚪", "window": "🪟", "smoke": "🔥",
}

_DC_COLORS = {
    "temperature": "#ff7043", "humidity": "#29b6f6",
    "energy": "#ffca28", "power": "#ab47bc", "battery": "#66bb6a",
}


class SensorEntityCard(QFrame):
    """Read-only card for numeric sensor entities."""

    def __init__(self, entity: "Entity", service: "UnifiedEntityService", parent=None):
        super().__init__(parent)
        self.entity = entity
        self.setFixedSize(_CARD_W, 160)
        self.setStyleSheet(_CARD_STYLE("SensorEntityCard"))

        attrs = entity.attributes
        dc = attrs.get("device_class", "")
        unit = attrs.get("unit_of_measurement", "")
        icon_str = _DC_ICONS.get(dc, "•")
        color = _DC_COLORS.get(dc, "#33b5e5")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)

        header = QHBoxLayout()
        header.addWidget(_make_icon_box(FIF.INFO))
        header.addStretch()
        header.addWidget(_label("READ ONLY", _RO_STYLE))
        layout.addLayout(header)

        layout.addWidget(_label(entity.name, _NAME_STYLE))

        dc_row = QHBoxLayout()
        icon_lbl = QLabel(icon_str)
        icon_lbl.setStyleSheet(f"color: {color}; font-size: 16px; background: transparent;")
        val_lbl = QLabel(f"{entity.state} {unit}".strip())
        val_lbl.setStyleSheet(f"color: {color}; font-size: 16px; font-weight: bold; background: transparent;")
        dc_row.addWidget(icon_lbl)
        dc_row.addStretch()
        dc_row.addWidget(val_lbl)
        layout.addLayout(dc_row)

        meta = QHBoxLayout()
        meta.addWidget(_provider_badge(entity.provider))
        meta.addStretch()
        meta.addWidget(_label(entity.zone, _SUB_STYLE))
        layout.addLayout(meta)


# ---------------------------------------------------------------------------
# BinarySensorEntityCard
# ---------------------------------------------------------------------------

class BinarySensorEntityCard(QFrame):
    """Read-only card for binary_sensor entities (door, motion, smoke, …)."""

    def __init__(self, entity: "Entity", service: "UnifiedEntityService", parent=None):
        super().__init__(parent)
        self.entity = entity
        self.setFixedSize(_CARD_W, 160)
        self.setStyleSheet(_CARD_STYLE("BinarySensorEntityCard"))

        attrs = entity.attributes
        dc = attrs.get("device_class", "")
        is_on = entity.state == "on"

        # Door/window → Open/Closed; generic → ON/OFF
        if dc == "door":
            display = "Open" if is_on else "Closed"
        elif dc == "window":
            display = "Open" if is_on else "Closed"
        else:
            display = "ON" if is_on else "OFF"

        color = "#4CAF50" if is_on else "#6e7a8e"

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)

        header = QHBoxLayout()
        header.addWidget(_make_icon_box(FIF.INFO))
        header.addStretch()
        header.addWidget(_label("READ ONLY", _RO_STYLE))
        layout.addLayout(header)

        layout.addWidget(_label(entity.name, _NAME_STYLE))

        state_lbl = QLabel(display)
        state_lbl.setStyleSheet(
            f"color: {color}; font-size: 20px; font-weight: bold; background: transparent;"
        )
        layout.addWidget(state_lbl)

        meta = QHBoxLayout()
        meta.addWidget(_provider_badge(entity.provider))
        meta.addStretch()
        meta.addWidget(_label(entity.zone, _SUB_STYLE))
        layout.addLayout(meta)


# ---------------------------------------------------------------------------
# MediaPlayerEntityCard
# ---------------------------------------------------------------------------

class MediaPlayerEntityCard(QFrame):
    """Card for media_player entities with optional TTS button."""

    def __init__(self, entity: "Entity", service: "UnifiedEntityService", parent=None):
        super().__init__(parent)
        self.entity = entity
        self.service = service
        self.setFixedSize(_CARD_W, 175)
        self.setStyleSheet(_CARD_STYLE("MediaPlayerEntityCard"))

        attrs = entity.attributes

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 18, 20, 18)
        layout.setSpacing(6)

        header = QHBoxLayout()
        header.addWidget(_make_icon_box(FIF.VOLUME))
        header.addStretch()
        if not entity.read_only:
            self.toggle = SwitchButton()
            self.toggle.setChecked(entity.state not in ("idle", "off", "unavailable"))
            self.toggle.checkedChanged.connect(self._on_toggle)
            header.addWidget(self.toggle)
        layout.addLayout(header)

        layout.addWidget(_label(entity.name, _NAME_STYLE))
        layout.addWidget(_label(entity.state.upper(), _SUB_STYLE))

        if "volume" in entity.capabilities:
            self.vol_slider = Slider(Qt.Horizontal)
            self.vol_slider.setRange(0, 100)
            vol = attrs.get("volume_level", 0.5)
            self.vol_slider.setValue(int(vol * 100))
            layout.addWidget(self.vol_slider)

        if "tts" in entity.capabilities:
            tts_btn = QPushButton("▶ TTS Test")
            tts_btn.setStyleSheet(_BTN_STYLE)
            tts_btn.clicked.connect(self._on_tts)
            layout.addWidget(tts_btn)

        meta = QHBoxLayout()
        meta.addWidget(_provider_badge(entity.provider))
        meta.addStretch()
        meta.addWidget(_label(entity.zone, _SUB_STYLE))
        layout.addLayout(meta)

    def _on_toggle(self, checked: bool):
        self.service.toggle_entity(self.entity.id, checked)

    def _on_tts(self):
        self.service.send_tts_to_entity(self.entity.id, "ADA is speaking.")


# ---------------------------------------------------------------------------
# CameraEntityCard (HA only — snapshots via ha_manager)
# ---------------------------------------------------------------------------

class CameraEntityCard(QFrame):
    """Card showing a camera snapshot, auto-refreshing every 5 seconds."""

    def __init__(self, entity: "Entity", service: "UnifiedEntityService", parent=None):
        super().__init__(parent)
        self.entity = entity
        self._snap_thread = None

        self.setFixedSize(_CARD_W, 230)
        self.setStyleSheet(_CARD_STYLE("CameraEntityCard"))

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self.image_label = QLabel()
        self.image_label.setFixedSize(_CARD_W, 185)
        self.image_label.setAlignment(Qt.AlignCenter)
        self.image_label.setText("⏳ Loading…")
        self.image_label.setStyleSheet(
            "color: #6e7a8e; font-size: 13px;"
            "background-color: #0d121d; border-radius: 20px 20px 0 0;"
        )
        layout.addWidget(self.image_label)

        footer = QHBoxLayout()
        footer.setContentsMargins(14, 6, 14, 8)
        footer.addWidget(_label(entity.name, _NAME_STYLE))
        footer.addStretch()
        footer.addWidget(_provider_badge(entity.provider))
        layout.addLayout(footer)

        self._fetch_snapshot()
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._fetch_snapshot)
        self._timer.start(5000)

    def _fetch_snapshot(self):
        if self.entity.provider != "home_assistant":
            return
        try:
            if self._snap_thread and self._snap_thread.isRunning():
                return
        except RuntimeError:
            self._snap_thread = None

        from PySide6.QtCore import QThread, Signal

        class _SnapThread(QThread):
            ready = Signal(bytes)
            def __init__(self, entity_id):
                super().__init__()
                self._eid = entity_id
            def run(self):
                try:
                    from core.ha_control import ha_manager
                    data = ha_manager.get_camera_snapshot(self._eid)
                    if data:
                        self.ready.emit(data)
                except Exception:
                    pass

        self._snap_thread = _SnapThread(self.entity.provider_entity_id)
        self._snap_thread.ready.connect(self._on_snapshot)
        self._snap_thread.finished.connect(self._snap_thread.deleteLater)
        self._snap_thread.start()

    def _on_snapshot(self, data: bytes):
        px = QPixmap()
        px.loadFromData(data)
        scaled = px.scaled(_CARD_W, 185, Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation)
        self.image_label.setPixmap(scaled)
        self.image_label.setStyleSheet(
            "background-color: #0d121d; border-radius: 20px 20px 0 0;"
        )

    def stop(self):
        self._timer.stop()
        if self._snap_thread and self._snap_thread.isRunning():
            self._snap_thread.quit()
            self._snap_thread.wait(2000)


# ---------------------------------------------------------------------------
# FallbackEntityCard
# ---------------------------------------------------------------------------

class FallbackEntityCard(QFrame):
    """Generic card for entity types without a dedicated widget."""

    def __init__(self, entity: "Entity", service: "UnifiedEntityService", parent=None):
        super().__init__(parent)
        self.entity = entity
        self.setFixedSize(_CARD_W, 160)
        self.setStyleSheet(_CARD_STYLE("FallbackEntityCard"))

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)

        header = QHBoxLayout()
        header.addWidget(_make_icon_box(FIF.TILES))
        header.addStretch()
        layout.addLayout(header)

        layout.addWidget(_label(entity.name, _NAME_STYLE))
        layout.addWidget(_label(entity.type.upper(), _SUB_STYLE))
        layout.addWidget(_label(entity.state, _VALUE_STYLE))

        meta = QHBoxLayout()
        meta.addWidget(_provider_badge(entity.provider))
        meta.addStretch()
        meta.addWidget(_label(entity.zone, _SUB_STYLE))
        layout.addLayout(meta)


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------

_TYPE_TO_CARD = {
    "light":         LightEntityCard,
    "switch":        SwitchEntityCard,
    "sensor":        SensorEntityCard,
    "binary_sensor": BinarySensorEntityCard,
    "media_player":  MediaPlayerEntityCard,
    "camera":        CameraEntityCard,
}


def entity_card_for(
    entity: "Entity",
    service: "UnifiedEntityService",
    parent=None,
) -> QFrame:
    """Return the most specific card widget for the given entity type."""
    cls = _TYPE_TO_CARD.get(entity.type, FallbackEntityCard)
    return cls(entity, service, parent)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _label(text: str, style: str) -> QLabel:
    lbl = QLabel(text)
    lbl.setStyleSheet(style)
    lbl.setWordWrap(True)
    return lbl
```

- [ ] **Step 2: Commit**

```bash
git add gui/components/entity_cards.py
git commit -m "feat: add specialized entity card widgets (Light/Switch/Sensor/Binary/Camera/MediaPlayer/Fallback)"
```

---

## Task 7: Home Automation tab refactor

**Files:**
- Modify: `gui/tabs/home_automation.py` — full rewrite

This task replaces the 4 sub-tab architecture with a 3-filter grid UI. The `HomeAutomationTab` class name and public interface are preserved so `gui/app.py` requires no changes.

- [ ] **Step 1: Rewrite `gui/tabs/home_automation.py`**

```python
"""
Environmental Control Dashboard — multi-provider, 3-filter grid.

Architecture:
  - _UnifiedFetchThread runs unified_entity_service.refresh_providers()
    in background and emits the entity list when done.
  - HomeAutomationTab shows 3 filter rows (Provider / Type / Zone).
  - Selecting any filter calls _rebuild_grid() which applies all 3 filters
    simultaneously and creates specialized entity cards.
  - Camera cards own their own auto-refresh timers; we track them for cleanup.
"""
from __future__ import annotations

from PySide6.QtCore import Qt, Signal, QThread
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QScrollArea, QGridLayout, QPushButton
)
from qfluentwidgets import TitleLabel, BodyLabel, FluentIcon as FIF, ToolButton

from core.settings_store import settings
from core.i18n import tr, i18n


# ---------------------------------------------------------------------------
# Constants / shared styles
# ---------------------------------------------------------------------------

_BTN_FILTER = """
    QPushButton {
        background-color: #1a2236; color: #6e7a8e;
        border-radius: 15px; padding: 6px 16px; border: none; font-weight: bold;
        font-size: 12px;
    }
    QPushButton:checked { background-color: #33b5e5; color: #0f1524; }
    QPushButton:hover   { background-color: #232d45; }
"""

_BADGE_BASE = """
    background-color: #0d121d;
    border: 1px solid #1a2236;
    border-radius: 16px;
    padding: 6px 16px;
    font-weight: bold;
    font-size: 12px;
"""

# Map ADA entity type → display label for the Type filter row
_TYPE_LABELS: dict[str, str] = {
    "light":         "Lights",
    "camera":        "Cameras",
    "media_player":  "Media Players",
    "sensor":        "Sensors",
    "binary_sensor": "Binary Sensors",
    "switch":        "Switches",
    "unknown":       "Other",
}

_FIXED_ZONES = ["All", "Bureau", "Chambre", "Cuisine", "Chillout", "Extérieur", "Couloir", "Other"]


# ---------------------------------------------------------------------------
# Background fetch thread
# ---------------------------------------------------------------------------

class _UnifiedFetchThread(QThread):
    """Runs refresh_providers() in background, emits list[Entity] when done."""
    done = Signal(list)

    def run(self):
        try:
            from core.unified_entities import unified_entity_service
            unified_entity_service.refresh_providers()
            self.done.emit(unified_entity_service.get_unified_entities())
        except Exception as e:
            print(f"[HomeAutomation] Fetch failed: {e}")
            self.done.emit([])


# ---------------------------------------------------------------------------
# Status badge thread (HA connectivity only)
# ---------------------------------------------------------------------------

class _HABadgeThread(QThread):
    result = Signal(bool, bool)   # (enabled, connected)

    def run(self):
        url = settings.get("home_assistant.url", "")
        enabled = settings.get("home_assistant.enabled", False)
        if not url or not enabled:
            self.result.emit(False, False)
            return
        try:
            from core.ha_control import ha_manager
            ha_manager.reload_config()
            connected = ha_manager.test_connection()
            self.result.emit(True, connected)
        except Exception:
            self.result.emit(True, False)


# ---------------------------------------------------------------------------
# Filter row helper
# ---------------------------------------------------------------------------

def _make_filter_row(labels: list[str]) -> tuple[QHBoxLayout, dict[str, QPushButton]]:
    """Build a horizontal row of checkable filter buttons. Returns layout + button dict."""
    layout = QHBoxLayout()
    layout.setSpacing(8)
    buttons: dict[str, QPushButton] = {}
    for i, label in enumerate(labels):
        btn = QPushButton(label)
        btn.setCheckable(True)
        btn.setChecked(i == 0)
        btn.setStyleSheet(_BTN_FILTER)
        buttons[label] = btn
        layout.addWidget(btn)
    layout.addStretch()
    return layout, buttons


# ---------------------------------------------------------------------------
# Main tab
# ---------------------------------------------------------------------------

class HomeAutomationTab(QWidget):
    """Environmental Control Dashboard — multi-provider, 3-filter grid."""

    navigate_to_settings = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("homeAutomationView")

        self._all_entities: list = []
        self._camera_cards: list = []
        self._fetch_thread: _UnifiedFetchThread | None = None
        self._destroyed = False

        self._filter_provider = "All"
        self._filter_type = "All"
        self._filter_zone = "All"

        # Provider name → id mapping (filled when entities arrive)
        self._provider_names: dict[str, str] = {}   # display name → provider id

        self._build_ui()
        self._start_badge_check()
        self._load_entities()

        from PySide6.QtWidgets import QApplication
        QApplication.instance().aboutToQuit.connect(self._cleanup)
        i18n.language_changed.connect(self._on_language_changed)

    # ------------------------------------------------------------------ #
    # Build UI                                                             #
    # ------------------------------------------------------------------ #

    def _build_ui(self):
        main = QVBoxLayout(self)
        main.setContentsMargins(40, 40, 40, 40)
        main.setSpacing(20)

        # Header
        self._build_header(main)

        # ── Provider filter row ──────────────────────────────────────────
        provider_header = QLabel("Providers")
        provider_header.setStyleSheet("color: #6e7a8e; font-size: 11px; font-weight: bold;")
        main.addWidget(provider_header)

        self._provider_row_layout = QHBoxLayout()
        self._provider_row_layout.setSpacing(8)
        self._provider_row_btns: dict[str, QPushButton] = {}
        self._provider_row_layout.addStretch()
        main.addLayout(self._provider_row_layout)

        # ── Type filter row ──────────────────────────────────────────────
        type_header = QLabel("Type")
        type_header.setStyleSheet("color: #6e7a8e; font-size: 11px; font-weight: bold;")
        main.addWidget(type_header)

        type_labels = ["All"] + list(_TYPE_LABELS.values())
        type_row, self._type_btns = _make_filter_row(type_labels)
        for label, btn in self._type_btns.items():
            btn.clicked.connect(lambda _, l=label: self._on_type_filter(l))
        main.addLayout(type_row)

        # ── Zone filter row ──────────────────────────────────────────────
        zone_header = QLabel("Zone")
        zone_header.setStyleSheet("color: #6e7a8e; font-size: 11px; font-weight: bold;")
        main.addWidget(zone_header)

        zone_row, self._zone_btns = _make_filter_row(_FIXED_ZONES)
        for label, btn in self._zone_btns.items():
            btn.clicked.connect(lambda _, l=label: self._on_zone_filter(l))
        main.addLayout(zone_row)

        # ── Scrollable entity grid ───────────────────────────────────────
        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setStyleSheet("background: transparent; border: none;")

        self._grid_widget = QWidget()
        self._grid_widget.setStyleSheet("background: transparent;")
        self._grid_layout = QGridLayout(self._grid_widget)
        self._grid_layout.setSpacing(20)
        self._grid_layout.setAlignment(Qt.AlignTop | Qt.AlignLeft)
        self._scroll.setWidget(self._grid_widget)
        main.addWidget(self._scroll)

        # Show "loading" initially
        self._show_grid_message("⏳ Loading devices…", "#6e7a8e")

    def _build_header(self, parent_layout: QVBoxLayout):
        header = QHBoxLayout()

        text = QVBoxLayout()
        title = TitleLabel("Environmental Control", self)
        title.setStyleSheet("font-size: 28px; font-weight: bold; color: white;")
        sub = BodyLabel("Unified device control across all providers.", self)
        sub.setStyleSheet("color: #6e7a8e; font-size: 14px;")
        text.addWidget(title)
        text.addWidget(sub)
        header.addLayout(text)
        header.addStretch()

        refresh_btn = ToolButton(FIF.SYNC, self)
        refresh_btn.setToolTip("Refresh all providers")
        refresh_btn.clicked.connect(self._on_refresh)
        header.addWidget(refresh_btn)
        header.addSpacing(10)

        self._ha_badge = QLabel("●  Home Assistant")
        self._ha_badge.setStyleSheet(_BADGE_BASE + "color: #6e7a8e;")
        header.addWidget(self._ha_badge)

        parent_layout.addLayout(header)

    # ------------------------------------------------------------------ #
    # Loading                                                              #
    # ------------------------------------------------------------------ #

    def _load_entities(self):
        try:
            if self._fetch_thread and self._fetch_thread.isRunning():
                return
        except RuntimeError:
            self._fetch_thread = None

        self._fetch_thread = _UnifiedFetchThread()
        self._fetch_thread.done.connect(self._on_entities_loaded)
        self._fetch_thread.finished.connect(self._fetch_thread.deleteLater)
        self._fetch_thread.start()

    def _on_entities_loaded(self, entities: list):
        if self._destroyed:
            return
        self._all_entities = entities

        # Build provider filter buttons from loaded providers
        self._rebuild_provider_row(entities)

        if not entities:
            self._show_grid_message("No devices found.", "#6e7a8e")
            return

        self._rebuild_grid()

    def _rebuild_provider_row(self, entities: list):
        """Repopulate provider filter buttons based on providers seen in entities."""
        # Clear existing buttons (except the stretch at the end)
        while self._provider_row_layout.count() > 1:
            item = self._provider_row_layout.takeAt(0)
            if item and item.widget():
                item.widget().deleteLater()
        self._provider_row_btns.clear()

        # Collect unique provider display names
        seen: dict[str, str] = {"All": "All"}  # display → provider_id
        try:
            from core.unified_entities import unified_entity_service
            for p in unified_entity_service.get_providers():
                if p.enabled:
                    seen[p.name] = p.id
        except Exception:
            pass
        # Fallback: derive names from entities
        for e in entities:
            pname = e.provider.replace("_", " ").title()
            if pname not in seen:
                seen[pname] = e.provider
        self._provider_names = seen

        for i, (display, _) in enumerate(seen.items()):
            btn = QPushButton(display)
            btn.setCheckable(True)
            btn.setChecked(display == self._filter_provider)
            btn.setStyleSheet(_BTN_FILTER)
            btn.clicked.connect(lambda _, d=display: self._on_provider_filter(d))
            self._provider_row_btns[display] = btn
            self._provider_row_layout.insertWidget(
                self._provider_row_layout.count() - 1, btn
            )

    # ------------------------------------------------------------------ #
    # Filters                                                              #
    # ------------------------------------------------------------------ #

    def _on_provider_filter(self, label: str):
        self._filter_provider = label
        for lbl, btn in self._provider_row_btns.items():
            btn.setChecked(lbl == label)
        self._rebuild_grid()

    def _on_type_filter(self, label: str):
        self._filter_type = label
        for lbl, btn in self._type_btns.items():
            btn.setChecked(lbl == label)
        self._rebuild_grid()

    def _on_zone_filter(self, label: str):
        self._filter_zone = label
        for lbl, btn in self._zone_btns.items():
            btn.setChecked(lbl == label)
        self._rebuild_grid()

    def _matches_filters(self, entity) -> bool:
        # Provider filter
        if self._filter_provider != "All":
            target_id = self._provider_names.get(self._filter_provider, "")
            if entity.provider != target_id:
                return False
        # Type filter
        if self._filter_type != "All":
            type_id = next(
                (k for k, v in _TYPE_LABELS.items() if v == self._filter_type),
                None
            )
            if type_id and entity.type != type_id:
                return False
        # Zone filter
        if self._filter_zone != "All":
            if entity.zone != self._filter_zone:
                return False
        return True

    # ------------------------------------------------------------------ #
    # Grid rebuild                                                         #
    # ------------------------------------------------------------------ #

    def _rebuild_grid(self):
        if self._destroyed:
            return
        self._clear_grid()

        from core.unified_entities import unified_entity_service
        from gui.components.entity_cards import entity_card_for

        filtered = [e for e in self._all_entities if self._matches_filters(e)]

        if not filtered:
            self._show_grid_message("No devices match the selected filters.", "#6e7a8e")
            return

        row = col = 0
        new_camera_cards = []
        for entity in filtered:
            if self._destroyed:
                return
            try:
                card = entity_card_for(entity, unified_entity_service, self._grid_widget)
                self._grid_layout.addWidget(card, row, col)
                if hasattr(card, "stop"):  # camera cards
                    new_camera_cards.append(card)
                col += 1
                if col >= 3:
                    col = 0
                    row += 1
            except Exception as ex:
                print(f"[HomeAutomation] Card creation failed for {entity.id}: {ex}")

        self._camera_cards = new_camera_cards

    def _clear_grid(self):
        """Stop camera timers and remove all widgets from the grid."""
        for card in self._camera_cards:
            try:
                card.stop()
            except Exception:
                pass
        self._camera_cards.clear()

        if not hasattr(self, "_grid_layout"):
            return
        try:
            while self._grid_layout.count():
                item = self._grid_layout.takeAt(0)
                if item is None:
                    break
                w = item.widget()
                if w is not None:
                    w.deleteLater()
        except RuntimeError:
            pass

    def _show_grid_message(self, text: str, color: str):
        self._clear_grid()
        lbl = QLabel(text)
        lbl.setAlignment(Qt.AlignCenter)
        lbl.setStyleSheet(f"color: {color}; font-size: 14px; font-weight: bold;")
        self._grid_layout.addWidget(lbl, 0, 0)

    # ------------------------------------------------------------------ #
    # HA badge                                                             #
    # ------------------------------------------------------------------ #

    def _start_badge_check(self):
        self._badge_thread = _HABadgeThread()
        self._badge_thread.result.connect(self._on_badge_result)
        self._badge_thread.finished.connect(self._badge_thread.deleteLater)
        self._badge_thread.start()

    def _on_badge_result(self, enabled: bool, connected: bool):
        if not enabled:
            self._ha_badge.setText("●  Home Assistant")
            self._ha_badge.setStyleSheet(_BADGE_BASE + "color: #6e7a8e;")
        elif connected:
            self._ha_badge.setText("●  Connected")
            self._ha_badge.setStyleSheet(_BADGE_BASE + "color: #4CAF50;")
        else:
            self._ha_badge.setText("●  Disconnected")
            self._ha_badge.setStyleSheet(_BADGE_BASE + "color: #f44336;")

    # ------------------------------------------------------------------ #
    # Refresh / cleanup                                                    #
    # ------------------------------------------------------------------ #

    def _on_refresh(self):
        self._show_grid_message("⏳ Refreshing…", "#6e7a8e")
        self._start_badge_check()
        self._load_entities()

    def _on_language_changed(self, _lang: str = ""):
        pass  # Filter labels are not i18n-translated (matched against ADA type constants)

    def _cleanup(self):
        self._destroyed = True
        self._clear_grid()

    def closeEvent(self, event):
        self._destroyed = True
        self._clear_grid()
        super().closeEvent(event)
```

- [ ] **Step 2: Run the app and verify**

```
python main.py
```

Open the **Home** tab. Verify:
- Header shows "Environmental Control" with a refresh button and HA badge
- 3 filter rows appear (Providers, Type, Zone)
- Entity grid loads in the background (spinner message first, then cards)
- Provider buttons are dynamically populated from loaded entities
- Selecting "Lights" in the Type row hides non-light entities
- Selecting "Bureau" in the Zone row shows only bureau entities
- Kasa bulbs show a brightness slider; color bulbs show a color picker
- HA sensors show READ ONLY badge with value and unit
- Camera cards show a snapshot image that auto-refreshes
- Clicking Refresh button reloads all providers

- [ ] **Step 3: Commit**

```bash
git add gui/tabs/home_automation.py
git commit -m "refactor: replace 4 sub-tabs with 3-filter multi-provider entity grid in Environmental Control"
```

---

## Task 8: Settings — Kasa provider section + i18n

**Files:**
- Modify: `gui/tabs/settings.py` — add Kasa provider group
- Modify: `locales/en.json` — new `settings.kasa*` keys
- Modify: `locales/fr.json` — French equivalents

- [ ] **Step 1: Add i18n keys to `locales/en.json`**

In `locales/en.json`, inside the `"settings"` object, add after `"ha_token_desc"`:

```json
    "kasa": "Kasa",
    "kasa_enabled": "Enable Kasa Discovery",
    "kasa_enabled_desc": "Discover and control TP-Link Kasa smart devices on the local network",
    "kasa_test": "Test Discovery",
    "kasa_test_desc": "Scan the local network for Kasa devices now",
    "kasa_test_btn": "Scan",
    "kasa_scanning": "Scanning…",
    "kasa_found": "Found {count} Kasa device(s)",
    "kasa_none": "No Kasa devices found on the network"
```

- [ ] **Step 2: Add i18n keys to `locales/fr.json`**

In `locales/fr.json`, inside the `"settings"` object, add after `"ha_token_desc"`:

```json
    "kasa": "Kasa",
    "kasa_enabled": "Activer la découverte Kasa",
    "kasa_enabled_desc": "Découvrir et contrôler les appareils TP-Link Kasa sur le réseau local",
    "kasa_test": "Tester la découverte",
    "kasa_test_desc": "Scanner le réseau local pour les appareils Kasa",
    "kasa_test_btn": "Scanner",
    "kasa_scanning": "Scan en cours…",
    "kasa_found": "{count} appareil(s) Kasa trouvé(s)",
    "kasa_none": "Aucun appareil Kasa trouvé sur le réseau"
```

- [ ] **Step 3: Add Kasa settings group to `gui/tabs/settings.py`**

In `gui/tabs/settings.py`, after the `_init_ui()` method's connection group and before the HA group, add a `kasa_group`. Find the section `# ── Home Assistant ───────────────────────────────────────────` (around line 429) and insert before it:

```python
        # ── Kasa ─────────────────────────────────────────────────────────
        self.kasa_group = SettingCardGroup(tr("settings.kasa"), self.scrollWidget)

        self.kasa_enabled_card = SwitchCard(
            FIF.WIFI,
            tr("settings.kasa_enabled"),
            tr("settings.kasa_enabled_desc"),
            "kasa.enabled",
            self.kasa_group
        )
        self.kasa_group.addSettingCard(self.kasa_enabled_card)

        self.kasa_test_card = PushSettingCard(
            tr("settings.kasa_test_btn"),
            FIF.SEARCH,
            tr("settings.kasa_test"),
            tr("settings.kasa_test_desc"),
            self.kasa_group
        )
        self.kasa_test_card.clicked.connect(self._on_kasa_scan)
        self.kasa_group.addSettingCard(self.kasa_test_card)
        self.expandLayout.addWidget(self.kasa_group)
```

- [ ] **Step 4: Add `_on_kasa_scan()` method to `SettingsTab`**

Add this method to `SettingsTab`, alongside the other `_on_*` callbacks:

```python
    def _on_kasa_scan(self):
        self.kasa_test_card.button.setEnabled(False)
        self.kasa_test_card.button.setText(tr("settings.kasa_scanning"))

        import threading

        def _run():
            from core.providers.kasa_provider import kasa_provider
            result = kasa_provider.fetch_entities()
            count = len(result)
            from PySide6.QtCore import QMetaObject, Qt
            QMetaObject.invokeMethod(
                self, "_on_kasa_scan_done",
                Qt.QueuedConnection,
                # Pass count as string via property trick
            )
            self._kasa_scan_count = count

        threading.Thread(target=_run, daemon=True).start()

    @Slot()
    def _on_kasa_scan_done(self):
        self.kasa_test_card.button.setEnabled(True)
        self.kasa_test_card.button.setText(tr("settings.kasa_test_btn"))
        count = getattr(self, "_kasa_scan_count", 0)
        if count > 0:
            InfoBar.success(
                title=tr("settings.kasa"),
                content=tr("settings.kasa_found", count=count),
                orient=Qt.Horizontal, isClosable=True,
                position=InfoBarPosition.TOP, duration=4000, parent=self.window()
            )
        else:
            InfoBar.warning(
                title=tr("settings.kasa"),
                content=tr("settings.kasa_none"),
                orient=Qt.Horizontal, isClosable=True,
                position=InfoBarPosition.TOP, duration=4000, parent=self.window()
            )
```

- [ ] **Step 5: Add kasa group to `retranslate_ui()`**

In `SettingsTab.retranslate_ui()`, before the HA lines, add:

```python
        self.kasa_group.titleLabel.setText(tr("settings.kasa"))
        self.kasa_enabled_card.titleLabel.setText(tr("settings.kasa_enabled"))
        self.kasa_enabled_card.contentLabel.setText(tr("settings.kasa_enabled_desc"))
        self.kasa_test_card.titleLabel.setText(tr("settings.kasa_test"))
        self.kasa_test_card.contentLabel.setText(tr("settings.kasa_test_desc"))
        self.kasa_test_card.button.setText(tr("settings.kasa_test_btn"))
```

- [ ] **Step 6: Run the app and verify**

```
python main.py
```

Open **Settings**. Verify:
- "Kasa" group appears between Connection and Home Assistant groups
- Toggle "Enable Kasa Discovery" saves `kasa.enabled` to settings
- "Scan" button triggers background discovery; shows InfoBar with device count
- Language switch to French shows "Activer la découverte Kasa" etc.

- [ ] **Step 7: Run full test suite**

```
python -m pytest tests/ -v --tb=short
```
Expected: all tests pass (no regressions).

- [ ] **Step 8: Commit**

```bash
git add gui/tabs/settings.py locales/en.json locales/fr.json
git commit -m "feat: add Kasa provider settings group with scan button + i18n keys"
```

---

## Self-Review

### 1. Spec coverage

| Spec requirement | Task |
|---|---|
| Provider model (id, name, enabled, type, baseUrl, token, priority, status, lastSync, capabilities) | Task 1 (`Provider` dataclass) |
| Entity model (id, provider, providerEntityId, name, type, zone, state, attributes, capabilities, readOnly, available, lastUpdated) | Task 1 (`Entity` dataclass) |
| Entity types: light, camera, speaker, sensor, binary_sensor, switch, media_player, printer, unknown | Task 1 (`ha_domain_to_entity_type`) |
| Capabilities: read, control, brightness, color, snapshot, motion, tts, volume, temperature, humidity, battery, energy | Task 1 (`infer_capabilities`) |
| Kasa as provider (enabled, priority) | Task 2 + Task 3 |
| HA as provider | Task 4 |
| `getUnifiedEntities()` | Task 5 |
| `refreshProviders()` | Task 5 |
| `testProviderConnection(providerId)` | Task 5 |
| `toggleEntity(entityId)` | Task 5 |
| `setEntityBrightness(entityId, value)` | Task 5 |
| `sendTtsToEntity(entityId, message)` | Task 5 |
| Light card (name, on/off, brightness, color, provider, zone) | Task 6 (`LightEntityCard`) |
| Camera card (snapshot, name, availability, provider, zone) | Task 6 (`CameraEntityCard`) |
| Speaker/media_player card (name, state, volume, TTS button, provider, zone) | Task 6 (`MediaPlayerEntityCard`) |
| Sensor card (name, value, unit, read-only, provider, zone, last updated) | Task 6 (`SensorEntityCard`) |
| Binary sensor card (name, ON/OFF or Open/Closed, read-only, provider, zone) | Task 6 (`BinarySensorEntityCard`) |
| Switch card (name, state, toggle, provider, zone) | Task 6 (`SwitchEntityCard`) |
| Fallback card | Task 6 (`FallbackEntityCard`) |
| Provider filter row | Task 7 |
| Type filter row | Task 7 |
| Zone filter row | Task 7 |
| Kasa settings section | Task 8 |
| HA settings preserved | HA group kept, unchanged |
| Provider isolation (HA down → Kasa continues) | Task 5 (`refresh_providers` per-provider try/except) |
| Cards support unavailable/null without crash | Task 6 (all cards guard state/attrs access) |
| No hardcoded Kasa exception in UI | Task 7 (provider filter is dynamic) |

### 2. Placeholder scan

No TBD, TODO, or placeholder text found. Every step contains actual implementation code.

### 3. Type consistency

- `Entity.id` format is `"{provider_id}.{provider_entity_id}"` — consistent across Task 1, Task 3, Task 4, Task 5, Task 6, Task 7
- `infer_capabilities(entity_type, attributes, read_only)` — signature identical across all callers in Tasks 3, 4
- `infer_zone(name)` — single function, called identically in Tasks 3, 4
- `entity_card_for(entity, service, parent)` — factory signature used identically in Task 7
- `unified_entity_service.toggle_entity(entity_id)` — called identically in Task 6 cards
- `BaseProvider.toggle(provider_entity_id, on)` — implemented identically in Tasks 3, 4; called identically in Task 5

---

Plan complete and saved to `docs/superpowers/plans/2026-05-15-environmental-control-providers.md`.

**Two execution options:**

**1. Subagent-Driven (recommended)** — I dispatch a fresh subagent per task with spec + quality review between each task. Fast iteration with checkpoints.

**2. Inline Execution** — Execute all 8 tasks in this session with progress tracking.

**Which approach?**

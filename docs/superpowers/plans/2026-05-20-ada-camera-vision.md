# ADA Camera Vision Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Integrate TP-Link Tapo C210 cameras exposed in Home Assistant as ADA vision endpoints — snapshot capture, area-based routing from voice/Telegram, and a Senses tab UI.

**Architecture:** `CameraManager` (new singleton) wraps HA camera entity discovery (with area resolution) and snapshot capture. `vision.describe_from_bytes()` extends the existing vision pipeline to accept pre-fetched JPEG bytes. Voice and Telegram handlers use `CameraManager` to pick the right camera from a room hint, falling back to local webcam if no HA cameras exist.

**Tech Stack:** PySide6/qfluentwidgets (UI), requests (HA REST API), existing Ollama vision pipeline (`llava-phi3`), `uv run pytest` for tests.

---

## File Map

| Action | File | Responsibility |
|--------|------|----------------|
| Modify | `core/ha_control.py` | Add `get_camera_endpoints()` joining entity+area registries |
| Create | `core/camera_manager.py` | Dataclasses + CameraManager singleton |
| Modify | `core/vision.py` | Add `describe_from_bytes(jpg_bytes, prompt)` |
| Modify | `core/voice_assistant.py` | Replace `_handle_vision()` with camera-aware version |
| Modify | `core/telegram_adapter.py` | Add `_handle_vision(text, chat_id)` for vision route |
| Modify | `gui/tabs/senses.py` | Add HA camera section with test snapshot button |
| Modify | `locales/fr.json` + `locales/en.json` | 8 new senses keys |
| Create | `tests/test_ha_camera_endpoints.py` | Unit tests for `get_camera_endpoints()` |
| Create | `tests/test_camera_manager.py` | Unit tests for CameraManager |

---

## Task 1: HA camera endpoint method

**Files:**
- Modify: `core/ha_control.py` (after `get_camera_entities()`, around line 143)
- Create: `tests/test_ha_camera_endpoints.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_ha_camera_endpoints.py
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


def test_get_camera_endpoints_ha_unreachable():
    mgr = _make_manager()
    with patch("core.ha_control.requests.get", side_effect=Exception("timeout")):
        result = mgr.get_camera_endpoints()
    assert result == []
```

- [ ] **Step 2: Run tests to verify they fail**

```
uv run pytest tests/test_ha_camera_endpoints.py -v
```
Expected: FAIL — `AttributeError: 'HAManager' object has no attribute 'get_camera_endpoints'`

- [ ] **Step 3: Implement `get_camera_endpoints()` in `core/ha_control.py`**

Add after `get_camera_entities()` (around line 149):

```python
def get_camera_endpoints(self) -> list[dict]:
    """
    Returns camera.* entities with resolved area_name.
    Joins HA entity registry + area registry + /api/states.
    Returns [] if HA is unreachable or not configured.
    """
    if not self._url or not self._token:
        return []
    try:
        # 1. Entity registry: entity_id → area_id (camera.* only)
        er_resp = requests.get(
            f"{self._url}/api/config/entity_registry/list",
            headers=self._headers(),
            timeout=5,
        )
        er_map: dict[str, str] = {}
        if er_resp.status_code == 200:
            for item in er_resp.json():
                eid = item.get("entity_id", "")
                if eid.startswith("camera."):
                    er_map[eid] = item.get("area_id") or ""

        # 2. Area registry: area_id → name
        ar_resp = requests.get(
            f"{self._url}/api/config/area_registry/list",
            headers=self._headers(),
            timeout=5,
        )
        area_names: dict[str, str] = {}
        if ar_resp.status_code == 200:
            for item in ar_resp.json():
                area_names[item["area_id"]] = item["name"]

        # 3. States: friendly_name + state
        states = self._fetch_all_states()

        result = []
        for eid, area_id in er_map.items():
            info = states.get(eid, {})
            friendly = info.get("attributes", {}).get("friendly_name", eid)
            state = info.get("state", "unknown")
            result.append({
                "entity_id": eid,
                "friendly_name": friendly,
                "area_id": area_id,
                "area_name": area_names.get(area_id, ""),
                "state": state,
            })
        return result
    except Exception as e:
        print(f"[HAManager] get_camera_endpoints failed: {e}")
        return []
```

- [ ] **Step 4: Run tests to verify they pass**

```
uv run pytest tests/test_ha_camera_endpoints.py -v
```
Expected: 3 PASSED

- [ ] **Step 5: Commit**

```
git add core/ha_control.py tests/test_ha_camera_endpoints.py
git commit -m "feat: add get_camera_endpoints() to HAManager with area resolution"
```

---

## Task 2: CameraManager module

**Files:**
- Create: `core/camera_manager.py`
- Create: `tests/test_camera_manager.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_camera_manager.py
import os
from unittest.mock import patch, MagicMock
from core.camera_manager import (
    CameraManager, CameraEndpoint, CameraCapabilities, SnapshotResult
)


def _make_manager():
    return CameraManager()


def _raw_endpoints():
    return [
        {
            "entity_id": "camera.bureau",
            "friendly_name": "camera bureau",
            "area_id": "cafe_jeff",
            "area_name": "Café Jeff",
            "state": "idle",
        },
        {
            "entity_id": "camera.entree",
            "friendly_name": "camera entree",
            "area_id": "",
            "area_name": "",
            "state": "idle",
        },
    ]


def test_refresh_populates_endpoints():
    mgr = _make_manager()
    with patch("core.camera_manager.ha_manager") as mock_ha:
        mock_ha.get_camera_endpoints.return_value = _raw_endpoints()
        mgr.refresh()
    eps = mgr.list_endpoints()
    assert len(eps) == 2
    assert eps[0].entity_id == "camera.bureau"
    assert eps[0].area_name == "Café Jeff"
    assert eps[0].capabilities.snapshot is True
    assert eps[0].capabilities.audio_input is False


def test_find_by_area_exact():
    mgr = _make_manager()
    with patch("core.camera_manager.ha_manager") as mock_ha:
        mock_ha.get_camera_endpoints.return_value = _raw_endpoints()
        mgr.refresh()
    result = mgr.find_by_area("café")
    assert result is not None
    assert result.entity_id == "camera.bureau"


def test_find_by_area_partial():
    mgr = _make_manager()
    with patch("core.camera_manager.ha_manager") as mock_ha:
        mock_ha.get_camera_endpoints.return_value = _raw_endpoints()
        mgr.refresh()
    result = mgr.find_by_area("cafe")   # no accent
    assert result is not None
    assert result.entity_id == "camera.bureau"


def test_find_by_area_no_match():
    mgr = _make_manager()
    with patch("core.camera_manager.ha_manager") as mock_ha:
        mock_ha.get_camera_endpoints.return_value = _raw_endpoints()
        mgr.refresh()
    result = mgr.find_by_area("chambre")
    assert result is None


def test_find_by_area_empty_hint():
    mgr = _make_manager()
    with patch("core.camera_manager.ha_manager") as mock_ha:
        mock_ha.get_camera_endpoints.return_value = _raw_endpoints()
        mgr.refresh()
    result = mgr.find_by_area("")
    assert result is None


def test_capture_snapshot_success(tmp_path):
    mgr = _make_manager()
    jpg = b"\xff\xd8\xff" + b"\x00" * 100   # fake JPEG bytes

    with patch("core.camera_manager.ha_manager") as mock_ha:
        mock_ha.get_camera_snapshot.return_value = jpg
        with patch("core.camera_manager._CACHE_DIR", str(tmp_path)):
            result = mgr.capture_snapshot("camera.bureau")

    assert result.success is True
    assert result.entity_id == "camera.bureau"
    assert os.path.exists(result.path)
    with open(result.path, "rb") as f:
        assert f.read() == jpg


def test_capture_snapshot_failure():
    mgr = _make_manager()
    with patch("core.camera_manager.ha_manager") as mock_ha:
        mock_ha.get_camera_snapshot.return_value = None
        result = mgr.capture_snapshot("camera.bureau")
    assert result.success is False
    assert result.error != ""
```

- [ ] **Step 2: Run tests to verify they fail**

```
uv run pytest tests/test_camera_manager.py -v
```
Expected: FAIL — `ModuleNotFoundError: No module named 'core.camera_manager'`

- [ ] **Step 3: Implement `core/camera_manager.py`**

```python
"""
CameraManager — discovers HA camera endpoints and captures snapshots.

Provides:
  CameraCapabilities  — phase 1: snapshot only; audio/speaker stubbed
  CameraEndpoint      — entity_id, friendly_name, area_id, area_name, capabilities
  SnapshotResult      — success, entity_id, path, mime_type, error
  CameraManager       — refresh(), list_endpoints(), find_by_area(), capture_snapshot()
  camera_manager      — module-level singleton
"""
from __future__ import annotations

import os
import time
import unicodedata
from dataclasses import dataclass, field
from typing import Optional

from core.ha_control import ha_manager

_CACHE_DIR = os.path.join("data", "cache", "snapshots")


def _normalize(text: str) -> str:
    """Lowercase + strip accents for fuzzy matching."""
    return "".join(
        c for c in unicodedata.normalize("NFD", text.lower())
        if unicodedata.category(c) != "Mn"
    )


@dataclass
class CameraCapabilities:
    snapshot: bool = True
    motion: bool = False       # future: HA event subscription
    audio_input: bool = False  # future: inbound audio stream
    speaker: bool = False      # future: TTS to camera speaker


@dataclass
class CameraEndpoint:
    entity_id: str
    friendly_name: str
    area_id: str
    area_name: str
    state: str = "unknown"
    capabilities: CameraCapabilities = field(default_factory=CameraCapabilities)


@dataclass
class SnapshotResult:
    success: bool
    entity_id: str
    path: str
    mime_type: str = "image/jpeg"
    error: str = ""


class CameraManager:
    def __init__(self) -> None:
        self._endpoints: list[CameraEndpoint] = []

    def refresh(self) -> None:
        """Load camera.* entities from HA and resolve area names."""
        raw = ha_manager.get_camera_endpoints()
        self._endpoints = [
            CameraEndpoint(
                entity_id=r["entity_id"],
                friendly_name=r["friendly_name"],
                area_id=r["area_id"],
                area_name=r["area_name"],
                state=r["state"],
            )
            for r in raw
        ]
        print(f"[CameraManager] {len(self._endpoints)} camera(s) loaded")

    def list_endpoints(self) -> list[CameraEndpoint]:
        return list(self._endpoints)

    def find_by_area(self, hint: str) -> Optional[CameraEndpoint]:
        """
        Fuzzy-match hint against area_name and friendly_name (accent-insensitive).
        Returns the first match or None.
        """
        if not hint:
            return None
        h = _normalize(hint)
        for ep in self._endpoints:
            area = _normalize(ep.area_name)
            name = _normalize(ep.friendly_name)
            if h in area or area in h or h in name or name in h:
                return ep
        return None

    def capture_snapshot(self, entity_id: str) -> SnapshotResult:
        """
        Fetch JPEG snapshot from HA and save to data/cache/snapshots/.
        Returns SnapshotResult with success=False on any failure.
        """
        os.makedirs(_CACHE_DIR, exist_ok=True)
        jpg = ha_manager.get_camera_snapshot(entity_id)
        if jpg is None:
            return SnapshotResult(
                success=False, entity_id=entity_id, path="",
                error="Snapshot unavailable"
            )
        safe = entity_id.replace(".", "_").replace("/", "_")
        filename = f"{safe}_{int(time.time())}.jpg"
        path = os.path.join(_CACHE_DIR, filename)
        with open(path, "wb") as f:
            f.write(jpg)
        return SnapshotResult(success=True, entity_id=entity_id, path=path)


camera_manager = CameraManager()
```

- [ ] **Step 4: Run tests to verify they pass**

```
uv run pytest tests/test_camera_manager.py -v
```
Expected: 7 PASSED

- [ ] **Step 5: Commit**

```
git add core/camera_manager.py tests/test_camera_manager.py
git commit -m "feat: add CameraManager with area-based endpoint discovery and snapshot capture"
```

---

## Task 3: `vision.describe_from_bytes()`

**Files:**
- Modify: `core/vision.py`

- [ ] **Step 1: Add `describe_from_bytes()` to `core/vision.py`**

Add after the existing `describe()` function (end of file):

```python
def describe_from_bytes(
    jpg_bytes: bytes,
    prompt: str = _DEFAULT_PROMPT,
    model: Optional[str] = None,
) -> dict:
    """
    Describe an image from raw JPEG bytes (e.g. from HA camera snapshot).
    Same return structure as describe(): {success, description, image_b64}.
    """
    img_b64 = base64.b64encode(jpg_bytes).decode("utf-8")
    base = OLLAMA_URL.rstrip("/")
    configured = model or _vision_model()
    models_to_try = [configured] + [m for m in _VISION_MODEL_CASCADE if m != configured]
    for m in models_to_try:
        print(f"[Vision] Trying model: {m}")
        text = _try_model(base, m, prompt, img_b64)
        if text:
            return {"success": True, "description": text, "image_b64": img_b64}
    return {
        "success": False,
        "description": "Erreur : aucun modèle vision n'a pu répondre.",
        "image_b64": img_b64,
    }
```

- [ ] **Step 2: Verify the function is importable**

```
uv run python -c "from core.vision import describe_from_bytes; print('OK')"
```
Expected: `OK`

- [ ] **Step 3: Commit**

```
git add core/vision.py
git commit -m "feat: add vision.describe_from_bytes() for pre-fetched JPEG input"
```

---

## Task 4: Camera-aware vision routing (voice + Telegram)

**Files:**
- Modify: `core/voice_assistant.py`
- Modify: `core/telegram_adapter.py`

### 4a — voice_assistant

- [ ] **Step 1: Add `_extract_area_hint()` module-level function in `core/voice_assistant.py`**

Add after the imports, before the class definition:

```python
import re as _re

_AREA_HINT_RE = _re.compile(
    r"\b(?:au|dans\s+le|dans\s+la|dans\s+l[''']?|le|la|du|de\s+la|caméra)\s+(\w+(?:\s+\w+)?)",
    _re.IGNORECASE,
)

def _extract_area_hint(text: str) -> str:
    """Extract room/area hint from a vision query. Returns '' if none found."""
    m = _AREA_HINT_RE.search(text)
    return m.group(1).strip() if m else ""
```

- [ ] **Step 2: Replace `_handle_vision()` in `VoiceAssistant` class**

Replace the existing `_handle_vision()` method (around line 258):

```python
def _handle_vision(self, user_text: str):
    """Capture from best HA camera (or local webcam) and describe in French."""
    try:
        from core.camera_manager import camera_manager
        from core.vision import describe, describe_from_bytes
        from core.tts import tts, SentenceBuffer

        # Lazy-load cameras on first vision call
        if not camera_manager.list_endpoints():
            camera_manager.refresh()

        endpoints = camera_manager.list_endpoints()
        # Filter out offline cameras
        live = [ep for ep in endpoints if ep.state != "unavailable"]

        prompt = user_text or "Décris ce que tu vois en détail en français."
        hint = _extract_area_hint(user_text)

        if not live:
            # No HA cameras — fallback to local webcam
            result = describe(prompt=prompt)
        else:
            match = camera_manager.find_by_area(hint) if hint else None

            if match is None and len(live) == 1:
                match = live[0]

            if match is None and len(live) > 1:
                names = ", ".join(ep.area_name or ep.friendly_name for ep in live)
                description = (
                    f"J'ai {len(live)} caméras disponibles : {names}. "
                    "Laquelle souhaitez-vous utiliser ?"
                )
                buf = SentenceBuffer()
                for s in buf.add(description) + [buf.flush()]:
                    if s:
                        tts.queue_sentence(s)
                return

            if match is None:
                result = describe(prompt=prompt)
            else:
                print(f"{GRAY}[VoiceAssistant] Vision → {match.entity_id} ({match.area_name}){RESET}")
                snap = camera_manager.capture_snapshot(match.entity_id)
                if not snap.success:
                    result = {
                        "success": False,
                        "description": f"Je ne peux pas accéder à la caméra {match.area_name or match.friendly_name}.",
                    }
                else:
                    with open(snap.path, "rb") as f:
                        jpg = f.read()
                    result = describe_from_bytes(jpg, prompt=prompt)

        description = result.get("description") or "Je ne peux pas accéder à la caméra."
        buf = SentenceBuffer()
        for s in buf.add(description) + [buf.flush()]:
            if s:
                tts.queue_sentence(s)

    except Exception as e:
        print(f"{GRAY}[VoiceAssistant] Vision error: {e}{RESET}")
    finally:
        self.processing_finished.emit()
```

### 4b — telegram_adapter

- [ ] **Step 3: Add `_handle_vision()` to `TelegramAdapter` in `core/telegram_adapter.py`**

Add before `_call_with_tools()`:

```python
def _handle_vision(self, text: str, chat_id: int) -> str:
    """Camera-aware vision handler for Telegram. Returns French description."""
    try:
        from core.camera_manager import camera_manager
        from core.vision import describe, describe_from_bytes

        if not camera_manager.list_endpoints():
            camera_manager.refresh()

        endpoints = camera_manager.list_endpoints()
        live = [ep for ep in endpoints if ep.state != "unavailable"]

        prompt = text or "Décris ce que tu vois en détail en français."

        # Extract area hint: "regarde le café" → "café"
        import re as _re
        _hint_re = _re.compile(
            r"\b(?:au|dans\s+le|dans\s+la|dans\s+l[''']?|le|la|du|caméra)\s+(\w+(?:\s+\w+)?)",
            _re.IGNORECASE,
        )
        m = _hint_re.search(text)
        hint = m.group(1).strip() if m else ""

        if not live:
            result = describe(prompt=prompt)
        else:
            match = camera_manager.find_by_area(hint) if hint else None
            if match is None and len(live) == 1:
                match = live[0]
            if match is None and len(live) > 1:
                names = ", ".join(ep.area_name or ep.friendly_name for ep in live)
                return f"J'ai {len(live)} caméras disponibles : {names}. Laquelle souhaitez-vous ?"
            if match is None:
                result = describe(prompt=prompt)
            else:
                print(f"[Telegram] Vision → {match.entity_id} ({match.area_name})")
                snap = camera_manager.capture_snapshot(match.entity_id)
                if not snap.success:
                    return f"Je ne peux pas accéder à la caméra {match.area_name or match.friendly_name}."
                with open(snap.path, "rb") as f:
                    jpg = f.read()
                result = describe_from_bytes(jpg, prompt=prompt)

        return result.get("description") or "Je ne peux pas accéder à la caméra."

    except Exception as e:
        print(f"[Telegram] Vision error: {e}")
        return "Erreur lors de l'accès à la caméra."
```

- [ ] **Step 4: Wire the vision route in `_handle_text()` in `core/telegram_adapter.py`**

In `_handle_text()`, add `elif route == "vision":` before the `else` branch:

```python
        route = semantic_route(text)
        print(f"[Telegram] Route: {route}")

        if route == "function_gemma":
            response = self._call_with_tools(text, messages)
        elif route == "vision":
            response = self._handle_vision(text, chat_id)
        else:
            response = self._call_llm(messages)
```

- [ ] **Step 5: Run a quick smoke test**

```
uv run python -c "
from core.camera_manager import camera_manager
from core.voice_assistant import _extract_area_hint
print(_extract_area_hint('que vois-tu dans le café'))
print(_extract_area_hint('regarde le bureau'))
print(_extract_area_hint('regarde'))
"
```
Expected:
```
café
bureau

```

- [ ] **Step 6: Commit**

```
git add core/voice_assistant.py core/telegram_adapter.py
git commit -m "feat: camera-aware vision routing in voice and Telegram handlers"
```

---

## Task 5: Senses tab — HA camera section + i18n

**Files:**
- Modify: `locales/fr.json`
- Modify: `locales/en.json`
- Modify: `gui/tabs/senses.py`

### 5a — i18n keys

- [ ] **Step 1: Add 8 keys to `locales/fr.json`**

In the `"senses"` object, after `"vision_test_btn": "Tester",` add:

```json
"ha_cameras": "Caméras connectées",
"ha_cameras_desc": "Caméras Home Assistant disponibles comme points de vision",
"ha_camera_area": "Zone",
"ha_camera_snapshot": "Snapshot",
"ha_camera_audio": "Audio",
"ha_camera_speaker": "Haut-parleur",
"ha_camera_test": "Tester snapshot",
"ha_camera_offline": "Hors ligne",
"ha_camera_refresh": "Rafraîchir",
```

- [ ] **Step 2: Add same 9 keys to `locales/en.json`**

In the `"senses"` object, after `"vision_test_btn": "Test",` add:

```json
"ha_cameras": "Connected Cameras",
"ha_cameras_desc": "Home Assistant cameras available as vision endpoints",
"ha_camera_area": "Zone",
"ha_camera_snapshot": "Snapshot",
"ha_camera_audio": "Audio",
"ha_camera_speaker": "Speaker",
"ha_camera_test": "Test snapshot",
"ha_camera_offline": "Offline",
"ha_camera_refresh": "Refresh",
```

### 5b — Senses tab

- [ ] **Step 3: Add `_HACameraProbeThread` class in `gui/tabs/senses.py`**

Add after `_HAProbeThread` class (around line 74), before the custom card subclasses:

```python
class _HACameraProbeThread(QThread):
    """Fetch HA camera endpoints in background."""
    done = Signal(list)   # list of dicts from camera_manager.list_endpoints()

    def run(self) -> None:
        try:
            from core.camera_manager import camera_manager
            camera_manager.refresh()
            self.done.emit(camera_manager.list_endpoints())
        except Exception as e:
            print(f"[_HACameraProbeThread] {e}")
            self.done.emit([])
```

- [ ] **Step 4: Add `_HACameraCard` class in `gui/tabs/senses.py`**

Add before `class SensesTab`:

```python
class _HACameraCard(SettingCard):
    """One card per HA camera: name, area badge, capability chips, test button."""

    snapshot_requested = Signal(str)   # emits entity_id

    def __init__(self, endpoint, parent=None):
        from qfluentwidgets import PushButton, isDarkTheme
        from PySide6.QtWidgets import QHBoxLayout
        super().__init__(FIF.CAMERA, endpoint.friendly_name, endpoint.area_name or "—", parent)
        self._entity_id = endpoint.entity_id
        self._offline = endpoint.state == "unavailable"

        # Capability chips (read-only labels)
        chip_row = QWidget(self)
        chip_layout = QHBoxLayout(chip_row)
        chip_layout.setContentsMargins(0, 0, 0, 0)
        chip_layout.setSpacing(6)

        def chip(label: str, active: bool) -> QLabel:
            lbl = QLabel(label)
            color = "#00b4d8" if active else "#666"
            lbl.setStyleSheet(f"color: {color}; font-size: 11px;")
            return lbl

        chip_layout.addWidget(chip(f"📸 {tr('senses.ha_camera_snapshot')}", True))
        chip_layout.addWidget(chip(f"🎤 {tr('senses.ha_camera_audio')}", False))
        chip_layout.addWidget(chip(f"🔊 {tr('senses.ha_camera_speaker')}", False))
        chip_layout.addStretch()
        self.hBoxLayout.addWidget(chip_row)

        # Offline badge
        if self._offline:
            badge = QLabel(tr("senses.ha_camera_offline"))
            badge.setStyleSheet("color: #ff6b6b; font-size: 11px; font-weight: bold;")
            self.hBoxLayout.addWidget(badge)

        # Test button
        self._btn = PushButton(tr("senses.ha_camera_test"))
        self._btn.setEnabled(not self._offline)
        self._btn.clicked.connect(lambda: self.snapshot_requested.emit(self._entity_id))
        self.hBoxLayout.addWidget(self._btn)
        self.hBoxLayout.addSpacing(16)
```

- [ ] **Step 5: Add HA camera section to `_build_ui()` in `SensesTab`**

Add after `self._layout.addWidget(self.vision_group)` (around line 430):

```python
        # ── 1b. HA Cameras ─────────────────────────────────────────────────
        self.ha_camera_group = SettingCardGroup(tr("senses.ha_cameras"), self._content)
        self._layout.addWidget(self.ha_camera_group)
```

- [ ] **Step 6: Add camera probe init and slot to `SensesTab`**

In `__init__`, after `self._probe_ha_devices()`, add:

```python
        self._ha_camera_thread: _HACameraProbeThread | None = None
        self._probe_ha_cameras()
```

Add new methods to `SensesTab`:

```python
    def _probe_ha_cameras(self) -> None:
        if not settings.get("home_assistant.enabled", False):
            return
        self._ha_camera_thread = _HACameraProbeThread(self)
        self._ha_camera_thread.done.connect(self._on_ha_cameras_ready)
        self._ha_camera_thread.finished.connect(self._ha_camera_thread.deleteLater)
        self._ha_camera_thread.start()

    def _on_ha_cameras_ready(self, endpoints: list) -> None:
        for ep in endpoints:
            card = _HACameraCard(ep, self.ha_camera_group)
            card.snapshot_requested.connect(self._on_test_ha_snapshot)
            self.ha_camera_group.addSettingCard(card)

    def _on_test_ha_snapshot(self, entity_id: str) -> None:
        from qfluentwidgets import InfoBar, InfoBarPosition
        from core.camera_manager import camera_manager
        snap = camera_manager.capture_snapshot(entity_id)
        if not snap.success:
            InfoBar.warning(
                title="Snapshot échoué",
                content=snap.error,
                orient=Qt.Horizontal, isClosable=True,
                position=InfoBarPosition.TOP, duration=3000, parent=self.window()
            )
            return
        # Show snapshot in a dialog
        import base64
        dialog = QDialog(self)
        dialog.setWindowTitle(f"Snapshot — {entity_id}")
        dialog.setMinimumSize(560, 420)
        layout = QVBoxLayout(dialog)
        img_label = QLabel()
        from PySide6.QtGui import QPixmap
        pixmap = QPixmap(snap.path)
        img_label.setPixmap(pixmap.scaledToWidth(540, Qt.SmoothTransformation))
        layout.addWidget(img_label)
        dialog.exec()
```

- [ ] **Step 7: Run smoke test (import check)**

```
uv run python -c "from gui.tabs.senses import SensesTab; print('OK')"
```
Expected: `OK`

- [ ] **Step 8: Commit**

```
git add gui/tabs/senses.py locales/fr.json locales/en.json
git commit -m "feat: add HA camera section to Senses tab with snapshot test button"
```

---

## Self-Review

**Spec coverage:**
- ✅ Section 1 (data model) — Task 2
- ✅ Section 2 (HA integration) — Task 1
- ✅ Section 3 (chat routing voice) — Task 4a
- ✅ Section 3 (chat routing Telegram) — Task 4b
- ✅ Section 4 (Senses tab UI) — Task 5
- ✅ Section 5 (snapshot cache) — `_CACHE_DIR` + `os.makedirs` in Task 2
- ✅ Section 6 (error handling) — offline badge, snap failure, HA unreachable returns []
- ✅ Section 7 (tests) — Tasks 1 and 2

**Placeholder scan:** No TBD, no "handle edge cases", all code blocks complete.

**Type consistency:** `CameraEndpoint`, `SnapshotResult`, `CameraCapabilities` defined in Task 2 and referenced identically in Tasks 4 and 5. `describe_from_bytes()` defined in Task 3 and called in Tasks 4a and 4b.

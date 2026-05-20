# ADA Camera Vision — Design Spec

**Date:** 2026-05-20
**Branch:** `integration-n8n`
**Status:** Approved

---

## Goal

Integrate TP-Link Tapo C210 cameras exposed in Home Assistant as ADA vision endpoints — the "eyes, ears and mouth" of ADA. Phase 1 implements snapshot vision. Audio input and speaker output are stubbed as future capabilities.

---

## Section 1 — Data Model (`core/camera_manager.py`)

New singleton module centralising all camera logic.

### Dataclasses

```python
@dataclass
class CameraCapabilities:
    snapshot: bool = True
    motion: bool = False        # future — HA event subscription
    audio_input: bool = False   # future — inbound audio stream
    speaker: bool = False       # future — TTS to camera speaker

@dataclass
class CameraEndpoint:
    entity_id: str              # "camera.bureau"
    friendly_name: str          # "camera bureau"
    area_id: str                # "cafe_jeff"
    area_name: str              # "Café Jeff"
    capabilities: CameraCapabilities

@dataclass
class SnapshotResult:
    success: bool
    entity_id: str
    path: str                   # data/cache/snapshots/{entity_id}_{ts}.jpg
    mime_type: str = "image/jpeg"
    error: str = ""
```

### CameraManager API

```python
class CameraManager:
    def refresh(self) -> None
        # Loads camera.* entities from HA, resolves area names, populates self._endpoints

    def list_endpoints(self) -> list[CameraEndpoint]

    def find_by_area(self, hint: str) -> CameraEndpoint | None
        # Fuzzy match hint against area_name and friendly_name (case-insensitive, partial)

    def capture_snapshot(self, entity_id: str) -> SnapshotResult
        # Calls ha_manager.get_camera_snapshot(), saves to data/cache/snapshots/
        # Creates cache dir if missing

camera_manager = CameraManager()   # module-level singleton
```

Cameras with no HA area (`area_name = ""`) are included in `list_endpoints()` and appear in ADA UI — they just cannot be matched by area hint.

---

## Section 2 — HA Integration (`core/ha_control.py`)

HA exposes area data via the config registries, not `/api/states`.

New method:

```python
def get_camera_endpoints(self) -> list[dict]:
    """
    Returns camera.* entities with resolved area_name.
    [{entity_id, friendly_name, area_id, area_name, state}, ...]
    """
    # 1. GET /api/config/entity_registry/list  → {entity_id: area_id}
    # 2. GET /api/config/area_registry/list    → {area_id: area_name}
    # 3. GET /api/states                       → friendly_name, state
    # 4. Filter domain == "camera", join area names
```

Existing `get_camera_snapshot(entity_id)` is already implemented and returns raw JPEG bytes or `None`.

---

## Section 3 — Chat Routing (vision pipeline)

### Trigger utterances (already in semantic router "vision" route)

```
"regarde", "que vois-tu", "analyse la caméra", "regarde le café",
"que vois-tu dans le bureau", "montre-moi", "prends une photo"
```

### Handler logic (`_handle_vision(user_text)`)

```
extract_area_hint(text)
  ↓
camera_manager.find_by_area(hint)
  ├── match found      → capture_snapshot() → LLM vision → French response
  ├── no match, 1 cam → use only available camera
  ├── no match, N cam → "J'ai N caméras : café, entrée... laquelle ?"
  └── 0 HA cameras    → fallback to local webcam (existing vision.describe())
```

### Area hint extraction

Simple regex on prepositions + nouns:
```
"regarde le café"          → hint = "café"
"que vois-tu dans le bureau" → hint = "bureau"
"analyse la caméra entrée"  → hint = "entrée"
"regarde"                  → hint = ""  (triggers clarification)
```

### LLM vision call

Reuses existing `vision.describe()` pipeline — pass JPEG bytes as `image_b64` instead of capturing from webcam. Default prompt: `"Décris ce que tu vois en détail en français. Sois concis et précis."`.

### Applies to both channels

- **Voice** (`voice_assistant._handle_vision`) — updated to use `camera_manager`
- **Telegram** (`telegram_adapter`) — "vision" route currently falls through to `_call_llm`; add `_handle_vision(text, chat_id)` method that sends text response (no TTS)

---

## Section 4 — Senses Tab UI (`gui/tabs/senses.py`)

New collapsible section **"Caméras connectées"** below existing Vision section.

### Per-camera card

```
┌─────────────────────────────────────┐
│ 📷 camera bureau          Café Jeff │
│ [📸 Snapshot] [🎤 Audio·] [🔊 ·]   │
│              [Tester snapshot]       │
└─────────────────────────────────────┘
```

- **Capability chips:** `📸 Snapshot` (active cyan), `🎤 Audio` (greyed), `🔊 Haut-parleur` (greyed)
- **"Tester snapshot"** button → captures snapshot → shows JPEG in a dialog (reuse pattern from existing `CameraLiveWidget`)
- Cameras with `state = "unavailable"` show a "Hors ligne" badge and disabled button
- Section header has a **Rafraîchir** button that calls `camera_manager.refresh()`

### i18n keys (fr.json / en.json)

```
senses_ha_cameras, senses_ha_cameras_desc,
senses_camera_snapshot, senses_camera_audio,
senses_camera_speaker, senses_camera_test,
senses_camera_offline, senses_camera_refresh
```

---

## Section 5 — Snapshot Cache

- Directory: `data/cache/snapshots/` (created on first use)
- Filename: `{entity_id_safe}_{unix_ts}.jpg` (e.g. `camera_bureau_1716220800.jpg`)
- No automatic cleanup in phase 1 (out of scope)

---

## Section 6 — Error Handling

| Case | Behaviour |
|---|---|
| HA unreachable at refresh | Empty endpoint list, logged at WARNING |
| Camera state = unavailable | Excluded from routing, shown with "Hors ligne" badge in UI |
| `get_camera_snapshot()` returns None | `SnapshotResult(success=False, error="Snapshot unavailable")` |
| Snapshot timeout | Same as above |
| No camera matches area hint | Clarification question (N > 1) or webcam fallback (N = 0) |
| Cache dir missing | Created automatically by `capture_snapshot()` |

---

## Section 7 — Tests

- `tests/test_camera_manager.py`
  - `test_refresh_populates_endpoints` — mock `get_camera_endpoints`, verify list
  - `test_find_by_area_match` — "café" matches "Café Jeff"
  - `test_find_by_area_partial` — "bur" matches "Bureau Jeff"
  - `test_find_by_area_no_match` — unknown hint returns None
  - `test_capture_snapshot_success` — mock `get_camera_snapshot` returning bytes, verify file written and SnapshotResult
  - `test_capture_snapshot_failure` — mock returns None, verify success=False

- `tests/test_ha_camera_endpoints.py`
  - `test_get_camera_endpoints_joins_areas` — mock entity + area registry, verify join
  - `test_get_camera_endpoints_no_area` — entity without area_id → area_name = ""

---

## Out of Scope (Phase 1)

- Audio input / microphone stream from camera
- Speaker / TTS output to camera
- Motion event subscriptions (separate from ha_state_watcher)
- Snapshot history / cache cleanup
- Multiple simultaneous snapshots
- Camera settings UI (area override)

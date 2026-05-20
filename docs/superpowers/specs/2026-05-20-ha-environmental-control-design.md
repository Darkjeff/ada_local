# HA Environmental Control — Design Spec

**Date:** 2026-05-20  
**Branch:** `integration-n8n`  
**Status:** Approved

---

## Goal

Improve the Environmental Control page (Home Automation tab) with three targeted enhancements: a tighter filter layout, per-entity visibility control, and a generic HA state watcher that sends a Telegram notification when the front door opens.

---

## Section 1 — Filter Layout

**Current:** Three dropdowns stacked vertically (Provider, Type, Zone).

**New layout:** Two rows.
- Row 1: `Provider` dropdown + visual separator + `Type` dropdown (both full-width on their half)
- Row 2: `Zone` dropdown (full width)

**Implementation:** `gui/tabs/home_automation.py`

- Replace the current `QVBoxLayout` filter stack with a `QGridLayout` (2 columns row 0, 1 column row 1).
- Add a `QFrame` with `Shape.VLine` between Provider and Type for the visual separator.
- No change to filter logic (`_matches_filters()`); only layout changes.

---

## Section 2 — Entity Visibility

**Goal:** Let the user hide noisy or irrelevant entity cards without deleting them from HA. Hidden state persists across restarts.

### Eye toggle per card

- Each entity card gets an eye icon button in its top-right corner.
- Clicking it hides the card immediately and saves the entity_id to `settings.json` under `home_assistant.hidden_entities: []`.
- Hidden entities are excluded when rebuilding the grid.

### Edit mode

- A button in the page header ("Edit mode" / "Terminé") toggles edit mode on/off.
- In edit mode: hidden entity cards reappear with a semi-transparent overlay and a "Restore" button.
- Clicking "Restore" removes the entity_id from `hidden_entities` and the card returns to normal.
- Exiting edit mode hides the restored view and rebuilds the grid.

### Storage

```json
// settings.json excerpt
"home_assistant": {
  "hidden_entities": ["sensor.temperature_bureau", "switch.prise_inutile"]
}
```

`settings.get("home_assistant.hidden_entities", [])` — read on each grid rebuild.  
`settings.set("home_assistant.hidden_entities", updated_list)` — written on toggle.

### Files touched

- `gui/tabs/home_automation.py` — filter/rebuild logic, edit mode button, hidden entity exclusion
- `gui/components/entity_cards.py` — eye icon overlay, restore overlay
- `core/settings_store.py` — `DEFAULT_SETTINGS["home_assistant"]["hidden_entities"] = []`

---

## Section 3 — HA State Watcher

### Overview

A generic background daemon (`core/ha_state_watcher.py`) polls HA entity states every 5 seconds and fires callbacks on state changes. The first subscription will be the front door (T110 contact sensor) → "🚪 Ciel un client !" via Telegram.

### Architecture

```
HAStateWatcher (daemon thread)
  ├── subscriptions: list[Subscription(entity_id, trigger_states, callback)]
  ├── _last_states: dict[entity_id, str]
  └── loop: every 5s → GET /api/states/{entity_id} → compare → fire callback
```

**`ha_state_watcher.py` API:**

```python
class HAStateWatcher:
    def subscribe(self, entity_id: str, trigger_states: list[str], callback: Callable) -> None
    def start(self) -> None   # daemon thread
    def stop(self) -> None

ha_state_watcher = HAStateWatcher()  # singleton
```

**Callback signature:** `callback(entity_id: str, new_state: str) -> None`

### Door notification

Subscription wired in `main.py` after `ha_state_watcher.start()`:

```python
def _on_door_open(entity_id, state):
    telegram_adapter.send_message("🚪 Ciel un client !")

ha_state_watcher.subscribe(
    entity_id=settings.get("home_assistant.door_entity", ""),
    trigger_states=["on"],
    callback=_on_door_open,
)
```

- Only fires on state **entering** `"on"` (open), not on close.
- If `door_entity` is empty string, subscription is skipped silently.
- Uses `ha_manager.get_state(entity_id)` from `core/ha_control.py` for the HTTP call.

### Settings UI

New card in the Settings page → Home Assistant section:

| Label | Key | Widget |
|---|---|---|
| Door entity ID | `home_assistant.door_entity` | `LineEditCard` (placeholder: `binary_sensor.t110_contact`) |
| Door alert message | `home_assistant.door_message` | `LineEditCard` (default: `🚪 Ciel un client !`) |
| Enable door alert | `home_assistant.door_alert_enabled` | `SwitchCard` |

### Files touched

- `core/ha_state_watcher.py` — new file
- `main.py` — `ha_state_watcher.start()` + subscription wiring
- `gui/tabs/settings.py` — 3 new cards in HA section
- `core/settings_store.py` — add `door_entity`, `door_message`, `door_alert_enabled` to defaults
- `locales/en.json` + `locales/fr.json` — new i18n keys

---

## Error Handling

- **HA unreachable:** watcher logs a warning and retries next cycle (no crash, no retry storm).
- **Entity not found (404):** skipped silently, logged at DEBUG level.
- **Callback raises:** caught and logged, watcher continues.
- **Telegram unavailable:** `telegram_adapter.send_message` already handles this gracefully.

---

## Testing

- `tests/test_ha_state_watcher.py`: mock `ha_manager.get_state`, verify callback fires on trigger state, does not fire on non-trigger state, does not fire twice on same state.
- `tests/test_home_automation_visibility.py`: mock settings, verify hidden entity excluded from grid build, verify edit mode restores it.
- Manual: add a test entity subscription, simulate state change via HA dev tools, confirm Telegram message arrives.

---

## Out of Scope

- HA webhook/push (polling only for now)
- Multiple door sensors (one entity ID in Settings)
- Watcher UI in the Environmental Control tab (Settings-only config)
- Rate-limiting Telegram messages (not needed for a single door sensor)

# HA Environmental Control Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add filter layout refactor, per-entity visibility (eye toggle + edit mode), and an HA State Watcher that sends "🚪 Ciel un client !" via Telegram when the front door opens.

**Architecture:** Three independent layers: (1) settings defaults for new keys, (2) UI changes to `home_automation.py` and `entity_cards.py`, (3) a new daemon `ha_state_watcher.py` wired at startup. Each task is self-contained and safe to commit independently.

**Tech Stack:** PySide6, qfluentwidgets, threading, requests, pytest

---

## File Map

| File | Action | Responsibility |
|------|--------|----------------|
| `core/settings_store.py` | Modify | Add 4 new defaults under `home_assistant` |
| `core/ha_state_watcher.py` | Create | Polling daemon + subscription API |
| `gui/tabs/home_automation.py` | Modify | Filter layout + entity visibility UI |
| `gui/tabs/settings.py` | Modify | 3 new HA cards (door entity/message/alert) |
| `locales/en.json` | Modify | 6 new i18n keys |
| `locales/fr.json` | Modify | 6 new i18n keys (French) |
| `main.py` | Modify | Start watcher + wire door subscription |
| `tests/test_settings_defaults.py` | Create | Verify new default keys |
| `tests/test_ha_state_watcher.py` | Create | Watcher callback logic (offline-safe) |

---

## Task 1: Settings Defaults

**Files:**
- Modify: `core/settings_store.py` (the `home_assistant` dict in `DEFAULT_SETTINGS`, around line 39)
- Create: `tests/test_settings_defaults.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_settings_defaults.py
from core.settings_store import DEFAULT_SETTINGS


def test_hidden_entities_default_is_empty_list():
    ha = DEFAULT_SETTINGS["home_assistant"]
    assert ha["hidden_entities"] == []


def test_door_watcher_defaults():
    ha = DEFAULT_SETTINGS["home_assistant"]
    assert ha["door_entity"] == ""
    assert ha["door_message"] == "🚪 Ciel un client !"
    assert ha["door_alert_enabled"] is False
```

- [ ] **Step 2: Run test to verify it fails**

```
uv run python -m pytest tests/test_settings_defaults.py -v
```

Expected: FAIL with `KeyError: 'hidden_entities'`

- [ ] **Step 3: Add the 4 new keys to DEFAULT_SETTINGS**

In `core/settings_store.py`, locate the `home_assistant` dict (currently ends at `"tts_target_entity": ""`). Add the 4 new keys so the block looks like:

```python
"home_assistant": {
    "url": "",
    "token": "",
    "enabled": False,
    "tts_service": "tts.piper",
    "tts_target_entity": "",
    "hidden_entities": [],
    "door_entity": "",
    "door_message": "🚪 Ciel un client !",
    "door_alert_enabled": False,
},
```

- [ ] **Step 4: Run tests to verify they pass**

```
uv run python -m pytest tests/test_settings_defaults.py -v
```

Expected: PASS (2 tests)

- [ ] **Step 5: Commit**

```
git add core/settings_store.py tests/test_settings_defaults.py
git commit -m "feat: add hidden_entities and door watcher defaults to settings"
```

---

## Task 2: Filter Layout Refactor

**Files:**
- Modify: `gui/tabs/home_automation.py`

The current `_build_ui` adds Provider header + row, then Type header + row, then Zone header + row — all as separate vertical items. Replace with a two-row layout: Provider+Type side-by-side (row 1), Zone full-width (row 2).

- [ ] **Step 1: Add QFrame to imports**

In `home_automation.py`, change the `QWidget` import line from:

```python
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QScrollArea, QGridLayout, QPushButton
)
```

to:

```python
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QScrollArea, QGridLayout, QPushButton, QFrame
)
```

- [ ] **Step 2: Replace the filter section in `_build_ui`**

In `_build_ui`, locate this block (lines ~167–197) and **replace it entirely**:

```python
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
```

Replace with:

```python
        # ── Row 1: Provider (left) + separator + Type (right) ───────────
        filter_row1 = QHBoxLayout()
        filter_row1.setSpacing(16)

        prov_col = QVBoxLayout()
        prov_col.setSpacing(4)
        prov_header = QLabel("Providers")
        prov_header.setStyleSheet("color: #6e7a8e; font-size: 11px; font-weight: bold;")
        prov_col.addWidget(prov_header)
        self._provider_row_layout = QHBoxLayout()
        self._provider_row_layout.setSpacing(8)
        self._provider_row_btns: dict[str, QPushButton] = {}
        self._provider_row_layout.addStretch()
        prov_col.addLayout(self._provider_row_layout)
        filter_row1.addLayout(prov_col, 1)

        _sep = QFrame()
        _sep.setFrameShape(QFrame.Shape.VLine)
        _sep.setStyleSheet("background-color: #2a3556;")
        _sep.setFixedWidth(1)
        filter_row1.addWidget(_sep)

        type_col = QVBoxLayout()
        type_col.setSpacing(4)
        type_header = QLabel("Type")
        type_header.setStyleSheet("color: #6e7a8e; font-size: 11px; font-weight: bold;")
        type_col.addWidget(type_header)
        type_labels = ["All"] + list(_TYPE_LABELS.values())
        type_row, self._type_btns = _make_filter_row(type_labels)
        for label, btn in self._type_btns.items():
            btn.clicked.connect(lambda _, l=label: self._on_type_filter(l))
        type_col.addLayout(type_row)
        filter_row1.addLayout(type_col, 1)

        main.addLayout(filter_row1)

        # ── Row 2: Zone (full width) ─────────────────────────────────────
        zone_header = QLabel("Zone")
        zone_header.setStyleSheet("color: #6e7a8e; font-size: 11px; font-weight: bold;")
        main.addWidget(zone_header)
        zone_row, self._zone_btns = _make_filter_row(_FIXED_ZONES)
        for label, btn in self._zone_btns.items():
            btn.clicked.connect(lambda _, l=label: self._on_zone_filter(l))
        main.addLayout(zone_row)
```

- [ ] **Step 3: Verify the app starts without error**

```
uv run python main.py
```

Navigate to the Environmental Control tab. Verify:
- Provider and Type filter buttons appear on the same line, separated by a thin vertical line
- Zone buttons appear on the row below
- All filter buttons still work (click each one and verify the grid updates)

- [ ] **Step 4: Commit**

```
git add gui/tabs/home_automation.py
git commit -m "feat: refactor filter layout — Provider+Type same row, Zone below"
```

---

## Task 3: Entity Visibility (Eye Toggle + Edit Mode)

**Files:**
- Modify: `gui/tabs/home_automation.py`

This task adds two inner classes (`_EntityCardWrapper`, `_HiddenCardRestore`) and modifies `_build_header`, `__init__`, and `_rebuild_grid`.

- [ ] **Step 1: Add `_edit_mode` to `__init__`**

In `HomeAutomationTab.__init__`, after the line `self._destroyed = False`, add:

```python
        self._edit_mode = False
```

- [ ] **Step 2: Add `_EntityCardWrapper` class**

Add this class just above `class HomeAutomationTab` (before line `class HomeAutomationTab(QWidget):`):

```python
class _EntityCardWrapper(QWidget):
    """Wraps an entity card with a hide button overlaid in the top-right corner."""

    def __init__(self, entity_id: str, card: QFrame, parent=None):
        super().__init__(parent)
        self.entity_id = entity_id
        self._card = card
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(card)
        self.setFixedSize(card.width(), card.height())

        self._eye_btn = ToolButton(FIF.VIEW, self)
        self._eye_btn.setFixedSize(24, 24)
        self._eye_btn.setToolTip("Hide this entity")
        self._eye_btn.clicked.connect(self._on_hide)
        self._eye_btn.raise_()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._eye_btn.move(self.width() - 28, 6)

    def _on_hide(self):
        hidden = list(settings.get("home_assistant.hidden_entities", []))
        if self.entity_id not in hidden:
            hidden.append(self.entity_id)
            settings.set("home_assistant.hidden_entities", hidden)
        self.hide()
```

- [ ] **Step 3: Add `_HiddenCardRestore` class**

Add this class right after `_EntityCardWrapper`:

```python
class _HiddenCardRestore(QFrame):
    """Shown in edit mode for a hidden entity — lets user restore it."""

    def __init__(self, entity_id: str, entity_name: str, tab: "HomeAutomationTab", parent=None):
        super().__init__(parent)
        self._entity_id = entity_id
        self._tab = tab
        self.setFixedSize(300, 160)
        self.setStyleSheet("""
            _HiddenCardRestore {
                background-color: #0d121d;
                border: 1px dashed #2a3556;
                border-radius: 20px;
            }
        """)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setAlignment(Qt.AlignCenter)

        icon_lbl = QLabel("👁")
        icon_lbl.setStyleSheet("font-size: 24px; background: transparent;")
        icon_lbl.setAlignment(Qt.AlignCenter)
        layout.addWidget(icon_lbl)

        name_lbl = QLabel(entity_name)
        name_lbl.setStyleSheet(
            "color: #6e7a8e; font-size: 12px; background: transparent;"
        )
        name_lbl.setAlignment(Qt.AlignCenter)
        name_lbl.setWordWrap(True)
        layout.addWidget(name_lbl)

        restore_btn = QPushButton("Restore")
        restore_btn.setStyleSheet("""
            QPushButton {
                background-color: #33b5e5; color: #0f1524;
                border-radius: 8px; padding: 4px 12px;
                font-weight: bold; border: none;
            }
            QPushButton:hover { background-color: #55caff; }
        """)
        restore_btn.clicked.connect(self._on_restore)
        layout.addWidget(restore_btn, 0, Qt.AlignCenter)

    def _on_restore(self):
        hidden = list(settings.get("home_assistant.hidden_entities", []))
        if self._entity_id in hidden:
            hidden.remove(self._entity_id)
            settings.set("home_assistant.hidden_entities", hidden)
        self._tab._rebuild_grid()
```

- [ ] **Step 4: Add the Edit button to the header**

In `_build_header`, after the `refresh_btn` block and before the HA badge, insert:

```python
        self._edit_btn = ToolButton(FIF.EDIT, self)
        self._edit_btn.setToolTip("Toggle entity visibility editing")
        self._edit_btn.clicked.connect(self._toggle_edit_mode)
        header.addWidget(self._edit_btn)
        header.addSpacing(10)
```

The final header should read (in order): `text` layout → stretch → `refresh_btn` → spacing → `_edit_btn` → spacing → `_ha_badge`.

- [ ] **Step 5: Add `_toggle_edit_mode` method**

Add this method to `HomeAutomationTab`, after `_on_refresh`:

```python
    def _toggle_edit_mode(self):
        self._edit_mode = not self._edit_mode
        self._edit_btn.setIcon(FIF.CLOSE if self._edit_mode else FIF.EDIT)
        self._rebuild_grid()
```

- [ ] **Step 6: Modify `_rebuild_grid` to respect hidden entities and edit mode**

Replace the entire `_rebuild_grid` method with:

```python
    def _rebuild_grid(self):
        if self._destroyed:
            return
        self._clear_grid()

        from core.unified_entities import unified_entity_service
        from gui.components.entity_cards import entity_card_for

        hidden_ids = set(settings.get("home_assistant.hidden_entities", []))
        filtered = [e for e in self._all_entities if self._matches_filters(e)]

        if self._edit_mode:
            # Show ALL entities so user can restore hidden ones
            entities_to_show = self._all_entities
        else:
            entities_to_show = [e for e in filtered if e.id not in hidden_ids]

        if not entities_to_show:
            self._show_grid_message("No devices match the selected filters.", "#6e7a8e")
            return

        row = col = 0
        new_camera_cards = []
        for entity in entities_to_show:
            if self._destroyed:
                return
            try:
                if entity.id in hidden_ids:
                    widget = _HiddenCardRestore(
                        entity.id, entity.name, self, self._grid_widget
                    )
                elif self._edit_mode:
                    widget = entity_card_for(entity, unified_entity_service, self._grid_widget)
                    if hasattr(widget, "stop"):
                        new_camera_cards.append(widget)
                else:
                    raw_card = entity_card_for(entity, unified_entity_service, self._grid_widget)
                    widget = _EntityCardWrapper(entity.id, raw_card, self._grid_widget)
                    if hasattr(raw_card, "stop"):
                        new_camera_cards.append(raw_card)

                self._grid_layout.addWidget(widget, row, col)
            except Exception as ex:
                print(f"[HomeAutomation] Card creation failed for {entity.id}: {ex}")

            col += 1
            if col >= 3:
                col = 0
                row += 1

        self._camera_cards = new_camera_cards
```

- [ ] **Step 7: Verify in the running app**

```
uv run python main.py
```

Test sequence:
1. Navigate to Environmental Control tab — all entity cards show with an eye icon button in the top-right corner.
2. Click the eye icon on any card — card disappears immediately.
3. Click the Edit button (pencil icon) in the header — it turns into an X icon, hidden entities appear as dashed grey "Restore" cards.
4. Click "Restore" on a hidden card — card is restored to the grid, shown normally.
5. Click the X button (edit mode off) — returns to normal view without the restored card's Restore button.
6. Restart the app — previously hidden entities remain hidden (persisted in settings.json).

- [ ] **Step 8: Commit**

```
git add gui/tabs/home_automation.py
git commit -m "feat: add entity visibility eye toggle and edit mode to Environmental Control"
```

---

## Task 4: HA State Watcher

**Files:**
- Create: `core/ha_state_watcher.py`
- Create: `tests/test_ha_state_watcher.py`
- Modify: `main.py`
- Modify: `gui/tabs/settings.py`
- Modify: `locales/en.json`
- Modify: `locales/fr.json`

### Part A: Core watcher + tests

- [ ] **Step 1: Write failing tests**

```python
# tests/test_ha_state_watcher.py
from unittest.mock import patch, MagicMock
from core.ha_state_watcher import HAStateWatcher


def _make_watcher():
    return HAStateWatcher(poll_interval=999)  # won't loop in tests


def test_callback_fires_on_trigger_state():
    watcher = _make_watcher()
    fired = []

    def cb(entity_id, state):
        fired.append((entity_id, state))

    watcher.subscribe("binary_sensor.door", ["on"], cb)

    with patch("core.ha_state_watcher.ha_manager") as mock_ha:
        mock_ha.get_state.return_value = {"state": "on"}
        watcher._check(watcher._subscriptions[0])

    assert fired == [("binary_sensor.door", "on")]


def test_callback_does_not_fire_on_non_trigger_state():
    watcher = _make_watcher()
    fired = []
    watcher.subscribe("binary_sensor.door", ["on"], lambda eid, s: fired.append(s))

    with patch("core.ha_state_watcher.ha_manager") as mock_ha:
        mock_ha.get_state.return_value = {"state": "off"}
        watcher._check(watcher._subscriptions[0])

    assert fired == []


def test_callback_does_not_fire_twice_for_same_state():
    watcher = _make_watcher()
    fired = []
    watcher.subscribe("binary_sensor.door", ["on"], lambda eid, s: fired.append(s))
    sub = watcher._subscriptions[0]

    with patch("core.ha_state_watcher.ha_manager") as mock_ha:
        mock_ha.get_state.return_value = {"state": "on"}
        watcher._check(sub)
        watcher._check(sub)  # second call, same state

    assert len(fired) == 1


def test_empty_entity_id_is_skipped():
    watcher = _make_watcher()
    watcher.subscribe("", ["on"], lambda eid, s: None)
    assert len(watcher._subscriptions) == 0


def test_ha_unreachable_does_not_raise():
    watcher = _make_watcher()
    watcher.subscribe("binary_sensor.door", ["on"], lambda eid, s: None)

    with patch("core.ha_state_watcher.ha_manager") as mock_ha:
        mock_ha.get_state.return_value = {}
        watcher._check(watcher._subscriptions[0])  # must not raise


def test_callback_exception_does_not_crash_watcher():
    watcher = _make_watcher()

    def bad_cb(eid, s):
        raise RuntimeError("callback error")

    watcher.subscribe("binary_sensor.door", ["on"], bad_cb)
    sub = watcher._subscriptions[0]

    with patch("core.ha_state_watcher.ha_manager") as mock_ha:
        mock_ha.get_state.return_value = {"state": "on"}
        watcher._check(sub)  # must not raise despite bad_cb
```

- [ ] **Step 2: Run tests to verify they fail**

```
uv run python -m pytest tests/test_ha_state_watcher.py -v
```

Expected: FAIL with `ModuleNotFoundError: No module named 'core.ha_state_watcher'`

- [ ] **Step 3: Create `core/ha_state_watcher.py`**

```python
"""
Generic HA entity state watcher — polls subscribed entities every N seconds
and fires callbacks when a target state is entered.
"""
from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from typing import Callable

from core.ha_control import ha_manager


@dataclass
class _Subscription:
    entity_id: str
    trigger_states: list[str]
    callback: Callable


class HAStateWatcher:
    """
    Daemon thread that polls HA entity states at a fixed interval.
    Fires callback(entity_id, new_state) when a subscribed entity
    enters one of its trigger_states.
    """

    def __init__(self, poll_interval: float = 5.0):
        self._poll_interval = poll_interval
        self._subscriptions: list[_Subscription] = []
        self._last_states: dict[str, str] = {}
        self._running = False
        self._thread: threading.Thread | None = None

    def subscribe(self, entity_id: str, trigger_states: list[str], callback: Callable) -> None:
        if not entity_id:
            return
        self._subscriptions.append(_Subscription(entity_id, trigger_states, callback))

    def start(self) -> None:
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(
            target=self._loop, daemon=True, name="HAStateWatcher"
        )
        self._thread.start()

    def stop(self) -> None:
        self._running = False

    def _loop(self) -> None:
        while self._running:
            for sub in list(self._subscriptions):
                try:
                    self._check(sub)
                except Exception as e:
                    print(f"[HAStateWatcher] Error checking {sub.entity_id}: {e}")
            time.sleep(self._poll_interval)

    def _check(self, sub: _Subscription) -> None:
        state_dict = ha_manager.get_state(sub.entity_id)
        if not state_dict:
            return
        new_state = state_dict.get("state")
        if new_state is None:
            return
        prev = self._last_states.get(sub.entity_id)
        self._last_states[sub.entity_id] = new_state
        if prev == new_state:
            return
        if new_state in sub.trigger_states:
            try:
                sub.callback(sub.entity_id, new_state)
            except Exception as e:
                print(f"[HAStateWatcher] Callback error for {sub.entity_id}: {e}")


# Singleton
ha_state_watcher = HAStateWatcher()
```

- [ ] **Step 4: Run tests to verify they pass**

```
uv run python -m pytest tests/test_ha_state_watcher.py -v
```

Expected: PASS (6 tests)

- [ ] **Step 5: Commit watcher + tests**

```
git add core/ha_state_watcher.py tests/test_ha_state_watcher.py
git commit -m "feat: add HAStateWatcher polling daemon with subscription API"
```

### Part B: i18n keys

- [ ] **Step 6: Add keys to `locales/en.json`**

In the `"settings"` object of `locales/en.json`, add after the `"ha_token_desc"` entry:

```json
    "ha_door_entity": "Door Entity ID",
    "ha_door_entity_desc": "HA entity_id of the door contact sensor",
    "ha_door_message": "Door Alert Message",
    "ha_door_message_desc": "Telegram message sent when the door opens",
    "ha_door_alert": "Enable Door Alert",
    "ha_door_alert_desc": "Send a Telegram message when the door sensor opens",
```

- [ ] **Step 7: Add keys to `locales/fr.json`**

In the `"settings"` object of `locales/fr.json`, add after `"ha_token_desc"`:

```json
    "ha_door_entity": "Entity ID de la porte",
    "ha_door_entity_desc": "Entité HA du capteur de contact de porte",
    "ha_door_message": "Message d'alerte porte",
    "ha_door_message_desc": "Message Telegram envoyé quand la porte s'ouvre",
    "ha_door_alert": "Activer l'alerte porte",
    "ha_door_alert_desc": "Envoyer un message Telegram quand le capteur de porte s'ouvre",
```

- [ ] **Step 8: Commit locales**

```
git add locales/en.json locales/fr.json
git commit -m "feat: add door watcher i18n keys (en + fr)"
```

### Part C: Settings UI

- [ ] **Step 9: Add 3 new cards to the HA section in `gui/tabs/settings.py`**

In `_init_ha_section` (or wherever `self.ha_group` is populated), after the line `self.ha_group.addSettingCard(self.ha_token_card)` (line ~561) and **before** `self.expandLayout.addWidget(self.ha_group)`, insert:

```python
        self.ha_door_entity_card = TextInputCard(
            FIF.SEARCH,
            tr("settings.ha_door_entity"),
            tr("settings.ha_door_entity_desc"),
            "home_assistant.door_entity",
            "binary_sensor.t110_contact",
            self.ha_group
        )
        self.ha_group.addSettingCard(self.ha_door_entity_card)

        self.ha_door_message_card = TextInputCard(
            FIF.CHAT,
            tr("settings.ha_door_message"),
            tr("settings.ha_door_message_desc"),
            "home_assistant.door_message",
            "🚪 Ciel un client !",
            self.ha_group
        )
        self.ha_group.addSettingCard(self.ha_door_message_card)

        self.ha_door_alert_card = SwitchCard(
            FIF.SEND,
            tr("settings.ha_door_alert"),
            tr("settings.ha_door_alert_desc"),
            "home_assistant.door_alert_enabled",
            self.ha_group
        )
        self.ha_group.addSettingCard(self.ha_door_alert_card)
```

- [ ] **Step 10: Add retranslate entries**

In `retranslate_ui`, after the block that sets `self.ha_token_card` labels (line ~784), add:

```python
        self.ha_door_entity_card.titleLabel.setText(tr("settings.ha_door_entity"))
        self.ha_door_entity_card.contentLabel.setText(tr("settings.ha_door_entity_desc"))
        self.ha_door_message_card.titleLabel.setText(tr("settings.ha_door_message"))
        self.ha_door_message_card.contentLabel.setText(tr("settings.ha_door_message_desc"))
        self.ha_door_alert_card.titleLabel.setText(tr("settings.ha_door_alert"))
        self.ha_door_alert_card.contentLabel.setText(tr("settings.ha_door_alert_desc"))
```

- [ ] **Step 11: Verify Settings tab**

```
uv run python main.py
```

Open Settings → Home Assistant section. Verify three new cards appear:
- "Door Entity ID" with a text input
- "Door Alert Message" with a text input (default: `🚪 Ciel un client !`)
- "Enable Door Alert" with a toggle switch

- [ ] **Step 12: Commit settings UI**

```
git add gui/tabs/settings.py
git commit -m "feat: add door watcher config cards to Settings HA section"
```

### Part D: Wire into main.py

- [ ] **Step 13: Start watcher and subscribe in `main.py`**

In `main.py`, after the `telegram_adapter.start()` line (line ~54), add:

```python
    # Start HA state watcher — fires callbacks on entity state changes
    from core.ha_state_watcher import ha_state_watcher
    ha_state_watcher.start()

    # Door alert: send Telegram message when door sensor opens
    def _on_door_open(entity_id: str, state: str) -> None:
        if not _settings.get("home_assistant.door_alert_enabled", False):
            return
        msg = _settings.get("home_assistant.door_message", "🚪 Ciel un client !")
        try:
            telegram_adapter.send_message(msg)
        except Exception as e:
            print(f"[DoorAlert] Telegram send failed: {e}")

    _door_entity = _settings.get("home_assistant.door_entity", "")
    if _door_entity:
        ha_state_watcher.subscribe(_door_entity, ["on"], _on_door_open)
```

Note: `_settings` is already assigned earlier in `main.py` as `from core.settings_store import settings as _settings`.

- [ ] **Step 14: Verify watcher starts without error**

```
uv run python main.py
```

Check console output: no crash, no error about `ha_state_watcher`. If `door_alert_enabled` is False, no subscription fires even if the door sensor state changes.

To test the subscription: in Home Assistant Developer Tools → States, set your door entity to `on`. Within 5 seconds a Telegram message should arrive (if `door_alert_enabled` is True and a valid bot token is configured).

- [ ] **Step 15: Commit main.py wiring**

```
git add main.py
git commit -m "feat: wire HAStateWatcher startup and door open Telegram alert in main"
```

---

## Full Test Run

- [ ] **Step 16: Run all tests**

```
uv run python -m pytest tests/ -v
```

Expected: all tests pass including `test_settings_defaults.py` and `test_ha_state_watcher.py`.

- [ ] **Step 17: Final commit if needed**

If any cleanup was done after the test run:

```
git add -p
git commit -m "chore: cleanup after HA environmental control implementation"
```

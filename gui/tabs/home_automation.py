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
    QScrollArea, QGridLayout, QPushButton, QFrame
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
        # Clear existing buttons (keep the stretch at the end)
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

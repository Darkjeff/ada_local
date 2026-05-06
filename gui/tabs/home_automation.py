import asyncio
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QFrame,
    QScrollArea, QGridLayout, QPushButton, QTabWidget
)
from PySide6.QtCore import Qt, Signal, QThread
from PySide6.QtGui import QColor
from qfluentwidgets import (
    TitleLabel, BodyLabel,
    FluentIcon as FIF, IconWidget, SwitchButton, Slider,
    ColorPickerButton, ToolButton
)

from core.kasa_control import kasa_manager
from core.ha_control import ha_manager
from core.settings_store import settings


# ══════════════════════════════════════════════════════════════════════
# Kasa threads & cards (unchanged from original)
# ══════════════════════════════════════════════════════════════════════

class DataFetchThread(QThread):
    devices_found = Signal(list)

    def run(self):
        try:
            print("[HomeAutomation] Starting Kasa device discovery...")
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            devices_dict = loop.run_until_complete(kasa_manager.discover_devices())
            loop.close()
            devices = list(devices_dict.values()) if isinstance(devices_dict, dict) else devices_dict
            print(f"[HomeAutomation] Found {len(devices)} devices")
            self.devices_found.emit(devices)
        except Exception as e:
            print(f"[HomeAutomation] Discovery error: {e}")
            self.devices_found.emit([])


class ActionThread(QThread):
    finished = Signal(bool)

    def __init__(self, action, ip, *args):
        super().__init__()
        self.action = action
        self.ip = ip
        self.args = tuple(arg for arg in args if not hasattr(arg, 'turn_on'))

    def run(self):
        try:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            success = False
            if self.action == "on":
                success = loop.run_until_complete(kasa_manager.turn_on(self.ip, dev=None))
            elif self.action == "off":
                success = loop.run_until_complete(kasa_manager.turn_off(self.ip, dev=None))
            elif self.action == "brightness":
                level = self.args[0] if self.args else 100
                success = loop.run_until_complete(kasa_manager.set_brightness(self.ip, level, dev=None))
            elif self.action == "color":
                h, s, v = self.args[0], self.args[1], self.args[2]
                success = loop.run_until_complete(kasa_manager.set_hsv(self.ip, h, s, v, dev=None))
            loop.close()
            self.finished.emit(success)
        except Exception as e:
            print(f"[HomeAutomation] Action '{self.action}' error: {e}")
            self.finished.emit(False)


class DeviceCard(QFrame):
    """Card representing a single Kasa smart device."""

    def __init__(self, device_info, parent=None):
        super().__init__(parent)
        self.device_info = device_info
        self.dev_obj = device_info.get('obj')
        self.ip = device_info['ip']
        self.is_bulb = "Bulb" in device_info.get("type", "") or device_info.get("brightness") is not None

        self.setFixedSize(300, 160)
        self.setStyleSheet("""
            DeviceCard {
                background-color: #1a2236;
                border: 1px solid #2a3556;
                border-radius: 20px;
            }
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)

        header = QHBoxLayout()
        icon_box = QFrame()
        icon_box.setFixedSize(40, 40)
        icon_box.setStyleSheet("background-color: #232d45; border-radius: 12px;")
        ib_layout = QVBoxLayout(icon_box)
        ib_layout.setAlignment(Qt.AlignCenter)
        ib_layout.setContentsMargins(0, 0, 0, 0)
        icon = FIF.BRIGHTNESS if self.is_bulb else FIF.TILES
        iw = IconWidget(icon)
        iw.setFixedSize(20, 20)
        ib_layout.addWidget(iw)
        header.addWidget(icon_box)
        header.addStretch()

        self.toggle = SwitchButton()
        self.toggle.setChecked(device_info['is_on'])
        self.toggle.checkedChanged.connect(self._on_toggle)
        header.addWidget(self.toggle)
        layout.addLayout(header)

        name_label = QLabel(device_info['alias'])
        name_label.setStyleSheet(
            "color: white; font-weight: bold; font-size: 16px; background: transparent;"
        )
        status_label = QLabel("ONLINE")
        status_label.setStyleSheet(
            "color: #6e7a8e; font-size: 11px; font-weight: bold; spacing: 2px; background: transparent;"
        )
        layout.addWidget(name_label)
        layout.addWidget(status_label)

        ctrl_layout = QHBoxLayout()
        ctrl_layout.setContentsMargins(0, 5, 0, 0)

        if self.is_bulb:
            self.slider = Slider(Qt.Horizontal)
            self.slider.setRange(0, 100)
            val = device_info.get('brightness')
            self.slider.setValue(val if val is not None else 100)
            self.slider.sliderReleased.connect(self._on_brightness_change)
            ctrl_layout.addWidget(self.slider)

        if device_info.get('is_color'):
            self.color_btn = ColorPickerButton(QColor("#ffffff"), "Color")
            self.color_btn.setFixedSize(30, 24)
            self.color_btn.colorChanged.connect(self._on_color_changed)
            ctrl_layout.addWidget(self.color_btn)

        if self.is_bulb:
            layout.addLayout(ctrl_layout)
        else:
            layout.addStretch()

    def _on_toggle(self, checked):
        action = "on" if checked else "off"
        self.worker = ActionThread(action, self.ip)
        self.worker.start()

    def _on_brightness_change(self):
        val = self.slider.value()
        self.worker_b = ActionThread("brightness", self.ip, val)
        self.worker_b.start()

    def _on_color_changed(self, color):
        h = color.hsvHue()
        s = int(color.hsvSaturationF() * 100)
        v = int(color.valueF() * 100)
        self.worker_c = ActionThread("color", self.ip, h, s, v)
        self.worker_c.start()


# ══════════════════════════════════════════════════════════════════════
# Home Assistant threads
# ══════════════════════════════════════════════════════════════════════

class HAConnectionThread(QThread):
    """Tests HA connectivity and emits True/False."""
    result = Signal(bool)

    def run(self):
        try:
            ha_manager.reload_config()
            self.result.emit(ha_manager.test_connection())
        except Exception:
            self.result.emit(False)


class HADataFetchThread(QThread):
    """Fetches all HA entities."""
    entities_found = Signal(dict)

    def run(self):
        try:
            self.entities_found.emit(ha_manager.get_entities())
        except Exception:
            self.entities_found.emit({})


class HAActionThread(QThread):
    """Executes a single HA action."""
    finished = Signal(bool)

    def __init__(self, action: str, entity_id: str, **kwargs):
        super().__init__()
        self.action = action
        self.entity_id = entity_id
        self.kwargs = kwargs

    def run(self):
        try:
            if self.action == "on":
                success = ha_manager.turn_on(self.entity_id, **self.kwargs)
            elif self.action == "off":
                success = ha_manager.turn_off(self.entity_id)
            else:
                success = False
            self.finished.emit(success)
        except Exception:
            self.finished.emit(False)


# ══════════════════════════════════════════════════════════════════════
# HA Entity Card
# ══════════════════════════════════════════════════════════════════════

_DOMAIN_ICONS = {
    "light":        FIF.BRIGHTNESS,
    "switch":       FIF.TILES,
    "script":       FIF.SYNC,
    "scene":        FIF.TILES,
    "media_player": FIF.VOLUME,
    "climate":      FIF.CLOUD,
}

_CARD_STYLE = """
    HAEntityCard {
        background-color: #1a2236;
        border: 1px solid #2a3556;
        border-radius: 20px;
    }
"""

_BTN_STYLE = """
    QPushButton {
        background-color: #33b5e5; color: #0f1524;
        border-radius: 10px; padding: 4px 12px; font-weight: bold; border: none;
    }
    QPushButton:hover { background-color: #55caff; }
"""


class HAEntityCard(QFrame):
    """Card representing a single Home Assistant entity."""

    def __init__(self, entity_id: str, entity_info: dict, parent=None):
        super().__init__(parent)
        self.entity_id = entity_id
        self.domain = entity_id.split(".")[0]
        attrs = entity_info.get("attributes", {})
        self.friendly_name = attrs.get("friendly_name", entity_id)
        self.state = entity_info.get("state", "off")
        self.is_on = self.state in ("on", "playing", "heat", "cool", "auto")
        self.supports_brightness = "brightness" in attrs
        self.is_trigger_only = self.domain in ("script", "scene")

        self.setFixedSize(300, 160)
        self.setStyleSheet(_CARD_STYLE)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)

        # Header row: icon + toggle/button
        header = QHBoxLayout()
        icon_box = QFrame()
        icon_box.setFixedSize(40, 40)
        icon_box.setStyleSheet("background-color: #232d45; border-radius: 12px;")
        ib_layout = QVBoxLayout(icon_box)
        ib_layout.setAlignment(Qt.AlignCenter)
        ib_layout.setContentsMargins(0, 0, 0, 0)
        iw = IconWidget(_DOMAIN_ICONS.get(self.domain, FIF.TILES))
        iw.setFixedSize(20, 20)
        ib_layout.addWidget(iw)
        header.addWidget(icon_box)
        header.addStretch()

        if self.is_trigger_only:
            label = "▶ Run" if self.domain == "script" else "✓ Activate"
            run_btn = QPushButton(label)
            run_btn.setStyleSheet(_BTN_STYLE)
            run_btn.clicked.connect(self._on_trigger)
            header.addWidget(run_btn)
        else:
            self.toggle = SwitchButton()
            self.toggle.setChecked(self.is_on)
            self.toggle.checkedChanged.connect(self._on_toggle)
            header.addWidget(self.toggle)

        layout.addLayout(header)

        name_label = QLabel(self.friendly_name)
        name_label.setStyleSheet(
            "color: white; font-weight: bold; font-size: 16px; background: transparent;"
        )
        domain_label = QLabel(self.domain.upper())
        domain_label.setStyleSheet(
            "color: #6e7a8e; font-size: 11px; font-weight: bold; background: transparent;"
        )
        layout.addWidget(name_label)
        layout.addWidget(domain_label)

        if self.domain == "light" and self.supports_brightness:
            brightness_raw = attrs.get("brightness", 255)
            brightness_pct = int(brightness_raw / 255 * 100)
            self.slider = Slider(Qt.Horizontal)
            self.slider.setRange(0, 100)
            self.slider.setValue(brightness_pct)
            self.slider.sliderReleased.connect(self._on_brightness_change)
            layout.addWidget(self.slider)
        else:
            layout.addStretch()

    def _on_toggle(self, checked: bool):
        self.worker = HAActionThread("on" if checked else "off", self.entity_id)
        self.worker.start()

    def _on_trigger(self):
        self.worker = HAActionThread("on", self.entity_id)
        self.worker.start()

    def _on_brightness_change(self):
        self.worker_b = HAActionThread("on", self.entity_id, brightness_pct=self.slider.value())
        self.worker_b.start()


# ══════════════════════════════════════════════════════════════════════
# Kasa sub-tab
# ══════════════════════════════════════════════════════════════════════

class KasaTab(QWidget):
    """Wraps the original Kasa device grid."""

    def __init__(self, parent=None):
        super().__init__(parent)
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 20, 0, 0)
        main_layout.setSpacing(20)

        # Filter row
        self.filter_layout = QHBoxLayout()
        self.filter_layout.setSpacing(15)
        self.filter_layout.addStretch()
        main_layout.addLayout(self.filter_layout)

        # Device grid
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setStyleSheet("background: transparent; border: none;")
        self.grid_widget = QWidget()
        self.grid_widget.setStyleSheet("background: transparent;")
        self.grid_layout = QGridLayout(self.grid_widget)
        self.grid_layout.setSpacing(20)
        self.grid_layout.setAlignment(Qt.AlignTop | Qt.AlignLeft)
        self.scroll.setWidget(self.grid_widget)
        main_layout.addWidget(self.scroll)

        if kasa_manager.devices:
            print("[HomeAutomation] Using cached devices")
            self._on_devices_loaded(list(kasa_manager.devices.values()))
        else:
            self._load_devices()

    def _load_devices(self):
        if hasattr(self, 'loader') and self.loader and self.loader.isRunning():
            print("[HomeAutomation] Skipping - discovery already in progress")
            return
        self.loader = DataFetchThread()
        self.loader.devices_found.connect(self._on_devices_loaded)
        self.loader.finished.connect(self.loader.deleteLater)
        self.loader.start()

    def _on_devices_loaded(self, devices):
        self.all_devices = devices
        self.room_groups = {}

        keywords = {
            "Office":      ["office", "desk", "work", "pc", "monitor"],
            "Living Room": ["living", "sofa", "tv", "lounge"],
            "Kitchen":     ["kitchen", "dining", "cook", "oven", "fridge"],
            "Bedroom":     ["bed", "sleep", "night"],
            "Exterior":    ["exterior", "garden", "patio", "porch", "garage"],
            "Hallway":     ["hall", "corridor", "stairs"],
        }

        for dev in devices:
            alias = dev['alias'].lower()
            assigned = False
            for room, keys in keywords.items():
                if any(k in alias for k in keys):
                    self.room_groups.setdefault(room, []).append(dev)
                    assigned = True
                    break
            if not assigned:
                self.room_groups.setdefault("Other", []).append(dev)

        self._update_filters()
        self._filter_grid("All")

    def _update_filters(self):
        while self.filter_layout.count() > 1:
            child = self.filter_layout.takeAt(0)
            if child.widget():
                child.widget().deleteLater()

        rooms = ["All"] + sorted(list(self.room_groups.keys()))
        for i, room in enumerate(rooms):
            btn = QPushButton(room)
            btn.setCheckable(True)
            btn.clicked.connect(lambda checked, r=room: self._filter_grid(r))
            if i == 0:
                btn.setChecked(True)
            btn.setStyleSheet("""
                QPushButton {
                    background-color: #1a2236; color: #6e7a8e;
                    border-radius: 15px; padding: 8px 20px; border: none; font-weight: bold;
                }
                QPushButton:checked { background-color: #33b5e5; color: #0f1524; }
                QPushButton:hover   { background-color: #232d45; }
            """)
            self.filter_layout.insertWidget(i, btn)

    def _filter_grid(self, room_name):
        for i in range(self.filter_layout.count() - 1):
            btn = self.filter_layout.itemAt(i).widget()
            if isinstance(btn, QPushButton):
                btn.setChecked(btn.text() == room_name)

        for i in reversed(range(self.grid_layout.count())):
            self.grid_layout.itemAt(i).widget().setParent(None)

        devices = self.all_devices if room_name == "All" else self.room_groups.get(room_name, [])
        row = col = 0
        for dev in devices:
            card = DeviceCard(dev)
            self.grid_layout.addWidget(card, row, col)
            col += 1
            if col >= 3:
                col = 0
                row += 1


# ══════════════════════════════════════════════════════════════════════
# Home Assistant sub-tab
# ══════════════════════════════════════════════════════════════════════

_BTN_PRIMARY = """
    QPushButton {
        background-color: #33b5e5; color: #0f1524;
        border-radius: 12px; padding: 8px 20px; font-weight: bold; border: none;
    }
    QPushButton:hover { background-color: #55caff; }
"""

_BTN_OUTLINE = """
    QPushButton {
        background-color: #1a2236; color: #33b5e5;
        border: 1px solid #33b5e5; border-radius: 12px;
        padding: 8px 20px; font-weight: bold;
    }
    QPushButton:hover { background-color: #232d45; }
"""


class HATab(QWidget):
    """Home Assistant entity grid with 3 states: unconfigured / disconnected / connected."""

    navigate_to_settings = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._main_layout = QVBoxLayout(self)
        self._main_layout.setContentsMargins(0, 20, 0, 0)
        self._content = None
        self._check_connection()

    # ── Connection flow ──────────────────────────────────────────────

    def _check_connection(self):
        url = settings.get("home_assistant.url", "")
        enabled = settings.get("home_assistant.enabled", False)
        if not url or not enabled:
            self._show_unconfigured()
            return
        self._show_status_message("● Connecting...", "#6e7a8e")
        self.conn_thread = HAConnectionThread()
        self.conn_thread.result.connect(self._on_connection_result)
        self.conn_thread.start()

    def _on_connection_result(self, connected: bool):
        if connected:
            self._load_entities()
        else:
            self._show_disconnected(settings.get("home_assistant.url", ""))

    def _load_entities(self):
        self.fetch_thread = HADataFetchThread()
        self.fetch_thread.entities_found.connect(self._on_entities_loaded)
        self.fetch_thread.start()

    def refresh(self):
        self._clear_content()
        self._check_connection()

    # ── Content helpers ──────────────────────────────────────────────

    def _clear_content(self):
        if self._content is not None:
            self._main_layout.removeWidget(self._content)
            self._content.deleteLater()
            self._content = None

    def _show_status_message(self, text: str, color: str):
        self._clear_content()
        w = QLabel(text)
        w.setAlignment(Qt.AlignCenter)
        w.setStyleSheet(f"color: {color}; font-size: 14px; font-weight: bold;")
        self._content = w
        self._main_layout.addWidget(w)

    def _show_unconfigured(self):
        self._clear_content()
        w = QWidget()
        layout = QVBoxLayout(w)
        layout.setAlignment(Qt.AlignCenter)

        msg = QLabel("Home Assistant is not configured.")
        msg.setStyleSheet("color: white; font-size: 16px; font-weight: bold;")
        msg.setAlignment(Qt.AlignCenter)

        sub = QLabel("Add your HA URL and token in Settings.")
        sub.setStyleSheet("color: #6e7a8e; font-size: 13px;")
        sub.setAlignment(Qt.AlignCenter)

        btn = QPushButton("Open Settings")
        btn.setFixedWidth(160)
        btn.setStyleSheet(_BTN_PRIMARY)
        btn.clicked.connect(self.navigate_to_settings)

        layout.addWidget(msg)
        layout.addSpacing(8)
        layout.addWidget(sub)
        layout.addSpacing(20)
        layout.addWidget(btn, alignment=Qt.AlignCenter)

        self._content = w
        self._main_layout.addWidget(w)

    def _show_disconnected(self, url: str):
        self._clear_content()
        w = QWidget()
        layout = QVBoxLayout(w)
        layout.setAlignment(Qt.AlignCenter)

        msg = QLabel("● Disconnected")
        msg.setStyleSheet("color: #f44336; font-size: 16px; font-weight: bold;")
        msg.setAlignment(Qt.AlignCenter)

        sub = QLabel(f"Could not reach {url}")
        sub.setStyleSheet("color: #6e7a8e; font-size: 13px;")
        sub.setAlignment(Qt.AlignCenter)

        btn = QPushButton("Retry")
        btn.setFixedWidth(120)
        btn.setStyleSheet(_BTN_OUTLINE)
        btn.clicked.connect(self.refresh)

        layout.addWidget(msg)
        layout.addSpacing(8)
        layout.addWidget(sub)
        layout.addSpacing(20)
        layout.addWidget(btn, alignment=Qt.AlignCenter)

        self._content = w
        self._main_layout.addWidget(w)

    def _on_entities_loaded(self, entities: dict):
        if not entities:
            self._show_disconnected(settings.get("home_assistant.url", ""))
            return

        self._clear_content()
        w = QWidget()
        w.setStyleSheet("background: transparent;")
        layout = QVBoxLayout(w)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(20)

        self.ha_entities = list(entities.values())
        self.ha_room_groups = self._categorize(self.ha_entities)

        # Filter row
        filter_row = QHBoxLayout()
        filter_row.setSpacing(15)
        rooms = ["All"] + sorted(self.ha_room_groups.keys())
        for i, room in enumerate(rooms):
            btn = QPushButton(room)
            btn.setCheckable(True)
            btn.setChecked(i == 0)
            btn.setStyleSheet("""
                QPushButton {
                    background-color: #1a2236; color: #6e7a8e;
                    border-radius: 15px; padding: 8px 20px; border: none; font-weight: bold;
                }
                QPushButton:checked { background-color: #33b5e5; color: #0f1524; }
                QPushButton:hover   { background-color: #232d45; }
            """)
            btn.clicked.connect(lambda _, r=room: self._filter_ha_grid(r))
            filter_row.addWidget(btn)
        filter_row.addStretch()
        layout.addLayout(filter_row)

        # Grid
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("background: transparent; border: none;")
        self.ha_grid_widget = QWidget()
        self.ha_grid_widget.setStyleSheet("background: transparent;")
        self.ha_grid_layout = QGridLayout(self.ha_grid_widget)
        self.ha_grid_layout.setSpacing(20)
        self.ha_grid_layout.setAlignment(Qt.AlignTop | Qt.AlignLeft)
        scroll.setWidget(self.ha_grid_widget)
        layout.addWidget(scroll)

        self._content = w
        self._main_layout.addWidget(w)
        self._filter_ha_grid("All")

    def _categorize(self, entities: list) -> dict:
        keywords = {
            "Office":      ["office", "desk", "work", "pc", "monitor"],
            "Living Room": ["living", "sofa", "tv", "lounge", "salon"],
            "Kitchen":     ["kitchen", "dining", "cook", "oven", "cuisine"],
            "Bedroom":     ["bed", "sleep", "night", "chambre"],
            "Exterior":    ["exterior", "garden", "patio", "porch", "garage", "exterieur"],
            "Hallway":     ["hall", "corridor", "stairs", "couloir"],
        }
        groups: dict = {}
        for e in entities:
            name = e.get("attributes", {}).get("friendly_name", "").lower()
            assigned = False
            for room, keys in keywords.items():
                if any(k in name for k in keys):
                    groups.setdefault(room, []).append(e)
                    assigned = True
                    break
            if not assigned:
                groups.setdefault("Other", []).append(e)
        return groups

    def _filter_ha_grid(self, room_name: str):
        for i in reversed(range(self.ha_grid_layout.count())):
            self.ha_grid_layout.itemAt(i).widget().setParent(None)

        items = (self.ha_entities if room_name == "All"
                 else self.ha_room_groups.get(room_name, []))
        row = col = 0
        for e in items:
            card = HAEntityCard(e["entity_id"], e)
            self.ha_grid_layout.addWidget(card, row, col)
            col += 1
            if col >= 3:
                col = 0
                row += 1


# ══════════════════════════════════════════════════════════════════════
# Main tab (entry point used by app.py)
# ══════════════════════════════════════════════════════════════════════

_BADGE_BASE = """
    background-color: #0d121d;
    border: 1px solid #1a2236;
    border-radius: 18px;
    padding: 8px 20px;
    font-weight: bold;
    font-size: 12px;
"""

_TAB_STYLE = """
    QTabWidget::pane  { border: none; background: transparent; }
    QTabBar::tab {
        background: #1a2236; color: #6e7a8e;
        padding: 8px 24px; border-radius: 8px; margin-right: 6px;
        font-weight: bold;
    }
    QTabBar::tab:selected { background: #33b5e5; color: #0f1524; }
    QTabBar::tab:hover    { background: #232d45; }
"""


class HomeAutomationTab(QWidget):
    """Environmental Control Dashboard — Kasa | Home Assistant sub-tabs."""

    navigate_to_settings = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("homeAutomationView")

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(40, 40, 40, 40)
        main_layout.setSpacing(30)

        self._setup_header(main_layout)

        self.tab_widget = QTabWidget(self)
        self.tab_widget.setStyleSheet(_TAB_STYLE)

        self.kasa_tab = KasaTab(self)
        self.ha_tab = HATab(self)
        self.ha_tab.navigate_to_settings.connect(self.navigate_to_settings)

        self.tab_widget.addTab(self.kasa_tab, "Kasa")
        self.tab_widget.addTab(self.ha_tab, "Home Assistant")

        main_layout.addWidget(self.tab_widget)

    def _setup_header(self, parent_layout):
        header = QHBoxLayout()

        text_layout = QVBoxLayout()
        title = TitleLabel("Environmental Control", self)
        title.setStyleSheet("font-size: 28px; font-weight: bold; color: white;")
        sub = BodyLabel("Localized automation interface.", self)
        sub.setStyleSheet("color: #6e7a8e; font-size: 14px;")
        text_layout.addWidget(title)
        text_layout.addWidget(sub)
        header.addLayout(text_layout)
        header.addStretch()

        refresh_btn = ToolButton(FIF.SYNC, self)
        refresh_btn.setToolTip("Refresh Devices")
        refresh_btn.clicked.connect(self._on_refresh)
        header.addWidget(refresh_btn)
        header.addSpacing(10)

        self.ha_badge = QLabel("●  Home Assistant")
        self.ha_badge.setStyleSheet(_BADGE_BASE + "color: #6e7a8e;")
        header.addWidget(self.ha_badge)

        parent_layout.addLayout(header)
        self._start_badge_check()

    def _start_badge_check(self):
        url = settings.get("home_assistant.url", "")
        enabled = settings.get("home_assistant.enabled", False)
        if not url or not enabled:
            self._update_badge(False, unconfigured=True)
            return
        self.badge_thread = HAConnectionThread()
        self.badge_thread.result.connect(lambda ok: self._update_badge(ok))
        self.badge_thread.start()

    def _update_badge(self, connected: bool, unconfigured: bool = False):
        if unconfigured:
            self.ha_badge.setText("●  Home Assistant")
            self.ha_badge.setStyleSheet(_BADGE_BASE + "color: #6e7a8e;")
        elif connected:
            self.ha_badge.setText("●  Connected")
            self.ha_badge.setStyleSheet(_BADGE_BASE + "color: #4CAF50;")
        else:
            self.ha_badge.setText("●  Disconnected")
            self.ha_badge.setStyleSheet(_BADGE_BASE + "color: #f44336;")

    def _on_refresh(self):
        self.kasa_tab._load_devices()
        self.ha_tab.refresh()
        self._start_badge_check()

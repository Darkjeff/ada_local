import asyncio
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QFrame,
    QScrollArea, QGridLayout, QPushButton, QTabWidget
)
from PySide6.QtCore import Qt, Signal, QThread, QTimer
from PySide6.QtGui import QColor, QPixmap
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


class HASensorsDataFetchThread(QThread):
    """Fetches HA sensor and binary_sensor entities."""
    entities_found = Signal(dict)

    def run(self):
        try:
            self.entities_found.emit(ha_manager.get_sensor_entities())
        except Exception:
            self.entities_found.emit({})


class HACameraFetchThread(QThread):
    """Fetches all camera entities."""
    cameras_found = Signal(dict)

    def run(self):
        try:
            self.cameras_found.emit(ha_manager.get_camera_entities())
        except Exception:
            self.cameras_found.emit({})


class HACameraSnapshotThread(QThread):
    """Fetches a single camera snapshot image."""
    snapshot_ready = Signal(str, bytes)

    def __init__(self, entity_id: str):
        super().__init__()
        self.entity_id = entity_id

    def run(self):
        data = ha_manager.get_camera_snapshot(self.entity_id)
        if data:
            self.snapshot_ready.emit(self.entity_id, data)


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
# HA Multi-Sensor Card (groups related sensors e.g. temp + humidity)
# ══════════════════════════════════════════════════════════════════════

_DEVICE_CLASS_ICONS = {
    "temperature":    "🌡",
    "humidity":       "💧",
    "pressure":       "🔵",
    "battery":        "🔋",
    "illuminance":    "☀",
    "co2":            "💨",
    "power":          "⚡",
    "energy":         "⚡",
    "voltage":        "⚡",
    "current":        "⚡",
    "motion":         "👁",
    "door":           "🚪",
    "window":         "🪟",
    "smoke":          "🔥",
}

_DEVICE_CLASS_COLORS = {
    "temperature": "#ff7043",
    "humidity":    "#29b6f6",
    "energy":      "#ffca28",
    "power":       "#ab47bc",
    "battery":     "#66bb6a",
}


class HAMultiSensorCard(QFrame):
    """Card displaying multiple related sensor values (e.g. temp + humidity)."""

    def __init__(self, device_name: str, sensors: list[dict], parent=None):
        super().__init__(parent)
        self.setFixedSize(300, 160)
        self.setStyleSheet("""
            HAMultiSensorCard {
                background-color: #1a2236;
                border: 1px solid #2a3556;
                border-radius: 20px;
            }
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 16, 20, 16)
        layout.setSpacing(8)

        title = QLabel(device_name)
        title.setStyleSheet(
            "color: white; font-weight: bold; font-size: 14px; background: transparent;"
        )
        title.setWordWrap(True)
        layout.addWidget(title)

        layout.addSpacing(4)

        for sensor in sensors[:3]:
            attrs = sensor.get("attributes", {})
            dc = attrs.get("device_class", "")
            unit = attrs.get("unit_of_measurement", "")
            friendly = attrs.get("friendly_name", sensor.get("entity_id", ""))
            state = sensor.get("state", "—")
            icon = _DEVICE_CLASS_ICONS.get(dc, "•")
            color = _DEVICE_CLASS_COLORS.get(dc, "#33b5e5")

            row = QHBoxLayout()
            row.setSpacing(10)

            icon_lbl = QLabel(icon)
            icon_lbl.setStyleSheet(f"color: {color}; font-size: 16px; background: transparent;")
            icon_lbl.setFixedWidth(22)

            name_lbl = QLabel(friendly.replace(device_name, "").strip() or friendly)
            name_lbl.setStyleSheet("color: #6e7a8e; font-size: 12px; background: transparent;")

            val_lbl = QLabel(f"{state} {unit}".strip())
            val_lbl.setStyleSheet(f"color: {color}; font-size: 13px; font-weight: bold; background: transparent;")
            val_lbl.setAlignment(Qt.AlignRight)

            row.addWidget(icon_lbl)
            row.addWidget(name_lbl, stretch=1)
            row.addWidget(val_lbl)
            layout.addLayout(row)

        layout.addStretch()


# ══════════════════════════════════════════════════════════════════════
# HA Camera Card (live snapshot)
# ══════════════════════════════════════════════════════════════════════

class HACameraCard(QFrame):
    """Card showing a camera snapshot, auto-refreshing every 5 seconds."""

    def __init__(self, entity_id: str, entity_info: dict, parent=None):
        super().__init__(parent)
        self.entity_id = entity_id
        attrs = entity_info.get("attributes", {})
        self.friendly_name = attrs.get("friendly_name", entity_id)

        self.setFixedSize(300, 220)
        self.setStyleSheet("""
            HACameraCard {
                background-color: #1a2236;
                border: 1px solid #2a3556;
                border-radius: 20px;
            }
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self.image_label = QLabel()
        self.image_label.setFixedSize(300, 180)
        self.image_label.setAlignment(Qt.AlignCenter)
        self.image_label.setStyleSheet(
            "background-color: #0d121d; border-radius: 20px 20px 0 0;"
        )
        self.image_label.setText("⏳ Chargement...")
        self.image_label.setStyleSheet(
            "color: #6e7a8e; font-size: 13px; background-color: #0d121d;"
            "border-radius: 20px 20px 0 0;"
        )
        layout.addWidget(self.image_label)

        name_label = QLabel(f"  {self.friendly_name}")
        name_label.setStyleSheet(
            "color: white; font-weight: bold; font-size: 12px;"
            "background: transparent; padding: 6px 0;"
        )
        layout.addWidget(name_label)

        self._fetch_snapshot()
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._fetch_snapshot)
        self._timer.start(5000)

    def _fetch_snapshot(self):
        try:
            if hasattr(self, "_snap_thread") and self._snap_thread and self._snap_thread.isRunning():
                return
        except RuntimeError:
            self._snap_thread = None
        self._snap_thread = HACameraSnapshotThread(self.entity_id)
        self._snap_thread.snapshot_ready.connect(self._on_snapshot)
        self._snap_thread.start()

    def stop(self):
        self._timer.stop()
        if hasattr(self, "_snap_thread") and self._snap_thread and self._snap_thread.isRunning():
            self._snap_thread.quit()
            self._snap_thread.wait(2000)

    def _on_snapshot(self, entity_id: str, data: bytes):
        pixmap = QPixmap()
        pixmap.loadFromData(data)
        scaled = pixmap.scaled(
            300, 180, Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation
        )
        self.image_label.setPixmap(scaled)
        self.image_label.setStyleSheet(
            "background-color: #0d121d; border-radius: 20px 20px 0 0;"
        )


# ══════════════════════════════════════════════════════════════════════
# HA Sensor Card (read-only)
# ══════════════════════════════════════════════════════════════════════

class HASensorCard(QFrame):
    """Read-only card displaying the current state of a sensor/binary_sensor."""

    def __init__(self, entity_id: str, entity_info: dict, parent=None):
        super().__init__(parent)
        self.entity_id = entity_id
        self.domain = entity_id.split(".")[0]
        attrs = entity_info.get("attributes", {})
        self.friendly_name = attrs.get("friendly_name", entity_id)
        self.state = entity_info.get("state", "unknown")
        unit = attrs.get("unit_of_measurement", "")

        self.setFixedSize(300, 160)
        self.setStyleSheet("""
            HASensorCard {
                background-color: #1a2236;
                border: 1px solid #2a3556;
                border-radius: 20px;
            }
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)

        # Header: icon only (no control)
        header = QHBoxLayout()
        icon_box = QFrame()
        icon_box.setFixedSize(40, 40)
        icon_box.setStyleSheet("background-color: #232d45; border-radius: 12px;")
        ib_layout = QVBoxLayout(icon_box)
        ib_layout.setAlignment(Qt.AlignCenter)
        ib_layout.setContentsMargins(0, 0, 0, 0)
        iw = IconWidget(FIF.INFO)
        iw.setFixedSize(20, 20)
        ib_layout.addWidget(iw)
        header.addWidget(icon_box)
        header.addStretch()

        read_label = QLabel("READ ONLY")
        read_label.setStyleSheet(
            "color: #6e7a8e; font-size: 10px; font-weight: bold; background: transparent;"
        )
        header.addWidget(read_label)
        layout.addLayout(header)

        name_label = QLabel(self.friendly_name)
        name_label.setStyleSheet(
            "color: white; font-weight: bold; font-size: 14px; background: transparent;"
        )
        name_label.setWordWrap(True)
        layout.addWidget(name_label)

        domain_label = QLabel(self.domain.upper().replace("_", " "))
        domain_label.setStyleSheet(
            "color: #6e7a8e; font-size: 10px; font-weight: bold; background: transparent;"
        )
        layout.addWidget(domain_label)

        # State value — colored by domain/state
        if self.domain == "binary_sensor":
            is_on = self.state == "on"
            color = "#4CAF50" if is_on else "#6e7a8e"
            display = "ON" if is_on else "OFF"
        else:
            color = "#33b5e5"
            display = f"{self.state} {unit}".strip()

        state_label = QLabel(display)
        state_label.setStyleSheet(
            f"color: {color}; font-size: 18px; font-weight: bold; background: transparent;"
        )
        layout.addWidget(state_label)


# ══════════════════════════════════════════════════════════════════════
# HA Entity Card (controllable)
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
            brightness_raw = attrs.get("brightness") or 255
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
        try:
            if hasattr(self, 'loader') and self.loader and self.loader.isRunning():
                print("[HomeAutomation] Skipping - discovery already in progress")
                return
        except RuntimeError:
            self.loader = None
        self.loader = DataFetchThread()
        self.loader.devices_found.connect(self._on_devices_loaded)
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

    def _start_auto_refresh(self):
        self._refresh_timer = QTimer(self)
        self._refresh_timer.timeout.connect(self._silent_refresh)
        self._refresh_timer.start(30_000)

    def _silent_refresh(self):
        """Refresh entity states without clearing the UI."""
        try:
            if hasattr(self, "_silent_thread") and self._silent_thread and self._silent_thread.isRunning():
                return
        except RuntimeError:
            self._silent_thread = None
        t = HADataFetchThread()
        t.entities_found.connect(self._on_silent_refresh)
        t.start()
        self._silent_thread = t

    def _on_silent_refresh(self, entities: dict):
        if not entities or not hasattr(self, "ha_entities"):
            return
        self.ha_entities = list(entities.values())
        self.ha_room_groups = self._categorize(self.ha_entities)
        self._filter_ha_grid(self._active_room)

    def refresh(self):
        if hasattr(self, "_refresh_timer"):
            self._refresh_timer.stop()
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
        self._active_room = "All"

        # Filter row
        self._filter_row_layout = QHBoxLayout()
        self._filter_row_layout.setSpacing(15)
        self._filter_buttons: dict[str, QPushButton] = {}
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
            self._filter_buttons[room] = btn
            self._filter_row_layout.addWidget(btn)
        self._filter_row_layout.addStretch()
        layout.addLayout(self._filter_row_layout)

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
        self._start_auto_refresh()

    def _categorize(self, entities: list) -> dict:
        keywords = {
            "Bureau":      ["bureau", "office", "desk", "work", "pc", "monitor", "etagere"],
            "Salon":       ["salon", "living", "sofa", "tv", "lounge", "sejour"],
            "Cuisine":     ["cuisine", "kitchen", "dining", "cook", "oven", "cafe", "cafetiere"],
            "Chambre":     ["chambre", "bedroom", "bed", "sleep", "night", "nuit"],
            "Extérieur":   ["exterieur", "exterior", "garden", "jardin", "patio", "porch", "garage"],
            "Couloir":     ["couloir", "hall", "corridor", "stairs", "entree"],
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
        self._active_room = room_name
        for btn_room, btn in self._filter_buttons.items():
            btn.setChecked(btn_room == room_name)

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
# Home Assistant Sensors sub-tab (read-only)
# ══════════════════════════════════════════════════════════════════════

class HASensorTab(QWidget):
    """Read-only grid of HA sensor and binary_sensor entities."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._main_layout = QVBoxLayout(self)
        self._main_layout.setContentsMargins(0, 20, 0, 0)
        self._content = None
        self._check_and_load()

    def _check_and_load(self):
        url = settings.get("home_assistant.url", "")
        enabled = settings.get("home_assistant.enabled", False)
        if not url or not enabled:
            self._show_message("Home Assistant non configuré.", "#6e7a8e")
            return
        self._show_message("● Connexion...", "#6e7a8e")
        self.conn_thread = HAConnectionThread()
        self.conn_thread.result.connect(self._on_connected)
        self.conn_thread.start()

    def _on_connected(self, ok: bool):
        if not ok:
            self._show_message("● Déconnecté — cliquer sur rafraîchir.", "#f44336")
            return
        self._show_message("⏳ Chargement des capteurs...", "#6e7a8e")
        self.fetch_thread = HASensorsDataFetchThread()
        self.fetch_thread.entities_found.connect(self._on_sensors_loaded)
        self.fetch_thread.start()

    def refresh(self):
        self._clear_content()
        self._check_and_load()

    def _clear_content(self):
        if self._content is not None:
            self._main_layout.removeWidget(self._content)
            self._content.deleteLater()
            self._content = None

    def _show_message(self, text: str, color: str):
        self._clear_content()
        w = QLabel(text)
        w.setAlignment(Qt.AlignCenter)
        w.setStyleSheet(f"color: {color}; font-size: 14px; font-weight: bold;")
        self._content = w
        self._main_layout.addWidget(w)

    def _group_sensors(self, sensor_list: list) -> list:
        """
        Group sensors that share the same device (common friendly_name prefix).
        Returns a list of items: either a single entity dict or a (device_name, [entities]) tuple.
        """
        from collections import defaultdict
        device_map: dict[str, list] = defaultdict(list)
        ungrouped = []

        for e in sensor_list:
            attrs = e.get("attributes", {})
            dc = attrs.get("device_class", "")
            friendly = attrs.get("friendly_name", "")
            # Sensors with recognized device_class go into device grouping
            if dc in _DEVICE_CLASS_ICONS and friendly:
                # Derive device name: remove common suffixes like "Temperature", "Humidity"
                suffixes = ["temperature", "humidity", "pressure", "battery",
                            "illuminance", "co2", "power", "energy", "voltage",
                            "current", "température", "humidité"]
                device_name = friendly.lower()
                for s in suffixes:
                    device_name = device_name.replace(s, "").strip(" -_")
                device_name = device_name.title() or friendly
                device_map[device_name].append(e)
            else:
                ungrouped.append(e)

        result = []
        for device_name, sensors in device_map.items():
            if len(sensors) > 1:
                result.append(("multi", device_name, sensors))
            else:
                result.append(("single", sensors[0]))
        for e in ungrouped:
            result.append(("single", e))
        return result

    def _on_sensors_loaded(self, entities: dict):
        if not entities:
            self._show_message("Aucun capteur trouvé.", "#6e7a8e")
            return

        self._clear_content()
        w = QWidget()
        w.setStyleSheet("background: transparent;")
        layout = QVBoxLayout(w)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(20)

        all_sensors = list(entities.values())
        self._grouped_all = self._group_sensors(all_sensors)
        self._grouped_sensor = self._group_sensors(
            [e for e in all_sensors if e["entity_id"].startswith("sensor.")]
        )
        self._grouped_binary = self._group_sensors(
            [e for e in all_sensors if e["entity_id"].startswith("binary_sensor.")]
        )

        _BTN_FILTER = """
            QPushButton {
                background-color: #1a2236; color: #6e7a8e;
                border-radius: 15px; padding: 8px 20px; border: none; font-weight: bold;
            }
            QPushButton:checked { background-color: #33b5e5; color: #0f1524; }
            QPushButton:hover   { background-color: #232d45; }
        """
        filter_row = QHBoxLayout()
        filter_row.setSpacing(15)
        for i, (label, key) in enumerate([("Tous", "all"), ("Capteurs", "sensor"), ("Binaires", "binary")]):
            btn = QPushButton(label)
            btn.setCheckable(True)
            btn.setChecked(i == 0)
            btn.setStyleSheet(_BTN_FILTER)
            btn.clicked.connect(lambda _, k=key: self._filter_grid(k))
            filter_row.addWidget(btn)
        filter_row.addStretch()
        layout.addLayout(filter_row)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("background: transparent; border: none;")
        self._grid_widget = QWidget()
        self._grid_widget.setStyleSheet("background: transparent;")
        self._grid_layout = QGridLayout(self._grid_widget)
        self._grid_layout.setSpacing(20)
        self._grid_layout.setAlignment(Qt.AlignTop | Qt.AlignLeft)
        scroll.setWidget(self._grid_widget)
        layout.addWidget(scroll)

        self._content = w
        self._main_layout.addWidget(w)
        self._filter_grid("all")

    def _filter_grid(self, key: str):
        for i in reversed(range(self._grid_layout.count())):
            self._grid_layout.itemAt(i).widget().setParent(None)

        groups = {"all": self._grouped_all, "sensor": self._grouped_sensor, "binary": self._grouped_binary}
        items = groups.get(key, self._grouped_all)

        row = col = 0
        for item in items:
            if item[0] == "multi":
                _, device_name, sensors = item
                card = HAMultiSensorCard(device_name, sensors)
            else:
                _, e = item
                card = HASensorCard(e["entity_id"], e)
            self._grid_layout.addWidget(card, row, col)
            col += 1
            if col >= 3:
                col = 0
                row += 1


# ══════════════════════════════════════════════════════════════════════
# HA Camera sub-tab
# ══════════════════════════════════════════════════════════════════════

class HACameraTab(QWidget):
    """Live camera snapshot grid — refreshes every 5 s per card."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._main_layout = QVBoxLayout(self)
        self._main_layout.setContentsMargins(0, 20, 0, 0)
        self._content = None
        self._check_and_load()

    def _check_and_load(self):
        url = settings.get("home_assistant.url", "")
        enabled = settings.get("home_assistant.enabled", False)
        if not url or not enabled:
            self._show_message("Home Assistant non configuré.", "#6e7a8e")
            return
        self._show_message("● Connexion...", "#6e7a8e")
        self.conn_thread = HAConnectionThread()
        self.conn_thread.result.connect(self._on_connected)
        self.conn_thread.start()

    def _on_connected(self, ok: bool):
        if not ok:
            self._show_message("● Déconnecté — cliquer sur rafraîchir.", "#f44336")
            return
        self._show_message("⏳ Chargement des caméras...", "#6e7a8e")
        self.fetch_thread = HACameraFetchThread()
        self.fetch_thread.cameras_found.connect(self._on_cameras_loaded)
        self.fetch_thread.start()

    def refresh(self):
        self._clear_content()
        self._check_and_load()

    def _clear_content(self):
        if self._content is not None:
            self._main_layout.removeWidget(self._content)
            self._content.deleteLater()
            self._content = None

    def _show_message(self, text: str, color: str):
        self._clear_content()
        w = QLabel(text)
        w.setAlignment(Qt.AlignCenter)
        w.setStyleSheet(f"color: {color}; font-size: 14px; font-weight: bold;")
        self._content = w
        self._main_layout.addWidget(w)

    def _on_cameras_loaded(self, entities: dict):
        if not entities:
            self._show_message("Aucune caméra trouvée.", "#6e7a8e")
            return

        self._clear_content()
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("background: transparent; border: none;")
        grid_widget = QWidget()
        grid_widget.setStyleSheet("background: transparent;")
        grid_layout = QGridLayout(grid_widget)
        grid_layout.setSpacing(20)
        grid_layout.setAlignment(Qt.AlignTop | Qt.AlignLeft)
        scroll.setWidget(grid_widget)

        row = col = 0
        for entity_id, info in entities.items():
            card = HACameraCard(entity_id, info)
            grid_layout.addWidget(card, row, col)
            col += 1
            if col >= 3:
                col = 0
                row += 1

        self._content = scroll
        self._main_layout.addWidget(scroll)


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
        self.ha_sensors_tab = HASensorTab(self)
        self.ha_cameras_tab = HACameraTab(self)
        self.ha_tab.navigate_to_settings.connect(self.navigate_to_settings)

        self.tab_widget.addTab(self.kasa_tab, "Kasa")
        self.tab_widget.addTab(self.ha_tab, "Home Assistant")
        self.tab_widget.addTab(self.ha_sensors_tab, "Capteurs")
        self.tab_widget.addTab(self.ha_cameras_tab, "Caméras")

        from PySide6.QtWidgets import QApplication
        QApplication.instance().aboutToQuit.connect(self._cleanup)

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

    def _cleanup(self):
        if hasattr(self, "ha_tab") and hasattr(self.ha_tab, "_refresh_timer"):
            self.ha_tab._refresh_timer.stop()
        # Stop all camera card timers
        cam_tab = getattr(self, "ha_cameras_tab", None)
        if cam_tab and cam_tab._content:
            grid = getattr(cam_tab._content.widget() if hasattr(cam_tab._content, "widget") else None, "layout", None)
            if grid and callable(grid):
                for i in range(grid().count()):
                    w = grid().itemAt(i).widget()
                    if hasattr(w, "stop"):
                        w.stop()

    def _on_refresh(self):
        self.kasa_tab._load_devices()
        self.ha_tab.refresh()
        self.ha_sensors_tab.refresh()
        self.ha_cameras_tab.refresh()
        self._start_badge_check()

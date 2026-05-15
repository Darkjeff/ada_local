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


def _label(text: str, style: str) -> QLabel:
    lbl = QLabel(text)
    lbl.setStyleSheet(style)
    lbl.setWordWrap(True)
    return lbl


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
        if self.entity.provider == "kasa":
            try:
                from core.kasa_control import kasa_manager
                import asyncio
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                try:
                    loop.run_until_complete(
                        kasa_manager.set_hsv(self.entity.provider_entity_id, h, s, v)
                    )
                finally:
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
        if dc in ("door", "window"):
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



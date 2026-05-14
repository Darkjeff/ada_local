"""
SensesTab — ADA sensory hardware selection and capabilities matrix.

Sections:
  1. Vision      — webcam index selection + test capture dialog
  2. Audio Input — microphone selection + STT active status
  3. Voice Output — audio output selection + current TTS voice
  4. Capabilities — active/inactive feature matrix
"""
from __future__ import annotations

from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QLabel, QDialog
)
from qfluentwidgets import (
    ScrollArea, SettingCardGroup, SettingCard, PushSettingCard,
    FluentIcon as FIF, ComboBox
)

from core.i18n import tr, i18n
from core.settings_store import settings
from core.device_enumerator import list_cameras, list_audio_inputs, list_audio_outputs


# ──────────────────────────────────────────────────────────────────────────────
# Background thread — probes hardware without blocking the Qt event loop
# ──────────────────────────────────────────────────────────────────────────────

class _DeviceProbeThread(QThread):
    """Probe cameras + audio devices in background; emit results when done."""
    done = Signal(list, list, list)   # cameras, inputs, outputs

    def run(self) -> None:
        cameras = list_cameras()
        inputs  = list_audio_inputs()
        outputs = list_audio_outputs()
        self.done.emit(cameras, inputs, outputs)


# ──────────────────────────────────────────────────────────────────────────────
# Custom SettingCard subclasses
# ──────────────────────────────────────────────────────────────────────────────

class _DeviceComboCard(SettingCard):
    """SettingCard with a ComboBox for selecting an audio device by index.

    The ComboBox stores the device integer index as item userData.
    Selections are persisted to `settings_key`.
    """
    device_changed = Signal(int)   # emits the selected device index (-1 = default)

    def __init__(self, icon, title: str, description: str,
                 settings_key: str, parent=None):
        super().__init__(icon, title, description, parent)
        self._settings_key = settings_key

        self.combo = ComboBox(self)
        self.combo.setMinimumWidth(220)
        self.combo.addItem(tr("senses.voice_stt_system_default"), userData=-1)
        self.combo.currentIndexChanged.connect(self._on_changed)
        self.hBoxLayout.addWidget(self.combo, 0, Qt.AlignRight)
        self.hBoxLayout.addSpacing(16)

    def populate(self, devices: list[dict], saved_index: int) -> None:
        """Fill combo with device list and restore the saved selection."""
        self.combo.blockSignals(True)
        self.combo.clear()
        self.combo.addItem(tr("senses.voice_stt_system_default"), userData=-1)
        for d in devices:
            self.combo.addItem(d["name"], userData=d["index"])
        # Restore saved selection
        for i in range(self.combo.count()):
            if self.combo.itemData(i) == saved_index:
                self.combo.setCurrentIndex(i)
                break
        self.combo.blockSignals(False)

    def _on_changed(self, combo_idx: int) -> None:
        device_idx = self.combo.itemData(combo_idx)
        if device_idx is not None:
            settings.set(self._settings_key, device_idx)
            self.device_changed.emit(device_idx)

    def retranslate(self, title: str, description: str) -> None:
        self.titleLabel.setText(title)
        self.contentLabel.setText(description)
        # Update "System Default" text while preserving selection
        if self.combo.count() > 0 and self.combo.itemData(0) == -1:
            self.combo.blockSignals(True)
            self.combo.setItemText(0, tr("senses.voice_stt_system_default"))
            self.combo.blockSignals(False)


class _CameraComboCard(SettingCard):
    """SettingCard with a ComboBox for selecting a camera by index."""
    camera_changed = Signal(int)

    def __init__(self, parent=None):
        super().__init__(
            FIF.CAMERA,
            tr("senses.vision_camera"),
            tr("senses.vision_camera_desc"),
            parent
        )
        self.combo = ComboBox(self)
        self.combo.setMinimumWidth(180)
        self.combo.addItem("Camera 0", userData=0)
        self.combo.currentIndexChanged.connect(self._on_changed)
        self.hBoxLayout.addWidget(self.combo, 0, Qt.AlignRight)
        self.hBoxLayout.addSpacing(16)

    def populate(self, cameras: list[dict], saved_index: int) -> None:
        """Fill combo with detected cameras; fall back to Camera 0 if none found."""
        cam_list = cameras if cameras else [{"index": 0, "name": "Camera 0"}]
        self.combo.blockSignals(True)
        self.combo.clear()
        for c in cam_list:
            self.combo.addItem(c["name"], userData=c["index"])
        for i in range(self.combo.count()):
            if self.combo.itemData(i) == saved_index:
                self.combo.setCurrentIndex(i)
                break
        self.combo.blockSignals(False)

    def current_index(self) -> int:
        """Return the currently selected camera index (int)."""
        data = self.combo.itemData(self.combo.currentIndex())
        return data if data is not None else 0

    def _on_changed(self, combo_idx: int) -> None:
        idx = self.combo.itemData(combo_idx)
        if idx is not None:
            settings.set("senses.camera_index", idx)
            self.camera_changed.emit(idx)

    def retranslate(self) -> None:
        self.titleLabel.setText(tr("senses.vision_camera"))
        self.contentLabel.setText(tr("senses.vision_camera_desc"))


class _StatusCard(SettingCard):
    """Read-only SettingCard showing a colored status text on the right."""

    def __init__(self, icon, title: str, status_text: str,
                 active: bool = True, parent=None):
        super().__init__(icon, title, "", parent)
        self.contentLabel.hide()

        self._status_lbl = QLabel(status_text, self)
        self._set_style(active)
        self.hBoxLayout.addWidget(self._status_lbl, 0, Qt.AlignRight)
        self.hBoxLayout.addSpacing(16)

    def _set_style(self, active: bool) -> None:
        if active:
            self._status_lbl.setStyleSheet(
                "color: #22c55e; font-size: 13px; font-weight: 500;"
            )
        else:
            self._status_lbl.setStyleSheet(
                "color: #6b7280; font-size: 13px;"
            )

    def set_status(self, text: str, active: bool) -> None:
        """Update displayed status text and colour."""
        self._status_lbl.setText(text)
        self._set_style(active)

    def retranslate(self, title: str) -> None:
        self.titleLabel.setText(title)


class CapabilityCard(SettingCard):
    """Read-only SettingCard for one row in the capabilities matrix.

    Shows a coloured "Active" / "Inactive" badge on the right.
    """

    def __init__(self, key: str, active: bool, parent=None):
        super().__init__(
            FIF.ACCEPT if active else FIF.CANCEL,
            tr(f"senses.{key}"),
            "",
            parent
        )
        self.key = key
        self._active = active
        self.contentLabel.hide()

        self._badge = QLabel(self)
        self.hBoxLayout.addWidget(self._badge, 0, Qt.AlignRight)
        self.hBoxLayout.addSpacing(16)
        self._refresh_badge()

    def _refresh_badge(self) -> None:
        if self._active:
            self._badge.setText(tr("senses.cap_active"))
            self._badge.setStyleSheet(
                "color: #22c55e; font-size: 13px; font-weight: 500;"
            )
        else:
            self._badge.setText(tr("senses.cap_inactive"))
            self._badge.setStyleSheet("color: #6b7280; font-size: 13px;")

    def retranslate(self) -> None:
        self.titleLabel.setText(tr(f"senses.{self.key}"))
        self._refresh_badge()


# ──────────────────────────────────────────────────────────────────────────────
# Main tab
# ──────────────────────────────────────────────────────────────────────────────

class SensesTab(ScrollArea):
    """
    ADA Senses page.

    Sections:
        Vision       — webcam selection + test-capture button
        Audio Input  — microphone selection + STT status
        Voice Output — audio output selection + current TTS voice
        Capabilities — read-only matrix of 8 capabilities
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("sensesInterface")
        self._probe_thread: _DeviceProbeThread | None = None

        # Central scroll container
        self._content = QWidget()
        self._content.setObjectName("sensesContent")
        self.setWidget(self._content)
        self.setWidgetResizable(True)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)

        self._layout = QVBoxLayout(self._content)
        self._layout.setSpacing(16)
        self._layout.setContentsMargins(36, 28, 36, 28)

        self._build_ui()
        self._probe_devices()
        i18n.language_changed.connect(self.retranslate_ui)

    # ── UI construction ────────────────────────────────────────────────────

    def _build_ui(self) -> None:
        # ── 1. Vision ──────────────────────────────────────────────────────
        self.vision_group = SettingCardGroup(tr("senses.vision"), self._content)

        self.camera_card = _CameraComboCard(self.vision_group)
        self.vision_group.addSettingCard(self.camera_card)

        self.test_card = PushSettingCard(
            text=tr("senses.vision_test_btn"),
            icon=FIF.VIDEO,
            title=tr("senses.vision_test"),
            content=tr("senses.vision_test_desc"),
            parent=self.vision_group
        )
        self.test_card.clicked.connect(self._on_test_capture)
        self.vision_group.addSettingCard(self.test_card)

        self._layout.addWidget(self.vision_group)

        # ── 2. Audio Input ─────────────────────────────────────────────────
        self.audio_group = SettingCardGroup(tr("senses.audio"), self._content)

        self.mic_card = _DeviceComboCard(
            icon=FIF.MICROPHONE,
            title=tr("senses.audio_mic"),
            description=tr("senses.audio_mic_desc"),
            settings_key="senses.audio_input_device",
            parent=self.audio_group,
        )
        self.audio_group.addSettingCard(self.mic_card)

        from core.voice_assistant import voice_assistant
        self._stt_active = getattr(voice_assistant, "running", False)
        stt_text = (tr("senses.audio_stt_status_active") if self._stt_active
                    else tr("senses.audio_stt_status_inactive"))
        self.stt_card = _StatusCard(
            icon=FIF.HEADPHONE,
            title=tr("senses.audio_stt_status"),
            status_text=stt_text,
            active=self._stt_active,
            parent=self.audio_group,
        )
        self.audio_group.addSettingCard(self.stt_card)

        self._layout.addWidget(self.audio_group)

        # ── 3. Voice Output ────────────────────────────────────────────────
        self.voice_group = SettingCardGroup(tr("senses.voice"), self._content)

        current_voice = settings.get("tts.voice", "—") or "—"
        self.tts_model_card = _StatusCard(
            icon=FIF.VOLUME,
            title=tr("senses.voice_model"),
            status_text=current_voice,
            active=True,
            parent=self.voice_group,
        )
        self.voice_group.addSettingCard(self.tts_model_card)

        self.output_card = _DeviceComboCard(
            icon=FIF.SPEAKERS,
            title=tr("senses.voice_output"),
            description=tr("senses.voice_output_desc"),
            settings_key="senses.audio_output_device",
            parent=self.voice_group,
        )
        self.voice_group.addSettingCard(self.output_card)

        self._layout.addWidget(self.voice_group)

        # ── 4. Capabilities ────────────────────────────────────────────────
        self.cap_group = SettingCardGroup(tr("senses.capabilities"), self._content)

        self._cap_cards: list[CapabilityCard] = []
        for key, active in self._check_capabilities():
            card = CapabilityCard(key, active, self.cap_group)
            self._cap_cards.append(card)
            self.cap_group.addSettingCard(card)

        self._layout.addWidget(self.cap_group)
        self._layout.addStretch(1)

    # ── Hardware probing ───────────────────────────────────────────────────

    def _probe_devices(self) -> None:
        """Start background device probe; populate combos when done."""
        self._probe_thread = _DeviceProbeThread()
        self._probe_thread.done.connect(self._on_devices_ready)
        self._probe_thread.finished.connect(self._probe_thread.deleteLater)
        self._probe_thread.start()

    def _on_devices_ready(self, cameras: list, inputs: list, outputs: list) -> None:
        saved_cam = settings.get("senses.camera_index", 0)
        self.camera_card.populate(cameras, saved_cam)

        saved_in = settings.get("senses.audio_input_device", -1)
        self.mic_card.populate(inputs, saved_in)

        saved_out = settings.get("senses.audio_output_device", -1)
        self.output_card.populate(outputs, saved_out)

    # ── Capabilities check ─────────────────────────────────────────────────

    @staticmethod
    def _check_capabilities() -> list[tuple[str, bool]]:
        """Return [(i18n_key_suffix, is_active)] for each capability row."""
        from core.voice_assistant import voice_assistant
        from core.tts import tts

        try:
            import cv2 as _cv2  # noqa: F401
            webcam_ok = True
        except ImportError:
            webcam_ok = False

        try:
            import playwright as _pw  # noqa: F401
            playwright_ok = True
        except ImportError:
            playwright_ok = False

        return [
            ("cap_webcam",   webcam_ok),
            ("cap_stt",      getattr(voice_assistant, "running", False)),
            ("cap_tts",      getattr(tts, "enabled", False)),
            ("cap_ha",       bool(settings.get("home_assistant.enabled", False))),
            ("cap_telegram", bool(settings.get("telegram.enabled", False))),
            ("cap_web",      playwright_ok),
            ("cap_memory",   True),    # always built-in
            ("cap_printers", bool(settings.get("k1.ip", ""))),
        ]

    # ── Test capture ───────────────────────────────────────────────────────

    def _on_test_capture(self) -> None:
        """Open live webcam preview in a modal dialog."""
        try:
            from gui.components.camera_preview import CameraLiveWidget
            import cv2 as _cv2_check  # noqa: F401
        except ImportError:
            from qfluentwidgets import InfoBar, InfoBarPosition
            from PySide6.QtCore import Qt
            InfoBar.warning(
                title="Webcam unavailable",
                content="opencv-python (cv2) is not installed.",
                orient=Qt.Horizontal, isClosable=True,
                position=InfoBarPosition.TOP, duration=3000, parent=self.window()
            )
            return

        cam_idx = self.camera_card.current_index()

        dialog = QDialog(self)
        dialog.setWindowTitle(tr("senses.vision_test"))
        dialog.setMinimumSize(560, 420)
        dialog.setStyleSheet("QDialog { background: #1a1a2e; }")

        layout = QVBoxLayout(dialog)
        layout.setContentsMargins(12, 12, 12, 12)

        live = CameraLiveWidget(camera_index=cam_idx, parent=dialog)
        live.captured.connect(lambda _bytes: dialog.accept())
        live.closed.connect(dialog.reject)
        layout.addWidget(live)

        dialog.exec()

    # ── Retranslation ──────────────────────────────────────────────────────

    def retranslate_ui(self, _lang: str = "") -> None:
        """Update all visible text in-place when the language changes."""
        # Vision
        self.vision_group.titleLabel.setText(tr("senses.vision"))
        self.camera_card.retranslate()
        self.test_card.titleLabel.setText(tr("senses.vision_test"))
        self.test_card.contentLabel.setText(tr("senses.vision_test_desc"))
        self.test_card.button.setText(tr("senses.vision_test_btn"))

        # Audio
        self.audio_group.titleLabel.setText(tr("senses.audio"))
        self.mic_card.retranslate(tr("senses.audio_mic"), tr("senses.audio_mic_desc"))
        self.stt_card.retranslate(tr("senses.audio_stt_status"))
        self.stt_card.set_status(
            tr("senses.audio_stt_status_active" if self._stt_active else "senses.audio_stt_status_inactive"),
            self._stt_active
        )

        # Voice
        self.voice_group.titleLabel.setText(tr("senses.voice"))
        self.tts_model_card.retranslate(tr("senses.voice_model"))
        self.output_card.retranslate(tr("senses.voice_output"), tr("senses.voice_output_desc"))

        # Capabilities
        self.cap_group.titleLabel.setText(tr("senses.capabilities"))
        for card in self._cap_cards:
            card.retranslate()

"""
Printers tab — OctoPrint / Moonraker control via REST API.
"""

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QFrame,
    QLineEdit, QPushButton, QProgressBar, QComboBox,
)
from PySide6.QtCore import Qt, Signal, QThread, QTimer
from qfluentwidgets import TitleLabel, BodyLabel, ToolButton, FluentIcon as FIF

from core.printer_agent import printer_agent, PrinterType
from core.settings_store import settings


# ── Styles ──────────────────────────────────────────────────────────── #

_BADGE_BASE = """
    background-color: #0d121d;
    border: 1px solid #1a2236;
    border-radius: 18px;
    padding: 8px 20px;
    font-weight: bold;
    font-size: 12px;
"""

_BTN_PRIMARY = """
    QPushButton {
        background-color: #33b5e5; color: #0f1524;
        border-radius: 12px; padding: 8px 20px; font-weight: bold; border: none;
    }
    QPushButton:hover { background-color: #55caff; }
    QPushButton:disabled { background-color: #2a3556; color: #6e7a8e; }
"""

_BTN_DANGER = """
    QPushButton {
        background-color: #f44336; color: white;
        border-radius: 12px; padding: 8px 20px; font-weight: bold; border: none;
    }
    QPushButton:hover { background-color: #e57373; }
    QPushButton:disabled { background-color: #2a3556; color: #6e7a8e; }
"""

_BTN_OUTLINE = """
    QPushButton {
        background-color: #1a2236; color: #33b5e5;
        border: 1px solid #33b5e5; border-radius: 12px;
        padding: 8px 20px; font-weight: bold;
    }
    QPushButton:hover { background-color: #232d45; }
    QPushButton:disabled { border-color: #2a3556; color: #6e7a8e; }
"""

_INPUT_STYLE = """
    QLineEdit {
        background-color: #1a2236;
        border: 1px solid #2a3556;
        border-radius: 10px;
        color: white;
        padding: 8px 14px;
        font-size: 14px;
    }
    QLineEdit:focus { border-color: #33b5e5; }
"""

_COMBO_STYLE = """
    QComboBox {
        background-color: #1a2236;
        border: 1px solid #2a3556;
        border-radius: 10px;
        color: white;
        padding: 8px 14px;
        font-size: 14px;
        min-width: 140px;
    }
    QComboBox:focus { border-color: #33b5e5; }
    QComboBox::drop-down { border: none; width: 24px; }
    QComboBox QAbstractItemView {
        background-color: #1a2236;
        color: white;
        selection-background-color: #2a3556;
    }
"""

_PROGRESS_STYLE = """
    QProgressBar {
        background-color: #232d45;
        border-radius: 6px;
        height: 12px;
        text-align: center;
        color: white;
        font-size: 11px;
        font-weight: bold;
        border: none;
    }
    QProgressBar::chunk { background-color: #33b5e5; border-radius: 6px; }
"""

_PANEL_STYLE = """
    QFrame#settingsPanel {
        background-color: #0d121d;
        border: 1px solid #1a2236;
        border-radius: 16px;
    }
"""

_CARD_STYLE = """
    QFrame#statusCard {
        background-color: #1a2236;
        border: 1px solid #2a3556;
        border-radius: 20px;
    }
"""


# ── Threads ──────────────────────────────────────────────────────────── #

class ConnectThread(QThread):
    result = Signal(bool)

    def run(self):
        try:
            self.result.emit(printer_agent.connect())
        except Exception:
            self.result.emit(False)


class StatusFetchThread(QThread):
    status_found = Signal(object)  # PrintStatus or None

    def run(self):
        try:
            self.status_found.emit(printer_agent.get_status())
        except Exception:
            self.status_found.emit(None)


class PrintActionThread(QThread):
    finished = Signal(bool)

    def __init__(self, action: str):
        super().__init__()
        self.action = action

    def run(self):
        try:
            if self.action == "pause":
                ok = printer_agent.pause_print()
            elif self.action == "resume":
                ok = printer_agent.resume_print()
            elif self.action == "cancel":
                ok = printer_agent.cancel_print()
            else:
                ok = False
            self.finished.emit(ok)
        except Exception:
            self.finished.emit(False)


class DiscoverThread(QThread):
    found = Signal(list)

    def run(self):
        try:
            self.found.emit(printer_agent.discover_printers(timeout=5.0))
        except Exception:
            self.found.emit([])


# ── Status card ──────────────────────────────────────────────────────── #

class PrinterStatusCard(QFrame):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("statusCard")
        self.setStyleSheet(_CARD_STYLE)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(16)

        # State row
        state_row = QHBoxLayout()
        self.state_label = QLabel("● Standby")
        self.state_label.setStyleSheet("color: #6e7a8e; font-size: 16px; font-weight: bold;")
        self.filename_label = QLabel("")
        self.filename_label.setStyleSheet("color: #6e7a8e; font-size: 13px;")
        state_row.addWidget(self.state_label)
        state_row.addStretch()
        state_row.addWidget(self.filename_label)
        layout.addLayout(state_row)

        # Progress bar
        self.progress_bar = QProgressBar()
        self.progress_bar.setStyleSheet(_PROGRESS_STYLE)
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress_bar.setFixedHeight(18)
        layout.addWidget(self.progress_bar)

        # Temperatures + time row
        info_row = QHBoxLayout()
        info_row.setSpacing(40)

        self.nozzle_label = self._make_temp_col(info_row, "NOZZLE")
        self.bed_label = self._make_temp_col(info_row, "BED")

        time_col = QVBoxLayout()
        time_col.setSpacing(4)
        time_title = QLabel("ELAPSED / LEFT")
        time_title.setStyleSheet("color: #6e7a8e; font-size: 11px; font-weight: bold;")
        self.time_label = QLabel("--:--:-- / --:--:--")
        self.time_label.setStyleSheet("color: white; font-size: 16px; font-weight: bold;")
        time_col.addWidget(time_title)
        time_col.addWidget(self.time_label)
        info_row.addLayout(time_col)

        info_row.addStretch()
        layout.addLayout(info_row)

    def _make_temp_col(self, parent_layout, title: str) -> QLabel:
        col = QVBoxLayout()
        col.setSpacing(4)
        t = QLabel(title)
        t.setStyleSheet("color: #6e7a8e; font-size: 11px; font-weight: bold;")
        val = QLabel("-- °C / -- °C")
        val.setStyleSheet("color: white; font-size: 22px; font-weight: bold;")
        col.addWidget(t)
        col.addWidget(val)
        parent_layout.addLayout(col)
        return val

    def update_status(self, status):
        if status is None:
            self.state_label.setText("● No data")
            self.state_label.setStyleSheet("color: #6e7a8e; font-size: 16px; font-weight: bold;")
            return

        color = {
            "printing": "#4CAF50",
            "paused":   "#FFC107",
            "error":    "#f44336",
        }.get(status.state, "#6e7a8e")

        self.state_label.setText(f"● {status.state.capitalize()}")
        self.state_label.setStyleSheet(f"color: {color}; font-size: 16px; font-weight: bold;")

        fname = status.filename or ""
        self.filename_label.setText(fname[:40] + "…" if len(fname) > 40 else fname)

        self.progress_bar.setValue(int(status.progress * 100))

        self.nozzle_label.setText(f"{status.nozzle_temp:.0f} °C / {status.nozzle_target:.0f} °C")
        self.bed_label.setText(f"{status.bed_temp:.0f} °C / {status.bed_target:.0f} °C")

        elapsed = status.format_time(status.time_elapsed)
        remaining = status.format_time(status.time_remaining)
        self.time_label.setText(f"{elapsed} / {remaining}")


# ── Main tab ─────────────────────────────────────────────────────────── #

class PrintersTab(QWidget):
    """3D Printer dashboard — OctoPrint / Moonraker."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("printersView")
        self._last_state = ""

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(40, 40, 40, 40)
        main_layout.setSpacing(30)

        self._setup_header(main_layout)
        self._setup_settings_panel(main_layout)
        self._setup_status_card(main_layout)
        self._setup_controls(main_layout)
        main_layout.addStretch()

        self._refresh_timer = QTimer(self)
        self._refresh_timer.setInterval(10_000)
        self._refresh_timer.timeout.connect(self._fetch_status)

        self._update_ui_connected(printer_agent.is_connected)
        if printer_agent.is_connected:
            self._fetch_status()

    # ── Header ──────────────────────────────────────────────────────── #

    def _setup_header(self, parent_layout):
        header = QHBoxLayout()

        text_col = QVBoxLayout()
        title = TitleLabel("Printers", self)
        title.setStyleSheet("font-size: 28px; font-weight: bold; color: white;")
        sub = BodyLabel("OctoPrint / Moonraker — REST API control.", self)
        sub.setStyleSheet("color: #6e7a8e; font-size: 14px;")
        text_col.addWidget(title)
        text_col.addWidget(sub)
        header.addLayout(text_col)
        header.addStretch()

        self.refresh_btn = ToolButton(FIF.SYNC, self)
        self.refresh_btn.setToolTip("Refresh Status")
        self.refresh_btn.clicked.connect(self._fetch_status)
        header.addWidget(self.refresh_btn)
        header.addSpacing(10)

        self.badge = QLabel("●  Disconnected")
        self.badge.setStyleSheet(_BADGE_BASE + "color: #f44336;")
        header.addWidget(self.badge)

        parent_layout.addLayout(header)

    # ── Settings panel ───────────────────────────────────────────────── #

    def _setup_settings_panel(self, parent_layout):
        panel = QFrame()
        panel.setObjectName("settingsPanel")
        panel.setStyleSheet(_PANEL_STYLE)

        playout = QHBoxLayout(panel)
        playout.setContentsMargins(24, 16, 24, 16)
        playout.setSpacing(16)

        # Type
        type_col = QVBoxLayout()
        type_col.setSpacing(6)
        type_col.addWidget(self._field_label("Type"))
        self.type_combo = QComboBox()
        self.type_combo.setStyleSheet(_COMBO_STYLE)
        self.type_combo.addItem("Moonraker / Klipper", "moonraker")
        self.type_combo.addItem("OctoPrint", "octoprint")
        self.type_combo.addItem("Creality K1 (SSH)", "k1_ssh")
        saved_type = settings.get("printer.type", "moonraker")
        idx = self.type_combo.findData(saved_type)
        if idx >= 0:
            self.type_combo.setCurrentIndex(idx)
        self.type_combo.currentIndexChanged.connect(self._on_type_changed)
        type_col.addWidget(self.type_combo)
        playout.addLayout(type_col)

        # Host
        host_col = QVBoxLayout()
        host_col.setSpacing(6)
        host_col.addWidget(self._field_label("Host / IP"))
        self.host_input = QLineEdit()
        self.host_input.setPlaceholderText("e.g. 192.168.1.100")
        self.host_input.setText(settings.get("printer.host", ""))
        self.host_input.setStyleSheet(_INPUT_STYLE)
        self.host_input.setMinimumWidth(180)
        host_col.addWidget(self.host_input)
        playout.addLayout(host_col)

        # Port
        port_col = QVBoxLayout()
        port_col.setSpacing(6)
        port_col.addWidget(self._field_label("Port"))
        self.port_input = QLineEdit()
        self.port_input.setPlaceholderText("80")
        self.port_input.setText(str(settings.get("printer.port", 80) or 80))
        self.port_input.setStyleSheet(_INPUT_STYLE)
        self.port_input.setMaximumWidth(80)
        port_col.addWidget(self.port_input)
        playout.addLayout(port_col)

        # API Key (OctoPrint) / SSH Password (K1)
        key_col = QVBoxLayout()
        key_col.setSpacing(6)
        self._key_label = self._field_label("API Key (OctoPrint)")
        key_col.addWidget(self._key_label)
        self.key_input = QLineEdit()
        self.key_input.setEchoMode(QLineEdit.Password)
        self.key_input.setPlaceholderText("optional")
        self.key_input.setText(settings.get("printer.api_key", ""))
        self.key_input.setStyleSheet(_INPUT_STYLE)
        self.key_input.setMinimumWidth(160)
        key_col.addWidget(self.key_input)
        playout.addLayout(key_col)

        playout.addStretch()

        # Buttons column
        btn_col = QVBoxLayout()
        btn_col.setSpacing(8)
        btn_col.addStretch()

        self.discover_btn = QPushButton("Discover")
        self.discover_btn.setStyleSheet(_BTN_OUTLINE)
        self.discover_btn.setFixedWidth(100)
        self.discover_btn.setToolTip("mDNS auto-discovery (needs zeroconf)")
        self.discover_btn.clicked.connect(self._on_discover)
        btn_col.addWidget(self.discover_btn)

        self.connect_btn = QPushButton("Connect")
        self.connect_btn.setStyleSheet(_BTN_PRIMARY)
        self.connect_btn.setFixedWidth(100)
        self.connect_btn.clicked.connect(self._on_connect)
        btn_col.addWidget(self.connect_btn)

        playout.addLayout(btn_col)
        parent_layout.addWidget(panel)

        self._update_key_visibility()

    def _field_label(self, text: str) -> QLabel:
        lbl = QLabel(text)
        lbl.setStyleSheet("color: #6e7a8e; font-size: 12px; font-weight: bold;")
        return lbl

    def _on_type_changed(self):
        self._update_key_visibility()

    def _update_key_visibility(self):
        ptype = self.type_combo.currentData()
        if ptype == "octoprint":
            self.key_input.setVisible(True)
            self._key_label.setText("API Key (OctoPrint)")
            self.key_input.setPlaceholderText("optional")
        elif ptype == "k1_ssh":
            self.key_input.setVisible(True)
            self._key_label.setText("SSH Password")
            self.key_input.setPlaceholderText("root password")
        else:
            self.key_input.setVisible(False)

    # ── Status card ──────────────────────────────────────────────────── #

    def _setup_status_card(self, parent_layout):
        self.status_card = PrinterStatusCard(self)
        parent_layout.addWidget(self.status_card)

    # ── Control buttons ──────────────────────────────────────────────── #

    def _setup_controls(self, parent_layout):
        ctrl_row = QHBoxLayout()
        ctrl_row.setSpacing(12)

        self.pause_btn = QPushButton("⏸  Pause")
        self.pause_btn.setStyleSheet(_BTN_OUTLINE)
        self.pause_btn.setFixedHeight(44)
        self.pause_btn.clicked.connect(lambda: self._send_action("pause"))

        self.resume_btn = QPushButton("▶  Resume")
        self.resume_btn.setStyleSheet(_BTN_PRIMARY)
        self.resume_btn.setFixedHeight(44)
        self.resume_btn.clicked.connect(lambda: self._send_action("resume"))

        self.cancel_btn = QPushButton("✕  Cancel Print")
        self.cancel_btn.setStyleSheet(_BTN_DANGER)
        self.cancel_btn.setFixedHeight(44)
        self.cancel_btn.clicked.connect(lambda: self._send_action("cancel"))

        ctrl_row.addWidget(self.pause_btn)
        ctrl_row.addWidget(self.resume_btn)
        ctrl_row.addWidget(self.cancel_btn)
        ctrl_row.addStretch()

        parent_layout.addLayout(ctrl_row)

    # ── Logic ────────────────────────────────────────────────────────── #

    def _on_connect(self):
        host = self.host_input.text().strip()
        port_str = self.port_input.text().strip()
        port = int(port_str) if port_str.isdigit() else 80
        ptype = self.type_combo.currentData()
        api_key = self.key_input.text().strip()

        settings.set("printer.host", host)
        settings.set("printer.port", port)
        settings.set("printer.type", ptype)
        settings.set("printer.api_key", api_key)
        # For K1 SSH: reuse k1.ip and k1.password so k1_control.py picks them up
        if ptype == "k1_ssh":
            settings.set("k1.ip", host)
            settings.set("k1.password", api_key)
        printer_agent.reload_config()

        self.connect_btn.setText("Connecting…")
        self.connect_btn.setEnabled(False)
        self.badge.setText("●  Connecting…")
        self.badge.setStyleSheet(_BADGE_BASE + "color: #6e7a8e;")

        self._conn_thread = ConnectThread()
        self._conn_thread.result.connect(self._on_connect_result)
        self._conn_thread.start()

    def _on_connect_result(self, ok: bool):
        self.connect_btn.setText("Connect")
        self.connect_btn.setEnabled(True)
        self._update_ui_connected(ok)
        if ok:
            self._fetch_status()

    def _on_discover(self):
        self.discover_btn.setText("Scanning…")
        self.discover_btn.setEnabled(False)
        self._disc_thread = DiscoverThread()
        self._disc_thread.found.connect(self._on_discover_result)
        self._disc_thread.start()

    def _on_discover_result(self, printers: list):
        self.discover_btn.setText("Discover")
        self.discover_btn.setEnabled(True)
        if printers:
            p = printers[0]
            self.host_input.setText(p["host"])
            self.port_input.setText(str(p["port"]))
            idx = self.type_combo.findData(p["type"])
            if idx >= 0:
                self.type_combo.setCurrentIndex(idx)
            self.badge.setText(f"●  Found: {p['name']}")
            self.badge.setStyleSheet(_BADGE_BASE + "color: #FFC107;")
        else:
            self.badge.setText("●  No printers found")
            self.badge.setStyleSheet(_BADGE_BASE + "color: #f44336;")

    def _fetch_status(self):
        if not printer_agent.is_connected:
            return
        self._fetch_thread = StatusFetchThread()
        self._fetch_thread.status_found.connect(self._on_status)
        self._fetch_thread.start()

    def _on_status(self, status):
        self.status_card.update_status(status)
        state = status.state if status else ""
        if state != self._last_state:
            self._last_state = state
            self._update_control_buttons(state)

    def _send_action(self, action: str):
        self._action_thread = PrintActionThread(action)
        self._action_thread.finished.connect(
            lambda ok: self._fetch_status() if ok else None
        )
        self._action_thread.start()

    def _update_ui_connected(self, connected: bool):
        if connected:
            self.badge.setText("●  Connected")
            self.badge.setStyleSheet(_BADGE_BASE + "color: #4CAF50;")
            self._refresh_timer.start()
        else:
            self.badge.setText("●  Disconnected")
            self.badge.setStyleSheet(_BADGE_BASE + "color: #f44336;")
            self._refresh_timer.stop()
            self._update_control_buttons("")

    def _update_control_buttons(self, state: str):
        is_printing = state == "printing"
        is_paused = state == "paused"
        self.pause_btn.setEnabled(is_printing)
        self.resume_btn.setEnabled(is_paused)
        self.cancel_btn.setEnabled(is_printing or is_paused)

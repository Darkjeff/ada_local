"""
Printers tab — Creality K1 status and control via Klipper/SSH.
"""

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QFrame,
    QLineEdit, QPushButton, QProgressBar,
)
from PySide6.QtCore import Qt, Signal, QThread, QTimer
from qfluentwidgets import TitleLabel, BodyLabel, ToolButton, FluentIcon as FIF

from core.k1_control import k1_manager
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
            self.result.emit(k1_manager.connect())
        except Exception:
            self.result.emit(False)


class StatusFetchThread(QThread):
    status_found = Signal(dict)

    def run(self):
        try:
            self.status_found.emit(k1_manager.get_status())
        except Exception:
            self.status_found.emit({})


class PrintActionThread(QThread):
    finished = Signal(bool)

    def __init__(self, action: str):
        super().__init__()
        self.action = action

    def run(self):
        try:
            if self.action == "pause":
                ok = k1_manager.pause_print()
            elif self.action == "resume":
                ok = k1_manager.resume_print()
            elif self.action == "cancel":
                ok = k1_manager.cancel_print()
            else:
                ok = False
            self.finished.emit(ok)
        except Exception:
            self.finished.emit(False)


# ── Status card ──────────────────────────────────────────────────────── #

class K1StatusCard(QFrame):
    """Displays K1 printer state, progress and temperatures."""

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
        self.state_label.setStyleSheet(
            "color: #6e7a8e; font-size: 16px; font-weight: bold;"
        )
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

        # Temperatures
        temp_row = QHBoxLayout()
        temp_row.setSpacing(40)

        nozzle_col = QVBoxLayout()
        nozzle_col.setSpacing(4)
        nozzle_title = QLabel("NOZZLE")
        nozzle_title.setStyleSheet(
            "color: #6e7a8e; font-size: 11px; font-weight: bold;"
        )
        self.nozzle_label = QLabel("-- °C / -- °C")
        self.nozzle_label.setStyleSheet(
            "color: white; font-size: 22px; font-weight: bold;"
        )
        nozzle_col.addWidget(nozzle_title)
        nozzle_col.addWidget(self.nozzle_label)
        temp_row.addLayout(nozzle_col)

        bed_col = QVBoxLayout()
        bed_col.setSpacing(4)
        bed_title = QLabel("BED")
        bed_title.setStyleSheet(
            "color: #6e7a8e; font-size: 11px; font-weight: bold;"
        )
        self.bed_label = QLabel("-- °C / -- °C")
        self.bed_label.setStyleSheet(
            "color: white; font-size: 22px; font-weight: bold;"
        )
        bed_col.addWidget(bed_title)
        bed_col.addWidget(self.bed_label)
        temp_row.addLayout(bed_col)

        temp_row.addStretch()
        layout.addLayout(temp_row)

    def update_status(self, status: dict):
        if not status:
            self.state_label.setText("● No data")
            self.state_label.setStyleSheet(
                "color: #6e7a8e; font-size: 16px; font-weight: bold;"
            )
            return

        state = status.get("state", "unknown")
        color = {
            "printing": "#4CAF50",
            "paused":   "#FFC107",
            "error":    "#f44336",
        }.get(state, "#6e7a8e")

        self.state_label.setText(f"● {state.capitalize()}")
        self.state_label.setStyleSheet(
            f"color: {color}; font-size: 16px; font-weight: bold;"
        )

        filename = status.get("filename", "")
        self.filename_label.setText(
            filename[:40] + "…" if len(filename) > 40 else filename
        )

        progress_pct = int(status.get("progress", 0.0) * 100)
        self.progress_bar.setValue(progress_pct)

        n_t = status.get("nozzle_temp", 0.0)
        n_g = status.get("nozzle_target", 0.0)
        self.nozzle_label.setText(f"{n_t:.0f} °C / {n_g:.0f} °C")

        b_t = status.get("bed_temp", 0.0)
        b_g = status.get("bed_target", 0.0)
        self.bed_label.setText(f"{b_t:.0f} °C / {b_g:.0f} °C")


# ── Main tab ─────────────────────────────────────────────────────────── #

class PrintersTab(QWidget):
    """Creality K1 printer dashboard."""

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

        self._update_ui_connected(k1_manager.is_connected)
        if k1_manager.is_connected:
            self._fetch_status()

    # ── Header ──────────────────────────────────────────────────────── #

    def _setup_header(self, parent_layout):
        header = QHBoxLayout()

        text_col = QVBoxLayout()
        title = TitleLabel("Printers", self)
        title.setStyleSheet("font-size: 28px; font-weight: bold; color: white;")
        sub = BodyLabel("Creality K1 — Klipper control interface.", self)
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

        ip_col = QVBoxLayout()
        ip_col.setSpacing(6)
        ip_label = QLabel("IP Address")
        ip_label.setStyleSheet("color: #6e7a8e; font-size: 12px; font-weight: bold;")
        self.ip_input = QLineEdit()
        self.ip_input.setPlaceholderText("e.g. 192.168.1.100")
        self.ip_input.setText(settings.get("k1.ip", ""))
        self.ip_input.setStyleSheet(_INPUT_STYLE)
        self.ip_input.setMinimumWidth(200)
        ip_col.addWidget(ip_label)
        ip_col.addWidget(self.ip_input)
        playout.addLayout(ip_col)

        pw_col = QVBoxLayout()
        pw_col.setSpacing(6)
        pw_label = QLabel("SSH Password")
        pw_label.setStyleSheet("color: #6e7a8e; font-size: 12px; font-weight: bold;")
        self.pw_input = QLineEdit()
        self.pw_input.setEchoMode(QLineEdit.Password)
        self.pw_input.setPlaceholderText("root password")
        self.pw_input.setText(settings.get("k1.password", ""))
        self.pw_input.setStyleSheet(_INPUT_STYLE)
        self.pw_input.setMinimumWidth(200)
        pw_col.addWidget(pw_label)
        pw_col.addWidget(self.pw_input)
        playout.addLayout(pw_col)

        playout.addStretch()

        btn_col = QVBoxLayout()
        btn_col.addStretch()
        self.connect_btn = QPushButton("Connect")
        self.connect_btn.setStyleSheet(_BTN_PRIMARY)
        self.connect_btn.setFixedWidth(120)
        self.connect_btn.clicked.connect(self._on_connect)
        btn_col.addWidget(self.connect_btn)
        playout.addLayout(btn_col)

        parent_layout.addWidget(panel)

    # ── Status card ──────────────────────────────────────────────────── #

    def _setup_status_card(self, parent_layout):
        self.status_card = K1StatusCard(self)
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
        ip = self.ip_input.text().strip()
        pw = self.pw_input.text()
        settings.set("k1.ip", ip)
        settings.set("k1.password", pw)
        k1_manager.reload_config()

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

    def _fetch_status(self):
        if not k1_manager.is_connected:
            return
        self._fetch_thread = StatusFetchThread()
        self._fetch_thread.status_found.connect(self._on_status)
        self._fetch_thread.start()

    def _on_status(self, status: dict):
        self.status_card.update_status(status)
        state = status.get("state", "")
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

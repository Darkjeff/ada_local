"""
Infrastructure Tab — Services status, n8n workflows, Docker containers.

Polls every 30 s via background QThread.
Never raises: all network/subprocess calls are guarded.
"""

import subprocess
from pathlib import Path

import requests
from PySide6.QtCore import Qt, QThread, QObject, Signal, QTimer
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QFrame, QScrollArea,
)
from qfluentwidgets import PushButton, FluentIcon as FIF

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

WORKFLOWS_DIR = Path(__file__).parent.parent.parent / "workflows"

# Known workflows: webhook-action → display metadata
_WORKFLOW_META: dict[str, dict] = {
    "shell-exec":      {"label": "Shell Execute",   "icon": "⚙️",  "desc": "Commandes système"},
    "weather":         {"label": "Météo",            "icon": "🌦️",  "desc": "OpenMeteo API"},
    "web-search":      {"label": "Recherche Web",    "icon": "🔍",  "desc": "Brave Search"},
    "set-timer":       {"label": "Timer",            "icon": "⏰",  "desc": "Minuterie"},
    "set-alarm":       {"label": "Alarme",           "icon": "🔔",  "desc": "Programmation d'alarme"},
    "control-light":   {"label": "Lumières",         "icon": "💡",  "desc": "Domotique HA / Kasa"},
    "calendar-event":  {"label": "Calendrier",       "icon": "📅",  "desc": "Événements Google Calendar"},
}

# ---------------------------------------------------------------------------
# Background worker
# ---------------------------------------------------------------------------

class InfraWorker(QObject):
    """Collects service statuses in a background thread. Never raises."""

    updated = Signal(dict)

    def collect(self) -> None:
        result: dict = {
            "n8n": None,
            "ollama": None,
            "docker_containers": [],
            "workflows": [],
        }

        # --- n8n health -------------------------------------------------
        try:
            from core.settings_store import settings as app_settings
            n8n_url = (app_settings.get("n8n") or {}).get("url", "http://localhost:5678")
            r = requests.get(f"{n8n_url.rstrip('/')}/healthz", timeout=2)
            result["n8n"] = r.status_code == 200
        except Exception:
            result["n8n"] = False

        # --- Ollama health ----------------------------------------------
        try:
            from config import OLLAMA_URL
            r = requests.get(f"{OLLAMA_URL.rstrip('/')}/tags", timeout=2)
            result["ollama"] = r.status_code == 200
        except Exception:
            result["ollama"] = False

        # --- Docker containers -----------------------------------------
        try:
            out = subprocess.check_output(
                ["docker", "ps", "--format", "{{.Names}}|{{.Status}}|{{.Image}}"],
                timeout=5,
                stderr=subprocess.DEVNULL,
            )
            for line in out.decode().strip().splitlines():
                parts = line.split("|")
                if len(parts) >= 2:
                    result["docker_containers"].append({
                        "name":   parts[0],
                        "status": parts[1],
                        "image":  parts[2] if len(parts) > 2 else "",
                    })
        except Exception:
            pass

        # --- Local workflow JSON files ---------------------------------
        if WORKFLOWS_DIR.exists():
            exported = {p.stem for p in WORKFLOWS_DIR.glob("*.json")}
            for action in _WORKFLOW_META:
                result["workflows"].append({
                    "action":   action,
                    "exported": action in exported,
                })
        else:
            for action in _WORKFLOW_META:
                result["workflows"].append({"action": action, "exported": False})

        self.updated.emit(result)


# ---------------------------------------------------------------------------
# Small UI helpers
# ---------------------------------------------------------------------------

def _section_title(text: str) -> QLabel:
    lbl = QLabel(text)
    lbl.setStyleSheet(
        "color: #8b9bb4; font-size: 11px; font-weight: bold; "
        "letter-spacing: 1px; padding: 2px 0;"
    )
    return lbl


def _card() -> QFrame:
    f = QFrame()
    f.setStyleSheet(
        "QFrame { background: #0f1524; border: 1px solid #1a2236; border-radius: 10px; }"
    )
    return f


class _StatusRow(QFrame):
    """Single service row: coloured dot + name + status text."""

    def __init__(self, name: str, parent=None):
        super().__init__(parent)
        self.setStyleSheet("QFrame { background: transparent; border: none; }")
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 3, 0, 3)
        lay.setSpacing(8)

        self._dot = QLabel("●")
        self._dot.setFixedWidth(14)
        self._dot.setStyleSheet("color: #555; font-size: 13px;")
        lay.addWidget(self._dot)

        lbl = QLabel(name)
        lbl.setStyleSheet("color: #d0d0d0; font-size: 13px;")
        lay.addWidget(lbl)
        lay.addStretch()

        self._status = QLabel("…")
        self._status.setStyleSheet("color: #666; font-size: 12px;")
        lay.addWidget(self._status)

    def set_status(self, ok: bool | None) -> None:
        if ok is True:
            self._dot.setStyleSheet("color: #4caf50; font-size: 13px;")
            self._status.setText("En ligne")
            self._status.setStyleSheet("color: #4caf50; font-size: 12px;")
        elif ok is False:
            self._dot.setStyleSheet("color: #f44336; font-size: 13px;")
            self._status.setText("Hors ligne")
            self._status.setStyleSheet("color: #f44336; font-size: 12px;")
        else:
            self._dot.setStyleSheet("color: #555; font-size: 13px;")
            self._status.setText("Inconnu")
            self._status.setStyleSheet("color: #666; font-size: 12px;")


class _WorkflowRow(QFrame):
    """Workflow row: icon + label/desc + JSON badge."""

    def __init__(self, action: str, exported: bool, parent=None):
        super().__init__(parent)
        self.setStyleSheet("QFrame { background: transparent; border: none; }")
        meta = _WORKFLOW_META.get(action, {"label": action, "icon": "🔧", "desc": ""})

        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 4, 0, 4)
        lay.setSpacing(10)

        icon = QLabel(meta["icon"])
        icon.setFixedWidth(24)
        icon.setStyleSheet("font-size: 16px; background: transparent; border: none;")
        lay.addWidget(icon)

        text_lay = QVBoxLayout()
        text_lay.setSpacing(1)
        label = QLabel(meta["label"])
        label.setStyleSheet(
            "color: #d0d0d0; font-size: 13px; font-weight: bold; "
            "background: transparent; border: none;"
        )
        desc = QLabel(meta.get("desc", ""))
        desc.setStyleSheet("color: #666; font-size: 11px; background: transparent; border: none;")
        text_lay.addWidget(label)
        text_lay.addWidget(desc)
        lay.addLayout(text_lay)
        lay.addStretch()

        badge = QLabel("✓ JSON" if exported else "À exporter")
        badge.setStyleSheet(
            f"color: {'#4caf50' if exported else '#555'}; font-size: 11px; "
            "background: transparent; border: none;"
        )
        lay.addWidget(badge)


class _DockerRow(QFrame):
    """One container: green dot + name + status."""

    def __init__(self, container: dict, parent=None):
        super().__init__(parent)
        self.setStyleSheet("QFrame { background: transparent; border: none; }")
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 3, 0, 3)
        lay.setSpacing(8)

        dot = QLabel("●")
        dot.setFixedWidth(14)
        dot.setStyleSheet("color: #4caf50; font-size: 12px;")
        lay.addWidget(dot)

        name_lbl = QLabel(container["name"])
        name_lbl.setStyleSheet("color: #d0d0d0; font-size: 13px;")
        lay.addWidget(name_lbl)
        lay.addStretch()

        # Trim verbose status ("Up 2 hours" → keep as-is, "Up X days" OK)
        status_txt = container["status"][:35]
        status_lbl = QLabel(status_txt)
        status_lbl.setStyleSheet("color: #666; font-size: 11px;")
        lay.addWidget(status_lbl)


# ---------------------------------------------------------------------------
# Infrastructure tab
# ---------------------------------------------------------------------------

class InfrastructureTab(QWidget):
    """
    Infrastructure tab.
    Shows: n8n + Ollama status / running Docker containers / local workflow catalogue.
    Auto-refreshes every 30 s.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("InfrastructureTab")
        self._worker: InfraWorker | None = None
        self._thread: QThread | None = None
        self._setup_ui()

        self._timer = QTimer(self)
        self._timer.timeout.connect(self._refresh)
        self._timer.start(30_000)
        self._refresh()

    # ── UI setup ─────────────────────────────────────────────────────────────

    def _setup_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(20, 16, 20, 16)
        root.setSpacing(16)

        # Toolbar
        toolbar = QHBoxLayout()
        title = QLabel("Infrastructure")
        title.setStyleSheet("font-size: 18px; font-weight: bold; color: #e0e0e0;")
        toolbar.addWidget(title)
        toolbar.addStretch()
        self._refresh_btn = PushButton(FIF.SYNC, "Actualiser")
        self._refresh_btn.clicked.connect(self._refresh)
        toolbar.addWidget(self._refresh_btn)
        root.addLayout(toolbar)

        # Two-column body
        columns = QHBoxLayout()
        columns.setSpacing(16)
        columns.addLayout(self._build_left(), 1)
        columns.addLayout(self._build_right(), 1)
        root.addLayout(columns)
        root.addStretch()

    def _build_left(self) -> QVBoxLayout:
        lay = QVBoxLayout()
        lay.setSpacing(12)

        # Services card
        svc = _card()
        svc_lay = QVBoxLayout(svc)
        svc_lay.setContentsMargins(14, 12, 14, 12)
        svc_lay.setSpacing(0)
        svc_lay.addWidget(_section_title("SERVICES"))
        self._row_n8n    = _StatusRow("n8n")
        self._row_ollama = _StatusRow("Ollama")
        svc_lay.addWidget(self._row_n8n)
        svc_lay.addWidget(self._row_ollama)
        lay.addWidget(svc)

        # Docker card
        docker = _card()
        self._docker_lay = QVBoxLayout(docker)
        self._docker_lay.setContentsMargins(14, 12, 14, 12)
        self._docker_lay.setSpacing(0)
        self._docker_lay.addWidget(_section_title("DOCKER"))
        lay.addWidget(docker)

        lay.addStretch()
        return lay

    def _build_right(self) -> QVBoxLayout:
        lay = QVBoxLayout()
        lay.setSpacing(12)

        # Workflows card
        wf = _card()
        self._wf_lay = QVBoxLayout(wf)
        self._wf_lay.setContentsMargins(14, 12, 14, 12)
        self._wf_lay.setSpacing(0)
        self._wf_lay.addWidget(_section_title("WORKFLOWS N8N"))
        lay.addWidget(wf)

        lay.addStretch()
        return lay

    # ── Data refresh ──────────────────────────────────────────────────────────

    def _refresh(self) -> None:
        self._refresh_btn.setEnabled(False)
        self._thread = QThread()
        self._worker = InfraWorker()
        self._worker.moveToThread(self._thread)
        self._thread.started.connect(self._worker.collect)
        self._worker.updated.connect(self._on_updated)
        self._worker.updated.connect(self._thread.quit)
        self._thread.finished.connect(self._thread.deleteLater)
        self._thread.start()

    def _on_updated(self, data: dict) -> None:
        self._refresh_btn.setEnabled(True)

        # Services
        self._row_n8n.set_status(data.get("n8n"))
        self._row_ollama.set_status(data.get("ollama"))

        # Docker — rebuild rows
        self._clear_after_title(self._docker_lay)
        containers = data.get("docker_containers", [])
        if containers:
            for c in containers:
                self._docker_lay.addWidget(_DockerRow(c))
        else:
            self._docker_lay.addWidget(self._empty_lbl("Aucun container actif"))

        # Workflows — rebuild rows
        self._clear_after_title(self._wf_lay)
        for wf in data.get("workflows", []):
            self._wf_lay.addWidget(_WorkflowRow(wf["action"], wf["exported"]))

    # ── Helpers ──────────────────────────────────────────────────────────────

    @staticmethod
    def _clear_after_title(layout: QVBoxLayout) -> None:
        """Remove all widgets after the first one (the section title)."""
        while layout.count() > 1:
            item = layout.takeAt(1)
            if item.widget():
                item.widget().deleteLater()

    @staticmethod
    def _empty_lbl(text: str) -> QLabel:
        lbl = QLabel(text)
        lbl.setStyleSheet("color: #444; font-size: 12px; padding: 4px 0;")
        return lbl

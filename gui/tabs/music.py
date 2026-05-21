"""
Music Tab — Navidrome control panel (no WebEngine, RDP-safe).

Shows library stats from the Navidrome API and opens the player
in the system browser via QDesktopServices.
"""

import requests
from PySide6.QtCore import Qt, QUrl, QObject, Signal, QThread
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QFrame, QSizePolicy, QLineEdit,
)
from qfluentwidgets import (
    PushButton, PrimaryPushButton, FluentIcon as FIF, TitleLabel, BodyLabel,
    SettingCardGroup, SettingCard,
)
from core.i18n import tr
from core.settings_store import settings

NAVIDROME_URL = "http://localhost:4533"
# Navidrome REST API — no auth needed for /api/ping and /api/getArtists.view
_PING_URL   = f"{NAVIDROME_URL}/api/ping"


# ---------------------------------------------------------------------------
# Background worker — fetch Navidrome stats via Subsonic API
# ---------------------------------------------------------------------------

class NaviWorker(QObject):
    done = Signal(dict)

    def __init__(self, user: str, password: str):
        super().__init__()
        self._user = user
        self._password = password

    def fetch(self) -> None:
        result = {"online": False, "artists": "—", "albums": "—", "songs": "—"}
        try:
            params = {
                "u": self._user,
                "p": self._password,
                "v": "1.16.1",
                "c": "ADA",
                "f": "json",
            }
            r = requests.get(
                f"{NAVIDROME_URL}/rest/getArtists",
                params=params,
                timeout=3,
            )
            if r.status_code == 200:
                data = r.json().get("subsonic-response", {})
                if data.get("status") == "ok":
                    result["online"] = True
                    artists = data.get("artists", {}).get("index", [])
                    count = sum(len(idx.get("artist", [])) for idx in artists)
                    result["artists"] = str(count)
        except Exception:
            pass

        # Album + song counts via getScanStatus
        try:
            params = {
                "u": self._user,
                "p": self._password,
                "v": "1.16.1",
                "c": "ADA",
                "f": "json",
            }
            r = requests.get(
                f"{NAVIDROME_URL}/rest/getScanStatus",
                params=params,
                timeout=3,
            )
            if r.status_code == 200:
                data = r.json().get("subsonic-response", {})
                scan = data.get("scanStatus", {})
                result["songs"]  = str(scan.get("count", "—"))
        except Exception:
            pass

        self.done.emit(result)


# ---------------------------------------------------------------------------
# Stat card
# ---------------------------------------------------------------------------

class _StatCard(QFrame):
    def __init__(self, icon: str, label: str, parent=None):
        super().__init__(parent)
        self.setFixedSize(130, 80)
        self.setStyleSheet(
            "QFrame { background: #0f1524; border: 1px solid #1a2236; border-radius: 10px; }"
        )
        lay = QVBoxLayout(self)
        lay.setContentsMargins(12, 8, 12, 8)
        lay.setSpacing(2)
        lay.setAlignment(Qt.AlignCenter)

        icon_lbl = QLabel(icon)
        icon_lbl.setAlignment(Qt.AlignCenter)
        icon_lbl.setStyleSheet("font-size: 20px; background: transparent; border: none;")
        lay.addWidget(icon_lbl)

        self._value = QLabel("…")
        self._value.setAlignment(Qt.AlignCenter)
        self._value.setStyleSheet(
            "color: #33b5e5; font-size: 18px; font-weight: bold; background: transparent; border: none;"
        )
        lay.addWidget(self._value)

        lbl = QLabel(label)
        lbl.setAlignment(Qt.AlignCenter)
        lbl.setStyleSheet("color: #666; font-size: 11px; background: transparent; border: none;")
        lay.addWidget(lbl)

    def set_value(self, v: str) -> None:
        self._value.setText(v)


# ---------------------------------------------------------------------------
# Default player setting card
# ---------------------------------------------------------------------------

class _PlayerLineCard(SettingCard):
    """Editable card for the default HA media_player entity_id."""

    def __init__(self, parent=None):
        super().__init__(
            FIF.SPEAKERS,
            tr("music.default_player"),
            tr("music.default_player_desc"),
            parent,
        )
        self._edit = QLineEdit(settings.get("music.default_player", ""), self)
        self._edit.setPlaceholderText("media_player.chillout_area")
        self._edit.setMinimumWidth(280)
        self._edit.textChanged.connect(lambda v: settings.set("music.default_player", v.strip()))
        self.hBoxLayout.addWidget(self._edit, 0, Qt.AlignRight)
        self.hBoxLayout.addSpacing(16)

    def retranslate(self):
        self.titleLabel.setText(tr("music.default_player"))
        self.contentLabel.setText(tr("music.default_player_desc"))


# ---------------------------------------------------------------------------
# Music tab
# ---------------------------------------------------------------------------

class MusicTab(QWidget):
    """Navidrome control panel — opens player in system browser."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("musicInterface")
        self._thread: QThread | None = None
        self._worker: NaviWorker | None = None
        self._setup_ui()
        self._refresh()

    def _setup_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(20, 20, 20, 20)
        root.setSpacing(20)
        root.setAlignment(Qt.AlignTop)

        # Header
        header = QHBoxLayout()
        title = QLabel("🎵  Musique")
        title.setStyleSheet("font-size: 22px; font-weight: bold; color: #e0e0e0;")
        header.addWidget(title)
        header.addStretch()
        self._status_dot = QLabel("●")
        self._status_dot.setStyleSheet("color: #555; font-size: 16px;")
        self._status_lbl = QLabel("Vérification…")
        self._status_lbl.setStyleSheet("color: #666; font-size: 13px;")
        header.addWidget(self._status_dot)
        header.addWidget(self._status_lbl)
        root.addLayout(header)

        # Stats row
        stats_row = QHBoxLayout()
        stats_row.setSpacing(12)
        self._card_artists = _StatCard("🎤", "Artistes")
        self._card_songs   = _StatCard("🎵", "Titres")
        stats_row.addWidget(self._card_artists)
        stats_row.addWidget(self._card_songs)
        stats_row.addStretch()
        root.addLayout(stats_row)

        # Separator
        sep = QFrame()
        sep.setFrameShape(QFrame.HLine)
        sep.setStyleSheet("color: #1a2236;")
        root.addWidget(sep)

        # Open button — big and obvious
        open_btn = PrimaryPushButton(FIF.LINK, "Ouvrir Navidrome dans le navigateur")
        open_btn.setFixedHeight(44)
        open_btn.clicked.connect(self._open_browser)
        root.addWidget(open_btn)

        url_lbl = QLabel(NAVIDROME_URL)
        url_lbl.setAlignment(Qt.AlignCenter)
        url_lbl.setStyleSheet("color: #444; font-size: 11px;")
        root.addWidget(url_lbl)

        # Refresh button (small, below)
        refresh_btn = PushButton(FIF.SYNC, "Actualiser le statut")
        refresh_btn.clicked.connect(self._refresh)
        root.addWidget(refresh_btn, alignment=Qt.AlignLeft)

        # Credentials hint
        hint = QLabel("💡 Identifiant par défaut : admin / (mot de passe créé à la 1ère connexion)")
        hint.setStyleSheet("color: #3a4a5a; font-size: 11px; padding-top: 10px;")
        root.addWidget(hint)

        # Default HA media_player setting
        self._player_group = SettingCardGroup(tr("music.default_player"), self)
        self._player_card = _PlayerLineCard(self._player_group)
        self._player_group.addSettingCard(self._player_card)
        root.addWidget(self._player_group)

    # ── Actions ──────────────────────────────────────────────────────────────

    def _open_browser(self) -> None:
        QDesktopServices.openUrl(QUrl(NAVIDROME_URL))

    def _refresh(self) -> None:
        from core.settings_store import settings as app_settings
        navi = app_settings.get("navidrome") or {}
        user     = navi.get("user", "admin")
        password = navi.get("password", "")

        self._thread = QThread()
        self._worker = NaviWorker(user, password)
        self._worker.moveToThread(self._thread)
        self._thread.started.connect(self._worker.fetch)
        self._worker.done.connect(self._on_done)
        self._worker.done.connect(self._thread.quit)
        self._thread.finished.connect(self._thread.deleteLater)
        self._thread.start()

    def _on_done(self, data: dict) -> None:
        if data["online"]:
            self._status_dot.setStyleSheet("color: #4caf50; font-size: 16px;")
            self._status_lbl.setText("En ligne")
            self._status_lbl.setStyleSheet("color: #4caf50; font-size: 13px;")
        else:
            self._status_dot.setStyleSheet("color: #f44336; font-size: 16px;")
            self._status_lbl.setText("Hors ligne")
            self._status_lbl.setStyleSheet("color: #f44336; font-size: 13px;")

        self._card_artists.set_value(data["artists"])
        self._card_songs.set_value(data["songs"])

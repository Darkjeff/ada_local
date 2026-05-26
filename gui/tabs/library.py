"""
Library Tab — Calibre-Web status panel with stats and quick access.

Shows library stats fetched from the Calibre-Web API and opens the
interface in the system browser.  Configuration (URL / credentials)
is kept in the settings card group at the bottom, matching the Music tab
pattern.
"""

import xml.etree.ElementTree as ET

import requests
from PySide6.QtCore import Qt, QUrl, QObject, Signal, QThread
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QFrame, QLineEdit,
)
from qfluentwidgets import (
    PushButton, PrimaryPushButton, FluentIcon as FIF,
    SettingCardGroup, SettingCard,
)
from core.i18n import tr
from core.settings_store import settings

_OPENSEARCH = "http://a9.com/-/spec/opensearch/1.1/"
_ATOM       = "http://www.w3.org/2005/Atom"


# ---------------------------------------------------------------------------
# Background worker — fetch Calibre-Web stats via OPDS (Basic Auth)
# ---------------------------------------------------------------------------

class CalibreWorker(QObject):
    done = Signal(dict)

    def fetch(self) -> None:
        result = {"online": False, "books": "—", "authors": "—"}
        base = settings.get("calibre.url", "").rstrip("/")
        user = settings.get("calibre.username", "")
        auth = (user, settings.get("calibre.password", ""))

        print(f"[CalibreWorker] base={base!r} user={user!r}")

        if not base:
            print("[CalibreWorker] No base URL configured — aborting")
            self.done.emit(result)
            return

        # ── Book count via /opds/new ──────────────────────────────────────
        try:
            url = f"{base}/opds/new"
            r = requests.get(url, params={"offset": 0}, auth=auth, timeout=5)
            print(f"[CalibreWorker] GET {url} → {r.status_code}")
            if r.status_code == 200:
                xml_root = ET.fromstring(r.content)
                el = xml_root.find(f"{{{_OPENSEARCH}}}totalResults")
                el_text = el.text if el is not None else "N/A"
                print(f"[CalibreWorker] opensearch:totalResults el={el!r} text={el_text!r}")
                if el is not None and el.text:
                    result["online"] = True
                    result["books"] = el.text.strip()
                else:
                    # Dump tag list to see what's actually in the feed
                    tags = [child.tag for child in xml_root]
                    print(f"[CalibreWorker] /opds/new root children: {tags[:10]}")
            else:
                print(f"[CalibreWorker] /opds/new body: {r.text[:200]!r}")
        except Exception as exc:
            print(f"[CalibreWorker] /opds/new exception: {exc}")

        # ── Author count via /opds/authors ────────────────────────────────
        try:
            url = f"{base}/opds/authors"
            r = requests.get(url, auth=auth, timeout=5)
            print(f"[CalibreWorker] GET {url} → {r.status_code}")
            if r.status_code == 200:
                xml_root = ET.fromstring(r.content)
                el = xml_root.find(f"{{{_OPENSEARCH}}}totalResults")
                el_text = el.text if el is not None else "N/A"
                print(f"[CalibreWorker] authors totalResults el={el!r} text={el_text!r}")
                if el is not None and el.text:
                    result["online"] = True
                    result["authors"] = el.text.strip()
                else:
                    entries = xml_root.findall(f"{{{_ATOM}}}entry")
                    print(f"[CalibreWorker] authors entry count on page: {len(entries)}")
                    if entries:
                        result["online"] = True
                        result["authors"] = str(len(entries)) + "+"
            else:
                print(f"[CalibreWorker] /opds/authors body: {r.text[:200]!r}")
        except Exception as exc:
            print(f"[CalibreWorker] /opds/authors exception: {exc}")

        # ── Fallback ping ─────────────────────────────────────────────────
        if not result["online"]:
            try:
                url = f"{base}/opds/"
                r = requests.get(url, auth=auth, timeout=5)
                print(f"[CalibreWorker] GET {url} (fallback) → {r.status_code}")
                result["online"] = r.status_code in (200, 302)
            except Exception as exc:
                print(f"[CalibreWorker] /opds/ fallback exception: {exc}")

        print(f"[CalibreWorker] final result: {result}")
        self.done.emit(result)


# ---------------------------------------------------------------------------
# Stat card  (identical look to music tab's _StatCard)
# ---------------------------------------------------------------------------

class _StatCard(QFrame):
    def __init__(self, icon: str, label: str, parent=None):
        super().__init__(parent)
        self.setFixedSize(130, 80)
        self.setStyleSheet(
            "QFrame { background: #0f1524; border: 1px solid #1a2236;"
            " border-radius: 10px; }"
        )
        lay = QVBoxLayout(self)
        lay.setContentsMargins(12, 8, 12, 8)
        lay.setSpacing(2)
        lay.setAlignment(Qt.AlignCenter)

        icon_lbl = QLabel(icon)
        icon_lbl.setAlignment(Qt.AlignCenter)
        icon_lbl.setStyleSheet(
            "font-size: 20px; background: transparent; border: none;"
        )
        lay.addWidget(icon_lbl)

        self._value = QLabel("…")
        self._value.setAlignment(Qt.AlignCenter)
        self._value.setStyleSheet(
            "color: #33b5e5; font-size: 18px; font-weight: bold;"
            " background: transparent; border: none;"
        )
        lay.addWidget(self._value)

        lbl = QLabel(label)
        lbl.setAlignment(Qt.AlignCenter)
        lbl.setStyleSheet(
            "color: #666; font-size: 11px; background: transparent; border: none;"
        )
        lay.addWidget(lbl)

    def set_value(self, v: str) -> None:
        self._value.setText(v)


# ---------------------------------------------------------------------------
# Editable setting card (reusable)
# ---------------------------------------------------------------------------

class _LineCard(SettingCard):
    def __init__(self, icon, title_key: str, desc_key: str,
                 setting_key: str, placeholder: str = "", masked: bool = False,
                 parent=None):
        super().__init__(icon, tr(title_key), tr(desc_key), parent)
        self._title_key = title_key
        self._desc_key = desc_key

        self._edit = QLineEdit(settings.get(setting_key, ""), self)
        self._edit.setPlaceholderText(placeholder)
        self._edit.setMinimumWidth(280)
        if masked:
            self._edit.setEchoMode(QLineEdit.Password)
        self._edit.textChanged.connect(lambda v: settings.set(setting_key, v.strip()))
        self.hBoxLayout.addWidget(self._edit, 0, Qt.AlignRight)
        self.hBoxLayout.addSpacing(16)

    def retranslate(self):
        self.titleLabel.setText(tr(self._title_key))
        self.contentLabel.setText(tr(self._desc_key))


# ---------------------------------------------------------------------------
# Library tab
# ---------------------------------------------------------------------------

class LibraryTab(QWidget):
    """Calibre-Web status panel — stats, quick-open, and connection settings."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("libraryInterface")
        self._thread: QThread | None = None
        self._worker: CalibreWorker | None = None
        self._setup_ui()
        self._refresh()

    # ── Build UI ─────────────────────────────────────────────────────────────

    def _setup_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(20, 20, 20, 20)
        root.setSpacing(20)
        root.setAlignment(Qt.AlignTop)

        # Header — title + status indicator
        header = QHBoxLayout()
        title = QLabel("📚  Bibliothèque")
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

        # Stats cards
        stats_row = QHBoxLayout()
        stats_row.setSpacing(12)
        self._card_books   = _StatCard("📖", "Livres")
        self._card_authors = _StatCard("✍️", "Auteurs")
        stats_row.addWidget(self._card_books)
        stats_row.addWidget(self._card_authors)
        stats_row.addStretch()
        root.addLayout(stats_row)

        # Separator
        sep = QFrame()
        sep.setFrameShape(QFrame.HLine)
        sep.setStyleSheet("color: #1a2236;")
        root.addWidget(sep)

        # Open button
        open_btn = PrimaryPushButton(FIF.LINK, "Ouvrir Calibre-Web dans le navigateur")
        open_btn.setFixedHeight(44)
        open_btn.clicked.connect(self._open_browser)
        root.addWidget(open_btn)

        self._url_lbl = QLabel(settings.get("calibre.url", ""))
        self._url_lbl.setAlignment(Qt.AlignCenter)
        self._url_lbl.setStyleSheet("color: #444; font-size: 11px;")
        root.addWidget(self._url_lbl)

        # Refresh button
        refresh_btn = PushButton(FIF.SYNC, "Actualiser le statut")
        refresh_btn.clicked.connect(self._refresh)
        root.addWidget(refresh_btn, alignment=Qt.AlignLeft)

        # Connection settings group
        group = SettingCardGroup(tr("library.calibre_group"), self)

        self._url_card = _LineCard(
            FIF.LINK,
            "library.url", "library.url_desc",
            "calibre.url",
            placeholder="http://192.168.1.70:8083",
            parent=group,
        )
        self._url_card._edit.textChanged.connect(self._on_url_changed)
        group.addSettingCard(self._url_card)

        group.addSettingCard(_LineCard(
            FIF.PEOPLE,
            "library.username", "library.username_desc",
            "calibre.username",
            placeholder="admin",
            parent=group,
        ))
        group.addSettingCard(_LineCard(
            FIF.FINGERPRINT,
            "library.password", "library.password_desc",
            "calibre.password",
            placeholder="••••••",
            masked=True,
            parent=group,
        ))

        root.addWidget(group)
        root.addStretch()

    # ── Actions ──────────────────────────────────────────────────────────────

    def _open_browser(self) -> None:
        url = settings.get("calibre.url", "").strip()
        if url:
            QDesktopServices.openUrl(QUrl(url))

    def _on_url_changed(self, value: str) -> None:
        self._url_lbl.setText(value.strip())

    def _refresh(self) -> None:
        self._status_dot.setStyleSheet("color: #555; font-size: 16px;")
        self._status_lbl.setText("Vérification…")
        self._status_lbl.setStyleSheet("color: #666; font-size: 13px;")

        self._thread = QThread()
        self._worker = CalibreWorker()
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

        self._card_books.set_value(data["books"])
        self._card_authors.set_value(data["authors"])

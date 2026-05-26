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
        auth = (
            settings.get("calibre.username", ""),
            settings.get("calibre.password", ""),
        )

        if not base:
            self.done.emit(result)
            return

        # ── Book count via /opds/new pagination ───────────────────────────
        # Calibre-Web OPDS does NOT include opensearch:totalResults.
        # Strategy: page_size = entries on page 1, rel="last" gives last offset
        # → total = last_offset + page_size.
        try:
            r = requests.get(
                f"{base}/opds/new", params={"offset": 0}, auth=auth, timeout=5,
            )
            print(f"[CalibreWorker] GET /opds/new → {r.status_code}")
            if r.status_code == 200:
                result["online"] = True
                xml_root = ET.fromstring(r.content)
                entries = xml_root.findall(f"{{{_ATOM}}}entry")
                page_size = len(entries)
                print(f"[CalibreWorker] /opds/new page_size={page_size}")

                links = {lnk.get("rel"): lnk.get("href", "")
                         for lnk in xml_root.findall(f"{{{_ATOM}}}link")}
                print(f"[CalibreWorker] /opds/new links: {links}")

                last_offset = None
                if "last" in links:
                    import re as _re
                    m = _re.search(r"offset=(\d+)", links["last"])
                    if m:
                        last_offset = int(m.group(1))

                print(f"[CalibreWorker] last_offset={last_offset}")
                if last_offset is not None and page_size:
                    result["books"] = str(last_offset + page_size)
                elif page_size:
                    result["books"] = str(page_size)
                print(f"[CalibreWorker] books={result['books']}")
        except Exception as exc:
            print(f"[CalibreWorker] /opds/new exception: {exc}")

        # ── Author count via OPDS root navigation ─────────────────────────
        # Parse /opds/ root → find "author" entry → follow its link → pagination
        try:
            r = requests.get(f"{base}/opds/", auth=auth, timeout=5)
            print(f"[CalibreWorker] GET /opds/ → {r.status_code}")
            if r.status_code == 200:
                result["online"] = True
                xml_root = ET.fromstring(r.content)
                nav_entries = xml_root.findall(f"{{{_ATOM}}}entry")
                print(f"[CalibreWorker] /opds/ nav entries: "
                      f"{[e.findtext(f'{{{_ATOM}}}title') for e in nav_entries]}")

                author_href = None
                for entry in nav_entries:
                    title_el = entry.find(f"{{{_ATOM}}}title")
                    if title_el is not None and title_el.text:
                        if "author" in title_el.text.lower() or "auteur" in title_el.text.lower():
                            link_el = entry.find(f"{{{_ATOM}}}link")
                            if link_el is not None:
                                author_href = link_el.get("href", "")
                            break
                print(f"[CalibreWorker] author_href={author_href!r}")

                if author_href:
                    if author_href.startswith("/"):
                        author_url = base + author_href.split("?")[0]
                    else:
                        author_url = author_href.split("?")[0]
                    r2 = requests.get(author_url, auth=auth, timeout=5)
                    print(f"[CalibreWorker] GET {author_url} → {r2.status_code}")
                    if r2.status_code == 200:
                        xml2 = ET.fromstring(r2.content)
                        entries2 = xml2.findall(f"{{{_ATOM}}}entry")
                        page2 = len(entries2)
                        links2 = {lnk.get("rel"): lnk.get("href", "")
                                  for lnk in xml2.findall(f"{{{_ATOM}}}link")}
                        print(f"[CalibreWorker] author page entries={page2} links={links2}")
                        last2 = None
                        if "last" in links2:
                            import re as _re
                            m = _re.search(r"offset=(\d+)", links2["last"])
                            if m:
                                last2 = int(m.group(1))
                        if last2 is not None and page2:
                            result["authors"] = str(last2 + page2)
                        elif page2:
                            result["authors"] = str(page2)
                        print(f"[CalibreWorker] authors={result['authors']}")
        except Exception as exc:
            print(f"[CalibreWorker] author count exception: {exc}")

        # ── Fallback online check ─────────────────────────────────────────
        if not result["online"]:
            try:
                r = requests.get(f"{base}/opds/", auth=auth, timeout=5)
                result["online"] = r.status_code in (200, 302)
            except Exception:
                pass

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

"""
Music Tab — Navidrome embedded via QWebEngineView.

Loads the local Navidrome instance (http://localhost:4533) inside ADA.
Falls back to a simple link if WebEngine is unavailable.
"""

from PySide6.QtCore import Qt, QUrl
from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel, QFrame
from qfluentwidgets import PushButton, LineEdit, FluentIcon as FIF

try:
    from PySide6.QtWebEngineWidgets import QWebEngineView
    from PySide6.QtWebEngineCore import QWebEngineSettings
    _WEBENGINE = True
except ImportError:
    _WEBENGINE = False

NAVIDROME_URL = "http://localhost:4533"


class MusicTab(QWidget):
    """Navidrome music player embedded in ADA."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("musicInterface")
        self._setup_ui()

    def _setup_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        if _WEBENGINE:
            self._build_webview(root)
        else:
            self._build_fallback(root)

    # ── WebEngine mode ────────────────────────────────────────────────────────

    def _build_webview(self, root: QVBoxLayout) -> None:
        # Toolbar
        toolbar = QFrame()
        toolbar.setFixedHeight(40)
        toolbar.setStyleSheet(
            "QFrame { background: #0a0f1e; border-bottom: 1px solid #1a2236; }"
        )
        tb_lay = QHBoxLayout(toolbar)
        tb_lay.setContentsMargins(10, 0, 10, 0)
        tb_lay.setSpacing(6)

        back_btn = PushButton(FIF.LEFT_ARROW, "")
        back_btn.setFixedWidth(36)
        back_btn.clicked.connect(lambda: self._view.back())
        tb_lay.addWidget(back_btn)

        fwd_btn = PushButton(FIF.RIGHT_ARROW, "")
        fwd_btn.setFixedWidth(36)
        fwd_btn.clicked.connect(lambda: self._view.forward())
        tb_lay.addWidget(fwd_btn)

        reload_btn = PushButton(FIF.SYNC, "")
        reload_btn.setFixedWidth(36)
        reload_btn.clicked.connect(lambda: self._view.reload())
        tb_lay.addWidget(reload_btn)

        self._url_bar = LineEdit()
        self._url_bar.setText(NAVIDROME_URL)
        self._url_bar.returnPressed.connect(self._on_navigate)
        tb_lay.addWidget(self._url_bar)

        home_btn = PushButton(FIF.MUSIC, "Navidrome")
        home_btn.clicked.connect(self._go_home)
        tb_lay.addWidget(home_btn)

        root.addWidget(toolbar)

        # WebView
        self._view = QWebEngineView()
        settings = self._view.settings()
        settings.setAttribute(QWebEngineSettings.WebAttribute.PlaybackRequiresUserGesture, False)
        settings.setAttribute(QWebEngineSettings.WebAttribute.JavascriptEnabled, True)
        settings.setAttribute(QWebEngineSettings.WebAttribute.LocalStorageEnabled, True)

        self._view.urlChanged.connect(self._on_url_changed)
        self._view.load(QUrl(NAVIDROME_URL))
        root.addWidget(self._view)

    def _on_navigate(self) -> None:
        url = self._url_bar.text().strip()
        if not url.startswith("http"):
            url = "http://" + url
        self._view.load(QUrl(url))

    def _go_home(self) -> None:
        self._view.load(QUrl(NAVIDROME_URL))
        self._url_bar.setText(NAVIDROME_URL)

    def _on_url_changed(self, url: QUrl) -> None:
        self._url_bar.setText(url.toString())

    # ── Fallback mode (no WebEngine) ─────────────────────────────────────────

    def _build_fallback(self, root: QVBoxLayout) -> None:
        root.setContentsMargins(20, 20, 20, 20)
        msg = QLabel(
            f"PySide6-WebEngine non disponible.\n\n"
            f"Ouvre Navidrome dans ton navigateur :\n{NAVIDROME_URL}"
        )
        msg.setStyleSheet("color: #888; font-size: 14px;")
        msg.setAlignment(Qt.AlignCenter)
        root.addWidget(msg)

"""
Library Tab — Calibre-Web connection settings.
"""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QWidget, QVBoxLayout, QLineEdit
from qfluentwidgets import (
    FluentIcon as FIF, SettingCardGroup, SettingCard, TitleLabel,
)
from core.i18n import tr
from core.settings_store import settings


class _LineCard(SettingCard):
    """Generic editable line-edit setting card."""

    def __init__(self, icon, title_key: str, desc_key: str,
                 setting_key: str, placeholder: str = "", masked: bool = False,
                 parent=None):
        super().__init__(icon, tr(title_key), tr(desc_key), parent)
        self._title_key = title_key
        self._desc_key = desc_key
        self._setting_key = setting_key

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


class LibraryTab(QWidget):
    """Calibre-Web connection settings."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("libraryInterface")
        self._setup_ui()

    def _setup_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(20, 20, 20, 20)
        root.setSpacing(20)
        root.setAlignment(Qt.AlignTop)

        root.addWidget(TitleLabel(tr("library.title"), self))

        group = SettingCardGroup(tr("library.calibre_group"), self)

        group.addSettingCard(_LineCard(
            FIF.LINK,
            "library.url", "library.url_desc",
            "calibre.url",
            placeholder="http://192.168.1.70:8083",
            parent=group,
        ))
        group.addSettingCard(_LineCard(
            FIF.PEOPLE,
            "library.username", "library.username_desc",
            "calibre.username",
            placeholder="jeff",
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

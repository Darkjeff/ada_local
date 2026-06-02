"""
# MODULE_SOCIETE: Barre de sélection de contexte société dans le chat.
Affiche des boutons colorés pour chaque société active.
Signal context_changed(company_id) : injecte le contexte dans Mistral.

Guard : importé uniquement si MODULES_ENABLED["societe"] = True.
"""
from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QWidget,
)
from qfluentwidgets import FluentIcon as FIF, TransparentToolButton

from core.societe.company_model import Company, company_model
from core.plugin_registry import plugin_registry


class _CompanyButton(QPushButton):
    """Bouton compact pour une société dans la context bar."""

    def __init__(self, company: Company, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._company = company
        self._active = False
        self.setText(f"{company.logo} {company.name}")
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self._update_style()

    @property
    def company_id(self) -> str:
        return self._company.id

    def set_active(self, active: bool) -> None:
        self._active = active
        self._update_style()

    def _update_style(self) -> None:
        c = self._company.color
        if self._active:
            self.setStyleSheet(f"""
                QPushButton {{
                    background-color: {c};
                    color: #ffffff;
                    border: 1px solid {c};
                    border-radius: 14px;
                    padding: 4px 12px;
                    font-size: 12px;
                    font-weight: 700;
                }}
            """)
        else:
            self.setStyleSheet(f"""
                QPushButton {{
                    background-color: transparent;
                    color: #8b9bb4;
                    border: 1px solid #1a2236;
                    border-radius: 14px;
                    padding: 4px 12px;
                    font-size: 12px;
                    font-weight: 600;
                }}
                QPushButton:hover {{
                    background-color: rgba(94, 106, 210, 0.15);
                    color: {c};
                    border-color: {c};
                }}
            """)


class ChatContextBar(QWidget):
    """
    # MODULE_SOCIETE: Barre de contexte société pour le chat.
    Placée au-dessus du champ de saisie du chat.
    Signal context_changed(company_id : str | "") — "" = aucun contexte société.

    Connexion attendue :
        bar.context_changed.connect(handlers.set_societe_context)
    """

    context_changed = Signal(str)  # company_id ou "" pour réinitialiser

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("ChatContextBar")
        self._buttons: list[_CompanyButton] = []
        self._active_id: str | None = None
        self._build_ui()
        self._load_companies()

    def _build_ui(self) -> None:
        root = QHBoxLayout(self)
        root.setContentsMargins(8, 4, 8, 4)
        root.setSpacing(8)

        prefix = QLabel("Contexte :")
        prefix.setStyleSheet("color: #8b9bb4; font-size: 11px; font-weight: 600;")
        root.addWidget(prefix)

        # Zone scrollable pour les boutons
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setFixedHeight(40)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setStyleSheet("background: transparent; border: none;")

        self._btn_widget = QWidget()
        self._btn_widget.setStyleSheet("background: transparent;")
        self._btn_layout = QHBoxLayout(self._btn_widget)
        self._btn_layout.setContentsMargins(0, 0, 0, 0)
        self._btn_layout.setSpacing(8)

        scroll.setWidget(self._btn_widget)
        root.addWidget(scroll, stretch=1)

        # Bouton reset "Aucun"
        reset_btn = QPushButton("✕ Aucun")
        reset_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        reset_btn.setStyleSheet("""
            QPushButton {
                background-color: transparent;
                color: #8b9bb4;
                border: 1px dashed #2a3550;
                border-radius: 14px;
                padding: 4px 10px;
                font-size: 11px;
            }
            QPushButton:hover {
                color: #e8eaed;
                border-color: #8b9bb4;
            }
        """)
        reset_btn.clicked.connect(self._reset_context)
        root.addWidget(reset_btn)

    def _load_companies(self) -> None:
        """# MODULE_SOCIETE: charge les sociétés actives depuis la DB."""
        for btn in self._buttons:
            btn.deleteLater()
        self._buttons.clear()
        while self._btn_layout.count():
            item = self._btn_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        companies = company_model.list_companies(status="active")
        for company in companies:
            btn = _CompanyButton(company)
            btn.clicked.connect(lambda _=False, cid=company.id: self._select_company(cid))
            self._buttons.append(btn)
            self._btn_layout.addWidget(btn)

        self._btn_layout.addStretch()

    def _select_company(self, company_id: str) -> None:
        """# MODULE_SOCIETE: active le contexte d'une société."""
        if self._active_id == company_id:
            # Désélectionner si re-clic
            self._reset_context()
            return

        self._active_id = company_id
        for btn in self._buttons:
            btn.set_active(btn.company_id == company_id)

        self.context_changed.emit(company_id)

    def _reset_context(self) -> None:
        """# MODULE_SOCIETE: supprime le contexte société du chat."""
        self._active_id = None
        for btn in self._buttons:
            btn.set_active(False)
        self.context_changed.emit("")

    def get_current_company_id(self) -> str | None:
        """Retourne l'id de la société active, ou None."""
        return self._active_id

    def get_current_context_prompt(self) -> str:
        """
        # MODULE_SOCIETE: retourne le bloc de contexte à injecter dans Mistral.
        Délègue au SocietePlugin si disponible.
        """
        plugin = plugin_registry.get("societe")
        if plugin:
            return plugin.get_chat_context(self._active_id)
        return ""

    def get_current_quick_prompts(self) -> list[str]:
        """# MODULE_SOCIETE: retourne les quick-prompts de la société active."""
        plugin = plugin_registry.get("societe")
        if plugin:
            return plugin.get_quick_prompts(self._active_id)
        return []

    def refresh(self) -> None:
        """Recharge les sociétés (à appeler après ajout/suppression d'une société)."""
        active = self._active_id
        self._load_companies()
        if active:
            self._select_company(active)

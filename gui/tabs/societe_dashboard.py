"""
# MODULE_SOCIETE: Dashboard principal — Grille des cards sociétés.
Affiche toutes les sociétés actives sous forme de cards avec métriques,
indicateurs et alertes croisées.

Guard : importé uniquement si MODULES_ENABLED["societe"] = True.
"""
from __future__ import annotations

from PySide6.QtCore import Qt, Signal, QTimer
from PySide6.QtGui import QColor, QFont
from PySide6.QtWidgets import (
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)
from qfluentwidgets import (
    BodyLabel,
    CardWidget,
    FluentIcon as FIF,
    PrimaryPushButton,
    ScrollArea,
    StrongBodyLabel,
    TitleLabel,
    TransparentToolButton,
)

# MODULE_SOCIETE: guard import modèle
from core.societe.company_model import Company, company_model


# MODULE_SOCIETE: palette badges forme juridique ──────────────────────────────

_TYPE_BADGE: dict[str, tuple[str, str]] = {
    "SARL":    ("#5E6AD2", "#e0e7ff"),  # indigo
    "SAS":     ("#2563EB", "#dbeafe"),  # blue
    "EI":      ("#16A349", "#d1fae5"),  # green
    "SCI":     ("#E86C3A", "#ffedd5"),  # orange
    "Holding": ("#7C3AED", "#ede9fe"),  # violet
    "Autre":   ("#4b5563", "#f3f4f6"),  # grey
}


def _badge_style(company_type: str) -> str:
    bg, fg = _TYPE_BADGE.get(company_type, ("#4b5563", "#f3f4f6"))
    return (
        f"background-color: {bg}; color: {fg}; "
        f"padding: 2px 8px; border-radius: 8px; "
        f"font-size: 11px; font-weight: 600;"
    )


def _metric_color(key: str, value: float) -> str:
    if key == "unpaid" and value > 0:
        return "#ef4444"  # rouge
    if key == "open_tickets" and value > 0:
        return "#f59e0b"  # orange
    return "#e8eaed"


# ── CompanyCard ───────────────────────────────────────────────────────────────

class CompanyCard(QFrame):
    """
    # MODULE_SOCIETE: Carte d'une société dans le dashboard.
    Affiche : logo + nom, badge type, métriques clés, alertes.
    Signal : clicked(company_id) pour ouvrir la vue détail.
    """

    clicked = Signal(str)  # company_id

    def __init__(self, company: Company, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._company = company
        self._build_ui()
        self._load_metrics()

    def _build_ui(self) -> None:
        self.setObjectName("CompanyCard")
        self.setFixedHeight(200)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        c = self._company
        self.setStyleSheet(f"""
            QFrame#CompanyCard {{
                background-color: #0f1524;
                border: 1px solid #1a2236;
                border-left: 4px solid {c.color};
                border-radius: 12px;
            }}
            QFrame#CompanyCard:hover {{
                border-color: {c.color};
                background-color: #131e35;
            }}
        """)

        root = QVBoxLayout(self)
        root.setContentsMargins(16, 14, 16, 14)
        root.setSpacing(10)

        # ── Header : logo + nom + badge ──
        header = QHBoxLayout()
        header.setSpacing(10)

        logo = QLabel(c.logo)
        logo.setStyleSheet("font-size: 24px;")
        logo.setFixedWidth(36)
        header.addWidget(logo)

        name_col = QVBoxLayout()
        name_col.setSpacing(2)
        name_lbl = QLabel(c.name)
        name_lbl.setStyleSheet(
            "color: #e8eaed; font-size: 15px; font-weight: 700; font-family: 'Segoe UI';"
        )
        badge = QLabel(c.type.capitalize())
        badge.setStyleSheet(_badge_style(c.type))
        badge.setFixedWidth(80)
        name_col.addWidget(name_lbl)
        name_col.addWidget(badge)
        header.addLayout(name_col)
        header.addStretch()

        root.addLayout(header)

        # ── Séparateur ──
        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setStyleSheet("color: #1a2236;")
        root.addWidget(sep)

        # ── Métriques ──
        self._metrics_row = QHBoxLayout()
        self._metrics_row.setSpacing(12)
        root.addLayout(self._metrics_row)

        # ── Alertes ──
        self._alert_label = QLabel()
        self._alert_label.setStyleSheet("color: #ef4444; font-size: 12px;")
        self._alert_label.setWordWrap(True)
        self._alert_label.hide()
        root.addWidget(self._alert_label)

        root.addStretch()

    def _load_metrics(self) -> None:
        metrics = company_model.get_metrics(self._company.id)
        self._refresh_metrics(metrics)

    def _refresh_metrics(self, metrics: dict[str, float]) -> None:
        # Vider l'ancien contenu
        while self._metrics_row.count():
            item = self._metrics_row.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        labels = {
            "ca_ytd": ("CA", "€"),
            "unpaid": ("Impayés", "€"),
            "open_tickets": ("Tickets", ""),
            "quotes_pending": ("Devis", ""),
        }
        alerts = []

        for key, (label, unit) in labels.items():
            val = metrics.get(key, 0)
            color = _metric_color(key, val)

            if val > 0 and key == "unpaid":
                alerts.append(f"⚠ Impayés : {val:,.0f} €")
            if val > 0 and key == "open_tickets":
                alerts.append(f"🎫 {int(val)} ticket(s) ouvert(s)")

            block = QVBoxLayout()
            block.setSpacing(2)
            val_str = f"{val:,.0f}{unit}" if unit == "€" else str(int(val))
            val_lbl = QLabel(val_str)
            val_lbl.setStyleSheet(
                f"color: {color}; font-size: 16px; font-weight: 700; font-family: 'Segoe UI';"
            )
            key_lbl = QLabel(label)
            key_lbl.setStyleSheet("color: #8b9bb4; font-size: 11px;")
            block.addWidget(val_lbl)
            block.addWidget(key_lbl)

            wrapper = QWidget()
            wrapper.setLayout(block)
            self._metrics_row.addWidget(wrapper)

        if alerts:
            self._alert_label.setText("  ·  ".join(alerts))
            self._alert_label.show()
        else:
            self._alert_label.hide()

    def mousePressEvent(self, event) -> None:
        self.clicked.emit(self._company.id)
        super().mousePressEvent(event)


# ── CompaniesDashboardTab ─────────────────────────────────────────────────────

class CompaniesDashboardTab(QWidget):
    """
    # MODULE_SOCIETE: Tab principal Sociétés — grille 2 colonnes de CompanyCard.
    Signal : company_selected(company_id) pour ouvrir la vue détail.
    """

    company_selected = Signal(str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("CompaniesDashboardTab")
        self._cards: list[CompanyCard] = []
        self._build_ui()
        self._load_companies()
        # Rafraîchissement auto toutes les 30 s
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._load_companies)
        self._timer.start(30_000)

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(24, 20, 24, 20)
        root.setSpacing(16)

        # ── En-tête ──
        header = QHBoxLayout()
        title = TitleLabel("Sociétés")
        title.setStyleSheet("color: #e8eaed;")
        header.addWidget(title)
        header.addStretch()

        refresh_btn = TransparentToolButton(FIF.SYNC)
        refresh_btn.setToolTip("Actualiser")
        refresh_btn.clicked.connect(self._load_companies)
        header.addWidget(refresh_btn)

        root.addLayout(header)

        # ── Sous-titre alertes croisées ──
        self._summary_label = QLabel()
        self._summary_label.setStyleSheet("color: #8b9bb4; font-size: 13px;")
        root.addWidget(self._summary_label)

        # ── Zone scrollable ──
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setStyleSheet("background: transparent; border: none;")

        self._grid_widget = QWidget()
        self._grid_widget.setStyleSheet("background: transparent;")
        self._grid = QGridLayout(self._grid_widget)
        self._grid.setSpacing(16)
        self._grid.setContentsMargins(0, 0, 0, 0)

        scroll.setWidget(self._grid_widget)
        root.addWidget(scroll, stretch=1)

    def _load_companies(self) -> None:
        """# MODULE_SOCIETE: recharge les sociétés depuis la DB."""
        # Vider la grille
        for card in self._cards:
            card.deleteLater()
        self._cards.clear()
        while self._grid.count():
            item = self._grid.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        companies = company_model.list_companies(status="active")
        total_unpaid = 0.0
        total_tickets = 0

        for i, company in enumerate(companies):
            card = CompanyCard(company)
            card.clicked.connect(self.company_selected)
            self._cards.append(card)
            row, col = divmod(i, 2)
            self._grid.addWidget(card, row, col)

            metrics = company_model.get_metrics(company.id)
            total_unpaid += metrics.get("unpaid", 0)
            total_tickets += int(metrics.get("open_tickets", 0))

        # Résumé alertes croisées
        parts = []
        if total_unpaid > 0:
            parts.append(f"⚠ Total impayés portefeuille : {total_unpaid:,.0f} €")
        if total_tickets > 0:
            parts.append(f"🎫 {total_tickets} ticket(s) ouvert(s) au total")
        if not parts:
            parts = [f"✅ {len(companies)} société(s) active(s) — aucune alerte"]
        self._summary_label.setText("  ·  ".join(parts))

"""
# MODULE_SOCIETE: Vue détail d'une société.
Header + KPI grid + Timeline + Documents, fidèle au HTML de référence
ada-dashboard-societe.html.

Guard : importé uniquement si MODULES_ENABLED["societe"] = True.
"""
from __future__ import annotations

import time
from datetime import datetime

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QFrame,
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
    StrongBodyLabel,
    SubtitleLabel,
    TitleLabel,
    TransparentToolButton,
)

from core.societe.company_model import Company, company_model


# ── Helpers ───────────────────────────────────────────────────────────────────

def _fmt_date(ts: float | None) -> str:
    if not ts:
        return "—"
    try:
        return datetime.fromtimestamp(ts).strftime("%d/%m/%Y")
    except Exception:
        return "—"


def _fmt_eur(val: float | None) -> str:
    if val is None:
        return "—"
    return f"{val:,.0f} €"


_TIMELINE_ICON: dict[str, str] = {
    "invoice": "🧾",
    "meeting": "📅",
    "call":    "📞",
    "note":    "📝",
    "ticket":  "🎫",
    "quote":   "📄",
}

_EVENT_COLOR: dict[str, str] = {
    "invoice": "#16A349",
    "meeting": "#5E6AD2",
    "call":    "#0ea5e9",
    "note":    "#8b9bb4",
    "ticket":  "#f59e0b",
    "quote":   "#E86C3A",
}

_DOC_ICON: dict[str, str] = {
    "invoice":  "🧾",
    "quote":    "📄",
    "contract": "📋",
    "report":   "📊",
    "other":    "📎",
}


# ── KPI Widget ────────────────────────────────────────────────────────────────

class _KpiCard(QFrame):
    """Carte KPI individuelle (valeur + label)."""

    def __init__(self, label: str, value: str, color: str = "#e8eaed") -> None:
        super().__init__()
        self.setObjectName("KpiCard")
        self.setStyleSheet("""
            QFrame#KpiCard {
                background-color: #0f1524;
                border: 1px solid #1a2236;
                border-radius: 10px;
            }
        """)
        self.setMinimumWidth(130)
        self.setFixedHeight(80)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 10, 14, 10)
        layout.setSpacing(4)

        val_lbl = QLabel(value)
        val_lbl.setStyleSheet(
            f"color: {color}; font-size: 20px; font-weight: 700; font-family: 'Segoe UI';"
        )
        key_lbl = QLabel(label)
        key_lbl.setStyleSheet("color: #8b9bb4; font-size: 11px;")
        layout.addWidget(val_lbl)
        layout.addWidget(key_lbl)


# ── Timeline Item ─────────────────────────────────────────────────────────────

class _TimelineItem(QFrame):
    """Un élément de timeline."""

    def __init__(self, event: dict) -> None:
        super().__init__()
        color = _EVENT_COLOR.get(event.get("event_type", ""), "#8b9bb4")
        icon = _TIMELINE_ICON.get(event.get("event_type", ""), "•")

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 4, 0, 4)
        layout.setSpacing(12)

        dot = QLabel(icon)
        dot.setStyleSheet(f"color: {color}; font-size: 16px;")
        dot.setFixedWidth(24)
        layout.addWidget(dot)

        col = QVBoxLayout()
        col.setSpacing(1)
        title_lbl = QLabel(event.get("title", ""))
        title_lbl.setStyleSheet("color: #e8eaed; font-size: 13px; font-weight: 600;")
        date_lbl = QLabel(_fmt_date(event.get("event_date")))
        date_lbl.setStyleSheet("color: #8b9bb4; font-size: 11px;")
        if event.get("description"):
            desc_lbl = QLabel(event["description"])
            desc_lbl.setStyleSheet("color: #8b9bb4; font-size: 12px;")
            desc_lbl.setWordWrap(True)
            col.addWidget(title_lbl)
            col.addWidget(desc_lbl)
        else:
            col.addWidget(title_lbl)
        col.addWidget(date_lbl)
        layout.addLayout(col)

        if event.get("amount"):
            amt_lbl = QLabel(_fmt_eur(event["amount"]))
            amt_lbl.setStyleSheet(f"color: {color}; font-size: 12px; font-weight: 600;")
            amt_lbl.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            layout.addWidget(amt_lbl)
        else:
            layout.addStretch()


# ── Document Item ─────────────────────────────────────────────────────────────

class _DocumentItem(QFrame):
    """Un document dans la liste docs."""

    def __init__(self, doc: dict) -> None:
        super().__init__()
        icon = _DOC_ICON.get(doc.get("doc_type", "other"), "📎")

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 4, 0, 4)
        layout.setSpacing(10)

        icon_lbl = QLabel(icon)
        icon_lbl.setStyleSheet("font-size: 18px;")
        icon_lbl.setFixedWidth(28)
        layout.addWidget(icon_lbl)

        col = QVBoxLayout()
        col.setSpacing(1)
        title_lbl = QLabel(doc.get("title", ""))
        title_lbl.setStyleSheet("color: #e8eaed; font-size: 13px; font-weight: 600;")
        meta = f"{doc.get('doc_type', '').capitalize()}  ·  {_fmt_date(doc.get('doc_date'))}"
        meta_lbl = QLabel(meta)
        meta_lbl.setStyleSheet("color: #8b9bb4; font-size: 11px;")
        col.addWidget(title_lbl)
        col.addWidget(meta_lbl)
        layout.addLayout(col)

        if doc.get("amount"):
            amt_lbl = QLabel(_fmt_eur(doc["amount"]))
            amt_lbl.setStyleSheet("color: #e8eaed; font-size: 12px;")
            amt_lbl.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            layout.addWidget(amt_lbl)
        else:
            layout.addStretch()

        if doc.get("status"):
            status_lbl = QLabel(doc["status"].upper())
            status_lbl.setStyleSheet(
                "color: #16A349; background: #d1fae5; padding: 1px 6px; "
                "border-radius: 6px; font-size: 10px; font-weight: 700;"
            )
            layout.addWidget(status_lbl)


# ── CompanyDetailTab ──────────────────────────────────────────────────────────

class CompanyDetailTab(QWidget):
    """
    # MODULE_SOCIETE: Vue détail d'une société (header, KPIs, timeline, docs).
    Signal : back_requested() pour revenir au dashboard.
    """

    back_requested = Signal()
    context_changed = Signal(str)  # company_id pour le chat context bar

    def __init__(self, company_id: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName(f"societeDetail_{company_id}")
        self._company_id = company_id
        self._company = company_model.get_company(company_id)
        self._build_ui()
        if self._company:
            self._load_data()
            self.context_changed.emit(company_id)

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(24, 16, 24, 20)
        root.setSpacing(0)

        if not self._company:
            root.addWidget(QLabel("Société introuvable."))
            return

        c = self._company

        # ── Bouton retour ──
        back_bar = QHBoxLayout()
        back_btn = TransparentToolButton(FIF.LEFT_ARROW)
        back_btn.setToolTip("Retour au dashboard")
        back_btn.clicked.connect(self.back_requested)
        back_bar.addWidget(back_btn)
        back_bar.addStretch()
        root.addLayout(back_bar)

        # ── Scroll ──
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setStyleSheet("background: transparent; border: none;")

        content = QWidget()
        content.setStyleSheet("background: transparent;")
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(20)

        # ── Header société ──
        header_frame = QFrame()
        header_frame.setStyleSheet(f"""
            QFrame {{
                background-color: #0f1524;
                border: 1px solid #1a2236;
                border-left: 6px solid {c.color};
                border-radius: 12px;
            }}
        """)
        h_layout = QHBoxLayout(header_frame)
        h_layout.setContentsMargins(20, 16, 20, 16)
        h_layout.setSpacing(16)

        logo_lbl = QLabel(c.logo)
        logo_lbl.setStyleSheet("font-size: 36px;")
        h_layout.addWidget(logo_lbl)

        info_col = QVBoxLayout()
        info_col.setSpacing(4)
        name_lbl = QLabel(c.name)
        name_lbl.setStyleSheet(
            "color: #e8eaed; font-size: 22px; font-weight: 700; font-family: 'Segoe UI';"
        )
        info_col.addWidget(name_lbl)
        if c.address:
            addr_lbl = QLabel(f"📍 {c.address}")
            addr_lbl.setStyleSheet("color: #8b9bb4; font-size: 12px;")
            info_col.addWidget(addr_lbl)
        if c.email:
            mail_lbl = QLabel(f"✉ {c.email}")
            mail_lbl.setStyleSheet("color: #8b9bb4; font-size: 12px;")
            info_col.addWidget(mail_lbl)
        h_layout.addLayout(info_col)
        h_layout.addStretch()

        if c.notes:
            notes_lbl = QLabel(c.notes)
            notes_lbl.setStyleSheet("color: #8b9bb4; font-size: 12px; font-style: italic;")
            notes_lbl.setWordWrap(True)
            notes_lbl.setMaximumWidth(300)
            h_layout.addWidget(notes_lbl)

        content_layout.addWidget(header_frame)

        # ── KPI Grid ──
        kpi_section_lbl = QLabel("Indicateurs clés")
        kpi_section_lbl.setStyleSheet(
            "color: #8b9bb4; font-size: 12px; font-weight: 600; letter-spacing: 1px;"
        )
        content_layout.addWidget(kpi_section_lbl)

        self._kpi_row = QHBoxLayout()
        self._kpi_row.setSpacing(12)
        self._kpi_placeholder = QWidget()
        self._kpi_placeholder.setLayout(self._kpi_row)
        content_layout.addWidget(self._kpi_placeholder)

        # ── Deux colonnes : Timeline | Documents ──
        cols = QHBoxLayout()
        cols.setSpacing(16)

        # Timeline
        tl_col = QVBoxLayout()
        tl_col.setSpacing(8)
        tl_title = QLabel("Historique")
        tl_title.setStyleSheet(
            "color: #e8eaed; font-size: 14px; font-weight: 700; font-family: 'Segoe UI';"
        )
        tl_col.addWidget(tl_title)

        self._timeline_frame = QFrame()
        self._timeline_frame.setStyleSheet(
            "background-color: #0f1524; border: 1px solid #1a2236; border-radius: 10px;"
        )
        self._timeline_inner = QVBoxLayout(self._timeline_frame)
        self._timeline_inner.setContentsMargins(14, 12, 14, 12)
        self._timeline_inner.setSpacing(4)
        tl_col.addWidget(self._timeline_frame)
        tl_col.addStretch()
        cols.addLayout(tl_col, stretch=1)

        # Documents
        doc_col = QVBoxLayout()
        doc_col.setSpacing(8)
        doc_title = QLabel("Documents")
        doc_title.setStyleSheet(
            "color: #e8eaed; font-size: 14px; font-weight: 700; font-family: 'Segoe UI';"
        )
        doc_col.addWidget(doc_title)

        self._docs_frame = QFrame()
        self._docs_frame.setStyleSheet(
            "background-color: #0f1524; border: 1px solid #1a2236; border-radius: 10px;"
        )
        self._docs_inner = QVBoxLayout(self._docs_frame)
        self._docs_inner.setContentsMargins(14, 12, 14, 12)
        self._docs_inner.setSpacing(4)
        doc_col.addWidget(self._docs_frame)
        doc_col.addStretch()
        cols.addLayout(doc_col, stretch=1)

        content_layout.addLayout(cols)
        content_layout.addStretch()

        scroll.setWidget(content)
        root.addWidget(scroll, stretch=1)

    def _load_data(self) -> None:
        """# MODULE_SOCIETE: charge métriques, timeline et documents."""
        self._refresh_kpis()
        self._refresh_timeline()
        self._refresh_documents()

    def _refresh_kpis(self) -> None:
        metrics = company_model.get_metrics(self._company_id)
        # Vider
        while self._kpi_row.count():
            item = self._kpi_row.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        defs = [
            ("ca_ytd",         "CA année",      "€", "#e8eaed"),
            ("unpaid",         "Impayés",       "€", "#ef4444"),
            ("open_tickets",   "Tickets ouverts", "", "#f59e0b"),
            ("quotes_pending", "Devis en attente", "", "#5E6AD2"),
        ]
        for key, label, unit, color in defs:
            val = metrics.get(key, 0)
            if val == 0 and key in ("ca_ytd",):
                color = "#8b9bb4"
            fmt_val = f"{val:,.0f} {unit}".strip() if unit else str(int(val))
            card = _KpiCard(label, fmt_val, color if val > 0 else "#8b9bb4")
            self._kpi_row.addWidget(card)
        self._kpi_row.addStretch()

    def _refresh_timeline(self) -> None:
        while self._timeline_inner.count():
            item = self._timeline_inner.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        events = company_model.get_timeline(self._company_id, limit=20)
        if not events:
            empty = QLabel("Aucun événement enregistré.")
            empty.setStyleSheet("color: #8b9bb4; font-size: 12px;")
            self._timeline_inner.addWidget(empty)
            return

        for ev in events:
            item = _TimelineItem(ev)
            self._timeline_inner.addWidget(item)
            sep = QFrame()
            sep.setFrameShape(QFrame.Shape.HLine)
            sep.setStyleSheet("color: #1a2236;")
            self._timeline_inner.addWidget(sep)

    def _refresh_documents(self) -> None:
        while self._docs_inner.count():
            item = self._docs_inner.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        docs = company_model.get_documents(self._company_id)
        if not docs:
            empty = QLabel("Aucun document enregistré.")
            empty.setStyleSheet("color: #8b9bb4; font-size: 12px;")
            self._docs_inner.addWidget(empty)
            return

        for doc in docs:
            item = _DocumentItem(doc)
            self._docs_inner.addWidget(item)
            sep = QFrame()
            sep.setFrameShape(QFrame.Shape.HLine)
            sep.setStyleSheet("color: #1a2236;")
            self._docs_inner.addWidget(sep)

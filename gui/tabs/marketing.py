"""
Marketing Tab — Générateur de contenu MargePro.

Sélecteurs : réseau, type de contenu, secteur, ton.
Génération via Ollama (marketing_executor.py) dans un QThread.
Historique SQLite.
"""

from PySide6.QtCore import Qt, QThread, Signal, QObject, QTimer
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QFrame,
    QTextEdit, QSplitter, QListWidget, QListWidgetItem,
    QSizePolicy, QApplication, QComboBox as _QComboBox,
)
from PySide6.QtGui import QFont, QClipboard
from qfluentwidgets import (
    ComboBox, PrimaryPushButton, PushButton, TransparentToolButton,
    LineEdit, FluentIcon as FIF, InfoBar, InfoBarPosition,
    ScrollArea,
)

from core.marketing_executor import (
    generate_stream,
    get_history,
    delete_history_entry,
    list_marketing_skills,
    list_ollama_models,
    CONTENT_TYPES,
    RESEAUX,
    SECTEURS,
    TONS,
)

# ---------------------------------------------------------------------------
# Styles
# ---------------------------------------------------------------------------

_CARD = """
    background: rgba(255,255,255,0.03);
    border: 1px solid rgba(255,255,255,0.06);
    border-radius: 12px;
"""

_COMBO = """
    QComboBox {
        background-color: #1a2236;
        border: 1px solid #2a3556;
        border-radius: 10px;
        color: #e0e0e0;
        padding: 7px 12px;
        font-size: 13px;
        min-width: 160px;
    }
    QComboBox:focus { border-color: #33b5e5; }
    QComboBox::drop-down { border: none; width: 24px; }
    QComboBox QAbstractItemView {
        background-color: #1a2236;
        color: #e0e0e0;
        border: 1px solid #2a3556;
        selection-background-color: #1e3a5f;
    }
"""

_TEXTEDIT = """
    QTextEdit {
        background-color: #111827;
        border: 1px solid #2a3556;
        border-radius: 10px;
        color: #e0e0e0;
        padding: 10px;
        font-size: 13px;
        line-height: 1.5;
    }
    QTextEdit:focus { border-color: #33b5e5; }
"""

_RESULT_EDIT = """
    QTextEdit {
        background-color: #0d1424;
        border: 1px solid #1e3a5f;
        border-radius: 10px;
        color: #e8f4fd;
        padding: 14px;
        font-size: 14px;
        line-height: 1.6;
        selection-background-color: #1e3a5f;
    }
"""

_HISTORY_LIST = """
    QListWidget {
        background: transparent;
        border: none;
        color: #8a9ab5;
        font-size: 12px;
    }
    QListWidget::item {
        padding: 6px 8px;
        border-radius: 6px;
    }
    QListWidget::item:selected {
        background: rgba(51, 181, 229, 0.15);
        color: #33b5e5;
    }
    QListWidget::item:hover {
        background: rgba(255,255,255,0.04);
    }
"""


# ---------------------------------------------------------------------------
# Worker thread
# ---------------------------------------------------------------------------

class _GenerateWorker(QObject):
    token_received = Signal(str)
    finished = Signal(str)
    error_occurred = Signal(str)

    def __init__(self, content_type, reseau, secteur, ton, brief, skill_name, model=""):
        super().__init__()
        self._ct = content_type
        self._reseau = reseau
        self._secteur = secteur
        self._ton = ton
        self._brief = brief
        self._skill = skill_name
        self._model = model

    def run(self):
        generate_stream(
            content_type=self._ct,
            reseau=self._reseau,
            secteur=self._secteur,
            ton=self._ton,
            brief=self._brief,
            on_token=self.token_received.emit,
            on_done=self.finished.emit,
            on_error=self.error_occurred.emit,
            skill_name=self._skill,
            model=self._model,
        )


# ---------------------------------------------------------------------------
# Main tab
# ---------------------------------------------------------------------------

class MarketingTab(QWidget):
    """Onglet générateur de contenu marketing MargePro."""

    def __init__(self):
        super().__init__()
        self.setObjectName("MarketingTab")
        self._thread: QThread | None = None
        self._worker: _GenerateWorker | None = None
        self._history_ids: list[int] = []
        self._setup_ui()
        self._load_history()
        # Charger les modèles Ollama après le rendu initial
        QTimer.singleShot(0, self._load_models)

    # ── UI ────────────────────────────────────────────────────────────────────

    def _setup_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(20, 16, 20, 16)
        root.setSpacing(12)

        # ── Header ──
        header = QHBoxLayout()
        self._title_label = QLabel("❆ Générateur de contenu")
        self._title_label.setStyleSheet("font-size: 20px; font-weight: bold; color: #e8f4fd;")
        header.addWidget(self._title_label)
        header.addStretch()
        root.addLayout(header)

        # ── Splitter principal : panneau gauche + résultat droit ──
        splitter = QSplitter(Qt.Horizontal)
        splitter.setChildrenCollapsible(False)
        splitter.setHandleWidth(6)

        # ─── Panneau gauche (contrôles) ───────────────────────────
        left_frame = QFrame()
        left_frame.setStyleSheet(_CARD)
        left_layout = QVBoxLayout(left_frame)
        left_layout.setContentsMargins(16, 14, 16, 14)
        left_layout.setSpacing(10)

        def _label(text: str) -> QLabel:
            lbl = QLabel(text)
            lbl.setStyleSheet("color: #8a9ab5; font-size: 11px; font-weight: bold; letter-spacing: 0.5px;")
            return lbl

        # Modèle IA
        model_row = QHBoxLayout()
        model_row.addWidget(_label("MODÈLE IA"))
        model_row.addStretch()
        refresh_model_btn = TransparentToolButton(FIF.SYNC)
        refresh_model_btn.setToolTip("Rafraîchir la liste des modèles")
        refresh_model_btn.setFixedSize(22, 22)
        refresh_model_btn.clicked.connect(self._load_models)
        model_row.addWidget(refresh_model_btn)
        left_layout.addLayout(model_row)
        self.combo_model = _QComboBox()
        self.combo_model.addItem("(défaut config)")
        self.combo_model.setStyleSheet(_COMBO)
        left_layout.addWidget(self.combo_model)

        # Produit / Skill
        left_layout.addWidget(_label("PRODUIT / MODULE"))
        self.combo_skill = ComboBox()
        self.combo_skill.setStyleSheet(_COMBO)
        self._skill_names: list[str] = []
        self._populate_skill_combo()
        self.combo_skill.currentIndexChanged.connect(self._on_skill_changed)
        left_layout.addWidget(self.combo_skill)

        # Réseau
        left_layout.addWidget(_label("RÉSEAU CIBLE"))
        self.combo_reseau = ComboBox()
        self.combo_reseau.addItems(RESEAUX)
        self.combo_reseau.setStyleSheet(_COMBO)
        left_layout.addWidget(self.combo_reseau)

        # Type de contenu
        left_layout.addWidget(_label("TYPE DE CONTENU"))
        self.combo_type = ComboBox()
        self.combo_type.addItems(list(CONTENT_TYPES.keys()))
        self.combo_type.setStyleSheet(_COMBO)
        left_layout.addWidget(self.combo_type)

        # Secteur — éditable (liste + saisie libre)
        left_layout.addWidget(_label("SECTEUR CIBLE"))
        self.combo_secteur = _QComboBox()
        self.combo_secteur.setEditable(True)
        self.combo_secteur.setInsertPolicy(_QComboBox.InsertPolicy.NoInsert)
        self.combo_secteur.addItems(SECTEURS)
        self.combo_secteur.setPlaceholderText("Choisir ou saisir un secteur…")
        self.combo_secteur.setStyleSheet(_COMBO + """
            QComboBox QLineEdit {
                background: transparent;
                border: none;
                color: #e0e0e0;
                padding: 0;
                font-size: 13px;
            }
        """)
        left_layout.addWidget(self.combo_secteur)

        # Ton
        left_layout.addWidget(_label("TON"))
        self.combo_ton = ComboBox()
        self.combo_ton.addItems(TONS)
        self.combo_ton.setStyleSheet(_COMBO)
        left_layout.addWidget(self.combo_ton)

        # Brief
        left_layout.addWidget(_label("BRIEF / CONTEXTE"))
        self.brief_edit = QTextEdit()
        self.brief_edit.setPlaceholderText(
            "Décris ici ton angle, un chiffre clé, une accroche de départ, "
            "une objection à traiter…"
        )
        self.brief_edit.setStyleSheet(_TEXTEDIT)
        self.brief_edit.setFixedHeight(110)
        left_layout.addWidget(self.brief_edit)

        # Boutons
        btn_row = QHBoxLayout()
        self.generate_btn = PrimaryPushButton(FIF.SEND, "Générer")
        self.generate_btn.setFixedHeight(38)
        self.generate_btn.clicked.connect(self._on_generate)
        btn_row.addWidget(self.generate_btn)

        self.stop_btn = PushButton(FIF.CLOSE, "Arrêter")
        self.stop_btn.setFixedHeight(38)
        self.stop_btn.setEnabled(False)
        self.stop_btn.clicked.connect(self._on_stop)
        btn_row.addWidget(self.stop_btn)
        left_layout.addLayout(btn_row)

        # ── Historique ──
        left_layout.addWidget(_label("HISTORIQUE"))
        self.history_list = QListWidget()
        self.history_list.setStyleSheet(_HISTORY_LIST)
        self.history_list.itemClicked.connect(self._on_history_click)
        left_layout.addWidget(self.history_list)

        # Bouton vider historique
        clear_hist_btn = PushButton(FIF.DELETE, "Vider l'historique")
        clear_hist_btn.setFixedHeight(32)
        clear_hist_btn.clicked.connect(self._on_clear_history)
        left_layout.addWidget(clear_hist_btn)

        splitter.addWidget(left_frame)
        splitter.setStretchFactor(0, 0)

        # ─── Panneau droit (résultat) ─────────────────────────────
        right_frame = QFrame()
        right_frame.setStyleSheet(_CARD)
        right_layout = QVBoxLayout(right_frame)
        right_layout.setContentsMargins(16, 14, 16, 14)
        right_layout.setSpacing(8)

        result_header = QHBoxLayout()
        result_title = QLabel("Contenu généré")
        result_title.setStyleSheet("color: #8a9ab5; font-size: 11px; font-weight: bold; letter-spacing: 0.5px;")
        result_header.addWidget(result_title)
        result_header.addStretch()

        self.char_count_label = QLabel("0 car.")
        self.char_count_label.setStyleSheet("color: #4a5a75; font-size: 11px;")
        result_header.addWidget(self.char_count_label)

        copy_btn = TransparentToolButton(FIF.COPY)
        copy_btn.setToolTip("Copier le contenu")
        copy_btn.clicked.connect(self._on_copy)
        result_header.addWidget(copy_btn)

        clear_btn = TransparentToolButton(FIF.CLOSE)
        clear_btn.setToolTip("Effacer")
        clear_btn.clicked.connect(self._on_clear_result)
        result_header.addWidget(clear_btn)

        right_layout.addLayout(result_header)

        self.result_edit = QTextEdit()
        self.result_edit.setReadOnly(True)
        self.result_edit.setStyleSheet(_RESULT_EDIT)
        self.result_edit.setPlaceholderText(
            "Le contenu généré apparaîtra ici…\n\n"
            "Sélectionne tes paramètres à gauche et clique sur Générer."
        )
        result_header_font = QFont("Segoe UI", 13)
        self.result_edit.setFont(result_header_font)
        right_layout.addWidget(self.result_edit)

        # Indicateur de statut
        self.status_label = QLabel("")
        self.status_label.setStyleSheet("color: #4a5a75; font-size: 11px;")
        self.status_label.setAlignment(Qt.AlignRight)
        right_layout.addWidget(self.status_label)

        splitter.addWidget(right_frame)
        splitter.setStretchFactor(1, 1)

        # Tailles initiales : 320 gauche, reste droite
        splitter.setSizes([320, 800])
        root.addWidget(splitter)

        # Connecter le compteur de caractères
        self.result_edit.textChanged.connect(self._update_char_count)

    # ── Slots ─────────────────────────────────────────────────────────────────

    def _on_generate(self):
        if self._thread and self._thread.isRunning():
            return

        skill_name = self._skill_names[self.combo_skill.currentIndex()] if self._skill_names else "margepro"
        reseau = self.combo_reseau.currentText()
        content_type = self.combo_type.currentText()
        secteur = self.combo_secteur.currentText()
        ton = self.combo_ton.currentText()
        brief = self.brief_edit.toPlainText().strip()
        model = self.combo_model.currentText()
        if model == "(défaut config)":
            model = ""

        # Reset UI
        self.result_edit.clear()
        self.status_label.setText(f"⏳ Génération en cours ({content_type} · {reseau})…")
        self.generate_btn.setEnabled(False)
        self.stop_btn.setEnabled(True)

        # Worker + thread
        self._worker = _GenerateWorker(content_type, reseau, secteur, ton, brief, skill_name, model)
        self._thread = QThread()
        self._worker.moveToThread(self._thread)

        self._thread.started.connect(self._worker.run)
        self._worker.token_received.connect(self._on_token)
        self._worker.finished.connect(self._on_done)
        self._worker.error_occurred.connect(self._on_error)

        # Cycle de vie Qt correct : le thread se quitte quand le worker a fini,
        # puis deleteLater est appelé — on ne détruit jamais manuellement.
        self._worker.finished.connect(self._thread.quit)
        self._worker.error_occurred.connect(self._thread.quit)
        self._thread.finished.connect(self._worker.deleteLater)
        self._thread.finished.connect(self._thread.deleteLater)
        self._thread.finished.connect(self._clear_thread_refs)

        self._thread.start()

    def _on_stop(self):
        """Arrête la génération proprement (le thread se terminera naturellement)."""
        if self._thread and self._thread.isRunning():
            self._thread.requestInterruption()
            # quit() est aussi envoyé par worker.finished/error via signal, pas besoin de quit() ici
        self._reset_buttons()
        self.status_label.setText("⏹ Génération interrompue.")

    def _on_token(self, token: str):
        cursor = self.result_edit.textCursor()
        from PySide6.QtGui import QTextCursor
        cursor.movePosition(QTextCursor.End)
        self.result_edit.setTextCursor(cursor)
        self.result_edit.insertPlainText(token)

    def _clear_thread_refs(self):
        """Appelé par thread.finished — les objets sont déjà en deleteLater."""
        self._thread = None
        self._worker = None

    def _on_done(self, full_text: str):
        self._reset_buttons()
        n = len(full_text)
        self.status_label.setText(f"✓ Généré — {n} caractères. Sauvegardé dans l'historique.")
        self._load_history()
        # Pas de cleanup ici : géré par thread.finished → deleteLater

    def _on_error(self, msg: str):
        self._reset_buttons()
        self.status_label.setText(f"✗ Erreur : {msg}")
        InfoBar.error(
            title="Erreur de génération",
            content=msg,
            parent=self,
            position=InfoBarPosition.BOTTOM_RIGHT,
            duration=5000,
        )
        # Pas de cleanup ici : géré par thread.finished → deleteLater

    def _on_copy(self):
        text = self.result_edit.toPlainText()
        if text:
            QApplication.clipboard().setText(text)
            InfoBar.success(
                title="Copié",
                content="Contenu copié dans le presse-papiers.",
                parent=self,
                position=InfoBarPosition.BOTTOM_RIGHT,
                duration=2000,
            )

    def _on_clear_result(self):
        self.result_edit.clear()
        self.status_label.setText("")

    def _on_history_click(self, item: QListWidgetItem):
        idx = self.history_list.row(item)
        if idx < 0 or idx >= len(self._history_ids):
            return
        history = get_history(limit=50)
        if idx < len(history):
            entry = history[idx]
            self.result_edit.setPlainText(entry["result"])
            # Restaurer les paramètres
            _set_combo(self.combo_reseau, entry["reseau"])
            _set_combo(self.combo_type, entry["content_type"])
            _set_combo(self.combo_secteur, entry["secteur"])
            _set_combo(self.combo_ton, entry["ton"])
            if entry.get("skill_name"):
                _set_skill_combo(self.combo_skill, self._skill_names, entry["skill_name"])
            if entry.get("brief"):
                self.brief_edit.setPlainText(entry["brief"])
            self.status_label.setText(f"📂 Historique — {entry['created_at']}")

    def _on_clear_history(self):
        import sqlite3
        from pathlib import Path
        db = Path(__file__).parent.parent.parent / "data" / "marketing_history.db"
        try:
            conn = sqlite3.connect(str(db))
            conn.execute("DELETE FROM marketing_history")
            conn.commit()
            conn.close()
        except Exception:
            pass
        self._load_history()
        InfoBar.success(
            title="Historique vidé",
            content="",
            parent=self,
            position=InfoBarPosition.BOTTOM_RIGHT,
            duration=2000,
        )

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _load_models(self):
        """Charge la liste des modèles Ollama disponibles dans le combo."""
        current = self.combo_model.currentText()
        models = list_ollama_models()
        self.combo_model.blockSignals(True)
        self.combo_model.clear()
        self.combo_model.addItem("(défaut config)")
        for m in models:
            self.combo_model.addItem(m)
        # Rétablir la sélection précédente si elle existe encore
        idx = self.combo_model.findText(current)
        self.combo_model.setCurrentIndex(idx if idx >= 0 else 0)
        self.combo_model.blockSignals(False)

    def _populate_skill_combo(self):
        """Charge les skills disponibles dans le sélecteur."""
        self.combo_skill.clear()
        self._skill_names = []
        skills = list_marketing_skills()
        for s in skills:
            # Affiche : nom du dossier + description courte (tronquée)
            desc = s['description'][:50] + '…' if len(s['description']) > 50 else s['description']
            self.combo_skill.addItem(f"{s['name']}  —  {desc}")
            self._skill_names.append(s['name'])
        # Sélectionner margepro par défaut
        if 'margepro' in self._skill_names:
            self.combo_skill.setCurrentIndex(self._skill_names.index('margepro'))

    def _on_skill_changed(self, idx: int):
        """Met à jour le titre de l'onglet avec le nom du produit sélectionné."""
        if 0 <= idx < len(self._skill_names):
            name = self._skill_names[idx].replace('_', ' ').replace('-', ' ').title()
            self._title_label.setText(f"❆ {name} — Générateur de contenu")

    def _reset_buttons(self):
        self.generate_btn.setEnabled(True)
        self.stop_btn.setEnabled(False)

    def _load_history(self):
        self.history_list.clear()
        self._history_ids = []
        entries = get_history(limit=50)
        for entry in entries:
            self._history_ids.append(entry["id"])
            date = entry["created_at"][:10]
            skill = entry.get("skill_name", "?")
            label = f"{date}  [{skill}]  {entry['content_type']} · {entry['reseau']}"
            self.history_list.addItem(label)

    def _update_char_count(self):
        n = len(self.result_edit.toPlainText())
        self.char_count_label.setText(f"{n} car.")


# ---------------------------------------------------------------------------
# Utility
# ---------------------------------------------------------------------------

def _set_combo(combo, value: str) -> None:
    idx = combo.findText(value)
    if idx >= 0:
        combo.setCurrentIndex(idx)
    elif hasattr(combo, 'setCurrentText'):
        # Combo éditable : on place le texte libre même s'il n'est pas dans la liste
        combo.setCurrentText(value)


def _set_skill_combo(combo: ComboBox, skill_names: list[str], skill_name: str) -> None:
    """Sélectionne le skill par son nom interne (nom du dossier)."""
    if skill_name in skill_names:
        combo.setCurrentIndex(skill_names.index(skill_name))

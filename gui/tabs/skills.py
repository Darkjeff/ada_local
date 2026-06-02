"""
Skills Tab — browse, reload, and create skills (SKILL.md files).
"""

from pathlib import Path

from PySide6.QtCore import Qt, Signal, QThread
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QFrame, QSplitter, QTextEdit, QFileDialog, QSizePolicy
)
from qfluentwidgets import (
    PushButton, PrimaryPushButton, TransparentToolButton,
    ListWidget, ScrollArea, LineEdit, FluentIcon as FIF,
    InfoBar, InfoBarPosition
)
from PySide6.QtWidgets import QListWidgetItem

from core.skill_manager import skill_manager, SKILLS_DIR, Skill


class SkillsTab(QWidget):
    """Tab for managing SKILL.md skills."""

    skill_reloaded = Signal()

    def __init__(self):
        super().__init__()
        self.setObjectName("SkillsTab")
        self._selected_skill: Skill | None = None
        self._setup_ui()
        self._load_skills()

    # ── UI ────────────────────────────────────────────────────────────────────

    def _setup_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(20, 16, 20, 16)
        root.setSpacing(12)

        # Toolbar
        toolbar = QHBoxLayout()
        toolbar.setSpacing(8)

        title = QLabel("Skills")
        title.setStyleSheet("font-size: 18px; font-weight: bold; color: #e0e0e0;")
        toolbar.addWidget(title)
        toolbar.addStretch()

        self.reload_btn = PushButton(FIF.SYNC, "Recharger")
        self.reload_btn.clicked.connect(self._on_reload)
        toolbar.addWidget(self.reload_btn)

        self.new_btn = PrimaryPushButton(FIF.ADD, "Nouveau skill")
        self.new_btn.clicked.connect(self._on_new)
        toolbar.addWidget(self.new_btn)

        root.addLayout(toolbar)

        # Splitter: list (left) + detail (right)
        splitter = QSplitter(Qt.Horizontal)
        splitter.setChildrenCollapsible(False)

        # Left — skill list
        left = QFrame()
        left.setStyleSheet("background: transparent;")
        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(6)

        self.search = LineEdit()
        self.search.setPlaceholderText("Filtrer…")
        self.search.setClearButtonEnabled(True)
        self.search.textChanged.connect(self._filter)
        left_layout.addWidget(self.search)

        self.skill_list = ListWidget()
        self.skill_list.setStyleSheet("background: transparent; border: none;")
        self.skill_list.currentItemChanged.connect(self._on_select)
        left_layout.addWidget(self.skill_list)

        splitter.addWidget(left)

        # Right — skill detail
        right = QFrame()
        right.setStyleSheet(
            "background: rgba(255,255,255,0.03); border-radius: 10px;"
        )
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(16, 12, 16, 12)
        right_layout.setSpacing(8)

        def _field_label(text):
            lbl = QLabel(text)
            lbl.setStyleSheet("color: #8a8a8a; font-size: 11px; margin-top: 4px;")
            return lbl

        right_layout.addWidget(_field_label("Nom du skill :"))
        self.detail_name = LineEdit()
        self.detail_name.setPlaceholderText("nom_du_skill")
        self.detail_name.setReadOnly(True)   # le nom = nom du dossier, lecture seule
        self.detail_name.setStyleSheet("background: rgba(0,0,0,.15); color: #c0c0c0; font-weight: bold;")
        right_layout.addWidget(self.detail_name)

        right_layout.addWidget(_field_label("Description :"))
        self.detail_desc = LineEdit()
        self.detail_desc.setPlaceholderText("Description courte du skill")
        self.detail_desc.setEnabled(False)
        right_layout.addWidget(self.detail_desc)

        right_layout.addWidget(_field_label("Triggers (séparés par des virgules) :"))
        self.detail_triggers = LineEdit()
        self.detail_triggers.setPlaceholderText("mot-clé 1, mot-clé 2")
        self.detail_triggers.setEnabled(False)
        right_layout.addWidget(self.detail_triggers)

        self.always_badge = QLabel("⚡ Toujours actif — injecté dans chaque message")
        self.always_badge.setStyleSheet(
            "color: #f0c040; font-size: 11px; background: rgba(240,192,64,0.10); "
            "padding: 6px 8px; border-radius: 6px;"
        )
        self.always_badge.setVisible(False)
        right_layout.addWidget(self.always_badge)

        body_label = _field_label("Contenu du skill :")
        body_label.setStyleSheet("color: #8a8a8a; font-size: 11px; margin-top: 8px;")
        right_layout.addWidget(body_label)

        self.detail_body = QTextEdit()
        self.detail_body.setStyleSheet(
            "background: rgba(0,0,0,0.2); border-radius: 6px; "
            "color: #c8c8c8; font-family: 'Consolas', monospace; font-size: 12px;"
        )
        right_layout.addWidget(self.detail_body, stretch=1)

        btn_row = QHBoxLayout()
        self.open_btn = PushButton(FIF.FOLDER, "Ouvrir dossier")
        self.open_btn.setEnabled(False)
        self.open_btn.clicked.connect(self._open_folder)
        btn_row.addWidget(self.open_btn)
        btn_row.addStretch()
        self.save_btn = PrimaryPushButton(FIF.SAVE, "Sauvegarder")
        self.save_btn.setEnabled(False)
        self.save_btn.clicked.connect(self._on_save)
        btn_row.addWidget(self.save_btn)
        right_layout.addLayout(btn_row)

        splitter.addWidget(right)
        splitter.setSizes([260, 600])

        root.addWidget(splitter, stretch=1)

        # Footer info
        self.footer = QLabel("")
        self.footer.setStyleSheet("color: #555; font-size: 11px;")
        root.addWidget(self.footer)

    # ── Logic ────────────────────────────────────────────────────────────────

    def _load_skills(self):
        skill_manager.reload()
        self.skill_list.clear()
        for skill in skill_manager.skills:
            prefix = "⚡ " if skill.always else "  "
            item = QListWidgetItem(f"{prefix}{skill.name}")
            item.setData(Qt.UserRole, skill.name)
            self.skill_list.addItem(item)
        count = len(skill_manager.skills)
        always_count = len(skill_manager.always_skills)
        self.footer.setText(
            f"{count} skill(s) chargé(s) · {always_count} toujours actif(s) · {SKILLS_DIR}"
        )

    def _filter(self, text: str):
        text = text.lower()
        for i in range(self.skill_list.count()):
            item = self.skill_list.item(i)
            name = item.data(Qt.UserRole) or ""
            item.setHidden(text not in name.lower())

    def _on_select(self, item: QListWidgetItem | None):
        if not item:
            return
        name = item.data(Qt.UserRole)
        skill = skill_manager.get(name)
        if not skill:
            return
        self._selected_skill = skill
        self.detail_name.setText(skill.name)
        self.detail_desc.setText(skill.description or "")
        self.detail_desc.setEnabled(True)

        self.always_badge.setVisible(skill.always)
        triggers_text = ", ".join(skill.triggers) if skill.triggers else ""
        self.detail_triggers.setText(triggers_text)
        self.detail_triggers.setEnabled(True)

        self.detail_body.setPlainText(skill.body)
        self.open_btn.setEnabled(True)
        self.save_btn.setEnabled(True)

    def _on_save(self):
        """Save description, triggers and body back to the SKILL.md."""
        if not self._selected_skill:
            return
        try:
            path = self._selected_skill.path
            desc = self.detail_desc.text().strip() or self._selected_skill.description or ""
            raw_triggers = [t.strip() for t in self.detail_triggers.text().split(",") if t.strip()]
            triggers_yaml = "\n".join(f"  - {t}" for t in raw_triggers) if raw_triggers else "  []"
            always_line = "\nalways: true" if self._selected_skill.always else ""
            frontmatter = (
                f"---\n"
                f"name: {self._selected_skill.name}\n"
                f"description: {desc}\n"
                f"triggers:\n{triggers_yaml}"
                f"{always_line}\n"
                f"---\n"
            )
            new_content = frontmatter + self.detail_body.toPlainText().strip() + "\n"
            path.write_text(new_content, encoding="utf-8")
            skill_manager.reload()
            InfoBar.success(
                title="Sauvegardé",
                content=f"Skill '{self._selected_skill.name}' mis à jour.",
                orient=Qt.Horizontal, isClosable=True,
                position=InfoBarPosition.TOP_RIGHT, duration=3000, parent=self,
            )
        except Exception as e:
            InfoBar.error(
                title="Erreur de sauvegarde",
                content=str(e),
                orient=Qt.Horizontal, isClosable=True,
                position=InfoBarPosition.TOP_RIGHT, duration=4000, parent=self,
            )

    def _on_reload(self):
        self._load_skills()
        self.skill_reloaded.emit()
        InfoBar.success(
            title="Skills rechargés",
            content=f"{len(skill_manager.skills)} skill(s) chargé(s).",
            orient=Qt.Horizontal,
            isClosable=True,
            position=InfoBarPosition.TOP_RIGHT,
            duration=3000,
            parent=self,
        )

    def _on_new(self):
        """Create a skeleton SKILL.md in a new subdirectory."""
        from PySide6.QtWidgets import QInputDialog
        name, ok = QInputDialog.getText(self, "Nouveau skill", "Nom du skill (ex: mon_skill) :")
        if not ok or not name.strip():
            return
        name = name.strip().lower().replace(" ", "_")
        skill_dir = SKILLS_DIR / name
        skill_file = skill_dir / "SKILL.md"
        if skill_file.exists():
            InfoBar.warning(
                title="Skill existant",
                content=f"Le skill '{name}' existe déjà.",
                orient=Qt.Horizontal, isClosable=True,
                position=InfoBarPosition.TOP_RIGHT, duration=3000, parent=self,
            )
            return
        skill_dir.mkdir(parents=True, exist_ok=True)
        skill_file.write_text(
            f"---\nname: {name}\ndescription: Description de mon skill\ntriggers:\n  - mot-clé 1\n  - mot-clé 2\n---\n\nTu es un expert en...\n",
            encoding="utf-8",
        )
        self._load_skills()
        InfoBar.success(
            title="Skill créé",
            content=f"Fichier créé : {skill_file}\nOuvre-le dans un éditeur pour le compléter.",
            orient=Qt.Horizontal, isClosable=True,
            position=InfoBarPosition.TOP_RIGHT, duration=5000, parent=self,
        )

    def _open_folder(self):
        if self._selected_skill:
            import subprocess, sys
            folder = str(self._selected_skill.path.parent)
            if sys.platform == "win32":
                subprocess.Popen(["explorer", folder])
            else:
                subprocess.Popen(["xdg-open", folder])

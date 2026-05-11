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

        self.detail_name = QLabel("Sélectionne un skill")
        self.detail_name.setStyleSheet("font-size: 15px; font-weight: bold; color: #e0e0e0;")
        right_layout.addWidget(self.detail_name)

        self.detail_desc = QLabel("")
        self.detail_desc.setStyleSheet("color: #8a8a8a; font-size: 12px;")
        self.detail_desc.setWordWrap(True)
        right_layout.addWidget(self.detail_desc)

        self.detail_triggers = QLabel("")
        self.detail_triggers.setStyleSheet(
            "color: #5294e2; font-size: 11px; background: rgba(82,148,226,0.08); "
            "padding: 6px 8px; border-radius: 6px;"
        )
        self.detail_triggers.setWordWrap(True)
        right_layout.addWidget(self.detail_triggers)

        self.always_badge = QLabel("⚡ Toujours actif — injecté dans chaque message")
        self.always_badge.setStyleSheet(
            "color: #f0c040; font-size: 11px; background: rgba(240,192,64,0.10); "
            "padding: 6px 8px; border-radius: 6px;"
        )
        self.always_badge.setVisible(False)
        right_layout.addWidget(self.always_badge)

        body_label = QLabel("Contenu du skill :")
        body_label.setStyleSheet("color: #8a8a8a; font-size: 11px; margin-top: 6px;")
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
        self.detail_name.setText(("⚡ " if skill.always else "") + skill.name)
        self.detail_desc.setText(skill.description or "Pas de description.")

        self.always_badge.setVisible(skill.always)
        if skill.always:
            self.detail_triggers.setVisible(False)
        else:
            self.detail_triggers.setVisible(True)
            triggers_text = "  ·  ".join(skill.triggers) if skill.triggers else "—"
            self.detail_triggers.setText(f"Triggers : {triggers_text}")

        self.detail_body.setPlainText(skill.body)
        self.open_btn.setEnabled(True)
        self.save_btn.setEnabled(True)

    def _on_save(self):
        """Save the edited body back to the SKILL.md, preserving frontmatter."""
        if not self._selected_skill:
            return
        try:
            path = self._selected_skill.path
            original = path.read_text(encoding="utf-8")
            # Extract existing frontmatter block
            import re
            m = re.match(r"^(---[ \t]*\r?\n.*?\r?\n---[ \t]*\r?\n)", original, re.DOTALL)
            frontmatter = m.group(1) if m else "---\n---\n"
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

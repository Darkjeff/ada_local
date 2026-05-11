"""
Memory Tab — browse, search and manage the semantic memory store (SQLite).
"""

from datetime import datetime

from PySide6.QtCore import Qt, QThread, Signal, QTimer
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QFrame, QListWidgetItem, QSizePolicy
)
from qfluentwidgets import (
    PushButton, PrimaryPushButton, LineEdit, ListWidget,
    FluentIcon as FIF, InfoBar, InfoBarPosition, ScrollArea
)

from core.memory_store import memory_store


class _SearchThread(QThread):
    results_ready = Signal(list)

    def __init__(self, query: str):
        super().__init__()
        self._query = query

    def run(self):
        if self._query.strip():
            results = memory_store.search(self._query, limit=30)
        else:
            results = memory_store.recent(limit=50)
        self.results_ready.emit(results)


class MemoryTab(QWidget):
    def __init__(self):
        super().__init__()
        self.setObjectName("MemoryTab")
        self._current_results: list = []
        self._setup_ui()
        QTimer.singleShot(200, self._load_recent)

    # ── UI ────────────────────────────────────────────────────────────────────

    def _setup_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(20, 16, 20, 16)
        root.setSpacing(12)

        # Header
        header = QHBoxLayout()
        title = QLabel("Mémoire sémantique")
        title.setStyleSheet("font-size: 18px; font-weight: bold; color: #e0e0e0;")
        header.addWidget(title)
        header.addStretch()

        stats = memory_store.stats()
        self.stats_label = QLabel(
            f"{stats.get('total', 0)} souvenirs · {stats.get('sessions', 0)} sessions"
        )
        self.stats_label.setStyleSheet("color: #555; font-size: 12px;")
        header.addWidget(self.stats_label)
        root.addLayout(header)

        # Search bar
        search_row = QHBoxLayout()
        self.search_input = LineEdit()
        self.search_input.setPlaceholderText("Rechercher dans les souvenirs… (laisse vide pour récents)")
        self.search_input.setClearButtonEnabled(True)
        self.search_input.setFixedHeight(38)
        self.search_input.returnPressed.connect(self._on_search)
        search_row.addWidget(self.search_input, stretch=1)

        search_btn = PrimaryPushButton(FIF.SEARCH, "Chercher")
        search_btn.setFixedHeight(38)
        search_btn.clicked.connect(self._on_search)
        search_row.addWidget(search_btn)

        refresh_btn = PushButton(FIF.SYNC, "Récents")
        refresh_btn.setFixedHeight(38)
        refresh_btn.clicked.connect(self._load_recent)
        search_row.addWidget(refresh_btn)

        root.addLayout(search_row)

        # Results list + detail pane
        from PySide6.QtWidgets import QSplitter
        splitter = QSplitter(Qt.Horizontal)
        splitter.setChildrenCollapsible(False)

        # Left — results list
        left = QFrame()
        left.setStyleSheet("background: transparent;")
        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(0, 0, 0, 0)

        self.result_count = QLabel("—")
        self.result_count.setStyleSheet("color: #555; font-size: 11px; margin-bottom: 4px;")
        left_layout.addWidget(self.result_count)

        self.memory_list = ListWidget()
        self.memory_list.setStyleSheet("background: transparent; border: none;")
        self.memory_list.currentItemChanged.connect(self._on_select)
        left_layout.addWidget(self.memory_list)

        splitter.addWidget(left)

        # Right — detail
        right = QFrame()
        right.setStyleSheet(
            "background: rgba(255,255,255,0.03); border-radius: 10px;"
        )
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(16, 12, 16, 12)
        right_layout.setSpacing(8)

        self.detail_meta = QLabel("Sélectionne un souvenir")
        self.detail_meta.setStyleSheet("color: #8a8a8a; font-size: 12px;")
        right_layout.addWidget(self.detail_meta)

        from PySide6.QtWidgets import QTextEdit
        self.detail_content = QTextEdit()
        self.detail_content.setReadOnly(True)
        self.detail_content.setStyleSheet(
            "background: rgba(0,0,0,0.2); border-radius: 6px; "
            "color: #d0d0d0; font-size: 13px; line-height: 1.5;"
        )
        right_layout.addWidget(self.detail_content, stretch=1)

        btn_row = QHBoxLayout()
        btn_row.addStretch()
        self.delete_btn = PushButton(FIF.DELETE, "Supprimer ce souvenir")
        self.delete_btn.setEnabled(False)
        self.delete_btn.clicked.connect(self._on_delete)
        btn_row.addWidget(self.delete_btn)
        right_layout.addLayout(btn_row)

        splitter.addWidget(right)
        splitter.setSizes([320, 560])
        root.addWidget(splitter, stretch=1)

        # Footer
        self.footer = QLabel("")
        self.footer.setStyleSheet("color: #444; font-size: 10px;")
        root.addWidget(self.footer)

    # ── Logic ────────────────────────────────────────────────────────────────

    def _load_recent(self):
        self.search_input.clear()
        self._run_search("")

    def _on_search(self):
        self._run_search(self.search_input.text())

    def _run_search(self, query: str):
        self.memory_list.clear()
        self.result_count.setText("Recherche…")
        self._thread = _SearchThread(query)
        self._thread.results_ready.connect(self._on_results)
        self._thread.start()

    def _on_results(self, results: list):
        self._current_results = results
        self.memory_list.clear()

        for r in results:
            date = datetime.fromtimestamp(r["timestamp"]).strftime("%d/%m %H:%M")
            role = "👤" if r["role"] == "user" else "🤖"
            snippet = r["content"][:60].replace("\n", " ")
            item = QListWidgetItem(f"{role} [{date}]  {snippet}")
            item.setData(Qt.UserRole, r["id"])
            self.memory_list.addItem(item)

        mode = "récents" if not self.search_input.text().strip() else "trouvés"
        self.result_count.setText(f"{len(results)} souvenir(s) {mode}")

        # Refresh stats
        stats = memory_store.stats()
        self.stats_label.setText(
            f"{stats.get('total', 0)} souvenirs · {stats.get('sessions', 0)} sessions"
        )

    def _on_select(self, item: QListWidgetItem | None):
        if not item:
            return
        mem_id = item.data(Qt.UserRole)
        r = next((x for x in self._current_results if x["id"] == mem_id), None)
        if not r:
            return

        date = datetime.fromtimestamp(r["timestamp"]).strftime("%A %d %B %Y à %H:%M")
        role_label = "Toi" if r["role"] == "user" else "ADA"
        self.detail_meta.setText(f"{role_label}  ·  {date}  ·  session {r['session_id'][:8]}…")
        self.detail_content.setPlainText(r["content"])
        self.delete_btn.setEnabled(True)
        self._selected_id = mem_id

    def _on_delete(self):
        if not hasattr(self, "_selected_id"):
            return
        memory_store.delete(self._selected_id)
        self._run_search(self.search_input.text())
        self.detail_content.clear()
        self.detail_meta.setText("Souvenir supprimé.")
        self.delete_btn.setEnabled(False)
        InfoBar.success(
            title="Souvenir supprimé",
            content="",
            orient=Qt.Horizontal, isClosable=True,
            position=InfoBarPosition.TOP_RIGHT, duration=2000, parent=self,
        )

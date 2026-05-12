from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QTextEdit, QSizePolicy, QSplitter
)
from PySide6.QtCore import Qt, QThread, Slot, Signal
from PySide6.QtGui import QPixmap, QImage

from qfluentwidgets import (
    PrimaryPushButton, PushButton, LineEdit, StrongBodyLabel,
    CaptionLabel, CardWidget, TextEdit
)

from core.agent import TextBrowserAgent


class BrowserTab(QWidget):
    """Web Agent tab — text-based browsing with qwen3:1.7b + Playwright."""

    run_signal = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("browserInterface")
        self._agent_thread = None
        self._agent = None
        self._setup_ui()

    # ── UI ────────────────────────────────────────────────────────────────────

    def _setup_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(16, 16, 16, 16)
        root.setSpacing(12)

        # Title
        title = StrongBodyLabel("Web Agent", self)
        root.addWidget(title)

        # Input row
        input_row = QHBoxLayout()
        self.task_input = LineEdit(self)
        self.task_input.setPlaceholderText(
            "e.g. Search for the latest Python release on python.org"
        )
        self.task_input.returnPressed.connect(self._on_start)
        input_row.addWidget(self.task_input)

        self.start_btn = PrimaryPushButton("Start", self)
        self.start_btn.clicked.connect(self._on_start)
        input_row.addWidget(self.start_btn)

        self.stop_btn = PushButton("Stop", self)
        self.stop_btn.clicked.connect(self._on_stop)
        self.stop_btn.setEnabled(False)
        input_row.addWidget(self.stop_btn)

        root.addLayout(input_row)

        # Status
        self.status_label = CaptionLabel("Status: Idle", self)
        root.addWidget(self.status_label)

        # Splitter: log left, result right
        splitter = QSplitter(Qt.Horizontal, self)

        # Action log
        log_card = CardWidget(self)
        log_layout = QVBoxLayout(log_card)
        log_layout.addWidget(StrongBodyLabel("Action Log", self))
        self.action_log = QTextEdit(self)
        self.action_log.setReadOnly(True)
        self.action_log.setStyleSheet("font-family: Consolas; font-size: 11px;")
        log_layout.addWidget(self.action_log)
        splitter.addWidget(log_card)

        # Result
        result_card = CardWidget(self)
        result_layout = QVBoxLayout(result_card)
        result_layout.addWidget(StrongBodyLabel("Result", self))
        self.result_view = TextEdit(self)
        self.result_view.setReadOnly(True)
        self.result_view.setPlaceholderText("The agent's final answer will appear here…")
        result_layout.addWidget(self.result_view)
        splitter.addWidget(result_card)

        splitter.setSizes([450, 350])
        root.addWidget(splitter, stretch=1)

    # ── Agent lifecycle ───────────────────────────────────────────────────────

    def _on_start(self):
        instruction = self.task_input.text().strip()
        if not instruction:
            return

        self.action_log.clear()
        self.result_view.clear()
        self.status_label.setText("Status: Running…")
        self.start_btn.setEnabled(False)
        self.stop_btn.setEnabled(True)

        # Create fresh agent + thread each run
        self._agent_thread = QThread(self)
        self._agent = TextBrowserAgent()
        self._agent.moveToThread(self._agent_thread)

        self._agent.step_update.connect(self._log)
        self._agent.result_ready.connect(self._on_result)
        self._agent.finished.connect(self._on_finished)
        self._agent.error_occurred.connect(self._on_error)

        self.run_signal.connect(self._agent.start_task)
        self._agent_thread.start()
        self.run_signal.emit(instruction)

    def _on_stop(self):
        if self._agent:
            self._agent.stop()
        self.status_label.setText("Status: Stopping…")
        self.stop_btn.setEnabled(False)

    # ── Slots ─────────────────────────────────────────────────────────────────

    @Slot(str)
    def _log(self, text: str):
        self.action_log.append(text)

    @Slot(str)
    def _on_result(self, text: str):
        self.result_view.setPlainText(text)

    @Slot()
    def _on_finished(self):
        self.status_label.setText("Status: Done")
        self.start_btn.setEnabled(True)
        self.stop_btn.setEnabled(False)
        if self._agent_thread:
            self._agent_thread.quit()
            self._agent_thread.wait(3000)

    @Slot(str)
    def _on_error(self, err: str):
        self.status_label.setText(f"Status: Error")
        self.action_log.append(f"ERROR: {err}")
        self.start_btn.setEnabled(True)
        self.stop_btn.setEnabled(False)
        if self._agent_thread:
            self._agent_thread.quit()

    def closeEvent(self, event):
        self._on_stop()
        if self._agent_thread and self._agent_thread.isRunning():
            self._agent_thread.quit()
            self._agent_thread.wait(3000)
        super().closeEvent(event)

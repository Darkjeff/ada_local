from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QFrame, QLabel,
    QListWidgetItem, QSizePolicy, QMenu
)
from PySide6.QtCore import Qt, QSize, QTimer, Signal, QThread
from PySide6.QtGui import QFont, QIcon, QColor, QPixmap

from qfluentwidgets import (
    PrimaryPushButton, PushButton, TransparentToolButton,
    LineEdit, SwitchButton, ListWidget, ScrollArea,
    FluentIcon as FIF, Action, RoundMenu
)

from gui.components.message_bubble import MessageBubble
from gui.components import ThinkingExpander
from gui.components.camera_preview import CameraLiveWidget
from core.history import history_manager


class ChatTab(QWidget):
    """
    Chat Tab Component using Fluent Widgets.
    Contains the Session List (Sidebar) and Chat Area.
    """
    
    # Signals to communicate with MainWindow/Handlers
    send_message_requested = Signal(str)
    stop_generation_requested = Signal()
    tts_toggled = Signal(bool)
    new_chat_requested = Signal()
    session_selected = Signal(str)
    vision_requested = Signal()

    # Session handling signals
    session_pin_requested = Signal(str)
    session_rename_requested = Signal(str, str)
    session_delete_requested = Signal(str)

    def __init__(self):
        super().__init__()
        self.setObjectName("ChatTab")
        self._setup_ui()
        self._connect_internal_signals()

    def _setup_ui(self):
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # --- Sidebar (Session List) ---
        self.sidebar = QFrame()
        self.sidebar.setObjectName("sidebar")
        self.sidebar.setFixedWidth(300)
        self.sidebar.setStyleSheet("background-color: transparent; border-right: 1px solid rgba(255, 255, 255, 0.05);")
        
        sidebar_layout = QVBoxLayout(self.sidebar)
        sidebar_layout.setContentsMargins(10, 10, 10, 10)
        sidebar_layout.setSpacing(10)

        # New Chat Button
        self.new_chat_btn = PushButton(FIF.ADD, "New Chat")
        sidebar_layout.addWidget(self.new_chat_btn)

        # Session List
        self.session_list = ListWidget()
        self.session_list.setContextMenuPolicy(Qt.CustomContextMenu)
        self.session_list.customContextMenuRequested.connect(self._show_session_context_menu)
        # Transparent background for list
        self.session_list.setStyleSheet("background: transparent; border: none;")
        sidebar_layout.addWidget(self.session_list)

        layout.addWidget(self.sidebar)

        # --- Chat Content Area ---
        self.chat_content = QFrame()
        self.chat_content.setObjectName("chatContent")
        self.chat_content.setStyleSheet("background-color: transparent;")
        chat_layout = QVBoxLayout(self.chat_content)
        chat_layout.setContentsMargins(0, 0, 0, 0)
        chat_layout.setSpacing(0)

        # Header (Status + Toggle)
        header = QFrame()
        header.setFixedHeight(50)
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(20, 0, 20, 0)

        self.status_label = QLabel("Ready")
        self.status_label.setStyleSheet("color: #8a8a8a; font-size: 12px;")
        header_layout.addWidget(self.status_label)
        
        header_layout.addStretch()

        # TTS Toggle
        self.tts_toggle = SwitchButton()
        self.tts_toggle.setOnText("Voice On")
        self.tts_toggle.setOffText("Voice Off")
        header_layout.addWidget(self.tts_toggle)

        chat_layout.addWidget(header)

        # Chat Scroll Area
        self.chat_scroll = ScrollArea()
        self.chat_scroll.setWidgetResizable(True)
        self.chat_scroll.setStyleSheet("background: transparent; border: none;")
        # Remove white background of scroll view
        self.chat_scroll.viewport().setStyleSheet("background: transparent;")

        self.chat_container = QWidget()
        self.chat_container.setStyleSheet("background: transparent;")
        self.chat_container_layout = QVBoxLayout(self.chat_container)
        self.chat_container_layout.setContentsMargins(20, 10, 20, 10)
        self.chat_container_layout.setSpacing(15)
        self.chat_container_layout.addStretch()

        self.chat_scroll.setWidget(self.chat_container)
        chat_layout.addWidget(self.chat_scroll)

        # Input Bar
        input_bar = QFrame()
        input_bar.setFixedHeight(80)
        input_bar.setStyleSheet("background-color: transparent; border-top: 1px solid rgba(255, 255, 255, 0.05);")
        
        input_layout = QHBoxLayout(input_bar)
        input_layout.setContentsMargins(20, 10, 20, 20)
        input_layout.setSpacing(10)

        self.user_input = LineEdit()
        self.user_input.setPlaceholderText("Ask generic anything...")
        self.user_input.setClearButtonEnabled(True)
        self.user_input.setFixedHeight(40)
        input_layout.addWidget(self.user_input, 1)

        self.camera_btn = TransparentToolButton(FIF.CAMERA, self)
        self.camera_btn.setToolTip("Capturer & décrire (vision)")
        self.camera_btn.setFixedSize(40, 40)
        input_layout.addWidget(self.camera_btn)

        self.stop_btn = PrimaryPushButton(FIF.CLOSE, "Stop")
        self.stop_btn.setVisible(False)
        self.stop_btn.setFixedWidth(100)
        input_layout.addWidget(self.stop_btn)

        self.send_btn = PrimaryPushButton(FIF.SEND, "Send")
        self.send_btn.setFixedWidth(100)
        input_layout.addWidget(self.send_btn)

        chat_layout.addWidget(input_bar)

        layout.addWidget(self.chat_content)

    def _connect_internal_signals(self):
        """Connect internal UI events to public signals."""
        self.new_chat_btn.clicked.connect(self.new_chat_requested.emit)
        self.send_btn.clicked.connect(self._on_send_clicked)
        self.user_input.returnPressed.connect(self._on_send_clicked)
        self.stop_btn.clicked.connect(self.stop_generation_requested.emit)
        self.tts_toggle.checkedChanged.connect(self.tts_toggled.emit)
        self.session_list.itemClicked.connect(self._on_session_clicked)
        self.camera_btn.clicked.connect(self._on_camera_clicked)

    def _on_camera_clicked(self):
        """Open live webcam preview panel in the chat area."""
        self.camera_btn.setEnabled(False)
        self._live_widget = CameraLiveWidget()
        self._live_widget.captured.connect(self._on_live_captured)
        self._live_widget.closed.connect(self._on_live_closed)

        # Insert live widget above the input bar (before last stretch)
        count = self.chat_container_layout.count()
        self.chat_container_layout.insertWidget(count - 1, self._live_widget)
        QTimer.singleShot(50, self.scroll_to_bottom)

    def _on_live_captured(self, jpg_bytes: bytes):
        """User clicked Capture — close live widget, show frozen frame, start analysis."""
        import base64

        # Remove live widget immediately
        if hasattr(self, "_live_widget") and self._live_widget:
            self._live_widget.deleteLater()
            self._live_widget = None

        img_b64 = base64.b64encode(jpg_bytes).decode("utf-8")
        self._add_vision_preview(img_b64)
        self.set_status("🤔 Analyse en cours…")

        self._vision_thread = _VisionThread(jpg_bytes)
        self._vision_thread.done.connect(self._on_vision_done)
        self._vision_thread.start()

    def _on_live_closed(self):
        """User closed the preview without capturing."""
        self.camera_btn.setEnabled(True)
        self.set_status("Ready")
        if hasattr(self, "_live_widget") and self._live_widget:
            self._live_widget = None

    def _on_vision_done(self, description: str):
        self.camera_btn.setEnabled(True)
        self.set_status("Ready")
        if description:
            self.add_message_bubble("assistant", description)

    def _on_send_clicked(self):
        text = self.user_input.text()
        if text.strip():
            self.send_message_requested.emit(text)

    def _on_session_clicked(self, item: QListWidgetItem):
        session_id = item.data(Qt.UserRole)
        if session_id:
            self.session_selected.emit(session_id)

    # --- Public API for Controller/MainWindow ---

    def set_status(self, text: str):
        """Update status label."""
        QTimer.singleShot(0, lambda: self.status_label.setText(text))

    def clear_input(self):
        self.user_input.clear()

    def set_generating_state(self, is_generating: bool):
         """Switch states."""
         self.send_btn.setVisible(not is_generating)
         self.stop_btn.setVisible(is_generating)
         self.user_input.setEnabled(not is_generating)
         if not is_generating:
             self.user_input.setFocus()

    def add_message_bubble(self, role: str, text: str, is_thinking: bool = False):
        """Add a bubble."""
        # Note: MessageBubble might need updates to look good on transparent background
        bubble = MessageBubble(role, text, is_thinking)
        
        wrapper = QWidget()
        wrapper.setStyleSheet("background: transparent;")
        wrapper_layout = QHBoxLayout(wrapper)
        wrapper_layout.setContentsMargins(0, 0, 0, 0)
        
        if role == "user":
            wrapper_layout.addStretch()
            wrapper_layout.addWidget(bubble)
        else:
            wrapper_layout.addWidget(bubble)
            wrapper_layout.addStretch()
        
        # Insert before stretch (last item)
        count = self.chat_container_layout.count()
        self.chat_container_layout.insertWidget(count - 1, wrapper)
        
        QTimer.singleShot(50, self.scroll_to_bottom)

    def add_streaming_widgets(self, thinking_ui, search_indicator, response_bubble):
        """Add streaming widgets."""
        wrapper = QWidget()
        wrapper.setStyleSheet("background: transparent;")
        wrapper_layout = QVBoxLayout(wrapper)
        wrapper_layout.setContentsMargins(0, 0, 0, 0)
        wrapper_layout.setSpacing(8)
        
        wrapper_layout.addWidget(thinking_ui)
        wrapper_layout.addWidget(search_indicator)
        
        bubble_wrapper = QWidget()
        bubble_wrapper.setStyleSheet("background: transparent;")
        bubble_layout = QHBoxLayout(bubble_wrapper)
        bubble_layout.setContentsMargins(0, 0, 0, 0)
        bubble_layout.addWidget(response_bubble)
        bubble_layout.addStretch()
        wrapper_layout.addWidget(bubble_wrapper)
        
        count = self.chat_container_layout.count()
        self.chat_container_layout.insertWidget(count - 1, wrapper)
        
        QTimer.singleShot(50, self.scroll_to_bottom)

    def clear_chat_display(self):
        """Clear chat."""
        # Keep only the last stretch item
        while self.chat_container_layout.count() > 1:
            item = self.chat_container_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

    def scroll_to_bottom(self):
        scrollbar = self.chat_scroll.verticalScrollBar()
        scrollbar.setValue(scrollbar.maximum())

    def refresh_sidebar(self, current_session_id: str = None):
        """Refresh sidebar list."""
        self.session_list.clear()
        sessions = history_manager.get_sessions()
        
        for sess in sessions:
            title = sess['title']
            sid = sess['id']
            is_pinned = sess.get('pinned', False)
            is_current = sid == current_session_id
            
            # Use standard QListWidgetItem but maybe with custom text/icon
            # Fluent ListWidget generally handles text well
            
            item = QListWidgetItem(title)
            item.setData(Qt.UserRole, sid)
            
            if is_pinned:
                item.setIcon(FIF.PIN.icon())
            else:
                item.setIcon(FIF.CHAT.icon())
                
            self.session_list.addItem(item)
            if is_current:
                self.session_list.setCurrentItem(item)

    def _show_session_context_menu(self, position):
        item = self.session_list.itemAt(position)
        if not item: return
        session_id = item.data(Qt.UserRole)
        if not session_id: return

        menu = RoundMenu(parent=self)
        
        menu.addAction(Action(FIF.PIN, "Pin/Unpin", triggered=lambda: self.session_pin_requested.emit(session_id)))
        menu.addAction(Action(FIF.EDIT, "Rename", triggered=lambda: self._prompt_rename(session_id)))
        menu.addSeparator()
        menu.addAction(Action(FIF.DELETE, "Delete", triggered=lambda: self.session_delete_requested.emit(session_id)))
        
        menu.exec(self.session_list.mapToGlobal(position))

    def _prompt_rename(self, session_id):
        from PySide6.QtWidgets import QInputDialog
        new_title, ok = QInputDialog.getText(self, "Rename Chat", "Enter new name:")
        if ok and new_title.strip():
            self.session_rename_requested.emit(session_id, new_title.strip())

    def _add_vision_preview(self, img_b64: str):
        """Show a small preview of the captured webcam image in the chat."""
        try:
            import base64
            raw = base64.b64decode(img_b64)
            pixmap = QPixmap()
            pixmap.loadFromData(raw)
            if pixmap.isNull():
                return
            pixmap = pixmap.scaledToWidth(320, Qt.SmoothTransformation)

            lbl = QLabel()
            lbl.setPixmap(pixmap)
            lbl.setStyleSheet("border-radius: 8px;")

            wrapper = QWidget()
            wrapper.setStyleSheet("background: transparent;")
            row = QHBoxLayout(wrapper)
            row.setContentsMargins(0, 0, 0, 0)
            row.addStretch()
            row.addWidget(lbl)

            count = self.chat_container_layout.count()
            self.chat_container_layout.insertWidget(count - 1, wrapper)
            QTimer.singleShot(50, self.scroll_to_bottom)
        except Exception as e:
            print(f"[ChatTab] Vision preview error: {e}")


class _VisionThread(QThread):
    """Sends a pre-captured JPEG frame to the vision model and emits the description."""
    done = Signal(str)

    def __init__(self, jpg_bytes: bytes):
        super().__init__()
        self._jpg_bytes = jpg_bytes

    def run(self):
        try:
            import base64
            from core.vision import _try_model, _vision_model, _VISION_MODEL_CASCADE
            from config import OLLAMA_URL

            img_b64 = base64.b64encode(self._jpg_bytes).decode("utf-8")
            base_url = OLLAMA_URL.rstrip("/")
            prompt = "Décris ce que tu vois en détail. Sois concis et précis."

            configured = _vision_model()
            models = [configured] + [m for m in _VISION_MODEL_CASCADE if m != configured]

            for m in models:
                text = _try_model(base_url, m, prompt, img_b64)
                if text:
                    self.done.emit(text)
                    return

            self.done.emit("Erreur : aucun modèle vision n'a pu répondre.")
        except Exception as e:
            self.done.emit(f"Erreur : {e}")

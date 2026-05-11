"""
CameraLiveWidget — live webcam preview with a Capture button.

Shows a ~15fps live feed from the webcam. Emits `captured(bytes)` with
the JPEG bytes of the frozen frame when the user clicks Capture.
"""

from PySide6.QtCore import Qt, QThread, Signal, QTimer
from PySide6.QtGui import QPixmap, QImage
from PySide6.QtWidgets import (
    QFrame, QVBoxLayout, QHBoxLayout, QLabel, QPushButton
)
from qfluentwidgets import PrimaryPushButton, TransparentToolButton, FluentIcon as FIF


class _CameraFeedThread(QThread):
    """Captures frames in a background thread and emits them as JPEG bytes."""
    frame_ready = Signal(bytes)

    def __init__(self, camera_index: int = 0):
        super().__init__()
        self.camera_index = camera_index
        self._running = False

    def run(self):
        try:
            import cv2
        except ImportError:
            return

        cap = cv2.VideoCapture(self.camera_index)
        if not cap.isOpened():
            return

        self._running = True
        try:
            while self._running:
                ret, frame = cap.read()
                if ret and frame is not None:
                    h, w = frame.shape[:2]
                    if w > 480:
                        scale = 480 / w
                        frame = cv2.resize(frame, (480, int(h * scale)),
                                           interpolation=cv2.INTER_AREA)
                    _, buf = cv2.imencode(".jpg", frame,
                                         [cv2.IMWRITE_JPEG_QUALITY, 75])
                    self.frame_ready.emit(bytes(buf))
                self.msleep(66)  # ~15 fps
        finally:
            cap.release()

    def stop(self):
        self._running = False
        self.quit()
        self.wait(2000)


class CameraLiveWidget(QFrame):
    """
    Live webcam preview panel.

    Signals:
        captured(bytes) — JPEG bytes of the frame at the moment of capture
        closed()        — user closed the preview without capturing
    """
    captured = Signal(bytes)
    closed = Signal()

    def __init__(self, camera_index: int = 0, parent=None):
        super().__init__(parent)
        self.camera_index = camera_index
        self._last_frame: bytes = b""
        self._feed_thread = _CameraFeedThread(camera_index)

        self._setup_ui()
        self._feed_thread.frame_ready.connect(self._on_frame)
        self._feed_thread.start()

    def _setup_ui(self):
        self.setStyleSheet(
            "CameraLiveWidget { background: #1a1a2e; border-radius: 12px; "
            "border: 1px solid rgba(255,255,255,0.08); }"
        )
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(8)

        # Video display label
        self.video_label = QLabel()
        self.video_label.setAlignment(Qt.AlignCenter)
        self.video_label.setMinimumSize(480, 270)
        self.video_label.setStyleSheet(
            "background: #000; border-radius: 8px;"
        )
        self.video_label.setText("Initialisation de la caméra…")
        layout.addWidget(self.video_label)

        # Buttons row
        btn_row = QHBoxLayout()
        btn_row.setSpacing(10)

        self.close_btn = TransparentToolButton(FIF.CLOSE, self)
        self.close_btn.setToolTip("Fermer")
        self.close_btn.setFixedSize(36, 36)
        self.close_btn.clicked.connect(self._on_close)
        btn_row.addWidget(self.close_btn)

        btn_row.addStretch()

        self.capture_btn = PrimaryPushButton(FIF.CAMERA, "Capturer & Analyser")
        self.capture_btn.setFixedHeight(36)
        self.capture_btn.setEnabled(False)
        self.capture_btn.clicked.connect(self._on_capture)
        btn_row.addWidget(self.capture_btn)

        layout.addLayout(btn_row)

    def _on_frame(self, jpg_bytes: bytes):
        self._last_frame = jpg_bytes
        pixmap = QPixmap()
        pixmap.loadFromData(jpg_bytes)
        if not pixmap.isNull():
            self.video_label.setPixmap(
                pixmap.scaled(self.video_label.size(),
                              Qt.KeepAspectRatio,
                              Qt.SmoothTransformation)
            )
            if not self.capture_btn.isEnabled():
                self.capture_btn.setEnabled(True)

    def _on_capture(self):
        if self._last_frame:
            self._stop_feed()
            # Freeze last frame
            pixmap = QPixmap()
            pixmap.loadFromData(self._last_frame)
            if not pixmap.isNull():
                self.video_label.setPixmap(
                    pixmap.scaled(self.video_label.size(),
                                  Qt.KeepAspectRatio,
                                  Qt.SmoothTransformation)
                )
            self.capture_btn.setEnabled(False)
            self.capture_btn.setText("Analyse en cours…")
            self.captured.emit(self._last_frame)

    def _on_close(self):
        self._stop_feed()
        self.closed.emit()
        self.deleteLater()

    def _stop_feed(self):
        if self._feed_thread.isRunning():
            self._feed_thread.stop()

    def closeEvent(self, event):
        self._stop_feed()
        super().closeEvent(event)

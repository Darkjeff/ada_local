"""
Pocket AI - Main Entry Point
"""

import os

# Must be set BEFORE any tokenizers/HuggingFace/loky import to prevent
# semaphore leaks and segfault at shutdown caused by loky process pool.
os.environ["TOKENIZERS_PARALLELISM"] = "false"
os.environ["LOKY_MAX_CPU_COUNT"] = "1"

import warnings
import sys

# Suppress ALL warnings globally before any other imports
warnings.simplefilter("ignore")

from PySide6.QtCore import QSize
from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QFont, QColor, QIcon
from gui.app import MainWindow
from qfluentwidgets import qconfig, Theme, SplashScreen
import threading

if __name__ == "__main__":
    # Initialize persistent memory store before UI starts
    from core.memory_store import memory_store
    memory_store.initialize()

    # Start nightly memory consolidation scheduler (runs at 3:00 AM)
    from core.memory_consolidator import start_nightly_scheduler
    start_nightly_scheduler(hour=3)

    # Start Telegram adapter (no-op if disabled or no token)
    from core.telegram_adapter import telegram_adapter
    telegram_adapter.start()

    app = QApplication(sys.argv)
    
    # Configure Aura Theme
    qconfig.theme = Theme.DARK
    
    # Set default font
    app.setFont(QFont("Segoe UI", 10))
    
    # Create SplashScreen
    splash = SplashScreen(QIcon("gui/assets/logo.png" if "gui/assets/logo.png" else None), None)
    splash.setIconSize(QSize(100, 100))
    splash.show()
    
    # Pre-load semantic router in background (doesn't block UI)
    def _warmup_router():
        try:
            from core.semantic_router import warmup
            warmup()
        except Exception as e:
            print(f"[SemanticRouter] Warmup failed: {e}")
    threading.Thread(target=_warmup_router, daemon=True).start()

    # Create main window
    window = MainWindow()
    
    # Show window and finish splash
    window.show()
    splash.finish()
    
    sys.exit(app.exec())

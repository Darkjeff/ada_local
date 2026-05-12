"""
Pocket AI - Main Entry Point
"""

import os

# Must be set BEFORE any tokenizers/HuggingFace/loky import to prevent
# semaphore leaks and segfault at shutdown caused by loky process pool.
os.environ["TOKENIZERS_PARALLELISM"] = "false"
os.environ["LOKY_MAX_CPU_COUNT"] = "1"
os.environ["OMP_NUM_THREADS"] = "1"
os.environ["MKL_NUM_THREADS"] = "1"

import warnings
import sys
import traceback

# Debug: intercept loky executor creation to find the culprit.
# Prints a stack trace every time a loky process pool is spawned.
try:
    from joblib.externals.loky import process_executor as _loky_pe
    _orig_call = _loky_pe._ReusablePoolExecutor.__init__

    def _traced_init(self, *args, **kwargs):
        print("\n[LOKY DEBUG] Process pool created from:")
        traceback.print_stack()
        _orig_call(self, *args, **kwargs)

    _loky_pe._ReusablePoolExecutor.__init__ = _traced_init
except Exception as _e:
    print(f"[LOKY DEBUG] Could not patch: {_e}")

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

    # Start morning briefing scheduler (no-op if disabled)
    from core.morning_briefing import start_morning_scheduler
    from core.settings_store import settings as _settings
    start_morning_scheduler(hour=_settings.get("briefing.hour", 7))

    app = QApplication(sys.argv)
    
    # Configure Aura Theme
    qconfig.theme = Theme.DARK
    
    # Set default font
    app.setFont(QFont("Segoe UI", 10))
    
    # Create SplashScreen
    splash = SplashScreen(QIcon("gui/assets/logo.png" if "gui/assets/logo.png" else None), None)
    splash.setIconSize(QSize(100, 100))
    splash.show()
    
    # Warm up keyword router (instant, no ML)
    from core.semantic_router import warmup
    warmup()

    # Create main window
    window = MainWindow()
    
    # Show window and finish splash
    window.show()
    splash.finish()
    
    sys.exit(app.exec())

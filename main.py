"""
Pocket AI - Main Entry Point
"""

import os
import faulthandler

# Print C stack trace on segfault — gives us the actual crash location
faulthandler.enable()

# Must be set BEFORE any tokenizers/HuggingFace/loky import to prevent
# semaphore leaks and segfault at shutdown caused by loky process pool.
os.environ["TOKENIZERS_PARALLELISM"] = "false"      # no parallel tokenizers workers
os.environ["JOBLIB_MULTIPROCESSING"] = "0"           # disable loky pool entirely
os.environ["LOKY_MAX_CPU_COUNT"] = "1"               # hard cap if loky is still used
os.environ["OMP_NUM_THREADS"] = "1"
os.environ["MKL_NUM_THREADS"] = "1"
os.environ["NUMEXPR_NUM_THREADS"] = "1"
os.environ["PYTORCH_NO_CUDA_MEMORY_CACHING"] = "1"  # reduce CUDA cleanup semaphores

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

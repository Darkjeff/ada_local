"""
Pocket AI - Main Entry Point
"""

import os
import faulthandler
import multiprocessing

# Print C stack trace on segfault — gives us the actual crash location
faulthandler.enable()

# RealtimeSTT spawns multiprocessing subprocesses for transcription.
# On Linux the default start method is "fork", which copies Qt/CUDA/PyAudio
# state into the child and causes a segfault in the main thread.
# "spawn" starts a clean Python interpreter instead, avoiding the crash.
multiprocessing.set_start_method("spawn", force=True)

# Must be set BEFORE any tokenizers/HuggingFace/loky import to prevent
# semaphore leaks and segfault at shutdown caused by loky process pool.
# WebEngine / Chromium — disable GPU rendering (required for RDP / headless environments)
os.environ["QTWEBENGINE_CHROMIUM_FLAGS"] = (
    "--no-sandbox --disable-gpu --disable-software-rasterizer "
    "--disable-gpu-compositing --disable-gpu-sandbox "
    "--disable-dev-shm-usage --single-process"
)
os.environ["QTWEBENGINE_DISABLE_SANDBOX"] = "1"

os.environ["TOKENIZERS_PARALLELISM"] = "false"      # no parallel tokenizers workers
os.environ["JOBLIB_MULTIPROCESSING"] = "0"           # disable loky pool entirely
os.environ["LOKY_MAX_CPU_COUNT"] = "1"               # hard cap if loky is still used
os.environ["OMP_NUM_THREADS"] = "1"
os.environ["MKL_NUM_THREADS"] = "1"
os.environ["NUMEXPR_NUM_THREADS"] = "1"
os.environ["PYTORCH_NO_CUDA_MEMORY_CACHING"] = "1"  # reduce CUDA cleanup semaphores
os.environ["PYTHONWARNINGS"] = "ignore::UserWarning"  # suppress resource_tracker semaphore warning in subprocesses

# PyAudio / PortAudio stability on Linux
# PA_ALSA_PLUGHW=1  : use ALSA plug layer (avoids direct hw format mismatches that segfault)
# AUDIODEV=default  : fallback to system default device if PA_ALSA_PLUGHW is ignored
os.environ.setdefault("PA_ALSA_PLUGHW", "1")
os.environ.setdefault("AUDIODEV", "default")

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

    # Start HA state watcher — fires callbacks on entity state changes
    from core.ha_state_watcher import ha_state_watcher
    ha_state_watcher.start()

    # Door alert: send Telegram message when door sensor opens
    def _on_door_open(entity_id: str, state: str) -> None:
        if not _settings.get("home_assistant.door_alert_enabled", False):
            return
        msg = _settings.get("home_assistant.door_message", "🚪 Ciel un client !")
        try:
            telegram_adapter.notify_owner(msg)
        except Exception as e:
            print(f"[DoorAlert] Telegram send failed: {e}")

    _door_entity = _settings.get("home_assistant.door_entity", "")
    if _door_entity:
        ha_state_watcher.subscribe(_door_entity, ["on"], _on_door_open)

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
